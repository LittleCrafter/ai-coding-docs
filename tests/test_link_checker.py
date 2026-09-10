"""Tests for the internal Markdown link verification module (mirror.core.link_checker)."""

from __future__ import annotations

from pathlib import Path

from mirror import config
from mirror.core import link_checker
from mirror.core.link_checker import LinkIssue


def test_link_issue_dataclass(tmp_path: Path):
    """Pin the LinkIssue data model properties and slots behavior."""
    file_p = tmp_path / "test.md"
    issue = LinkIssue(
        file=file_p,
        line=42,
        target="./missing.md",
        reason="Target file does not exist",
    )
    assert issue.file == file_p
    assert issue.line == 42
    assert issue.target == "./missing.md"
    assert issue.reason == "Target file does not exist"


def test_check_file_links_valid_relative_targets(tmp_path: Path):
    """Valid sibling, subdirectory, parent, and directory targets must pass."""
    guides_dir = tmp_path / "guides"
    guides_dir.mkdir()
    sub_dir = guides_dir / "sub"
    sub_dir.mkdir()
    pkg_dir = tmp_path / "pkg"
    pkg_dir.mkdir()

    # Target files
    (tmp_path / "root.md").write_text("# Root")
    (guides_dir / "sibling.md").write_text("# Sibling")
    (sub_dir / "nested.md").write_text("# Nested")
    (pkg_dir / "README.md").write_text("# Pkg Index")
    (guides_dir / "image.png").write_bytes(b"\x89PNG")
    (guides_dir / "spaced file.md").write_text("# Spaced")

    source_file = guides_dir / "doc.md"
    source_file.write_text(
        "# Title\n"
        "- Sibling: [Sibling](./sibling.md)\n"
        "- Bare sibling: [Bare](sibling.md)\n"
        "- Parent: [Root](../root.md)\n"
        "- Nested: [Nested](./sub/nested.md)\n"
        "- Directory with README: [Pkg](../pkg/)\n"
        "- Bare directory: [Pkg](../pkg)\n"
        "- With query and anchor: [Sibling](./sibling.md?v=2#sec)\n"
        "- Angle brackets: [Angle](<./sibling.md>)\n"
        "- Image: ![Alt text](./image.png)\n"
        "- URL encoded: [Spaced](./spaced%20file.md)\n"
        "- Reference link: [RefLabel]\n\n"
        "[RefLabel]: ./sibling.md 'Title'\n"
    )

    issues = link_checker.check_file_links(source_file)
    assert issues == []


def test_check_file_links_ignores_external_and_anchors(tmp_path: Path):
    """External protocols, mailto, protocol-relative, and pure anchors are ignored."""
    source_file = tmp_path / "external.md"
    source_file.write_text(
        "- Web HTTP: [HTTP](http://example.com/missing.md)\n"
        "- Web HTTPS: [HTTPS](https://example.com/missing.md)\n"
        "- Mailto: [Mail](mailto:user@example.com)\n"
        "- FTP: [FTP](ftp://files.example.com/doc.md)\n"
        "- Data URI: [Data](data:image/png;base64,iVBORw0KGgo=)\n"
        "- Javascript: [JS](javascript:void(0))\n"
        "- VSCode extension: [VSCode](vscode:extension/foo)\n"
        "- Cursor extension: [Cursor](cursor:extension/foo)\n"
        "- Codex deep link: [Codex](codex://settings)\n"
        "- Protocol relative: [CDN](//cdn.example.com/lib.js)\n"
        "- Pure anchor: [Section](#heading)\n"
        "- Multi-hash anchor: [Sub](#sub-heading-1)\n"
        "- Upstream site root: [SiteRoot](/docs/en/settings)\n"
    )

    issues = link_checker.check_file_links(source_file)
    assert issues == []


def test_check_file_links_ignores_links_in_fenced_code_blocks(tmp_path: Path):
    """Links inside backtick and tilde code fences must be ignored."""
    source_file = tmp_path / "code_blocks.md"
    source_file.write_text(
        "# Heading\n"
        "```markdown\n"
        "[Broken inside backtick fence](./nonexistent1.md)\n"
        "```\n"
        "~~~python\n"
        "# [Broken inside tilde fence](./nonexistent2.md)\n"
        "~~~\n"
        "````text\n"
        "```markdown\n"
        "[Nested fence broken link](./nonexistent3.md)\n"
        "```\n"
        "````\n"
    )

    issues = link_checker.check_file_links(source_file)
    assert issues == []


def test_check_file_links_ignores_inline_code_links(tmp_path: Path):
    """Links inside inline backtick spans must be ignored; inline code inside labels works."""
    (tmp_path / "valid.md").write_text("# Valid")
    source_file = tmp_path / "inline_code.md"
    source_file.write_text(
        "Inline link in code: `[Missing](./missing_in_code.md)`\n"
        "Double backtick: ``[Missing](./missing_in_code2.md)``\n"
        "Code inside label: [`ValidClass`](./valid.md)\n"
    )

    issues = link_checker.check_file_links(source_file)
    assert issues == []


def test_mask_inline_code_stress_linear_time():
    """Line with 8,000 unclosed/alternating backticks finishes in under 50ms without catastrophic backtracking."""
    import time

    stress_line = "`" * 8000
    start = time.perf_counter()
    result = link_checker._mask_inline_code(stress_line)
    elapsed = time.perf_counter() - start
    assert elapsed < 0.05
    assert result == stress_line

    # Also test non-matching alternating fence runs
    alternating = "".join("`" * i + " x " for i in range(1, 200))
    start = time.perf_counter()
    alt_result = link_checker._mask_inline_code(alternating)
    elapsed_alt = time.perf_counter() - start
    assert elapsed_alt < 0.05
    assert len(alt_result) == len(alternating)


def test_mask_inline_code_commonmark_scenarios():
    """Validate CommonMark code span masking edge cases."""
    # Single backtick span
    assert link_checker._mask_inline_code("`code`") == "      "
    # Double backtick span containing single backticks
    target = "``code with ` backtick``"
    assert link_checker._mask_inline_code(target) == " " * len(target)
    # Unclosed backtick treated as normal text
    assert link_checker._mask_inline_code("`unclosed") == "`unclosed"
    # Mismatched backtick lengths
    assert link_checker._mask_inline_code("`code``") == "`code``"


def test_check_file_links_reports_broken_targets(tmp_path: Path):
    """Missing target files and empty directories must be reported with line numbers."""
    empty_dir = tmp_path / "empty_dir"
    empty_dir.mkdir()

    source_file = tmp_path / "broken.md"
    source_file.write_text(
        "# Title\n"
        "Line 2 is okay.\n"
        "Line 3 has [Broken File](./missing.md).\n"
        "Line 4 has [Empty Directory](./empty_dir/).\n"
        "Line 5 has [Broken Parent](../missing_parent.md).\n"
    )

    issues = link_checker.check_file_links(source_file)
    assert len(issues) == 3

    assert issues[0].line == 3
    assert issues[0].target == "./missing.md"
    assert "does not exist" in issues[0].reason

    assert issues[1].line == 4
    assert issues[1].target == "./empty_dir/"
    assert "contains no README.md or index.md" in issues[1].reason

    assert issues[2].line == 5
    assert issues[2].target == "../missing_parent.md"
    assert "does not exist" in issues[2].reason


def test_check_file_links_unreadable_file(tmp_path: Path):
    """OSError when reading a file produces a structured LinkIssue on line 1."""
    nonexistent = tmp_path / "does_not_exist.md"
    issues = link_checker.check_file_links(nonexistent)
    assert len(issues) == 1
    assert issues[0].line == 1
    assert "Failed to read file" in issues[0].reason


def test_check_links_directory_traversal(tmp_path: Path):
    """check_links scans all Markdown files recursively in sorted order."""
    sub_a = tmp_path / "a"
    sub_b = tmp_path / "b"
    sub_a.mkdir()
    sub_b.mkdir()

    (sub_a / "test.md").write_text("[Broken A](./missing_a.md)")
    (sub_b / "test.markdown").write_text("[Broken B](./missing_b.md)")
    (sub_b / "ignored.txt").write_text("[Ignored](./missing_c.md)")

    issues, count = link_checker.check_links(tmp_path)
    assert len(issues) == 2
    assert count == 2
    assert issues[0].target == "./missing_a.md"
    assert issues[1].target == "./missing_b.md"


def test_check_links_nonexistent_path(tmp_path: Path):
    """Non-existent directory or file returns an empty list and 0 count."""
    assert link_checker.check_links(tmp_path / "not_there") == ([], 0)


def test_check_source_links(monkeypatch, tmp_path: Path):
    """check_source_links verifies DOCS_DIR or DOCS_DIR / source_name."""
    docs_dir = tmp_path / "docs"
    source_a = docs_dir / "source_a"
    source_b = docs_dir / "source_b"
    source_a.mkdir(parents=True)
    source_b.mkdir(parents=True)

    (source_a / "a.md").write_text("[Broken A](./bad_a.md)")
    (source_b / "b.md").write_text("[Broken B](./bad_b.md)")

    monkeypatch.setattr(config, "DOCS_DIR", docs_dir)

    # Check all sources (None)
    all_issues, all_count = link_checker.check_source_links(None)
    assert len(all_issues) == 2
    assert all_count == 2

    # Check source_a only
    a_issues, a_count = link_checker.check_source_links("source_a")
    assert len(a_issues) == 1
    assert a_count == 1
    assert a_issues[0].target == "./bad_a.md"

    # Nonexistent source
    assert link_checker.check_source_links("unknown_source") == ([], 0)


def test_check_file_links_ignores_query_only_links(tmp_path: Path):
    """Query-only links like ?tab=cli or ?mode=all#top refer to the current page and must pass."""
    source_file = tmp_path / "page.md"
    source_file.write_text(
        "# Heading\n"
        "- Query only: [Tab](?tab=cli)\n"
        "- Query with fragment: [Mode](?mode=all#top)\n"
    )
    issues = link_checker.check_file_links(source_file)
    assert issues == []


def test_check_file_links_honors_exempt_targets(tmp_path: Path):
    """Known illustrative targets configured for claude-directory.md must be exempted."""
    claude_dir_file = tmp_path / "claude-directory.md"
    claude_dir_file.write_text(
        "# Directory\n"
        "- [build-and-test.md](build-and-test.md)\n"
        "- [architecture.md](architecture.md)\n"
        "- [debugging.md](debugging.md)\n"
        "- [real_broken.md](real_broken.md)\n"
    )
    issues = link_checker.check_file_links(claude_dir_file)
    assert len(issues) == 1
    assert issues[0].target == "real_broken.md"
