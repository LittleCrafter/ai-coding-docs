"""Source: Kimi Code.

Kimi Code's documentation is already Markdown in the public GitHub repo
`MoonshotAI/kimi-code` under `docs/en/` (it's a VitePress site). We list that
tree via the GitHub API (one call) and download each `.md` from
`raw.githubusercontent.com`. No whats-new for this source.

This adapter shares its discovery mechanics with ``codex_cli.py``: both list
a GitHub repo's file tree via ``core.github.fetch_git_tree`` (which owns the
rate-limited API call, the rate-limit error mapping, and the truncation
guard) and download raw file content from ``raw.githubusercontent.com``. What
differs is only the per-source configuration and filtering:

* the docs tree is *nested* (e.g. ``docs/en/configuration/config-files.md``),
  so discovery recurses into subfolders instead of keeping only direct
  children, and the slug's first path segment becomes the index group;
* the human-facing ``source_url`` is the published docs site rather than a
  GitHub blob URL, because that is where readers actually consume these docs.

The upstream files are VitePress page sources, not plain CommonMark: some
pages open with a YAML frontmatter block, headings carry ``<Badge />`` Vue
components, callouts are wrapped in ``::: tip`` container markers, and layout
wrappers such as ``<div class="step">`` position content for the Vue theme.
None of those render meaningfully in a plain-Markdown reader, so this adapter
defines the optional ``fetch_markdown`` hook: the raw ``.md`` is downloaded
and normalised to standard Markdown (see ``_normalize_page``) before the
pipeline hashes and writes it.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from typing import TYPE_CHECKING

from ..core import fetch
from ..core.github import fetch_git_tree, fetch_latest_release_tag
from ..core.html_markdown import iter_code_block_spans
from ..core.media import AssetSourceConfig
from ..core.page import Page
from .base import SourceConfig, try_make_page, warn_duplicate_slug

if TYPE_CHECKING:
    # Annotation-only import: ``from __future__ import annotations`` keeps the
    # ``httpx.Client`` annotations from being evaluated at runtime.
    import httpx

# Upstream repository + derived URLs. Kept local to this source rather than
# in the shared config.py, so config.py stays source-agnostic.
REPO = "MoonshotAI/kimi-code"
BRANCH = "main"
DOCS_PREFIX = "docs/en"  # English docs live here in the upstream repo
# raw.githubusercontent.com serves the unprocessed file content -- this is
# what the pipeline actually downloads for each page.
# Using raw.githubusercontent.com for content fetching is a deliberate
# choice to avoid GitHub REST API rate limits. The Git Blob REST API endpoint
# imposes strict rate limits (e.g., 60 requests per hour for unauthenticated
# users). In contrast, raw.githubusercontent.com is largely unmetered for
# fetching static file content, allowing us to download hundreds of markdown
# files rapidly without hitting API caps or requiring authentication tokens.
RAW_BASE = f"https://raw.githubusercontent.com/{REPO}/{BRANCH}"
# Human-facing docs site; mirrored files link here as their "source". The
# repository's own Pages build renders exactly the ``docs/en/`` tree this
# adapter mirrors, one ``.html`` file per Markdown page, so every mirrored
# slug has a counterpart there. The vendor's product site
# (``https://www.kimi.com/code/docs/en/``) was used before and does NOT work
# as a source base: its tree no longer maps one-to-one onto the mirrored
# pages (its ``kimi-code-cli`` landing route answers 403, and what does
# resolve under ``/code/docs/en/`` is a re-organised documentation set rather
# than this tree), which is why the links built from it 404ed.
SOURCE_URL_BASE = "https://moonshotai.github.io/kimi-code/en"
# Extension of the published page files. The site's routes keep the ``.html``
# suffix (no clean-URL rewriting), so the suffix is part of the URL contract
# and lives next to the base as configuration rather than being inlined into
# the URL construction.
SOURCE_URL_SUFFIX = ".html"

# Static-asset rules for the pipeline's media stage. Several docs pages embed
# screenshots via relative refs of the shape ``../../media/<file>`` -- those
# resolve upstream to ``docs/media/`` (a sibling of ``docs/en/``), but in the
# mirror they point nowhere. The media stage downloads each referenced asset
# into ``docs/kimi-code/media/`` (write-only-what-changed, hashed), rewrites
# the in-page refs to resolve from the mirrored page location, and prunes
# assets no page references anymore.
MEDIA = AssetSourceConfig(
    name="kimi-code",
    asset_subdir="media",
    ref_prefixes=("../../media/",),
    raw_base_url=f"{RAW_BASE}/docs/media/",
)

CONFIG = SourceConfig(
    name="kimi-code",
    title="Kimi Code",
    home_url=SOURCE_URL_BASE,
    generate_whats_new=False,
    version="0.42.0",
    origin=f"github.com/{REPO} (`docs/en/`)",
    how_mirrored="scraping (GitHub tree → VitePress `.md` → Markdown)",
)


def get_version(client: httpx.Client) -> str | None:
    """Query the GitHub API for the latest release tag of Kimi Code."""
    return fetch_latest_release_tag(client, repo=REPO)


def _source_url(slug: str) -> str:
    """Return the public docs-site URL of one mirrored slug.

    The site publishes one file per Markdown page at the same relative path
    the mirror uses (``configuration/config-files`` ->
    ``.../en/configuration/config-files.html``), so the mapping is uniform:
    only the base and the file suffix are configuration. An ``index`` slug is
    the directory landing of its folder and therefore resolves to
    ``index.html`` at that same path (the docs root for the top-level page,
    ``<dir>/index.html`` for a nested one), which is exactly what the generic
    construction produces -- no per-slug special-casing is needed.
    """
    return f"{SOURCE_URL_BASE}/{slug}{SOURCE_URL_SUFFIX}"


def discover(client: httpx.Client) -> list[Page]:
    """Discover all English docs pages from the repo's git tree.

    Lists the full tree of ``MoonshotAI/kimi-code@main`` in one API call
    (via ``core.github.fetch_git_tree``, which also enforces the rate-limit
    and truncation safety guards) and keeps every Markdown file anywhere
    under ``docs/en/`` (unlike the Codex adapter, nesting is expected:
    subfolders map to index groups). The slug is the path relative to
    ``docs/en/`` without ``.md`` (e.g. ``"configuration/config-files"``),
    and ``source_id`` is the full repo path -- stable across content edits,
    so it doubles as the pipeline's rename-detection key. The human-facing
    ``source_url`` is the page's published URL on the docs site
    (``_source_url`` builds it from the slug: one ``.html`` file per page at
    the mirrored path, so an ``index`` page becomes that folder's landing
    page). Slugs are deduplicated with a ``seen`` set (first
    entry wins, later duplicates are skipped with a stderr warning) as
    defense in depth against duplicate paths in the git tree listing --
    the same guard the Codex adapter applies.

    Raises ``RuntimeError`` when discovery finds zero pages: an empty result
    would make the pipeline diff "nothing discovered" against the previous
    manifest and delete every mirrored file, so a total filter miss (e.g.
    the upstream moved its docs out of ``docs/en/``) must be a loud error,
    not silent data loss.
    """
    tree = fetch_git_tree(client, repo=REPO, branch=BRANCH)

    pages: list[Page] = []
    # Slugs already claimed by an earlier tree entry, backing the duplicate
    # guard below.  Distinct from ``pages`` membership so the lookup stays
    # O(1) regardless of how many pages have been collected.
    seen: set[str] = set()
    for entry in tree:
        if entry.get("type") != "blob":
            continue  # skip directories ("tree" entries) and submodules
        path = entry.get("path", "")
        if not path.startswith(DOCS_PREFIX + "/") or not path.endswith(".md"):
            continue
        rel = path[len(DOCS_PREFIX) + 1 :]  # e.g. "configuration/config-files.md"
        # Strip the trailing ".md" file extension to derive the slug.
        # ``rel`` is guaranteed to end with ".md" by the combined guard
        # on the line above (``path.startswith(...) and path.endswith(".md")``),
        # so the ``-3`` slice always removes exactly the three extension
        # characters. The resulting slug preserves the upstream directory
        # structure (e.g. "configuration/config-files" from
        # "configuration/config-files.md") so the mirrored tree mirrors
        # the VitePress sidebar grouping one level down.
        slug = rel[:-3]
        # The slug IS the on-disk layout: the pipeline writes each page to
        # ``docs/kimi-code/<slug>.md``, so a nested upstream path like
        # ``docs/en/configuration/config-files.md`` lands at
        # ``docs/kimi-code/configuration/config-files.md`` -- the upstream
        # category directory structure is preserved one level down in the
        # mirror, and readers browsing the mirrored tree see the same
        # grouping the VitePress sidebar shows. The first slug segment
        # doubles as the index group (the section header in docs/README.md),
        # which is why nested categories matter here while the Codex adapter
        # (flat docs folder) can reject them outright.
        # A repo file named exactly ".md" (no basename) at the docs root
        # would yield an empty slug, which Page rejects with a ValueError
        # (caught by try_make_page below, where it would surface as a
        # spurious warning). Such a file carries no usable page identity, so
        # skip it quietly instead.
        if not slug:
            continue
        # Duplicate-slug guard (defense in depth), matching the codex_cli
        # adapter.  Here the slug is derived 1:1 from the repo path and the
        # git-trees API is not expected to list the same blob twice, so a
        # collision "cannot happen" -- but the slug IS the on-disk output
        # path, so if a duplicate ever did slip through (a malformed API
        # response, or a future slug-normalisation step that collapses two
        # distinct paths onto one slug), two ``Page`` objects would fight
        # over a single mirrored file.  Without this guard the duplicate
        # would instead trip the pipeline-level duplicate-slug check and
        # fail the whole source.  Keep the FIRST entry and skip the later
        # one with the shared loud stderr warning (``warn_duplicate_slug``
        # in ``sources/base.py``).
        if slug in seen:
            warn_duplicate_slug(slug, path)
            continue
        seen.add(slug)
        group = slug.split("/", 1)[0] if "/" in slug else "root"
        # The human-facing source URL is the page's published address on the
        # docs site (see ``_source_url`` for the base/suffix contract and for
        # why the vendor's product site is not usable as that base). The SLUG
        # itself is left untouched: it keys the mirrored file layout
        # (``docs/kimi-code/index.md``) and the manifest, where the upstream
        # path shape must stay visible.
        source_url = _source_url(slug)
        # Per-entry guard: a file path whose name falls outside the slug
        # alphabet (parentheses, unicode, spaces, ...) raises ValueError from
        # ``Page.__post_init__``. Without this guard, ONE such entry would
        # crash discovery for the entire Kimi Code source. ``try_make_page``
        # (see ``sources/base.py``) owns the guard/warning: the path is named
        # in a stderr warning and discovery continues with the remaining
        # entries.
        page = try_make_page(
            path,
            slug=slug,
            source_url=source_url,
            source_md_url=f"{RAW_BASE}/{path}",
            source_id=path,  # stable upstream GitHub path -> rename key
            group=group,
        )
        if page is not None:
            pages.append(page)
    pages.sort(key=lambda p: p.slug)
    # Zero-page guard (see the docstring): if every tree entry was filtered
    # out, the upstream almost certainly moved or renamed its docs tree.
    # Raising here -- with the exact filter values in the message -- beats
    # letting the pipeline delete the whole mirrored tree.
    if not pages:
        raise RuntimeError(
            f"No Markdown files found under {DOCS_PREFIX!r}/ in "
            f"{REPO}@{BRANCH}. A zero-page discovery would delete all "
            "mirrored files. If the upstream moved its docs tree, update "
            "DOCS_PREFIX in this source module."
        )
    return pages


# ---------------------------------------------------------------------------
# VitePress normalisation: frontmatter, components and container markers
# ---------------------------------------------------------------------------
# The upstream pages are VitePress sources rather than plain CommonMark, so
# each VitePress-specific construct below is converted to the standard
# Markdown a reader (human or LLM) expects. Every conversion is deliberately
# conservative: a construct the adapter cannot translate with certainty is
# left exactly as upstream wrote it, so an unmapped artifact stays visible in
# the mirror instead of the page silently losing text. No pass ever rewrites a
# fenced code block -- a code sample that happens to contain ``:::` or
# ``<div class="...">`` is code, not page structure -- which the shared
# ``iter_code_block_spans`` scanner and the ``_FenceSpans`` guard enforce.
# Inline code spans get no such protection: upstream writes these constructs
# as block markup only, so the conversions below never meet one inside
# backticks, and guarding that case would mean a second inline scanner for a
# shape the mirrored pages do not contain.

# YAML frontmatter block: an opening ``---`` fence, the block body (captured),
# and a closing fence, anchored at the very first character of the document.
# The anchor is exact on purpose: tolerating leading whitespace made the
# pattern recognise a document that merely STARTS WITH A HORIZONTAL RULE as
# frontmatter, and the body between that rule and the next one -- ordinary
# page prose -- was then deleted along with it, silently (the result still
# validated as Markdown, so nothing downstream noticed the loss). The body is
# matched non-greedily so the block ends at its own closing fence rather than
# at a horizontal rule further down the page, and two block shapes are
# accepted: a body, and the empty block (``---`` immediately followed by its
# closing fence). This mirrors the frontmatter recognition ``core.fetch``
# applies when it extracts a documentation title; it is repeated here because
# this adapter needs the parsed FIELDS (title, description, ``hero`` block),
# not only the title.
_FRONTMATTER_RE = re.compile(
    r"\A---[ \t]*\r?\n"
    r"(?:---[ \t]*(?:\r?\n|\Z)|(?P<body>.*?)\r?\n---[ \t]*(?:\r?\n|\Z))",
    re.DOTALL,
)
# A YAML mapping entry -- ``key:`` with optional leading indentation, optional
# ``- `` list-item markers in front of it (VitePress writes list items as
# ``- key: value``), and an optional value. Only used to tell a real
# frontmatter body from page prose sitting between two horizontal rules: a
# block that carries no such entry is not metadata, so treating it as
# frontmatter would delete the prose. A body whose every line is a comment
# therefore does not qualify either; leaving its ``---`` lines in the mirrored
# page is the conservative outcome, since nothing is lost by not recognising
# metadata that carries no fields.
_FRONTMATTER_KEY_RE = re.compile(
    r"^[ \t]*(?:-[ \t]+)*[A-Za-z_][A-Za-z0-9_.-]*[ \t]*:", re.MULTILINE
)

# The attribute region of one component tag, shared by the ``<Badge>`` and the
# layout-wrapper patterns below. It is a sequence of runs, each one either a
# double-quoted value, a single-quoted value, or a bare stretch of characters
# that cannot end a tag (the lone ``/`` alternative covers a slash used as an
# attribute value character). Matching quoted values as WHOLE runs is what lets
# an attribute value contain a ``>`` (``text="a > b"``, a style with a
# comparison in it) without the tag being cut short at the first ``>``;
# ``/(?!>)`` leaves a slash that opens a self-closing ``/>`` to the tag's own
# tail instead of consuming it here.
#
# BACKTRACKING HAZARD (why the runs are bounded and the repetition possessive):
# the obvious way to write "any attributes" is ``[^>]*``, which crosses line
# breaks and has no upper bound, so at EVERY ``<Badge``/``<div`` occurrence the
# engine consumed the rest of the document looking for the closing ``>``,
# failed, and retried from the next occurrence -- quadratic in document length,
# and a single adversarial page could stall the mirror for minutes (measured on
# that form: 96 KB of ``"<Badge"`` took about 7 s). Three bounds remove the
# hazard: no run may cross a line break (``[^"\n]``/``[^'\n]``/``[^>"'\n]``
# everywhere, so a tag can never span two lines, let alone reach into a fenced
# code block), one run spans at most ``_TAG_RUN_LIMIT`` characters, and one tag
# holds at most ``_TAG_RUN_COUNT`` runs. The ``{0,N}+`` possessive quantifier
# then commits to the runs it consumed, so a failed attempt costs a small
# constant instead of backtracking through them. A tag whose attribute region
# exceeds either bound is simply left as upstream wrote it -- visible in the
# mirror instead of silently rewritten -- which is the same conservative
# outcome as every other construct this adapter does not recognize.
_TAG_RUN_LIMIT = 80
_TAG_RUN_COUNT = 8
_TAG_RUNS = (
    rf"(?:\"[^\"\n]{{0,{_TAG_RUN_LIMIT}}}\"|'[^'\n]{{0,{_TAG_RUN_LIMIT}}}'"
    rf"|[^>\"'\n/]{{0,{_TAG_RUN_LIMIT}}}|/(?!>))"
    rf"{{0,{_TAG_RUN_COUNT}}}+"
)

# ``<Badge type="tip" text="v3.4.0" />``: a Vue component that renders a small
# version/status pill next to a heading. Its information is the ``text``
# attribute or, in the paired form, the text shown between the tags, so the
# component is replaced by that text (``### Kimi Datasource <Badge type="tip"
# text="v3.4.0" />`` -> ``### Kimi Datasource v3.4.0``); ``_replace_badge``
# decides between the two. Both the self-closing and the paired form are
# matched, and the ``inner`` group carries the paired form's display text. The
# ``ws`` group captures the whitespace in front of the tag: it is re-emitted
# with the text so the annotated heading keeps its spacing, and dropped
# together with a badge that has no text at all (leaving a heading like
# ``### X <Badge type="info" />`` without a dangling space).
_BADGE_RE = re.compile(
    rf"(?P<ws>[ \t]*)(?P<tag><Badge\b{_TAG_RUNS}"
    rf"(?:/>|>(?P<inner>[^\n]{{0,{_TAG_RUN_LIMIT}}}?)</Badge>))"
)
# The ``text`` attribute of a badge. The quote pair is matched through a
# backreference (``\1``) so a value containing the other quote kind -- e.g.
# ``text="A 'B' C"`` -- is captured whole instead of being truncated at the
# first inner quote. The attribute name must stand on its own: ``\b`` alone
# also fires after a hyphen, which made ``data-text="wrong"`` read as the
# badge's own ``text`` and print that wrong value into the heading, so the
# lookbehind rejects any name character or hyphen in front of it. The value
# itself cannot cross a line, because the tag it is searched in cannot.
_BADGE_TEXT_RE = re.compile(r"(?<![-\w])text[ \t]*=[ \t]*([\"'])(.*?)\1")

# Presentation-only layout wrappers: ``<div class="step">``, ``<span
# class="step-num">``, ``<div style="max-width: 380px">``. These exist to
# position content inside the Vue theme and carry no meaning a Markdown reader
# can act on, so their tags are dropped and the inner content is kept. Only
# tags carrying a ``class`` or ``style`` attribute qualify as presentational:
# a bare ``<div>`` (a semantic container or anchor target) is preserved
# together with its closing tag. HTML elements with real meaning in Markdown
# output -- ``<kbd>`` key caps, ``<details>``/``<summary>`` collapsibles,
# ``<table>`` rows, ``<strong>`` emphasis -- are not touched at all. The
# attribute region is matched with the bounded runs described above (see
# ``_TAG_RUNS`` for the quadratic-blowup hazard this closes).
_LAYOUT_TAG_RE = re.compile(rf"</?(?:div|span)\b{_TAG_RUNS}>")
_PRESENTATIONAL_ATTR_RE = re.compile(r"\b(?:class|style)\s*=")

# VitePress container markers. The opening marker names a single-word
# container type (``tip``, ``warning``, ``code-group``, ``details``, ...)
# optionally followed by the container's title on the same line; the closing
# marker is a bare ``:::`` line. Both are matched with optional leading
# indentation because upstream nests callouts inside numbered list steps. A
# marker with no type is NOT an opening marker (only a closing one), which is
# what keeps a stray closer from swallowing the text that follows it, and a
# longer fence (``::::``) does not match at all -- such a marker is left as
# written rather than guessed at.
_CONTAINER_OPEN_RE = re.compile(
    r"^(?P<indent>[ \t]*):::[ \t]*(?P<type>[A-Za-z][A-Za-z-]*)[ \t]*"
    r"(?P<title>.*?)[ \t]*$",
    re.MULTILINE,
)
_CONTAINER_CLOSE_RE = re.compile(r"^[ \t]*:::[ \t]*$", re.MULTILINE)

# Container type -> GitHub Alert label. GitHub renders exactly five alert
# labels (NOTE, TIP, IMPORTANT, WARNING, CAUTION), so VitePress's ``info``
# maps to NOTE and its ``danger`` to CAUTION -- the closest supported
# equivalents, which keeps the severity the author intended. ``details`` and
# ``code-group`` have no alert equivalent and are unwrapped as plain content
# (see ``_render_container``).
_ALERT_LABELS = {
    "note": "NOTE",
    "tip": "TIP",
    "important": "IMPORTANT",
    "info": "NOTE",
    "warning": "WARNING",
    "caution": "CAUTION",
    "danger": "CAUTION",
}


class _FenceSpans:
    """The fenced code blocks of one document, queried through a moving cursor.

    The spans come from ``core.html_markdown.iter_code_block_spans``, the
    shared CommonMark fence scanner, and are the guard that keeps every
    conversion in this module away from code samples. A query only ever has to
    look at the current span: every caller here walks its document strictly
    left to right (a ``finditer``/``sub`` callback, or a marker scan that
    resumes after each match), so the spans that end before a queried position
    are retired once and never revisited -- the whole walk costs O(spans)
    instead of re-scanning the span list from the start at every query.
    Queries must therefore be made in non-decreasing position order, which
    ``overlaps`` respects by asking for its start before its end.
    """

    __slots__ = ("_spans", "_index")

    def __init__(self, text: str) -> None:
        """Scan *text* once for its fenced code blocks."""
        self._spans = list(iter_code_block_spans(text))
        self._index = 0

    def contains(self, position: int) -> bool:
        """Return True when *position* falls inside one of the code spans."""
        spans = self._spans
        while self._index < len(spans) and spans[self._index][1] <= position:
            self._index += 1  # span ends at or before the query: it is past
        return self._index < len(spans) and spans[self._index][0] <= position

    def overlaps(self, start: int, end: int) -> bool:
        """Return True when the ``[start, end)`` range touches a code span.

        Both boundaries are tested rather than only *start*: a match that
        begins before a fence and reaches into it would otherwise consume
        fence text while being treated as page structure. The patterns in this
        module cannot currently produce such a match -- none of them can cross
        a line break, and a fence occupies whole lines -- so this is a second
        line of defence rather than a behaviour the tests rely on.
        """
        return self.contains(start) or self.contains(end - 1)


def _unquote(value: str) -> str:
    """Return a YAML scalar without the surrounding quotes authors add to it."""
    return value.strip().strip("\"'")


def _indent_width(line: str) -> int:
    """Return the leading-whitespace width of *line*, counting tabs as one."""
    return len(line) - len(line.lstrip(" \t"))


def _split_frontmatter(text: str) -> tuple[dict[str, str], str]:
    """Split a leading VitePress frontmatter block off *text*.

    Returns the parsed fields (an empty mapping when the page has no
    frontmatter) and the page body with the block removed. Only the YAML
    subset the upstream pages use is parsed: top-level ``key: value`` scalars
    plus one nesting level, flattened to dotted keys (``hero.name``) because
    the VitePress home layout nests the landing page's display name and
    tagline under ``hero:``. List items and deeper nesting (the ``head:``
    meta refresh list, the hero's ``actions:``) are ignored on purpose:
    nothing this adapter renders needs them, and interpreting them would mean
    re-implementing a YAML parser for metadata that is about to be discarded.
    Field keys are folded to lower case, so a page writing ``Title:`` or
    ``Hero:`` is read exactly like one writing ``title:``/``hero:`` -- real
    frontmatter uses both, and the canonical values would otherwise be
    silently missed. A block that carries no ``key:`` line is not frontmatter
    at all (see ``_FRONTMATTER_KEY_RE``): the text is returned as it is, block
    and all, so nothing in the page is lost to the decision.
    """
    # Strip a leading BOM (U+FEFF) before matching: Python's ``\s`` does not
    # match U+FEFF, so a BOM-prefixed page would otherwise miss the
    # start-of-document anchor, keep its frontmatter in the mirrored page, and
    # lose the frontmatter title with it. ``core.fetch`` strips the same
    # character for the same reason before its own frontmatter and heading
    # patterns run -- this adapter must agree with it, since a page whose title
    # is extracted downstream from a block that was never recognized here would
    # be titled by its file name.
    text = text.lstrip("\ufeff")
    block = _FRONTMATTER_RE.match(text)
    if block is None:
        return {}, text
    body = block.group("body") or ""  # None for the empty ``---\n---`` form
    if body.strip() and not _FRONTMATTER_KEY_RE.search(body):
        # Content with no ``key:`` line anywhere in it is page text between two
        # horizontal rules, not metadata: treating it as frontmatter would
        # delete that text from the mirrored page without a trace.
        return {}, text
    fields: dict[str, str] = {}
    # Top-level key whose indented children are being read ("" when the last
    # top-level entry was a scalar), and the indentation width of those direct
    # children once the first one has been seen.
    parent = ""
    child_indent = -1
    for line in body.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue  # blank line or YAML comment
        key, separator, value = stripped.partition(":")
        if not separator:
            continue  # not a ``key: value`` line (e.g. a list-item sequence)
        key, value = key.strip().lower(), _unquote(value)
        indent = _indent_width(line)
        if indent == 0:
            parent, child_indent = "", -1
            if value:
                fields[key] = value
            else:
                parent = key  # a nested map follows
            continue
        if not parent:
            continue  # an indented line before any top-level key
        if child_indent < 0 or indent < child_indent:
            # The direct-child level is the shallowest indentation among the
            # parent's indented lines, re-anchored downwards whenever a
            # shallower one turns up. It cannot be fixed by the first indented
            # line that carries a SCALAR: a nested map may open with a list (the
            # landing page's ``hero:`` can list its ``actions:`` first, with
            # ``name:``/``text:`` after them), and a level taken from the list's
            # own items then hides every direct child. An indented LIST ITEM
            # still belongs to the parent's direct-child level, which is why the
            # re-anchoring below happens before the list-item check.
            child_indent = indent
        if indent != child_indent or not value or key.startswith("-"):
            continue  # a list item, or a nested map with no scalar
        fields[f"{parent}.{key}"] = value
    return fields, text[block.end() :]


def _replace_badge(match: re.Match[str]) -> str:
    """Return the display text of one ``<Badge>`` match (or "" when none).

    The ``text`` attribute wins when the tag carries one, because that is what
    the Vue component renders in the heading it annotates; a paired badge
    without that attribute shows its inner text (``<Badge type="tip">v9</Badge>``
    displays ``v9``). A badge with neither shows nothing, so the tag and the
    whitespace in front of it are dropped together, leaving no dangling space.
    """
    text = _BADGE_TEXT_RE.search(match.group("tag"))
    value = _unquote(text.group(2)).strip() if text else ""
    if not value:
        value = (match.group("inner") or "").strip()
    return f"{match.group('ws')}{value}" if value else ""


def _sub_outside_fences(
    text: str, pattern: re.Pattern[str], replace: Callable[[re.Match[str]], str]
) -> str:
    """Apply *replace* to every *pattern* match that is not inside a fence.

    Matches inside fenced code blocks are re-emitted verbatim, so a code
    sample that happens to contain the matched construct keeps its exact text.
    """
    spans = _FenceSpans(text)

    def _guarded(match: re.Match[str]) -> str:
        if spans.overlaps(match.start(), match.end()):
            return match.group(0)
        return replace(match)

    return pattern.sub(_guarded, text)


def _unwrap_layout_wrappers(text: str) -> str:
    """Drop presentation-only ``<div>``/``<span>`` wrappers, keeping content.

    A tag is dropped when it is a CLOSING tag whose opening tag was dropped,
    or an OPENING tag that carries a ``class`` or ``style`` attribute. An
    opening tag without either attribute is re-emitted verbatim and its
    closing tag is kept with it, so the two always stay balanced -- a wrapper
    the adapter does not recognize never leaves unbalanced markup behind.
    Nesting is tracked with a stack for the same reason. Tags inside fenced
    code blocks are code text: they are re-emitted verbatim and do not take
    part in the nesting bookkeeping.
    """
    spans = _FenceSpans(text)
    out: list[str] = []
    dropped: list[bool] = []  # stack: was each currently open element dropped?
    position = 0
    for match in _LAYOUT_TAG_RE.finditer(text):
        out.append(text[position : match.start()])
        position = match.end()
        tag = match.group(0)
        if spans.overlaps(match.start(), match.end()):
            out.append(tag)
        elif tag.startswith("</"):
            out.append("" if dropped and dropped.pop() else tag)
        else:
            presentational = _PRESENTATIONAL_ATTR_RE.search(tag) is not None
            dropped.append(presentational)
            if not presentational:
                out.append(tag)
    out.append(text[position:])
    return "".join(out)


def _dedent(body: str) -> list[str]:
    """Return *body*'s lines with their common leading indentation removed.

    Tabs are expanded first so a body mixing tabs and spaces is measured on a
    single column basis (one tab is several columns wide, not one character).
    Blank lines are excluded from the minimum because they carry no meaningful
    indentation, and only the COMMON prefix is removed, so content indented
    deeper than its siblings -- a nested list, an indented code sample -- keeps
    its internal structure.
    """
    lines = [line.expandtabs() for line in body.split("\n")]
    indent = min(
        (len(line) - len(line.lstrip()) for line in lines if line.strip()),
        default=0,
    )
    return [line[indent:] if line.strip() else "" for line in lines]


def _render_container(opener: re.Match[str], body: str) -> str:
    """Render one closed ``:::`` container as standard Markdown.

    A container whose type maps to a GitHub Alert label (``_ALERT_LABELS``)
    becomes a blockquote alert: its optional title is rendered bold on the
    line after the label, and every body line is prefixed with ``> `` (blank
    lines become a bare ``>``, preserving the paragraph breaks inside the
    block). The body is dedented first and the container's own indentation is
    re-applied to every produced line, so a callout nested inside a list step
    stays part of that step. A container with an empty body produces just the
    label line (plus its title): the separator that normally introduces the
    body would otherwise be left dangling.

    Every other container -- ``details`` (VitePress's collapsible block),
    ``code-group`` (a tab group over code samples), and any type this adapter
    does not know -- is unwrapped as plain content: the markers disappear, the
    optional title survives as its own paragraph, and the body is kept exactly
    as written.
    """
    indent = opener.group("indent")
    title = _unquote(opener.group("title")).strip()
    body = body.strip("\n")
    label = _ALERT_LABELS.get(opener.group("type").lower())
    if label is None:
        parts = [f"{indent}{title}"] if title else []
        if body:
            parts.append(body)
        return "\n\n".join(parts)
    lines = [f"{indent}> [!{label}]"]
    if title:
        lines.append(f"{indent}> **{title}**")
    if body:
        if title:
            lines.append(f"{indent}>")
        for line in _dedent(body):
            lines.append(f"{indent}> {line}" if line.strip() else f"{indent}>")
    return "\n".join(lines)


def _next_marker(
    pattern: re.Pattern[str],
    text: str,
    start: int,
    spans: _FenceSpans,
) -> re.Match[str] | None:
    """Return the next *pattern* match at or after *start* that is not code.

    Container markers are searched with this helper rather than with a plain
    ``pattern.search``: a marker-shaped line inside a fenced code block (a
    page documenting the container syntax, for instance) must be skipped
    instead of closing a container early. Each retry resumes where the skipped
    candidate ended, so the scan stays linear in the document length.
    """
    position = start
    while True:
        match = pattern.search(text, position)
        if match is None or not spans.overlaps(match.start(), match.end()):
            return match
        position = match.end()


def _convert_containers(text: str) -> str:
    """Convert every closed VitePress ``:::`` container in *text*.

    Containers are rewritten with a linear opener/closer scan (the shape
    ``opencode._convert_jsx_callouts`` uses for JSX callouts): find the next
    opening marker, find the first closing marker after it, rewrite the block
    between them, and resume after the closer. An opening marker with no
    closer anywhere after it leaves the rest of the document untouched -- an
    unterminated container is uncertain structure, and swallowing the rest of
    the page into it would be far worse than leaving its markers visible.
    """
    spans = _FenceSpans(text)
    out: list[str] = []
    position = 0
    while True:
        opener = _next_marker(_CONTAINER_OPEN_RE, text, position, spans)
        if opener is None:
            break
        closer = _next_marker(_CONTAINER_CLOSE_RE, text, opener.end(), spans)
        if closer is None:
            break
        out.append(text[position : opener.start()])
        out.append(_render_container(opener, text[opener.end() : closer.start()]))
        position = closer.end()
    out.append(text[position:])
    return "".join(out)


def _page_heading(fields: dict[str, str], body: str) -> str:
    """Return the leading ``# <title>`` block a page needs, or "".

    The title comes from the frontmatter ``title`` when it has one and from
    the VitePress ``hero.name`` otherwise (the home layout spells the product
    name there instead of using ``title``). The heading is emitted only when
    the body carries no heading of its own: a page that has one already is
    titled by it -- both upstream and the pipeline's own
    ``fetch.extract_title`` read that heading -- and re-emitting the
    frontmatter title would duplicate it. Pages with no heading of their own
    are exactly the pure-frontmatter ones, the landing page above all: without
    this heading such a page would reach the mirror as an empty file whose
    manifest title is its file name. The frontmatter description (or the
    hero's tagline, the equivalent field on the landing page) is carried along
    so the page still says what the source says it says. Field keys arrive
    lower-cased from ``_split_frontmatter``, so the lookups below match a page
    that spells them ``Title:``/``Hero:`` as well.
    """
    title = fields.get("title") or fields.get("hero.name") or ""
    if not title or fetch.extract_title(body, fallback=""):
        return ""
    description = fields.get("description") or fields.get("hero.text") or ""
    return "\n\n".join(part for part in (f"# {title}", description) if part)


def _normalize_page(text: str) -> str:
    """Convert one upstream VitePress page source to plain Markdown.

    The passes run in this order (each one re-derives the fenced-code spans of
    the text it receives, since the previous pass may have resized the
    document):

    1. the YAML frontmatter block is split off -- a reader of the mirror wants
       the page, not its build metadata;
    2. ``<Badge />`` components are replaced by the version/status text they
       display, and presentation-only ``<div>``/``<span>`` wrappers are
       unwrapped while their content is preserved;
    3. ``:::`` containers become GitHub Alerts (typed callouts) or plain
       content (``details``, ``code-group``, unknown types);
    4. the frontmatter's title becomes a ``# <title>`` heading when the page
       has no heading of its own.

    Constructs that are deliberately NOT converted, because they are already
    valid Markdown or because converting them would destroy meaning, are left
    exactly as upstream wrote them: ``<kbd>`` key caps,
    ``<details>``/``<summary>`` collapsibles, HTML tables, ``<strong>``
    emphasis, and prose placeholders that merely look like tags
    (``<sessionId>``, ``KIMI_CODE_EXPERIMENTAL_<NAME>``). A generic
    "strip every tag" pass would delete content in the last group, which is
    why each conversion above targets one known construct instead.
    """
    fields, body = _split_frontmatter(text)
    body = _sub_outside_fences(body, _BADGE_RE, _replace_badge)
    body = _unwrap_layout_wrappers(body)
    body = _convert_containers(body)
    heading = _page_heading(fields, body)
    body = body.strip()
    parts = [part for part in (heading, body) if part]
    return "\n\n".join(parts) + "\n"


def fetch_markdown(client: httpx.Client, page: Page) -> tuple[str, str]:
    """Pipeline hook: fetch one page's raw Markdown and return ``(markdown, hash)``.

    This is the optional ``fetch_markdown`` hook described in
    ``sources/base.py``: the pipeline calls it via ``getattr`` instead of
    downloading ``page.source_md_url`` directly, because the upstream files
    are VitePress page sources rather than ready-to-read Markdown.

    The raw file is downloaded from ``raw.githubusercontent.com``, normalised
    by ``_normalize_page`` (frontmatter, Vue components, container markers,
    layout wrappers), and validated before the content hash is computed -- the
    hash therefore covers the normalized text, which is exactly what the
    manifest and ``core.diff`` compare across runs.

    Any unexpected exception out of the normalisation (an unforeseen markup
    shape, a bug in the passes above) is caught and re-raised as
    ``FetchError``: the pipeline isolates failures PER PAGE only for that
    exception type, so a bare exception escaping this hook would abort the
    whole source's run instead of failing just this page. Chaining with
    ``from`` keeps the original exception on ``__cause__`` so a genuine
    programming error stays distinguishable in the traceback.
    """
    raw = fetch.get_with_retry(client, page.source_md_url)
    try:
        markdown = _normalize_page(raw)
    except Exception as exc:
        # Deliberate catch-all (then re-raised as FetchError): see the
        # docstring -- only FetchError is isolated per page by the pipeline.
        raise fetch.FetchError(
            f"VitePress normalisation failed for {page.slug}: {exc}"
        ) from exc
    if not fetch.validate_markdown(markdown):
        raise fetch.FetchError(f"validation failed for {page.slug} (not Markdown?)")
    return markdown, fetch.content_hash(markdown)
