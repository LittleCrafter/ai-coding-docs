"""Shared string/URL sanitation helpers and atomic-write utilities used across
core modules.

The ``safe_url`` helper avoids duplication between ``index.py`` and
``whats_new.py`` (they used to keep two copies of the same logic, kept in
sync by cross-reference comments).  Extracting into one shared module removes
the duplication and the sync burden.

``atomic_write`` is the third common pattern extracted here: the
temp-file-plus-rename sequence that ``index.write``, ``manifest.save``,
``whats_new.write_entry``, and ``pipeline.write_docs`` / ``pipeline.write_top_index``
previously implemented independently at each call site (near-identical copies
of the same try/finally boilerplate, kept in sync by cross-reference
comments).  All of them now delegate here, which removes the duplication and
guarantees every call site uses the same crash-safe write semantics without
having to replicate the try/finally cleanup boilerplate.

``atomic_write_bytes`` is the binary twin of ``atomic_write``: the media
stage (``core.media``) downloads upstream image assets with it.  Both public
entry points delegate to the shared ``_atomic_write`` core, so text and
bytes payloads are staged and renamed through exactly one crash-safe
implementation and can never drift apart.
"""

from __future__ import annotations

import os
import re
import sys
import uuid
from pathlib import Path
from urllib.parse import urlsplit

# Percent-encoding table for the characters that would corrupt the link
# destination ``safe_url`` emits. Two distinct corruption modes are covered:
#
#  * CommonMark forbids unescaped ``<``, ``>``, and line endings inside an
#    angle-bracket link destination (``<...>``): a raw ``<`` or ``>`` would
#    prematurely close the destination, and a newline/carriage-return is not
#    allowed there at all.
#  * GFM table syntax treats an unescaped ``|`` as a column separator. The
#    ``[source](<url>)`` link rendered by ``index.render`` lives inside a
#    table cell, so a raw ``|`` anywhere in ``source_url`` would split that
#    cell in two and corrupt the whole row layout. The slug and the title
#    are both already protected against ``|`` (the slug charset excludes it,
#    and titles map ``|`` -> ``\\|`` in ``index._TITLE_ESCAPES``); encoding
#    it here closes the gap for the third rendered value, the URL, so the
#    escaping contract is consistent across all three cell fields.
#
# The URLs passed through here come from sitemaps and upstream manifests,
# where these characters are practically impossible -- but a silently broken
# ``[source]`` link or a corrupted table row is exactly the kind of failure
# nobody notices, so every emission site sanitizes anyway.  Percent-encoding
# (rather than stripping) keeps the URL valid and reversible: ``%`` is itself
# a legal destination character inside angle brackets, and the encoded value
# decodes back to the original URL.
_URL_ESCAPES = str.maketrans(
    {"<": "%3C", ">": "%3E", "\n": "%0A", "\r": "%0D", "|": "%7C"}
)


def safe_url(url: str) -> str:
    """Percent-encode characters that would corrupt a rendered link or table.

    Two failure modes are prevented, one per syntax the URL is emitted into:

      * CommonMark angle-bracket destinations (``[label](<url>)``) forbid
        unescaped ``<``, ``>``, and line endings. A raw ``<``/``>`` would
        prematurely close the destination, and a newline would split it across
        two lines.
      * GFM table cells treat an unescaped ``|`` as a column separator. The
        ``[source]`` link emitted by ``index.render`` sits inside a table
        row, so a raw ``|`` anywhere in the URL would split that row's cell
        in two and corrupt the table layout. The whats-new bullets emit the
        same URL inside a plain list item, where ``|`` carries no table
        meaning -- encoding it there is harmless, but the table row is the
        case that actually needs the protection. This is the same
        protection ``index._TITLE_ESCAPES`` already applies to titles and
        the slug charset already enforces for slugs; encoding it here keeps
        the URL -- the third cell field -- consistent with them.

    ``source_url`` values come from sitemaps and manifests and should never
    contain any of these characters, yet the cost of sanitizing at emission
    time is one ``str.translate`` call -- cheap insurance against a link that
    renders broken with no error anywhere.  Encoding (not stripping) preserves
    the information: the emitted URL still decodes to the original string.

    Examples (the wrapped form is what callers emit as ``[label](<...>)``)::

        "https://a/b (v2)/c"      -> unchanged; spaces/parens are legal
                                     inside <...>, so the wrapped link
                                     "[x](<https://a/b (v2)/c>)" works as-is
        "https://a/<draft>"       -> "https://a/%3Cdraft%3E"  (a raw "<"
                                     would corrupt the <...> destination)
        "https://a/b\\nc"          -> "https://a/b%0Ac"  (a raw newline would
                                     split the destination across two lines)
        "https://a/p|q"           -> "https://a/p%7Cq"  (a raw "|" would split
                                     the GFM table cell that wraps the link)

    Ordinary URLs pass through untouched, so the common case costs nothing.
    """
    return url.translate(_URL_ESCAPES)


_SEMVER_RE = re.compile(r"(\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?)")


def extract_version(raw: str | None) -> str | None:
    """Extract SemVer string or strip leading 'v'/'V' prefix.

    Returns the first matching Semantic Version string (e.g. ``1.2.3`` or
    ``1.2.3-beta.1``). If no standard SemVer is matched, strips leading
    ``v``/``V`` prefixes and surrounding whitespace; returns ``None`` if
    the resulting string is empty or *raw* is not a string.
    """
    if not raw or not isinstance(raw, str):
        return None
    clean = raw.strip()
    if not clean:
        return None
    match = _SEMVER_RE.search(clean)
    if match:
        return match.group(1)
    stripped = clean.removeprefix("v").removeprefix("V").strip()
    return stripped if stripped else None


def _atomic_write(dest: Path, content: str | bytes) -> None:
    """Write *content* to *dest* atomically against process-level failures.

    The write is performed by staging the full content in a uniquely-named
    temporary file (a sibling of *dest* in the same directory, suffixed with
    ``.{pid}_{token}.tmp``), then using ``Path.replace()`` to atomically swap it over
    *dest* in a single filesystem operation.  This guarantees that a Python
    exception, SIGTERM, or any other process-level interruption between the
    write and the rename can never leave *dest* in a truncated or partially-
    written state -- readers (and git commits) only ever see the old file or
    the new one.

    **Limitation**: ``Path.replace()`` is only atomic at the metadata level
    on POSIX (``rename(2)``).  A kernel panic or power loss at the instant of
    the rename could leave *dest* partially written.  For the purposes of this
    pipeline (which regenerates files from upstream on the next run), a torn
    write self-heals and is acceptable.

    The temporary file is placed as a sibling of *dest* (not in ``/tmp`` or
    another system temp directory) so the rename stays within one filesystem.
    ``os.replace`` / ``Path.replace`` is only guaranteed atomic when source
    and destination live on the same mount, and ``/tmp`` is frequently a
    separate tmpfs -- staging there would silently degrade the atomic rename
    into a copy-plus-delete, losing exactly the crash safety this pattern
    provides.

    Uniqueness is achieved by appending ``os.getpid()`` and a random UUID
    token (``uuid.uuid4().hex[:8]``) to the temporary filename. On a running
    system, process IDs and unique random tokens guarantee isolation across
    both concurrent OS processes and concurrent threads within the same process.
    This prevents race conditions where one worker's temp write is overwritten
    or cleaned up by another before either rename completes.

    If writing or renaming fails (e.g. disk full, permission denied), the
    temporary file is cleaned up best-effort in a ``finally`` block so that
    stale temporary files do not accumulate across failed runs.  The
    cleanup is best-effort only: an ``OSError`` during cleanup is logged to
    stderr but never re-raised, so it cannot mask the original failure.

    Args:
        dest: The destination file path to write to.  Its parent directory
            must already exist (this function does not create parent
            directories).
        content: The full content to write.  ``str`` payloads are encoded
            UTF-8 on write; ``bytes`` payloads (downloaded media assets,
            which must never round-trip through a text decode) are written
            verbatim.
    """
    # Generate a temporary file in the same directory as dest so that
    # Path.replace() stays within one filesystem (and therefore atomic).
    # We suffix with os.getpid() and a random uuid token to guarantee
    # uniqueness across both multi-process and multi-threaded execution.
    tmp_path = dest.with_name(f"{dest.name}.{os.getpid()}_{uuid.uuid4().hex[:8]}.tmp")
    try:
        # Write the full content to the temp file first.  If this write or
        # the subsequent rename fails, the finally block cleans up.  The
        # isinstance branch picks the write call that matches the payload
        # type: write_bytes for binary content, write_text (UTF-8) for str.
        if isinstance(content, bytes):
            tmp_path.write_bytes(content)
        else:
            tmp_path.write_text(content, encoding="utf-8")
        # Atomic rename: replaces dest with tmp_path in a single filesystem
        # operation.  After this call, tmp_path no longer exists at its
        # original name -- it has been swapped onto the dest inode.
        tmp_path.replace(dest)
    finally:
        # Best-effort cleanup of the temporary file.  On a successful
        # replace(), the temp file is already gone (missing_ok=True makes this
        # a no-op).  On a failed write or rename, we remove what we can so
        # the filesystem does not accumulate orphaned .tmp files.  The
        # cleanup must never mask the original exception, so OSError is
        # caught, logged, and swallowed.
        try:
            tmp_path.unlink(missing_ok=True)
        except OSError as exc:
            print(
                f"  warning: could not remove temporary file {tmp_path}: {exc}",
                file=sys.stderr,
            )


def atomic_write(dest: Path, content: str) -> None:
    """Write a text payload to *dest* atomically (see ``_atomic_write``).

    The text entry point used by ``index.write``, ``manifest.save``,
    ``whats_new.write_entry``, and the ``pipeline.write_docs`` /
    ``pipeline.write_top_index`` writers.  It delegates to the shared
    ``_atomic_write`` core, whose docstring documents the full crash-safe
    staging + rename + cleanup contract.
    """
    _atomic_write(dest, content)


def atomic_write_bytes(dest: Path, content: bytes) -> None:
    """Write a binary payload to *dest* atomically (see ``_atomic_write``).

    The media stage uses this for downloaded static assets (images), which
    must never be decoded as text: arbitrary binary can trip a UTF-8 decode
    or, worse, be silently mangled by an encode/decode round-trip.  Shares
    the ``_atomic_write`` core with the text entry point, so both payload
    kinds get identical crash-safe semantics.
    """
    _atomic_write(dest, content)


def clean_url(url: str) -> str:
    """Canonicalize URL by stripping query, fragment, and trailing slashes."""
    return urlsplit(url.strip())._replace(query="", fragment="").geturl().rstrip("/")


def same_origin(url: str, site_url: str) -> bool:
    """Return True iff *url* belongs to the *site_url* origin.

    Every sitemap-driven adapter must establish the origin boundary BEFORE
    any path-level filtering happens: its path filter sees only the URL's
    parsed path and would happily accept a foreign-host sitemap entry whose
    PATH still starts with the expected prefix.

    Requiring either exact equality or a ``/`` immediately after the host
    rules out every hostname that merely shares the prefix.
    """
    site_url = site_url.rstrip("/")
    return url == site_url or url.startswith(site_url + "/")
