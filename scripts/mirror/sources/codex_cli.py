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

No whats-new for this source.
"""

from __future__ import annotations

import json
import posixpath
import re
import sys
from typing import TYPE_CHECKING
from urllib.parse import urlparse

from ..core import fetch
from ..core.github import fetch_git_tree, fetch_latest_release_tag
from ..core.page import Page
from .base import SourceConfig, try_make_page, warn_duplicate_slug

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

CONFIG = SourceConfig(
    name="codex-cli",
    title="Codex CLI",
    home_url=f"https://github.com/{REPO}",
    generate_whats_new=False,
    version="0.147.0",
    origin=f"github.com/{REPO} (`docs/`)",
    how_mirrored="scraping (GitHub tree + developers.openai.com/codex/llms.txt)",
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

# Maintained and populated during discover() to record all known slugs for cross-link rewriting.
_KNOWN_SLUGS: set[str] = set()


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
    4. Updates the module-level ``_KNOWN_SLUGS`` set.
    5. Raises ``RuntimeError`` when discovery finds zero pages (zero-page guard).
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

    pages.sort(key=lambda p: p.slug)
    if not pages:
        raise RuntimeError(
            f"No Markdown files found directly under {DOCS_PREFIX!r}/ in "
            f"{REPO}@{BRANCH} or via {LLMS_TXT_URL}. A zero-page discovery would "
            "delete all mirrored files."
        )

    _KNOWN_SLUGS.clear()
    _KNOWN_SLUGS.update(p.slug for p in pages)
    return pages


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
    preserves any anchor fragment. Unmatched or unknown links are left intact.
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

        # Check against known slugs, including guides/ prefix fallback for /guides/ routes
        if target_slug not in known_slugs:
            if f"guides/{target_slug}" in known_slugs:
                target_slug = f"guides/{target_slug}"
            else:
                return match.group(0)

        current_dir = posixpath.dirname(current_slug) or "."
        rel_path = posixpath.relpath(f"{target_slug}.md", current_dir)
        if not rel_path.startswith((".", "/")):
            rel_path = f"./{rel_path}"
        new_target = f"{rel_path}{anchor}"
        return f"[{link_text}]({new_target})"

    return _CROSS_DOC_LINK_RE.sub(replace, text)


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


def _protect_fenced_code(text: str) -> tuple[str, list[str]]:
    """Protect fenced code blocks by replacing them with unique placeholder tokens.

    Shields code examples (in ``` or ~~~ fences) from subsequent MDX transformations,
    such as component tag stripping or link rewriting, and returns the protected
    text alongside the list of original code block strings.
    """
    code_blocks: list[str] = []

    def repl(match: re.Match[str]) -> str:
        code_blocks.append(match.group(0))
        return f"<!--__FENCED_CODE_BLOCK_{len(code_blocks) - 1}__-->"

    fenced_re = re.compile(r"(```[^\n]*\n.*?```|~~~[^\n]*\n.*?~~~)", re.DOTALL)
    return fenced_re.sub(repl, text), code_blocks


def _restore_fenced_code(text: str, code_blocks: list[str]) -> str:
    """Restore previously protected fenced code blocks from placeholder tokens."""
    for i, block in enumerate(code_blocks):
        text = text.replace(f"<!--__FENCED_CODE_BLOCK_{i}__-->", block)
    return text


def _tokenize_js_props(raw_props: str) -> list[tuple[str, str]]:
    """Tokenize JavaScript object and array literals embedded in JSX component props.

    Recognizes quoted strings, numbers, punctuation (braces, brackets, colons, commas),
    operators (equals), and identifiers or keyword values.
    """
    tokens: list[tuple[str, str]] = []
    token_re = re.compile(
        r"""
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

    def parse_value(self) -> object:
        """Parse a single JavaScript literal value (string, number, boolean, array, or object)."""
        kind, val = self.peek()
        if kind == "STRING" and val is not None:
            self.next()
            if val.startswith("'"):
                val = val[1:-1].replace("\\'", "'").replace('"', '\\"')
                return val
            return json.loads(val)
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
            if kind in ("WORD", "STRING") and val is not None:
                self.next()
                key = val if kind == "WORD" else json.loads(val)
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
    If the target is external or unknown, falls back to the canonical upstream URL.
    """
    href_clean, _, query = href.partition("?")
    href_path, _, anchor = href_clean.partition("#")

    if href_path.startswith("/codex/"):
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
    overview_re = re.compile(
        r"<CodexDocsOverviewLanding\b([^>]*?)(?:/>|>(.*?)</CodexDocsOverviewLanding>)",
        re.DOTALL,
    )

    def repl(match: re.Match[str]) -> str:
        raw_props = match.group(1)
        tokens = _tokenize_js_props(raw_props)
        parser = _JSParser(tokens)
        try:
            props = parser.parse_jsx_props()
        except Exception:
            return match.group(0)

        parts: list[str] = []
        title = props.get("title")
        description = props.get("description")
        intro = props.get("intro")
        primary_cta = props.get("primaryCta")
        sections = props.get("sections", [])

        # Ensure top-level H1 heading exists if not already present in the preceding text
        if not re.search(r"^#\s+", text[: match.start()], re.MULTILINE) and title:
            parts.append(f"# {title}\n")

        if description and isinstance(description, str):
            parts.append(f"{description}\n")
        if intro and isinstance(intro, str) and intro != description:
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
                sec_title = str(sec.get("title", ""))
                sec_desc = sec.get("description", "")
                pages = sec.get("pages", [])

                parts.append(f"## {sec_title}\n")
                if sec_desc and isinstance(sec_desc, str):
                    parts.append(f"{sec_desc}\n")

                if isinstance(pages, list):
                    for page in pages:
                        if not isinstance(page, dict):
                            continue
                        p_title = str(page.get("title", ""))
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

    return overview_re.sub(repl, text)


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
    filetree_re = re.compile(r"<FileTree\b([^>]*?)(?:/>|>(.*?)</FileTree>)", re.DOTALL)

    def repl(match: re.Match[str]) -> str:
        raw_props = match.group(1)
        tokens = _tokenize_js_props(raw_props)
        parser = _JSParser(tokens)
        try:
            props = parser.parse_jsx_props()
        except Exception:
            return match.group(0)
        tree = props.get("tree", [])
        if not isinstance(tree, list):
            return ""
        rendered_lines = _render_tree_items(tree)
        tree_body = "\n".join(rendered_lines)
        return f"```text\n{tree_body}\n```"

    return filetree_re.sub(repl, text)


def _convert_toggle_sections(text: str) -> str:
    """Convert <ToggleSection> components into standard HTML details blocks."""
    toggle_re = re.compile(
        r"""<ToggleSection\s+title=["']([^"']+)["']\s*>(.*?)</ToggleSection>""",
        re.DOTALL,
    )

    def repl(match: re.Match[str]) -> str:
        title = match.group(1).strip()
        body = match.group(2).strip()
        return f"<details>\n<summary>{title}</summary>\n\n{body}\n\n</details>"

    return toggle_re.sub(repl, text)


def _convert_pricing_cards(text: str) -> str:
    """Convert <PricingCard> components into structured Markdown sub-headings and lists."""
    pricing_re = re.compile(
        r"<PricingCard\b([^>]*?)(?:/>|>(.*?)</PricingCard>)", re.DOTALL
    )

    def repl(match: re.Match[str]) -> str:
        raw = match.group(1)
        body = (match.group(2) or "").strip()
        name_m = re.search(r'name="([^"]+)"', raw)
        price_m = re.search(r'price="([^"]+)"', raw)
        interval_m = re.search(r'interval="([^"]+)"', raw)
        subtitle_m = re.search(r'subtitle="([^"]+)"', raw)
        cta_label_m = re.search(r'ctaLabel="([^"]+)"', raw)
        cta_href_m = re.search(r'ctaHref="([^"]+)"', raw)

        name = name_m.group(1) if name_m else "Plan"
        price = price_m.group(1) if price_m else ""
        interval = interval_m.group(1) if interval_m else ""
        subtitle = subtitle_m.group(1) if subtitle_m else ""
        cta_label = cta_label_m.group(1) if cta_label_m else ""
        cta_href = cta_href_m.group(1) if cta_href_m else ""

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

    return pricing_re.sub(repl, text)


def _convert_model_details(text: str) -> str:
    """Convert <ModelDetails> components into Markdown sub-headings and feature lists."""
    model_re = re.compile(
        r"<ModelDetails\b([^>]*?)(?:/>|>(.*?)</ModelDetails>)", re.DOTALL
    )

    def repl(match: re.Match[str]) -> str:
        raw = match.group(1)
        toks = _tokenize_js_props(raw)
        parser = _JSParser(toks)
        props = parser.parse_jsx_props()
        name = props.get("name", "")
        description = props.get("description", "")
        data = props.get("data", {})
        features = data.get("features", []) if isinstance(data, dict) else []

        parts: list[str] = []
        if name:
            parts.append(f"### `{name}`\n")
        if description and isinstance(description, str):
            parts.append(f"{description}\n")

        feat_lines: list[str] = []
        if isinstance(features, list):
            for feat in features:
                if not isinstance(feat, dict):
                    continue
                f_title = str(feat.get("title", ""))
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

    return model_re.sub(repl, text)


def _clean_mdx_components(
    text: str,
    current_slug: str,
    known_slugs: set[str] | None = None,
) -> str:
    """Transform custom Astro/MDX components into standard CommonMark.

    1. Shields fenced code blocks from modification.
    2. Removes JSX comments ({/* ... */}).
    3. Converts <CodexDocsOverviewLanding> components into structured outlines.
    4. Converts <FileTree> components into indented ASCII directory trees in code blocks.
    5. Converts <ToggleSection> components into HTML <details> blocks.
    6. Converts <ModelDetails> and <PricingCard> components into Markdown sections.
    7. Converts callout components (<WarningTip>, <Alert>, <CodexCallout>) into blockquotes.
    8. Converts inline components (<CtaPillLink>, <ButtonLink>, <CodexMicroTableKeycap>).
    9. Converts media components (<VideoPlayer>, <CodexScreenshot>).
    10. Unwraps container tags (<ContentModeSwitch>, <WorkflowSteps>, <Tabs>, <TabItem>, <ContentSwitcher>).
    11. Strips decorative badges and client-interactive tags (<ElevatedRiskBadge>, <ConfigTable>, etc.).
    12. Normalizes whitespace and restores shielded code blocks.
    """
    if known_slugs is None:
        known_slugs = _KNOWN_SLUGS

    protected_text, code_blocks = _protect_fenced_code(text)

    # Strip JSX comments {/* ... */}
    cleaned = re.sub(r"\{\s*/\*.*?\*/\s*\}", "", protected_text, flags=re.DOTALL)

    # Component conversions
    cleaned = _convert_overview_landing(cleaned, current_slug, known_slugs)
    cleaned = _convert_file_trees(cleaned)
    cleaned = _convert_toggle_sections(cleaned)
    cleaned = _convert_model_details(cleaned)
    cleaned = _convert_pricing_cards(cleaned)

    # Unwrap structural containers
    cleaned = re.sub(
        r"</?(?:ContentModeSwitch|WorkflowSteps|Tabs|TabItem|ContentSwitcher)\b[^>]*>",
        "",
        cleaned,
    )

    # Convert WarningTip to GitHub alert blockquote
    def warning_tip_repl(match: re.Match[str]) -> str:
        inner = match.group(1).strip()
        lines = [f"> {line}" if line else ">" for line in inner.splitlines()]
        return "> [!WARNING]\n" + "\n".join(lines)

    cleaned = re.sub(
        r"<WarningTip\b[^>]*>(.*?)</WarningTip>",
        warning_tip_repl,
        cleaned,
        flags=re.DOTALL,
    )

    # Convert Alert to blockquote
    def alert_repl(match: re.Match[str]) -> str:
        raw = match.group(1)
        desc_m = re.search(r'description="([^"]+)"', raw)
        desc = desc_m.group(1) if desc_m else ""
        return f"> [!NOTE]\n> {desc}" if desc else ""

    cleaned = re.sub(
        r"<Alert\b([^>]*?)(?:/>|>(.*?)</Alert>)",
        alert_repl,
        cleaned,
        flags=re.DOTALL,
    )

    # Convert CtaPillLink to Markdown link
    def cta_pill_repl(match: re.Match[str]) -> str:
        raw = match.group(1)
        href_m = re.search(r'href="([^"]+)"', raw)
        label_m = re.search(r'label="([^"]+)"', raw)
        if href_m and label_m:
            href = _resolve_internal_href(href_m.group(1), current_slug, known_slugs)
            return f"[{label_m.group(1)}]({href})"
        return ""

    cleaned = re.sub(
        r"<CtaPillLink\b([^>]*?)(?:/>|>(.*?)</CtaPillLink>)",
        cta_pill_repl,
        cleaned,
        flags=re.DOTALL,
    )

    # Convert ButtonLink to Markdown link
    def button_link_repl(match: re.Match[str]) -> str:
        raw = match.group(1)
        btn_text = match.group(2).strip()
        href_m = re.search(r'href="([^"]+)"', raw)
        if href_m:
            href = _resolve_internal_href(href_m.group(1), current_slug, known_slugs)
            return f"[{btn_text}]({href})"
        return btn_text

    cleaned = re.sub(
        r"<ButtonLink\b([^>]*?)>(.*?)</ButtonLink>",
        button_link_repl,
        cleaned,
        flags=re.DOTALL,
    )

    # Convert CodexCallout to blockquote
    def callout_repl(match: re.Match[str]) -> str:
        raw = match.group(1)
        href_m = re.search(r'href="([^"]+)"', raw)
        title_m = re.search(r'title="([^"]+)"', raw)
        desc_m = re.search(r'description="([^"]+)"', raw)
        title = title_m.group(1) if title_m else ""
        desc = desc_m.group(1) if desc_m else ""
        href = (
            _resolve_internal_href(href_m.group(1), current_slug, known_slugs)
            if href_m
            else ""
        )
        if title and href:
            return f"> **[{title}]({href})**\n>\n> {desc}"
        return ""

    cleaned = re.sub(
        r"<CodexCallout\b([^>]*?)(?:/>|>(.*?)</CodexCallout>)",
        callout_repl,
        cleaned,
        flags=re.DOTALL,
    )

    # Convert CodexMicroTableKeycap to bold text
    cleaned = re.sub(
        r'<CodexMicroTableKeycap\b[^>]*label="([^"]+)"[^>]*?/?>',
        r"**\1**",
        cleaned,
    )

    # Convert VideoPlayer to Markdown video link
    def video_repl(match: re.Match[str]) -> str:
        raw = match.group(1)
        src_m = re.search(r'src="([^"]+)"', raw)
        if src_m:
            src = src_m.group(1)
            video_url = (
                f"https://developers.openai.com{src}" if src.startswith("/") else src
            )
            return f"[Video Demo]({video_url})"
        return ""

    cleaned = re.sub(
        r"<VideoPlayer\b([^>]*?)(?:/>|>(.*?)</VideoPlayer>)",
        video_repl,
        cleaned,
        flags=re.DOTALL,
    )

    # Convert CodexScreenshot to Markdown image
    def screenshot_repl(match: re.Match[str]) -> str:
        raw = match.group(1)
        src_m = re.search(r'src="([^"]+)"', raw)
        alt_m = re.search(r'alt="([^"]+)"', raw)
        src = src_m.group(1) if src_m else ""
        alt = alt_m.group(1) if alt_m else "Screenshot"
        img_url = f"https://developers.openai.com{src}" if src.startswith("/") else src
        return f"![{alt}]({img_url})" if src else ""

    cleaned = re.sub(
        r"<CodexScreenshot\b([^>]*?)(?:/>|>(.*?)</CodexScreenshot>)",
        screenshot_repl,
        cleaned,
        flags=re.DOTALL,
    )

    # Strip visual-only and client-interactive tags
    cleaned = re.sub(
        r"<(?:ElevatedRiskBadge|CodexModelSwitcher|CodexAppDownloadCta|ConfigTable)\b[^>]*?/?>",
        "",
        cleaned,
    )

    # Normalize excess blank lines
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)

    return _restore_fenced_code(cleaned, code_blocks)


def fetch_markdown(client: httpx.Client, page: Page) -> tuple[str, str]:
    """Fetch raw markdown from upstream and resolve reference stubs to .md twins.

    1. For pages discovered via llms.txt (or not served from raw.githubusercontent.com),
       fetches validated markdown directly from `page.source_md_url`.
    2. For GitHub pages:
       - Fetches raw Markdown from GitHub (`page.source_md_url`).
       - Resolves pure reference stubs and hybrid composite pages (such as `config.md`)
         by fetching their `.md` twin endpoints with route normalization and anchor stripping.
       - Falls back gracefully to original text with a stderr warning if the external fetch fails.
    3. Cleans custom Astro and MDX components (converting overview landing pages,
       rendering file trees as ASCII code blocks, unwrapping surface switches,
       converting toggle sections to collapsible HTML, and stripping visual badges).
    4. Rewrites relative links pointing to repository root files outside docs/
       (`../SECURITY.md` and `../LICENSE`, with or without `#anchor`) to canonical upstream GitHub URLs.
    5. Rewrites cross-documentation absolute links to relative links for known slugs.
    6. Returns `(text, content_hash(text))`.
    """
    if (
        page.source_id.startswith("llms:")
        or "raw.githubusercontent.com" not in page.source_md_url
    ):
        raw_text, _ = fetch.fetch_validated(client, page.source_md_url)
        text = raw_text
    else:
        raw_text, _ = fetch.fetch_validated(client, page.source_md_url)
        if _STUB_MD_LINK_RE.search(raw_text):
            if _is_pure_stub(raw_text):
                match = _STUB_MD_LINK_RE.search(raw_text)
                assert match is not None
                text = _fetch_pure_stub(client, raw_text, page, match)
            else:
                text = _fetch_hybrid_page(client, raw_text, page)
        else:
            text = raw_text

    text = _clean_mdx_components(text, page.slug)
    text = _rewrite_root_link(text)
    text = _rewrite_cross_links(text, page.slug)
    return text, fetch.content_hash(text)
