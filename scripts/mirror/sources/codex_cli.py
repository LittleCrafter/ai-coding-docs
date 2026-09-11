"""Source: Codex CLI.

The official Codex CLI documentation lives as Markdown in the open-source repo
`openai/codex` under `docs/` (getting-started, install, config, sandbox,
slash_commands, agents_md, authentication, ...). The folder contains both
CLI guides and repo meta/legal Markdown (the Contributor License Agreement,
the license text, contributing guide, and open-source-fund pages). We mirror
those too, deliberately: they are part of the upstream `docs/` tree, version
together with the CLI docs they govern, and dropping them would require extra
filter rules whose only effect would be to hide accurate upstream content.
We list that directory via the GitHub API and download each `.md` from
raw.githubusercontent.com.

In addition to GitHub repository files, documentation pages listed in the
upstream `codex/llms.txt` index (on developers.openai.com / learn.chatgpt.com)
are discovered to mirror comprehensive guides and reference documentation.

For pages that upstream provides as reference stubs pointing to
`developers.openai.com` or `learn.chatgpt.com`, this adapter resolves them to
their rich `.md` twins (e.g. `https://developers.openai.com/codex/guides/agents-md.md`),
normalizing known route differences and stripping URL anchors. Hybrid pages
such as `config.md` are assembled into composite documents incorporating the
referenced sub-guides alongside local sections. If any external twin fetch
fails, the adapter logs a warning and falls back gracefully to the original
GitHub text.

Cross-documentation links pointing to known documentation slugs are rewritten
into local relative Markdown links during fetching.

How discovery works:

* Step 1: The GitHub "git trees" API returns the repo's entire file tree in a single
  call (``?recursive=1``) as a flat list of entries; each file is a
  ``{"type": "blob", "path": ...}`` object. One API call replaces what would
  otherwise be a crawl of directory listings. We keep only Markdown files that
  are direct children of ``docs/``.
* Step 2: The upstream documentation index at ``codex/llms.txt``
  (``https://developers.openai.com/codex/llms.txt``) is fetched. Bullet links to
  ``learn.chatgpt.com`` and ``developers.openai.com`` are parsed, filtering for
  ``.md`` targets, and converted to ``Page`` objects with hierarchical slugs and groups.
  If the index fetch fails, a warning is logged to stderr and discovery proceeds with
  GitHub pages.
* First discovery wins during deduplication using a ``seen`` set. Duplicate slugs
  trigger a stderr warning.
* Discovery enforces a zero-page guard raising ``RuntimeError`` if no pages are found.

This source generates no structural whats-new digest: upstream already
publishes a maintained ``whats-new`` page, which is mirrored like any other
page, so a second generated changelog would only restate it.
"""

from __future__ import annotations

import json
import posixpath
import re
import sys
import textwrap
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from typing import TYPE_CHECKING
from urllib.parse import urlparse

from ..core import fetch
from ..core.fenced_code import protect_fenced_code, restore_fenced_code
from ..core.github import fetch_git_tree, fetch_latest_release_tag
from ..core.page import Page
from .base import (
    SourceConfig,
    ensure_known_slugs,
    try_make_page,
    warn_duplicate_slug,
)

if TYPE_CHECKING:
    # Annotation-only import: ``from __future__ import annotations`` keeps the
    # ``httpx.Client`` annotations from being evaluated at runtime.
    import httpx

REPO = "openai/codex"
BRANCH = "main"
DOCS_PREFIX = "docs"  # CLI docs live directly under docs/
# raw.githubusercontent.com serves the unprocessed file content -- this is
# what the pipeline actually downloads for each page.
RAW_BASE = f"https://raw.githubusercontent.com/{REPO}/{BRANCH}"
# Human-facing page URL (used for the "source" link in the mirrored files),
# as opposed to RAW_BASE which is the machine-facing download URL.
BLOB_BASE = f"https://github.com/{REPO}/blob/{BRANCH}"

LLMS_TXT_URL = "https://developers.openai.com/codex/llms.txt"

# Route the documentation host serves its use-case collections under (the
# `<CodexCollectionList>` component lists them by identifier).
COLLECTIONS_BASE_URL = "https://learn.chatgpt.com/use-cases/collections"

# The mirrored corpus has two origins, and they carry different licensing:
#
# * the docs index (``codex/llms.txt``) lists the rich guides and reference
#   pages, which are served by learn.chatgpt.com and make up the vast majority
#   of the mirror;
# * the repository tree contributes the versioned ``docs/`` Markdown files
#   (the Contributor License Agreement, the license text, the contributing
#   guide, ...), which are covered by the Apache-2.0 LICENSE and NOTICE kept
#   alongside this content.
CONFIG = SourceConfig(
    name="codex-cli",
    title="Codex CLI",
    home_url=f"https://github.com/{REPO}",
    generate_whats_new=False,
    version="0.154.0",
    origin=f"learn.chatgpt.com (`/docs/`) + github.com/{REPO} (`docs/`)",
    how_mirrored=(
        "scraping (learn.chatgpt.com pages listed in the codex/llms.txt index "
        f"+ the {REPO} git tree)"
    ),
)

# Known route discrepancies between upstream GitHub stub links and OpenAI doc twins.
# For example, docs/execpolicy.md references codex/execpolicy (or execpolicy), which 404s
# unless normalized to codex/exec-policy on developers.openai.com.
ROUTE_REWRITES: dict[str, str] = {
    "codex/execpolicy": "codex/exec-policy",
    "execpolicy": "exec-policy",
}

# Regex to detect markdown links pointing to developers.openai.com or learn.chatgpt.com.
_STUB_MD_LINK_RE = re.compile(
    r"\[([^\]]*)\]\((https?://(?:developers\.openai\.com|learn\.chatgpt\.com)/[^\s)]+)\)"
)

# Regex to match markdown bullet links in llms.txt index.
_LLMS_BULLET_RE = re.compile(r"^-\s+\[([^\]]+)\]\((https?://[^\s)]+)\)", re.MULTILINE)

# Regex to match cross-doc markdown links to learn.chatgpt.com or developers.openai.com.
#
# BACKTRACKING HAZARD (why this is only applied through `_iter_link_matches`,
# never via `re.sub`): the greedy `[^\s)#]+` destination class expands to
# end-of-string from every candidate, fails to find its `)`, and the engine
# then retries the whole scan from the next candidate -- one full scan of the
# remaining document per candidate, the classic 4x-per-2x quadratic signature
# (measured on `"[a](https://learn.chatgpt.com/docs/"` repeated: 3.3/13.2/53.2
# s for 2/4/8 thousand copies). The pass runs on raw Markdown fetched from the
# network, so this is a remotely-triggerable hang. `_iter_link_matches` keeps
# this pattern for the actual matching (so group semantics are untouched) but
# drives it with a linear `str.find` scan -- see that function for the
# monotonicity argument.
_CROSS_DOC_LINK_RE = re.compile(
    r"\[([^\]]*)\]\((https?://(?:learn\.chatgpt\.com|developers\.openai\.com)/(?:docs|guides)/([^\s)#]+)(#[^\s)]*)?)\)"
)

# Banner at top of OpenAI docs linking to llms.txt index, stripped from sub-sections
# in hybrid pages to avoid repetitive clutter.
_INDEX_BANNER_RE = re.compile(
    r"^>\s*For the complete documentation index, see\s*\[llms\.txt\].*?\n+",
    re.MULTILINE,
)

_ROOT_LINK_RE = re.compile(r"\]\(\.\./(SECURITY\.md|LICENSE)(#[^)]*)?\)")

# Opening line of a fenced code block: a line that starts with three or more
# backticks or tildes, followed by an optional info string. Group 1 is the
# fence run itself, whose character and length decide which line closes the
# block. Indentation is not restricted: a fence inside a list item is indented
# by the list, and shielding it is what keeps the example out of the component
# converters.
_FENCE_OPENER_RE = re.compile(r"(?m)^[ \t]*(`{3,}|~{3,})[^\n]*\n")

# One `key:` line, the smallest evidence that a `---` block delimited by two
# rules is frontmatter rather than a document that opens with a thematic break.
_FRONTMATTER_KEY_RE = re.compile(r"(?m)^[A-Za-z_][\w.-]*[ \t]*:")

# Human-readable names for the product surfaces an MDX section can be scoped
# to. Each name labels the section that only applies to that surface, so a page
# carrying one variant per surface reads as distinct sections instead of
# repeating the same heading.
SURFACE_LABELS: dict[str, str] = {
    "app": "Desktop app",
    "web": "Web",
    "cli": "CLI",
    "ide": "IDE extension",
}

# Container components with no content of their own: they lay out the Markdown
# around them (step sequencing, tab chrome, a horizontally scrollable wrapper),
# so unwrapping them keeps every child block and drops only the layout.
CONTAINER_COMPONENT_NAMES = (
    "WorkflowSteps",
    "Tabs",
    "TabItem",
    "ContentSwitcher",
)

# Components that render decoration or an interactive widget and carry no
# documentation text: badges, live demos, download buttons, and the inline
# icons used inside link labels. They are removed outright, since their props
# hold display configuration only and the surrounding prose says everything a
# reader needs. Nothing here is ever rendered as data, so removal cannot lose
# documented content.
VISUAL_COMPONENT_NAMES = (
    "ElevatedRiskBadge",
    "CodexModelSwitcher",
    "CodexAppDownloadCta",
    "CodexReasoningLevelTerminal",
    "PermissionModeSelectorDemo",
    "CodexPetsDemo",
    "ServiceAccountsDemo",
    "ComputerHistoryThreadDemo",
    "ChatGPTModeDropdown",
    "ChatWorkSegmentPicker",
    "Images",
    "OpenBook",
    "CompareArrows",
    "Plugin",
    "Settings",
    "Desktop",
    "Storage",
    "Terminal",
    "Tools",
    "Chat",
)

# Availability states used by the plan feature matrix, rendered as compact
# table cells. An unknown state falls back to its raw value so a new upstream
# state is visible in the mirror rather than silently blanked.
_AVAILABILITY_LABELS: dict[str, str] = {
    "available": "Yes",
    "unavailable": "No",
    "limited": "Limited",
}

# A line that holds nothing but whitespace, i.e. the residue left behind by an
# unwrapped component that occupied a whole line. The line itself stays in
# place (only its padding is dropped), so no surrounding block boundary moves.
_BLANK_WHITESPACE_LINE_RE = re.compile(r"^[ \t]+$", re.MULTILINE)

# Markdown link whose target is site-absolute (``/codex/...``) rather than a
# full URL; the resolution helper turns it into a relative link or an upstream
# URL.
#
# BACKTRACKING HAZARD (why this is only applied through `_iter_link_matches`,
# never via `re.sub`): the greedy `[^)\s]*` destination class expands to
# end-of-string from every candidate, fails to find its `)`, and the engine
# then retries the whole scan from the next candidate -- one full scan of the
# remaining document per candidate, the classic 4x-per-2x quadratic signature
# (measured: 0.05/0.21/0.84/3.38 s for 1/2/4/8 thousand copies of
# `](/docs`). The pass runs on raw Markdown fetched from the network, so this
# is a remotely-triggerable hang. `_iter_link_matches` keeps this pattern for
# the actual matching (so group semantics are untouched) but drives it with a
# linear `str.find` scan -- see that function for the monotonicity argument.
_SITE_ABSOLUTE_LINK_RE = re.compile(r"\]\((?P<href>/(?!/)[^)\s]*)\)")

# Relative Markdown link with a ``.md`` target, used to repoint references to a
# slug that was skipped in favor of its twin.
#
# Same BACKTRACKING HAZARD as the pattern above -- the destination class
# `[^)\s#]*` scans to end-of-string from every candidate and backtracks one
# character at a time looking for the `.md` its `)` must follow (measured:
# 0.06/0.25/0.98/3.92 s for 1/2/4/8 thousand copies of `](./x.md`) -- so this
# pattern is likewise only ever applied through `_iter_link_matches`.
_RELATIVE_MD_LINK_RE = re.compile(
    r"\]\((?P<href>(?!\w+:)(?!/)(?P<path>[^)\s#]*\.md)(?P<anchor>#[^)\s]*)?)\)"
)

# Repository ``docs/`` files that upstream ships as one-line reference stubs
# pointing at a rich guide, where that guide is *also* published as its own
# page by the documentation index and therefore already mirrored under its own
# slug. Mirroring both would produce two byte-identical files for one document
# and duplicate rows in the generated index, so the stub is skipped and every
# reference to it is redirected to the surviving slug (see `_SLUG_REDIRECTS`).
#
# Keys are the GitHub ``docs/`` slugs (the file name without ``.md``); values
# are the slugs of the mirrored pages that carry the same content. The mapping
# is applied only while the twin really is part of this run's discovery, so a
# renamed or missing twin degrades to mirroring the stub as before instead of
# dropping the document.
STUB_TWIN_SLUGS: dict[str, str] = {
    "authentication": "auth",
    "sandbox": "security",
    "exec": "non-interactive-mode",
    "skills": "build-skills",
}

# Maintained and populated during discover() to record all known slugs for cross-link rewriting.
_KNOWN_SLUGS: set[str] = set()

# Maintained and populated during discover(): maps a skipped stub slug onto the
# mirrored slug that replaced it, so link rewriting can point references at the
# file that exists. Empty whenever no stub was skipped in this run.
_SLUG_REDIRECTS: dict[str, str] = {}


def normalize_route(url: str) -> str:
    """Normalize route discrepancies between GitHub docs and OpenAI doc twins.

    Strips any `#anchor` fragment and trailing slashes, and applies known
    rewrites (such as mapping `codex/execpolicy` to `codex/exec-policy`).
    """
    url_no_anchor = url.split("#", 1)[0].rstrip("/")
    for old_route, new_route in ROUTE_REWRITES.items():
        url_no_anchor = re.sub(
            rf"(?<=/){re.escape(old_route)}(?=(?:/|\.md|$))",
            new_route,
            url_no_anchor,
        )
    return url_no_anchor


def to_md_twin_url(url: str) -> str:
    """Convert a human-facing documentation URL to its .md twin endpoint.

    Strips anchor fragments, normalizes routes, and appends the `.md` extension
    if not already present.
    """
    normalized = normalize_route(url)
    if not normalized.endswith(".md"):
        normalized = f"{normalized}.md"
    return normalized


def _has_h1(md_text: str) -> bool:
    """Return True if md_text contains a top-level ATX or Setext heading."""
    in_fence = False
    lines = md_text.splitlines()
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("```") or stripped.startswith("~~~"):
            in_fence = not in_fence
            continue
        if not in_fence:
            if stripped.startswith("# ") or stripped.startswith("#\t"):
                return True
            if (
                i + 1 < len(lines)
                and stripped
                and not stripped.startswith("#")
                and re.fullmatch(r"={2,}", lines[i + 1].strip())
            ):
                return True
    return False


def _demote_headings(text: str, levels: int = 1) -> str:
    """Demote Markdown ATX and Setext headings by *levels*, skipping code blocks."""
    in_fence = False
    lines = text.splitlines(keepends=True)
    out: list[str] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()
        if stripped.startswith("```") or stripped.startswith("~~~"):
            in_fence = not in_fence
            out.append(line)
            i += 1
            continue

        if not in_fence:
            # Check Setext heading (next line is === or ---)
            if i + 1 < len(lines):
                next_line = lines[i + 1]
                next_stripped = next_line.strip()
                if (
                    stripped
                    and not stripped.startswith("#")
                    and (
                        re.fullmatch(r"={2,}", next_stripped)
                        or re.fullmatch(r"-{2,}", next_stripped)
                    )
                ):
                    is_h1 = next_stripped.startswith("=")
                    orig_level = 1 if is_h1 else 2
                    new_level = min(orig_level + levels, 6)
                    out.append(f"{'#' * new_level} {stripped}\n")
                    i += 2
                    continue

            if line.startswith("#"):
                m = re.match(r"^(#{1,6})(\s+.*)", line)
                if m:
                    hashes, rest = m.groups()
                    new_count = min(len(hashes) + levels, 6)
                    out.append("#" * new_count + rest)
                    i += 1
                    continue

        out.append(line)
        i += 1
    return "".join(out)


def _section_title_from_url(url: str) -> str:
    """Derive a human-readable section title from a target URL slug."""
    slug = url.split("#", 1)[0].rstrip("/").split("/")[-1]
    if slug.endswith(".md"):
        slug = slug[:-3]
    if slug.startswith("config-"):
        part = slug[len("config-") :].replace("-", " ").capitalize()
        return f"{part} Configuration"
    return slug.replace("-", " ").title()


def _is_pure_stub(text: str) -> bool:
    """Return True if text is a single-link stub page (heading + one link)."""
    links = _STUB_MD_LINK_RE.findall(text)
    if len(links) != 1:
        return False
    headings = re.findall(r"^#{1,6}\s+.*$", text, re.MULTILINE)
    if len(headings) > 1:
        return False
    non_heading_lines = [
        line.strip()
        for line in text.splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]
    non_heading_text = " ".join(non_heading_lines)
    return len(non_heading_text) < 300


def _fetch_pure_stub(
    client: httpx.Client,
    text: str,
    page: Page,
    match: re.Match[str],
) -> str:
    """Fetch rich markdown from the .md twin of a pure reference stub."""
    target_url = match.group(2)
    target_md_url = to_md_twin_url(target_url)
    try:
        rich_text, _ = fetch.fetch_validated(client, target_md_url)
    except fetch.FetchError as exc:
        print(
            f"  warning: failed to fetch rich docs from {target_md_url} ({exc}); "
            f"falling back to original GitHub text for {page.slug}",
            file=sys.stderr,
        )
        return text

    if not _has_h1(rich_text):
        heading_match = re.search(r"^#{1,6}\s+.+$", text, re.MULTILINE)
        if heading_match:
            stub_heading = heading_match.group(0).strip()
            rich_text = f"{stub_heading}\n\n{rich_text}"
    return rich_text


def _fetch_hybrid_page(
    client: httpx.Client,
    text: str,
    page: Page,
) -> str:
    """Resolve stub links in a hybrid page by embedding rich subsections."""
    paragraphs = re.split(r"\n\s*\n", text)
    resolved_paragraphs: list[str] = []

    for para in paragraphs:
        match = _STUB_MD_LINK_RE.search(para)
        if not match:
            resolved_paragraphs.append(para)
            continue

        target_url = match.group(2)
        target_md_url = to_md_twin_url(target_url)
        try:
            rich_text, _ = fetch.fetch_validated(client, target_md_url)
        except fetch.FetchError as exc:
            print(
                f"  warning: failed to fetch rich docs from {target_md_url} ({exc}); "
                f"falling back to original link in {page.slug}",
                file=sys.stderr,
            )
            resolved_paragraphs.append(para)
            continue

        # Strip redundant doc-index banner from subpages
        rich_text = _INDEX_BANNER_RE.sub("", rich_text).strip()

        if _has_h1(rich_text):
            section_content = _demote_headings(rich_text, levels=1)
        else:
            title = _section_title_from_url(target_url)
            demoted_body = _demote_headings(rich_text, levels=1)
            section_content = f"## {title}\n\n{demoted_body}"

        resolved_paragraphs.append(section_content)

    return "\n\n".join(resolved_paragraphs)


def get_version(client: httpx.Client) -> str | None:
    """Query the GitHub API for the latest release tag of Codex CLI."""
    return fetch_latest_release_tag(client, repo=REPO)


def discover(client: httpx.Client) -> list[Page]:
    """Discover CLI docs from the repo git tree and codex/llms.txt.

    1. Lists the full tree of ``openai/codex@main`` in one API call (via
       ``core.github.fetch_git_tree``) and keeps Markdown files that are direct
       children of ``docs/``.
    2. Fetches the ``codex/llms.txt`` index from developers.openai.com.
       If the request fails, logs a warning and proceeds with GitHub pages only.
       Filters bullet links to allowed domains, normalizes paths to slugs and groups,
       and constructs Page objects.
    3. Deduplicates pages by slug (first discovery wins; later duplicates log a warning).
    4. Skips the GitHub reference stubs whose rich twin is already discovered as
       its own page (see ``STUB_TWIN_SLUGS``), recording the skip in the
       module-level ``_SLUG_REDIRECTS`` map so links to the skipped slug are
       repointed at the mirrored twin.
    5. Updates the module-level ``_KNOWN_SLUGS`` set.
    6. Raises ``RuntimeError`` when discovery finds zero pages (zero-page guard).
    """
    tree = fetch_git_tree(client, repo=REPO, branch=BRANCH)

    pages: list[Page] = []
    seen: set[str] = set()

    # Step 1: GitHub Repository Files (direct Markdown children of docs/)
    for entry in tree:
        if entry.get("type") != "blob":
            continue
        path = entry.get("path", "")
        if not path.startswith(DOCS_PREFIX + "/"):
            continue
        rest = path[len(DOCS_PREFIX) + 1 :]
        if not rest.endswith(".md") or "/" in rest:
            continue
        slug = rest[:-3]
        if not slug:
            continue
        if slug in seen:
            warn_duplicate_slug(slug, path)
            continue
        seen.add(slug)
        page = try_make_page(
            path,
            slug=slug,
            source_url=f"{BLOB_BASE}/{path}",
            source_md_url=f"{RAW_BASE}/{path}",
            source_id=path,
            group="root",
        )
        if page is not None:
            pages.append(page)

    # Step 2: codex/llms.txt Documentation Pages
    try:
        llms_text = fetch.get_with_retry(client, LLMS_TXT_URL)
    except Exception as exc:
        print(
            f"  warning: failed to fetch llms.txt index ({exc}); "
            "continuing with GitHub repository pages only",
            file=sys.stderr,
        )
        llms_text = ""

    if llms_text:
        for match in _LLMS_BULLET_RE.finditer(llms_text):
            raw_url = match.group(2).strip()

            parsed = urlparse(raw_url)
            if parsed.netloc not in ("learn.chatgpt.com", "developers.openai.com"):
                continue

            clean_path = parsed.path
            if not clean_path.endswith(".md") or not clean_path.startswith("/docs/"):
                continue

            slug = clean_path[len("/docs/") : -3]
            if not slug:
                continue

            if slug in seen:
                warn_duplicate_slug(slug, raw_url)
                continue
            seen.add(slug)

            group = slug.split("/", 1)[0] if "/" in slug else "root"
            canonical_path = clean_path[:-3]
            source_url = f"{parsed.scheme}://{parsed.netloc}{canonical_path}"
            source_md_url = f"{parsed.scheme}://{parsed.netloc}{clean_path}"
            source_id = f"llms:{slug}"

            page = try_make_page(
                raw_url,
                slug=slug,
                source_url=source_url,
                source_md_url=source_md_url,
                source_id=source_id,
                group=group,
            )
            if page is not None:
                pages.append(page)

    # Step 3: drop the GitHub reference stubs whose rich twin is mirrored
    # under its own slug. Mirroring both members of such a pair would put two
    # byte-identical files on disk and list the same document twice in the
    # generated index, which makes the mirror look like it holds two pages
    # where upstream publishes one. The stub is skipped only while its twin is
    # really part of this run -- if the twin is missing (a renamed upstream
    # route, an unreachable documentation index), the stub is mirrored as
    # before rather than losing the document.
    redirected: dict[str, str] = {}
    kept: list[Page] = []
    for page in pages:
        twin = STUB_TWIN_SLUGS.get(page.slug)
        if twin is not None and page.source_id.startswith(DOCS_PREFIX) and twin in seen:
            print(
                f"  note: skipping reference stub {page.slug!r} "
                f"({page.source_url}); its content is mirrored as {twin!r}",
                file=sys.stderr,
            )
            redirected[page.slug] = twin
            continue
        kept.append(page)
    pages = kept

    pages.sort(key=lambda p: p.slug)
    if not pages:
        raise RuntimeError(
            f"No Markdown files found directly under {DOCS_PREFIX!r}/ in "
            f"{REPO}@{BRANCH} or via {LLMS_TXT_URL}. A zero-page discovery would "
            "delete all mirrored files."
        )

    _KNOWN_SLUGS.clear()
    _KNOWN_SLUGS.update(p.slug for p in pages)
    _SLUG_REDIRECTS.clear()
    _SLUG_REDIRECTS.update(redirected)
    return pages


def _redirect_slug(slug: str) -> str:
    """Follow a skipped-stub redirect to the slug that is actually mirrored.

    A slug that was skipped in favor of its twin is rewritten to the twin, so
    references land on the file that exists; chains are followed (bounded by
    the visited set, which makes a malformed cycle terminate instead of
    hanging) and every other slug is returned unchanged.
    """
    visited: set[str] = set()
    while slug in _SLUG_REDIRECTS and slug not in visited:
        visited.add(slug)
        slug = _SLUG_REDIRECTS[slug]
    return slug


def _iter_link_matches(
    text: str,
    pattern: re.Pattern[str],
    candidate: str,
    *,
    starts_at_link_text: bool = False,
) -> Iterator[re.Match[str]]:
    """Yield every match of *pattern* in *text*, in document order.

    Semantics-identical to ``pattern.finditer(text)`` but LINEAR on adversarial
    input (see the hazard comment on each pattern above). The scan is
    decomposed into:

    1. ``str.find(candidate, ...)`` to locate the next candidate -- a literal
       the pattern requires, so no position that cannot match is ever handed
       to the regex engine. Each pattern is given the tightest such literal:
       ``](/`` for the site-absolute pattern, whose head that is, and ``](``
       for the relative-``.md`` pattern, whose head is a lookahead and so has
       no longer common literal.
    2. ``str.find(")", ...)`` to locate the first closing parenthesis after
       it. Every destination class in the patterns excludes ``)``, so a match
       can only ever end at that first parenthesis; passing its position to
       the engine as ``endpos`` is what bounds each attempt to one link's
       worth of text instead of letting it scan to end-of-string and
       backtrack one character at a time.
    3. ``pattern.match`` on the proven window, so the groups are produced by
       the original pattern itself, not reimplemented.

    *starts_at_link_text* selects where a match begins. The patterns applied
    to a page's body start at the ``](`` the candidate names, so the candidate
    position IS the match start. The cross-documentation pattern does not: it
    opens with the link TEXT (``\\[([^\\]]*)\\]``) and only then reaches the
    destination. For it, the match start is recovered from the pattern's own
    link-text rule: the text between the ``[`` and the ``]`` may not contain a
    ``]``, so the match starts at the leftmost ``[`` in the run of
    ``]``-free text that ends at the candidate. That ``[`` is not part of the
    destination the candidate pinned down, which is why it is searched for
    separately rather than assumed; the match itself, groups included, is
    still produced by the pattern.

    LINEAR-TIME ARGUMENT: every ``str.find``/``str.rfind`` above resumes where
    an earlier one stopped. The candidate cursor only moves forward, each
    iteration resuming the parenthesis search at or after the candidate it is
    about to prove, and the ``]``/``[`` searches of an iteration are bounded
    by the region between the previous iteration's candidate and this one --
    a region no later iteration reaches back into, because the cursor that
    delimits it only ever advances. Each character of the document is
    therefore examined a bounded number of times, and each ``pattern.match``
    is confined to one link's worth of text. When no closing parenthesis
    exists, the loop STOPS rather than retrying from the next candidate: a
    ``)`` for any later link would sit after this candidate too and would have
    been found, so no later link can match either.
    """
    pos = 0
    closer = -1  # cached first ")" at or after the candidate cursor
    while True:
        found = text.find(candidate, pos)
        if found == -1:
            break
        if closer < found + 2:
            closer = text.find(")", found + 2)
            if closer == -1:
                # No ")" anywhere after this candidate -- and therefore after
                # ANY later one either (see the docstring).
                break
        start = found
        if starts_at_link_text:
            # ``rfind`` answers -1 when the cursor's own text holds no "]",
            # in which case the run starts at the cursor -- using 0 instead
            # would put the run's start before every match already consumed
            # and re-match one of them forever.
            bracket = text.rfind("]", pos, found)
            run_start = pos if bracket == -1 else bracket + 1
            start = text.find("[", run_start, found)
            if start == -1:
                # No "[" before the destination in this run, so the pattern
                # cannot match here. A later candidate starts after it.
                pos = found + 1
                continue
        match = pattern.match(text, start, closer + 1)
        if match is None:
            # The destination does not continue the way the pattern needs
            # (a different host, a space before the closer), so this
            # candidate is not a link. A later one starts after it.
            pos = found + 1
            continue
        yield match
        pos = closer = match.end()


def _splice_matches(
    text: str,
    matches: Iterator[re.Match[str]],
    replacement: Callable[[re.Match[str]], str],
) -> str:
    """Rebuild *text*, replacing each of *matches* with *replacement* of it.

    The substitution half of a link pass: the caller's scanner names the
    matches in document order, *replacement* answers what each one becomes,
    and everything between two matches is copied through byte for byte --
    which is what keeps a rewrite confined to the links the scanner proved,
    instead of re-examining the rest of the page.

    The caller may return ``match.group(0)`` to leave a match as it was; that
    is the same string the copy would have produced, so the two are
    interchangeable.
    """
    out: list[str] = []
    pos = 0
    for match in matches:
        out.append(text[pos : match.start()])
        out.append(replacement(match))
        pos = match.end()
    out.append(text[pos:])
    return "".join(out)


def _rewrite_cross_links(
    text: str,
    current_slug: str,
    known_slugs: set[str] | None = None,
) -> str:
    """Rewrite absolute documentation links pointing to known slugs to relative Markdown links.

    Matches links pointing to learn.chatgpt.com/docs/..., learn.chatgpt.com/guides/...,
    or developers.openai.com/(docs|guides)/..., normalizes the target path to a potential
    slug, and checks if the slug is present in `known_slugs` (defaulting to `_KNOWN_SLUGS`).
    If found, rewrites the target as a relative link with `./` prefix if needed and
    preserves any anchor fragment. A slug that was skipped in favor of its twin
    resolves through that redirect. Unmatched or unknown links are left intact.

    The matches come from :func:`_iter_link_matches` rather than from a
    ``re.sub`` over the pattern: the pass runs on raw Markdown fetched from
    the network, and the pattern's greedy destination class is quadratic on
    input that repeats its head without a closing parenthesis (see the hazard
    comment on the pattern). Links the pattern rejects -- another host, an
    unknown slug -- are copied through unchanged.
    """
    if known_slugs is None:
        known_slugs = _KNOWN_SLUGS

    def replace(match: re.Match[str]) -> str:
        link_text = match.group(1)
        raw_target = match.group(3)
        anchor = match.group(4) or ""

        # Normalize target path to potential slug, stripping query params and .md
        target_path = raw_target.split("?", 1)[0]
        if target_path.endswith(".md"):
            target_path = target_path[:-3]
        target_slug = target_path.strip("/")

        # A link to a skipped stub names a page this mirror does not hold;
        # follow the redirect so it points at the page carrying that content.
        redirected_slug = _redirect_slug(target_slug)

        # Check against known slugs, including guides/ prefix fallback for /guides/ routes
        if redirected_slug not in known_slugs:
            if f"guides/{redirected_slug}" in known_slugs:
                redirected_slug = f"guides/{redirected_slug}"
            else:
                return match.group(0)

        current_dir = posixpath.dirname(current_slug) or "."
        rel_path = posixpath.relpath(f"{redirected_slug}.md", current_dir)
        if not rel_path.startswith((".", "/")):
            rel_path = f"./{rel_path}"
        new_target = f"{rel_path}{anchor}"
        return f"[{link_text}]({new_target})"

    return _splice_matches(
        text,
        _iter_link_matches(
            text, _CROSS_DOC_LINK_RE, "](http", starts_at_link_text=True
        ),
        replace,
    )


def _rewrite_body_links(
    text: str,
    current_slug: str,
    known_slugs: set[str] | None = None,
) -> str:
    """Rewrite links written in a page's prose into links this mirror can serve.

    Two shapes reach the mirrored pages as body text rather than as component
    props, and both would otherwise stay broken:

    * **site-absolute links** (``/codex/config-file/config-advanced#...``).
      They resolve against the documentation site's root, so they are routed
      through the same resolution the components use: a relative link when the
      target is mirrored, the upstream URL when it is not.
    * **relative links to a skipped stub** (``./skills.md``). The stub is not
      mirrored, so the link is repointed at the twin that replaced it.

    Both shapes are found by :func:`_iter_link_matches`, not by a ``re.sub``
    over their patterns: the pass runs on raw Markdown fetched from the
    network, and each pattern's greedy destination class is quadratic on
    input that repeats its head without a closing parenthesis (see the hazard
    comments on the patterns). The two passes are applied in turn because they
    answer different questions -- which page a site-absolute link should point
    at, and which file a reference to a skipped stub should point at -- and
    neither can undo the other: the second pass only repoints a link whose
    target is a stub this run skipped, and the first resolves such a target
    through its redirect already.
    """
    if known_slugs is None:
        known_slugs = _KNOWN_SLUGS

    def site_absolute_replace(match: re.Match[str]) -> str:
        href = match.group("href")
        return f"]({_resolve_internal_href(href, current_slug, known_slugs)})"

    def relative_redirect_replace(match: re.Match[str]) -> str:
        anchor = match.group("anchor") or ""
        current_dir = posixpath.dirname(current_slug) or "."
        joined = posixpath.normpath(posixpath.join(current_dir, match.group("path")))
        target_slug = joined[:-3] if joined.endswith(".md") else joined
        twin = _redirect_slug(target_slug)
        if twin == target_slug:
            return match.group(0)
        rel_path = posixpath.relpath(f"{twin}.md", current_dir)
        if not rel_path.startswith((".", "/")):
            rel_path = f"./{rel_path}"
        return f"]({rel_path}{anchor})"

    text = _splice_matches(
        text,
        _iter_link_matches(text, _SITE_ABSOLUTE_LINK_RE, "](/"),
        site_absolute_replace,
    )
    return _splice_matches(
        text,
        _iter_link_matches(text, _RELATIVE_MD_LINK_RE, "]("),
        relative_redirect_replace,
    )


def _rewrite_root_link(text_or_match: str | re.Match[str]) -> str:
    """Rebuild a matched ``](../<file>#anchor)`` link as its canonical GitHub URL.

    Accepts either a ``re.Match`` object when used as a ``re.sub`` replacement function,
    or a ``str`` to perform the replacement directly on the input text.
    The optional ``#anchor`` fragment is preserved verbatim so section links
    such as ``../SECURITY.md#policy`` keep resolving after the rewrite.
    """
    if isinstance(text_or_match, str):
        return _ROOT_LINK_RE.sub(_rewrite_root_link, text_or_match)
    match = text_or_match
    return (
        f"](https://github.com/{REPO}/blob/{BRANCH}/{match.group(1)}"
        f"{match.group(2) or ''})"
    )


def _find_fence_close(text: str, opener: str, start: int) -> int | None:
    """Return the index just past the fence run that closes the block opened by *opener*.

    A fence only closes on a run of the same character that is at least as long
    as the one that opened it, so the closing run is searched for by length
    rather than by the mere presence of three backticks. The index returned
    stops at the run itself: whatever follows it on the line (trailing spaces,
    the line's newline) is not part of the code block, so shielding ends where
    the fence ends. Returns ``None`` when the document runs out first.
    """
    close_re = re.compile(
        rf"(?m)^[ \t]*({re.escape(opener[0])}{{{len(opener)},}})[ \t]*(?:\n|\Z)"
    )
    match = close_re.search(text, start)
    return None if match is None else match.start(1) + len(match.group(1))


def _iter_fence_spans(text: str) -> Iterator[tuple[int, int]]:
    """Yield the ``(start, end)`` span of every complete fenced code block.

    The spans are the ones this adapter's fence rules select: an opening line
    at ANY indentation (a sample inside a list item is indented by the list,
    and shielding it is what keeps the example out of the component
    converters), and a closing fence of the same character that is AT LEAST
    as long as the opener -- so a four-backtick block documenting
    three-backtick fences closes at its own four-backtick line rather than at
    the first inner run.

    Both rules are deliberately WIDER than the shared column-zero scanner in
    ``core/fenced_code`` (the one the other shielded adapters use), which is
    why this adapter supplies its own span finder to
    ``core.fenced_code.protect_fenced_code`` instead of the shared one: a
    page's indentation and fence lengths are properties of the page, and
    narrowing them here would stop shielding blocks this adapter's
    transformations must not touch. The extraction loop itself is shared.

    An opener with no closing fence is not a block: skipping it leaves the
    text exactly as it was, where shielding a run to the end of the document
    would hide the components that follow.

    A failed closer search is remembered per fence RUN -- the first position
    from which that run's closer is known to be absent -- and every later
    opener of the same run starts further right, so the absence still holds
    and the search is skipped instead of repeated. Without that, a document
    full of opener lines that no fence closes costs one scan to
    end-of-document PER OPENER, which is quadratic in the document length: a
    520 KB page of them took 50 s to scan. Each distinct fence run now
    reaches the end of the document at most once.
    """
    # Fence run -> the earliest index from which that run's closer search
    # failed. The closer pattern depends on the run's character AND its
    # length, so runs are keyed by their own text rather than by their
    # character alone: three backticks close a three-backtick fence but not a
    # four-backtick one, and the two therefore fail independently.
    no_closer_from: dict[str, int] = {}
    position = 0
    while (open_match := _FENCE_OPENER_RE.search(text, position)) is not None:
        fence = open_match.group(1)
        known_absent = no_closer_from.get(fence)
        if known_absent is not None and open_match.end() >= known_absent:
            position = open_match.end()
            continue
        close_at = _find_fence_close(text, fence, open_match.end())
        if close_at is None:
            no_closer_from[fence] = open_match.end()
            position = open_match.end()
            continue
        yield open_match.start(), close_at
        position = close_at


def _fence_placeholder(index: int) -> str:
    """Return the placeholder token that stands for one shielded block.

    An HTML comment: it survives every regex this module runs (the component
    and link passes match Markdown and JSX, not comments), it is invisible in
    a rendered document if a token ever leaked, and its shape cannot occur in
    the upstream MDX by accident.
    """
    return f"<!--__FENCED_CODE_BLOCK_{index}__-->"


def _protect_fenced_code(text: str) -> tuple[str, list[str]]:
    """Protect fenced code blocks by replacing them with unique placeholder tokens.

    Shields code examples (in ``` or ~~~ fences) from subsequent MDX
    transformations, such as component tag stripping or link rewriting, and
    returns the protected text alongside the list of original code block
    strings.

    The extraction loop and the splice come from :mod:`core.fenced_code`,
    which is where the mechanism every fence-shielding adapter shares is kept
    (the same extract -> transform -> splice principle the HTML-to-Markdown
    adapters apply to ``<pre>`` elements); this module contributes its own
    fence rules and its own token shape.
    """
    return protect_fenced_code(
        text, spans=_iter_fence_spans, placeholder=_fence_placeholder
    )


def _restore_fenced_code(text: str, code_blocks: list[str]) -> str:
    """Restore previously protected fenced code blocks from placeholder tokens."""
    return restore_fenced_code(text, code_blocks, _fence_placeholder)


@dataclass(frozen=True, slots=True)
class _ComponentBlock:
    """One JSX component occurrence located in a document.

    ``start`` is the index of the opening ``<`` and ``end`` the index just past
    the closing ``>`` (self-closing tags) or past the matching ``</name>``
    (container tags), so ``raw`` is the whole component exactly as it appears
    in the source. ``props`` holds the raw attribute text between the tag name
    and the closing bracket -- the input every converter parses -- and ``body``
    the inner Markdown of a container component, empty for self-closing tags.
    """

    name: str
    start: int
    end: int
    raw: str
    props: str
    body: str
    self_closing: bool


def _find_tag_end(text: str, start: int, limit: int | None = None) -> int | None:
    """Return the index just past the ``>`` that closes the tag opened at *start*.

    A regex cannot delimit a JSX tag: attribute values legitimately contain
    ``>`` (``type: "array<string>"``, comparison expressions, ``=>``), and the
    props of the larger components span dozens of lines, so ``<Tag[^>]*>``
    either stops at the first ``>`` inside the data or -- worse, because it
    looks like it worked -- swallows everything up to the next line-final
    ``>``, deleting documented entries. This scanner walks the tag instead and
    only accepts a ``>`` that is both outside a quoted string and outside a
    ``{...}`` expression, which is exactly where JSX ends a tag.

    *limit*, when given, is an exclusive index the scan may not reach. Callers
    pass the start of the next opening tag with the same name, because an
    unterminated tag must not read across its sibling: the sibling would be
    consumed by a tag that never closes, and a page full of unterminated tags
    would be rescanned to its end once per tag.

    Returns ``None`` for an unterminated tag; callers then leave the text
    untouched rather than guessing at a boundary.
    """
    quote = ""
    depth = 0
    index = start + 1
    stop = len(text) if limit is None else min(limit, len(text))
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
            # use them for prompt text and never for ``${}`` interpolation, so
            # treating the whole literal as opaque keeps the scanner simple
            # without losing a boundary in this corpus.
            quote = char
        elif char == "{":
            depth += 1
        elif char == "}" and depth:
            depth -= 1
        index += 1
    return None


def _matching_close(text: str, name: str, tag_end: int) -> int | None:
    """Return the index just past the closing tag that matches the open at *tag_end*.

    Containers can nest (a surface switch holding one variant per surface, a
    wrapper around another wrapper), so the matching close is the one where the
    nesting depth returns to zero. Self-closing tags of the same name do not
    open a level. Returns ``None`` when the text ends first, which leaves that
    component untouched rather than guessing at a boundary.
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
        # Skip past the nested tag's own opening boundary, then keep looking
        # for the closing tags that follow it.
        position = nested_end if nested_end is not None else nested.end()
    return position


def _iter_components(text: str, name: str) -> Iterator[_ComponentBlock]:
    """Yield every ``<name ...>`` component in *text*, in document order.

    Self-closing tags yield a block with an empty ``body``. Container tags
    (``<name ...>...</name>``) yield the inner Markdown up to the matching
    closing tag. A tag whose opening or closing boundary cannot be located is
    skipped, leaving the text as-is for the remnant report to catch, and the
    scan then resumes after it so that a later occurrence -- which may well be
    well formed -- is still converted.
    """
    opener = re.compile(rf"<{re.escape(name)}\b")
    position = 0
    # Set once a closing tag is known to be absent from some index onward. A
    # later opener starts searching for its own closing tag further right, so
    # the same absence holds for it, and recording it keeps a document of
    # unterminated container tags from rescanning its tail once per tag.
    no_closer_from: int | None = None
    while True:
        match = opener.search(text, position)
        if match is None:
            return
        # An open tag may not read across the next opener of its own name: that
        # is where a tag the scanner cannot terminate ends and its sibling
        # begins.
        following = opener.search(text, match.end())
        limit = following.start() if following is not None else len(text)
        tag_end = _find_tag_end(text, match.start(), limit)
        if tag_end is None:
            # The tag never closes: an unclosed quote or brace inside it makes
            # the scanner run out of text (or reach its sibling). Resume right
            # after the opener rather than abandoning the document, because the
            # next occurrence is scanned from its own index and can still
            # parse.
            position = match.end()
            continue
        props = text[match.end() : tag_end]
        if text[tag_end - 2 : tag_end] == "/>":
            yield _ComponentBlock(
                name,
                match.start(),
                tag_end,
                text[match.start() : tag_end],
                props,
                "",
                True,
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
        yield _ComponentBlock(
            name,
            match.start(),
            end,
            text[match.start() : end],
            props,
            text[tag_end : end - len(f"</{name}>")],
            False,
        )
        position = end


# Bound on the nesting depth of components that wrap other components of the
# same name. Real pages nest two levels at most; the bound only exists so a
# renderer that somehow re-emits its own tag cannot spin forever.
_MAX_NESTED_COMPONENT_PASSES = 10


def _render_components(
    text: str,
    name: str,
    render: Callable[[str, _ComponentBlock], str],
) -> str:
    """Replace every ``<name>`` component in *text* with ``render(text, block)``.

    Every block carries its own source text in ``raw``, so a converter that
    keeps a component verbatim (unreadable props) restores that component
    exactly, whatever the surrounding passes did before it. The renderer also
    receives the text the block was found in, for converters that need the
    document around it rather than the component alone.

    Note for converters that restore a component: the text handed to the
    renderer is the text the block was *found* in, which for every pass after
    the first is no longer the text being assembled -- slicing it by the
    block's offsets would take a run of characters from the wrong place.
    Return ``block.raw`` instead.

    Passes repeat while the text keeps changing, which is what converts
    components nested inside another component of the same name: the outer one
    is rendered first with its body intact, and the next pass picks up the
    tags that body still holds.
    """
    for _ in range(_MAX_NESTED_COMPONENT_PASSES):
        parts: list[str] = []
        cursor = 0
        for block in _iter_components(text, name):
            parts.append(text[cursor : block.start])
            parts.append(render(text, block))
            cursor = block.end
        parts.append(text[cursor:])
        updated = "".join(parts)
        if updated == text:
            return text
        text = updated
    return text


def _unescape_js_string(value: object) -> str:
    """Return a parsed JavaScript string value as a plain ``str``.

    The JS parser returns Python objects (``str``, ``int``, ``bool``, ``None``,
    ``dict``, ``list``); converters render text, so non-strings collapse to an
    empty string rather than leaking a Python repr into the Markdown.
    """
    return value if isinstance(value, str) else ""


def _dedent_block(text: str) -> str:
    """Remove a component body's common leading indentation.

    Indentation inside an MDX component is source formatting with no meaning,
    but it *does* mean something once the component is unwrapped into plain
    Markdown: a heading or list indented by four spaces becomes an indented
    code block. Collapsing the common indentation (and normalizing
    whitespace-only lines to empty, which ``textwrap.dedent`` does as well)
    keeps the unwrapped content at the level its surrounding document uses.
    """
    return textwrap.dedent(text).strip("\n")


def _markdown_cell(value: str) -> str:
    """Render one Markdown table cell: single line, pipes escaped.

    Component data is single-line prose, but descriptions do contain ``|``
    (union types such as ``on-request | never``), which would otherwise split
    the row into extra columns.
    """
    return " ".join(value.split()).replace("|", r"\|")


def _markdown_table(header: list[str], rows: list[list[str]]) -> str:
    """Render a GitHub-flavored Markdown table from plain string cells."""
    lines = [
        "| " + " | ".join(header) + " |",
        "| " + " | ".join("---" for _ in header) + " |",
    ]
    for row in rows:
        lines.append("| " + " | ".join(row) + " |")
    return "\n".join(lines)


def _fenced_block(text: str, language: str = "text") -> str:
    """Wrap *text* in a fenced code block whose fence outlives any inner run.

    Content that itself contains backticks (a prompt quoting Markdown, a
    snippet documenting fences) would close a fixed three-backtick fence early
    and spill the remainder into prose, so the fence is one backtick longer
    than the longest run inside.
    """
    longest = max((len(run) for run in re.findall(r"`+", text)), default=0)
    fence = "`" * max(3, longest + 1)
    return f"{fence}{language}\n{text}\n{fence}"


def _heading_slug(heading: str) -> str:
    """Compute the URL anchor GitHub derives from a heading's text.

    Mirrors the slugger used for the mirrored pages: inline code markers and
    punctuation are dropped, letters are lowercased, and runs of whitespace
    become single dashes (``### `codex exec``` becomes ``codex-exec``).
    """
    slug = heading.replace("`", "").strip().lower()
    slug = re.sub(r"[^\w\s-]", "", slug)
    return re.sub(r"\s+", "-", slug).strip("-")


def _tokenize_js_props(raw_props: str) -> list[tuple[str, str]]:
    """Tokenize JavaScript object and array literals embedded in JSX component props.

    Recognizes quoted strings, template literals, numbers, punctuation
    (braces, brackets, colons, commas), operators (equals), and identifiers
    or keyword values.
    """
    tokens: list[tuple[str, str]] = []
    token_re = re.compile(
        r"""
        (?P<TEMPLATE>`(?:[^`\\]|\\.)*`) |
        (?P<STRING>"(?:[^"\\]|\\.)*"|'(?:[^'\\]|\\.)*') |
        (?P<LBRACE>\{) |
        (?P<RBRACE>\}) |
        (?P<LBRACKET>\[) |
        (?P<RBRACKET>\]) |
        (?P<COLON>:) |
        (?P<COMMA>,) |
        (?P<EQUALS>=) |
        (?P<WORD>[a-zA-Z_$][a-zA-Z0-9_$-]*) |
        (?P<NUMBER>-?\d+(?:\.\d+)?)
        """,
        re.VERBOSE,
    )
    for match in token_re.finditer(raw_props):
        kind = match.lastgroup
        assert kind is not None
        val = match.group(kind)
        tokens.append((kind, val))
    return tokens


def _parse_props(props: str) -> dict[str, object] | None:
    """Parse a component's JSX attributes, or ``None`` when they are unreadable.

    Component props are JavaScript, and the mirror must never lose a page
    because one component happens to use a literal shape the small parser does
    not understand. Every converter therefore goes through this guard and
    leaves the component text untouched on ``None``; the remnant scan in the
    test suite is what surfaces such a component for a follow-up.
    """
    try:
        return _JSParser(_tokenize_js_props(props)).parse_jsx_props()
    except Exception:
        # Breadth is the point: the parser raises ``ValueError`` for unexpected
        # tokens and ``json.JSONDecodeError`` for malformed string escapes, and
        # both mean the same thing to a caller -- unreadable props.
        return None


def _availability_label(value: object) -> str:
    """Render one plan feature matrix availability value as a table cell."""
    if isinstance(value, str) and value:
        return _AVAILABILITY_LABELS.get(value, value.replace("-", " ").capitalize())
    return "—"


class _JSParser:
    """Recursive-descent parser for JavaScript literal values in component attributes."""

    def __init__(self, tokens: list[tuple[str, str]]) -> None:
        self.tokens = tokens
        self.pos = 0

    def peek(self) -> tuple[str | None, str | None]:
        """Return the next token without advancing the parser position."""
        if self.pos < len(self.tokens):
            return self.tokens[self.pos]
        return (None, None)

    def next(self) -> tuple[str | None, str | None]:
        """Return the next token and advance the parser position."""
        tok = self.peek()
        self.pos += 1
        return tok

    @staticmethod
    def string_value(token: str) -> str:
        """Return the text of a quoted string token, with its escapes resolved.

        Double-quoted tokens decode as JSON, which also resolves the standard
        escape sequences. Single-quoted and template-literal tokens keep their
        text verbatim apart from the quote and backslash escapes: the single
        quote is the style upstream uses for values that themselves contain
        double quotes (``key: 'a."b".c'``), and keeping those inner quotes
        intact is what lets such a value render as it reads.
        """
        if token.startswith(("'", "`")):
            quote = token[0]
            return token[1:-1].replace(f"\\{quote}", quote).replace("\\\\", "\\")
        return json.loads(token)

    def parse_value(self) -> object:
        """Parse a single JavaScript literal value (string, number, boolean, array, or object)."""
        kind, val = self.peek()
        if kind in ("TEMPLATE", "STRING") and val is not None:
            # Template literals are used for multi-line prompt text; their text
            # is kept verbatim, escape sequences included.
            self.next()
            return self.string_value(val)
        if kind == "NUMBER" and val is not None:
            self.next()
            return float(val) if "." in val else int(val)
        if kind == "WORD" and val is not None:
            self.next()
            if val == "true":
                return True
            if val == "false":
                return False
            if val == "null":
                return None
            return val
        if kind == "LBRACE":
            return self.parse_object()
        if kind == "LBRACKET":
            return self.parse_array()
        raise ValueError(f"Unexpected token {kind}: {val} at position {self.pos}")

    def parse_object(self) -> dict[str, object]:
        """Parse a JavaScript object literal enclosed in curly braces."""
        self.next()
        obj: dict[str, object] = {}
        while self.pos < len(self.tokens):
            kind, val = self.peek()
            if kind == "RBRACE":
                self.next()
                return obj
            if kind == "COMMA":
                self.next()
                continue
            if kind in ("WORD", "STRING", "TEMPLATE") and val is not None:
                self.next()
                key = val if kind == "WORD" else self.string_value(val)
                c_kind, _ = self.peek()
                if c_kind == "COLON":
                    self.next()
                    obj[key] = self.parse_value()
                else:
                    obj[key] = True
            else:
                raise ValueError(f"Unexpected token in object {kind}: {val}")
        return obj

    def parse_array(self) -> list[object]:
        """Parse a JavaScript array literal enclosed in square brackets."""
        self.next()
        arr: list[object] = []
        while self.pos < len(self.tokens):
            kind, _ = self.peek()
            if kind == "RBRACKET":
                self.next()
                return arr
            if kind == "COMMA":
                self.next()
                continue
            arr.append(self.parse_value())
        return arr

    def parse_jsx_props(self) -> dict[str, object]:
        """Parse top-level JSX attributes from token stream into a Python dictionary."""
        props: dict[str, object] = {}
        while self.pos < len(self.tokens):
            kind, val = self.peek()
            if kind == "WORD" and val is not None:
                prop_name = val
                self.next()
                eq_kind, _ = self.peek()
                if eq_kind == "EQUALS":
                    self.next()
                    v_kind, _ = self.peek()
                    if v_kind == "STRING":
                        props[prop_name] = self.parse_value()
                    elif v_kind == "LBRACE":
                        self.next()
                        props[prop_name] = self.parse_value()
                        r_kind, _ = self.peek()
                        if r_kind == "RBRACE":
                            self.next()
                    else:
                        props[prop_name] = self.parse_value()
                else:
                    props[prop_name] = True
            else:
                self.next()
        return props


def _resolve_internal_href(
    href: str,
    current_slug: str,
    known_slugs: set[str],
) -> str:
    """Resolve an internal documentation href to a relative Markdown link.

    Normalizes `/codex/...` or `/docs/...` paths to potential page slugs and looks
    them up in `known_slugs`. When found, returns a relative Markdown path with
    appropriate directory traversal (`../` or `./`) and preserves URL anchors.
    If the target is external or unknown, falls back to the canonical upstream URL
    (or, for a URL that already names a different host, is returned unchanged).

    Absolute URLs are only candidate mirrors when they point at the Codex
    documentation routes: other OpenAI properties reuse slugs the Codex docs
    also use (``/plugins/build/plugins``, ``/workspace-agents/authentication``),
    and matching those by their last path segment would silently repoint a link
    at a different page of the mirror.

    A slug that is not mirrored under its own name is retried under three
    further spellings, in order: with a ``guides/`` prefix, as its last path
    segment alone, and with hyphens replaced by underscores. They cover the
    two origins this module mirrors under one folder -- the documentation
    catalogue names a page ``agents-md`` while the repository file for it is
    ``agents_md.md`` -- while staying conservative: a spelling is only used
    when it names a page this run mirrors, so an unknown reference still falls
    through to its upstream URL.
    """
    href_clean, _, query = href.partition("?")
    href_path, _, anchor = href_clean.partition("#")

    parsed = urlparse(href_path)
    if parsed.scheme in ("http", "https"):
        route = parsed.path
        if route.startswith("/codex/"):
            slug = route[len("/codex/") :]
        elif route.startswith("/docs/"):
            slug = route[len("/docs/") :]
        else:
            return href
    elif href_path.startswith("/codex/"):
        slug = href_path[len("/codex/") :]
    elif href_path.startswith("/docs/"):
        slug = href_path[len("/docs/") :]
    elif href_path.startswith("/"):
        slug = href_path[1:]
    else:
        slug = href_path

    slug = slug.rstrip("/")
    if slug.endswith(".md"):
        slug = slug[:-3]

    # A reference to a slug that was skipped in favor of its twin must land on
    # the mirrored twin, not on a file this mirror does not hold.
    slug = _redirect_slug(slug)

    matched_slug: str | None = None
    if slug in known_slugs:
        matched_slug = slug
    elif f"guides/{slug}" in known_slugs:
        matched_slug = f"guides/{slug}"
    elif slug.split("/")[-1].replace("-", "_") in known_slugs:
        matched_slug = slug.split("/")[-1].replace("-", "_")
    elif slug.replace("-", "_") in known_slugs:
        matched_slug = slug.replace("-", "_")

    if matched_slug is not None:
        current_dir = posixpath.dirname(current_slug) or "."
        rel_target = posixpath.relpath(f"{matched_slug}.md", current_dir)
        if not rel_target.startswith((".", "/")):
            rel_target = f"./{rel_target}"
        if anchor:
            rel_target = f"{rel_target}#{anchor}"
        return rel_target

    anchor_part = f"#{anchor}" if anchor else ""
    query_part = f"?{query}" if query else ""
    if href.startswith(("http://", "https://")):
        return href
    return f"https://developers.openai.com{href_path}{query_part}{anchor_part}"


def _convert_overview_landing(
    text: str,
    current_slug: str,
    known_slugs: set[str],
) -> str:
    """Convert <CodexDocsOverviewLanding> components into standard CommonMark outlines.

    Extracts title, intro, primary call-to-action guide, and grouped topic sections,
    producing structured headings and bulleted guide lists with relative Markdown links.
    """

    def repl(_text: str, block: _ComponentBlock) -> str:
        props = _parse_props(block.props)
        if props is None:
            return block.raw

        parts: list[str] = []
        title = _unescape_js_string(props.get("title"))
        description = _unescape_js_string(props.get("description"))
        intro = _unescape_js_string(props.get("intro"))
        primary_cta = props.get("primaryCta")
        sections = props.get("sections", [])

        # Ensure top-level H1 heading exists if not already present in the preceding text
        if title and not re.search(r"^#\s+", text[: block.start], re.MULTILINE):
            parts.append(f"# {title}\n")

        if description:
            parts.append(f"{description}\n")
        if intro and intro != description:
            parts.append(f"{intro}\n")

        if isinstance(primary_cta, dict) and "href" in primary_cta:
            cta_label = str(primary_cta.get("label", "Primary guide"))
            cta_href = _resolve_internal_href(
                str(primary_cta["href"]), current_slug, known_slugs
            )
            parts.append(f"> **Recommended:** [{cta_label}]({cta_href})\n")

        if isinstance(sections, list):
            for sec in sections:
                if not isinstance(sec, dict):
                    continue
                sec_title = _unescape_js_string(sec.get("title"))
                sec_desc = sec.get("description", "")
                pages = sec.get("pages", [])

                parts.append(f"## {sec_title}\n")
                if sec_desc and isinstance(sec_desc, str):
                    parts.append(f"{sec_desc}\n")

                if isinstance(pages, list):
                    for page in pages:
                        if not isinstance(page, dict):
                            continue
                        p_title = _unescape_js_string(page.get("title"))
                        p_desc = page.get("description", "")
                        p_href = page.get("href", "")
                        resolved_link = (
                            _resolve_internal_href(
                                str(p_href), current_slug, known_slugs
                            )
                            if p_href
                            else ""
                        )

                        if resolved_link and p_title:
                            item = f"- [{p_title}]({resolved_link})"
                        elif p_title:
                            item = f"- {p_title}"
                        else:
                            continue

                        if p_desc and isinstance(p_desc, str):
                            item += f" — {p_desc}"
                        parts.append(f"{item}")
                parts.append("")

        return "\n".join(parts).strip()

    return _render_components(text, "CodexDocsOverviewLanding", repl)


def _render_tree_items(items: list[object], indent: int = 0) -> list[str]:
    """Recursively format FileTree hierarchy entries into indented text lines."""
    lines: list[str] = []
    prefix = "  " * indent
    for item in items:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name", ""))
        comment = item.get("comment", "")
        line = f"{prefix}{name}"
        if comment and isinstance(comment, str):
            line += f"  # {comment}"
        lines.append(line)
        children = item.get("children")
        if isinstance(children, list):
            lines.extend(_render_tree_items(children, indent + 1))
    return lines


def _convert_file_trees(text: str) -> str:
    """Convert <FileTree> components into indented ASCII directory trees in code blocks."""

    def repl(_text: str, block: _ComponentBlock) -> str:
        props = _parse_props(block.props)
        if props is None:
            return block.raw
        tree = props.get("tree", [])
        if not isinstance(tree, list):
            return ""
        tree_body = "\n".join(_render_tree_items(tree))
        return _fenced_block(tree_body, "text")

    return _render_components(text, "FileTree", repl)


def _convert_toggle_sections(text: str) -> str:
    """Convert <ToggleSection> components into standard HTML details blocks."""

    def repl(_text: str, block: _ComponentBlock) -> str:
        props = _parse_props(block.props)
        if props is None:
            return block.raw
        title = _unescape_js_string(props.get("title")).strip()
        body = _dedent_block(block.body)
        return f"<details>\n<summary>{title}</summary>\n\n{body}\n\n</details>"

    return _render_components(text, "ToggleSection", repl)


def _convert_pricing_cards(text: str) -> str:
    """Convert <PricingCard> components into structured Markdown sub-headings and lists.

    The component is indented to wherever it sits inside its parent MDX
    container, so the rendered block is emitted at column zero -- a heading
    indented by four or more spaces would render as an indented code block
    instead of a heading.
    """

    def repl(_text: str, block: _ComponentBlock) -> str:
        props = _parse_props(block.props)
        if props is None:
            return block.raw
        name = _unescape_js_string(props.get("name")) or "Plan"
        price = _unescape_js_string(props.get("price"))
        interval = _unescape_js_string(props.get("interval"))
        subtitle = _unescape_js_string(props.get("subtitle"))
        cta_label = _unescape_js_string(props.get("ctaLabel"))
        cta_href = _unescape_js_string(props.get("ctaHref"))
        body = _dedent_block(block.body)

        title = f"### {name}"
        if price:
            title += f" ({price}{interval})"

        parts = [title]
        if subtitle:
            parts.append(subtitle)
        if cta_label and cta_href:
            parts.append(f"[{cta_label}]({cta_href})")
        if body:
            parts.append(body)

        return "\n\n".join(parts)

    return _render_components(text, "PricingCard", repl)


def _convert_model_details(text: str) -> str:
    """Convert <ModelDetails> components into Markdown sub-headings and feature lists."""

    def repl(_text: str, block: _ComponentBlock) -> str:
        props = _parse_props(block.props)
        if props is None:
            return block.raw
        name = _unescape_js_string(props.get("name"))
        description = _unescape_js_string(props.get("description"))
        data = props.get("data", {})
        features = data.get("features", []) if isinstance(data, dict) else []

        parts: list[str] = []
        if name:
            parts.append(f"### `{name}`\n")
        if description:
            parts.append(f"{description}\n")

        feat_lines: list[str] = []
        if isinstance(features, list):
            for feat in features:
                if not isinstance(feat, dict):
                    continue
                f_title = _unescape_js_string(feat.get("title"))
                f_val = feat.get("value")
                if f_val is True:
                    feat_lines.append(f"- **{f_title}**: Supported")
                elif f_val is False:
                    feat_lines.append(f"- **{f_title}**: Not supported")
                elif f_val:
                    feat_lines.append(f"- **{f_title}**: {f_val}")
        if feat_lines:
            parts.append("\n".join(feat_lines))

        return "\n\n".join(parts)

    return _render_components(text, "ModelDetails", repl)


def _convert_config_tables(text: str) -> str:
    """Convert <ConfigTable> components into Markdown reference tables.

    Each entry carries a configuration key, its accepted type, and a
    description; rendering them as a three-column table keeps the reference
    searchable in plain Markdown instead of leaving the component's object
    literal in the page.
    """

    def repl(_text: str, block: _ComponentBlock) -> str:
        props = _parse_props(block.props)
        if props is None:
            return block.raw
        options = props.get("options", [])
        if not isinstance(options, list):
            # ``options`` is sometimes a bare identifier referring to a value
            # defined elsewhere in the app; there is no data to render, so the
            # component leaves no trace in the page.
            return ""
        rows: list[list[str]] = []
        for option in options:
            if not isinstance(option, dict):
                continue
            key = _unescape_js_string(option.get("key"))
            type_name = _unescape_js_string(option.get("type"))
            description = _unescape_js_string(option.get("description"))
            rows.append(
                [
                    f"`{_markdown_cell(key)}`",
                    f"`{_markdown_cell(type_name)}`",
                    _markdown_cell(description),
                ]
            )
        if not rows:
            return ""
        return _markdown_table(["Key", "Type", "Description"], rows)

    return _render_components(text, "ConfigTable", repl)


def _convert_glossary_tables(
    text: str,
    current_slug: str,
    known_slugs: set[str],
) -> str:
    """Convert <GlossaryTable> components into a term/definition Markdown table.

    Every entry links to the page that explains the term, resolved to the
    mirrored file when that page is part of this mirror and to the upstream
    documentation URL otherwise.
    """

    def repl(_text: str, block: _ComponentBlock) -> str:
        props = _parse_props(block.props)
        if props is None:
            return block.raw
        options = props.get("options", [])
        if not isinstance(options, list):
            return ""
        rows: list[list[str]] = []
        for option in options:
            if not isinstance(option, dict):
                continue
            term = _unescape_js_string(option.get("key"))
            href = _unescape_js_string(option.get("href"))
            applies_to = _unescape_js_string(option.get("appliesTo"))
            description = _unescape_js_string(option.get("description"))
            if href:
                term = f"[{_markdown_cell(term)}]({_resolve_internal_href(href, current_slug, known_slugs)})"
            else:
                term = _markdown_cell(term)
            rows.append([term, _markdown_cell(applies_to), _markdown_cell(description)])
        if not rows:
            return ""
        return _markdown_table(["Term", "Applies to", "Definition"], rows)

    return _render_components(text, "GlossaryTable", repl)


def _convert_plan_feature_matrices(
    text: str,
    current_slug: str,
    known_slugs: set[str],
) -> str:
    """Convert <CodexPlanFeatureMatrix> components into per-section Markdown tables.

    The component renders one column per plan and one row per capability,
    marking each cell with an availability state; the Markdown equivalent is a
    row of plan names followed by one row per feature. The feature's full name
    is used rather than its optional short label, because the abbreviated label
    only exists to fit the component's narrow columns.
    """

    def repl(_text: str, block: _ComponentBlock) -> str:
        props = _parse_props(block.props)
        if props is None:
            return block.raw
        data = props.get("data", {})
        if not isinstance(data, dict):
            return ""
        plans = data.get("plans", [])
        sections = data.get("sections", [])
        if not isinstance(plans, list) or not isinstance(sections, list):
            return ""

        plan_ids = [
            _unescape_js_string(plan.get("id"))
            for plan in plans
            if isinstance(plan, dict)
        ]
        plan_labels = [
            _unescape_js_string(plan.get("label"))
            or _unescape_js_string(plan.get("id"))
            for plan in plans
            if isinstance(plan, dict)
        ]
        if not plan_ids:
            return ""

        parts: list[str] = []
        for section in sections:
            if not isinstance(section, dict):
                continue
            title = _unescape_js_string(section.get("title"))
            if title:
                parts.append(f"### {title}\n")
            rows: list[list[str]] = []
            for feature in section.get("features", []):
                if not isinstance(feature, dict):
                    continue
                name = _unescape_js_string(feature.get("name"))
                href = _unescape_js_string(feature.get("href"))
                if href:
                    name = f"[{_markdown_cell(name)}]({_resolve_internal_href(href, current_slug, known_slugs)})"
                else:
                    name = _markdown_cell(name)
                availability = feature.get("availability", {})
                if not isinstance(availability, dict):
                    availability = {}
                cells = [
                    _availability_label(availability.get(plan_id))
                    for plan_id in plan_ids
                ]
                rows.append([name, *cells])
            if rows:
                parts.append(_markdown_table(["Feature", *plan_labels], rows))

        return "\n".join(parts).strip()

    return _render_components(text, "CodexPlanFeatureMatrix", repl)


def _convert_collection_lists(text: str) -> str:
    """Convert <CodexCollectionList> components into bulleted link lists.

    The component lists use-case collections by identifier. Its rendered form
    links each identifier under the documentation host's collection route, so
    the Markdown equivalent is a bulleted link list built from the same route:
    the identifiers are collection names, not Codex documentation routes, and
    resolving them as if they were would produce dead links.
    """

    def repl(_text: str, block: _ComponentBlock) -> str:
        props = _parse_props(block.props)
        if props is None:
            return block.raw
        slugs = props.get("slugs", [])
        if not isinstance(slugs, list):
            return ""
        items: list[str] = []
        for entry in slugs:
            slug = _unescape_js_string(entry)
            if not slug:
                continue
            label = slug.replace("-", " ").replace("/", " ").strip().capitalize()
            items.append(f"- [{label}]({COLLECTIONS_BASE_URL}/{slug})")
        return "\n".join(items)

    return _render_components(text, "CodexCollectionList", repl)


def _convert_prompt_components(text: str) -> str:
    """Convert <PromptComponent> components into fenced code blocks.

    The component shows a prompt the reader can copy; a fenced block preserves
    it verbatim, which is also what keeps its text out of the surrounding
    prose's inline formatting.
    """

    def repl(_text: str, block: _ComponentBlock) -> str:
        props = _parse_props(block.props)
        if props is None:
            return block.raw
        prompt = _unescape_js_string(props.get("prompt")).strip()
        if not prompt:
            return ""
        return _fenced_block(prompt)

    return _render_components(text, "PromptComponent", repl)


def _convert_table_wrappers(text: str) -> str:
    """Convert <TableWrapper> components into Markdown tables.

    The wrapper only adds horizontal scrolling around a plain HTML table, so
    its body is rewritten as a Markdown table with the same header, alignment,
    and cells. A body that does not parse as a table is unwrapped verbatim
    instead of being dropped, so an unrecognized markup shape degrades to raw
    HTML rather than to missing content.
    """

    def repl(_text: str, block: _ComponentBlock) -> str:
        rendered = _html_table_to_markdown(block.body)
        return rendered if rendered is not None else _dedent_block(block.body)

    return _render_components(text, "TableWrapper", repl)


def _content_mode_surfaces(props: str) -> list[str]:
    """Return the surface ids a <ContentModeSwitch> component is scoped to.

    The component declares either a single surface (``id="cli"``) or several
    (``ids="app,web,cli,ide"``); both spellings describe the same thing, so
    they are read into one list.
    """
    attributes = _parse_props(props)
    if attributes is None:
        return []
    single = _unescape_js_string(attributes.get("id"))
    if single:
        return [single]
    return [
        surface.strip()
        for surface in _unescape_js_string(attributes.get("ids")).split(",")
        if surface.strip()
    ]


def _convert_content_mode_switches(text: str) -> str:
    """Convert <ContentModeSwitch> sections into labeled, anchor-stable sections.

    Upstream renders one content variant per product surface and links to each
    variant with a surface-prefixed anchor (``#cli-codex-exec``). Unwrapping the
    component alone would drop that discriminator twice over: the reader sees
    the same heading repeated once per surface with no way to tell them apart,
    and every surface-prefixed link becomes unresolvable. Each variant is
    therefore labeled with the surface it belongs to and gets an explicit
    ``<a id="<surface>-<heading>">`` anchor in front of every heading it
    contains, reproducing the anchors upstream derives from the same component.
    """

    # How many times each anchor id has been emitted on this page. Upstream
    # repeats whole sections -- the same heading under the same surface -- so
    # the same id would be emitted twice, and a page may not carry two anchors
    # with one id. Only the first occurrence keeps the plain id, so links
    # written against upstream's anchor still land on the section they name;
    # the repeats are numbered.
    emitted: dict[str, int] = {}

    def anchor(surface: str, slug: str) -> str:
        anchor_id = f"{surface}-{slug}"
        count = emitted.get(anchor_id, 0) + 1
        emitted[anchor_id] = count
        return (
            f'<a id="{anchor_id}"></a>'
            if count == 1
            else f'<a id="{anchor_id}-{count}"></a>'
        )

    def repl(_text: str, block: _ComponentBlock) -> str:
        surfaces = _content_mode_surfaces(block.props)
        body = _dedent_block(block.body)
        if not surfaces or not body:
            return body

        parts: list[str] = []
        if len(surfaces) == 1:
            surface = surfaces[0]
            parts.append(f"**Surface: {SURFACE_LABELS.get(surface, surface)}**\n")
        for line in body.splitlines():
            heading = re.match(r"^#{1,6}\s+(.+?)\s*$", line)
            if heading:
                slug = _heading_slug(heading.group(1))
                # One anchor per surface the section applies to, so a link to
                # any of them lands on the same (single) rendered section.
                parts.extend(anchor(surface, slug) for surface in surfaces)
                parts.append("")
            parts.append(line)
        return "\n".join(parts)

    return _render_components(text, "ContentModeSwitch", repl)


def _unwrap_containers(text: str) -> str:
    """Unwrap layout-only container components, keeping their Markdown content.

    The container is MDX layout, not documentation: what matters is the
    Markdown it wraps. Its body is de-indented on the way out, because the
    indentation that made sense inside the component would render as a code
    block once the component is gone.
    """

    def repl(_text: str, block: _ComponentBlock) -> str:
        return _dedent_block(block.body) if not block.self_closing else ""

    for name in CONTAINER_COMPONENT_NAMES:
        text = _render_components(text, name, repl)
    return text


def _strip_visual_components(text: str) -> str:
    """Remove decorative components that carry no documentation text.

    Only self-closing occurrences are removed. A component from this list used
    as a container would carry Markdown between its tags, and dropping it would
    silently delete that content -- such a tag is left in place for the remnant
    scan to report instead.
    """

    def repl(_text: str, block: _ComponentBlock) -> str:
        if block.self_closing:
            return ""
        return block.raw

    for name in VISUAL_COMPONENT_NAMES:
        text = _render_components(text, name, repl)
    return text


def _iter_html_elements(html: str, names: str) -> Iterator[tuple[str, str, str]]:
    """Yield ``(name, attributes, content)`` for every element in *html*.

    *names* is a regex alternation of element names (``"th|td"``), matched
    directly after the ``<``. Tag boundaries come from the same scanner the JSX
    components use, because an attribute value may itself contain ``>``
    (``<td title="a > b">``): a ``[^>]*`` character class ends the tag inside
    that value and cuts the element -- and the cell it holds -- at the ``>``.

    Elements are yielded with their own content, not their descendants': a
    nested table inside a cell ends the enclosing row at the inner row's
    closing tag, so its markup is flattened into the text of the cell that
    holds it rather than rendered as a table of its own.
    """
    open_re = re.compile(rf"<({names})\b")
    position = 0
    while (match := open_re.search(html, position)) is not None:
        tag_end = _find_tag_end(html, match.start())
        if tag_end is None:
            return
        close_match = re.compile(rf"</{re.escape(match.group(1))}>").search(
            html, tag_end
        )
        if close_match is None:
            return
        yield (
            match.group(1),
            html[match.end() : tag_end - 1],
            html[tag_end : close_match.start()],
        )
        position = close_match.end()


def _html_table_to_markdown(html: str) -> str | None:
    """Render the rows of a plain HTML table body as a Markdown table.

    Returns ``None`` when the body holds no rows, which tells the caller to
    keep the original markup. Only the elements the wrapper is used with are
    understood (``tr``/``th``/``td`` plus the usual grouping elements); any
    other markup inside a cell is flattened to its text content.
    """
    header: list[str] = []
    header_styles: list[str] = []
    body: list[list[str]] = []
    for _, _, row_content in _iter_html_elements(html, "tr"):
        cells: list[str] = []
        styles: list[str] = []
        is_header_row = False
        for tag, attributes, content in _iter_html_elements(row_content, "th|td"):
            is_header_row = is_header_row or tag == "th"
            cells.append(_markdown_cell(re.sub(r"<[^>]+>", " ", content)))
            styles.append(attributes)
        if not cells:
            continue
        if is_header_row and not header:
            header, header_styles = cells, styles
        else:
            body.append(cells)

    if not header and not body:
        return None

    width = max((len(cells) for cells in [header, *body]), default=0)
    header = [*header, *[""] * (width - len(header))]
    header_styles = [*header_styles, *[""] * (width - len(header_styles))]

    # Column alignment comes from the header cells' inline style, the only
    # alignment signal the upstream markup carries.
    separator: list[str] = []
    for style in header_styles:
        if "text-align:center" in style:
            separator.append(":---:")
        elif "text-align:right" in style:
            separator.append("---:")
        else:
            separator.append("---")

    lines = [
        "| " + " | ".join(header) + " |",
        "| " + " | ".join(separator) + " |",
    ]
    lines.extend(
        "| " + " | ".join([*cells, *[""] * (width - len(cells))]) + " |"
        for cells in body
    )
    return "\n".join(lines)


def _clean_mdx_components(
    text: str,
    current_slug: str,
    known_slugs: set[str] | None = None,
) -> str:
    """Transform custom Astro/MDX components into standard CommonMark.

    1. Shields fenced code blocks from modification.
    2. Removes JSX comments ({/* ... */}) and collapses whitespace-only lines.
    3. Unwraps layout containers (<WorkflowSteps>, <Tabs>, <TabItem>,
       <ContentSwitcher>) and de-indents what they wrapped.
    4. Converts <ToggleSection> components into HTML <details> blocks.
    5. Converts <ContentModeSwitch> sections into labeled, anchor-stable sections.
    6. Converts data components: <CodexDocsOverviewLanding>, <FileTree>,
       <ModelDetails>, <PricingCard>, <ConfigTable>, <GlossaryTable>,
       <CodexPlanFeatureMatrix>, <CodexCollectionList>, <PromptComponent>,
       <TableWrapper>.
    7. Converts callout components (<WarningTip>, <Alert>, <CodexCallout>) into blockquotes.
    8. Converts inline components (<CtaPillLink>, <ButtonLink>, <CodexMicroTableKeycap>).
    9. Converts media components (<VideoPlayer>, <CodexScreenshot>).
    10. Strips decorative components that carry no documentation text.
    11. Normalizes whitespace and restores shielded code blocks.
    """
    if known_slugs is None:
        known_slugs = _KNOWN_SLUGS

    protected_text, code_blocks = _protect_fenced_code(text)

    # Strip JSX comments {/* ... */}
    cleaned = re.sub(r"\{\s*/\*.*?\*/\s*\}", "", protected_text, flags=re.DOTALL)
    cleaned = _collapse_whitespace_lines(cleaned)

    # Structural conversion comes first: unwrapping and de-indenting the
    # layout containers is what puts the components they hold at the column
    # the surrounding document uses, so the blocks they render are laid out
    # as Markdown blocks rather than as indented text.
    cleaned = _unwrap_containers(cleaned)
    cleaned = _convert_toggle_sections(cleaned)
    cleaned = _convert_content_mode_switches(cleaned)

    # Component conversions
    cleaned = _convert_overview_landing(cleaned, current_slug, known_slugs)
    cleaned = _convert_file_trees(cleaned)
    cleaned = _convert_model_details(cleaned)
    cleaned = _convert_pricing_cards(cleaned)
    cleaned = _convert_config_tables(cleaned)
    cleaned = _convert_glossary_tables(cleaned, current_slug, known_slugs)
    cleaned = _convert_plan_feature_matrices(cleaned, current_slug, known_slugs)
    cleaned = _convert_collection_lists(cleaned)
    cleaned = _convert_prompt_components(cleaned)
    cleaned = _convert_table_wrappers(cleaned)

    # Convert WarningTip to GitHub alert blockquote
    def warning_tip_repl(_text: str, block: _ComponentBlock) -> str:
        inner = _dedent_block(block.body)
        lines = [f"> {line}" if line else ">" for line in inner.splitlines()]
        return "> [!WARNING]\n" + "\n".join(lines)

    cleaned = _render_components(cleaned, "WarningTip", warning_tip_repl)

    # Convert Alert to blockquote
    def alert_repl(_text: str, block: _ComponentBlock) -> str:
        props = _parse_props(block.props)
        if props is None:
            return block.raw
        desc = _unescape_js_string(props.get("description"))
        return f"> [!NOTE]\n> {desc}" if desc else ""

    cleaned = _render_components(cleaned, "Alert", alert_repl)

    # Convert CtaPillLink to Markdown link
    def cta_pill_repl(_text: str, block: _ComponentBlock) -> str:
        props = _parse_props(block.props)
        if props is None:
            return block.raw
        href = _unescape_js_string(props.get("href"))
        label = _unescape_js_string(props.get("label"))
        if href and label:
            return (
                f"[{label}]({_resolve_internal_href(href, current_slug, known_slugs)})"
            )
        return ""

    cleaned = _render_components(cleaned, "CtaPillLink", cta_pill_repl)

    # Convert ButtonLink to Markdown link
    def button_link_repl(_text: str, block: _ComponentBlock) -> str:
        props = _parse_props(block.props)
        if props is None:
            return block.raw
        btn_text = block.body.strip()
        href = _unescape_js_string(props.get("href"))
        if href:
            return f"[{btn_text}]({_resolve_internal_href(href, current_slug, known_slugs)})"
        return btn_text

    cleaned = _render_components(cleaned, "ButtonLink", button_link_repl)

    # Convert CodexCallout to blockquote
    def callout_repl(_text: str, block: _ComponentBlock) -> str:
        props = _parse_props(block.props)
        if props is None:
            return block.raw
        title = _unescape_js_string(props.get("title"))
        desc = _unescape_js_string(props.get("description"))
        href = _unescape_js_string(props.get("href"))
        if title and href:
            resolved = _resolve_internal_href(href, current_slug, known_slugs)
            return f"> **[{title}]({resolved})**\n>\n> {desc}"
        return ""

    cleaned = _render_components(cleaned, "CodexCallout", callout_repl)

    # Convert CodexMicroTableKeycap to bold text
    def keycap_repl(_text: str, block: _ComponentBlock) -> str:
        props = _parse_props(block.props)
        label = _unescape_js_string(props.get("label")) if props else ""
        return f"**{label}**" if label else ""

    cleaned = _render_components(cleaned, "CodexMicroTableKeycap", keycap_repl)

    # Convert VideoPlayer to Markdown video link
    def video_repl(_text: str, block: _ComponentBlock) -> str:
        props = _parse_props(block.props)
        src = _unescape_js_string(props.get("src")) if props else ""
        if src:
            video_url = (
                f"https://developers.openai.com{src}" if src.startswith("/") else src
            )
            return f"[Video Demo]({video_url})"
        return ""

    cleaned = _render_components(cleaned, "VideoPlayer", video_repl)

    # Convert CodexScreenshot to Markdown image
    def screenshot_repl(_text: str, block: _ComponentBlock) -> str:
        props = _parse_props(block.props)
        src = _unescape_js_string(props.get("src")) if props else ""
        alt = (_unescape_js_string(props.get("alt")) if props else "") or "Screenshot"
        if not src:
            return ""
        img_url = f"https://developers.openai.com{src}" if src.startswith("/") else src
        return f"![{alt}]({img_url})"

    cleaned = _render_components(cleaned, "CodexScreenshot", screenshot_repl)

    # Strip decorative and client-interactive components
    cleaned = _strip_visual_components(cleaned)

    # Normalize whitespace: whitespace-only lines appear wherever a component
    # tag was removed from its own line, and runs of blank lines appear
    # wherever a whole block was removed.
    cleaned = _collapse_whitespace_lines(cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)

    return _restore_fenced_code(cleaned, code_blocks)


def _collapse_whitespace_lines(text: str) -> str:
    """Replace whitespace-only lines with empty ones.

    An MDX component that occupied a whole line leaves its indentation behind
    when the tag is removed, and the upstream sources are full of lines that
    hold nothing but the indentation of a block that used to follow. Those
    lines are invisible in a rendered document but they end paragraphs and
    list items all the same, and they make the mirrored files noisy to diff.
    """
    return _BLANK_WHITESPACE_LINE_RE.sub("", text)


def _strip_frontmatter(text: str) -> str:
    """Replace a leading Astro frontmatter block with an equivalent H1 heading.

    A few upstream pages carry a YAML frontmatter block at the very top. Its
    keys are build instructions for the upstream site (``hidden: true`` keeps
    the page out of their navigation) and mean nothing in a mirror, so the
    block is dropped -- but its ``title`` is the page's real title, and the
    manifest title is extracted from the body, so the title is re-emitted as a
    level-one heading rather than lost.

    The block is only dropped when it reads as YAML. A document that opens with
    a thematic break (``---``, then a blank line, then prose, then ``---``)
    matches the same shape, and treating that as frontmatter would delete its
    middle section from the mirrored page.
    """
    match = re.match(
        r"\A---[ \t]*\r?\n(.*?)\r?\n---[ \t]*(?:\r?\n|\Z)", text, re.DOTALL
    )
    if match is None:
        return text
    block = match.group(1)
    if block.startswith(("\n", "\r")) or not _FRONTMATTER_KEY_RE.search(block):
        return text
    title_match = re.search(r"^title:[ \t]*(?P<title>.+?)[ \t]*$", block, re.MULTILINE)
    body = text[match.end() :]
    if title_match is None:
        return body
    title = title_match.group("title").strip().strip("'\"")
    # A body that already opens with a level-one heading keeps it; anything
    # else gets the frontmatter title as its H1, which is also what the
    # manifest reads the page title from.
    if not title or re.match(r"#\s", body.lstrip()):
        return body
    return f"# {title}\n\n{body}"


def fetch_markdown(client: httpx.Client, page: Page) -> tuple[str, str]:
    """Fetch raw markdown from upstream and resolve reference stubs to .md twins.

    1. For pages discovered via llms.txt (or not served from raw.githubusercontent.com),
       fetches validated markdown directly from `page.source_md_url`.
    2. For GitHub pages:
       - Fetches raw Markdown from GitHub (`page.source_md_url`).
       - Resolves pure reference stubs and hybrid composite pages (such as `config.md`)
         by fetching their `.md` twin endpoints with route normalization and anchor stripping.
       - Falls back gracefully to original text with a stderr warning if the external fetch fails.
    3. Drops the upstream site's YAML frontmatter, keeping its title as a heading.
    4. Cleans custom Astro and MDX components (converting overview landing pages,
       rendering file trees as ASCII code blocks, converting data tables and
       matrices, labeling surface-specific sections, and stripping visual badges).
    5. Rewrites relative links pointing to repository root files outside docs/
       (`../SECURITY.md` and `../LICENSE`, with or without `#anchor`) to canonical upstream GitHub URLs.
    6. Rewrites cross-documentation absolute links to relative links for known slugs,
       and body-text site-absolute or skipped-stub links through the same resolution.
       These link passes run with fenced code blocks shielded, so a link written
       inside a code example reaches the mirrored page unchanged.
    7. Returns `(text, content_hash(text))`.

    The link passes of step 6 resolve each reference against the pages the
    current run mirrors, so the hook refuses to run without that set (see
    ``ensure_known_slugs``): with an empty one every internal link would be
    rewritten to its upstream URL and the manifest would record the result as
    the page's correct content. The guard runs BEFORE the download, so a hook
    invoked without discovery fails immediately instead of fetching every page
    first and failing on each one in turn.

    Raises:
        fetch.FetchError: When no discovered slug set is available.
    """
    ensure_known_slugs("codex-cli", _KNOWN_SLUGS, page.slug)

    raw_text, _ = fetch.fetch_validated(client, page.source_md_url)
    if (
        page.source_id.startswith("llms:")
        or "raw.githubusercontent.com" not in page.source_md_url
    ):
        text = raw_text
    else:
        stub_link = _STUB_MD_LINK_RE.search(raw_text)
        if stub_link is None:
            text = raw_text
        elif _is_pure_stub(raw_text):
            text = _fetch_pure_stub(client, raw_text, page, stub_link)
        else:
            text = _fetch_hybrid_page(client, raw_text, page)

    text = _strip_frontmatter(text)
    text = _clean_mdx_components(text, page.slug)
    # The component conversion restored the fenced blocks on its way out, so
    # they are shielded once more around the link rewrites: a code example
    # showing a link is an illustration of a link, not a link to follow.
    protected_text, code_blocks = _protect_fenced_code(text)
    protected_text = _rewrite_root_link(protected_text)
    protected_text = _rewrite_cross_links(protected_text, page.slug)
    protected_text = _rewrite_body_links(protected_text, page.slug)
    text = _restore_fenced_code(protected_text, code_blocks)
    return text, fetch.content_hash(text)
