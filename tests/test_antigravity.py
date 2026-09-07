"""Offline tests for the Antigravity sitemap adapter (mirror.sources.antigravity).

Every test uses the scripted fake HTTP client from ``conftest`` (the same
pattern as ``tests/test_adapters.py``): no real network access, each ``get``
pops the next scripted response. What is pinned down here is the *filtering
and safety* behavior of the adapter -- the parts where a bug silently drops
pages or deletes mirrored files -- plus the mapping of `.md` twin URLs.
"""

from __future__ import annotations

import pytest
from conftest import _FakeClient, _Resp
from mirror.core import fetch
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
