"""Per-source docs-mirroring pipeline and cross-source orchestration.

This module is the engine. For each registered source it discovers pages,
fetches the Markdown, diffs against the previous manifest, writes only what
changed, and (where enabled) records a whats-new entry; finally it regenerates
the top-level index. Console output is delegated to ``mirror.reporting`` so the
control flow here is free of formatting.

The overall data flow for one source is::

    previous manifest.json (on disk)
            |
            v
    discover() -> list[Page]          # what the upstream site currently has
            |
            v
    fetch_pages() -> entries, texts, failed
            |                          # entries: what the manifest will record
            |                          # texts:   freshly fetched Markdown only
            v
    diff(old, entries) -> ChangeSet   # added/modified/renamed/removed
            |
            v
    write_docs()                      # write only changed/new files,
            |                          # delete pages gone from discovery
            v
    whats-new/<date>.md               # only for sources that opt in; written
            |                          # first so a crash leaves the old
            |                          # manifest intact for a retry
            v
    README.md index                   # regenerated only if anything changed
            |
            v
    manifest.json                     # saved last: it commits the new state

Fetched page content is carried alongside its manifest entry in a separate
``texts`` dict rather than as a hidden attribute on the dataclass. That keeps a
clear boundary between "what we fetched this run" (ephemeral, goes to disk) and
"what we record" (the manifest entry), and avoids reaching into private state.

Three invariants drive the design and are worth knowing before touching this
file:

* **A no-op run produces an empty git diff.** Hashes decide what is written;
  timestamps are preserved for unchanged content; manifest/index files are
  saved only when the diff is non-empty. This is what makes the mirrored docs
  reviewable as ordinary git history.
* **A transient network failure is never recorded as a structural change.**
  A failed fetch of a page we already know about carries its old manifest
  entry forward, so the page is neither deleted nor reported as removed.
* **One source's failure never aborts the run.** ``run()`` isolates sources
  from each other: an exception escaping one source's pipeline (a broken
  ``discover()``, an upstream site overhaul, a bug in a conversion hook) is
  reported to stderr and the remaining sources still mirror; the process
  exit code is 1 when any source failed. This is deliberately coarser than
  the per-page isolation above -- a source-level failure means *nothing*
  about that source's outcome is known, so its manifest and files are left
  untouched.

Usage is driven by ``mirror.cli``::

    pipeline.run()                          # update every source
    pipeline.run(only="kimi-code")          # a single source (unknown name
                                            # raises ValueError)
    pipeline.run(dry_run=True)              # discover only, write nothing
    pipeline.run(force=True)                # rewrite every file
"""

from __future__ import annotations

import concurrent.futures
import json
import sys
import time
import unicodedata
from collections import Counter
from collections.abc import Iterator
from contextlib import contextmanager, redirect_stdout, redirect_stderr
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, TextIO, cast

from . import config, reporting
from .core import diff, fetch, index, manifest, media, whats_new
from .core.utils import atomic_write, extract_version
from .core.manifest import FetchMetadata, FileEntry, Manifest
from .core.page import Page
from .sources import antigravity, claude_code, codex_cli, deepseek, kimi_code, opencode
from .sources.base import Source

if TYPE_CHECKING:
    import httpx

# The registry of everything this pipeline mirrors. Each entry is a source
# *module* (from mirror.sources) exposing the same duck-typed interface:
# a CONFIG dataclass (name/title/home_url/generate_whats_new), a discover()
# function, and optionally fetch_markdown() / get_version() hooks. The
# static counterpart of that interface is the ``Source`` Protocol declared
# in sources/base.py; run() asserts it exactly once, via a cast, where the
# duck-typed registry meets the typed pipeline (see the run loop below).
# Adding a new site means adding a sources module and one entry here.
# Order matters only for the console output and the top-level index rows.
# The registry is a tuple (immutable by design) to prevent accidental
# runtime mutation -- sources are fixed at import time.
SOURCES = (antigravity, claude_code, codex_cli, deepseek, kimi_code, opencode)


@dataclass
class SourceResult:
    """Outcome of running one source, returned to callers/tests for inspection.

    ``run_source`` prints its own human-readable summary via ``reporting``;
    this dataclass is the *machine-readable* twin of that summary. The CLI
    ignores it, but tests (and any future caller embedding the pipeline) use
    it to assert on counts, failures, and the diff without scraping stdout.

    Consumed vs. public surface: the CLI's ``run()`` discards the returned
    objects entirely, and the test suite currently reads only ``name``,
    ``discovered``, ``mirrored``, ``written``, and ``whats_new_path``. The
    remaining fields (``title``, ``deleted``, ``failed``, ``changes``,
    ``is_baseline``) are deliberately kept as documented programmatic API
    for embedders of the pipeline -- they are not dead weight, so they must
    not be pruned as unused even though nothing in this repository reads
    them today.

    The ``is_baseline`` field is particularly important for downstream
    consumers: when it is True, the manifest was just created for the first
    time, so there is no previous state to compare against -- every page
    appears as "added" in the ChangeSet, and whats-new entries are skipped.
    """

    name: str
    title: str
    # Pages found by discover() this run (raw count before any filtering).
    discovered: int
    # Entries in the resulting manifest (incl. carry-forwards for failed known
    # pages).
    mirrored: int
    # Files actually (re)written to disk this run (excludes carry-forwards and
    # hash-skipped).
    written: int
    # Files removed because their slug vanished from upstream discovery.
    deleted: int
    # Slugs that could not be fetched this run (network errors, parse
    # failures, etc.).
    failed: list[str]
    # Structural diff vs the previous manifest (added, modified, renamed,
    # removed).
    changes: diff.ChangeSet
    # Path of the whats-new entry file, if one was written; None otherwise.
    whats_new_path: str | None
    # True when there was no previous manifest on disk (first-ever run for
    # this source). Note this predicate is deliberately NARROWER than the
    # whats-new baseline check in ``run_source``: whats-new also treats a
    # previous manifest that exists but contains ZERO files (what a first
    # run with all-failed fetches leaves behind) as a baseline, while this
    # field and the reporting summary count only a missing manifest.
    is_baseline: bool


# One worker's outcome for a single page: the page itself (so the result can
# be attributed without relying on positional order), the freshly fetched
# ``(text, hash)`` pair on success, or the ``FetchError`` that replaced it.
# ``_fetch_single_page`` never raises for per-page failures -- every failure
# mode that belongs to one page is captured in this triple -- so aggregating
# worker outcomes is a plain data shuffle with no exception handling.
_FetchOutcome = tuple[Page, tuple[str, str] | None, fetch.FetchError | None]


def fetch_pages(
    client: httpx.Client,
    source: Source,
    pages: list[Page],
    old: Manifest | None,
    workers: int = config.DEFAULT_WORKERS,
) -> tuple[dict[str, FileEntry], dict[str, str], list[str]]:
    """Fetch every page for a source.

    Returns ``(entries, texts, failed)``:

    * ``entries`` maps slug -> ``FileEntry`` for every page we have an answer
      for -- either freshly fetched, or carried forward from the previous
      manifest when a *known* page failed to fetch;
    * ``texts`` maps slug -> Markdown text for freshly fetched pages only.
      Carry-forward entries are deliberately absent, which :func:`write_docs`
      uses to tell them apart (there is nothing new to write for them);
    * ``failed`` lists the slugs that could not be fetched this run.

    The two dicts are the split between "what the manifest will record"
    (``entries`` -- always complete, one way or another) and "what is new on
    disk" (``texts`` -- fresh downloads only). Keeping them separate is what
    lets :func:`write_docs` skip carry-forwards without any flag on the entry.

    A source may define ``fetch_markdown(client, page) -> (text, hash)`` when
    its pages are not served as ready Markdown (e.g. DeepSeek's docs are an
    HTML site, converted to Markdown with html2text; OpenCode's docs are raw
    MDX with JSX that must be stripped first); the hook is looked up
    once per source via ``getattr`` so sources that serve plain Markdown need
    no boilerplate and simply fall through to the generic fetch.

    When ``workers > 1`` and ``len(pages) > 1``, pages are fetched concurrently
    using ``concurrent.futures.ThreadPoolExecutor(max_workers=workers)``.
    Consecutive request dispatches across all threads are paced by a thread-safe
    :class:`core.fetch.RateLimiter` enforcing :data:`config.RATE_LIMIT_DELAY`.
    When ``workers <= 1`` or ``len(pages) <= 1``, execution runs sequentially in
    the current thread. Worker futures are consumed as they COMPLETE (see the
    inline comments at the executor site), then re-associated with their page
    slugs, so result order across ``entries``, ``texts``, and ``failed``
    remains strictly deterministic -- matching the original discovery order of
    ``pages`` regardless of which fetch happened to finish first.

    The ``hash`` in each entry (a SHA-256 hex digest of the Markdown content)
    is what drives the "write only what changed" invariant in
    :func:`write_docs`: if the hash matches the previous manifest's hash for
    the same slug, the file is not rewritten (unless ``--force`` is set).

    A failed fetch of a page we already know about carries its previous entry
    forward so a single transient network blip is never recorded as a structural
    removal (which would pollute whats-new and delete the file). Only *known*
    pages get this protection: a page that fails on its very first appearance
    is simply absent (there is nothing sensible to carry forward).
    """
    if workers < 1:
        raise ValueError(f"workers must be >= 1, got {workers}")

    # ``getattr`` (rather than attribute access ``source.fetch_markdown``) is
    # required because ``fetch_markdown`` is declared in the ``Source`` Protocol
    # but is OPTIONAL -- only sources whose pages aren't served as ready Markdown
    # define it: deepseek.py converts HTML to Markdown, and opencode.py
    # converts raw MDX (stripping the JSX the Markdown renderer cannot handle).
    # Python's Protocol has no notion of optional members, so the defensive
    # getattr is the correct runtime pattern while the Protocol declaration
    # buys type-checking and IDE support at the call site (see the
    # ``fetch_markdown`` rationale paragraph in the ``Source`` Protocol
    # docstring in mirror/sources/base.py).
    custom_fetch = getattr(source, "fetch_markdown", None)
    rate_limiter = fetch.RateLimiter()

    def _fetch_single_page(page: Page) -> _FetchOutcome:
        rate_limiter.wait()
        try:
            if custom_fetch is not None:
                # Source-specific conversion path (e.g. HTML -> Markdown).
                text, digest = custom_fetch(client, page)
            else:
                # Default path: the page is served as Markdown; fetch it and
                # validate that the response really looks like Markdown.
                text, digest = fetch.fetch_validated(client, page.source_md_url)
            return page, (text, digest), None
        except fetch.FetchError as exc:
            return page, None, exc

    entries: dict[str, FileEntry] = {}
    texts: dict[str, str] = {}
    failed: list[str] = []

    if workers > 1 and len(pages) > 1:
        # --- Concurrent path: consume futures as they COMPLETE ----------------
        # Every page is submitted up front -- the bounded pool drains its
        # internal queue as workers free up, so all fetches overlap regardless
        # of how results are read back. Results are then consumed via
        # ``as_completed``, NOT as ``[f.result() for f in futures]``: that
        # list comprehension waits on the first-submitted future before
        # touching any later one, so a single slow page (a retry storm
        # against a struggling upstream, a stalled connection) head-of-line
        # blocks the collection of every page submitted after it even when
        # those fetches finished long ago. ``as_completed`` yields each future
        # the moment its own fetch finishes instead, decoupling result
        # collection from submission order entirely.
        #
        # The observable output stays byte-for-byte deterministic even though
        # collection is completion-ordered: each outcome is filed under the
        # slug of the page it was computed for, and ``results`` is rebuilt
        # below by walking ``pages`` in discovery order. Dict insertion
        # order, the ``failed`` ordering, and the per-page error output
        # therefore match the sequential branch exactly -- the aggregation is
        # keyed by slug, never by whichever future happened to finish first.
        executor = concurrent.futures.ThreadPoolExecutor(max_workers=workers)
        try:
            # Slugs are unique keys here: run_source rejects duplicate slugs
            # before fetch_pages is ever called, so each key owns exactly one
            # future and the slug-keyed filing below cannot collide.
            futures: dict[str, concurrent.futures.Future[_FetchOutcome]] = {
                page.slug: executor.submit(_fetch_single_page, page) for page in pages
            }
            outcomes: dict[str, _FetchOutcome] = {}
            for future in concurrent.futures.as_completed(futures.values()):
                page, res_tuple, exc = future.result()
                outcomes[page.slug] = (page, res_tuple, exc)
        except BaseException:
            executor.shutdown(wait=False, cancel_futures=True)
            raise
        else:
            executor.shutdown(wait=True)
        # Rebuild the aggregation in deterministic discovery order (see the
        # comment at the executor site for why completion order must not leak
        # into the outputs).
        results = [outcomes[page.slug] for page in pages]
    else:
        results = [_fetch_single_page(page) for page in pages]

    for page, res_tuple, exc in results:
        if exc is not None:
            failed.append(page.slug)
            reporting.fetch_error(source.CONFIG.name, page.slug, exc)
            # Carry-forward: keep the old entry (so the page is not seen as
            # removed) but leave it out of `texts` (nothing new to write).
            # The old FileEntry is COPIED (via dataclasses.replace with no
            # changes) rather than shared by reference: `write_docs` mutates
            # last_updated on entries, and sharing the reference would mutate
            # the old manifest object in-place.
            if old and page.slug in old.files:
                entries[page.slug] = replace(old.files[page.slug])
            continue
        assert res_tuple is not None
        text, digest = res_tuple
        # Note: last_updated is deliberately left empty here. It is stamped
        # later by write_docs, which is the only place that knows whether the
        # content actually changed (and therefore deserves a new timestamp).
        entries[page.slug] = FileEntry(
            slug=page.slug,
            title=fetch.extract_title(text, fallback=page.slug.split("/")[-1]),
            group=page.group,
            source_url=page.source_url,
            source_md_url=page.source_md_url,
            source_id=page.source_id,
            hash=digest,
            last_updated="",
        )
        texts[page.slug] = text
    return entries, texts, failed


def write_docs(
    base: Path,
    entries: dict[str, FileEntry],
    texts: dict[str, str],
    old: Manifest | None,
    discovered_slugs: set[str],
    force: bool,
    now_iso: str,
) -> tuple[int, int]:
    """Persist the fetched Markdown, writing only what actually changed.

    Three cases per slug, evaluated in this order:

    * **Carry-forward** (failed fetch of a known page -- the slug is in
      ``entries`` but absent from ``texts``): nothing to write. The old
      ``last_updated`` is preserved via the ``dataclasses.replace()`` copy
      made in ``fetch_pages``.
    * **Unchanged content** (slug is in ``texts``, hash matches the previous
      manifest, and ``--force`` is not set): skip the write and preserve the
      previous ``last_updated`` timestamp -- but only when the file actually
      exists on disk. A hash-matching page whose file was deleted by hand is
      rewritten (restored from the freshly fetched text), getting a new
      timestamp.
    * **New or modified content** (slug is in ``texts``, hash differs, or
      ``--force`` is set): (re)write the file and stamp ``last_updated``.

    The first two cases are subtly different: a carry-forward was NEVER
    fetched, while a hash-skip WAS fetched but the content is identical.
    Both avoid writing, but only the hash-skip path compares the old hash
    against the new one (via ``old_entry.hash == entry.hash``), which is why
    they are separate logical branches in the loop body below.

    Files for slugs that vanished from discovery are deleted from disk. The
    "write only what changed" rule is what keeps a no-op run's git diff empty.

    Side-effect ordering inside this function is deliberate. The mass-
    deletion safety guard is evaluated FIRST, before any write or deletion:
    a run whose discovery dropped more than half of the previously-known
    pages aborts with the on-disk tree still matching the previous manifest
    byte for byte, because nothing has been written or deleted yet. Only
    after the guard has passed are new/modified pages written, and only then
    are the vanished pages deleted.

    Each file write is atomic against process-level failures (Python
    exceptions and SIGTERM): the text is written to a sibling
    ``.{pid}_{token}.tmp`` file first and then ``Path.replace()``d over the
    target (via ``core.utils.atomic_write``, the same helper
    ``core.manifest.save`` and :func:`write_top_index` use), so a crash or
    exception mid-write leaves either the old file or nothing -- never a
    truncated ``.md`` that a later hash comparison would mistake for real
    content. This does NOT cover power loss / kernel panic: the temp file is
    not ``fsync``-ed before the rename (rename is metadata-atomic only), so a
    hard crash could expose a partially-written page. The next run
    regenerates every page from upstream, so a torn file self-heals. On
    failure the temp file is cleaned up best-effort so stale
    ``.{pid}_{token}.tmp`` files do not accumulate.

    The temp file is a SIBLING of the target (same directory) rather than a
    ``tempfile.NamedTemporaryFile`` in the system temp dir for a reason:
    ``os.replace``/``Path.replace`` is only atomic when source and
    destination live on the same filesystem, and ``/tmp`` is frequently a
    separate tmpfs mount -- staging there would silently degrade the rename
    into a copy-plus-delete and lose exactly the crash safety this pattern
    exists for. Writing next to the target guarantees the atomic-rename
    semantics on every platform and mount layout.

    Ordering with the manifest matters too: ``run_source`` saves the new
    manifest only AFTER every content file is fully on disk (and after the
    whats-new and index writes), so the manifest never commits to a state
    the filesystem does not yet reflect -- a crash anywhere in between
    leaves the old manifest pointing at the old files, which is a
    consistent, retryable state.

    Returns ``(written, deleted)`` -- file counts only; written includes new,
    modified, and restored files; carry-forwards and hash-skipped files count
    as neither.
    """
    # --- Mass-deletion safety guard: evaluated BEFORE any file is touched. --
    # A slug present in the old manifest but missing from this run's discovery
    # means the page was removed upstream, so its local copy is scheduled for
    # deletion below. Carry-forward protection happens one stage earlier (the
    # slug is still in `discovered_slugs`, because it was discovered -- it
    # merely failed to fetch), so this deletion never fires for a transient
    # network error.
    #
    # The >50% threshold check runs here, ahead of the write loop, on
    # purpose: a discovery that drops more than half of the known pages is
    # treated as an upstream outage or a broken source rather than a real
    # mass removal, and aborting before the first atomic_write leaves the
    # on-disk tree byte-identical to what the previous manifest describes.
    # (Guarding after the writes would let a tripped guard still leave
    # freshly-written files behind -- a half-mutated tree the next run would
    # have to reconcile.) ``--force`` keeps its override semantics: the
    # operator has accepted the risk of a mass removal, so the guard is
    # skipped and the deletions below proceed normally.
    slugs_to_delete: list[str] = []
    if old is not None:
        slugs_to_delete = [slug for slug in old.files if slug not in discovered_slugs]
        if not force and old.files and (len(slugs_to_delete) / len(old.files)) > 0.5:
            raise RuntimeError(
                f"Safety guard: Discovery drops >50% of known pages "
                f"({len(slugs_to_delete)} of {len(old.files)}). "
                f"Aborting to protect on-disk state. Use --force to override."
            )

    base.mkdir(parents=True, exist_ok=True)
    # One timestamp for the whole run, received from the caller, so every file
    # written (or defaulted) in this pass shares the same last_updated value --
    # easier to eyeball in the manifest and in whats-new entries than a spray
    # of near-identical timestamps. Using the caller's timestamp also prevents
    # drift between file stamps and manifest.last_updated.
    written = 0
    for slug, entry in entries.items():
        text = texts.get(slug)
        if text is None:
            # Carry-forward entry: this slug was in `entries` (set during
            # fetch_pages via dataclasses.replace for a previously-known page
            # whose fetch failed), but it is absent from `texts` (only freshly
            # downloaded content goes there).  Nothing new to write, so we also
            # skip the hash comparison and stamp below -- the old file remains
            # on disk exactly as it was, and the old last_updated is preserved
            # via the carry-forward copy made in fetch_pages.
            continue
        out = base / f"{slug}.md"
        # The previous manifest's entry for this slug is looked up ONCE (the
        # value is None for a brand-new page or when there is no previous
        # manifest). The hash-equality skip below must also check that the
        # file still exists: the manifest claiming "unchanged" means nothing
        # if someone deleted the .md from disk by hand. Without the exists()
        # guard such a page would be left with a manifest entry but no file
        # until the next --force run; with it, the page simply falls through
        # to the write path and is restored from the freshly fetched text
        # (getting a new last_updated stamp, since a file was in fact
        # written).
        old_entry = old.files.get(slug) if old is not None else None
        if (
            not force
            and old_entry is not None
            and old_entry.hash == entry.hash
            and out.exists()
        ):
            # Content identical to last run: keep the file and its old
            # timestamp. old_entry is guaranteed non-None on this branch
            # (the condition short-circuits on it before the hash
            # comparison), so the stamp is copied straight from the entry
            # looked up above.
            entry.last_updated = old_entry.last_updated
            continue
        out.parent.mkdir(parents=True, exist_ok=True)
        # This per-slug mkdir handles files in subdirectories whose parents
        # might not exist yet -- they differ from the base docs/ dir created
        # above, so the outer ``base.mkdir`` alone is not sufficient. Real
        # examples from the current mirror include ``docs/deepseek-api/api/``
        # and ``docs/kimi-code/configuration/`` (slugs like ``api/chat`` or
        # ``configuration/settings`` map to nested ``.md`` files). Subsequent
        # slugs in the same subdirectory are no-ops.
        # Delegate the atomic write (temp file + rename + best-effort
        # cleanup) to the shared utility function.  The lock-light
        # serialization from the separate lock file is not used here
        # (unlike whats_new.py) because the content files are
        # single-writer-per-run: write_docs iterates entries sequentially,
        # so there is no concurrent-write race even across multiple
        # pipeline processes (the temp filename includes the process ID).
        # Note: ``atomic_write`` combines ``os.getpid()`` with a random UUID
        # token for temp-file naming, providing collision isolation across both
        # concurrent pipeline processes and concurrent threads on the same host.
        atomic_write(out, text)
        entry.last_updated = now_iso
        written += 1
    # Any entry still carrying an empty last_updated at this point defaults to
    # now. The realistic trigger is a corrupt or hand-edited manifest whose
    # entry arrived with last_updated blanked: carry-forward copies preserve
    # the old timestamp (fetch_pages uses dataclasses.replace with no field
    # changes), and freshly written entries are stamped above, so an empty
    # value here means the input data was broken. Defaulting to now keeps the
    # manifest's invariant -- every file has a populated last_updated --
    # without aborting the run over a recoverable data problem.
    for entry in entries.values():
        if not entry.last_updated:
            entry.last_updated = now_iso

    # --- Deletion phase: remove files whose slugs vanished from discovery. --
    # The candidate list (and its >50% guard) was computed at the top of this
    # function, before any write happened; this loop is only reached once the
    # guard has passed (or --force overrode it). When there was no previous
    # manifest (first-ever run) the candidate list is empty and the loop is a
    # no-op.
    deleted = 0
    for slug in slugs_to_delete:
        target = base / f"{slug}.md"
        if target.exists():
            target.unlink()
            deleted += 1
            # Clean up empty parent directories up to the source base,
            # keeping the file tree tidy when a whole subtree is removed
            # upstream. rmdir() raises OSError if the directory is not
            # empty (other files remain) or cannot be removed -- both
            # are benign and simply stop the upward walk.
            parent = target.parent
            while parent != base:
                try:
                    parent.rmdir()
                except OSError:
                    break
                parent = parent.parent
    return written, deleted


def run_source(
    source: Source,
    client: httpx.Client,
    force: bool,
    dry_run: bool,
    workers: int = config.DEFAULT_WORKERS,
) -> SourceResult | None:
    """Run the full pipeline for one source.

    Stages: load previous manifest -> discover pages -> (dry-run stops here) ->
    fetch Markdown -> mirror media assets (opt-in per source) -> diff vs
    previous -> write only what changed -> optionally write a whats-new entry
    -> regenerate the index -> save the new manifest.

    Returns a :class:`SourceResult` describing the outcome, or ``None`` for a
    dry run (nothing was fetched or written, so there is no outcome to
    describe).
    """
    if workers < 1:
        raise ValueError(f"workers must be >= 1, got {workers}")

    cfg = source.CONFIG
    base = config.DOCS_DIR / cfg.name
    manifest_path = base / "manifest.json"
    # `old` is None on the very first run for a source (the "baseline" run);
    # every stage below treats None as "everything is new".
    old = manifest.load(manifest_path)

    # --- Stage 1: Discovery -----------------------------------------------
    # Print the source header to the console (a banner line like
    # "== Claude Code ==", built from the source's human-readable TITLE) so the
    # operator can see which source is currently being processed when scanning
    # the run output.
    reporting.header(cfg.title)
    # ``source.discover(client)`` queries the upstream site's index (sitemap,
    # sidebar, API listing) and returns an ordered list of ``Page`` objects
    # representing every document the pipeline should mirror.  This is the only
    # network call made before fetching individual pages.
    pages = source.discover(client)

    # --- Pipeline-level validation guards ----------------------------------
    # Each check below is a safety net that catches issues any source could
    # produce, independent of the source's own implementation. They run after
    # discovery and before any side effects (fetching or writing).

    # Duplicate slug detection: every slug must be unique in a single run, or
    # the manifest would silently overwrite one page's entry with another.
    # The cheap set/size comparison guards the counting work: only when a
    # duplicate is known to exist do we build the full per-slug occurrence
    # counts (via Counter) to name the offending slugs in the error message.
    slug_set = {p.slug for p in pages}
    if len(slug_set) != len(pages):
        counts = Counter(p.slug for p in pages)
        dups = sorted(s for s, c in counts.items() if c > 1)
        raise ValueError(f"Duplicate slugs in source {cfg.name!r}: {', '.join(dups)}")

    # Slug path-safety (no absolute paths, no ".." segments, no backslashes,
    # no trailing slashes) is deliberately NOT re-checked here: it is an
    # invariant of the Page dataclass itself. Page.__post_init__ validates
    # every slug against its character alphabet (which excludes backslashes)
    # and rejects the path-escape shapes at construction time, so an unsafe
    # slug raises before a Page can even exist -- an extra check in this loop
    # would be unreachable dead code duplicating a stronger, earlier guard.

    # Zero-page guard: if a non-empty previous manifest exists but discovery
    # returned zero pages, abort with an error. This prevents a transient
    # upstream outage or misbehaving source from silently deleting every
    # mirrored file. The antigravity and claude_code adapters already have this
    # check; this is a universal pipeline-level safety net.
    #
    # The guard is deliberately skipped for dry runs: a dry run writes
    # nothing, so the on-disk state this guard protects is never at risk --
    # and dry-run mode is exactly the diagnostic tool an operator reaches for
    # when an upstream outage is suspected, so aborting it on zero pages
    # would defeat its purpose. The duplicate-slug guard above still runs in
    # dry-run mode: it is pure input validation, with no side effects to
    # protect.
    if not dry_run and old is not None and old.files and not pages:
        raise RuntimeError(
            f"Source {cfg.name!r} discovered 0 pages, but the previous "
            f"manifest contains {len(old.files)} file(s). Mirroring zero "
            f"pages would delete all existing docs. Aborting to protect "
            f"the on-disk state."
        )

    # Alias the slug set for use in downstream functions (write_docs, the
    # structural-removal loop) under a name that makes its purpose clear --
    # it is the set of every slug found by discovery, used to decide which
    # previously-mirrored slugs should be deleted from disk.
    discovered_slugs = slug_set

    if dry_run:
        # Discovery-only mode: report what was found (and how it differs
        # structurally from the previous manifest) and stop before any
        # fetching or writing.
        reporting.dry_run(cfg.title, pages, old)
        return None

    # Print a "Fetching <N> pages ..." line to the console so the operator
    # sees progress before the potentially slow per-page network requests.
    reporting.fetch_start(len(pages))
    # ``time.perf_counter()`` (not ``time.time()``): perf_counter is a
    # monotonic high-resolution clock, so the duration measurement is immune to
    # system clock adjustments (NTP corrections, daylight saving, leap seconds)
    # that would make ``time.time()``-based deltas unreliable.  It also has
    # sub-microsecond precision on most platforms, which matters for the
    # sub-second fetch durations we see for small sources.
    fetch_start_time = time.perf_counter()
    entries, texts, failed = fetch_pages(client, source, pages, old, workers=workers)
    fetch_duration = time.perf_counter() - fetch_start_time
    # --- Media stage (opt-in per source) ------------------------------------
    # Sources that reference local images/diagrams declare a ``MEDIA`` config
    # (mirroring how the ``fetch_markdown`` hook is discovered via getattr);
    # when present, ``media.stage_pages`` downloads the referenced assets into
    # ``docs/<source>/<asset-dir>/``, rewrites the in-text references so they
    # resolve locally, and re-hashes the rewritten text. This MUST run after
    # ``fetch_pages`` (only the fresh texts are rewritten; carried-forward
    # pages keep their previous text and hash untouched, and their presence
    # makes the stage skip pruning entirely -- ``media.stage_pages`` is the
    # contract authority) and before ``diff.diff``
    # (every entry hash must already reflect the rewritten text, or the first
    # post-rewrite run would report phantom modifications forever). Asset
    # download failures are reported but never abort the run: the reference is
    # still rewritten deterministically, and the next healthy run heals the
    # file.
    media_config = getattr(source, "MEDIA", None)
    media_result = None
    if media_config is not None:
        entries, texts, media_result = media.stage_pages(
            client, media_config, base, entries, texts
        )
        for url, reason in media_result.assets_failed:
            reporting.warning(f"failed to download media asset {url!r}: {reason}")
        reporting.media_summary(media_result)
    # diff the newly fetched entries against the previous manifest's entries,
    # producing a ``ChangeSet`` that classifies every slug as added, modified,
    # renamed, or removed. This ChangeSet is the sole input to the decision of
    # whether anything was written (and thus whether the index and manifest need
    # updating later).
    changes = diff.diff(old, entries)
    # One canonical instant for the entire source run: file stamps (via
    # write_docs), manifest.last_updated, the fetch metadata, and the
    # whats-new entry below all derive from the same `now`. Generating it
    # once prevents timestamp drift between these outputs -- two independent
    # datetime.now() calls could straddle a second boundary and disagree.
    now = datetime.now(UTC)
    # now_iso uses the manifest's string format (second precision, Z suffix --
    # the same format core.manifest.now_iso produces). It is derived from
    # `now` rather than by calling manifest.now_iso(), which would take its
    # own clock reading and reintroduce the drift this block exists to avoid.
    now_iso = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    # Persist the fetched Markdown files to disk.  `write_docs` handles the
    # three-way decision (carry-forward / unchanged / new) and returns the
    # count of files that were actually written and deleted.
    written, deleted = write_docs(
        base, entries, texts, old, discovered_slugs, force, now_iso
    )

    # Pages "fetched successfully" excludes carry-forwards (failed fetches of
    # pages we kept from the previous manifest) so the metadata reflects real
    # fresh downloads, not preserved entries. The count is computed by
    # intersecting the set of failed slugs with the set of slugs in the old
    # manifest -- only previously-known pages contributed to the carry-forward
    # (first-appearance failures are simply absent).
    carried = sum(1 for s in failed if old and s in old.files)
    version = getattr(cfg, "version", "—")
    version_hook = getattr(source, "get_version", None)
    if version_hook is not None and callable(version_hook):
        resolved_version: str | None = None
        try:
            raw_version = version_hook(client)
            if isinstance(raw_version, str):
                resolved_version = extract_version(raw_version)
        except Exception as exc:
            reporting.warning(
                f"failed to dynamically discover version for {cfg.name!r} ({exc}); "
                f"using fallback"
            )
        if resolved_version:
            version = resolved_version
        elif old is not None and old.version:
            version = old.version
    new_manifest = Manifest(files=entries, version=version, last_updated=now_iso)
    # Populate the fetch-metadata section of the new manifest with timing
    # and page-count information. This metadata is purely informational --
    # it is never used to drive pipeline logic -- but it provides operators
    # with observability into how long each source's fetch phase took,
    # how many pages succeeded, and which (if any) failed.
    new_manifest.fetch_metadata = FetchMetadata(
        last_fetch_completed=now_iso,
        fetch_duration_seconds=round(fetch_duration, 3),
        total_pages_discovered=len(pages),
        pages_fetched_successfully=len(entries) - carried,
        pages_failed=len(failed),
        failed_pages=failed,
    )

    # --- Side effects: whats-new, index, manifest ---------------------------
    # Order matters: the whats-new entry is written FIRST so that if the
    # write fails (disk full, permission error) the manifest is NOT yet
    # updated. If we saved the manifest first and the whats-new write then
    # crashed, the manifest would already reflect the changes -- and the next
    # run would see an empty diff (manifest matches on-disk state) and never
    # log the lost changes. By writing whats-new first, a crash leaves the
    # old manifest intact, so the next run re-detects the same changes and
    # retries the whats-new write.
    #
    # Whats-new entries are opt-in per source (CONFIG.generate_whats_new) and
    # are skipped for baseline runs: a first-ever mirror would otherwise
    # produce a giant "everything is new" entry that carries no signal. A
    # previous manifest with ZERO files counts as a baseline too: that is
    # what a first run leaves behind when every fetch failed (the empty
    # manifest is still saved so the source is not re-baselined forever), and
    # without this check the recovered next run would see a non-None old and
    # emit the same pointless "everything is new" entry.
    whats_new_path = None
    if (
        cfg.generate_whats_new
        and old is not None
        and old.files
        and not changes.is_empty
    ):
        whats_new_path = whats_new.write_entry(
            base / "whats-new", cfg.title, changes, now
        )

    # The manifest and per-source README index are rewritten only when the
    # run actually changed something (baseline run, a non-empty diff, or a
    # version bump).
    # This is the second half of the "no-op run = empty git diff" invariant;
    # the first half is write_docs skipping hash-identical pages.
    #
    # Index goes to disk BEFORE the manifest for the same reason whats-new
    # comes first: if the index write fails (disk full, permission error),
    # the old manifest remains intact so the next run re-detects the same
    # changes and retries. Writing the manifest first would commit the new
    # state unconditionally, losing the error window.
    changed = (
        old is None or not changes.is_empty or (old.version != new_manifest.version)
    )
    if changed:
        index.write(base / "README.md", new_manifest, cfg.title, cfg.home_url)
        manifest.save(new_manifest, manifest_path)

    # The string form of the whats-new path is needed twice below (once for
    # the console summary, once for the machine-readable SourceResult), so it
    # is computed once here instead of repeating the conditional expression
    # in two back-to-back argument lists.
    whats_new_str = str(whats_new_path) if whats_new_path else None
    # Print a per-source summary line to the console showing the page counts,
    # the structural diff summary, and any failures.  The formatted output is
    # handled by ``reporting.summary`` so the pipeline itself stays free of
    # formatting logic.
    reporting.summary(
        len(pages),
        len(entries),
        written,
        deleted,
        failed,
        changes,
        whats_new_str,
        old is None,
    )
    return SourceResult(
        cfg.name,
        cfg.title,
        len(pages),
        len(entries),
        written,
        deleted,
        failed,
        changes,
        whats_new_str,
        old is None,
    )


def write_top_index() -> None:
    """(Re)generate ``docs/README.md`` from the persisted manifests.

    This deliberately reads each source's ``manifest.json`` from disk rather than
    the in-memory :class:`SourceResult` objects: a partial run
    (``--source X``) updates only one source, but the top-level index must still
    list *every* source -- so the on-disk manifest (the single source of truth)
    is authoritative here.

    A source whose manifest is missing (never mirrored, or deleted) is still
    listed, with 0 pages and a placeholder date -- the index always shows the
    full registry rather than silently dropping rows.
    """
    rows: list[tuple[str, str, str, int, str, bool]] = []
    for source in SOURCES:
        cfg = source.CONFIG
        mp = config.DOCS_DIR / cfg.name / "manifest.json"
        # Defaults for a source with no manifest on disk yet -- and also the
        # fallback for a manifest that exists but cannot be read or parsed.
        # Setting them once here (instead of repeating `count = 0` /
        # `last = "—"` in every failure branch) means each branch below only
        # has to decide whether to OVERWRITE the defaults with real data or
        # warn and keep them.
        count = 0
        last = "—"
        version = getattr(cfg, "version", "—")
        if mp.exists():
            # Read the manifest as raw JSON rather than through the Manifest
            # dataclass: the index only needs flat fields, and staying
            # tolerant of schema drift here keeps the index generatable even
            # from older manifests.
            try:
                m = json.loads(mp.read_text(encoding="utf-8"))
                if isinstance(m, dict):
                    # dict.get's default applies only when the key is MISSING;
                    # an explicit null or scalar "files" / "last_updated" is
                    # returned as-is (None, a number, ...), which would make
                    # len(None) raise TypeError or render a non-string date
                    # straight into the markdown table. Guard each field with
                    # isinstance so an explicitly-corrupt value falls back to
                    # the defaults above -- mirroring how
                    # core.manifest.Manifest.from_dict tolerates the same kind
                    # of per-field corruption.
                    raw_files = m.get("files")
                    count = len(raw_files) if isinstance(raw_files, dict) else 0
                    raw_last = m.get("last_updated")
                    last = raw_last if isinstance(raw_last, str) and raw_last else "—"
                    raw_version = m.get("version")
                    if isinstance(raw_version, str) and raw_version.strip():
                        version = raw_version
                else:
                    # Valid JSON but not an object (e.g. a stray list or
                    # scalar) -- unusable as a manifest, so keep the defaults.
                    reporting.warning(
                        f"failed to read manifest for {cfg.name!r}; using defaults"
                    )
            except json.JSONDecodeError, UnicodeDecodeError, OSError:
                # A corrupted or unreadable manifest should not prevent the
                # top-level index from being generated. Keep the defaults and
                # log a warning so the issue is visible in the run output.
                reporting.warning(
                    f"failed to read manifest for {cfg.name!r}; using defaults"
                )
        wn = getattr(cfg, "generate_whats_new", False)
        rows.append((cfg.name, cfg.title, version, count, last, wn))

    # Sum the page counts (r[3] = count, the fourth element of each tuple) across
    # every source to produce the "Total pages mirrored" line in the index header.
    total = sum(r[3] for r in rows)
    lines = [
        "# AI Coding Docs — Index",
        "",
        "Auto-generated mirror of documentation for several AI coding tools/CLIs.",
        f"**Total pages mirrored:** {total}",
        "",
        "| Source | Version | Pages | Last updated | Whats-new |",
        "| --- | :---: | ---: | --- | :---: |",
    ]
    for name, title, version, count, last, wn in rows:
        lines.append(
            f"| [{title}](./{name}/) | {version} | {count} | {last} | {'yes' if wn else 'no'} |"
        )
    lines.append("")
    lines.append("Each subfolder has its own `README.md` index and `manifest.json`.")
    lines.append("")
    config.DOCS_DIR.mkdir(parents=True, exist_ok=True)
    # Delegate the atomic write (temp file + rename + best-effort cleanup) to
    # the shared utility function (same crash-safety pattern used everywhere
    # else in the pipeline).  The parent directory is guaranteed to exist by
    # the mkdir call above, satisfying atomic_write's precondition.
    atomic_write(config.TOP_INDEX_PATH, "\n".join(lines))


def update_root_readme() -> None:
    """Update the auto-generated sources table in the repository root ``README.md``.

    Finds the section demarcated by ``<!-- SOURCES_TABLE:START -->`` and
    ``<!-- SOURCES_TABLE:END -->`` in ``config.ROOT_README_PATH`` and replaces it
    with the up-to-date table generated from the registered sources and their
    on-disk manifests.
    """
    if not config.ROOT_README_PATH.exists():
        return

    content = config.ROOT_README_PATH.read_text(encoding="utf-8")
    start_marker = config.SOURCES_TABLE_START
    end_marker = config.SOURCES_TABLE_END

    if start_marker not in content or end_marker not in content:
        return

    table_header = ["Source", "Version", "Origin", "How it is mirrored", "Whats-new"]
    table_align = ["l", "c", "l", "l", "c"]
    table_rows: list[list[str]] = []
    for source in SOURCES:
        cfg = source.CONFIG
        mp = config.DOCS_DIR / cfg.name / "manifest.json"
        version = getattr(cfg, "version", "—")
        if mp.exists():
            try:
                m = json.loads(mp.read_text(encoding="utf-8"))
                if isinstance(m, dict):
                    raw_version = m.get("version")
                    if isinstance(raw_version, str) and raw_version.strip():
                        version = raw_version
            except json.JSONDecodeError, UnicodeDecodeError, OSError:
                pass

        wn = getattr(cfg, "generate_whats_new", False)
        wn_icon = "✅" if wn else "—"
        origin = getattr(cfg, "origin", "")
        how_mirrored = getattr(cfg, "how_mirrored", "")
        table_rows.append(
            [
                f"[**{cfg.title}**](./docs/{cfg.name}/)",
                version,
                origin,
                how_mirrored,
                wn_icon,
            ]
        )

    # Prettier-compliant padding. Prettier (which gates this file in
    # ``make format-check``) normalizes Markdown tables by padding every
    # column to the DISPLAY width of its widest cell (East-Asian-wide
    # characters such as the ✅ icon count as 2) and centering the cells of
    # center-aligned columns. Emitting the table already padded keeps a
    # mirror run from producing a README that fails the formatting gate;
    # emitting it compact would fail the gate after every run.
    def _display_width(cell: str) -> int:
        return sum(
            2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1 for ch in cell
        )

    def _pad_cell(cell: str, width: int, align: str) -> str:
        extra = width - _display_width(cell)
        if align == "c":
            left = extra // 2
            return f"{' ' * left}{cell}{' ' * (extra - left)}"
        return f"{cell}{' ' * extra}"

    widths = [
        max(_display_width(header), *(_display_width(row[i]) for row in table_rows))
        for i, header in enumerate(table_header)
    ]
    table_lines = [
        "| "
        + " | ".join(
            _pad_cell(cell, width, align)
            for cell, width, align in zip(table_header, widths, table_align)
        )
        + " |",
        "| "
        + " | ".join(
            f":{'-' * (width - 2)}:" if align == "c" else f":{'-' * (width - 1)}"
            for width, align in zip(widths, table_align)
        )
        + " |",
    ]
    table_lines += [
        "| "
        + " | ".join(
            _pad_cell(cell, width, align)
            for cell, width, align in zip(row, widths, table_align)
        )
        + " |"
        for row in table_rows
    ]

    rows: list[str] = [start_marker, "", *table_lines, "", end_marker]
    table_block = "\n".join(rows)

    start_idx = content.find(start_marker)
    end_idx = content.find(end_marker) + len(end_marker)
    new_content = content[:start_idx] + table_block + content[end_idx:]

    atomic_write(config.ROOT_README_PATH, new_content)


class _Tee:
    """A write-only file-like object that duplicates output to two streams.

    Every ``write`` call is forwarded to both the original stream
    (typically ``sys.stdout`` or ``sys.stderr``) and a log file, so
    console output is preserved exactly as-is while a persistent copy
    accumulates in the log. ``flush`` is forwarded to both streams so
    buffered output appears in both places at the same time. All other
    attribute accesses (``isatty``, ``fileno``, ``encoding``, ...) are
    delegated to the original stream via ``__getattr__``, so anything
    checking whether stdout is a terminal still gets the right answer.

    The wrapper is TEXT-ONLY: byte-level writes via the delegated
    ``.buffer`` attribute (or any direct write to the wrapped stream)
    bypass this class entirely and are therefore NOT duplicated to the
    log file -- only text ``write()``/``flush()`` calls routed through
    this wrapper are tee'd to both destinations.

    The class is deliberately NOT a subclass of ``io.TextIOBase``: it
    wraps two existing streams rather than implementing the full TextIO
    contract, and the handful of methods it does implement (``write``,
    ``flush``, the ``__getattr__`` delegation, and the
    ``_disable_log_copy`` best-effort latch) are the only ones the
    Python ``print()`` function and ``sys.stdout``/``sys.stderr``
    assignment require in practice. Inheriting from ``TextIOBase`` would
    pull in abstract method requirements for ``detach()``, ``read()``,
    ``seek()``, and others that are never called and would need stub
    implementations -- more code with no benefit.

    Defined at module level (not inside ``_tee_stream``) so the class is
    created once at import time rather than re-created on every call.
    """

    # ``__slots__`` prevents accidental attribute attachment (which would
    # go unnoticed on a plain ``object()`` with ``__getattr__`` delegation)
    # and keeps the wrapper lightweight -- no per-instance dict.  Two
    # instances of this class (one wrapping ``sys.stdout`` and one wrapping
    # ``sys.stderr``) may both be routing to the same log file
    # simultaneously; the Python file object's *internal* ``write()``
    # serialises on the GIL for the small writes (single ``print()`` calls)
    # this tool produces, so no explicit locking is needed.
    # The slot names (``_original``, ``_log_file``) store the stream
    # references that were previously closure variables when this class was
    # nested inside ``_tee_stream``; ``_log_failed`` is the best-effort log
    # flag (see ``_disable_log_copy``) that latches True the first time the
    # log copy raises, so every later write/flush skips it instead of
    # re-raising.
    __slots__ = ("_original", "_log_file", "_log_failed")

    def __init__(self, original: TextIO, log_file: TextIO) -> None:
        """Store references to the two output streams.

        The references are kept in slots (``_original`` and ``_log_file``)
        rather than as closure variables, which is necessary now that this
        class lives at module level instead of inside ``_tee_stream``.
        ``_log_failed`` starts False and is latched True by
        ``_disable_log_copy`` once the log copy first fails.
        """
        self._original = original
        self._log_file = log_file
        self._log_failed = False

    def write(self, data: str) -> int:
        """Forward *data* to both the original stream and the log file.

        Returns the number of characters written. The count returned is
        ``len(data)`` -- both streams receive the same string, so the
        count is the same for both, and returning the character count of
        the data is simpler than coordinating return values from two
        independent ``write()`` calls.

        The copy to the log file is BEST-EFFORT. The log file is a
        secondary record of output the operator already sees on the
        console, so a full or unwritable log volume must never be allowed
        to abort the mirror: if the log write raises ``OSError`` (disk
        full, broken pipe, permission revoked mid-run), the log copy is
        disabled for the rest of the process via ``self._log_failed`` and
        a one-shot warning is emitted to the real console stream. The
        write to ``self._original`` always happens and is never
        suppressed, even when the log copy has been disabled.

        Thread-safety note: within a single process, individual writes to the
        underlying streams are serialized by the GIL and stream buffers,
        preventing byte-level corruption. However, concurrent writes from
        worker threads (such as parallel page fetchers emitting warnings)
        can interleave output lines between console and log streams.
        """
        # The console write is unconditional and must never be suppressed
        # -- it is the primary output the operator relies on, independent
        # of whether the secondary log copy is healthy.
        self._original.write(data)
        # The log copy is best-effort (see docstring): once it has failed
        # once, skip it entirely rather than re-raising OSError on every
        # subsequent write, which would otherwise propagate through
        # print() -> reporting -> run_source and escape the per-source
        # isolation boundary in run().
        if not self._log_failed:
            try:
                self._log_file.write(data)
            except OSError:
                self._disable_log_copy()
        return len(data)

    def flush(self) -> None:
        """Flush both the original stream and the log file.

        Called by ``print()`` when ``flush=True`` is passed, and by the
        Python runtime on interpreter shutdown. Flushing both streams
        keeps the console and log file synchronised: a line that appears
        on screen is guaranteed to be in the log file as well.

        Like :meth:`write`, the log-file flush is best-effort: if it
        raises ``OSError`` the log copy is disabled for the rest of the
        run, while the flush of ``self._original`` always happens.
        """
        self._original.flush()
        if not self._log_failed:
            try:
                self._log_file.flush()
            except OSError:
                self._disable_log_copy()

    def _disable_log_copy(self) -> None:
        """Disable the log copy and warn once on the real console stream.

        Called the first time writing or flushing the log file raises
        ``OSError``. Latches ``self._log_failed`` to ``True`` so every
        subsequent :meth:`write`/:meth:`flush` skips the log copy instead
        of re-raising, and emits a single warning to the wrapped original
        stream -- written DIRECTLY to ``self._original`` (not through the
        tee) to avoid recursion. The flag makes this one-shot: only the
        first failure for this instance produces a warning; later calls
        are silent no-ops on the log side.
        """
        self._log_failed = True
        self._original.write(
            "\nwarning: log file write failed; log copy disabled "
            "for the rest of this run\n"
        )
        self._original.flush()

    def __getattr__(self, name: str) -> Any:
        """Delegate any attribute not defined on this class to the original
        stream.

        This is the escape hatch that makes the wrapper transparent: code
        that checks ``sys.stdout.isatty()``, reads
        ``sys.stdout.encoding``, or accesses ``sys.stdout.errors`` still
        gets the real answer from the underlying stream. The methods
        defined on the class (``write``, ``flush``,
        ``_disable_log_copy``, and ``__getattr__`` itself)
        are never reached through here -- Python only calls
        ``__getattr__`` when normal attribute lookup fails.
        """
        return getattr(self._original, name)


def _tee_stream(original: TextIO, log_file: TextIO) -> TextIO:
    """Return a file-like object that writes to both *original* and *log_file*.

    Every ``write`` call is forwarded to both streams, and ``flush`` is
    forwarded so buffered output appears in both places at the same time.
    All other attribute accesses (``isatty``, ``fileno``, ``encoding``, ...)
    are delegated to *original*, so anything checking whether stdout is a
    terminal still gets the right answer.  The returned object is a thin
    wrapper, not a subclass -- it holds references, not copies, so closing
    the log file is the caller's responsibility.
    """
    return cast(TextIO, _Tee(original, log_file))


@contextmanager
def _log_file_context(log_file_path: str | None) -> Iterator[None]:
    """Context manager that optionally tees stdout/stderr to a log file.

    When *log_file_path* is ``None`` (the default), this is a no-op. When a
    path is given, it opens the file in append mode and wraps both
    ``sys.stdout`` and ``sys.stderr`` using the standard library's
    ``contextlib.redirect_stdout`` and ``contextlib.redirect_stderr`` context
    managers. This cleanly manages log redirection, restoring the original
    streams automatically on exit without the risks associated with manual
    global interpreter mutation (e.g. failing to restore them on exception).

    The tee-ing is implemented by the :class:`_Tee` wrapper defined above:
    each ``print()`` call writes to BOTH the console and the log file,
    with ``flush()`` forwarded to both streams so output appears
    simultaneously in both places.  The ``__getattr__`` delegation on
    ``_Tee`` preserves terminal-detection behaviour (``isatty()``,
    ``encoding``, etc.) so redirected code paths cannot tell the difference.

    If the log file cannot be set up at all (parent directory not creatable,
    path not writable, read-only filesystem), the ``OSError`` is translated
    into a one-line stderr message and ``SystemExit(2)`` instead of
    propagating as a raw traceback through ``cli.main()`` -- see the
    try/except around the setup below.
    """
    if log_file_path is None:
        yield
        return

    # Ensure the log file's parent directory exists (race-free: mkdir is
    # a no-op when the directory already exists). The log file itself is
    # opened in append mode so multiple runs accumulate without overwriting.
    # Both operations can raise OSError (unwritable directory, read-only
    # filesystem, a path component that is a regular file, ...). Catching it
    # here -- BEFORE any stream is redirected, so the message still reaches
    # the real stderr -- turns an operator-facing configuration error into
    # the same one-line "!!" style used for source failures, plus exit code
    # 2 (argparse's usage-error code; the run has not started, so there is
    # no partial state to preserve). Without this, the raw traceback would
    # escape through cli.main(), which only catches KeyboardInterrupt.
    try:
        Path(log_file_path).parent.mkdir(parents=True, exist_ok=True)
        log_fh = open(log_file_path, "a", encoding="utf-8")
    except OSError as exc:
        print(f"!! cannot open log file {log_file_path!r}: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc
    with log_fh:
        # Wrap both stdout and stderr with _Tee proxies that duplicate
        # every write() call to the log file.  The contextlib.redirect_*
        # managers save the original streams and restore them on exit, so
        # an exception inside the pipeline never leaves the streams in a
        # redirected state.
        with (
            redirect_stdout(_tee_stream(sys.stdout, log_fh)),
            redirect_stderr(_tee_stream(sys.stderr, log_fh)),
        ):
            yield


def run(
    force: bool = False,
    dry_run: bool = False,
    only: str | None = None,
    log_file: str | None = None,
    workers: int = config.DEFAULT_WORKERS,
) -> int:
    """Update every source (or just ``only``), then refresh the top index.

    Returns 0 when every selected source completed and both the top index
    and root README were updated, 1 when at least one source failed (see the
    isolation guarantee below) or either the top-index write or root README
    update failed. A ``--dry-run`` discovers pages only and writes nothing
    (including the top index and root README).

    Raises ``ValueError`` when ``only`` names no registered source. The CLI
    already restricts ``--source`` to valid names via argparse ``choices``;
    validating again here gives programmatic callers the same fail-fast
    behaviour instead of a silent no-op run that matches nothing and still
    regenerates the top index.

    When *log_file* is provided (a path string), all console output produced
    by this run -- both stdout and stderr -- is also written to that file in
    append mode. The console output is unchanged; the file receives a copy.
    This is the implementation backing the ``--log-file`` / ``-l`` CLI flag.
    If the log file cannot be opened at all (unwritable path, uncreatable
    parent directory), the setup failure is reported as a one-line stderr
    message and the process exits via ``SystemExit(2)`` before any source
    runs -- see :func:`_log_file_context`.

    Failure isolation: each source runs inside its own try/except. An
    exception escaping one source (from ``discover()``, a conversion hook,
    or any pipeline stage) is reported via :func:`reporting.source_error`
    and the run continues with the remaining sources -- one broken source
    must never leave the others stale. Per-page ``FetchError`` carry-forward
    is unaffected: it happens one level down, inside ``fetch_pages``.

    A single HTTP client is shared across all sources in the run: connection
    pooling and keep-alive make consecutive fetches cheaper, and the shared
    client is where the global timeout/retry/User-Agent policy from
    :mod:`mirror.config` is applied.
    """
    if workers < 1:
        raise ValueError(f"workers must be >= 1, got {workers}")
    if only is not None and only not in {s.CONFIG.name for s in SOURCES}:
        # Fail fast on a name no source registers (typically a typo). Done
        # before the client is built so the error costs nothing.  The set
        # of registered names is also used to build the error message --
        # sorted alphabetically so a human can quickly spot a mistyped name.
        known = ", ".join(sorted(s.CONFIG.name for s in SOURCES))
        raise ValueError(f"unknown source {only!r}; known sources: {known}")
    # Track which sources errored out for the final exit code. This list is
    # appended to inside the per-source try/except below; if it remains empty
    # at the end, every source completed successfully and run() returns 0.
    failed_sources: list[str] = []
    # Separate flag for a failed top-index write: the top index is not a
    # source (it aggregates every source's on-disk manifest), so it does not
    # belong in ``failed_sources``, but its failure must still fold into the
    # exit code the same way -- a nonzero return tells the operator the run
    # did not fully succeed.
    top_index_failed = False
    # The log-file tee wraps stdout/stderr for the full duration of the
    # pipeline run, so every print() in reporting, every source adapter's
    # stderr warning, and every exception traceback is captured in the log
    # file in addition to appearing on the console. The context manager
    # restores the original streams on exit even if an exception escapes.
    with _log_file_context(log_file):
        with fetch.make_client() as client:
            # Iterate every registered source (in the order defined by SOURCES).
            # When ``only`` is set, skip sources whose name does not match --
            # the membership check above already guarantees it names a real
            # source, so the skip is the only filtering needed here.
            for source in SOURCES:
                if only and source.CONFIG.name != only:
                    continue
                try:
                    # The registry holds plain module objects, whose static
                    # type is ``ModuleType``; at runtime they duck-type the
                    # ``Source`` Protocol (CONFIG + discover + optional
                    # hooks). The interface is therefore asserted exactly
                    # once here -- at the boundary where the untyped
                    # registry meets the typed pipeline stages below.
                    run_source(
                        cast(Source, source), client, force, dry_run, workers=workers
                    )
                except Exception as exc:
                    # Breadth is the point: isolation must hold for ANY error
                    # a source can raise, not a hand-picked list of known
                    # exception types. Isolate the failure: report it (with
                    # traceback), record the source name for the exit code,
                    # and keep mirroring the remaining sources. The failed
                    # source's manifest and on-disk files are left exactly as
                    # they were -- nothing about its outcome is known with
                    # certainty after an exception, so writing anything
                    # (manifest, index, whats-new) for it would be guessing at
                    # partial state. BaseException subclasses
                    # (KeyboardInterrupt, SystemExit) are deliberately NOT
                    # caught: those must propagate unconditionally to abort
                    # the whole pipeline.
                    failed_sources.append(source.CONFIG.name)
                    reporting.source_error(source.CONFIG.name, exc)
        # The top index is skipped for dry runs (nothing was written, so there is
        # nothing new to index) and regenerated unconditionally otherwise -- it is
        # cheap, and write_docs-style diffing does not apply to it. It still runs
        # after a partial failure: it reads on-disk manifests, and a failed
        # source simply keeps its previous row.
        if not dry_run:
            # Failure isolation for the top-index write, matching the
            # per-source isolation above: an OSError here (unwritable
            # docs/README.md, a docs directory that cannot be listed, ...)
            # must not escape run() as an unhandled traceback -- that would
            # break the one-line report convention the rest of the module
            # follows and would leave the exit code undefined. Report the
            # degradation via reporting.warning (the generic non-fatal
            # channel) and fold it into the exit code: the mirrored pages
            # are fine, but the operator must know the index is stale.
            try:
                write_top_index()
            except OSError as exc:
                reporting.warning(f"failed to write top index: {exc}")
                top_index_failed = True
            try:
                update_root_readme()
            except (OSError, UnicodeDecodeError) as exc:
                reporting.warning(f"failed to update root readme: {exc}")
                top_index_failed = True
    return 1 if failed_sources or top_index_failed else 0
