"""Shared test doubles, helper factories, and autouse fixtures for the mirror's
test suite.

Everything here is a building block that every test file uses — rather than
each file defining its own variant with slightly different semantics and
subtle incompatibilities:

  * HTTP doubles -- ``_Resp`` and ``_FakeClient`` stand in for
    ``httpx.Response`` and (part of) ``httpx.Client`` so the retry / fetch
    paths can be exercised with no real network.  ``tree_client`` is a
    convenience builder that pre-loads a ``_FakeClient`` with a single
    git-trees API JSON response, and ``blob_entry`` constructs one tree
    entry dict -- these two eliminate repetitive setup in every test file
    that exercises the source adapters' tree-based discovery logic.
  * ``make_entry`` -- a factory that builds a valid ``FileEntry`` with
    sensible defaults, so tests only spell the fields that matter to them.
  * Three autouse fixtures that apply to EVERY test in the suite regardless
    of whether they request them: ``_no_sleep`` patches the shared stdlib
    ``time.sleep`` so no retry back-off can stall the suite,
    ``isolated_docs`` redirects ``config.DOCS_DIR`` / ``config.TOP_INDEX_PATH``
    to a temporary directory so no test can ever clobber the real ``docs/``
    tree, and ``_reset_active_locales`` restores the run-scoped locale
    selection holder (``config.ACTIVE_LOCALES``) to its ``None`` default so
    a CLI test that passed ``--locales`` cannot leak that selection into
    later tests.

Usage in any test file::

    from conftest import _FakeClient, _Resp, make_entry, tree_client, blob_entry
"""

from __future__ import annotations

import collections
import contextlib
import json
import time

import pytest
from mirror.core.manifest import FileEntry


class _Resp:
    """Minimal ``httpx.Response`` stub for tests that do not need real HTTP.

    Only the attributes and methods the mirror's fetch and validation code
    paths actually access at runtime are implemented; adding a new code path
    that reads a different ``Response`` attribute or calls a different method
    will need a corresponding addition to this stub. The ``status_code``,
    ``headers``, ``text``, ``encoding``, and ``iter_bytes()`` attributes mirror
    their httpx counterparts exactly. There is deliberately no
    ``raise_for_status()``: the production fetch path reads the body via
    ``client.stream()`` and checks ``status_code`` manually, so no code under
    test ever calls it.
    """

    # Default encoding for the response, used by ``get_with_retry`` when
    # decoding bytes from the streaming path. Real httpx sets this from the
    # Content-Type charset or sniffs it from a <meta> tag; the stub hardcodes
    # UTF-8, which matches the encoding of every test fixture body.
    encoding: str = "utf-8"

    def __init__(
        self, status: int, text: str = "ok", *, retry_after: str | None = None
    ):
        self.status_code = status
        self.text = text
        self.headers: dict[str, str] = {}
        if retry_after is not None:
            self.headers["Retry-After"] = retry_after

    def iter_bytes(self):
        """Yield the response body as a single bytes chunk.

        The streaming path in ``get_with_retry`` uses this to read the body
        incrementally when Content-Length is absent. Yielding the full body
        as one chunk exercises the per-chunk size-check logic without
        depending on httpx's actual chunk-size internals (typically a few
        KiB per yield). Real chunking is an httpx implementation detail;
        what matters for correctness is that the size guard fires within
        one chunk of crossing the limit.

        Yields:
            The UTF-8 encoded bytes of ``self.text`` as a single chunk.
        """
        yield self.text.encode("utf-8")


class _FakeClient:
    """Configurable ``httpx.Client`` stub for pipeline-level integration tests.

    Replays an ORDERED script of pre-configured responses: the client is
    constructed with a list of ``_Resp`` stubs and/or ``Exception`` instances,
    and each request method consumes exactly one item from the front of that
    queue (FIFO ``pop(0)``).  The URL being fetched is never looked up
    anywhere -- the stub does not map URLs to responses; a test that fetches
    N URLs must script exactly N items in the order the fetches occur, and
    each item answers the next fetch regardless of its URL.

    Two request methods are supported, both drawing from the same script
    queue: ``get()`` returns the next scripted response directly, and
    ``stream()`` (a context manager mimicking ``httpx.Client.stream``) yields
    the next scripted response inside a ``with`` block for the incremental
    download path.

    Calling either method with an empty queue raises ``RuntimeError`` naming
    the URL that was asked for, to catch tests that accidentally introduce a
    new fetch path without declaring what that fetch should return -- the
    failure is loud and immediate rather than a silent default empty response
    that masks the untested code path.
    """

    def __init__(self, script: list):
        """Initialise the fake client with an ordered list of responses.

        The *script* is a list of ``_Resp`` instances (or ``Exception``
        subclasses) that ``get()`` will return in FIFO order.  Each call to
        ``get()`` pops the next item from the front — a test that makes N
        fetch calls must script exactly N items, or the empty-script guard
        will raise ``RuntimeError`` with the URL that was asked for.

        Args:
            script: List of ``_Resp`` stubs and/or ``Exception`` instances.
        """
        self._script = collections.deque(script)
        self.calls = 0

    def __enter__(self):
        """Support use as a context manager (``with _FakeClient(...) as client:``).

        Returns ``self`` so the caller can bind the fake client to a variable
        within the ``with`` block exactly as it would a real ``httpx.Client``.
        The production code opens clients via ``fetch.make_client()`` and uses
        them in ``with`` blocks, and ``_FakeClient`` must be substitutable
        in those same ``with`` blocks without structural changes — this method
        makes that possible.
        """
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """No-op exit that does not close or tear down any resources.

        A real ``httpx.Client.__exit__`` calls ``self.close()`` to release
        the underlying connection pool, but ``_FakeClient`` has no real
        connections — the stub holds only an in-memory script list, so there
        is nothing to tear down.  Accepting the standard three-tuple of
        exception information (``exc_type``, ``exc_val``, ``exc_tb``)
        avoids a ``TypeError`` from the run-time ``with``-statement machinery;
        returning ``None`` means the exit does not suppress any exception that
        the body may have raised.
        """
        return None

    def get(self, url: str, headers: dict | None = None, **kwargs):
        """Pop the next pre-configured ``_Resp`` stub from the script queue.

        Each call to ``get()`` consumes one item from the script list the
        client was constructed with.  Items can be either a ``_Resp`` stub
        (returned to the caller) or an ``Exception`` subclass (raised
        immediately) — this lets tests simulate transient errors like HTTP
        500s without a separate error-injection path.

        Args:
            url: The URL being fetched (passed through to the caller as the
                request target; also used in the error message when the script
                queue is exhausted).
            headers: Request headers sent with the GET (accepted for
                interface compatibility with ``httpx.Client.get`` but
                currently ignored by this stub).

        Returns:
            The ``_Resp`` stub that was next in the script queue.

        Raises:
            RuntimeError:
                When the script queue is empty — i.e. ``get()`` was called
                ``len(script) + 1`` times but only ``len(script)`` responses
                were scripted.  The message includes the URL being fetched so
                the developer can immediately see which code path lacks a
                scripted response.
            Exception:
                Any ``Exception`` subclass placed in the script list is
                raised as-is.
        """
        if not self._script:
            raise RuntimeError(
                f"_FakeClient.get('{url}') called but the script queue is empty.  "
                f"The test scripted {self.calls} response(s) but at least "
                f"{self.calls + 1} fetch call(s) were made.  Every call to get() "
                f"must have a matching _Resp or Exception in the script list "
                f"passed to the constructor."
            )
        self.calls += 1
        item = self._script.popleft()
        if isinstance(item, Exception):
            raise item
        return item

    @contextlib.contextmanager
    def stream(self, method: str, url: str, **kwargs):
        """Mimic ``httpx.Client.stream()`` by yielding the next scripted response.

        The production fetch path issues requests via
        ``with client.stream("GET", url, ...) as resp:`` so the response body
        is genuinely read incrementally from the socket (bounded memory) rather
        than fully buffered by httpx before the size guard can fire.  A real
        ``httpx.Client.stream`` returns a context manager that yields the
        ``httpx.Response`` and closes the underlying connection on exit; this
        stub reproduces that contract by yielding the next ``_Resp`` from the
        same FIFO script queue that ``get()`` pops, so every existing test
        script keeps working unchanged whether the code under test calls
        ``get()`` or ``stream()``.

        There is no real connection to close on exit, so the context manager
        body is a bare ``yield`` with no teardown.

        Args:
            method: HTTP method of the request (accepted for interface
                compatibility with ``httpx.Client.stream``; always ``"GET"``
                from the production code, ignored by this stub).
            url: The URL being fetched (forwarded to ``get()`` so the
                exhausted-queue error message names it).
            **kwargs: Additional keyword arguments such as ``headers``
                (accepted for interface compatibility, forwarded to
                ``get()``).

        Yields:
            The ``_Resp`` stub that was next in the script queue.
        """
        yield self.get(url, **kwargs)


def make_entry(
    slug: str = "test-page",
    *,
    title: str = "Test Page",
    group: str = "docs",
    source_url: str | None = None,
    source_md_url: str | None = None,
    source_id: str = "",
    hash: str = "abc123",
    last_updated: str = "2026-07-25T00:00:00Z",
) -> FileEntry:
    """Build a FileEntry dataclass with sensible defaults for tests.

    Every keyword argument has a default so callers only specify the fields
    relevant to their test case.  The defaults produce a valid,
    realistic-looking entry that passes all ``FileEntry.__post_init__``
    validations (slug whitelist, length limits, path-traversal guards).

    Args:
        slug: Relative page path (default: ``"test-page"``).
        title: Human-readable page title (default: ``"Test Page"``).
        group: Navigation category group (default: ``"docs"``).
        source_url: Canonical web page URL (default:
            ``"https://example.com/{slug}"``).
        source_md_url: Raw Markdown source URL (default:
            ``"https://example.com/{slug}.md"``).
        source_id: Stable upstream page identifier (default: the slug value).
        hash: SHA-256 content digest string (default: ``"abc123"``).
        last_updated: ISO 8601 UTC timestamp string (default:
            ``"2026-07-25T00:00:00Z"``).

    Returns:
        A fully constructed ``FileEntry`` instance.
    """
    return FileEntry(
        slug=slug,
        title=title,
        group=group,
        source_url=source_url
        if source_url is not None
        else f"https://example.com/{slug}",
        source_md_url=source_md_url
        if source_md_url is not None
        else f"https://example.com/{slug}.md",
        source_id=source_id or slug,
        hash=hash,
        last_updated=last_updated,
    )


def tree_client(entries, truncated=False):
    """Build a fake client that answers a single git-trees API call.

    Creates a ``_FakeClient`` pre-loaded with one ``_Resp(200)`` whose body
    is the JSON payload that GitHub's Trees API returns::

        {"truncated": false, "tree": [{"type": "blob", "path": "..."}, ...]}

    Source adapters whose ``discover()`` method fetches a repo's git-tree
    listing (``codex_cli``, ``kimi_code``, ``opencode``) use this client
    to script the tree response without every test file having to spell out
    the ``_Resp`` + ``json.dumps`` dance.  Tests that need to simulate a
    truncated tree response (``"truncated": true`` — the API could not fit
    the whole tree) pass ``truncated=True``.

    Args:
        entries: List of dicts, each representing a single git-tree entry.
            Minimum entry: ``{"type": "blob", "path": "some/file.md"}``.
        truncated: Whether the artificial response carries
            ``"truncated": true``.  Defaults to ``False``.

    Returns:
        A ``_FakeClient`` that yields the JSON tree payload on its first
        ``get()`` call.
    """
    payload = {"truncated": truncated, "tree": entries}
    return _FakeClient([_Resp(200, json.dumps(payload))])


def blob_entry(path):
    """Build a git-trees API file entry dict for a blob at *path*.

    GitHub's Trees API returns a list of objects, each describing one file
    or subdirectory.  The entries that source adapters are interested in
    have ``"type": "blob"`` (a plain file) and a ``"path"`` field giving
    the repo-relative location.  This helper constructs such a dict so
    tests can declare which files the fake tree response contains without
    repeatedly writing the boilerplate ``{"type": "blob", "path": ...}``
    dict literal.

    Directory entries (``"type": "tree"``) are *not* built by this helper
    because the adapters filter them out; tests that need to verify the
    filtering behaviour can inline the directory entry:

        {"type": "tree", "path": "docs"}

    Args:
        path: Repository-relative path of the file, e.g.
            ``"docs/config.md"`` or ``"src/main.py"``.

    Returns:
        A dict shaped like a single git-trees API blob entry::

            {"type": "blob", "path": <path>}
    """
    return {"type": "blob", "path": path}


@pytest.fixture(autouse=True)
def _no_sleep(monkeypatch):
    """Replace ``time.sleep`` globally so no test in ANY file can incur a real delay.

    The retry logic in ``mirror.core.fetch`` backs off between attempts with
    ``time.sleep`` (starting at ``config.RETRY_DELAY`` seconds and doubling up
    to ``config.MAX_RETRY_DELAY``). Tests exercise those retry paths heavily,
    and the production code does a plain ``import time``, so patching the
    shared stdlib ``time`` module's ``sleep`` attribute covers every caller
    regardless of how each module imports ``time``.

    This fixture lives in conftest (rather than in the one test file that
    first needed it) and is autouse on purpose: a retry test added to any
    other test file in the future must not be able to stall the whole suite
    by seconds per attempt just because nobody remembered to opt in. If a
    future test ever needs REAL sleeps (e.g. timing-sensitive logic), narrow
    this fixture -- make it non-autouse or override it locally in that test --
    rather than removing it wholesale.

    The replacement lambda accepts ``*a, **k`` (any positional and keyword
    arguments) so it can stand in for ``time.sleep(seconds)`` regardless of
    how the caller formats the call.  The return value of the real
    ``time.sleep`` is ``None``, which the lambda also returns implicitly.
    """
    monkeypatch.setattr(time, "sleep", lambda *a, **k: None)


@pytest.fixture(autouse=True)
def isolated_docs(tmp_path, monkeypatch):
    """Redirect the mirror's docs/ tree to a temporary directory for EVERY test.

    Creates a temporary ``DOCS_DIR`` and points ``TOP_INDEX_PATH`` into it,
    so tests that write manifests or indexes never touch the real ``docs/``
    tree.  This is critical because the pipeline deletes stale docs (files
    whose source pages disappeared upstream) — without isolation a single
    test run could permanently delete real content.

    The fixture is autouse on purpose: the mirror resolves ``DOCS_DIR`` from
    the repository layout (not the current working directory), so any test
    that reaches ``pipeline.run()``, ``write_top_index()``, or any other
    function that reads or writes to ``config.DOCS_DIR`` without this
    redirection writes straight into the real ``docs/`` tree — an incident
    that once clobbered the real ``docs/README.md``.  Making isolation the
    default (rather than opt-in) means a future test cannot repeat that
    mistake by simply forgetting to request the fixture.  Tests that
    legitimately need the fixture's return value (the temporary docs path)
    can still declare ``isolated_docs`` as a parameter; tests that never
    touch the docs tree pay only a harmless tmp-dir creation (a few
    microseconds of filesystem overhead).

    Returns:
        The ``pathlib.Path`` of the temporary ``docs/``-like directory, in
        case a test needs to inspect files written there.
    """
    import mirror.config as cfg

    # The directory is deliberately NOT named "docs": several tests build
    # their own tmp_path/"docs" tree with an explicit mkdir() to pass as the
    # `base` argument of write_docs-style functions (which take the path
    # directly and never consult config.DOCS_DIR). A same-named fixture
    # directory would make those mkdir() calls fail with FileExistsError.
    #
    # The choice of "isolated-docs" as the subdirectory name (rather than
    # a truly random string) makes test-fixture debug output more readable:
    # when a test fails and pytest prints the tmpdir path, the name
    # "isolated-docs" is immediately recognisable as the fixture's output
    # directory rather than an opaque UUID.
    docs = tmp_path / "isolated-docs"
    docs.mkdir()
    monkeypatch.setattr(cfg, "DOCS_DIR", docs)
    monkeypatch.setattr(cfg, "TOP_INDEX_PATH", docs / "README.md")
    monkeypatch.setattr(cfg, "ROOT_README_PATH", tmp_path / "README.md")
    return docs


@pytest.fixture(autouse=True)
def _reset_active_locales(monkeypatch):
    """Reset the run-scoped locale selection to ``None`` for EVERY test.

    ``cli.main`` stores the validated ``--locales`` flag in the module-level
    holder ``config.ACTIVE_LOCALES``, which the OpenCode adapter reads when
    its ``discover()`` is called without an explicit ``locales`` argument.
    Because the holder is process-global, a CLI test that passes
    ``--locales pt-br`` would otherwise leak that selection into every later
    test that runs discovery through the config fallback channel -- an
    order-dependent failure in which a translation test suddenly sees
    English-only results or vice versa. Resetting the holder to ``None``
    (its default: the English-only mirror) before each test restores the
    exact state a fresh process would have, mirroring how
    ``config.DOCS_DIR`` isolation works for the docs tree.
    """
    import mirror.config as cfg

    monkeypatch.setattr(cfg, "ACTIVE_LOCALES", None)
