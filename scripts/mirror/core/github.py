"""Shared helpers for sources that call the GitHub REST API.

Three of the mirrored documentation sets (Codex CLI, Kimi Code, OpenCode) live as
Markdown inside public GitHub repositories. Each source discovers its pages
the same way: one call to the "git trees" API (``?recursive=1``) returns the
repo's entire file tree as a flat list, and each Markdown file is then
downloaded from ``raw.githubusercontent.com`` -- raw file serving is NOT
subject to the API rate limit, which matters because the pipeline fetches
every page.

This module owns everything about talking to the API itself:

* :func:`api_headers` -- builds the request headers, attaching a Bearer
  token when one is available in the environment;
* :func:`fetch_git_tree` -- performs the single rate-limited tree-listing
  call, wraps rate-limit failures in an actionable error, refuses
  truncated (incomplete) responses, and warns once per process when the
  response headers show the rate-limit budget running low.

Why this lives in ``core/`` and not in the source adapters: the tree-fetch,
the rate-limit error mapping, and the truncation guard used to be copy-pasted
between ``sources/codex_cli.py`` and ``sources/kimi_code.py`` with a "keep
both copies in sync" comment. Any logic that needs a comment demanding
synchronization is one edit away from drifting apart, so the shared
implementation lives here and the adapters keep only their per-source
configuration (repo, branch, docs prefix, URL bases).

Anonymous GitHub API requests are capped at 60/hour per IP, which a scheduled
job (or a shared CI runner) blows through easily. Authenticating raises that
to 5000/hour, so when a token is available we attach it automatically. Tokens
are read from the environment and never logged.
"""

from __future__ import annotations

import json
import os
import sys
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any

from .fetch import FetchError, get_with_retry
from .utils import extract_version

if TYPE_CHECKING:
    import httpx

# Module-level boolean flag that tracks whether the unauthenticated-access
# warning has already been printed to stderr during the current process run.
# It starts as False and is flipped to True by fetch_git_tree on the first
# anonymous API call of each run, suppressing the warning on all subsequent
# calls within the same process invocation.
#
# The reason for using a module-level variable rather than threading a
# "warned" boolean through the call chain is that threading would require
# every calling function to accept and return an additional parameter,
# bloating the signatures in every source adapter (codex_cli, kimi_code,
# opencode) just to carry a single boolean that controls a cosmetic warning.
# A module-level flag avoids that API churn entirely while keeping the
# suppression logic self-contained and trivially testable (the flag can be
# reset between test runs).
#
# One warning per process run is the right frequency: a scheduled job that
# runs every 3 hours will emit the warning once per invocation, giving a
# human reviewing the output a single reminder without flooding the log
# with identical lines across every GitHub-backed source.
_auth_warning_emitted = False

# Module-level boolean flag that latches the "rate limit nearly exhausted"
# warning to a single emission per process run -- the exact same one-shot
# pattern as ``_auth_warning_emitted`` above (see that flag's comment for why
# a module-level latch is used instead of threading state through the call
# chain, and why once per run is the right frequency). The two latches are
# independent: the auth warning fires once for MISSING credentials, this one
# fires once for a nearly exhausted budget, and a run can legitimately emit
# both (an anonymous caller burning through its 60/hour allowance) or
# neither.
_rate_limit_warning_emitted = False

# The ``X-RateLimit-Remaining`` value below which the low-budget warning
# fires. GitHub attaches this header to every API response; it counts down
# towards 0 as the current hourly window's budget is consumed. Warning once
# the budget drops BELOW ten remaining requests -- rather than waiting for
# zero -- gives an operator reading
# a scheduled run's log enough lead time to act (export a token, or wait for
# the window to reset) BEFORE the next runs start failing hard with
# 403/429; the hard failure path already exists (the FetchError re-wrap in
# fetch_git_tree), so this threshold exists purely to turn that post-mortem
# into an early alert while the run is still succeeding.
_RATE_LIMIT_WARN_THRESHOLD = 10

# Request GitHub's canonical JSON media type for every API call. GitHub's
# REST API documentation recommends explicitly sending
# "application/vnd.github+json" so that responses use the documented,
# stable JSON representation of each resource rather than whatever default
# the endpoint would otherwise serve. The trees and blobs endpoints the
# mirror calls all return snake_case property names; the point of the
# header is not to change the shape of the payload but to pin the mirror to
# the representation GitHub documents and commits to keeping stable.
_JSON_ACCEPT = {"Accept": "application/vnd.github+json"}

# Pin a specific GitHub REST API version so that response shapes do not
# change unexpectedly under the running code. When this header is absent,
# GitHub serves whichever API version is the current default, and that
# default can advance whenever GitHub releases a new stable version. An
# upstream default change would alter response payloads with no local code
# change -- a silent behavioral shift that could break parsing logic or
# produce subtly wrong data without any error signal.
#
# By pinning to "2022-11-28" (the oldest stable version available as of the
# mirror's initial implementation), the API contract is made explicit:
# upgrading to a newer version is a deliberate, tested action rather than an
# accidental side-effect of a GitHub deployment. When GitHub eventually
# deprecates this version the pipeline will start receiving a 400-level
# error response that surfaces in the run logs as a clear failure, prompting
# an intentional migration to a newer version after validation against the
# new response shape.
_API_VERSION = {"X-GitHub-Api-Version": "2022-11-28"}


def api_headers() -> dict[str, str]:
    """Return the headers to send with a GitHub API request.

    Always includes the JSON ``Accept`` header and the
    ``X-GitHub-Api-Version`` pin (see ``_API_VERSION`` above). When a
    ``GITHUB_TOKEN`` (or the shorter ``GH_TOKEN`` used by the gh CLI)
    environment variable is set, an ``Authorization: Bearer <token>`` header
    is added so the request counts against the authenticated rate limit.
    With no token present the request is still made, just anonymously and
    rate-limited.

    Why the fallback chain: CI typically exports ``GITHUB_TOKEN`` while local
    developers who already use the gh CLI have ``GH_TOKEN`` in their shell --
    accepting both means neither audience needs extra setup.

    Fallback mechanics when BOTH variables are absent: no ``Authorization``
    header is attached at all and the request goes out anonymously. That is
    a deliberate degrade-don't-fail choice -- a one-off local run works fine
    within GitHub's 60 requests/hour anonymous budget -- but it is made
    visible rather than silent: `fetch_git_tree` emits a one-time stderr
    warning on the first anonymous call of each run, and if the anonymous
    budget is exhausted anyway (403/429), the raised error message names the
    remedy (set either variable) so the operator never has to diagnose a
    bare "403 Forbidden".

    The token is attached to the request and *never* logged or included in
    any error message; callers must preserve that when handling failures.
    """
    headers = {**_JSON_ACCEPT, **_API_VERSION}
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def _warn_if_rate_limit_nearly_exhausted(headers: Mapping[str, str] | None) -> None:
    """Emit a one-time stderr warning when GitHub's rate limit runs low.

    Reads the ``X-RateLimit-Remaining`` header that GitHub attaches to every
    API response. When the value parses as an integer below
    ``_RATE_LIMIT_WARN_THRESHOLD``, a single warning is printed to stderr and
    the module-level ``_rate_limit_warning_emitted`` latch suppresses any
    repetition for the rest of the process run (see the flag's comment for
    why one emission per run is the right frequency). The point is lead
    time: an operator reading a scheduled run's log learns the budget is
    almost gone while the run is still SUCCEEDING, instead of discovering it
    from the hard 403/429 failure of a later run.

    Every non-actionable input is silently ignored -- a missing header (e.g.
    a proxy that strips response headers), an unparseable value, or ``None``
    headers. ``None`` happens when `fetch_git_tree` is driven through a stub
    of ``get_with_retry`` that returns a plain ``str``: the real fetch path
    returns the ``ResponseText`` subclass that carries the headers, but the
    public return type is plain ``str``, so the caller reaches the headers
    via ``getattr`` and must tolerate their absence. A warning that cried
    wolf on malformed input would train operators to ignore the real alert.

    Args:
        headers: The response headers of a successful GitHub API call, or
            ``None`` when they are unavailable.
    """
    global _rate_limit_warning_emitted
    if _rate_limit_warning_emitted or headers is None:
        return
    raw = headers.get("X-RateLimit-Remaining")
    if raw is None:
        return
    try:
        remaining = int(raw)
    except TypeError, ValueError:
        # A non-numeric header value (proxy corruption, a future API change)
        # says nothing about the budget -- skip silently rather than guess.
        return
    if remaining >= _RATE_LIMIT_WARN_THRESHOLD:
        return
    _rate_limit_warning_emitted = True
    # Raw ``print`` to stderr rather than a call into ``mirror.reporting``,
    # for the same layer-boundary reasons documented at the auth warning in
    # `fetch_git_tree`; the message follows the same ``  warning: <text>``
    # convention documented in ``mirror.reporting``'s module docstring.
    print(
        "  warning: GitHub API rate limit nearly exhausted "
        f"({remaining} requests remaining in the current hourly window). "
        "Set GITHUB_TOKEN or GH_TOKEN to raise the limit to 5,000/hr, or "
        "delay the next run until the window resets.",
        file=sys.stderr,
    )


def fetch_git_tree(
    client: httpx.Client, *, repo: str, branch: str
) -> list[dict[str, Any]]:
    """Fetch the full recursive git tree of ``repo``@``branch`` via the API.

    Performs the single ``GET /repos/{repo}/git/trees/{branch}?recursive=1``
    call that discovery for GitHub-backed sources is built on, and returns
    the response's ``"tree"`` list: one dict per filesystem entry in the
    repository. Each dict carries at minimum these keys (the GitHub API may
    include additional keys that callers should ignore for forward-compat):

    * ``"path"`` (str) -- the full file path from the repository root, e.g.
      ``"docs/en/configuration/config-files.md"``. This is what callers use
      to filter entries by directory prefix (``DOCS_PREFIX``) and file
      extension (``.md``);
    * ``"type"`` (str) -- the git object type: ``"blob"`` for files,
      ``"tree"`` for directories, ``"commit"`` for submodules. Callers
      typically skip everything that is not ``"blob"``;
    * ``"sha"`` (str) -- the SHA-1 hash of the git object, provided
      implicitly by the Git data model and not used by the mirror (the
      mirror fetches full file content from raw.githubusercontent.com
      rather than via the blob API, so the tree-entries' SHAs are
      informational only).

    Callers filter that list down to the Markdown files their docs tree
    consists of.

    Two failure modes are converted into loud, actionable errors instead of
    being allowed to corrupt the mirror:

    * **Rate limiting.** An HTTP 403 or 429 from this endpoint almost always
      means an *unauthenticated* request hit GitHub's anonymous rate ceiling
      (60 requests/hour per IP) -- easily reached by a scheduled job or a
      shared CI egress IP. The raised :class:`FetchError` names the remedy
      (set ``GITHUB_TOKEN``/``GH_TOKEN``) so the operator does not have to
      diagnose a bare "403 Forbidden". The status is read from the
      structured ``FetchError.status_code`` attribute, never by
      string-matching the message.
    * **Truncation.** The git-trees API caps its response size and flags
      oversized replies with ``"truncated": true`` instead of erroring.
      Continuing with a partial tree would make discovery return an
      incomplete page list, and the pipeline would interpret the missing
      pages as deleted upstream and remove their mirrored files from disk.
      A truncated response therefore raises ``RuntimeError`` naming the
      repo, turning silent data loss into a visible failure that says
      exactly why the run refused to proceed.

    Independently of those failure modes, a SUCCESSFUL response whose
    ``X-RateLimit-Remaining`` header shows the hourly budget nearly spent
    triggers a one-time stderr warning (see
    `_warn_if_rate_limit_nearly_exhausted`), so operators get ahead of
    rate-limit exhaustion before scheduled runs start failing.
    """
    url = f"https://api.github.com/repos/{repo}/git/trees/{branch}?recursive=1"
    # Emit a one-time warning to stderr on the first unauthenticated (no
    # Authorization header) call of each run. The warning explains what the
    # GitHub anonymous rate limit is (60 requests per hour per source IP) and
    # names the remedy (set GITHUB_TOKEN or GH_TOKEN) so that operators seeing
    # the warning in cron logs know exactly what to do without having to
    # search documentation or diagnose a bare "403 Forbidden" / "429 Too Many
    # Requests" in a later failure.
    #
    # The "one-time" behavior is controlled by the module-level
    # _auth_warning_emitted flag above: it starts as False and is flipped to
    # True after the first emission, suppressing subsequent warnings across
    # all calls within the same process run. This matters because the pipeline
    # mirrors multiple GitHub-backed sources (Codex CLI, Kimi Code, OpenCode),
    # each calling fetch_git_tree independently, and a wall of three identical
    # warnings per run would desensitize operators instead of alerting them.
    global _auth_warning_emitted
    headers = api_headers()
    if "Authorization" not in headers and not _auth_warning_emitted:
        _auth_warning_emitted = True
        # Deliberate layer boundary: this is a raw ``print`` to stderr rather
        # than a call into the presentation layer (``mirror.reporting``).
        # ``reporting`` sits ABOVE ``core`` in the dependency direction -- it
        # imports ``core.diff``, ``core.manifest``, and ``core.page`` to
        # format their results -- so a ``core`` module importing ``reporting``
        # would invert that layering and couple a low-level network helper to
        # the console-reporting machinery. This helper must also stay usable
        # on its own (source adapters call it during discovery, potentially
        # before the pipeline's reporting/log-file context is set up, and
        # tests drive it directly), so it cannot assume any reporting
        # initialization has happened. To keep the OUTPUT consistent with the
        # rest of the tool despite the raw print, the message below follows
        # the exact ``  warning: <text>``-on-stderr convention documented in
        # ``mirror.reporting``'s module docstring.
        print(
            "  warning: no GITHUB_TOKEN or GH_TOKEN set -- GitHub API requests "
            "will be unauthenticated (rate limit: 60/hr per IP). Set either "
            "environment variable to raise the limit to 5,000/hr.",
            file=sys.stderr,
        )
    try:
        tree_json = get_with_retry(client, url, extra_headers=headers)
    except FetchError as exc:
        if exc.status_code in (403, 429):
            raise FetchError(
                f"{exc} -- set GITHUB_TOKEN or GH_TOKEN to avoid GitHub API "
                "rate limits for unauthenticated requests. If a token is already "
                "set, verify that it has SSO authorization for the organization.",
                # Preserve the original HTTP status code through the error
                # re-wrapping. FetchError.status_code is the machine-readable
                # contract that callers and upstream error handlers use to
                # distinguish between different failure modes (for example,
                # 403 Forbidden vs. 429 Too Many Requests) without
                # string-parsing the error message. If we omitted this
                # argument, the re-wrapped error would carry
                # status_code=None, breaking that contract and forcing
                # downstream consumers to fall back on fragile, locale-
                # sensitive message matching to decide whether the failure
                # was a rate limit vs. an authorization error.
                status_code=exc.status_code,
            ) from exc
        raise
    # Inspect the rate-limit bookkeeping header BEFORE parsing the body: the
    # header reflects the remaining budget after this request regardless of
    # whether the payload turns out to be parseable, so a malformed-body
    # failure below must not skip the early warning. ``getattr`` is used
    # because ``get_with_retry`` is typed (and stubbed in tests) as returning
    # a plain ``str`` -- only the real fetch path returns the ``ResponseText``
    # subclass that carries the response headers, and a plain string simply
    # skips the check (see `_warn_if_rate_limit_nearly_exhausted`).
    _warn_if_rate_limit_nearly_exhausted(getattr(tree_json, "headers", None))
    try:
        data = json.loads(tree_json)
    except json.JSONDecodeError as exc:
        # The response body received from GitHub is not valid JSON, which
        # is an unexpected condition -- the git-trees endpoint always
        # returns a JSON document on success, and any non-JSON body
        # indicates a problem such as a proxy returning an HTML error
        # page, a corrupted transport stream, or GitHub serving a
        # non-JSON error payload masquerading as a 200. Whatever the
        # cause, there is no tree data to parse, so the pipeline must
        # stop rather than guess. The raised FetchError includes both
        # the repo/branch identifiers and the underlying JSON parser's
        # error text so that operators can investigate without reading
        # raw response dumps.
        raise FetchError(
            f"Invalid JSON from GitHub API for {repo}@{branch}: {exc}"
        ) from exc
    # The parsed JSON must be an object at the top level. ``json.loads`` can
    # also produce a list or a scalar (e.g. a proxy serving ``[]`` or a bare
    # JSON string with a 200 status); calling ``.get()`` on such a value would
    # escape as a bare ``AttributeError`` far from its root cause, breaking the
    # module's contract of surfacing every unexpected payload shape as a
    # descriptive ``FetchError`` that names the repo and branch.
    if not isinstance(data, dict):
        raise FetchError(
            f"GitHub API response for {repo}@{branch} has unexpected "
            f"top-level type {type(data).__name__}; expected JSON object"
        )
    # Check for the "truncated" flag that the git-trees API sets when the
    # response exceeds its internal size cap. The API does NOT return an
    # error status code in this case -- it returns HTTP 200 with
    # "truncated": true and a partial tree. Continuing with a partial tree
    # would cause the pipeline to discover only a subset of pages, and the
    # mirror logic would interpret the missing pages as deleted upstream,
    # triggering their removal from disk. This silent data loss is far
    # worse than a hard failure, so a truncated response raises a
    # RuntimeError with a message that names the repo and branch and makes
    # the consequence explicit ("would delete mirrored pages"), ensuring
    # the operator cannot miss or misinterpret the severity.
    if data.get("truncated"):
        raise RuntimeError(
            f"GitHub tree listing for {repo}@{branch} was truncated; "
            "refusing incomplete discovery (would delete mirrored pages)."
        )
    # Verify that the response data contains the expected "tree" key before
    # continuing. A well-formed response from the git-trees API always includes
    # a "tree" key whose value is a list of entry dicts, but an HTTP 200 with
    # an unexpected payload shape (for example, a future API version that
    # changes the response schema, or a proxy caching issue returning stale
    # or corrupted JSON) could omit it entirely. Raising FetchError here
    # rather than silently returning [] ensures the pipeline fails loudly
    # with a clear message naming the repo and branch, instead of producing a
    # zero-page discovery that the caller would interpret as "all docs were
    # deleted" and trigger removal of every mirrored file on disk.
    if "tree" not in data:
        raise FetchError(
            f"GitHub API response for {repo}@{branch} is missing the 'tree' key"
        )
    tree = data["tree"]
    # The "tree" value must be a list of entry dicts (each describing one
    # filesystem entry in the repository). A malformed response that carries
    # the "tree" key but with a different JSON type (such as null, a string,
    # or a plain object) would crash the caller with a confusing
    # AttributeError or TypeError when it tries to iterate over the result.
    # This isinstance check acts as a belt-and-suspenders guard that raises a
    # descriptive FetchError instead of letting a subtle type mismatch
    # propagate as an unhelpful runtime exception far from its root cause.
    if not isinstance(tree, list):
        raise FetchError(
            f"GitHub API response for {repo}@{branch} has 'tree' key with "
            f"unexpected type {type(tree).__name__}; expected list"
        )
    # Every element of the tree list must be a dict (one per filesystem
    # entry, carrying at least "path" and "type" -- see the docstring). The
    # list-ness check above does not imply element dict-ness: a proxy-
    # corrupted or future-schema payload could be a list of strings or
    # scalars, and callers immediately do ``entry["path"]`` /
    # ``entry.get(...)`` on each element, which would escape as a cryptic
    # ``TypeError`` deep inside a source adapter. Checking here keeps this
    # module's contract: every unexpected payload shape surfaces as a
    # descriptive ``FetchError`` that names the repo, the branch, and the
    # offending element's position and type.
    for position, entry in enumerate(tree):
        if not isinstance(entry, dict):
            raise FetchError(
                f"GitHub API response for {repo}@{branch} has a 'tree' "
                f"element at index {position} with unexpected type "
                f"{type(entry).__name__}; expected object"
            )
    return tree


def fetch_latest_release_tag(client: httpx.Client, *, repo: str) -> str | None:
    """Fetch the latest release tag name for *repo* via the GitHub API.

    Queries ``GET /repos/{repo}/releases/latest`` with standard GitHub API headers
    and extracts the ``tag_name`` property (stripping any leading 'v' and surrounding
    whitespace).

    Returns the stripped version string if found and valid, or ``None``.
    """
    url = f"https://api.github.com/repos/{repo}/releases/latest"
    headers = api_headers()
    try:
        res_text = get_with_retry(client, url, extra_headers=headers)
    except FetchError as exc:
        if exc.status_code in (403, 429):
            raise FetchError(
                f"{exc} -- set GITHUB_TOKEN or GH_TOKEN to avoid GitHub API "
                "rate limits for unauthenticated requests. If a token is already "
                "set, verify that it has SSO authorization for the organization.",
                status_code=exc.status_code,
            ) from exc
        raise
    _warn_if_rate_limit_nearly_exhausted(getattr(res_text, "headers", None))
    try:
        data = json.loads(res_text)
    except json.JSONDecodeError as exc:
        raise FetchError(
            f"Invalid JSON from GitHub API for {repo} releases/latest: {exc}"
        ) from exc
    if not isinstance(data, dict):
        raise FetchError(
            f"GitHub API response for {repo} releases/latest has unexpected "
            f"top-level type {type(data).__name__}; expected JSON object"
        )
    tag = data.get("tag_name")
    if isinstance(tag, str):
        return extract_version(tag)
    return None
