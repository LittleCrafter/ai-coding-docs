#!/usr/bin/env bash
# ==============================================================================
# Helper Script: Local Execution of the Docs Mirror Scraper
# ==============================================================================
# This script prepares the Python virtual environment and executes the scraper.
# It is designed to be run manually or triggered automatically via cron tasks
# or systemd timers.
#
# What it does, in order:
#   1. Refuse to run when SOURCED instead of executed (`source run_local.sh` /
#      `. run_local.sh`): the `exit` statements and `set -e` below would
#      otherwise terminate the user's own interactive shell session, so the
#      guard bails out before any of them can fire;
#   2. Enable strict error handling (`set -euo pipefail`) so that every later
#      failure aborts the script immediately with a non-zero status instead
#      of being silently skipped over -- the behaviour cron and systemd rely
#      on for their failure alerting;
#   3. Install an EXIT trap that logs a timestamped line whenever the script
#      exits non-zero -- FAILED for real errors, INTERRUPTED for signal
#      cancellations (Ctrl+C / SIGTERM) -- for cron log tracking;
#   4. Resolve the script's own location THROUGH SYMLINKS and cd into the
#      repository root (so relative paths always resolve the same, no matter
#      where or how the script was invoked from);
#   5. Verify the resolved directory really is the repository root (pyproject.toml
#      present), failing loudly if the symlink dance landed outside the tree;
#   6. Verify `uv` is installed and on PATH (clear error in minimal cron/container envs
#      before a confusing 'exit 127');
#   7. `uv sync --quiet` to bring .venv in line with pyproject.toml / uv.lock;
#   8. `uv run mirror-docs "$@"` to run the mirror pipeline, forwarding any
#      arguments straight through to the Python CLI.
#
# The script exits with the exit code of the failing command (or of the mirror
# run itself): 0 on success, non-zero if uv sync fails, an entire SOURCE
# fails, or the pipeline itself crashes -- which is what cron (via MAILTO) and
# systemd (via the unit's failed state) use to alert you. A whole-source
# failure is a handled, reported condition: the pipeline logs it, skips that
# source, and returns 1 at the end. Individual page-fetch failures are
# different: they are carried forward by the pipeline (reported on stderr,
# previous page content kept in place) and do NOT affect the exit code, so a
# flaky upstream page never pages you at 3am.
#
# ------------------------------------------------------------------------------
# Manual usage (arguments are forwarded verbatim to `mirror-docs`):
#   ./scripts/run_local.sh                      # update every source
#   ./scripts/run_local.sh --dry-run            # discover only, write nothing
#   ./scripts/run_local.sh --source google-antigravity-cli
#   ./scripts/run_local.sh --force              # rewrite every file
#
# ------------------------------------------------------------------------------
# Examples of automated scheduling:
#
#   1. Cron scheduling (run `crontab -e` to configure). Runs every 3 hours,
#      appending all output (stdout + stderr) to a log file. Use an absolute
#      path to the repo; cron's working directory and PATH are minimal:
#      0 */3 * * * cd /path/to/ai-coding-docs && ./scripts/run_local.sh >> /tmp/ai-coding-docs.log 2>&1
#
#   2. Systemd user timer (drop-in units under ~/.config/systemd/user/):
#
#      # ai-coding-docs.service
#      [Service]
#      Type=oneshot
#      WorkingDirectory=/path/to/ai-coding-docs
#      ExecStart=/path/to/ai-coding-docs/scripts/run_local.sh
#
#      # ai-coding-docs.timer  (OnCalendar=*-*-* 00/3:00:00, Persistent=true:
#      # every 3 hours at minute :00, catching up on runs missed while the
#      # machine was off)
#      [Timer]
#      OnCalendar=*-*-* 00/3:00:00
#      Persistent=true
#
#      [Install]
#      WantedBy=timers.target
#
#      Then: systemctl --user daemon-reload
#            systemctl --user enable --now ai-coding-docs.timer
#      Output lands in the journal: journalctl --user -u ai-coding-docs.service
# ==============================================================================

# Guard against sourcing: this script uses 'exit' and 'set -e' at the top
# level, which would immediately terminate the user's interactive shell session
# (closing their terminal window or shell prompt) if the script were sourced
# instead of executed. Sourcing happens when a user runs `source run_local.sh`
# or `. run_local.sh` -- either intentionally or via a typo in PATH resolution.
# Since crontab lines and systemd units always execute scripts (never source
# them), a sourcing mistake is exclusively a manual-invocation problem. The
# guard checks whether "${BASH_SOURCE[0]}" (the script's own path) matches
# "${0}" (the name the shell used to invoke the current context). When the script
# is sourced, ${0} will usually evaluate to the shell executable (for example,
# "-bash" or "/bin/bash"), whereas ${BASH_SOURCE[0]} will evaluate to the path
# of this script itself. Since these differ, we can safely detect that the script
# has been sourced rather than executed. In that case we print an error to stderr and
# return (or exit, if return is also unavailable in the sourced context).
if [[ "${BASH_SOURCE[0]}" != "${0}" ]]; then
    echo "Error: run_local.sh must be executed, not sourced." >&2
    # `return` is the correct way out of a sourced script (it unwinds the
    # source without killing the caller's shell), but `return` is only valid
    # in a sourced or function context: if this branch were ever reached in a
    # context where `return` itself is illegal, it would fail, and WITHOUT the
    # `|| exit 1` fallback execution would simply fall through and run the
    # rest of the script -- including `set -e` and the `exit` statements below
    # -- inside the user's interactive shell. The fallback keeps the guard
    # airtight: one way or the other, the script body never runs here.
    # Note: the SC2317 suppression below is required because the checker
    # flags the `exit 1` as unreachable -- `return` succeeds in every normal
    # sourced context -- but this apparent dead code is a deliberate
    # fallback, not a mistake.
    # shellcheck disable=SC2317
    return 1 2>/dev/null || exit 1
fi

# Enable strict error-handling modes in bash. These three options work together
# to convert silent or ambiguous failures into immediate, loud exits with a
# non-zero status -- critical for a script that runs unattended under cron or
# systemd, where nobody watches stderr in real time.
#
#   -e (errexit):  Exits immediately if any command returns a non-zero exit
#                  status. Without it, a failing `uv sync` (e.g. network
#                  timeout, disk full) would be silently followed by a `uv run`
#                  on a stale or half-installed .venv, producing confusing
#                  import errors that point nowhere near the real cause. With
#                  -e, the script stops at the first hiccup, and the EXIT trap
#                  logs a clear FAILED line for cron to surface via MAILTO.
#
#   -u (nounset):  Treats references to unset variables as an error and exits
#                  immediately. Guards against typos in variable names silently
#                  expanding to empty strings (e.g. "$DIR" vs "$DIRR"). In a
#                  script that changes directories and runs commands against
#                  relative paths, an empty expansion could cause the script to
#                  operate on the wrong directory or pass unintended arguments
#                  to commands -- both of which are hard to debug from a log
#                  file after the fact.
#
#   -o pipefail:   Changes how a pipeline's exit status is computed. By
#                  default, a pipeline's status is simply the exit status of
#                  its LAST command, regardless of whether earlier commands
#                  failed; with pipefail, the pipeline instead returns the
#                  rightmost non-zero status of any command in it (still zero
#                  only when every command succeeded). This matters the
#                  moment output is piped through `tee` for logging: without
#                  pipefail, a failing mirror run piped to a succeeding `tee`
#                  would still exit 0 and look perfectly healthy to cron,
#                  hiding the actual failure from MAILTO and systemd alerts.
set -euo pipefail

# ------------------------------------------------------------------------------
# Failure trap: one greppable line per failed or interrupted run.
# ------------------------------------------------------------------------------
# WHY: under cron, this script's output is typically appended to a log file
# (see the crontab example above) that nobody reads until something looks
# stale. `set -e` can make the script die at many different points (uv sync
# failure, network outage mid-run, a full disk), and the raw error text is not
# always obviously a *failure* when skimmed between two successful runs. This
# EXIT trap fires on every script exit; when the exit status is non-zero it
# appends a single, unambiguous, ISO 8601-timestamped FAILED line (to stderr,
# so `grep FAILED` / `grep -E '\] .*FAILED'` on the log finds every incident,
# and the exit code tells you where to start reading). On success ($? = 0)
# the trap stays silent -- the explicit "run complete" line at the bottom of
# the script already marks success, and duplicate noise would make the log
# harder to scan. The trap is installed BEFORE any fallible command runs, so
# even a failure in the cd dance below is caught.
#
# on_exit: The callback registered with `trap on_exit EXIT`. Bash calls this
# function automatically when the script exits for any reason -- whether normal
# completion, a `set -e`-triggered abort, an explicit `exit 1` from a guard
# clause, or an external signal (SIGINT/SIGTERM). The exit status is captured
# immediately from $? at the top of the function before any other command
# overwrites it. The function then classifies the exit code into one of three
# cases and logs accordingly:
#   0       → silent exit (success is already announced by the final echo);
#   129/130/131/143 → logged as "INTERRUPTED" (operator- or system-cancelled);
#   any other non-zero → logged as "FAILED" (a real malfunction to investigate).
on_exit() {
    local exit_code=$?
    # Exit codes 130 and 143 mean the run was interrupted from the OUTSIDE
    # rather than failing on its own. Bash encodes signal deaths as
    # 128 + signal_number in the $? exit status:
    #   130 = 128 + SIGINT  (2)  -- the operator pressed Ctrl+C on a
    #                              manual run, or the terminal sent an
    #                              interrupt signal to the process group;
    #   143 = 128 + SIGTERM (15) -- the environment sent a termination
    #                              signal (`systemctl stop`, a `timeout`
    #                              wrapper, container or host shutdown).
    # These are deliberate cancellations initiated from outside the script,
    # not malfunctions of the mirror itself, so they get their own wording
    # ("INTERRUPTED"): an operator who cancels a run should not see an
    # alarming "FAILED" line for their own Ctrl+C, and `grep FAILED` on the
    # cron log should surface only incidents that actually need attention.
    if [ "$exit_code" -eq 129 ] || [ "$exit_code" -eq 130 ] || [ "$exit_code" -eq 131 ] || [ "$exit_code" -eq 143 ]; then
        echo "[$(date -u +'%Y-%m-%dT%H:%M:%SZ')] Docs mirror run INTERRUPTED (exit code ${exit_code} -- cancelled by signal, not a mirror failure)." >&2
    elif [ "$exit_code" -ne 0 ]; then
        echo "[$(date -u +'%Y-%m-%dT%H:%M:%SZ')] Docs mirror run FAILED (exit code ${exit_code})." >&2
    fi
}
trap on_exit EXIT

# In addition to the EXIT trap above, we must explicitly map the INT (Ctrl+C),
# TERM (termination request), HUP, and QUIT signals to exit with specific
# status codes (130, 143, 129, and 131 respectively). This guarantees that
# when these signals interrupt the script, the EXIT trap receives the exact
# signal codes expected to classify the run as INTERRUPTED rather than FAILED.
trap 'exit 129' HUP
trap 'exit 130' INT
trap 'exit 131' QUIT
trap 'exit 143' TERM

# Log a start-of-run marker with an ISO 8601 UTC timestamp. This gives every
# invocation a clearly identifiable beginning in the log file, which is
# essential for correlating output with the cron/systemd schedule and for
# spotting runs that started but never finished (a missing "complete" line
# below marks a crash or hang that the EXIT trap should also have caught).
echo "[$(date -u +'%Y-%m-%dT%H:%M:%SZ')] Starting docs mirror run..."

# ------------------------------------------------------------------------------
# Working directory: always the repository root.
# ------------------------------------------------------------------------------
# WHY the dance: every later step (uv sync, uv run, the mirror's own relative
# paths to docs/) assumes the current directory is the repo root. Cron starts
# jobs in $HOME, systemd units may set any WorkingDirectory, and a human may
# invoke the script from anywhere -- so we must cd to the repo root
# ourselves instead of trusting the caller's cwd.
#
# Resolves the absolute physical path of the script directory
# Validates that the directory exists before proceeding.
# The assignment is kept separate from the `readonly` declaration so a
# failing command substitution cannot be masked by the declaration's exit
# status (shellcheck SC2155).
SCRIPT_DIR="$(cd -P -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
readonly SCRIPT_DIR
cd "$SCRIPT_DIR/.." || { echo "Error: failed to cd to repo root ($SCRIPT_DIR/..)." >&2; exit 1; }

# Verify that the resolved directory is indeed the repository root by checking
# for the presence of pyproject.toml. This catches cases where physical directory
# resolution (cd -P / pwd -P) resolves to a directory outside the expected
# repository tree -- for example, if an operator accidentally creates a
# cross-filesystem symlink or the script is invoked from a container mount that
# maps the script but not the rest of the repository. Without this check,
# subsequent commands (uv sync, uv run) would fail with confusing error
# messages about missing lock files or import errors, making it difficult to
# diagnose the real root cause from a cron log at 3am.
if [[ ! -f "pyproject.toml" ]]; then
    # We use the shell builtin ${PWD} instead of $(pwd) to avoid spawning an
    # unnecessary subshell, keeping execution faster and strictly within bash.
    echo "Error: resolved directory ${PWD} does not contain pyproject.toml -- is this the repo root?" >&2
    echo "Resolved from: $SCRIPT_DIR" >&2
    exit 1
fi

# Verify that 'uv' is installed and on PATH before attempting to use it.
# In minimal cron environments or containers, uv may not be present, and
# failing here with a clear message is much more useful than a raw
# "command not found" exit (code 127) buried in a log file.
if ! command -v uv >/dev/null 2>&1; then
    echo "Error: 'uv' is required but not found on PATH." >&2
    echo "Install uv: https://docs.astral.sh/uv/getting-started/installation/" >&2
    exit 1
fi

# Synchronize virtual environment packages using 'uv'.
# This checks pyproject.toml / uv.lock and installs or updates dependencies
# (such as httpx, beautifulsoup4, html2text) into the local .venv folder silently.
# Using --quiet suppresses unnecessary installation logs during automated runs.
# This is intentionally run on every invocation, not just once: after a `git
# pull` that changed dependencies, the next scheduled run self-heals its
# environment instead of failing on an outdated .venv.
uv sync --quiet

# Execute the entry point script 'mirror-docs' (mapped to mirror.cli:main) inside
# the synchronized virtual environment using 'uv run'.
# "$@" expands all arguments passed to this shell script and forwards them
# verbatim to the Python entrypoint (quoted form preserves arguments that
# contain spaces or globs, e.g. a source name with special characters).
uv run mirror-docs "$@"

# Log a completion marker with an ISO 8601 UTC timestamp. This line tells an
# operator scanning the log that the script reached its natural end (exit code 0
# from `uv run mirror-docs`) as opposed to being aborted mid-stream by a signal
# or a `set -e` failure. Cron/systemd use the exit code to determine alerting,
# but the log timestamp here provides independent observability: a missing
# "complete" line when the start line is present indicates an unhandled crash
# (one that bypassed the EXIT trap, e.g. a `kill -9`), while an exit code of 0
# but a missing complete line would expose a logic bug in the EXIT handler
# itself.
echo "[$(date -u +'%Y-%m-%dT%H:%M:%SZ')] Docs mirror run complete."
