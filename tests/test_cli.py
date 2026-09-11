"""Smoke tests for the command-line entry point (mirror.cli).

The CLI is deliberately thin (parse argv, call pipeline.run), so these tests
only pin the wiring: flag forwarding, exit-code propagation, and fail-fast
rejection of an unknown --source. pipeline.run is faked throughout, so no
network or docs/ tree is ever touched.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest
from mirror import cli, config, pipeline


@pytest.mark.parametrize(
    ("argv", "expected"),
    [
        # Use a hardcoded valid source name (kimi-code is always registered)
        # rather than indexing into the live pipeline.SOURCES registry: if the
        # registry is ever empty (broken import, refactored module), this would
        # IndexError with a confusing message. A hardcoded name fails with a
        # clear "invalid choice" message from argparse instead.
        pytest.param(
            ["--source", "kimi-code", "--dry-run", "--force"],
            {
                "force": True,
                "dry_run": True,
                "only": "kimi-code",
                "log_file": None,
                "workers": config.DEFAULT_WORKERS,
            },
            id="all-flags",
        ),
        pytest.param(
            [],
            {
                "force": False,
                "dry_run": False,
                "only": None,
                "log_file": None,
                "workers": config.DEFAULT_WORKERS,
            },
            id="no-flags-defaults",
        ),
    ],
)
def test_main_forwards_argv_to_pipeline_run(monkeypatch, argv, expected):
    """Pin the argv -> pipeline.run mapping in both directions:

    - all-flags: --source/--dry-run/--force must arrive as the
      only/dry_run/force keyword arguments. A wrong mapping here would
      silently misinterpret every invocation, so it is worth pinning directly.
    - no-flags-defaults: the no-flags invocation (the common scheduled-run
      form) must forward the argparse defaults verbatim: force=False,
      dry_run=False, only=None (meaning: every registered source). A flipped
      default here would make a plain ``mirror-docs`` run silently rewrite
      every file or mirror nothing.
    """
    seen = {}

    def fake_run(force, dry_run, only, log_file, workers=config.DEFAULT_WORKERS):
        seen.update(
            force=force,
            dry_run=dry_run,
            only=only,
            log_file=log_file,
            workers=workers,
        )
        return 0

    monkeypatch.setattr(pipeline, "run", fake_run)
    assert cli.main(argv) == 0
    assert seen == expected


@pytest.mark.parametrize(
    ("argv", "expected_workers"),
    [
        (["--concurrency", "4"], 4),
        (["--workers", "2"], 2),
    ],
)
def test_main_forwards_concurrency_and_workers_flags(
    monkeypatch, argv, expected_workers
):
    """--concurrency and --workers must forward the integer value to pipeline.run."""
    seen = {}

    def fake_run(**kwargs):
        seen.update(kwargs)
        return 0

    monkeypatch.setattr(pipeline, "run", fake_run)
    assert cli.main(argv) == 0
    assert seen.get("workers") == expected_workers


@pytest.mark.parametrize(
    "invalid_val",
    ["0", "-1", "abc"],
)
def test_main_rejects_invalid_concurrency(invalid_val):
    """--concurrency must reject values < 1 or non-integers with exit code 2."""
    with pytest.raises(SystemExit) as excinfo:
        cli.main(["--concurrency", invalid_val])
    assert excinfo.value.code == 2


# --- --locales flag parsing and validation -----------------------------------


def test_main_locales_flag_stores_validated_selection(monkeypatch):
    """``--locales pt-br,es`` must arrive at pipeline.run NOT as a keyword
    argument (pipeline.run does not accept it yet) but stored -- normalized
    (sorted, deduplicated) -- in the run-scoped holder
    config.ACTIVE_LOCALES, which the locale-capable source adapter reads
    during discovery. A wrong normalization here would make runs with
    differently-ordered flags behave differently."""
    seen = {}

    def fake_run(**kwargs):
        seen.update(kwargs)
        return 0

    monkeypatch.setattr(pipeline, "run", fake_run)
    assert cli.main(["--locales", "pt-br,es"]) == 0
    assert config.ACTIVE_LOCALES == ("es", "pt-br")
    # pipeline.run must not receive the selection as a new keyword argument.
    assert "locales" not in seen


def test_main_locales_all_expands_to_known_locale_dirs(monkeypatch):
    """``--locales all`` must expand to the full set of locale codes the
    locale-capable source adapter knows (the adapter's KNOWN_LOCALE_DIRS is
    the single source of truth for what can be mirrored), sorted."""
    from mirror.sources.opencode import KNOWN_LOCALE_DIRS

    monkeypatch.setattr(pipeline, "run", lambda *args, **kwargs: 0)
    assert cli.main(["--locales", "all"]) == 0
    assert config.ACTIVE_LOCALES == tuple(sorted(KNOWN_LOCALE_DIRS))


def test_main_locales_tolerates_whitespace_and_duplicates(monkeypatch):
    """Whitespace around tokens (``"es, pt-br "``) and repeated codes
    (``es`` twice) must be tolerated; the stored selection is sorted and
    deduplicated."""
    monkeypatch.setattr(pipeline, "run", lambda *args, **kwargs: 0)
    assert cli.main(["--locales", "es, pt-br ,es"]) == 0
    assert config.ACTIVE_LOCALES == ("es", "pt-br")


@pytest.mark.parametrize(
    "bad_value",
    ["", "xx", "pt-br,xx", "pt-br,,es", ",pt-br", "pt-br,", "all,pt-br"],
)
def test_main_rejects_invalid_locales(bad_value, capsys):
    """--locales must fail fast with argparse's usage-error exit code 2 --
    never silently mirror fewer locales than requested -- for: an empty
    value, codes outside the known set, empty tokens in the list, and
    ``all`` mixed with explicit codes (a contradiction: ``all`` already
    includes every code)."""
    with pytest.raises(SystemExit) as excinfo:
        cli.main(["--locales", bad_value])
    assert excinfo.value.code == 2
    captured = capsys.readouterr()
    assert "--locales" in captured.err


@pytest.mark.parametrize(
    ("argv", "expected_path"),
    [
        # Long form: --log-file PATH.
        pytest.param(
            ["--source", "kimi-code", "--log-file", "run.log"],
            "run.log",
            id="long-form",
        ),
        # Short alias -l PATH (declared alongside --log-file in add_argument).
        pytest.param(["-l", "short.log"], "short.log", id="short-alias"),
    ],
)
def test_main_forwards_log_file_flag(monkeypatch, argv, expected_path):
    """Pin the argparse wiring for ``--log-file`` / ``-l``: the path string
    must arrive at ``pipeline.run`` as the ``log_file`` keyword argument. A
    refactor that renamed the argparse dest (e.g. reading ``args.l`` instead
    of ``args.log_file``) or dropped the ``-l`` short alias would silently
    regress to ``log_file=None`` for every invocation, and every other CLI
    test would still pass because they only assert the None case. Both the
    long form and the ``-l`` short alias declared in ``add_argument`` are
    exercised here so the whole wiring is pinned, not just the happy path."""
    seen = {}

    def fake_run(*args, **kwargs):
        seen.update(kwargs)
        return 0

    monkeypatch.setattr(pipeline, "run", fake_run)
    assert cli.main(argv) == 0
    assert seen["log_file"] == expected_path


def test_main_returns_pipeline_exit_code(monkeypatch):
    """main() must propagate pipeline.run's exit code verbatim (e.g. 1 after
    a partially failed run) so the console script's ``raise
    SystemExit(main())`` reflects the real outcome instead of always
    reporting success."""
    monkeypatch.setattr(pipeline, "run", lambda *args, **kwargs: 1)
    assert cli.main([]) == 1


def test_main_returns_130_on_keyboard_interrupt(monkeypatch):
    """A KeyboardInterrupt escaping pipeline.run (Ctrl+C mid-run) must become
    the RETURN VALUE 130, not a raw traceback dumped to the console.

    pipeline.run deliberately lets BaseException propagate so an operator
    interrupt aborts the whole run; the CLI's job is to translate that into
    the conventional shell exit status for SIGINT termination (128 + 2 =
    130, the convention grep and make follow), so cron logs and wrapper
    scripts see a clean, recognizable exit instead of a multi-line
    KeyboardInterrupt traceback that looks like a bug in the tool.

    The status is RETURNED (not raised as SystemExit) because main() has a
    plain int-return contract: every real entry point -- the ``mirror-docs``
    console script, ``python -m mirror``, and the ``__main__`` block in
    cli.py -- translates the returned int via ``raise SystemExit(main())``,
    so the observed process exit code is still exactly 130."""

    def fake_run(*args, **kwargs):
        raise KeyboardInterrupt

    monkeypatch.setattr(pipeline, "run", fake_run)
    assert cli.main([]) == 130


def test_main_rejects_unknown_source():
    """An unknown --source must fail fast at argument parsing: argparse's
    ``choices=`` raises SystemExit with code 2 (the standard usage-error
    exit) instead of letting a typo silently mirror nothing and exit 0."""
    with pytest.raises(SystemExit) as exc_info:
        cli.main(["--source", "not-a-source"])
    assert exc_info.value.code == 2


def test_main_help():
    """--help prints usage and exits with code 0."""
    with pytest.raises(SystemExit) as exc_info:
        cli.main(["--help"])
    assert exc_info.value.code == 0


def test_main_version_flag(capsys):
    """--version prints the resolved tool version and exits 0.

    argparse's built-in ``version`` action raises SystemExit(0) after
    printing, before pipeline.run() is reached, so the real (unfaked)
    pipeline is never involved and no network or docs/ tree is touched.
    The asserted version string is read back from config.TOOL_VERSION
    rather than hardcoded so the test keeps passing across version bumps.
    """
    with pytest.raises(SystemExit) as exc_info:
        cli.main(["--version"])
    assert exc_info.value.code == 0
    captured = capsys.readouterr()
    assert config.TOOL_VERSION in captured.out


def test_main_unwritable_log_file_exits_cleanly(tmp_path, capsys):
    """An unwritable --log-file path must fail cleanly, not with a traceback.

    The log path is placed UNDER A REGULAR FILE, so creating its parent
    directory raises NotADirectoryError (an OSError subclass) regardless of
    platform or user privileges -- unlike a chmod-based permission test,
    which silently passes when the suite runs as root. The failure happens
    inside pipeline.run's log-file setup, BEFORE the real pipeline builds
    its HTTP client, so this test exercises the real pipeline.run (not a
    fake) without touching the network or the docs/ tree.

    The contract being pinned: a one-line "!! ..." message on stderr (the
    same style reporting uses for source failures), the exact exit code 2
    (argparse's usage-error code -- the run never started, so there is no
    partial state to report as a mirror failure), and no raw traceback
    dumped to the console.
    """
    blocker = tmp_path / "not-a-directory"
    blocker.write_text("a regular file occupying the path")
    bad_log = str(blocker / "run.log")
    with pytest.raises(SystemExit) as exc_info:
        cli.main(["--log-file", bad_log])
    # pipeline._log_file_context translates the OSError into SystemExit(2):
    # exit 1 would mean "a source failed mid-run", which is not what happened.
    assert exc_info.value.code == 2
    captured = capsys.readouterr()
    assert "!!" in captured.err
    assert "Traceback" not in captured.err


def test_python_m_mirror_version_entrypoint_runs_cleanly():
    """End-to-end smoke test: ``python -m mirror --version`` must execute in
    a fresh interpreter and exit with status 0.

    Every other test in this file drives ``cli.main()`` in-process with a
    faked pipeline; this is the only one that exercises the real
    ``__main__.py`` entry point as a subprocess, so broken entry-point
    wiring (a bad import in ``__main__.py``, a missing ``main()`` call)
    cannot slip through. ``--version`` is used because argparse's version
    action prints and exits before ``pipeline.run()`` is ever reached -- no
    network and no docs/ tree is touched.

    The ``scripts/`` directory is prepended to ``PYTHONPATH`` explicitly so
    the subprocess can import the ``mirror`` package regardless of whether
    the project happens to be installed into the running venv. A short
    timeout keeps a hung interpreter from stalling the suite.
    """
    repo_root = Path(__file__).resolve().parent.parent
    env = os.environ.copy()
    env["PYTHONPATH"] = (
        str(repo_root / "scripts") + os.pathsep + env.get("PYTHONPATH", "")
    )
    result = subprocess.run(
        [sys.executable, "-m", "mirror", "--version"],
        cwd=repo_root,
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0
    assert config.TOOL_VERSION in result.stdout
    assert "Traceback" not in result.stderr


# --- --check-links standalone offline verification ---------------------------


def test_main_check_links_flag_success(monkeypatch):
    """--check-links without issues returns exit code 0."""
    from mirror.core import link_checker

    monkeypatch.setattr(
        link_checker, "check_source_links", lambda source, *args: ([], 1)
    )
    assert cli.main(["--check-links"]) == 0


def test_main_check_links_flag_failure(monkeypatch, tmp_path):
    """--check-links with issues returns exit code 1."""
    from mirror.core import link_checker

    fake_issue = link_checker.LinkIssue(
        file=tmp_path / "doc.md",
        line=10,
        target="./missing.md",
        reason="Target file does not exist",
    )
    monkeypatch.setattr(
        link_checker, "check_source_links", lambda source, *args: ([fake_issue], 1)
    )
    assert cli.main(["--check-links"]) == 1


def test_main_check_links_forwards_source_flag(monkeypatch):
    """--check-links --source <name> forwards the source filter."""
    from mirror.core import link_checker

    seen_source = []

    def fake_check(source, exempt_targets_by_source=None):
        seen_source.append(source)
        return [], 1

    monkeypatch.setattr(link_checker, "check_source_links", fake_check)
    assert cli.main(["--check-links", "--source", "kimi-code"]) == 0
    assert seen_source == ["kimi-code"]


def test_main_check_links_does_not_call_pipeline_run(monkeypatch):
    """--check-links executes standalone without invoking pipeline.run."""
    from mirror.core import link_checker

    monkeypatch.setattr(
        link_checker, "check_source_links", lambda source, *args: ([], 1)
    )

    def forbidden_run(*args, **kwargs):
        raise AssertionError("pipeline.run should not be called with --check-links")

    monkeypatch.setattr(pipeline, "run", forbidden_run)
    assert cli.main(["--check-links"]) == 0


@pytest.mark.parametrize(
    "incompatible_flag",
    [
        ["--dry-run"],
        ["--force"],
        ["--concurrency", "2"],
        ["--workers", "4"],
        ["--locales", "pt-br"],
    ],
)
def test_main_check_links_rejects_incompatible_flags(incompatible_flag, capsys):
    """--check-links combined with --dry-run, --force, concurrency, or
    --locales flags raises SystemExit(2)."""
    with pytest.raises(SystemExit) as exc_info:
        cli.main(["--check-links", *incompatible_flag])
    assert exc_info.value.code == 2
    captured = capsys.readouterr()
    assert "cannot be combined" in captured.err


def test_main_check_links_creates_and_writes_log_file(monkeypatch, tmp_path):
    """--check-links with --log-file tees output to the specified log path."""
    from mirror.core import link_checker

    monkeypatch.setattr(
        link_checker, "check_source_links", lambda source, *args: ([], 1)
    )
    log_path = tmp_path / "check_links.log"

    ret = cli.main(["--check-links", "--log-file", str(log_path)])
    assert ret == 0
    assert log_path.is_file()
    content = log_path.read_text(encoding="utf-8")
    assert "Link Verification" in content
    assert "0 broken internal links found" in content


def test_main_check_links_zero_scanned_files_warns_and_returns_1(monkeypatch, capsys):
    """--check-links returning 0 scanned files warns on stderr and exits with code 1."""
    from mirror.core import link_checker

    monkeypatch.setattr(
        link_checker, "check_source_links", lambda source, *args: ([], 0)
    )
    ret = cli.main(["--check-links", "--source", "kimi-code"])
    assert ret == 1
    captured = capsys.readouterr()
    assert "warning: no Markdown documentation files found" in captured.err
    assert "warning: no Markdown documentation files found" not in captured.out


def test_main_locales_warns_when_used_with_non_opencode_source(monkeypatch, capsys):
    """--locales specified with a non-opencode source prints an informational note to stderr."""
    monkeypatch.setattr(pipeline, "run", lambda **kwargs: 0)
    ret = cli.main(["--source", "claude-code", "--locales", "pt-br"])
    assert ret == 0
    captured = capsys.readouterr()
    assert "Note: --locales is only supported by opencode" in captured.err
