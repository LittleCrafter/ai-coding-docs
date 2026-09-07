"""Tests for structural change detection (mirror.core.diff)."""

from __future__ import annotations

from conftest import make_entry
from mirror.core import diff
from mirror.core.manifest import FileEntry, Manifest


def _manifest(entries: dict[str, FileEntry]) -> Manifest:
    """Wrap raw entries in a Manifest, mimicking the stored 'old' baseline
    side of a diff (the 'new' side is passed as a plain dict)."""
    return Manifest(files=dict(entries))


def test_baseline_old_none_is_empty():
    """A missing baseline (None) with no new files must yield an empty
    changeset. Guards the first-ever-run path of a source, before any
    manifest has been written."""
    assert diff.diff(None, {}).is_empty


def test_no_changes_is_empty():
    """Identical old and new manifests must produce an empty changeset —
    the common no-op case between two consecutive mirror runs."""
    files = {"a": make_entry("a")}
    assert diff.diff(_manifest(files), files).is_empty


def test_added_and_removed():
    """Slugs only in the new manifest are 'added', slugs only in the old are
    'removed'. With different source ids (the default here) a slug swap must
    not be misread as a rename."""
    old = _manifest({"a": make_entry("a", title="Page A")})
    new = {"b": make_entry("b", title="Page B")}
    cs = diff.diff(old, new)
    assert [c.slug for c in cs.added] == ["b"]
    assert [c.slug for c in cs.removed] == ["a"]
    assert cs.renamed == []


def test_modified_on_hash_change():
    """Same slug, different content hash => 'modified'. This is what drives
    the Modified section of the whats-new log when an upstream page changes."""
    old = _manifest({"a": make_entry("a", hash="h1")})
    new = {"a": make_entry("a", hash="h2")}
    cs = diff.diff(old, new)
    assert [m.slug for m in cs.modified] == ["a"]
    assert cs.added == [] and cs.removed == []


def test_rename_by_source_id():
    """Rename detection prefers the stable upstream id: a page that changes
    slug but keeps its source_id is reported as a rename, so a moved page
    reads as a move in the log instead of a deletion plus an addition."""
    # A page that moves slug but keeps its stable upstream id is one rename,
    # not a separate add + remove.
    old = _manifest({"cli/old": make_entry("cli/old", source_id="cli-overview")})
    new = {"cli/new": make_entry("cli/new", source_id="cli-overview")}
    cs = diff.diff(old, new)
    assert cs.added == [] and cs.removed == []
    assert len(cs.renamed) == 1
    r = cs.renamed[0]
    assert (r.old_slug, r.new_slug, r.matched_by) == ("cli/old", "cli/new", "source_id")


def test_blank_source_id_never_matched_as_rename():
    """A removed page and an added page that BOTH carry a blank (empty or
    whitespace-only) source_id must be reported as add + remove, NEVER as a
    rename: a blank id carries no identity information, yet both pages would
    be filed under the same empty key in the uniqueness indexes, and when
    each side holds exactly one blank-id page that key is "unique" on both
    sides -- the uniqueness check would happily pair two unrelated pages
    into a fabricated rename.

    ``FileEntry.__post_init__`` rejects blank ids, so the entries are built
    with valid ids and then mutated: the diff guard is defensive (it must
    not silently depend on every caller's validation), and the test must
    reach it the same way a corrupt hand-built manifest would. The two
    titles are deliberately distinct so the title fallback (pass 2) cannot
    pair the pages either."""
    old_entry = make_entry("old", source_id="x", title="Old Title")
    old_entry.source_id = " "
    new_entry = make_entry("new", source_id="y", title="New Title")
    new_entry.source_id = ""
    cs = diff.diff(_manifest({"old": old_entry}), {"new": new_entry})
    assert cs.renamed == []
    assert [c.slug for c in cs.added] == ["new"]
    assert [c.slug for c in cs.removed] == ["old"]


def test_rename_by_title_fallback():
    """When source ids differ but the titles match exactly (and are not
    generic), the title fallback still pairs the pages as a rename."""
    old = _manifest(
        {"old": make_entry("old", source_id="x", title="Configuring Agents")}
    )
    new = {"new": make_entry("new", source_id="y", title="Configuring Agents")}
    cs = diff.diff(old, new)
    assert len(cs.renamed) == 1
    assert cs.renamed[0].matched_by == "title"
    assert cs.added == [] and cs.removed == []


def test_rename_by_title_case_insensitive():
    """Title-based rename matching must be case-insensitive: an upstream
    retitle that only tweaks casing while moving the page ("Getting Started"
    -> "getting started") is still one rename, not an add plus a remove.
    Note 'Getting started' is in the generic-title blocklist in lowercase,
    so this scenario uses a specific title whose casing changed."""
    old = _manifest(
        {"old": make_entry("old", source_id="x", title="Advanced Configuration")}
    )
    new = {"new": make_entry("new", source_id="y", title="advanced configuration")}
    cs = diff.diff(old, new)
    assert len(cs.renamed) == 1
    r = cs.renamed[0]
    assert (r.old_slug, r.new_slug, r.matched_by) == ("old", "new", "title")
    # The displayed title keeps the old entry's original casing.
    assert r.title == "Advanced Configuration"
    assert cs.added == [] and cs.removed == []


def test_generic_title_not_used_for_rename():
    """Generic titles like 'Overview' appear on many pages, so they must not
    be trusted for rename pairing — otherwise unrelated pages would be
    chained into bogus renames."""
    # "Overview" is too generic to pair on -> falls back to add + remove.
    old = _manifest({"old": make_entry("old", source_id="x", title="Overview")})
    new = {"new": make_entry("new", source_id="y", title="Overview")}
    cs = diff.diff(old, new)
    assert cs.renamed == []
    assert [c.slug for c in cs.added] == ["new"]
    assert [c.slug for c in cs.removed] == ["old"]


def test_normalized_title_strips_multi_extension_suffixes():
    """Titles that are really filenames with several stacked registered
    extensions must canonicalize down to their semantic title, not just lose
    the outermost extension: "x.html.md" must normalize to "x", not "x.html".
    Stripping repeats until no registered suffix matches, so every stacked
    suffix is removed regardless of order."""
    assert diff._normalized_title("x.html.md") == "x"
    assert diff._normalized_title("x.md.html") == "x"
    assert diff._normalized_title("index.htm") == "index"


def test_rename_ambiguous_on_removed_side_is_not_matched():
    """Rename matching requires the key to be unique on BOTH sides: when two
    removed slugs share one added slug's source_id, pairing either of them
    with the added slug would be an arbitrary guess, so no rename is
    fabricated at all and the pages are reported as plain add/remove."""
    old = _manifest(
        {
            "a": make_entry("a", source_id="shared"),
            "b": make_entry("b", source_id="shared"),
        }
    )
    new = {"c": make_entry("c", source_id="shared")}
    cs = diff.diff(old, new)
    assert cs.renamed == []
    assert {c.slug for c in cs.removed} == {"a", "b"}
    assert [c.slug for c in cs.added] == ["c"]


def test_rename_one_to_one_invariant():
    """Rename matching is one-to-one: each removed slug and each added slug
    may participate in at most one rename pair, even when several distinct
    renames happen in one run."""
    old = _manifest(
        {
            "a": make_entry("a", source_id="sid-a"),
            "b": make_entry("b", source_id="sid-b"),
        }
    )
    new = {
        "x": make_entry("x", source_id="sid-a"),
        "y": make_entry("y", source_id="sid-b"),
    }
    cs = diff.diff(old, new)
    assert cs.added == [] and cs.removed == []
    assert {(r.old_slug, r.new_slug) for r in cs.renamed} == {("a", "x"), ("b", "y")}


def test_changeset_total_matches_sum():
    """`total` must equal the sum of all four change categories; downstream
    code (log headings, no-change short-circuits) relies on this bookkeeping.
    Here: 1 modified + 1 added = 2."""
    old = _manifest({"a": make_entry("a", hash="h1")})
    new = {"a": make_entry("a", hash="h2"), "b": make_entry("b")}
    cs = diff.diff(old, new)
    expected = len(cs.added) + len(cs.removed) + len(cs.modified) + len(cs.renamed)
    assert cs.total == expected
    assert cs.total == 2
