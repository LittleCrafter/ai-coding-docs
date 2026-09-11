"""Presentation layer: human-readable output for the docs-mirror pipeline.

The pipeline (``mirror.pipeline``) owns control flow and decides *what* to
report; this module owns *how* it is formatted and printed. Keeping the two
apart means the pipeline logic can be read (and unit-tested) without any console
I/O, and the wording/layout of every message lives in exactly one place.

Two deliberate design choices to know before "modernising" this module:

* **Plain ``print`` instead of a logging framework.** This tool is run by
  humans (manually, from cron, or from a systemd timer) and its entire output
  is the report. There are no log levels to filter, no handlers to configure,
  and no library code here that would need to stay silent when imported.
  Informational progress goes to stdout; per-page fetch failures and
  per-source pipeline failures go to stderr so ``run_local.sh >> log 2>&1``
  still captures everything while a ``2>/dev/null`` keeps the happy-path
  output clean. Introducing a logging framework here would add complexity
  (configuration boilerplate, handler setup) for zero observable benefit,
  since every invocation always writes a full report from start to finish --
  there is never a reason to suppress informational output conditionally.
* **Nothing here returns a value the pipeline depends on** -- each function is
  a pure side effect on stdout/stderr. That is intentional: call sites stay
  simple, and formatting can never accidentally influence control flow.
  Because the pipeline never reads a return value from any function in this
  module, adding or removing a printed line cannot introduce a logic bug in
  the caller, which keeps these two concerns (what happened vs. how to say
  it) truly decoupled rather than layered behind an abstraction that leaks.

Output formatting conventions (the whole "palette"): there are deliberately
NO ANSI color codes -- the output is routinely redirected into cron log
files and GitHub Actions logs, where escape sequences render as noise like
``[31m`` and break simple ``grep`` scanning. Visual hierarchy is instead
carried by a small set of textual markers, kept consistent so log searches
are predictable. The markers are chosen to be visually scannable in a plain
terminal as well as in a pager (``less``), in a CI step summary folded by
default, and in a flat text file saved to disk -- one set of conventions
works everywhere without conditional logic:

* ``== Title ==``       a source's run banner -- the only heading style;
  the equals signs make it stand out from any indented content below it
  even when the output is scrolled quickly.
* 3-space indent        progress and summary lines inside a source's run
                        (``fetching N page(s)...``, ``mirrored x/y | ...``);
                        three spaces rather than the more common two creates
                        a stronger visual distinction from the ``== Title ==``
                        banner above, while still leaving room on an 80-column
                        terminal for long page slugs on deeper-indented lines.
* 4-space indent        per-item detail lines (discovered slugs, per-page
                        fetch errors); the extra space relative to the 3-space
                        grouping line indicates that these are children or
                        sub-items of the section they follow.
* 2-space ``warning:``  a non-fatal degradation, on stderr; the ``warning:``
                        keyword is a greppable anchor that operators can search
                        for across runs without needing to remember module-
                        specific error codes.
* ``!!`` / ``!``        failure markers on stderr -- ``!!`` for a whole
                        source failing (catastrophic for that source, but the
                        pipeline continues to the next source), ``!`` for a
                        single page (recovered via carry-forward). The double
                        exclamation is intentionally more jarring than the
                        single one, giving a quick visual cue of severity.
* ``+ ~ > -``           structural-diff sigils in the summary's changes
                        line: added, modified, renamed, removed. These mirror
                        common version-control convention (``git diff
                        --stat``, ``diff -u``) for immediate familiarity.
"""

from __future__ import annotations

import sys
import traceback
from pathlib import Path
from typing import TYPE_CHECKING, Any

from . import config
from .core import diff
from .core.manifest import Manifest
from .core.page import Page

if TYPE_CHECKING:
    # Annotation-only import: ``from __future__ import annotations`` keeps the
    # ``MediaStageResult`` annotation below from being evaluated at runtime,
    # so the media module (which pulls in fetch/utils) is not imported just
    # to render this presentation layer.
    from .core import media


def header(title: str) -> None:
    """Banner printed at the start of a single source's run.

    Visually separates one source from the next in the (potentially long)
    multi-source output -- the only "heading" this layer produces. Even when
    there is only one source configured, the banner is still printed so the
    output always starts with the same visual structure, making automated
    parsing (e.g. ``grep '^== '``) work reliably without special-casing.
    The ``==`` wrapping was chosen over alternatives like ``---`` or ``###``
    because it reads identically in terminal, log file, and CI output -- it
    does not look like a horizontal rule (``---``) nor like a comment syntax
    (``###``) from any common configuration language.
    """
    print(f"== {title} ==")


def fetch_start(count: int) -> None:
    """Printed just before fetching the pages discovered for a source.

    Fetching is the slow, network-bound stage (rate-limited on purpose), so
    this line is the operator's cue that the run has moved from discovery to
    downloading, and how many requests to expect. The count is the number
    of unique page slugs discovered during the scrape phase -- it tells the
    operator roughly how long the upcoming network I/O phase will take (e.g.
    50 pages at roughly 1 second each after rate-limiting means about 50
    seconds). A large gap between this count and the final mirrored count in
    the summary line below can indicate network issues or unexpected fetch
    failures that warrant investigation.
    """
    print(f"   fetching {count} page(s)...")


def warning(message: str) -> None:
    """A non-fatal problem the pipeline recovered from. Reported to stderr.

    This is the generic counterpart to :func:`fetch_error` and
    :func:`source_error`: those two cover their specific failure shapes
    (per-page fetch failure, whole-source pipeline failure), while this helper
    exists for one-off degradations that do not fit neatly into either category
    -- for example, an unreadable manifest row in the top-level index whose
    entry silently falls back to default configuration values. The message is
    deliberately free-form: the caller owns the wording (because the specific
    degradation varies too much to enumerate), and this layer owns only the
    ``warning:`` prefix and the stderr routing. The leading two spaces match
    the visual indentation level of the surrounding per-source output, so the
    warning appears at the same nesting level as the progress and summary
    lines of the source it relates to.
    """
    print(f"  warning: {message}", file=sys.stderr)


def fetch_error(source_name: str, slug: str, exc: Exception) -> None:
    """A single page failed to fetch. Reported to stderr; never fatal.

    The pipeline carries the page's previous manifest entry forward (if it
    has one) and keeps going, so this message is informational: it exists so
    a pattern of repeated failures for the same slug is visible in the logs
    instead of being silently absorbed by the carry-forward mechanism. If the
    same slug fails across multiple consecutive runs, the operator will see
    the pattern in the logs (and can investigate the upstream URL) rather than
    discovering it only when a stale cached page becomes visibly outdated.

    The ``exc`` parameter is typed ``Exception``, not ``BaseException``: fetch
    failures are always ``core.fetch.FetchError`` (an ``Exception``
    subclass), and ``KeyboardInterrupt``/``SystemExit`` must abort the run
    rather than be formatted as a recoverable page failure. Using the narrower
    type documents this contract at the signature level, so anyone reading
    the function's interface knows immediately that it is not designed to
    swallow fatal signals.
    """
    print(f"    ! [{source_name}] failed: {slug} ({exc})", file=sys.stderr)


def source_error(name: str, exc: Exception) -> None:
    """An entire source failed mid-run. Reported to stderr; never fatal.

    Unlike :func:`fetch_error` (a single page, recovered via carry-forward),
    a source-level failure means the source's whole pipeline aborted -- its
    discovery, conversion, or write stage raised -- so nothing about its
    outcome is known and its manifest and files are left exactly as they
    were. ``pipeline.run`` catches the exception, prints this message, and
    moves on to the remaining sources, so this line is what keeps a failed
    source loud in the logs instead of being silently absorbed by the
    isolation mechanism; the process exit code (1) records that the run was
    partial, which is important for monitoring and alerting systems that
    watch the exit code of the cron job or systemd timer.

    The one-line summary is printed first (``!! [{name}] source failed:
    {exc}``) -- this is the greppable signal that an operator can find with
    ``grep '!!'`` across runs. The full traceback is printed to stderr
    immediately after the one-line summary, providing the complete call stack
    for diagnosis without needing to re-run locally with extra flags such as
    ``--traceback`` or ``PYTHONVERBOSE=1``. In CI and cron logs the traceback
    renders as a contiguous block directly below the summary line, so the two
    always travel together and the operator can scroll from the summary line
    down through the traceback to understand the failure path.

    The traceback is extracted from the exception object itself (via
    ``exc.__traceback__``) rather than from a separate captured stack --
    the Python runtime attaches the traceback to the exception when it is
    raised, so the exception already carries everything needed. This means
    callers do not need to pass any additional context (no ``sys.exc_info()``,
    no ``inspect.trace()``, no manual stack capture) -- they simply re-raise
    or let the exception propagate to ``pipeline.run``, which catches it and
    passes it here with the traceback intact.

    Note on the three-argument form of ``traceback.print_exception``: Python
    3.10 deprecated the single-argument shortcut (``print_exception(exc)``)
    in favour of the explicit three-argument form
    ``print_exception(type(exc), exc, exc.__traceback__)``, which avoids
    ambiguity when the exception has been re-raised or its traceback chain
    modified. This module uses the explicit form.

    The ``exc`` parameter is typed ``Exception`` rather than ``BaseException``
    on purpose: ``KeyboardInterrupt``/``SystemExit`` are never reported here
    (``pipeline.run`` deliberately does not catch them -- they must abort the
    run), so the narrower type documents that contract instead of implying
    they would be formatted as an ordinary source failure. Using
    ``BaseException`` would mislead readers into thinking that catching
    ``SystemExit`` here is intentional behaviour.
    """
    print(f"!! [{name}] source failed: {exc}", file=sys.stderr)
    traceback.print_exception(type(exc), exc, exc.__traceback__, file=sys.stderr)


def dry_run(title: str, pages: list[Page], old: Manifest | None) -> None:
    """List the pages discovered for a source, plus structural drift vs ``old``.

    This function is called when the pipeline is running in dry-run mode
    (``--dry-run`` flag): the source's pages are discovered and scraped
    normally, but nothing is fetched, written, or deleted. The added/gone
    lines compare the freshly discovered slugs against the previous manifest
    so a reviewer can spot pages that appeared or vanished without consuming
    network bandwidth or modifying files on disk. This is especially useful
    for reviewing configuration changes (such as a URL pattern update or a
    new scrape rule) before running the pipeline for real, because the
    structural diff gives early feedback about whether the change had the
    intended effect on page discovery.

    On a source's first-ever run (``old is None``) there is no previous
    manifest to compare against, so an explicit "no previous manifest"
    notice is printed instead of the diff lines. Without this distinction,
    a first-run dry run would produce no diff output and appear identical
    to a subsequent run that found no structural changes, which would be
    confusing for the operator.

    The ``pages`` parameter is the list of ``Page`` objects produced by the
    scrape phase -- each ``Page`` carries a ``slug`` (the unique identifier
    for that page within the source) and a URL to fetch. The ``old``
    parameter is the ``Manifest`` from the previous successful run, or
    ``None`` if this source has never succeeded. The function only reads
    ``old.files`` (the set of previously-known slugs) and does not modify
    anything.
    """
    print(f"[{title}] discovered {len(pages)} page(s):")
    for p in pages:
        print(f"    {p.slug}")
    if old is None:
        # First-ever run for this source: there is no manifest to diff
        # against, so the added/gone lines below cannot be produced. Say so
        # explicitly -- without this line a baseline dry run's output looks
        # identical to a run whose structural diff simply found nothing new,
        # and the operator cannot tell "first run, everything will be
        # created" from "no drift detected". The notice also serves as
        # documentation for new operators who may not know that a missing
        # manifest is the normal state of a source that has never been run.
        print("    (no previous manifest found; all discovered pages will be created)")
    else:
        new_slugs = {p.slug for p in pages}
        added = sorted(new_slugs - set(old.files))
        gone = sorted(set(old.files) - new_slugs)
        if added:
            print(f"    structurally new : {', '.join(added)}")
        if gone:
            print(f"    structurally gone: {', '.join(gone)}")
    print()


def summary(
    total: int,
    mirrored: int,
    written: int,
    deleted: int,
    failed: list[str],
    changes: diff.ChangeSet,
    whats_new_path: str | None,
    is_baseline: bool,
) -> None:
    """Print the per-source outcome line(s) at the end of a run.

    This function is called once per source after its pipeline run completes
    successfully; when the run fails, ``source_error`` is called instead. It prints the final summary block: how many pages were
    mirrored successfully, how many files were written to disk, how many
    were deleted, how many fetch failures occurred, and a compact structural
    diff showing added/modified/renamed/removed pages.

    A baseline run (``is_baseline=True``, meaning there was no previous
    manifest for this source) gets its own wording because the usual
    "written/deleted/changes" numbers are meaningless there -- by definition
    everything is new and nothing was deleted. The baseline summary simply
    reports how many pages out of the total were successfully mirrored, plus
    any failures, without the structural breakdown.

    For normal runs (``is_baseline=False``), two lines are printed:
    1. A counts line showing ``mirrored/total | written | deleted | failed``
       so the operator can see at a glance how the run did.
    2. A changes line with the compact sigils
       ``+added ~modified >renamed -removed`` that mirror the ChangeSet
       fields, so the structural diff can be read at a glance next to the
       file counts. Each sigil shows the count of pages in that category.

    The ``changes`` parameter is a ``diff.ChangeSet`` dataclass with
    ``added``, ``modified``, ``renamed``, and ``removed`` fields, each
    being a list of the corresponding record type: ``diff.Change`` records
    for ``added`` and ``removed`` (slug, title, source_url), ``diff.Modified``
    records for ``modified`` (same three fields, kept as a separate class so
    modification-specific fields can be added later), and ``diff.Rename``
    records for ``renamed`` (old_slug, new_slug, title, source_url,
    matched_by). ``changes.is_empty`` is ``True`` when all
    four lists are empty. The ``whats_new_path`` parameter is an optional
    path to a "what's new" index file that was generated during the run,
    shown as an extra line if present.

    The ``failed`` parameter is a list of page slugs that failed during
    fetch. Only the count is shown in the summary (the individual failure
    details were already printed by :func:`fetch_error` during the run).
    """
    if is_baseline:
        failed_suffix = f" | failed: {len(failed)}" if failed else ""
        print(f"   baseline created: {mirrored}/{total} pages.{failed_suffix}")
    else:
        # Align: | mirrored | written | deleted | failed |
        print(
            f"   mirrored {mirrored}/{total} | written: {written} | "
            f"deleted: {deleted} | failed: {len(failed)}"
        )
        # "No changes" is determined by the structural diff alone, not by
        # the file write counts: a ``--force`` run against unchanged upstream
        # content will rewrite all files to disk (so ``written > 0``) yet
        # produces an empty structural diff because the page slugs and their
        # content hashes are identical to the previous run. Printing a
        # ``+0 ~0 >0 -0`` changes line in that case would wrongly suggest
        # that something structural changed when nothing did. The
        # written/deleted counts on the line above already convey that files
        # were (re)written (or left untouched), so nothing is lost by
        # classifying such a run as "no changes detected". This decision
        # ensures the changes line always reflects meaningful structural
        # modifications rather than mechanical file I/O.
        if changes.is_empty:
            # ASCII-only on purpose: this orchestration layer emits no
            # non-ASCII bytes so a minimal/ASCII locale (e.g.
            # PYTHONCOERCECLOCALE=0) cannot raise UnicodeEncodeError on the
            # console. The em-dash that read naturally in a terminal was
            # replaced with the ASCII "--" stand-in.
            print("   no changes detected -- no structural modifications.")
        else:
            print(
                f"   changes: +{len(changes.added)} ~{len(changes.modified)} "
                f">{len(changes.renamed)} -{len(changes.removed)}"
            )
    if whats_new_path:
        print(f"   whats-new: {whats_new_path}")
    print()


def media_summary(result: media.MediaStageResult) -> None:
    """Print the media-asset outcome line for one source.

    Called by the pipeline when a source runs its media stage (i.e. its
    adapter declares a ``MEDIA`` config). The single informational line
    follows the three-space indentation convention of the other per-source
    lines and covers the four stage counters: assets downloaded to disk,
    assets whose bytes already matched (cached, no write), assets that could
    not be fetched or written (each already reported individually via
    :func:`warning` before this line), and pages whose references were
    rewritten. The prune counter is only shown when something was actually
    pruned, so a routine no-op run stays compact.
    """
    line = (
        f"   media assets: {result.assets_written} written, "
        f"{result.assets_cached} cached, {len(result.assets_failed)} failed, "
        f"{result.pages_rewritten} page(s) rewritten"
    )
    if result.files_pruned:
        line += f", {result.files_pruned} pruned"
    print(line)


def link_check_report(
    issues: list[Any],
    scanned_files: int = 0,
    source_name: str | None = None,
) -> None:
    """Print the human-readable summary of internal link verification.

    Reports whether all internal Markdown hyperlinks resolved successfully,
    warns if no Markdown files were scanned, or details every broken reference
    grouped by file.
    """
    scope = f": {source_name}" if source_name else ""
    header(f"Link Verification{scope}")
    if scanned_files == 0:
        # Routed through ``warning`` so this degradation carries the same
        # two-space ``warning:`` prefix and stderr channel as every other
        # non-fatal diagnostic, instead of mixing a warning into the stdout
        # report stream. The trailing blank line stays on stdout: it
        # terminates the report block begun by the header above.
        warning("no Markdown documentation files found to verify.")
        print()
        return

    if not issues:
        print("   link verification passed: 0 broken internal links found.")
        print()
        return

    by_file: dict[Path, list[Any]] = {}
    for issue in issues:
        by_file.setdefault(issue.file, []).append(issue)

    total_files = len(by_file)
    print(
        f"   found {len(issues)} broken internal link(s) across {total_files} file(s):"
    )
    for file_path, file_issues in by_file.items():
        try:
            rel_file = file_path.relative_to(config.REPO_ROOT)
        except ValueError:
            rel_file = file_path
        print(f"    {rel_file}:")
        for issue in file_issues:
            print(f"      ! line {issue.line}: [{issue.target}] ({issue.reason})")
    print()
