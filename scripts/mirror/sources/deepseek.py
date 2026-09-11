"""Source: DeepSeek API.

The docs at https://api-docs.deepseek.com are a Docusaurus site. Unlike the
Markdown-native sources, it serves only rendered HTML (no ``.md`` twins, no
``llms.txt``, no public source repo), so it converts HTML to Markdown
and defines the optional ``fetch_markdown(client, page)`` hook. The pipeline
picks that hook up via ``getattr`` and calls it instead of downloading
``page.source_md_url`` (see ``sources/base.py`` for the hook contract). Note
that ``source_md_url`` here points at the HTML page itself; the hook ignores
it and re-fetches ``source_url``.

Discovery comes from the sitemap (real XML at ``/sitemap.xml``). What that
sitemap registers is English pages only, so every URL under the site root
becomes a page -- the site does serve a full Simplified-Chinese tree under
``/zh-cn/``, but the sitemap does not list it, which is why no locale filter
is needed here.

Conversion strategy (see ``_html_to_markdown``): Docusaurus renders the doc
body inside ``<div class="theme-doc-markdown">``, so we isolate that node
(with the ``div.PromptLibrary`` container of the bespoke prompt-library
landing page, ``<article>``, and then the whole document as fallbacks),
strip leftover chrome (nav/footer/aside plus breadcrumbs and pagination),
and run html2text over what remains. ``<pre>`` code blocks are lifted out
*before* conversion and spliced back in afterwards as fenced code blocks,
so they keep their language tag and their exact text (line breaks and blank
lines included) instead of being mangled into html2text's indented-block
rendering. Three constructs that survive the chrome removal but render wrong
under html2text are normalised on the tree first: a paragraph nested inside a
heading, a tab strip that would become a bullet list naming content further
down the page, and a site-absolute cross-link that only resolves on the
upstream site.

The core conversion pipeline -- html2text configuration, the code-block
extraction skeleton (grouping ``<pre>`` elements by replacement target,
reading each block's text with its markup line breaks intact, and swapping in
placeholder tokens), code-block post-processing (blank-line collapse,
invisible-character stripping, fence-length adaptation), and the
fetch/convert/validate/hash body of the ``fetch_markdown`` hook -- is
provided via ``core.html_markdown``. This adapter keeps only the
DeepSeek/Docusaurus-specific parts: the content-container selection
(``div.theme-doc-markdown``), the Docusaurus-specific chrome removal
(breadcrumbs, pagination), the page-shape normalisation described above, and
the code-block language detection (from ``language-*`` CSS classes on the
``<pre>``, its ``<code>`` child, and the ``theme-code-block`` container). No
whats-new for this source.

Fragility notes -- what breaks when the upstream site changes:

* If the sitemap moves or empties, discovery raises (zero-page guard)
  instead of silently mirroring nothing.
* If a Docusaurus upgrade renames ``theme-doc-markdown``, the fallback
  chain still finds content but may include navigation chrome.
* If the ``PromptLibrary`` class of the bespoke landing page is renamed,
  that page drops to the ``<article>``/full-body fallbacks and warns.
* If the code-block markup stops carrying a ``language-*`` class (the
  stable, non-CSS-module class Docusaurus puts on the code container and
  the ``<pre>``), fences survive but lose their info string -- degraded,
  never corrupt.
"""

from __future__ import annotations

import posixpath
import sys
from typing import TYPE_CHECKING

import bs4

from ..core import fetch
from ..core.html_markdown import (
    collapse_blank_lines,
    extract_code_blocks,
    fetch_markdown_converted,
    make_converter,
    splice_code_blocks,
    strip_invisible_characters,
)
from ..core.page import Page
from ..core.sitemap import extract_locs
from .base import (
    SourceConfig,
    clean_url,
    ensure_discovered_pages,
    ensure_known_slugs,
    same_origin,
    try_make_page,
)

if TYPE_CHECKING:
    # Annotation-only import: ``from __future__ import annotations`` keeps the
    # ``httpx.Client`` annotations from being evaluated at runtime (the test
    # doubles duck-type the client interface, so httpx is never touched at
    # runtime in this module).
    import httpx

# The base URL of the DeepSeek API documentation site. This is used both as
# the site-root boundary for sitemap filtering (only URLs under this prefix
# are included in discovery) and as the home URL registered in SourceConfig.
# It is also the prefix the page-to-page cross-links are written with, and
# therefore the base of the upstream URL an unmirrored target is rewritten to.
# If the upstream site moves to a new domain, updating this single constant
# is sufficient -- SITEMAP_URL and all boundary checks derive from it.
SITE_URL = "https://api-docs.deepseek.com"
# The sitemap URL is derived from the site URL by appending ``/sitemap.xml``.
# This follows the standard sitemaps.org convention that sitemaps live at the
# site root; a custom path would require an override here. If the upstream
# site moves its sitemap to a non-standard URL, only this line needs changing.
SITEMAP_URL = f"{SITE_URL}/sitemap.xml"

CONFIG = SourceConfig(
    name="deepseek-api",
    title="DeepSeek API",
    home_url=SITE_URL,
    # ``generate_whats_new`` is set to ``False`` as a deliberate per-source
    # choice: DeepSeek opts out of whats-new generation. The whats-new
    # machinery itself is structural and source-agnostic -- the pipeline
    # diffs each cycle's discovered manifest against the previous one
    # (pages added/removed/renamed/modified) and appends a dated entry;
    # it does not parse any upstream changelog or release-notes page.
    # Antigravity is currently the only source that opts in.
    generate_whats_new=False,
    version="—",
    origin="api-docs.deepseek.com",
    how_mirrored="scraping (HTML → Markdown via `html2text`)",
)


def get_version(client: httpx.Client) -> str | None:
    """Return the version string for DeepSeek API documentation (not versioned)."""
    return CONFIG.version


def discover(client: httpx.Client) -> list[Page]:
    """Discover all DeepSeek API docs pages from the sitemap.

    Every ``<loc>`` under the site root becomes a page; the slug is the URL
    path (the homepage gets the synthetic slug ``"index"`` because an empty
    slug is rejected by ``Page.__post_init__``), and the index group is the
    slug's first path segment or ``"root"`` for pages directly at the site
    root. Because pages are HTML, ``source_md_url`` is set to the page URL
    itself as a placeholder -- the ``fetch_markdown`` hook below performs the
    actual fetch-and-convert.

    **Why there is no locale/section filter.** The site serves two
    documentation trees -- English under the site root and Simplified Chinese
    under ``/zh-cn/`` -- but its sitemap registers the English pages only, so
    discovery never sees a Chinese URL and no other content (blog, marketing)
    is mixed into the listing either. The site-root boundary below is
    therefore sufficient: every ``<loc>`` it keeps is part of the English API
    docs. The margin is upstream's sitemap, not the site layout -- if
    ``/zh-cn/`` URLs ever appear in the sitemap, they would pass the boundary
    check and be mirrored under ``zh-cn/...`` slugs, so a locale exclusion
    would have to be added here at that point.

    **Query/fragment stripping.** Sitemap entries can carry query strings
    (``?utm_source=newsletter``) or fragments (``#section``). These are
    stripped before deriving the slug, so:

    * ``/quickstart?utm=...`` -> slug ``"quickstart"`` -- the ``?`` is
      removed rather than leaking into the slug and being rejected;
    * Two entries differing only in their query string (``/quickstart`` and
      ``/quickstart?v=2``) deduplicate to a single page.

    **Per-entry error isolation.** A sitemap entry whose PATH itself
    contains characters outside the slug alphabet ``Page`` enforces (spaces,
    unicode, parentheses, ...) cannot be fixed by query/fragment cleaning.
    Such an entry is SKIPPED with a stderr warning naming the URL, while
    the remaining entries are still discovered -- one irreducibly-bad entry
    must not abort discovery for the whole source. The zero-page guard below
    remains the loud backstop for the case where EVERY entry ends up skipped.

    Raises ``RuntimeError`` in two zero-page scenarios, both of which would
    otherwise make the pipeline delete every mirrored file:

    * The sitemap itself contains zero ``<loc>`` entries (empty, moved, or
      replaced by an error page upstream);
    * The sitemap has entries but none survived the site-root filter (an
      upstream domain move).

    Each case carries its own message so the operator can tell them apart --
    a loud error, never silent data loss.
    """
    # Fetch the sitemap XML document via HTTP with automatic retry logic.
    # ``get_with_retry`` applies exponential backoff on transient errors
    # (HTTP 429 Too Many Requests, 503 Service Unavailable, connection
    # timeouts) so that a brief upstream glitch does not abort discovery.
    # If the sitemap is unreachable after exhausting all retries, the
    # function raises ``FetchError``, which the pipeline treats as a
    # failure for this source's discovery phase -- pages carry over from
    # the previous cycle rather than being deleted.
    xml = fetch.get_with_retry(client, SITEMAP_URL)
    # Parse the fetched XML document and extract every ``<loc>`` element's
    # text content -- these are the absolute URLs of all pages the upstream
    # site has registered in its sitemap. ``extract_locs`` handles the
    # standard ``http://www.sitemaps.org/schemas/sitemap/0.9`` namespace
    # transparently so the caller does not need to deal with XML namespaces
    # or element-tree traversal.
    locs = extract_locs(xml)
    # Guard against an empty (or unparseable) sitemap up front: with no
    # <loc> entries at all, something is wrong upstream (the sitemap moved,
    # was emptied, or got replaced by an HTML error page), and continuing
    # would discover zero pages. This is distinct from the zero-page guard
    # at the END of this function, which fires when the sitemap HAS entries
    # but none survived the site-root filter -- separating the two cases
    # gives the operator an accurate diagnosis (empty sitemap vs. domain
    # move) instead of the same generic "matched nothing" message for both.
    # Mirrors the equivalent guard in antigravity.discover so the two
    # HTML-to-Markdown adapters surface the same set of diagnostic signals.
    if not locs:
        raise RuntimeError(
            f"Sitemap {SITEMAP_URL} contained no <loc> entries. "
            "A zero-page discovery would delete all mirrored files. "
            "If the upstream sitemap moved, update SITEMAP_URL in this "
            "source module."
        )
    pages: list[Page] = []
    # Deduplication set: track every slug already processed so that two
    # sitemap entries collapsing to the same slug after query/fragment
    # stripping (e.g. ``/quickstart?utm=1`` and ``/quickstart``) are not
    # processed twice. The dedupe operates on the FINAL slug (derived after
    # query/fragment removal), not on the raw URL, because the slug is what
    # the pipeline uses as the page's identity throughout its lifecycle
    # (manifest keys, file paths, change detection). Two entries mapping to
    # the same slug would cause duplicate ``Page`` objects in the manifest,
    # which the pipeline would detect as a conflict and raise an error.
    seen: set[str] = set()
    for url in locs:
        # Strip any query string or fragment BEFORE the boundary check and
        # slug derivation. Cleaning first canonicalizes every entry:
        #
        #   * A sitemap entry like
        #     ``https://api-docs.deepseek.com/quickstart?utm_source=newsletter``
        #     or one carrying a ``#section`` fragment would otherwise leak
        #     "?"/"#" characters into the slug -- and ``Page.__post_init__``
        #     rejects slugs containing those characters.
        #   * The boundary check and the dedupe below operate on canonical
        #     URLs: two entries differing only in their query string collapse
        #     to a single page instead of being processed twice.
        #
        # Cleaning alone cannot rescue every odd entry, though: a URL whose
        # PATH itself contains characters outside the slug alphabet ``Page``
        # enforces (a space, parentheses, unicode, ...) still fails
        # validation. That case is handled by the per-entry guard around the
        # ``Page(...)`` construction below, and the zero-page guard at the
        # end of this function remains the loud backstop if every entry ends
        # up skipped.
        clean = clean_url(url)
        # Boundary check: ``clean`` must belong to the DeepSeek origin --
        # see ``same_origin`` in ``core/utils.py`` for the full rationale
        # (why a bare ``startswith`` would match a different domain whose
        # hostname shares the prefix, e.g.
        # "https://api-docs.deepseek.com.evil.com/..."). Query strings and
        # fragments need no boundary of their own: they were stripped just
        # above, so ``clean`` contains neither.
        if not same_origin(clean, SITE_URL):
            continue
        path = clean[len(SITE_URL) :].lstrip("/")
        slug = path or "index"  # homepage -> "index" (empty slug rejected by Page)
        if slug in seen:
            continue
        seen.add(slug)
        group = slug.split("/", 1)[0] if "/" in slug else "root"
        # `clean` is guaranteed non-empty here: the origin boundary check
        # above already requires it to equal SITE_URL or begin with
        # SITE_URL + "/" (both non-empty), so no `or SITE_URL` fallback is
        # needed -- the homepage case is the bare SITE_URL itself, which
        # passes through unchanged.
        # Per-entry guard: even after cleaning, a path can contain characters
        # outside the slug alphabet (a space, parentheses, unicode, ...),
        # which ``Page.__post_init__`` rejects with a ValueError. Without this
        # guard, ONE such sitemap entry would crash discovery for the entire
        # DeepSeek source. ``try_make_page`` (see ``sources/base.py``) owns
        # the guard/warning: the URL is named in a stderr warning and
        # discovery continues with the remaining entries.
        page = try_make_page(
            url,
            slug=slug,
            source_url=clean,
            source_md_url=clean,  # HTML URL; fetch_markdown handles conversion
            source_id=slug,
            group=group,
        )
        if page is not None:
            pages.append(page)
    pages.sort(key=lambda p: p.slug)
    # Publish the slugs of this run for the cross-link pass in the conversion
    # hook: it can only point a reference at a mirrored page if it knows which
    # pages this run actually mirrors. Replacing the set wholesale (rather
    # than adding to it) keeps a run's view exact even when a page disappeared
    # upstream, so a reference to it falls back to its upstream URL instead of
    # a relative link to a file that no longer exists.
    _KNOWN_SLUGS.clear()
    _KNOWN_SLUGS.update(page.slug for page in pages)
    return ensure_discovered_pages(pages, "deepseek-api", f"site root {SITE_URL!r}")


def _resolve_site_href(href: str, current_slug: str, known_slugs: set[str]) -> str:
    """Resolve one site-absolute destination to something the mirror can serve.

    *href* is an ``<a href>`` value that starts at the site root
    (``/guides/vision#limits``). A documentation route this run mirrors
    becomes a relative ``.md`` link to the page that holds it; a route it does
    not mirror -- an asset the mirror does not download, a page that has
    disappeared upstream -- becomes its upstream URL, the only destination
    that still resolves.

    The anchor is preserved on both branches: a fragment is resolved by the
    reader's browser against whichever document the link lands on, so it keeps
    working whether that document is a mirrored file or the upstream page. A
    query string is kept on the upstream branch and dropped on the mirrored
    one, because a mirrored file is a static document with nothing to
    parameterise.

    The site root itself resolves to the mirrored landing page (slug
    ``"index"``, the slug discovery gives the homepage), so the navigation
    links every page carries keep pointing at a file in the mirror.
    """
    path, _, anchor = href.partition("#")
    suffix = f"#{anchor}" if anchor else ""
    path, _, query = path.partition("?")

    slug = path.strip("/")
    if slug:
        upstream = f"{SITE_URL}{path}"
    else:
        slug = "index"
        upstream = f"{SITE_URL}/"

    if slug not in known_slugs:
        return f"{upstream}{query}{suffix}"

    # ``current_slug`` is the on-disk path of the page being rewritten, so the
    # relative path is derived the same way whatever depth the page sits at.
    current_dir = posixpath.dirname(current_slug) or "."
    relative = posixpath.relpath(f"{slug}.md", current_dir)
    if not relative.startswith((".", "/")):
        relative = f"./{relative}"
    return f"{relative}{suffix}"


def _rewrite_content_hrefs(
    content: bs4.Tag | bs4.BeautifulSoup,
    current_slug: str,
    known_slugs: set[str],
) -> None:
    """Repoint every site-absolute link under *content* at a live destination.

    The pages cross-reference each other with site-absolute paths
    (``<a href="/guides/vision">``), which only resolve while the reader is on
    the upstream site: in a local checkout a leading ``/`` means the
    filesystem root, so every one of those links is dead exactly where this
    mirror is read. Each is routed through :func:`_resolve_site_href`.

    Only ``<a href>`` values that start at the site root are touched. An
    external URL, a mail address, an intra-page ``#anchor``, and an already
    relative path are copied through unchanged, so this pass can never break a
    link that already worked. It is idempotent too: its output holds relative
    paths and absolute ``https://`` URLs, and neither starts with a single
    ``/``.

    The pass runs on the DOM rather than on the converted Markdown, which is
    what keeps code samples out of it: the ``<pre>`` blocks have already been
    lifted out of the tree by the time this runs, so a snippet that shows a
    site path keeps showing exactly what it showed without any fence-shielding
    step of its own.
    """
    for anchor in content.find_all("a", href=True):
        href = anchor["href"]
        # ``href=True`` selects anchors that have the attribute, but bs4 types
        # an attribute value as possibly multi-valued; a link destination is a
        # single string, so anything else is not a destination to rewrite.
        if not isinstance(href, str):
            continue
        if not href.startswith("/") or href.startswith("//"):
            continue
        anchor["href"] = _resolve_site_href(href, current_slug, known_slugs)


def _unwrap_heading_paragraphs(content: bs4.Tag | bs4.BeautifulSoup) -> None:
    """Lift paragraphs out of headings so each heading keeps its own text.

    The embedded OpenAPI renderer wraps a heading's text in a paragraph:
    ``<h3><p>Body</p></h3>``. html2text treats the nested block as its own
    block, emits the heading marker alone and the text as the paragraph under
    it, and the document outline loses a heading -- readers see a stray
    ``###`` line followed by an unrelated paragraph. Unwrapping the paragraph
    before conversion puts the text back where the heading expects it.

    Only ``<p>`` children are touched. A heading that carries inline markup
    (a ``<code>``, a link) keeps it: unwrapping swaps the paragraph element
    for its children, it does not flatten them.
    """
    for heading in content.find_all(["h1", "h2", "h3", "h4", "h5", "h6"]):
        for paragraph in heading.find_all("p"):
            paragraph.unwrap()


def _holds_tab_panels(node: bs4.Tag) -> bool:
    """Report whether *node* is a tab panel itself or carries one below it."""
    return node.get("role") == "tabpanel" or node.select('[role="tabpanel"]') != []


def _own_tab_panels(panels: list[bs4.Tag], group: bs4.Tag) -> list[bs4.Tag]:
    """Filter *panels* down to the ones that belong to the group *group*.

    A tab group may render INSIDE one of another group's panels -- an OpenAPI
    page nests a schema's groups inside the request-body panel that holds
    them -- so a search over a group's subtree finds the inner groups' panels
    too. A panel belongs to the OUTERMOST panel-bearing element it sits in:
    one that has another panel between itself and *group* is the inner
    group's, and pairing it with the outer strip's labels would attach a
    label to a sample it does not name.
    """
    own: list[bs4.Tag] = []
    for panel in panels:
        for ancestor in panel.parents:
            if ancestor is group:
                own.append(panel)
                break
            if isinstance(ancestor, bs4.Tag) and ancestor.get("role") == "tabpanel":
                break
    return own


def _tab_panels_for(strip: bs4.Tag) -> list[bs4.Tag]:
    """Return the panels one tab strip controls, in document order.

    A tab group is a container holding the strip and its panels side by side,
    each behind a wrapper of its own (``div.openapi-tabs__mime-container`` for
    the strip, ``div.margin-top--md`` for the panels, in the markup this
    adapter converts). The group is therefore found by walking OUTWARDS from
    the strip and taking the first sibling subtree that holds panels: that is
    the strip's own group, because a strip's panels always sit nearer to it
    than another group's do.

    Scoping the search this way is what keeps the pairing correct on a page
    that nests tab groups: searching the whole ``tabs-container`` subtree, as
    this pass used to, counts the nested groups' panels as well, so the counts
    never agree and every strip on such a page goes unlabelled. Keying the
    search on the wrapper's layout class instead would pair correctly but
    break silently if upstream renamed it.
    """
    node: bs4.Tag = strip
    parent = strip.parent
    while isinstance(parent, bs4.Tag):
        for child in parent.find_all(recursive=False):
            # The strip's own ancestry is not its panel group: those children
            # are the wrappers the strip sits in.
            if child is node or node in child.parents:
                continue
            if _holds_tab_panels(child):
                return _own_tab_panels(child.select('[role="tabpanel"]'), child)
        node = parent
        parent = parent.parent
    return []


def _label_tab_panels(content: bs4.Tag | bs4.BeautifulSoup) -> None:
    """Replace each Docusaurus tab strip with a label above the panel it names.

    Tabs are layout only: they decide which panel is visible at a time, a
    distinction a Markdown reader cannot act on. The strip that carries the
    labels is an HTML list, though, so converting the page as-is turns the
    labels into a bare bullet list that names content appearing further down
    the page with nothing to connect the two. The panels themselves must stay
    -- the mirror is a document, not an interactive page, so every panel is
    content a reader wants.

    Each label is therefore moved onto a bold line of its own directly above
    its panel, matching the convention the other adapters' tab conversions
    use, and the strip is removed. The pairing is made positionally: the tabs
    of a strip and the panels it controls are emitted in the same order (see
    :func:`_tab_panels_for` for how a strip's panels are told apart from those
    of a group nested inside them).

    The strip is removed ONLY when the pairing succeeded. A count mismatch
    means the markup changed shape, and a wrong pairing would attach a label
    to the wrong sample -- worse than the bare list it replaced. Leaving the
    strip in place then costs a bullet list but loses nothing: every label is
    still on the page as text, next to the panel it names.
    """
    for strip in content.find_all("ul", attrs={"role": "tablist"}):
        labels = [
            item.get_text().strip()
            for item in strip.find_all("li", attrs={"role": "tab"})
        ]
        panels = _tab_panels_for(strip)
        if not labels or len(labels) != len(panels):
            continue
        for label, panel in zip(labels, panels):
            heading = content.new_tag("p")
            strong = content.new_tag("strong")
            strong.string = label
            heading.append(strong)
            panel.insert_before(heading)
        strip.decompose()


# Slugs of the pages discovered by the current run; populated by ``discover``
# and read by the cross-link pass each page conversion runs. The pipeline
# discovers every page of a source before it fetches the first one, so the set
# is already complete when the first page is converted. A module-level set is
# what carries the information between the two hooks: the pipeline calls them
# separately, with nothing but the module itself in between.
_KNOWN_SLUGS: set[str] = set()


def _code_placeholder(index: int) -> str:
    """Return the stand-in token spliced in for one extracted code block.

    The token is plain alphanumerics so html2text passes it through the
    conversion unescaped and unwrapped. Any punctuation character (``[``,
    ``]``, ``(``, ``)``, ``*``, ``_``, ``{``, ``}``, ``#``, ``!``) could
    be escaped by html2text or merged into surrounding Markdown syntax,
    breaking the later literal ``str.replace`` that swaps the real fenced
    block back in. Pure alphanumerics are invisible to the converter.

    The token carries the source-specific ``DEEPSEEKCODEBLOCK`` prefix as
    a defensive identifier. The splice pass only ever runs over text this
    same adapter produced. Should a placeholder ever escape unspliced into
    the mirrored output (a bug in the extraction/splice logic), the prefix
    makes it trivial to trace back to the adapter that emitted it.

    **Index alignment between extraction and splicing.** The ``index``
    parameter doubles as the block's position in the extracted-blocks list
    *and* the numeric suffix embedded in the placeholder string. This is the
    contract that binds extraction and splicing together: the extraction pass
    (``_extract_code_blocks``) appends each ``(language, code_text)`` pair to
    a list and calls this function with ``len(list) - 1`` to produce the
    token it inserts into the HTML tree, while the splice pass
    (``splice_code_blocks``) iterates the same list in the same order and
    uses ``str.replace`` to swap each token for the corresponding fenced
    block. As long as both sides call ``_code_placeholder(index)`` with the
    same list index, alignment is guaranteed -- no separate matching logic
    is needed.
    """
    return f"DEEPSEEKCODEBLOCK{index}PLACEHOLDER"


def _detect_language(pre: bs4.Tag, container: bs4.Tag | None) -> str:
    """Detect the language label for one ``<pre>`` (DeepSeek / Docusaurus).

    **Docusaurus code-block markup (the HTML this adapter targets).**
    Docusaurus (the framework api-docs.deepseek.com is built on) renders
    code blocks as::

        <div class="theme-code-block">                      <!-- wrapper -->
          <div class="language-bash codeBlockContainer_*">  <!-- container -->
            <div class="codeBlockContent_*">
              <pre class="prism-code language-bash ..."><code>...</code></pre>
              <div class="buttonGroup_*"><button>Copy</button>...</div>
            </div>
          </div>
        </div>

    The ``codeBlockContainer_*`` / ``codeBlockContent_*`` / ``buttonGroup_*``
    classes are CSS-module hashes that change between Docusaurus builds, so
    they must NEVER be matched directly. The stable, semantic classes that
    survive across Docusaurus v2/v3 versions are ``theme-code-block`` on
    the outermost wrapper (used by ``extract_code_blocks`` to locate the
    replacement target) and ``language-*`` on the container ``<div>``, the
    ``<pre>``, and sometimes the ``<code>`` child.

    The label comes from the first ``language-*`` CSS class found on, in
    priority order:

    1. the ``<pre>`` element itself (most direct, least likely to be
       affected by a Docusaurus CSS-module reshuffle);
    2. its ``<code>`` child element (Docusaurus sometimes moves the class
       down one level);
    3. the ``theme-code-block`` container (the class is carried here too
       in current Docusaurus, and serves as the broadest fallback).

    Docusaurus derives this class from the Markdown fence info string of
    the source document, so it is accurate -- unlike highlight.js-guessed
    classes, which can mislabel shell blocks as JSON or plain text as
    JavaScript. Checking several nodes in this priority order keeps
    detection working if a future Docusaurus version moves the class to a
    different element in the tree.

    *container* is the ``theme-code-block`` div already located by
    ``extract_code_blocks`` during grouping (shared by every ``<pre>`` in
    the same group), NOT a fresh ``find_parent`` walk -- re-walking would
    be wasted work on code-heavy pages and a consistency hazard if the
    container class ever changes. Returns ``""`` when no ``language-*``
    class exists anywhere; the fenced block then gets no info string.
    Sanitisation of the label happens in ``extract_code_blocks``, not here.
    """
    # ``get_attribute_list`` (not ``get``) is the correct bs4 API here: it
    # ALWAYS returns a list of attribute strings -- empty when the attribute
    # is absent -- whereas ``Tag.get("class", ...)`` is annotated (and can
    # be, depending on the tree builder) a plain string or None. ``class``
    # is one of bs4's known multi-valued attributes, so under the html.parser
    # builder used in this adapter every class token is already a separate
    # list item and the returned list needs no splitting or type guards
    # before the ``language-*`` scan below.
    candidates = [pre.get_attribute_list("class")]
    code = pre.find("code")
    if code is not None:
        candidates.append(code.get_attribute_list("class"))
    if container is not None:
        candidates.append(container.get_attribute_list("class"))
    for classes in candidates:
        for cls in classes:
            if cls.startswith("language-"):
                return cls[len("language-") :]
    return ""


def _extract_code_blocks(
    content: bs4.Tag | bs4.BeautifulSoup, soup: bs4.BeautifulSoup
) -> list[tuple[str, str]]:
    """Replace every ``<pre>`` under *content* with a placeholder token.

    Thin wrapper over ``core.html_markdown.extract_code_blocks``: the
    grouping/replacement skeleton (two passes, ``id()``-keyed groups,
    label sanitisation, token joining) is provided by the shared helper;
    this adapter supplies only its site-specific parameters --
    the Docusaurus container class ``theme-code-block`` and the
    ``_detect_language`` callback above.

    When a ``<pre>`` sits inside a ``theme-code-block`` container, the
    WHOLE container is replaced by the token, which also removes the copy
    button and any line-number chrome in one move. Returns ``(language,
    code_text)`` pairs in document order, aligned with the placeholder
    indices -- see the shared function's docstring for the full contract.
    """
    return extract_code_blocks(
        content,
        soup,
        container_class="theme-code-block",
        detect_language=_detect_language,
        placeholder=_code_placeholder,
    )


def _html_to_markdown(
    html: str, slug: str = "", known_slugs: set[str] | None = None
) -> str:
    """Convert one Docusaurus docs page from HTML to Markdown.

    Isolates the doc body (``div.theme-doc-markdown``, Docusaurus's content
    container, or ``div.PromptLibrary`` on the bespoke prompt-library
    landing page), lifts out ``<pre>`` code blocks, strips navigation chrome
    that may live inside it, normalises the constructs html2text would
    otherwise mistranslate (a paragraph nested in a heading, a tab strip that
    would become a bare bullet list), repoints the page's site-absolute
    cross-links at mirrored files or upstream URLs, runs the configured
    html2text instance over the remainder, splices the code blocks back in as
    fenced blocks, strips invisible Unicode characters, and collapses
    excessive blank lines while preserving blank lines inside code blocks.

    *slug* is the on-disk path of the page being converted and *known_slugs*
    the page set this run mirrors; together they drive the cross-link pass
    (see :func:`_rewrite_content_hrefs`). Both default to "nothing is known",
    which leaves every link exactly as upstream wrote it -- the state the
    converter-only tests want, and the safe behaviour for a page converted
    outside a run.

    The fallback chain for content-container selection (the ``PromptLibrary``
    landing-page container, then ``<article>``, then the whole document)
    keeps conversion working -- if noisier -- should Docusaurus rename the
    container class. Warnings on fallback go to stderr so operators get
    early visibility of a selector break.

    The tree surgery (heading paragraphs, tab strips, cross-links) runs BEFORE
    the conversion, so html2text sees a document it already knows how to
    render; the three post-processing steps (splicing, invisible-character
    stripping, blank-line collapsing) are shared via ``core.html_markdown``.
    The ordering of those steps is deliberate:

    1. Splice code blocks back in FIRST -- the placeholder tokens are bare
       strings in the converted text, and the strip and collapse passes
       must not see them (they would treat the tokens as regular text and
       could modify them);
    2. Strip invisible characters -- these are formatting residues and stray
       control bytes from Docusaurus markup that html2text preserves; they
       corrupt copy-paste and diffs (a NUL byte even makes the file binary to
       ``git`` and ``grep``), so they go before the blank-line pass which
       works on visible whitespace only;
    3. Collapse blank lines LAST -- this is pure cosmetic cleanup of the
       visible whitespace, and it must run after code blocks are back in
       place so their interiors are protected by the fenced-block scanner
       ``iter_code_block_spans`` in ``core/html_markdown.py`` (the collapse
       pass uses it to skip over fenced code blocks instead of touching
       their semantically significant blank lines).
    """
    soup = bs4.BeautifulSoup(html, "html.parser")
    # Docusaurus renders the doc body inside div.theme-doc-markdown -- that is
    # the primary content container and produces the cleanest Markdown output.
    # When it is missing (a Docusaurus upgrade may rename the theme class),
    # fall back to the bespoke landing-page container, then to <article>,
    # then to the full document body. The fallback chain keeps conversion
    # working, but the secondary selectors may include navigation chrome
    # (breadcrumbs, pagination) that the primary container naturally
    # excludes. Log a warning on fallback so operators get early visibility
    # -- the output still validates as Markdown, so a selector break shows up
    # as noisier mirrored files rather than an error, and a logged warning
    # surfaces the cause weeks before anyone would notice the noise. The
    # element type is pinned to ``div`` (matching the fallback warnings'
    # ``div.theme-doc-markdown`` wording): Docusaurus always renders the
    # container as a div, and matching any element type could latch onto an
    # unrelated node that happens to carry the class.
    primary = soup.find("div", class_="theme-doc-markdown")
    if primary is not None:
        content = primary
    else:
        # The prompt-library page is a bespoke landing page that does not use
        # the Docusaurus doc container at all: its content lives in a custom
        # "PromptLibrary" div. That class is a stable hand-written marker
        # (not a hashed CSS-module name), so matching it is silent by design
        # -- unlike the fallbacks below, finding it is the EXPECTED outcome
        # for that page, not a selector break.
        landing = soup.find("div", class_="PromptLibrary")
        if landing is not None:
            content = landing
        else:
            content = soup.find("article")
            if content is not None:
                print(
                    "  warning: primary content container 'div.theme-doc-markdown' "
                    "not found -- falling back to <article> (upstream may have "
                    "renamed the Docusaurus theme class; mirrored Markdown may "
                    "include navigation chrome)",
                    file=sys.stderr,
                )
            else:
                # Type transition: ``content`` starts as ``bs4.Tag`` when the
                # primary container (``div.theme-doc-markdown``), the
                # landing-page container (``div.PromptLibrary``), or the
                # ``<article>`` fallback is found, but here in the deepest
                # fallback it is reassigned to the ``bs4.BeautifulSoup`` soup
                # object itself. The downstream helper ``_extract_code_blocks``
                # explicitly accepts ``bs4.Tag | bs4.BeautifulSoup`` to maintain
                # strict static typing compliance across all fallback branches.
                content = soup
                print(
                    "  warning: neither 'div.theme-doc-markdown' nor the "
                    "'PromptLibrary' container nor <article> found -- falling "
                    "back to full document body (upstream may have "
                    "significantly restructured the page; mirrored Markdown "
                    "likely includes navigation chrome)",
                    file=sys.stderr,
                )
    # Lift code blocks out first: chrome removal and conversion below must
    # not see the code text at all, and the code container's own chrome
    # (copy button, line numbers) disappears together with the block.
    blocks = _extract_code_blocks(content, soup)
    # Strip any leftover generic HTML chrome elements that may live inside
    # the content node. These carry navigation, metadata, or scripting and
    # are never part of the documentation content.
    # (Note: content(...) is a shorthand for content.find_all(...))
    for tag in content(["nav", "footer", "aside", "script", "style"]):
        tag.decompose()
    # Docusaurus also renders breadcrumb and prev/next-page navigation
    # INSIDE the content column; those carry site chrome, not documentation.
    # Remove them by exact CSS class selector. CSS class selectors match
    # WHOLE class names exactly, so ``.breadcrumbs`` cannot false-match a
    # hypothetical class like ``pseudo-breadcrumbs``.
    for tag in content.select(".pagination-nav, .breadcrumbs"):
        tag.decompose()
    # Three constructs survive the chrome removal but render WRONG under
    # html2text, so they are normalised on the tree first (each helper's
    # docstring covers its own failure mode): a paragraph nested in a heading,
    # a tab strip that would become a bullet list naming content further down,
    # and a site-absolute cross-link that resolves on the upstream site only.
    _unwrap_heading_paragraphs(content)
    _label_tab_panels(content)
    # The cross-link pass needs to know which pages this run mirrors, and an
    # empty set means that is unknown rather than "nothing is mirrored" -- the
    # two would rewrite the same links in opposite directions, so an absent
    # page set leaves every href exactly as upstream wrote it. A real run
    # always has one (``fetch_markdown`` refuses to convert without it).
    if known_slugs:
        _rewrite_content_hrefs(content, slug, known_slugs)
    # Run the pre-configured html2text converter over the stripped content
    # tree. ``make_converter()`` (from ``core.html_markdown``) returns an
    # ``html2text.HTML2Text`` instance configured with five shared options:
    # ``bodywidth = 0`` (no hard line wrapping), ``ignore_links = False``
    # (hyperlinks preserved), ``ignore_images = True`` (``<img>`` tags
    # dropped -- the mirror does not download binary files),
    # ``protect_links = True`` (no line breaks inside URLs), and
    # ``unicode_snob = True`` (Unicode characters kept verbatim rather than
    # ASCII-ified). The ``str(content)`` serialises the (now-stripped)
    # BeautifulSoup tree back to an HTML string -- this is safe because
    # ``content`` is either a ``Tag`` or a ``BeautifulSoup`` instance, and
    # both implement ``__str__`` to produce well-formed HTML. Calling
    # ``str()`` here rather than ``content.prettify()`` is deliberate:
    # prettify adds cosmetic whitespace that would change the semantics of
    # inline code spans and list-item text, while the default serializer
    # preserves the browser-rendered structure faithfully.
    text = make_converter().handle(str(content))
    # Splice the extracted code blocks back in as fenced code blocks. The
    # fence length adapts to each block's content: a block that itself
    # contains a run of backticks (docs documenting Markdown) gets a fence
    # one backtick longer than the longest inner run, so the inner run can
    # never close the fence prematurely.
    text = splice_code_blocks(text, blocks, _code_placeholder)
    # Strip the invisible characters (Unicode categories Cf and Cc, minus the
    # three controls that are line structure) that html2text and Docusaurus
    # can leave in the output.
    text = strip_invisible_characters(text)
    # Collapse runs of 3+ blank lines down to 2, but only OUTSIDE fenced
    # code blocks.
    text = collapse_blank_lines(text)
    # Strip leading/trailing whitespace from the final Markdown output before
    # returning. The pipeline compares hashes to detect upstream changes, and
    # cosmetic leading/trailing newlines (introduced by the html2text conversion
    # or the splice pass) would produce a spurious hash difference across cycles
    # even when the content is semantically identical. ``strip()`` removes all
    # leading and trailing whitespace characters (spaces, tabs, newlines) but
    # preserves internal whitespace structure including blank lines between
    # sections and fenced code blocks.
    return text.strip()


def fetch_markdown(client: httpx.Client, page: Page) -> tuple[str, str]:
    """Pipeline hook: fetch one page's HTML and return ``(markdown, hash)``.

    This is the optional ``fetch_markdown`` hook described in
    ``sources/base.py``: the pipeline calls it via ``getattr`` instead of
    downloading ``page.source_md_url``, because this source serves HTML, not
    Markdown. The converted text is validated like any other fetched
    Markdown; a page that fails validation raises ``FetchError`` so the
    pipeline records it as a failed fetch (and carries the previous manifest
    entry forward) rather than writing garbage to disk.

    Any unexpected exception out of the HTML-to-Markdown conversion (a
    parser edge case, an unforeseen markup shape, a bug in the tree surgery
    above) is caught and re-raised as ``FetchError``. The pipeline isolates
    failures PER PAGE only for ``FetchError``, so a bare exception escaping
    this hook would abort the entire source's run instead of failing just
    this page. Chaining with ``from`` keeps the original exception on
    ``__cause__``, so genuine programming errors stay distinguishable in the
    traceback instead of being silently misclassified as a page failure.

    The fetch / convert / validate / hash sequence itself is provided via
    ``core.html_markdown.fetch_markdown_converted``; this hook contributes
    only the Docusaurus-specific converter -- bound here to this page's slug
    and to the page set this run mirrors, so the converter can resolve the
    page's site-absolute cross-links (see ``_rewrite_content_hrefs``).

    Raises:
        fetch.FetchError: When no discovered slug set is available -- the
            conversion would otherwise rewrite every internal link to its
            upstream URL (see ``ensure_known_slugs``).
    """
    ensure_known_slugs("deepseek-api", _KNOWN_SLUGS, page.slug)
    known_slugs = _KNOWN_SLUGS

    def convert(html: str) -> str:
        """Convert one fetched page with its cross-links resolved."""
        return _html_to_markdown(html, page.slug, known_slugs)

    return fetch_markdown_converted(client, page, convert)
