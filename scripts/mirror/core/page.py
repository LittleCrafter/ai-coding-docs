"""Source-agnostic page model.

A `Page` is one documentation page discovered by a source, before its content
has been fetched. The title is filled in later from the Markdown content.

Discovery and fetching are deliberately separate stages: a source first yields
one `Page` per document it found (cheap, usually a single sitemap or API call),
and the orchestrator then fetches each page's Markdown one at a time with
rate-limiting and retries. Keeping the record frozen makes it safe to collect
pages into sets or use them as dict keys while deduplicating discoveries.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# Allowed slug characters, compiled once at module level rather than on every
# Page instantiation (a run may build thousands of Page objects, and
# recompiling a regex per instance is pure waste). The dash sits at the very
# end of the character class, where it is unambiguously a literal -- no
# backslash escape is needed or wanted.
#
# Why this exact alphabet: slugs appear in Markdown links and code spans in
# the generated index and whats-new logs, and they double as relative file
# paths on disk. Characters that would break Markdown parsing (spaces, #, ?,
# |, [, ], (, )) or path handling (:, \, wildcards) are rejected. Only
# alphanumerics, dots, hyphens, underscores, and forward slashes are allowed
# -- typical path-like slugs such as "cli/commands" work fine.
_SLUG_RE = re.compile(r"^[A-Za-z0-9._/-]+$")

# Hard upper bound on slug length. The slug names the on-disk file
# (``<source_dir>/<slug>.md``), so it must fit the per-component filename
# limit every relevant filesystem enforces (255 bytes on ext4, APFS, and
# NTFS). Because ``_SLUG_RE`` restricts slugs to ASCII, one character is one
# byte, so a 200-character cap guarantees every path *segment* stays under
# 255 bytes with room for the ".md" suffix and the source directory prefix.
# Real upstream slugs are a handful of dozen characters at most; anything
# near 200 is almost certainly a malformed discovery URL, so rejecting it
# loudly at validation time beats crashing the whole source run later with
# an unhandled ``OSError: [Errno 36] File name too long`` from the write.
_MAX_SLUG_LENGTH = 200


def validate_slug(slug: str, *, label: str = "Page.slug") -> None:
    """Raise ``ValueError`` unless `slug` is a safe mirror slug.

    This is the single enforcement point for the slug contract, shared by the
    two places a slug enters the pipeline:

      * ``Page.__post_init__`` -- newly discovered pages (the upstream-driven
        entry point);
      * ``manifest.FileEntry.__post_init__`` -- pages loaded back from a
        persisted ``manifest.json`` (the on-disk entry point, where a tampered
        or corrupt file must not be able to smuggle in a slug that discovery
        would have rejected).

    `label` prefixes every error message so a rejection names the record type
    that carried the bad value (``Page.slug ...`` vs ``FileEntry.slug ...``);
    the checks themselves are identical for both.

    The contract, in check order:

      * non-empty (and not whitespace-only) and already stripped --
        whitespace is *rejected*, not silently normalized, because an
        unstripped value is almost always a bug at the producer and quietly
        fixing it here would both hide that bug and risk two distinct
        values colliding onto one stripped key;
      * at most ``_MAX_SLUG_LENGTH`` characters -- the slug doubles as a
        filename, and an over-long one crashes the write with ``OSError``
        (see the constant above);
      * characters limited to the ``_SLUG_RE`` alphabet -- slugs appear in
        Markdown links and code spans in the generated index and whats-new
        logs, and they double as relative file paths on disk;
      * no leading ``/`` -- ``Path(base) / slug`` would otherwise resolve to
        an absolute path outside the mirror tree (``PurePath.__truediv__``
        discards the left side when the right side is absolute);
      * no ``..`` path segment -- that would walk out of the per-source
        directory the same way, which matters most for the manifest-loaded
        entry point: the deletion cleanup step unlinks ``base / f"{slug}.md"``
        verbatim, so a ``..``-bearing slug in a tampered manifest would
        delete arbitrary files;
      * no trailing slash -- meaningless for a file name and a sign of a
        malformed discovery URL.
    """
    if not slug.strip():
        # ``strip()`` before the emptiness test so a whitespace-only slug
        # (truthy in Python, useless as a filename) is rejected here too.
        # The message names both cases explicitly: a whitespace-only value
        # IS non-empty, so a bare "must be non-empty" would misdescribe why
        # it was rejected. The distinct "must be stripped" message below
        # stays accurate as well: it only fires for values with non-space
        # content surrounded by padding (e.g. " x"), never for the
        # whitespace-only case handled here.
        raise ValueError(f"{label} must be non-empty and not whitespace-only")
    if slug != slug.strip():
        raise ValueError(
            f"{label} must be stripped of leading/trailing whitespace: {slug!r}"
        )
    if len(slug) > _MAX_SLUG_LENGTH:
        raise ValueError(
            f"{label} must be at most {_MAX_SLUG_LENGTH} characters "
            f"(got {len(slug)}): {slug[:50]!r}..."
        )
    # Character whitelist: see the comment on `_SLUG_RE` for why this exact
    # alphabet.
    if not _SLUG_RE.match(slug):
        raise ValueError(
            f"{label} {slug!r} contains characters that would break Markdown "
            f"rendering; slugs may only contain alphanumeric characters, "
            f"dots, hyphens, underscores, and forward slashes"
        )
    # Path-traversal guards. The slug is later joined onto the per-source
    # docs directory (``Path(source_dir) / f"{slug}.md"``); without these
    # checks a hostile or buggy upstream URL -- or a tampered manifest --
    # could make the mirror read/write/delete outside its tree.
    if slug.startswith("/"):
        raise ValueError(f"{label} must be a relative path, not absolute: {slug!r}")
    # Split the slug into path segments ONCE and reuse the result for both the
    # ``..`` traversal-segment check below and the empty-segment check further
    # down. The two checks used to call ``slug.split("/")`` independently,
    # which rebuilt an identical list twice for no reason on every validated
    # slug.
    parts = slug.split("/")
    if ".." in parts:
        raise ValueError(f"{label} must not contain '..' path segments: {slug!r}")
    # Check trailing slash BEFORE empty segments: a slug like "foo/" splits
    # to ["foo", ""] on "/", which would trigger the empty-segments check with
    # a misleading message.  Checking the trailing slash first gives the more
    # specific and actionable error.
    if slug.endswith("/"):
        raise ValueError(f"{label} must not end with a trailing slash: {slug!r}")
    if "" in parts:
        raise ValueError(
            f"{label} must not contain empty path segments "
            f"(consecutive slashes): {slug!r}"
        )


@dataclass(frozen=True)
class Page:
    """One discovered documentation page, prior to fetching its content.

    Everything except `title` is known at discovery time. `title` is not a
    field at all: it is extracted from the fetched Markdown (see
    ``core.fetch.extract_title``) and only enters the persisted state via
    ``manifest.FileEntry``, because many upstreams put the real title only in
    the page body, not in any listing.
    """

    # Non-empty, enforced in __post_init__: keys the manifest and names the
    # local file (<source_dir>/<slug>.md); must be unique within a source.
    slug: str
    source_url: str  # human-facing page
    source_md_url: str  # raw Markdown URL
    # Non-empty, enforced in __post_init__: rename detection matches on
    # source_id *equality*, so empty ids would false-match unrelated pages.
    source_id: str
    # Grouping label for the per-source index. ``core.index.render`` buckets
    # pages by this value and turns each distinct value into one ``## `` section
    # heading in the generated ``docs/<source>/README.md``: an empty string
    # falls back to a "Documentation" section, and the literal name "root" is
    # promoted to the top section and displayed as the source's own title.
    # Sources set it from their own taxonomy (e.g. "cli", "guides") so the
    # index reads like the upstream docs' navigation rather than a flat list.
    group: str = ""  # grouping label for the index (e.g. "cli", "guides")

    def __post_init__(self) -> None:
        """Enforce the invariants the rest of the pipeline assumes.

        `slug` is validated by `validate_slug` (the shared slug contract:
        non-empty, stripped, length-capped, character-whitelisted, and free
        of path-escape shapes) because it keys the manifest (``files`` maps
        slug -> entry) and names the local file (``<slug>.md``) -- an empty
        or hostile slug would collapse pages onto one key/file or write
        outside the mirror tree.

        `source_id` is the identity signal for rename detection:
        ``core.diff`` pairs a removed slug with an added slug whenever their
        ``source_id`` values are *equal*, so two pages with an empty id
        would satisfy that test and be reported as a rename of unrelated
        pages. Like the slug, it is rejected rather than silently normalized
        when unstripped: an unstripped value is almost always a discovery
        bug (a sloppy ``.strip()`` omission in a source adapter), and quietly
        fixing it here would both hide that bug and risk collisions. Loud
        rejection at discovery time pins the fix where the bad value
        originates.

        Finally, both URLs must be non-empty: they are rendered as links in
        the generated index/whats-new logs, and an empty URL produces a
        broken link for every reader of the mirror.

        `group` has no non-emptiness requirement (``""`` is the documented
        default, bucketed as "Documentation" by ``core.index.render``), but
        it must be a STRING: it keys the group buckets and is rendered as a
        ``## `` section heading, so a non-string value (e.g. ``None`` from a
        buggy adapter) is rejected here rather than deep inside index
        rendering, far from the discovery bug that produced it.

        These used to be conventions every source module happened to uphold;
        raising here makes them enforced invariants instead, turning a silent
        data bug (bogus renames, overwritten or escaped files, broken links)
        into a loud error at discovery time, right where the bad value
        originates.
        """
        # Full slug contract (charset, length, path-escape shapes) lives in
        # `validate_slug` so manifest-loaded entries are held to exactly the
        # same standard as freshly discovered pages.
        validate_slug(self.slug)
        if not self.source_id.strip():
            raise ValueError(
                "Page.source_id must be non-empty "
                "(rename detection matches on source_id equality)"
            )
        if self.source_id != self.source_id.strip():
            raise ValueError(
                f"Page.source_id must be stripped of leading/trailing "
                f"whitespace: {self.source_id!r}"
            )
        # Both URLs end up as [label](url) links in the generated README and
        # whats-new logs; an empty or whitespace-only URL renders as a broken
        # link on every mirrored page listing.
        if not self.source_url.strip():
            raise ValueError("Page.source_url must be non-empty")
        if not self.source_md_url.strip():
            raise ValueError("Page.source_md_url must be non-empty")
        # ``group`` needs no non-emptiness check ("" is the documented
        # default, remapped to a "Documentation" bucket by
        # ``core.index.render``), but it must be a STRING: it keys the
        # group-bucket dict and is rendered as a ``## `` section heading. A
        # non-string value (e.g. ``None`` from a buggy adapter forgetting to
        # populate it) would otherwise sail through discovery and only crash
        # much later -- deep inside index rendering, after page content has
        # already been fetched -- far from the discovery bug that produced
        # it. Reject it loudly here, mirroring the type guards
        # ``FileEntry.__post_init__`` applies to its rendered fields at
        # manifest-load time.
        if not isinstance(self.group, str):
            raise ValueError(
                f"Page.group must be a string, got {type(self.group).__name__}"
            )
