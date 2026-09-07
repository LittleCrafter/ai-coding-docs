"""Shared HTTP fetching, validation and hashing for all sources.

Every source ultimately needs the same thing: download a Markdown URL, make
sure it really is Markdown, hash it, and pull out a title. Source-specific
*discovery* lives in the source modules; this module handles the generic
fetch+validate+hash pipeline.

The pieces compose bottom-up, and the orchestrator almost always wants only
the top-level convenience wrapper::

    make_client      -- the shared httpx.Client factory; the entry point every
                        run calls first, before any fetching happens
    get_with_retry   -- HTTP GET with bounded retries + backoff
    fetch_binary     -- HTTP GET with the same retry policy, returning the
                        raw response bytes (no decode, no markdown validation)
    validate_markdown -- cheap heuristic: is this really Markdown?
    extract_title    -- best-effort title for the manifest/index
    content_hash     -- sha256 used for change detection
    fetch_validated  -- = get_with_retry + validate_markdown + content_hash

Design notes:

  * Retries are reserved for *transient* failures (transport errors, 429,
    5xx); other 4xx responses fail fast (see `get_with_retry` for why).
  * Validation is a heuristic, not a parser: the mirror only needs to reject
    HTML error pages and near-empty bodies cheaply, not prove the document is
    well-formed CommonMark.
  * The hash covers the *exact response text*, so any upstream edit -- even
    whitespace -- is detected as a modification. That is intentional: a false
    positive costs a rewritten file, a false negative costs a stale mirror.
"""

from __future__ import annotations

import hashlib
import random
import re
import threading
import time
from bisect import bisect_right
from collections.abc import Mapping

import httpx

from .. import config

# Anchored YAML frontmatter block at the very start of the document:
# an opening ``---`` fence, the block body (captured), and a closing fence.
# Anchoring matters: a bare ``^title:`` search would also hit ``title:``
# lines inside the page body (e.g. in a fenced code sample or a later
# horizontal-rule section), which are *not* the document title. Leading
# whitespace before the opening fence (blank lines, spaces) is tolerated;
# the block body is matched non-greedily so it stops at the *first* closing
# fence, never at a ``---`` rule further down the page.
#
# NOTE: Python's ``\s`` in default re mode does NOT match U+FEFF (BOM /
# ZERO WIDTH NO-BREAK SPACE). That character shows up at the very start of
# real-world documents for two reasons: as an encoding signature (the UTF-8
# BOM some Windows tools prepend on save) and as its original Unicode role,
# an invisible zero-width formatting character. Either way it is *invisible
# but present*: wedged between the start of the string and the opening fence
# it silently defeats both the ``\A`` anchor here and the ``^``-anchored
# heading patterns downstream. Both callers (`validate_markdown` and
# `extract_title`) therefore strip a leading BOM before matching, so a
# BOM-prefixed document still validates and still gets its frontmatter
# title extracted.
# The ``\r?\n`` in the fence lines handles CRLF line endings (``\r\n``)
# from Windows-hosted or Windows-generated documents.
_FRONTMATTER_BLOCK_RE = re.compile(
    r"\A\s*---[ \t]*\r?\n(.*?)\r?\n---[ \t]*(?:\r?\n|\Z)", re.DOTALL
)
# A ``title:`` key, matched only inside the captured frontmatter block.
# Case-insensitive: YAML keys are case-sensitive by spec, but real-world
# frontmatter in documentation sites routinely uses ``Title:`` or ``TITLE:``
# (particularly in older Jekyll/Hugo sites), so we accept any casing rather
# than silently falling through to the heading-fallback path and losing the
# canonical title. Surrounding quotes are stripped downstream.
#
# The padding around the value is ``[ \t]*``, NOT ``\s*``: ``\s`` also matches
# newlines, so with ``\s*`` an entry with an EMPTY value (``title:`` followed
# directly by a newline) would have the trailing ``\s*`` swallow the newline
# and the ``(.+?)`` capture the *next* frontmatter line (e.g. ``description:
# X``) as the title. ``[ \t]*`` confines the match to a single line, so an
# empty value simply does not match and the caller falls through to the
# heading-extraction path as intended.
_FRONTMATTER_TITLE_RE = re.compile(
    r"^title:[ \t]*(.+?)[ \t]*$", re.MULTILINE | re.IGNORECASE
)
# The ``re.MULTILINE`` flag is essential here: without it, ``^`` only matches
# at the very start of the frontmatter block string (position 0) and ``$`` only
# matches at the very end. With MULTILINE, ``^title:`` matches at the start of
# ANY line within the block, and ``$`` anchors each captured value to its own
# line end. The captured block is a multi-line string (the entire frontmatter
# body between the opening and closing ``---`` fences), so without MULTILINE
# this pattern would only find a ``title:`` key on the very first frontmatter
# line -- missing it entirely when frontmatter has preceding keys like
# ``description:`` or ``sidebar_position:`` above the title.
#
# ``re.IGNORECASE`` accepts both ``title:`` and ``Title:`` (and ``TITLE:``).
# YAML keys are case-sensitive by the spec, but real-world documentation
# frontmatter -- particularly in older Jekyll and Hugo sites -- routinely uses
# ``Title:`` as the key. Accepting any casing here means we extract the
# canonical title rather than silently falling through to the heading-fallback
# path and losing it. The cost of accepting ``TITLE:`` is zero: it is never a
# legitimate page-prose heading, so no false extraction can occur.
# A heading-shaped line used by `validate_markdown` as the "looks like
# Markdown" signal once the frontmatter check has failed. It accepts either:
#   * an ATX heading (``# ...`` with optional leading whitespace and at least
#     one non-space character after the hashes); or
#   * a Setext heading (a text line immediately underlined by a run of
#     ``===`` or ``---``).
# The Setext tail ``\s*$`` already absorbs an optional carriage return, so
# CRLF-encoded Setext headings validate correctly (see `_SETEXT_HEADING_RE`
# below for why the title extractor needs the matching tolerance).
#
# The Setext content line must contain at least one character that is not
# ``=``, ``-`` or whitespace (the ``[^-=\s]`` in the middle of the
# ``[^\n]*?[^-=\s][^\n]*`` pattern): without that guard, a line consisting
# only of dashes above a ``---`` underline -- i.e. two adjacent horizontal
# rules like ``---\n---`` -- would be misread as a Setext heading and would
# pass validation despite having no real heading structure. The guard's
# scope is deliberately limited to keeping the Setext branch honest: it is
# NOT a full document-structure proof -- a longer run of ``---`` lines can
# still validate through the frontmatter branch above.
#
# BACKTRACKING HAZARD (why the atomic group): the naive form
# ``[^\n]*[^-=\s][^\n]*`` sandwiches one character class between two
# overlapping greedy quantifiers. On a line where the Setext match fails
# late -- e.g. a single very long line with no newline at all -- the engine
# retries every split point of the first quantifier, and for each one the
# second quantifier scans and gives back the whole rest of the line, which
# is O(n^2) in line length. The pattern runs on raw network input and
# ``MAX_RESPONSE_BYTES`` allows bodies of several MiB, so this is a
# remotely-triggerable hang (measured: ~18 s for one 200 KB single-line
# body; multi-MiB bodies are effectively unbounded). Making the first
# quantifier lazy (``[^\n]*?``) does NOT help: the second greedy quantifier
# still re-scans the line for every expansion step. The atomic group
# ``(?>...)`` (Python 3.11+) removes the hazard instead: the lazy inner
# quantifier commits to the FIRST position that satisfies ``[^-=\s]`` and
# the group is never re-entered, so each line is scanned exactly once --
# O(n) overall. The match semantics are unchanged: the split point of the
# sandwich is unobservable from outside the group because everything the
# group consumes is non-newline either way, so any successful naive match
# succeeds identically here (and vice versa).
_HEADING_MARKER_RE = re.compile(
    r"(?:^\s*#{1,6}\s+\S|^(?>[^\n]*?[^-=\s][^\n]*)\n[-=]{2,}\s*$)", re.MULTILINE
)
# Fenced code block stripping, in either CommonMark fence style: an opening
# fence of three backticks or three tildes (optionally followed by an info
# string on the same line), a body of any number of lines, and a matching
# closing fence of the SAME style (exactly three fence characters plus
# optional trailing spaces/tabs). Used by `extract_title` to strip code
# blocks before scanning for headings, so a heading-shaped line inside a
# code sample is never mistaken for the document title.
#
# Both fence styles are handled in ONE left-to-right pass (see
# `_strip_fenced_code_blocks`): a ``~~~`` line *inside* a backtick block is
# never mistaken for that block's closing fence, and whichever fence style
# opens first wins -- exactly like CommonMark's own left-to-right parse.
#
# BACKTRACKING HAZARD (why this is a line scanner, not a regex): the
# natural regex form ``^```[^\n]*\n.*?^```[ \t]*$`` (with a tilde
# alternative, DOTALL|MULTILINE) is O(N x body length) on input with N
# unclosed opening fences. When no closing fence exists, the lazy ``.*?``
# expands all the way to end-of-string looking for a closer, fails, and the
# regex engine then retries the whole scan from the NEXT unclosed opener --
# so every unclosed fence costs one full scan of the remaining body. The
# pattern runs on raw network input and ``MAX_RESPONSE_BYTES`` allows bodies
# of several MiB, making this a remotely-triggerable hang (measured: 20,000
# lines of ``"```python\n"`` -- ~140 KB, well under the size cap -- did not
# finish in 180 s; 2,000/4,000/8,000 openers took 0.34/1.33/5.26 s, the
# classic 4x-per-2x quadratic signature). A tempered body such as
# ``(?:(?!^```[ \t]*$)[\s\S])*`` does NOT fix this: it only changes which
# lines the body may contain, not the per-opener scan-to-end failure cost.
# The line scanner below is linear instead: each line is examined a bounded
# number of times, and the closer lookup per opener is a ``bisect`` over a
# precomputed index list (O(log n)) rather than a re-scan of the tail.
# An ATX heading in the body, used by `extract_title` as the first
# heading-fallback: one to six leading hashes, required whitespace, then the
# heading text (captured, non-greedy) up to the end of the line. ``\s*$``
# absorbs any trailing carriage return so CRLF-encoded ATX headings extract
# the same way LF-encoded ones do.
#
# The ``^ {0,3}`` prefix allows up to three leading SPACES before the hashes,
# exactly as CommonMark specifies for ATX headings (0-3 spaces of indentation
# are still a heading; 4+ would make it an indented code block). This keeps
# the extractor consistent with `_HEADING_MARKER_RE`, whose ATX branch
# already tolerates leading whitespace: without the prefix, a page whose
# only heading is indented 1-3 spaces would validate as Markdown but then be
# filed under the fallback title. The bound is a literal space run (NOT
# ``\s*``) for two reasons: ``\s`` would also match newlines (letting the
# pattern drift across line boundaries and break CommonMark correctness),
# and an unbounded whitespace run would re-introduce a polynomial
# backtracking hazard against long network-controlled lines -- ``{0,3}`` is
# bounded, so the prefix adds at most three match attempts per line start.
_ATX_HEADING_RE = re.compile(r"^ {0,3}#{1,6}\s+(.+?)\s*$", re.MULTILINE)
# A Setext heading in the body, used by `extract_title` as the second
# heading-fallback: a text line (captured) immediately followed by an
# underline of two or more ``=`` or ``-`` characters. The underline tail
# ``[ \t]*\r?$`` accepts an optional trailing carriage return, so a
# CRLF-encoded Setext heading (``Title\r\n===\r\n``) is extracted rather than
# silently dropping to the fallback title. This keeps the Setext path
# CRLF-tolerant exactly like the frontmatter and ATX paths above; without the
# ``\r?`` such a heading would validate as Markdown (the
# `_HEADING_MARKER_RE` tail uses ``\s*``, which matches ``\r``) but then fail
# to yield a title here. The content line must contain at least one character
# that is not ``=``, ``-`` or whitespace so a pair of adjacent horizontal
# rules is not mistaken for a heading.
#
# BACKTRACKING HAZARD: the capture uses the same atomic-group form as the
# Setext branch of `_HEADING_MARKER_RE` above (see its comment for the full
# analysis): the naive ``[^\n]*[^-=\s][^\n]*`` sandwich is O(n^2) in line
# length on network-controlled input, and a lazy first quantifier does not
# fix it. ``(?>...)`` commits to the first viable split and is never
# re-entered, so a pathological single-line body cannot hang the run. The
# captured text is identical to the naive form: within one line, the lazy
# first quantifier commits to the FIRST ``[^-=\s]`` position and the greedy
# tail consumes the rest, which always spans the same maximal non-newline
# run the naive backtracking search would ultimately return.
_SETEXT_HEADING_RE = re.compile(
    r"^((?>[^\n]*?[^-=\s][^\n]*))\r?\n[-=]{2,}[ \t]*\r?$", re.MULTILINE
)
# Markers that strongly suggest the server answered with an HTML page (an
# error page, a login wall, a JS shell) instead of the requested Markdown.
# Only the lowercase forms are listed: the scanned head is lowercased before
# comparison, so uppercase variants here would be dead entries.
_HTML_MARKERS = ("<!doctype", "<html")
# The minimum byte count a response body must reach to be considered a
# potentially useful documentation page -- applied only to bodies that show
# no Markdown structure (see ``validate_markdown``, where a short body that
# opens with a heading or frontmatter is accepted regardless of size). Real
# documentation pages are kilobytes in size -- even the thinnest stub page
# on a mirrored site carries frontmatter or a heading plus some prose, and
# the observed pages range from a few kilobytes to hundreds of kilobytes --
# so a threshold of fifty bytes sits far below every legitimate page. What
# the guard actually catches is the other end of the scale: empty bodies,
# bare error strings, and truncated error responses, none of which would
# give the mirror anything worth persisting to disk.
_MIN_BYTES = 50


# Small helper that returns the byte length of a UTF-8-encoded string,
# used by the size-checking logic in ``get_with_retry`` to measure the
# actual on-wire footprint of a response body. Centralising the
# ``len(text.encode("utf-8"))`` pattern here makes the intent explicit at
# each call site and isolates the one allocation-heavy step to a single
# definition, so that a cheaper approach (e.g. a C extension or a
# ``memoryview``-based count) can replace it later without touching every
# call site.
def _byte_length(text: str) -> int:
    """Return the number of bytes ``text`` occupies when encoded as UTF-8.

    This is the measure that the ``MAX_RESPONSE_BYTES`` limit enforces:
    HTTP bodies are byte sequences on the wire, and Python's ``len(text)``
    counts Unicode code points, which can underestimate the byte footprint
    for strings with multi-byte characters (emoji, CJK, accented Latin,
    etc.), potentially allowing oversized payloads to bypass the guard.
    """
    return len(text.encode("utf-8"))


class FetchError(Exception):
    """Raised when a page cannot be fetched or fails validation.

    One exception type for the whole fetch pipeline (transport failure,
    exhausted retries, non-transient HTTP status, failed validation) lets the
    orchestrator catch a single error kind per page, record it in the
    manifest's ``failed_pages`` list, and move on to the next page instead of
    aborting the whole run.

    `status_code` carries the HTTP response status that caused the failure
    (e.g. 403, 404, 429, or 500 after retries) whenever the error originates
    from an HTTP response; it is ``None`` for failures with no response at
    all (transport errors, undecodable bodies, validation failures, invalid
    URLs). Consumers use it to distinguish "the page is gone" (404) from
    "the upstream is rate-limiting us" (429) without parsing the message.
    It is a keyword-only, defaulted attribute so existing bare
    ``FetchError("msg")`` constructions keep working unchanged.
    """

    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        """Record why a page fetch failed and which HTTP status the upstream
        server returned, when the failure came from an HTTP response.

        Args:
            message: Human-readable description of what went wrong. Stored as
                the exception message and surfaced in the pipeline's per-page
                error output and the manifest's ``failed_pages`` list.
            status_code: The HTTP response status code that caused the failure
                (e.g. 403, 404, 429, or 500 after retries are exhausted).
                ``None`` when the error has no HTTP response -- transport
                failures (DNS, connection refused, timeout), undecodable
                bodies, validation failures, and invalid URLs. Consumers read
                this attribute (never string-parse the message) to distinguish
                "the page is gone" (404) from "the upstream is rate-limiting
                us" (429).
        """
        super().__init__(message)
        self.status_code = status_code


class ResponseText(str):
    """The decoded body of a successful GET, carrying the response headers.

    `get_with_retry` returns this ``str`` subclass rather than a plain
    ``str`` so the response headers stay reachable after the
    ``client.stream`` context has closed -- without changing the return
    contract. Every existing consumer treats the result as a plain string
    (``json.loads``, ``str`` methods, and equality with plain strings all
    behave identically on a ``str`` subclass), while the rare caller that
    needs response metadata -- currently only
    ``core.github.fetch_git_tree``, which reads GitHub's
    ``X-RateLimit-Remaining`` bookkeeping header -- reaches it via the
    ``headers`` attribute instead of issuing a second request or threading
    an extra return value through every call layer.

    ``headers`` is annotated as a plain ``Mapping`` (not ``httpx.Headers``)
    because the attribute is assigned AFTER construction -- a ``str``
    subclass's value is fixed at ``__new__`` time, so the headers cannot be
    a constructor parameter -- and nothing therefore enforces the concrete
    mapping type. In production it holds the real ``httpx.Headers`` (whose
    lookup is case-insensitive, per HTTP header semantics); tests may
    substitute any mapping.
    """

    headers: Mapping[str, str]


def make_client() -> httpx.Client:
    """Build the shared HTTP client with the project's standard settings.

    The returned client should be created once at the start of a mirror run
    and reused across all page fetches, because httpx.Client pools TCP
    connections and reuses them for requests to the same host. Without this
    pooling, every page fetch from the same upstream would open (and later
    close) a new TCP connection -- adding latency from TLS handshakes and
    needlessly consuming upstream connection slots.

    The ``User-Agent`` identifies the mirror to upstream operators (so they
    can distinguish us from anonymous scraping and reach out if the load
    bothers them), and the ``Accept`` header advertises that we prefer raw
    Markdown -- several docs platforms content-negotiate on it. Redirects are
    followed because upstreams routinely move pages and respond with 301/302.
    """
    return httpx.Client(
        headers={
            "User-Agent": config.USER_AGENT,
            "Accept": "text/markdown, text/plain, */*",
        },
        timeout=config.TIMEOUT,
        follow_redirects=True,
    )


def _fetch_raw_with_retry(
    client: httpx.Client,
    url: str,
    *,
    extra_headers: dict[str, str] | None = None,
) -> tuple[bytes, httpx.Headers, str | None]:
    """Execute GET request with bounded retries, streaming accumulation, and error classification.

    Returns ``(body_bytes, headers, encoding)``.
    """
    delay = config.RETRY_DELAY
    last_exc: Exception | None = None
    for attempt in range(1, config.MAX_RETRIES + 1):
        try:
            with client.stream("GET", url, headers=extra_headers) as resp:
                status = resp.status_code

                if 400 <= status < 500 and status != 429:
                    raise FetchError(
                        f"HTTP {status} for {url} (non-transient, not retried)",
                        status_code=status,
                    )

                if status == 429 or status >= 500:
                    retry_after = resp.headers.get("Retry-After")
                    wait = delay * random.uniform(0.5, 1.5)
                    if retry_after:
                        try:
                            wait = max(
                                0.0, min(float(retry_after), config.MAX_RETRY_DELAY)
                            )
                        except ValueError, OverflowError:
                            pass
                    last_exc = FetchError(
                        f"HTTP {status} for {url}", status_code=status
                    )
                    if attempt == config.MAX_RETRIES:
                        break
                else:
                    content_length = resp.headers.get("Content-Length")
                    if content_length is not None:
                        try:
                            if int(content_length) > config.MAX_RESPONSE_BYTES:
                                raise FetchError(
                                    f"Response body too large for {url}: Content-Length "
                                    f"{content_length} bytes exceeds limit of "
                                    f"{config.MAX_RESPONSE_BYTES} bytes"
                                )
                        except ValueError:
                            pass

                    body_bytes = bytearray()
                    for chunk in resp.iter_bytes():
                        body_bytes.extend(chunk)
                        if len(body_bytes) > config.MAX_RESPONSE_BYTES:
                            raise FetchError(
                                f"Response body too large for {url}: exceeds limit of "
                                f"{config.MAX_RESPONSE_BYTES} bytes"
                            )

                    return bytes(body_bytes), resp.headers, resp.encoding
        except httpx.InvalidURL as exc:
            raise FetchError(f"Invalid URL {url!r}: {exc}") from exc
        except httpx.RequestError as exc:
            last_exc = exc
            if attempt == config.MAX_RETRIES:
                break
            time.sleep(delay * random.uniform(0.5, 1.5))
            delay = min(delay * 2, config.MAX_RETRY_DELAY)
            continue

        time.sleep(wait)
        delay = min(delay * 2, config.MAX_RETRY_DELAY)

    raise FetchError(
        f"Failed after {config.MAX_RETRIES} attempts: {url} ({last_exc})",
        status_code=last_exc.status_code if isinstance(last_exc, FetchError) else None,
    )


def get_with_retry(
    client: httpx.Client, url: str, *, extra_headers: dict[str, str] | None = None
) -> str:
    """GET `url` with bounded retries + exponential backoff, returning text.

    Retries are reserved for *transient* failures only:

      * request-level errors raised by httpx (DNS, connection, read, timeout
        and other ``httpx.RequestError`` subclasses -- including
        ``httpx.DecodingError`` from a corrupt or truncated compressed body,
        which surfaces mid-stream from ``iter_bytes()``);
      * HTTP ``429 Too Many Requests`` and any ``5xx`` server response.

    A *non-transient* client error -- any ``4xx`` other than ``429``, e.g.
    ``404 Not Found`` or ``403 Forbidden`` -- is raised immediately. Such a
    response describes a problem with the request itself that re-issuing it
    will not fix, so retrying would only waste attempts and upstream API
    quota. The same fail-fast rule applies to ``httpx.InvalidURL``: a
    malformed URL fails identically on every attempt, so it is converted to
    a `FetchError` at once instead of burning all retries on it.

    Backoff doubles after every failed attempt (starting at
    ``config.RETRY_DELAY``) and is capped at ``config.MAX_RETRY_DELAY``, so a
    stubborn endpoint stalls the run by seconds, not minutes. Every backoff
    sleep is JITTERED with a random factor in ``[0.5, 1.5]``. A numeric
    ``Retry-After`` response header, when present, overrides the jittered delay.

    `extra_headers` lets callers attach per-request headers (e.g. GitHub API
    auth from ``core.github.api_headers``) without mutating the shared client.

    Raises `FetchError` once all ``config.MAX_RETRIES`` attempts are
    exhausted. When the failure was caused by an HTTP response status, the
    raised (or recorded) error carries that status in
    ``FetchError.status_code``; transport failures leave it ``None``.

    The returned text is a `ResponseText` -- a ``str`` in every respect that
    matters to consumers, additionally carrying the response headers.
    """
    body_bytes, headers, encoding = _fetch_raw_with_retry(
        client, url, extra_headers=extra_headers
    )
    try:
        body = body_bytes.decode("utf-8")
    except UnicodeDecodeError:
        try:
            body = body_bytes.decode(encoding or "utf-8")
        except (UnicodeDecodeError, LookupError) as exc:
            raise FetchError(
                f"Could not decode response body for {url}: {exc}"
            ) from exc

    body_byte_length = _byte_length(body)
    if body_byte_length > config.MAX_RESPONSE_BYTES:
        raise FetchError(
            f"Response body too large for {url}: {body_byte_length} bytes "
            f"exceeds limit of {config.MAX_RESPONSE_BYTES} bytes"
        )

    result = ResponseText(body)
    result.headers = headers
    return result


def validate_markdown(text: str) -> bool:
    """Reject HTML error pages and obviously-empty responses.

    This is a cheap heuristic, not a Markdown parser -- the goal is to stop
    garbage from reaching ``docs/``, not to certify the document. A response
    passes when all of the following hold:

      1. it is at least ``_MIN_BYTES`` long, UNLESS it already shows Markdown
         structure (see rule 3) -- the floor targets empty bodies, bare
         error strings, and truncated responses, none of which carry a
         heading, while a short document that opens with a heading or
         frontmatter is legitimately small (e.g. a landing-page shell whose
         static content is a heading and a single line);
      2. its first 512 characters contain no HTML doctype/``<html>`` marker,
         which is what upstreams serve when the ``.md`` URL actually 404s into
         an HTML error page or a JS-app shell;
      3. it looks like Markdown: either it opens with a *complete* YAML
         frontmatter block (an opening ``---`` fence *and* a closing one)
         or it contains at least one ATX (``# ...``) or Setext (underlined
         with ``===``/``---``) heading.

    Rule 3 errs on the side of rejection: a Markdown page with no frontmatter
    and no heading at all is rare enough in real documentation sets that
    dropping it is safer than risking mirrored HTML. The frontmatter branch
    deliberately requires the closing fence: a bare ``---`` at the start of
    the body is just a horizontal rule, and treating one as frontmatter
    would wave through thin HTML-stub-adjacent content that happens to open
    with a rule.
    """
    # Strip a leading BOM (U+FEFF) before any matching, exactly as
    # `extract_title` does (see the comment there for why ``\s`` never
    # matches U+FEFF). Without this, a BOM-prefixed document that relies on
    # a heading -- rather than frontmatter -- as its Markdown signal would
    # fail rule 3: the BOM sits between ``^`` and the ``#``, and neither the
    # frontmatter anchor nor the ATX pattern can see past it. Such a page
    # would then be rejected as "not Markdown" and never mirrored even though
    # `extract_title` would have handled it fine.
    text = text.lstrip("\ufeff")
    # Use len(text) (character count) rather than len(text.encode("utf-8"))
    # (byte count): for ASCII content the values are identical, and for
    # multi-byte content the character count is a slightly more permissive
    # lower bound -- which is fine for a heuristic that only needs to reject
    # trivially-tiny stub/error responses. Avoiding the encode() call also
    # saves allocating a bytes copy of the full document on every validation.
    # The Markdown-structure flag is computed BEFORE the size floor because
    # the floor is deliberately waived for bodies that already show Markdown
    # structure (rule 3): the empty bodies, bare error strings, and truncated
    # responses the floor exists to reject never carry a heading or
    # frontmatter, while a short document that opens with either is a real,
    # if small, page. Computing the flag once here also lets the final
    # acceptance test reuse it instead of re-scanning the body.
    #
    # Frontmatter branch: reuse the full block regex (opening fence, body,
    # closing fence) so a bare "---" horizontal rule alone does not pass.
    # Accept both ATX headings (with optional leading whitespace) and Setext
    # headings (underlined with === or ---) as Markdown indicators.
    is_markdown = bool(_FRONTMATTER_BLOCK_RE.match(text)) or bool(
        _HEADING_MARKER_RE.search(text)
    )
    if len(text) < _MIN_BYTES and not is_markdown:
        return False
    # Only the head is scanned: error pages announce themselves immediately,
    # and scanning a full document for "<html" would false-positive on
    # legitimate docs that discuss HTML tags inline.
    head = text[:512].lower()
    # `head` is already lowercased, and _HTML_MARKERS entries are stored in
    # lowercase, so a direct `in` check on the lowercased head is sufficient
    # -- no per-marker .lower() call is needed.
    if any(marker in head for marker in _HTML_MARKERS):
        return False
    return is_markdown


def _is_fence_closer(line: str, fence: str) -> bool:
    """Return True when *line* is a valid closing fence for *fence*.

    Mirrors the closing-fence half of the former ``_CODE_FENCE_RE`` pattern
    exactly: the line must be the three-character fence string followed by
    nothing but spaces or tabs. A longer fence run (e.g. four backticks) is
    NOT a closer for a three-backtick opener, and a carriage return is NOT
    tolerated -- the old pattern's ``[ \t]*$`` accepted neither, so a
    CRLF-encoded document's fences never close (the whole fence is treated
    as unclosed and its lines are kept, headings and all).
    """
    return line.startswith(fence) and all(c in " \t" for c in line[len(fence) :])


def _strip_fenced_code_blocks(text: str) -> str:
    """Remove every complete fenced code block from *text* in one linear pass.

    This is a drop-in, semantics-identical replacement for the former
    ``_CODE_FENCE_RE.sub("", text)`` call: a block runs from an opening
    fence line (`` ``` `` or ``~~~`` plus an optional info string, and a
    terminating newline -- an opener on the very last line without one can
    never open a block, exactly as the old pattern's required ``\n``
    dictated) through the first following line that is a bare closing fence
    of the same style. Both fence lines and the body between them are
    dropped; everything else -- including UNCLOSED fences, which the old
    regex simply never matched -- is kept verbatim.

    The scan replicates the old substitution's left-to-right, first-opener-
    wins behaviour: the earliest opening fence claims the block, its body is
    consumed up to its closer (inner fence lines of either style are body
    text, never openers or closers in their own right), and scanning resumes
    on the line after the closer. An opener with no closer anywhere after it
    matches nothing and is emitted as ordinary text, and -- this is the key
    linear-time observation -- no LATER opener of the same style can close
    either, because a closer for it would also have closed this one. That
    monotonicity lets each style's closer candidates be precomputed once as
    a sorted list of line indices; each opener then finds its first possible
    closer with one ``bisect_right`` instead of re-scanning the document
    tail, so N unclosed openers cost O(N log N) total rather than
    O(N x body length) -- see the hazard comment where ``_CODE_FENCE_RE``
    used to be defined for why the regex form was a remotely-triggerable
    hang on network-controlled input.
    """
    # Split on "\n" only (never ``str.splitlines``): the old pattern's ``^``
    # anchor recognised line starts exclusively after ``\n``, so a `` ``` ``
    # following a bare ``\r`` or a Unicode line separator must NOT count as
    # fence-shaped. Every part except the last ended with ``\n`` in the
    # original text, which is also how the opener's required trailing
    # newline is detected below.
    parts = text.split("\n")
    # Closer-candidate line indices per fence style, precomputed in one
    # pass. A line qualifies as a closer candidate even when it also LOOKS
    # like an opener (a bare "```" line is both): which role it plays is
    # decided by the scan order below, matching the regex's leftmost-match
    # resolution.
    closers = {
        "```": [i for i, p in enumerate(parts) if _is_fence_closer(p, "```")],
        "~~~": [i for i, p in enumerate(parts) if _is_fence_closer(p, "~~~")],
    }
    out: list[str] = []
    i = 0
    last = len(parts) - 1
    while i <= last:
        part = parts[i]
        # Opener check: the line must start with a fence AND be followed by
        # a newline (i.e. not be the final part), mirroring the old
        # pattern's ``^```[^\n]*\n``. The info string needs no validation --
        # ``[^\n]*`` accepted anything, including extra fence characters.
        fence = None
        if i < last:
            if part.startswith("```"):
                fence = "```"
            elif part.startswith("~~~"):
                fence = "~~~"
        if fence is not None:
            candidates = closers[fence]
            # O(N log N) lookup: bisect_right finds the first valid closer after `i`
            k = bisect_right(candidates, i)
            if k < len(candidates):
                # Complete block: skip opener, body, and closer wholesale.
                # Lines inside are never reconsidered as openers, exactly
                # like the consumed body of a regex match.
                i = candidates[k] + 1
                continue
        # Not an opener, or an opener with no closer: keep the line as
        # ordinary text and move on, as the failed regex match did.
        out.append(part)
        i += 1
    return "\n".join(out)


def extract_title(text: str, fallback: str = "Untitled") -> str:
    """Best-effort title: frontmatter `title:`, else first Markdown heading.

    The frontmatter `title:` key is only honored inside a proper YAML
    frontmatter block anchored at the start of the document
    (``---\\n...\\n---``); a ``title:`` line elsewhere in the body -- say,
    inside a fenced code sample -- is ignored. Frontmatter wins because it is
    what upstreams themselves treat as the canonical title (and it may differ
    from the first heading, e.g. when the H1 repeats a site name). Surrounding
    single/double quotes are stripped since YAML authors commonly quote titles
    containing colons.

    Without a frontmatter title, the first ATX heading (``# Heading``) in the
    document BODY wins. Only if the body contains no ATX heading at all is
    the first Setext heading (a text line underlined with ``===`` or ``---``)
    used instead. ATX is checked first across the whole body rather than
    "whichever heading syntax appears earliest", because ATX is by far the
    more common heading form in the mirrored upstream docs; the Setext pass
    is a fallback that exists because `validate_markdown` already accepts
    Setext-headed documents as valid Markdown -- without extracting them here
    such pages would all be filed under the fallback title even though their
    heading is right there. The heading search deliberately starts AFTER the
    frontmatter block (not at the start of the whole document): YAML
    frontmatter commonly contains ``#``-prefixed comment lines
    (commented-out keys, section dividers like ``# --- navigation ---``),
    and a document whose frontmatter has no ``title:`` key but does carry
    such a comment would otherwise have that comment line mis-extracted as
    the page title. Searching only the post-frontmatter text mirrors the way
    a real Markdown renderer treats the frontmatter as opaque metadata,
    never as heading-bearing content.

    When neither source yields anything, `fallback` is returned so the
    manifest always has *some* displayable title.
    """
    # Strip a leading BOM (U+FEFF) before any regex matching: Python's ``\s``
    # does not match U+FEFF, so a BOM-prefixed document would otherwise miss
    # both the frontmatter block anchor and the start-of-line heading
    # patterns. ``lstrip("\ufeff")`` (not ``strip``) is used so trailing
    # content is never touched; the title itself is stripped downstream.
    # `validate_markdown` performs the same strip for the same reason -- keep
    # the two in sync, since a page must pass validation before its title is
    # ever extracted.
    text = text.lstrip("\ufeff")
    block = _FRONTMATTER_BLOCK_RE.match(text)
    if block:
        m = _FRONTMATTER_TITLE_RE.search(block.group(1))
        if m:
            title = m.group(1).strip().strip("\"'")
            # Empty quoted titles (title: "" or title: '') are treated as
            # absent and fall through to the heading/fallback path below.
            if title:
                return title
    # Search for headings only in the text AFTER the frontmatter block (when
    # one was matched), never across the whole document. YAML frontmatter
    # routinely carries ``#``-prefixed comment lines -- commented-out keys,
    # section dividers like ``# --- navigation ---`` -- and a frontmatter
    # block with no ``title:`` key but with such a comment would otherwise
    # have the FIRST comment line mis-extracted as the page title, because
    # the ATX pattern ``^#{1,6}\s+...`` matches a YAML comment exactly the
    # way it matches a real ATX heading. Restricting the search to the
    # post-frontmatter body mirrors how a Markdown renderer treats the
    # frontmatter as opaque metadata rather than heading-bearing content, and
    # it is the minimal change that preserves all the existing BOM / CRLF /
    # fenced-code-block tolerance (those patterns still run, just over the
    # body slice). When there is no frontmatter at all, ``block`` is None and
    # the whole document is searched exactly as before.
    search_text = text[block.end() :] if block else text
    # Strip fenced code blocks so headings inside code samples are not matched
    # as document headings. The linear scanner handles both backtick (```)
    # and tilde (~~~) fences in one left-to-right pass (see
    # `_strip_fenced_code_blocks` for the matching rules and for why a regex
    # substitution was a quadratic-time hazard on unclosed fences).
    text_no_blocks = _strip_fenced_code_blocks(search_text)
    heading = _ATX_HEADING_RE.search(text_no_blocks)
    if heading:
        # The regex ``^#{1,6}\s+(.+?)\s*$`` consumes the opening ``#{1,6}`` and
        # the mandatory whitespace after it, so capture group 1 holds ONLY the
        # heading text -- no leading hash can ever reach it. A leading-hash
        # strip (e.g. ``lstrip("#")``) is therefore neither needed nor correct:
        # the capture never starts with a markup ``#``, and applying such a
        # strip would corrupt a title that legitimately begins with ``#``, such
        # as the heading ``# #hashtag notes`` whose title is ``#hashtag notes``
        # (lstripping would silently drop the meaningful leading ``#``).
        #
        # What the captured text CAN end with is the decorative trailing hash
        # run of a "closed" ATX heading such as ``# Title #`` (valid Markdown
        # whose closing ``#`` is not part of the title). The cleanup below
        # handles exactly that case:
        #   1. ``.strip()``  -- trim whitespace around the captured text;
        #   2. ``re.sub(r"\s#+$", "", title)`` -- drop a trailing closing-ATX
        #      hash run, but ONLY when whitespace separates it from the
        #      title: the ``\s`` guard keeps a hash that is part of the title
        #      itself (e.g. the heading ``# C#``) intact, where a plain
        #      ``rstrip("#")`` would silently truncate it to ``C``;
        #   3. ``.strip()``  -- trim the whitespace the removal just exposed
        #      (the space before the closing ``#`` in ``# Title #`` becomes a
        #      trailing space once the ``#`` is gone).
        title = heading.group(1).strip()
        return re.sub(r"\s#+$", "", title).strip()
    # Setext fallback: a text line underlined by a run of = or -. The content
    # line must contain at least one character that is not ``=``, ``-`` or
    # whitespace, so a pair of consecutive horizontal rules ("---\n---") is
    # not mistaken for a heading.
    setext = _SETEXT_HEADING_RE.search(text_no_blocks)
    if setext:
        return setext.group(1).strip()
    return fallback


def content_hash(text: str) -> str:
    """Return the sha256 hex digest of the exact response text.

    Stored in the manifest and compared by ``core.diff``: a page counts as
    *modified* only when this digest changes between runs. Hashing the raw
    bytes (rather than a normalized form) means even a whitespace-only
    upstream edit is caught -- the cost of a false positive is one rewritten
    file, while a missed change would leave the mirror silently stale.

    SHA-256 is chosen over faster algorithms (MD5, SHA-1) because the hash
    is exposed as a first-class field in the manifest JSON: a weaker
    algorithm that later proves collision-prone would make the manifest
    hash untrustworthy. The performance cost of SHA-256 vs. e.g. SHA-1 is
    negligible at the scale of documentation pages (tens of KiB each).
    """
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def fetch_validated(client: httpx.Client, md_url: str) -> tuple[str, str]:
    """Return (markdown_text, sha256_hash) for a URL, or raise FetchError.

    The one-call pipeline used by the orchestrator for every page: download
    with retries, reject anything that does not look like Markdown, and return
    the body together with the hash the manifest needs. Raising on validation
    failure (instead of returning the bad text) guarantees a broken response
    can never be written into ``docs/``.

    Pages are fetched with the client's own default headers; there is no
    per-request header pass-through here because the only caller that needs
    one (GitHub API auth during discovery in ``core.github``) calls
    ``get_with_retry`` directly rather than going through this function.

    The returned tuple is designed so the caller always receives both the
    content and its identity hash from the same operation -- there is no way
    to accidentally use an outdated hash with updated content or vice versa.
    This pairing matters because ``core.diff`` compares only hashes, never
    the text itself; a hash that doesn't match the text it accompanies would
    be a silent correctness bug.
    """
    text = get_with_retry(client, md_url)
    if not validate_markdown(text):
        raise FetchError(f"Validation failed for {md_url} (not Markdown?)")
    return text, content_hash(text)


class RateLimiter:
    """Thread-safe rate limiter enforcing a minimum delay between dispatches.

    Enforces that at least ``delay`` seconds elapse between consecutive request
    dispatches across all threads sharing this instance. A thread calls
    :meth:`wait` (or :meth:`acquire`) before issuing a network request.

    The first request dispatched through this limiter is executed immediately
    without delay (as ``_next_allowed_time`` starts at 0.0, which is in the past).
    Subsequent dispatches are scheduled at least ``delay`` seconds apart using
    a monotonic clock (:func:`time.monotonic`).

    Thread safety is achieved using a :class:`threading.Lock` to coordinate the
    calculation of scheduled times. The lock is held only for arithmetic and
    state updates; the actual sleep (:func:`time.sleep`) is performed outside
    the lock so other threads can compute their scheduled slots concurrently
    without unnecessary blocking.
    """

    def __init__(self, delay: float = config.RATE_LIMIT_DELAY) -> None:
        """Initialize the rate limiter with a minimum inter-request delay.

        Args:
            delay: Minimum seconds required between consecutive request
                dispatches. Defaults to :data:`config.RATE_LIMIT_DELAY`.
                Values <= 0 disable rate limiting (no sleeping occurs).
        """
        self.delay = delay
        self._lock = threading.Lock()
        self._next_allowed_time = 0.0

    def wait(self) -> None:
        """Wait until enough time has elapsed since the last dispatch."""
        if self.delay <= 0:
            return
        with self._lock:
            now = time.monotonic()
            wait_time = max(0.0, self._next_allowed_time - now)
            scheduled_time = now + wait_time
            self._next_allowed_time = scheduled_time + self.delay

        if wait_time > 0:
            time.sleep(wait_time)

    def acquire(self) -> None:
        """Alias for :meth:`wait`."""
        self.wait()

    def __enter__(self) -> RateLimiter:
        """Context manager entry point; waits for slot allocation."""
        self.wait()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: object,
    ) -> None:
        pass


def fetch_binary(client: httpx.Client, url: str) -> bytes:
    """GET `url` with the same bounded retry policy as `get_with_retry`.

    Returns the raw response body as ``bytes``, unmodified. It is the binary
    counterpart of `get_with_retry` for payloads that are NOT text documents
    -- the media stage (``core.media``) downloads image assets with it, and
    an image must round-trip through the fetch byte-for-byte.

    Reuses `_fetch_raw_with_retry` for identical transient error classification,
    jittered backoff, Retry-After honoring, Content-Length pre-check, and per-chunk
    streaming limits without decoding as UTF-8 or checking markdown validity.
    """
    raw_bytes, _, _ = _fetch_raw_with_retry(client, url)
    return raw_bytes
