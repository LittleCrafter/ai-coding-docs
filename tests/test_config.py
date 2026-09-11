"""Tests for the shared mirror configuration (mirror.config).

The version pins here are deliberately loose: the released version value
lives in pyproject.toml (the single source of truth) and changes with every
release, so the tests around the resolution chain assert only the *contract*
-- non-emptiness, and that the User-Agent embeds whatever was resolved --
never a literal version string.

The one deliberate exception is
``test_resolve_version_tier3_hardcoded_fallback``, which asserts the exact
string ``"0.2.0"``. That is not a release pin: ``"0.2.0"`` is the literal
hardcoded LAST-RESORT value inside ``config._resolve_version``, returned only
when both the installed metadata and pyproject.toml are unreadable. Asserting
it verbatim is what fails the suite when someone edits the fallback, which is
the drift this test exists to catch; the released version is irrelevant to
it.
"""

from __future__ import annotations

import pytest

import mirror
from mirror import config


def test_tool_version_is_non_empty_string():
    """TOOL_VERSION must always resolve to a non-empty string: it is stamped
    into the User-Agent and re-exported as ``mirror.__version__``, and the
    importlib.metadata fallback (a hardcoded default matching pyproject.toml,
    used when the project is not installed) guarantees it is never None."""
    assert isinstance(config.TOOL_VERSION, str)
    assert config.TOOL_VERSION


def test_user_agent_embeds_tool_version():
    """The User-Agent string must embed TOOL_VERSION, so upstream operators
    can tell which release of the mirror is hitting their servers. Asserting
    containment (not the whole string) keeps the test stable across rebrands
    of the agent name."""
    assert config.TOOL_VERSION in config.USER_AGENT
    assert config.USER_AGENT.startswith("ai-coding-docs-mirror/")


def _no_installed_dist(name: str) -> str:
    """``importlib.metadata.version`` stand-in that always reports the
    package is not installed, forcing ``_resolve_version`` past tier 1."""
    from importlib.metadata import PackageNotFoundError

    raise PackageNotFoundError(name)


def test_resolve_version_tier2_reads_pyproject_toml(monkeypatch, tmp_path):
    """Tier 2: when the installed-distribution metadata is unavailable, the
    version must be read from the ``[project]`` table of ``pyproject.toml``
    at REPO_ROOT -- the fallback that keeps ``python -m mirror`` runs from a
    source checkout consistent with the installed package."""
    monkeypatch.setattr(config, "_dist_version", _no_installed_dist)
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nversion = "9.9.9"\n', encoding="utf-8"
    )
    monkeypatch.setattr(config, "REPO_ROOT", tmp_path)
    assert config._resolve_version() == "9.9.9"


def test_resolve_version_tier3_hardcoded_fallback(monkeypatch, tmp_path):
    """Tier 3: when neither the installed metadata nor a readable
    pyproject.toml exists at REPO_ROOT, the hardcoded fallback version is
    returned so the tool always boots (e.g. embedded in a foreign project
    whose root carries no pyproject.toml of its own)."""
    monkeypatch.setattr(config, "_dist_version", _no_installed_dist)
    monkeypatch.setattr(config, "REPO_ROOT", tmp_path)  # no pyproject.toml
    assert config._resolve_version() == "0.2.0"


def test_package_version_matches_config():
    """``mirror.__version__`` is a re-export of ``config.TOOL_VERSION`` --
    both resolve pyproject.toml's version via the same code path, so they
    must never disagree."""
    assert mirror.__version__ == config.TOOL_VERSION


def test_prettier_version_consistent():
    """Prettier is pinned in four separate files across the repo.  If
    one gets bumped and the others are missed, formatting behaviour can drift
    between CI, pre-commit, `make`, and the README quick-start.  This test
    reads all four files and verifies the version string is identical."""
    import re

    # -- file paths relative to the repo root --------------------------------
    files = {
        "Makefile": config.REPO_ROOT / "Makefile",
        ".pre-commit-config.yaml": config.REPO_ROOT / ".pre-commit-config.yaml",
        ".github/workflows/lint.yml": config.REPO_ROOT / ".github/workflows/lint.yml",
        "README.md": config.REPO_ROOT / "README.md",
    }

    # This gate is non-hermetic BY DESIGN: it reads the real working-tree
    # files at ``config.REPO_ROOT`` because its whole purpose is to check the
    # repo's own consistency. ``REPO_ROOT`` is env-overridable via
    # ``AI_CODING_DOCS_ROOT`` (see config.py), so when that override points
    # at a different tree -- or when the package runs from an installed copy
    # that has no repo dotfiles -- the pinned files may simply not exist at
    # the resolved root. That is an environment condition, not a version
    # mismatch, so skip rather than fail spuriously (or, worse, pass/fail
    # against an unrelated tree).
    missing = [label for label, path in files.items() if not path.exists()]
    if missing:
        pytest.skip(
            "repo-consistency gate needs the real working tree; not found at "
            f"resolved REPO_ROOT ({config.REPO_ROOT}): {', '.join(missing)}"
        )

    # -- regex: match "prettier@<semver>" anywhere in a line -----------------
    pattern = re.compile(r"prettier@(\d+\.\d+\.\d+)")

    versions: dict[str, str] = {}

    for label, path in files.items():
        # Read the file and find the first prettier version reference.
        text = path.read_text(encoding="utf-8")
        match = pattern.search(text)
        assert match is not None, f"No prettier@<version> found in {label} ({path})"
        versions[label] = match.group(1)

    # -- all four versions must be identical ---------------------------------
    # If they disagree, print every value so the fix is obvious.
    distinct_versions = set(versions.values())
    assert len(distinct_versions) == 1, (
        f"Prettier version mismatch across repo files: {versions}"
    )


# --- Numeric configuration boundary assertions --------------------------------
#
# The four scalar knobs below share one contract: each must be a number of the
# expected type and sit inside a defensible range. The bounds are load-bearing
# guardrails (they protect the retry loop, memory usage, and run duration),
# not exact-value pins, so they are grouped into a single parametrized test;
# the per-knob rationale for each bound lives in the comments on each
# parameter set below.


@pytest.mark.parametrize(
    ("attr", "allowed_types", "lower", "lower_inclusive", "upper"),
    [
        # MAX_RETRIES is the upper bound of the range(1, MAX_RETRIES + 1) call
        # in get_with_retry, so both the type and the sign matter: 0 or
        # negative would make the retry loop skip every attempt entirely,
        # treating all failures as permanent, and a non-integer would crash
        # the range call. Above 20, a single-page failure would stall the run
        # for minutes (with exponential backoff capped at MAX_RETRY_DELAY).
        # The current value of 3 is intentionally low -- documentation pages
        # are static content that rarely needs more than one retry for a
        # transient network hiccup.
        pytest.param("MAX_RETRIES", int, 1, True, 20, id="MAX_RETRIES"),
        # MAX_RESPONSE_BYTES guards against OOM crashes from oversized
        # upstream responses (the mirror reads the full body into memory for
        # Markdown validation). The 1 KiB floor asserted here is a coarse
        # sanity bound, not the value's real design constraint: the mirrored
        # pages span 56 bytes (docs/kimi-code/index.md) to ~2.2 MiB
        # (docs/codex-cli/codex-manual.md), so what the cap must
        # actually clear is the LARGEST page, and a floor of 1 KiB only
        # rules out a catastrophically mis-scaled constant. Above 1 GiB the
        # guard would effectively disable itself and risk an OOM crash on a
        # misconfigured upstream serving multi-gigabyte payloads.
        pytest.param(
            "MAX_RESPONSE_BYTES",
            int,
            1024,
            True,
            1024 * 1024 * 1024,
            id="MAX_RESPONSE_BYTES",
        ),
        # RETRY_DELAY is the base delay between retry attempts. It must be
        # strictly positive -- 0 would turn retries into a tight loop
        # hammering the upstream server -- and at most 60 seconds, above
        # which a single transient-failure page would stall the run for
        # minutes before the first retry even fires.
        pytest.param("RETRY_DELAY", (int, float), 0, False, 60, id="RETRY_DELAY"),
        # RATE_LIMIT_DELAY is the polite delay between consecutive page
        # fetches within a source. 0 is legal (no delay between pages --
        # useful for dry-run testing against local fixtures); above 10s the
        # mirror would be extremely slow for sources with hundreds of pages.
        pytest.param(
            "RATE_LIMIT_DELAY", (int, float), 0, True, 10, id="RATE_LIMIT_DELAY"
        ),
        # DEFAULT_WORKERS is the default thread concurrency for page fetching.
        # It must be at least 1 (sequential fallback) and bounded to avoid
        # excessive thread spawning.
        pytest.param("DEFAULT_WORKERS", int, 1, True, 32, id="DEFAULT_WORKERS"),
    ],
)
def test_numeric_config_bounds(attr, allowed_types, lower, lower_inclusive, upper):
    """Each numeric config knob must resolve to a number of the expected type
    and stay inside its defensible range (see the per-parameter comments above
    for why each bound exists). The same three assertions -- type, lower
    bound, upper bound -- apply to every knob; only ``RETRY_DELAY`` has a
    strict (exclusive) lower bound, because a zero base delay is harmful
    there while a zero rate-limit delay is a legitimate configuration."""
    value = getattr(config, attr)
    assert isinstance(value, allowed_types), (
        f"{attr} must be of type {allowed_types}, got {type(value).__name__}"
    )
    if lower_inclusive:
        assert value >= lower, f"{attr} must be >= {lower}, got {value}"
    else:
        assert value > lower, f"{attr} must be > {lower}, got {value}"
    assert value <= upper, f"{attr} must be <= {upper}, got {value}"


# --- REPO_ROOT derivation error paths -----------------------------------------
#
# Both derivation modes (the AI_CODING_DOCS_ROOT override and the
# ``__file__``-based fallback) validate the resolved root by requiring a
# pyproject.toml there. The guards run at module level, so these tests
# execute the config source in a fresh module namespace (via
# ``spec_from_file_location``) with a doctored environment or file
# location -- the real imported ``mirror.config`` module is never touched.


def _exec_config_module(path, monkeypatch=None):
    """Execute the config source at *path* in an isolated module namespace,
    returning the resulting module object (or propagating its import-time
    RuntimeError). The caller controls ``__file__`` by choosing *path* and
    the environment via monkeypatch, exactly like a real import would."""
    import importlib.util

    spec = importlib.util.spec_from_file_location("config_under_test", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_repo_root_override_must_be_a_checkout(monkeypatch, tmp_path):
    """An ``AI_CODING_DOCS_ROOT`` override that points at a directory
    WITHOUT a pyproject.toml must raise at import time: a non-checkout
    directory would make the mirror write into the wrong tree just as
    silently as a misderived fallback root, so the override is validated
    with the same marker as the ``__file__`` fallback."""
    not_a_checkout = tmp_path / "not-a-checkout"
    not_a_checkout.mkdir()
    monkeypatch.setenv("AI_CODING_DOCS_ROOT", str(not_a_checkout))
    with pytest.raises(RuntimeError, match="AI_CODING_DOCS_ROOT"):
        _exec_config_module(config.__file__)


def test_repo_root_derivation_requires_pyproject_toml(monkeypatch, tmp_path):
    """With no ``AI_CODING_DOCS_ROOT`` override set, a ``__file__``-derived
    root that lacks a pyproject.toml must raise at import time instead of
    silently writing into a wrong directory tree (the exact shape of a
    non-editable install, where ``parents[2]`` lands in site-packages)."""
    from pathlib import Path

    monkeypatch.delenv("AI_CODING_DOCS_ROOT", raising=False)
    # Copy the real config source into a fake layout whose parents[2] is an
    # empty tree, then execute it from there.
    fake_config = tmp_path / "scripts" / "mirror" / "config.py"
    fake_config.parent.mkdir(parents=True)
    fake_config.write_text(
        Path(config.__file__).read_text(encoding="utf-8"), encoding="utf-8"
    )
    with pytest.raises(RuntimeError, match="pyproject.toml"):
        _exec_config_module(fake_config)


def test_whitespace_only_root_env_var_is_ignored(monkeypatch):
    """A whitespace-only ``AI_CODING_DOCS_ROOT`` (``"  "``) must be treated as
    UNSET: such a value is trivially produced by shell snippets like
    ``export AI_CODING_DOCS_ROOT="$MAYBE_EMPTY_VAR"``, and honouring it would
    turn ``Path("  ")`` into a bogus relative path instead of falling back to
    the normal ``__file__``-based derivation. The value is stripped in
    ``config.py``, so a whitespace-only value must resolve ``REPO_ROOT``
    exactly as if the variable were never set."""
    import importlib
    from pathlib import Path

    monkeypatch.setenv("AI_CODING_DOCS_ROOT", "  \t  ")
    try:
        importlib.reload(config)
        # Falls back to the ``__file__``-based derivation, exactly as when
        # the variable is absent.
        assert config.REPO_ROOT == Path(config.__file__).resolve().parents[2]
    finally:
        # Reload with the override removed so the module's global state
        # (REPO_ROOT, DOCS_DIR, TOP_INDEX_PATH) is restored to what the rest
        # of the suite expects.
        monkeypatch.delenv("AI_CODING_DOCS_ROOT", raising=False)
        importlib.reload(config)
