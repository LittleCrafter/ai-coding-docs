"""Tests for the GitHub API helpers (mirror.core.github)."""

from __future__ import annotations

import json

import pytest
from conftest import _FakeClient, _Resp, tree_client
from mirror.core import fetch, github


def test_api_headers_anonymous_without_token(monkeypatch):
    """With no token in the environment the request must go out anonymously:
    an Authorization header must be absent entirely (not empty), otherwise
    GitHub would reject the request instead of serving it at the public rate
    limit. Both supported env vars are cleared to isolate this case."""
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.delenv("GH_TOKEN", raising=False)
    headers = github.api_headers()
    assert headers["Accept"] == "application/vnd.github+json"
    assert "Authorization" not in headers


def test_api_headers_attaches_token(monkeypatch):
    """A GITHUB_TOKEN must be turned into a `Bearer` Authorization header
    while the required GitHub API Accept header is kept."""
    monkeypatch.delenv("GH_TOKEN", raising=False)
    monkeypatch.setenv("GITHUB_TOKEN", "abc123")
    headers = github.api_headers()
    assert headers["Authorization"] == "Bearer abc123"
    assert headers["Accept"] == "application/vnd.github+json"


def test_api_headers_prefers_github_token(monkeypatch):
    """When both env vars are set, GITHUB_TOKEN wins over GH_TOKEN. This pins
    the precedence order so CI and local `gh` setups behave predictably."""
    monkeypatch.setenv("GITHUB_TOKEN", "primary")
    monkeypatch.setenv("GH_TOKEN", "secondary")
    headers = github.api_headers()
    assert headers["Authorization"] == "Bearer primary"


def test_api_headers_uses_gh_token_alone(monkeypatch):
    """When only GH_TOKEN is set (no GITHUB_TOKEN), it must be used as the
    Bearer token. This covers the local developer who uses `gh auth login`
    (which sets GH_TOKEN) but has no GITHUB_TOKEN -- the fallback chain must
    not silently skip auth on such a machine."""
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.setenv("GH_TOKEN", "gh-token-value")
    headers = github.api_headers()
    assert headers["Authorization"] == "Bearer gh-token-value"


def test_api_headers_includes_x_github_api_version():
    """The returned headers must include ``X-GitHub-Api-Version`` pinning the
    REST API version so that an upstream default change never silently shifts
    the response shape under us."""
    headers = github.api_headers()
    assert headers["X-GitHub-Api-Version"] == "2022-11-28"


# --- fetch_git_tree: shared tree listing for GitHub-backed sources -----------


def test_fetch_git_tree_returns_tree_entries():
    """The happy path: a 200 git-trees response yields its ``"tree"`` list
    verbatim (both blob and tree entries), so the source adapters can apply
    their own per-source filtering on top."""
    entries = [
        {"type": "blob", "path": "docs/config.md"},
        {"type": "tree", "path": "docs"},
    ]
    client = tree_client(entries)
    tree = github.fetch_git_tree(client, repo="openai/codex", branch="main")
    assert tree == entries


def test_fetch_git_tree_warns_about_anonymous_requests_exactly_once(
    monkeypatch, capsys
):
    """An unauthenticated fetch must emit the rate-limit warning to stderr
    exactly once per process, no matter how many times fetch_git_tree is
    called.

    The pipeline mirrors several GitHub-backed sources in one run, each
    calling fetch_git_tree independently; without the module-level
    ``_auth_warning_emitted`` latch, every call would repeat the same
    warning and operators would start ignoring it. The flag is reset via
    monkeypatch (not direct assignment) so the latch state is restored after
    the test and cannot leak into other tests in the same process. Both
    token env vars are cleared so api_headers() builds an anonymous header
    set regardless of the developer's or CI's environment."""
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.delenv("GH_TOKEN", raising=False)
    # Module-level latch reset for pytest-xdist parallel test safety.
    monkeypatch.setattr(github, "_auth_warning_emitted", False)

    tree_json = json.dumps({"truncated": False, "tree": []})
    monkeypatch.setattr(
        github, "get_with_retry", lambda client, url, *, extra_headers=None: tree_json
    )

    for _ in range(3):
        github.fetch_git_tree(object(), repo="openai/codex", branch="main")

    captured = capsys.readouterr()
    assert captured.err.count("no GITHUB_TOKEN or GH_TOKEN set") == 1


def test_fetch_git_tree_raises_on_truncated_response():
    """A ``"truncated": true`` reply must raise, not return a partial tree:
    incomplete discovery would make the pipeline delete the missing pages'
    mirrored files. The error names the repo so the failure is actionable."""
    client = tree_client([], truncated=True)
    with pytest.raises(RuntimeError, match="openai/codex"):
        github.fetch_git_tree(client, repo="openai/codex", branch="main")


def _rate_limit_error(status):
    """Build the FetchError shape get_with_retry produces for an HTTP status
    failure: the message plus the structured ``status_code`` attribute that
    fetch_git_tree keys its rate-limit mapping on."""
    return fetch.FetchError(
        f"HTTP {status} for https://api.github.com/x", status_code=status
    )


@pytest.mark.parametrize("status", [403, 429])
def test_fetch_git_tree_adds_token_hint_on_rate_limit(monkeypatch, status):
    """A 403/429 from the git-trees API almost always means an anonymous
    request hit GitHub's rate ceiling, so the re-raised FetchError must
    point at the GITHUB_TOKEN/GH_TOKEN remedy. The mapping keys on the
    structured status_code, never on the message text."""
    err = _rate_limit_error(status)

    def _raise(client, url, *, extra_headers=None):
        raise err

    monkeypatch.setattr(github, "get_with_retry", _raise)
    with pytest.raises(fetch.FetchError, match="GITHUB_TOKEN") as exc_info:
        github.fetch_git_tree(object(), repo="openai/codex", branch="main")
    assert exc_info.value.__cause__ is err


def test_fetch_git_tree_reraises_other_statuses_without_hint(monkeypatch):
    """A non-rate-limit failure (e.g. 404 for a renamed repo/branch) must be
    re-raised unchanged -- appending a rate-limit hint to it would send the
    operator chasing the wrong fix."""
    err = _rate_limit_error(404)

    def _raise(client, url, *, extra_headers=None):
        raise err

    monkeypatch.setattr(github, "get_with_retry", _raise)
    with pytest.raises(fetch.FetchError) as exc_info:
        github.fetch_git_tree(object(), repo="openai/codex", branch="main")
    assert exc_info.value is err


@pytest.mark.parametrize("status", [403, 429])
def test_fetch_git_tree_rate_limit_hint_preserves_status_code(monkeypatch, status):
    """The rate-limit re-raise wraps the original FetchError in a new one with
    an actionable message -- but the structured ``status_code`` attribute must
    survive the wrap. Consumers rely on it (never on the message text) to tell
    "the page is gone" (404) from "the upstream is rate-limiting us" (429), so
    dropping it here would silently break the FetchError contract for exactly
    the errors where the status matters most."""
    err = _rate_limit_error(status)

    def _raise(client, url, *, extra_headers=None):
        raise err

    monkeypatch.setattr(github, "get_with_retry", _raise)
    with pytest.raises(fetch.FetchError, match="GITHUB_TOKEN") as exc_info:
        github.fetch_git_tree(object(), repo="openai/codex", branch="main")
    assert exc_info.value.status_code == status


def test_fetch_git_tree_malformed_200_without_tree_key_raises_fetch_error():
    """A 200 response that is valid JSON but has no ``"tree"`` key must raise
    ``FetchError`` instead of silently returning an empty list. Silent ``[]``
    fallback makes a malformed response indistinguishable from "this repo has
    zero Markdown files" -- if the caller's zero-page guard ever has a bug,
    data loss results. Raising ``FetchError`` ensures the pipeline fails loudly
    with a clear message naming the repo and branch, so the operator can
    diagnose the upstream API change rather than discovering missing docs
    weeks later."""
    client = _FakeClient([_Resp(200, json.dumps({"truncated": False}))])
    with pytest.raises(fetch.FetchError, match="missing the 'tree' key"):
        github.fetch_git_tree(client, repo="openai/codex", branch="main")


def test_fetch_git_tree_malformed_200_with_non_dict_top_level_raises_fetch_error():
    """A 200 response that is valid JSON but whose top-level value is not an
    object (e.g. a JSON array, as a misbehaving proxy or a future API version
    might serve) must raise ``FetchError`` instead of crashing with a bare
    ``AttributeError`` when the code calls ``.get("truncated")`` on the
    parsed value. A bare ``AttributeError`` would surface as an opaque stack
    trace pointing at an internal line of ``fetch_git_tree`` -- the operator
    would have to reproduce the run with a debugger to learn that the payload
    shape was wrong. A ``FetchError`` instead names the repo, the branch, and
    the actual top-level type received, so an upstream payload-shape change
    is diagnosable from the CI log alone."""
    client = _FakeClient([_Resp(200, json.dumps(["not", "a", "dict"]))])
    with pytest.raises(fetch.FetchError, match="unexpected top-level type list"):
        github.fetch_git_tree(client, repo="openai/codex", branch="main")


def test_fetch_git_tree_malformed_200_with_non_list_tree_key_raises_fetch_error():
    """A 200 response carrying a ``"tree"`` key whose value is not a list (e.g.
    a string or dict) must raise ``FetchError`` with a descriptive type-mismatch
    message instead of crashing with ``TypeError`` or ``AttributeError`` when
    the caller tries to iterate over it. A bare crash would surface as an
    opaque stack trace; a ``FetchError`` names the repo, the branch, and the
    actual type received, so an upstream API shape change is diagnosable from
    the CI log alone."""
    client = _FakeClient(
        [_Resp(200, json.dumps({"truncated": False, "tree": "not a list"}))]
    )
    with pytest.raises(fetch.FetchError, match="unexpected type str"):
        github.fetch_git_tree(client, repo="openai/codex", branch="main")


def test_fetch_git_tree_malformed_200_with_non_dict_tree_elements_raises_fetch_error():
    """A 200 response whose ``"tree"`` value IS a list but whose elements are
    not objects (e.g. a list of strings from a proxy-corrupted payload) must
    raise ``FetchError`` instead of letting the source adapters crash later
    with a cryptic ``TypeError`` on ``entry["path"]``. The top-level shape
    checks (dict / ``"tree"`` key / list-ness) do not imply element
    dict-ness; this pins the module's contract that EVERY unexpected payload
    shape surfaces as a descriptive ``FetchError`` naming the repo, the
    branch, and the offending element's position and type."""
    client = _FakeClient(
        [_Resp(200, json.dumps({"truncated": False, "tree": ["docs/a.md", 42]}))]
    )
    with pytest.raises(
        fetch.FetchError, match="element at index 0 with unexpected type str"
    ):
        github.fetch_git_tree(client, repo="openai/codex", branch="main")


# --- fetch_git_tree: X-RateLimit-Remaining early warning ---------------------


def _tree_client_with_rate_limit_header(remaining):
    """Build a fake client whose single git-trees response carries a given
    ``X-RateLimit-Remaining`` header value (or no such header at all when
    ``remaining`` is None).

    ``_Resp`` starts with an empty header dict, so the header is set by plain
    assignment after construction. A real httpx response exposes the same
    ``headers`` mapping with case-INSENSITIVE lookup; the stub's plain dict
    is case-sensitive, so the canonical header casing used here is also what
    keeps the production ``.get("X-RateLimit-Remaining")`` lookup working
    against the stub."""
    body = json.dumps({"truncated": False, "tree": []})
    resp = _Resp(200, body)
    if remaining is not None:
        resp.headers["X-RateLimit-Remaining"] = remaining
    return _FakeClient([resp])


def test_fetch_git_tree_warns_when_rate_limit_nearly_exhausted(monkeypatch, capsys):
    """An ``X-RateLimit-Remaining`` value below the warning threshold must
    emit the early-warning line to stderr: the whole point of the check is
    that the operator learns the budget is almost gone while the run is
    still succeeding, instead of discovering it from a later run's hard
    403/429 failure. The latch is reset via monkeypatch (not direct
    assignment) so its state is restored after the test and cannot leak
    into other tests in the same process."""
    monkeypatch.setattr(github, "_rate_limit_warning_emitted", False)
    client = _tree_client_with_rate_limit_header("3")
    github.fetch_git_tree(client, repo="openai/codex", branch="main")
    captured = capsys.readouterr()
    assert captured.err.count("rate limit nearly exhausted") == 1


@pytest.mark.parametrize("remaining", ["10", "5000", "not-a-number", None])
def test_fetch_git_tree_no_rate_limit_warning_when_budget_healthy(
    monkeypatch, capsys, remaining
):
    """No warning may fire when the header is at or above the threshold
    ("10", "5000"), unparseable ("not-a-number" -- a proxy-corrupted or
    future-schema value says nothing about the budget), or absent entirely
    (None). A warning that cried wolf on benign input would train operators
    to ignore the real alert."""
    monkeypatch.setattr(github, "_rate_limit_warning_emitted", False)
    client = _tree_client_with_rate_limit_header(remaining)
    github.fetch_git_tree(client, repo="openai/codex", branch="main")
    captured = capsys.readouterr()
    assert "rate limit nearly exhausted" not in captured.err


def test_fetch_git_tree_rate_limit_warning_emitted_once(monkeypatch, capsys):
    """Two consecutive low-remaining responses must produce exactly one
    warning: the pipeline mirrors several GitHub-backed sources per run,
    each calling fetch_git_tree independently, and repeating the alert for
    every call would desensitize operators instead of informing them. The
    second call must therefore be swallowed by the module-level latch."""
    monkeypatch.setattr(github, "_rate_limit_warning_emitted", False)
    body = json.dumps({"truncated": False, "tree": []})
    first = _Resp(200, body)
    first.headers["X-RateLimit-Remaining"] = "2"
    second = _Resp(200, body)
    second.headers["X-RateLimit-Remaining"] = "1"
    client = _FakeClient([first, second])

    github.fetch_git_tree(client, repo="openai/codex", branch="main")
    github.fetch_git_tree(client, repo="openai/codex", branch="main")

    captured = capsys.readouterr()
    assert captured.err.count("rate limit nearly exhausted") == 1


# --- fetch_latest_release_tag ------------------------------------------------


def test_fetch_latest_release_tag_success():
    """fetch_latest_release_tag returns stripped tag name on 200."""
    client = _FakeClient([_Resp(200, '{"tag_name": "v2.0.0"}')])
    assert github.fetch_latest_release_tag(client, repo="openai/codex") == "2.0.0"


def test_fetch_latest_release_tag_missing_tag_or_invalid():
    """fetch_latest_release_tag returns None when tag_name is missing."""
    client = _FakeClient([_Resp(200, "{}")])
    assert github.fetch_latest_release_tag(client, repo="openai/codex") is None


def test_fetch_latest_release_tag_malformed_json():
    """fetch_latest_release_tag raises FetchError on unparseable JSON."""
    client = _FakeClient([_Resp(200, "not json")])
    with pytest.raises(fetch.FetchError):
        github.fetch_latest_release_tag(client, repo="openai/codex")
