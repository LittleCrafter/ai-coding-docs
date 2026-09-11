"""Source: Claude Code.

Claude Code's docs site (https://code.claude.com) serves every page as raw
Markdown at ``<canonical-url>.md`` -- each HTML page has a ``.md`` twin
carrying the same content. This is a deliberate convention of Anthropic's
documentation server (mintlify-style "llms-friendly" serving): appending
``.md`` to ANY docs page URL returns the page's Markdown source instead of
the rendered HTML, so the Markdown endpoint needs no discovery of its own
-- it is derived mechanically from the canonical URL. It also publishes an
XML sitemap at ``/docs/sitemap.xml`` listing every page of every locale.

Discovery is therefore simple and robust: read the sitemap, keep only the
English pages (URLs whose path starts with ``/docs/en/``), and derive each
page's Markdown URL by appending ``.md``. No HTML parsing, no JavaScript, no
guessing at URL structure.

Fragility notes -- what breaks when the upstream site changes:

* If the site drops the ``.md`` twins, discovery still succeeds but every
  page fetch starts failing (404s).
* If the English tree moves off ``/docs/en/`` (e.g. a locale restructure),
  the filter below matches nothing, and the zero-page guard in ``discover``
  raises a RuntimeError loudly instead of letting the pipeline treat every
  mirrored slug as deleted upstream.

Upstream serves those Markdown twins as MDX page sources, not as plain
Markdown: the prose carries JSX components (callouts, step and tab groups,
cards, accordions, media wrappers), the site's own HTML wrappers and
attributes, and site-absolute cross-links. None of that renders in a
plain-Markdown reader, so this adapter defines the optional ``fetch_markdown``
hook: the raw twin is downloaded and normalised to standard Markdown (see
``_normalize_page``) before the pipeline hashes and writes it.

A few pages are instead almost entirely one JavaScript component, and carry
their documentation -- prompt texts, per-file descriptions, per-event
explanations -- in that component's own data rather than in prose. Those pages
are rendered from the data (see ``_convert_data_components``), so their text
reaches a reader as standard Markdown instead of as source code.

This source generates no structural whats-new digest: ``generate_whats_new``
is off for Claude Code because upstream maintains its own weekly ``whats-new/``
pages, which are mirrored as ordinary pages -- a generated digest would only
restate them.
"""

from __future__ import annotations

import json
import posixpath
import re
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from typing import TYPE_CHECKING
from urllib.parse import urlsplit

from ..core import fetch, media
from ..core.page import Page
from ..core.sitemap import crawl_sitemap
from .base import (
    SourceConfig,
    ensure_discovered_pages,
    ensure_known_slugs,
    same_origin,
    try_make_page,
)

if TYPE_CHECKING:
    # Guard ``httpx.Client`` behind ``TYPE_CHECKING`` so that the ``httpx``
    # package is never imported at runtime — it is only needed for static type
    # checking performed by mypy, pyright, or similar tools.  The combination
    # of ``if TYPE_CHECKING`` and the top-level ``from __future__ import
    # annotations`` (PEP 563 / PEP 649) means that even the ``httpx.Client``
    # annotation strings are never actually evaluated by the CPython interpreter:
    # they exist purely as metadata for type checkers.  This avoids:
    #   - Import cycles (if ``httpx`` ever imports back into this package,
    #     the guard prevents a circular-import crash).
    #   - The runtime cost of importing ``httpx`` just for type hints.
    import httpx

SITE_URL = "https://code.claude.com"
SITEMAP_URL = f"{SITE_URL}/docs/sitemap.xml"
# Filter marker that isolates the English documentation tree from any other
# locale (e.g. ``/docs/ja/``, ``/docs/es/``, ``/docs/zh/``) that the upstream
# sitemap may list.  The filter is anchored on the URL's PARSED PATH:
# ``urlsplit(url).path`` must START WITH this prefix.  A bare substring test
# (``EN_PREFIX in url``) would also match a URL whose path merely CONTAINS
# the marker further along (e.g. ``/blog/docs/en/announcement``) and would
# then derive a bogus slug from whatever follows the marker; anchoring on the
# parsed path makes the marker's position meaningful and also immunises the
# filter against the marker appearing in a query string or fragment (those
# are stripped by ``crawl_sitemap`` before URLs reach ``discover`` anyway).
# Note that because this prefix ends with a slash, the English tree's ROOT
# page (``/docs/en``) does NOT match it; ``discover`` handles that one page
# explicitly (slug ``"index"``) before applying this prefix filter.
EN_PREFIX = "/docs/en/"

NPM_REGISTRY_URL = "https://registry.npmjs.org/@anthropic-ai/claude-code/latest"

MEDIA = media.AssetSourceConfig(
    name="claude-code",
    asset_subdir="media",
    ref_prefixes=("https://mintcdn.com/claude-code/",),
    raw_base_url="",
    strip_token_depth=1,
    allowed_extensions=(".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp"),
)

CONFIG = SourceConfig(
    name="claude-code",
    title="Claude Code",
    home_url=f"{SITE_URL}/docs/en/overview",
    generate_whats_new=False,
    version="2.1.268",
    origin="code.claude.com/docs/en/",
    how_mirrored="scraping (sitemap → `<url>.md`)",
    # The memory-directory page shows readers a sample ``MEMORY.md`` index
    # whose entries point at the topic files of the reader's OWN project
    # (``- [architecture.md](architecture.md): API client singleton``). Those
    # files are illustrative: they exist in the project being documented, not
    # in this mirror, and no upstream page serves them. Every other relative
    # destination in this source does resolve, so the exemption is limited to
    # exactly the names that sample uses.
    illustrative_link_targets=(
        "build-and-test.md",
        "architecture.md",
        "debugging.md",
    ),
)

# Slugs discovered by ``discover`` in the current run. The site's own pages
# link to each other with site-absolute paths (``](/docs/en/hooks)``); those
# paths only become links a local reader can follow once they are resolved
# against the tree this mirror actually holds, which is what this set is for.
# It is filled during discovery -- the pipeline discovers before it fetches --
# and read by the normalisation passes through ``_resolve_docs_href``.
_KNOWN_SLUGS: set[str] = set()

# Site-absolute prefix the pages' cross-links are written with, and the origin
# those paths resolve against -- the fallback target for a path that names a
# page this mirror does not hold.
DOCS_PATH_PREFIX = "/docs/en/"
DOCS_ORIGIN = f"{SITE_URL}/docs/en"
# A handful of upstream cross-links are written WITHOUT the ``docs`` segment
# (``/en/skills``). The site serves that spelling as the same page, so it
# denotes the same slug and is resolved identically; without this second
# prefix those links would reach a mirrored page as literal site-absolute
# paths, which resolve to nothing in a local checkout.
EN_PATH_PREFIX = "/en/"
# The two spellings of the documentation root, whose page is mirrored under
# the slug ``"index"``.
_ROOT_PATH_PREFIXES = (DOCS_PATH_PREFIX.rstrip("/"), EN_PATH_PREFIX.rstrip("/"))


def get_version(client: httpx.Client) -> str | None:
    """Query the npm registry for the latest published Claude Code version."""
    raw = fetch.get_with_retry(client, NPM_REGISTRY_URL)
    data = json.loads(raw)
    if isinstance(data, dict):
        version = data.get("version")
        if isinstance(version, str) and version.strip():
            return version.strip().removeprefix("v").removeprefix("V").strip()
    return None


def _sitemap_urls(client: httpx.Client) -> list[str]:
    """Fetch the sitemap, following nested sitemap indexes breadth-first.

    Upstream serves a single flat ``<urlset>`` today -- one hop, every page's
    URL in one document -- so the crawl needs no index chain to reach the
    pages. The depth bound is headroom rather than a description of the
    current tree: it exists for the day the site splits its sitemap into a
    per-section index, and it lets a chain of any shape be followed without
    the caller knowing which shape upstream chose. It is fixed rather than
    configurable because no caller has ever needed a different bound. Should
    upstream ever nest deeper than the bound, the pipeline's own child-sitemap
    warning and the zero-page guard in ``discover`` both fire loudly rather
    than the mirror quietly losing pages.
    """
    return crawl_sitemap(
        client,
        SITEMAP_URL,
        max_depth=3,
        allowed_origin=SITE_URL,
    )


def discover(client: httpx.Client) -> list[Page]:
    """Discover all English Claude Code docs pages from the sitemap.

    The slug is the URL path after ``/docs/en/`` (e.g. ``"hooks"`` or
    ``"agent-sdk/python"``); the group shown in the index is the slug's
    first path segment, or ``"root"`` for top-level pages. The English
    tree's root page itself (``/docs/en``, whose trailing slash the URL
    cleaner strips) is mirrored under the slug ``"index"``. Each page's
    ``source_md_url`` is the ``.md`` twin of its canonical URL. Results are
    deduplicated by slug (the sitemap can list a URL more than once) and
    sorted for deterministic output.
    """
    pages: list[Page] = []
    seen_slugs: set[str] = set()
    # ``_sitemap_urls`` already canonicalises every URL via ``crawl_sitemap``
    # (stripping the query string, fragment, and trailing slash), so ``url``
    # arrives here in canonical form -- no inline cleaning is needed (a
    # redundant ``urlsplit`` re-clean would only reproduce ``url`` itself).
    for url in _sitemap_urls(client):
        # Origin boundary: the URL must belong to the Claude Code origin
        # before any path-level filtering happens. The path-anchored
        # EN_PREFIX check below sees only the URL's parsed path and would
        # happily accept a foreign-host sitemap entry whose PATH starts
        # with ``/docs/en/`` -- see ``same_origin`` in ``core/utils.py``
        # for the full rationale (why a bare ``startswith(SITE_URL)`` is
        # insufficient); ``sources/base.py`` only re-exports the helper. ``_sitemap_urls`` applies the same check to child
        # sitemaps before fetching them; page URLs (non-.xml locs) are
        # passed through unchecked and are filtered here instead.
        if not same_origin(url, SITE_URL):
            continue  # foreign-origin URLs are not this adapter's docs
        # Anchor the English-tree filter on the URL's parsed PATH rather than
        # on the raw URL string: a path-anchored ``startswith`` cannot
        # false-match a URL whose path merely CONTAINS ``/docs/en/`` further
        # along (see the EN_PREFIX comment above), and slicing the slug off a
        # fixed-length prefix keeps slug derivation exact.
        path = urlsplit(url).path
        if path == EN_PREFIX.rstrip("/"):
            # The English tree's ROOT page.  The sitemap lists it as
            # ``https://code.claude.com/docs/en/`` and ``crawl_sitemap`` strips
            # the trailing slash, so it arrives here as the bare path
            # ``/docs/en`` -- which a plain ``startswith(EN_PREFIX)`` check
            # would REJECT, because EN_PREFIX itself ends with a slash.  The
            # root is therefore matched explicitly.  It is a real content
            # page (the English docs landing page) with a working Markdown
            # twin at ``/docs/en.md``, so it is mirrored like any other
            # page.  Having no path segment after the prefix, it takes the
            # conventional slug ``"index"`` -- the same slug the kimi_code
            # adapter derives for the root ``index.md`` of its docs tree --
            # and falls into the ``"root"`` group below.
            slug = "index"
        elif path.startswith(EN_PREFIX):
            # The path after ``/docs/en/`` becomes the page's slug —
            # the unique identifier used throughout the mirror pipeline for
            # file naming, index entries, and cross-references.  For a URL
            # ending in ``/docs/en/hooks`` the slug is ``"hooks"``; for
            # ``/docs/en/agent-sdk/python`` it is ``"agent-sdk/python"``
            # (a two-segment path preserved as-is).  The slice can never be
            # empty here: the bare root was handled by the branch above, and
            # ``crawl_sitemap`` has already stripped trailing slashes, so any
            # path that starts with EN_PREFIX carries at least one
            # non-slash character beyond it. For the same reason the slice
            # needs no trailing-slash cleanup of its own: every URL reaching
            # this point passed through ``crawl_sitemap``, which already strips
            # ``/`` suffixes, so no trailing slash can survive to this line.
            slug = path[len(EN_PREFIX) :]
        else:
            # The URL path does not begin with the English-docs marker
            # ``/docs/en/``, so it belongs to a different locale
            # (e.g. ``/docs/ja/``, ``/docs/es/``), or is outside the docs
            # tree entirely (e.g. a top-level homepage or a blog entry).
            # Both are irrelevant for this English-only mirror source and
            # are silently skipped — no warning is raised because it is
            # normal for a multi-locale sitemap to list many non-English
            # entries.
            continue
        # The group is the first path segment of the slug, used by the
        # index generator to organise pages into collapsible sections
        # (e.g. "agent-sdk", "deployment").  For slug ``"hooks"`` (no
        # slash) the group falls back to ``"root"``; for
        # ``"agent-sdk/python"`` it is ``"agent-sdk"``.
        group = slug.split("/", 1)[0] if "/" in slug else "root"
        # Per-entry guard: ``crawl_sitemap`` already canonicalises each URL
        # via ``clean_url``, but that cannot fix an entry whose PATH itself
        # contains characters outside the slug alphabet ``Page`` enforces
        # (a space, parentheses, unicode, ...). ``Page.__post_init__`` rejects
        # such slugs with a ValueError; without this guard that exception
        # would abort discovery for the entire source. ``try_make_page``
        # (see ``sources/base.py``) owns the guard/warning: the URL is named
        # in a stderr warning and discovery continues. The two layers are
        # complementary -- canonicalisation fixes fixable entries, this guard
        # skips unfixable ones -- and the zero-page guard below remains the
        # loud backstop if EVERY entry ends up skipped.
        if slug in seen_slugs:
            continue
        seen_slugs.add(slug)

        page = try_make_page(
            url,
            slug=slug,
            # ``url`` is already canonical: ``crawl_sitemap`` stripped
            # the query string, fragment, and any trailing slash, so it can
            # be used directly -- an inline ``rstrip("/")`` here would be
            # a dead defense that can never change the value.
            source_url=url,
            # The Markdown endpoint is derived, not discovered:
            # Anthropic's docs server serves every page's Markdown
            # source at ``<canonical-url>.md`` (see the module
            # docstring), so appending ".md" to the canonical URL is
            # the complete resolution logic -- no separate lookup
            # table or HTML scraping needed. The URL already carries
            # no trailing slash (see above), so the twin is always
            # ``.../overview.md``, never ``.../overview/.md``.
            source_md_url=f"{url}.md",
            source_id=slug,
            group=group,
        )
        if page is not None:
            pages.append(page)
    # Sort for deterministic output. Sorting by slug guarantees that the output
    # list has a stable order across runs, which matters for git diff
    # hygiene: if the list order changed between runs, the mirror tool
    # would produce spurious diffs even when no content changed.
    pages.sort(key=lambda p: p.slug)
    # Publish the discovered tree for the normalisation passes: they run per
    # page during the fetch stage (after discovery) and need to know which
    # site-absolute cross-links can be pointed at a mirrored file.
    _KNOWN_SLUGS.clear()
    _KNOWN_SLUGS.update(page.slug for page in pages)
    return ensure_discovered_pages(
        pages, "claude-code", f"English-tree filter {EN_PREFIX!r}"
    )


# ---------------------------------------------------------------------------
# MDX normalisation: fenced code, JSX components, inline HTML, cross-links
# ---------------------------------------------------------------------------
# The Markdown twins are MDX page sources, so their prose mixes four kinds of
# construct that a plain-Markdown reader cannot render:
#
# * fenced code blocks, which must survive every pass byte for byte;
# * JSX components (``<Note>``, ``<Steps>``, ``<Tabs>``, ``<Card>``, ...),
#   each of which stands for a Markdown structure (a callout, a numbered
#   list, a labelled section, a link list);
# * the site's own HTML wrappers and JSX-only attributes, which carry layout
#   and no documented content;
# * site-absolute cross-links (``](/docs/en/hooks)``), which resolve against
#   the upstream site and are dead for a reader of the mirror.
#
# Every conversion below is deliberately conservative: a construct this
# adapter cannot translate with certainty is left exactly as upstream wrote
# it, so an unmapped artifact stays visible in the mirror instead of the page
# silently losing text. A generic "strip every tag" pass would delete page
# content -- the pages use angle-bracket placeholders in prose
# (``<sessionId>``, ``CLAUDE_PLUGIN_OPTION_<KEY>``) that look like tags and are
# not -- which is why each conversion targets one known construct instead.
# Nor does any pass ever rewrite a fenced code block: a code sample that
# happens to contain ``<Note>`` or a ``/docs`` link is code, not page
# structure, which ``_shield_fenced_code`` guarantees by swapping every block
# for a one-line placeholder while the passes run.

# Opening line of a fenced code block: a line whose leading (optionally
# indented) run of backticks or tildes is at least three characters long,
# followed by anything (the info string) and a newline. The indentation is
# part of the pattern because MDX nests whole blocks -- a tab's body, a
# step's body -- and their fences are indented with them.
_FENCE_OPEN_RE = re.compile(
    r"^(?P<indent>[ \t]*)(?P<fence>`{3,}|~{3,})[^\n]*\n", re.MULTILINE
)
# The placeholders that stand in for shielded regions: one per fenced code
# block, one per MDX component definition (see ``_component_source_spans``).
# The text in front of a placeholder on its own line is captured because that
# is what the passes put there -- indentation, a list marker's continuation
# indent, a blockquote marker -- and it is what the region's remaining lines
# have to be aligned with at restore time.
_PLACEHOLDER_TEMPLATE = "<!--__{kind}_{index}__-->"
_PLACEHOLDER_RES = {
    "FENCED_CODE_BLOCK": re.compile(
        r"(?P<prefix>[^\n]*)<!--__FENCED_CODE_BLOCK_(?P<index>\d+)__-->"
    ),
    "MDX_SOURCE_BLOCK": re.compile(
        r"(?P<prefix>[^\n]*)<!--__MDX_SOURCE_BLOCK_(?P<index>\d+)__-->"
    ),
}

# An MDX component definition: the page's own JavaScript, written as a module
# export that runs from the first column. Such a block is source code, not
# page prose, so the passes that rewrite page structure leave it alone (the
# passes that only remove attributes or convert inline markup still apply --
# a ``style={{...}}`` or a ``<C>`` inside a component's code is exactly the
# JSX noise this adapter exists to remove). The block ends at the first
# closing brace of its own statement; a definition whose end cannot be found
# is left unprotected rather than guessed at, since protecting too much would
# leave real page structure unconverted.
_COMPONENT_SOURCE_START_RE = re.compile(
    r"^export[ \t]+(?:const|let|var|function|default)\b", re.MULTILINE
)
_COMPONENT_SOURCE_END_RE = re.compile(r"^};[ \t]*$", re.MULTILINE)

# An opening or closing tag, with the name of its element. Angle-bracket
# placeholders in prose (``<name>``, ``<KEY>``) match this pattern too; every
# pass below filters by element name, which is what keeps them out of reach.
_TAG_START_RE = re.compile(r"<(?P<closing>/?)(?P<name>[A-Za-z][A-Za-z0-9-]*)")
# A hard bound on how far the scanner that finds a tag's closing ``>`` may
# read. A JSX tag's attribute region legitimately spans several lines and can
# hold a large image description, but an unbounded scan would make a document
# full of unterminated tags quadratic in its length; 4000 characters covers
# the longest real tag by a wide margin (the longest in this corpus measures
# about 1150) and the bound only ever costs a tag that exceeds it, which is
# then left as upstream wrote it.
_TAG_SCAN_LIMIT = 4000

# Attribute name inside a JSX/HTML tag. The colon is part of the name so that
# Astro's client directives (``client:load``, ``client:visible``) are read as
# single attributes instead of as a name with a stray value.
_ATTR_NAME_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_:.-]*")

# Inline HTML elements this adapter understands by name. Restricting every
# tag-level pass to this set is what makes the passes safe on pages that use
# angle brackets as prose: ``<sessionId>`` and ``CLAUDE_PLUGIN_OPTION_<KEY>``
# carry a name this set does not contain, so no pass ever treats them as
# markup.
_HTML_ELEMENT_NAMES = frozenset(
    {
        "a",
        "br",
        "button",
        "code",
        "div",
        "em",
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
        "hr",
        "img",
        "input",
        "kbd",
        "li",
        "ol",
        "p",
        "path",
        "pre",
        "script",
        "section",
        "span",
        "strong",
        "summary",
        "svg",
        "table",
        "tbody",
        "td",
        "th",
        "thead",
        "tr",
        "ul",
        "video",
    }
)
# Wrappers that exist only to position content inside the upstream theme.
# Their tags are dropped and their content is kept; see
# ``_unwrap_layout_wrappers`` for the attribute that marks them.
_LAYOUT_WRAPPER_NAMES = frozenset({"div", "span", "p"})
# Attributes that describe how the upstream site renders a node and nothing
# about its content. ``className`` and ``style`` are JSX spellings that render
# as literal text in a Markdown reader, and ``data-path`` names the upstream
# asset behind a media tag whose ``src`` already carries the same path.
_PRESENTATION_ATTRIBUTES = frozenset({"style", "className", "class", "data-path"})
# Elements whose tags are unwrapped when they carry a presentation attribute.
# A bare ``<div>`` (no attributes) is left alone: it may be a semantic
# container, and only the attribute makes a wrapper's role unambiguous.
_PRESENTATION_ATTRIBUTE_NAMES = frozenset({"class", "className", "style"})

# Callout components and the GitHub Alert label each one maps to. GitHub
# renders exactly five alert labels (NOTE, TIP, IMPORTANT, WARNING, CAUTION),
# so ``info`` maps to NOTE and ``danger`` to CAUTION -- the closest supported
# equivalents, which keeps the severity the author intended. ``Callout`` is
# upstream's generic callout and renders in the informational style.
_CALLOUT_LABELS = {
    "Note": "NOTE",
    "Tip": "TIP",
    "Info": "NOTE",
    "Warning": "WARNING",
    "Danger": "CAUTION",
    "Callout": "NOTE",
}

# Components that render decoration or an interactive widget: call-to-action
# buttons, the inline icons used inside the site's own diagrams, and the mount
# points of the interactive demo pages. Only their self-closing form is
# removed; a component from this list used as a container would hold text
# between its tags, and dropping it would delete that text.
#
# What decides whether a component belongs here is whether the page's text
# can reach the reader without it. The reference filter does not: its props
# carry the column help, so ``_convert_reference_filter`` writes that out
# instead. The two settings views do not either, but their text is in the
# definition rather than in the props, so ``_convert_view_components`` puts it
# at the mount point first -- they stay listed here as the fallback for a page
# whose data cannot be rendered at all, where dropping the mount point is
# still better than leaving raw JSX where the view was.
_WIDGET_COMPONENTS = (
    "ContactSalesCard",
    "Experiment",
    "BackToIndex",
    "ClaudeExplorer",
    "ContextWindow",
    "PromptLibrary",
    "LaptopIcon",
    "FileIcon",
    "CloudIcon",
    "FolderIcon",
    "SettingsScope",
    "SettingsPrecedence",
)

# Site-absolute documentation link, in the two shapes the pages use it: a
# Markdown link destination, and an HTML/JSX ``href`` attribute. Both are
# resolved through ``_resolve_docs_href``.
_MARKDOWN_DOCS_LINK_RE = re.compile(r"\]\((?P<href>/(?:docs/)?en(?:[/#?][^)\s]*)?)\)")
_HTML_DOCS_HREF_RE = re.compile(
    r"(?P<prefix>\bhref[ \t]*=[ \t]*)(?P<quote>[\"'])"
    r"(?P<href>/(?:docs/)?en[^\"']*)(?P=quote)"
)
# One inline-code expression inside a JSX prop value: ``{'text'}`` and
# ``{"text"}``. Upstream wraps literals that would otherwise be parsed as
# markup (``<C>{'${NOTION_TOKEN}'}</C>``) in exactly this form, so unwrapping
# it is what lets the value render as the code span the component displays.
_JSX_STRING_EXPR_RE = re.compile(r"^[ \t]*\{[ \t]*([\"'])(?P<text>.*)\1[ \t]*\}[ \t]*$")


@dataclass(frozen=True, slots=True)
class _ShieldedRegion:
    """One region hidden from the passes: its text and its own indentation.

    Both kinds of shielded region -- a fenced code block and an MDX component
    definition -- are held this way, which is what lets a single restore put
    either of them back at the position its placeholder ended up at. The
    indentation is the whitespace the region's first line was written with,
    empty for a region that starts at the beginning of its line.
    """

    text: str
    indent: str


@dataclass(frozen=True, slots=True)
class _Tag:
    """One located tag: where it is, what it carries, and how it ends."""

    name: str
    start: int
    end: int
    props: str
    closing: bool
    self_closing: bool


@dataclass(frozen=True, slots=True)
class _Component:
    """One located JSX component occurrence.

    ``props`` is the raw attribute text between the tag name and the closing
    bracket -- the input every converter parses -- and ``body`` the inner
    Markdown of a container component, empty for self-closing tags. ``raw`` is
    the whole occurrence as it appears in the source, which is what a
    converter returns verbatim when it decides not to convert it.
    """

    name: str
    start: int
    end: int
    raw: str
    props: str
    body: str
    self_closing: bool


def _fence_closer(fence: str) -> re.Pattern[str]:
    """Return the pattern matching the line that closes *fence*.

    A fence only closes on a run of the same character at least as long as the
    one that opened it, so the closer is matched by length rather than by the
    mere presence of three backticks. Trailing spaces, tabs, and carriage
    returns are allowed on the closing line, as CommonMark permits.
    """
    character = re.escape(fence[0])
    return re.compile(rf"^[ \t]*{character}{{{len(fence)},}}[ \t]*\r?$", re.MULTILINE)


def _iter_fenced_spans(text: str) -> Iterator[tuple[int, int, str]]:
    """Yield ``(start, end, indent)`` for every fenced code block in *text*.

    ``start`` is the index of the fence run itself rather than of the line's
    indentation, because the indentation is what the surrounding text keeps
    when the block is taken out. The pair of indices is what lets a caller ask
    whether some other construct lies inside a block.

    An opener with no closing fence is not a code block (it is a lone run of
    backticks in prose), so the scan resumes after it and the text keeps its
    original form. A failed closer search is remembered per fence run -- the
    first position from which that run's closer is known to be absent -- and
    every later opener of the same run starts further right, so the absence
    still holds and the search is skipped instead of repeated. That is what
    keeps a document full of lone backtick runs linear in its length rather
    than quadratic: each distinct fence run reaches the end of the document at
    most once.
    """
    # Fence run -> the earliest index from which that run's closer search
    # failed. The closer pattern depends on the run's character and length, so
    # runs are keyed by their own text rather than by their character alone: a
    # line of three backticks closes a three-backtick fence but not a
    # four-backtick one, and the two therefore fail independently.
    no_closer_from: dict[str, int] = {}
    position = 0
    while (opener := _FENCE_OPEN_RE.search(text, position)) is not None:
        fence = opener.group("fence")
        known_absent = no_closer_from.get(fence)
        if known_absent is not None and opener.end() >= known_absent:
            position = opener.end()
            continue
        closer = _fence_closer(fence).search(text, opener.end())
        if closer is None:
            no_closer_from[fence] = opener.end()
            position = opener.end()
            continue
        yield opener.start("fence"), closer.end(), opener.group("indent")
        position = closer.end()


def _shield_fenced_code(text: str) -> tuple[str, list[_ShieldedRegion]]:
    """Replace every fenced code block in *text* with a one-line placeholder.

    Shielding code up front is what makes the passes that follow safe to write:
    none of them has to know where the fences are, because the code they must
    not touch is no longer in the document they are handed.

    The shield replaces the fence run itself, not the indentation in front of
    it: the placeholder then sits at the column the fence sat at, which is what
    keeps a body's common indentation measurable while the code is hidden, and
    what lets the restore put the block back at the column the placeholder
    ended up at. The blocks themselves are found by ``_iter_fenced_spans``,
    which is also what the passes that run before the shield use to tell a
    construct inside a code sample from one in the page's own prose.
    """
    blocks: list[_ShieldedRegion] = []
    parts: list[str] = []
    cursor = 0
    for start, end, indent in _iter_fenced_spans(text):
        blocks.append(_ShieldedRegion(text[start:end], indent))
        parts.append(text[cursor:start])
        parts.append(
            _PLACEHOLDER_TEMPLATE.format(
                kind="FENCED_CODE_BLOCK", index=len(blocks) - 1
            )
        )
        cursor = end
    parts.append(text[cursor:])
    return "".join(parts), blocks


def _component_source_spans(text: str) -> list[tuple[int, int]]:
    """Return the spans of the pages' own MDX component definitions.

    Several pages are mostly a JavaScript component the site renders
    interactively: the exported definition is the page's source, and the prose
    a reader wants is inside its string literals. Rewriting page structure
    there would edit code rather than documentation, so these spans are
    shielded from the structural passes.
    """
    spans: list[tuple[int, int]] = []
    for start in _COMPONENT_SOURCE_START_RE.finditer(text):
        end = _COMPONENT_SOURCE_END_RE.search(text, start.end())
        if end is None:
            continue  # unterminated definition: leave the text unprotected
        spans.append((start.start(), end.end()))
    return spans


def _shield_component_sources(
    text: str, spans: list[tuple[int, int]]
) -> tuple[str, list[_ShieldedRegion]]:
    """Replace every MDX component definition with a one-line placeholder.

    The definitions are source code rather than page text, so the passes that
    rewrite page structure are run without them in the document -- the same
    trick ``_shield_fenced_code`` uses for code samples, and restored the same
    way. A placeholder sits on the first line of the definition's span, which
    starts a line of its own, so it keeps the block's position exactly.
    """
    blocks: list[_ShieldedRegion] = []
    parts: list[str] = []
    cursor = 0
    for start, end in spans:
        blocks.append(_ShieldedRegion(text[start:end], ""))
        parts.append(text[cursor:start])
        parts.append(
            _PLACEHOLDER_TEMPLATE.format(kind="MDX_SOURCE_BLOCK", index=len(blocks) - 1)
        )
        cursor = end
    parts.append(text[cursor:])
    return "".join(parts), blocks


def _reshift_block(block: _ShieldedRegion, prefix: str) -> str:
    """Return a shielded block's text rewritten for the line prefix *prefix*.

    Every block line ends up carrying the text the passes left in front of the
    placeholder, in place of the indentation the fence was written with: a
    block that stayed in the body it came from keeps its column, one dedented
    under a list marker moves with the marker's continuation indent, and one
    quoted into a GitHub Alert gets the same ``> `` marker as the prose around
    it -- without which the alert's blockquote would end at the fence and the
    sample would spill out of the callout.

    A blank line inside a code block must keep a blockquote marker to stay
    inside the quote, but needs nothing where the prefix is only whitespace,
    so a whitespace-only prefix leaves blank lines blank.
    """
    lines = block.text.split("\n")
    shifted = [f"{prefix}{lines[0]}"]
    for line in lines[1:]:
        if not line.strip():
            shifted.append(prefix.rstrip() if prefix.strip() else "")
            continue
        cut = 0
        while cut < len(block.indent) and cut < len(line) and line[cut] in " \t":
            cut += 1
        shifted.append(f"{prefix}{line[cut:]}")
    return "\n".join(shifted)


def _restore_shielded(text: str, blocks: list[_ShieldedRegion], kind: str) -> str:
    """Put every shielded region back where its placeholder ended up.

    A pass that dedents a component body, re-indents one under a list marker,
    or quotes one into an alert moves the placeholder line along with the rest
    of the text, while the region itself, hidden in ``blocks``, keeps the
    indentation it was written with. Restoring it verbatim would move a fence's
    opening line without moving its body, which is enough to break the block:
    an interior line still indented as a component's child no longer belongs to
    a fence that now starts at column zero, and the sample spills into the
    prose as an indented code block (or out of the callout that quoted it).
    Each region is therefore rewritten for the prefix its placeholder line
    carries -- see ``_reshift_block``.
    """
    if not blocks:
        return text
    parts: list[str] = []
    cursor = 0
    for match in _PLACEHOLDER_RES[kind].finditer(text):
        index = int(match.group("index"))
        parts.append(text[cursor : match.start()])
        if index < len(blocks):
            parts.append(_reshift_block(blocks[index], match.group("prefix")))
        else:
            # Not a placeholder this scan produced: the text is page content
            # that merely looks like one, so it is re-emitted untouched.
            parts.append(match.group(0))
        cursor = match.end()
    parts.append(text[cursor:])
    return "".join(parts)


def _find_tag_end(text: str, start: int, limit: int | None = None) -> int | None:
    """Return the index just past the ``>`` that closes the tag opened at *start*.

    A regex cannot delimit a JSX tag: attribute values legitimately contain
    ``>`` (``alt="a > b"``, a comparison in a style expression), and the props
    of the larger components span several lines, so ``<Tag[^>]*>`` either
    stops at the first ``>`` inside the data or -- worse, because it looks like
    it worked -- swallows everything up to the next line-final ``>``, deleting
    documented entries. This scanner walks the tag instead and only accepts a
    ``>`` that is both outside a quoted string and outside a ``{...}``
    expression, which is exactly where JSX ends a tag.

    *limit*, when given, is an exclusive index the scan may not reach; callers
    pass the start of the next opening tag with the same name, because an
    unterminated tag must not read across its sibling. The scan is additionally
    bounded by ``_TAG_SCAN_LIMIT`` characters, so a document full of
    unterminated tags costs a constant per tag instead of a pass to its end.

    Returns ``None`` for an unterminated tag; callers then leave the text
    untouched rather than guessing at a boundary.
    """
    quote = ""
    depth = 0
    index = start + 1
    stop = len(text) if limit is None else min(limit, len(text))
    stop = min(stop, start + _TAG_SCAN_LIMIT)
    while index < stop:
        char = text[index]
        if quote:
            if char == "\\":
                # Backslash escape inside a string literal: skip the next
                # character unconditionally, so an escaped quote does not end
                # the string early.
                index += 2
                continue
            if char == quote:
                quote = ""
            index += 1
            continue
        if char == ">" and depth == 0:
            return index + 1
        if char in "\"'`":
            # Template literals (`` ` ``) are scanned like plain strings: docs
            # use them for prompt text and URL builders and never for a nested
            # tag, so treating the whole literal as opaque keeps the scanner
            # simple without losing a boundary in this corpus.
            quote = char
        elif char == "{":
            depth += 1
        elif char == "}" and depth:
            depth -= 1
        index += 1
    return None


def _iter_tags(text: str, names: frozenset[str]) -> Iterator[_Tag]:
    """Yield every tag in *text* whose element name is in *names*, in order.

    Both opening and closing tags are yielded, and a tag whose closing ``>``
    cannot be located is skipped: the scan resumes after its ``<``, so a
    malformed tag never hides the well-formed ones that follow it.
    """
    position = 0
    while (match := _TAG_START_RE.search(text, position)) is not None:
        if match.group("name") not in names:
            position = match.end()
            continue
        end = _find_tag_end(text, match.start())
        if end is None:
            position = match.end()
            continue
        closing = bool(match.group("closing"))
        self_closing = not closing and text[end - 2 : end] == "/>"
        props = text[match.end() : end - 1]
        if self_closing:
            props = props[:-1]
        yield _Tag(
            name=match.group("name"),
            start=match.start(),
            end=end,
            props=props,
            closing=closing,
            self_closing=self_closing,
        )
        position = end


def _brace_end(text: str, start: int) -> int | None:
    """Return the index just past the ``}`` that closes the brace at *start*.

    Quoted strings inside the expression are skipped in whole, so a brace
    written inside a string literal does not close the expression early.
    Returns ``None`` when the expression never closes within the text.
    """
    depth = 0
    index = start
    quote = ""
    while index < len(text):
        char = text[index]
        if quote:
            if char == "\\":
                index += 2
                continue
            if char == quote:
                quote = ""
            index += 1
            continue
        if char in "\"'`":
            quote = char
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return index + 1
        index += 1
    return None


def _attribute_value_end(props: str, start: int) -> int | None:
    """Return the index just past the value that starts at *start*.

    The four value shapes JSX allows are a double-quoted string, a
    single-quoted string, a ``{...}`` expression, and a bare run of
    characters ending at whitespace or the tag's own end. Returns ``None`` for
    a value that never closes, which leaves that attribute unread.
    """
    if start >= len(props):
        return None
    char = props[start]
    if char in "\"'":
        end = props.find(char, start + 1)
        if end == -1 or "\n" in props[start + 1 : end]:
            return None
        return end + 1
    if char == "{":
        return _brace_end(props, start)
    index = start
    while index < len(props) and not props[index].isspace():
        index += 1
    return index


def _iter_attributes(props: str) -> Iterator[tuple[int, int, str]]:
    """Yield ``(start, end, name)`` for every attribute in a tag's props.

    A spread attribute (``{...rest}``) is yielded with an empty name: it has no
    name to match and no value a converter may read, but it must still be
    accounted for so the spans of the attributes around it stay exact.
    """
    index = 0
    length = len(props)
    while index < length:
        char = props[index]
        if char.isspace():
            index += 1
            continue
        if char == "{":
            end = _brace_end(props, index)
            if end is None:
                return
            yield (index, end, "")
            index = end
            continue
        match = _ATTR_NAME_RE.match(props, index)
        if match is None:
            index += 1
            continue
        name = match.group(0)
        cursor = match.end()
        probe = cursor
        while probe < length and props[probe] in " \t":
            probe += 1
        if probe < length and props[probe] == "=":
            probe += 1
            while probe < length and props[probe].isspace():
                probe += 1
            value_end = _attribute_value_end(props, probe)
            if value_end is None:
                index = cursor
                continue
            yield (cursor - len(name), value_end, name)
            index = value_end
            continue
        yield (index, cursor, name)
        index = cursor


def _attribute_text(props: str, name: str) -> str:
    """Return the text of attribute *name*, or "" when the tag has none.

    A quoted value loses its quotes, and a ``{...}`` expression loses the
    braces that mark it as one, because what every caller wants is the text
    the attribute carries, not the syntax that carries it. The lookup is
    case-insensitive as a defensive measure: the pages this adapter converts
    spell their attributes in lowercase (``title``, ``href``, ``src``), and
    folding case costs nothing while keeping the lookup working on a page
    that writes one of them in the HTML style.
    """
    wanted = name.lower()
    for start, end, attribute in _iter_attributes(props):
        if attribute.lower() != wanted:
            continue
        raw = props[start:end]
        _, separator, value = raw.partition("=")
        if not separator:
            return ""
        value = value.strip()
        if value.startswith("{"):
            inner = _brace_end(value, 0)
            return value[1 : inner - 1].strip() if inner is not None else ""
        return value.strip("\"'")
    return ""


def _quoted_values(text: str) -> list[str]:
    """Return the quoted strings of a JSX array expression, in order.

    ``["v2.1.234-v2.1.239"]`` is how the ``tags`` attribute of an ``<Update>``
    spells its version list, and the strings inside it are the whole of what
    it carries.
    """
    return re.findall(r"[\"']([^\"'\n]*)[\"']", text)


# ---------------------------------------------------------------------------
# JavaScript literal reader: the pages' own data
# ---------------------------------------------------------------------------
# Some pages are almost entirely a JavaScript component, and the documentation
# they carry -- prompt texts, file descriptions, per-event explanations -- sits
# inside that component's own data as JavaScript objects and arrays. This
# reader turns those literals back into Python values so the renderers below
# can write them out as Markdown.
#
# The reader claims one dialect: object and array literals built from strings,
# templates, numbers, booleans, nulls, nested literals, and JSX fragments. It
# is a reader rather than a parser on purpose -- it never evaluates anything,
# so a page cannot smuggle code into the mirror through it -- and everything
# it does not recognize comes back as ``_JS_UNREADABLE``. A caller that meets
# that marker keeps the page's component source as a fenced code block instead
# of rendering from a half-read value, so an unseen shape costs readability
# and never content.

# Bound on how many wrappers (a call, an arrow function, a pair of brackets)
# the reader steps over before it expects the literal itself. Real data sits
# behind ``useMemo(() => [...], [])`` and little else; the bound exists so a
# pathological declaration cannot spin.
_MAX_JS_WRAPPER_DEPTH = 8

_JS_NUMBER_RE = re.compile(r"-?\d+(?:\.\d+)?")
_JS_IDENTIFIER_RE = re.compile(r"[A-Za-z_$][\w$]*")
_JS_CALL_RE = re.compile(r"[A-Za-z_$][\w$.]*[ \t]*\([ \t]*")
_JS_ARROW_RE = re.compile(r"(?:\([^()]*\)|[A-Za-z_$][\w$]*)[ \t]*=>[ \t]*")
_JS_BRACKET_PAIRS = {"(": ")", "[": "]", "{": "}"}


class _JsUnreadable:
    """Marker for a JavaScript value the literal reader cannot represent.

    Every renderer treats it as "not understood": the page then keeps its
    component source, rather than being rewritten from a value that was only
    partly read.
    """

    __slots__ = ()

    def __repr__(self) -> str:
        return "_JS_UNREADABLE"


_JS_UNREADABLE = _JsUnreadable()


@dataclass(frozen=True, slots=True)
class _Jsx:
    """A JSX expression, held as the source text that spells it.

    The inline components the pages write inside their data (``<C>``/``<A>``)
    are converted by the same passes that convert them anywhere else, so a JSX
    value is best carried through untouched as text.
    """

    text: str


def _js_skip_space(text: str, index: int) -> int:
    """Return the index of the first non-whitespace character at or after *index*."""
    while index < len(text) and text[index].isspace():
        index += 1
    return index


def _js_string_end(text: str, start: int) -> int | None:
    """Return the index just past the string literal that opens at *start*.

    Backslash escapes are stepped over whole, so an escaped quote does not end
    the string early. A template literal may also carry ``${...}``
    interpolations, which are stepped over as balanced groups. Returns ``None``
    for a single- or double-quoted string that never closes on its line -- the
    only shape a JavaScript file cannot continue past.
    """
    quote = text[start]
    index = start + 1
    while index < len(text):
        char = text[index]
        if char == "\\":
            index += 2
            continue
        if char == quote:
            return index + 1
        if char == "\n" and quote != "`":
            return None
        if quote == "`" and char == "$" and text[index + 1 : index + 2] == "{":
            group_end = _bracket_end(text, index + 1)
            if group_end is None:
                return None
            index = group_end
            continue
        index += 1
    return None


def _js_unescape(raw: str) -> str:
    """Return *raw* with the JavaScript escape sequences it carries resolved.

    ``\\n``, ``\\t`` and ``\\r`` become the characters they stand for; every
    other escape (``\\'``, ``\\"``, ``\\```, ``\\$``, ``\\\\``) stands for the
    character it quotes, so the text is the text the page displays.
    """
    out: list[str] = []
    index = 0
    while index < len(raw):
        char = raw[index]
        if char != "\\" or index + 1 >= len(raw):
            out.append(char)
            index += 1
            continue
        following = raw[index + 1]
        out.append({"n": "\n", "t": "\t", "r": "\r"}.get(following, following))
        index += 2
    return "".join(out)


def _bracket_end(text: str, start: int) -> int | None:
    """Return the index just past the bracket group that opens at *start*.

    The three bracket kinds are tracked on one stack, so a group of any shape
    nested inside another is stepped over as a unit, and quoted strings are
    skipped whole so a bracket written inside one does not count. Returns
    ``None`` for a group that never closes.
    """
    stack = [text[start]]
    index = start + 1
    while index < len(text):
        char = text[index]
        if char in "\"'`":
            end = _js_string_end(text, index)
            if end is None:
                return None
            index = end
            continue
        if char in _JS_BRACKET_PAIRS:
            stack.append(char)
        elif char in ")]}":
            if not stack or _JS_BRACKET_PAIRS[stack[-1]] != char:
                return None
            stack.pop()
            if not stack:
                return index + 1
        index += 1
    return None


def _jsx_end(text: str, start: int) -> int | None:
    """Return the index just past the JSX expression that starts at *start*.

    Both shapes the pages' data uses are handled: a single element with its
    closing tag, and a fragment (``<>...</>``) holding text and elements
    between them. ``{...}`` expressions inside the JSX are stepped over whole,
    so a tag or a brace written inside one does not end the value early.
    Returns ``None`` for a value that never closes.
    """
    depth = 0
    index = start
    while index < len(text):
        char = text[index]
        if char == "{":
            group_end = _brace_end(text, index)
            if group_end is None:
                return None
            index = group_end
            continue
        if char != "<":
            index += 1
            continue
        if text.startswith("</>", index):
            depth -= 1
            index += 3
            if depth <= 0:
                return index
            continue
        if text.startswith("<>", index):
            depth += 1
            index += 2
            continue
        match = _TAG_START_RE.match(text, index)
        if match is None:
            index += 1
            continue
        tag_end = _find_tag_end(text, index)
        if tag_end is None:
            return None
        if text[tag_end - 2 : tag_end] == "/>":
            index = tag_end
            if depth <= 0:
                return tag_end
            continue
        depth += -1 if match.group("closing") else 1
        index = tag_end
        if depth <= 0:
            return tag_end
    return None


def _js_value_skip(text: str, start: int) -> int:
    """Return the index at which an unreadable value at *start* gives way.

    The scan stops at the first character that separates values at the
    enclosing literal's own level -- a comma, a semicolon, or the bracket that
    closes it -- so the caller can carry on with the elements around the value
    it could not read. Quoted strings and bracketed groups are stepped over
    whole, so a separator written inside one does not end the value early.
    """
    index = start
    while index < len(text):
        char = text[index]
        if char in "\"'`":
            end = _js_string_end(text, index)
            if end is None:
                return index + 1
            index = end
            continue
        if char in _JS_BRACKET_PAIRS:
            group_end = _bracket_end(text, index)
            if group_end is None:
                return index + 1
            index = group_end
            continue
        if char in ",}];":
            return index
        index += 1
    return index


def _js_literal(
    text: str, start: int, resolving: frozenset[str] = frozenset()
) -> tuple[object, int]:
    """Read the JavaScript value at *start* and return it with its end index.

    The end index is always returned, even for a value the reader cannot
    represent, so the enclosing array or object keeps its place and the values
    around the unreadable one are still read.

    *resolving* names the declarations currently being looked up, which is how
    a value written as another declaration's name (``note: commandsNote``) is
    read from that declaration instead of coming back unreadable. The set
    stops a declaration that refers to itself (directly or through a cycle)
    from recursing forever.
    """
    char = text[start]
    if char in "\"'`":
        end = _js_string_end(text, start)
        if end is None:
            return _JS_UNREADABLE, start + 1
        return _js_unescape(text[start + 1 : end - 1]), end
    if char == "[":
        return _js_array(text, start, resolving)
    if char == "{":
        return _js_object(text, start, resolving)
    if char == "<":
        end = _jsx_end(text, start)
        if end is None:
            return _JS_UNREADABLE, start + 1
        return _Jsx(text[start:end]), end
    number = _JS_NUMBER_RE.match(text, start)
    if number is not None:
        raw = number.group(0)
        return (float(raw) if "." in raw else int(raw)), number.end()
    identifier = _JS_IDENTIFIER_RE.match(text, start)
    if identifier is not None:
        word = identifier.group(0)
        if word in ("true", "false"):
            return word == "true", identifier.end()
        if word == "null":
            return None, identifier.end()
        if word not in resolving:
            reference = _js_declaration(text, word, resolving | {word})
            if reference is not None:
                return reference.value, identifier.end()
    return _JS_UNREADABLE, _js_value_skip(text, start)


def _js_array(text: str, start: int, resolving: frozenset[str]) -> tuple[object, int]:
    """Read the array literal that opens at *start*, with its end index."""
    items: list[object] = []
    index = start + 1
    while True:
        index = _js_skip_space(text, index)
        if index >= len(text):
            return _JS_UNREADABLE, start + 1
        if text[index] == "]":
            return items, index + 1
        value, index = _js_literal(text, index, resolving)
        items.append(value)
        index = _js_skip_space(text, index)
        if text[index : index + 1] == ",":
            index += 1
            continue
        if text[index : index + 1] != "]":
            return _JS_UNREADABLE, start + 1


def _js_key(text: str, index: int) -> tuple[str | None, int]:
    """Read the key of an object entry, returning it with its end index."""
    if text[index : index + 1] in ("'", '"', "`"):
        end = _js_string_end(text, index)
        if end is None:
            return None, index
        return _js_unescape(text[index + 1 : end - 1]), end
    identifier = _JS_IDENTIFIER_RE.match(text, index)
    if identifier is not None:
        return identifier.group(0), identifier.end()
    number = _JS_NUMBER_RE.match(text, index)
    if number is not None:
        return number.group(0), number.end()
    return None, index


def _js_object(text: str, start: int, resolving: frozenset[str]) -> tuple[object, int]:
    """Read the object literal that opens at *start*, with its end index.

    A spread entry (``...rest``) has no key to read and no value a renderer
    may print, so it makes the whole object unreadable rather than being
    silently dropped from it.
    """
    fields: dict[str, object] = {}
    index = start + 1
    while True:
        index = _js_skip_space(text, index)
        if index >= len(text):
            return _JS_UNREADABLE, start + 1
        if text[index] == "}":
            return fields, index + 1
        key, index = _js_key(text, index)
        if key is None:
            return _JS_UNREADABLE, start + 1
        index = _js_skip_space(text, index)
        if text[index : index + 1] != ":":
            return _JS_UNREADABLE, start + 1
        value, index = _js_literal(text, _js_skip_space(text, index + 1), resolving)
        fields[key] = value
        index = _js_skip_space(text, index)
        if text[index : index + 1] == ",":
            index += 1
            continue
        if text[index : index + 1] != "}":
            return _JS_UNREADABLE, start + 1


def _js_value_start(text: str, index: int) -> int | None:
    """Return the index at which the value expression at *index* becomes a literal.

    A declaration rarely hands its literal over directly: the pages pass their
    data through a hook (``useMemo(() => [...], [])``) or wrap it in a
    parenthesised expression, so a call, an arrow function, or a pair of
    brackets may stand between the ``=`` and the value. Each wrapper is
    stepped over until a literal is reached. Returns ``None`` when what
    remains is not a literal -- an identifier, a function body, a conditional.
    """
    for _ in range(_MAX_JS_WRAPPER_DEPTH):
        index = _js_skip_space(text, index)
        if index >= len(text):
            return None
        char = text[index]
        if char in "\"'`<[{" or char == "-" or char.isdigit():
            return index
        # The arrow is tested before the bracket: an arrow's parameter list and
        # a parenthesised expression both open with ``(``, and only the arrow
        # has a ``=>`` after the closing bracket to tell them apart.
        arrow = _JS_ARROW_RE.match(text, index)
        if arrow is not None:
            index = arrow.end()
            continue
        call = _JS_CALL_RE.match(text, index)
        if call is not None:
            index = call.end()
            continue
        if char == "(":
            # A parenthesised expression: the value is inside the brackets, so
            # the scan moves past the opening one and stops at its content.
            index += 1
            continue
        return None
    return None


@dataclass(frozen=True, slots=True)
class _JsDeclaration:
    """One ``const``/``let``/``var`` binding: its value and the span it occupies."""

    value: object
    start: int
    end: int


def _js_declaration(
    text: str, name: str, resolving: frozenset[str] = frozenset()
) -> _JsDeclaration | None:
    """Return the value bound to *name*, with the span the declaration occupies.

    The span covers the binding from the ``const`` keyword through its closing
    semicolon, which is what a caller needs to take the declaration out of the
    document it came from. Returns ``None`` when no such binding exists or when
    the value behind it is not a literal this reader understands.
    """
    pattern = re.compile(rf"\b(?:const|let|var)[ \t]+{re.escape(name)}[ \t]*=")
    match = pattern.search(text)
    if match is None:
        return None
    value_start = _js_value_start(text, match.end())
    if value_start is None:
        return None
    value, end = _js_literal(text, value_start, resolving)
    return _JsDeclaration(
        value=value, start=match.start(), end=_js_statement_end(text, end)
    )


def _js_readable(value: object) -> bool:
    """Return whether *value* holds nothing the literal reader failed to read."""
    if isinstance(value, _JsUnreadable):
        return False
    if isinstance(value, dict):
        return all(_js_readable(item) for item in value.values())
    if isinstance(value, list):
        return all(_js_readable(item) for item in value)
    return True


def _js_text(value: object) -> str:
    """Return a readable value as the text it stands for.

    A string is its own text; a JSX value is emitted as the source it was
    written with, so the passes that convert inline ``<C>``/``<A>`` markup and
    resolve site-absolute links see it exactly as they see it anywhere else in
    the page. Anything else -- a number, a boolean, an unreadable value --
    contributes no text.
    """
    if isinstance(value, str):
        return value
    if isinstance(value, _Jsx):
        raw = value.text
        if raw.startswith("<>") and raw.endswith("</>"):
            raw = raw[2:-3]
        return " ".join(raw.split())
    return ""


def _iter_components(text: str, name: str) -> Iterator[_Component]:
    """Yield every ``<name ...>`` component in *text*, in document order.

    Self-closing tags yield a component with an empty ``body``. Container tags
    (``<name ...>...</name>``) yield the inner Markdown up to the matching
    closing tag; nesting of the same name is respected, so the body of an
    outer component ends at its own closer rather than at the first inner one.
    A tag whose opening or closing boundary cannot be located is skipped,
    leaving its text for the caller to keep, and the scan resumes after it so
    that a later occurrence -- which may well be well formed -- is still
    converted.
    """
    opener = re.compile(rf"<{re.escape(name)}\b")
    position = 0
    # Set once a closing tag is known to be absent from some index onward: a
    # later opener starts searching further right, so the same absence holds
    # for it, and recording it keeps a document of unterminated container tags
    # from rescanning its tail once per tag.
    no_closer_from: int | None = None
    while True:
        match = opener.search(text, position)
        if match is None:
            return
        following = opener.search(text, match.end())
        limit = following.start() if following is not None else None
        tag_end = _find_tag_end(text, match.start(), limit)
        if tag_end is None:
            position = match.end()
            continue
        props = text[match.end() : tag_end - 1]
        if text[tag_end - 2 : tag_end] == "/>":
            yield _Component(
                name=name,
                start=match.start(),
                end=tag_end,
                raw=text[match.start() : tag_end],
                props=props[:-1],
                body="",
                self_closing=True,
            )
            position = tag_end
            continue
        if no_closer_from is not None and tag_end >= no_closer_from:
            position = tag_end
            continue
        end = _matching_close(text, name, tag_end)
        if end is None:
            no_closer_from = tag_end
            position = tag_end
            continue
        yield _Component(
            name=name,
            start=match.start(),
            end=end,
            raw=text[match.start() : end],
            props=props,
            body=text[tag_end : end - len(f"</{name}>")],
            self_closing=False,
        )
        position = end


def _matching_close(text: str, name: str, tag_end: int) -> int | None:
    """Return the index just past the closing tag that matches the open at *tag_end*.

    Containers nest (a card group inside a step, a callout inside a tab), so
    the matching close is the one where the nesting depth returns to zero.
    Self-closing tags of the same name do not open a level. Returns ``None``
    when the text ends first, which leaves that component untouched rather
    than guessing at a boundary.
    """
    opener = re.compile(rf"<{re.escape(name)}\b")
    closer = f"</{name}>"
    depth = 1
    position = tag_end
    while depth:
        close_index = text.find(closer, position)
        if close_index == -1:
            return None
        nested = opener.search(text, position)
        if nested is None or nested.start() > close_index:
            depth -= 1
            position = close_index + len(closer)
            continue
        nested_end = _find_tag_end(text, nested.start())
        if nested_end is not None and text[nested_end - 2 : nested_end] != "/>":
            depth += 1
        position = nested_end if nested_end is not None else nested.end()
    return position


# Bound on the nesting depth of components that wrap other components of the
# same name. Real pages nest two levels at most; the bound only exists so a
# renderer that somehow re-emits its own tag cannot spin forever.
_MAX_NESTED_COMPONENT_PASSES = 10


def _align_to_line(before: str, rendered: str) -> tuple[str, str]:
    """Indent *rendered* to the column the component it replaces sits at.

    A component that occupies its own line is written at its block's
    indentation, and what it renders to takes that block's place, so every
    line of the rendering -- a callout's quoted lines, a list item's
    continuation indent, a fence's own markers -- has to start at the same
    column. The indentation in front of the component moves from the text
    before it to the front of each rendered line, which is what makes the
    result valid Markdown and what keeps a body's common indentation
    measurable afterwards: a body whose first line was dedented while the rest
    was not has no common prefix left to remove. A component used inside a
    sentence keeps its exact position instead -- only a run of whitespace
    between the line start and the component is treated as its indentation.

    Returns the text before the component with that indentation removed, and
    the rendering with it applied.
    """
    line_start = before.rfind("\n") + 1
    indent = before[line_start:]
    if not indent or indent.strip():
        return before, rendered
    lines = [f"{indent}{line}" if line else "" for line in rendered.split("\n")]
    return before[:line_start], "\n".join(lines)


def _render_components(
    text: str, name: str, render: Callable[[_Component], str]
) -> str:
    """Replace every ``<name>`` component in *text* with ``render(component)``.

    Each component carries its own source text in ``raw``, so a converter that
    keeps a component verbatim (unreadable props, an unexpected shape) restores
    that component exactly, whatever the surrounding passes did before it. The
    rendering is aligned to the component's own line (see ``_align_to_line``)
    so a converted component never leaves the block it was part of.
    Passes repeat while the text keeps changing, which is what converts
    components nested inside another component of the same name: the outer one
    is rendered first with its body intact, and the next pass picks up the tags
    that body still holds.
    """
    for _ in range(_MAX_NESTED_COMPONENT_PASSES):
        parts: list[str] = []
        cursor = 0
        for component in _iter_components(text, name):
            before, rendered = _align_to_line(
                text[cursor : component.start], render(component)
            )
            parts.append(before)
            parts.append(rendered)
            cursor = component.end
        parts.append(text[cursor:])
        updated = "".join(parts)
        if updated == text:
            return text
        text = updated
    return text


def _dedent(body: str) -> list[str]:
    """Return *body*'s lines with their common leading indentation removed.

    Indentation inside an MDX component is source formatting with no meaning,
    but it means something once the component is unwrapped into plain
    Markdown: a heading or a list indented by four spaces becomes an indented
    code block, and a fence indented away from the text that follows it stops
    being a fence. Tabs are expanded first so a body mixing tabs and spaces is
    measured on a single column basis, blank lines are excluded from the
    minimum because they carry no meaningful indentation, and only the COMMON
    prefix is removed -- content indented deeper than its siblings (a nested
    list, a code sample) keeps its internal structure.
    """
    lines = [line.expandtabs() for line in body.split("\n")]
    indent = min(
        (len(line) - len(line.lstrip()) for line in lines if line.strip()),
        default=0,
    )
    return [line[indent:] if line.strip() else "" for line in lines]


def _indent_block(text: str, indent: str) -> str:
    """Return *text* with *indent* in front of each of its lines."""
    return "\n".join(f"{indent}{line}" if line else "" for line in text.split("\n"))


def _drop_site_scripts(text: str) -> str:
    """Remove the site's own script tags, which are not page content.

    One page loads a browser-side asset that rewrites SDK type links in place;
    a mirrored page has no such script and cannot use one, and an ``<script>``
    tag in a Markdown file renders as literal text. A script tag that carries
    content between its tags is left alone: that content may be prose.
    """

    def render(component: _Component) -> str:
        return "" if component.self_closing else component.raw

    return _render_components(text, "script", render)


def _render_callout(label: str, component: _Component) -> str:
    """Render one callout component as a GitHub Alert blockquote.

    The alert's label line is followed by the body with every line quoted, and
    blank lines inside the body keep the blockquote open (they render as a
    bare ``>``), so paragraph breaks inside the callout survive. A title
    attribute, when the component carries one, is rendered bold on the line
    after the label, matching the alert style the other source adapters use.
    """
    detected = _attribute_text(component.props, "title")
    lines = [f"> [!{label}]"]
    detected = detected.strip()
    if detected:
        lines.append(f"> **{detected}**")
    body = "\n".join(_dedent(component.body)).strip("\n")
    if body:
        if detected:
            lines.append(">")
        lines.extend(f"> {line}" if line.strip() else ">" for line in body.split("\n"))
    return "\n".join(lines)


def _convert_callouts(text: str) -> str:
    """Convert ``<Note>``/``<Tip>``/``<Warning>``-style callouts to alerts."""
    for name, label in _CALLOUT_LABELS.items():

        def render(component: _Component, label: str = label) -> str:
            return _render_callout(label, component)

        text = _render_components(text, name, render)
    return text


def _render_step(component: _Component, number: int) -> str:
    """Render one ``<Step>`` as an ordered-list item, body indented under it.

    The item's marker is numbered rather than a repeated ``1.``: the mirror is
    read as text as often as it is rendered, and there the explicit number is
    what keeps the steps countable. The continuation indent is the marker's own
    width, which is the column Markdown requires a list item's block content
    (a code sample above all) to start at.
    """
    title = _attribute_text(component.props, "title").strip()
    marker = f"{number}. "
    lines = [f"{marker}**{title}**" if title else marker.rstrip()]
    body = "\n".join(_dedent(component.body)).strip("\n")
    if body:
        lines.append("")
        lines.extend(_indent_block(body, " " * len(marker)).split("\n"))
    return "\n".join(lines)


def _render_step_group(component: _Component) -> str:
    """Render a whole ``<Steps>`` group as one ordered list.

    The group's own tags are dropped and its ``<Step>`` children become the
    list items, numbered within this group, so the numbering restarts where
    the author started a new group. Text between the steps is preserved around
    them, and a group holding no recognisable step is unwrapped verbatim
    rather than dropped.
    """
    parts: list[str] = []
    cursor = 0
    number = 0
    for step in _iter_components(component.body, "Step"):
        number += 1
        parts.append(component.body[cursor : step.start])
        parts.append(_render_step(step, number))
        cursor = step.end
    parts.append(component.body[cursor:])
    if number == 0:
        return "\n".join(_dedent(component.body)).strip("\n")
    return "\n".join(part.strip("\n") for part in parts if part.strip())


def _convert_steps(text: str) -> str:
    """Convert ``<Steps>`` groups and standalone ``<Step>`` items to lists."""
    text = _render_components(text, "Steps", _render_step_group)
    counter = 0

    def render(component: _Component) -> str:
        # A step outside a group is still a step: it keeps its own numbering,
        # which for a lone item is simply the item marker itself.
        nonlocal counter
        counter += 1
        return _render_step(component, counter)

    return _render_components(text, "Step", render)


def _render_labelled_block(component: _Component) -> str:
    """Render a labelled container as a bold label followed by its body.

    The tab and accordion components both display a title the reader needs
    (``Native Install (Recommended)``, ``Color token reference``) above the
    content they reveal. A bold line keeps that title in place without
    claiming a heading level the surrounding page may already use, and keeps
    the body -- code samples included -- intact beneath it.
    """
    title = _attribute_text(component.props, "title").strip()
    body = "\n".join(_dedent(component.body)).strip("\n")
    parts = [part for part in (f"**{title}**" if title else "", body) if part]
    return "\n\n".join(parts)


def _convert_tabs(text: str) -> str:
    """Render ``<Tabs>`` groups and standalone ``<Tab>`` panels as sections.

    The group is layout only -- it decides which panel is visible at a time,
    a distinction a Markdown reader cannot act on -- so its tabs are rendered
    one after another under their own labels, which keeps every panel's
    content in the page.
    """
    text = _render_components(text, "Tabs", _render_children_verbatim)
    return _render_components(text, "Tab", _render_labelled_block)


def _render_children_verbatim(component: _Component) -> str:
    """Unwrap a layout-only container, keeping its content and indentation."""
    return "\n".join(_dedent(component.body)).strip("\n")


def _render_card(component: _Component, slug: str, known_slugs: set[str]) -> str:
    """Render one ``<Card>`` as a bold linked title with its body beneath.

    The component's ``title`` and ``href`` are content, not styling: the card
    is a link to another page with a short description, and dropping the
    attributes as markup would delete both the label the reader sees and the
    target it points at. They are rendered as a Markdown link instead, with
    the site-absolute ``href`` resolved like any other internal link.
    """
    title = _attribute_text(component.props, "title").strip()
    href = _attribute_text(component.props, "href").strip()
    if title and href:
        head = f"**[{title}]({_resolve_docs_href(href, slug, known_slugs)})**"
    elif title:
        head = f"**{title}**"
    else:
        head = ""
    body = "\n".join(_dedent(component.body)).strip("\n")
    return "\n\n".join(part for part in (head, body) if part)


def _convert_cards(text: str, slug: str, known_slugs: set[str]) -> str:
    """Render ``<CardGroup>`` grids and their ``<Card>`` children as text."""
    text = _render_components(text, "CardGroup", _render_children_verbatim)

    def render(component: _Component) -> str:
        return _render_card(component, slug, known_slugs)

    return _render_components(text, "Card", render)


def _convert_accordions(text: str) -> str:
    """Render ``<AccordionGroup>``/``<Accordion>`` collapsibles as sections."""
    text = _render_components(text, "AccordionGroup", _render_children_verbatim)
    return _render_components(text, "Accordion", _render_labelled_block)


def _render_update(component: _Component) -> str:
    """Render one ``<Update>`` digest entry as a heading with its metadata.

    The label names the entry (``Week 34``) and the ``tags`` array carries the
    releases it covers, so both become the heading; the description holds the
    entry's date range and is kept as an italic line beneath it. Everything
    the component states about the entry therefore stays in the page, and the
    body follows as ordinary Markdown.
    """
    label = _attribute_text(component.props, "label").strip()
    tags = _quoted_values(_attribute_text(component.props, "tags"))
    description = _attribute_text(component.props, "description").strip()
    heading = label or "Update"
    if tags:
        heading = f"{heading} ({', '.join(tags)})"
    body = "\n".join(_dedent(component.body)).strip("\n")
    parts = [f"## {heading}"]
    if description:
        parts.append(f"*{description}*")
    if body:
        parts.append(body)
    return "\n\n".join(parts)


def _convert_updates(text: str) -> str:
    """Convert ``<Update>`` digest entries to headed sections."""
    return _render_components(text, "Update", _render_update)


def _convert_code_groups(text: str) -> str:
    """Unwrap ``<CodeGroup>`` blocks, which are tabbed code samples.

    Each sample inside the group already carries its own label on its opening
    fence line (the shell or file name after the language), which is code text
    and stays exactly as written, so the group's own tags are the only thing
    the reader would otherwise see. Unwrapping removes them and leaves every
    sample -- and its label -- in place.
    """
    return _render_components(text, "CodeGroup", _render_children_verbatim)


def _convert_frames(text: str) -> str:
    """Unwrap ``<Frame>`` wrappers, which only add a border around a figure.

    The wrapper's whole content is the media tag inside it (an ``<img>`` or a
    ``<video>``), which the media stage and ``_convert_media_tags`` handle; the
    frame itself contributes nothing a Markdown reader can render.
    """
    return _render_components(text, "Frame", _render_children_verbatim)


def _js_attribute_value(props: str, name: str) -> object | None:
    """Return the JavaScript value an attribute of a component carries.

    The value is read through the same literal reader the pages' own data goes
    through, so ``columnHelp={{ topic: "..." }}`` and ``facets={['scope']}``
    both arrive as the value they are. Returns ``None`` for an absent
    attribute and for a value the reader cannot represent, which callers treat
    as "leave this component alone".
    """
    raw = _attribute_text(props, name)
    if not raw:
        return None
    start = _js_value_start(raw, 0)
    if start is None:
        return None
    value, _ = _js_literal(raw, start)
    return value if _js_readable(value) else None


def _js_string_list(value: object) -> list[str]:
    """Return the strings of a readable value that holds a list of them."""
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str)]


def _render_reference_filter(component: _Component) -> str:
    """Render the reference filter's help text where the widget sat.

    The filter bar shows one explanation per column it can filter on, and
    those explanations live in the component's props, so the widget's own
    removal would take them out of the page. They become a bullet list
    instead. The props that only configure the widget -- the noun it counts,
    its search placeholder -- say nothing about the content and go with it.

    A component whose help text cannot be read is left exactly as upstream
    wrote it: a shape this adapter does not know must not turn into a page
    that silently lost the explanation.
    """
    if not component.self_closing:
        return component.raw
    lines: list[str] = []
    column_help = _js_attribute_value(component.props, "columnHelp")
    if not isinstance(column_help, dict):
        return component.raw
    for key, help_text in column_help.items():
        text = _js_text(help_text).strip()
        if text:
            lines.append(f"* **{key}**: {text}")
    facets = _js_string_list(_js_attribute_value(component.props, "facets"))
    if facets:
        lines.append(f"* **facets**: {', '.join(facets)}")
    facet_order = _js_attribute_value(component.props, "facetOrder")
    if isinstance(facet_order, dict):
        for key, values in facet_order.items():
            ordered = _js_string_list(values)
            if ordered:
                lines.append(f"* **{key}** (sort order): {', '.join(ordered)}")
    return "\n".join(lines) if lines else component.raw


def _convert_reference_filter(text: str) -> str:
    """Replace the reference filter with the column help its props carry."""
    return _render_components(text, "ReferenceFilter", _render_reference_filter)


def _drop_widget_components(text: str) -> str:
    """Remove the components that render a widget and no documentation text.

    Only self-closing occurrences are removed. A component from this list used
    as a container would hold Markdown between its tags, and dropping it would
    silently delete that content -- such a tag is left in place instead.
    """

    def render(component: _Component) -> str:
        return "" if component.self_closing else component.raw

    for name in _WIDGET_COMPONENTS:
        text = _render_components(text, name, render)
    return text


def _convert_media_tags(text: str) -> str:
    """Rewrite ``<video>`` wrappers into a plain link to the same media.

    The wrapper's attributes are browser playback flags, and the mirrored
    pages keep video demos as external links (the mirror stage only downloads
    images and diagrams -- see the project README), so the element is replaced
    by a link to the exact URL it played. A ``<video>`` with no readable
    ``src`` is left as upstream wrote it.
    """

    def render(component: _Component) -> str:
        source = _attribute_text(component.props, "src").strip()
        if not source:
            return component.raw
        label = _attribute_text(component.props, "title").strip() or "Video demo"
        return f"[{label}]({source})"

    return _render_components(text, "video", render)


def _convert_pseudo_tags(text: str, slug: str, known_slugs: set[str]) -> str:
    """Convert the pages' inline ``<C>``/``<B>``/``<A>`` components to Markdown.

    One page defines three short inline components -- a code span, a bold run,
    and a link -- and uses them throughout its prose, so the mirrored page
    would otherwise read as raw JSX. The value of a code component is written
    as a JSX expression wherever it would otherwise be parsed as markup
    (``<C>{'${NOTION_TOKEN}'}</C>``), which is unwrapped to the literal text it
    stands for before the span is built.
    """

    def render_code(component: _Component) -> str:
        expression = _JSX_STRING_EXPR_RE.match(component.body)
        value = expression.group("text") if expression else component.body
        value = " ".join(value.split())
        return f"`{value}`" if value else ""

    def render_bold(component: _Component) -> str:
        value = " ".join(component.body.split())
        return f"**{value}**" if value else ""

    def render_link(component: _Component) -> str:
        href = _attribute_text(component.props, "href").strip()
        label = " ".join(component.body.split())
        if not href:
            return label
        return f"[{label}]({_resolve_docs_href(href, slug, known_slugs)})"

    text = _render_components(text, "C", render_code)
    text = _render_components(text, "B", render_bold)
    return _render_components(text, "A", render_link)


def _drop_attributes(props: str, drop: frozenset[str]) -> str:
    """Remove the named attributes from a tag's props, whitespace included.

    The whitespace run in front of each removed attribute goes with it, so the
    rebuilt tag has no double space and no dangling space before its closing
    bracket; the attributes around it keep their own text untouched.
    """
    parts: list[str] = []
    cursor = 0
    for start, end, name in _iter_attributes(props):
        if name not in drop:
            continue
        cut = start
        while cut > cursor and props[cut - 1] in " \t\n":
            cut -= 1
        parts.append(props[cursor:cut])
        cursor = end
    parts.append(props[cursor:])
    return "".join(parts)


def _render_clean_tag(tag: _Tag, text: str) -> str:
    """Return one tag with its presentation-only attributes removed.

    A self-closing ``<span>`` that carries an ``id`` is the pages' anchor
    marker for a footnote or a deep link (``<span id="fn1" ... />``). It is
    rendered as an explicit ``<a id="fn1"></a>`` element: the anchor is what
    makes ``[text](#fn1)`` resolve, and an empty anchor element is the form
    every Markdown reader keeps in the output.
    """
    raw = text[tag.start : tag.end]
    if tag.name == "span" and tag.self_closing:
        anchor_id = _attribute_text(tag.props, "id").strip()
        if anchor_id:
            return f'<a id="{anchor_id}"></a>'
    cleaned = _drop_attributes(tag.props, _PRESENTATION_ATTRIBUTES)
    if cleaned == tag.props:
        return raw
    opening = "/" if tag.closing else ""
    closing = "/" if tag.self_closing else ""
    return f"<{opening}{tag.name}{cleaned}{closing}>"


def _strip_presentation_attributes(text: str) -> str:
    """Remove the site's own styling attributes from the tags that carry them.

    ``style={{...}}`` and ``className="..."`` are JSX spellings of CSS that
    render as literal text in a Markdown reader, and ``data-path`` repeats the
    asset path already present in a media tag's ``src``. None of them says
    anything about the content, so their removal cannot lose documentation;
    the element itself -- and every other attribute on it -- is kept.
    """
    parts: list[str] = []
    cursor = 0
    for tag in _iter_tags(text, _HTML_ELEMENT_NAMES):
        parts.append(text[cursor : tag.start])
        parts.append(_render_clean_tag(tag, text))
        cursor = tag.end
    parts.append(text[cursor:])
    return "".join(parts)


def _unwrap_layout_wrappers(text: str) -> str:
    """Drop presentation-only ``<div>``/``<span>``/``<p>`` wrappers, keeping content.

    A tag is dropped when it is a CLOSING tag whose opening tag was dropped,
    or an OPENING tag that carries a ``class``/``className``/``style``
    attribute. An opening tag without one of those is re-emitted verbatim and
    its closing tag is kept with it, so the two always stay balanced -- a
    wrapper this adapter does not recognize never leaves unbalanced markup
    behind. Self-closing wrappers are not containers and are kept as well.
    Nesting is tracked with a stack for the same reason.
    """
    parts: list[str] = []
    dropped: list[bool] = []
    cursor = 0
    for tag in _iter_tags(text, _LAYOUT_WRAPPER_NAMES):
        parts.append(text[cursor : tag.start])
        cursor = tag.end
        raw = text[tag.start : tag.end]
        if tag.closing:
            parts.append("" if dropped and dropped.pop() else raw)
        elif tag.self_closing:
            parts.append(raw)
        else:
            presentational = any(
                name in _PRESENTATION_ATTRIBUTE_NAMES
                for _, _, name in _iter_attributes(tag.props)
            )
            dropped.append(presentational)
            if not presentational:
                parts.append(raw)
    parts.append(text[cursor:])
    return "".join(parts)


def _resolve_docs_href(href: str, current_slug: str, known_slugs: set[str]) -> str:
    """Resolve one site-absolute ``/docs/en/...`` reference for the mirror.

    The path names a page of the upstream documentation tree, so it is
    rewritten to the relative link that reaches the same page in the mirror
    (``/docs/en/hooks`` read from ``agent-sdk/python`` becomes
    ``../hooks.md``), with any anchor preserved. A path that is not part of
    the mirrored tree -- an unpublished route, a page the sitemap omits -- is
    rewritten to its upstream URL instead: the link then still works for a
    reader who is online, where a site-absolute path would work for nobody.

    Upstream writes most of those paths with the ``docs`` segment
    (``/docs/en/hooks``) and a few without it (``/en/skills``); both
    spellings address the same page, so both resolve to the same slug. The
    upstream fallback always names the canonical ``/docs/en/...`` route.

    Anything else -- an external URL, a bare anchor, a link that is already
    relative -- is returned unchanged: it names no upstream documentation page,
    and prefixing it with the documentation origin would turn a working link
    into a broken one.

    A query string is dropped on every branch, mirrored and upstream alike:
    only the path up to the ``?`` names the page, and the upstream fallback is
    rebuilt from the slug that path produced, so the parameters are not
    carried over.
    """
    path, _, anchor = href.partition("#")
    path = path.split("?", 1)[0].rstrip("/")
    if path in _ROOT_PATH_PREFIXES:
        slug = "index"  # the English tree's root page
    elif path.startswith(DOCS_PATH_PREFIX):
        slug = path[len(DOCS_PATH_PREFIX) :]
    elif path.startswith(EN_PATH_PREFIX):
        slug = path[len(EN_PATH_PREFIX) :]
    else:
        return href
    if slug.endswith(".md"):
        slug = slug[: -len(".md")]
    if slug in known_slugs:
        current_dir = posixpath.dirname(current_slug) or "."
        relative = posixpath.relpath(f"{slug}.md", current_dir)
        if not relative.startswith((".", "/")):
            relative = f"./{relative}"
        return f"{relative}#{anchor}" if anchor else relative
    upstream = DOCS_ORIGIN if slug == "index" else f"{DOCS_ORIGIN}/{slug}"
    return f"{upstream}#{anchor}" if anchor else upstream


def _resolve_internal_links(text: str, slug: str, known_slugs: set[str]) -> str:
    """Point the pages' site-absolute links at the mirror or at upstream.

    Both shapes the pages use are handled: Markdown link destinations
    (``[Hooks](/docs/en/hooks)``) and HTML ``href`` attributes
    (``<a href="/docs/en/changelog#2-1-83">``). The two passes only match a
    leading ``/docs/en`` path, so external URLs and already-relative links are
    never touched -- which is also what keeps the resolution idempotent, since
    neither of its results begins with that path.
    """

    def markdown_target(match: re.Match[str]) -> str:
        return f"]({_resolve_docs_href(match.group('href'), slug, known_slugs)})"

    def html_target(match: re.Match[str]) -> str:
        resolved = _resolve_docs_href(match.group("href"), slug, known_slugs)
        return f"{match.group('prefix')}{match.group('quote')}{resolved}{match.group('quote')}"

    text = _MARKDOWN_DOCS_LINK_RE.sub(markdown_target, text)
    return _HTML_DOCS_HREF_RE.sub(html_target, text)


def _fenced_block(info: str, body: str) -> str:
    """Return *body* as a fenced code block, labelled with *info*.

    The fence is made longer than the longest run of backticks in the body, so
    a sample that carries Markdown of its own -- a ``CLAUDE.md`` example with
    its own fences -- keeps them instead of ending the block around it.
    """
    longest = max((len(run) for run in re.findall(r"`+", body)), default=0)
    fence = "`" * max(3, longest + 1)
    return f"{fence}{info}\n{body.strip()}\n{fence}"


def _js_statement_end(text: str, start: int) -> int:
    """Return the index just past the ``;`` that ends the statement at *start*.

    A declaration's value is often only the head of its statement
    (``useMemo(() => [...], [])`` keeps going past the array), so cutting a
    declaration out of a page needs the statement's own end rather than the
    value's. Quoted strings and bracketed groups are stepped over whole; a
    newline ends the search, which leaves a statement written without a
    semicolon in the page rather than cutting it in the wrong place.
    """
    index = start
    while index < len(text):
        char = text[index]
        if char in "\"'`":
            end = _js_string_end(text, index)
            if end is None:
                return index
            index = end
            continue
        if char in _JS_BRACKET_PAIRS:
            end = _bracket_end(text, index)
            if end is None:
                return index
            index = end
            continue
        if char == ";":
            return index + 1
        if char == "\n":
            return index
        index += 1
    return index


def _js_read_data(text: str, name: str) -> object | None:
    """Return the value bound to *name* when it is readable in full.

    ``None`` means the declaration is absent, is not a literal, or holds a
    value the reader did not understand. Callers treat all three the same way:
    they do not render the page from it.
    """
    declaration = _js_declaration(text, name)
    if declaration is None or not _js_readable(declaration.value):
        return None
    return declaration.value


# ---------------------------------------------------------------------------
# Pages whose body is a JavaScript component carrying the documentation
# ---------------------------------------------------------------------------
# A handful of pages are mostly one JavaScript component, and the prose a
# reader wants -- prompt texts, per-file descriptions, per-event explanations
# -- sits inside its data. Each page below is rendered from that data:
#
# * the data literals become ordinary Markdown (sections, lists, tables);
# * the component source that carried them is not mirrored. It is the site's
#   implementation of an interactive view, and a mirrored page has no renderer
#   to hand it to -- the same judgement the widget list makes. Source that
#   also holds page text which no data literal carries is kept as a fenced
#   code block rather than dropped, since fencing preserves text where
#   dropping it does not (the context window page's per-phase commentary);
# * a page whose data cannot be read in full keeps its definitions as fenced
#   code blocks instead of being rendered from a partly-read value. That is
#   the safe direction: an upstream shape this adapter has not seen costs a
#   page its readability, never its content.
#
# The rendering is a text transformation like every other pass, so an already
# written page has no component definitions left for it to find and the pass
# is a no-op on it.

# Lead-in labels for the lists the explorer shows under a file: they are the
# headings the upstream detail panel prints above each one.
_DIRECTORY_SECTION_LABELS = {"tips": "Tips", "contains": "Common keys"}

# The explorer's example blocks carry the file's own extension as their
# language, which is what tells a reader (or an agent) how to read the sample.
_EXAMPLE_LANGUAGES = {"md": "markdown", "json": "json"}

# Labels the pages' own views print: the link from a file entry to its
# documentation page, the line that says when a file is read, and the link
# from a timeline step to the page that explains it. Reusing the views' own
# wording keeps a rendered page reading the way the view it replaces reads.
_DIRECTORY_WHEN_LABEL = "When it loads"
_DIRECTORY_DOCS_LABEL = "Full docs"
_CONTEXT_LINK_LABEL = "Learn more"


@dataclass(frozen=True, slots=True)
class _DataPage:
    """The Markdown a page's component definitions and view mounts become.

    ``definitions`` holds one entry per definition span: the Markdown that
    replaces it, an empty string for a definition whose data is rendered at a
    mount point elsewhere in the page, or ``None`` for a definition kept as a
    fenced code block. ``views`` maps a component name to the Markdown that
    replaces its self-closing mount point, for the pages that need it.
    """

    definitions: list[str | None]
    views: dict[str, str]


def _label_map(value: object) -> dict[str, str]:
    """Return a label map -- a data object whose every value names something.

    The keys are the page's own identifiers and the values the text it shows
    for them; anything else in the object makes the map unusable, since a
    label that cannot be read would leave an identifier printed in the page.
    """
    if not isinstance(value, dict):
        return {}
    labels: dict[str, str] = {}
    for key, item in value.items():
        text = _js_text(item)
        if not text:
            return {}
        labels[key] = text
    return labels


def _docs_path(href: str) -> str:
    """Return a reference written against the locale root as a docs path.

    The pages' prose writes its own cross-links site-absolute (``/docs/en/...``)
    while the data inside their components writes them locale-relative
    (``/en/...``). Both name the same page of the same tree; rewriting the
    second into the first is what lets the pass that resolves cross-links --
    which only matches a leading ``/docs/en`` path -- reach them too.
    """
    return f"/docs{href}" if href.startswith("/en/") else href


@dataclass(frozen=True, slots=True)
class _PromptLabels:
    """The label maps the prompt library's component renders its text with.

    Read from the page's own maps rather than written into the adapter, so the
    mirror keeps the wording the page uses -- and so a heading the page renames
    is renamed here too.
    """

    headings: dict[str, str]
    tags: dict[str, str]
    groups: dict[str, str]
    sources: dict[str, str]
    needs: dict[str, str]
    paste: dict[str, str]
    hrefs: dict[str, str]


def _render_prompt_records(
    raw: list[object], docs: dict[str, object], labels: _PromptLabels
) -> str | None:
    """Render the prompt library's records as Markdown sections, or ``None``.

    ``None`` is returned for any record whose documentation cannot be read,
    which is what keeps a partly-understood page from being rendered with a
    prompt missing from it.
    """
    lines: list[str] = ["## Prompts"]
    group = ""
    for record in raw:
        if not isinstance(record, dict):
            return None
        identifier = record.get("id")
        entry = docs.get(identifier) if isinstance(identifier, str) else None
        if not isinstance(identifier, str) or not isinstance(entry, dict):
            return None
        phase = labels.groups.get(str(record.get("sdlc", "")), "")
        category = labels.groups.get(str(record.get("cat", "")), "")
        header = " - ".join(part for part in (phase, category) if part)
        if header and header != group:
            group = header
            lines.extend(("", f"### {header}"))
        title = _js_text(entry.get("title")).strip() or identifier
        lines.extend(("", f"#### {title}"))
        if record.get("startN") is not None:
            lines.extend(("", f"*Start here: {record['startN']}*"))
        tags = [
            labels.tags.get(role, role)
            for role in record.get("roles") or []
            if isinstance(role, str)
        ]
        if tags:
            lines.extend(("", f"*Tags: {', '.join(tags)}*"))
        paste = record.get("paste")
        if isinstance(paste, str) and labels.paste.get(paste):
            lines.extend(("", f"*{labels.paste[paste]}*"))
        lines.extend(("", _fenced_block("text", _fill_prompt(record))))
        details: list[str] = []
        for key, field in (("whyWorks", "teaches"), ("makeItStick", "next")):
            value = _js_text(entry.get(field)).strip()
            if value and labels.headings.get(key):
                details.append(f"* **{labels.headings[key]}**: {value}")
        needs = record.get("needs")
        if isinstance(needs, str) and labels.needs.get(needs):
            heading = labels.headings.get("needsLabel")
            details.append(f"* **{heading}**: {labels.needs[needs]}")
        source = record.get("src")
        if isinstance(source, str) and labels.sources.get(source):
            source_label = labels.sources[source]
            href = _docs_path(labels.hrefs.get(source, ""))
            linked = f"[{source_label}]({href})" if href else source_label
            details.append(f"* **{labels.headings['from']}**: {linked}")
        if details:
            lines.extend(("", *details))
    return "\n".join(lines)


def _fill_prompt(record: dict[str, object]) -> str:
    """Return a prompt record's text with its slot defaults filled in.

    The page shows every prompt with the slot values it ships substituted for
    the ``{slot}`` markers, which is what a reader copies, so the mirror shows
    the same text rather than the template with its markers still in it.
    """
    prompt = _js_text(record.get("prompt"))
    slots = record.get("slots")
    if not isinstance(slots, dict):
        return prompt

    def replace(match: re.Match[str]) -> str:
        slot = match.group(1)
        value = slots.get(slot)
        return _js_text(value) if isinstance(value, str) else match.group(0)

    return re.sub(r"\{(\w+)\}", replace, prompt)


def _render_prompt_library(text: str, spans: list[tuple[int, int]]) -> _DataPage | None:
    """Render the prompt library page from its data exports.

    The page is one component plus five label maps: the prompts sit in a
    ``RAW`` array inside the component, their titles and explanations in a
    ``text`` map keyed by prompt id, and the labels the component renders its
    filters and section headings with in the maps beside it. Only the first
    definition is replaced by the rendering; the maps have no place of their
    own once the data they name is written out.
    """
    raw = _js_read_data(text, "RAW")
    docs = _js_read_data(text, "text")
    shared = _js_read_data(text, "labels")
    tag_labels = _label_map(_js_read_data(text, "tagLabels"))
    phase_labels = _label_map(_js_read_data(text, "phaseLabels"))
    cat_labels = _label_map(_js_read_data(text, "catLabels"))
    source_labels = _label_map(_js_read_data(text, "sourceLabels"))
    sources = _label_map(_js_read_data(text, "SOURCES"))
    if not isinstance(shared, dict):
        return None
    headings = _label_map(
        {
            key: shared.get(key)
            for key in ("whyWorks", "makeItStick", "needsLabel", "from")
        }
    )
    labels = _PromptLabels(
        headings=headings,
        tags=tag_labels,
        groups={**phase_labels, **cat_labels},
        sources=source_labels,
        needs=_label_map(shared.get("needs")),
        paste=_label_map(shared.get("paste")),
        hrefs=sources,
    )
    if not (
        isinstance(raw, list)
        and isinstance(docs, dict)
        and headings
        and labels.tags
        and labels.groups
        and labels.sources
        and labels.hrefs
    ):
        return None
    rendered = _render_prompt_records(raw, docs, labels)
    if rendered is None:
        return None
    return _DataPage(definitions=[rendered, *([""] * (len(spans) - 1))], views={})


def _directory_example_language(node: dict[str, object]) -> str:
    """Return the language label for a file entry's example block."""
    icon = node.get("icon")
    return _EXAMPLE_LANGUAGES.get(icon, "text") if isinstance(icon, str) else "text"


def _render_directory_entry(
    node: dict[str, object], depth: int, badges: dict[str, str]
) -> str | None:
    """Render one file or folder entry of the ``.claude`` explorer.

    The entry's heading carries its path, so the nesting of the tree is the
    nesting of the document's headings; the entry's own text -- what the file
    is, when Claude Code reads it, what it holds, and how to write one -- is
    the body under that heading. ``None`` is returned for an entry whose text
    cannot be read.
    """
    label = _js_text(node.get("label")).strip()
    if not label:
        return None
    # Two levels of heading are reserved for the two roots of the tree (the
    # project directory and the home directory), so an entry's level is its
    # distance from the root plus two. A tree deeper than Markdown's six
    # heading levels keeps its place through the bold label instead.
    level = depth + 2
    head = f"{'#' * level} {label}" if level <= 6 else f"**{label}**"
    blocks: list[str] = [head]
    one_liner = _js_text(node.get("oneLiner")).strip()
    badge = node.get("badge")
    badge_label = badges.get(badge, "") if isinstance(badge, str) else ""
    if node.get("autogen") is True:
        badge_label = badges.get("autogen", badge_label)
    if one_liner:
        suffix = f" ({badge_label})" if badge_label else ""
        blocks.append(f"*{one_liner}*{suffix}")
    when = _js_text(node.get("when")).strip()
    if when:
        blocks.append(f"*{_DIRECTORY_WHEN_LABEL}: {when}*")
    description = node.get("description")
    paragraphs = description if isinstance(description, list) else [description]
    for paragraph in paragraphs:
        text = _js_text(paragraph).strip()
        if text:
            blocks.append(text)
    for field, section in _DIRECTORY_SECTION_LABELS.items():
        items = node.get(field)
        if not isinstance(items, list):
            continue
        entries = [f"* {text}" for text in map(_js_text, items) if text.strip()]
        if entries:
            # The label and its list are one block, so the items stay a single
            # list rather than a run of one-item lists separated by blank
            # lines.
            blocks.append("\n\n".join([f"**{section}**", "\n".join(entries)]))
    example = node.get("example")
    if isinstance(example, str) and example.strip():
        intro = _js_text(node.get("exampleIntro")).strip()
        if intro:
            blocks.append(intro)
        blocks.append(
            _fenced_block(_directory_example_language(node), _js_unescape(example))
        )
    docs_link = _docs_path(_js_text(node.get("docsLink")).strip())
    if docs_link:
        blocks.append(f"[{_DIRECTORY_DOCS_LABEL}]({docs_link})")
    children = node.get("children")
    if isinstance(children, list):
        for child in children:
            if not isinstance(child, dict):
                return None
            rendered = _render_directory_entry(child, depth + 1, badges)
            if rendered is None:
                return None
            blocks.append(rendered)
    return "\n\n".join(blocks)


def _render_claude_directory(
    text: str, spans: list[tuple[int, int]]
) -> _DataPage | None:
    """Render the ``.claude`` directory page from its file tree.

    The page's explorer holds every file and folder it shows -- paths, what
    each one is for, when Claude Code reads it, its example, and the link to
    its documentation page -- as one nested object. Rendering it walks the
    tree, so the document keeps the shape the interactive view has: a section
    per root, a heading per entry under it, and the file reference the page's
    own tables cannot carry in full.
    """
    tree = _js_read_data(text, "FILE_TREE")
    badge_styles = _js_read_data(text, "BADGE_STYLES")
    if not isinstance(tree, dict) or not isinstance(badge_styles, dict):
        return None
    badges: dict[str, str] = {}
    for key, style in badge_styles.items():
        if not isinstance(style, dict):
            return None
        badges[key] = _js_text(style.get("label"))
    blocks: list[str] = []
    for root in tree.values():
        if not isinstance(root, dict):
            return None
        label = _js_text(root.get("label")).strip()
        children = root.get("children")
        if not label or not isinstance(children, list):
            return None
        rendered_children: list[str] = []
        for child in children:
            if not isinstance(child, dict):
                return None
            rendered = _render_directory_entry(child, 1, badges)
            if rendered is None:
                return None
            rendered_children.append(rendered)
        blocks.append("\n\n".join([f"## {label}", *rendered_children]))
    return _DataPage(definitions=["\n\n".join(blocks)], views={})


def _table_cell(value: object) -> str:
    """Return *value*'s text as one table cell: a single line, pipes escaped."""
    return " ".join(_js_text(value).split()).replace("|", r"\|")


def _excise(text: str, cuts: list[tuple[int, int]]) -> str:
    """Return *text* without the given spans, which must not overlap.

    Used to take the declarations a renderer has already written out of a
    component's source, so what remains is only the source no data carries.
    """
    parts: list[str] = []
    cursor = 0
    for start, end in cuts:
        parts.append(text[cursor:start])
        cursor = end
    parts.append(text[cursor:])
    return "".join(parts)


def _render_context_timeline(
    max_tokens: int,
    events: list[object],
    vis_meta: dict[str, object],
    kind_meta: dict[str, object],
) -> str | None:
    """Render the simulated session as a table, or ``None`` for a step it cannot read.

    One row per step, in the order the session reaches it. The row says what
    enters the context window, which label the page gives the thing that put
    it there, what it costs, whether the reader sees it in the terminal, and
    the page's own explanation of it -- with the step's tip and the link to
    its documentation page folded into that last cell, since a table row can
    hold no blocks of its own.
    """
    rows: list[str] = []
    for event in events:
        if not isinstance(event, dict) or event.get("t") is None:
            continue  # a spacer entry between stretches of the timeline
        label = _table_cell(event.get("label"))
        if not label:
            return None
        kind = event.get("kind")
        kind_meta_entry = kind_meta.get(kind) if isinstance(kind, str) else None
        kind_text = ""
        if isinstance(kind_meta_entry, dict):
            kind_text = _table_cell(kind_meta_entry.get("detail"))
        visibility = event.get("vis")
        vis_meta_entry = (
            vis_meta.get(visibility) if isinstance(visibility, str) else None
        )
        visible_text = ""
        if isinstance(vis_meta_entry, dict):
            visible_text = _table_cell(vis_meta_entry.get("label"))
        tokens = event.get("tokens")
        if not isinstance(tokens, int) or tokens == 0:
            # A step inside a subagent's own window counts its cost as
            # ``subTokens``; the main-window count stays zero for it.
            tokens = event.get("subTokens")
        needed = f"{tokens:,}" if isinstance(tokens, int) else ""
        detail = _table_cell(event.get("desc"))
        tip = _table_cell(event.get("tip"))
        if tip:
            detail = f"{detail} *{tip}*" if detail else f"*{tip}*"
        link = _js_text(event.get("link")).strip()
        if link:
            detail = (
                f"{detail} [{_CONTEXT_LINK_LABEL}]({_docs_path(link)})"
                if detail
                else f"[{_CONTEXT_LINK_LABEL}]({_docs_path(link)})"
            )
        rows.append(f"| {label} | {kind_text} | {needed} | {visible_text} | {detail} |")
    if not rows:
        return None
    return "\n".join(
        [
            "## Session timeline",
            "",
            "Each row is one step of a simulated session, in the order it happens. "
            "Token counts are representative, and the context window they fill "
            f"holds {max_tokens:,} tokens.",
            "",
            "| What enters context | Loaded by | Tokens | In your terminal | What it is |",
            "| ------------------- | --------- | ------ | ---------------- | ---------- |",
            *rows,
        ]
    )


def _render_context_window(text: str, spans: list[tuple[int, int]]) -> _DataPage | None:
    """Render the context window page from its timeline data.

    The page's simulation holds each step of a session -- what enters the
    context window, which mechanism put it there, what it costs, whether the
    reader sees it, and why -- in an ``EVENTS`` array, with the label maps
    that name its vocabulary beside it, and those become a table.

    What the data does not hold is the commentary the page prints for each
    stretch of the timeline, which is written into the view's own render code
    as conditional text. That code is kept as a fenced code block beneath the
    table: the page cannot be rendered without it, and dropping it would take
    the commentary with it.
    """
    start, end = spans[0]
    read: dict[str, object] = {}
    cuts: list[tuple[int, int]] = []
    for name in ("MAX", "EVENTS", "VIS_META", "KIND_META"):
        declaration = _js_declaration(text, name)
        if declaration is None or not _js_readable(declaration.value):
            return None
        read[name] = declaration.value
        cuts.append((declaration.start, _js_statement_end(text, declaration.end)))
    max_tokens = read["MAX"]
    events = read["EVENTS"]
    vis_meta = read["VIS_META"]
    kind_meta = read["KIND_META"]
    if (
        not isinstance(max_tokens, int)
        or not isinstance(events, list)
        or not isinstance(vis_meta, dict)
        or not isinstance(kind_meta, dict)
    ):
        return None
    timeline = _render_context_timeline(max_tokens, events, vis_meta, kind_meta)
    if timeline is None:
        return None
    remainder = _excise(text[start:end], [(a - start, b - start) for a, b in cuts])
    return _DataPage(
        definitions=[f"{timeline}\n\n{_fenced_block('jsx', remainder)}"], views={}
    )


def _render_settings_page(text: str, spans: list[tuple[int, int]]) -> _DataPage | None:
    """Render the settings page's two interactive views from their data.

    The precedence stack lists the levels a key can be set at, highest first,
    with the file or flag each one is set by and who it applies to; the scope
    view lists the settings files a scope corresponds to. Both are small
    tables and lists once the diagram around them is gone, and the diagram
    geometry -- tile positions, ring sizes, canvas dimensions -- has nothing
    to say about a settings file.

    Unlike the other data pages, this one mounts its views well below the
    definitions that feed them, so each view's Markdown is put where the view
    itself appears rather than where its data was declared: a reader meets the
    precedence stack in the precedence section, not in the page's opening.
    """
    levels = _js_read_data(text, "LEVELS")
    files = _js_read_data(text, "FILES")
    if not isinstance(levels, list) or not isinstance(files, list):
        return None
    rows: list[str] = []
    for level in levels:
        if not isinstance(level, dict):
            return None
        name = _table_cell(level.get("name"))
        where = _table_cell(level.get("file"))
        who = _table_cell(level.get("who"))
        if not name:
            return None
        rows.append(f"| {level.get('n')}. {name} | {where} | {who} |")
    entries: list[str] = []
    for entry in files:
        if not isinstance(entry, dict):
            return None
        path = _js_text(entry.get("path")).strip()
        if not path:
            return None
        ring = _js_text(entry.get("ring")).strip()
        entries.append(f"* `{path}`" + (f" ({ring})" if ring else ""))
    if not rows or not entries:
        return None
    table = "\n".join(
        [
            "| Level | Where you set it | Who it applies to |",
            "| ----- | ---------------- | ----------------- |",
            *rows,
        ]
    )
    return _DataPage(
        definitions=[""] * len(spans),
        views={
            "SettingsPrecedence": table,
            "SettingsScope": "\n".join(entries),
        },
    )


def _keep_component_source(text: str, spans: list[tuple[int, int]]) -> _DataPage | None:
    """Keep a page's component definitions as source instead of rendering them.

    The page's two definitions are the site's own implementation of a
    promotional card and of its experiment assignment script: styles, an icon,
    a click-tracking bucket, and the card's call to action. None of it is
    documentation, and a mirrored page has no way to run it, but the text the
    card shows is inside it -- so the definitions are kept as fenced code
    blocks rather than dropped. Fenced code is valid CommonMark: a reader
    scrolls past it and an agent reads it as a sample, where un-fenced JSX is
    neither.
    """
    return _DataPage(definitions=[None] * len(spans), views={})


def _convert_data_components(text: str, slug: str) -> tuple[str, dict[str, str]]:
    """Replace the component definitions of a data page with what they document.

    Only the pages listed in ``_DATA_COMPONENT_BUILDERS`` are touched: the
    rest keep the treatment the other passes give them, which leaves a
    component's own text visible rather than rendering from data an adapter
    has no renderer for. A page whose definitions cannot be read is not left
    as it was either -- its definitions become fenced code blocks, so no page
    this pass decides to handle ends up with raw JSX in it.

    Returns the rewritten text and the Markdown to put at each of the page's
    view mount points, which ``_convert_view_components`` applies later, when
    the rest of the document's structure has been converted.
    """
    builder = _DATA_COMPONENT_BUILDERS.get(slug)
    if builder is None:
        return text, {}
    # A definition is only the page's own source when it stands outside the
    # fenced samples. A page whose prose shows an ``export const ...`` sample
    # is showing page content, and one that has already been rendered carries
    # its definitions only inside a fence -- so honouring the fences here is
    # what keeps this pass from rewriting a code sample, and it is also what
    # makes a second run over an already-written page a no-op.
    fenced = list(_iter_fenced_spans(text))
    spans = [
        span
        for span in _component_source_spans(text)
        if not any(start <= span[0] < end for start, end, _ in fenced)
    ]
    if not spans:
        return text, {}
    page = builder(text, spans)
    if page is None or len(page.definitions) != len(spans):
        # A builder answers for every definition it was handed. A page whose
        # builder cannot is rendered as source rather than mis-aligned.
        page = _DataPage(definitions=[None] * len(spans), views={})
    parts: list[str] = []
    cursor = 0
    for (start, end), replacement in zip(spans, page.definitions):
        parts.append(text[cursor:start])
        if replacement is None:
            parts.append(_fenced_block("jsx", text[start:end]))
        else:
            parts.append(replacement)
        cursor = end
    parts.append(text[cursor:])
    return "".join(parts), page.views


def _convert_view_components(text: str, views: dict[str, str]) -> str:
    """Put each rendered view where the page mounts it.

    A page whose data feeds a view that appears further down the document --
    the settings precedence stack, the settings scope diagram -- is rendered
    at the mount point rather than at the definition, which is where a reader
    meets the view. A mount used as a container holds Markdown of its own, so
    only the self-closing form is replaced.
    """
    for name, rendered in views.items():

        def render(component: _Component, rendered: str = rendered) -> str:
            return rendered if component.self_closing else component.raw

        text = _render_components(text, name, render)
    return text


# Pages whose body is a JavaScript component that carries the documentation:
# slug -> the renderer that turns its data back into Markdown.
_DATA_COMPONENT_BUILDERS: dict[
    str, Callable[[str, list[tuple[int, int]]], _DataPage | None]
] = {
    "claude-directory": _render_claude_directory,
    "claude-platform-on-aws": _keep_component_source,
    "context-window": _render_context_window,
    "prompt-library": _render_prompt_library,
    "settings": _render_settings_page,
}


def _collapse_whitespace_lines(text: str) -> str:
    """Replace whitespace-only lines with empty ones and collapse blank runs.

    A JSX tag that occupied a whole line leaves its indentation behind when the
    tag is removed, and a block that was removed leaves a run of blank lines.
    Both are invisible in a rendered document but they end paragraphs and list
    items all the same, and they make the mirrored files noisy to diff.
    """
    text = re.sub(r"^[ \t]+$", "", text, flags=re.MULTILINE)
    return re.sub(r"\n{3,}", "\n\n", text)


def _normalize_page(text: str, slug: str, known_slugs: set[str] | None = None) -> str:
    """Convert one upstream MDX page source to plain Markdown.

    The passes run in this order, on a copy of the document in which every
    fenced code block has been replaced by a placeholder (so no pass can see,
    let alone rewrite, a code sample):

    0. the pages that are mostly a JavaScript component have that component
       replaced by the Markdown its data stands for (see
       ``_convert_data_components``), which is the one pass that runs before
       the code samples are shielded: the Markdown it writes carries samples
       of its own, and those have to be shielded like any other. A page this
       pass does not handle keeps its component source exactly as upstream
       wrote it;
    1. the site's own ``<script>`` tags are removed, and the pages' own MDX
       component definitions are shielded in the same way as the code samples;
    2. the passes that rewrite page structure run around those definitions:
       presentation-only ``<div>``/``<span>``/``<p>`` wrappers are unwrapped,
       ``<video>`` wrappers become links to the media they played, the
       settings filter bar becomes the column help its props carry, and the
       MDX components become the Markdown they stand for -- callouts to GitHub
       Alerts, steps to ordered lists, tabs, cards, accordions and digest
       entries to labelled sections, code groups and frames to their content;
    3. the passes that only remove markup run over the whole document, the
       component definitions included: a styling attribute or an inline
       ``<C>``/``<B>``/``<A>`` component is JSX noise in a Markdown reader
       even where it sits inside the page's own code;
    4. the site-absolute cross-links are resolved against the discovered tree;
    5. runs of blank lines are collapsed and the shielded regions are put back
       at the position they ended up with.

    The unwrap in step 2 has to run before the attribute removal in step 3:
    the attribute is what marks a wrapper as presentation-only, so a pass that
    stripped it first would leave every wrapper looking semantic.

    Constructs that are deliberately NOT converted, because they are already
    valid Markdown or because converting them would delete content, are left
    exactly as upstream wrote them: HTML tables, ``<details>`` collapsibles,
    ``<kbd>`` key caps, ``<sup>``/``<br>`` inline markup, and angle-bracket
    placeholders in prose (``<sessionId>``, ``CLAUDE_PLUGIN_OPTION_<KEY>``).
    """
    if known_slugs is None:
        known_slugs = _KNOWN_SLUGS
    text, views = _convert_data_components(text, slug)
    shielded, code_blocks = _shield_fenced_code(text)
    shielded = _drop_site_scripts(shielded)
    shielded, source_blocks = _shield_component_sources(
        shielded, _component_source_spans(shielded)
    )
    shielded = _unwrap_layout_wrappers(shielded)
    shielded = _convert_media_tags(shielded)
    shielded = _convert_callouts(shielded)
    shielded = _convert_steps(shielded)
    shielded = _convert_tabs(shielded)
    shielded = _convert_cards(shielded, slug, known_slugs)
    shielded = _convert_accordions(shielded)
    shielded = _convert_code_groups(shielded)
    shielded = _convert_frames(shielded)
    shielded = _convert_updates(shielded)
    shielded = _restore_shielded(shielded, source_blocks, "MDX_SOURCE_BLOCK")
    shielded = _strip_presentation_attributes(shielded)
    shielded = _convert_pseudo_tags(shielded, slug, known_slugs)
    shielded = _convert_reference_filter(shielded)
    shielded = _convert_view_components(shielded, views)
    shielded = _drop_widget_components(shielded)
    shielded = _resolve_internal_links(shielded, slug, known_slugs)
    shielded = _collapse_whitespace_lines(shielded).strip()
    return _restore_shielded(shielded, code_blocks, "FENCED_CODE_BLOCK") + "\n"


def fetch_markdown(client: httpx.Client, page: Page) -> tuple[str, str]:
    """Pipeline hook: fetch one page's raw Markdown and return ``(markdown, hash)``.

    This is the optional ``fetch_markdown`` hook described in
    ``sources/base.py``: the pipeline calls it via ``getattr`` instead of
    downloading ``page.source_md_url`` directly, because the upstream files are
    MDX page sources rather than ready-to-read Markdown.

    The raw twin is downloaded, normalised by ``_normalize_page`` (components,
    inline HTML, cross-links), and validated before the content hash is
    computed -- the hash therefore covers the normalized text, which is exactly
    what the manifest and ``core.diff`` compare across runs.

    Any unexpected exception out of the normalisation (an unforeseen markup
    shape, a bug in the passes above) is caught and re-raised as
    ``FetchError``: the pipeline isolates failures PER PAGE only for that
    exception type, so a bare exception escaping this hook would abort the
    whole source's run instead of failing just this page. Chaining with ``from``
    keeps the original exception on ``__cause__`` so a genuine programming
    error stays distinguishable in the traceback.
    """
    # The normalisation resolves the page's site-absolute cross-links, which
    # needs the page set this run discovers; without it every internal link
    # would be rewritten to its upstream URL (see ``ensure_known_slugs``). The
    # guard runs BEFORE the download: a hook invoked without discovery must
    # fail immediately, not fetch every page first and then fail on each one.
    ensure_known_slugs("claude-code", _KNOWN_SLUGS, page.slug)
    raw = fetch.get_with_retry(client, page.source_md_url)
    try:
        markdown = _normalize_page(raw, page.slug)
    except Exception as exc:
        # Deliberate catch-all (then re-raised as FetchError): see the
        # docstring -- only FetchError is isolated per page by the pipeline.
        raise fetch.FetchError(
            f"MDX normalisation failed for {page.slug}: {exc}"
        ) from exc
    if not fetch.validate_markdown(markdown):
        raise fetch.FetchError(f"validation failed for {page.slug} (not Markdown?)")
    return markdown, fetch.content_hash(markdown)
