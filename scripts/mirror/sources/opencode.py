"""Source: OpenCode.

OpenCode's documentation lives as MDX in the open-source repo
`anomalyco/opencode` under `packages/web/src/content/docs/` (branch `dev`).
We list the tree via the GitHub API and fetch each `.mdx` file from
raw.githubusercontent.com, converting MDX elements to clean standard Markdown.

The adapter defines the optional ``fetch_markdown`` hook so the pipeline
downloads raw MDX and runs it through ``_mdx_to_md`` before the content hash
is computed -- the mirrored files are pure Markdown, never raw MDX.

Upstream also publishes translations of the docs, one top-level directory
per locale (``pt-br/``, ``ja/``, ... -- see ``KNOWN_LOCALE_DIRS``).  Discovery
mirrors the English pages only by default and adds the pages of selected
locales on request: the CLI's ``--locales`` flag stores the selection in the
run-scoped holder ``config.ACTIVE_LOCALES``, and ``discover()`` also accepts
it as an explicit ``locales`` parameter (see that function's docstring for
the full call contract).  Locale pages are ordinary pages for the manifest
and the whats-new log -- no per-locale suppression anywhere -- and
``CONFIG.generate_whats_new`` stays False, so this source never produces a
structural changelog either way.
"""

from __future__ import annotations

import re
import sys
from typing import TYPE_CHECKING

from .. import config
from ..core import fetch
from ..core.github import fetch_git_tree, fetch_latest_release_tag
from ..core.html_markdown import iter_code_block_spans
from ..core.media import AssetSourceConfig
from ..core.page import Page
from .base import SourceConfig, try_make_page, warn_duplicate_slug

if TYPE_CHECKING:
    import httpx

REPO = "anomalyco/opencode"
BRANCH = "dev"
DOCS_PREFIX = "packages/web/src/content/docs"
RAW_BASE = f"https://raw.githubusercontent.com/{REPO}/{BRANCH}"
SOURCE_URL_BASE = "https://opencode.ai/docs"

# Static-asset rules for the pipeline's media stage. A few pages embed
# screenshots via relative refs of the shape ``../../assets/<relpath>`` --
# those resolve upstream to ``packages/web/src/assets/``, two levels above
# the content root, but in the mirror (where slugs are flat) they point
# nowhere. The media stage downloads each referenced asset into
# ``docs/opencode/assets/`` (write-only-what-changed, hashed), rewrites the
# in-page refs to resolve from the mirrored page location, and prunes assets
# no page references anymore.
MEDIA = AssetSourceConfig(
    name="opencode",
    asset_subdir="assets",
    ref_prefixes=("../../assets/",),
    raw_base_url=f"{RAW_BASE}/packages/web/src/assets/",
)

CONFIG = SourceConfig(
    name="opencode",
    title="OpenCode",
    home_url=SOURCE_URL_BASE,
    generate_whats_new=False,
    version="1.18.18",
    origin=f"github.com/{REPO} (`packages/web/src/content/docs/`)",
    how_mirrored="scraping (GitHub tree → raw `.mdx` → `.md` conversion)",
)


def get_version(client: httpx.Client) -> str | None:
    """Query the GitHub API for the latest release tag of OpenCode."""
    return fetch_latest_release_tag(client, repo=REPO)


# ---------------------------------------------------------------------------
# MDX-to-Markdown sanitizer: regex patterns and converter functions
# ---------------------------------------------------------------------------
# All module-level regex constants and converter routines used by
# ``_mdx_to_md`` to strip JSX component wiring, transform callout syntaxes,
# and produce clean GitHub-flavored Markdown.

# Top-level JS import / export statements (e.g. ``import { Tabs } from
# '@/components'`` or ``export const foo = ...``). These are Astro/Starlight
# component wiring that only makes sense in the build context; stripping them
# keeps them out of the mirrored Markdown.  The strip deliberately runs AFTER
# the callout conversions (see ``_mdx_to_md``): an ``import`` line quoted
# inside a callout body is content (e.g. a setup snippet inside a note), not
# wiring, and once the callout converter has wrapped it in ``> `` blockquote
# prefixes this line-anchored pattern no longer matches it.
#
# ReDoS safety: the match is confined to ONE line on purpose. The earlier
# cross-line form (``[\s\S]*?`` with a ``;`` / blank-line terminator) was
# quadratic on adversarial input -- with N lines starting with
# ``import``/``export`` and no terminator anywhere, every failed match
# re-scanned the whole remaining document, and the strip runs on raw
# network MDX (up to ``MAX_RESPONSE_BYTES``, 10 MiB), making that a
# remotely-triggerable hang. ``[^\n]*`` bounds every match attempt to its
# own line, so the substitution is O(N) in document size. A consequence of
# the single-line bound is that a hypothetical MULTILINE import/export
# statement is only stripped up to the end of its first line; upstream
# wiring statements are always single-line, so no real content is lost
# (see the linearity regression test in tests/test_opencode.py).
_IMPORT_EXPORT_RE = re.compile(r"^(?:import|export)\s+[^\n]*(?:;|$)", re.MULTILINE)

# JSX comments: ``{/* ... */}``. Converted to HTML comments (``<!-- ... -->``)
# rather than being stripped entirely, so the annotation text survives in the
# mirrored Markdown as a human-readable note that is invisible when rendered.
#
# This pattern is ONLY ever applied through ``_convert_jsx_comments`` (never
# via a bare ``.sub()``), because the naive substitution is O(N x body
# length) on input with N unclosed ``{/*`` openers: when no ``*/}`` closer
# exists, the lazy ``.*?`` expands to end-of-string, fails, and the regex
# engine retries the whole scan from the NEXT unclosed opener -- every
# unclosed opener costs one full scan of the remaining body. The converter
# runs on raw MDX fetched from the network (up to ``MAX_RESPONSE_BYTES``,
# 10 MiB), making that a remotely-triggerable hang (measured: 1,000/2,000/
# 4,000 unclosed openers took 0.36/1.42/6.05 s, the classic 4x-per-2x
# quadratic signature; the growth extrapolates to minutes well below the
# size cap). ``_convert_jsx_comments`` keeps this pattern for the actual
# matching (so group semantics are untouched) but drives it with a linear
# ``str.find`` scan -- see that function for the monotonicity argument.
_JSX_COMMENT_RE = re.compile(r"\{/\*\s*(.*?)\s*\*/\}", re.DOTALL)


def _jsx_comment_to_html(match: re.Match[str]) -> str:
    """Rewrite one JSX comment match as an HTML comment.

    The captured body is wrapped as ``<!-- body -->``.  A naive wrapping is
    not enough, though: HTML comments may not contain ``--`` anywhere in
    their text (the HTML spec forbids a double hyphen between ``<!--`` and
    ``-->``), so a JSX comment like ``{/* note -- draft */}`` would become
    ``<!-- note -- draft -->`` -- invalid comment syntax that strict HTML
    parsers terminate early or reject, potentially leaking the remainder of
    the "comment" as visible text.

    Every ``--`` inside the body is therefore rewritten to ``==``.  ``==``
    is chosen over the numeric character reference ``&#45;&#45;`` because
    character references are NOT decoded inside HTML comments -- the entity
    would sit there as literal gibberish for anyone reading the Markdown
    source, while ``==`` stays plainly readable and preserves the visual
    rhythm of the original annotation.  The replacement is intentionally
    visible (not a silent deletion) so the note still reads as written.
    """
    return f"<!-- {match.group(1).replace('--', '==')} -->"


def _convert_jsx_comments(text: str) -> str:
    """Rewrite every ``{/* ... */}`` JSX comment as an HTML comment.

    Semantics-identical to ``_JSX_COMMENT_RE.sub(_jsx_comment_to_html, text)``
    but LINEAR on adversarial input (see the hazard comment on
    ``_JSX_COMMENT_RE``). The substitution is decomposed into:

    1. ``str.find("{/*", ...)`` to locate the next opener -- the literal
       opener needs no regex;
    2. ``str.find("*/}", ...)`` to locate the first closer after it -- the
       lazy ``.*?`` in the pattern always terminates at the FIRST ``*/}``
       occurrence (any characters between the body and that closer, whitespace
       included, are absorbable by the ``\\s*`` in front of ``\\*/\\}``), so a
       plain substring search finds the same match end the regex would;
    3. ``_JSX_COMMENT_RE.match(text, start, end + 3)`` on the proven-match
       window, so the capture-group semantics (including the ``\\s*`` trimming
       around the body) are produced by the original pattern itself, not
       reimplemented.

    LINEAR-TIME ARGUMENT: every ``str.find`` resumes where the previous match
    ended, so each character of the document is scanned a bounded number of
    times. When step 2 finds no closer, the loop STOPS rather than retrying
    from the next opener: a closer for any later opener would sit after this
    opener too and would have been found, so no later opener can ever match
    -- the rest of the document is copied verbatim, exactly as the old
    substitution left it. This monotonicity is what removes the old
    O(N x body length) behaviour on N unclosed openers.
    """
    out: list[str] = []
    pos = 0
    while True:
        start = text.find("{/*", pos)
        if start == -1:
            break
        end = text.find("*/}", start + 3)
        if end == -1:
            # No closer anywhere after this opener -- and therefore after
            # ANY later opener either (see the docstring), so nothing in the
            # remainder of the document can be converted.
            break
        match = _JSX_COMMENT_RE.match(text, start, end + 3)
        # The ``str.find`` calls above proved the opener and the first closer
        # both sit inside the bounded window, so the match cannot fail; the
        # assert only documents that invariant (and satisfies type checkers).
        assert match is not None
        out.append(text[pos:start])
        out.append(_jsx_comment_to_html(match))
        pos = end + 3
    out.append(text[pos:])
    return "".join(out)


# Shared JSX attribute-list subpattern, interpolated into every tag-matching
# regex below (``_SELF_CLOSING_RE``, ``_JSX_OPEN_RE``, ``_CALLOUT_BLOCK_RE``).
# A naive ``[^>]*`` stops at the FIRST ``>`` character, so a ``>`` inside a
# quoted attribute value -- e.g. ``<Card title="A > B" />`` -- would
# terminate the tag match early, leaving the remainder of the tag (``B" />``)
# behind as raw JSX fragments leaking into the Markdown output.  The
# alternation instead accepts either a single character that is neither a
# quote, ``>``, nor ``/``, a complete single- OR double-quoted string (which
# may itself contain ``>``), or a ``/`` that does NOT begin the closing
# ``/>`` of a self-closing tag (the ``/(?!\s*>)`` lookahead).  Quoted
# attribute values are therefore consumed whole, and the self-closing slash
# is never swallowed by the attribute list -- that distinction matters
# because the group is atomic: no backtracking is possible once it has
# matched, so if the ``/`` were consumed here, the trailing ``/>`` in
# ``_SELF_CLOSING_RE`` could never match and the tag would survive.
#
# ReDoS safety: the four alternatives are mutually exclusive on their first
# character (a quote can only start a quoted string, ``/`` only matches via
# the lookahead-guarded alternative, and ``[^\"'>/]`` matches everything
# else), so there is no ambiguity for the regex engine to explore; the
# wrapping atomic group ``(?>...)`` additionally freezes the matched
# attribute list once consumed, guaranteeing no nested unbounded
# backtracking even on adversarial input.
#
# MINIMUM PYTHON VERSION: the ``(?>...)`` atomic-group syntax (and the
# related possessive quantifiers) was added to the ``re`` module in
# Python 3.11; on 3.10 and older this pattern fails to compile with
# ``re.error``.  The project requires Python >= 3.14, so the requirement
# is satisfied -- this note exists so a future maintainer does not
# "simplify" the atomic group away (it is load-bearing for the
# backtracking guarantee above) or lower the version floor without
# replacing the pattern.
_JSX_ATTRS = r"(?>(?:[^\"'>/\{]|\"[^\"]*\"|'[^']*'|\{(?>(?:[^{}]|\{(?>(?:[^{}]|\{[^{}]*\})*)\})*)\}|/(?!\s*>))*)"
# Nesting ceiling: the brace alternative above matches up to THREE levels of
# ``{...}`` nesting in an attribute value (enough for inline styles and small
# object literals). A value nested deeper than that still defeats the whole
# open-tag match, so the raw JSX leaks into the mirrored page -- a known
# limitation kept deliberately shallow: each extra level lengthens the
# pattern, and the ReDoS guarantee above depends on the alternatives staying
# mutually exclusive on their first character.

# Self-closing JSX tags: ``<Card title="X" />``, ``<Link href="..." />``, etc.
# Converted to an empty string -- the semantic content is lost, but these are
# typically decorative or navigation elements whose text equivalent is
# captured elsewhere in the page.  Add targeted rules if upstream uses
# content-bearing self-closing tags.  The attribute list is matched by the
# shared ``_JSX_ATTRS`` subpattern (see its comment), so a ``>`` inside a
# quoted attribute value cannot truncate the match.
_SELF_CLOSING_RE = re.compile(r"<[A-Z][\w-]*(?:\s" + _JSX_ATTRS + r")?\s*/>", re.DOTALL)

# Generic JSX element open/close tags. Stripped while preserving inner text
# content (e.g. ``<Tabs>...content...</Tabs>`` becomes ``...content...``).
# Matches tags whose name starts with an uppercase letter (JSX convention)
# so standard HTML elements (``<div>``, ``<a>``, ``<code>``) are left alone.
# The attribute list of the open tag is matched by the shared ``_JSX_ATTRS``
# subpattern (see its comment), so a ``>`` inside a quoted attribute value
# cannot terminate the opening-tag match early.
_JSX_OPEN_RE = re.compile(r"<(?:[A-Z][\w-]*)(?:\s" + _JSX_ATTRS + r")?\s*>", re.DOTALL)
_JSX_CLOSE_RE = re.compile(r"</(?:[A-Z][\w-]*)\s*>", re.DOTALL)

# Starlight ``<TabItem label="...">`` elements inside ``<Tabs>``.
# Converted to bold labels (``**Label**``) before generic JSX tag stripping
# so tab context (package managers, operating systems, languages) is preserved.
_TAB_ITEM_RE = re.compile(
    r"<TabItem\b" + _JSX_ATTRS + r"\s*>", re.DOTALL | re.IGNORECASE
)
_TAB_LABEL_RE = re.compile(r"label\s*=\s*([\"'])(.*?)\1", re.IGNORECASE)

# Known non-English locale directories at the top level of the upstream docs
# tree (``packages/web/src/content/docs/`` in ``anomalyco/opencode@dev``),
# verified against the live repository via the GitHub contents API.  Upstream
# keeps each translation as a top-level directory named by its ISO 639-1
# code (with an optional region suffix, e.g. ``pt-br``, ``zh-cn``), mirroring
# the English page structure one level down.
#
# The set is EXPLICIT rather than a name-shape regex (``^[a-z]{2,3}...``)
# because several English pages have short, locale-shaped names -- the
# upstream tree today contains ``cli.mdx``, ``go.mdx``, ``tui.mdx``,
# ``lsp.mdx``, ``ide.mdx``, ``web.mdx``, and ``zen.mdx``.  If upstream ever
# restructures such a page into a directory (``cli.mdx`` -> ``cli/index.mdx``),
# a shape heuristic would silently drop the entire subtree; an explicit set
# can never mistake English content for a locale.
#
# PUBLIC BY DESIGN: the CLI validates its ``--locales`` flag against this set
# (``all`` expands to it), and discovery only ever mirrors directories it
# names.  A locale outside the set can therefore be neither requested nor
# mirrored, and -- until it is added here -- its pages would be mirrored as
# if they were English content.
#
# MAINTENANCE CONTRACT: when upstream adds a new locale directory, add its
# name to this set.  Conversely, the discovery-time informational line (which
# names every excluded locale directory found in the upstream tree) is the
# operator's cue to audit this set against that tree whenever the exclusion
# list looks unexpected.
KNOWN_LOCALE_DIRS = frozenset(
    {
        "ar",
        "bs",
        "da",
        "de",
        "es",
        "fr",
        "it",
        "ja",
        "ko",
        "nb",
        "pl",
        "pt-br",
        "ru",
        "th",
        "tr",
        "zh-cn",
        "zh-tw",
    }
)


# Starlight ``:::`` callout block.  Matches from the opening fence
# (``:::type[title]``) through the body lines to the closing fence (``:::``)
# on its own line (possibly indented inside a list item).
#
# The opening fence length is captured via ``(:{3,})`` and the closing fence
# is matched via a backreference (``\1``) so that an outer ``::::`` fence is
# only closed by a matching ``::::`` sequence, never by a shorter ``:::``
# fence.  This correctly handles Starlight's nested callout syntax where
# an inner ``:::`` callout is placed inside an outer ``::::`` callout.
#
# Groups:
#   Group 1 — the colon fence sequence (e.g. ``:::`` or ``::::``)
#   Group 2 — callout type (one of the known Starlight callout types)
#   Group 3 — optional bracketed title (``[title]``)
#   Group 4 — body content (all lines between opening and closing fences)
#
# Leading whitespace is tolerated on both fences so that callouts embedded
# deep inside indented list items can be matched reliably without breaking
# the content structure.
#
# The closing delimiter is ``(?:\n[ \t]*\1|\Z)``: normally the body is
# terminated by a newline followed by the closing fence, but ``\Z``
# (absolute end of string) is accepted as a fallback terminator so that a
# callout running to the end of the file is still converted instead of
# leaking its raw ``:::`` fences into the Markdown output.  ``\Z`` is used
# rather than ``$`` on purpose: the pattern is compiled with
# ``re.MULTILINE``, under which ``$`` matches before EVERY newline, so an
# unclosed callout anywhere in the middle of a document would "close" at
# the end of its first line and mangle everything after it.  ``\Z`` only
# matches at the true end of the string, confining the fallback to the
# document tail.  Because ``.*?`` is lazy, a real closing fence is always
# preferred over the ``\Z`` fallback whenever both are reachable.
_STARLIGHT_CALLOUT_RE = re.compile(
    r"^[ \t]*(:{3,})(note|tip|warning|caution|danger|info)\s*(?:\[(.*?)\])?\s*\n"
    r"(.*?)(?:\n[ \t]*\1|\Z)",
    re.DOTALL | re.MULTILINE,
)

# Map Starlight callout types to their GitHub Alert label equivalents.
# GitHub Alert syntax (``> [!TYPE]``) supports exactly five labels:
# ``NOTE``, ``TIP``, ``IMPORTANT``, ``WARNING``, and ``CAUTION``; a keyword
# outside that set renders as a plain blockquote and the alert is silently
# lost.  Starlight's ``danger`` type has no direct equivalent, so it is
# mapped to ``CAUTION`` -- the most severe supported label and therefore
# the closest semantic match -- and ``info`` is mapped to ``NOTE``.  This
# mapping ensures every callout in the mirrored Markdown renders as a real
# GitHub Alert while preserving the original intent.
_ALERT_MAP = {
    "note": "NOTE",
    "tip": "TIP",
    "warning": "WARNING",
    "caution": "CAUTION",
    "danger": "CAUTION",
    "info": "NOTE",
}

# JSX ``<Callout ...>...</Callout>`` block.  Matches the opening tag with
# whatever attribute list it carries (in ANY order), the body content, and
# the closing tag in one pass so the entire block can be rewritten as a
# GitHub Alert with per-line ``> `` prefixes.  The ``type`` attribute is NOT
# pinned into this pattern: requiring it to be the FIRST attribute would
# silently miss ``<Callout title="..." type="warning">``, and the generic
# JSX tag strips below would then remove the tags while the callout body
# leaked through as unformatted text.  ``type`` (and the optional ``title``)
# are extracted from the opening tag separately, via ``_TYPE_RE`` /
# ``_TITLE_RE``.  Compiled once at module level (the codebase-wide
# convention -- see ``core/page.py``) because ``_convert_jsx_callouts`` runs
# once per fetched page and recompiling the pattern on every call would be
# pure waste.
#
# The attribute list of the opening tag is matched by the shared
# ``_JSX_ATTRS`` subpattern (see its comment for the quote-aware matching
# and ReDoS-safety rationale), so a ``>`` inside a quoted attribute value --
# e.g. ``<Callout title="A > B" type="warning">`` -- cannot terminate the
# opening-tag match early, leak raw JSX fragments into the Markdown output,
# or lose the ``type``/``title`` attributes.
#
# Groups:
#   Group 1 — the complete opening tag (``<Callout ...>``), captured so the
#             converter can extract attributes without re-deriving where
#             the tag ends (a plain ``index(">")`` would hit a ``>``
#             inside a quoted attribute value)
#   Group 2 — body content (everything between the opening and closing
#             tags)
#
# This pattern is ONLY ever applied through ``_convert_jsx_callouts``
# (never via a bare ``.sub()``), because the naive substitution is
# O(N x body length) on input with N unclosed ``<Callout ...>`` openers:
# when no ``</Callout>`` closer exists, the lazy ``.*?`` expands to
# end-of-string, fails, and the regex engine retries the whole scan from
# the NEXT unclosed opener -- every unclosed opener costs one full scan of
# the remaining body. The converter runs on raw MDX fetched from the
# network (up to ``MAX_RESPONSE_BYTES``, 10 MiB), making that a
# remotely-triggerable hang (measured: 500/1,000/2,000 unclosed openers
# took 0.12/0.46/1.84 s, the classic 4x-per-2x quadratic signature).
# ``_convert_jsx_callouts`` keeps this pattern for the actual matching (so
# group semantics are untouched) but drives it with linear opener/closer
# searches -- see that function for the monotonicity argument.
_CALLOUT_BLOCK_RE = re.compile(
    r"(<Callout\b" + _JSX_ATTRS + r">)"
    r"\s*(.*?)"
    r"</Callout>",
    re.DOTALL | re.IGNORECASE,
)

# The opening and closing halves of ``_CALLOUT_BLOCK_RE`` as standalone
# literal-ish searches, used by ``_convert_jsx_callouts`` to locate the next
# candidate block without re-running the full block pattern at every string
# position.  The opener pattern is byte-identical to group 1 of the block
# pattern (same quote-aware ``_JSX_ATTRS`` attribute list), so it finds
# exactly the openers the block pattern would; the closer is a fixed
# literal (matched case-insensitively, mirroring the block pattern's
# ``re.IGNORECASE``), which carries no backtracking hazard on its own.
_CALLOUT_OPEN_RE = re.compile(r"<Callout\b" + _JSX_ATTRS + r">", re.IGNORECASE)
_CALLOUT_CLOSE_RE = re.compile(r"</Callout>", re.IGNORECASE)

# ``type`` attribute inside a ``<Callout>`` opening tag.  Kept separate from
# the block-level regex above (mirroring how ``_TITLE_RE`` handles
# ``title``) so the attribute ORDER does not matter; a single combined
# pattern that handles every ordering would be overly complex and brittle.
_TYPE_RE = re.compile(r"type\s*=\s*[\"'](\w+)[\"']", re.IGNORECASE)

# Optional ``title`` attribute inside a ``<Callout>`` opening tag.  Kept
# separate from the block-level regex above because the title can appear
# before or after ``type`` in the attribute list, and a single combined
# pattern that handles both orderings would be overly complex and brittle.
#
# The quote pair is MATCHED via a backreference (``\1``): group 1 captures
# whichever quote character opened the value and the closer must be that
# same character.  The naive form ``[\"'](.*?)[\"']`` accepted EITHER quote
# as the closer regardless of the opener, so a value containing the other
# quote kind -- e.g. ``title="A 'B' C"`` -- was silently truncated to
# ``A '`` (the first single quote ended the capture even though the value
# was double-quoted).  With the backreference, group 2 holds the full
# value up to the matching quote; the other quote kind may appear inside
# the value freely.
_TITLE_RE = re.compile(r"title\s*=\s*([\"'])(.*?)\1", re.IGNORECASE)

# ``iter_code_block_spans`` (imported from ``core/html_markdown.py``)
# locates every complete fenced code block (CommonMark): an opening fence
# of 3+ backticks OR 3+ tildes, an optional info string on the opening
# fence line, a body of any number of lines, and a closing fence that is
# the EXACT same character sequence as the opening fence.  Used by
# ``_protect_fenced_code`` to lift code samples out of the raw MDX before
# the JSX / import transformations run, so that a line which looks like a
# JS ``import``/``export`` statement or a JSX tag inside a code sample is
# never stripped or rewritten -- it is code, not MDX wiring.  The scanner
# is shared with the HTML-to-Markdown adapters (which use it for their
# blank-line-collapse pass); see its definition in
# ``core/html_markdown.py`` for the full matching rules and for why it is
# a linear line scan rather than a regex (the regex form was a
# quadratic-time hazard on unclosed fences, and this protector runs on
# raw network MDX).


def _convert_starlight_callouts(text: str) -> str:
    """Convert Starlight ``:::type`` callout blocks to GitHub Alerts.

    Each ``:::type[optional title] ... :::`` block becomes a ``> [!TYPE]``
    block quote with every body line prefixed by ``> ``.  When a bracketed
    title is present, it is rendered as bold text on the alert's first line
    (``> [!TYPE]\n> **Title**\n> ...``).  Common leading whitespace is
    stripped from body lines so indented callouts (e.g. inside list items)
    produce clean output.
    """

    def _replace(match: re.Match[str]) -> str:
        starlight_type = match.group(2).lower()
        alert_label = _ALERT_MAP.get(starlight_type, "NOTE")
        title = match.group(3)
        body = match.group(4)

        lines = [f"> [!{alert_label}]"]
        if title:
            lines.append(f"> **{title}**")
            lines.append(">")

        body_lines = body.split("\n")
        # Normalise tabs to spaces on every body line before measuring the
        # common indent.  A raw character count (``len(l) - len(l.lstrip())``)
        # miscounts when a body mixes tabs and spaces, because a single tab
        # represents several columns of indentation; ``expandtabs()`` gives
        # every line a consistent column basis so the minimum is meaningful and
        # the slice below takes the right number of columns off every line.
        # For space-indented bodies (the common case) ``expandtabs()`` is a
        # no-op, so this is behaviour-identical for them.
        expanded_lines = [line.expandtabs() for line in body_lines]
        # Dedent: find the common leading whitespace across non-blank lines
        # and strip it so indented callouts (inside list items, etc.) don't
        # carry their indentation into the output.
        # This indentation deduction works by taking the minimum number of
        # leading columns across all non-blank lines in the (tab-expanded)
        # callout body.  By determining the baseline indentation level, we
        # can cleanly strip it away, ensuring the resulting GitHub Alert does
        # not suffer from cascading or erroneous formatting due to inherited
        # list indentation.
        indent = min(
            (len(line) - len(line.lstrip()) for line in expanded_lines if line.strip()),
            default=0,
        )
        for body_line in expanded_lines:
            stripped = body_line[indent:] if body_line.strip() else ""
            if stripped:
                lines.append(f"> {stripped}")
            else:
                lines.append(">")

        return "\n".join(lines)

    return _STARLIGHT_CALLOUT_RE.sub(_replace, text)


def _convert_jsx_callouts(text: str) -> str:
    """Convert JSX ``<Callout type="X" title="...">`` elements to GitHub Alerts.

    Finds every ``<Callout ...>...</Callout>`` block and converts it into a
    ``> [!TYPE]`` GitHub Alert with a ``> `` blockquote prefix on every body
    line.  When an optional ``title`` attribute is present, it is rendered as
    bold text on the alert's first content line (``> **Title**``).

    A naive rewrite that only patches the opening tag and prefixes the
    first body line would mangle multi-line callouts; this function instead
    wraps the entire content block with per-line ``> `` prefixes, correctly
    handling multi-line paragraphs, nested lists, and other body text that
    spans several lines.  Body lines are dedented by their COMMON leading
    whitespace (the same algorithm ``_convert_starlight_callouts`` uses),
    so an indented ``<Callout>`` block produces clean output while internal
    indentation -- nested lists, indented code -- is preserved.
    """

    def _replace(match: re.Match[str]) -> str:
        # The opening tag arrives as group 1 of the block regex, already
        # delimited by the quote-aware attribute pattern, so the attribute
        # lookups below see only the tag text, never the body.  Slicing the
        # tag out of ``group(0)`` with ``index(">")`` would be wrong here:
        # the first ``>`` can sit inside a quoted attribute value (e.g.
        # ``title="A > B"``), which would truncate the tag mid-attribute
        # and silently drop every attribute after that point.
        opening_tag = match.group(1)

        # Extract the GitHub Alert label from the ``type`` attribute via the
        # dedicated attribute regex -- attribute ORDER is irrelevant, so
        # ``<Callout title="..." type="warning">`` converts exactly like
        # ``<Callout type="warning" title="...">``.  The value is routed
        # through the same ``_ALERT_MAP`` used by the Starlight callout
        # converter, defaulting to ``NOTE`` when the attribute is missing or
        # unknown.  This keeps the two converters in agreement:
        # ``type="info"`` becomes ``> [!NOTE]`` (the closest GitHub Alert
        # equivalent) rather than the invalid ``> [!INFO]`` -- GitHub Alerts
        # only render the labels NOTE/TIP/IMPORTANT/WARNING/CAUTION.
        # ``.lower()`` makes the lookup case-insensitive, mirroring the
        # Starlight converter's handling, and matches the lowercase keys of
        # ``_ALERT_MAP``.
        type_match = _TYPE_RE.search(opening_tag)
        callout_type = type_match.group(1).lower() if type_match else ""
        label = _ALERT_MAP.get(callout_type, "NOTE")
        # The body content (everything between the opening and closing
        # tags), captured as group 2 of the block regex.
        body = match.group(2)

        # Search the opening tag for an optional ``title`` attribute (also
        # order-independent, via ``_TITLE_RE``).  Group 2 holds the value:
        # group 1 is the matched quote character itself (see ``_TITLE_RE``).
        title_match = _TITLE_RE.search(opening_tag)
        title = title_match.group(2) if title_match else None

        # Build the GitHub Alert block with a ``> [!LABEL]`` header line.
        lines = [f"> [!{label}]"]
        if title:
            lines.append(f"> **{title}**")
            lines.append(">")

        # Split the body into individual lines and prefix each with ``> ``,
        # dedenting by the COMMON leading whitespace first.  A flat
        # ``str.strip()`` per line would be wrong here: it destroys INTERNAL
        # indentation, so a nested list or an indented code sample inside
        # the callout would collapse to column zero and lose its structure.
        # The approach mirrors ``_convert_starlight_callouts`` above, so the
        # two callout syntaxes produce identically-shaped output:
        #
        # 1. ``expandtabs()`` normalises tabs to spaces on every line, so a
        #    body that mixes tabs and spaces is measured on a consistent
        #    column basis (a single tab counts as several columns, not one
        #    character).  For space-indented bodies it is a no-op.
        # 2. The minimum indent across NON-BLANK lines is the baseline:
        #    blank lines are excluded because they carry no meaningful
        #    indentation and would drag the minimum to zero.
        # 3. Exactly that many columns are sliced off each line, so lines
        #    indented DEEPER than the baseline keep their extra indentation
        #    and nested structure survives the conversion.
        expanded_lines = [line.expandtabs() for line in body.split("\n")]
        indent = min(
            (len(line) - len(line.lstrip()) for line in expanded_lines if line.strip()),
            default=0,
        )
        # Blank body lines become a bare ``>`` (preserving paragraph breaks
        # within the blockquote without emitting trailing whitespace).
        for body_line in expanded_lines:
            stripped = body_line[indent:] if body_line.strip() else ""
            if stripped:
                lines.append(f"> {stripped}")
            else:
                lines.append(">")

        return "\n" + "\n".join(lines) + "\n"

    # The substitution is decomposed into linear opener/closer searches
    # (see the hazard comment on ``_CALLOUT_BLOCK_RE``):
    #
    # 1. ``_CALLOUT_OPEN_RE.search`` locates the next opening tag -- the
    #    same prefix the block pattern would try at each position, but
    #    without committing to a body scan;
    # 2. ``_CALLOUT_CLOSE_RE.search`` locates the FIRST ``</Callout>``
    #    after it -- the lazy ``.*?`` in the block pattern always
    #    terminates at the first closer occurrence, so this finds the same
    #    match end the naive substitution would;
    # 3. ``_CALLOUT_BLOCK_RE.match`` on the proven-match window reproduces
    #    the exact capture groups of the old substitution (leading
    #    whitespace trimmed from the body by the pattern's own ``\s*``,
    #    trailing whitespace kept inside group 2).
    #
    # LINEAR-TIME ARGUMENT: every search resumes where the previous block
    # ended, so each character is scanned a bounded number of times. When
    # step 2 finds no closer, the loop STOPS rather than retrying from the
    # next opener: a closer for any later opener would sit after this
    # opener too and would have been found, so no later opener can ever
    # match -- the rest of the document is copied verbatim, exactly as the
    # old substitution left it. This monotonicity is what removes the old
    # O(N x body length) behaviour on N unclosed openers.
    out: list[str] = []
    pos = 0
    while True:
        opener = _CALLOUT_OPEN_RE.search(text, pos)
        if opener is None:
            break
        closer = _CALLOUT_CLOSE_RE.search(text, opener.end())
        if closer is None:
            # No closer anywhere after this opener -- and therefore after
            # ANY later opener either (see above), so nothing in the
            # remainder of the document can be converted.
            break
        block = _CALLOUT_BLOCK_RE.match(text, opener.start(), closer.end())
        # The opener/closer searches above proved both delimiters sit
        # inside the bounded window, so the match cannot fail; the assert
        # only documents that invariant (and satisfies type checkers).
        assert block is not None
        out.append(text[pos : opener.start()])
        out.append(_replace(block))
        pos = closer.end()
    out.append(text[pos:])
    return "".join(out)


def _convert_tab_items(text: str) -> str:
    """Convert <TabItem label="..."> opening tags into bold label headers.

    Preserves the tab title (e.g. 'npm', 'pnpm', 'macOS') so that subsequent
    code blocks or explanations maintain their contextual tab heading.
    """

    def _replace(match: re.Match[str]) -> str:
        tag = match.group(0)
        label_match = _TAB_LABEL_RE.search(tag)
        if label_match:
            label = label_match.group(2).strip()
            if label:
                return f"\n\n**{label}**\n\n"
        return "\n\n"

    return _TAB_ITEM_RE.sub(_replace, text)


def _protect_fenced_code(content: str) -> tuple[str, list[str]]:
    """Replace every fenced code block in *content* with an opaque placeholder.

    Returns the placeholder-embedded text plus the list of original fenced
    blocks (opening fence, body, closing fence) in document order.  The
    caller runs the MDX-to-Markdown transformations on the placeholder
    text and then calls ``_restore_fenced_code`` to splice the originals
    back in verbatim.

    This is the same extract->transform->splice principle used by
    ``core/html_markdown.py`` (which lifts ``<pre>`` blocks around the
    html2text pass): fenced code samples are opaque to the JSX and
    import/export transformations because a JS/TS snippet that contains
    an ``import ...`` or ``export ...`` line, or a JSX tag such as
    ``<MyComponent/>``, is real code -- not MDX wiring -- and must
    survive the conversion byte-for-byte.

    This design trade-off means that single-backtick inline code spans
    containing JSX tokens could be altered, but this is an acceptable
    limitation for our current documentation structure.

    The placeholder token is a bare uppercase sentinel that is never
    produced upstream and cannot be confused with prose or code, so it
    passes through every downstream regex untouched and does not collide
    with the document's own text.
    """

    blocks: list[str] = []
    segments: list[str] = []
    pos = 0
    for start, end in iter_code_block_spans(content):
        # Copy the text between the previous block and this one verbatim,
        # then stash the full spanned fenced block (fences included) and
        # emit a unique placeholder token keyed by the block's position in
        # document order, so each block restores to its original location.
        segments.append(content[pos:start])
        index = len(blocks)
        blocks.append(content[start:end])
        segments.append(f"OPENCODEFENCEBLOCK{index}PLACEHOLDER")
        pos = end
    segments.append(content[pos:])
    return "".join(segments), blocks


def _restore_fenced_code(text: str, blocks: list[str]) -> str:
    """Splice the original fenced code blocks back into *text*.

    The inverse of ``_protect_fenced_code``: each placeholder token is
    replaced with the exact fenced block that was stashed in its place, so
    the code samples reappear verbatim -- no transformation was applied to
    them while they were lifted out.  Blocks are spliced in ascending
    index order, matching the order in which they were stashed.
    """
    for index, block in enumerate(blocks):
        text = text.replace(f"OPENCODEFENCEBLOCK{index}PLACEHOLDER", block)
    return text


def _mdx_to_md(content: str) -> str:
    """Convert raw MDX text into clean standard Markdown.

    The conversion is deliberately conservative: it strips JSX component
    wiring (imports, self-closing tags, generic JSX wrappers), converts
    Starlight ``:::`` callout blocks and ``<Callout>`` JSX elements to
    GitHub Alerts, and preserves everything else -- frontmatter, Markdown
    body, HTML elements, and code blocks all pass through unchanged.

    Fenced code blocks (triple-backtick and triple-tilde) are lifted out
    into placeholders before the JSX / import transformations run and
    spliced back verbatim only after EVERY pass -- including the trailing
    whitespace cleanup (steps 7-8) -- has run on the placeholder text, so a
    code sample that contains an ``import``/``export`` line or a JSX tag is
    never stripped or rewritten, and a blank run or indentation-only line
    inside a sample is never collapsed or blanked: it is code, not MDX
    wiring, and no regex ever sees it.
    """
    # 0. Lift fenced code blocks (both the triple-backtick and the
    #    triple-tilde styles) out into opaque placeholder tokens.  This
    #    MUST happen before any of the transformations below: a fenced
    #    JS/TS sample can legitimately contain an ``import ...`` or
    #    ``export ...`` line, a JSX comment, or a JSX tag, and the
    #    import/export strip plus the JSX regexes below would otherwise
    #    silently strip or rewrite those lines, corrupting the code
    #    sample.  The placeholders are spliced back (verbatim) only after
    #    ALL regex-driven passes -- import/JSX strips, callout conversion,
    #    AND the whitespace cleanup in steps 7-8 -- are done, because none
    #    of those passes is fence-aware.  The callout converters still run
    #    in between, which is correct because callouts are never fenced.
    text, fenced_blocks = _protect_fenced_code(content)

    # 1. Convert JSX comments to HTML comments.  The replacement goes
    #    through ``_jsx_comment_to_html`` (not a plain ``<!-- \1 -->``
    #    template) so that a ``--`` sequence inside the comment body is
    #    sanitised to ``==`` -- a raw double hyphen would make the emitted
    #    HTML comment syntactically invalid.  The substitution is driven by
    #    ``_convert_jsx_comments`` rather than a bare ``re.sub`` so that N
    #    unclosed ``{/*`` openers cannot trigger the pattern's quadratic
    #    lazy-scan failure mode (see the comment on ``_JSX_COMMENT_RE``).
    text = _convert_jsx_comments(text)

    # 2. Convert Starlight ``:::`` callout blocks to GitHub Alerts.  These
    #    are the primary callout syntax used by the upstream Starlight docs.
    #    Pattern: ``:::type[title]\n...content...\n:::``
    text = _convert_starlight_callouts(text)

    # 3. Convert JSX ``<Callout type="X">`` elements to GitHub Alerts.
    #    Handles the full ``<Callout>...</Callout>`` block, wrapping every
    #    body line with the ``> `` blockquote prefix required by GitHub
    #    Alert syntax.  Also supports an optional ``title`` attribute.
    #    This step catches any JSX callouts that were not already converted
    #    by the Starlight ``:::`` callout converter in step 2.
    text = _convert_jsx_callouts(text)

    # 4. Strip top-level import / export statements.  This MUST run after
    #    the callout conversions (steps 2-3): an ``import ...`` line that
    #    appears inside a callout body is content (e.g. a setup snippet
    #    quoted in a note), not component wiring, and once the callout
    #    converter has wrapped the body lines in ``> `` blockquote prefixes
    #    the line-anchored ``_IMPORT_EXPORT_RE`` no longer matches it.
    #    Stripping first would silently delete such lines before the
    #    callout converter ever sees the block.
    text = _IMPORT_EXPORT_RE.sub("", text)

    # 5. Strip self-closing JSX tags (e.g. ``<Card title="X" />``,
    #    ``<Link href="..." />``).  These are typically Astro/Starlight
    #    decorative or navigation components whose visual content is not
    #    meaningful as plain text in the mirror.  Removing them prevents
    #    garbled markup from leaking into the final Markdown output.
    text = _SELF_CLOSING_RE.sub("", text)

    # 5.5 Convert <TabItem label="..."> opening tags into bold markdown labels
    #     so package manager or platform tab names survive.
    text = _convert_tab_items(text)

    # 6. Strip generic JSX element open/close tags while preserving inner
    #    text content.  For example, ``<Tabs>...content...</Tabs>`` becomes
    #    ``...content...``.  Only tags starting with an uppercase letter are
    #    matched (per JSX/React convention), so standard HTML elements like
    #    ``<div>``, ``<a>``, and ``<code>`` pass through unchanged.
    text = _JSX_OPEN_RE.sub("", text)
    text = _JSX_CLOSE_RE.sub("", text)

    # 7. Strip whitespace-only lines (common artefact after removing
    #    indented JSX wrappers like ``<Tabs>`` / ``<TabItem>``).
    text = re.sub(r"^[ \t]+$", "", text, flags=re.MULTILINE)

    # 8. Collapse runs of 3+ consecutive blank lines into at most 2.  After
    #    stripping JSX tags and empty whitespace lines, the document can
    #    accumulate excessive vertical gaps.  Normalizing to a maximum of
    #    one empty line between block elements (two consecutive newlines)
    #    keeps the output readable without losing meaningful paragraph breaks.
    text = re.sub(r"\n{3,}", "\n\n", text)

    # Splice the original fenced code blocks back into the text, verbatim.
    # This MUST be the last content transformation: steps 7 and 8 run over
    # the full text and are not fence-aware, so if they ran AFTER the
    # restore they would silently alter code samples -- step 7 would blank
    # an indentation-only line inside a block, and step 8 would collapse
    # 3+ consecutive blank lines that are semantically significant inside a
    # sample.  Running them while the code is still lifted out into opaque
    # placeholders confines their effect to the prose portions, which is
    # exactly the cleanup they exist for; the lifted code samples reappear
    # exactly as they were in the input.
    text = _restore_fenced_code(text, fenced_blocks)

    return text.strip() + "\n"


def _locale_of(rel: str) -> str | None:
    """Return the known locale code *rel* lives under, else ``None``.

    Locale directories sit at the top level within ``DOCS_PREFIX`` and are
    matched EXPLICITLY against ``KNOWN_LOCALE_DIRS`` -- not by a name-shape
    regex -- because several English pages carry short, locale-shaped names
    (``cli``, ``go``, ``tui``, ``lsp``, ``ide``, ``web``, ``zen``).  A shape
    heuristic would silently drop one of those subtrees if upstream ever
    turned such a page into a directory; the explicit set cannot.  A path
    lives under a locale when it contains a ``/`` AND its first segment is
    in the known set -- single-segment paths (always English) return
    ``None`` regardless of whether their name happens to be a known locale
    name.
    """
    if "/" not in rel:
        return None
    first = rel.split("/", 1)[0]
    return first if first in KNOWN_LOCALE_DIRS else None


# ---------------------------------------------------------------------------
# Discovery: enumerate documentation pages from the upstream repo
# ---------------------------------------------------------------------------
# Lists the full git tree of ``anomalyco/opencode@dev`` via the GitHub API,
# filters to Markdown/MDX files under the docs prefix, mirrors non-English
# locale directories only when their locale is selected, and returns a
# sorted list of ``Page`` objects ready for the pipeline's fetch stage.


def discover(
    client: httpx.Client,
    *,
    locales: tuple[str, ...] | None = None,
) -> list[Page]:
    """Discover the OpenCode documentation pages to mirror.

    Lists the full tree of ``anomalyco/opencode@dev`` in one API call (via
    ``core.github.fetch_git_tree``, which also enforces the rate-limit and
    truncation safety guards). Keeps every ``.mdx`` (and ``.md``) file under
    ``packages/web/src/content/docs/`` while filtering out
    non-documentation assets. Non-English locale directories (the explicit
    ``KNOWN_LOCALE_DIRS`` set -- see its comment for why a name-shape regex
    is unsafe) are mirrored only when their locale is selected, and partial
    translations are handled gracefully: a locale directory may hold fewer
    pages than the English root (upstream omits pages it has not translated
    yet), may nest deeper, or may be missing entirely -- discovery mirrors
    whatever exists and never treats a sparse translation as a failure.

    The English root ``index.mdx`` (the landing / home page) is mapped to
    slug ``"intro"`` to match the site's introduction layout, and a NESTED
    ``index`` / ``README`` (e.g. ``cli/index.mdx``) collapses to its
    directory route (``cli``) -- the site serves that page at ``/docs/cli``,
    so keeping the trailing segment would produce a ``source_url`` that
    404s. All other slugs are the path relative to ``DOCS_PREFIX`` without
    the file extension. ``source_id`` is the full repo path, stable across
    content edits, so it doubles as the pipeline's rename-detection key.

    Locale pages (when their locale is selected) are namespaced under their
    locale code using the SAME normalisation as the English pages, applied
    to the path INSIDE the locale directory: ``pt-br/cli.mdx`` -> slug
    ``"pt-br/cli"``, a nested ``pt-br/guides/index.mdx`` ->
    ``"pt-br/guides"``, and the locale's own landing page
    (``pt-br/index.mdx``, the translation of the English ``intro`` page) ->
    ``"pt-br/intro"``. The group of every locale page is its locale code
    (the raw slug's first segment), so each translation forms its own
    section in the generated per-source index. Slug collisions anywhere in
    the combined English+locale namespace (e.g. ``foo.md`` + ``foo.mdx``,
    or ``cli/index.mdx`` + ``cli/README.md`` after normalisation) are
    deduplicated with the shared stderr warning, keeping the first entry.

    LOCALE-SELECTION CALL CONTRACT -- read carefully by any future pipeline
    wiring that wants to thread a locale selection through:
      * ``discover(client)`` -- the exact call the pipeline makes today
        (``pipeline.run_source`` calls ``source.discover(client)`` with no
        further arguments) -- mirrors English pages only, UNLESS the
        run-scoped holder ``config.ACTIVE_LOCALES`` carries a selection.
        The CLI writes that holder from its ``--locales`` flag immediately
        before calling ``pipeline.run``; it is the only channel that can
        reach this adapter before ``pipeline.run`` itself forwards the
        flag.
      * ``discover(client, locales=("pt-br", ...))`` -- the explicit,
        keyword-only parameter is the integration seam for that future
        wiring: it ALWAYS overrides the ``config.ACTIVE_LOCALES`` holder,
        and a ``pipeline.run`` / ``run_source`` that one day accepts a
        ``locales`` value should pass it through here directly, retiring
        the holder. The value is expected normalized (sorted, unique
        codes), but discovery does not rely on the order.
      * ``locales=()`` mirrors English pages only, exactly like
        ``locales=None``; only codes in ``KNOWN_LOCALE_DIRS`` can select
        anything, and any other code is reported as requested-but-absent
        (the CLI rejects such codes up front during argument parsing).

    Change tracking: locale pages are ORDINARY manifest pages -- no
    per-locale suppression anywhere. ``CONFIG.generate_whats_new`` stays
    False for this source, so no structural changelog exists today; should
    it ever be enabled, the first run that adds locale pages truthfully
    records one large "added" entry (the pipeline's baseline semantics for
    a first diff) and later translation drift is logged page by page like
    any other structural change.

    Console contract: informational lines go to stdout with the reporting
    module's 3-space progress indent; genuine problems go to stderr with
    the shared ``  warning: `` prefix. An English-only run prints at most
    ONE informational line naming the excluded locale directories found in
    the tree (never one warning per directory), a run with locales prints
    one informational line naming the mirrored directories plus a stderr
    warning per requested locale the upstream tree does not contain.

    Raises ``RuntimeError`` when discovery finds zero pages, preventing a
    silent deletion of every mirrored file.
    """
    # Effective locale selection: the explicit ``locales`` argument always
    # wins; ``None`` falls back to the run-scoped holder populated by the
    # CLI's ``--locales`` flag (see ``config.ACTIVE_LOCALES`` for the write
    # side of that contract). ``None`` and an empty tuple both mean the
    # historical English-only mirror.
    if locales is None:
        locales = config.ACTIVE_LOCALES
    requested: frozenset[str] | None = frozenset(locales) if locales else None

    tree = fetch_git_tree(client, repo=REPO, branch=BRANCH)

    pages: list[Page] = []
    # Slugs already claimed by an earlier tree entry (the collision guard
    # below), plus the locale handling bookkeeping for the report after the
    # loop: the top-level locale directories observed in this tree
    # (``present_locales``) and the subset of them that yielded at least
    # one page (``mirrored_locales``).
    seen: set[str] = set()
    present_locales: set[str] = set()
    mirrored_locales: set[str] = set()
    for entry in tree:
        if entry.get("type") != "blob":
            continue  # skip directories ("tree" entries) and submodules
        path = entry.get("path", "")

        # Docs-prefix filter: only files under DOCS_PREFIX (the Starlight
        # content directory of the upstream web package) are documentation.
        # Everything else in the repo -- source code, the repo's own README
        # and CHANGELOG, other packages' files -- is not docs content, and
        # without this guard it would be mirrored into docs/opencode/
        # alongside the real pages.  The trailing "/" in the prefix makes
        # the match segment-level, so a sibling path that merely shares the
        # string prefix could never leak in.
        if not path.startswith(DOCS_PREFIX + "/"):
            continue

        # Extension filter: keep only Markdown sources (``.mdx`` and
        # ``.md``).  The docs tree also lists non-prose blobs -- images,
        # downloadable examples, config snippets -- that are assets OF the
        # documentation, not pages; without this guard they would either be
        # mirrored as bogus pages or fail slug validation downstream.
        if not (path.endswith(".mdx") or path.endswith(".md")):
            continue

        rel = path[len(DOCS_PREFIX) + 1 :]

        # Locale filter: a page inside a top-level locale directory
        # (detected set-based via ``_locale_of``, never shape-based -- see
        # that helper) is mirrored only when its locale is selected; every
        # other locale page is skipped, with its directory recorded so the
        # run's report can name the excluded or mirrored set exactly once.
        locale = _locale_of(rel)
        if locale is not None:
            present_locales.add(locale)
            if requested is None or locale not in requested:
                continue

        # Derive slug: strip the file extension (``.mdx`` or ``.md``).
        raw_slug = re.sub(r"\.(?:mdx|md)$", "", rel)
        # A file named exactly ``.mdx`` / ``.md`` (no basename) would yield
        # an empty slug, which ``Page`` rejects with a ValueError (caught by
        # try_make_page below, where it would surface as a spurious
        # warning).  Such a file carries no usable page identity, so skip it
        # quietly instead -- the same degenerate-filename guard the sibling
        # adapters (codex_cli, kimi_code) apply.
        if not raw_slug:
            continue

        # Normalise the page's path inside its locale (or the English root)
        # to a slug.  Index files become their directory route; the
        # ``intro`` landing is the special case of that rule at the top
        # level.  A locale page gets its locale code prepended to the
        # normalised inner path, so ``<locale>/cli/index.mdx`` becomes
        # ``<locale>/cli`` and the locale's own landing page becomes
        # ``<locale>/intro`` (it is the translation of the English ``intro``
        # page, and the site serves it at the locale root, mirroring how the
        # English landing is served at ``/docs/`` under the name "intro").
        if locale is not None:
            # The relative path inside the locale directory: strip the
            # ``<locale>/`` prefix from the raw slug.
            inner = raw_slug[len(locale) + 1 :]
            # A hidden file such as ``.mdx`` directly inside the locale
            # directory would leave nothing usable after the prefix -- same
            # degenerate case the empty-raw_slug guard above handles for
            # English paths, so skip it the same quiet way.
            if not inner:
                continue
            if inner.lower() in ("index", "readme"):
                slug = f"{locale}/intro"
            elif inner.lower().endswith(("/index", "/readme")):
                slug = f"{locale}/{inner.rsplit('/', 1)[0]}"
            else:
                slug = f"{locale}/{inner}"
        elif raw_slug.lower() in ("index", "readme"):
            # The root ``index`` / ``README`` becomes ``"intro"`` (the
            # site's landing page, titled "Intro" upstream).
            slug = "intro"
        elif raw_slug.lower().endswith(("/index", "/readme")):
            # A nested ``cli/index.mdx`` (or ``cli/README.md``) becomes
            # ``cli``: the site serves that page at ``/docs/cli``, so
            # keeping the trailing ``/index`` segment would produce a
            # ``source_url`` that 404s and an output path that duplicates
            # the directory route.
            slug = raw_slug.rsplit("/", 1)[0]
        else:
            slug = raw_slug

        # Slug collision guard: two different source files can map to the
        # same slug -- ``foo.md`` and ``foo.mdx``, or ``cli/index.mdx`` and
        # ``cli/README.md`` after the normalisation above.  Because the slug
        # IS the output path, a duplicate would make two ``Page`` objects
        # fight over one mirrored file.  Keep the first entry and skip the
        # later one with the shared loud stderr warning
        # (``warn_duplicate_slug`` in ``sources/base.py``), matching the
        # dedupe guards in the sibling adapters (codex_cli, kimi_code).
        if slug in seen:
            warn_duplicate_slug(slug, path)
            continue
        seen.add(slug)

        # The group (used to section the generated per-source index) is
        # derived from the RAW slug, not the normalised one: a section
        # landing page such as ``cli/index.mdx`` (normalised to slug
        # ``cli`` above) must stay grouped with the rest of its section
        # (``cli``) instead of being hoisted into the ``root`` group by the
        # index normalisation.  For a locale page the raw slug starts with
        # the locale code, so the group IS that code and each translation
        # gets its own section in the index.
        group = raw_slug.split("/", 1)[0] if "/" in raw_slug else "root"

        # Per-entry guard: a path whose name falls outside the slug alphabet
        # ``Page`` enforces raises ValueError from ``Page.__post_init__``;
        # without this guard ONE such entry would abort discovery for the
        # whole source. ``try_make_page`` (see ``sources/base.py``) owns the
        # guard/warning: the path is named in a stderr warning and discovery
        # continues with the remaining entries.
        page = try_make_page(
            path,
            slug=slug,
            source_url=f"{SOURCE_URL_BASE}/{slug}",
            source_md_url=f"{RAW_BASE}/{path}",
            source_id=path,
            group=group,
        )
        if page is not None:
            pages.append(page)
            if locale is not None:
                mirrored_locales.add(locale)

    pages.sort(key=lambda p: p.slug)

    if not pages:
        raise RuntimeError(
            f"No documentation files found under {DOCS_PREFIX!r} in "
            f"{REPO}@{BRANCH}. A zero-page discovery would delete all "
            "mirrored files. If the upstream moved its docs tree, update "
            "DOCS_PREFIX in this source module."
        )

    # --- Locale-scope report (see the console contract in the docstring) -----
    # Report this run's locale handling exactly once, on the right channel:
    # an informational stdout line (3-space indent, the reporting module's
    # progress style) for what was excluded or mirrored -- never one line
    # per locale directory or per page -- and a stderr warning ONLY for a
    # REQUESTED locale that is missing from the upstream tree (a drift the
    # operator should investigate), since an absent request otherwise has
    # no visible effect.
    if requested is None:
        # English-only run (no ``--locales`` given): one informational line
        # naming the excluded locale directories that actually exist in the
        # upstream tree.  If the exclusion list ever looks unexpected, the
        # operator knows to audit ``KNOWN_LOCALE_DIRS`` against that tree.
        if present_locales:
            print(
                "   excluding non-English locale directories: "
                f"{', '.join(sorted(present_locales))} (English-only mirror)"
            )
    else:
        # Locale run: warn per requested locale absent from the upstream
        # tree (nothing was mirrored for it -- the slug namespace simply has
        # no such section), then name the directories that were mirrored.
        for code in sorted(requested - present_locales):
            print(
                f"  warning: requested locale {code!r} not found under "
                f"{DOCS_PREFIX!r} -- nothing mirrored for it",
                file=sys.stderr,
            )
        if mirrored_locales:
            print(
                "   mirroring locale directories: "
                f"{', '.join(sorted(mirrored_locales))}"
            )

    return pages


# ---------------------------------------------------------------------------
# Fetch hook: download raw MDX and convert to Markdown
# ---------------------------------------------------------------------------
# The pipeline calls ``fetch_markdown`` (via ``getattr`` on the source module)
# instead of downloading ``page.source_md_url`` directly.  This hook fetches
# the raw MDX from ``raw.githubusercontent.com``, runs it through
# ``_mdx_to_md`` to strip JSX and convert callouts, validates the output,
# and returns ``(markdown, content_hash)`` for the pipeline's manifest.
# Any conversion or validation failure raises ``FetchError`` so the pipeline
# carries the previous manifest entry forward rather than writing corruption.


def fetch_markdown(client: httpx.Client, page: Page) -> tuple[str, str]:
    """Pipeline hook: fetch one page's raw MDX and return ``(markdown, hash)``.

    This is the optional ``fetch_markdown`` hook described in
    ``sources/base.py``: the pipeline calls it via ``getattr`` instead of
    downloading ``page.source_md_url`` as ready Markdown, because the upstream
    files are MDX (Markdown with embedded JSX), not plain Markdown.

    The raw MDX is fetched from ``raw.githubusercontent.com``, converted to
    clean Markdown via ``_mdx_to_md``, and validated before the content hash
    is computed. A validation failure raises ``FetchError`` so the pipeline
    carries the previous manifest entry forward rather than writing garbage
    to disk.
    """
    raw = fetch.get_with_retry(client, page.source_md_url)
    try:
        md = _mdx_to_md(raw)
    except Exception as exc:
        raise fetch.FetchError(
            f"MDX to Markdown conversion failed for {page.slug}: {exc}"
        ) from exc
    if not fetch.validate_markdown(md):
        raise fetch.FetchError(f"validation failed for {page.slug} (not Markdown?)")
    return md, fetch.content_hash(md)
