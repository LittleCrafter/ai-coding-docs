"""Per-source manifest: a machine-readable index of the mirrored docs.

Each source owns `docs/<source>/manifest.json`. It is git-tracked, which makes
structural change detection possible between runs (load previous -> diff ->
write new).

The manifest is the pipeline's only persistent state: it records, per mirrored
page, everything the next run needs to decide "did anything change?" without
re-reading the Markdown files -- most importantly the content hash and the
stable `source_id` used for rename detection (see ``core.diff``). It also
doubles as a machine-readable directory for consumers (the ``description``
field explains the format to anyone who stumbles upon the file).

Reading is deliberately tolerant: manifests written by older or newer versions
of this tool must still load, so unknown keys are filtered out instead of
raising (see `Manifest.from_dict`).
"""

from __future__ import annotations

import json
import sys
from dataclasses import asdict, dataclass, field, fields
from datetime import UTC, datetime
from pathlib import Path

from .. import config
from .page import validate_slug
from .utils import atomic_write


def now_iso() -> str:
    """Current UTC time as ``YYYY-MM-DDTHH:MM:SSZ`` (the manifest timestamp).

    The second-precision, ``Z``-suffixed format is stable, sortable, and free
    of microseconds/timezone noise, which keeps manifest diffs in git minimal
    and human-reviewable.
    """
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


@dataclass
class FileEntry:
    """Everything the mirror knows about one mirrored page.

    `hash` is the sha256 of the fetched Markdown (see ``fetch.content_hash``);
    `last_updated` is the time this entry was (re)written -- i.e. when the
    page content last changed as far as the mirror knows, not when the run
    happened.

    The three source-identifying fields have distinct roles that are easy to
    conflate:

      * ``source_url`` is the canonical *human-facing* documentation page --
        the link rendered as ``[source]`` in the generated index and
        whats-new logs for readers who want to check the page upstream;
      * ``source_md_url`` is the *raw Markdown endpoint* the mirror actually
        fetches -- often an ``.md`` suffixed variant or a
        ``raw.githubusercontent.com`` URL, and never shown to readers;
      * ``source_id`` is the stable upstream identity used purely as a
        *tracking key*: ``core.diff`` matches removed and added pages on
        ``source_id`` equality to detect renames, so it must stay constant
        when a page moves (it is typically the upstream filename or repo
        path, which survives URL changes).
    """

    slug: str
    title: str
    group: str
    source_url: str
    source_md_url: str
    source_id: str
    hash: str
    last_updated: str

    def __post_init__(self) -> None:
        """Reject empty/whitespace identity fields, unsafe slugs, and
        non-string rendered fields.

        This dataclass has two construction sites: the discovery path
        (``Page`` -> ``pipeline.fetch_pages`` -> ``FileEntry``), where every
        field has already been validated by ``Page.__post_init__``; and the
        load path (``Manifest.from_dict`` -> ``FileEntry``), where the values
        come straight from a persisted ``manifest.json`` on disk. The load
        path is the reason every check below exists: a tampered, hand-edited,
        or partially-overwritten manifest must not be able to smuggle in
        values that the discovery path would have rejected. Every
        ``ValueError`` raised here is caught by ``Manifest.from_dict``,
        wrapped as a ``TypeError`` with the offending slug attached, and
        ``load()`` then maps that ``TypeError`` to "no baseline" -- so the
        tolerant-load contract is preserved (one noisy "everything changed"
        regenerator run instead of a permanent crash loop on the bad file).

        Checks, grouped by the failure mode they prevent:

        Slug contract (full ``validate_slug``): ``slug`` keys
        ``Manifest.files`` and names the on-disk file, and the pipeline's
        deletion cleanup unlinks ``base / f"{slug}.md"`` verbatim for removed
        pages. A tampered manifest carrying ``../../../etc/x`` would therefore
        delete arbitrary files without the re-run below (character whitelist,
        length cap, no absolute paths, no ``..`` segments) -- this is the
        same contract ``Page`` enforces at discovery time, re-applied here so
        the on-disk entry point cannot bypass it.

        Rename-detection identity: ``core.diff`` matches removed and added
        pages on ``source_id`` *equality*. An empty id is fatal because two
        corrupt entries with empty ids would false-match unrelated pages into
        a fabricated rename; an *unstripped* id is just as bad because
        ``"x"`` and ``"x "`` would be treated as two different upstream
        identities, splitting one page's history into a fabricated
        add/remove pair -- so the value must be stripped exactly as ``Page``
        requires at discovery time.

        Content-hash integrity: an empty ``hash`` would compare equal to any
        other empty hash, reporting two unrelated pages as unmodified and
        silently dropping the change from the whats-new log.

        Rendered-field type guards: ``title``, ``source_url``,
        ``source_md_url``, ``group``, and ``last_updated`` are all consumed
        by the index/whats-new renderers (``title.translate(...)``,
        ``safe_url(source_url)``, f-string interpolation of ``group`` and
        ``last_updated``). A non-string value -- e.g. a JSON ``null`` title in
        a hand-edited manifest -- would otherwise pass load silently and
        crash the renderer with ``AttributeError`` AFTER content files have
        already been written and BEFORE ``manifest.save`` runs, leaving the
        manifest corrupt and the source stuck in a crash loop on every
        subsequent run. Rejecting non-strings here turns that stuck-loop
        shape into a loud load error instead. The two URL fields are
        additionally required to be non-empty because they are rendered as
        ``[source](<url>)`` links in both the per-source README and the
        whats-new log, and an empty URL renders as a broken link on every
        page row.
        """
        validate_slug(self.slug, label="FileEntry.slug")
        if not self.source_id.strip():
            raise ValueError(
                "FileEntry.source_id must be non-empty "
                "(rename detection matches on source_id equality)"
            )
        if self.source_id != self.source_id.strip():
            # Mirror Page.source_id: an unstripped value never equality-
            # matches the stripped value discovery produces, so a real
            # rename would be misreported as a plain add+remove pair.
            raise ValueError(
                "FileEntry.source_id must be stripped of leading/trailing "
                f"whitespace: {self.source_id!r}"
            )
        if not self.hash.strip():
            raise ValueError("FileEntry.hash must be non-empty")
        # Type guards for fields the renderers consume directly. ``isinstance``
        # (not truthiness) because an empty string is legal for some of these
        # -- ``last_updated`` is intentionally left empty by ``fetch_pages``
        # until ``write_docs`` stamps it, and ``group`` defaults to "" -- but a
        # non-string is always corrupt. The two URL fields additionally must be
        # non-empty: they are the only ones rendered as links, and an empty
        # link destination is silently broken rather than loudly wrong.
        if not isinstance(self.title, str):
            raise ValueError(
                f"FileEntry.title must be a string, got {type(self.title).__name__}"
            )
        if not isinstance(self.source_url, str) or not self.source_url.strip():
            raise ValueError("FileEntry.source_url must be a non-empty string")
        if not isinstance(self.source_md_url, str) or not self.source_md_url.strip():
            raise ValueError("FileEntry.source_md_url must be a non-empty string")
        if not isinstance(self.group, str):
            raise ValueError(
                f"FileEntry.group must be a string, got {type(self.group).__name__}"
            )
        if not isinstance(self.last_updated, str):
            raise ValueError(
                "FileEntry.last_updated must be a string, "
                f"got {type(self.last_updated).__name__}"
            )
        if self.last_updated and not (
            len(self.last_updated) == 20
            and self.last_updated[10] == "T"
            and self.last_updated[-1] == "Z"
        ):
            raise ValueError(
                f"FileEntry.last_updated must be in ISO 8601 format (YYYY-MM-DDTHH:MM:SSZ), "
                f"got {self.last_updated!r}"
            )


@dataclass
class FetchMetadata:
    """Run-level statistics, written once per mirror run.

    Purely informational (nothing in the pipeline reads it back), but it makes
    each run auditable from git history: how many pages were discovered, how
    many failed, and which ones. `failed_pages` defaults via
    ``default_factory`` so instances never share one mutable list.
    """

    last_fetch_completed: str
    fetch_duration_seconds: float
    total_pages_discovered: int
    pages_fetched_successfully: int
    pages_failed: int
    failed_pages: list[str] = field(default_factory=list)


# Field-name sets for the forward/backward-compatible key filtering in
# `Manifest.from_dict`, computed once at import time instead of inside the
# per-entry exception handlers (a corrupt or newer-version manifest would
# otherwise recompute the identical set for every single entry). The public
# ``dataclasses.fields()`` API is used rather than the private
# ``__dataclass_fields__`` dunder.
_FILE_ENTRY_FIELDS = frozenset(fld.name for fld in fields(FileEntry))
_FETCH_METADATA_FIELDS = frozenset(fld.name for fld in fields(FetchMetadata))


@dataclass
class Manifest:
    """In-memory form of `manifest.json` for one source.

    `files` maps slug -> `FileEntry`; `fetch_metadata` is ``None`` until a
    full fetch run completes (e.g. on a discovery-only or dry run).
    `version` records the upstream target version (defaulting to "—").
    """

    files: dict[str, FileEntry] = field(default_factory=dict)
    fetch_metadata: FetchMetadata | None = None
    version: str = "—"
    # `default_factory` (not a bare `now_iso()` call) so the timestamp is taken
    # when an instance is created, not once at module import / class definition.
    last_updated: str = field(default_factory=now_iso)

    def to_dict(self) -> dict:
        """Serialize to the exact JSON shape written to disk.

        Files are sorted by slug so the committed manifest.json diff reflects
        only real changes, never dict-insertion-order churn between runs.
        """
        return {
            "description": config.MANIFEST_DESCRIPTION,
            "version": self.version,
            "last_updated": self.last_updated,
            "files": {slug: asdict(e) for slug, e in sorted(self.files.items())},
            "fetch_metadata": asdict(self.fetch_metadata)
            if self.fetch_metadata
            else None,
        }

    @classmethod
    def from_dict(cls, data: dict) -> Manifest:
        """Deserialize a manifest dict, tolerating unknown keys.

        If ``data`` is not a dict (e.g. a corrupt manifest.json whose root is
        a JSON list, scalar, or null), ``TypeError`` is raised -- the same
        corruption signal used for malformed per-file entries -- so ``load()``
        maps it to ``None`` ("no baseline") exactly like every other
        corruption shape, instead of mistaking the file for a valid but empty
        baseline.

        Raises:
            TypeError: If ``data`` is not a dict, or if any per-file entry or
                the ``fetch_metadata`` block fails schema validation.
        """
        # Root-level guard: a non-dict value means the manifest.json root is
        # not a JSON object at all (a list, scalar, or null). That is
        # corruption, not an empty manifest -- returning an empty Manifest
        # here would make ``load()`` treat the file as a valid baseline with
        # zero pages, which both hides the corruption (no warning, no
        # regeneration) and misleads ``core.diff`` into diffing every
        # previously mirrored page against nothing. Raising TypeError routes
        # the file through ``load()``'s existing corruption handling: warn to
        # stderr, return None ("no baseline"), and regenerate the manifest
        # from scratch on the next write.
        if not isinstance(data, dict):
            raise TypeError(f"Manifest root must be a dict, got {type(data).__name__}")

        # Forward/backward compatibility rule: a manifest may contain keys
        # this version of the tool does not know (written by a newer version)
        # or miss keys it expects (written by an older one). Unknown keys --
        # both on per-file entries and on ``fetch_metadata`` -- are silently
        # dropped rather than raising, so mixed-version checkouts and rollbacks
        # keep working. A missing or null ``last_updated`` falls back to now.
        files: dict[str, FileEntry] = {}
        raw_files = data.get("files")
        if not isinstance(raw_files, dict):
            # If files is missing, null, or a non-dict (corrupt manifest),
            # treat it as empty so the pipeline keeps running.
            raw_files = {}
        for slug, f in raw_files.items():
            # Verify each entry is a dict before attempting deserialisation;
            # a corrupt manifest with non-dict entries would otherwise produce
            # an opaque TypeError. Raise a TypeError that names the offending
            # slug so the corruption is easy to locate.
            if not isinstance(f, dict):
                raise TypeError(
                    f"File entry for slug {slug!r} must be a dict, "
                    f"got {type(f).__name__}"
                )
            # Reject any divergence between the JSON dict key and the entry's
            # own ``slug`` field. Content files are written under the dict key
            # (see ``pipeline.write_docs``) but the generated README links are
            # rendered from the entry's ``slug`` (see ``core.index.render``),
            # so a tampered manifest such as ``{"a": {"slug": "b", ...}}``
            # would write one file and link another -- a broken mirror that
            # silently points readers at a non-existent page. Reject (rather
            # than silently normalizing one value to the other) to match this
            # module's documented corruption-rejection design.
            if f.get("slug") != slug:
                raise TypeError(
                    f"Corrupt manifest entry for slug={slug!r}: dict key does not "
                    f"match entry slug {f.get('slug')!r}"
                )
            try:
                # Forward/backward compatibility: filter the entry's keys to
                # the fields this version knows ONCE, up front, and construct
                # a single FileEntry. Unknown keys (written by a newer
                # version) are silently dropped so mixed-version checkouts and
                # rollbacks keep working. A missing required key raises
                # TypeError here; an empty/unsafe value raises ValueError or
                # AttributeError from ``FileEntry.__post_init__`` (which also
                # runs ``validate_slug``, so a malicious slug is still
                # rejected). Any of those means the manifest is corrupt rather
                # than merely ahead of this version, so the error is re-raised
                # as a single TypeError that names the slug -- making the bad
                # entry findable in a large manifest.json instead of surfacing
                # as a bare, context-free error. Raised as TypeError so
                # ``load()`` treats it like any other schema corruption
                # (missing baseline) instead of crashing the run.
                files[slug] = FileEntry(
                    **{k: v for k, v in f.items() if k in _FILE_ENTRY_FIELDS}
                )
            except (TypeError, ValueError, AttributeError) as exc:
                raise TypeError(
                    f"Corrupt manifest entry for slug={slug!r}: {exc}"
                ) from exc
        meta = data.get("fetch_metadata")
        # fetch_metadata is only accepted as a dict; anything else (null,
        # stale scalar) degrades to None instead of crashing the load.
        if isinstance(meta, dict):
            try:
                # Same forward/backward-compatibility rule as per-file entries
                # above: filter the keys to the fields this version knows ONCE
                # and construct a single FetchMetadata, silently dropping
                # unknown extra keys. A missing required key (such as
                # last_fetch_completed) raises TypeError, so the manifest is
                # corrupt; the error is re-raised with context instead of
                # propagating as a bare TypeError. The except clause mirrors
                # the per-file-entry branch for consistency.
                fetch_meta = FetchMetadata(
                    **{k: v for k, v in meta.items() if k in _FETCH_METADATA_FIELDS}
                )
            except (TypeError, ValueError, AttributeError) as exc:
                raise TypeError(f"Corrupt fetch_metadata in manifest: {exc}") from exc
        else:
            fetch_meta = None
        # The stored ``last_updated`` is validated before use: it must be a
        # non-empty string without embedded newlines/carriage returns, else
        # the current time is substituted. Every ``FileEntry`` field is
        # hardened at load (see ``FileEntry.__post_init__``) precisely because
        # this value flows verbatim into ``core.index.render``'s
        # "Last updated:" line -- a non-string (e.g. a JSON number from a
        # hand-edited manifest) or a newline-bearing string would corrupt the
        # generated README's header block. Unlike per-entry corruption (which
        # is rejected loudly via TypeError so ``load()`` regenerates the whole
        # baseline), a bad run-level timestamp only loses cosmetic
        # information, so the tolerant choice here is to fall back to the
        # current time rather than fail the load.
        raw_last_updated = data.get("last_updated")
        raw_version = data.get("version")
        return cls(
            files=files,
            fetch_metadata=fetch_meta,
            version=(
                raw_version
                if isinstance(raw_version, str)
                and raw_version.strip()
                and "\n" not in raw_version
                and "\r" not in raw_version
                else "—"
            ),
            # Truthiness (not the two-argument ``dict.get`` default) so an
            # explicit ``"last_updated": null`` in the manifest -- produced
            # e.g. by a serializer that emits null for missing values --
            # also falls back to the current time. ``data.get(key, default)``
            # would return the stored None verbatim, which would later render
            # as the literal text "Last updated: None" in the index.
            last_updated=(
                raw_last_updated
                if isinstance(raw_last_updated, str)
                and raw_last_updated
                and "\n" not in raw_last_updated
                and "\r" not in raw_last_updated
                else now_iso()
            ),
        )


def load(path: Path) -> Manifest | None:
    """Load a manifest from disk, or return None on the first run.

    ``None`` (rather than an empty Manifest) signals "no baseline exists" to
    ``core.diff.diff``, which then skips change detection entirely -- on a
    baseline run every page would otherwise be reported as "added".

    Four failure shapes are all treated as "no baseline", with a warning to
    stderr, so the next run regenerates the manifest from scratch rather than
    entering a permanent crash loop:

      * invalid JSON (``json.JSONDecodeError`` -- truncated or hand-mangled
        file);
      * undecodable bytes (``UnicodeDecodeError`` -- a file that is not UTF-8
        at all, e.g. binary garbage written over the manifest by a crashed
        tool or a filesystem mishap; ``read_text(encoding="utf-8")`` raises
        it BEFORE ``json.loads`` ever runs, and it is a ``ValueError``
        subclass, NOT a ``json.JSONDecodeError``, so it needs its own entry
        in the except tuple);
      * schema corruption (``TypeError`` from `Manifest.from_dict` -- e.g. a
        required entry field missing, an entry that is not a dict, or a JSON
        root that is not an object at all, such as a list or scalar);
      * an unreadable file (``OSError`` -- e.g. a permission problem or a
        directory sitting where the manifest should be).

    Losing the baseline is the safe failure mode here: it costs one noisy
    "everything changed" run, whereas crashing would leave the mirror
    permanently stuck on a file it can never read.
    """
    if not path.exists():
        return None
    try:
        return Manifest.from_dict(json.loads(path.read_text(encoding="utf-8")))
    except (json.JSONDecodeError, UnicodeDecodeError, TypeError, OSError) as exc:
        print(
            f"  warning: failed to load {path} ({exc}); treating as missing "
            f"(will regenerate on next write)",
            file=sys.stderr,
        )
        return None


def save(manifest: Manifest, path: Path) -> None:
    """Write the manifest as stable, review-friendly JSON.

    Indented with a trailing newline (so the file is POSIX-clean and diffs
    read well), with ``ensure_ascii=False`` so non-ASCII page titles are kept
    verbatim instead of escaped into ``\\uXXXX`` soup. Parent directories are
    created on first run.

    The manifest is serialised first, then handed to ``utils.atomic_write``,
    which stages it in a uniquely-named sibling temp file (suffixed
    ``.{pid}_{token}.tmp``, e.g. ``manifest.json.12345_a1b2c3d4.tmp``) and
    atomically renames it over the target.  If the write or the rename fails,
    the temp file is cleaned up best-effort inside ``atomic_write`` so no stale
    ``.{pid}_{token}.tmp`` files accumulate.

    Durability caveat: the temp file is not ``fsync``-ed before the rename, so
    the atomic-rename guarantee covers process-level failures (Python
    exceptions and SIGTERM) but NOT power loss / kernel panic -- ``rename(2)``
    is only metadata-atomic, so a hard crash could expose a partially-written
    file. The next mirror run regenerates the manifest from upstream, so any
    such torn write self-heals.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(manifest.to_dict(), indent=2, ensure_ascii=False) + "\n"
    # Delegate the atomic-write (temp file + rename + cleanup) to the shared
    # utility so every call site uses the same crash-safe write pattern with
    # identical semantics. The parent directory is guaranteed to exist by the
    # mkdir call above, which matches atomic_write's precondition.
    atomic_write(path, payload)
