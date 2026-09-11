"""Offline tests for the source adapters' discovery and conversion logic.

Every test uses a scripted fake HTTP client (the same pattern as
``tests/test_fetch.py``): no real network access, each ``get`` pops the next
scripted response. What is pinned down here is the *filtering and safety*
behavior of the adapters -- the parts where a bug silently drops pages or
deletes mirrored files.
"""

from __future__ import annotations

import re
import time

import pytest
from conftest import _FakeClient, _Resp, blob_entry, tree_client
from mirror.core import fetch
from mirror.core.page import Page
import mirror.sources
from mirror.sources import (
    antigravity,
    claude_code,
    codex_cli,
    deepseek,
    kimi_code,
    opencode,
)
from mirror.sources.base import clean_url, ensure_discovered_pages


# --- codex_cli / kimi_code: git-tree filtering ------------------------------


def test_codex_discover_keeps_only_direct_md_children_of_docs():
    """The Codex docs are a flat folder: only `.md` files directly under
    `docs/` may be discovered. Nested paths, non-Markdown files, files
    outside docs/, and directory entries must all be dropped -- accepting
    any of them would mirror unrelated repo content."""
    client = tree_client(
        [
            blob_entry("docs/config.md"),  # keep
            blob_entry("docs/getting-started.md"),  # keep
            blob_entry("docs/nested/thing.md"),  # drop: not a direct child
            blob_entry("docs/notes.txt"),  # drop: not Markdown
            blob_entry("src/main.py"),  # drop: outside docs/
            {"type": "tree", "path": "docs"},  # drop: directory entry
        ]
    )
    client._script.append(_Resp(200, ""))
    pages = codex_cli.discover(client)
    assert [p.slug for p in pages] == ["config", "getting-started"]
    assert all(p.group == "root" for p in pages)
    config = next(p for p in pages if p.slug == "config")
    assert config.source_md_url.endswith("/openai/codex/main/docs/config.md")
    assert config.source_id == "docs/config.md"


def test_kimi_discover_allows_nested_md_under_docs_en():
    """Unlike Codex, the Kimi docs tree is nested: every `.md` anywhere
    under `docs/en/` is kept, the slug is the path relative to `docs/en/`,
    and the first slug segment becomes the index group."""
    client = tree_client(
        [
            blob_entry("docs/en/index.md"),  # keep, group "root"
            blob_entry("docs/en/configuration/config-files.md"),  # keep, nested
            blob_entry("docs/en/notes.txt"),  # drop: not Markdown
            blob_entry("docs/de/anleitung.md"),  # drop: wrong locale tree
            {"type": "tree", "path": "docs/en"},  # drop: directory entry
        ]
    )
    pages = kimi_code.discover(client)
    assert [p.slug for p in pages] == ["configuration/config-files", "index"]
    by_slug = {p.slug: p for p in pages}
    assert by_slug["configuration/config-files"].group == "configuration"
    assert by_slug["index"].group == "root"
    assert by_slug["index"].source_md_url.endswith(
        "/MoonshotAI/kimi-code/main/docs/en/index.md"
    )


def test_codex_discover_dedupes_duplicate_tree_paths(capsys):
    """If the git-tree listing ever contains the same path twice (a malformed
    API response -- the slug IS the on-disk output path, so two ``Page``
    objects for it would fight over one mirrored file), only the FIRST entry
    may win. The later duplicate is skipped with a loud stderr warning
    naming both the slug and the skipped path, and the remaining pages are
    still discovered."""
    client = tree_client(
        [
            blob_entry("docs/config.md"),
            blob_entry("docs/config.md"),  # duplicate path: first entry wins
            blob_entry("docs/setup.md"),
        ]
    )
    client._script.append(_Resp(200, ""))
    pages = codex_cli.discover(client)
    assert [p.slug for p in pages] == ["config", "setup"]
    err = capsys.readouterr().err
    assert "warning" in err
    assert "duplicate slug" in err
    assert "'config'" in err
    assert "docs/config.md" in err


def test_kimi_discover_dedupes_duplicate_tree_paths(capsys):
    """Same duplicate-slug guard as the Codex adapter, pinned for the Kimi
    repo: if the git-tree listing ever contains the same path twice, only
    the FIRST entry may win (the slug IS the on-disk output path, so two
    ``Page`` objects for it would fight over one mirrored file). The later
    duplicate is skipped with a loud stderr warning naming both the slug
    and the skipped path, and the remaining pages are still discovered."""
    client = tree_client(
        [
            blob_entry("docs/en/index.md"),
            blob_entry("docs/en/index.md"),  # duplicate path: first entry wins
            blob_entry("docs/en/guide/setup.md"),
        ]
    )
    pages = kimi_code.discover(client)
    assert [p.slug for p in pages] == ["guide/setup", "index"]
    err = capsys.readouterr().err
    assert "warning" in err
    assert "duplicate slug" in err
    assert "'index'" in err
    assert "docs/en/index.md" in err


def test_kimi_discover_builds_published_page_urls():
    """The human-facing ``source_url`` is the page's published address on the
    docs site: one ``.html`` file per page at the mirrored path, so an
    ``index`` page resolves to that folder's landing page (``index.html``)
    rather than to a literal ``.../index`` URL that would 404. The slug
    itself is left untouched -- it keys the mirrored file layout and the
    manifest -- and every URL shares the configured base and suffix.

    One URL is pinned LITERALLY: asserting only ``f"{base}/..."``-shaped
    strings cannot catch a wrong base or suffix VALUE, because both sides of
    such an assertion move together with the constant. The literal is what
    keeps a mirrored page pointing at the address the docs site actually
    serves."""
    client = tree_client(
        [
            blob_entry("docs/en/index.md"),
            blob_entry("docs/en/guide/index.md"),
            blob_entry("docs/en/guide/setup.md"),
            blob_entry("docs/en/guides/web.md"),
        ]
    )
    pages = kimi_code.discover(client)
    by_slug = {p.slug: p for p in pages}
    base = kimi_code.SOURCE_URL_BASE
    suffix = kimi_code.SOURCE_URL_SUFFIX
    assert by_slug["index"].source_url == f"{base}/index{suffix}"
    assert by_slug["guide/index"].source_url == f"{base}/guide/index{suffix}"
    assert by_slug["guide/setup"].source_url == f"{base}/guide/setup{suffix}"
    assert (
        by_slug["guides/web"].source_url
        == "https://moonshotai.github.io/kimi-code/en/guides/web.html"
    )


def test_codex_discover_raises_on_truncated_tree():
    """A `"truncated": true` git-trees response must raise, not return a
    partial page list: incomplete discovery would make the pipeline delete
    the missing pages' mirrored files from disk. The error names the repo."""
    client = tree_client([blob_entry("docs/config.md")], truncated=True)
    with pytest.raises(RuntimeError, match="openai/codex"):
        codex_cli.discover(client)


def test_kimi_discover_raises_on_truncated_tree():
    """Same truncation guard as the Codex adapter, pinned for the Kimi repo:
    a capped tree listing is a loud RuntimeError naming the repo, never a
    silently incomplete discovery."""
    client = tree_client([blob_entry("docs/en/index.md")], truncated=True)
    with pytest.raises(RuntimeError, match="MoonshotAI/kimi-code"):
        kimi_code.discover(client)


# --- claude_code: sitemap -> slugs ------------------------------------------


def test_claude_code_discover_maps_en_urls_to_slugs_and_filters_rest():
    """Only URLs containing `/docs/en/` become pages; translations and
    off-site URLs are dropped. The slug is the path after `/docs/en/`, the
    group its first segment, and `source_md_url` is the `.md` twin of the
    canonical URL. Duplicate sitemap entries collapse to one page."""
    sitemap = """<?xml version="1.0" encoding="UTF-8"?>
    <urlset>
      <url><loc>https://code.claude.com/docs/en/overview</loc></url>
      <url><loc>https://code.claude.com/docs/en/agent-sdk/python</loc></url>
      <url><loc>https://code.claude.com/docs/en/overview</loc></url>
      <url><loc>https://code.claude.com/docs/fr/apercu</loc></url>
    </urlset>
    """
    pages = claude_code.discover(_FakeClient([_Resp(200, sitemap)]))
    by_slug = {p.slug: p for p in pages}
    assert by_slug["overview"].group == "root"
    assert by_slug["agent-sdk/python"].group == "agent-sdk"
    assert by_slug["overview"].source_md_url == (
        "https://code.claude.com/docs/en/overview.md"
    )
    assert by_slug["overview"].source_url == "https://code.claude.com/docs/en/overview"
    assert "apercu" not in by_slug  # translation filtered out
    assert len([p for p in pages if p.slug == "overview"]) == 1  # deduped


def test_claude_code_discover_mirrors_en_root_as_index():
    """The English tree's ROOT page (``/docs/en/``) is a real content page
    with a working ``.md`` twin, so it must be mirrored under the
    conventional slug ``"index"`` (group ``"root"``) rather than skipped.
    Both sitemap spellings -- ``/docs/en/`` and the bare ``/docs/en`` --
    normalise to the same canonical URL and therefore dedupe to a single
    page; a non-English root (``/docs/fr/``) is still filtered out."""
    sitemap = """<urlset>
      <url><loc>https://code.claude.com/docs/en/</loc></url>
      <url><loc>https://code.claude.com/docs/en</loc></url>
      <url><loc>https://code.claude.com/docs/fr/</loc></url>
      <url><loc>https://code.claude.com/docs/en/hooks</loc></url>
    </urlset>
    """
    pages = claude_code.discover(_FakeClient([_Resp(200, sitemap)]))
    # The two spellings of the root collapse to ONE "index" page, sorted
    # before "hooks".
    assert [p.slug for p in pages] == ["hooks", "index"]
    root = next(p for p in pages if p.slug == "index")
    assert root.group == "root"
    assert root.source_url == "https://code.claude.com/docs/en"
    assert root.source_md_url == "https://code.claude.com/docs/en.md"
    assert root.source_id == "index"


def test_claude_code_discover_skips_foreign_host_sitemap_entries():
    """A sitemap entry whose PATH starts with `/docs/en/` but whose HOST is
    not code.claude.com must be skipped: without the origin check the
    path-anchored filter alone would mirror pages from a foreign origin.
    A domain that merely shares the hostname prefix
    (`code.claude.com.evil.example`) must also be rejected."""
    sitemap = """<urlset>
      <url><loc>https://code.claude.com/docs/en/overview</loc></url>
      <url><loc>https://example.com/docs/en/hooks</loc></url>
      <url><loc>https://code.claude.com.evil.example/docs/en/setup</loc></url>
    </urlset>
    """
    pages = claude_code.discover(_FakeClient([_Resp(200, sitemap)]))
    assert [p.slug for p in pages] == ["overview"]


def test_claude_code_sitemap_skips_malformed_loc_entries(capsys):
    """A malformed ``<loc>`` entry -- one that ``urlsplit`` cannot parse
    (e.g. an unmatched IPv6 bracket in the netloc) -- must be skipped with
    a stderr warning instead of aborting discovery for the whole source:
    sitemap content arrives from the network, and a single corrupt entry
    must not kill the run."""
    sitemap = """<urlset>
      <url><loc>https://code.claude.com/docs/en/overview</loc></url>
      <url><loc>https://[::1/docs/en/broken</loc></url>
    </urlset>
    """
    pages = claude_code.discover(_FakeClient([_Resp(200, sitemap)]))
    assert [p.slug for p in pages] == ["overview"]
    err = capsys.readouterr().err
    assert "warning" in err
    assert "malformed" in err


def test_claude_code_sitemap_index_skips_foreign_host_child_sitemaps():
    """A `.xml` child sitemap loc on a foreign host must not be fetched:
    the origin guard in ``_sitemap_urls`` drops it before enqueueing, so
    the fake client (scripted with only the root response) is never asked
    for it."""
    root = """<sitemapindex>
      <sitemap><loc>https://evil.example/docs/sitemap-en.xml</loc></sitemap>
      <url><loc>https://code.claude.com/docs/en/overview</loc></url>
    </sitemapindex>
    """
    pages = claude_code.discover(_FakeClient([_Resp(200, root)]))
    assert [p.slug for p in pages] == ["overview"]


# --- deepseek: HTML -> Markdown conversion -----------------------------------


def _seed_deepseek_slugs(*slugs: str) -> None:
    """Publish *slugs* as the page set the current run mirrors.

    ``deepseek.fetch_markdown`` refuses to convert without one -- an empty set
    would send every internal link to its upstream URL -- so each test that
    reaches the hook seeds the set the way ``discover`` would, rather than
    relying on a test earlier in the module having left one behind.
    """
    deepseek._KNOWN_SLUGS.clear()
    deepseek._KNOWN_SLUGS.update(slugs or {"index", "quickstart"})


def test_deepseek_html_to_markdown_extracts_theme_doc_markdown():
    """Conversion must isolate the `div.theme-doc-markdown` content node and
    strip Docusaurus chrome living inside it (nav/breadcrumbs), so the
    mirrored Markdown carries the doc body only. The configured html2text
    options (see ``make_converter`` in ``core.html_markdown``) keep links
    and drop images."""
    # Given: HTML with a doc container and navigation chrome
    html = """
    <html><body>
      <header>site header that must not leak</header>
      <div class="theme-doc-markdown markdown">
        <nav class="breadcrumbs"><a href="/">Home</a></nav>
        <h1>Quickstart</h1>
        <p>Call the <a href="/api">API</a> with your key.</p>
        <img src="logo.png" alt="logo"/>
      </div>
      <footer>site footer that must not leak</footer>
    </body></html>
    """
    # When: The HTML is converted to Markdown
    md = deepseek._html_to_markdown(html)
    # Then: The content is isolated and chrome is stripped
    assert "# Quickstart" in md  # h1 converted to an ATX heading
    assert "[API](</api>)" in md  # links kept (ignore_links = False)
    assert "logo.png" not in md  # images dropped (ignore_images = True)
    # Chrome inside and outside the content node must be gone.
    assert "breadcrumbs" not in md and "Home" not in md
    assert "site header" not in md and "site footer" not in md


def test_deepseek_html_to_markdown_strips_zero_width_artifacts():
    """Zero-width characters html2text leaves around headings (U+200B and
    U+FEFF) must be removed from the output -- they are invisible junk that
    would otherwise end up in the mirrored files."""
    md = deepseek._html_to_markdown(
        '<div class="theme-doc-markdown"><h1>\u200bTitle\ufeff</h1></div>'
    )
    assert "\u200b" not in md
    assert "\ufeff" not in md
    assert "Title" in md


def test_deepseek_html_to_markdown_isolates_prompt_library_container(capsys):
    """The bespoke /prompt-library landing page has no Docusaurus doc
    container: its content lives in a custom ``div.PromptLibrary``. Conversion
    must isolate that node (skip-link and footer chrome excluded) and must
    emit NO fallback warning -- matching a known container is the expected
    outcome for that page, not a selector break."""
    html = """
    <html><body>
      <div role="region" aria-label="Skip to main content">
        <a href="#main">Skip to main content</a>
      </div>
      <div id="main" class="main-wrapper">
        <div class="PromptLibrary">
          <header class="PromptLibrary-header"><h1>Prompt Library</h1>
          <p>Explore the prompt samples.</p></header>
          <div class="prompt-grid"></div>
        </div>
      </div>
      <nav class="navbar"><a href="/">Home</a></nav>
      <footer>site footer that must not leak</footer>
    </body></html>
    """
    md = deepseek._html_to_markdown(html)
    assert "# Prompt Library" in md  # landing-page content converted
    assert "Explore the prompt samples." in md
    assert "Skip to main content" not in md  # body-level chrome excluded
    assert "site footer" not in md and "navbar" not in md
    assert capsys.readouterr().err == ""  # known container: no fallback warning


# --- deepseek.discover(): full entry-point test --------------------------------


def test_deepseek_discover_extracts_slugs_and_groups_from_sitemap():
    """Pin the full deepseek.discover() pipeline: sitemap XML -> loc extraction
    -> slug/group derivation -> Page construction. The homepage URL maps to
    slug "index" (group "root"), and nested paths split into groups by their
    first path segment. Non-site URLs are dropped."""
    sitemap = """<?xml version="1.0" encoding="UTF-8"?>
    <urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
      <url><loc>https://api-docs.deepseek.com/</loc></url>
      <url><loc>https://api-docs.deepseek.com/quickstart</loc></url>
      <url><loc>https://api-docs.deepseek.com/api/create-chat-completion</loc></url>
      <url><loc>https://other.example.com/ignore</loc></url>
    </urlset>
    """
    pages = deepseek.discover(_FakeClient([_Resp(200, sitemap)]))
    by_slug = {p.slug: p for p in pages}
    assert set(by_slug) == {"index", "quickstart", "api/create-chat-completion"}
    assert by_slug["index"].group == "root"
    assert by_slug["quickstart"].group == "root"
    assert by_slug["api/create-chat-completion"].group == "api"
    assert by_slug["index"].source_url == "https://api-docs.deepseek.com"
    assert by_slug["index"].source_id == "index"


def test_deepseek_discover_strips_query_and_fragment():
    """Sitemap entries carrying a query string (``?utm_source=...``) or a
    fragment (``#section``) must be cleaned BEFORE the slug is derived:
    otherwise "?"/"#" leak into the slug, ``Page.__post_init__`` rejects it,
    and the per-entry guard skips the page entirely -- a real docs page would
    silently go missing from the mirror behind a stderr warning. Entries
    differing only in their query/fragment must also dedupe to a single page,
    and the cleaned URL is what lands in ``source_url``/``source_md_url``."""
    sitemap = """<?xml version="1.0" encoding="UTF-8"?>
    <urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
      <url><loc>https://api-docs.deepseek.com/?x=1</loc></url>
      <url><loc>https://api-docs.deepseek.com/quickstart?utm_source=newsletter</loc></url>
      <url><loc>https://api-docs.deepseek.com/quickstart#section</loc></url>
      <url><loc>https://api-docs.deepseek.com/api/create-chat-completion?v=2</loc></url>
    </urlset>
    """
    pages = deepseek.discover(_FakeClient([_Resp(200, sitemap)]))
    by_slug = {p.slug: p for p in pages}
    assert set(by_slug) == {"index", "quickstart", "api/create-chat-completion"}
    assert len(pages) == 3  # the two /quickstart entries deduped after cleaning
    assert by_slug["quickstart"].source_url == (
        "https://api-docs.deepseek.com/quickstart"
    )
    assert by_slug["quickstart"].source_md_url == (
        "https://api-docs.deepseek.com/quickstart"
    )
    assert by_slug["api/create-chat-completion"].source_url == (
        "https://api-docs.deepseek.com/api/create-chat-completion"
    )
    assert by_slug["api/create-chat-completion"].source_md_url == (
        "https://api-docs.deepseek.com/api/create-chat-completion"
    )


@pytest.mark.parametrize(
    ("adapter_module", "sitemap_xml", "expected_slugs", "bad_url"),
    [
        pytest.param(
            deepseek,
            """<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url><loc>https://api-docs.deepseek.com/quickstart</loc></url>
  <url><loc>https://api-docs.deepseek.com/quick start</loc></url>
  <url><loc>https://api-docs.deepseek.com/api/create-chat-completion</loc></url>
</urlset>
""",
            ["api/create-chat-completion", "quickstart"],
            "https://api-docs.deepseek.com/quick start",
            id="deepseek",
        ),
        pytest.param(
            claude_code,
            """<urlset>
  <url><loc>https://code.claude.com/docs/en/overview</loc></url>
  <url><loc>https://code.claude.com/docs/en/my page</loc></url>
  <url><loc>https://code.claude.com/docs/en/hooks</loc></url>
</urlset>
""",
            ["hooks", "overview"],
            "https://code.claude.com/docs/en/my page",
            id="claude_code",
        ),
    ],
)
def test_discover_skips_entry_with_illegal_slug_characters(
    capsys, adapter_module, sitemap_xml, expected_slugs, bad_url
):
    """A sitemap entry whose path contains characters outside the slug
    alphabet ``Page`` enforces (here: a space, which would break Markdown
    links and file naming) cannot be fixed by query/fragment cleaning. Such
    an entry must be SKIPPED with a stderr warning naming the URL, while the
    remaining entries are still discovered -- one irreducibly-bad entry must
    not abort discovery for the whole source.

    Parametrized over both sitemap-driven adapters: ``deepseek`` filters to
    its site root, ``claude_code`` filters to the ``/docs/en/`` English tree,
    so each case exercises a distinct discovery filter on the way to the same
    per-entry slug contract. The assertions -- the surviving slugs (sorted),
    the ``warning`` keyword, and the bad URL named in stderr -- pin both
    halves of that contract for each adapter.
    """
    pages = adapter_module.discover(_FakeClient([_Resp(200, sitemap_xml)]))
    assert [p.slug for p in pages] == expected_slugs  # sorted
    warning = capsys.readouterr().err
    assert "warning" in warning
    assert bad_url in warning


# --- Claude Code sitemap-index tests ------------------------------------------


def test_claude_code_sitemap_index_follows_child_sitemaps():
    """When every ``<loc>`` in the sitemap ends with ``.xml``, ``discover``
    must fetch each child sitemap and return the aggregated pages from all of
    them — without this, pages listed in nested sitemaps would be silently
    missing from the mirror."""
    index_xml = """<?xml version="1.0"?>
    <sitemapindex>
      <sitemap><loc>https://code.claude.com/docs/sitemap-en.xml</loc></sitemap>
      <sitemap><loc>https://code.claude.com/docs/sitemap-more.xml</loc></sitemap>
    </sitemapindex>
    """
    child_a = """<?xml version="1.0"?>
    <urlset>
      <url><loc>https://code.claude.com/docs/en/overview</loc></url>
    </urlset>
    """
    child_b = """<?xml version="1.0"?>
    <urlset>
      <url><loc>https://code.claude.com/docs/en/hooks</loc></url>
    </urlset>
    """
    client = _FakeClient(
        [_Resp(200, index_xml), _Resp(200, child_a), _Resp(200, child_b)]
    )
    pages = claude_code.discover(client)
    assert {p.slug for p in pages} == {"overview", "hooks"}


def test_claude_code_rejects_path_containing_en_marker_off_anchor():
    """The English-tree filter is anchored on the parsed PATH: only URLs
    whose path STARTS WITH ``/docs/en/`` are English pages. A URL whose path
    merely CONTAINS the marker further along (e.g. a blog post filed under
    ``/blog/docs/en/...``) must be excluded -- a substring filter would
    include it and derive a bogus slug (``announcement``) from whatever
    follows the marker."""
    sitemap = """<?xml version="1.0"?>
    <urlset>
      <url><loc>https://code.claude.com/docs/en/overview</loc></url>
      <url><loc>https://code.claude.com/blog/docs/en/announcement</loc></url>
    </urlset>
    """
    pages = claude_code.discover(_FakeClient([_Resp(200, sitemap)]))
    assert {p.slug for p in pages} == {"overview"}


def test_claude_code_sitemap_mixed_locs_fetches_xml_children():
    """A sitemap that mixes child-sitemap references (``.xml`` locs) with
    plain page URLs must fetch EACH ``.xml`` loc as a child sitemap AND keep
    the non-``.xml`` locs as page URLs. The ``.xml`` test must apply per-loc,
    not per-document: a whole-document heuristic would treat a mixed index as
    a flat URL set and silently drop every page listed in its child
    sitemaps."""
    xml = """<?xml version="1.0"?>
    <urlset>
      <url><loc>https://code.claude.com/docs/en/overview</loc></url>
      <url><loc>https://code.claude.com/docs/sitemap-more.xml</loc></url>
    </urlset>
    """
    child = """<?xml version="1.0"?>
    <urlset>
      <url><loc>https://code.claude.com/docs/en/hooks</loc></url>
    </urlset>
    """
    client = _FakeClient([_Resp(200, xml), _Resp(200, child)])
    pages = claude_code.discover(client)
    assert {p.slug for p in pages} == {"overview", "hooks"}


def test_claude_code_sitemap_index_child_with_query_string():
    """A child-sitemap loc carrying a query string (``sitemap-en.xml?v=2``,
    e.g. a CDN cache-buster) must still be recognized as a sitemap reference
    and fetched: if the ".xml" test ran against the raw URL, the loc would
    fail the endswith check, be treated as a plain page URL, and every page
    listed in that child sitemap would be silently missing from the mirror."""
    index_xml = """<?xml version="1.0"?>
    <sitemapindex>
      <sitemap><loc>https://code.claude.com/docs/sitemap-en.xml?v=2</loc></sitemap>
    </sitemapindex>
    """
    child = """<?xml version="1.0"?>
    <urlset>
      <url><loc>https://code.claude.com/docs/en/overview</loc></url>
      <url><loc>https://code.claude.com/docs/en/hooks</loc></url>
    </urlset>
    """
    client = _FakeClient([_Resp(200, index_xml), _Resp(200, child)])
    pages = claude_code.discover(client)
    assert {p.slug for p in pages} == {"overview", "hooks"}
    assert client.calls == 2  # the child sitemap was actually fetched


def test_claude_code_sitemap_index_child_with_trailing_slash():
    """A child-sitemap loc with a trailing slash (``sitemap-en.xml/``) — and
    the combined trailing-slash-plus-query form (``sitemap-en.xml/?v=2``) —
    must still be recognized as a sitemap reference: ``clean_url`` strips
    the slash AFTER discarding the query, so both forms normalise to the
    bare ``.xml`` URL.  If the slash survived, the loc would fail the
    ``endswith(".xml")`` check, be misclassified as a page URL, and every
    page listed in that child sitemap would be silently lost.  Both variants
    also normalise to the SAME cleaned URL, so the child is fetched once,
    not twice (``client.calls`` pins the dedup)."""
    index_xml = """<?xml version="1.0"?>
    <sitemapindex>
      <sitemap><loc>https://code.claude.com/docs/sitemap-en.xml/</loc></sitemap>
      <sitemap><loc>https://code.claude.com/docs/sitemap-en.xml/?v=2</loc></sitemap>
    </sitemapindex>
    """
    child = """<?xml version="1.0"?>
    <urlset>
      <url><loc>https://code.claude.com/docs/en/overview</loc></url>
    </urlset>
    """
    client = _FakeClient([_Resp(200, index_xml), _Resp(200, child)])
    pages = claude_code.discover(client)
    assert {p.slug for p in pages} == {"overview"}
    assert client.calls == 2  # both slash variants deduped to ONE child fetch


def test_claude_code_sitemap_index_follows_two_levels_of_nesting():
    """A sitemap index can itself list another sitemap index (e.g.
    ``sitemap-index.xml`` -> ``sitemap-categories.xml`` ->
    ``sitemap-en.xml`` -> pages). The crawler must keep following ``.xml``
    locs through multiple index levels -- a fixed one-level follow would
    silently drop every page listed below the second level."""
    index_xml = """<?xml version="1.0"?>
    <sitemapindex>
      <sitemap><loc>https://code.claude.com/docs/sitemap-categories.xml</loc></sitemap>
    </sitemapindex>
    """
    category_xml = """<?xml version="1.0"?>
    <sitemapindex>
      <sitemap><loc>https://code.claude.com/docs/sitemap-en.xml</loc></sitemap>
    </sitemapindex>
    """
    child = """<?xml version="1.0"?>
    <urlset>
      <url><loc>https://code.claude.com/docs/en/overview</loc></url>
      <url><loc>https://code.claude.com/docs/en/hooks</loc></url>
    </urlset>
    """
    client = _FakeClient(
        [_Resp(200, index_xml), _Resp(200, category_xml), _Resp(200, child)]
    )
    pages = claude_code.discover(client)
    assert {p.slug for p in pages} == {"overview", "hooks"}
    assert client.calls == 3  # root index + nested index + leaf sitemap


def test_claude_code_sitemap_circular_reference_terminates():
    """Sitemap indexes can reference each other in a cycle (a malformed or
    auto-generated index pointing back at an ancestor). The visited set must
    make the crawl terminate instead of looping forever, and pages collected
    before the cycle closes must still be returned. Here the root index
    lists child A, child A lists child B, and child B points BACK at child A
    -- the third fetch must be the last one."""
    index_xml = """<?xml version="1.0"?>
    <sitemapindex>
      <sitemap><loc>https://code.claude.com/docs/sitemap-a.xml</loc></sitemap>
    </sitemapindex>
    """
    child_a = """<?xml version="1.0"?>
    <sitemapindex>
      <sitemap><loc>https://code.claude.com/docs/sitemap-b.xml</loc></sitemap>
    </sitemapindex>
    """
    child_b = """<?xml version="1.0"?>
    <urlset>
      <url><loc>https://code.claude.com/docs/en/overview</loc></url>
      <url><loc>https://code.claude.com/docs/sitemap-a.xml</loc></url>
    </urlset>
    """
    client = _FakeClient(
        [_Resp(200, index_xml), _Resp(200, child_a), _Resp(200, child_b)]
    )
    pages = claude_code.discover(client)
    assert [p.slug for p in pages] == ["overview"]
    assert client.calls == 3  # the back-reference to A was NOT fetched


def test_claude_code_sitemap_self_referencing_index_terminates():
    """The strongest cycle: an index that lists ITSELF. The root sitemap URL
    is seeded into the visited set before the crawl starts, so the
    self-reference is skipped immediately and the crawl ends after one
    fetch."""
    index_xml = """<?xml version="1.0"?>
    <sitemapindex>
      <sitemap><loc>https://code.claude.com/docs/sitemap.xml</loc></sitemap>
      <sitemap><loc>https://code.claude.com/docs/sitemap-en.xml</loc></sitemap>
    </sitemapindex>
    """
    child = """<?xml version="1.0"?>
    <urlset>
      <url><loc>https://code.claude.com/docs/en/overview</loc></url>
    </urlset>
    """
    client = _FakeClient([_Resp(200, index_xml), _Resp(200, child)])
    pages = claude_code.discover(client)
    assert [p.slug for p in pages] == ["overview"]
    assert client.calls == 2  # the self-reference was NOT fetched


def test_claude_code_sitemap_beyond_max_depth_warns_and_skips(capsys):
    """A chain of nested indexes deeper than ``max_depth`` (default 3: root
    is depth 0, so children are fetched through depth 3) must stop at the
    limit: the too-deep child is NOT fetched, a stderr warning names both
    the limit and the skipped URL, and pages at or above the limit are still
    collected. Silently skipping would hide pages from the mirror with no
    trace; fetching unboundedly would defeat the guard."""
    # Given: a scripted chain of nested sitemap indexes root→a→b→c, where c
    # (fetched at depth 3 == max_depth) mixes a real page with a reference to
    # d (depth 4, beyond the limit).
    chain = [
        "https://code.claude.com/docs/sitemap-a.xml",
        "https://code.claude.com/docs/sitemap-b.xml",
        "https://code.claude.com/docs/sitemap-c.xml",
        "https://code.claude.com/docs/sitemap-d.xml",
    ]

    def index_pointing_to(url):
        return f"""<?xml version="1.0"?>
        <sitemapindex>
          <sitemap><loc>{url}</loc></sitemap>
        </sitemapindex>
        """

    c_doc = """<?xml version="1.0"?>
    <urlset>
      <url><loc>https://code.claude.com/docs/en/overview</loc></url>
      <url><loc>https://code.claude.com/docs/sitemap-d.xml</loc></url>
    </urlset>
    """
    client = _FakeClient(
        [
            _Resp(200, index_pointing_to(chain[0])),
            _Resp(200, index_pointing_to(chain[1])),
            _Resp(200, index_pointing_to(chain[2])),
            _Resp(200, c_doc),
        ]
    )
    # When: discovery crawls the chain.
    pages = claude_code.discover(client)
    # Then: the page at the limit is collected, d is never fetched, and a
    # stderr warning names both the limit and the skipped URL.
    assert [p.slug for p in pages] == ["overview"]
    assert client.calls == 4  # root + a + b + c; d was never fetched
    warning = capsys.readouterr().err
    assert "max_depth" in warning
    assert chain[3] in warning  # the skipped sitemap URL is named


def test_claude_code_discover_strips_query_and_fragment():
    """Sitemap URLs carrying a query string (``?hl=1``) or fragment
    (``#section``) must have them stripped before the slug is derived:
    otherwise "?"/"#" would leak into the slug, ``Page.__post_init__`` would
    reject it, and the per-entry guard would skip the page entirely -- a real
    docs page silently missing from the mirror behind a stderr warning. The
    canonical ``source_url``/``source_md_url`` are stripped too."""
    sitemap = """<urlset>
      <url><loc>https://code.claude.com/docs/en/overview?hl=1</loc></url>
      <url><loc>https://code.claude.com/docs/en/hooks#section</loc></url>
    </urlset>
    """
    pages = claude_code.discover(_FakeClient([_Resp(200, sitemap)]))
    by_slug = {p.slug: p for p in pages}
    assert set(by_slug) == {"overview", "hooks"}
    assert by_slug["overview"].source_url == "https://code.claude.com/docs/en/overview"
    assert by_slug["hooks"].source_md_url == "https://code.claude.com/docs/en/hooks.md"


def test_claude_code_discover_ignores_en_prefix_in_query_string():
    """Regression: an entry containing ``/docs/en/`` only inside its QUERY
    STRING (e.g. a redirect-style URL like
    ``https://code.claude.com/redirect?next=/docs/en/overview``) must be
    skipped, not crash. The English-tree filter and the slug split must both
    run on the CLEANED URL: if the filter ran on the raw URL it would pass
    this entry, and the split would then fail to find the prefix after
    cleaning and raise IndexError -- aborting discovery for the whole source
    on one odd sitemap entry."""
    sitemap = """<urlset>
      <url><loc>https://code.claude.com/redirect?next=/docs/en/overview</loc></url>
      <url><loc>https://code.claude.com/docs/en/hooks</loc></url>
    </urlset>
    """
    pages = claude_code.discover(_FakeClient([_Resp(200, sitemap)]))
    assert [p.slug for p in pages] == ["hooks"]


# --- claude_code: MDX normalisation -------------------------------------------


def test_claude_normalize_converts_callouts_to_github_alerts():
    """The callout components are the pages' prose asides: each one becomes a
    GitHub Alert blockquote with the matching label, its body quoted in full
    (blank lines included, so paragraph breaks survive), and any title
    attribute rendered as the alert's bold first line. ``Info`` maps to NOTE
    and ``Danger`` to CAUTION because GitHub renders no INFO or DANGER
    label."""
    raw = (
        "# Page\n"
        "\n"
        "<Note>\n"
        "  First paragraph.\n"
        "\n"
        "  Second paragraph with `code`.\n"
        "</Note>\n"
        "\n"
        '<Warning title="Careful">\n'
        "  Destructive operation.\n"
        "</Warning>\n"
        "\n"
        "<Info>Informational.</Info>\n"
        "\n"
        "<Danger>Dangerous.</Danger>\n"
    )
    md = claude_code._normalize_page(raw, "sample", set())
    assert "> [!NOTE]\n> First paragraph.\n>\n> Second paragraph with `code`." in md
    assert "> [!WARNING]\n> **Careful**\n>\n> Destructive operation." in md
    assert "> [!NOTE]\n> Informational." in md
    assert "> [!CAUTION]\n> Dangerous." in md
    assert "<Note>" not in md and "</Warning>" not in md


def test_claude_normalize_renders_steps_as_an_ordered_list():
    """A ``<Steps>`` group is a numbered procedure: its steps become ordered
    list items carrying their own titles, each body indented to the marker's
    own width so its blocks -- a nested callout above all -- belong to the
    item. Numbering restarts per group, and a step body never loses its
    content."""
    raw = (
        "# Page\n"
        "\n"
        "<Steps>\n"
        '  <Step title="Install">\n'
        "    Run the installer.\n"
        "  </Step>\n"
        "\n"
        '  <Step title="Sign in">\n'
        "    Use your account.\n"
        "\n"
        "    <Tip>Any account works.</Tip>\n"
        "  </Step>\n"
        "</Steps>\n"
        "\n"
        "<Steps>\n"
        '  <Step title="Restart">\n'
        "    Restart the app.\n"
        "  </Step>\n"
        "</Steps>\n"
    )
    md = claude_code._normalize_page(raw, "sample", set())
    assert "1. **Install**\n\n   Run the installer." in md
    assert (
        "2. **Sign in**\n\n   Use your account.\n\n   > [!TIP]\n   > Any account works."
        in md
    )
    # The second group restarts at one rather than continuing the first.
    assert md.count("1. **Install**") == 1
    assert "1. **Restart**" in md
    assert "<Step " not in md and "<Steps>" not in md


def test_claude_normalize_keeps_every_tab_panel_under_its_label():
    """Tabs are a browser affordance a Markdown reader cannot act on, so every
    panel is kept, one after another, under its own bold label -- the label a
    reader needs to tell the installation methods apart, and the content
    (code samples included) beneath it."""
    raw = (
        "# Page\n"
        "\n"
        "<Tabs>\n"
        '  <Tab title="Homebrew">\n'
        "    ```bash theme={null}\n"
        "    brew install --cask claude-code\n"
        "    ```\n"
        "  </Tab>\n"
        "\n"
        '  <Tab title="WinGet">\n'
        "    ```powershell theme={null}\n"
        "    winget install Anthropic.ClaudeCode\n"
        "    ```\n"
        "  </Tab>\n"
        "</Tabs>\n"
    )
    md = claude_code._normalize_page(raw, "sample", set())
    assert "**Homebrew**" in md and "**WinGet**" in md
    assert "brew install --cask claude-code" in md
    assert "winget install Anthropic.ClaudeCode" in md
    # The dedented samples are the fences they were, at column zero.
    assert "\n```bash theme={null}\nbrew install" in md
    assert "<Tab " not in md and "<Tabs>" not in md


def test_claude_normalize_unwraps_layout_components_and_keeps_content():
    """The layout-only components (a tab group over code samples, a frame
    around a figure, a grid wrapper) contribute no text of their own, so their
    tags are dropped and everything they wrapped -- labels included -- is
    kept. An accordion keeps its title as a bold label, the same convention
    the tab panels use."""
    raw = (
        "# Page\n"
        "\n"
        "<CodeGroup>\n"
        "  ```bash Bash\n"
        "  echo one\n"
        "  ```\n"
        "</CodeGroup>\n"
        "\n"
        "<Frame>\n"
        '  <img src="media/images/shot.png" alt="A screenshot" />\n'
        "</Frame>\n"
        "\n"
        "<AccordionGroup>\n"
        '  <Accordion title="Reference">\n'
        "    Token reference.\n"
        "  </Accordion>\n"
        "</AccordionGroup>\n"
    )
    md = claude_code._normalize_page(raw, "sample", set())
    assert "```bash Bash\necho one\n```" in md
    assert '<img src="media/images/shot.png" alt="A screenshot" />' in md
    assert "**Reference**\n\nToken reference." in md
    for tag in ("CodeGroup", "Frame", "Accordion", "AccordionGroup"):
        assert f"<{tag}" not in md


def test_claude_normalize_renders_cards_with_their_titles_and_links():
    """A card's title and href are content, not styling: they are the label
    and the destination of a link list entry. Dropping them as markup would
    delete both, so they are rendered as a Markdown link -- with an internal
    target resolved like any other cross-link and an external one left
    exactly as upstream wrote it."""
    raw = (
        "# Page\n"
        "\n"
        "<CardGroup cols={2}>\n"
        '  <Card title="Worktrees" icon="code-branch" href="/docs/en/worktrees">\n'
        "    Run isolated parallel sessions\n"
        "  </Card>\n"
        "\n"
        '  <Card title="Help Centre" icon="store" href="https://support.claude.com">\n'
        "    Get additional support\n"
        "  </Card>\n"
        "</CardGroup>\n"
    )
    known = {"hooks", "sample", "worktrees"}
    md = claude_code._normalize_page(raw, "sample", known)
    assert "**[Worktrees](./worktrees.md)**\n\nRun isolated parallel sessions" in md
    assert (
        "**[Help Centre](https://support.claude.com)**\n\nGet additional support" in md
    )
    assert "<Card" not in md and "icon=" not in md


def test_claude_normalize_renders_update_entries_as_sections():
    """The weekly digest entries are ``<Update>`` components: their label and
    version tags become the section heading, their description (the entry's
    dates) the italic line beneath it, and their body ordinary Markdown."""
    raw = (
        "# What's new\n"
        "\n"
        '<Update label="Week 34" description="August 17-21, 2026" tags={["v2.1.234-v2.1.239"]}>\n'
        "  **`/design`**: a research preview.\n"
        "\n"
        "  [Read the digest](/docs/en/whats-new/2026-w34)\n"
        "</Update>\n"
    )
    known = {"sample", "whats-new/2026-w34"}
    md = claude_code._normalize_page(raw, "whats-new", known)
    assert "## Week 34 (v2.1.234-v2.1.239)" in md
    assert "*August 17-21, 2026*" in md
    assert "[Read the digest](./whats-new/2026-w34.md)" in md
    assert "<Update" not in md and "tags={" not in md


def test_claude_normalize_removes_widgets_only_when_self_closing():
    """The decorative components render a widget and no documentation text, so
    their self-closing form is removed outright. A container form of the same
    component would hold text between its tags, and dropping it would delete
    that text -- the test pins that it survives instead."""
    raw = (
        "# Page\n"
        "\n"
        '<ContactSalesCard surface="bedrock" />\n'
        "\n"
        '<BackToIndex href="#all-settings" label="Back to index" />\n'
        "\n"
        "<ClaudeExplorer>Kept text.</ClaudeExplorer>\n"
    )
    md = claude_code._normalize_page(raw, "sample", set())
    assert "ContactSalesCard" not in md
    assert "BackToIndex" not in md
    assert "Kept text." in md


def test_claude_normalize_renders_the_reference_filter_column_help():
    """The settings index's filter bar is the one widget whose props carry
    documentation: the help text it shows for each column. Dropping the
    component outright would take those explanations out of the page, so they
    become a bullet list where the widget sat. The props that only configure
    the widget -- the noun it counts, its search placeholder -- say nothing
    about the content and go with it."""
    raw = (
        "# Page\n"
        "\n"
        "Every key below links to its entry.\n"
        "\n"
        "<ReferenceFilter\n"
        '  noun="settings"\n'
        '  placeholder="Filter settings by key or purpose"\n'
        '  facetOrder={{ scope: ["Any file", "Managed"] }}\n'
        "  columnHelp={{\n"
        '    topic: "The section of this page that holds the entry.",\n'
        '    scope: "Which settings files can set the key."\n'
        "  }}\n"
        "/>\n"
        "\n"
        "| Key | Description |\n"
    )
    md = claude_code._normalize_page(raw, "sample", set())
    assert "ReferenceFilter" not in md
    assert "Filter settings by key" not in md
    assert "* **topic**: The section of this page that holds the entry." in md
    assert "* **scope**: Which settings files can set the key." in md
    assert "* **scope** (sort order): Any file, Managed" in md
    assert "| Key | Description |" in md


def test_claude_normalize_keeps_a_reference_filter_it_cannot_read():
    """A filter bar whose props this adapter cannot read is left exactly as
    upstream wrote it. Rendering from a partly-read value would replace the
    column help with a shorter list -- or with nothing -- which is worse than
    leaving the component visible."""
    raw = (
        "# Page\n"
        "\n"
        "<ReferenceFilter columnHelp={helpFor(columns)} />\n"
        "\n"
        "<ReferenceFilter>Filtered table.</ReferenceFilter>\n"
    )
    md = claude_code._normalize_page(raw, "sample", set())
    assert "<ReferenceFilter columnHelp={helpFor(columns)} />" in md
    assert "Filtered table." in md


def test_claude_normalize_renders_prompt_library_data_as_markdown():
    """A page that is mostly a JavaScript component carries its documentation
    inside the component's own data. The prompt library's records -- the
    prompt to copy, its title, why it works, what it needs, where it came
    from -- become ordinary Markdown, and the rendering code around them,
    which holds no text of its own, is not mirrored: a reader or an agent
    gets the prompts rather than the React source they were trapped in."""
    raw = (
        "# Prompt library\n"
        "\n"
        "export const PromptLibrary = ({text = {}, labels = {}}) => {\n"
        "  const RAW = useMemo(() => [{\n"
        "    id: 'explain-code',\n"
        "    sdlc: 'discover',\n"
        "    cat: 'Understand',\n"
        "    roles: ['pm'],\n"
        "    prompt: 'explain {target}',\n"
        "    slots: {\n"
        "      target: 'the queue'\n"
        "    },\n"
        "    needs: 'tracker',\n"
        "    src: 'workflows'\n"
        "  }], []);\n"
        "  const SOURCES = useMemo(() => ({\n"
        "    workflows: '/en/common-workflows'\n"
        "  }), []);\n"
        '  return <div className="pl">{RAW.length}</div>;\n'
        "};\n"
        "\n"
        "export const labels = {\n"
        "  whyWorks: 'Why this works',\n"
        "  makeItStick: 'Make it stick',\n"
        "  needsLabel: 'Needs',\n"
        "  from: 'From',\n"
        "  needs: {\n"
        '    tracker: "your issue tracker added as a [connector](/docs/en/mcp)."\n'
        "  }\n"
        "};\n"
        "\n"
        "export const tagLabels = {\n"
        "  pm: 'Product'\n"
        "};\n"
        "\n"
        "export const phaseLabels = {\n"
        "  discover: 'Discover'\n"
        "};\n"
        "\n"
        "export const catLabels = {\n"
        "  Understand: 'Understand'\n"
        "};\n"
        "\n"
        "export const sourceLabels = {\n"
        "  workflows: 'Common workflows'\n"
        "};\n"
        "\n"
        "export const text = {\n"
        "  'explain-code': {\n"
        "    title: 'Explain unfamiliar code',\n"
        "    teaches: 'Name the file; say what you want back.',\n"
        "    next: 'Set an output style'\n"
        "  }\n"
        "};\n"
        "\n"
        "<PromptLibrary text={text} labels={labels} />\n"
        "\n"
        "## Closing prose\n"
    )
    md = claude_code._normalize_page(raw, "prompt-library", {"mcp", "common-workflows"})
    assert "export const" not in md
    assert "PromptLibrary" not in md
    assert "### Discover - Understand" in md
    assert "#### Explain unfamiliar code" in md
    assert "*Tags: Product*" in md
    # The prompt is shown with its slot defaults filled in, which is the text
    # the page displays and the reader copies.
    assert "```text\nexplain the queue\n```" in md
    assert "* **Why this works**: Name the file; say what you want back." in md
    assert "* **Make it stick**: Set an output style" in md
    assert "* **Needs**: your issue tracker added as a [connector](./mcp.md)." in md
    assert "* **From**: [Common workflows](./common-workflows.md)" in md
    assert "## Closing prose" in md


def test_claude_normalize_fences_data_page_source_it_cannot_read():
    """When a data page's component cannot be read, its definitions are kept in
    a fenced code block rather than rendered from a partly-read value. Fenced
    code is valid CommonMark -- an agent reads it as a sample -- where raw JSX
    is neither readable nor parseable, and nothing the page carried is lost."""
    raw = (
        "# Prompt library\n"
        "\n"
        "export const PromptLibrary = () => {\n"
        "  const RAW = loadPrompts(locale);\n"
        "  return <div>{RAW.length}</div>;\n"
        "};\n"
    )
    md = claude_code._normalize_page(raw, "prompt-library", set())
    assert "```jsx\nexport const PromptLibrary = () => {" in md
    assert "const RAW = loadPrompts(locale);" in md
    assert "return <div>{RAW.length}</div>;" in md


def test_claude_normalize_fences_a_page_whose_source_is_only_implementation():
    """A page whose components are implementation rather than documentation --
    styles, an icon, an experiment's bucket assignment -- keeps that source in
    a fenced code block. The text the components show a reader lives inside
    it, so dropping it would lose content, while leaving it un-fenced is what
    makes a page unreadable to everything but a browser."""
    raw = (
        "# Claude Platform on AWS\n"
        "\n"
        "export const ContactSalesCard = ({surface}) => {\n"
        "  const STYLES = `.cc-cs-text { margin: 0; }`;\n"
        '  return <div className="cc-cs">Talk to sales.</div>;\n'
        "};\n"
    )
    md = claude_code._normalize_page(raw, "claude-platform-on-aws", set())
    assert "```jsx\nexport const ContactSalesCard" in md
    assert "Talk to sales." in md
    assert "style={{" not in md


def test_claude_normalize_renders_context_window_timeline_and_keeps_the_rest():
    """The context window page's steps -- what enters the context window, what
    loaded it, what it costs, whether the reader sees it, and why -- are data,
    so they become a table. The commentary the page prints for each stretch of
    the timeline is written into the view's own render code instead, and no
    literal holds it: that code stays in the page as a fenced code block, so
    the commentary is kept rather than dropped with the code around it."""
    raw = (
        "# Explore the context window\n"
        "\n"
        "export const ContextWindow = () => {\n"
        "  const MAX = 200000;\n"
        "  const EVENTS = [{}, {\n"
        "    t: 0.015,\n"
        "    kind: 'auto',\n"
        "    label: 'System prompt',\n"
        "    tokens: 4200,\n"
        "    vis: 'hidden',\n"
        "    desc: 'Core instructions. Always loaded first.',\n"
        "    link: '/en/memory'\n"
        "  }, {\n"
        "    t: 0.22,\n"
        "    kind: 'user',\n"
        "    label: 'Your prompt',\n"
        "    tokens: 40,\n"
        "    vis: 'full',\n"
        "    desc: 'What you typed.'\n"
        "  }];\n"
        "  const VIS_META = {\n"
        "    hidden: {\n"
        "      label: 'Invisible in your terminal'\n"
        "    },\n"
        "    full: {\n"
        "      label: 'Shown in your terminal'\n"
        "    }\n"
        "  };\n"
        "  const KIND_META = {\n"
        "    auto: {\n"
        "      detail: 'Auto-loaded'\n"
        "    },\n"
        "    user: {\n"
        "      detail: 'You typed this'\n"
        "    }\n"
        "  };\n"
        "  const takeaway = 'Only the render code holds this sentence.';\n"
        "  return <div>{takeaway}</div>;\n"
        "};\n"
    )
    md = claude_code._normalize_page(raw, "context-window", {"memory"})
    assert "## Session timeline" in md
    assert "holds 200,000 tokens" in md
    assert (
        "| System prompt | Auto-loaded | 4,200 | Invisible in your terminal "
        "| Core instructions. Always loaded first. [Learn more](./memory.md) |" in md
    )
    assert "| Your prompt | You typed this | 40 | Shown in your terminal |" in md
    # The spacer entry that separates stretches of the timeline is not a step.
    assert "|  |" not in md
    assert "```jsx\nexport const ContextWindow" in md
    assert "Only the render code holds this sentence." in md


def test_claude_normalize_renders_settings_views_at_their_mount_points():
    """The settings page declares its two views at the top and mounts them
    hundreds of lines further down, in the sections that introduce them. Each
    view's Markdown is written where the view appears, so a reader meets the
    precedence stack in the precedence section, not in the page's opening."""
    raw = (
        "# Settings files and precedence\n"
        "\n"
        "export const SettingsPrecedence = () => {\n"
        "  const LEVELS = [{\n"
        "    n: 1,\n"
        "    name: 'Managed settings',\n"
        "    file: 'managed-settings.json',\n"
        "    who: 'Your organization',\n"
        "    w: 390\n"
        "  }];\n"
        '  return <div className="sp-root">stack</div>;\n'
        "};\n"
        "\n"
        "export const SettingsScope = () => {\n"
        "  const FILES = [{\n"
        "    id: 'user',\n"
        "    path: '~/.claude/settings.json'\n"
        "  }, {\n"
        "    id: 'managed',\n"
        "    path: 'Managed settings',\n"
        "    ring: 'managed-settings.json, MDM, or the claude.ai console'\n"
        "  }];\n"
        '  return <div className="ssc-root">scope</div>;\n'
        "};\n"
        "\n"
        "Opening prose.\n"
        "\n"
        "## Compare the scope of each settings file\n"
        "\n"
        "Click a settings file to see the folders it reaches.\n"
        "\n"
        "<SettingsScope />\n"
        "\n"
        "## Settings precedence\n"
        "\n"
        "The stack below shows the levels, highest on top.\n"
        "\n"
        "<SettingsPrecedence />\n"
        "\n"
        "In order, highest precedence first:\n"
    )
    md = claude_code._normalize_page(raw, "settings", set())
    assert "export const" not in md
    assert "SettingsPrecedence" not in md and "SettingsScope" not in md
    assert "sp-root" not in md and "ssc-root" not in md
    # The view's data lands where the view was mounted, not where it was declared.
    assert "Opening prose." in md
    assert md.index("Click a settings file") < md.index("* `~/.claude/settings.json`")
    assert md.index("* `~/.claude/settings.json`") < md.index("## Settings precedence")
    assert "| Level | Where you set it | Who it applies to |" in md
    assert "| 1. Managed settings | managed-settings.json | Your organization |" in md
    assert (
        "* `Managed settings` (managed-settings.json, MDM, or the claude.ai console)"
        in md
    )
    assert md.index("| 1. Managed settings") < md.index(
        "In order, highest precedence first:"
    )


def test_claude_normalize_data_pages_are_idempotent():
    """Normalisation is applied once per page fetch, but the passes have to
    agree with what they produce: the component source a rendered page keeps
    is inside a fence, so a later run must recognize it as a code sample and
    leave it alone rather than fencing it a second time or reading its
    declarations back out."""
    raw = (
        "# Explore the context window\n"
        "\n"
        "export const ContextWindow = () => {\n"
        "  const MAX = 200000;\n"
        "  const EVENTS = [{\n"
        "    t: 0.015,\n"
        "    kind: 'auto',\n"
        "    label: 'System prompt',\n"
        "    tokens: 4200,\n"
        "    vis: 'hidden',\n"
        "    desc: 'Core instructions.'\n"
        "  }];\n"
        "  const VIS_META = {\n"
        "    hidden: {\n"
        "      label: 'Invisible in your terminal'\n"
        "    }\n"
        "  };\n"
        "  const KIND_META = {\n"
        "    auto: {\n"
        "      detail: 'Auto-loaded'\n"
        "    }\n"
        "  };\n"
        "  const takeaway = 'Held by the render code.';\n"
        '  return <div className="cw-root">{takeaway}</div>;\n'
        "};\n"
    )
    once = claude_code._normalize_page(raw, "context-window", set())
    assert claude_code._normalize_page(once, "context-window", set()) == once


def test_claude_normalize_keeps_a_data_page_definition_inside_a_code_sample():
    """A page may show its own component source inside a fenced sample, and a
    rendered page carries the source it kept in a fence as well. A definition
    that stands inside a code block is sample text, so the pass that renders
    data pages must not touch it -- the sample has to come through byte for
    byte."""
    raw = (
        "# Prompt library\n"
        "\n"
        "`export const PromptLibrary = () => {};`\n"
        "\n"
        "```jsx\n"
        "export const PromptLibrary = () => {};\n"
        "```\n"
    )
    md = claude_code._normalize_page(raw, "prompt-library", set())
    assert "```jsx\nexport const PromptLibrary = () => {};\n```" in md


def test_claude_normalize_protects_fenced_code_and_keeps_it_a_fence():
    """Nothing inside a fenced code sample may be converted: a sample that
    documents the components (``<Note>``, ``](/docs/en/hooks)``) is code, not
    page structure. The sample also has to survive the reshaping around it --
    a step body is dedented and re-indented under its marker, and the fence
    has to move with it, or the sample breaks out of the list item it
    belongs to."""
    raw = (
        "# Page\n"
        "\n"
        "```markdown\n"
        "<Note>Not a callout here.</Note>\n"
        "[Hooks](/docs/en/hooks)\n"
        "```\n"
        "\n"
        "<Steps>\n"
        '  <Step title="Document it">\n'
        "    Add this to the file:\n"
        "\n"
        "    ```markdown\n"
        "    <Note>Still code.</Note>\n"
        "    ```\n"
        "  </Step>\n"
        "</Steps>\n"
    )
    md = claude_code._normalize_page(raw, "sample", {"hooks"})
    assert "<Note>Not a callout here.</Note>" in md
    assert "[Hooks](/docs/en/hooks)" in md
    assert "1. **Document it**" in md
    assert "   ```markdown\n   <Note>Still code.</Note>\n   ```" in md


def test_claude_normalize_strips_presentation_attributes():
    """``style={{...}}`` and ``className`` are JSX spellings of CSS that a
    Markdown reader renders as literal text, and ``data-path`` repeats the
    asset path already carried by ``src``. All three are removed from the
    elements that carry them -- including a multi-line expression value and a
    braced one -- while the element itself keeps every other attribute it
    has."""
    raw = (
        "# Page\n"
        "\n"
        '<img src="media/images/diagram.svg" className="dark:hidden"\n'
        '  alt="Diagram" width="680" data-path="images/diagram.svg" style={{\n'
        '  maxWidth: "640px",\n'
        "  margin: '0 auto'\n"
        "}} />\n"
        "\n"
        "<code style={mono}>claude</code>\n"
    )
    md = claude_code._normalize_page(raw, "sample", set())
    assert "style={" not in md
    assert "className" not in md
    assert "data-path" not in md
    assert 'alt="Diagram" width="680"' in md
    assert '<img src="media/images/diagram.svg"' in md and md.count("<img") == 1
    assert "<code>claude</code>" in md


def test_claude_normalize_keeps_footnote_anchor_ids():
    """A self-closing ``<span id="fn1" style={{...}} />`` is the pages' anchor
    marker for a footnote: the style is site styling, but the id is what makes
    ``[1](#fn1)`` resolve. It becomes an explicit anchor element, so the link
    still lands on its footnote after the styling is gone."""
    raw = (
        "# Page\n"
        "\n"
        'See note <sup><a href="#fn1">1</a></sup>\n'
        "\n"
        "<span id=\"fn1\" style={{display: 'block', position: 'relative'}} "
        "/><sup>1</sup> The footnote text.<br />\n"
    )
    md = claude_code._normalize_page(raw, "sample", set())
    assert '<a id="fn1"></a><sup>1</sup> The footnote text.' in md
    assert "style={{" not in md
    assert "[1](#fn1)" in md or 'href="#fn1"' in md


def test_claude_normalize_converts_inline_pseudo_tags():
    """One page defines three short inline components -- a code span, a bold
    run, and a link -- and uses them throughout its prose. They become the
    Markdown they stand for, including the JSX expression wrapper upstream
    uses wherever the value would otherwise be parsed as markup."""
    raw = (
        "# Page\n"
        "\n"
        "Run <C>/memory</C> to edit <C>{'${NOTION_TOKEN}'}</C> and see <B>bold</B>.\n"
        "\n"
        'Read the <A href="/docs/en/hooks">hooks guide</A> next.\n'
    )
    md = claude_code._normalize_page(raw, "sample", {"hooks"})
    assert "Run `/memory` to edit `${NOTION_TOKEN}` and see **bold**." in md
    assert "Read the [hooks guide](./hooks.md) next." in md
    for tag in ("<C>", "</C>", "<B>", "</B>", "<A "):
        assert tag not in md


def test_claude_normalize_removes_the_site_script_tag():
    """One page loads a browser-side asset that rewrites SDK type links in
    place. A mirrored page has no such script and cannot use one, and a
    ``<script>`` tag in a Markdown file renders as literal text, so the tag is
    removed. A script element that carries content between its tags is kept:
    that content may be prose."""
    raw = (
        "# Page\n"
        "\n"
        '<script src="/docs/components/typescript-sdk-type-links.js" defer />\n'
        "\n"
        "Prose.\n"
    )
    md = claude_code._normalize_page(raw, "sample", set())
    assert "script" not in md
    assert "Prose." in md


def test_claude_normalize_rewrites_video_wrappers_to_external_links():
    """Video demos stay upstream CDN links (the mirror's media stage mirrors
    images and diagrams only), so a ``<video>`` element -- whose attributes are
    browser playback flags -- becomes a plain link to the media it played.
    A video element with no readable source is left exactly as upstream wrote
    it rather than being dropped."""
    raw = (
        "# Page\n"
        "\n"
        "<Frame>\n"
        '  <video autoPlay muted loop playsInline className="w-full" '
        'src="https://mintcdn.com/claude-code/token/images/whats-new/demo.mp4?fit=max" '
        'data-path="images/whats-new/demo.mp4" />\n'
        "</Frame>\n"
        "\n"
        "<video autoplay />\n"
    )
    md = claude_code._normalize_page(raw, "sample", set())
    assert (
        "[Video demo](https://mintcdn.com/claude-code/token/images/whats-new/demo.mp4?fit=max)"
        in md
    )
    assert "<video autoplay />" in md
    assert "autoPlay" not in md


def test_claude_normalize_unwraps_only_presentation_wrappers():
    """Only a ``div``/``span``/``p`` carrying a class or style is a layout
    wrapper: its tags go and its content stays. A bare ``<div>`` may be a
    semantic container or an anchor target, so it is kept together with its
    closing tag -- the two stay balanced whatever the nesting order is."""
    raw = (
        "# Page\n"
        "\n"
        '<div className="digest-feature">\n'
        "  <div>\n"
        "    Kept by the semantic wrapper.\n"
        "  </div>\n"
        "</div>\n"
        "\n"
        "<p style={{margin: 0}}>A styled paragraph.</p>\n"
    )
    md = claude_code._normalize_page(raw, "sample", set())
    assert "Kept by the semantic wrapper." in md
    assert "A styled paragraph." in md
    assert "digest-feature" not in md
    assert "<p" not in md
    assert md.count("<div>") == 1 and md.count("</div>") == 1


def test_claude_normalize_resolves_internal_cross_links():
    """The pages link to each other with site-absolute paths, which resolve
    against the upstream site and are dead for a reader of the mirror. Each
    one becomes the relative link that reaches the same page here (nested
    slugs and anchors included); a target the mirror does not hold becomes its
    upstream URL, and anything that is not a documentation path -- an external
    URL, a bare anchor -- is left alone."""
    raw = (
        "# Page\n"
        "\n"
        "See [hooks](/docs/en/hooks#exec-form) and [python](/docs/en/agent-sdk/python).\n"
        "\n"
        "Also [settings](/docs/en/settings-reference#available-settings), "
        "[unmirrored](/docs/en/unknown-page#x), [external](https://example.com/x), "
        "and [a fragment](#local).\n"
        "\n"
        'In HTML too: <a href="/docs/en/hooks">hooks</a>.\n'
    )
    known = {"hooks", "sample", "agent-sdk/python", "agent-sdk/typescript"}
    md = claude_code._normalize_page(raw, "agent-sdk/typescript", known)
    assert "[hooks](../hooks.md#exec-form)" in md
    assert "[python](./python.md)" in md
    assert (
        "[settings](https://code.claude.com/docs/en/settings-reference#available-settings)"
        in md
    )
    assert "[unmirrored](https://code.claude.com/docs/en/unknown-page#x)" in md
    assert "[external](https://example.com/x)" in md
    assert "[a fragment](#local)" in md
    assert '<a href="../hooks.md">hooks</a>' in md
    assert "](" + "/docs/en/" not in md


def test_claude_normalize_resolves_links_idempotently():
    """Resolution is applied once per page fetch, but the page a later pass
    sees is already the output of the earlier one -- so the same text must
    resolve to itself. Both passes only match a leading ``/docs/en`` or
    ``/en`` path and neither result starts with one, which is what makes the
    second run a no-op and keeps the content hash stable across mirror
    runs."""
    raw = "# Page\n\nSee [hooks](/docs/en/hooks) and [skills](/en/skills).\n"
    known = {"hooks", "skills", "sample"}
    once = claude_code._normalize_page(raw, "sample", known)
    assert claude_code._normalize_page(once, "sample", known) == once


def test_claude_normalize_resolves_the_unprefixed_en_link_form():
    """A few upstream cross-links omit the ``docs`` segment (``/en/skills``)
    while the site serves that spelling as the same page. Without covering
    it, those links reach the mirror as literal site-root-absolute paths,
    which resolve to nothing in a local checkout."""
    raw = (
        "# Page\n\nSee [skills](/en/skills) and "
        "[tool](/en/tools-reference#powershell-tool) and "
        '[html](<a href="/en/skills">s</a>).\n'
    )
    known = {"skills", "tools-reference", "sample"}
    md = claude_code._normalize_page(raw, "sample", known)
    assert "[skills](./skills.md)" in md
    assert "[tool](./tools-reference.md#powershell-tool)" in md
    assert '<a href="./skills.md">' in md
    assert "](/en/" not in md


def test_claude_normalize_sends_an_unmirrored_en_link_upstream():
    """The unprefixed form resolves against the same slug set as the
    ``/docs/en`` form, so a route this run does not mirror falls back to its
    CANONICAL upstream URL -- the ``/docs/en`` spelling -- rather than the
    alias the page happened to use."""
    raw = "# Page\n\nSee [gone](/en/retired-page#top).\n"
    md = claude_code._normalize_page(raw, "sample", {"sample"})
    assert "[gone](https://code.claude.com/docs/en/retired-page#top)" in md


def test_claude_normalize_keeps_component_definitions_structural():
    """Pages whose body is a JavaScript component carry the prose inside the
    component's own code. The passes that only remove markup still apply there
    (a ``style={{...}}`` or a ``<C>`` is JSX noise in a Markdown reader either
    way), while the passes that rewrite page structure leave the definition
    alone: its elements and their nesting are the page's code, and rewriting
    them would edit code rather than documentation."""
    raw = (
        "# Page\n"
        "\n"
        "export const Widget = () => {\n"
        '  return <div className={"w-root"} style={{padding: 4}}>\n'
        "    <p className=\"w-text\">Rendered <C>{'text'}</C> here.</p>\n"
        "  </div>;\n"
        "};\n"
        "\n"
        "<Widget />\n"
    )
    md = claude_code._normalize_page(raw, "sample", set())
    assert 'return <div style="' not in md
    assert "<div>\n    <p>Rendered `text` here.</p>\n  </div>;" in md


def test_claude_normalize_leaves_an_unterminated_component_visible():
    """A component tag whose partner never arrives is uncertain structure: the
    page keeps the text exactly as upstream wrote it instead of guessing where
    the component ends and swallowing the rest of the page into it. The
    malformed pair of an empty group is converted, since both of its tags are
    present."""
    raw = (
        "# Page\n"
        "\n"
        "<Note>\n"
        "Prose that never closes.\n"
        "\n"
        "<CardGroup></CardGroup>\n"
        "\n"
        "Closing prose.\n"
    )
    md = claude_code._normalize_page(raw, "sample", set())
    assert "<Note>" in md
    assert "Prose that never closes." in md
    assert "Closing prose." in md
    assert "<CardGroup>" not in md


def test_claude_normalize_keeps_prose_placeholders_and_unknown_markup():
    """The pages use angle brackets as prose placeholders (``<sessionId>``,
    ``CLAUDE_PLUGIN_OPTION_<KEY>``) and carry inline HTML that Markdown
    readers render as it is. A generic "strip every tag" pass would delete the
    first group, so every conversion above targets one known construct
    instead; this pins that the rest of the page is untouched."""
    raw = (
        "# Page\n"
        "\n"
        "Pass an `AsyncIterable<SDKUserMessage>` and read "
        "`$CLAUDE_PLUGIN_OPTION_<KEY>` from the environment.\n"
        "\n"
        "| Key   | Type   |\n"
        "| ----- | ------ |\n"
        "| `a`   | string |\n"
        "\n"
        "<details>\n"
        "<summary>More</summary>\n"
        "\n"
        "Body.\n"
        "\n"
        "</details>\n"
    )
    md = claude_code._normalize_page(raw, "sample", set())
    assert "`AsyncIterable<SDKUserMessage>`" in md
    assert "`$CLAUDE_PLUGIN_OPTION_<KEY>`" in md
    assert "| `a`   | string |" in md
    assert "<details>" in md and "</details>" in md


def test_claude_normalize_has_no_component_remnants():
    """Representative converted output carries no MDX component tag, no JSX
    styling attribute, and no site-absolute cross-link.

    This is the guard that fails loudly if a future upstream adds a component,
    or changes one of these into a shape the passes do not recognize: the page
    would keep raw JSX instead of degrading quietly.
    """
    raw = (
        "# Sample\n"
        "\n"
        '<Update label="Week 34" description="August 17-21, 2026" tags={["v2.1.234-v2.1.239"]}>\n'
        "Body of the entry.\n"
        "</Update>\n"
        "\n"
        '<Note title="Heads up">\n'
        "A callout.\n"
        "</Note>\n"
        "\n"
        "<Tip>Another callout.</Tip>\n"
        "\n"
        "<Warning>A third.</Warning>\n"
        "\n"
        "<Info>A fourth.</Info>\n"
        "\n"
        "<Steps>\n"
        '  <Step title="First">\n'
        "    Do the first thing.\n"
        "  </Step>\n"
        '  <Step title="Second">\n'
        "    Do the second thing.\n"
        "  </Step>\n"
        "</Steps>\n"
        "\n"
        "<Tabs>\n"
        '  <Tab title="macOS">\n'
        "    Run it on macOS.\n"
        "  </Tab>\n"
        '  <Tab title="Linux">\n'
        "    Run it on Linux.\n"
        "  </Tab>\n"
        "</Tabs>\n"
        "\n"
        "<CodeGroup>\n"
        "  ```bash\n"
        "  echo hi\n"
        "  ```\n"
        "</CodeGroup>\n"
        "\n"
        "<AccordionGroup>\n"
        '  <Accordion title="Details">\n'
        "    The details.\n"
        "  </Accordion>\n"
        "</AccordionGroup>\n"
        "\n"
        "<Frame>\n"
        '  <img src="media/images/shot.png" alt="Shot" width="10" height="10" />\n'
        "</Frame>\n"
        "\n"
        "<CardGroup cols={2}>\n"
        '  <Card title="Hooks" icon="hook" href="/docs/en/hooks">\n'
        "    Wire up hooks.\n"
        "  </Card>\n"
        "</CardGroup>\n"
        "\n"
        '<div style={{maxWidth: "640px"}}>\n'
        '  <span className="nowrap">Prose in a wrapper.</span>\n'
        "</div>\n"
        "\n"
        '<span id="fn1" style={{display: "block"}} />Footnote one.\n'
        "\n"
        "Use <C>claude --version</C> and <B>bold</B>, see "
        '<A href="/docs/en/hooks">hooks</A>.\n'
        "\n"
        '<script src="/docs/components/x.js" defer />\n'
        "\n"
        '<video autoPlay src="https://mintcdn.com/claude-code/t/images/x.mp4" />\n'
        "\n"
        '<ContactSalesCard surface="bedrock" />\n'
        "\n"
        "Closing prose with [hooks](/docs/en/hooks).\n"
    )
    md = claude_code._normalize_page(raw, "sample", {"hooks", "sample"})
    assert re.search(r"<[A-Z][A-Za-z]*\b", md) is None
    assert "style={{" not in md
    assert "className" not in md
    assert "](/docs/en/" not in md
    assert '<script src="/docs/' not in md
    # The conversions produced content rather than deleting it.
    assert "## Week 34 (v2.1.234-v2.1.239)" in md
    assert "> [!NOTE]\n> **Heads up**\n>\n> A callout." in md
    assert "> [!TIP]\n> Another callout." in md
    assert "> [!WARNING]\n> A third." in md
    assert "1. **First**" in md and "2. **Second**" in md
    assert "**macOS**" in md and "**Linux**" in md
    assert "echo hi" in md
    assert "**Details**\n\nThe details." in md
    assert '<img src="media/images/shot.png" alt="Shot" width="10" height="10" />' in md
    assert "**[Hooks](./hooks.md)**" in md
    assert "Prose in a wrapper." in md
    assert '<a id="fn1"></a>Footnote one.' in md
    assert "`claude --version`" in md and "**bold**" in md
    assert "[Video demo](https://mintcdn.com/claude-code/t/images/x.mp4)" in md
    assert "[hooks](./hooks.md)" in md


def test_claude_normalize_many_unterminated_components_complete_quickly():
    """A page full of component openers that never close must not be quadratic:
    the tag scanner resumes after each one instead of restarting its search
    from the top, so a large malformed page costs the same order as a
    well-formed one. The text is kept -- nothing is silently deleted."""
    raw = "# Page\n\n" + "<Note>\nunterminated prose\n" * 2000
    md = claude_code._normalize_page(raw, "sample", set())
    assert md.count("<Note>") == 2000
    assert "unterminated prose" in md


def test_claude_shield_many_unterminated_fences_complete_quickly():
    """A page full of fence openers that no fence line ever closes must not be
    quadratic: once a closer search has failed for a fence run, every later
    opener of that run is known to have no closer either and skips the search
    entirely. The text is kept exactly -- a lone fence run in prose is not a
    code block, so nothing is shielded and nothing is rewritten.

    The openers carry an info string, which is what stops one opener from
    closing the one before it. The threshold is deliberately far above the
    cost of the linear walk and far below the cost of the quadratic one, so
    the test measures the shape of the scan rather than the speed of the
    machine it runs on."""
    text = "# Page\n\n" + "```text\nunterminated code\n" * 20000
    started = time.monotonic()
    shielded, blocks = claude_code._shield_fenced_code(text)
    elapsed = time.monotonic() - started
    assert blocks == []
    assert shielded == text
    assert elapsed < 2.0, f"shielding {len(text)} characters took {elapsed:.2f}s"


def _seed_claude_slugs(*slugs: str) -> None:
    """Publish *slugs* as the page set the current run mirrors.

    ``claude_code.fetch_markdown`` refuses to normalise without one -- an
    empty set would send every internal link to its upstream URL -- so each
    test that reaches the hook seeds the set the way ``discover`` would,
    rather than relying on a test earlier in the module having left one
    behind.
    """
    claude_code._KNOWN_SLUGS.clear()
    claude_code._KNOWN_SLUGS.update(slugs or {"overview", "hooks"})


def _claude_page(slug: str = "overview") -> Page:
    """Build the ``Page`` a ``fetch_markdown`` test needs, with realistic URLs."""
    return Page(
        slug=slug,
        source_url=f"{claude_code.SITE_URL}/docs/en/{slug}",
        source_md_url=f"{claude_code.SITE_URL}/docs/en/{slug}.md",
        source_id=slug,
        group="root",
    )


def test_claude_fetch_markdown_returns_normalized_markdown_and_hash():
    """The SUCCESS path of ``claude_code.fetch_markdown``: the raw MDX twin
    must come back as a ``(markdown, sha256_hash)`` tuple, with the
    normalisation applied and the hash matching ``fetch.content_hash`` of the
    returned text -- that pairing is what the pipeline stores in the manifest
    and what ``core.diff`` compares across runs."""
    raw = (
        "> ## Documentation Index\n> Fetch the complete documentation index.\n"
        "\n"
        "# Overview\n"
        "\n"
        "<Note>\nInstall it first.\n</Note>\n"
    )
    page = _claude_page()
    _seed_claude_slugs("overview")
    md, digest = claude_code.fetch_markdown(_FakeClient([_Resp(200, raw)]), page)
    assert md.startswith("> ## Documentation Index")
    assert "# Overview" in md
    assert "> [!NOTE]\n> Install it first." in md
    assert digest == fetch.content_hash(md)


def test_claude_fetch_markdown_rejects_non_markdown():
    """A response that normalises to something with no Markdown structure (an
    HTML error page, a truncated body) must raise ``FetchError`` rather than
    being written to the mirror: the pipeline isolates failures per page for
    that exception type only, so this is also what keeps one bad response from
    aborting the whole source."""
    client = _FakeClient([_Resp(200, "<html><body><p>404 Not Found</p></body></html>")])
    _seed_claude_slugs("hooks")
    with pytest.raises(fetch.FetchError):
        claude_code.fetch_markdown(client, _claude_page("hooks"))


def test_claude_fetch_markdown_wraps_a_normalisation_failure(monkeypatch):
    """An exception out of the normalisation passes is re-raised as
    ``FetchError``, naming the page and keeping the original exception on
    ``__cause__``. The pipeline isolates failures per page for that exception
    type only, so an unforeseen markup shape (or a bug in a pass) must fail
    just this page instead of aborting the whole source's run."""
    page = _claude_page("hooks")
    _seed_claude_slugs("hooks")

    def _explode(text: str, slug: str, known_slugs=None) -> str:
        raise ValueError("unforeseen markup shape")

    monkeypatch.setattr(claude_code, "_normalize_page", _explode)
    client = _FakeClient([_Resp(200, "# Hooks\n\nSome prose.\n")])
    with pytest.raises(fetch.FetchError) as exc_info:
        claude_code.fetch_markdown(client, page)
    assert page.slug in str(exc_info.value)
    assert isinstance(exc_info.value.__cause__, ValueError)


def test_claude_fetch_markdown_refuses_to_normalise_without_discovered_slugs():
    """Normalising with no discovered slug set would rewrite every internal
    link on the page to its upstream URL (see ``ensure_known_slugs``), so the
    hook must fail loudly instead -- and as a ``FetchError``, the one type the
    pipeline isolates per page rather than aborting the source. The refusal
    comes before the download, so a run that skipped discovery stops at the
    first page instead of fetching the whole source and then failing."""
    claude_code._KNOWN_SLUGS.clear()
    page = _claude_page("hooks")
    client = _FakeClient([_Resp(200, "# Hooks\n\nSome prose.\n")])
    with pytest.raises(fetch.FetchError, match="no discovered slugs"):
        claude_code.fetch_markdown(client, page)
    assert client.calls == 0


# --- DeepSeek code-block blank-line preservation ------------------------------


def test_deepseek_html_to_markdown_preserves_blank_lines_in_code_blocks():
    """Blank lines inside fenced code blocks must survive the post-conversion
    collapsing pass — they are semantically significant in code (they separate
    function definitions, mark string boundaries, etc.) and collapsing them
    would corrupt the mirrored document."""
    html = """
    <div class="theme-doc-markdown">
      <h1>Code Example</h1>
      <pre><code>def foo():
        return 1

    def bar():
        return 2</code></pre>
    </div>
    """
    md = deepseek._html_to_markdown(html)
    # The blank line between the two functions should survive.
    assert "return 1" in md
    assert "return 2" in md
    lines = md.splitlines()
    idx1 = next(i for i, l in enumerate(lines) if "return 1" in l)
    idx2 = next(i for i, l in enumerate(lines) if "return 2" in l)
    # At least one blank line must be preserved between the two code lines.
    assert idx2 > idx1 + 1


# --- DeepSeek fetch_markdown rejection ----------------------------------------


def test_deepseek_fetch_markdown_rejects_non_markdown():
    """``deepseek.fetch_markdown`` must raise ``FetchError`` when the
    downloaded HTML does not convert to valid Markdown (e.g. an empty/too-short
    body).  Without this check, a broken upstream HTML page would silently be
    mirrored as near-empty Markdown."""
    client = _FakeClient([_Resp(200, "<html><body><p>too short</p></body></html>")])
    # Use the real Page model, not an ad-hoc mock: fetch_markdown reads the
    # page's URL fields, and a hand-rolled namespace could drift out of sync
    # with the dataclass (e.g. after a field rename) without any test noticing.
    page = Page(
        slug="x",
        source_url="https://api-docs.deepseek.com/x",
        source_md_url="https://api-docs.deepseek.com/x.md",
        source_id="x",
        group="",
    )
    _seed_deepseek_slugs()
    with pytest.raises(fetch.FetchError):
        deepseek.fetch_markdown(client, page)


def test_deepseek_fetch_markdown_returns_markdown_and_hash():
    """The SUCCESS path of ``deepseek.fetch_markdown``: a well-formed
    Docusaurus page must come back as a ``(markdown, sha256_hash)`` tuple --
    the markdown containing the converted doc body (heading and prose, chrome
    stripped), and the hash matching ``fetch.content_hash`` of that exact
    text, which is what the pipeline stores in the manifest for change
    detection. Pinning the success path (not just error handling) is what
    catches a regression that breaks or reorders this return contract."""
    html = """
    <html><body>
      <header>site header that must not leak</header>
      <div class="theme-doc-markdown markdown">
        <h1>Quickstart</h1>
        <p>Call the API with your key to create your first chat completion.</p>
      </div>
      <footer>site footer that must not leak</footer>
    </body></html>
    """
    client = _FakeClient([_Resp(200, html)])
    page = Page(
        slug="quickstart",
        source_url="https://api-docs.deepseek.com/quickstart",
        source_md_url="https://api-docs.deepseek.com/quickstart",
        source_id="quickstart",
        group="root",
    )
    _seed_deepseek_slugs("quickstart")
    md, digest = deepseek.fetch_markdown(client, page)
    assert "# Quickstart" in md  # converted ATX heading present
    assert "create your first chat completion" in md  # prose converted
    assert "site header" not in md and "site footer" not in md  # chrome gone
    assert digest == fetch.content_hash(md)


# --- codex_cli: fetch_markdown hook -------------------------------------------


def _seed_codex_slugs(*slugs: str) -> None:
    """Publish *slugs* as the page set the current run mirrors.

    ``codex_cli.fetch_markdown`` refuses to run without one -- an empty set
    would send every internal link to its upstream URL -- so each test that
    reaches the hook seeds the set the way ``discover`` would, rather than
    relying on a test earlier in the module having left one behind.
    """
    codex_cli._KNOWN_SLUGS.clear()
    codex_cli._KNOWN_SLUGS.update(slugs or {"config", "overview"})


def test_codex_fence_spans_of_unclosed_fences_complete_quickly():
    """A page of fence opener lines that no fence line ever closes must not be
    quadratic: once a closer search has failed for a fence run, every later
    opener of that run is known to have no closer either and skips the search
    entirely. An opener with no closer is not a code block, so the scan
    reports nothing and the text is left exactly as it was.

    The openers carry an info string, which is what stops one opener from
    closing the one before it. The threshold is deliberately far above the
    cost of the linear walk and far below the cost of the quadratic one
    (50 s for this input), so the test measures the shape of the scan rather
    than the speed of the machine it runs on."""
    text = "# Page\n\n" + "```text\nunterminated code\n" * 20000
    started = time.monotonic()
    spans = list(codex_cli._iter_fence_spans(text))
    elapsed = time.monotonic() - started
    assert spans == []
    assert elapsed < 2.0, f"scanning {len(text)} characters took {elapsed:.2f}s"


def test_codex_fetch_markdown_refuses_to_fetch_without_discovered_slugs():
    """The link passes resolve each reference against the pages this run
    mirrors, so a hook that ran without that set would rewrite every internal
    link to its upstream URL (see ``ensure_known_slugs``) and the manifest
    would record the result as the page's correct content. The guard fails
    loudly instead -- as a ``FetchError``, the one type the pipeline isolates
    per page -- and does so BEFORE the download, so a run that skipped
    discovery stops at the first page rather than downloading the whole
    source and then failing on every page."""
    codex_cli._KNOWN_SLUGS.clear()
    client = _FakeClient([_Resp(200, "# Config\n\nSome prose.\n")])
    page = Page(
        slug="config",
        source_url="https://github.com/openai/codex/blob/main/docs/config.md",
        source_md_url="https://raw.githubusercontent.com/openai/codex/main/docs/config.md",
        source_id="config",
        group="",
    )
    with pytest.raises(fetch.FetchError, match="no discovered slugs"):
        codex_cli.fetch_markdown(client, page)
    assert client.calls == 0


def test_codex_fetch_markdown_rewrites_root_links_with_anchors():
    """``../SECURITY.md`` / ``../LICENSE`` links (with or without a
    ``#anchor``) must be rewritten to canonical upstream GitHub URLs so they
    resolve outside the mirrored docs/ tree; unrelated links must pass
    through untouched."""
    raw = (
        "# Config\n\n"
        "See [security](../SECURITY.md) and [reporting](../SECURITY.md#policy) "
        "plus [license](../LICENSE); keep [local](./local.md) as-is."
    )
    client = _FakeClient([_Resp(200, raw)])
    page = Page(
        slug="config",
        source_url="https://github.com/openai/codex/blob/main/docs/config.md",
        source_md_url="https://raw.githubusercontent.com/openai/codex/main/docs/config.md",
        source_id="config",
        group="",
    )
    _seed_codex_slugs("config")
    md, digest = codex_cli.fetch_markdown(client, page)
    assert "https://github.com/openai/codex/blob/main/SECURITY.md" in md
    assert "https://github.com/openai/codex/blob/main/SECURITY.md#policy" in md
    assert "https://github.com/openai/codex/blob/main/LICENSE" in md
    assert "(./local.md)" in md
    assert digest == fetch.content_hash(md)


def test_codex_how_mirrored_metadata():
    """Verify CONFIG metadata names both origins of the mirrored corpus.

    Most pages come from the documentation index (served by learn.chatgpt.com)
    and the rest from the repository's own ``docs/`` tree, so the generated
    tables in the root README and the per-source index must say both -- a
    description that mentions only the repository hides where the majority of
    the pages come from (and, with them, which license governs them).
    """
    assert "learn.chatgpt.com" in codex_cli.CONFIG.how_mirrored
    assert "openai/codex" in codex_cli.CONFIG.how_mirrored
    assert "learn.chatgpt.com" in codex_cli.CONFIG.origin
    assert "github.com/openai/codex" in codex_cli.CONFIG.origin


def test_codex_normalize_route_and_md_twin_url():
    """Route normalization and anchor stripping for Codex CLI stub endpoints."""
    # Anchor is stripped and .md appended
    url = "https://developers.openai.com/codex/cli/features#running-in-interactive-mode"
    assert codex_cli.to_md_twin_url(url) == (
        "https://developers.openai.com/codex/cli/features.md"
    )

    # Route rewrite: codex/execpolicy -> codex/exec-policy
    assert codex_cli.to_md_twin_url(
        "https://developers.openai.com/codex/execpolicy"
    ) == ("https://developers.openai.com/codex/exec-policy.md")
    assert codex_cli.to_md_twin_url(
        "https://developers.openai.com/codex/execpolicy#rules"
    ) == ("https://developers.openai.com/codex/exec-policy.md")

    # learn.chatgpt.com domain support
    assert codex_cli.to_md_twin_url("https://learn.chatgpt.com/codex/execpolicy") == (
        "https://learn.chatgpt.com/codex/exec-policy.md"
    )

    # Already ending with .md
    assert codex_cli.to_md_twin_url(
        "https://developers.openai.com/codex/guides/agents-md.md"
    ) == ("https://developers.openai.com/codex/guides/agents-md.md")


def test_codex_fetch_markdown_resolves_pure_stub():
    """A pure stub pointing to developers.openai.com fetches the rich .md twin.
    If the remote twin lacks an H1, the stub's heading is preserved."""
    stub_raw = (
        "# AGENTS.md\n\n"
        "For information about AGENTS.md, see "
        "[this documentation](https://developers.openai.com/codex/guides/agents-md).\n"
    )
    rich_twin = (
        "> For the complete documentation index, see [llms.txt](https://learn.chatgpt.com/llms.txt).\n\n"
        "Codex reads `AGENTS.md` files before doing any work.\n\n"
        "## How Codex discovers guidance\n\n"
        "Precedence order details here.\n"
    )
    # 1st response: GitHub raw stub; 2nd response: rich .md twin
    client = _FakeClient([_Resp(200, stub_raw), _Resp(200, rich_twin)])
    page = Page(
        slug="agents_md",
        source_url="https://github.com/openai/codex/blob/main/docs/agents_md.md",
        source_md_url="https://raw.githubusercontent.com/openai/codex/main/docs/agents_md.md",
        source_id="docs/agents_md.md",
        group="root",
    )
    _seed_codex_slugs("agents_md")
    md, digest = codex_cli.fetch_markdown(client, page)
    # Heading # AGENTS.md is retained because rich_twin lacked an H1
    assert md.startswith("# AGENTS.md\n\n")
    assert "Codex reads `AGENTS.md` files before doing any work." in md
    assert "## How Codex discovers guidance" in md
    assert digest == fetch.content_hash(md)


def test_codex_fetch_markdown_resolves_pure_stub_with_remote_h1():
    """When the remote .md twin already contains an H1 heading, it is kept
    without duplicating the stub's heading."""
    stub_raw = (
        "# Authentication\n\n"
        "For information about Codex CLI authentication, see "
        "[this documentation](https://developers.openai.com/codex/auth).\n"
    )
    rich_twin = (
        "# Authentication\n\n"
        "> For the complete documentation index...\n\n"
        "## OpenAI authentication\n\n"
        "Codex supports two ways for a person to sign in.\n"
    )
    client = _FakeClient([_Resp(200, stub_raw), _Resp(200, rich_twin)])
    page = Page(
        slug="authentication",
        source_url="https://github.com/openai/codex/blob/main/docs/authentication.md",
        source_md_url="https://raw.githubusercontent.com/openai/codex/main/docs/authentication.md",
        source_id="docs/authentication.md",
        group="root",
    )
    _seed_codex_slugs("authentication")
    md, digest = codex_cli.fetch_markdown(client, page)
    # Exactly one "# Authentication" heading
    assert md.count("# Authentication") == 1
    assert "## OpenAI authentication" in md
    assert digest == fetch.content_hash(md)


def test_codex_fetch_markdown_fallback_on_error(capsys):
    """If the external .md twin fetch fails (e.g. 404), a warning is logged
    to stderr and fetch_markdown gracefully falls back to the original GitHub text."""
    stub_raw = (
        "# AGENTS.md\n\n"
        "For information about AGENTS.md, see "
        "[this documentation](https://developers.openai.com/codex/guides/agents-md).\n"
    )
    # 1st response: 200 (GitHub); 2nd response: 404 (developers.openai.com)
    client = _FakeClient([_Resp(200, stub_raw), _Resp(404, "Not Found")])
    page = Page(
        slug="agents_md",
        source_url="https://github.com/openai/codex/blob/main/docs/agents_md.md",
        source_md_url="https://raw.githubusercontent.com/openai/codex/main/docs/agents_md.md",
        source_id="docs/agents_md.md",
        group="root",
    )
    _seed_codex_slugs("agents_md")
    md, digest = codex_cli.fetch_markdown(client, page)
    # Gracefully returns the original stub text
    assert md == stub_raw
    assert digest == fetch.content_hash(stub_raw)

    err = capsys.readouterr().err
    assert "warning:" in err
    assert "failed to fetch rich docs from" in err
    assert "agents_md" in err


def test_codex_fetch_markdown_resolves_hybrid_page():
    """Hybrid pages like config.md with multiple stub links and local sections
    are combined into a composite document with demoted subheadings."""
    config_raw = (
        "# Configuration\n\n"
        "For basic configuration instructions, see [this documentation](https://developers.openai.com/codex/config-basic).\n\n"
        "For advanced configuration instructions, see [this documentation](https://developers.openai.com/codex/config-advanced).\n\n"
        "## Lifecycle hooks\n\n"
        "Admins can set top-level allow_managed_hooks_only = true in requirements.toml.\n"
    )
    basic_twin = (
        "Codex reads configuration details from more than one location.\n\n"
        "## Codex configuration file\n\n"
        "User-level config at ~/.codex/config.toml.\n"
    )
    advanced_twin = (
        "# Advanced Configuration\n\n"
        "Use these options when you need more control.\n\n"
        "## Profiles\n\n"
        "Profiles let you save named configurations.\n"
    )
    client = _FakeClient(
        [
            _Resp(200, config_raw),
            _Resp(200, basic_twin),
            _Resp(200, advanced_twin),
        ]
    )
    page = Page(
        slug="config",
        source_url="https://github.com/openai/codex/blob/main/docs/config.md",
        source_md_url="https://raw.githubusercontent.com/openai/codex/main/docs/config.md",
        source_id="docs/config.md",
        group="root",
    )
    _seed_codex_slugs("config")
    md, digest = codex_cli.fetch_markdown(client, page)

    # Top heading # Configuration remains
    assert md.startswith("# Configuration\n\n")
    # Basic config section derived and demoted
    assert "## Basic Configuration" in md
    assert "### Codex configuration file" in md
    # Advanced config demoted from # to ##, and ## Profiles demoted to ### Profiles
    assert "## Advanced Configuration" in md
    assert "### Profiles" in md
    # Local section preserved
    assert "## Lifecycle hooks" in md
    assert "allow_managed_hooks_only = true" in md
    assert digest == fetch.content_hash(md)


def test_codex_fetch_markdown_hybrid_page_partial_fallback(capsys):
    """If one subpage fetch fails in a hybrid page, that link is preserved as fallback
    while successful subpages are still resolved."""
    config_raw = (
        "# Configuration\n\n"
        "For basic configuration instructions, see [this documentation](https://developers.openai.com/codex/config-basic).\n\n"
        "For advanced configuration instructions, see [this documentation](https://developers.openai.com/codex/config-advanced).\n\n"
        "## Lifecycle hooks\n\n"
        "Local section text.\n"
    )
    basic_twin = "## Basic info\n\nBasic setup details.\n"
    # Basic succeeds, advanced 404s
    client = _FakeClient(
        [
            _Resp(200, config_raw),
            _Resp(200, basic_twin),
            _Resp(404, "Not Found"),
        ]
    )
    page = Page(
        slug="config",
        source_url="https://github.com/openai/codex/blob/main/docs/config.md",
        source_md_url="https://raw.githubusercontent.com/openai/codex/main/docs/config.md",
        source_id="docs/config.md",
        group="root",
    )
    _seed_codex_slugs("config")
    md, digest = codex_cli.fetch_markdown(client, page)

    # Basic section resolved
    assert "Basic setup details." in md
    # Advanced section preserved as fallback link
    assert (
        "For advanced configuration instructions, see [this documentation]"
        "(https://developers.openai.com/codex/config-advanced)." in md
    )
    # Local section preserved
    assert "## Lifecycle hooks" in md

    err = capsys.readouterr().err
    assert "warning:" in err
    assert "failed to fetch rich docs" in err


def test_codex_discover_skips_bare_md_filename_and_guards_zero_pages():
    """A repo file named exactly ``.md`` at the docs root would yield an
    empty slug (which ``Page`` rejects with an uncaught ValueError) and must
    be skipped instead. When that skip leaves discovery empty, the zero-page
    guard must raise rather than return [] -- an empty result would make the
    pipeline delete every mirrored file."""
    client = tree_client([blob_entry("docs/.md")])
    client._script.append(_Resp(200, ""))
    with pytest.raises(RuntimeError, match="zero-page"):
        codex_cli.discover(client)


def test_codex_discover_with_llms_txt(capsys):
    """Discovery merges direct GitHub repository files and codex/llms.txt pages.
    Deduplicates against seen slugs (first discovery wins) and assigns correct
    slugs, groups, and canonical source URLs."""
    import json

    tree_payload = {
        "truncated": False,
        "tree": [
            blob_entry("docs/config.md"),
            blob_entry("docs/administration.md"),  # git tree discovery
        ],
    }
    llms_txt_body = (
        "# Codex Docs\n\n"
        "- [Record & Replay](https://learn.chatgpt.com/docs/extend/record-and-replay.md)\n"
        "- [Subagents](https://learn.chatgpt.com/docs/agent-configuration/subagents.md)\n"
        "- [Administration](https://learn.chatgpt.com/docs/administration.md)\n"  # duplicate slug: git tree wins
        "- [External Site](https://other.com/docs/something.md)\n"  # filtered out by domain
        "- [Text File](https://learn.chatgpt.com/docs/llms-full.txt)\n"  # filtered out (.txt)
    )
    client = _FakeClient(
        [
            _Resp(200, json.dumps(tree_payload)),
            _Resp(200, llms_txt_body),
        ]
    )
    pages = codex_cli.discover(client)

    # Slugs are sorted alphabetically
    assert [p.slug for p in pages] == [
        "administration",
        "agent-configuration/subagents",
        "config",
        "extend/record-and-replay",
    ]

    by_slug = {p.slug: p for p in pages}

    # Git tree page
    assert by_slug["config"].group == "root"
    assert by_slug["config"].source_id == "docs/config.md"

    # Git tree duplicate of administration won over llms.txt
    assert by_slug["administration"].group == "root"
    assert by_slug["administration"].source_id == "docs/administration.md"

    # LLMS nested pages
    assert by_slug["extend/record-and-replay"].group == "extend"
    assert (
        by_slug["extend/record-and-replay"].source_url
        == "https://learn.chatgpt.com/docs/extend/record-and-replay"
    )
    assert (
        by_slug["extend/record-and-replay"].source_md_url
        == "https://learn.chatgpt.com/docs/extend/record-and-replay.md"
    )
    assert (
        by_slug["extend/record-and-replay"].source_id == "llms:extend/record-and-replay"
    )

    assert by_slug["agent-configuration/subagents"].group == "agent-configuration"
    assert (
        by_slug["agent-configuration/subagents"].source_url
        == "https://learn.chatgpt.com/docs/agent-configuration/subagents"
    )
    assert (
        by_slug["agent-configuration/subagents"].source_id
        == "llms:agent-configuration/subagents"
    )

    # Check that _KNOWN_SLUGS was populated
    assert codex_cli._KNOWN_SLUGS == {
        "administration",
        "agent-configuration/subagents",
        "config",
        "extend/record-and-replay",
    }

    # Verify duplicate warning on stderr for administration
    err = capsys.readouterr().err
    assert "warning:" in err
    assert "duplicate slug 'administration'" in err


def test_codex_discover_llms_txt_fallback_on_error(capsys):
    """If fetching llms.txt fails (e.g. 404 or network error), a warning is logged
    to stderr and discovery continues with GitHub repository pages only."""
    import json

    tree_payload = {
        "truncated": False,
        "tree": [
            blob_entry("docs/config.md"),
        ],
    }
    # 1st call: git tree (200); 2nd call: llms.txt (404)
    client = _FakeClient(
        [
            _Resp(200, json.dumps(tree_payload)),
            _Resp(404, "Not Found"),
        ]
    )
    pages = codex_cli.discover(client)
    assert [p.slug for p in pages] == ["config"]
    assert codex_cli._KNOWN_SLUGS == {"config"}

    err = capsys.readouterr().err
    assert "warning: failed to fetch llms.txt index" in err
    assert "continuing with GitHub repository pages only" in err


def test_codex_rewrite_cross_links():
    """Verify _rewrite_cross_links transforms cross-doc URLs to relative paths:
    - Root-to-nested relative path calculation
    - Nested-to-nested relative path calculation
    - Anchor preservation (#anchor)
    - Untouched external links or links to unknown slugs
    """
    known_slugs = {
        "skills",
        "extend/record-and-replay",
        "agent-configuration/subagents",
    }

    # 1. Root to nested (skills -> ./extend/record-and-replay.md)
    root_text = (
        "Check out [Record & Replay](https://learn.chatgpt.com/docs/extend/record-and-replay) "
        "and [Direct MD](https://developers.openai.com/docs/extend/record-and-replay.md)."
    )
    rewritten_root = codex_cli._rewrite_cross_links(
        root_text, current_slug="skills", known_slugs=known_slugs
    )
    assert "[Record & Replay](./extend/record-and-replay.md)" in rewritten_root
    assert "[Direct MD](./extend/record-and-replay.md)" in rewritten_root

    # 2. Nested to nested (extend/record-and-replay -> ../agent-configuration/subagents.md)
    nested_text = (
        "Configure agents via "
        "[Subagents](https://learn.chatgpt.com/docs/agent-configuration/subagents)."
    )
    rewritten_nested = codex_cli._rewrite_cross_links(
        nested_text,
        current_slug="extend/record-and-replay",
        known_slugs=known_slugs,
    )
    assert "[Subagents](../agent-configuration/subagents.md)" in rewritten_nested

    # 3. Anchor preservation (#anchor)
    anchor_text = (
        "See [Custom Agents](https://learn.chatgpt.com/docs/agent-configuration/subagents#custom-agents) "
        "for more details."
    )
    rewritten_anchor = codex_cli._rewrite_cross_links(
        anchor_text, current_slug="skills", known_slugs=known_slugs
    )
    assert (
        "[Custom Agents](./agent-configuration/subagents.md#custom-agents)"
        in rewritten_anchor
    )

    # 4. Untouched: external domains and unknown slugs
    untouched_text = (
        "See [External](https://example.com/docs/extend/record-and-replay) and "
        "[Unknown Page](https://learn.chatgpt.com/docs/unknown/feature#anchor)."
    )
    rewritten_untouched = codex_cli._rewrite_cross_links(
        untouched_text, current_slug="skills", known_slugs=known_slugs
    )
    assert rewritten_untouched == untouched_text


def test_codex_fetch_markdown_for_llms_page():
    """Pages discovered via llms.txt are fetched via fetch_validated and have
    root link and cross-link rewrites applied."""
    raw_content = (
        "# Record & Replay\n\n"
        "See [Subagents](https://learn.chatgpt.com/docs/agent-configuration/subagents).\n"
    )
    client = _FakeClient([_Resp(200, raw_content)])
    page = Page(
        slug="extend/record-and-replay",
        source_url="https://learn.chatgpt.com/docs/extend/record-and-replay",
        source_md_url="https://learn.chatgpt.com/docs/extend/record-and-replay.md",
        source_id="llms:extend/record-and-replay",
        group="extend",
    )
    _seed_codex_slugs("extend/record-and-replay", "agent-configuration/subagents")
    md, digest = codex_cli.fetch_markdown(client, page)
    assert "[Subagents](../agent-configuration/subagents.md)" in md
    assert digest == fetch.content_hash(md)


def test_codex_clean_overview_landing():
    """<CodexDocsOverviewLanding> components are converted to structured CommonMark
    outlines with headers, descriptions, recommended guide links, and resolved
    relative links for section pages."""
    raw = (
        "# Administration\n\n"
        "> Banner text.\n\n"
        "<CodexDocsOverviewLanding\n"
        '  title="Administration"\n'
        '  description="Access and policy boundaries."\n'
        '  intro="Detailed introduction to boundaries."\n'
        "  primaryCta={{\n"
        '    label: "Explore authentication",\n'
        '    href: "/codex/auth?surface=app",\n'
        "  }}\n"
        "  sections={[\n"
        "    {\n"
        '      title: "Getting started",\n'
        '      description: "Start with the rollout guide.",\n'
        "      pages: [\n"
        "        {\n"
        '          title: "Admin rollout guide",\n'
        '          description: "Plan access and controls.",\n'
        '          href: "/codex/enterprise/admin-setup",\n'
        "        },\n"
        "        {\n"
        '          title: "External doc",\n'
        '          description: "Not mirrored.",\n'
        '          href: "/codex/unmirrored-topic",\n'
        "        },\n"
        "      ],\n"
        "    },\n"
        "  ]}\n"
        "/>\n"
    )
    known = {"administration", "auth", "enterprise/admin-setup"}
    cleaned = codex_cli._clean_mdx_components(raw, "administration", known)
    assert "# Administration" in cleaned
    assert "Access and policy boundaries." in cleaned
    assert "Detailed introduction to boundaries." in cleaned
    assert "> **Recommended:** [Explore authentication](./auth.md)" in cleaned
    assert "## Getting started" in cleaned
    assert "Start with the rollout guide." in cleaned
    assert (
        "- [Admin rollout guide](./enterprise/admin-setup.md) — Plan access and controls."
        in cleaned
    )
    assert (
        "- [External doc](https://developers.openai.com/codex/unmirrored-topic) — Not mirrored."
        in cleaned
    )
    assert "<CodexDocsOverviewLanding" not in cleaned


def test_codex_clean_file_tree():
    """<FileTree> components are converted to indented ASCII text directory
    trees enclosed in code blocks."""
    raw = (
        "<FileTree\n"
        '  class="mt-4"\n'
        "  tree={[\n"
        "    {\n"
        '      name: "AGENTS.md",\n'
        '      comment: "Repository expectations",\n'
        "    },\n"
        "    {\n"
        '      name: "services/",\n'
        "      children: [\n"
        "        {\n"
        '          name: "payments/",\n'
        "          children: [\n"
        '            { name: "README.md" },\n'
        "          ],\n"
        "        },\n"
        "      ],\n"
        "    },\n"
        "  ]}\n"
        "/>\n"
    )
    cleaned = codex_cli._clean_mdx_components(raw, "sample-slug", set())
    assert "```text" in cleaned
    assert "AGENTS.md  # Repository expectations" in cleaned
    assert "services/\n  payments/\n    README.md" in cleaned
    assert "<FileTree" not in cleaned


def test_codex_clean_toggle_section():
    """<ToggleSection> components are converted to standard HTML details blocks."""
    raw = (
        '<ToggleSection title="Detailed comparison">\n'
        "Here is the collapsible content.\n"
        "</ToggleSection>\n"
    )
    cleaned = codex_cli._clean_mdx_components(raw, "sample-slug", set())
    assert (
        "<details>\n<summary>Detailed comparison</summary>\n\n"
        "Here is the collapsible content.\n\n</details>" in cleaned
    )
    assert "<ToggleSection" not in cleaned


def test_codex_unwrap_wrappers_and_strip_badges():
    """Structural wrappers (<ContentModeSwitch>, <WorkflowSteps>, <Tabs>) are unwrapped,
    comments are stripped, and visual/interactive badges (<ElevatedRiskBadge>, <ConfigTable>)
    are removed."""
    raw = (
        "{/* prettier-ignore */}\n"
        "<WorkflowSteps>\n"
        "1. Step one\n"
        "2. Step two\n"
        "</WorkflowSteps>\n\n"
        '<ContentModeSwitch group="surface" id="cli">\n'
        "CLI specific instructions <ElevatedRiskBadge />\n"
        "</ContentModeSwitch>\n\n"
        "<ConfigTable client:load options={globalFlagOptions} />\n"
    )
    cleaned = codex_cli._clean_mdx_components(raw, "sample-slug", set())
    assert "prettier-ignore" not in cleaned
    assert "1. Step one\n2. Step two" in cleaned
    assert "<WorkflowSteps>" not in cleaned
    assert "CLI specific instructions" in cleaned
    assert "<ContentModeSwitch" not in cleaned
    assert "<ElevatedRiskBadge" not in cleaned
    assert "<ConfigTable" not in cleaned


def test_codex_clean_model_details_and_pricing_cards():
    """<ModelDetails> and <PricingCard> components are converted to Markdown
    sections with feature lists."""
    raw_model = (
        "<ModelDetails\n"
        '  name="gpt-6-astra"\n'
        '  description="Most capable model."\n'
        "  data={{\n"
        "    features: [\n"
        '      { title: "Codex CLI", value: true },\n'
        '      { title: "Codex cloud", value: false },\n'
        "    ],\n"
        "  }}\n"
        "/>\n"
    )
    cleaned_model = codex_cli._clean_mdx_components(raw_model, "models", set())
    assert "### `gpt-6-astra`" in cleaned_model
    assert "Most capable model." in cleaned_model
    assert "- **Codex CLI**: Supported" in cleaned_model
    assert "- **Codex cloud**: Not supported" in cleaned_model

    raw_pricing = (
        "<PricingCard\n"
        '  name="Plus"\n'
        '  price="$20"\n'
        '  interval="/month"\n'
        '  subtitle="Power focused coding."\n'
        '  ctaLabel="Get Plus"\n'
        '  ctaHref="https://chatgpt.com/plans/plus"\n'
        ">\n"
        "- Feature 1\n"
        "- Feature 2\n"
        "</PricingCard>\n"
    )
    cleaned_pricing = codex_cli._clean_mdx_components(raw_pricing, "pricing", set())
    assert "### Plus ($20/month)" in cleaned_pricing
    assert "Power focused coding." in cleaned_pricing
    assert "[Get Plus](https://chatgpt.com/plans/plus)" in cleaned_pricing
    assert "- Feature 1\n- Feature 2" in cleaned_pricing


def test_codex_clean_protects_fenced_code():
    """Fenced code blocks containing MDX-like syntax or component names remain
    completely unchanged."""
    raw = '```markdown\n<ContentModeSwitch group="test">\n<FileTree tree={[]} />\n```\n'
    cleaned = codex_cli._clean_mdx_components(raw, "slug", set())
    assert cleaned.strip() == raw.strip()


def test_codex_clean_config_table_keeps_data_after_multiline_tag():
    """A <ConfigTable> renders as a Markdown table, and none of its entries are
    lost to a multi-line opening tag.

    The regression this pins: the opening tag spans many lines and its data
    contains ``>`` characters (``type: "array<string>"``). A tag matcher that
    stops at the first ``>`` -- or that treats ``/>`` inside the data as the end
    of the tag -- silently deletes every entry before that character, which took
    documented configuration keys such as ``model`` and ``approval_policy`` out
    of the mirrored reference. Every entry of both tables must survive, and the
    tag itself must be gone.
    """
    raw = (
        "# Configuration Reference\n\n"
        "<ConfigTable\n"
        "  options={[\n"
        "    {\n"
        '      key: "model",\n'
        '      type: "string",\n'
        '      description: "Model to use (e.g., `gpt-5.5`).",\n'
        "    },\n"
        "    {\n"
        '      key: "allowed_sandbox_modes",\n'
        '      type: "array<string>",\n'
        '      description: "Allowed values for `sandbox_mode`.",\n'
        "    },\n"
        "    {\n"
        '      key: "sandbox_workspace_write.network_access",\n'
        '      type: "boolean",\n'
        '      description: "Allow outbound network access (`a | b`).",\n'
        "    },\n"
        "  ]}\n"
        "  client:load\n"
        "/>\n"
        "\nAfter the table.\n"
    )
    cleaned = codex_cli._clean_mdx_components(
        raw, "config-file/config-reference", set()
    )
    assert "<ConfigTable" not in cleaned
    assert "client:load" not in cleaned
    assert "| Key | Type | Description |" in cleaned
    # Every entry is present, including the ones that follow a `>` in the data.
    assert "| `model` | `string` | Model to use (e.g., `gpt-5.5`). |" in cleaned
    assert (
        "| `allowed_sandbox_modes` | `array<string>` | Allowed values for `sandbox_mode`. |"
        in cleaned
    )
    # A pipe inside a value is escaped so it cannot split the row into columns.
    assert r"(`a \| b`)" in cleaned
    assert "After the table." in cleaned


def test_codex_clean_glossary_table_links_terms():
    """A <GlossaryTable> becomes a term/applies-to/definition table whose terms
    link to the mirrored page when it exists and to the upstream URL when not."""
    raw = (
        "<GlossaryTable\n"
        "  client:load\n"
        '  searchPlaceholder="Filter by term"\n'
        "  options={[\n"
        "    {\n"
        '      key: "Agent",\n'
        '      href: "/codex/agent-configuration/subagents",\n'
        '      appliesTo: "Desktop app, CLI",\n'
        '      description: "The Codex agent that completes a task.",\n'
        "    },\n"
        "    {\n"
        '      key: "Appshot",\n'
        '      href: "/codex/appshots",\n'
        '      appliesTo: "Desktop app",\n'
        '      description: "Snapshot of the frontmost app window.",\n'
        "    },\n"
        "  ]}\n"
        "/>\n"
    )
    cleaned = codex_cli._clean_mdx_components(
        raw, "glossary", {"agent-configuration/subagents"}
    )
    assert "<GlossaryTable" not in cleaned
    assert "| Term | Applies to | Definition |" in cleaned
    assert (
        "| [Agent](./agent-configuration/subagents.md) | Desktop app, CLI | "
        "The Codex agent that completes a task. |" in cleaned
    )
    assert (
        "| [Appshot](https://developers.openai.com/codex/appshots) | Desktop app | "
        "Snapshot of the frontmost app window. |" in cleaned
    )


def test_codex_clean_plan_feature_matrix_renders_availability():
    """A <CodexPlanFeatureMatrix> becomes one table per section, with a column
    per plan and one row per capability."""
    raw = (
        "## Feature availability\n\n"
        "<CodexPlanFeatureMatrix\n"
        "  client:load\n"
        "  data={{\n"
        "    plans: [\n"
        '      { id: "plus", shortLabel: "Plus", label: "ChatGPT Plus" },\n'
        '      { id: "api", shortLabel: "API Key", label: "API Key" },\n'
        "    ],\n"
        "    sections: [\n"
        "      {\n"
        '        title: "Access and surfaces",\n'
        "        features: [\n"
        "          {\n"
        '            name: "Codex cloud",\n'
        '            href: "/codex/cloud",\n'
        '            availability: { plus: "available", api: "unavailable" },\n'
        "          },\n"
        "          {\n"
        '            name: "Codex IDE extension",\n'
        '            href: "/codex/ide",\n'
        '            availability: { plus: "limited", api: "unavailable" },\n'
        "          },\n"
        "        ],\n"
        "      },\n"
        "    ],\n"
        "  }}\n"
        "/>\n"
    )
    cleaned = codex_cli._clean_mdx_components(raw, "pricing", {"cloud"})
    assert "<CodexPlanFeatureMatrix" not in cleaned
    assert "### Access and surfaces" in cleaned
    assert "| Feature | ChatGPT Plus | API Key |" in cleaned
    assert "| [Codex cloud](./cloud.md) | Yes | No |" in cleaned
    assert (
        "| [Codex IDE extension](https://developers.openai.com/codex/ide) | Limited | No |"
        in cleaned
    )


def test_codex_clean_collection_list_and_prompt_component():
    """<CodexCollectionList> becomes a bulleted link list and <PromptComponent>
    becomes a fenced block holding the prompt verbatim."""
    raw = (
        "## More use cases\n\n"
        "<CodexCollectionList\n"
        "  slugs={[\n"
        '    "productivity-and-collaboration",\n'
        '    "data-science",\n'
        "  ]}\n"
        "/>\n"
        "\n"
        "<PromptComponent\n"
        "prompt={`Summarize the review feedback in / and prepare a plan.`}\n"
        "/>\n"
    )
    cleaned = codex_cli._clean_mdx_components(raw, "get-started-with-work", set())
    assert "<CodexCollectionList" not in cleaned
    assert "<PromptComponent" not in cleaned
    assert (
        "- [Productivity and collaboration]"
        "(https://learn.chatgpt.com/use-cases/collections/"
        "productivity-and-collaboration)" in cleaned
    )
    assert (
        "- [Data science]"
        "(https://learn.chatgpt.com/use-cases/collections/data-science)" in cleaned
    )
    assert (
        "```text\nSummarize the review feedback in / and prepare a plan.\n```"
        in cleaned
    )


def test_codex_clean_table_wrapper_becomes_markdown_table():
    """A <TableWrapper> around a plain HTML table becomes a Markdown table with
    the same header, alignment, and cells."""
    raw = (
        '<TableWrapper class="w-full min-w-[46rem]">\n'
        "  <thead>\n"
        "    <tr>\n"
        '      <th scope="col">Model</th>\n'
        '      <th scope="col" style="text-align:center">Plus</th>\n'
        "    </tr>\n"
        "  </thead>\n"
        "  <tbody>\n"
        "    <tr>\n"
        "      <td>GPT-6 Astra</td>\n"
        '      <td style="text-align:center">5-45</td>\n'
        "    </tr>\n"
        "  </tbody>\n"
        "</TableWrapper>\n"
    )
    cleaned = codex_cli._clean_mdx_components(raw, "pricing", set())
    assert "<TableWrapper" not in cleaned
    assert "<td>" not in cleaned and "<tr>" not in cleaned
    assert "| Model | Plus |" in cleaned
    assert "| --- | :---: |" in cleaned
    assert "| GPT-6 Astra | 5-45 |" in cleaned


def test_codex_clean_table_cell_keeps_a_greater_than_in_its_attributes():
    """A ``>`` inside a cell attribute does not truncate the cell.

    The regression this pins: the cell was delimited with ``[^>]*``, so an
    attribute value such as ``title="a > b"`` ended the cell tag early and the
    cell came back as the tail of its own attribute marker plus whatever text
    followed it, with the leading content gone.
    """
    raw = (
        "<TableWrapper>\n"
        "<thead>\n"
        '<tr><th scope="col">Col</th></tr>\n'
        "</thead>\n"
        "<tbody>\n"
        '<tr><td title="a > b">value</td></tr>\n'
        "</tbody>\n"
        "</TableWrapper>\n"
    )
    cleaned = codex_cli._clean_mdx_components(raw, "config", set())
    assert "| value |" in cleaned
    assert 'b">' not in cleaned


def test_codex_clean_flattens_a_table_nested_in_a_cell():
    """A table nested inside a cell is flattened into the text of that cell.

    The wrapper is only used around plain tables, and a nested one has no
    Markdown equivalent: its row markup belongs to the cell that holds it, so
    the cell text is what survives. This pins that the nested rows are not
    emitted as rows of the outer table.
    """
    raw = (
        "<TableWrapper>\n"
        "<thead>\n"
        '<tr><th scope="col">Outer</th></tr>\n'
        "</thead>\n"
        "<tbody>\n"
        "<tr><td>before <table><tr><td>inner</td></tr></table> after</td></tr>\n"
        "</tbody>\n"
        "</TableWrapper>\n"
    )
    cleaned = codex_cli._clean_mdx_components(raw, "config", set())
    assert "| Outer |" in cleaned
    assert "inner" in cleaned
    assert "| inner |" not in cleaned


def test_codex_clean_strips_visual_components_only_when_self_closing():
    """Decorative components are removed line-bounded, leaving no orphan
    ``client:*`` directive behind, while a container use of the same name is
    kept so its Markdown body cannot be deleted by mistake."""
    raw = (
        "# Models\n"
        "\n"
        "  <CodexReasoningLevelTerminal\n"
        "    client:load\n"
        '    className="lg:mt-7 lg:justify-self-end"\n'
        "  />\n"
        "\n"
        "<CodexModelSwitcher client:visible forceDark />\n"
        "\n"
        "Select <Settings /> to open settings.\n"
        "\n"
        "<ElevatedRiskBadge>\n"
        "This body carries documentation.\n"
        "</ElevatedRiskBadge>\n"
    )
    cleaned = codex_cli._clean_mdx_components(raw, "models", set())
    assert "<CodexReasoningLevelTerminal" not in cleaned
    assert "<CodexModelSwitcher" not in cleaned
    assert "<Settings" not in cleaned
    assert "client:" not in cleaned
    assert "Select  to open settings." in cleaned
    # The container form is NOT stripped: its body is content.
    assert "This body carries documentation." in cleaned


def test_codex_clean_labels_surfaces_and_emits_anchors():
    """Each <ContentModeSwitch> variant is labeled with its surface and every
    heading inside it gets the surface-prefixed anchor upstream links use."""
    raw = (
        "# Models\n"
        "\n"
        '<ContentModeSwitch group="codex-surface" id="app">\n'
        "\n"
        "## Choose a model\n"
        "\n"
        "In the desktop app, use the model switcher.\n"
        "\n"
        "</ContentModeSwitch>\n"
        "\n"
        '<ContentModeSwitch group="codex-surface" id="cli">\n'
        "\n"
        "## Choose a model\n"
        "\n"
        "In a CLI session, use `/model`.\n"
        "\n"
        "</ContentModeSwitch>\n"
        "\n"
        '<ContentModeSwitch group="codex-surface" ids="app,cli,ide">\n'
        "\n"
        "## Recommended models\n"
        "\n"
        "Recommendations for every surface.\n"
        "\n"
        "</ContentModeSwitch>\n"
    )
    cleaned = codex_cli._clean_mdx_components(raw, "models", set())
    assert "<ContentModeSwitch" not in cleaned
    # Each surface-only variant is labeled; the shared variant is not.
    assert "**Surface: Desktop app**" in cleaned
    assert "**Surface: CLI**" in cleaned
    assert cleaned.count("**Surface:") == 2
    # Surface-prefixed anchors resolve on every surface the section applies to.
    assert '<a id="app-choose-a-model"></a>' in cleaned
    assert '<a id="cli-choose-a-model"></a>' in cleaned
    assert '<a id="app-recommended-models"></a>' in cleaned
    assert '<a id="cli-recommended-models"></a>' in cleaned
    assert '<a id="ide-recommended-models"></a>' in cleaned
    # The heading text itself is untouched.
    assert cleaned.count("## Choose a model") == 2


def test_codex_clean_numbers_repeated_surface_anchors():
    """A page that repeats a surface section keeps one anchor per id.

    Upstream repeats whole sections, so the same surface-and-heading pair can
    occur twice on a page and would emit two anchors with one id. The first
    occurrence keeps the plain id, which is the one upstream links point at;
    the repeats are numbered so every id on the page stays unique.
    """
    raw = (
        '<ContentModeSwitch group="codex-surface" id="cli">\n'
        "\n"
        "#### Sign in\n"
        "\n"
        "First copy.\n"
        "\n"
        "</ContentModeSwitch>\n"
        "\n"
        '<ContentModeSwitch group="codex-surface" id="cli">\n'
        "\n"
        "#### Sign in\n"
        "\n"
        "Second copy.\n"
        "\n"
        "</ContentModeSwitch>\n"
    )
    cleaned = codex_cli._clean_mdx_components(raw, "auth", set())
    assert cleaned.count('<a id="cli-sign-in"></a>') == 1
    assert cleaned.count('<a id="cli-sign-in-2"></a>') == 1
    assert "First copy." in cleaned and "Second copy." in cleaned


def test_codex_clean_nested_content_mode_switches():
    """A surface switch nested inside another one is converted too, instead of
    being kept verbatim as part of the outer section's body."""
    raw = (
        '<ContentModeSwitch group="codex-surface" ids="app,web,cli,ide">\n'
        "\n"
        "## Recommended models\n"
        "\n"
        '<ContentModeSwitch group="codex-surface" id="app">\n'
        "\n"
        "### Compare models\n"
        "\n"
        "Open the compare view.\n"
        "\n"
        "</ContentModeSwitch>\n"
        "\n"
        "</ContentModeSwitch>\n"
    )
    cleaned = codex_cli._clean_mdx_components(raw, "models", set())
    assert "<ContentModeSwitch" not in cleaned
    assert '<a id="app-compare-models"></a>' in cleaned
    assert '<a id="ide-recommended-models"></a>' in cleaned
    assert "Open the compare view." in cleaned


def test_codex_clean_deindents_component_output():
    """A component indented by its MDX container renders at column zero, so its
    headings are headings instead of four-space indented code blocks."""
    raw = (
        '<ToggleSection title="View other models">\n'
        "  \n"
        "\n"
        "    <ModelDetails\n"
        '      name="gpt-5.4"\n'
        '      description="Previous-generation flagship model."\n'
        "      data={{\n"
        "        features: [\n"
        '          { title: "Codex CLI", value: true },\n'
        "        ],\n"
        "      }}\n"
        "    />\n"
        "\n"
        "    <ModelDetails\n"
        '      name="gpt-5.4-mini"\n'
        '      description="Fast, efficient mini model."\n'
        "      data={{ features: [] }}\n"
        "    />\n"
        "</ToggleSection>\n"
    )
    cleaned = codex_cli._clean_mdx_components(raw, "models", set())
    # Both headings -- the first one and the one that follows a sibling
    # component -- start at column zero.
    assert "\n### `gpt-5.4`\n" in cleaned
    assert "\n### `gpt-5.4-mini`\n" in cleaned
    assert re.search(r"^[ \t]+#{1,6} ", cleaned, re.MULTILINE) is None


def test_codex_clean_model_details_survives_unparseable_props():
    """A component whose props the small JS parser cannot read is kept verbatim
    instead of raising and carrying the whole page forward stale."""
    raw = '<ModelDetails\n  name="broken"\n  data={ : }\n/>\n'
    cleaned = codex_cli._clean_mdx_components(raw, "models", set())
    assert "<ModelDetails" in cleaned


def test_codex_clean_keeps_unreadable_components_around_convertible_ones():
    """A component with unreadable props is preserved exactly, whatever the
    conversions of the components around it were.

    The regression this pins: the inline converters restored the component by
    slicing the enclosing variable, which still held the text from *before* the
    pass that had already rewritten an earlier component of the same name. The
    restored text then came from the wrong offsets -- on a mixed page the first
    ``<Alert>`` converted, and the second one came back as a fragment of its
    own tag plus a duplicated paragraph, losing the component.
    """
    raw = (
        "Before.\n"
        "\n"
        '<Alert description="Convertible note." />\n'
        "\n"
        '<Alert onClick={() => doThing()} description="Unreadable." />\n'
        "\n"
        "After.\n"
    )
    cleaned = codex_cli._clean_mdx_components(raw, "slug", set())
    # The readable component converted, and only once.
    assert "> [!NOTE]\n> Convertible note." in cleaned
    assert cleaned.count("> [!NOTE]") == 1
    # The unreadable one survived whole, with no duplicated tail.
    assert '<Alert onClick={() => doThing()} description="Unreadable." />' in cleaned
    assert cleaned.count("Before.") == 1
    assert cleaned.count("After.") == 1
    assert "\n\n\n" not in cleaned


def test_codex_clean_keeps_unreadable_inline_components_verbatim():
    """The same restoration guard on the remaining inline converters: an
    unreadable component is left byte for byte as upstream wrote it, including
    when a convertible sibling of the same name precedes it in the page.

    The sibling is what makes the second pass necessary, and the second pass is
    where the stale slice used to return a run of characters belonging to the
    already-converted text instead of the component.
    """
    for convertible, unreadable in (
        (
            '<CtaPillLink href="/codex/start" label="Start" />',
            '<CtaPillLink href={() => go()} label="Go" />',
        ),
        (
            '<ButtonLink href="/codex/start">Start</ButtonLink>',
            "<ButtonLink href={() => go()}>Go</ButtonLink>",
        ),
        (
            '<CodexCallout title="Guide" href="/codex/start" description="Text." />',
            '<CodexCallout title="Broken" href={() => go()} />',
        ),
    ):
        raw = f"{convertible}\n\n{unreadable}\n"
        cleaned = codex_cli._clean_mdx_components(raw, "slug", set())
        assert unreadable in cleaned
        assert convertible not in cleaned


def test_codex_clean_skips_an_unterminated_tag_and_converts_the_next_one():
    """An opening tag with no closing quote is left as-is, and a later
    occurrence of the same component is still converted.

    The regression this pins: the scan stopped at the first tag it could not
    delimit, so every later occurrence of that component name in the document
    was abandoned with it -- one malformed tag upstream silently removed all
    the well-formed ones from the page.
    """
    raw = (
        "Before.\n"
        "\n"
        "<Alert description='unterminated\n"
        "\n"
        "More text about the alert.\n"
        "\n"
        '<Alert description="valid note" />\n'
        "\n"
        "After.\n"
    )
    cleaned = codex_cli._clean_mdx_components(raw, "slug", set())
    assert "> [!NOTE]\n> valid note" in cleaned
    # The malformed tag itself is kept verbatim, and nothing was duplicated.
    assert "<Alert description='unterminated" in cleaned
    assert cleaned.count("More text about the alert.") == 1


def test_codex_clean_does_not_let_an_unterminated_tag_swallow_its_sibling():
    """An unquoted ``>`` inside an unterminated tag's props does not consume the
    next component of the same name.

    A scan that runs past its own tag boundary reads the *next* ``<Alert ...>``
    as the end of the first one, so that component would come back as a
    fragment of the broken tag's text and lose its own conversion.
    """
    raw = (
        '<Alert description="unterminated\n'
        "\n"
        "Prose between the two tags.\n"
        "\n"
        '<Alert description="valid note" />\n'
    )
    cleaned = codex_cli._clean_mdx_components(raw, "slug", set())
    assert "> [!NOTE]\n> valid note" in cleaned
    assert "Prose between the two tags." in cleaned


def test_codex_clean_many_unterminated_tags_completes_quickly():
    """A document of unterminated tags is scanned in linear time.

    Every tag is malformed on purpose, which is the shape that made the scan
    quadratic: each tag walked to the end of the document, so the work grew
    with the square of the page size. The bound is what keeps the mirror from
    stalling on a broken upstream page, and it is generous enough that only a
    return to quadratic behavior can trip it (the linear scan is two orders of
    magnitude below it).
    """
    import time

    unterminated = '<Alert description="x"\n' * 20000
    unclosed = '<Alert description="x">\n' * 20000
    for text in (unterminated, unclosed):
        start = time.perf_counter()
        cleaned = codex_cli._clean_mdx_components(text, "slug", set())
        assert time.perf_counter() - start < 5
        # Nothing was converted away, and the malformed tags are still there.
        assert cleaned.count("<Alert") == 20000


def test_codex_clean_collapses_whitespace_only_lines():
    """Lines holding nothing but the indentation of a removed component are
    collapsed to empty, keeping the mirrored page diff-clean."""
    raw = (
        "# Quickstart\n"
        "\n"
        "                Learn more about [ChatGPT](./use-chatgpt.md).\n"
        "\n"
        "              \n"
        "\n"
        "          <ChatGPTModeDropdown client:visible />\n"
        "\n"
        "    \n"
        "\n"
        "Next step text.\n"
    )
    cleaned = codex_cli._clean_mdx_components(raw, "quickstart", {"use-chatgpt"})
    assert re.search(r"^[ \t]+$", cleaned, re.MULTILINE) is None
    assert "Next step text." in cleaned


def test_codex_fetch_markdown_strips_frontmatter_and_keeps_title(capsys):
    """Astro frontmatter is dropped from the mirrored body, and its title is
    re-emitted as an H1 so the manifest keeps the page's real title."""
    raw = (
        "---\n"
        'title: "Codex Manual"\n'
        "hidden: true\n"
        "---\n"
        "\n"
        "> For the complete documentation index, see [llms.txt](/llms.txt).\n"
        "\n"
        "## Find By Topic\n"
        "\n"
        "Reference text.\n"
    )
    client = _FakeClient([_Resp(200, raw)])
    page = Page(
        slug="codex-manual",
        source_url="https://learn.chatgpt.com/docs/codex-manual",
        source_md_url="https://learn.chatgpt.com/docs/codex-manual.md",
        source_id="llms:codex-manual",
        group="root",
    )
    _seed_codex_slugs("codex-manual")
    md, digest = codex_cli.fetch_markdown(client, page)
    assert not md.startswith("---")
    assert "hidden: true" not in md
    assert md.startswith("# Codex Manual\n")
    assert fetch.extract_title(md, fallback="fallback") == "Codex Manual"
    # The site-absolute index link is routed through the link resolution.
    assert "[llms.txt](https://developers.openai.com/llms.txt)" in md
    assert digest == fetch.content_hash(md)


def test_codex_strip_frontmatter_keeps_a_leading_thematic_break():
    """A document that opens with a thematic break keeps its content.

    The regression this pins: the block between two ``---`` lines was dropped
    whenever the document *started* with one, so a page written as a rule, a
    blank line, a section, and another rule lost that middle section -- the
    visible text went to the body while the source's own middle block was
    deleted. Only a block that reads as YAML (keys from its first line on) is
    frontmatter.
    """
    raw = "---\n\nIMPORTANT SECTION CONTENT\n\n---\n\nRest of doc.\n"
    assert codex_cli._strip_frontmatter(raw) == raw

    # A real frontmatter block is still dropped, with its title kept as the H1.
    frontmatter = '---\ntitle: "Codex Manual"\nhidden: true\n---\n\nBody text.\n'
    stripped = codex_cli._strip_frontmatter(frontmatter)
    assert stripped.startswith("# Codex Manual\n")
    assert "hidden: true" not in stripped
    assert "Body text." in stripped

    # A rule at the top followed by more rules is prose throughout.
    rules = "---\n\nSection A\n\n---\n\nSection B\n\n---\n\nSection C\n"
    assert codex_cli._strip_frontmatter(rules) == rules


def test_codex_fetch_markdown_keeps_long_fences_and_their_examples():
    """A fence longer than three characters shields its whole content.

    The regression this pins: the shielding regex closed a block at the first
    three-character run inside it, so a four-backtick example documenting
    three-backtick fences ended early. Everything after that inner run -- the
    example's second half, the component tags shown in it, and the links it
    demonstrates -- was then converted as if it were page text. The link
    rewrites run after the shielding pass, so they are covered here too.
    """
    raw = (
        "# Page\n"
        "\n"
        "````markdown\n"
        "Example:\n"
        "\n"
        "```bash\n"
        "codex exec\n"
        "```\n"
        "\n"
        '<Alert description="Do not convert me." />\n'
        "\n"
        "[cross](/codex/quickstart) and [root](../SECURITY.md)\n"
        "````\n"
        "\n"
        "Prose link: [cross](/codex/quickstart).\n"
    )
    client = _FakeClient([_Resp(200, raw)])
    page = Page(
        slug="config",
        source_url="https://learn.chatgpt.com/docs/config",
        source_md_url="https://learn.chatgpt.com/docs/config.md",
        source_id="llms:config",
        group="root",
    )
    _seed_codex_slugs("config", "quickstart")
    md, digest = codex_cli.fetch_markdown(client, page)
    # The example block reached the page exactly as upstream wrote it.
    fenced = raw.split("````markdown\n", 1)[1].rsplit("````", 1)[0]
    assert fenced in md
    assert '<Alert description="Do not convert me." />' in md
    assert "> [!NOTE]" not in md
    assert "[cross](/codex/quickstart)" in md
    assert "[root](../SECURITY.md)" in md
    # The same link written as prose is still rewritten.
    assert "[cross](./quickstart.md)" in md
    assert digest == fetch.content_hash(md)


def test_codex_fetch_markdown_rewrites_body_site_absolute_links():
    """Links written in a page's prose as site-absolute paths resolve to the
    mirrored file when it exists and to the upstream URL when it does not."""
    raw = (
        "# Auto review\n"
        "\n"
        "Configure [`[auto_review].policy`]"
        "(/codex/config-file/config-advanced#approval-policies-and-sandbox-modes).\n"
        "\n"
        "See [Learn more](/codex/not-mirrored-topic).\n"
    )
    client = _FakeClient([_Resp(200, raw)])
    page = Page(
        slug="sandboxing/auto-review",
        source_url="https://learn.chatgpt.com/docs/sandboxing/auto-review",
        source_md_url="https://learn.chatgpt.com/docs/sandboxing/auto-review.md",
        source_id="llms:sandboxing/auto-review",
        group="sandboxing",
    )
    _seed_codex_slugs("sandboxing/auto-review", "config-file/config-advanced")
    md, digest = codex_cli.fetch_markdown(client, page)
    assert (
        "[`[auto_review].policy`](../config-file/config-advanced.md"
        "#approval-policies-and-sandbox-modes)" in md
    )
    assert "[Learn more](https://developers.openai.com/codex/not-mirrored-topic)" in md
    assert digest == fetch.content_hash(md)


def test_codex_discover_skips_stub_with_mirrored_twin(capsys):
    """A GitHub reference stub whose rich twin is discovered as its own page is
    not mirrored, and the skip is recorded as a redirect for link rewriting."""
    import json

    tree_payload = {
        "truncated": False,
        "tree": [
            blob_entry("docs/skills.md"),
            blob_entry("docs/config.md"),
        ],
    }
    llms_txt_body = (
        "# Codex Docs\n\n"
        "- [Build skills](https://learn.chatgpt.com/docs/build-skills.md)\n"
    )
    client = _FakeClient(
        [
            _Resp(200, json.dumps(tree_payload)),
            _Resp(200, llms_txt_body),
        ]
    )
    pages = codex_cli.discover(client)

    # The stub is gone; the page that carries its content stays.
    assert [p.slug for p in pages] == ["build-skills", "config"]
    assert codex_cli._SLUG_REDIRECTS == {"skills": "build-skills"}
    err = capsys.readouterr().err
    assert "skipping reference stub 'skills'" in err
    assert "mirrored as 'build-skills'" in err

    # A stub whose twin is NOT discovered is mirrored as before: dropping it
    # would lose the document when the documentation index is unavailable.
    client = _FakeClient(
        [
            _Resp(200, json.dumps(tree_payload)),
            _Resp(404, "Not Found"),
        ]
    )
    pages = codex_cli.discover(client)
    assert [p.slug for p in pages] == ["config", "skills"]
    assert codex_cli._SLUG_REDIRECTS == {}


def test_codex_stub_twin_table_matches_mirrored_pairs():
    """The stub/twin table only names pages whose content upstream publishes
    twice: the GitHub reference stub, and the guide it points at."""
    assert codex_cli.STUB_TWIN_SLUGS == {
        "authentication": "auth",
        "sandbox": "security",
        "exec": "non-interactive-mode",
        "skills": "build-skills",
    }


def test_codex_links_follow_stub_redirects(monkeypatch):
    """Every internal reference shape that can name a skipped stub slug is
    repointed at the mirrored twin."""
    monkeypatch.setattr(codex_cli, "_SLUG_REDIRECTS", {"skills": "build-skills"})
    known = {"build-skills", "enterprise/skills", "guides/build-skills"}
    # Site-absolute reference (component href or body-link resolution path).
    assert (
        codex_cli._resolve_internal_href(
            "/codex/skills#where-to-save-skills", "import", known
        )
        == "./build-skills.md#where-to-save-skills"
    )
    # Absolute cross-documentation link.
    assert (
        codex_cli._rewrite_cross_links(
            "See [Skills](https://learn.chatgpt.com/docs/skills#where-to-save-skills).",
            "import",
            known,
        )
        == "See [Skills](./build-skills.md#where-to-save-skills)."
    )
    # Relative link from a nested page, traversing back up to the root.
    assert (
        codex_cli._rewrite_body_links(
            "[Skills](../skills.md)", "enterprise/skills", known
        )
        == "[Skills](../build-skills.md)"
    )
    # A link that names no skipped slug is left alone.
    assert (
        codex_cli._rewrite_body_links("[Skills](./build-skills.md)", "import", known)
        == "[Skills](./build-skills.md)"
    )


def test_codex_clean_has_no_component_remnants():
    """Representative converted output carries no MDX component tag and no
    orphan client directive.

    This is the guard that fails loudly if a future upstream adds a component,
    or changes one of these into a shape the converters do not recognize: the
    page would keep raw JSX instead of degrading quietly.
    """
    raw = (
        "# Sample\n"
        "\n"
        "<CodexDocsOverviewLanding\n"
        '  title="Sample"\n'
        '  primaryCta={{ label: "Start", href: "/codex/start" }}\n'
        "  sections={[\n"
        '    { title: "Guides", pages: [ { title: "Start", href: "/codex/start" }, ] },\n'
        "  ]}\n"
        "/>\n"
        "\n"
        '<WorkflowSteps variant="headings">\n'
        "1. First step\n"
        "2. Second step\n"
        "</WorkflowSteps>\n"
        "\n"
        '<ContentModeSwitch group="codex-surface" id="cli">\n'
        "## Run it\n"
        "</ContentModeSwitch>\n"
        "\n"
        "<FileTree tree={[ { name: 'AGENTS.md' } ]} />\n"
        "\n"
        "<ModelDetails\n"
        '  name="gpt-6"\n'
        '  description="Most capable model."\n'
        "  data={{ features: [ { title: 'CLI', value: true } ] }}\n"
        "/>\n"
        "\n"
        "<PricingCard\n"
        '  name="Plus"\n'
        '  price="$20"\n'
        '  interval="/month"\n'
        ">\n"
        "- Feature\n"
        "</PricingCard>\n"
        "\n"
        '<ToggleSection title="Details">\n'
        "Body text.\n"
        "</ToggleSection>\n"
        "\n"
        "<ConfigTable client:load options={[ { key: 'model', type: 'string' } ]} />\n"
        "\n"
        "<GlossaryTable client:load options={[ { key: 'Agent', description: 'Text.' } ]} />\n"
        "\n"
        "<CodexPlanFeatureMatrix\n"
        "  client:load\n"
        "  data={{ plans: [ { id: 'plus', label: 'Plus' } ],"
        " sections: [ { title: 'S', features:"
        " [ { name: 'F', availability: { plus: 'available' } } ] } ] }}\n"
        "/>\n"
        "\n"
        '<CodexCollectionList slugs={[ "data-science" ]} />\n'
        "\n"
        "<PromptComponent prompt={`Do the thing.`} />\n"
        "\n"
        '<TableWrapper class="w-full"><thead><tr><th>A</th></tr></thead>'
        "<tbody><tr><td>B</td></tr></tbody></TableWrapper>\n"
        "\n"
        "<WarningTip>\nCareful.\n</WarningTip>\n"
        "\n"
        '<Alert client:load description="Note text." />\n'
        "\n"
        '<CtaPillLink href="/codex/start" label="Start" />\n'
        "\n"
        '<ButtonLink href="/codex/start">Start</ButtonLink>\n'
        "\n"
        '<CodexCallout title="Guide" description="Text." href="/codex/start" />\n'
        "\n"
        '<CodexMicroTableKeycap label="Cmd" />\n'
        "\n"
        '<VideoPlayer src="https://cdn.openai.com/demo.mp4" />\n'
        "\n"
        '<CodexScreenshot src="/images/shot.png" alt="Shot" />\n'
        "\n"
        '<CodexReasoningLevelTerminal client:load className="mt-4" />\n'
        "\n"
        "Closing prose.\n"
    )
    cleaned = codex_cli._clean_mdx_components(raw, "sample", {"start"})
    assert re.search(r"<[A-Z][A-Za-z]*\b", cleaned) is None
    assert re.search(r"^\s*client:\S*\s*$", cleaned, re.MULTILINE) is None
    assert re.search(r"^[ \t]+$", cleaned, re.MULTILINE) is None
    # The conversions actually produced content rather than deleting it.
    assert "1. First step\n2. Second step" in cleaned
    assert "AGENTS.md" in cleaned
    assert "| Key | Type | Description |" in cleaned
    assert "| A |" in cleaned and "| B |" in cleaned
    assert "Careful." in cleaned
    assert "- Feature" in cleaned


def test_codex_version_fallback_matches_current_release():
    """The static version fallback is the release the mirror currently tracks;
    it is only used when the GitHub release lookup fails."""
    assert codex_cli.CONFIG.version == "0.154.0"


def test_kimi_discover_skips_bare_md_filename_and_guards_zero_pages():
    """Same degenerate-filename skip and zero-page guard as the Codex
    adapter, pinned for the nested Kimi docs tree."""
    client = tree_client([blob_entry("docs/en/.md")])
    with pytest.raises(RuntimeError, match="zero-page"):
        kimi_code.discover(client)


def test_deepseek_discover_raises_on_zero_pages():
    """If no sitemap URL survives the site-root filter (e.g. the upstream
    moved domains), discovery must raise instead of returning [] -- an empty
    result would make the pipeline delete every mirrored DeepSeek page."""
    sitemap = """<urlset>
      <url><loc>https://other.example.com/ignore</loc></url>
    </urlset>
    """
    with pytest.raises(RuntimeError, match="zero-page"):
        deepseek.discover(_FakeClient([_Resp(200, sitemap)]))


def test_deepseek_discover_raises_on_empty_sitemap():
    """A sitemap with NO ``<loc>`` entries at all (moved, emptied, or replaced
    by an HTML error page upstream) must raise with a DISTINCT message that
    names the sitemap -- not the generic "matched nothing" message the
    site-root-filter miss produces. Both cases must be loud (a zero-page
    discovery would delete every mirrored file), but the empty-sitemap path
    is a separate diagnostic that points the operator at the sitemap rather
    than at the filter. Mirrors ``antigravity.discover``'s two-stage guard;
    pinned here so a future refactor that collapses the two guards back into
    one does not silently regress the diagnosis."""
    sitemap = """<?xml version="1.0"?><urlset></urlset>"""
    with pytest.raises(RuntimeError, match="no <loc> entries"):
        deepseek.discover(_FakeClient([_Resp(200, sitemap)]))


# --- DeepSeek code-block integrity --------------------------------------------


def test_deepseek_html_to_markdown_keeps_fenced_block_verbatim():
    """A fenced code block containing a blank line must survive conversion
    intact: the blank line is semantically significant, and the closing fence
    must appear exactly once. These are the two ways a collapsing
    implementation can corrupt a prose-carried fence -- duplicating the
    closing fence, or collapsing blank lines INSIDE the block -- so both are
    pinned here.

    The fences here come from literal backticks in the HTML source (html2text
    renders ``<pre>`` as indented blocks, but prose fences pass through
    verbatim, with ``<br>`` becoming a hard line break) -- this is exactly
    how "docs documenting Markdown" arrive at the collapsing pass."""
    html = (
        '<div class="theme-doc-markdown"><h1>Markdown Guide</h1>'
        "<p>```<br>def foo():<br><br>    return 1<br>```</p>"
        "<p>trailing paragraph</p></div>"
    )
    md = deepseek._html_to_markdown(html)
    lines = md.splitlines()
    # Opening and closing fence, each exactly once -- a duplicated closing
    # fence is the failure mode this pins. Trailing whitespace is ignored
    # because html2text turns the ``<br>`` after the opening fence into
    # hard-break spaces.
    assert sum(1 for line in lines if line.rstrip() == "```") == 2
    # The blank line between the two code lines survives inside the block.
    idx_def = next(i for i, l in enumerate(lines) if "def foo():" in l)
    idx_ret = next(i for i, l in enumerate(lines) if "return 1" in l)
    assert idx_ret > idx_def + 1
    # Blank-line collapsing still applies everywhere (no 3+ newline runs).
    assert "\n\n\n" not in md


def test_deepseek_html_to_markdown_fences_docusaurus_code_block_verbatim():
    """A Docusaurus ``theme-code-block`` must come out as a fenced code
    block: the fence carries the language from the ``language-*`` class, the
    code text is verbatim -- MULTIPLE consecutive blank lines included --
    and the container's chrome (the "Copy" button) is gone.

    This is the core protection of the pre-extraction step: without it,
    html2text renders ``<pre>`` as an indented block, which the fenced-block
    scanner ``iter_code_block_spans`` (backtick/tilde fenced blocks) cannot
    recognize as code, so the blank-line collapsing pass would eat blank runs
    inside code samples. The double blank line below (a 3-newline run) is
    exactly what collapsing would destroy.

    The fixture reproduces the REAL markup the site serves: every code line
    is a ``<span class="token-line">`` followed by a ``<br>``, and the line
    content itself is split into per-token ``<span>`` elements. A fixture
    built from literal newlines inside ``<pre>`` would pass whether or not
    the extraction honours ``<br>``, because the raw text already carries the
    breaks -- which is precisely how a conversion that drops every newline
    went unnoticed. Blank lines are the empty ``token-line`` spans."""
    html = """
    <div class="theme-doc-markdown markdown">
      <h1>Your First API Call</h1>
      <div class="theme-code-block">
        <div class="language-python codeBlockContainer_abc theme-code-block">
          <div class="codeBlockContent_def">
            <pre class="prism-code language-python codeBlock_ghi"><code class="codeBlockLines_jkl"><span class="token-line"><span class="token keyword">from</span><span class="token plain"> openai </span><span class="token keyword">import</span><span class="token plain"> OpenAI</span><br></span><span class="token-line"><span class="token plain" style="display:inline-block"></span><br></span><span class="token-line"><span class="token plain">client </span><span class="token operator">=</span><span class="token plain"> OpenAI</span><span class="token punctuation">(</span><span class="token plain">base_url</span><span class="token operator">=</span><span class="token string">"https://api.deepseek.com"</span><span class="token punctuation">)</span><br></span><span class="token-line"><span class="token plain" style="display:inline-block"></span><br></span><span class="token-line"><span class="token plain" style="display:inline-block"></span><br></span><span class="token-line"><span class="token plain">response </span><span class="token operator">=</span><span class="token plain"> client.chat.completions.create</span><span class="token punctuation">(</span><span class="token plain">model</span><span class="token operator">=</span><span class="token string">"deepseek-chat"</span><span class="token punctuation">)</span><br></span></code></pre>
            <div class="buttonGroup_mno"><button type="button">Copy</button></div>
          </div>
        </div>
      </div>
      <p>Done.</p>
    </div>
    """
    md = deepseek._html_to_markdown(html)
    assert (
        "```python\n"
        "from openai import OpenAI\n"
        "\n"
        'client = OpenAI(base_url="https://api.deepseek.com")\n'
        "\n\n"  # two blank lines INSIDE the code survive the collapse pass
        'response = client.chat.completions.create(model="deepseek-chat")\n'
        "```"
    ) in md
    # The container chrome must not leak into the mirrored Markdown.
    assert "Copy" not in md
    assert "Done." in md  # prose after the block survives conversion


def test_deepseek_html_to_markdown_bare_pre_falls_back_to_code_class():
    """A bare ``<pre>`` (no ``theme-code-block`` container) must still be
    fenced, taking its language from the ``language-*`` class on the
    ``<code>`` element, and its single blank line must survive."""
    html = """
    <div class="theme-doc-markdown">
      <pre><code class="language-json">{"model": "deepseek-chat",

"stream": false}</code></pre>
    </div>
    """
    md = deepseek._html_to_markdown(html)
    assert '```json\n{"model": "deepseek-chat",\n\n"stream": false}\n```' in md


def test_deepseek_html_to_markdown_fence_outlives_inner_backticks():
    """A code block whose content contains a run of backticks (docs
    documenting Markdown) must get a fence one backtick longer than the
    longest inner run; otherwise the inner run would close the fence early
    and corrupt the mirrored Markdown."""
    html = """
    <div class="theme-doc-markdown">
      <pre><code>Use ``` for fences.</code></pre>
    </div>
    """
    md = deepseek._html_to_markdown(html)
    assert "````\nUse ``` for fences.\n````" in md


# --- DeepSeek page-shape normalisation ----------------------------------------


def test_deepseek_html_to_markdown_keeps_heading_text_in_the_heading():
    """The embedded API renderer wraps a heading's text in a paragraph
    (``<h3><p>Body</p></h3>``). Left alone, html2text emits the heading
    marker alone and the text as the paragraph beneath it, so the document
    outline loses the heading and the reader sees a stray ``###``."""
    html = (
        '<div class="theme-doc-markdown">'
        '<h3 class="openapi-markdown__details-summary-header-body"><p>Body</p></h3>'
        "<p>Prose after the heading.</p></div>"
    )
    md = deepseek._html_to_markdown(html)
    assert "### Body" in md
    assert "###\n" not in md


def test_deepseek_html_to_markdown_labels_tab_panels():
    """A Docusaurus tab strip is an HTML list, so converting it as-is turns
    the tab labels into a bullet list that names content further down the
    page with nothing connecting the two. Every panel is content (the mirror
    is a document, not an interactive page), so each keeps its label on a
    bold line directly above it and the strip itself is dropped."""
    html = (
        '<div class="theme-doc-markdown">'
        '<div class="tabs-container tabList_x"><ul role="tablist" class="tabs">'
        '<li role="tab" class="tabs__item tabs__item--active">curl</li>'
        '<li role="tab" class="tabs__item">python</li></ul>'
        '<div class="margin-top--md">'
        '<div role="tabpanel" class="tabItem_a"><pre><code class="language-bash">curl x</code></pre></div>'
        '<div role="tabpanel" class="tabItem_a" hidden=""><pre><code class="language-python">py x</code></pre></div>'
        "</div></div></div>"
    )
    md = deepseek._html_to_markdown(html)
    assert "**curl**\n\n```bash\ncurl x\n```" in md
    assert "**python**\n\n```python\npy x\n```" in md
    assert "* curl" not in md  # the strip is gone, not converted to a list


def test_deepseek_html_to_markdown_labels_nested_tab_groups():
    """Tab groups NEST on the embedded OpenAPI pages: a schema's groups render
    inside the request-body panel that holds them. A strip's panels are
    therefore only the ones up to the next panel boundary -- counting the
    nested groups' panels too would make the counts disagree, and every strip
    on the page would go unlabelled, taking its labels off the page with it.

    Both groups are paired here, the outer one included its nested panel, so
    no label is lost and no label is attached to the wrong sample."""
    html = (
        '<div class="theme-doc-markdown">'
        '<div class="tabs-container">'
        '<div class="tabs__container">'
        '<div class="openapi-tabs__mime-container">'
        '<ul role="tablist" class="tabs openapi-tabs__mime">'
        '<li role="tab" class="tabs__item tabs__item--active">application/json</li>'
        "</ul></div></div>"
        '<div class="margin-top--md">'
        '<div role="tabpanel" class="tabItem_a">'
        '<div class="openapi-tabs__schema-container">'
        '<div class="openapi-tabs__schema-tabs-container">'
        '<ul role="tablist" class="tabs openapi-tabs__schema">'
        '<li role="tab" class="tabs__item">System message</li>'
        '<li role="tab" class="tabs__item">User message</li>'
        "</ul></div>"
        '<div class="margin-top--md">'
        '<div role="tabpanel" class="tabItem_b">'
        '<pre><code class="language-json">{"role": "system"}</code></pre></div>'
        '<div role="tabpanel" class="tabItem_b" hidden="">'
        '<pre><code class="language-json">{"role": "user"}</code></pre></div>'
        "</div></div></div></div></div></div>"
    )
    md = deepseek._html_to_markdown(html)
    # Every label survived, each on the bold line above the panel it names.
    assert "**application/json**\n\n**System message**" in md
    assert '**System message**\n\n```json\n{"role": "system"}\n```' in md
    assert '**User message**\n\n```json\n{"role": "user"}\n```' in md
    # Both strips are gone, and no label was left behind as a bullet list.
    assert "* application/json" not in md
    assert "* System message" not in md


def test_deepseek_html_to_markdown_keeps_tab_labels_when_they_do_not_pair():
    """The label/panel pairing is positional, so it is only made when the two
    counts agree. A mismatch means the markup changed shape: nothing is
    labelled, because attaching a label to the wrong sample is worse than the
    bare list it replaced. The strip is KEPT in that case -- dropping it
    would delete the labels from the page entirely, and the panel they name
    would lose the only thing that says which sample it is."""
    html = (
        '<div class="theme-doc-markdown">'
        '<div class="tabs-container tabList_x"><ul role="tablist" class="tabs">'
        '<li role="tab" class="tabs__item">curl</li>'
        '<li role="tab" class="tabs__item">python</li></ul>'
        '<div class="margin-top--md">'
        '<div role="tabpanel" class="tabItem_a"><pre><code class="language-bash">curl x</code></pre></div>'
        "</div></div></div>"
    )
    md = deepseek._html_to_markdown(html)
    assert "**curl**" not in md
    assert "* curl" in md  # the labels survive as the list they were written as
    assert "* python" in md
    assert "```bash\ncurl x\n```" in md  # the panel content still survives


def test_deepseek_html_to_markdown_keeps_a_strip_whose_panels_are_missing():
    """A strip with no panels of its own has nothing to label, so it is left
    alone rather than removed: the labels are the only text it carries, and
    deleting them would lose them from the page."""
    html = (
        '<div class="theme-doc-markdown">'
        '<div class="tabs-container"><ul role="tablist" class="tabs">'
        '<li role="tab" class="tabs__item">curl</li></ul>'
        "</div>"
        "<p>Prose that follows the strip.</p></div>"
    )
    md = deepseek._html_to_markdown(html)
    assert "* curl" in md
    assert "Prose that follows the strip." in md


def test_deepseek_html_to_markdown_resolves_site_absolute_links():
    """A ``/guides/...`` href resolves on the upstream site only: in a local
    checkout a leading ``/`` means the filesystem root, so every such link is
    dead where the mirror is read. A mirrored route becomes a relative link
    to the page that holds it, an unmirrored one becomes its upstream URL,
    and the anchor survives both branches."""
    html = (
        '<div class="theme-doc-markdown">'
        '<p><a href="/guides/vision#limits">Vision</a> and '
        '<a href="/img/diagram.png">Diagram</a> and '
        '<a href="/">Home</a> and '
        '<a href="https://example.com/x">External</a>.</p></div>'
    )
    md = deepseek._html_to_markdown(
        html, "guides/tool_calls", {"index", "guides/vision", "guides/tool_calls"}
    )
    assert "[Vision](<./vision.md#limits>)" in md
    assert "[Diagram](<https://api-docs.deepseek.com/img/diagram.png>)" in md
    assert "[Home](<../index.md>)" in md
    assert "[External](<https://example.com/x>)" in md


def test_deepseek_html_to_markdown_leaves_links_alone_without_a_page_set():
    """An absent page set means "which pages this run mirrors is unknown", not
    "nothing is mirrored": resolving against an empty set would rewrite every
    internal link to its upstream URL, so the links are left exactly as
    upstream wrote them instead."""
    html = (
        '<div class="theme-doc-markdown">'
        '<p><a href="/guides/vision">Vision</a></p></div>'
    )
    md = deepseek._html_to_markdown(html)
    assert "[Vision](</guides/vision>)" in md


def test_deepseek_html_to_markdown_keeps_code_samples_out_of_the_link_pass():
    """The cross-link pass runs on the DOM after the ``<pre>`` blocks have
    been lifted out, so a snippet that shows a site path keeps showing
    exactly what it showed. Fenced code that reached the text-level passes
    would have to be shielded explicitly; here the ordering does it."""
    html = (
        '<div class="theme-doc-markdown">'
        '<p><a href="/guides/vision">Real link</a></p>'
        '<pre><code class="language-json">{"url": "/guides/vision"}</code></pre>'
        "</div>"
    )
    md = deepseek._html_to_markdown(html, "index", {"index", "guides/vision"})
    assert "[Real link](<./guides/vision.md>)" in md
    assert '{"url": "/guides/vision"}' in md


def test_deepseek_fetch_markdown_refuses_to_convert_without_discovered_slugs():
    """Converting with no discovered slug set would rewrite every internal
    link on the page to its upstream URL (see ``ensure_known_slugs``), so the
    hook must fail loudly instead -- and as a ``FetchError``, the one type the
    pipeline isolates per page. The refusal comes before the download, so a
    run that skipped discovery stops at the first page instead of fetching
    the whole source and then failing."""
    client = _FakeClient(
        [
            _Resp(
                200,
                '<div class="theme-doc-markdown"><h1>Quickstart</h1>'
                "<p>Enough prose to validate as Markdown.</p></div>",
            )
        ]
    )
    page = Page(
        slug="quickstart",
        source_url="https://api-docs.deepseek.com/quickstart",
        source_md_url="https://api-docs.deepseek.com/quickstart",
        source_id="quickstart",
        group="root",
    )
    deepseek._KNOWN_SLUGS.clear()
    with pytest.raises(fetch.FetchError, match="no discovered slugs"):
        deepseek.fetch_markdown(client, page)
    assert client.calls == 0


# --- discovery under HTTP fetch errors ----------------------------------------


def test_claude_code_discover_surfaces_fetch_error_on_404():
    """A 404 on the sitemap fetch must surface as a ``FetchError`` carrying
    the structured status code -- not as a confusing downstream crash (e.g. a
    parse error on an HTML error page, or the zero-page RuntimeError, which
    would misdiagnose a fetch failure as a locale restructure). 404 is
    non-transient, so exactly one request is made."""
    client = _FakeClient([_Resp(404)])
    with pytest.raises(fetch.FetchError) as exc_info:
        claude_code.discover(client)
    assert exc_info.value.status_code == 404
    assert client.calls == 1  # fail-fast: a 404 is never retried


def test_codex_discover_surfaces_fetch_error_on_404():
    """The git-tree based adapters must likewise propagate a fetch failure
    from the trees API as a ``FetchError`` with the status attached. A 404
    (renamed repo or branch) is NOT a rate limit, so it must come back
    without the GITHUB_TOKEN hint appended (see test_github.py for the hint
    mapping itself)."""
    client = _FakeClient([_Resp(404)])
    with pytest.raises(fetch.FetchError) as exc_info:
        codex_cli.discover(client)
    assert exc_info.value.status_code == 404
    assert "GITHUB_TOKEN" not in str(exc_info.value)


def test_deepseek_discover_surfaces_fetch_error_after_500_retries():
    """A persistent 500 on the sitemap is transient, so discovery must retry
    up to ``config.MAX_RETRIES`` and then surface a ``FetchError`` carrying
    the 500 status -- bounded retries, never an infinite loop and never a
    misleading zero-page RuntimeError. time.sleep is patched out so the
    exponential backoff does not slow the test run down."""
    client = _FakeClient([_Resp(500), _Resp(500), _Resp(500)])
    with pytest.raises(fetch.FetchError) as exc_info:
        deepseek.discover(client)
    assert exc_info.value.status_code == 500
    assert client.calls == 3  # config.MAX_RETRIES


# --- kimi_code: VitePress normalisation ---------------------------------------


def _kimi_page(slug: str = "customization/plugins") -> Page:
    """Build the ``Page`` a normalisation test needs, with realistic URLs."""
    return Page(
        slug=slug,
        source_url=kimi_code._source_url(slug),
        source_md_url=(
            f"https://raw.githubusercontent.com/MoonshotAI/kimi-code/main/"
            f"docs/en/{slug}.md"
        ),
        source_id=f"docs/en/{slug}.md",
        group=slug.split("/", 1)[0],
    )


def test_kimi_normalize_strips_frontmatter_and_keeps_the_body():
    """The YAML frontmatter block is build metadata, not page content: it must
    not reach the mirrored page. The body -- heading and prose -- must survive
    unchanged, and the page's manifest title must still come out of the
    normalized Markdown."""
    raw = (
        "---\n"
        "outline: 2\n"
        "---\n"
        "\n"
        "# Changelog\n"
        "\n"
        "This page documents the changes in each release.\n"
    )
    md = kimi_code._normalize_page(raw)
    assert md.startswith("# Changelog")
    assert "---" not in md
    assert "outline" not in md
    assert "This page documents the changes in each release." in md
    assert fetch.extract_title(md) == "Changelog"


def test_kimi_normalize_titles_a_page_that_has_no_heading_of_its_own():
    """A frontmatter ``title`` must become the page's heading when the body
    carries none, so the manifest title is the upstream title instead of the
    slug-derived fallback."""
    raw = "---\ntitle: Kimi Datasource\noutline: 2\n---\n\nMoved to the plugins page.\n"
    md = kimi_code._normalize_page(raw)
    assert md.startswith("# Kimi Datasource")
    assert "Moved to the plugins page." in md
    assert fetch.extract_title(md, fallback="datasource") == "Kimi Datasource"


def test_kimi_normalize_keeps_page_text_between_horizontal_rules():
    """A page whose first line is prose is never frontmatter, however many
    ``---`` rules follow. Reading the text between two rules as a metadata
    block deleted it from the mirrored page outright -- and the result still
    validated as Markdown, so nothing downstream reported the loss."""
    raw = "---\n\nSome prose here\n\n---\n\n# Heading\n\nMore prose\n"
    md = kimi_code._normalize_page(raw)
    assert "Some prose here" in md
    assert "More prose" in md
    assert fetch.validate_markdown(md)


def test_kimi_normalize_strips_a_bom_before_reading_the_frontmatter():
    """A BOM (U+FEFF) in front of the opening ``---`` is invisible but breaks
    the start-of-document anchor, because ``\\s`` does not match that
    character. Leaving it in place would keep the raw YAML in the mirrored
    page AND lose the frontmatter title, so the adapter strips it exactly like
    ``core.fetch`` does before its own frontmatter and heading patterns run.
    The normalized page is the same one either way, and carries no BOM."""
    without_bom = "---\ntitle: Kimi Notes\n---\n\nprose\n"
    md = kimi_code._normalize_page("\ufeff" + without_bom)
    assert md.startswith("# Kimi Notes")
    assert "\ufeff" not in md
    assert md == kimi_code._normalize_page(without_bom)


def test_kimi_normalize_reads_frontmatter_keys_in_any_case():
    """Frontmatter keys are matched case-insensitively: ``Title:`` is as valid
    as ``title:``, and the canonical title (or hero name) is what reaches the
    page heading. A case-sensitive lookup left a bodyless page with no title
    at all, so its manifest title fell back to the file name."""
    assert kimi_code._normalize_page("---\nTitle: Kimi Notes\n---\n") == (
        kimi_code._normalize_page("---\ntitle: Kimi Notes\n---\n")
    )
    md = kimi_code._normalize_page(
        "---\nLayout: home\nHero:\n  Name: Kimi Code CLI\n  Text: Tagline\n---\n"
    )
    assert md.startswith("# Kimi Code CLI")
    assert "Tagline" in md


def test_kimi_normalize_recognises_an_empty_frontmatter_block():
    """An empty ``---``/``---`` block is legal frontmatter carrying no fields.
    It is recognised (the two fence lines are build metadata, not page
    content), and the body that follows is kept untouched."""
    md = kimi_code._normalize_page("---\n---\n\n# Heading\n\nbody\n")
    assert md.startswith("# Heading")
    assert "body" in md
    assert "---" not in md


def test_kimi_normalize_skips_blank_and_comment_lines_in_frontmatter():
    """Blank lines and YAML comments inside the block are not fields and must
    not disturb the parse: the real keys around them are still read, and the
    comment never reaches the mirrored page."""
    md = kimi_code._normalize_page(
        "---\n# navigation section\ntitle: Kimi Notes\n\noutline: 2\n---\n"
    )
    assert md.startswith("# Kimi Notes")
    assert "outline" not in md
    assert "navigation section" not in md


def test_kimi_normalize_keeps_a_body_heading_over_the_frontmatter_title():
    """When the body has its own heading, that heading is the page title --
    re-emitting the frontmatter title on top of it would leave the page with
    two competing top-level headings."""
    raw = "---\ntitle: Frontmatter Title\n---\n\n# Real body heading\n\nprose\n"
    md = kimi_code._normalize_page(raw)
    assert md.startswith("# Real body heading")
    assert "Frontmatter Title" not in md


def test_kimi_normalize_renders_a_frontmatter_only_landing_page():
    """The landing page is pure VitePress frontmatter (a ``layout: home`` hero
    block with no body at all). It must come out as a readable page: the
    hero's product name as the heading and its tagline as the description, and
    nothing of the raw YAML. Without this the page mirrored as an empty file
    titled after its file name."""
    raw = (
        "---\n"
        "layout: home\n"
        "hero:\n"
        "  name: Kimi Code CLI\n"
        "  text: The Starting Point for Next-Gen Agents\n"
        "  actions:\n"
        "    - theme: brand\n"
        "      text: Get started\n"
        "      link: guides/getting-started\n"
        "    - theme: alt\n"
        "      text: GitHub\n"
        "      link: https://github.com/MoonshotAI/kimi-code\n"
        "---\n"
    )
    md = kimi_code._normalize_page(raw)
    assert md.startswith("# Kimi Code CLI")
    assert "The Starting Point for Next-Gen Agents" in md
    # Only the hero's name and tagline are rendered: the action links are
    # navigation for the Vue theme, not page content, so neither they nor the
    # raw frontmatter keys leak into the mirrored page.
    assert "layout" not in md and "hero" not in md and "theme: brand" not in md
    assert fetch.extract_title(md, fallback="index") == "Kimi Code CLI"


def test_kimi_normalize_reads_a_nested_map_that_opens_with_a_list():
    """The same landing page with its hero entries in the other order (the
    ``actions:`` list first, ``name:``/``text:`` after it) must normalize to
    the same page. Taking the direct-child indentation from the first indented
    line that carried a SCALAR made the level the list's own items sit at, so
    every real child was read as "deeper than a direct child" and dropped --
    leaving the landing page as an empty file."""
    raw = (
        "---\n"
        "layout: home\n"
        "hero:\n"
        "  actions:\n"
        "    - theme: brand\n"
        "      text: Get started\n"
        "      link: guides/getting-started\n"
        "  name: Kimi Code CLI\n"
        "  text: The Starting Point for Next-Gen Agents\n"
        "---\n"
    )
    md = kimi_code._normalize_page(raw)
    assert md.startswith("# Kimi Code CLI")
    assert "The Starting Point for Next-Gen Agents" in md
    assert md.strip()
    # The list's own keys are not hero fields: only the direct children are.
    assert "Get started" not in md and "theme: brand" not in md


def test_kimi_normalize_drops_head_meta_refresh_but_keeps_the_moved_notice():
    """A stub page whose frontmatter only carries a ``head:`` meta-refresh
    must lose the redirect plumbing and keep its visible body -- the notice
    that tells a reader where the page went."""
    raw = (
        "---\n"
        "head:\n"
        "  - - meta\n"
        "    - http-equiv: refresh\n"
        "      content: 0; url=./plugins.html#kimi-datasource\n"
        "---\n"
        "\n"
        "# Kimi Datasource\n"
        "\n"
        "This page has moved to [Plugins: Kimi Datasource](./plugins.md#kimi-datasource).\n"
    )
    md = kimi_code._normalize_page(raw)
    assert md.startswith("# Kimi Datasource")
    assert "http-equiv" not in md and "url=./plugins.html" not in md
    assert (
        "This page has moved to [Plugins: Kimi Datasource](./plugins.md#kimi-datasource)."
        in md
    )


def test_kimi_normalize_replaces_badge_component_with_its_text():
    """A ``<Badge />`` renders a version pill next to a heading; in Markdown
    its information is the ``text`` attribute, which must survive as plain
    text. The attribute value is matched through its own quote pair, so a
    value containing the other quote kind is not truncated."""
    raw = (
        '### Kimi WebBridge <Badge type="tip" text="v1.11.3" />\n'
        "\n"
        "### Kimi Notes <Badge text='the \"draft\" plugin' />\n"
        "\n"
        "Plugin docs.\n"
    )
    md = kimi_code._normalize_page(raw)
    assert "### Kimi WebBridge v1.11.3" in md
    assert '### Kimi Notes the "draft" plugin' in md
    assert "<Badge" not in md


def test_kimi_normalize_drops_a_textless_badge_without_a_dangling_space():
    """A badge with no ``text`` attribute shows nothing, so the tag (and the
    whitespace in front of it) must be removed -- leaving a trailing space
    after the heading it annotated would be a Markdown line-end artifact."""
    raw = '### Kimi WebBridge <Badge type="info" />\n\nPlugin docs.\n'
    md = kimi_code._normalize_page(raw)
    assert "### Kimi WebBridge\n" in md
    assert "<Badge" not in md


def test_kimi_normalize_replaces_a_paired_badge_by_its_inner_text():
    """The paired form wraps the text it displays between the tags, with no
    ``text`` attribute to read it from: ``<Badge>v9</Badge>`` must show ``v9``
    rather than being left in the page as raw markup. When a tag carries both,
    the attribute wins -- that is the value the component renders."""
    md = kimi_code._normalize_page('### Kimi WebBridge <Badge type="tip">v9</Badge>\n')
    assert "### Kimi WebBridge v9" in md
    assert "<Badge" not in md
    paired_and_empty = kimi_code._normalize_page('### X <Badge type="tip"></Badge>\n')
    assert paired_and_empty == "### X\n"
    assert kimi_code._normalize_page(
        '### X <Badge type="tip" text="v1">v9</Badge>\n'
    ) == ("### X v1\n")


def test_kimi_normalize_ignores_an_attribute_merely_named_like_text():
    """Only a ``text`` attribute of the badge itself is its display text. A
    word boundary alone also fires after a hyphen, which made
    ``data-text="wrong"`` print that value into the heading it annotated."""
    md = kimi_code._normalize_page('### X <Badge type="info" data-text="wrong" />\n')
    assert md == "### X\n"
    assert "wrong" not in md


def test_kimi_normalize_reads_attribute_values_containing_angle_brackets():
    """An attribute value is a quoted run, so a ``>`` inside it does not end
    the tag: the badge is still recognized and shows its full text instead of
    being left in the page as raw markup."""
    md = kimi_code._normalize_page('### X <Badge type="tip" text="a > b" />\n')
    assert md == "### X a > b\n"
    assert "<Badge" not in md


def test_kimi_component_patterns_cannot_cross_a_line_or_scan_unbounded():
    """Structural bounds of the two component patterns, asserted without any
    timing threshold.

    A match may not cross a line break: ``[^>]*`` used to let it do exactly
    that, so at every ``<Badge``/``<div`` the engine consumed to the next
    ``>`` or to end-of-file and then backtracked character by character --
    quadratic in the document length, and a single adversarial page could
    stall the mirror for minutes. The same bound is also what keeps a match
    from reaching into a fenced code block (a fence occupies whole lines).
    The attribute run is additionally capped, so an unterminated tag costs a
    constant per occurrence rather than a scan to the end of the line: the
    long-tag cases below must NOT match, while tags within the cap still do.
    """
    assert kimi_code._BADGE_RE.search('<Badge type="tip"\ntext="v1" />') is None
    assert kimi_code._LAYOUT_TAG_RE.search('<div class="step"\n>') is None

    within_cap = '### X <Badge type="tip" text="' + "v" * 40 + '" />\n'
    assert kimi_code._BADGE_RE.search(within_cap) is not None
    assert kimi_code._normalize_page(within_cap).startswith("### X v")

    long_run = "x" * (kimi_code._TAG_RUN_LIMIT * 4)
    assert kimi_code._BADGE_RE.search(f'### X <Badge text="{long_run}" />') is None
    assert kimi_code._LAYOUT_TAG_RE.search(f'<div class="{long_run}">') is None


def test_kimi_normalize_converts_typed_containers_to_github_alerts():
    """``::: tip``/``warning``/``info``/``danger`` containers become GitHub
    Alerts: the label line, the optional title in bold, and every body line
    prefixed as a blockquote line. ``code-group`` has no alert equivalent and
    is unwrapped, keeping its code samples verbatim. No ``:::`` marker may
    survive either conversion."""
    raw = (
        "# Guide\n"
        "\n"
        "::: warning Note\n"
        "Keep the token secret.\n"
        ":::\n"
        "\n"
        "::: code-group\n"
        "\n"
        "```sh\n"
        "curl example\n"
        "```\n"
        "\n"
        ":::\n"
    )
    md = kimi_code._normalize_page(raw)
    assert "> [!WARNING]\n> **Note**\n>\n> Keep the token secret." in md
    assert "```sh\ncurl example\n```" in md
    assert ":::" not in md
    # An empty container collapses to its label line: the separator that
    # normally introduces the body must not be left dangling behind it.
    assert kimi_code._normalize_page("::: tip\n:::\n") == "> [!TIP]\n"


def test_kimi_normalize_maps_info_and_danger_containers():
    """``info`` and ``danger`` have no GitHub Alert label of their own, so they
    map to the closest supported severity (NOTE and CAUTION). Losing that
    mapping would either drop the callout's severity or leave an unsupported
    label that renders as plain text."""
    assert kimi_code._normalize_page("::: info\nHeads up.\n:::\n") == (
        "> [!NOTE]\n> Heads up.\n"
    )
    assert kimi_code._normalize_page("::: danger\nDo not run this.\n:::\n") == (
        "> [!CAUTION]\n> Do not run this.\n"
    )


def test_kimi_normalize_unwraps_a_container_type_it_does_not_know():
    """A container type the adapter has no mapping for is uncertain structure:
    its markers are removed, but the title and the body stay in the page
    exactly as written, so the reader loses nothing to the conversion."""
    raw = "::: custom-block A Title\nBody text.\n:::\n"
    md = kimi_code._normalize_page(raw)
    assert "A Title" in md
    assert "Body text." in md
    assert ":::" not in md


def test_kimi_normalize_keeps_an_indented_container_inside_its_list_step():
    """A callout nested inside a numbered step must stay part of that step:
    its produced lines keep the container's indentation, and the body is
    dedented before the blockquote prefix is added, so a code sample inside
    the callout keeps its own structure."""
    raw = (
        "1. Do not use goals for broad topics.\n"
        "\n"
        "    ::: warning Counterexample\n"
        "    ```sh\n"
        "    /goal Greetings!\n"
        "    ```\n"
        "    :::\n"
        "\n"
        "    Agents mark the goal complete immediately.\n"
    )
    md = kimi_code._normalize_page(raw)
    assert (
        "    > [!WARNING]\n"
        "    > **Counterexample**\n"
        "    >\n"
        "    > ```sh\n"
        "    > /goal Greetings!\n"
        "    > ```" in md
    )
    assert "    Agents mark the goal complete immediately." in md
    assert ":::" not in md


def test_kimi_normalize_unwraps_details_container_as_plain_content():
    """``::: details`` is VitePress's collapsible block. It has no GitHub
    Alert equivalent, so it is unwrapped: the markers go, the optional title
    the opening marker carried survives as its own paragraph, and the body is
    kept."""
    raw = (
        "::: details **Standards lookup** — Need to check compliance?\n"
        "Look up national (GB) and industry standards by number.\n"
        ":::\n"
    )
    md = kimi_code._normalize_page(raw)
    assert md.startswith("**Standards lookup** — Need to check compliance?")
    assert "Look up national (GB) and industry standards by number." in md
    assert ":::" not in md


def test_kimi_normalize_leaves_an_unterminated_container_untouched():
    """An opening marker with no closing marker is uncertain structure. The
    page must keep the text exactly as upstream wrote it -- silently treating
    the rest of the document as container content would delete page structure
    that the adapter merely failed to recognize."""
    raw = "# Guide\n\n::: tip Never closed\n\ntrailing prose\n"
    md = kimi_code._normalize_page(raw)
    assert "::: tip Never closed" in md
    assert "trailing prose" in md


def test_kimi_normalize_unwraps_presentation_only_layout_wrappers():
    """Class/style-only ``<div>``/``<span>`` wrappers position content for the
    Vue theme and carry no Markdown meaning: the tags go, the inner content
    (including the inline HTML the page uses for emphasis) stays."""
    raw = (
        "## Getting started\n"
        "\n"
        '<div class="step">\n'
        '<span class="step-num">1</span> <strong>Install the CLI</strong>\n'
        "\n"
        "Run the install script.\n"
        "</div>\n"
        "\n"
        '<div style="max-width: 380px; margin: 0 auto;">\n'
        "\n"
        "![Authorization window](../../media/auth.jpeg)\n"
        "\n"
        "</div>\n"
    )
    md = kimi_code._normalize_page(raw)
    assert "<div" not in md and "</div>" not in md
    assert "<span" not in md and "</span>" not in md
    assert "1 <strong>Install the CLI</strong>" in md
    assert "Run the install script." in md
    assert "![Authorization window](../../media/auth.jpeg)" in md


def test_kimi_normalize_keeps_semantic_markup_and_fenced_code_intact():
    """Two things must survive the conversions: a wrapper WITHOUT a class or
    style attribute is semantic markup (an anchor target, a container), so
    both of its tags stay and the page is never left unbalanced; and anything
    written inside a fenced code block is a code sample, so component tags and
    container markers there come out byte-for-byte."""
    raw = (
        "# Guide\n"
        "\n"
        "<div>\n"
        "\n"
        "kept content\n"
        "\n"
        "</div>\n"
        "\n"
        "```html\n"
        '<div class="step">\n'
        "::: tip sample\n"
        '<Badge type="tip" text="v1" />\n'
        "```\n"
    )
    md = kimi_code._normalize_page(raw)
    assert "<div>\n\nkept content\n\n</div>" in md
    assert '<div class="step">\n::: tip sample\n<Badge type="tip" text="v1" />' in md
    assert "[!TIP]" not in md


def test_kimi_normalize_protects_a_fence_indented_inside_a_list_item():
    """Upstream nests code samples inside list steps, which indents the whole
    fence. The conversions match their constructs anywhere on a line -- a
    ``<div class="step">`` needs no anchor, a ``:::`` marker accepts any
    indentation -- so an indented sample quoting one would be rewritten as
    page structure unless its fence counts as a fence."""
    raw = (
        "# Guide\n"
        "\n"
        "1. Apply the patch:\n"
        "\n"
        "   ```html\n"
        '   <div class="step">\n'
        "   ::: tip sample\n"
        '   <Badge type="tip" text="v1" />\n'
        "   ```\n"
    )
    md = kimi_code._normalize_page(raw)
    assert "[!TIP]" not in md
    assert '<div class="step">' in md
    assert '<Badge type="tip" text="v1" />' in md


def test_kimi_normalize_still_converts_a_fence_indented_too_far_to_be_one():
    """Four columns is an indented code block, not a fence, so the content
    there is ordinary page text to the conversions -- the guard widens the
    fence rule the way CommonMark does and no further."""
    raw = "# Guide\n\n    ::: tip sample\n    body\n    :::\n"
    md = kimi_code._normalize_page(raw)
    assert "[!TIP]" in md


def test_kimi_fetch_markdown_returns_normalized_markdown_and_hash():
    """The SUCCESS path of ``kimi_code.fetch_markdown``: the raw VitePress
    file must come back as a ``(markdown, sha256_hash)`` tuple, with the
    normalization applied and the hash matching ``fetch.content_hash`` of the
    returned text -- that pairing is what the pipeline stores in the manifest
    and what ``core.diff`` compares across runs."""
    raw = (
        "---\n"
        "title: Kimi WebBridge\n"
        "---\n"
        "\n"
        "::: tip Note\n"
        "Install the browser extension first.\n"
        ":::\n"
    )
    page = _kimi_page()
    md, digest = kimi_code.fetch_markdown(_FakeClient([_Resp(200, raw)]), page)
    assert md.startswith("# Kimi WebBridge")
    assert "> [!TIP]" in md
    assert "---" not in md
    assert digest == fetch.content_hash(md)


def test_kimi_fetch_markdown_rejects_non_markdown():
    """A response that normalises to something with no Markdown structure (an
    HTML error page, a truncated body) must raise ``FetchError`` rather than
    being written to the mirror: the pipeline isolates failures per page for
    that exception type only, so this is also what keeps one bad response from
    aborting the whole source."""
    page = _kimi_page("guides/getting-started")
    client = _FakeClient([_Resp(200, "<html><body><p>404 Not Found</p></body></html>")])
    with pytest.raises(fetch.FetchError):
        kimi_code.fetch_markdown(client, page)


def test_kimi_fetch_markdown_wraps_a_normalisation_failure(monkeypatch):
    """An exception out of the normalisation passes is re-raised as
    ``FetchError``, naming the page and keeping the original exception on
    ``__cause__``. The pipeline isolates failures per page for that exception
    type only, so an unforeseen markup shape (or a bug in a pass) must fail
    just this page instead of aborting the whole source's run."""
    page = _kimi_page("guides/getting-started")

    def _explode(text: str) -> str:
        raise ValueError("unforeseen markup shape")

    monkeypatch.setattr(kimi_code, "_normalize_page", _explode)
    client = _FakeClient([_Resp(200, "# Guide\n\nSome prose.\n")])
    with pytest.raises(fetch.FetchError) as exc_info:
        kimi_code.fetch_markdown(client, page)
    assert page.slug in str(exc_info.value)
    assert isinstance(exc_info.value.__cause__, ValueError)


# --- get_version unit tests --------------------------------------------------


def test_claude_code_get_version_parses_npm_registry():
    """claude_code.get_version queries the npm registry endpoint and extracts version."""
    client = _FakeClient(
        [_Resp(200, '{"name": "@anthropic-ai/claude-code", "version": "2.1.223"}')]
    )
    assert claude_code.get_version(client) == "2.1.223"


def test_claude_code_get_version_error_handling():
    """claude_code.get_version surfaces FetchError on 404/500 and handles non-dict."""
    client_404 = _FakeClient([_Resp(404)])
    with pytest.raises(fetch.FetchError):
        claude_code.get_version(client_404)

    client_empty = _FakeClient([_Resp(200, "{}")])
    assert claude_code.get_version(client_empty) is None


def test_github_adapters_get_version_parse_tags():
    """opencode, kimi_code, and codex_cli parse tag_name stripping leading 'v'."""
    client_opencode = _FakeClient([_Resp(200, '{"tag_name": "v1.18.18"}')])
    assert opencode.get_version(client_opencode) == "1.18.18"

    client_kimi = _FakeClient([_Resp(200, '{"tag_name": "v0.1.0"}')])
    assert kimi_code.get_version(client_kimi) == "0.1.0"

    client_codex = _FakeClient([_Resp(200, '{"tag_name": "v0.1.0"}')])
    assert codex_cli.get_version(client_codex) == "0.1.0"


def test_github_adapters_get_version_rate_limit():
    """GitHub releases endpoint 403 wraps into descriptive rate limit error."""
    client = _FakeClient([_Resp(403)])
    with pytest.raises(fetch.FetchError) as exc_info:
        opencode.get_version(client)
    assert "GITHUB_TOKEN" in str(exc_info.value)


def test_antigravity_get_version(monkeypatch):
    """antigravity.get_version queries agy --version or falls back to CONFIG.version."""
    client = _FakeClient([])
    # Fallback when binary not present
    monkeypatch.setattr("shutil.which", lambda _: None)
    assert antigravity.get_version(client) == antigravity.CONFIG.version

    # Mocked binary
    monkeypatch.setattr("shutil.which", lambda _: "/usr/local/bin/agy")
    monkeypatch.setattr(
        "subprocess.run",
        lambda *args, **kwargs: type(
            "Proc", (), {"returncode": 0, "stdout": "agy version 1.2.3\n"}
        )(),
    )
    assert antigravity.get_version(client) == "1.2.3"


def test_deepseek_get_version():
    """deepseek.get_version returns CONFIG.version ('—')."""
    client = _FakeClient([])
    assert deepseek.get_version(client) == "—"


def test_clean_url():
    """clean_url strips whitespace, query string, fragment, and trailing slashes."""
    assert (
        clean_url("https://example.com/docs/page?query=1#frag")
        == "https://example.com/docs/page"
    )
    assert (
        clean_url("  https://example.com/docs/page/  ")
        == "https://example.com/docs/page"
    )
    assert (
        clean_url("https://example.com/index.html?v=2")
        == "https://example.com/index.html"
    )
    assert clean_url("https://example.com/") == "https://example.com"


def test_ensure_discovered_pages():
    """ensure_discovered_pages returns non-empty list or raises RuntimeError."""
    sample_page = Page(
        slug="index",
        source_url="https://example.com",
        source_md_url="https://example.com/index.md",
        source_id="index",
        group="root",
    )
    pages = [sample_page]
    assert ensure_discovered_pages(pages, "test-source") is pages

    with pytest.raises(RuntimeError, match="test-source: discovery returned 0 pages"):
        ensure_discovered_pages([], "test-source")

    with pytest.raises(RuntimeError, match=r"prefix '/docs/'"):
        ensure_discovered_pages([], "test-source", "prefix '/docs/'")


def test_mirror_sources_package_exports():
    """mirror.sources.__all__ exports Source, SourceConfig, and all 6 adapters."""
    expected = {
        "Source",
        "SourceConfig",
        "antigravity",
        "claude_code",
        "codex_cli",
        "deepseek",
        "kimi_code",
        "opencode",
    }
    assert set(mirror.sources.__all__) == expected
    for name in mirror.sources.__all__:
        assert hasattr(mirror.sources, name)
        assert getattr(mirror.sources, name) is not None
