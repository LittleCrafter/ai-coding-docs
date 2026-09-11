"""Shared HTML-to-Markdown conversion utilities for source adapters.

This module owns the conversion pipeline used for HTML-to-Markdown source
adapters (such as ``sources/deepseek.py``) and code block protection utilities
used across sources (including ``sources/opencode.py``): creating a configured
``html2text.HTML2Text`` instance, pre-extracting ``<pre>`` code blocks from
BeautifulSoup trees, splicing them back in as fenced code blocks after
conversion, stripping the invisible Unicode characters that web markup leaves
behind, collapsing excessive blank lines while preserving blank lines inside
fenced code blocks, and running the whole fetch-convert-validate-hash
sequence behind the pipeline's ``fetch_markdown`` hook.

The shared utilities provided are:

* ``iter_code_block_spans()`` -- the linear scanner locating complete
  fenced code blocks (it replaced a regex whose lazy body made unclosed
  fences a quadratic-time hazard);
* ``make_converter()`` -- the configured ``html2text.HTML2Text`` factory;
* ``extract_code_blocks()`` -- the ``<pre>``-extraction skeleton (grouping
  blocks by their replacement target, sanitising language labels, swapping
  in placeholder tokens), parameterised by container CSS class and
  language-detection callback;
* the blank-line-collapse loop (driven by ``iter_code_block_spans()``,
  collapsing ``\\n{3,}`` only in the gaps between blocks);
* ``strip_invisible_characters()`` -- the Cf/Cc character filtering pass;
* ``fetch_markdown_converted()`` -- the fetch / convert / validate / hash
  sequence that ``fetch_markdown`` pipeline hooks run.

The ``iter_code_block_spans()`` scanner locates complete fenced code blocks in
the Markdown text so the blank-line-collapse pass can skip over code-block
interiors -- blank lines inside code are semantically significant (they
separate code paragraphs, mark the end of multi-line strings, etc.) and must
survive verbatim. It recognises COLUMN-ZERO fences only, which is the rule the
collapse pass needs; the adapters that must also shield a fence indented
inside a list item widen it through :mod:`~.fenced_code`, which is also where
the extract -> transform -> splice mechanism those adapters share lives.
"""

from __future__ import annotations

import re
import sys
import unicodedata
from bisect import bisect_right
from collections.abc import Callable, Iterator
from typing import TYPE_CHECKING

import bs4
import html2text
from bs4.element import NavigableString, PageElement

from . import fetch

if TYPE_CHECKING:
    # Annotation-only imports: ``from __future__ import annotations`` keeps
    # these annotations from being evaluated at runtime. ``httpx`` is only
    # needed to annotate the client parameter of ``fetch_markdown_converted``
    # (the pipeline and the test doubles duck-type the client interface), and
    # ``Page`` only to annotate the page parameter -- pulling the page model
    # in at runtime would add an import edge this leaf module does not need.
    import httpx

    from .page import Page


def make_converter() -> html2text.HTML2Text:
    """Create a configured HTML2Text converter for the docs mirror.

    This factory is the single source of truth for html2text configuration
    across all HTML-to-Markdown source adapters. It is instantiated per
    call (not stored at module level) because ``HTML2Text`` is both mutable
    and stateful during ``handle()`` -- a shared instance would not be
    safe if the pipeline ever ran source adapters concurrently within one
    process. Creating a fresh converter per conversion avoids any risk of
    cross-thread interference entirely.

    Configuration rationale, option by option:

    * ``body_width = 0`` -- Disables line wrapping entirely. This is the
      REAL html2text knob: the ``HTML2Text()`` constructor accepts a
      ``bodywidth`` parameter and copies it into ``self.body_width``, so
      assigning to ``h.bodywidth`` would silently create a dead attribute
      that the wrapping logic never reads. Since html2text 2025.4.15 (the
      floor pinned in ``pyproject.toml`` dependencies), ``optwrap()``
      returns the text unchanged when ``body_width`` is falsy. Older
      releases ignored ``bodywidth=0`` and wrapped anyway, which is why
      this project previously used a huge sentinel value (10_000_000
      bytes) as a workaround. The floor version constraint guarantees the
      falsy-means-no-wrap behaviour.

    * ``ignore_links = False`` -- Preserve hyperlinks. Documentation
      pages cross-reference heavily (links to other pages, to API
      references, to external resources), and those links are valuable
      in the mirrored Markdown. Dropping them would silently remove
      navigable structure from the mirror.

    * ``ignore_images = True`` -- Drop ``<img>`` tags. Documentation
      images (screenshots, logos, diagrams) reference binary files that
      the mirror does not download, so an ``<img>`` tag in Markdown would
      render as a broken image. Stripping them keeps the output clean.

    * ``protect_links = True`` -- Prevent line-wrapping inside link URLs.
      URLs can be long (particularly Docusaurus-generated ones), and a
      line break in the middle of a URL would silently break the link in
      the mirrored Markdown. With ``body_width = 0`` this is technically
      redundant (no wrapping happens at all), but it is kept as a
      belt-and-suspenders guard in case a future html2text release changes
      the ``body_width = 0`` contract.

    * ``unicode_snob = True`` -- Keep Unicode characters as-is instead of
      ASCII-ifying them. Documentation pages routinely use Unicode
      (em-dashes, smart quotes, arrows, mathematical symbols), and
      converting them to ASCII approximations would degrade readability
      and accuracy of the mirror.

    The tested html2text version range is exactly what ``uv.lock``
    resolves (currently 2025.4.15) against the ``html2text>=2025.4.15``
    floor in ``pyproject.toml``. The option combination above is a stable,
    long-standing part of the html2text API, so newer releases are expected
    to behave identically. If a future release ever changes the behaviour
    of one of these options, the conversion tests in
    ``tests/test_adapters.py`` pin the exact expected output and will fail
    loudly on any behavioural drift.
    """
    h = html2text.HTML2Text()
    h.body_width = 0  # Disable wrapping (requires html2text >= 2025.4.15)
    h.ignore_links = False  # Preserve cross-reference hyperlinks
    h.ignore_images = True  # Drop <img> tags (binary files not mirrored)
    h.protect_links = True  # Keep URLs intact (no mid-URL line breaks)
    h.unicode_snob = True  # Preserve Unicode characters verbatim
    return h


# Complete fenced code blocks are located by the linear line scanner
# ``iter_code_block_spans`` below (no regex), so the blank-line-collapse
# pass and the adapters' fence protectors in ``core.fenced_code`` never
# touch the interior of a code block (blank lines and JSX-looking lines
# inside code are semantically significant). A block is:
#
#   * an opening fence of 3+ backticks (```) or tildes (~~~), optionally
#     followed by an info string on the same line, and a terminating
#     newline;
#   * the block body, spanning any number of lines;
#   * a closing fence that is the SAME string as the opening one (same
#     fence character AND same length), at line start, with optional
#     trailing whitespace or carriage-return characters (``[ \t\r]``).
#
# Requiring the closing fence to be the EXACT SAME string as the opening
# fence is STRICTER than the CommonMark specification, which requires the
# same fence character but only mandates that the closing fence be AT LEAST
# AS LONG as the opening sequence (CommonMark allows a 5-backtick opening
# fence to be closed by 6 or more backticks). This scanner (like the regex
# it replaced) does not match such a longer fence, so technically some
# valid CommonMark documents are not recognised as containing a block.
#
# In practice, this strictness is harmless: ``html2text`` always generates
# closing fences that are byte-identical to the opening fence (it never
# produces a longer or shorter closing sequence). Every code block in the
# mirror's input is produced by ``html2text``, so the exact-match rule
# always succeeds. Without it, the first bare `` ``` `` inside a block body
# would close the fence and the blank-line-collapse pass would start
# modifying the remaining code text -- corrupting it.
#
# The ``[ \t\r]`` tolerance after the closing fence handles the edge case
# where raw Windows-style ``\r\n`` line endings reach this point.
# BeautifulSoup normalises line endings to ``\n`` during HTML parsing
# today, so ``\r`` never appears in this adapter's output under current
# conditions; but if a future code path feeds text through the collapse
# pass without going through BeautifulSoup first (e.g. a new source adapter
# that fetches pre-converted Markdown from an endpoint that uses CRLF), a
# stray ``\r`` after the closing fence would otherwise prevent the block
# from matching -- and an unmatched block means its blank lines lose
# protection and get collapsed, silently corrupting the code samples.
# Accepting ``\r`` costs nothing and prevents a subtle, hard-to-diagnose
# data corruption.
#
# Line starts are recognised only after ``\n`` (never after a bare ``\r``
# or a Unicode line separator), matching the behaviour of a MULTILINE
# ``^`` anchor.
#
# BACKTRACKING HAZARD (why this is a line scanner, not a regex): the
# natural regex form ``^(`{3,}|~{3,})[^\n]*\n[\s\S]*?^\1[ \t\r]*$`` is
# O(N x body length) on input with N unclosed opening fences. When no
# closing fence exists, the lazy ``[\s\S]*?`` expands all the way to
# end-of-string looking for a closer, fails, and the regex engine retries
# the whole scan from the NEXT unclosed opener -- every unclosed fence
# costs one full scan of the remaining body. The collapse pass runs on
# converter output derived from network-fetched pages, and the OpenCode
# adapter runs the fence matcher on raw network MDX of up to
# ``MAX_RESPONSE_BYTES`` (10 MiB), making this a remotely-triggerable hang
# (measured on the equivalent three-backtick pattern in ``core.fetch``:
# 20,000 lines of ``"```python\n"`` -- ~140 KB -- did not finish in 180 s;
# 2,000/4,000/8,000 openers took 0.32/1.27/5.30 s here, the classic
# 4x-per-2x quadratic signature). A tempered body does NOT fix this: it
# changes which lines the body may contain, not the per-opener scan-to-end
# failure cost. The scanner below is linear instead (see its docstring for
# the monotonicity argument).


def _leading_fence_run(line: str) -> str:
    """Return the maximal leading run of backticks or tildes in *line*.

    Returns ``""`` when the line does not start with a fence character.
    The run is maximal (every leading fence character is included), matching
    the greedy ``{3,}`` quantifier of the regex this scanner replaces; the
    caller decides whether the run is long enough to act as a fence.
    """
    if not line or line[0] not in "`~":
        return ""
    end = 1
    while end < len(line) and line[end] == line[0]:
        end += 1
    return line[:end]


def iter_code_block_spans(text: str) -> Iterator[tuple[int, int]]:
    """Yield ``(start, end)`` spans of every complete fenced code block.

    Spans are non-overlapping, in document order, and each runs from the
    opening fence's line start through the end of the closing fence line
    (the closing line's trailing newline is NOT included).

    Only COLUMN-ZERO fences are recognised here -- a fence indented by any
    amount is ordinary text to this scanner. That is deliberate: it is the
    exact fence rule the blank-line-collapse pass must apply (the collapse
    input is converter output, whose fences always start at column zero),
    and keeping the scanner on one unambiguous rule is what makes its
    linear-time guarantee easy to reason about. An adapter that must also
    shield fences inside list items wraps this scanner in a de-indent pass of
    its own (see :func:`~.fenced_code.iter_indented_fence_spans`), leaving
    these semantics untouched for every other caller.

    Matching rules:

    * An opener is a line whose leading fence run is 3+ backticks or 3+
      tildes, followed by anything (the info string), and terminated by a
      newline -- an opener-shaped LAST line of the document (no trailing
      newline) can never open a block, because a block needs the newline
      after the info string to have a body at all.
    * The opener's effective fence is not always its maximal run: a
      six-backtick opener CAN be closed by a three-backtick fence (the
      three extra backticks then reading as part of the info string). The
      scanner decides this by trying run lengths from the longest down to
      three and using the longest length that has a closer anywhere ahead
      of the opener.
    * A closer is a line consisting of exactly that fence string plus
      optional trailing spaces, tabs, or carriage returns. The first closer
      after the opener wins, and scanning resumes on the line after the
      closer (non-overlapping matches).
    * An opener with no closer at any tried length matches nothing: it is
      ordinary text, and scanning continues on the next line.

    LINEAR-TIME ARGUMENT (why this cannot go quadratic): all pure-fence
    closer lines are collected in ONE pass into per-fence-string sorted
    index lists. Each opener then locates its first possible closer with a
    ``bisect_right`` per tried fence length -- O(log n) each, and the number
    of tried lengths is bounded by the opener line's own length -- so N
    unclosed openers cost O(N log N) total rather than the O(N x body
    length) a per-opener scan to the end of the document would cost.
    """
    # Split on "\n" only (never ``str.splitlines``): a line start here means
    # a position right after ``\n``, so a fence following a bare ``\r`` or a
    # Unicode line separator must NOT count as an opener or closer.
    parts = text.split("\n")
    offsets: list[int] = []
    offset = 0
    for part in parts:
        offsets.append(offset)
        offset += len(part) + 1
    # Closer candidates per exact fence string, collected once: a line
    # whose leading fence run is 3+ characters and whose remainder is only
    # spaces, tabs, or carriage returns. A line can be both an opener and a
    # closer candidate (e.g. a bare "```" line); which role it plays is
    # decided by scan order, matching the regex's leftmost-match resolution.
    occurrences: dict[str, list[int]] = {}
    for i, part in enumerate(parts):
        run = _leading_fence_run(part)
        if len(run) >= 3 and all(c in " \t\r" for c in part[len(run) :]):
            occurrences.setdefault(run, []).append(i)

    last = len(parts) - 1
    i = 0
    while i < last:  # the opener needs a following "\n" (see docstring)
        run = _leading_fence_run(parts[i])
        advanced = False
        # Try the greedy run longest-first, down to three characters,
        # replicating the old ``{3,}`` backtracking order.
        for length in range(len(run), 2, -1):
            candidates = occurrences.get(run[:length])
            if candidates is None:
                continue
            k = bisect_right(candidates, i)
            if k < len(candidates):
                closer = candidates[k]
                yield offsets[i], offsets[closer] + len(parts[closer])
                i = closer + 1
                advanced = True
                break
        if not advanced:
            i += 1


# The control characters (category "Cc") that ARE document structure rather
# than noise, and therefore survive :func:`strip_invisible_characters`: tab,
# line feed, and carriage return. Membership is checked before the category
# call, so the common characters on a documentation page cost nothing.
_PRESERVED_CONTROL_CHARACTERS = frozenset("\t\n\r")


def strip_invisible_characters(text: str) -> str:
    """Remove invisible Unicode characters from *text*.

    Two Unicode categories are dropped, because both are invisible in a
    rendered document yet survive the HTML-to-Markdown conversion and end up
    in the mirror's Markdown files, where they silently corrupt copy-paste,
    diffs, and string searches:

    * **Cf (format)** -- code points used for text shaping, bidirectional
      ordering, and encoding metadata. The most commonly encountered ones in
      documentation contexts are U+200B ZERO WIDTH SPACE (used by web
      frameworks for layout micro-adjustments), U+FEFF BOM / ZERO WIDTH
      NO-BREAK SPACE (a byte-order mark some tools prepend to UTF-8 content),
      U+200E LEFT-TO-RIGHT MARK and U+200F RIGHT-TO-LEFT MARK (inserted by
      bidirectional-text engines), U+200C ZERO WIDTH NON-JOINER and U+200D
      ZERO WIDTH JOINER, and U+2060 WORD JOINER.
    * **Cc (control)** -- the C0/C1 control range, except the three that ARE
      document structure and must survive: TAB (U+0009), LINE FEED (U+000A),
      and CARRIAGE RETURN (U+000D). A NUL byte (U+0000) is the one that
      actually shows up in practice: it makes a mirrored page BINARY to
      ``git`` and to ``grep``, so the file silently drops out of every diff,
      every search, and every text-mode tool. Control characters are also
      rejected outright by most Markdown toolchains, so keeping one buys
      nothing.

    Filtering by Unicode category (``unicodedata.category(c)``) is more
    robust than maintaining a blocklist of individual code points: the
    Unicode standard can assign new Cf characters in future versions, and a
    category-based filter catches them all automatically without needing to
    update a hardcoded list. The cost is one ``unicodedata.category`` call
    per character, which is acceptable for documentation pages (typically a
    few tens of thousands of characters at most).

    The three whitespace controls are kept because they are line structure,
    not noise: dropping TAB would re-indent code samples and dropping the
    line terminators would concatenate every line of a page. Every other
    control character carries no rendering the caller could want.

    The return value is a new string; the input is never modified in place
    (Python strings are immutable).
    """
    return "".join(
        c
        for c in text
        if c in _PRESERVED_CONTROL_CHARACTERS
        or unicodedata.category(c) not in ("Cf", "Cc")
    )


def collapse_blank_lines(text: str) -> str:
    """Collapse runs of 2+ blank lines down to ONE blank line, but ONLY
    outside fenced code blocks.

    HTML-to-Markdown conversion can leave long stretches of blank lines in
    the output (from removed HTML elements, from the gap between nav chrome
    and content, from the html2text post-processing of block-level elements
    like ``<div>`` and ``<section>``). The collapse operates on newline
    runs: every run of 3+ consecutive ``\\n`` characters -- i.e. 2 or more
    blank lines -- is rewritten to exactly ``\\n\\n``, a single blank line.
    A single blank line (``\\n\\n``) is already the canonical paragraph
    separator and is left untouched.

    Blank lines INSIDE fenced code blocks are semantically significant:
    they separate code paragraphs, mark the end of a multi-line string,
    indicate a blank line in a data sample, etc. Collapsing them would
    silently corrupt the code samples in the mirror. The fix is to locate
    every complete fenced code block -- opening fence, body, closing fence
    -- with ``iter_code_block_spans``, collapse blank runs only in the
    non-code GAPS between blocks, and copy each block's spanned text
    through verbatim without modification.

    The result is assembled from alternating gap-collapsed text segments
    and verbatim code-block segments in document order. The trailing gap
    after the last code block is also collapsed. A document with no code
    blocks at all is simply regex-collapsed in full, which is equivalent
    to the gap between the (empty) block list and the trailing text.

    The block locator this relies on is also the base of the fence scanner the
    shielding adapters share (``core.fenced_code``) -- which is why
    ``iter_code_block_spans`` is a module-level function rather than being
    re-derived per call.
    """
    segments: list[str] = []
    # Position cursor tracking how far through the document we have already
    # processed. This marks the start of the next non-code gap that needs
    # blank-line collapsing. It advances past each code block as it is
    # matched, so the gap between consecutive blocks is handled correctly.
    pos = 0

    # Walk through every fenced code block in document order. For each
    # block found, there is a "gap" region before it (the text between
    # the end of the previous code block and the start of this one) and
    # the code block itself. Gaps get their blank-line runs collapsed;
    # code blocks are copied verbatim without any modification.
    for start, end in iter_code_block_spans(text):
        # Gap before this code block: this is the region of text from
        # the end of the previous block (or from the start of the document
        # if this is the first block) up to the start of this block. Any
        # run of three or more consecutive newline characters in this gap
        # is collapsed down to exactly two newlines.
        segments.append(re.sub(r"\n{3,}", "\n\n", text[pos:start]))

        # The code block itself: copy the entire spanned region verbatim
        # (opening fence, code body, closing fence) without any blank-line
        # modification. Blank lines inside code are semantically
        # significant and must survive unaltered.
        segments.append(text[start:end])

        # Advance the position cursor past this block so the next
        # iteration of the loop processes the gap that starts right
        # after this block's closing fence.
        pos = end

    # Trailing gap after the last code block (or the entire document when
    # there are no code blocks at all). When the document has no code
    # blocks, the loop above never executes, ``pos`` stays at 0, and
    # ``segments`` is empty, so this single append processes the entire
    # document as one big gap -- which is the correct behaviour.
    segments.append(re.sub(r"\n{3,}", "\n\n", text[pos:]))

    # Concatenate all gap-collapsed segments and verbatim code-block
    # segments back into a single document string in their original order.
    return "".join(segments)


def _pre_text(pre: bs4.Tag) -> str:
    """Return the text of one ``<pre>`` with the line breaks of its markup intact.

    ``Tag.get_text()`` joins every descendant string with the separator (empty
    here) and DROPS the line breaks a code block expresses as markup: a
    syntax highlighter renders each code line as
    ``<span class="token-line">...</span><br>``, and a ``<br>`` element
    contributes no text of its own. Such a block read with ``get_text()``
    collapses onto a single line -- the characters are all still there, but
    every newline is gone, which is corruption for anyone reading or copying
    the sample. (Docusaurus/Prism markup, the shape this pipeline converts,
    is exactly that.)

    This walk therefore keeps document order and turns each ``<br>`` into a
    newline. Text nodes are taken exactly as ``get_text()`` takes them, so a
    block whose newlines are already literal text -- the shape a plain
    ``<pre>`` produces -- is returned unchanged.

    The line-break element is the only child handled specially: any other
    element contributes its text and nothing else, so nesting, inline spans,
    and entity decoding all behave as they did with ``get_text()``.

    Comment nodes contribute nothing, exactly as ``get_text()`` skips them.
    Taking every ``NavigableString`` would let a comment's own text into the
    sample: a rendered React tree writes an empty ``<!-- -->`` between two
    adjacent text nodes, and reading that as text would splice its content --
    ``" "`` for the separator, or a source comment's whole body for a
    comment the page carries -- into the middle of a code line.
    """
    parts: list[str] = []
    for node in pre.descendants:
        if isinstance(node, bs4.Comment):
            continue
        if isinstance(node, NavigableString):
            parts.append(str(node))
        elif isinstance(node, bs4.Tag) and node.name == "br":
            parts.append("\n")
    return "".join(parts)


def extract_code_blocks(
    content: bs4.Tag | bs4.BeautifulSoup,
    soup: bs4.BeautifulSoup,
    *,
    container_class: str,
    detect_language: Callable[[bs4.Tag, bs4.Tag | None], str],
    placeholder: Callable[[int], str],
) -> list[tuple[str, str]]:
    """Replace every ``<pre>`` under *content* with a placeholder token.

    Returns ``(language, code_text)`` pairs in document order, aligned with
    the placeholder indices: each pair's index is its position in the
    returned list, which matches the argument passed to *placeholder* when
    the token for that block was generated. ``splice_code_blocks`` relies
    on exactly this alignment to swap each token back for its fenced block.

    Extraction happens BEFORE html2text runs because html2text renders
    ``<pre>`` as an indented block: it re-wraps the text, loses the
    language tag, and decorates the output with the site's code-block
    chrome (header bars, copy buttons, line numbers). Splicing fenced
    blocks back in afterwards keeps the code verbatim -- indentation and
    blank lines included.

    **Replacement-target grouping (why the ``id()`` keys exist).** When a
    ``<pre>`` sits inside a ``<div>`` carrying *container_class*, the WHOLE
    container is replaced by the token, which also removes the header bar,
    copy button, and any other block chrome in one move. A bare ``<pre>``
    (no container) is replaced by itself. One container can hold several
    ``<pre>`` elements (tabbed/split code examples are a realistic pattern
    on both mirrored sites), so the ``<pre>`` elements are first grouped by
    the element their replacement will swap out, and each group is replaced
    exactly once.

    Attempting ``replace_with`` per-``<pre>`` would break on a shared
    container: the first ``replace_with`` detaches the container (and every
    other ``<pre>`` inside it) from the tree, and a second ``replace_with``
    on the already-detached container raises ``ValueError`` ("element ...
    is not part of a tree") -- while the second block's text would be lost
    entirely even if the error were swallowed.

    The groups are keyed by ``id()`` of the replacement target. ``id()``
    is a safe key here because every target element stays alive --
    referenced by the soup tree or by the groups dict -- for the whole
    function, so no two distinct live elements can share an id and no id
    can be recycled mid-loop.

    The container located during grouping is stored alongside the target so
    *detect_language* can reuse it instead of walking back up the tree a
    second time: within one group every ``<pre>`` shares the same
    replacement target, and that target IS the container when one exists
    (otherwise the target is the bare ``<pre>`` and the container is None),
    so one lookup per group is both sufficient and exact.

    Args:
        content: The content subtree to scan for ``<pre>`` elements. May be
            a ``bs4.Tag`` or a whole ``bs4.BeautifulSoup`` document (the
            adapters' container-fallback chain can pass either); both
            support ``find_all``. The tree is MUTATED in place -- every
            replacement target is swapped for its token string.
        soup: The ``BeautifulSoup`` document *content* belongs to, used to
            manufacture the replacement ``NavigableString`` tokens so they
            live in the same tree as the elements they replace.
        container_class: The CSS class identifying the code-block wrapper
            ``<div>`` (``theme-code-block`` for DeepSeek / Docusaurus). A
            ``<pre>`` with no such ancestor becomes its own replacement target.
        detect_language: Callback ``(pre, container) -> str`` returning the
            raw language label for one ``<pre>``; ``container`` is the
            wrapper div already located during grouping (shared by every
            ``<pre>`` in that group), or ``None`` for a bare ``<pre>``. It
            may return ``""`` when no label exists -- the fenced block then
            gets no info string. Sanitisation happens HERE, not in the
            callback, so callbacks can return raw site text.
        placeholder: Callable ``(index: int) -> str`` returning the
            placeholder token for a block index (the adapter's
            ``_code_placeholder``). The token must be plain alphanumerics
            so html2text passes it through unescaped and unwrapped; see
            ``splice_code_blocks`` for the other half of that contract.

    Returns:
        ``(language, code_text)`` pairs in document order. ``language`` is
        sanitised to ``[A-Za-z0-9_+#.-]`` -- the label is spliced raw into
        the fence info string, so a stray backtick would close or reopen
        the fence, a newline or space would break the fence line, and fence
        info strings have no escaping mechanism, making removal the only
        safe option. ``code_text`` is the verbatim ``<pre>`` text with only
        the trailing newline stripped (``rstrip("\\n")`` preserves internal
        blank lines; the trailing one BeautifulSoup appends after
        block-level elements is cosmetic and would add a needless blank
        line at the end of every fenced block).
    """
    blocks: list[tuple[str, str]] = []
    # Group by replacement target, preserving document order. ``id()`` is a
    # safe key here because every target element stays alive (referenced by
    # the soup tree or by this dict) for the whole function.
    groups: dict[int, tuple[bs4.Tag | None, PageElement, list[bs4.Tag]]] = {}
    order: list[int] = []
    # First pass: walk every <pre> element in the content area and group
    # them by their replacement target (the outermost container div, or the
    # <pre> itself when there is no container). Grouping by target is
    # load-bearing: if one container holds several <pre> elements (tabbed
    # or split code examples), they must be replaced together -- the target
    # is replaced exactly ONCE per group, so every <pre> inside it
    # contributes a placeholder token to the single replacement string.
    for pre in content.find_all("pre"):
        if pre.find_parent("pre"):
            continue
        # Walk up the tree from this <pre> to find the nearest ancestor div
        # with the container class. If no such container exists (unusual,
        # but possible when a page uses a bare <pre> outside the site's
        # component model), None is returned and the <pre> itself becomes
        # the replacement target.
        container = pre.find_parent("div", class_=container_class)
        target: PageElement = container if container is not None else pre
        key = id(target)
        if key not in groups:
            groups[key] = (container, target, [])
            order.append(key)
        groups[key][2].append(pre)
    # Second pass: for each replacement target (in document order), extract
    # every <pre>'s language label and code text, build placeholder tokens,
    # and swap the entire target out of the BeautifulSoup tree in one
    # operation.
    for key in order:
        container, target, group_pres = groups[key]
        tokens: list[str] = []
        for pre in group_pres:
            # The container handed to the callback is the one already
            # located during grouping above (shared by every <pre> in this
            # group), NOT a fresh find_parent walk. The two would always
            # return the same element, so re-walking would be wasted work
            # on code-heavy pages and a consistency hazard if the container
            # class ever changes (two places to update instead of one).
            language = detect_language(pre, container)
            # The language label is spliced raw into the fence info string
            # (```LANG), so it must be a single safe token. A stray
            # backtick would close or reopen the fence, a newline or space
            # would break the fence line, and any non-ASCII character would
            # be ambiguous in a CommonMark info string. Unsafe characters
            # are stripped rather than escaped because fence info strings
            # have no escaping mechanism -- the only safe option is to
            # remove everything outside the widely-accepted set of
            # alphanumerics plus ``_``, ``+``, ``#``, ``.``, and ``-``.
            language = re.sub(r"[^A-Za-z0-9_+#.-]", "", language)
            # ``_pre_text`` returns the full text content of the <pre>
            # element, with all HTML tags removed, entities decoded, and
            # every markup line break turned back into a newline (see its
            # docstring for why ``get_text()`` cannot be used here). The
            # trailing newline that BeautifulSoup appends after block-level
            # elements is stripped with ``rstrip("\n")`` -- it is cosmetic
            # and would add a needless blank line at the end of every fenced
            # code block. Internal blank lines are preserved verbatim.
            blocks.append((language, _pre_text(pre).rstrip("\n")))
            tokens.append(placeholder(len(blocks) - 1))
        # Multiple tokens from one shared container are joined into a
        # single replacement string: every block keeps its own token (so
        # the splice pass restores them all) at roughly the container's
        # original position.
        target.replace_with(soup.new_string("\n\n".join(tokens)))
    return blocks


def splice_code_blocks(
    text: str, blocks: list[tuple[str, str]], placeholder_func: Callable[[int], str]
) -> str:
    """Replace placeholder tokens in *text* with fenced code blocks.

    This is the post-conversion step that splices extracted ``<pre>`` code
    blocks back into the converted Markdown text. Each block arrives as a
    ``(language, code_text)`` pair from the adapter's ``_extract_code_blocks``
    function, and each block's placeholder token is generated by
    *placeholder_func(index)* (e.g. ``"DEEPSEEKCODEBLOCK0PLACEHOLDER"``).

    The fence length for each block adapts to the block's own content: if
    the code text contains a run of backticks (e.g. documentation that
    documents Markdown itself), the fence is one backtick longer than the
    longest inner run. This guarantees the inner backtick sequence can never
    close the fence prematurely. The minimum fence length is 3 backticks,
    the CommonMark minimum for a fenced code block.

    Each fenced block is surrounded by ``\\n\\n`` on both sides. The
    placeholder token is a bare string in the converted text, and if a
    code container was ever nested inline (inside a paragraph), html2text
    leaves the token mid-line. A fence spliced in mid-line would not sit
    at the start of a line, so the blank-line-collapse pass
    (``collapse_blank_lines``) would fail to recognise the block as code
    and could collapse blank lines inside it. The extra newlines prevent
    that: they force the opening fence to line start, and any excess
    newlines are harmless -- ``collapse_blank_lines`` reduces runs of 3+
    in the gaps between blocks anyway.

    Args:
        text: The converted Markdown text with placeholder tokens still
            embedded (output from html2text's ``handle()`` method).
        blocks: ``(language, code_text)`` pairs in document order, as
            returned by the adapter's ``_extract_code_blocks``.
        placeholder_func: A callable ``(index: int) -> str`` that returns
            the placeholder token for the given block index (e.g. the
            adapter's ``_code_placeholder`` function).

    Returns:
        The Markdown text with all placeholder tokens replaced by fenced
        code blocks, ready for Cf-stripping and blank-line collapsing.
        Blocks whose placeholder token is missing from *text* (because
        html2text mangled or dropped it during conversion) cannot be
        spliced; each such block triggers a stderr warning naming the
        token, and splicing continues with the remaining blocks rather
        than aborting the page.
    """
    for index, (language, code_text) in enumerate(blocks):
        placeholder = placeholder_func(index)
        # Verify the placeholder token actually survives in the converted
        # text before splicing. ``str.replace`` with a missing search string
        # is a SILENT no-op: if html2text mangled or dropped the token (e.g.
        # by escaping or reflowing it), the code block would vanish from the
        # mirrored page with no signal anywhere. A missing token is not
        # fatal -- the rest of the page is still worth mirroring -- so the
        # block is skipped with a stderr warning (the project's standard
        # "  warning: ..." style, matching core.manifest.load and
        # core.github.fetch_git_tree) instead of raising.
        if placeholder not in text:
            print(
                f"  warning: code-block placeholder {placeholder!r} missing "
                f"from converted text; skipping that code block",
                file=sys.stderr,
            )
            continue
        # Scan the code text for the longest consecutive backtick run.
        # This is necessary so we can pick a fence length that cannot be
        # confused with any inner backtick sequence -- if the code itself
        # contains `` ``` ``, the fence must be longer than three backticks
        # to prevent premature closure of the code block.
        longest = max(
            (len(m.group(0)) for m in re.finditer(r"`+", code_text)), default=0
        )

        # The fence length is the longest inner backtick run plus one,
        # but never fewer than three backticks (the CommonMark minimum
        # for a fenced code block). Adding one guarantees that the
        # opening fence is distinct from any inner backtick sequence.
        fence = "`" * max(3, longest + 1)

        # Replace the placeholder token with a complete fenced code block.
        # Each block is surrounded by blank lines (``\n\n`` before and
        # after) to prevent mid-line placement issues: if a placeholder
        # ever ends up mid-line (e.g. an inline code container), the
        # extra newlines force the opening fence to start at the
        # beginning of a line, which is required for the fenced-block
        # scanner to recognise it as a code block later.
        #
        # ``count=1`` limits the substitution to the FIRST occurrence of
        # this index's placeholder. Each placeholder token embeds its own
        # block index (e.g. ``DEEPSEEKCODEBLOCK0PLACEHOLDER``), so in
        # practice it appears exactly once per block. Passing an explicit
        # count is a defensive guard: if a placeholder ever recurred
        # (e.g. a future code path that duplicated a placeholder token into
        # the text), an unbounded ``str.replace`` would splice the same
        # fenced block into every occurrence -- silently duplicating code.
        # With ``count=1`` only the intended site is replaced, and the
        # single-occurrence case is byte-identical to the old behaviour.
        text = text.replace(
            placeholder,
            f"\n\n{fence}{language}\n{code_text}\n{fence}\n\n",
            1,
        )
    return text


def fetch_markdown_converted(
    client: httpx.Client, page: Page, convert: Callable[[str], str]
) -> tuple[str, str]:
    """Fetch one HTML page, convert it to Markdown, validate, and hash it.

    This is the shared body of the ``fetch_markdown`` pipeline hook (see
    ``sources/base.py`` for the hook contract) defined by the
    HTML-to-Markdown source adapters. Each adapter passes its own *convert*
    callable (its ``_html_to_markdown``); everything else -- which URL is
    fetched, how conversion failures are classified, how the output is
    validated, and how the content hash is computed -- is identical across
    adapters and lives here.

    The page's ``source_url`` (not ``source_md_url``) is fetched: for these
    sources both fields point at the HTML page, and ``source_md_url`` is
    only a placeholder so the page model can treat Markdown-native and
    HTML-native sources uniformly.

    Error semantics -- two distinct ``FetchError`` paths, both of which the
    pipeline isolates PER PAGE (the failed page is recorded as a failed
    fetch and its previous manifest entry is carried forward, while the
    rest of the source continues):

    * Any unexpected exception out of *convert* (a parser edge case, an
      unforeseen markup shape, a bug in the tree surgery) is caught and
      re-raised as ``FetchError``. A bare exception escaping the hook would
      abort the entire source's run instead of failing just this page.
      Chaining with ``from`` keeps the original exception on ``__cause__``,
      so genuine programming errors stay distinguishable in the traceback
      instead of being silently misclassified as a page failure.
    * Output that fails ``validate_markdown`` (e.g. the HTML was a login
      page or a 404 error page the sitemap still lists) raises
      ``FetchError`` before the text can be written to disk, so a broken
      conversion never silently replaces a valid mirror file with garbage.

    Args:
        client: The HTTP client handed to the hook by the pipeline (the
            adapters only annotate it; the pipeline and test doubles
            duck-type the interface).
        page: The page being fetched; ``source_url`` is downloaded and
            ``slug`` is used in error messages.
        convert: Callable ``(html: str) -> str`` turning the fetched HTML
            into Markdown -- the adapter's ``_html_to_markdown``.

    Returns:
        ``(markdown, content_hash)`` -- the pair the pipeline writes to
        disk and stores in the manifest for change detection.

    Raises:
        fetch.FetchError: On HTTP failure (propagated from
            ``fetch.get_with_retry``), on any conversion exception
            (wrapped, original exception on ``__cause__``), or when the
            converted text fails Markdown validation.
    """
    # ``fetch.get_with_retry`` handles transient network errors with
    # exponential backoff and raises ``FetchError`` on permanent failures
    # (4xx status codes, DNS resolution failures, TLS errors, timeouts).
    # That exception propagates straight up -- it is already the per-page
    # failure type the pipeline isolates.
    html = fetch.get_with_retry(client, page.source_url)
    try:
        md = convert(html)
    except Exception as exc:
        raise fetch.FetchError(
            f"HTML to Markdown conversion failed for {page.slug}: {exc}"
        ) from exc
    # Validate that the conversion produced something that looks like
    # Markdown before returning it to the pipeline. A validation failure
    # takes the same FetchError path as a network failure: the pipeline
    # carries the previous cycle's manifest entry forward instead of
    # writing the suspect output to disk.
    if not fetch.validate_markdown(md):
        raise fetch.FetchError(f"validation failed for {page.slug} (not Markdown?)")
    return md, fetch.content_hash(md)
