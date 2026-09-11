"""Offline tests for the Antigravity sitemap adapter (mirror.sources.antigravity).

Every test uses the scripted fake HTTP client from ``conftest`` (the same
pattern as ``tests/test_adapters.py``): no real network access, each ``get``
pops the next scripted response. What is pinned down here is the *filtering
and safety* behavior of the adapter -- the parts where a bug silently drops
pages or deletes mirrored files -- plus the mapping of `.md` twin URLs, the
rewriting of the site-absolute links the published Markdown carries, and the
version probing that decides what the manifest reports.
"""

from __future__ import annotations

import subprocess
import time

import pytest
from conftest import _FakeClient, _Resp
from mirror.core import fetch
from mirror.core.page import Page
from mirror.sources import antigravity as ag

# A minimal sitemap exercising every discovery rule: CLI pages at two nesting
# levels, a sibling tree sharing the "cli" string prefix, non-CLI URLs, a
# duplicate entry, and entries carrying a query string / fragment.
_SITEMAP = """<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url><loc>https://antigravity.google</loc></url>
  <url><loc>https://antigravity.google/blog/introducing-antigravity-cli</loc></url>
  <url><loc>https://antigravity.google/docs/agent-settings</loc></url>
  <url><loc>https://antigravity.google/docs/cli/overview</loc></url>
  <url><loc>https://antigravity.google/docs/cli/install?hl=1</loc></url>
  <url><loc>https://antigravity.google/docs/cli/commands/agents#usage</loc></url>
  <url><loc>https://antigravity.google/docs/cli/overview</loc></url>
  <url><loc>https://antigravity.google/docs/cli-tools/other</loc></url>
</urlset>
"""


def _discover(sitemap: str = _SITEMAP):
    """Discover pages from *sitemap* via a one-shot fake HTTP client (no network)."""
    return ag.discover(_FakeClient([_Resp(200, sitemap)]))


@pytest.fixture(autouse=True)
def _restore_known_slugs():
    """Snapshot and restore ``_KNOWN_SLUGS`` around every test in this module.

    The set is module-level state shared between the discovery hook and the
    link pass. A test that discovers pages, or that seeds the set to give the
    rewrite something to resolve against, would otherwise leave that state
    behind for every test that runs after it -- including the ones that assert
    on the set's exact contents.
    """
    saved = set(ag._KNOWN_SLUGS)
    yield
    ag._KNOWN_SLUGS.clear()
    ag._KNOWN_SLUGS.update(saved)


# --- discover(): sitemap -> slugs & .md endpoints ----------------------------


def test_discover_keeps_only_cli_tree_and_maps_slugs_groups():
    """Only ``/docs/cli/`` URLs become pages. The slug is the path after
    ``/docs/`` (the same on-disk layout the mirror has always used), the
    group is the slug's directory part, and ``source_id`` is the full slug
    (unique and stable, which is all rename detection needs). Each page's
    ``source_md_url`` is derived by appending ``.md`` to its canonical URL."""
    pages = _discover()
    by_slug = {p.slug: p for p in pages}
    assert set(by_slug) == {"cli/overview", "cli/install", "cli/commands/agents"}
    overview = by_slug["cli/overview"]
    assert overview.group == "cli"
    assert by_slug["cli/commands/agents"].group == "cli/commands"
    assert overview.source_id == "cli/overview"
    assert overview.source_url == "https://antigravity.google/docs/cli/overview"
    assert overview.source_md_url == "https://antigravity.google/docs/cli/overview.md"


def test_discover_excludes_sibling_prefix_paths():
    """The prefix filter must be segment-level: ``/docs/cli-tools/other``
    shares the ``/docs/cli`` string prefix but is a different tree, and a
    raw ``startswith("/docs/cli")`` would wrongly mirror it. The trailing
    slash in ``CLI_PREFIX`` is what excludes it."""
    pages = _discover()
    assert all(p.slug.startswith("cli/") for p in pages)
    assert "cli-tools/other" not in {p.slug for p in pages}


def test_discover_excludes_urls_from_foreign_hosts():
    """A sitemap URL on a different host whose PATH still starts with
    ``/docs/cli/`` must be excluded: the path filter alone (``urlsplit``
    splits host and path apart) would happily mirror a page from an origin
    this adapter does not control. The origin boundary (``clean`` must equal
    ``SITE_URL`` or start with ``SITE_URL + "/"``) rejects both an
    attacker-style lookalike domain and a sibling subdomain."""
    sitemap = """<urlset>
      <url><loc>https://antigravity.google/docs/cli/overview</loc></url>
      <url><loc>https://antigravity.google.evil.example/docs/cli/malware</loc></url>
      <url><loc>https://blog.antigravity.google/docs/cli/other</loc></url>
    </urlset>
    """
    pages = _discover(sitemap)
    assert [p.slug for p in pages] == ["cli/overview"]


def test_discover_strips_query_and_fragment():
    """Sitemap URLs carrying a query string (``?hl=1``) or fragment
    (``#usage``) must have them stripped before the slug is derived:
    otherwise "?"/"#" would leak into the slug and ``Page.__post_init__``
    would reject it."""
    pages = _discover()
    by_slug = {p.slug: p for p in pages}
    assert by_slug["cli/install"].source_url == (
        "https://antigravity.google/docs/cli/install"
    )
    assert by_slug["cli/install"].source_md_url == (
        "https://antigravity.google/docs/cli/install.md"
    )
    assert by_slug["cli/commands/agents"].source_url == (
        "https://antigravity.google/docs/cli/commands/agents"
    )
    assert by_slug["cli/commands/agents"].source_md_url == (
        "https://antigravity.google/docs/cli/commands/agents.md"
    )


def test_discover_skips_entry_with_invalid_slug_characters(capsys):
    """A sitemap URL whose PATH contains characters outside the slug
    alphabet (a space here; urlsplit cleaning only strips query/fragment)
    is rejected by ``Page.__post_init__``. That single odd entry must be
    skipped with a stderr warning -- not abort discovery for the whole
    source, which would mirror nothing at all. The remaining valid entries
    are still discovered."""
    sitemap = """<urlset>
      <url><loc>https://antigravity.google/docs/cli/overview</loc></url>
      <url><loc>https://antigravity.google/docs/cli/bad slug</loc></url>
      <url><loc>https://antigravity.google/docs/cli/install</loc></url>
    </urlset>
    """
    pages = _discover(sitemap)
    assert {p.slug for p in pages} == {"cli/overview", "cli/install"}
    assert "bad slug" in capsys.readouterr().err


def test_discover_dedupes_and_sorts():
    """The sitemap lists ``/docs/cli/overview`` twice; mirroring it twice
    would collide on the same output file, so duplicates collapse to one
    page. The result is sorted by slug for deterministic diffs against the
    previous manifest.

    Asserting the EXACT expected slug list pins both properties at once --
    the duplicate overview collapses to a single entry, and the sort order
    is the slug order."""
    pages = _discover()
    slugs = [p.slug for p in pages]
    assert slugs == ["cli/commands/agents", "cli/install", "cli/overview"]


def test_discover_normalises_trailing_slash_variants_and_cli_root():
    """Sitemap entries with a trailing slash must normalise BEFORE the slug
    is derived: ``/docs/cli/overview/`` must dedupe against
    ``/docs/cli/overview`` (a slug derived from the unstripped path would be
    ``cli/overview/``, which ``Page.__post_init__`` rejects, sending the
    entry to the skip path with a spurious warning instead of collapsing the
    duplicate). The CLI landing page itself (``/docs/cli/``, which normalises
    to ``/docs/cli``) must be discovered as the single-segment slug ``cli``
    with the ``root`` group, not dropped."""
    sitemap = """<urlset>
      <url><loc>https://antigravity.google/docs/cli/</loc></url>
      <url><loc>https://antigravity.google/docs/cli/overview</loc></url>
      <url><loc>https://antigravity.google/docs/cli/overview/</loc></url>
    </urlset>
    """
    pages = _discover(sitemap)
    by_slug = {p.slug: p for p in pages}
    assert set(by_slug) == {"cli", "cli/overview"}
    assert by_slug["cli"].group == "root"
    assert by_slug["cli"].source_url == "https://antigravity.google/docs/cli"
    assert by_slug["cli"].source_md_url == "https://antigravity.google/docs/cli.md"


def test_discover_raises_on_empty_sitemap():
    """A sitemap with no ``<loc>`` entries at all (moved, emptied, or
    replaced by an error page upstream) must raise instead of discovering
    zero pages -- an empty result would make the pipeline delete every
    mirrored file."""
    sitemap = """<?xml version="1.0"?><urlset></urlset>"""
    with pytest.raises(RuntimeError, match="zero-page"):
        _discover(sitemap)


def test_discover_raises_when_cli_prefix_filters_everything():
    """If no sitemap URL survives the ``/docs/cli/`` filter (e.g. the CLI
    docs moved to a different path upstream), discovery must raise instead
    of returning [] -- an empty result would make the pipeline delete every
    mirrored Antigravity page."""
    sitemap = """<urlset>
      <url><loc>https://antigravity.google/blog/post</loc></url>
      <url><loc>https://antigravity.google/docs/agent-settings</loc></url>
    </urlset>
    """
    with pytest.raises(RuntimeError, match="zero-page"):
        _discover(sitemap)


def test_discover_surfaces_fetch_error_on_404():
    """A 404 on the sitemap fetch must surface as a ``FetchError`` carrying
    the structured status code -- not as a downstream parse error or the
    zero-page RuntimeError, which would misdiagnose a fetch failure as an
    upstream restructure. 404 is non-transient, so exactly one request is
    made."""
    client = _FakeClient([_Resp(404)])
    with pytest.raises(fetch.FetchError) as exc_info:
        ag.discover(client)
    assert exc_info.value.status_code == 404
    assert client.calls == 1  # fail-fast: a 404 is never retried


def test_discover_publishes_the_slug_set_for_link_rewriting():
    """``discover`` must leave the run's slugs in ``_KNOWN_SLUGS``, which is
    what the link pass consults: a reference can only be pointed at a
    mirrored file when the mirror actually holds that file. The set is
    REPLACED, never added to, so a slug that disappeared upstream stops
    being a rewrite target on the very next run."""
    ag._KNOWN_SLUGS.update({"stale/from-an-earlier-run"})
    _discover()
    assert ag._KNOWN_SLUGS == {"cli/overview", "cli/install", "cli/commands/agents"}


# --- get_version: local binary probing and fallback ---------------------------


def _fake_run(*, returncode: int = 0, stdout: str = "", error: Exception | None = None):
    """Build a ``subprocess.run`` stand-in returning (or raising) *error*."""

    def run(*args, **kwargs):
        if error is not None:
            raise error
        return subprocess.CompletedProcess(
            args=(), returncode=returncode, stdout=stdout, stderr=""
        )

    return run


def test_get_version_reads_the_installed_cli(monkeypatch):
    """A successful ``--version`` probe supplies the version, with the
    command's surrounding noise stripped off by the shared extractor."""
    monkeypatch.setattr("shutil.which", lambda _: "/home/user/.local/bin/agy")
    monkeypatch.setattr("subprocess.run", _fake_run(stdout="agy version 1.2.0\n"))
    assert ag.get_version(_FakeClient([])) == "1.2.0"


def test_get_version_probes_the_antigravity_executable_alias(monkeypatch):
    """``agy`` and ``antigravity`` are two names for the same executable and
    either may be the one on ``PATH``, so the probe must try both -- and try
    ``agy`` first, the canonical name."""
    probed: list[str] = []

    def which(name: str) -> str | None:
        probed.append(name)
        return "/usr/local/bin/antigravity" if name == "antigravity" else None

    monkeypatch.setattr("shutil.which", which)
    monkeypatch.setattr("subprocess.run", _fake_run(stdout="1.4.2\n"))
    assert ag.get_version(_FakeClient([])) == "1.4.2"
    assert probed == ["agy", "antigravity"]


@pytest.mark.parametrize(
    ("case", "run"),
    [
        ("non-zero return code", _fake_run(returncode=1, stdout="1.2.0\n")),
        ("empty stdout", _fake_run(stdout="   \n")),
        (
            "stdout with nothing a version can be read from",
            _fake_run(stdout="v\n"),
        ),
        ("subprocess failure", _fake_run(error=subprocess.SubprocessError("boom"))),
        ("executable is not runnable", _fake_run(error=OSError("not executable"))),
    ],
)
def test_get_version_falls_back_when_the_probe_yields_nothing(
    monkeypatch, case: str, run
):
    """Every unusable probe result -- a failing exit status, empty output,
    output a version cannot be read from (non-empty, but with nothing left
    once the extractor has stripped it), or the process failing outright --
    must fall back to ``CONFIG.version`` rather than raising. The version is
    display metadata: a broken local installation must not be able to abort
    a mirror run that has nothing else to do with it."""
    monkeypatch.setattr("shutil.which", lambda _: "/usr/local/bin/agy")
    monkeypatch.setattr("subprocess.run", run)
    assert ag.get_version(_FakeClient([])) == ag.CONFIG.version, case


def test_get_version_falls_back_when_the_binary_is_absent(monkeypatch):
    """No ``agy`` / ``antigravity`` on ``PATH`` means no probe at all, and the
    configured fallback is returned without ever spawning a process."""
    monkeypatch.setattr("shutil.which", lambda _: None)

    def explode(*args, **kwargs):
        raise AssertionError("no process may be spawned without a binary")

    monkeypatch.setattr("subprocess.run", explode)
    assert ag.get_version(_FakeClient([])) == ag.CONFIG.version


# --- Link rewriting: site-absolute ``/docs/...`` references -------------------


def _page(slug: str) -> Page:
    """Build a real ``Page`` for the ``fetch_markdown`` tests."""
    return Page(
        slug=slug,
        source_url=f"{ag.SITE_URL}/docs/{slug}",
        source_md_url=f"{ag.SITE_URL}/docs/{slug}.md",
        source_id=slug,
        group=slug.rsplit("/", 1)[0] if "/" in slug else "root",
    )


def _rewrite(text: str, slug: str = "cli/reference") -> str:
    """Rewrite *text* against a small, explicit set of mirrored slugs."""
    known = {
        "cli",
        "cli/install",
        "cli/reference",
        "cli/commands/agents",
        "cli/statusline",
    }
    return ag._rewrite_docs_links(text, slug, known)


def test_rewrite_docs_links_points_mirrored_targets_at_the_local_file():
    """A ``/docs/...`` reference to a mirrored page becomes a relative ``.md``
    link: a leading ``/`` resolves against the reader's file system root, so
    the published form is dead in a checkout. ``cli/reference`` lives in
    ``cli/``, so a sibling target is one step away and a nested one is one
    step down."""
    text = "[Ref](/docs/cli/statusline) and [Agents](/docs/cli/commands/agents)\n"
    assert _rewrite(text) == (
        "[Ref](./statusline.md) and [Agents](./commands/agents.md)\n"
    )


def test_rewrite_docs_links_walks_up_from_a_nested_page():
    """The relative path is derived from the CURRENT page's directory, so a
    page nested under ``cli/commands/`` reaches a page at the top of the CLI
    tree with ``../`` rather than with a path that only works from the
    root."""
    assert _rewrite("[Ref](/docs/cli/reference)", "cli/commands/agents") == (
        "[Ref](../reference.md)"
    )


def test_rewrite_docs_links_preserves_anchors():
    """The fragment is resolved by the browser against whichever document the
    link lands on, so it must survive the rewrite verbatim -- dropping it
    would send the reader to the top of the right page instead of to the
    section the sentence is about."""
    assert _rewrite("[Keys](/docs/cli/statusline#available-json-fields)") == (
        "[Keys](./statusline.md#available-json-fields)"
    )


def test_rewrite_docs_links_preserves_trailing_slash_variants():
    """``/docs/cli/`` and ``/docs/cli`` name the same page, so both resolve
    to the same mirrored file instead of one of them falling back to the
    upstream URL. The path is relative to the page being rewritten, so a
    page inside ``cli/`` reaches the ``cli`` landing one level up."""
    assert _rewrite("[Landing](/docs/cli/)") == "[Landing](../cli.md)"
    assert _rewrite("[Landing](/docs/cli)") == "[Landing](../cli.md)"


def test_rewrite_docs_links_sends_unmirrored_targets_upstream():
    """The site documents far more than the CLI tree this source mirrors.
    A reference to a page outside the mirror scope must be sent to its
    upstream URL -- the only destination that still resolves -- rather than
    left as a dead site-absolute path or rewritten to a file that does not
    exist."""
    text = "[Boost](/docs/boost) and [Teams](/docs/teamwork)\n"
    assert _rewrite(text) == (
        "[Boost](https://antigravity.google/docs/boost) and "
        "[Teams](https://antigravity.google/docs/teamwork)\n"
    )


def test_rewrite_docs_links_keeps_the_anchor_on_the_upstream_fallback():
    """The upstream branch is a real page with real sections, so the fragment
    is carried over there too."""
    assert _rewrite("[MCP](/docs/mcp#antigravity-cli)") == (
        "[MCP](https://antigravity.google/docs/mcp#antigravity-cli)"
    )


def test_rewrite_docs_links_leaves_every_other_link_alone():
    """Only documentation links are touched: an external URL, an intra-page
    anchor, a relative path, an asset reference, and a destination that
    merely STARTS with ``/docs`` without being a path under it already
    resolve, and a pass that rewrote them would be breaking links to fix
    links."""
    text = (
        "[Site](https://antigravity.google/docs/cli/overview) "
        "[Other](https://example.com/docs/x) "
        "[Section](#usage) "
        "[Sibling](./features.md) "
        "[Near-miss](/docsomething) "
        "![Shot](../../assets/image/docs/cli/shot.png)\n"
    )
    assert _rewrite(text) == text


def test_rewrite_docs_links_skips_fenced_code_blocks():
    """A code sample that quotes a documentation URL is showing what a
    command or a config file looks like, not linking to a page: rewriting it
    would change what the sample says. The fenced block is shielded for the
    duration of the pass, and restored byte for byte."""
    text = (
        "See [Install](/docs/cli/install).\n"
        "\n"
        "```bash\n"
        "curl https://antigravity.google/docs/cli/install\n"
        "grep '](/docs/cli/install)' notes.md\n"
        "```\n"
        "\n"
        "Done.\n"
    )
    assert _rewrite(text) == (
        "See [Install](./install.md).\n"
        "\n"
        "```bash\n"
        "curl https://antigravity.google/docs/cli/install\n"
        "grep '](/docs/cli/install)' notes.md\n"
        "```\n"
        "\n"
        "Done.\n"
    )


def test_rewrite_docs_links_skips_a_fence_indented_inside_a_list_item():
    """A sample the upstream page writes inside a list item is indented by
    the list marker, and CommonMark still reads a fence indented up to three
    columns as a fence. Its content must therefore survive the pass
    untouched, exactly like a column-zero sample: the shared scanner the
    shield is built on only recognises column-zero fences, which left the
    ``](/docs/...)`` text quoted in such a sample exposed to the rewrite."""
    text = "- Install it:\n\n  ```bash\n  grep '](/docs/cli/install)' notes.md\n  ```\n"
    assert _rewrite(text) == text


def test_rewrite_docs_links_still_rewrites_prose_beside_an_indented_fence():
    """Shielding a sample must not shield the page around it: the prose link
    of the same list item is rewritten exactly like one outside a list, so
    widening the shield to indented fences costs no rewrite it should have
    made."""
    text = (
        "- See [Install](/docs/cli/install):\n"
        "\n"
        "  ```bash\n"
        "  grep '](/docs/cli/install)' notes.md\n"
        "  ```\n"
    )
    assert _rewrite(text) == (
        "- See [Install](./install.md):\n"
        "\n"
        "  ```bash\n"
        "  grep '](/docs/cli/install)' notes.md\n"
        "  ```\n"
    )


@pytest.mark.parametrize("indent", [0, 1, 2, 3, 4])
def test_iter_fence_spans_stops_at_the_commonmark_indent_limit(indent: int):
    """The widened shield stops exactly where CommonMark stops calling a
    fence a fence: up to three columns of indentation is a sample inside a
    list item, four is an indented code block whose ``` line renders as
    literal text. Shielding the latter would protect page content from the
    link pass that is supposed to rewrite it."""
    text = " " * indent + "```\nvalue\n" + " " * indent + "```\n"
    spans = list(ag._iter_fence_spans(text))
    assert bool(spans) is (indent <= 3)
    if spans:
        # The span covers the block from its fence character, leaving the
        # indentation outside it so the line keeps its column.
        assert text[spans[0][0] : spans[0][1]] == "```\nvalue\n" + " " * indent + "```"


def test_rewrite_docs_links_does_not_shield_an_indented_code_block():
    """Four columns of indentation is an indented code block, not a fence:
    CommonMark renders its ``` line as literal text, so a link written there
    is page content and is rewritten like any other prose. Treating it as a
    sample would leave a dead site-absolute link in the mirrored page."""
    text = "    ```\n    ](/docs/cli/install)\n    ```\n"
    assert _rewrite(text) == "    ```\n    ](./install.md)\n    ```\n"


def test_rewrite_docs_links_is_linear_on_unterminated_destinations():
    """A page of ``](/docs...`` candidates with no closing parenthesis
    anywhere must be scanned in linear time. The pattern's greedy
    destination class used to expand to end-of-string from every candidate,
    fail, and let the engine retry the whole scan from the next one --
    quadratic, several seconds on this input. The scan now stops at the
    first candidate that has no ``)`` after it, because no later candidate
    can have one either. The bound is far above the cost of the linear walk
    and far below the cost of the quadratic one, so it measures the shape of
    the scan rather than the speed of the machine it runs on."""
    text = "](/docs/a" * 8192  # ~72 KB: the quadratic form needed ~7 s for this
    started = time.perf_counter()
    assert _rewrite(text) == text
    elapsed = time.perf_counter() - started
    assert elapsed < 2.0, f"rewriting {len(text)} characters took {elapsed:.2f}s"


def test_rewrite_docs_links_is_idempotent():
    """The output holds relative ``.md`` links and absolute ``https://`` URLs,
    neither of which matches the site-absolute pattern, so a second
    application -- a re-run against a page already converted, a retried pass
    -- changes nothing."""
    text = "[A](/docs/cli/reference) [B](/docs/boost) [C](/docs/cli/)\n"
    once = _rewrite(text)
    assert _rewrite(once) == once
    assert once != text


def test_fetch_markdown_rewrites_links_and_hashes_the_result():
    """The pipeline hook fetches the published Markdown, rewrites its
    site-absolute links, and hashes what it returns -- the manifest hash must
    cover the text that is actually written, or an unchanged page would keep
    reporting a change."""
    ag._KNOWN_SLUGS.clear()
    ag._KNOWN_SLUGS.update({"cli/reference", "cli/install"})
    body = "# CLI reference\n\nSee [Install](/docs/cli/install).\n"
    md, digest = ag.fetch_markdown(
        _FakeClient([_Resp(200, body)]), _page("cli/reference")
    )
    assert "[Install](./install.md)" in md
    assert digest == fetch.content_hash(md)


def test_fetch_markdown_rejects_non_markdown():
    """The hook validates like the generic fetch path it replaces: a response
    that is not Markdown raises ``FetchError`` so the pipeline carries the
    previous manifest entry forward instead of writing garbage."""
    ag._KNOWN_SLUGS.clear()
    ag._KNOWN_SLUGS.update({"cli/reference"})
    client = _FakeClient([_Resp(200, "not markdown at all")])
    with pytest.raises(fetch.FetchError):
        ag.fetch_markdown(client, _page("cli/reference"))


def test_fetch_markdown_refuses_to_rewrite_links_without_discovered_slugs():
    """Rewriting with no discovered slug set would send every internal link to
    its upstream URL (see ``ensure_known_slugs``), so the hook fails loudly
    instead -- as a ``FetchError``, the one type the pipeline isolates per
    page rather than aborting the source. The refusal comes before the
    download, so a run that skipped discovery stops at the first page instead
    of fetching the whole source and then failing."""
    assert ag._KNOWN_SLUGS == set()
    client = _FakeClient([_Resp(200, "# Title\n\nEnough prose to be Markdown.\n")])
    with pytest.raises(fetch.FetchError, match="no discovered slugs"):
        ag.fetch_markdown(client, _page("cli/reference"))
    assert client.calls == 0


def test_fetch_markdown_wraps_a_rewrite_failure(monkeypatch):
    """An exception out of the rewrite pass is re-raised as ``FetchError``,
    naming the page and keeping the original on ``__cause__``. The pipeline
    isolates failures per page for that exception type only, so an unforeseen
    link shape must fail just this page instead of aborting the whole run."""
    page = _page("cli/reference")
    # The hook refuses to run without a discovered slug set (the link pass
    # cannot resolve anything without it), so the test seeds one to reach the
    # rewrite pass it is actually exercising.
    ag._KNOWN_SLUGS.clear()
    ag._KNOWN_SLUGS.update({"cli/reference"})

    def explode(text: str, current_slug: str, known_slugs=None) -> str:
        raise ValueError("unforeseen link shape")

    monkeypatch.setattr(ag, "_rewrite_docs_links", explode)
    client = _FakeClient([_Resp(200, "# Title\n\nProse.\n")])
    with pytest.raises(fetch.FetchError) as exc_info:
        ag.fetch_markdown(client, page)
    assert page.slug in str(exc_info.value)
    assert isinstance(exc_info.value.__cause__, ValueError)
