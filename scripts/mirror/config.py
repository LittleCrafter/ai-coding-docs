"""Shared configuration for the multi-source docs mirror.

This module is the single place where *environment-shaped* values live:

* the on-disk layout of the mirror (where ``docs/`` is, where the top-level
  index goes);
* the HTTP behaviour shared by every source (timeouts, retries, rate limiting,
  and the User-Agent we present to upstream servers);
* metadata constants baked into every generated ``manifest.json``.

Everything here is a plain module-level constant, with exactly ONE
deliberate exception: ``ACTIVE_LOCALES`` (bottom of this module), the
run-scoped locale selection that the CLI writes from its ``--locales`` flag
and the locale-capable source adapter reads during discovery. It is mutable
on purpose -- a per-run value cannot be a constant -- and its section below
documents who writes it, who reads it, and why a module-level holder is the
only channel that can carry it today. There is deliberately no settings file
and no per-source overrides, and -- with exactly one carve-out -- no
environment-variable parsing either: the mirror is a small, single-purpose
tool, and keeping the tuning knobs as constants in one importable module
means every layer (``core.fetch``, ``pipeline``, tests) reads exactly the
same values without any wiring. The single exception is
``AI_CODING_DOCS_ROOT`` (documented inline below, next to ``REPO_ROOT``),
which exists so a wheel-installed copy of this package -- where no
``pyproject.toml`` is reachable from the ``__file__`` parents chain -- can
still be pointed at a docs checkout. Nothing else in this module reads the
environment.

This module is deliberately a *leaf*: it imports nothing from the ``mirror``
package itself. ``mirror.__init__`` eagerly imports ``config`` to re-export
``TOOL_VERSION`` as ``mirror.__version__``, so any package import added here
would risk an import cycle. Keep it dependency-free.
"""

from __future__ import annotations

import os
import tomllib
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as _dist_version
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    # Only needed for the ``TIMEOUT`` annotation; the real import happens
    # lazily on first access (see the module ``__getattr__`` below).
    import httpx

# --- On-disk layout --------------------------------------------------------
# How the mirror finds its project root and where it writes its output.
# Every path below is derived from this file's own location on disk rather than
# from the process's current working directory (CWD). This design choice makes
# the mirror robust and predictable: it writes to the same directory tree no
# matter where the operator (or a cron job, or a systemd timer, or an IDE task
# runner) invoked it from. Deriving paths from ``__file__`` also means the
# mirror still works correctly when the user changes directory mid-session.
#
# The ``parents`` chain, concretely:
#   parents[0] -> <repo>/scripts/mirror/   (the directory housing this package)
#   parents[1] -> <repo>/scripts/          (where helper scripts live)
#   parents[2] -> <repo>/                  (the repository root itself)
# ``.resolve()`` collapses any symlinks in the path before we start, so the
# result is a filesystem-real absolute path even when the script is reached
# through a symlinked wrapper (e.g. ``/usr/local/bin/mirror-docs -> ...``).
#
# Environment override (AI_CODING_DOCS_ROOT):
# Allow the docs target tree to be overridden via the environment so the
# mirror stays usable when this file does NOT live inside a source checkout
# at all. This is the normal case for a non-editable / wheel-based install
# (``pip install ai-coding-docs``), where ``config.py`` is copied to
# ``<prefix>/lib/pythonX.Y/site-packages/mirror/config.py`` and no
# ``pyproject.toml`` is reachable from the parents chain. In that scenario,
# the operator sets ``AI_CODING_DOCS_ROOT`` to point at a checkout, and the
# mirror writes into that checkout's ``docs/`` directory instead of wherever
# the installed package happens to live.
# When the env var is unset, fall back to deriving the repo root from this
# file's own location (the normal case: running ``uv run mirror-docs`` or
# ``python -m mirror`` from a source checkout).
#
# The value is ``strip()``-ed: a whitespace-only value (``"  "``) is treated
# as unset, because a shell snippet like ``export
# AI_CODING_DOCS_ROOT="$MAYBE_UNSET_VAR"`` can easily leave the variable set
# to nothing meaningful, and turning that into ``Path("  ")`` would silently
# resolve to a bogus relative path instead of falling back to the normal
# ``__file__``-based derivation. Stripping leaves valid values untouched
# except for trimming accidental surrounding whitespace, which ``Path`` would
# have interpreted as part of the (wrong) path.
_env_root = os.environ.get("AI_CODING_DOCS_ROOT", "").strip()
REPO_ROOT = (
    Path(_env_root).resolve() if _env_root else Path(__file__).resolve().parents[2]
)
# Guard against a silent wrong-path resolution in BOTH derivation modes.
# The ``__file__``-based fallback assumes ``config.py`` lives at exactly
# ``<repo>/scripts/mirror/config.py``, so ``parents[2]`` is the repository
# root; the ``AI_CODING_DOCS_ROOT`` override assumes the variable points at
# a real checkout. If this file was moved, the directory layout was
# restructured, the package was installed non-editably (in which case
# ``parents[2]`` points into the Python site-packages prefix rather than the
# source checkout), or the override names a directory that is not a
# checkout, the derivation silently resolves to a wrong directory, and every
# path derived from ``REPO_ROOT`` (namely ``DOCS_DIR`` and ``TOP_INDEX_PATH``)
# would point at the wrong place, causing the mirror to write documentation
# files into an unintended directory tree.
# Therefore, both modes require the presence of a ``pyproject.toml`` at the
# resolved root, which confirms we are looking at a real project checkout.
# If it is missing, stop fast with a clear, actionable error message that
# tells the operator exactly what happened and how to fix it, rather than
# silently writing files into the wrong location and failing opaquely later.
if _env_root and not (REPO_ROOT / "pyproject.toml").exists():
    raise RuntimeError(
        f"AI_CODING_DOCS_ROOT is set to {_env_root!r}, but it is not a "
        "valid repository checkout root: pyproject.toml was not found "
        "there. Please set it to a valid repository checkout root (a "
        "directory containing pyproject.toml)."
    )
if not _env_root and not (REPO_ROOT / "pyproject.toml").exists():
    raise RuntimeError(
        f"REPO_ROOT resolved to {REPO_ROOT}, but pyproject.toml was not found "
        "there. config.py must live at <repo>/scripts/mirror/config.py -- was "
        "it moved, or was the package installed non-editably? Set "
        "AI_CODING_DOCS_ROOT to the repository checkout root (or run via "
        "`uv run mirror-docs` from a checkout)."
    )

# The mirrored documentation output tree rooted at ``<REPO_ROOT>/docs/``.
# Each documentation source (e.g. Anthropic, OpenAI) gets its own subfolder
# under this directory (``docs/<source-name>/``). Inside each subfolder the
# mirror writes:
#   - the fetched Markdown pages (as ``.md`` files);
#   - ``manifest.json``, a machine-readable index of all pages for that source;
#   - its own ``README.md`` acting as a human-readable index page;
#   - and optionally a ``whats-new/`` subfolder with change logs.
#
# The mirror never writes outside ``DOCS_DIR``. Deleting or moving this
# directory between runs effectively resets the mirror to a clean state.
DOCS_DIR = REPO_ROOT / "docs"

# The cross-source index page at the root of ``docs/`` (``docs/README.md``).
# This file is regenerated after every non-dry run by
# ``pipeline.write_top_index``, which reads the on-disk ``manifest.json``
# files from every source subfolder, merges their metadata, and writes a
# top-level ``README.md`` that lists every mirrored source and links to each
# source's own index page. The user navigates the full mirror by opening
# this single file in their Markdown viewer.
#
# Because ``docs/README.md`` is also shown by default when someone opens the
# ``docs/`` directory on GitHub, this file serves double duty as both a
# local index and the repository's rendered documentation landing page.
TOP_INDEX_PATH = DOCS_DIR / "README.md"

# The repository root README file and markers for the auto-generated sources table.
ROOT_README_PATH = REPO_ROOT / "README.md"
SOURCES_TABLE_START = "<!-- SOURCES_TABLE:START -->"
SOURCES_TABLE_END = "<!-- SOURCES_TABLE:END -->"

# Version of the tool, shared by the User-Agent below and re-exported by
# ``mirror.__init__`` as ``mirror.__version__``.
#
# The version is resolved via a three-tier fallback chain:
#
#   Tier 1 — installed-distribution metadata (best, preferred)
#   ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
#   When the package is installed normally (``uv sync``, ``pip install``, or an
#   editable ``pip install -e .``), ``importlib.metadata.version`` reads the
#   distribution metadata that was baked in at install time. This is the most
#   reliable source because it matches what ``pip list`` and ``pip show``
#   report, and it works regardless of the working directory.
#
#   Tier 2 — pyproject.toml at REPO_ROOT (runtime fallback)
#   ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
#   When the package is NOT installed (e.g. ``python -m mirror`` run directly
#   from a source checkout), ``importlib.metadata`` raises
#   ``PackageNotFoundError``. In that case we read the version from the
#   ``[project]`` table of the project's ``pyproject.toml`` using ``tomllib``,
#   the TOML parser in the Python standard library (available since 3.11;
#   this project requires >= 3.14). Using the standard parser keeps this
#   module free of third-party dependencies and import-cycle risk while
#   still handling the full TOML grammar correctly. This avoids the old
#   single hardcoded fallback, which silently drifted out of sync every
#   time ``pyproject.toml`` was bumped without a reinstall.
#
#   Tier 3 — hardcoded "0.2.0" (last resort, only if both above fail)
#   ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
#   If ``pyproject.toml`` is also missing or unreadable (e.g. the file was
#   deleted, the layout was restructured, or the mirror is running embedded in
#   another project without a ``pyproject.toml`` at ``REPO_ROOT``), we fall
#   back to a static string. This fallback is inherently fragile — it must be
#   bumped by hand when ``pyproject.toml`` changes — but it guarantees the
#   tool always initialises, even in pathological environments.
#
# Note on import safety: we resolve the version eagerly at module scope so
# every consumer (the User-Agent below, ``mirror.__init__`` for
# ``mirror.__version__``) gets it without any lazy-initialisation ceremony.


def _resolve_version() -> str:
    """Apply the three-tier fallback chain described above.

    Returns the resolved version string. This function exists as a single
    callable so the fallback logic is testable and the module-level constant
    below stays a simple assignment.
    """
    # --- Tier 1: try installed-distribution metadata ---------------------------
    try:
        return _dist_version("ai-coding-docs")
    except PackageNotFoundError:
        pass  # fall through to Tier 2

    # --- Tier 2: parse pyproject.toml at REPO_ROOT -----------------------------
    pyproject_path = REPO_ROOT / "pyproject.toml"
    try:
        text = pyproject_path.read_text(encoding="utf-8")
    except OSError:
        # ``FileNotFoundError`` is a subclass of ``OSError``, so this single
        # clause already covers both "file is not there" and every other
        # read failure (permissions, I/O errors) -- all of which take the
        # same fallback path.
        pass  # fall through to Tier 3
    else:
        # Parse the file with ``tomllib``, the TOML parser from the Python
        # standard library, and read ``version`` from the ``[project]``
        # table. Using the real parser means the lookup is correct for any
        # valid TOML formatting (whitespace, section ordering, comments),
        # not just the exact line shape the file happens to have today.
        # ``tomllib`` is part of the standard library since Python 3.11 and
        # this project requires >= 3.14, so no third-party dependency is
        # introduced and this module stays a safe import leaf.
        try:
            return tomllib.loads(text)["project"]["version"]
        except tomllib.TOMLDecodeError, KeyError:
            # Malformed TOML, or a ``pyproject.toml`` without a
            # ``[project]`` table / ``version`` key (e.g. the mirror is
            # running embedded in another project): fall through to Tier 3.
            pass

    # --- Tier 3: hardcoded fallback -------------------------------------------
    # Both importlib.metadata and pyproject.toml parsing failed. Return a
    # static string so the tool still boots. Bump this whenever the version
    # in pyproject.toml changes.
    return "0.2.0"


TOOL_VERSION = _resolve_version()

# --- HTTP behaviour (shared by all sources) --------------------------------
# These values tune the behaviour of the single shared ``httpx.Client`` (the
# synchronous client built by ``core.fetch`` -- the pipeline is fully
# synchronous, there is no async code anywhere in it) and are used by every
# source fetcher. They are defined as global constants because the mirror is
# a *polite batch fetcher*, not a per-source custom crawler. Every source gets the same identification
# (one User-Agent string so upstream operators see a consistent caller), the
# same timeout policy (generous enough for the slowest doc server but still
# bounded), and the same retry policy (for transient network failures that
# can affect any HTTP request).
#
# Why a single shared client rather than per-source clients?
#   - httpx connection pooling: a single client reuses TCP connections to the
#     same host, reducing latency and server load.
#   - Simpler configuration: one set of knobs to tune instead of per-source
#     overrides that would require a settings file or config dictionaries.
#   - Predictable resource usage: one retry budget, one timeout profile.
#     If a particular source needs different values in the future, the
#     ``core.fetch.make_client()`` function can accept overrides —
#     but that complexity is not needed yet.

# USER_AGENT identifies the tool honestly and consistently to every upstream
# server. Some documentation servers (and the CDNs in front of them) throttle
# or outright reject clients that send no User-Agent or a generic one (like
# "python-httpx/0.28"). Sending an explicit, descriptive User-Agent string
# avoids these blocks. It also helps upstream operators identify which release
# of the mirror is hitting them if they check their access logs — the version
# is stamped directly into the string so they can correlate issues with a
# specific release.
# Format: ``ai-coding-docs-mirror/{TOOL_VERSION} (+{repo_url})``
USER_AGENT = f"ai-coding-docs-mirror/{TOOL_VERSION} (+https://github.com/LittleCrafter/ai-coding-docs)"

# Timeout object applied to every HTTP request made by the mirror.
# ``httpx.Timeout(30.0, connect=10.0)`` means:
#
#   - **Overall request timeout: 30 seconds.** The entire operation (DNS
#     resolution + TCP connection + TLS handshake + sending headers + reading
#     response body) must complete within this window. 30 seconds is generous
#     enough for slow CDN cold caches or servers that stream their response
#     incrementally, but short enough that a wedged server does not stall the
#     entire mirror run indefinitely.
#
#   - **Connect timeout: 10 seconds.** DNS resolution and the TCP/TLS handshake
#     must complete within this shorter window. This catches dead DNS entries,
#     unreachable IPs, or servers that silently drop SYN packets early, without
#     waiting the full 30 seconds for the overall timeout to fire. A server
#     that answers the TCP handshake but then stalls while generating its
#     response still gets the full 30-second overall timeout.
#
# When either timeout fires, ``httpx`` raises ``httpx.TimeoutException``,
# which the fetch layer's retry loop catches and retries up to
# ``MAX_RETRIES`` times with exponential backoff.
#
# The constant itself is created LAZILY (see the module ``__getattr__`` at
# the bottom of this file) rather than at import time: building it requires
# importing httpx, and the CLI's ``--version`` fast path must never import
# third-party HTTP machinery just to print a version string. Only
# ``core.fetch.make_client`` ever reads ``TIMEOUT``, so the import cost is
# deferred to the first real client construction (and paid exactly once).
_TIMEOUT: "httpx.Timeout | None" = None

# Seconds of deliberate, polite delay inserted *between* consecutive page
# fetches (the delay is never applied before the first page of a source).
# The mirror crawls entire documentation sites page by page; without this
# delay, the mirror would fire requests as fast as ``httpx`` can dispatch
# them (typically dozens per second), which many documentation servers
# interpret as abusive behaviour and respond to with HTTP 429 (Too Many
# Requests) or outright connection drops.
#
# 0.35 seconds (~3 pages per second, ~180 pages per minute) is a conservative
# rate that stays well below what real-world doc sites consider abusive:
#   - GitHub's recommended rate limit is 5000 authenticated requests per hour,
#     which is ~1.4 requests/second — our rate is about 2x that.
#   - Cloudflare-protected sites typically allow hundreds of requests per
#     minute before triggering a challenge.
#   - Static doc hosts (ReadTheDocs, GitHub Pages) do not enforce rate limits
#     at all at this rate.
#
# If you need a faster crawl (e.g. for a small private wiki), decrease this
# value. If you encounter 429 responses in logs, increase it.
RATE_LIMIT_DELAY = 0.35

# Default number of concurrent worker threads used to fetch documentation pages
# for a single source (via ``concurrent.futures.ThreadPoolExecutor``).
#
# Bounded concurrency allows I/O-bound page fetching to overlap network latency
# across multiple pages while staying polite:
#   - 3 workers provide a noticeable speedup for large documentation sets (e.g.
#     Claude Code or OpenCode with dozens of pages) without causing excessive
#     connection churn or triggering anti-scraping / rate-limiting defenses on
#     upstream servers.
#   - Combined with the thread-safe ``core.fetch.RateLimiter`` (which enforces
#     ``RATE_LIMIT_DELAY`` between consecutive request dispatches across all
#     threads), requests remain spaced out and polite.
#   - Can be overridden at runtime via the ``--concurrency`` / ``--workers`` CLI
#     flag or by passing ``workers=<int>`` to ``pipeline.run()`` / ``fetch_pages()``.
#   - Setting workers=1 forces sequential single-threaded fetching.
DEFAULT_WORKERS = 3

# Retry policy for transient network failures. The mirror will automatically
# retry a request when it encounters any of the following:
#   - Connection errors (DNS failure, TCP reset, TLS handshake failure)
#   - HTTP 5xx server errors (502 Bad Gateway, 503 Service Unavailable,
#     504 Gateway Timeout — the server is temporarily overloaded or down)
#   - Timeouts (either the overall 30s timeout or the 10s connect timeout)
#
# The retry uses *exponential backoff with jitter*: after each failed
# attempt, the mirror waits ``RETRY_DELAY * 2^attempt`` seconds before the
# next attempt (capped at ``MAX_RETRY_DELAY``), and the actual sleep is that
# delay times a random factor in [0.5, 1.5]. The jitter window is
# deliberately symmetric around the deterministic value: the mean wait is
# unchanged, but parallel workers that hit a rate limit (HTTP 429) at the
# same instant no longer sleep for identical durations and retry in lockstep
# (the thundering-herd problem). The exact multiplication lives in
# ``core.fetch.get_with_retry``; this module only owns the base constants.
# A numeric ``Retry-After`` header overrides the jittered value and is
# honored verbatim, since it is the server's explicit instruction.
#
# Constants:
#   MAX_RETRIES      = 3  — Total number of attempts per URL (the initial
#                           attempt plus up to 2 retries). After the 3rd
#                           failed attempt the page is abandoned (logged
#                           as a fetch error).
#   RETRY_DELAY      = 2.0  — Base delay in seconds; it doubles after each
#                             failed attempt (attempt 1 fails: wait 2s,
#                             attempt 2 fails: wait 4s).
#   MAX_RETRY_DELAY  = 30.0 — Cap on the delay. Without this cap a server
#                             that stays broken for a long time would cause
#                             increasingly long waits (attempt 5: 64s,
#                             attempt 10: 2048s, ...), stalling the entire
#                             run. With 3 attempts there are at most 2
#                             backoff sleeps per page, so a persistently
#                             broken upstream stalls the run by at most
#                             ~60s of waiting per page (2 sleeps × 30s max
#                             each).
MAX_RETRIES = 3
RETRY_DELAY = 2.0
MAX_RETRY_DELAY = 30.0

# Maximum number of bytes the mirror will accept in the body of a single HTTP
# response. This is a safety valve against two scenarios:
#
#   1. A misconfigured upstream server serving a multi-gigabyte payload
#      (e.g. a static-file server that accidentally serves a 4 GB video file
#      instead of a 200 KB documentation page because of a misconfigured
#      rewrite rule). Without this limit, the mirror would read the entire
#      payload into memory and either exhaust the system's RAM (OOM crash) or
#      swap heavily and bring the system to a crawl.
#
#   2. A malicious or compromised upstream returning an unbounded streaming
#      response, keeping the connection open and slowly feeding data to waste
#      resources.
#
# When ``Content-Length`` exceeds this value, the fetch layer rejects the
# response with ``FetchError`` right after reading the response headers,
# before a single byte of the body is pulled in. When
# ``Content-Length`` is absent (chunked transfer encoding), the fetch layer
# still streams the body in chunks and keeps a running total of the
# decompressed byte count: the per-chunk guard raises ``FetchError``
# mid-stream the moment that cumulative count crosses this limit, so an
# unbounded body is cut off after at most one overshooting chunk rather than
# being read into memory in full first.
#
# 10 MiB is generous enough for any real documentation page — the largest
# page currently in this mirror is ~530 KiB — while still capping worst-case
# memory usage at well below a typical desktop system's available RAM.
# The limit is expressed as a multiplication (10 * 1024 * 1024) rather than
# as the literal 10485760 so the intent (10 mebibytes) is obvious to anyone
# reading the code.
MAX_RESPONSE_BYTES = 10 * 1024 * 1024  # 10 MiB

# --- Manifest metadata -----------------------------------------------------
# A static, human-readable description string that is embedded into every
# source's ``manifest.json`` file at generation time. Anyone (or any tool)
# opening an arbitrary ``manifest.json`` file — perhaps months or years later,
# outside the original repository context — can read this description to
# understand what the file represents without needing to look up the
# repository's ``README.md`` or trace the original source code.
#
# The description appears as the top-level ``"description"`` key in every
# manifest. It is intentionally value-neutral and generic so it remains
# accurate even when the set of mirrored sources changes over time.
# Readers who want a human-readable overview of a source's pages should open
# the sibling ``README.md`` in the same directory, which the mirror generates
# as a formatted Markdown index of that source's content.
MANIFEST_DESCRIPTION = (
    "Mirror of a coding-tool's documentation. Keys are slugs (the path under "
    "this folder). See the sibling README.md for a human-readable index."
)


def __getattr__(name: str) -> httpx.Timeout:
    """Resolve the lazily-created ``TIMEOUT`` constant on first access.

    ``httpx`` is deliberately NOT imported at module level: the CLI's
    ``--version`` path must stay fast and free of third-party HTTP imports.
    ``TIMEOUT`` is only consumed by ``core.fetch.make_client`` when it builds
    the shared client, so importing httpx at that moment (once, then cached
    in ``_TIMEOUT``) is the cheapest point the dependency is actually
    needed. Any other missing attribute raises the standard AttributeError,
    keeping the module's introspection behaviour identical to a plain module.
    (The return annotation names httpx only under TYPE_CHECKING; with
    postponed annotations it is never evaluated at runtime.)
    """
    if name == "TIMEOUT":
        global _TIMEOUT
        if _TIMEOUT is None:
            import httpx

            _TIMEOUT = httpx.Timeout(30.0, connect=10.0)
        return _TIMEOUT
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


# --- Run-scoped locale selection -------------------------------------------
# The one mutable, run-scoped value in this module -- and the ONLY departure
# from the "plain constants" rule this module documents at the top.
#
# Writers: ``mirror.cli.main`` stores the validated ``--locales`` flag value
# here right before calling ``pipeline.run`` (nothing else may write it).
# Readers: a source adapter whose discovery supports non-English locales --
# currently only ``mirror.sources.opencode`` -- reads it when its
# ``discover()`` is called without an explicit ``locales`` argument.
#
# Why a module-level holder? ``pipeline.run()``'s signature does not (yet)
# carry the flag, and the CLI must not be reachable from the adapters (the
# dependency direction is cli -> pipeline -> sources). This holder is the
# only channel that can move a per-run value across that boundary without
# touching the pipeline. The adapters accept the same selection as an
# explicit ``locales`` parameter, so the holder is a stopgap that a future
# pipeline wiring can bypass entirely -- see ``opencode.discover``'s
# docstring for the full call contract.
#
# Semantics: ``None`` (the default) means the historical English-only
# mirror; a tuple holds the locale codes selected for THIS run (``all`` is
# expanded by the CLI into the full known set). The CLI stores the value
# normalized (sorted, de-duplicated) so runs with differently-ordered flags
# behave identically. Tests reset the holder to ``None`` between tests (the
# ``_reset_active_locales`` autouse fixture in ``tests/conftest.py``) so a
# test that runs the CLI cannot leak its locale selection into later tests.
ACTIVE_LOCALES: tuple[str, ...] | None = None
