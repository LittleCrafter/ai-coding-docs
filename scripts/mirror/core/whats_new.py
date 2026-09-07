"""Generate the whats-new log for a source from a ChangeSet.

Only sources that opt into whats-new use this. One file per day; multiple
runs on the same day append a new `## ` section.

The log answers "what changed upstream since I last looked?" for a human
reader. The layout is deliberately append-only and date-partitioned:

  * one file per day (``whats-new/YYYY-MM-DD.md``) keeps files small and
    makes the git history of the log itself a timeline;
  * a repeat run on the same day *appends* a new timestamped `## ` section
    behind a ``---`` rule instead of rewriting, so nothing detected earlier
    that day is ever lost;
  * an empty ChangeSet is an error (see `write_entry`), not an empty section:
    days with no changes should simply produce no file.

Platform note: the cross-process lock around read-modify-write of the daily
log file uses ``fcntl.flock`` (see the lock design comments near
`write_entry`), and ``fcntl`` is a POSIX-only module that does not exist on
Windows. The import below is therefore defensive: on platforms without
``fcntl`` the module still imports and works correctly, simply without the
inter-process lock -- a safe degradation because the mirror is operated
under a single-writer assumption (one scheduled job at a time), and the
write itself stays atomic via ``atomic_write`` regardless of the lock.
"""

from __future__ import annotations

import errno
import html
import os
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

from .diff import ChangeSet
from .utils import atomic_write, safe_url

try:
    import fcntl
except ImportError:
    # ``fcntl`` is POSIX-only; on Windows this import raises ImportError
    # (specifically ModuleNotFoundError), which would crash the entire CLI at
    # import time if it were unconditional. Falling back to ``None`` keeps the
    # module importable everywhere: the flock acquisition in ``write_entry``
    # is guarded by ``if fcntl is not None``, so on platforms without
    # ``fcntl`` the read-modify-write of the daily log simply runs unlocked.
    # That is a safe degradation, not a correctness gap -- the lock is a
    # best-effort guard against two mirror processes writing the same day's
    # file concurrently, the pipeline is operated under a single-writer
    # assumption, and the write itself remains atomic via ``atomic_write``
    # (temp file + rename) even without the lock.
    fcntl = None  # type: ignore[assignment]


def _as_utc(now: datetime) -> datetime:
    """Normalize a datetime to UTC.

    Naive datetimes are *assumed* to already be UTC (the pipeline's own
    caller passes ``datetime.now(UTC)``; a naive value only arrives from
    tests or future callers, and assuming UTC beats silently mislabeling a
    local time). Aware datetimes in any other timezone are converted, so the
    date key and the human-facing stamp below can never disagree with each
    other or mislabel the timezone.
    """
    if now.tzinfo is None:
        return now.replace(tzinfo=UTC)
    return now.astimezone(UTC)


def _date(now: datetime) -> str:
    """The log-file date key, e.g. ``2026-07-25`` (used as the filename)."""
    return _as_utc(now).strftime("%Y-%m-%d")


def _stamp(now: datetime) -> str:
    """The human-facing section timestamp, always suffixed ``UTC``.

    Minute precision is enough for a change log and keeps repeated-run
    sections compact; the explicit UTC suffix removes any doubt about which
    timezone the pipeline (usually CI) ran in. The datetime is normalized to
    UTC first (see `_as_utc`), so the suffix is always accurate rather than
    appended unconditionally to whatever wall-clock time was passed in.
    """
    return _as_utc(now).strftime("%Y-%m-%d %H:%M") + " UTC"


def _render_section(changes: ChangeSet, now: datetime) -> str:
    """Render one timestamped `## ` section for a ChangeSet.

    Sections are emitted in a fixed order (added, modified, renamed, removed)
    and each category is omitted entirely when empty, so a run that only
    modified pages produces no dead "Added (0)" headings. The rename bullets
    include `matched_by` so readers can tell a certain ``source_id`` match
    from a heuristic title match.
    """
    lines: list[str] = []
    total = changes.total
    noun = "change" if total == 1 else "changes"
    lines.append(f"## {_stamp(now)} — {total} {noun}")
    lines.append("")

    def _escape_md(text: str) -> str:
        """Escape Markdown formatting characters that would break rendering.

        The output is only used inside ``**bold**`` spans (the bullet title
        and the rename line), so the characters that can actually corrupt
        the layout there are escaped. The passes run in a strict order so
        no pass double-escapes the output of an earlier one:

        Backslash (``\\``) is doubled FIRST among the escaping passes (the
        entity-normalization step described below runs before all of them).
        Every later backslash escape
        injects a fresh ``\\`` into the text; if the backslash pass ran after
        any of them it would double those injected backslashes too,
        corrupting the text (``a\\b`` must stay ``a\\b``, not become
        ``a\\\\b``). Running it first means later passes only see original
        characters plus the doubled backslashes, which they never re-touch.

        ``&`` is HTML-entity-escaped (``&amp;``) SECOND, before the other
        entity passes below. A raw ``&`` is interpreted as the start of an
        entity reference (``&amp;``, ``&copy;``, …) which would either render
        as the wrong character or be left as visible noise. It must run
        before the ``<``/``>`` entity passes because those inject NEW
        ampersands (``<`` -> ``&lt;``): if ``&`` were escaped afterwards it
        would double-escape them into ``&amp;lt;``. Running it second --
        after the backslash pass -- is safe because ``&`` is not a backslash.

        Before ANY escaping pass runs, pre-existing HTML entities in the
        input are normalized away with ``html.unescape`` (see the code below):
        titles come from upstream sources that may already carry entities
        (``A &amp; B``), and escaping such a title directly would
        double-escape the ampersand (``A &amp;amp; B``). Unescaping first
        collapses every entity to its literal character, after which the
        passes below re-escape exactly the characters that need it --
        normalize-then-escape, so every entity appears exactly once.

        ``*``, ``_``, ``[``, ``]`` are backslash-escaped: inside a bold span
        these are the Markdown formatting characters that would otherwise
        terminate or reshape the span (a stray ``*`` could close the bold
        early, a ``[`` could start a link). Backslash-escaping (rather than
        entity-escaping) is the idiomatic Markdown way to literalise them and
        keeps the raw source readable. This pass runs after the ``&`` pass,
        and none of the characters involved overlap, so ordering between them
        is only constrained by the backslash-first rule above.

        ``<``, ``>`` are HTML-entity-escaped (``&lt;``, ``&gt;``), NOT
        backslash-escaped, because a raw ``<`` or ``>`` inside a ``**bold**``
        span can confuse some renderers into starting or ending an inline
        HTML tag. Entity-escaping is reversible and is the same convention
        used by the title-escape table in ``core.index`` (see
        ``_TITLE_ESCAPES``), so the two renderers stay consistent. These run
        LAST among the substitution passes: after the backslash pass (safe,
        none of these characters is a backslash) and after the ``&`` pass
        (required, so the ``&lt;``/``&gt;`` entities injected here are never
        re-escaped).

        Backticks are deliberately NOT escaped here. A backtick inside
        ``**bold**`` CAN open an inline code span in CommonMark (contrary to
        a common misconception -- code spans nest inside emphasis, so a
        title like ``**Using `uv` workspaces**`` renders as bold "Using "
        plus code "uv" plus bold " workspaces"). For the realistic upstream
        titles the mirror sees, that nesting renders on one line and stays
        bold, so the visual outcome is acceptable; escaping every backtick
        would only add raw-Markdown noise. Titles with pathological backtick
        patterns are vanishingly rare, and code-span safety for SLUGS (which
        are wrapped in their own single-backtick code spans) is handled
        separately by ``_safe_code``.

        Newlines and carriage returns are collapsed to spaces rather than
        escaped: titles come from upstream Markdown and can contain anything,
        and a literal line break inside a title would split the bullet across
        two lines, silently breaking the log's one-line-per-change layout
        (and producing a stray, malformed line that no renderer asked for).
        """
        # Normalize-then-escape: unescape any HTML entities the title already
        # carries BEFORE any escaping pass runs, so a pre-escaped title
        # (``A &amp; B``) is not double-escaped (``A &amp;amp; B``). After
        # this, the text contains only literal characters, and the passes
        # below re-escape exactly the ones that need it -- every entity ends
        # up in the output exactly once.
        text = html.unescape(text)
        text = text.replace("\\", "\\\\")
        text = text.replace("&", "&amp;")
        for ch in ("*", "_", "[", "]"):
            text = text.replace(ch, "\\" + ch)
        text = text.replace("<", "&lt;")
        text = text.replace(">", "&gt;")
        # Collapse line breaks to single spaces: CRLF first, so a Windows
        # line ending becomes ONE space rather than two.
        return text.replace("\r\n", " ").replace("\n", " ").replace("\r", " ")

    def _safe_code(text: str) -> str:
        """Sanitize text for use inside Markdown code spans.

        Slugs are interpolated raw into the bullet template wrapped in
        single-backtick code spans (the ``- **Title** — `slug` — …`` shape,
        where the slug sits between two backtick characters). If the slug
        itself contained a backtick, that backtick would be interpreted as
        the CLOSER of the wrapping code span: everything after it would
        escape the code span and re-enter running Markdown, corrupting the
        bullet layout and potentially re-triggering the formatting
        characters ``_escape_md`` was supposed to neutralise. Replacing
        backticks with ``'`` (a single quote) sidesteps that entirely: the
        quote is visible, inert inside a code span, and ASCII, so the slug
        stays readable and the wrapping span can never be closed early.

        In practice ``validate_slug`` already restricts the slug alphabet to
        ``[A-Za-z0-9._/-]`` which excludes backticks, so this substitution
        never actually fires on a valid slug today. It is kept as a
        defensive backstop so that if the slug contract ever loosens (or if
        a future caller passes a non-slug string through this helper), the
        worst case is a cosmetic quote in the code span, not a corrupted
        bullet.
        """
        return text.replace("`", "'")

    def bullet(title: str, slug: str, url: str) -> str:
        """Render a formatted Markdown bullet for one added or modified page.

        The bullet shape is ``- **Title** — `slug` — [source](<url>)``,
        with the title escaped against Markdown formatting characters that
        would corrupt the bold span, the slug sanitised so embedded backticks
        cannot close the wrapping code span early, and the URL wrapped in
        angle brackets (``<...>``, valid CommonMark) so spaces and parentheses
        in the raw URL do not terminate the link destination prematurely.
        The URL also passes through ``safe_url`` to percent-encode the
        characters that angle brackets alone do not make safe: ``<``, ``>``,
        line endings, and ``|`` (the last of which would otherwise act as a
        GFM table column separator).
        """
        # Title and slug are escaped/sanitised so embedded Markdown syntax
        # characters do not break the rendered output. The link destination
        # is wrapped in angle brackets (``<...>``, valid CommonMark): the
        # URL is interpolated raw, so a space or ``)`` in it would otherwise
        # terminate a bare ``(...)`` destination early and break the link.
        # Angle brackets do not cover ``<``, ``>``, or line endings, though,
        # so the URL passes through ``safe_url`` first to percent-encode
        # exactly those.
        return f"- **{_escape_md(title)}** — `{_safe_code(slug)}` — [source](<{safe_url(url)}>)"

    if changes.added:
        lines.append(f"### ➕ Added ({len(changes.added)})")
        lines += [bullet(c.title, c.slug, c.source_url) for c in changes.added]
        lines.append("")
    if changes.modified:
        lines.append(f"### ✏️ Modified ({len(changes.modified)})")
        lines += [bullet(c.title, c.slug, c.source_url) for c in changes.modified]
        lines.append("")
    if changes.renamed:
        lines.append(f"### 🔀 Renamed / Moved ({len(changes.renamed)})")
        for r in changes.renamed:
            lines.append(
                f"- **{_escape_md(r.title)}** moved `{_safe_code(r.old_slug)}` "
                f"→ `{_safe_code(r.new_slug)}` "
                # Angle-bracketed destination, same reason as in `bullet`:
                # a raw URL containing a space or ``)`` would break a bare
                # ``(...)`` link. ``safe_url`` additionally percent-encodes
                # ``<``, ``>``, and line endings, which angle brackets do
                # not make safe.
                f"(matched by {r.matched_by}) — [source](<{safe_url(r.source_url)}>)"
            )
        lines.append("")
    if changes.removed:
        lines.append(f"### ➖ Removed ({len(changes.removed)})")
        for c in changes.removed:
            # A removal only means "no longer discovered" -- the page may have
            # moved, been merged, or genuinely been deprecated. The trailing
            # note states that uncertainty honestly instead of asserting a
            # deletion upstream. The link destination is angle-bracketed for
            # the same reason as in `bullet`: a raw URL containing a space or
            # ``)`` would break a bare ``(...)`` link, and ``safe_url``
            # percent-encodes the ``<``/``>``/line-ending characters that
            # angle brackets do not make safe.
            lines.append(
                f"- **{_escape_md(c.title)}** — `{_safe_code(c.slug)}` — "
                f"[source](<{safe_url(c.source_url)}>) "
                f"(no longer in the source; possibly deprecated)"
            )
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def _read_and_prepare_payload(path: Path, section: str, source_title: str) -> str:
    """Read the existing whats-new file (if any) and decide what to write.

    This function encapsulates the read-modify stage of the write_entry
    critical section.  It is called while the exclusive flock on the lock file
    is held (on platforms where ``fcntl`` is available; without ``fcntl`` the
    same code simply runs unlocked under the single-writer assumption), so
    the decision it makes (append vs start fresh) is based on the
    latest on-disk state every time -- another process that wrote between our
    earlier stat() and this read would be serialised behind the lock.  (Why
    the flock is taken on a dedicated, never-renamed lock file rather than on
    the content file itself -- the inode-swap race with ``atomic_write`` --
    is analysed in the inline comments of ``write_entry``, next to
    ``lock_path``.)

    Three cases, determined by whether the target file already exists and
    has content:

    * **Existing, non-empty file** -- same-day re-run.  The file from an
      earlier run today already has the header and at least one ``## ``
      section.  We append the *new* section behind a ``---`` horizontal rule
      so the two runs read as distinct chronological entries within one day's
      file.  The existing content is preserved verbatim.

    * **Missing or empty file** -- first entry of the day.  We prepend an
      explanatory header that describes the format (one file per day, multiple
      sections per file) so a reader landing on any day's file immediately
      understands the structure without having to find the generator.

    * **Unreadable or corrupted file** -- an existing file whose bytes are
      not valid UTF-8 (e.g. left behind by a crashed writer) or that cannot
      be read (I/O error).  Treated exactly like the missing-file case above:
      a warning is printed to stderr and the day's file is restarted from
      scratch, so one corrupt log can never abort the whats-new write for
      the whole source.

    Args:
        path: The target file path (e.g. ``whats-new/2026-07-27.md``).  May
            or may not exist on disk.
        section: The rendered ``## `` section to insert (including the
            trailing newline from ``_render_section``).
        source_title: The human-readable source name, used in the
            first-entry header.

    Returns:
        The complete payload string ready for atomic_write.
    """
    # The content file may not exist yet (first entry of the day) or may be
    # empty (e.g. a truncated file from a crashed previous run).  Both cases
    # are treated identically: produce the "first entry" header.  A single
    # ``stat()`` answers both questions at once: an OSError (FileNotFoundError
    # for the not-yet-created file) collapses to size 0, while an existing
    # empty file reports a real size of 0 -- and unlike a separate
    # ``exists()`` + ``stat()`` pair there is no TOCTOU window between the two
    # syscalls in which the file could be deleted or truncated.
    try:
        size = path.stat().st_size
    except OSError:
        size = 0
    if size > 0:
        # Same-day re-run: the file already has a header and at least one
        # section.  We read the existing content, strip any trailing
        # whitespace (the last line already ends with ``\n`` from the
        # previous write), and insert a ``---`` rule plus the new section.
        # Because the read happens under the lock, we see the other
        # process's full entry -- never a partial or interleaved write.
        try:
            existing = path.read_text(encoding="utf-8").rstrip() + "\n"
        except (UnicodeDecodeError, OSError) as exc:
            # A corrupted or unreadable daily file (invalid UTF-8 bytes from
            # a crashed writer, an I/O error) must not abort the whats-new
            # write for the whole source: report it on stderr and fall
            # through to the first-entry header below, exactly as if the
            # file were missing. Appending behind corrupted bytes is not an
            # option -- the result would still fail to decode on every later
            # read.
            print(
                f"  warning: cannot read existing whats-new file {path}: {exc}; "
                "starting today's entry from scratch",
                file=sys.stderr,
            )
        else:
            return f"{existing}\n---\n\n{section}"
    # First entry of the day -- or the fallback for an unreadable/corrupted
    # file (see above): produce the complete file including the explanatory
    # header.  The header tells a human reader what this file is and how to
    # interpret multiple ``## `` sections (which result from repeated runs
    # on the same calendar day).
    header = (
        f"# What's New — {source_title}\n\n"
        f"Auto-generated log of changes detected in the mirrored "
        f"{source_title} documentation. One file per day; multiple runs "
        f"on the same day append a new `## ` section.\n\n---\n\n"
    )
    return f"{header}{section}"


def write_entry(
    whats_new_dir: Path,
    source_title: str,
    changes: ChangeSet,
    now: datetime | None = None,
    lock_timeout: float = 10.0,
) -> Path:
    """Append a change section to today's log file and return its path.

    Raises `ValueError` for an empty ChangeSet: writing a "0 changes" section
    would create noise on every no-op run, and callers are expected to check
    ``changes.is_empty`` first -- reaching this function empty-handed is a
    caller bug worth surfacing loudly.

    Same-day multi-run behavior: the file is keyed by calendar date
    (``whats-new/YYYY-MM-DD.md``), so when the mirror runs several times on
    one day (the scheduled job plus manual runs, say), each run *appends* its
    own timestamped `## ` section behind a ``---`` rule instead of
    overwriting the file. Nothing detected by an earlier run that day is
    ever lost, and the sections read as a chronological timeline within the
    day. A run on a new calendar day starts a fresh file with the
    explanatory header.

    `now` defaults to the current UTC time but can be injected, which keeps
    the filename/section timestamps deterministic in tests.

    `lock_timeout` bounds how long the exclusive-lock acquisition may spin
    before raising `TimeoutError` (platforms where `fcntl` is unavailable
    skip the lock entirely and cannot raise it). Contention is retried until
    the deadline; a PERMANENT lock failure (an unsupported filesystem, say)
    surfaces immediately as the original `OSError` instead of masquerading
    as contention.
    """
    if changes.is_empty:
        raise ValueError("Cannot write a whats-new entry for an empty change set")
    if now is None:
        now = datetime.now(UTC)

    whats_new_dir.mkdir(parents=True, exist_ok=True)
    path = whats_new_dir / f"{_date(now)}.md"
    section = _render_section(changes, now)

    # Concurrent-write safety: the flock is taken on a DEDICATED lock file,
    # never on the content file itself. The content file is swapped by atomic
    # rename (``atomic_write`` stages a temp file and ``Path.replace``s it
    # over the target), so its inode changes on every write -- a flock held
    # on the content file's descriptor would keep guarding the OLD, unlinked
    # inode while a second process opens the NEW inode and acquires its own
    # "exclusive" lock in parallel, breaking mutual exclusion exactly during
    # the read-modify-write window it was meant to protect. The lock file is
    # never renamed or replaced (only opened with O_CREAT), so its inode is
    # stable and every process that opens the path serialises on the same
    # lock object. This is the full race rationale; the comments at the
    # flock call site below summarise against it.
    #
    # One SINGLE lock file per source (``whats-new/.lock``) is used rather
    # than one ``YYYY-MM-DD.md.lock`` per day file. The inode-stability
    # argument above only requires a lock path that is never renamed --
    # any fixed path satisfies it -- and keying the lock by date had a
    # concrete cost: every calendar day left a stale, empty ``*.md.lock``
    # file behind forever, accumulating unboundedly in the git-tracked
    # ``whats-new/`` directory. A per-source lock also serialises writes to
    # DIFFERENT day files (e.g. two processes racing across midnight), which
    # is harmless: the critical section is a small read-plus-write that
    # completes in milliseconds. The leading dot keeps the lock file out of
    # date-ordered listings of the log files it guards.
    lock_path = whats_new_dir / ".lock"
    # The lock file is opened with an explicit mode (0o644) so the permission
    # intent is clear and not left to the platform default (0o777 masked by
    # umask). 0o644 grants read/write to the owner and read-only to group and
    # others -- the lock file carries no secrets and should never be executable.
    # Note that the passed 0o644 is ITSELF masked by the process umask: the
    # effective on-disk mode is ``0o644 & ~umask``, so a stricter umask further
    # restricts permissions (a CI umask of 0o077 yields 0o600, for instance).
    # That is harmless for a secret-free lock file -- tighter is fine, looser
    # is impossible because 0o644 already caps every permission bit.
    lock_fd = os.open(lock_path, os.O_CREAT | os.O_RDWR, mode=0o644)
    try:
        # Acquire an exclusive BSD flock on the LOCK file's descriptor --
        # NOT on the content file itself. Why this must be a separate,
        # never-renamed file (the inode-swap race with atomic_write) is
        # analysed in the comment block above, next to ``lock_path``.
        #
        # The flock is SKIPPED on platforms where ``fcntl`` is unavailable
        # (Windows -- see the guarded import at the top of this module).
        # Losing the lock there is a safe degradation, not a correctness gap:
        # the lock only guards against two mirror processes writing the same
        # day's log concurrently, the pipeline is operated under a
        # single-writer assumption (one scheduled job at a time), and the
        # content write below stays atomic via ``atomic_write`` regardless,
        # so the worst case of a concurrent writer without the lock is a
        # lost or duplicated same-day section -- never a corrupt file.
        if fcntl is not None:
            deadline = time.monotonic() + lock_timeout
            while True:
                try:
                    fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except (BlockingIOError, OSError) as err:
                    # Contention is signalled two ways depending on the
                    # platform: Python maps EAGAIN/EWOULDBLOCK to
                    # ``BlockingIOError`` for file locks, but some systems
                    # raise a plain ``OSError`` carrying those errnos. Every
                    # OTHER errno is a permanent environment failure (e.g.
                    # ENOLCK or EOPNOTSUPP on a mount without flock support)
                    # that no amount of retrying can fix -- surface it
                    # immediately instead of burning the full timeout and
                    # then mislabelling it as lock contention.
                    if err.errno not in (errno.EAGAIN, errno.EWOULDBLOCK):
                        raise
                    if time.monotonic() >= deadline:
                        raise TimeoutError(
                            f"Timed out after {lock_timeout}s waiting for lock on {lock_path}"
                        ) from err
                    time.sleep(0.05)
        # Read the existing file (or decide to start fresh) and assemble the
        # final payload under the lock.  Reading outside the lock would race
        # with another process that wrote between our stat() and read_text():
        # the other process's entry would be silently overwritten.  The
        # helper centralises the "same-day append vs first-entry header"
        # logic so the caller (this function) only worries about locking and
        # atomic write, and the helper only worries about content assembly.
        payload = _read_and_prepare_payload(path, section, source_title)
        # Delegate the atomic write (temp file + rename + best-effort cleanup)
        # to the shared utility function.  The lock on the separate lock file
        # is still held during the write and through the content file's inode
        # swap (the lock_fd is only closed in the outer finally), so a second
        # process blocks at flock() above until we release it -- the atomic
        # write runs inside the critical section.
        atomic_write(path, payload)
    finally:
        os.close(lock_fd)
    return path
