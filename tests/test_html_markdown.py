"""Tests for the shared HTML-to-Markdown helpers (mirror.core.html_markdown).

Only the functions with non-trivial behaviour contracts are pinned here:
``splice_code_blocks`` (placeholder splicing, adaptive fence lengths, and
the missing-placeholder warning path) and ``collapse_blank_lines`` (the
blank-run collapse semantics stated in its docstring). ``make_converter``
and ``strip_cf_characters`` are exercised end-to-end by the adapter tests.
"""

from __future__ import annotations

from mirror.core import html_markdown


def _placeholder(index: int) -> str:
    """Placeholder-token factory mirroring the adapters' ``_code_placeholder``
    shape: an index embedded between an identifying prefix and suffix, so
    each block's token is unique and attributable."""
    return f"TESTCODEBLOCK{index}PLACEHOLDER"


# --- splice_code_blocks ---------------------------------------------------------


def test_splice_code_blocks_replaces_placeholder_with_fenced_block():
    """The happy path: each placeholder token is replaced by a complete
    fenced code block carrying the block's language tag, surrounded by blank
    lines so the fence sits at line start for the later blank-line-collapse
    pass."""
    text = f"Intro paragraph.\n\n{_placeholder(0)}\n\nOutro."
    out = html_markdown.splice_code_blocks(
        text, [("python", "print('hi')")], _placeholder
    )
    assert "```python\nprint('hi')\n```" in out
    assert _placeholder(0) not in out
    # The fence is forced to line start by the surrounding blank lines.
    assert "\n\n```python\n" in out


def test_splice_code_blocks_fence_adapts_to_inner_backticks():
    """A code block whose content contains a backtick run must be fenced with
    one more backtick than the longest inner run, so the inner run can never
    close the fence prematurely (CommonMark's variable-length fence rule)."""
    text = _placeholder(0)
    out = html_markdown.splice_code_blocks(
        text, [("markdown", "use ``` like this")], _placeholder
    )
    assert "````markdown\nuse ``` like this\n````" in out


def test_splice_code_blocks_missing_placeholder_warns_and_continues(capsys):
    """If html2text mangled or dropped a placeholder token, the block must
    NOT silently vanish: a stderr warning naming the token is emitted, the
    text is left unmodified for that block, and splicing CONTINUES with the
    remaining blocks. (``str.replace`` on a missing needle is a silent
    no-op, which is exactly the failure mode this guards against.)"""
    text = f"Intro.\n\n{_placeholder(1)}\n\nOutro."  # only token 1 present
    out = html_markdown.splice_code_blocks(
        text, [("python", "lost()"), ("go", "kept()")], _placeholder
    )
    # The missing token's block is skipped; the present one is spliced.
    assert "lost()" not in out
    assert "```go\nkept()\n```" in out
    # The text is otherwise untouched (no partial splice of the lost block).
    assert _placeholder(1) not in out  # token 1 was replaced normally
    # The warning names the missing token so the loss is diagnosable.
    err = capsys.readouterr().err
    assert "warning" in err
    assert _placeholder(0) in err


# --- collapse_blank_lines ---------------------------------------------------------


def test_collapse_blank_lines_collapses_two_or_more_blank_lines_to_one():
    """Pin the docstring's actual contract: every run of 3+ consecutive
    newlines (i.e. 2 or more blank lines) collapses to exactly ``\\n\\n`` --
    ONE blank line -- while a single blank line (``\\n\\n``) is left
    untouched."""
    text = "a\n\n\nb\n\n\n\n\nc\n\nd"
    assert html_markdown.collapse_blank_lines(text) == "a\n\nb\n\nc\n\nd"


def test_collapse_blank_lines_preserves_blank_lines_inside_code_blocks():
    """Blank lines INSIDE fenced code blocks are semantically significant and
    must survive verbatim even when they form long runs; only the gaps
    between blocks are collapsed."""
    text = "x\n\n\n```\nline1\n\n\n\nline2\n```\n\n\ny"
    assert html_markdown.collapse_blank_lines(text) == (
        "x\n\n```\nline1\n\n\n\nline2\n```\n\ny"
    )


def test_extract_code_blocks_with_containers():
    """When a `<pre>` sits inside a `<div>` carrying *container_class*, the WHOLE
    container must be replaced by the token. One container holding several `<pre>`
    elements is replaced exactly once, and its blocks are returned in order."""
    import bs4

    html = """
    <div class="code-container">
      <div class="header">bash</div>
      <pre><code>linux</code></pre>
      <pre><code>macos</code></pre>
    </div>
    <pre><code>bare</code></pre>
    """
    soup = bs4.BeautifulSoup(html, "html.parser")

    def _detect(pre, code):
        if pre.parent.get("class") == ["code-container"]:
            return pre.parent.find("div", class_="header").get_text(strip=True)
        return "text"

    # The signature takes (content, soup): ``content`` is the subtree whose
    # <pre> elements are replaced by placeholder tokens, and ``soup`` is the
    # document used to create the replacement nodes. The whole parsed
    # document serves as both here.
    blocks = html_markdown.extract_code_blocks(
        soup,
        soup,
        container_class="code-container",
        detect_language=_detect,
        placeholder=lambda i: f"TOKEN{i}",
    )
    assert len(blocks) == 3
    assert blocks[0] == ("bash", "linux")
    assert blocks[1] == ("bash", "macos")
    assert blocks[2] == ("text", "bare")
    out = str(soup)
    assert "TOKEN0" in out
    assert "TOKEN1" in out
    assert "TOKEN2" in out
    assert "linux" not in out
    assert "code-container" not in out
