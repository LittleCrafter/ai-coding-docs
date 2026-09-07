"""Tests for the whats-new log renderer (mirror.core.whats_new)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone
import os

import pytest
from mirror.core import whats_new
from mirror.core.diff import Change, ChangeSet, Modified, Rename

# Fixed timestamp so rendered headings and file names are deterministic.
_NOW = datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC)


def test_render_section_all_categories():
    """A changeset containing all four categories must render a section with
    a dated heading, the total count, and one subsection per category with
    per-category counts — this is the exact format readers of the whats-new
    logs see, so the strings are pinned verbatim."""
    cs = ChangeSet()
    cs.added.append(Change(slug="a", title="A", source_url="https://x/a"))
    cs.modified.append(Modified(slug="b", title="B", source_url="https://x/b"))
    cs.renamed.append(
        Rename(
            old_slug="o",
            new_slug="n",
            title="T",
            source_url="https://x/n",
            matched_by="source_id",
        )
    )
    cs.removed.append(Change(slug="c", title="C", source_url="https://x/c"))
    out = whats_new._render_section(cs, _NOW)
    assert "## 2026-01-02 03:04 UTC — 4 changes" in out
    assert "### ➕ Added (1)" in out and "- **A**" in out
    assert "### ✏️ Modified (1)" in out
    assert "### 🔀 Renamed / Moved (1)" in out and "`o` → `n`" in out
    assert "### ➖ Removed (1)" in out


def test_write_entry_creates_file_then_appends_same_day(tmp_path):
    """The first write of the day creates a log file with the source title;
    a second write on the same day must append a new section to the same
    file (keyed by date) rather than overwrite or create a new one — multiple
    mirror runs per day must accumulate, not clobber each other."""
    cs1 = ChangeSet()
    cs1.added.append(Change(slug="a", title="A", source_url="https://x/a"))
    p1 = whats_new.write_entry(tmp_path / "wn", "My Source", cs1, now=_NOW)
    assert p1.exists()
    assert p1.read_text(encoding="utf-8").startswith("# What's New — My Source")

    # A second run on the same day appends a new section to the same file.
    cs2 = ChangeSet()
    cs2.removed.append(Change(slug="b", title="B", source_url="https://x/b"))
    p2 = whats_new.write_entry(tmp_path / "wn", "My Source", cs2, now=_NOW)
    assert p2 == p1  # same date -> same file
    text = p2.read_text(encoding="utf-8")
    assert "### ➕ Added" in text  # carried over from the first run
    assert "### ➖ Removed" in text  # from the second run


def test_write_entry_restarts_corrupted_same_day_file(tmp_path, capsys):
    """An existing same-day whats-new file whose bytes are not valid UTF-8
    must not abort the write: the corruption is reported as a warning and
    the day's file is restarted from scratch (header + new section), so a
    crashed writer can never take down the whole whats-new step."""
    cs = ChangeSet()
    cs.added.append(Change(slug="a", title="A", source_url="https://x/a"))
    path = tmp_path / "wn"
    path.mkdir(parents=True)
    target = path / "2026-01-02.md"
    # 0xFF is not decodable as UTF-8, so read_text raises UnicodeDecodeError.
    target.write_bytes(b"\xff\xfe broken bytes")
    written = whats_new.write_entry(path, "My Source", cs, now=_NOW)
    assert written == target
    text = target.read_text(encoding="utf-8")
    assert text.startswith("# What's New — My Source")
    assert "### ➕ Added" in text
    err = capsys.readouterr().err
    assert "warning" in err
    assert "cannot read existing whats-new file" in err


def test_write_entry_rejects_empty_changeset(tmp_path):
    """Writing an entry for a changeset with no changes is a programming
    error (callers must skip empty diffs); it must raise rather than emit an
    empty log section."""
    with pytest.raises(ValueError):
        whats_new.write_entry(tmp_path / "wn", "S", ChangeSet(), now=_NOW)


def test_write_entry_creates_separate_files_for_different_days(tmp_path):
    """Two runs on different calendar days must produce two distinct log files.
    If same-date logic leaked across day boundaries, one day's changes would
    be appended to the other day's file -- or worse, silently lost."""
    cs = ChangeSet()
    cs.added.append(Change(slug="a", title="A", source_url="https://x/a"))
    day1 = datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC)
    day2 = datetime(2026, 1, 3, 3, 4, 5, tzinfo=UTC)
    p1 = whats_new.write_entry(tmp_path / "wn", "Src", cs, now=day1)
    p2 = whats_new.write_entry(tmp_path / "wn", "Src", cs, now=day2)
    assert p1 != p2
    assert p1.name == "2026-01-02.md"
    assert p2.name == "2026-01-03.md"
    assert p1.exists() and p2.exists()


# --- multi-entry same-day with different timestamps ---------------------------


def test_write_entry_multi_entry_same_day_different_timestamps(tmp_path):
    """Multiple entries written on the same calendar day at different times
    must all appear in the same file, each with its own distinct timestamped
    section heading."""
    cs = ChangeSet()
    cs.added.append(Change(slug="a", title="A", source_url="https://x/a"))

    t1 = datetime(2026, 1, 2, 3, 0, 0, tzinfo=UTC)
    t2 = datetime(2026, 1, 2, 15, 30, 0, tzinfo=UTC)

    p = whats_new.write_entry(tmp_path / "wn", "Src", cs, now=t1)
    p = whats_new.write_entry(tmp_path / "wn", "Src", cs, now=t2)

    text = p.read_text(encoding="utf-8")
    assert "2026-01-02 03:00" in text
    assert "2026-01-02 15:30" in text


# --- removed-section escaping -------------------------------------------------


def test_removed_section_escapes_special_chars():
    """Removed-section titles escape Markdown formatting chars (``*``, ``_``,
    ``[``, ``]``) and the backslash itself; backticks are intentionally left
    alone (code spans they open inside ``**bold**`` render acceptably for
    realistic upstream titles, and code-span safety for slugs is handled
    separately by ``_safe_code``)."""
    cs = ChangeSet()
    cs.removed.append(
        Change(
            slug="old-page",
            title=r"Using *emphasis* and \backslash",
            source_url="https://example.com",
        )
    )
    out = whats_new._render_section(cs, _NOW)
    assert r"Using \*emphasis\* and \\backslash" in out


def test_removed_section_leaves_backticks_unescaped():
    """Backticks in titles are NOT escaped by the bold-span escaper. They CAN
    open code spans inside ``**bold**`` (in CommonMark, code spans nest inside
    emphasis), but for realistic upstream titles the nesting renders on one
    line and stays bold, so the visual outcome is acceptable and escaping is
    forgone to keep the raw Markdown clean. This pins the deliberate
    no-escape choice so a future change that silently adds backtick escaping
    here is caught."""
    cs = ChangeSet()
    cs.removed.append(
        Change(
            slug="old-page",
            title="Using `uv` workspaces",
            source_url="https://example.com",
        )
    )
    out = whats_new._render_section(cs, _NOW)
    assert "Using `uv` workspaces" in out
    assert r"\`" not in out


def test_escape_md_html_entity_escapes_amp_lt_gt():
    """``_escape_md`` HTML-entity-escapes ``&``, ``<``, ``>`` (rather than
    backslash-escaping them) so they cannot start an entity reference or an
    inline HTML tag inside the bold title span. This matches the
    title-escape table in ``core.index`` (``_TITLE_ESCAPES``) so the whats-new
    log and the per-source README render these characters consistently. The
    ``&`` pass runs BEFORE ``<``/``>`` so the ``&`` that ``&lt;``/``&gt;``
    introduce is never itself re-escaped into ``&amp;lt;``."""
    cs = ChangeSet()
    cs.added.append(
        Change(
            slug="entities",
            title="A & B < C > D",
            source_url="https://example.com",
        )
    )
    out = whats_new._render_section(cs, _NOW)
    assert "A &amp; B &lt; C &gt; D" in out
    # The wrong double-escaped forms must not appear.
    assert "&amp;lt;" not in out
    assert "&amp;gt;" not in out


def test_escape_md_does_not_double_escape_existing_entities():
    """A title that already contains HTML entities (``A &amp; B &lt; C``,
    as some upstream sources ship pre-escaped titles) must render with each
    entity exactly once. ``_escape_md`` normalizes the input with
    ``html.unescape`` before escaping, so a pre-existing ``&amp;`` collapses
    to a literal ``&`` and is re-escaped to ``&amp;`` -- never to the
    double-escaped ``&amp;amp;`` that a plain escape would produce."""
    cs = ChangeSet()
    cs.added.append(
        Change(
            slug="pre-escaped",
            title="A &amp; B &lt; C",
            source_url="https://example.com",
        )
    )
    out = whats_new._render_section(cs, _NOW)
    # Each entity appears exactly once: unescaped first, then re-escaped.
    assert "A &amp; B &lt; C" in out
    # The double-escaped forms (escape-without-normalize) must not appear.
    assert "&amp;amp;" not in out
    assert "&amp;lt;" not in out


# --- source-link destinations -----------------------------------------------------


def test_source_links_angle_bracketed_for_special_chars():
    """Every ``[source]`` link emission site (added/modified bullets, rename
    lines, removal lines) must wrap the URL in angle brackets: the URL is
    interpolated raw, so a space or ``)`` in it would terminate a bare
    ``(...)`` destination early and break the rendered link."""
    url = "https://example.com/docs/v1 (stable)/guide"
    cs = ChangeSet()
    cs.added.append(Change(slug="a", title="A", source_url=url))
    cs.renamed.append(
        Rename(
            old_slug="o",
            new_slug="n",
            title="T",
            source_url=url,
            matched_by="source_id",
        )
    )
    cs.removed.append(Change(slug="c", title="C", source_url=url))
    out = whats_new._render_section(cs, _NOW)
    # The exact bracketed URL appears once per emission site used above.
    assert out.count(f"[source](<{url}>)") == 3


def test_source_links_sanitize_forbidden_destination_chars():
    """Every ``[source]`` link emission site must percent-encode the
    characters that angle brackets do NOT make safe: CommonMark forbids
    unescaped ``<``, ``>``, and line endings inside a ``<...>`` destination.
    A raw newline in particular would split the rendered bullet across two
    lines, silently breaking the log's Markdown. Encoding (not stripping)
    keeps the emitted URL valid and decodable back to the original."""
    url = "https://example.com/a<b>\nc>d"
    safe = "https://example.com/a%3Cb%3E%0Ac%3Ed"
    cs = ChangeSet()
    cs.added.append(Change(slug="a", title="A", source_url=url))
    cs.renamed.append(
        Rename(
            old_slug="o",
            new_slug="n",
            title="T",
            source_url=url,
            matched_by="source_id",
        )
    )
    cs.removed.append(Change(slug="c", title="C", source_url=url))
    out = whats_new._render_section(cs, _NOW)
    # The sanitized URL appears once per emission site used above, and the
    # raw URL (with its literal ``<`` and newline) appears nowhere.
    assert out.count(f"[source](<{safe}>)") == 3
    assert url not in out


def test_as_utc_converts_aware_non_utc_datetime():
    """An aware datetime in a non-UTC timezone must be converted to true UTC
    before the date key and timestamp are derived: 01:30 at UTC+05:00 is
    still the PREVIOUS day in UTC, and labeling it with the local date would
    both mislabel the timezone and split one run's changes across two log
    files depending on where CI ran."""
    local = datetime(2026, 1, 2, 1, 30, tzinfo=timezone(timedelta(hours=5)))
    assert whats_new._as_utc(local) == datetime(2026, 1, 1, 20, 30, tzinfo=UTC)
    assert whats_new._date(local) == "2026-01-01"
    assert whats_new._stamp(local) == "2026-01-01 20:30 UTC"


# --- _escape_md backslash-before-special-chars ordering -------------------------


def test_escape_md_backslash_before_special_chars():
    """``_escape_md`` escapes the backslash FIRST (``\\`` → ``\\\\``) before
    escaping Markdown formatting characters (``*``, ``_``, ``[``, ``]``), so a
    title containing ``\\*test`` renders as ``\\\\\\*test`` — the backslash is
    doubled first, then the star is escaped. If the order were reversed the
    output would be ``\\\\\\\\*test`` (star escaped to ``\\*``, then the
    injected backslash doubled again), which is never correct."""
    cs = ChangeSet()
    cs.added.append(
        Change(
            slug="escape-test",
            title=r"\*test",
            source_url="https://example.com",
        )
    )
    out = whats_new._render_section(cs, _NOW)
    # Correct form: backslash escaped (\\), then star escaped (\*) → \\\*test.
    assert r"\\\*test" in out
    # Wrong forms from reversed or incomplete escaping must not appear.
    assert r"\\\\*test" not in out


def test_as_utc_assumes_naive_datetime_is_utc():
    """A naive datetime (no tzinfo) is assumed to already be UTC rather than
    silently interpreted as local time -- the pipeline's own caller always
    passes ``datetime.now(UTC)``, so a naive value only arrives from tests
    or future callers, and assuming UTC beats mislabeling a local time."""
    naive = datetime(2026, 1, 2, 3, 4, 5)
    assert whats_new._as_utc(naive) == datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC)


def test_escape_md_collapses_newlines_and_carriage_returns():
    """Newlines and carriage returns inside a title must be collapsed to
    spaces, not emitted raw: titles come from upstream Markdown and can
    contain anything, and a literal line break would split the bullet across
    two lines, breaking the log's one-line-per-change layout with a stray
    malformed line. The collapsed title must stay a single bullet line."""
    cs = ChangeSet()
    cs.added.append(
        Change(
            slug="multiline",
            title="First line\nsecond line\r\nthird\rline",
            source_url="https://example.com",
        )
    )
    out = whats_new._render_section(cs, _NOW)
    assert "- **First line second line third line**" in out
    # The title's bullet must occupy exactly one line in the rendered log.
    bullet_lines = [ln for ln in out.splitlines() if ln.startswith("- **First")]
    assert len(bullet_lines) == 1
    # No fragment of the original multiline title may leak onto its own line.
    assert "second line" not in [ln.strip() for ln in out.splitlines()]


# --- lock file mechanism -------------------------------------------------------


def test_write_entry_creates_and_reuses_lock_file(tmp_path):
    """``write_entry`` must create a single dedicated ``.lock`` file per
    whats-new directory and reuse it across multiple writes. The lock file's
    inode never changes (it is never renamed), so ``flock`` exclusion holds
    across the content file's atomic replacement.

    The lock file is the fix for the inode-swap race: before this change,
    flock was acquired directly on the content file descriptor, and the
    subsequent ``tmp_path.replace(path)`` swapped the content file's inode --
    breaking the lock and allowing a second concurrent writer to acquire its
    own lock on the new inode before the first writer released. The separate
    lock file (never replaced) keeps the lock valid across the full
    read-modify-write cycle.

    There is exactly ONE lock file per source (``whats-new/.lock``), not one
    ``YYYY-MM-DD.md.lock`` per day file: the inode-stability argument only
    needs a never-renamed path, and per-day lock files accumulated stale
    empty files in the git-tracked log directory forever.
    """
    wn_dir = tmp_path / "wn"
    cs = ChangeSet()
    cs.added.append(Change(slug="a", title="A", source_url="https://x/a"))

    # First write creates both the content file and the lock file.
    p1 = whats_new.write_entry(wn_dir, "Test", cs, now=_NOW)
    assert p1.exists()
    lock_path = wn_dir / ".lock"
    assert lock_path.exists(), (
        "write_entry must create a .lock file in the whats-new directory"
    )

    # Second write to the same day reuses the same lock file.
    cs2 = ChangeSet()
    cs2.added.append(Change(slug="b", title="B", source_url="https://x/b"))
    p2 = whats_new.write_entry(wn_dir, "Test", cs2, now=_NOW)
    assert p2 == p1
    assert lock_path.exists()

    # Both entries are present (the second write appended, not overwrote).
    # Assert on the full distinctive bullet lines that the nested bullet()
    # helper in whats_new._render_section emits
    # (``- **Title** — `slug` — [source](<url>)``), never on single
    # letters or fragments: "A"/"B" would trivially match section headings
    # like "Added" or "Test" even if the second write had silently replaced
    # rather than appended the content.
    content = p2.read_text(encoding="utf-8")
    assert "- **A** — `a` — [source](<https://x/a>)" in content
    assert "- **B** — `b` — [source](<https://x/b>)" in content


def test_write_entry_lock_file_is_never_replaced(tmp_path):
    """The lock file's inode must remain stable across writes. Verify that the
    lock file is opened with ``os.open`` (no truncation) and never renamed --
    the content file gets atomic replacement via temp file + rename, but the
    lock file stays put with its original inode. This is the property that
    keeps ``flock`` exclusion valid: other processes opening the same lock
    path always reach the same inode."""
    wn_dir = tmp_path / "wn"
    cs = ChangeSet()
    cs.added.append(Change(slug="x", title="X", source_url="https://x/x"))

    whats_new.write_entry(wn_dir, "Test", cs, now=_NOW)
    lock_path = wn_dir / ".lock"

    # Record the lock file's inode after first write.
    inode_before = os.stat(lock_path).st_ino

    # Second write reuses the same lock file.
    cs2 = ChangeSet()
    cs2.added.append(Change(slug="y", title="Y", source_url="https://x/y"))
    whats_new.write_entry(wn_dir, "Test", cs2, now=_NOW)

    # The lock file's inode must be unchanged -- it was never replaced.
    inode_after = os.stat(lock_path).st_ino
    assert inode_before == inode_after, (
        f"Lock file inode changed ({inode_before} -> {inode_after}); "
        "the lock file must never be replaced, or flock exclusion breaks"
    )


def test_write_entry_single_lock_file_across_days(tmp_path):
    """Writes on DIFFERENT calendar days must still share the single
    per-source ``.lock`` file, and no per-day ``*.md.lock`` files may be
    created. This pins the fix for lock-file accumulation: previously every
    calendar day left a stale, empty ``YYYY-MM-DD.md.lock`` behind forever
    in the git-tracked whats-new directory."""
    wn_dir = tmp_path / "wn"
    cs = ChangeSet()
    cs.added.append(Change(slug="a", title="A", source_url="https://x/a"))
    day1 = datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC)
    day2 = datetime(2026, 1, 3, 3, 4, 5, tzinfo=UTC)
    whats_new.write_entry(wn_dir, "Test", cs, now=day1)
    whats_new.write_entry(wn_dir, "Test", cs, now=day2)

    names = sorted(p.name for p in wn_dir.iterdir())
    assert names == [".lock", "2026-01-02.md", "2026-01-03.md"]
    # Explicitly: no per-day lock files anywhere.
    assert not list(wn_dir.glob("*.md.lock"))


# --- optional fcntl import (platforms without flock) ----------------------------


def test_write_entry_without_fcntl_produces_identical_output(tmp_path, monkeypatch):
    """When ``fcntl`` is unavailable (``whats_new.fcntl is None`` -- the
    Windows fallback of the guarded import at module top), ``write_entry``
    must skip the flock but produce BYTE-IDENTICAL log output: the lock is a
    best-effort guard against concurrent writers, not part of the content,
    and the write itself stays atomic via ``atomic_write`` either way.

    The monkeypatch simulates a platform without ``fcntl`` on this POSIX
    test host. Both the first-entry-of-the-day path (header creation) and
    the same-day append path (``---`` rule + new section) are exercised,
    then compared against the locked equivalents written into a separate
    directory."""
    cs1 = ChangeSet()
    cs1.added.append(Change(slug="a", title="A", source_url="https://x/a"))
    cs2 = ChangeSet()
    cs2.removed.append(Change(slug="b", title="B", source_url="https://x/b"))

    # Locked reference output (fcntl intact).
    p_locked = whats_new.write_entry(tmp_path / "locked", "Src", cs1, now=_NOW)
    whats_new.write_entry(tmp_path / "locked", "Src", cs2, now=_NOW)

    # Unlocked output: flock skipped because fcntl is None.
    monkeypatch.setattr(whats_new, "fcntl", None)
    p_unlocked = whats_new.write_entry(tmp_path / "unlocked", "Src", cs1, now=_NOW)
    whats_new.write_entry(tmp_path / "unlocked", "Src", cs2, now=_NOW)

    assert p_unlocked.read_text(encoding="utf-8") == p_locked.read_text(
        encoding="utf-8"
    )


def test_write_entry_lock_timeout_raises_timeout_error(tmp_path):
    """When a lock is held by another process or descriptor and the timeout expires,
    write_entry must raise a TimeoutError."""
    if whats_new.fcntl is None:
        pytest.skip("fcntl not available on this platform")
    wn_dir = tmp_path / "wn"
    wn_dir.mkdir()
    lock_file = wn_dir / ".lock"
    fd = os.open(lock_file, os.O_CREAT | os.O_RDWR, 0o644)
    try:
        whats_new.fcntl.flock(fd, whats_new.fcntl.LOCK_EX)
        cs = ChangeSet()
        cs.added.append(Change(slug="a", title="A", source_url="https://x/a"))
        with pytest.raises(
            TimeoutError, match="Timed out after 0.05s waiting for lock"
        ):
            whats_new.write_entry(wn_dir, "Src", cs, lock_timeout=0.05)
    finally:
        os.close(fd)
