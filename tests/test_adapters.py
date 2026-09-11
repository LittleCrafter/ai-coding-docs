"""Offline tests for the source adapters' discovery and conversion logic.

Every test uses a scripted fake HTTP client (the same pattern as
``tests/test_fetch.py``): no real network access, each ``get`` pops the next
scripted response. What is pinned down here is the *filtering and safety*
behavior of the adapters -- the parts where a bug silently drops pages or
deletes mirrored files.
"""

from __future__ import annotations


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
    md, digest = deepseek.fetch_markdown(client, page)
    assert "# Quickstart" in md  # converted ATX heading present
    assert "create your first chat completion" in md  # prose converted
    assert "site header" not in md and "site footer" not in md  # chrome gone
    assert digest == fetch.content_hash(md)


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
    md, digest = codex_cli.fetch_markdown(client, page)
    assert "https://github.com/openai/codex/blob/main/SECURITY.md" in md
    assert "https://github.com/openai/codex/blob/main/SECURITY.md#policy" in md
    assert "https://github.com/openai/codex/blob/main/LICENSE" in md
    assert "(./local.md)" in md
    assert digest == fetch.content_hash(md)


def test_codex_how_mirrored_metadata():
    """Verify CONFIG.how_mirrored reflects the expanded discovery approach."""
    assert (
        codex_cli.CONFIG.how_mirrored
        == "scraping (GitHub tree + developers.openai.com/codex/llms.txt)"
    )


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
    codex_cli._KNOWN_SLUGS.clear()
    codex_cli._KNOWN_SLUGS.update(
        {"extend/record-and-replay", "agent-configuration/subagents"}
    )
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
    exactly what collapsing would destroy."""
    html = """
    <div class="theme-doc-markdown markdown">
      <h1>Your First API Call</h1>
      <div class="theme-code-block">
        <div class="language-python codeBlockContainer_abc theme-code-block">
          <div class="codeBlockContent_def">
            <pre class="prism-code language-python codeBlock_ghi"><code class="codeBlockLines_jkl">from openai import OpenAI

client = OpenAI(base_url="https://api.deepseek.com")


response = client.chat.completions.create(model="deepseek-chat")</code></pre>
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
