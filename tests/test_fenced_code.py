"""Tests for the shared fenced-code shielding helpers (mirror.core.fenced_code).

The module is the single home of the extract -> transform -> splice mechanism
the shielded adapters share, so what is pinned here is the mechanism itself:
which spans the indentation-aware scanner reports, that protecting and
restoring round-trips byte for byte, and that the two knobs the adapters vary
(the span finder and the placeholder factory) are honoured. Each adapter's own
fence policy and token shape are pinned by that adapter's tests.
"""

from __future__ import annotations

import time

from mirror.core import fenced_code
from mirror.core.html_markdown import iter_code_block_spans


def _simple_spans(text: str):
    """Span finder for the shared tests: column-zero fences only."""
    return fenced_code.iter_indented_fence_spans(text, max_indent=0)


def _placeholder(index: int) -> str:
    """Placeholder factory in the shape the adapters use."""
    return f"TESTFENCEBLOCK{index}PLACEHOLDER"


# --- iter_indented_fence_spans --------------------------------------------------


def test_iter_indented_fence_spans_reports_a_complete_block():
    """A block runs from the opening fence line's start through the end of
    the closing fence line (whose trailing newline is excluded), so splicing
    the span back restores exactly the block."""
    text = "before\n```python\ncode\n```\nafter"
    spans = list(fenced_code.iter_indented_fence_spans(text))
    assert spans == [(7, 25)]
    start, end = spans[0]
    assert text[start:end] == "```python\ncode\n```"


def test_iter_indented_fence_spans_recognises_an_indented_fence():
    """A fence indented by up to the configured bound is a fence: upstream
    writes samples inside list items and CommonMark still reads those as
    fenced code, so they must be shielded like any other block."""
    text = "1. Step:\n\n   ```sh\n   kimi --x\n   ```\n"
    spans = list(fenced_code.iter_indented_fence_spans(text))
    assert len(spans) == 1
    start, end = spans[0]
    # The span starts at the fence character, leaving the indentation in the
    # surrounding text where the container re-indent pass expects to read it.
    assert text[start:end] == "```sh\n   kimi --x\n   ```"


def test_iter_indented_fence_spans_rejects_a_deeper_indentation():
    """Four columns is an indented code block, not a fence, so the line is
    ordinary text and no span is reported."""
    text = "1. Step:\n\n    ```sh\n    not a fence\n    ```\n"
    assert list(fenced_code.iter_indented_fence_spans(text)) == []


def test_iter_indented_fence_spans_leaves_tab_indentation_alone():
    """A tab advances to an unknown column, so a tab-indented fence is not
    claimed: guessing the width could shield something that is not a block."""
    text = "1. Step:\n\n\t```sh\n\tx\n\t```\n"
    assert list(fenced_code.iter_indented_fence_spans(text)) == []


def test_iter_indented_fence_spans_bound_is_configurable():
    """The bound is the adapter's policy knob: the same text yields a span at
    the permissive bound and none at the strict one."""
    text = "   ```\n   x\n   ```\n"
    assert len(list(fenced_code.iter_indented_fence_spans(text, max_indent=3))) == 1
    assert list(fenced_code.iter_indented_fence_spans(text, max_indent=0)) == []


# Documents the zero-indent equivalence is checked against: every shape whose
# line accounting could disagree with the shared scanner's, one per entry.
_ZERO_INDENT_CORPUS = {
    "empty": "",
    "no fences": "just prose\nand more prose",
    "one block": "before\n```python\ncode\n```\nafter",
    "two blocks": "a\n```\nfirst\n```\nb\n~~~\nsecond\n~~~\nc",
    "no trailing newline": "a\n```\nunterminated",
    "opener on the last line": "a\n```",
    "unclosed fence": "a\n```python\ncode without a closer\n",
    "tilde fences": "a\n~~~\nbody\n~~~\nb\n~~~~\nbody\n~~~~\nc",
    "four-backtick fences": "a\n````\n```\ninner\n```\n````\nb",
    "blank lines inside": "a\n```\n\n\n```\nb",
    "info string": 'a\n```json title="x"\n{}\n```\nb',
    "three-space indent": "1. step\n\n   ```sh\n   x\n   ```\n",
    "four-space indent": "    ```sh\n    x\n    ```\n",
    "tab indent": "1. step\n\n\t```sh\n\tx\n\t```\n",
    "crlf line endings": "a\r\n```\r\nx\r\n```\r\nb\r\n",
    "bare carriage return": "a\r```\rx\r```\rb",
    "fence characters only": "```\n```\n~~~\n~~~\n",
    "a close with no opener": "a\n```\nb",
    "runs of fence characters": "a\n`````\nx\n`````\nb",
}


def test_iter_indented_fence_spans_with_no_indent_matches_the_shared_scanner():
    """At a zero indent bound the de-indented copy the wrapper scans IS the
    document it was handed, so the wrapper has to report exactly the spans the
    shared column-zero scanner reports -- same starts, same ends, nothing
    gained and nothing lost. That equality is what lets a caller ask for the
    shared rule through this scanner instead of a second copy of it, and it is
    what the per-line offset mapping has to preserve: a line accounting that
    drifted by one byte would move every span after it.

    The corpus holds the shapes whose line accounting is easiest to get wrong:
    a tab or a carriage return changes what a line contains without changing
    how many lines there are, and an unclosed or last-line fence changes which
    lines are part of a block at all."""
    for name, text in _ZERO_INDENT_CORPUS.items():
        assert list(fenced_code.iter_indented_fence_spans(text, 0)) == list(
            iter_code_block_spans(text)
        ), f"spans disagree on the {name!r} document"


# --- protect_fenced_code / restore_fenced_code ----------------------------------


def test_protect_replaces_each_block_and_keeps_the_rest_verbatim():
    """Every block becomes its own token and the text around them is copied
    unchanged, so the caller's transformations see no code at all."""
    text = "intro\n```\na()\n```\nmiddle\n~~~\nb()\n~~~\noutro"
    protected, blocks = fenced_code.protect_fenced_code(
        text, spans=_simple_spans, placeholder=_placeholder
    )
    assert blocks == ["```\na()\n```", "~~~\nb()\n~~~"]
    assert protected == (f"intro\n{_placeholder(0)}\nmiddle\n{_placeholder(1)}\noutro")
    assert "a()" not in protected and "b()" not in protected


def test_protect_and_restore_round_trip_byte_for_byte():
    """The point of the mechanism: whatever happens to the placeholder text in
    between, restoring puts every sample back exactly as upstream wrote it."""
    text = "intro\n```python\nx = 1\n\n\n```\nmiddle\n"
    protected, blocks = fenced_code.protect_fenced_code(
        text, spans=_simple_spans, placeholder=_placeholder
    )
    # A transformation that rewrote the prose around the tokens.
    transformed = protected.replace("intro", "INTRO").replace("middle", "MIDDLE")
    assert fenced_code.restore_fenced_code(
        transformed, blocks, _placeholder
    ) == text.replace("intro", "INTRO").replace("middle", "MIDDLE")


def test_protect_honours_the_callers_span_policy():
    """The span finder is the adapter's policy: a finder that claims nothing
    leaves the text untouched, which is how an adapter keeps fence rules of
    its own without a second copy of this loop."""
    text = "```\nx\n```\n"
    protected, blocks = fenced_code.protect_fenced_code(
        text, spans=lambda _text: iter(()), placeholder=_placeholder
    )
    assert (protected, blocks) == (text, [])


def test_restore_skips_a_block_whose_token_is_gone():
    """A transformation may delete the markup a token sat on, leaving no
    position to restore that block to. The remaining blocks must still come
    back rather than the whole restore failing."""
    text = "a\n```\nfirst\n```\nb\n```\nsecond\n```\nc"
    protected, blocks = fenced_code.protect_fenced_code(
        text, spans=_simple_spans, placeholder=_placeholder
    )
    without_first = protected.replace(_placeholder(0), "")
    restored = fenced_code.restore_fenced_code(without_first, blocks, _placeholder)
    assert restored == "a\n\nb\n```\nsecond\n```\nc"


def test_restore_leaves_text_that_only_looks_like_a_token():
    """Only an exact token is a token: a pass is free to write text that
    resembles one -- an index no block was stashed under, a zero-padded index
    -- and that text is not a placeholder, so it keeps its own content instead
    of being replaced by an unrelated sample."""
    text = "looks like TESTFENCEBLOCK7PLACEHOLDER and TESTFENCEBLOCK00PLACEHOLDER\n"
    blocks = ["```\nfirst\n```", "```\nsecond\n```"]
    restored = fenced_code.restore_fenced_code(text, blocks, _placeholder)
    assert restored == text


def test_restore_handles_a_token_shape_with_no_constant_split():
    """The one-branch scan pattern applies only to the shape the adapters'
    factories produce. A caller whose tokens do not fit it -- here the index
    is written as repeated characters rather than digits -- still gets every
    block spliced, through the per-token route."""
    variable = _Placeholder(lambda index: "TOKEN" + "X" * index)
    text = f"{variable(0)}\nmiddle\n{variable(2)}\nend\n"
    blocks = ["```\nzero\n```", "```\none\n```", "```\ntwo\n```"]
    restored = fenced_code.restore_fenced_code(text, blocks, variable)
    assert restored == "```\nzero\n```\nmiddle\n```\ntwo\n```\nend\n"


def test_restore_many_blocks_completes_quickly():
    """Restoring must stay linear in the document length. Replacing the tokens
    one at a time re-scans the whole document once per block, which is
    quadratic in the block count: 20 000 blocks took 4.3 s that way and 0.02 s
    with the single pass. The threshold is far above the single-pass cost and
    far below the per-block cost, so the test measures the shape of the splice
    rather than the speed of the machine it runs on."""
    count = 20000
    blocks = [f"```python\nvalue = {index}\n```" for index in range(count)]
    text = "".join(
        f"prose {index}\n\n{_placeholder(index)}\n\n" for index in range(count)
    )
    started = time.monotonic()
    restored = fenced_code.restore_fenced_code(text, blocks, _placeholder)
    elapsed = time.monotonic() - started
    assert restored == "".join(
        f"prose {index}\n\n{blocks[index]}\n\n" for index in range(count)
    )
    assert elapsed < 1.0, f"splicing {count} blocks took {elapsed:.2f}s"


class _Placeholder:
    """Placeholder factory whose tokens do not carry a decimal index.

    A callable object rather than a lambda so the call is typed: the module
    hands the factory straight to ``restore_fenced_code`` as its
    ``placeholder`` argument.
    """

    def __init__(self, template):
        """Wrap *template*, a ``str -> str`` used to name one token."""
        self._template = template

    def __call__(self, index: int) -> str:
        """Return the token standing for the block stashed under *index*."""
        return self._template(index)
