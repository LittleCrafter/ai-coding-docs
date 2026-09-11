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


def test_check_file_links_reports_site_absolute_targets(tmp_path: Path):
    """A site-root-absolute destination is always an issue: it cannot resolve
    from a mirrored file, so it means the owning adapter did not rewrite it."""
    source_file = tmp_path / "page.md"
    source_file.write_text(
        "# Page\n"
        "- Absolute: [hooks](/docs/en/hooks)\n"
        "- Angle-bracketed: [hooks](</docs/en/hooks#x>)\n"
        "- Bare root: [home](/)\n"
    )
    issues = link_checker.check_file_links(source_file)
    assert [issue.line for issue in issues] == [2, 3, 4]
    assert issues[0].target == "/docs/en/hooks"
    assert issues[1].target == "</docs/en/hooks#x>"
    assert "'/docs/en/hooks'" in issues[0].reason
    assert "cannot resolve in the mirror" in issues[0].reason


def test_check_file_links_ignores_absolute_targets_in_code(tmp_path: Path):
    """Fenced code and inline code hold samples, not references: an absolute
    path inside one is quoted documentation and must not be reported."""
    source_file = tmp_path / "page.md"
    source_file.write_text(
        "# Page\n"
        "\n"
        "```sh\n"
        "curl https://example.com/docs/en/hooks\n"
        "echo [sample](/docs/en/hooks)\n"
        "```\n"
        "\n"
        "Inline: `[hooks](/docs/en/hooks)` stays quoted.\n"
    )
    assert link_checker.check_file_links(source_file) == []


def test_check_file_links_reports_site_absolute_html_attributes(tmp_path: Path):
    """A site-absolute path is just as dead written as an inline HTML
    attribute as it is written as a Markdown link, and a mirrored page carries
    both: an adapter that passes HTML through leaves ``href="/..."`` and
    ``src="/..."`` in the body text where the Markdown patterns cannot see
    them. Every one is reported, whatever quoting the attribute used."""
    source_file = tmp_path / "page.md"
    source_file.write_text(
        "# Page\n"
        '<a href="/docs/en/hooks">Hooks</a> and <img src="/img/logo.svg" alt="L" />\n'
        "<a class='x' href='/docs/en/skills'>Skills</a>\n"
    )
    issues = link_checker.check_file_links(source_file)
    assert [issue.line for issue in issues] == [2, 2, 3]
    assert [issue.target for issue in issues] == [
        "/docs/en/hooks",
        "/img/logo.svg",
        "/docs/en/skills",
    ]
    assert "cannot resolve in the mirror" in issues[0].reason


def test_check_file_links_ignores_html_attributes_inside_code(tmp_path: Path):
    """An HTML sample that shows a site-absolute link is quoted documentation,
    so it stays exempt exactly like the Markdown form does -- both inside a
    fenced block and inside an inline code span."""
    source_file = tmp_path / "page.md"
    source_file.write_text(
        "# Page\n"
        "\n"
        "```html\n"
        '<a href="/signin-with-chatgpt">Sign in with ChatGPT</a>\n'
        "```\n"
        "\n"
        'Inline: `<a href="/signin-with-chatgpt">Sign in</a>` stays quoted.\n'
    )
    assert link_checker.check_file_links(source_file) == []


def test_check_file_links_ignores_resolvable_html_attributes(tmp_path: Path):
    """Only site-absolute attribute destinations are defects of their own:
    an external URL names another site, a fragment names this page, and a
    relative destination is resolved on disk like any other reference."""
    (tmp_path / "img").mkdir()
    (tmp_path / "img" / "logo.svg").write_text("<svg />\n")
    source_file = tmp_path / "page.md"
    source_file.write_text(
        "# Page\n"
        '<a href="https://example.com/x">External</a>\n'
        '<a href="#section">Anchor</a>\n'
        '<img src="img/logo.svg" alt="L" />\n'
        '<img src="img/missing.svg" alt="M" />\n'
    )
    issues = link_checker.check_file_links(source_file)
    assert [issue.line for issue in issues] == [5]
    assert issues[0].target == "img/missing.svg"
    assert "does not exist" in issues[0].reason


def test_check_file_links_reports_a_destination_the_uri_parser_rejects(
    tmp_path: Path,
):
    """A destination ``urllib.parse.urlsplit`` refuses -- an IPv6 host with no
    closing bracket, here -- must be reported as a defect of its own line
    instead of raising out of the check and aborting the whole run before any
    other page is examined."""
    source_file = tmp_path / "page.md"
    source_file.write_text(
        "# Page\n- Bad: [bad](http://[::1)\n- Good: [hooks](./missing.md)\n"
    )
    issues = link_checker.check_file_links(source_file)
    assert [issue.line for issue in issues] == [2, 3]
    assert issues[0].target == "http://[::1"
    assert "Malformed link destination" in issues[0].reason
    assert "cannot be parsed as a URI" in issues[0].reason


def test_check_file_links_ignores_protocol_relative_and_external_targets(
    tmp_path: Path,
):
    """``//host/path`` names a host, like any other external URL, so it is not
    a path into this mirror and stays ignored."""
    source_file = tmp_path / "page.md"
    source_file.write_text(
        "# Page\n"
        "- Protocol relative: [cdn](//cdn.example.com/x.png)\n"
        "- External: [site](https://example.com/docs/en/hooks)\n"
    )
    assert link_checker.check_file_links(source_file) == []


def test_check_file_links_honors_exempt_targets(tmp_path: Path):
    """Illustrative targets passed in by the caller must be exempted."""
    claude_dir_file = tmp_path / "claude-directory.md"
    claude_dir_file.write_text(
        "# Directory\n"
        "- [build-and-test.md](build-and-test.md)\n"
        "- [architecture.md](architecture.md)\n"
        "- [debugging.md](debugging.md)\n"
        "- [real_broken.md](real_broken.md)\n"
    )
    issues = link_checker.check_file_links(
        claude_dir_file,
        ("build-and-test.md", "architecture.md", "debugging.md"),
    )
    assert len(issues) == 1
    assert issues[0].target == "real_broken.md"


def test_check_links_resolves_exemptions_from_the_owning_source(
    monkeypatch, tmp_path: Path
):
    """``exempt_targets_by_source`` applies only to files under that source.

    A destination is exempt in the source that declared it and broken in every
    other source, which is what keeps one source's sample-driven exemption
    from silencing a genuinely dead link elsewhere in the mirror.
    """
    docs_dir = tmp_path / "docs"
    (docs_dir / "source-a").mkdir(parents=True)
    (docs_dir / "source-b").mkdir(parents=True)
    (docs_dir / "source-a" / "page.md").write_text("[Sample](architecture.md)\n")
    (docs_dir / "source-b" / "page.md").write_text("[Real](architecture.md)\n")
    monkeypatch.setattr(config, "DOCS_DIR", docs_dir)

    by_source = {"source-a": ("architecture.md",)}

    issues, count = link_checker.check_links(docs_dir, by_source)
    assert count == 2
    assert [issue.file.name for issue in issues] == ["page.md"]
    assert issues[0].file.parent.name == "source-b"

    # Scanning one source's directory resolves the same ownership rule.
    a_issues, a_count = link_checker.check_source_links("source-a", by_source)
    assert (a_issues, a_count) == ([], 1)
    b_issues, b_count = link_checker.check_source_links("source-b", by_source)
    assert b_count == 1
    assert len(b_issues) == 1
