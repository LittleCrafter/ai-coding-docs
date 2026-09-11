"""Tests for the shared HTML-to-Markdown helpers (mirror.core.html_markdown).

Only the functions with non-trivial behaviour contracts are pinned here:
``splice_code_blocks`` (placeholder splicing, adaptive fence lengths, and
the missing-placeholder warning path), ``collapse_blank_lines`` (the
blank-run collapse semantics stated in its docstring), the ``<pre>`` text
extraction (which must keep the line breaks a syntax highlighter expresses
as ``<br>``), and ``strip_invisible_characters`` (which must drop control
characters without touching line structure). ``make_converter`` is exercised
end-to-end by the adapter tests.
"""

from __future__ import annotations

import bs4

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


# --- extract_code_blocks: line breaks expressed as markup -----------------------


def _extract(html: str) -> list[tuple[str, str]]:
    """Extract the code blocks of *html* with a container-free configuration."""
    soup = bs4.BeautifulSoup(html, "html.parser")
    return html_markdown.extract_code_blocks(
        soup,
        soup,
        container_class="theme-code-block",
        detect_language=lambda pre, container: "",
        placeholder=lambda index: f"TOKEN{index}",
    )


def test_extract_code_blocks_keeps_line_breaks_written_as_br():
    """A syntax highlighter renders each code line as a ``<span>`` followed by
    a ``<br>``, and a ``<br>`` carries no text of its own -- so reading the
    block with ``get_text()`` would concatenate every line of the sample into
    one. Each ``<br>`` must come back as a real newline instead."""
    blocks = _extract(
        "<pre><code>"
        '<span class="token-line">first<span class="token plain"></span><br></span>'
        '<span class="token-line"><span class="token plain"></span><br></span>'
        '<span class="token-line">second</span><br>'
        "</code></pre>"
    )
    assert blocks == [("", "first\n\nsecond")]


def test_extract_code_blocks_keeps_literal_newlines_unchanged():
    """A plain ``<pre>`` whose newlines are already text must be returned
    exactly as before: the markup handling only adds the breaks that markup
    expressed and leaves literal ones alone."""
    blocks = _extract("<pre><code>alpha\n\nbeta</code></pre>")
    assert blocks == [("", "alpha\n\nbeta")]


def test_extract_code_blocks_handles_inline_markup_inside_a_line():
    """Inline spans inside one line are not breaks: the line keeps its text
    and only an actual ``<br>`` splits it."""
    blocks = _extract(
        '<pre><code><span class="token keyword">def</span> '
        '<span class="token plain">f()</span><br>'
        '<span class="token plain">    pass</span></code></pre>'
    )
    assert blocks == [("", "def f()\n    pass")]


def test_extract_code_blocks_leaves_comments_out_of_the_sample():
    """A comment between two text nodes is not code. React separates the text
    nodes it renders with an empty ``<!-- -->``, and a page's own comment
    inside a ``<pre>`` carries prose rather than sample text; reading either
    as text would splice it into the middle of a code line, which is exactly
    what ``get_text()`` avoids by not considering comment nodes."""
    blocks = _extract(
        "<pre><code><span>line1</span><!-- --><br>"
        "<span>line2</span><!-- do not ship this --><br>"
        "<span>line3</span></code></pre>"
    )
    assert blocks == [("", "line1\nline2\nline3")]


# --- strip_invisible_characters --------------------------------------------------


def test_strip_invisible_characters_removes_format_and_control_characters():
    """Both invisible categories go: the Cf formatting residues and the Cc
    control bytes (a NUL byte makes a mirrored page binary to ``git`` and
    ``grep``, which is how such a file silently drops out of every diff)."""
    text = "a​b﻿c\x00d\x07e"
    assert html_markdown.strip_invisible_characters(text) == "abcde"


def test_strip_invisible_characters_keeps_line_structure():
    """Tab, line feed, and carriage return are structure, not noise: dropping
    them would re-indent code samples and join the lines of a page."""
    text = "col1\tcol2\nrow2\r\nrow3\rrow4"
    assert html_markdown.strip_invisible_characters(text) == text


def test_strip_invisible_characters_leaves_ordinary_text_alone():
    """Visible Unicode is untouched: the filter is category-based and must not
    drop or fold accents, CJK characters, or emoji."""
    # Sample CHARACTERS, not a sentence: the point is that none of these
    # categories is filtered out.
    text = "Café, naïve, 日本語, 🚀"
    assert html_markdown.strip_invisible_characters(text) == text
