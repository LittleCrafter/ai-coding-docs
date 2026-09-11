"""Command-line entry point for the docs mirror.

This module is intentionally thin: it parses arguments and hands them to the
pipeline (:mod:`mirror.pipeline`). Everything that does real work -- discovery,
fetching, diffing, writing -- lives there, and all console output lives in
:mod:`mirror.reporting`. The layering is strictly ``cli -> pipeline ->
reporting``: the pipeline never sees ``sys.argv`` or ``argparse``, and the CLI
never sees a manifest, a diff, or a file write. That separation is what makes
the pipeline importable and drivable from tests or other scripts without any
console or argument-parsing concerns.

Run with no arguments to update every source::

    uv run mirror-docs                 # update every source
    uv run mirror-docs --source kimi-code
    uv run mirror-docs --dry-run       # discover only, write nothing
    uv run mirror-docs --force         # rewrite every file even if unchanged
    uv run mirror-docs --source opencode --locales pt-br,es  # add translations
"""

from __future__ import annotations

import argparse
import sys

from . import config


class _SourceNameChoices:
    """Lazy ``choices`` container for ``--source``.

    The real source names live on ``pipeline.SOURCES`` (one entry per
    source, each carrying ``CONFIG.name``). Importing ``pipeline`` pulls in
    every source adapter and their heavy third-party dependencies (httpx,
    beautifulsoup4, html2text) -- a cost the ``--version`` fast path must
    never pay. The import is therefore deferred to the first membership
    test, i.e. the first invocation that actually passes ``--source``;
    ``--version`` and bare runs never touch it. ``__iter__`` exists so
    argparse can list the choices in ``--help`` output.
    """

    def __contains__(self, name: object) -> bool:
        from . import pipeline

        return any(name == s.CONFIG.name for s in pipeline.SOURCES)

    def __iter__(self):
        from . import pipeline

        return (s.CONFIG.name for s in pipeline.SOURCES)


def _positive_int(value: str) -> int:
    """Parse and validate that *value* is a positive integer (>= 1)."""
    try:
        val = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"invalid integer value: {value!r}") from exc
    if val < 1:
        raise argparse.ArgumentTypeError(f"workers must be at least 1, got {val}")
    return val


def _locales(value: str) -> tuple[str, ...]:
    """Parse and validate the ``--locales`` flag value.

    Accepts ``all`` (meaning: every known locale) or a comma-separated list
    of locale codes; surrounding whitespace around each token is tolerated
    and duplicates are collapsed. The normalized result is a sorted tuple
    with no repeats, so runs with differently-ordered flags behave
    identically.

    The known codes come from the OpenCode adapter's ``KNOWN_LOCALE_DIRS``
    -- the single source of truth the adapter discovers against (a locale
    outside that set can never be mirrored, so accepting it here would be a
    silent no-op). The adapter is imported lazily so the ``--version`` fast
    path never pays for importing source adapters.

    Rejects (with argparse's standard usage-error exit code 2): empty tokens
    (``"pt-br,,es"``, ``","``), codes outside the known set, and ``all``
    mixed with explicit codes (``"all,pt-br"`` is a contradiction -- ``all``
    already includes every code).
    """
    from .sources.opencode import KNOWN_LOCALE_DIRS

    tokens = [token.strip() for token in value.split(",")]
    if any(not token for token in tokens):
        raise argparse.ArgumentTypeError(
            f"empty locale code in --locales value {value!r} "
            "(use 'all' or comma-separated locale codes)"
        )
    if "all" in tokens:
        if len(tokens) > 1:
            raise argparse.ArgumentTypeError(
                "'all' cannot be combined with other locale codes"
            )
        return tuple(sorted(KNOWN_LOCALE_DIRS))
    unknown = sorted(set(tokens) - set(KNOWN_LOCALE_DIRS))
    if unknown:
        raise argparse.ArgumentTypeError(
            f"unknown locale code(s): {', '.join(unknown)} "
            f"(known codes: {', '.join(sorted(KNOWN_LOCALE_DIRS))})"
        )
    return tuple(sorted(set(tokens)))


def main(argv: list[str] | None = None) -> int:
    """Parse command-line arguments and run the mirror pipeline.

    ``argv`` defaults to ``None`` (meaning: read ``sys.argv[1:]`` -- argparse
    skips the program name at index 0), which is the normal console-script
    behaviour. Tests pass an explicit list instead, so the CLI can be
    exercised end-to-end without monkeypatching ``sys.argv``.

    Returns the process exit code (0 when every selected source mirrored
    cleanly, 1 when at least one source failed -- see
    :func:`mirror.pipeline.run`; 130 when the operator aborts the run with
    Ctrl+C -- see the ``KeyboardInterrupt`` handler below); the wrapper entry
    points translate it into a real exit status via
    ``raise SystemExit(main())``.

    Raises ``SystemExit(2)`` when ``--log-file`` points at a path that
    cannot be opened: the setup failure is translated by
    ``pipeline._log_file_context`` into a one-line stderr message plus exit
    code 2 (argparse's usage-error code). The run never started, so there is
    no partial state to report as a mirror failure.
    """
    parser = argparse.ArgumentParser(
        prog="mirror-docs",
        description="Mirror AI coding-tool docs into docs/.",
    )
    # --source narrows the run to a single registered source (matched against
    # each source's CONFIG.name, e.g. "kimi-code", "deepseek-api"). choices=
    # is a LAZY container over the live registry (see _SourceNameChoices):
    # building the list eagerly would import the pipeline -- and with it
    # httpx/bs4/html2text -- before argparse even looks at the arguments,
    # which is exactly the cost --version must not pay. A typo ("--source
    # kimi") still fails fast with argparse's standard "invalid choice" error
    # (exit code 2) instead of silently matching nothing and exiting 0 after
    # a no-op run. The pipeline validates `only` again on its own (see
    # pipeline.run), so programmatic callers get the same protection.
    parser.add_argument(
        "--source",
        choices=_SourceNameChoices(),
        help="Only update the named source (e.g. kimi-code).",
    )
    # --dry-run stops after discovery: no fetching, no writing, and the
    # top-level index is not regenerated either. Useful to preview what a
    # source's site structure looks like right now (and to diff discovered
    # slugs against the previous manifest) without touching the network
    # beyond the discovery request or the docs/ tree at all.
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Discover pages without fetching or writing.",
    )
    # --force bypasses the hash-equality skip in write_docs, re-stamping every
    # page's last_updated and rewriting every file. Intended for recovering
    # from a corrupted local tree or after changing how pages are converted.
    parser.add_argument(
        "--force",
        action="store_true",
        help="Rewrite every file even if its hash is unchanged.",
    )
    # --concurrency / --workers sets the number of concurrent worker threads
    # used when fetching pages for a source in pipeline.fetch_pages.
    # Defaults to config.DEFAULT_WORKERS (3). Must be >= 1.
    parser.add_argument(
        "--concurrency",
        "--workers",
        dest="concurrency",
        type=_positive_int,
        default=None,
        metavar="N",
        help=f"Number of concurrent page-fetch workers (default: {config.DEFAULT_WORKERS}).",
    )
    # --log-file writes a copy of ALL console output (both stdout and stderr)
    # to the given path, in addition to the normal console output. This is
    # useful for cron / systemd timer runs where the console output is
    # captured but a persistent, timestamped log file is also desired for
    # later inspection or debugging. The file is opened in append mode so
    # repeated runs (e.g. a scheduled job) accumulate instead of overwriting.
    parser.add_argument(
        "--log-file",
        "-l",
        metavar="PATH",
        default=None,
        help="Also write all output to PATH (append mode).",
    )
    # --locales extends the run to the non-English translations some sources
    # publish, in addition to their (always-mirrored) English pages. The
    # accepted values are validated against the locale codes the
    # locale-capable adapter actually knows -- see _locales; the validated
    # value is stored in the run-scoped holder config.ACTIVE_LOCALES, which
    # that adapter (opencode) reads during discovery, because pipeline.run()
    # does not (yet) accept the flag itself. Absent: the historical
    # English-only mirror. Generic flag; sources without locale directories
    # simply never read the holder.
    parser.add_argument(
        "--locales",
        type=_locales,
        metavar="LOCALES",
        default=None,
        help=(
            "Also mirror non-English locale directories: 'all', or "
            "comma-separated locale codes (e.g. pt-br,es). Currently only "
            "the OpenCode source publishes locale directories."
        ),
    )
    # --check-links runs the offline internal link checker on docs/ (or on a
    # single source if --source is passed) without fetching or writing.
    parser.add_argument(
        "--check-links",
        action="store_true",
        help="Verify internal links in docs/ without fetching or writing.",
    )
    # --version uses argparse's built-in "version" action: it prints the
    # prog name plus the resolved tool version (the same three-tier-resolved
    # config.TOOL_VERSION that goes into the HTTP User-Agent) to stdout and
    # exits 0 immediately, before pipeline.run() is ever reached -- so it
    # works even when the docs tree or network is unavailable.
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {config.TOOL_VERSION}",
    )
    args = parser.parse_args(argv)

    if args.check_links:
        if args.dry_run:
            parser.error("--check-links cannot be combined with --dry-run")
        if args.force:
            parser.error("--check-links cannot be combined with --force")
        if args.concurrency is not None:
            parser.error(
                "--check-links cannot be combined with --concurrency / --workers"
            )
        if args.locales is not None:
            parser.error("--check-links cannot be combined with --locales")

        from . import pipeline, reporting
        from .core import link_checker

        # The illustrative-link exemptions belong to the sources, so the
        # registry is read here -- the CLI is the boundary that may know about
        # concrete sources -- and handed to the checker as plain data.
        exempt_targets_by_source = {
            source.CONFIG.name: source.CONFIG.illustrative_link_targets
            for source in pipeline.SOURCES
        }

        with pipeline._log_file_context(args.log_file):
            issues, scanned_files = link_checker.check_source_links(
                args.source, exempt_targets_by_source
            )
            reporting.link_check_report(
                issues, scanned_files=scanned_files, source_name=args.source
            )
            if scanned_files == 0:
                return 1
            return 0 if not issues else 1

    # The pipeline is imported only now, NOT at module level: argparse has
    # already handled --version and --help above, so the heavy import chain
    # (source adapters, httpx, beautifulsoup4, html2text) is paid only by
    # runs that actually mirror. When --source was passed, the lazy choices
    # container already pulled the module in, so this import is a no-op.
    from . import pipeline

    workers = (
        args.concurrency if args.concurrency is not None else config.DEFAULT_WORKERS
    )

    # Persist the validated --locales selection in the run-scoped holder
    # config.ACTIVE_LOCALES, where source adapters can read it during
    # discovery: pipeline.run() does not (yet) accept the flag itself, so the
    # holder is the channel between the CLI and opencode.discover() -- which
    # also takes the selection as an explicit ``locales`` argument (the seam
    # a future pipeline wiring will use; see its docstring for the contract).
    # None (flag absent) keeps the historical English-only behavior. Only the
    # CLI writes the holder, and only once per run.
    config.ACTIVE_LOCALES = args.locales
    if args.locales and args.source and args.source != "opencode":
        sys.stderr.write(
            f"Note: --locales is only supported by opencode; '{args.source}' will run standard discovery.\n"
        )

    # argparse maps --dry-run/--force to args.dry_run/args.force (dashes
    # become underscores) and --source to args.source; pipeline.run() takes
    # these as keyword arguments force/dry_run/only/log_file/workers.
    try:
        return pipeline.run(
            force=args.force,
            dry_run=args.dry_run,
            only=args.source,
            log_file=args.log_file,
            workers=workers,
        )
    except KeyboardInterrupt:
        # pipeline.run() catches plain Exception per source but deliberately
        # lets BaseException (including KeyboardInterrupt raised on Ctrl+C)
        # propagate so it can abort the whole run. Without this handler the
        # raw "Traceback (most recent call last) ... KeyboardInterrupt" would
        # be dumped to the console, which is noisy and unhelpful for an
        # intentional operator interrupt. Translate it into the conventional
        # exit status 130 that shells use for a process terminated by SIGINT
        # (128 + 2), matching the POSIX convention tools like grep and make
        # follow.
        #
        # The status is RETURNED, not raised via ``SystemExit``, because
        # ``main`` has an integer-return contract: every entry point -- the
        # ``mirror-docs`` console script (which the installer generates as
        # ``sys.exit(main())``), ``python -m mirror`` (``__main__.py``), and
        # the ``if __name__ == "__main__"`` block below -- translates the
        # returned int into the process exit status via
        # ``raise SystemExit(main())``. Returning 130 therefore produces
        # exactly the same observed exit code as ``raise SystemExit(130)``
        # would, while keeping ``main()`` a plain int-returning function that
        # tests and programmatic callers can invoke without catching
        # ``SystemExit``. The _log_file_context context manager in
        # pipeline.run() restores the original stdout/stderr during stack
        # unwind, so no extra stream cleanup is needed here.
        sys.stderr.write("\nRun interrupted by user.\n")
        return 130


if __name__ == "__main__":
    # Reached when this file is run directly (rare; the supported entry points
    # are the `mirror-docs` console script and `python -m mirror`).
    raise SystemExit(main())
