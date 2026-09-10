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
* **Directory target support**: Resolves directory targets by checking for
  the presence of ``README.md`` or ``index.md``.
"""

from __future__ import annotations

import bisect
import re
import urllib.parse
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

# Known illustrative relative links that appear in documentation code examples
# or sample config snippets (e.g. claude-directory.md memory index sample).
_KNOWN_ILLUSTRATIVE_TARGETS: dict[str, frozenset[str]] = {
    "claude-directory.md": frozenset(
        {
            "build-and-test.md",
            "architecture.md",
            "debugging.md",
        }
    ),
}

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


def _is_relative_link(destination: str) -> bool:
    """Determine if a link destination is a local relative reference.

    Returns False for empty destinations, pure anchor fragments (``#...``),
    external URI schemes (``http://``, ``https://``, ``mailto:``, etc.),
    protocol-relative links (``//...``), and site-root absolute links (``/...``).
    """
    clean = destination.strip()
    if not clean:
        return False
    if clean.startswith("<") and clean.endswith(">"):
        clean = clean[1:-1].strip()
    if not clean or clean.startswith("#") or clean.startswith("?"):
        return False
    if clean.startswith("//") or clean.startswith("/"):
        return False

    parsed = urllib.parse.urlsplit(clean)
    if parsed.scheme.lower() in _EXTERNAL_SCHEMES:
        return False

    lower = clean.lower()
    for scheme in _EXTERNAL_SCHEMES:
        if lower.startswith(f"{scheme}:"):
            return False

    return True


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


def check_file_links(file_path: Path) -> list[LinkIssue]:
    """Verify all internal relative links in a single Markdown file.

    Scans the file line by line, ignores fenced code blocks and inline code,
    and returns a list of all identified LinkIssue records.
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
    exempt_targets = _KNOWN_ILLUSTRATIVE_TARGETS.get(file_path.name, frozenset())

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

        for raw_dest in raw_destinations:
            if not _is_relative_link(raw_dest):
                continue

            clean_path = _clean_target_path(raw_dest)
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


def check_links(base_dir: Path) -> tuple[list[LinkIssue], int]:
    """Recursively verify all Markdown links in files under base_dir.

    Returns a tuple of (issues, scanned_files_count).
    """
    if not base_dir.exists():
        return [], 0

    if base_dir.is_file():
        if base_dir.suffix.lower() in {".md", ".markdown"}:
            return check_file_links(base_dir), 1
        return [], 0

    md_files = sorted(
        p
        for p in base_dir.rglob("*")
        if p.is_file() and p.suffix.lower() in {".md", ".markdown"}
    )

    issues: list[LinkIssue] = []
    for md_file in md_files:
        issues.extend(check_file_links(md_file))

    return issues, len(md_files)


def check_source_links(source_name: str | None = None) -> tuple[list[LinkIssue], int]:
    """Verify Markdown links across docs/ or for a specific documentation source.

    Returns a tuple of (issues, scanned_files_count).
    """
    if source_name is None:
        return check_links(config.DOCS_DIR)

    source_dir = config.DOCS_DIR / source_name
    if not source_dir.exists() or not source_dir.is_dir():
        return [], 0

    return check_links(source_dir)
