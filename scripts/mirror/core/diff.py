"""Structural change detection between the previous manifest and a run.

Categorizes every change as added / removed / modified / renamed:

  * added     - a slug present now but not before
  * removed   - a slug gone (possibly deprecated)
  * modified  - a slug in both whose content hash changed
  * renamed   - a vanished slug paired with an appeared slug sharing the same
                `source_id` (or a specific-enough title) -> reported as a move

`source_id` is a source-specific stable upstream identifier (the upstream
markdown filename, the canonical path, the GitHub path, ...), so a page that
moves URL but keeps its source identity is recognized as a rename.

Rename detection matters beyond cosmetics: without it, a page that simply
moved would show up as one removal plus one addition, drowning real changes
in noise every time an upstream reorganizes its docs. The matching itself is
strictly one-to-one and two-pass -- see `diff` for the algorithm and its
invariants.
"""

from __future__ import annotations

from collections.abc import Callable, Collection
from dataclasses import dataclass, field

from .manifest import FileEntry, Manifest

# Titles too generic to be evidence of identity. An upstream reorganization
# can easily have two different pages both titled "Overview" or "Settings";
# matching a removed "Overview" to an added "Overview" would fabricate a
# rename between unrelated pages. These are matched case-insensitively after
# stripping -- see `_usable_title`.
#
# Concrete false-positive this prevents: say a source once had
# ``cli/overview`` and ``api/overview`` (two distinct pages, both titled
# "Overview"), and a reorganization replaces them with ``guides/overview``.
# Without this filter, pass 2 of rename detection could pair the vanished
# ``cli/overview`` with the appeared ``guides/overview`` purely because the
# titles coincide, reporting a "rename" for a page that was actually deleted
# while a brand-new one was created. With the filter, a generic title is
# never accepted as identity evidence, so all three pages are honestly
# reported as removals plus an addition. The cost of that caution is
# negligible: a *real* move of a generically-titled page is still detected
# in pass 1 whenever its ``source_id`` survives the move.
#
# Every entry here must be at least 4 characters long: ``_usable_title``
# rejects any canonical title shorter than 4 characters BEFORE consulting
# this set, so a shorter entry (e.g. "faq" or "api") would be unreachable
# dead weight -- those titles are already excluded by the length check.
_GENERIC_TITLES = {
    "overview",
    "settings",
    "features",
    "introduction",
    "getting started",
    "reference",
    "index",
    "home",
    "configuration",
    "usage",
    "setup",
    "guide",
    "quickstart",
    "troubleshooting",
    "examples",
    "installation",
    "api reference",
    "readme",
    "changelog",
    "about",
    "help",
    "support",
    "contributing",
    "license",
    "prerequisites",
    "migration",
    "quick start",
    "glossary",
    "summary",
    "notes",
    "status",
    "faqs",
    "tutorials",
    "samples",
    "releases",
    "limitations",
    "dependencies",
}


@dataclass
class Change:
    """One added or removed page (the same shape serves both categories).

    `Change` and `Modified` are intentionally *parallel* record types: they
    currently carry the same three fields, but neither pipeline nor reporting
    imports the classes by name (they only consume `ChangeSet`'s lists), so
    the duplication is cheap -- and merging them (or aliasing one to the
    other) would make a future field that applies to only one category a
    breaking change. Keep them separate.
    """

    slug: str
    title: str
    source_url: str


@dataclass
class Modified:
    """One page whose content hash changed between runs.

    Kept as a separate class from `Change` (rather than a flag on it) so a
    future field -- old/new hash, diff size -- can be added to modifications
    without touching the add/remove shape. See `Change` for why the
    duplication between the two is deliberate.
    """

    slug: str
    title: str
    source_url: str


@dataclass
class Rename:
    """One page recognized as moved: vanished `old_slug` paired with appeared `new_slug`.

    `matched_by` records which signal established the pair ("source_id" or
    "title") and is surfaced in the whats-new log, so a suspicious title-based
    match can be spotted and audited after the fact.
    """

    old_slug: str
    new_slug: str
    title: str
    source_url: str
    matched_by: str  # "source_id" | "title"


@dataclass
class ChangeSet:
    """The full structural diff between two runs of one source.

    Lists default to empty via ``default_factory`` so `diff` can build the
    result incrementally with plain ``append`` calls.

    **When to use each category (and how they differ).** The four lists model
    distinct semantic events; choosing the right one matters because the
    whats-new log and the console summary render each category differently:

    * ``added`` -- a slug that appears in the new manifest but was absent from
      the old one. Reported as "new page" in whats-new. Uses ``Change``
      (slug, title, source_url);
    * ``removed`` -- a slug that was present in the old manifest but is absent
      from the new one. Reported as "possibly deprecated" in whats-new. Uses
      ``Change`` (same shape as ``added`` -- the two are semantically dual);
    * ``modified`` -- a slug present in BOTH manifests whose content hash
      changed between runs. Reported as "modified" in whats-new. Uses
      ``Modified`` which TODAY carries the same three fields as ``Change``
      (slug, title, source_url), but is a SEPARATE class from ``Change`` so
      that a future field -- old/new hash, diff size in bytes, number of
      changed lines -- can be added to modifications WITHOUT touching the
      add/remove shape. Merging ``Modified`` into ``Change`` with a flag
      would make that future addition a breaking change to the add/remove
      consumers that do not need it;
    * ``renamed`` -- a page recognised as the same document moved to a new
      slug. Discovered in two passes: first by ``source_id`` equality (the
      strongest signal -- the stable upstream identity survives the move),
      then by canonical title match on whatever is left (restricted to
      specific-enough titles via ``_GENERIC_TITLES``). Uses ``Rename`` which
      carries BOTH the old and new slugs plus ``matched_by`` so the heuristic
      title matches can be audited after the fact.

    ``is_empty`` is the single check the pipeline uses to decide whether to
    skip the whats-new entry and the manifest/index rewrite; it is True only
    when ALL four lists are empty, which means the run detected zero
    structural change against the previous manifest.
    """

    added: list[Change] = field(default_factory=list)
    removed: list[Change] = field(default_factory=list)
    modified: list[Modified] = field(default_factory=list)
    renamed: list[Rename] = field(default_factory=list)

    @property
    def is_empty(self) -> bool:
        """True when nothing at all changed (used to skip whats-new entries)."""
        return not (self.added or self.removed or self.modified or self.renamed)

    @property
    def total(self) -> int:
        """Total number of changes across all four categories."""
        return (
            len(self.added) + len(self.removed) + len(self.modified) + len(self.renamed)
        )


def _normalized_title(title: str) -> str:
    """Canonical form of a title, used for *both* the generic-title check and
    the pass-2 rename comparison.

    Normalization steps, in order:

      1. strip surrounding whitespace and ``casefold`` (Unicode's designated
         caseless-matching operation, preferred over ``lower``), so a pure
         casing tweak during a move ("Getting Started" -> "getting started")
         still matches;
      2. strip trailing punctuation (``.,!?``), so "Overview." and "Overview"
         canonicalize identically;
      3. strip trailing file extension(s) (``.html``/``.md``/``.htm``): the
         stripping repeats until no known extension sits at the end, so a
         title that is really a filename canonicalizes to its semantic
         title ("index.html" -> "index") -- including multi-extension
         names, where several registered suffixes stack and every one of
         them must be removed ("x.html.md" -> "x", "x.md.html" -> "x"). A
         single pass over the extension tuple would stop after the first
         match and leave an earlier suffix behind ("x.html.md" -> "x.html"),
         which is why the strip must loop;
      4. strip whitespace *again*: step 3 can expose trailing whitespace that
         step 1 could not see ("Overview .md" -> "overview " -> "overview").

    Using one canonical form for both `_usable_title` and the pass-2 equality
    comparison is load-bearing: if the two saw different normalizations, a
    title could pass the generic check yet compare unequal to an identical
    title on the other side (or vice versa), producing silent false-negative
    renames.
    """
    t = title.strip().casefold().rstrip(".,!?")
    # Strip registered extension suffixes repeatedly, not just once: a single
    # pass over the extension tuple removes at most one suffix per extension
    # and never re-checks what remains, so a multi-extension title like
    # "x.html.md" would end up as "x.html". Loop until a full pass removes
    # nothing, guaranteeing every stacked suffix is gone ("x.html.md" -> "x").
    while True:
        stripped_any = False
        for ext in (".html", ".md", ".htm"):
            if t.endswith(ext):
                t = t[: -len(ext)]
                stripped_any = True
        if not stripped_any:
            break
    return t.strip()


def _usable_title(title: str) -> bool:
    """Whether a title is specific enough to identify a page for rename matching.

    Two rejections: titles under 4 characters ("FAQ", "CLI") and titles in
    `_GENERIC_TITLES`. In both cases a match proves nothing -- many unrelated
    pages share them -- so pass 2 simply skips such pages and lets them be
    reported as a plain add/remove pair instead of a fabricated move. The
    check runs on the canonical form from `_normalized_title`, so a generic
    title wearing a disguise ("Overview.", "index.html", "Overview .md") is
    still recognized as generic.
    """
    t = _normalized_title(title)
    return len(t) >= 4 and t not in _GENERIC_TITLES


def _unique_index(slugs: Collection[str], key: Callable[[str], str]) -> dict[str, str]:
    """Map ``key(slug) -> slug`` for keys that occur exactly once.

    Keys shared by two or more slugs are dropped from the result entirely.
    Rename matching is only sound when the matching key identifies *one*
    candidate on *each* side: if two added pages share a key with a removed
    page (or two removed pages share it), any pairing would be an arbitrary
    guess, so ambiguous keys are excluded up front and those pages fall
    through to plain add/remove reporting. Building this index once per pass
    replaces a pairwise O(N x M) scan of every removed slug against every
    added slug with O(1) dict lookups, and because only globally-unique keys
    can match, consuming a pair can never change the ambiguity of any other
    key -- the index stays valid for the whole pass (no stale-count
    bookkeeping needed).

    The ``slugs`` parameter is typed ``Collection[str]`` (not ``Iterable``)
    and is materialised into a list at the top because the function iterates
    it TWICE: once to count key occurrences and once to build the returned
    dict. A one-shot iterable (e.g. a generator) would be exhausted by the
    first loop, and the second pass would then silently see an empty sequence
    and yield ``{}`` -- a soundness bug rather than a crash. All four current
    callers pass ``sorted(...)`` lists, so the ``list()`` call is a no-op for
    them today; it exists to keep the function correct for any input.
    """
    # Materialise once so the counting loop and the return comprehension
    # iterate the SAME data (see the docstring for why a single pass over a
    # raw iterable would silently break the uniqueness check).
    slugs = list(slugs)
    counts: dict[str, int] = {}
    keys: dict[str, str] = {}
    for slug in slugs:
        k = key(slug)
        keys[slug] = k
        counts[k] = counts.get(k, 0) + 1
    return {keys[slug]: slug for slug in slugs if counts[keys[slug]] == 1}


def diff(old: Manifest | None, new_files: dict[str, FileEntry]) -> ChangeSet:
    """Compare the previous manifest against this run's entries.

    `old` is ``None`` on the very first run of a source (no manifest on disk
    yet); an empty ChangeSet is returned then, because there is no baseline to
    meaningfully diff against -- reporting every page as "added" would spam
    the whats-new log with a wall of initial-mirror noise.

    Rename detection runs first and in two passes, each strictly one-to-one:

      1. by `source_id` -- the stable upstream identity, the strongest signal
         (pages with a blank ``source_id`` are excluded: a blank id carries no
         identity information and must never pair two unrelated pages);
      2. by title match on whatever is left, restricted to titles that are
         specific enough to be meaningful (`_usable_title`); titles are
         compared in canonical form (see `_normalized_title`) so a casing or
         punctuation tweak during a move is still recognized as a rename.

    In both passes a pair is only formed when the matching key is unique on
    *both* sides; an ambiguous key (two removed pages sharing one added
    page's key, or vice versa) would make any pairing an arbitrary guess, so
    those pages fall through to plain add/remove reporting.

    Whatever remains unmatched after both passes is categorized as a genuine
    add or remove; slugs present in both runs are "modified" only when their
    content hash differs.
    """
    changes = ChangeSet()
    if old is None:
        return changes  # baseline run: nothing to diff against

    old_files = old.files
    old_slugs = set(old_files)
    new_slugs = set(new_files)

    added_slugs = new_slugs - old_slugs
    removed_slugs = old_slugs - new_slugs

    # --- Rename / move detection ---------------------------------------------
    # Pair vanished slugs with appeared slugs so that a page which simply moved
    # is reported once as a rename rather than as a separate add + remove.
    #
    # Two passes, each producing strictly one-to-one matches:
    #   1. source_id primary  -- the strongest signal (same upstream identity);
    #   2. title fallback      -- only for leftovers, and only when the title is
    #      specific enough to be meaningful (see `_usable_title`); compared in
    #      canonical form (see `_normalized_title`) so a casing/punctuation
    #      tweak during a move still matches.
    #
    # Both passes share one matching rule: a pair is formed only when the
    # matching key (source_id, resp. canonical title) is *unique on both
    # sides*. Uniqueness is what makes a match sound -- if two removed pages
    # share a key with one added page (or vice versa), any pairing would be
    # an arbitrary guess, so ambiguous keys are skipped and those pages are
    # reported as a plain add/remove instead of a fabricated rename. The
    # `_unique_index` helper pre-computes the unique-key lookup for each
    # side, so matching is a pair of O(1) dict lookups per candidate instead
    # of scanning every removed slug against every added slug (O(N x M)).
    # Because only globally-unique keys can match, consuming a pair can never
    # make another key ambiguous or unambiguous, so the indexes stay valid
    # for the whole pass without any decrement/recompute bookkeeping.
    remaining_removed = set(removed_slugs)
    remaining_added = set(added_slugs)

    # Pass 1: match on the stable upstream identifier (source_id). Pages
    # whose source_id is blank are skipped by the loop below: a blank id is
    # not identity evidence, so it must never serve as a rename key.
    removed_by_sid = _unique_index(
        sorted(removed_slugs), lambda s: old_files[s].source_id
    )
    added_by_sid = _unique_index(sorted(added_slugs), lambda s: new_files[s].source_id)
    for r in sorted(removed_slugs):
        sid = old_files[r].source_id
        # Never match on a blank (empty or whitespace-only) source_id.
        # ``FileEntry.__post_init__`` already rejects blank ids, so this guard
        # cannot fire on manifest-sourced data today -- it is defensive, so
        # the soundness of rename detection does not silently depend on every
        # caller's validation. Why a blank id is dangerous here: a removed
        # page and an added page that BOTH have a blank source_id would be
        # filed under the same empty key in the two ``_unique_index`` maps;
        # when each side happens to hold exactly one blank-id page, that key
        # is "unique" on both sides, and the uniqueness check below would
        # happily pair two completely unrelated pages into a fabricated
        # rename. Skipping blank ids lets such pages fall through to pass 2
        # (title match) or to plain add/remove reporting instead.
        if not sid.strip():
            continue
        # Skip when r's source_id is ambiguous on the removed side (r is not
        # the unique holder of this key) or unmatched/ambiguous on the added
        # side (no unique holder there either).
        if removed_by_sid.get(sid) != r:
            continue
        a = added_by_sid.get(sid)
        if a is None:
            continue
        changes.renamed.append(
            Rename(
                old_slug=r,
                new_slug=a,
                # Prefer the new title (upstream may have retitled the
                # page while moving it); fall back to the old one if
                # the new entry somehow has none.
                title=new_files[a].title or old_files[r].title,
                source_url=new_files[a].source_url,
                matched_by="source_id",
            )
        )
        remaining_removed.discard(r)
        remaining_added.discard(a)

    # Pass 2: for everything still unmatched, fall back to a title match.
    # The indexes are (re)built here, *after* pass 1 consumed its pairs, so
    # they cover exactly the leftover pages. Only the removed side is checked
    # for `_usable_title`: usability depends solely on the canonical title,
    # and an added page can only key-match a removed page when their
    # canonical titles are equal -- hence equally usable. The *displayed*
    # rename title keeps the old entry's original casing.
    removed_by_title = _unique_index(
        sorted(remaining_removed), lambda s: _normalized_title(old_files[s].title)
    )
    added_by_title = _unique_index(
        sorted(remaining_added), lambda s: _normalized_title(new_files[s].title)
    )
    for r in sorted(remaining_removed):
        rt = old_files[r].title
        if not _usable_title(rt):
            continue
        rt_normalized = _normalized_title(rt)
        if removed_by_title.get(rt_normalized) != r:
            continue
        a = added_by_title.get(rt_normalized)
        if a is None:
            continue
        changes.renamed.append(
            Rename(
                old_slug=r,
                new_slug=a,
                title=rt,
                source_url=new_files[a].source_url,
                matched_by="title",
            )
        )
        remaining_removed.discard(r)
        remaining_added.discard(a)

    # --- Categorize the leftovers + content changes --------------------------
    # Anything still in remaining_* after rename detection is a genuine add or
    # removal (not part of a move). Slugs present in both runs are "modified"
    # only when their content hash actually changed.
    for slug in sorted(remaining_added):
        f = new_files[slug]
        changes.added.append(Change(slug=slug, title=f.title, source_url=f.source_url))
    for slug in sorted(remaining_removed):
        f = old_files[slug]
        changes.removed.append(
            Change(slug=slug, title=f.title, source_url=f.source_url)
        )

    for slug in sorted(old_slugs & new_slugs):
        if old_files[slug].hash != new_files[slug].hash:
            changes.modified.append(
                Modified(
                    slug=slug,
                    title=new_files[slug].title,
                    source_url=new_files[slug].source_url,
                )
            )

    return changes
