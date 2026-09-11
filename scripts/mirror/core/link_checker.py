"""Automated verification of internal and relative Markdown links.

This module provides offline link-checking functionality across mirrored
documentation trees. It scans Markdown files, extracts local relative links,
and validates that their targets exist on disk (as individual files or as
directories containing an index or README document).

Deliberate design choices:
* **Zero external dependencies**: Built entirely on the Python 3.14 standard
  library (``pathlib``, ``re``, ``dataclasses``, ``urllib.parse``).
* **Code-fence awareness**: Ignores hyperlinks located within Markdown fenced
  code blocks (both backtick and tilde variants) as well as inline code spans.
* **External URL filtering**: Automatically ignores external web protocols
  (``http://``, ``https://``, ``ftp://``), special URL schemes (``mailto:``,
  ``data:``, ``javascript:``, ``tel:``, ``sms:``, ``irc:``), protocol-relative
  links (``//...``), and pure page anchor fragments (``#heading``).
* **Site-absolute detection**: Reports a destination that starts at the site
  root (``/docs/en/hooks``) as an issue rather than skipping it. Such a path
  cannot resolve from a mirrored file, so it is always a defect: either the
  adapter failed to rewrite it or upstream introduced a new one. Both the
  Markdown link syntax and the inline HTML ``href``/``src`` attributes a page
  passes through are read, because a site-absolute path is just as dead
  whichever syntax carries it.
* **Directory target support**: Resolves directory targets by checking for
  the presence of ``README.md`` or ``index.md``.
* **Illustrative exemptions**: Each source may declare relative destinations
  that its pages use inside documentation samples rather than as real
  cross-references (see ``sources.base.SourceConfig``). The caller passes
  those lists in; nothing here knows about any concrete source.
"""

from __future__ import annotations

import bisect
import re
import urllib.parse
from collections.abc import Collection, Mapping
from dataclasses import dataclass
from pathlib import Path

from .. import config

# Schemes that indicate external destinations or non-file URI protocols.
_EXTERNAL_SCHEMES = frozenset(
    {
        "http",
        "https",
        "mailto",
        "ftp",
        "data",
        "javascript",
        "tel",
        "sms",
        "irc",
        "git",
        "ssh",
        "vscode",
        "cursor",
        "vscodium",
        "windsurf",
        "zed",
        "codex",
    }
)

# Regular expression matching Markdown fenced code block boundaries.
# Matches 0-3 leading spaces, followed by 3 or more backticks or tildes.
_FENCE_START_RE = re.compile(r"^[ ]{0,3}(?P<fence>`{3,}|~{3,})(?P<info>.*)$")


# Regular expression matching Markdown inline links and images:
# [label](destination) or ![alt](destination)
# Supports optional title in quotes or parens, and angle-bracket destinations <...>.
_INLINE_LINK_RE = re.compile(
    r"!?\[(?P<text>(?:[^\[\]]|\[[^\[\]]*\])*)\]"
    r"\(\s*(?P<dest><[^>]+>|[^)\s]+)"
    r"(?:\s+(?:\"[^\"]*\"|'[^']*'|\([^)]*\)))?\s*\)"
)

# Regular expression matching Markdown link reference definitions:
# [label]: destination "title"
_REF_LINK_RE = re.compile(
    r"^[ ]{0,3}\[(?P<label>[^\]]+)\]:\s*"
    r"(?P<dest><[^>]+>|\S+)"
    r"(?:\s+(?:\"[^\"]*\"|'[^']*'|\([^)]*\)))?\s*$"
)

# Regular expression matching the destination of an inline HTML link or media
# attribute: href="..." / href='...' / src="..." / src='...'. A page's body
# text may carry HTML that an adapter passes through verbatim, and a
# site-absolute HTML destination is as dead as a site-absolute Markdown one
# (see ``_destination_kind``), but the Markdown patterns above cannot see it.
# The attribute name must be followed by ``=``, so ``srcset=`` is not matched;
# a prefixed form such as ``data-href=`` still is, which is intended -- the
# destination it carries is a real one.
_HTML_LINK_ATTR_RE = re.compile(
    r"\b(?:href|src)\s*=\s*(?P<quote>[\"'])(?P<dest>[^\"']*)(?P=quote)",
    re.IGNORECASE,
)


@dataclass(frozen=True, slots=True)
class LinkIssue:
    """Represents a broken or unresolved internal link discovered in Markdown."""

    file: Path
    line: int
    target: str
    reason: str


def _mask_inline_code(line: str) -> str:
    """Replace inline Markdown code spans with spaces of identical length in linear time.

    Scans the line for matching backtick delimiters according to CommonMark
    code span rules. Delimiter runs are pre-indexed by length so that finding
    a matching closer runs in O(log M) time per delimiter, ensuring strict
    linear performance even on adversarial inputs with thousands of unmatched
    backticks. When a matching pair of backtick delimiters of equal length is
    found, the delimiter runs and their enclosed body are masked with spaces
    so that Markdown link patterns inside code spans are not falsely detected,
    while preserving column offsets for error reporting.
    """
    if "`" not in line:
        return line
    chars = list(line)
    n = len(chars)

    # Collect all backtick delimiter runs: (start_pos, length)
    runs: list[tuple[int, int]] = []
    runs_by_len: dict[int, list[int]] = {}

    i = 0
    while i < n:
        if chars[i] == "`":
            start = i
            while i < n and chars[i] == "`":
                i += 1
            fence_len = i - start
            run_idx = len(runs)
            runs.append((start, fence_len))
            runs_by_len.setdefault(fence_len, []).append(run_idx)
        else:
            i += 1

    if not runs:
        return line

    r_idx = 0
    num_runs = len(runs)
    while r_idx < num_runs:
        start_pos, fence_len = runs[r_idx]
        candidates = runs_by_len[fence_len]
        pos_in_candidates = bisect.bisect_right(candidates, r_idx)
        if pos_in_candidates < len(candidates):
            closer_run_idx = candidates[pos_in_candidates]
            closer_start, _ = runs[closer_run_idx]
            closer_end = closer_start + fence_len
            for k in range(start_pos, closer_end):
                chars[k] = " "
            r_idx = closer_run_idx + 1
        else:
            r_idx += 1

    return "".join(chars)


def _destination_kind(destination: str) -> str | None:
    """Classify a link destination, however the page wrote it.

    Returns ``"relative"`` for a local relative reference (the only kind whose
    target is resolved on disk), ``"site-absolute"`` for a destination
    anchored at the site root (``/docs/en/hooks``), ``"malformed"`` for a
    destination the URI parser rejects, and ``None`` for every destination
    this checker deliberately ignores: empty destinations, pure anchor
    fragments (``#...``), query-only references (``?...``), external URI
    schemes (``http://``, ``https://``, ``mailto:``, ...), and
    protocol-relative links (``//host/path``).

    A site-absolute destination gets a category of its own because it can
    NEVER resolve from a mirrored file: the mirror is browsed from a local
    checkout, where a leading ``/`` means the filesystem root, not a docs
    site. Reporting it as an issue is what keeps an adapter that forgot to
    rewrite its site links from shipping a tree full of dead references
    silently. Protocol-relative links stay in the ignored bucket: they name a
    host as well, so they are an external reference written in shorthand
    rather than a path into this mirror.

    A malformed destination is one ``urllib.parse.urlsplit`` refuses to parse
    (``http://[::1`` and anything else with an unclosed IPv6 bracket), which
    it signals by raising ``ValueError``. Catching it here keeps one bad link
    in one page from aborting the whole ``--check-links`` run: the defect is
    reported against the line that carries it, exactly like a broken target.
    """
    clean = destination.strip()
    if not clean:
        return None
    if clean.startswith("<") and clean.endswith(">"):
        clean = clean[1:-1].strip()
    if not clean or clean.startswith("#") or clean.startswith("?"):
        return None
    if clean.startswith("//"):
        return None
    if clean.startswith("/"):
        return "site-absolute"

    try:
        parsed = urllib.parse.urlsplit(clean)
    except ValueError:
        return "malformed"
    if parsed.scheme.lower() in _EXTERNAL_SCHEMES:
        return None

    lower = clean.lower()
    for scheme in _EXTERNAL_SCHEMES:
        if lower.startswith(f"{scheme}:"):
            return None

    return "relative"


def _clean_target_path(destination: str) -> str:
    """Strip surrounding angle brackets, query strings, and anchor fragments."""
    clean = destination.strip()
    if clean.startswith("<") and clean.endswith(">"):
        clean = clean[1:-1].strip()
    path_only = clean.split("#", 1)[0].split("?", 1)[0].strip()
    return urllib.parse.unquote(path_only)


def _check_target_exists(referencing_file: Path, clean_path: str) -> str | None:
    """Verify that the relative path exists relative to the referencing file.

    Returns None if the target is valid, or a descriptive failure reason if broken.
    """
    target_path = referencing_file.parent / clean_path
    if target_path.is_file():
        return None
    if target_path.is_dir():
        if (target_path / "README.md").is_file() or (
            target_path / "index.md"
        ).is_file():
            return None
        return (
            f"Target directory exists but contains no README.md or index.md: "
            f"{clean_path}"
        )
    return f"Target file does not exist: {clean_path}"


def check_file_links(
    file_path: Path, exempt_targets: Collection[str] = ()
) -> list[LinkIssue]:
    """Verify all internal relative links in a single Markdown file.

    Scans the file line by line, ignores fenced code blocks and inline code,
    and returns a list of all identified LinkIssue records. Destinations the
    owning source declared illustrative (*exempt_targets*) are not reported,
    and a site-root-absolute destination is always reported: it cannot resolve
    from a mirrored file wherever it appears, whether the page wrote it as a
    Markdown link or as an inline HTML ``href``/``src`` attribute. A
    destination the URI parser rejects is reported the same way, so one
    malformed link fails its own line instead of the whole run.
    """
    try:
        content = file_path.read_text(encoding="utf-8")
    except OSError as exc:
        return [
            LinkIssue(
                file=file_path,
                line=1,
                target=str(file_path),
                reason=f"Failed to read file: {exc}",
            )
        ]

    issues: list[LinkIssue] = []
    lines = content.splitlines()

    in_fence = False
    fence_char = ""
    fence_len = 0

    for line_num, line in enumerate(lines, start=1):
        fence_match = _FENCE_START_RE.match(line)
        if fence_match:
            fence_str = fence_match.group("fence")
            char = fence_str[0]
            length = len(fence_str)
            if not in_fence:
                in_fence = True
                fence_char = char
                fence_len = length
                continue
            if char == fence_char and length >= fence_len:
                rest = line[fence_match.end("fence") :].strip()
                if not rest:
                    in_fence = False
                    fence_char = ""
                    fence_len = 0
                continue

        if in_fence:
            continue

        sanitized_line = _mask_inline_code(line)

        raw_destinations: list[str] = []

        for m in _INLINE_LINK_RE.finditer(sanitized_line):
            raw_destinations.append(m.group("dest"))

        ref_match = _REF_LINK_RE.match(sanitized_line)
        if ref_match:
            raw_destinations.append(ref_match.group("dest"))

        # Inline HTML carried through into the mirror is read as well, so a
        # site-absolute attribute destination is reported like any other.
        for attr_match in _HTML_LINK_ATTR_RE.finditer(sanitized_line):
            raw_destinations.append(attr_match.group("dest"))

        for raw_dest in raw_destinations:
            kind = _destination_kind(raw_dest)
            if kind is None:
                continue

            clean_path = _clean_target_path(raw_dest)

            if kind == "site-absolute":
                issues.append(
                    LinkIssue(
                        file=file_path,
                        line=line_num,
                        target=raw_dest,
                        reason=(
                            f"Site-root-absolute link target {clean_path!r} cannot "
                            "resolve in the mirror; it must be rewritten to a "
                            "relative path or an upstream URL"
                        ),
                    )
                )
                continue

            if kind == "malformed":
                issues.append(
                    LinkIssue(
                        file=file_path,
                        line=line_num,
                        target=raw_dest,
                        reason=(
                            f"Malformed link destination {raw_dest!r}: it cannot "
                            "be parsed as a URI, so no target can be resolved "
                            "from it"
                        ),
                    )
                )
                continue

            if not clean_path or clean_path in exempt_targets:
                continue

            failure_reason = _check_target_exists(file_path, clean_path)
            if failure_reason is not None:
                issues.append(
                    LinkIssue(
                        file=file_path,
                        line=line_num,
                        target=raw_dest,
                        reason=failure_reason,
                    )
                )

    return issues


def _exempt_targets_for(
    file_path: Path, by_source: Mapping[str, Collection[str]] | None
) -> Collection[str]:
    """Return the illustrative destinations declared by the source owning *file_path*.

    The owning source is the first path segment of the file's location under
    ``config.DOCS_DIR`` (``<DOCS_DIR>/<source>/...``), so a scan of the whole
    docs tree and a scan of one source's directory both resolve the same way.
    A file outside the docs tree -- a scan invoked directly on an arbitrary
    path -- belongs to no source and therefore has no exemptions; both sides
    are resolved before the comparison so a symlinked temporary docs tree
    still matches its own files.
    """
    if not by_source:
        return ()
    try:
        relative = file_path.resolve().relative_to(config.DOCS_DIR.resolve())
    except OSError, ValueError:
        return ()
    if not relative.parts:
        return ()
    return by_source.get(relative.parts[0], ())


def check_links(
    base_dir: Path,
    exempt_targets_by_source: Mapping[str, Collection[str]] | None = None,
) -> tuple[list[LinkIssue], int]:
    """Recursively verify all Markdown links in files under base_dir.

    *exempt_targets_by_source* maps a source name to the illustrative
    destinations that source declares; each file is checked against the list
    of the source directory it lives under. Returns a tuple of (issues,
    scanned_files_count).
    """
    if not base_dir.exists():
        return [], 0

    if base_dir.is_file():
        if base_dir.suffix.lower() in {".md", ".markdown"}:
            exempt = _exempt_targets_for(base_dir, exempt_targets_by_source)
            return check_file_links(base_dir, exempt), 1
        return [], 0

    md_files = sorted(
        p
        for p in base_dir.rglob("*")
        if p.is_file() and p.suffix.lower() in {".md", ".markdown"}
    )

    issues: list[LinkIssue] = []
    for md_file in md_files:
        exempt = _exempt_targets_for(md_file, exempt_targets_by_source)
        issues.extend(check_file_links(md_file, exempt))

    return issues, len(md_files)


def check_source_links(
    source_name: str | None = None,
    exempt_targets_by_source: Mapping[str, Collection[str]] | None = None,
) -> tuple[list[LinkIssue], int]:
    """Verify Markdown links across docs/ or for a specific documentation source.

    *exempt_targets_by_source* is forwarded to :func:`check_links`; the caller
    (the CLI) builds it from the source registry, which keeps this module free
    of any knowledge about concrete sources. Returns a tuple of (issues,
    scanned_files_count).
    """
    if source_name is None:
        return check_links(config.DOCS_DIR, exempt_targets_by_source)

    source_dir = config.DOCS_DIR / source_name
    if not source_dir.exists() or not source_dir.is_dir():
        return [], 0

    return check_links(source_dir, exempt_targets_by_source)
