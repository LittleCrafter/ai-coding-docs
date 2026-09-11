"""Fenced-code-block shielding shared by the source adapters.

Several adapters convert a page through text passes -- rewriting cross-links,
stripping JSX, converting components -- that must never touch a code sample: a
snippet containing a documentation URL, an ``import`` line, or a JSX tag is
code, and rewriting it would change what the sample says. The technique is the
same everywhere, and the same one ``core.html_markdown`` uses for ``<pre>``
elements: lift every fenced block OUT of the text, put an opaque placeholder
token in its place, run the transformations on what remains, and splice the
originals back verbatim.

This module owns the two halves of that technique, plus the fence scanner the
adapters that need it share:

* :func:`protect_fenced_code` -- the extraction: walk the spans, stash each
  block, emit a token per block (parameterised by the span finder and the
  placeholder factory);
* :func:`restore_fenced_code` -- the splice that puts every stashed block back
  at the position its token ended up (a transformation may move or re-indent a
  token, which is exactly why the blocks are restored by token rather than by
  offset);
* :func:`iter_indented_fence_spans` -- the span finder for adapters that must
  also shield a fence indented by a few columns (a sample inside a list item),
  built on the column-zero scanner in :mod:`~.html_markdown`.

Source-specific policy stays with the adapter, and only the mechanism lives
here: WHICH fences count is the adapter's choice (it passes its own span
finder when its fence rules differ from the shared ones), and what a token
looks like is its placeholder factory's choice. Nothing in this module knows
about a concrete source.
"""

from __future__ import annotations

import re
from bisect import bisect_right
from collections.abc import Callable, Iterator

from .html_markdown import iter_code_block_spans

# The largest indentation, in columns, a fenced code block may carry and still
# be a fence: CommonMark reads four or more leading spaces as an indented code
# block instead, with the fence line as literal text. Used as the default for
# :func:`iter_indented_fence_spans`.
MAX_FENCE_INDENT = 3


def iter_indented_fence_spans(
    text: str, max_indent: int = MAX_FENCE_INDENT
) -> Iterator[tuple[int, int]]:
    """Yield the ``(start, end)`` span of every fenced code block in *text*.

    Same spans as the shared :func:`~.html_markdown.iter_code_block_spans`
    scanner, with one difference: a fence indented by up to *max_indent*
    columns is recognised here, where the shared scanner sees column-zero
    fences only. Upstream indents a sample that sits inside a list item -- the
    list marker pushes the whole item's content right -- and CommonMark still
    reads a fence indented that far as a fence. Those blocks need shielding
    exactly like a top-level one: a sample in a list item quotes documentation
    URLs just as often, and rewriting it would change what the sample says.

    The fence semantics stay with the shared scanner, which is fed a copy of
    *text* with up to *max_indent* leading spaces removed from every line --
    exactly the transformation that turns an indented fence into a column-zero
    one. A line indented further than that is an indented code block, not a
    fence, in either form: removing *max_indent* of its spaces leaves it
    indented, so the copy can neither gain nor lose a fence there. A tab is
    left alone: it advances to the next multiple of four columns, which is out
    of fence range however it is written, and its width is not knowable here.

    Each span the scanner reports in that copy is mapped back through the
    per-line offsets, so the caller receives the original text of the block.
    The span starts where the opening fence character sits in *text*: at the
    line start for a column-zero fence, and past the indentation for an
    indented one, so a shielded block keeps the column the page wrote it at.
    The indentation is deliberately left OUTSIDE the span: it stays in the
    surrounding text, where a pass that re-indents a container reads it.
    """
    lines = text.split("\n")
    shifts = [min(len(line) - len(line.lstrip(" ")), max_indent) for line in lines]
    starts: list[int] = []
    indented_starts: list[int] = []
    offset = 0
    indented_offset = 0
    for line, shift in zip(lines, shifts):
        starts.append(offset)
        indented_starts.append(indented_offset)
        offset += len(line) + 1
        indented_offset += len(line) - shift + 1
    indented = "\n".join(line[shift:] for line, shift in zip(lines, shifts))

    def to_source(index: int) -> int:
        """Map an offset of the de-indented copy back to one of *text*."""
        line = bisect_right(indented_starts, index) - 1
        return starts[line] + shifts[line] + (index - indented_starts[line])

    for start, end in iter_code_block_spans(indented):
        yield to_source(start), to_source(end)


def protect_fenced_code(
    text: str,
    *,
    spans: Callable[[str], Iterator[tuple[int, int]]],
    placeholder: Callable[[int], str],
) -> tuple[str, list[str]]:
    """Replace every fenced code block in *text* with an opaque placeholder.

    Returns the placeholder-embedded text plus the list of original fenced
    blocks (opening fence, body, closing fence) in document order, so
    :func:`restore_fenced_code` can splice each one back after the caller has
    run its transformations on the placeholder text.

    *spans* supplies the blocks and *placeholder* names them. Both are
    arguments rather than fixed behaviour because they are the two things that
    differ between sources -- which fences count as a block, and what a token
    looks like -- while the extraction loop itself is identical everywhere:
    copy the text before the block, stash the block, emit the token for its
    index, and continue after it. Document order gives every block a stable
    index, which is what ties a token back to its block without any matching
    step.

    The token must be a string the surrounding text cannot already contain and
    the caller's transformations cannot produce, and it should be plain
    (alphanumeric, or an HTML comment) so those transformations pass it
    through untouched. A token that a pass rewrites would no longer be found
    by :func:`restore_fenced_code` and its block would be lost -- which is why
    each adapter's factory carries a name that identifies it.

    *spans* is called once, over the whole of *text*, and the spans it yields
    must be ASCENDING (each start at or after the previous span's end) and
    NON-OVERLAPPING. The extraction loop relies on both: it copies the text
    between two consecutive spans, so an out-of-order span would be stitched
    back into the document at the wrong offset, and an overlapping one would
    be lifted twice, with the second copy replacing the first at a span that
    its own token had already shifted. Both properties hold for every finder
    this module ships (a single forward scan cannot produce anything else),
    and a finder an adapter supplies its own has to preserve them.
    """
    blocks: list[str] = []
    segments: list[str] = []
    pos = 0
    for start, end in spans(text):
        segments.append(text[pos:start])
        index = len(blocks)
        blocks.append(text[start:end])
        segments.append(placeholder(index))
        pos = end
    segments.append(text[pos:])
    return "".join(segments), blocks


def _indexed_token_pattern(tokens: list[str]) -> re.Pattern[str] | None:
    """Return a ONE-branch pattern matching every token in *tokens*, or ``None``.

    The adapters' placeholder factories all build a token out of a constant
    prefix, the stashed block's index, and a constant suffix, so a single
    ``prefix\\d+suffix`` branch recognises the whole set. That matters because
    the alternative -- one branch per token -- costs the engine a comparison
    per branch at every position it reaches, which grows with the token count:
    20 000 tokens took 1.6 s to scan, against 0.03 s for the one-branch form.
    The pattern only NAMES candidates; which of them are real tokens is
    decided by the caller's lookup, so a text that merely looks like a token
    is left alone.

    The shape is VERIFIED against every token rather than assumed, and a set
    that does not fit it yields ``None``, which sends the caller down the
    always-correct per-token route. The candidate split points come from the
    token of index 0, whose index digits are a single ``"0"``: each ``0`` in
    it is tried as that token's index position, and the split that reproduces
    all the others is the shape.
    """
    if not tokens:
        return None
    first = tokens[0]
    for at, char in enumerate(first):
        if char != "0":
            continue
        prefix, suffix = first[:at], first[at + 1 :]
        if all(
            token == f"{prefix}{index}{suffix}" for index, token in enumerate(tokens)
        ):
            return re.compile(rf"{re.escape(prefix)}(?:\d+){re.escape(suffix)}")
    return None


def restore_fenced_code(
    text: str, blocks: list[str], placeholder: Callable[[int], str]
) -> str:
    """Splice the fenced code blocks lifted by :func:`protect_fenced_code` back.

    The inverse of :func:`protect_fenced_code`: each placeholder token is
    replaced by the exact block that was stashed under its index, so every
    sample reappears byte for byte -- no transformation was applied to it
    while it was lifted out.

    A block whose token is no longer present in *text* cannot be spliced and
    is skipped silently: a transformation is allowed to delete the markup
    around a token (a component that wrapped a code block, say), and there is
    no position left to restore that block to. The token itself is preserved
    by every caller's passes, so this is a property of the surrounding text
    rather than a case the callers have to detect.

    Every token is spliced in ONE left-to-right pass over *text*: the tokens
    are turned into a single pattern, and each match is replaced by the block
    it stands for. Replacing them one at a time instead -- a ``str.replace``
    per block, as this function used to -- re-scans the whole document once
    per block, which is quadratic in the block count and cost 1.9 s on the
    largest mirrored page (828 blocks). The single pass is linear in the
    document length plus the length of the pattern.

    The pattern comes from :func:`_indexed_token_pattern` -- one branch for
    the whole set -- and falls back to an alternation of the tokens, longer
    ones first, when they do not share that shape. Longer-first keeps a
    shorter token from claiming a match where a longer one starts; the
    factories all append the block's index before a fixed suffix, which
    already prevents one token from being a prefix of another, and the
    ordering makes the splice independent of that property rather than
    relying on it. Only an exact token is spliced: a match that is not one of
    the tokens -- text that merely looks like a token carrying an index no
    block was stashed under -- is left exactly as it was. Replacement is not
    rescanned, so a block that literally contained another block's token
    would keep it verbatim rather than having it substituted -- impossible
    under the token contract documented on :func:`protect_fenced_code`.
    """
    if not blocks:
        return text
    tokens = [placeholder(index) for index in range(len(blocks))]
    pattern = _indexed_token_pattern(tokens)
    if pattern is None:
        pattern = re.compile(
            "|".join(
                re.escape(token) for token in sorted(tokens, key=len, reverse=True)
            )
        )
    by_token = dict(zip(tokens, blocks))
    return pattern.sub(lambda match: by_token.get(match.group(0), match.group(0)), text)
