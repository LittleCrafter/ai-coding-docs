"""Tests for HTTP fetching, validation and hashing (mirror.core.fetch)."""

from __future__ import annotations

import contextlib
import gzip
import threading

import httpx
import pytest
from conftest import _FakeClient, _Resp
from mirror import config
from mirror.core import fetch

# --- Markdown validation, title extraction, and content-hash determinism ---


def test_validate_markdown_frontmatter():
    """A body with YAML frontmatter counts as valid markdown — most mirrored
    docs start this way, so this acceptance path must keep working."""
    body = "body text here with enough bytes to clear the minimum length check"
    assert fetch.validate_markdown(f"---\ntitle: X\n---\n{body}")


def test_validate_markdown_heading():
    """A document starting with a Markdown heading (no frontmatter) is also
    accepted; some sources publish heading-only pages."""
    assert fetch.validate_markdown("# Title\n\nsome text\n" * 5)


def test_validate_markdown_rejects_html():
    """HTML (e.g. an error page or login wall served with a 200) must be
    rejected — saving it would silently mirror junk into docs/."""
    assert not fetch.validate_markdown("<!doctype html><html>" + "x" * 100)


def test_validate_markdown_rejects_too_short():
    """Very short bodies are rejected as degenerate/truncated content, even
    if they are technically not HTML."""
    assert not fetch.validate_markdown("tiny")


def test_validate_markdown_accepts_short_heading_body():
    """A short body that opens with a heading is legitimate Markdown and must
    clear the size floor: the floor targets empty bodies and bare error
    strings (which never carry a heading), not real -- if small -- pages
    such as a landing-page shell whose static content is a heading and a
    single line."""
    assert fetch.validate_markdown("# Prompt Library\n\nExplore the prompt samples.")
    # A heading-less body of the same length is still rejected.
    assert not fetch.validate_markdown("x" * 40)


def test_extract_title_from_frontmatter():
    """The frontmatter `title` wins when present; it is the most reliable
    title source for mirrored docs."""
    assert fetch.extract_title('---\ntitle: "Hello World"\n---\n') == "Hello World"


def test_extract_title_heading_fallback():
    """Without frontmatter, the first Markdown heading is used as title."""
    assert fetch.extract_title("## My Heading\n") == "My Heading"


def test_extract_title_default_fallback():
    """With neither frontmatter nor heading, the caller-supplied fallback is
    returned so every manifest entry still gets a title."""
    assert fetch.extract_title("no title here", fallback="x") == "x"


def test_content_hash_is_stable():
    """The content hash must be deterministic (same input, same hash) and
    sensitive to any change — the whole diff/modified detection rests on it.
    Pinning the digest to the known SHA-256 of ``"abc"`` (rather than comparing
    the function to itself, which is true for any function regardless of
    correctness) also fixes the algorithm, so a future swap to a different
    hash would be caught here."""
    assert (
        fetch.content_hash("abc")
        == "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
    )
    assert fetch.content_hash("abc") != fetch.content_hash("abd")


# --- get_with_retry (fake client; no real network, no real sleeping) --------
#
# Real sleeps during retries are suppressed suite-wide by the autouse
# ``_no_sleep`` fixture in ``conftest.py`` (it patches the shared stdlib
# ``time.sleep``, which the fetch module reaches via its plain ``import
# time``); individual tests below that need to *observe* the computed delays
# re-patch ``fetch.time.sleep`` with their own capture double.


def test_retry_success_first_try():
    """A 200 on the first attempt returns the body immediately with exactly
    one request — no pointless retries on the happy path."""
    c = _FakeClient([_Resp(200, "body")])
    assert fetch.get_with_retry(c, "https://x") == "body"
    assert c.calls == 1


def test_retry_4xx_fails_fast():
    """Client errors (4xx) are not transient, so they must fail fast without
    retries; retrying a 404 would just hammer the server pointlessly."""
    # A 404 describes a bad request: it must not be retried.
    c = _FakeClient([_Resp(404)])
    with pytest.raises(fetch.FetchError):
        fetch.get_with_retry(c, "https://x")
    assert c.calls == 1


def test_retry_429_then_success():
    """A 429 (rate limited) is transient: the client must honor Retry-After
    and retry, succeeding on the next attempt."""
    c = _FakeClient([_Resp(429, retry_after="0"), _Resp(200, "ok")])
    assert fetch.get_with_retry(c, "https://x") == "ok"
    assert c.calls == 2


def test_retry_5xx_exhausts_then_raises():
    """Persistent server errors (5xx) are retried up to config.MAX_RETRIES
    and then surface as FetchError — bounded retries, never an infinite loop.
    The call count is asserted explicitly: exactly config.MAX_RETRIES attempts
    must be consumed before FetchError is raised, proving the loop does not
    stop early on persistent server errors."""
    c = _FakeClient([_Resp(500), _Resp(500), _Resp(500)])
    with pytest.raises(fetch.FetchError):
        fetch.get_with_retry(c, "https://x")
    assert c.calls == 3


def test_retry_transport_error_then_success():
    """A transport-level failure (no HTTP response at all, e.g. connection
    refused) is also transient and must be retried like a 5xx."""
    c = _FakeClient([httpx.ConnectError("boom"), _Resp(200, "ok")])
    assert fetch.get_with_retry(c, "https://x") == "ok"
    assert c.calls == 2


def test_retry_transport_error_exhausts_then_raises():
    """When ALL attempts raise a transport-level error (here
    ``httpx.ConnectError`` on every call), ``get_with_retry`` must raise
    ``FetchError`` with ``status_code is None`` and exactly
    ``config.MAX_RETRIES`` attempts consumed — transport failures have no HTTP
    status to propagate, so the caller distinguishes them from exhausted-5xx
    errors by the ``None`` status. The call count is asserted explicitly: all
    retries must be used even though no HTTP response was ever received."""
    c = _FakeClient([httpx.ConnectError("boom")] * 3)
    with pytest.raises(fetch.FetchError) as exc_info:
        fetch.get_with_retry(c, "https://x")
    assert exc_info.value.status_code is None
    assert c.calls == 3


def test_fetch_validated_rejects_non_markdown():
    """fetch_validated must validate the body after a successful GET and
    reject HTML-looking content — guards against mirroring an error page or
    login wall served with a 200 status."""
    with pytest.raises(fetch.FetchError):
        fetch.fetch_validated(
            _FakeClient([_Resp(200, "<html>" + "x" * 100)]), "https://x"
        )


# --- fetch_validated success path: returns (text, sha256-hash) tuple ---------


def test_fetch_validated_success_returns_text_and_hash():
    """The happy path through fetch_validated must return a (text, hash) tuple
    where the hash is the sha256 of the text. A regression in the return-value
    shape or the hashing function would corrupt the manifest."""
    text, digest = fetch.fetch_validated(
        _FakeClient(
            [
                _Resp(
                    200,
                    "# Title\n\nbody text here with enough content to pass validation\n"
                    * 5,
                )
            ]
        ),
        "https://x/page.md",
    )
    assert text.startswith("# Title")
    assert digest == fetch.content_hash(text)
    assert len(digest) == 64  # sha256 hex is always 64 chars


# --- Extra request-header forwarding through get_with_retry ------------------


def test_extra_headers_forwarding():
    """``get_with_retry`` must forward ``extra_headers`` to the client's
    ``stream()`` call.  Without this, per-request headers (e.g. GitHub API auth)
    would be silently dropped."""

    class _HeaderCapture:
        """``httpx.Client`` stub that captures the headers dict on every call.

        Each ``stream()`` invocation saves the incoming ``headers`` argument to
        ``self.last_headers`` so a test can later assert that the correct
        ``User-Agent``, ``Accept``, and (when present) ``Authorization``
        headers were passed by ``get_with_retry``. Unlike ``_FakeClient``,
        this stub does not maintain a response script: every call yields a
        hardcoded 200 ``_Resp`` with body ``"ok"``, because the tests that
        use it only care about what headers were sent, not what response
        content was received.
        """

        def __init__(self):
            """Initialize the capture store with no recorded headers.

            ``last_headers`` starts as ``None`` so a test that forgets to
            make a request before asserting gets a clear ``AssertionError``
            rather than a stale value inherited from a previous test run.
            """
            self.last_headers = None

        @contextlib.contextmanager
        def stream(self, method, url, headers=None):
            """Record the request headers and yield a 200 ``_Resp`` stub.

            Mirrors the ``httpx.Client.stream()`` contract that
            ``get_with_retry`` uses: a context manager yielding the response
            object. The ``headers`` dict (or ``None``) is saved to
            ``self.last_headers`` for later assertion. The actual headers
            are not inspected or validated here -- that is the test's
            responsibility.

            Args:
                method: HTTP method of the request (accepted for interface
                    compatibility but not stored or inspected).
                url: The URL being fetched (accepted for interface
                    compatibility but not stored or inspected).
                headers: The HTTP headers sent with the request, saved to
                    ``self.last_headers`` for subsequent assertion.

            Yields:
                A ``_Resp`` instance with ``status_code=200`` and a minimal
                ``"ok"`` body.
            """
            self.last_headers = headers
            yield _Resp(200, "ok")

    client = _HeaderCapture()
    fetch.get_with_retry(client, "https://x", extra_headers={"X-Test": "42"})
    assert client.last_headers == {"X-Test": "42"}


# --- Case-insensitive frontmatter title key: "Title:" treated same as "title:" ---


def test_extract_title_case_insensitive():
    """The frontmatter ``Title:`` (capitalised) must be treated the same as
    ``title:`` — the regex is case-insensitive so that upstreams which use
    capitalised keys still yield a usable title."""
    assert fetch.extract_title('---\nTitle: "Hello World"\n---\n') == "Hello World"


# --- Negative and non-numeric Retry-After header values are handled safely ---


@pytest.mark.parametrize("retry_after", ["-5", "NaN", "-1.5", "-0", "invalid"])
def test_retry_after_negative_is_safe(monkeypatch, retry_after):
    """Negative Retry-After header values (or values that cannot be parsed as
    a positive number, such as ``NaN``) must not cause ``ValueError`` when
    ``get_with_retry`` passes them to ``time.sleep``. The retry logic clamps
    all sleep durations to a non-negative floor, so a buggy or adversarial
    server sending ``Retry-After: -5`` or ``Retry-After: NaN`` results in a
    zero-second delay rather than a crash. The test captures the actual sleep
    calls and asserts every recorded duration is zero or positive."""
    sleeps: list[float] = []
    monkeypatch.setattr(fetch.time, "sleep", sleeps.append)

    fake = _FakeClient(
        [
            _Resp(429, "rate limited", retry_after=retry_after),
            _Resp(
                200,
                "# Valid\n\nContent here.\n\nMore content.\n\nEven more.\n\n"
                "And more.\n\nStill going.\n\nAlmost there.\n\nDone now.",
            ),
        ]
    )

    text = fetch.get_with_retry(fake, "https://example.com/doc")
    assert "Valid" in text
    assert all(s >= 0 for s in sleeps), f"Negative sleep detected: {sleeps}"


# --- empty frontmatter title falls through to headings ------------------------


def test_extract_title_empty_frontmatter_title_falls_through():
    """A frontmatter entry with an EMPTY ``title:`` value must not capture the
    next line as the title. The title regex confines its whitespace tolerance
    to spaces/tabs on the same line, so an empty value simply does not match
    and extraction falls through to the first Markdown heading instead of
    returning something like ``description: X``."""
    text = "---\ntitle:\ndescription: X\n---\n\n# Real Title\n\nbody\n"
    assert fetch.extract_title(text) == "Real Title"


def test_extract_title_ignores_yaml_comment_inside_frontmatter():
    """A ``#``-prefixed YAML comment line inside the frontmatter block must
    NEVER be returned as the page title, even when the frontmatter has no
    ``title:`` key.

    YAML frontmatter commonly carries ``#`` comment lines (commented-out
    keys, section dividers like ``# --- navigation ---``), and a YAML comment
    ``# Foo`` matches the ATX heading regex ``^#{1,6}\\s+...`` exactly the
    way a real ``# Foo`` heading does. The heading-fallback search therefore
    runs over the text AFTER the frontmatter block (not the whole document):
    a Markdown renderer treats frontmatter as opaque metadata, never as
    heading-bearing content. Without this scoping the comment line below
    would be mis-extracted as the title and propagate into the manifest, the
    per-source README, and the whats-new bullets."""
    text = (
        "---\n"
        "# This is a YAML comment, not a heading\n"
        "description: Foo\n"
        "---\n"
        "\n"
        "# Real Title\n"
        "\n"
        "body text here\n"
    )
    assert fetch.extract_title(text) == "Real Title"


def test_extract_title_yaml_comment_with_setext_body_heading():
    """The post-frontmatter scoping must also cover the Setext fallback: when
    the frontmatter has no ``title:`` and the body's first heading is
    Setext-style (text underlined with ``===``), a ``#`` YAML comment inside
    the frontmatter must not shadow it. Pinning the Setext path separately
    guards against a future refactor that re-introduces the whole-document
    search for only one of the two heading styles."""
    text = (
        "---\n"
        "# commented-out-key: old value\n"
        "---\n"
        "\n"
        "Setext Title\n"
        "============\n"
        "\n"
        "body\n"
    )
    assert fetch.extract_title(text) == "Setext Title"


# --- UTF-8 BOM (byte-order mark) prefixed documents ---


def test_validate_markdown_accepts_bom_prefixed_heading_doc():
    """A document that starts with a UTF-8 BOM and relies on an ATX heading
    (no frontmatter) as its Markdown signal must validate: the BOM is stripped
    before matching, so it cannot wedge itself between the line-start anchor
    and the ``#``. Without the strip such pages were rejected as "not
    Markdown" and never mirrored at all."""
    body = "# Title\n\nsome text\n" * 5
    assert fetch.validate_markdown("\ufeff" + body)


def test_extract_title_bom_prefixed_heading():
    """The title of a BOM-prefixed document must still be extracted from its
    first heading -- validation and title extraction strip the BOM the same
    way, so a page that passes validation always yields its real title."""
    assert fetch.extract_title("\ufeff# Bom Title\n\nbody\n") == "Bom Title"


def test_extract_title_bom_prefixed_frontmatter():
    """A BOM-prefixed frontmatter block is likewise seen through the BOM: the
    frontmatter ``title:`` still wins over any body heading."""
    text = "\ufeff---\ntitle: Front Title\n---\n\n# Body Heading\n"
    assert fetch.extract_title(text) == "Front Title"


# --- adjacent horizontal rules are not a Setext heading -------------------------


def test_validate_markdown_rejects_adjacent_horizontal_rules():
    """A document consisting of adjacent horizontal rules (``---\\n---``) plus
    prose must NOT validate as Markdown: the Setext branch of the heading
    heuristic requires the would-be heading text to contain at least one
    character that is not ``=``, ``-`` or whitespace, so a rule underlined by
    another rule is not mistaken for a Setext heading. This keeps the
    validator consistent with its own docstring, which only promises to
    accept frontmatter or genuine headings."""
    text = "---\n---\n" + "plain prose without any heading structure. " * 3
    assert not fetch.validate_markdown(text)


# --- Setext headings: validation and title extraction agree ----------------------


def test_setext_document_validates_and_yields_title():
    """Both sides of the documented Setext pairing must hold: a document whose
    only heading is Setext-style (text underlined with ``===``) is accepted by
    ``validate_markdown`` AND its title is extracted by ``extract_title``.
    Pinning both together guards against a drift where one function learns a
    heading form the other does not -- such pages would validate but all be
    filed under the fallback title."""
    text = "My Setext Title\n================\n\n" + "body text\n" * 8
    assert fetch.validate_markdown(text)
    assert fetch.extract_title(text) == "My Setext Title"


# --- CRLF (carriage-return + line-feed) line endings -------------------------


def test_validate_markdown_accepts_crlf_frontmatter():
    """A document whose YAML frontmatter uses CRLF line endings must pass
    validation — the frontmatter regex (``_FRONTMATTER_BLOCK_RE``) uses
    ``\\r?\\n`` so it accepts both LF-only and CRLF line endings without
    requiring the caller to normalise the document first."""
    body = "body text here with enough bytes to clear the minimum length check"
    assert fetch.validate_markdown("---\r\ntitle: Hello\r\n---\r\n" + body)


def test_extract_title_from_crlf_setext_heading():
    """A Setext heading whose content line and underline both use CRLF endings
    must still yield its title — ``_SETEXT_HEADING_RE`` uses ``\\r?\\n`` for
    the underline boundary and ``\\r?$`` for the line end, matching the same
    CRLF tolerance the ATX and frontmatter patterns provide."""
    text = "My Setext Title\r\n================\r\n\r\n" + "body text\n" * 8
    assert fetch.extract_title(text) == "My Setext Title"


def test_extract_title_from_crlf_frontmatter():
    """A title inside a frontmatter block with CRLF line endings must be
    extracted correctly — ``_FRONTMATTER_TITLE_RE`` uses ``$`` which in
    MULTILINE mode matches before ``\\n``, so ``\\r`` is part of the
    captured group but is removed by the subsequent ``.strip()`` call."""
    text = "---\r\ntitle: Hello World\r\n---\r\n"
    assert fetch.extract_title(text) == "Hello World"


# --- headings inside fenced code blocks are not titles ----------------------------


@pytest.mark.parametrize("fence", ["```", "~~~"])
def test_extract_title_ignores_headings_inside_fenced_code(fence):
    """A ``# heading`` line inside a fenced code block (backtick or tilde
    fences) is a code sample, not the document title: fenced blocks are
    stripped before heading extraction, so the first heading OUTSIDE the
    fence wins. Both fence styles are pinned because CommonMark allows
    either, and the stripper's single alternation pattern keeps one branch
    per style so a closing fence always matches its opener's style."""
    text = f"{fence}\n# Not The Title\n{fence}\n\n# Real Title\n\nbody\n"
    assert fetch.extract_title(text) == "Real Title"


@pytest.mark.parametrize("fence", ["```", "~~~"])
def test_extract_title_only_fenced_heading_uses_fallback(fence):
    """When the ONLY heading-shaped line sits inside a fenced code block,
    there is no real heading at all and the caller-supplied fallback must be
    returned -- a code sample must never become the manifest title."""
    text = f"{fence}python\n# install: pip install x\n{fence}\n\nsome prose\n"
    assert fetch.extract_title(text, fallback="fb") == "fb"


# --- Retry-After header handling: upper-clamp, numeric passthrough, HTTP-date fallback ---


def test_retry_after_upper_clamp(monkeypatch):
    """A ``Retry-After`` value far above ``config.MAX_RETRY_DELAY`` must be
    clamped DOWN to the cap: without the upper clamp a hostile or buggy
    server could make a single page stall the whole run for hours. The
    existing negative-value test only covers the lower clamp (no negative
    sleeps); this one covers the upper bound by capturing the actual sleep
    durations."""
    sleeps: list[float] = []
    monkeypatch.setattr(fetch.time, "sleep", sleeps.append)

    fake = _FakeClient(
        [_Resp(429, "rate limited", retry_after="99999"), _Resp(200, "ok")]
    )
    assert fetch.get_with_retry(fake, "https://example.com/doc") == "ok"
    assert sleeps, "a 429 with Retry-After must cause at least one sleep"
    assert all(s <= config.MAX_RETRY_DELAY for s in sleeps), (
        f"Sleep above the cap detected: {sleeps}"
    )


def test_retry_after_numeric_value_is_honored(monkeypatch):
    """A positive numeric ``Retry-After`` within the clamp is waited
    verbatim: the server's explicit pacing instruction takes precedence over
    the computed exponential backoff delay."""
    sleeps: list[float] = []
    monkeypatch.setattr(fetch.time, "sleep", sleeps.append)

    fake = _FakeClient([_Resp(429, "rate limited", retry_after="2"), _Resp(200, "ok")])
    assert fetch.get_with_retry(fake, "https://example.com/doc") == "ok"
    assert sleeps == [2.0]


def test_retry_after_http_date_falls_back_to_backoff(monkeypatch):
    """A ``Retry-After`` header whose value is an HTTP-date string (e.g.
    ``"Wed, 21 Oct 2015 07:28:00 GMT"``) must NOT be parsed as a number —
    ``float()`` raises ``ValueError``, the exception is caught, and the
    standard exponential backoff delay is used instead. Without this fallback
    the ``ValueError`` would propagate uncaught and crash the run. The jitter
    factor is pinned to 1.0 (monkeypatched ``random.uniform``) so the
    fallback sleep is exactly ``config.RETRY_DELAY`` — the property under
    test is the fallback VALUE, not the random ±50 % spread."""
    sleeps: list[float] = []
    monkeypatch.setattr(fetch.time, "sleep", sleeps.append)
    monkeypatch.setattr(fetch.random, "uniform", lambda lo, hi: 1.0)

    fake = _FakeClient(
        [
            _Resp(429, "rate limited", retry_after="Wed, 21 Oct 2015 07:28:00 GMT"),
            _Resp(200, "ok"),
        ]
    )
    assert fetch.get_with_retry(fake, "https://example.com/doc") == "ok"
    # The standard backoff (config.RETRY_DELAY = 2.0) was used, not the
    # unparseable HTTP-date string.
    assert sleeps == [config.RETRY_DELAY]


# --- Retry jitter: every backoff sleep is the (doubled, capped) delay -------
# --- multiplied by a random factor in [0.5, 1.5] ----------------------------
#
# Rationale (thundering herd): several pages fetch concurrently, so when an
# overloaded upstream starts rate-limiting, every worker can receive a 429 in
# the same instant. Without jitter they would all retry in lockstep,
# re-hammering the server as one synchronized herd; the ±50 % random spread
# scatters the retries while keeping the mean wait unchanged. A numeric
# Retry-After header is the exception: the server dictated that wait
# explicitly, so it is honored verbatim (see the dedicated test below).


def test_retry_backoff_sleep_uses_jittered_delay(monkeypatch):
    """A 5xx backoff sleep must be the current delay times the random jitter
    factor, not the bare delay. Pinning ``random.uniform`` to a fixed 0.75
    makes the assertion exact: the pre-jitter code would have slept the full
    ``config.RETRY_DELAY`` (2.0) here and failed the comparison, so this test
    proves the sleep really goes through the jitter multiplication while the
    exponential delay stays the jitter base."""
    sleeps: list[float] = []
    monkeypatch.setattr(fetch.time, "sleep", sleeps.append)
    monkeypatch.setattr(fetch.random, "uniform", lambda lo, hi: 0.75)

    fake = _FakeClient([_Resp(500), _Resp(200, "ok")])
    assert fetch.get_with_retry(fake, "https://example.com/doc") == "ok"
    assert sleeps == [config.RETRY_DELAY * 0.75]


def test_retry_backoff_jitter_preserves_exponential_doubling(monkeypatch):
    """Jitter must randomize each sleep WITHOUT distorting the underlying
    exponential schedule: across consecutive failed attempts the base delays
    still double (``RETRY_DELAY``, then ``RETRY_DELAY * 2``), and each actual
    sleep is that attempt's base times its own jitter draw. Pinning the two
    draws to DIFFERENT factors (1.5, then 0.5) also proves the jitter is
    drawn per attempt rather than computed once per page. The third attempt
    succeeds (500, 500, 200), so exactly the two retry sleeps occur."""
    sleeps: list[float] = []
    monkeypatch.setattr(fetch.time, "sleep", sleeps.append)
    factors = iter([1.5, 0.5])
    monkeypatch.setattr(fetch.random, "uniform", lambda lo, hi: next(factors))

    fake = _FakeClient([_Resp(500), _Resp(500), _Resp(200, "ok")])
    assert fetch.get_with_retry(fake, "https://example.com/doc") == "ok"
    assert sleeps == [config.RETRY_DELAY * 1.5, config.RETRY_DELAY * 2 * 0.5]
    assert fake.calls == config.MAX_RETRIES


def test_retry_backoff_sleeps_stay_within_jitter_window(monkeypatch):
    """Every backoff sleep must land inside the documented ±50 % window of its
    (doubled) base delay — here 2.0 then 4.0 for two consecutive 500s. The
    REAL ``random.uniform`` is used on purpose: the assertions can never flake
    because the function's own contract bounds every draw to [0.5, 1.5], so
    each recorded sleep must equal base × draw and therefore lie in
    [base × 0.5, base × 1.5]. This complements the monkeypatched exact-value
    tests above: it verifies the sleep-to-base proportionality end to end with
    the real random source (catching e.g. a stray second doubling or a wrong
    base variable), while the exact pins catch the un-jittered case."""
    sleeps: list[float] = []
    monkeypatch.setattr(fetch.time, "sleep", sleeps.append)

    fake = _FakeClient([_Resp(500)] * config.MAX_RETRIES)
    with pytest.raises(fetch.FetchError):
        fetch.get_with_retry(fake, "https://example.com/doc")
    assert len(sleeps) == config.MAX_RETRIES - 1
    for attempt, sleep in enumerate(sleeps, start=1):
        base = config.RETRY_DELAY * 2 ** (attempt - 1)
        assert base * 0.5 <= sleep <= base * 1.5


def test_retry_transport_error_sleep_is_jittered(monkeypatch):
    """The transport-error retry path (no HTTP response at all) sleeps through
    the same jittered backoff as the 429/5xx path: a connection failure hits
    every concurrent worker at once just as easily as a rate limit does, so
    those retries must be spread too. Pinning the factor to 1.25 makes the
    assertion exact for this second, independent sleep site."""
    sleeps: list[float] = []
    monkeypatch.setattr(fetch.time, "sleep", sleeps.append)
    monkeypatch.setattr(fetch.random, "uniform", lambda lo, hi: 1.25)

    fake = _FakeClient([httpx.ConnectError("boom"), _Resp(200, "ok")])
    assert fetch.get_with_retry(fake, "https://example.com/doc") == "ok"
    assert sleeps == [config.RETRY_DELAY * 1.25]


def test_retry_after_wait_is_honored_verbatim_despite_jitter(monkeypatch):
    """A numeric ``Retry-After`` header is the upstream's explicit pacing
    instruction and must NOT be jittered: even with the jitter factor pinned
    to its worst case of 1.5 (which would stretch a 2 s wait to 3 s), the
    recorded sleep stays exactly 2.0. Jitter exists to de-synchronize OUR
    retries from each other, not to second-guess a server that told us
    precisely when to come back."""
    sleeps: list[float] = []
    monkeypatch.setattr(fetch.time, "sleep", sleeps.append)
    monkeypatch.setattr(fetch.random, "uniform", lambda lo, hi: 1.5)

    fake = _FakeClient([_Resp(429, "rate limited", retry_after="2"), _Resp(200, "ok")])
    assert fetch.get_with_retry(fake, "https://example.com/doc") == "ok"
    assert sleeps == [2.0]


# --- Decode-failure classification: deterministic (UnicodeDecodeError) fails ---
# --- fast, transient (httpx.DecodingError) is retried; invalid URL fails fast ---


def test_invalid_url_fails_fast_without_retries():
    """``httpx.InvalidURL`` means the URL itself is malformed, so every
    attempt would fail identically: it is converted to FetchError on the
    FIRST attempt instead of burning the whole retry budget. (It is not an
    ``httpx.HTTPError`` subclass, so it needs -- and has -- its own except
    clause; this test would hang through all retries if that clause ever
    caught the wrong type.)"""
    fake = _FakeClient([httpx.InvalidURL("bad URL scheme")])
    with pytest.raises(fetch.FetchError, match="Invalid URL"):
        fetch.get_with_retry(fake, "not-a-url")
    assert fake.calls == 1


class _UndecodableResp:
    """Response stub whose body cannot be decoded into text.

    Simulates two real-world failure modes of ``get_with_retry``'s
    streaming path, which take DIFFERENT retry paths by design:

      * ``UnicodeDecodeError`` -- the wire bytes are fine but do not decode
        as the response's declared charset (binary content served with a
        text Content-Type, or a mislabelled charset). The stub yields bytes
        that are invalid UTF-8, so the failure happens at the final
        ``body_bytes.decode(...)`` call in the code under test, exactly as
        it would against a live server. This failure is deterministic -- the
        same bytes arrive on every attempt -- so it must NOT be retried.
      * ``httpx.DecodingError`` -- the Content-Encoding (gzip/deflate/br)
        stream itself is corrupt (e.g. a connection truncated mid-body).
        Real httpx surfaces this from ``iter_bytes()`` while the body is
        being consumed, so the stub raises from ``iter_bytes()`` directly.
        This failure is transient (a fresh attempt usually receives a clean
        stream), and because ``httpx.DecodingError`` is an
        ``httpx.RequestError`` subclass it must be retried like any other
        transport error.
    """

    status_code = 200
    encoding = "utf-8"

    def __init__(self, error):
        """Store the error that decoding the body should fail with.

        Args:
            error: An exception instance (``UnicodeDecodeError`` or
                ``httpx.DecodingError``) selecting which of the two failure
                modes described above the stub simulates.
        """
        self._error = error
        self.headers: dict[str, str] = {}

    def iter_bytes(self):
        """Yield undecodable bytes, or raise, depending on the stored error.

        For ``UnicodeDecodeError`` a single chunk of invalid UTF-8 is
        yielded so the final ``.decode()`` in ``get_with_retry`` raises it
        naturally. For ``httpx.DecodingError`` the error is raised from
        this generator itself, matching how httpx reports a broken
        compressed stream mid-download.
        """
        if isinstance(self._error, (UnicodeDecodeError, LookupError)):
            yield b"\xff"
        else:
            raise self._error


def test_unicode_decode_error_fails_fast_without_retries():
    """A body that does not decode as its declared charset is unusable and
    the failure is DETERMINISTIC -- the same bytes would arrive on every
    attempt -- so the decode error is converted to FetchError immediately
    (no retries), letting the orchestrator record a per-page failure instead
    of burning the retry budget on a page that can never succeed."""
    error = UnicodeDecodeError("utf-8", b"\xff", 0, 1, "invalid start byte")
    fake = _FakeClient([_UndecodableResp(error), _Resp(200, "ok")])
    with pytest.raises(fetch.FetchError, match="Could not decode"):
        fetch.get_with_retry(fake, "https://example.com/doc")
    assert fake.calls == 1


def test_get_with_retry_handles_unknown_charset_encoding_lookup_error():
    """A body with an unknown charset encoding raises LookupError which is
    DETERMINISTIC, so the error must be converted to FetchError immediately
    without retries, exactly like UnicodeDecodeError."""
    error = LookupError("unknown encoding: bogus")
    resp = _UndecodableResp(error)
    resp.encoding = "bogus"
    fake = _FakeClient([resp, _Resp(200, "ok")])
    with pytest.raises(fetch.FetchError, match="Could not decode"):
        fetch.get_with_retry(fake, "https://example.com/doc")
    assert fake.calls == 1


# --- Charset handling: valid UTF-8 is decoded as UTF-8 first, and the -------
# --- declared charset is only a fallback for genuinely non-UTF-8 bodies -----


@pytest.mark.parametrize("declared", ["iso-8859-1", "windows-1252"])
def test_declared_legacy_charset_over_utf8_bytes_decodes_as_utf8(declared):
    """A text/* response that DECLARES a legacy charset (iso-8859-1,
    windows-1252, ...) while its body is actually UTF-8 gets that charset
    assigned to ``resp.encoding`` by httpx. iso-8859-1 decodes EVERY byte
    sequence without error, so decoding such a body strictly with its
    declared encoding would silently turn valid multibyte UTF-8 (accents,
    em-dashes, CJK, emoji) into mojibake. The UTF-8-first decode must
    therefore win and return the exact original text even when
    ``resp.encoding`` claims a legacy charset."""
    body = "Café — já foi: 中文测试, 🚀"
    resp = _Resp(200, body)
    resp.encoding = declared  # what httpx assigns for a declared legacy charset
    fake = _FakeClient([resp])
    assert fetch.get_with_retry(fake, "https://example.com/doc") == body
    assert fake.calls == 1


class _Latin1Resp(_Resp):
    """``_Resp`` variant whose body is genuinely latin-1, not UTF-8.

    ``_Resp.iter_bytes`` always encodes the fixture text as UTF-8, which is
    right for every other test but useless for exercising the fallback
    path: a UTF-8-encoded body would simply succeed on the UTF-8-first
    attempt. This subclass encodes the text as iso-8859-1 instead, so the
    first decode attempt raises ``UnicodeDecodeError`` and the declared
    charset has real work to do.
    """

    def iter_bytes(self):
        """Yield the body as one latin-1 encoded chunk (see the class
        docstring for why this overrides the UTF-8 base behaviour)."""
        yield self.text.encode("iso-8859-1")


def test_utf8_decode_failure_falls_back_to_declared_charset():
    """When the body is genuinely NOT UTF-8 -- here: latin-1 text served
    with a matching iso-8859-1 charset -- the UTF-8-first attempt raises
    UnicodeDecodeError and the response's declared charset is used as the
    fallback, returning the exact text. (The fixture text uses only
    characters representable in latin-1; characters outside it, e.g. an
    em-dash, would not survive the stub's latin-1 encode step.)"""
    body = "café, olá, São Paulo, ação"
    resp = _Latin1Resp(200, body)
    resp.encoding = "iso-8859-1"
    fake = _FakeClient([resp])
    assert fetch.get_with_retry(fake, "https://example.com/doc") == body
    assert fake.calls == 1


def test_decoding_error_is_retried_then_succeeds():
    """A corrupt compressed stream (``httpx.DecodingError``, e.g. a
    connection truncated mid-gzip) is a TRANSIENT transport failure: it is
    an ``httpx.RequestError`` subclass raised from ``iter_bytes()`` while
    the body streams, so it must take the same retry path as a DNS or
    connect error. Here the first attempt's stream is broken and the second
    succeeds, proving the retry loop (not fail-fast conversion) handles it."""
    error = httpx.DecodingError(
        "broken gzip", request=httpx.Request("GET", "https://x")
    )
    fake = _FakeClient([_UndecodableResp(error), _Resp(200, "ok")])
    assert fetch.get_with_retry(fake, "https://example.com/doc") == "ok"
    assert fake.calls == 2


def test_decoding_error_exhausts_retries_then_raises():
    """When EVERY attempt's stream fails with ``httpx.DecodingError``, all
    ``config.MAX_RETRIES`` attempts must be consumed before FetchError is
    raised -- exactly like any other persistent transport failure -- and the
    final error carries ``status_code is None`` because no HTTP status ever
    caused the failure."""
    error = httpx.DecodingError(
        "broken gzip", request=httpx.Request("GET", "https://x")
    )
    fake = _FakeClient([_UndecodableResp(error)] * config.MAX_RETRIES)
    with pytest.raises(fetch.FetchError, match="Failed after") as exc_info:
        fetch.get_with_retry(fake, "https://example.com/doc")
    assert exc_info.value.status_code is None
    assert fake.calls == config.MAX_RETRIES


# --- Response body size limit (MAX_RESPONSE_BYTES): Content-Length, streaming, and byte-level enforcement ---


def test_body_size_limit_rejects_oversized_content_length():
    """A response whose Content-Length header exceeds MAX_RESPONSE_BYTES must
    be rejected BEFORE the body is read into memory. This is the front-line
    defence: a single oversized page must not OOM the whole mirror run. The
    raised FetchError must carry ``status_code is None``: the HTTP exchange
    itself succeeded (2xx), so the failure is our LOCAL size guard, and the
    FetchError.status_code contract reserves the attribute for the HTTP
    status that caused the failure -- a local guard must not masquerade as
    an upstream HTTP 200 to consumers that branch on the status."""
    oversized = config.MAX_RESPONSE_BYTES + 1
    resp = _Resp(200, "ok")
    resp.headers["Content-Length"] = str(oversized)
    fake = _FakeClient([resp])
    with pytest.raises(fetch.FetchError, match="Response body too large") as exc_info:
        fetch.get_with_retry(fake, "https://example.com/large")
    assert exc_info.value.status_code is None
    assert fake.calls == 1


def test_body_size_limit_accepts_content_length_within_bounds():
    """A response whose Content-Length is within MAX_RESPONSE_BYTES must be
    accepted and returned normally. Even with a valid, in-bounds header the
    body is read through the streaming path (there is no ``resp.text`` fast
    path -- the header measures compressed wire bytes, not the decompressed
    body), so this test also proves the streaming path handles the common
    case of an ordinary, honestly-sized page."""
    body = "# Valid\n\n" + "x" * (config.MAX_RESPONSE_BYTES // 10)
    resp = _Resp(200, body)
    resp.headers["Content-Length"] = str(len(body))
    fake = _FakeClient([resp])
    result = fetch.get_with_retry(fake, "https://example.com/doc")
    assert result == body


def test_body_size_limit_enforced_by_bytes_not_characters():
    """A response whose character length len(body) is smaller than MAX_RESPONSE_BYTES
    but whose UTF-8 byte length len(body.encode('utf-8')) exceeds MAX_RESPONSE_BYTES
    must be correctly rejected. This proves strict byte-level enforcement.
    Like every body-size guard, the raised FetchError carries
    ``status_code is None`` (local validation failure, not an upstream
    status)."""
    # Each '🔥' character is 1 char long but 4 bytes when encoded in UTF-8.
    # We create a body that is well under MAX_RESPONSE_BYTES in characters,
    # but strictly larger in bytes.
    char_count = (config.MAX_RESPONSE_BYTES // 4) + 100
    body = "🔥" * char_count

    # Verify our preconditions for the test:
    assert len(body) <= config.MAX_RESPONSE_BYTES
    assert len(body.encode("utf-8")) > config.MAX_RESPONSE_BYTES

    resp = _Resp(200, body)
    fake = _FakeClient([resp])
    with pytest.raises(fetch.FetchError, match="Response body too large") as exc_info:
        fetch.get_with_retry(fake, "https://example.com/large-multibyte")
    assert exc_info.value.status_code is None
    assert fake.calls == 1


def test_body_size_limit_malformed_content_length_uses_streaming():
    """A Content-Length header with a non-integer value (e.g. a buggy upstream
    returning a string) must NOT crash the fetch. The ValueError from
    ``int()`` is caught and the code falls through to the streaming path,
    which measures the actual body size."""
    resp = _Resp(200, "ok body here")
    resp.headers["Content-Length"] = "not-a-number"
    fake = _FakeClient([resp])
    # The body is small, so it should succeed via the streaming fallback.
    result = fetch.get_with_retry(fake, "https://example.com/doc")
    assert result == "ok body here"
    assert fake.calls == 1


# --- Decompression bomb: compressed Content-Length vs decompressed body size ---
#
# httpx transparently decompresses gzip/deflate/br response bodies, so the
# Content-Length header of a compressed response reports the small WIRE size
# while the body the caller receives is the much larger DECOMPRESSED text.
# ``get_with_retry`` must therefore never size-check (or worse, fully read)
# the body based on Content-Length alone: the only meaningful guard is the
# streaming path's running count of decompressed bytes. The stub and tests
# below pin that behaviour.


class _GzipBombResp(_Resp):
    """Response stub modelling a compressed response, bomb or not.

    The headers declare a Content-Encoding of ``gzip`` and a Content-Length
    equal to the COMPRESSED size (what a real server sends -- Content-Length
    always measures wire bytes), while ``iter_bytes()`` yields the
    DECOMPRESSED body, matching httpx's transparent decompression.

    The ``text`` property raises ``AssertionError`` if it is ever read:
    ``get_with_retry`` must not touch ``resp.text`` on any code path,
    because ``resp.text`` materialises the entire decompressed body in
    memory before any size guard can fire -- a small compressed payload
    would expand to its full (possibly hundreds-of-MiB) size with the limit
    never enforced. A test using this stub therefore fails loudly if a
    ``resp.text`` fast path is ever reintroduced.
    """

    def __init__(self, status: int, body: str, *, compressed_length: int):
        """Create a gzip-encoded response stub.

        Args:
            status: HTTP status code forwarded to ``_Resp.__init__``.
            body: The DECOMPRESSED body text that ``iter_bytes()`` yields.
            compressed_length: The value reported via the Content-Length
                header, i.e. the size of the gzip payload on the wire.
        """
        self._body = body
        super().__init__(status, "")
        self.headers["Content-Length"] = str(compressed_length)
        self.headers["Content-Encoding"] = "gzip"

    @property
    def text(self):
        raise AssertionError(
            "get_with_retry must not read resp.text: it materialises the "
            "entire decompressed body in memory before the size guard can "
            "fire, defeating MAX_RESPONSE_BYTES for compressed responses"
        )

    @text.setter
    def text(self, value):
        # Swallow the initialising assignment from ``_Resp.__init__`` (which
        # sets ``self.text`` unconditionally); the real body travels through
        # ``iter_bytes()`` only. Only READS of ``.text`` are forbidden.
        pass

    def iter_bytes(self):
        """Yield the decompressed body as a single chunk.

        Real httpx applies the gzip decoder while streaming, so
        ``iter_bytes()`` yields decompressed bytes; a single chunk is
        sufficient here because the per-chunk guard must fire within one
        chunk of crossing the limit (the multi-chunk timing is covered by
        ``_MultiChunkStreamingResp`` below).
        """
        yield self._body.encode("utf-8")


def test_gzip_bomb_rejected_despite_small_content_length():
    """A response whose COMPRESSED Content-Length is within
    MAX_RESPONSE_BYTES but whose DECOMPRESSED body exceeds it must be
    rejected. This is the decompression-bomb regression: if the body were
    read via ``resp.text`` based on the in-bounds header, a tiny gzip
    payload would expand to an oversized in-memory string with the guard
    firing only after the damage (or the stub's ``AssertionError`` here).
    The raised FetchError carries ``status_code is None``: the HTTP
    exchange succeeded, so the failure is our LOCAL size guard, not an
    upstream status."""
    body = "x" * (config.MAX_RESPONSE_BYTES + 1)
    compressed = gzip.compress(body.encode("utf-8"))
    # Sanity-check the bomb premise: the wire payload really is far under
    # the limit while the decompressed body is over it.
    assert len(compressed) < config.MAX_RESPONSE_BYTES
    resp = _GzipBombResp(200, body, compressed_length=len(compressed))
    fake = _FakeClient([resp])
    with pytest.raises(fetch.FetchError, match="Response body too large") as exc_info:
        fetch.get_with_retry(fake, "https://example.com/bomb")
    assert exc_info.value.status_code is None
    assert fake.calls == 1


def test_gzip_response_within_limit_accepted_via_streaming():
    """A compressed response whose decompressed body is within
    MAX_RESPONSE_BYTES must be accepted and returned normally. Paired with
    the bomb test above, this proves the streaming path is used for ALL
    responses with a Content-Length header (the stub's ``text`` property
    raises on any access) and that legitimate gzip traffic still decodes
    correctly end to end."""
    body = "# Title\n\nsome content here\n" * 5
    compressed = gzip.compress(body.encode("utf-8"))
    resp = _GzipBombResp(200, body, compressed_length=len(compressed))
    fake = _FakeClient([resp])
    result = fetch.get_with_retry(fake, "https://example.com/doc")
    assert result == body
    assert fake.calls == 1


# --- Network timeout handling: TimeoutException triggers retry, exhausts to FetchError with None status ---


def test_timeout_exception_triggers_retry():
    """An ``httpx.TimeoutException`` is a transient transport error (the
    upstream did not answer in time) and must trigger a retry, not fail
    immediately. The exception is a subclass of ``httpx.RequestError``,
    so it is caught by the generic transport-error handler and follows
    the same backoff-and-retry policy as connection errors."""
    c = _FakeClient(
        [
            httpx.TimeoutException("read timed out"),
            _Resp(200, "# Title\n\nbody text here with enough bytes\n" * 5),
        ]
    )
    result = fetch.get_with_retry(c, "https://x")
    assert "Title" in result
    assert c.calls == 2


def test_timeout_exception_exhausts_retries():
    """When every attempt times out, ``get_with_retry`` must raise
    ``FetchError`` after exhausting ``config.MAX_RETRIES`` attempts, with
    ``status_code is None`` (a timeout never produces an HTTP response). The
    call count is asserted explicitly: every retry slot must be used even
    though each attempt timed out before producing a response."""
    c = _FakeClient([httpx.TimeoutException("read timed out")] * 3)
    with pytest.raises(fetch.FetchError) as exc_info:
        fetch.get_with_retry(c, "https://x")
    assert exc_info.value.status_code is None
    assert c.calls == 3


def test_streaming_body_size_enforcement_rejects_oversized():
    """The streaming path (triggered when Content-Length is absent) must reject
    a response whose accumulated bytes exceed MAX_RESPONSE_BYTES. The
    rejection must happen before the loop finishes -- i.e., the guard fires
    mid-stream -- so the full body is never fully accumulated and decoded.
    The raised FetchError carries ``status_code is None`` (local guard, not
    an upstream status)."""
    oversized_body = "x" * (config.MAX_RESPONSE_BYTES + 1)
    resp = _Resp(200, oversized_body)
    fake = _FakeClient([resp])
    with pytest.raises(fetch.FetchError, match="Response body too large") as exc_info:
        fetch.get_with_retry(fake, "https://example.com/large-stream")
    assert exc_info.value.status_code is None
    assert fake.calls == 1


def test_streaming_body_size_enforcement_accepts_small():
    """The streaming path must accept and decode a response whose body is
    within MAX_RESPONSE_BYTES when no Content-Length header is present."""
    body = "# Title\n\nsome content here\n" * 5
    resp = _Resp(200, body)
    fake = _FakeClient([resp])
    result = fetch.get_with_retry(fake, "https://example.com/doc")
    assert result == body
    assert fake.calls == 1


# --- Multi-chunk streaming --------------------------------------------------
# The base _Resp.iter_bytes() yields the full body as ONE chunk, which
# exercises the per-chunk check but NOT the case where the limit is breached
# on a later chunk (the guard fires at the end of the first and only chunk
# when that single chunk is already oversized). A streaming response in real
# httpx yields several chunks (typically a few KiB each), and the guard must
# fire on whichever chunk pushes the total over the limit. The
# _MultiChunkStreamingResp stub below lets us test that scenario specifically,
# because its iter_bytes() splits the body into fixed-size pieces and yields
# them one at a time, allowing the cumulative byte counter to grow across
# multiple iterations before crossing the threshold.


class _MultiChunkStreamingResp(_Resp):
    """Extension of ``_Resp`` whose ``iter_bytes()`` yields data in smaller
    chunks across multiple iterations.

    The base ``_Resp.iter_bytes()`` yields the full body as a single bytes chunk,
    which exercises the per-chunk size-check logic but cannot test the case
    where ``MAX_RESPONSE_BYTES`` is breached on the THIRD or later chunk
    (the guard fires at the end of the very first chunk, which is already
    oversized). This stub splits the body into fixed-size chunks, so a test
    can verify that the cumulative byte-count tracking works correctly
    across multiple iterations of the streaming loop.

    For example, with ``chunk_size=1024`` and a body 3.5 KB long, the first
    chunk is under the limit (1 KB), the second chunk is still under (2 KB),
    and a 10 MB limit would only be breached on chunk ~10,240 -- testing
    the exact guard condition that a single-chunk yield cannot reach.
    """

    encoding = "utf-8"

    def __init__(
        self,
        status: int,
        text: str = "ok",
        *,
        retry_after: str | None = None,
        chunk_size: int = 1024,
    ):
        """Create a streaming response that yields *text* in *chunk_size* pieces.

        Args:
            status: HTTP status code forwarded to ``_Resp.__init__``.
            text: The full response body, split into chunks by
                ``iter_bytes()``.
            retry_after: Optional ``Retry-After`` header value (forwarded
                to ``_Resp.__init__``).
            chunk_size: Number of bytes per chunk yielded by
                ``iter_bytes()``.  The last chunk may be shorter if the
                body length is not a multiple of *chunk_size*.
        """
        super().__init__(status, text, retry_after=retry_after)
        self._chunk_size = chunk_size

    def iter_bytes(self):
        """Yield the response body in fixed-size chunks.

        Each chunk is exactly ``_chunk_size`` bytes except possibly the last
        one, which carries the remainder. The cumulative sum of all chunk
        lengths equals ``len(self.text.encode("utf-8"))`` -- the same total
        the base ``_Resp.iter_bytes()`` yields as a single chunk.

        Yields:
            ``bytes`` chunks of at most ``_chunk_size`` bytes, in sequence,
            until the full body has been yielded.
        """
        data = self.text.encode("utf-8")
        for i in range(0, len(data), self._chunk_size):
            yield data[i : i + self._chunk_size]


def test_multi_chunk_streaming_accepts_body_within_limit():
    """The streaming path with multiple chunks must accumulate byte counts
    correctly and accept a response whose total body is within
    ``MAX_RESPONSE_BYTES`` when no ``Content-Length`` header is present.
    This exercises the per-chunk cumulative tracking for the common case
    (body within bounds) that the base ``_Resp.iter_bytes()`` (which yields
    the entire body as a single chunk) already covers; it guards against
    off-by-one or accumulator-reset bugs in the chunk-tracking logic that a
    single-chunk yield would mask because the accumulator never crosses an
    intermediate boundary."""
    body = "# Title\n\nsome content here\n" * 50
    resp = _MultiChunkStreamingResp(200, body, chunk_size=64)
    fake = _FakeClient([resp])
    result = fetch.get_with_retry(fake, "https://example.com/doc")
    assert result == body
    assert fake.calls == 1


def test_multi_chunk_streaming_rejects_body_exceeding_limit_on_later_chunk():
    """The streaming path must reject a response whose cumulative byte count
    exceeds ``MAX_RESPONSE_BYTES`` on a LATER chunk, not just on the first
    one. With small chunks and a body just over the limit, the first several
    chunks are accepted, the cumulative counter grows with each, and the
    guard fires on the chunk that crosses the threshold.

    This is the scenario the base ``_Resp.iter_bytes()`` (which yields the
    full body as a single chunk) could NOT test: its one-and-only chunk is
    already oversized when the size limit is exceeded, so the guard fires
    on iteration 1, before any partial accumulation can be observed. With
    the multi-chunk stub the first several chunks are well under the limit
    individually, and only the accumulated total across chunks triggers the
    rejection -- exactly the condition a real multi-gigabyte streaming
    response without ``Content-Length`` would produce."""
    chunk_size = 1000
    # Build a body that is MAX_RESPONSE_BYTES + 1 byte -- exactly one past
    # the limit. With 1000-byte chunks the first ~10,485 chunks are under
    # the limit; the guard fires on the chunk that pushes the total over.
    body = "x" * (config.MAX_RESPONSE_BYTES + 1)
    resp = _MultiChunkStreamingResp(200, body, chunk_size=chunk_size)
    fake = _FakeClient([resp])
    with pytest.raises(fetch.FetchError, match="Response body too large") as exc_info:
        fetch.get_with_retry(fake, "https://example.com/large-stream-chunked")
    # The mid-stream guard is a local validation failure: status_code must
    # be None, not the 200 the upstream actually returned.
    assert exc_info.value.status_code is None
    assert fake.calls == 1


# --- Regex backtracking regression: pathological single-line bodies ---------
#
# The Setext branches of ``_HEADING_MARKER_RE`` and ``_SETEXT_HEADING_RE``
# match raw network input (``MAX_RESPONSE_BYTES`` allows multi-MiB bodies).
# Their naive ``[^\n]*[^-=\s][^\n]*`` sandwich of two overlapping greedy
# quantifiers was O(n^2) in line length: a single 200 KB line with no
# newline took ~18 s to reject, and a multi-MiB body was an effective hang.
# The atomic-group rewrite (see the comments on both regexes in
# ``core.fetch``) scans each line once. The tests below do NOT assert
# timing -- they simply feed the pathological input and assert the correct
# result, so a regression to the quadratic form would fail the suite by
# timeout/extreme slowness rather than by a wrong assertion.


def test_validate_markdown_pathological_single_line_body_is_fast():
    """A 200,000-character single-line body (no newline, no heading) must be
    rejected as "not Markdown" without triggering catastrophic backtracking
    in the Setext branch of the heading heuristic. With the old quadratic
    pattern this input took ~18 s on its own; with the atomic-group form it
    is one linear scan."""
    body = "a" * 200_000
    assert not fetch.validate_markdown(body)


def test_extract_title_pathological_single_line_body_is_fast():
    """The same pathological single-line body must yield the caller-supplied
    fallback title without hanging ``_SETEXT_HEADING_RE``: the Setext
    fallback search shares the same quantifier-sandwich hazard as the
    validator, so it is pinned separately."""
    body = "a" * 200_000
    assert fetch.extract_title(body, fallback="fb") == "fb"


# --- Indented ATX headings (1-3 leading spaces, per CommonMark) -------------


def test_extract_title_indented_atx_heading():
    """An ATX heading indented by 1-3 spaces is still a heading per
    CommonMark, so it must yield its title. ``_HEADING_MARKER_RE`` already
    tolerates leading whitespace, which means such a page VALIDATES as
    Markdown -- without the matching tolerance in ``_ATX_HEADING_RE`` it
    would then be filed under the fallback title even though its heading is
    right there."""
    assert fetch.extract_title("  # Indented Title\n\nbody\n") == "Indented Title"


def test_extract_title_keeps_trailing_hash_that_is_part_of_title():
    """A heading whose title legitimately ends with ``#`` (e.g. ``# C#``)
    must keep it: the closing-ATX-hash cleanup only strips a trailing hash
    run that is separated from the title by whitespace (``# Title #``), never
    a hash that is part of the title itself."""
    assert fetch.extract_title("# C#\n") == "C#"
    assert fetch.extract_title("# Title #\n") == "Title"
    assert fetch.extract_title("# Title ##\n") == "Title"


def test_extract_title_four_space_indented_hashes_not_a_heading():
    """Four or more leading spaces make the line an indented CODE block per
    CommonMark, not an ATX heading -- so the fallback must be returned. The
    ``{0,3}`` bound (rather than ``\\s*``) is both CommonMark-correct and
    backtracking-free; this pins the upper edge of the bound."""
    text = "    # not a heading\n\nsome prose without headings\n"
    assert fetch.extract_title(text, fallback="fb") == "fb"


# --- make_client: shared HTTP client configuration ---------------------------


def test_make_client_configuration():
    """``make_client()`` must build the shared client with the project's
    standard settings: the identifying ``User-Agent`` (so upstream operators
    can tell the mirror from anonymous scraping), the Markdown-preferring
    ``Accept`` header (several docs platforms content-negotiate on it), the
    configured ``config.TIMEOUT``, and ``follow_redirects=True`` (upstreams
    routinely move pages with 301/302). No request is made -- the client is
    constructed and its configuration asserted directly."""
    client = fetch.make_client()
    assert client.headers["User-Agent"] == config.USER_AGENT
    assert client.headers["Accept"] == "text/markdown, text/plain, */*"
    assert client.timeout == config.TIMEOUT
    assert client.follow_redirects is True


# --- RateLimiter: thread-safe inter-request pacing -----------------------------


def test_rate_limiter_first_request_immediate(monkeypatch):
    """The very first dispatch through RateLimiter must not incur any sleep."""
    sleeps: list[float] = []
    monkeypatch.setattr(fetch.time, "sleep", sleeps.append)
    limiter = fetch.RateLimiter(delay=1.0)
    limiter.wait()
    assert sleeps == []


def test_rate_limiter_enforces_spacing(monkeypatch):
    """Consecutive dispatches must be spaced by at least the configured delay."""
    sleeps: list[float] = []
    monkeypatch.setattr(fetch.time, "sleep", sleeps.append)
    limiter = fetch.RateLimiter(delay=0.35)
    limiter.wait()
    limiter.wait()
    assert len(sleeps) == 1
    assert sleeps[0] == pytest.approx(0.35, rel=1e-2)


def test_rate_limiter_zero_or_negative_delay(monkeypatch):
    """When delay is zero or negative, rate limiting is a no-op."""
    sleeps: list[float] = []
    monkeypatch.setattr(fetch.time, "sleep", sleeps.append)
    limiter_zero = fetch.RateLimiter(delay=0.0)
    limiter_neg = fetch.RateLimiter(delay=-1.0)
    limiter_zero.wait()
    limiter_neg.wait()
    assert sleeps == []


def test_rate_limiter_acquire_alias(monkeypatch):
    """acquire() is a direct alias for wait()."""
    sleeps: list[float] = []
    monkeypatch.setattr(fetch.time, "sleep", sleeps.append)
    limiter = fetch.RateLimiter(delay=0.01)
    limiter.acquire()
    assert sleeps == []


def test_rate_limiter_context_manager(monkeypatch):
    """RateLimiter supports context manager syntax entering via wait()."""
    sleeps: list[float] = []
    monkeypatch.setattr(fetch.time, "sleep", sleeps.append)
    limiter = fetch.RateLimiter(delay=0.01)
    with limiter as active:
        assert active is limiter
    assert sleeps == []


def test_rate_limiter_concurrent_threads(monkeypatch):
    """RateLimiter paces concurrent threads so that request dispatches schedule sleeps."""
    from concurrent.futures import ThreadPoolExecutor

    sleeps: list[float] = []
    lock = threading.Lock()

    def record_sleep(dur: float) -> None:
        with lock:
            sleeps.append(dur)

    monkeypatch.setattr(fetch.time, "sleep", record_sleep)
    limiter = fetch.RateLimiter(delay=0.35)

    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(lambda _: limiter.wait(), range(4)))

    # For 4 dispatches, 3 of them must have scheduled sleeps
    assert len(sleeps) == 3
    assert all(s > 0 for s in sleeps)


# --- fetch_binary: raw-bytes GET with the same retry policy ------------------


def test_fetch_binary_returns_raw_bytes():
    """``fetch_binary`` returns the response body as unmodified bytes.

    The media stage downloads image assets with it; the payload must reach
    the caller byte-for-byte with none of the text-path post-processing."""
    fake = _FakeClient([_Resp(200, "ok")])
    assert fetch.fetch_binary(fake, "https://example.com/a.png") == b"ok"
    assert fake.calls == 1


def test_fetch_binary_does_not_decode_the_body():
    """A body that is not valid UTF-8 succeeds on the binary path.

    The text path converts such bytes into a deterministic (non-retried)
    FetchError; for an image the bytes ARE the product, so the binary path
    must hand them over verbatim -- decode-hardening would be a bug here."""
    fake = _FakeClient(
        [_UndecodableResp(UnicodeDecodeError("utf-8", b"\xff", 0, 1, "x"))]
    )
    assert fetch.fetch_binary(fake, "https://example.com/a.png") == b"\xff"
    assert fake.calls == 1


def test_fetch_binary_retries_transient_server_errors():
    """5xx responses are transient: the fetch retries and then succeeds."""
    fake = _FakeClient([_Resp(500), _Resp(200, "img")])
    assert fetch.fetch_binary(fake, "https://example.com/x.png") == b"img"
    assert fake.calls == 2


def test_fetch_binary_retries_transport_errors():
    """Transport-level failures (httpx.RequestError) retry like the text path."""
    fake = _FakeClient([httpx.ConnectError("boom"), _Resp(200, "img")])
    assert fetch.fetch_binary(fake, "https://example.com/x.png") == b"img"
    assert fake.calls == 2


def test_fetch_binary_fails_fast_on_4xx():
    """Non-transient 4xx raises immediately with the status code attached."""
    fake = _FakeClient([_Resp(404)])
    with pytest.raises(fetch.FetchError, match="404") as exc_info:
        fetch.fetch_binary(fake, "https://example.com/gone.png")
    assert exc_info.value.status_code == 404
    assert fake.calls == 1


def test_fetch_binary_rejects_oversized_content_length():
    """An already-oversized Content-Length header rejects the response early.

    The rejection is a local size guard, so status_code must stay None (the
    HTTP exchange itself succeeded) -- same contract as the text path."""
    resp = _Resp(200, "ok")
    resp.headers["Content-Length"] = str(config.MAX_RESPONSE_BYTES + 1)
    fake = _FakeClient([resp])
    with pytest.raises(fetch.FetchError, match="Response body too large") as exc_info:
        fetch.fetch_binary(fake, "https://example.com/huge.png")
    assert exc_info.value.status_code is None
    assert fake.calls == 1


def test_fetch_binary_rejects_oversized_streamed_body():
    """A body crossing the limit mid-stream is rejected by the chunk guard.

    Multi-chunk streaming is what the Content-Length pre-check cannot cover
    (a body without a header, or one whose decompressed size explodes past
    its wire size); the per-chunk guard must fire on the chunk that pushes
    the running total over the limit."""
    body = "x" * (config.MAX_RESPONSE_BYTES + 1)
    resp = _MultiChunkStreamingResp(200, body, chunk_size=1000)
    fake = _FakeClient([resp])
    with pytest.raises(fetch.FetchError, match="Response body too large") as exc_info:
        fetch.fetch_binary(fake, "https://example.com/huge-stream.png")
    assert exc_info.value.status_code is None
    assert fake.calls == 1
