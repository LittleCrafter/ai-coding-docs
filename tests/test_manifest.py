"""Tests for the manifest model (mirror.core.manifest)."""

from __future__ import annotations

import dataclasses
import json

import pytest
from conftest import make_entry
from mirror.core import manifest


def _file_entry(slug: str = "a") -> manifest.FileEntry:
    """Thin wrapper over conftest.make_entry for manifest round-trip tests:
    only the slug varies between tests, and the hash is pinned to "h" because
    the round-trip assertions compare against that literal."""
    return make_entry(slug, title="A", group="root", hash="h")


def test_from_dict_round_trip():
    """A Manifest must survive a to_dict/from_dict round trip with files and
    fetch metadata intact — the manifest is persisted to disk as JSON, so any
    field lost here corrupts the next run's diff baseline."""
    m = manifest.Manifest(files={"a": _file_entry("a")})
    m.fetch_metadata = manifest.FetchMetadata(
        last_fetch_completed="2026-01-01T00:00:00Z",
        fetch_duration_seconds=1.234,
        total_pages_discovered=1,
        pages_fetched_successfully=1,
        pages_failed=0,
    )
    data = m.to_dict()
    assert data["files"]["a"]["slug"] == "a"
    back = manifest.Manifest.from_dict(data)
    assert back.files["a"].hash == "h"
    assert back.fetch_metadata.fetch_duration_seconds == 1.234


def test_from_dict_tolerates_unknown_keys():
    """Loading must be forward-compatible: a manifest written by a newer
    version may carry extra keys, and those must be ignored rather than
    crash the load."""
    # A manifest from a future schema may carry extra keys; only known fields
    # are kept when constructing the FileEntry.
    extra = {**dataclasses.asdict(_file_entry()), "unknown_future_key": "x"}
    m = manifest.Manifest.from_dict({"files": {"a": extra}})
    assert m.files["a"].slug == "a"
    assert not hasattr(m.files["a"], "unknown_future_key")


def test_from_dict_tolerates_unknown_fetch_metadata_keys():
    """The same forward-compatibility rule applies to fetch_metadata: a
    manifest written by a newer version may add run-level statistics this
    version does not know, and those must be dropped rather than crash
    from_dict with an unexpected-keyword TypeError."""
    meta = {
        "last_fetch_completed": "2026-01-01T00:00:00Z",
        "fetch_duration_seconds": 1.5,
        "total_pages_discovered": 3,
        "pages_fetched_successfully": 3,
        "pages_failed": 0,
        "unknown_future_stat": {"nested": "x"},
    }
    m = manifest.Manifest.from_dict({"fetch_metadata": meta})
    assert m.fetch_metadata is not None
    assert m.fetch_metadata.total_pages_discovered == 3
    assert m.fetch_metadata.failed_pages == []
    assert not hasattr(m.fetch_metadata, "unknown_future_stat")


def test_from_dict_handles_missing_files():
    """A manifest without a 'files' key loads as an empty manifest instead of
    raising — covers freshly created or partially written manifests."""
    assert manifest.Manifest.from_dict({}).files == {}


def test_manifest_last_updated_uses_factory():
    """`last_updated` must default via a factory so every Manifest instance
    gets its own timestamp; a plain default would freeze one value at class
    definition time and stamp all later manifests with it."""
    fld = {f.name: f for f in dataclasses.fields(manifest.Manifest)}["last_updated"]
    assert fld.default_factory is manifest.now_iso


def test_manifest_save_load_roundtrip(tmp_path):
    """Manifest survives a save -> load round-trip unchanged."""
    path = tmp_path / "manifest.json"
    entry = make_entry("test")
    mf = manifest.Manifest(files={"test": entry}, last_updated="2026-07-25T00:00:00Z")
    manifest.save(mf, path)

    loaded = manifest.load(path)
    assert loaded is not None
    assert loaded.last_updated == mf.last_updated
    assert loaded.files["test"].hash == entry.hash
    assert loaded.files["test"].title == entry.title
    # Full dataclass equality catches any field lost in the round trip that
    # the individual checks above happen not to name (``Manifest`` and
    # ``FileEntry`` are dataclasses with a generated ``__eq__``, and
    # ``fetch_metadata`` is None on both sides here, so the whole objects must
    # compare equal -- not just the two fields spelled out above).
    assert loaded == mf


def test_manifest_load_corrupt_json(tmp_path):
    """load() returns None for corrupt JSON instead of crashing."""
    path = tmp_path / "manifest.json"
    path.write_text("this is not json{{{", encoding="utf-8")
    result = manifest.load(path)
    assert result is None  # Should not crash


def test_from_dict_non_dict_root_raises_type_error():
    """A JSON root that is not an object (here a list) is corruption, not an
    empty manifest: ``from_dict`` must raise ``TypeError`` -- its standard
    corruption signal -- so ``load()`` routes it through the same
    "no baseline" handling as every other corrupt shape. Returning an empty
    Manifest instead would silently treat the file as a valid baseline with
    zero pages, hiding the corruption and disabling change detection for
    every previously mirrored page."""
    with pytest.raises(TypeError, match="Manifest root must be a dict"):
        manifest.Manifest.from_dict([])


@pytest.mark.parametrize("payload", ["[]", "42", '"just a string"', "null"])
def test_manifest_load_non_dict_root_returns_none(tmp_path, payload):
    """load() must return None (no baseline) when manifest.json parses as
    valid JSON whose root is not an object -- a list, scalar, or null, the
    shape a truncated copy or a tool writing the wrong file could produce.
    ``from_dict`` raises TypeError for such roots, and ``load`` catches that
    TypeError alongside ``JSONDecodeError``/``OSError`` so the pipeline
    regenerates the manifest on the next write instead of crashing in a
    loop or mistaking the file for an empty-but-valid baseline."""
    path = tmp_path / "manifest.json"
    path.write_text(payload, encoding="utf-8")
    assert manifest.load(path) is None


def test_manifest_load_non_dict_entry(tmp_path):
    """load() returns None when a per-file entry is not a dict (here a bare
    integer), which is the corruption shape a hand-edited or partially
    overwritten manifest.json could produce. ``Manifest.from_dict`` raises
    ``TypeError`` for such entries, and ``load`` catches that ``TypeError``
    alongside ``JSONDecodeError``/``OSError`` so the pipeline regenerates the
    manifest on the next write instead of crashing in a loop -- losing the
    baseline is the safe failure mode, since it only costs one noisy
    "everything changed" run."""
    path = tmp_path / "manifest.json"
    path.write_text('{"files": {"a": 42}}', encoding="utf-8")
    assert manifest.load(path) is None


def test_manifest_load_entry_missing_required_fields(tmp_path):
    """load() returns None when a per-file entry is a dict but is missing the
    fields ``FileEntry`` requires (here only ``slug`` is present). ``from_dict``
    surfaces this as a ``TypeError`` (re-raised with the offending slug so the
    bad entry is findable in a large manifest), which ``load`` catches and
    treats as a missing baseline for the same crash-loop-avoidance reason as
    corrupt JSON or non-dict entries."""
    path = tmp_path / "manifest.json"
    path.write_text('{"files": {"a": {"slug": "a"}}}', encoding="utf-8")
    assert manifest.load(path) is None


def test_from_dict_null_last_updated_falls_back_to_now():
    """An explicit ``"last_updated": null`` in the JSON must fall back to the
    current time just like a missing key. ``dict.get(key, default)`` only
    substitutes the default for a MISSING key and would return the stored
    None verbatim here, which would later render as the literal text
    "Last updated: None" in the index -- hence the fallback uses ``or``."""
    m = manifest.Manifest.from_dict({"last_updated": None})
    assert m.last_updated  # non-empty, never None
    assert m.last_updated != "None"


def test_from_dict_missing_last_updated_falls_back_to_now():
    """A manifest without any ``last_updated`` key likewise gets stamped with
    the current time on load -- the field is always a usable ISO string."""
    m = manifest.Manifest.from_dict({})
    assert m.last_updated


def test_manifest_load_entry_empty_hash(tmp_path):
    """A per-file entry with an empty ``"hash": ""`` is corrupt, not merely
    ahead of this version: ``FileEntry.__post_init__`` rejects it because an
    empty hash would compare equal to any other empty hash and report two
    unrelated pages as unmodified. Under the documented tolerant-loading
    contract, ``load`` treats that schema corruption exactly like corrupt
    JSON: it warns and returns None ("no baseline"), so the next run
    regenerates the manifest instead of crash-looping on it."""
    path = tmp_path / "manifest.json"
    entry = dataclasses.asdict(_file_entry("a"))
    entry["hash"] = ""
    path.write_text(json.dumps({"files": {"a": entry}}), encoding="utf-8")
    assert manifest.load(path) is None


# --- slug re-validation on load (path-traversal defense) -------------------------

# Slugs that discovery-time validation (Page) would reject, and that a
# tampered or corrupt manifest.json must therefore also be rejected for: the
# pipeline's deletion cleanup unlinks ``base / f"{slug}.md"`` verbatim, so a
# traversal slug smuggled in via the manifest would delete files outside the
# mirror tree.
_MALICIOUS_SLUGS = [
    "../../../etc/x",  # walks out of the per-source docs directory
    "/etc/passwd",  # absolute path: Path(base) / slug discards base
    "foo/",  # trailing slash: malformed as a file name
    "bad slug",  # character outside the whitelist (space)
    "a" * 201,  # over the 200-character slug length cap
]


@pytest.mark.parametrize("bad_slug", _MALICIOUS_SLUGS)
def test_file_entry_rejects_malicious_slug(bad_slug):
    """Constructing a FileEntry with a slug that Page would reject must raise
    immediately: FileEntry re-runs the full discovery-time slug contract so
    the on-disk entry point (manifest load) is held to the same standard as
    the upstream entry point (page discovery)."""
    with pytest.raises(ValueError, match="FileEntry.slug"):
        make_entry(bad_slug)


@pytest.mark.parametrize("bad_slug", _MALICIOUS_SLUGS)
def test_from_dict_rejects_malicious_slug(bad_slug):
    """A manifest dict whose entry carries a hostile slug must fail
    deserialization with TypeError (from_dict's corruption signal), naming
    the offending slug so the bad entry is findable in a large manifest."""
    entry = dataclasses.asdict(_file_entry("a"))
    entry["slug"] = bad_slug
    with pytest.raises(TypeError, match="Corrupt manifest entry"):
        manifest.Manifest.from_dict({"files": {bad_slug: entry}})


@pytest.mark.parametrize("bad_slug", _MALICIOUS_SLUGS)
def test_load_rejects_manifest_with_malicious_slug(tmp_path, bad_slug):
    """End to end: a manifest.json on disk containing a hostile slug (the
    path-traversal attack shape) must make ``load()`` warn and return None
    ("no baseline"), so the pipeline regenerates the manifest on the next
    write instead of ever passing the traversal slug to the deletion
    cleanup step."""
    path = tmp_path / "manifest.json"
    entry = dataclasses.asdict(_file_entry("a"))
    entry["slug"] = bad_slug
    path.write_text(json.dumps({"files": {bad_slug: entry}}), encoding="utf-8")
    assert manifest.load(path) is None


# --- FileEntry identity / rendered-field re-validation on load ---------------
#
# FileEntry is constructed not only from Page (already validated at discovery
# time) but also from Manifest.from_dict when a persisted manifest.json is
# loaded back from disk. The tests below pin the load-path re-validation that
# hardens against tampered, hand-edited, or partially-overwritten manifests:
# every field a renderer later consumes must be held to the same standard at
# the on-disk entry point as at the discovery entry point. Each ValueError
# raised here is wrapped by from_dict as a TypeError, which load() then maps
# to "no baseline" -- preserving the tolerant-load contract.


@pytest.mark.parametrize("field", ["source_url", "source_md_url"])
@pytest.mark.parametrize("value", ["", "   "])
def test_file_entry_rejects_empty_or_whitespace_url(field, value):
    """Both URL fields must be non-empty and non-whitespace when loaded from
    disk, mirroring Page's discovery-time check: they render as
    ``[source](<url>)`` links in the per-source README and the whats-new log,
    and an empty URL would produce a broken link on every page row.
    Whitespace-only values are truthy in Python, so the guard strips before
    checking emptiness."""
    base = dataclasses.asdict(_file_entry("a"))
    base[field] = value
    with pytest.raises(ValueError, match=f"FileEntry.{field} must be a non-empty"):
        manifest.FileEntry(**base)


def test_file_entry_rejects_unstripped_source_id():
    """An unstripped ``source_id`` loaded from a tampered manifest must raise,
    mirroring Page's discovery-time check: rename detection in ``core.diff``
    matches on source_id *equality*, so ``"a"`` and ``"a "`` would be treated
    as two different upstream identities and split one page's history into a
    fabricated add/remove pair."""
    base = dataclasses.asdict(_file_entry("a"))
    base["source_id"] = "a "
    with pytest.raises(ValueError, match="FileEntry.source_id must be stripped"):
        manifest.FileEntry(**base)


@pytest.mark.parametrize(
    "field", ["title", "source_url", "source_md_url", "group", "last_updated"]
)
def test_file_entry_rejects_non_string_rendered_field(field):
    """Every field a renderer later reads (``title.translate``,
    ``safe_url(source_url)``, f-string interpolation of ``group`` and
    ``last_updated``) must be a string at load time. A JSON ``null`` in a
    hand-edited manifest would otherwise pass load silently and crash the
    renderer with ``AttributeError`` AFTER content files have been written
    and BEFORE ``manifest.save`` runs -- leaving the manifest corrupt and the
    source stuck in a crash loop on every subsequent run. ``isinstance`` (not
    truthiness) is used because empty strings are legal for some of these
    (``last_updated`` is left empty by ``fetch_pages`` until ``write_docs``
    stamps it; ``group`` defaults to ``""``)."""
    base = dataclasses.asdict(_file_entry("a"))
    base[field] = None
    with pytest.raises(ValueError, match=f"FileEntry.{field} must be"):
        manifest.FileEntry(**base)


def test_load_rejects_manifest_with_null_title(tmp_path):
    """End to end: a manifest.json whose entry carries ``"title": null`` is
    corrupt, not merely ahead of this version. ``FileEntry.__post_init__``'s
    type guard rejects it, ``from_dict`` wraps the ValueError as TypeError,
    and ``load()`` maps that to "no baseline" (returns None) so the pipeline
    regenerates the manifest on the next write instead of crash-looping on
    the bad entry -- the same crash-loop-avoidance contract as a malicious
    slug or an empty hash."""
    path = tmp_path / "manifest.json"
    entry = dataclasses.asdict(_file_entry("a"))
    entry["title"] = None
    path.write_text(json.dumps({"files": {"a": entry}}), encoding="utf-8")
    assert manifest.load(path) is None


def test_load_rejects_manifest_with_empty_source_url(tmp_path):
    """End to end: a manifest.json whose entry carries an empty
    ``source_url`` is corrupt (it would render as a broken ``[source](<>)``
    link on every page row of the per-source README). ``load()`` must reject
    it and return None so the next run regenerates, rather than passing the
    empty URL through to the renderer."""
    path = tmp_path / "manifest.json"
    entry = dataclasses.asdict(_file_entry("a"))
    entry["source_url"] = ""
    path.write_text(json.dumps({"files": {"a": entry}}), encoding="utf-8")
    assert manifest.load(path) is None


def test_manifest_load_non_utf8_bytes(tmp_path):
    """A manifest file containing binary garbage (bytes that are not valid
    UTF-8) must be treated exactly like corrupt JSON: ``load()`` warns and
    returns None ("no baseline") so the next run regenerates the manifest,
    instead of crashing the whole run with an uncaught ``UnicodeDecodeError``
    from ``read_text``. This is the fourth tolerated-failure shape in
    ``load()``'s docstring, alongside invalid JSON, schema corruption, and
    unreadable files."""
    path = tmp_path / "manifest.json"
    # \xff\xfe are invalid UTF-8 start bytes: read_text(encoding="utf-8")
    # raises UnicodeDecodeError before json.loads ever runs.
    path.write_bytes(b'\xff\xfe{"files": {}}\x00\x01')
    assert manifest.load(path) is None


# --- last_updated hardening on load -------------------------------------------
#
# ``last_updated`` flows verbatim into ``core.index.render``'s "Last
# updated:" line, so -- like every FileEntry field -- it is validated at
# load: it must be a non-empty string without embedded newlines, else the
# current time is substituted (tolerant fallback rather than load failure,
# because a bad run-level timestamp only loses cosmetic information).


def test_from_dict_non_string_last_updated_falls_back_to_now():
    """A non-string ``last_updated`` (e.g. a JSON number from a hand-edited
    manifest) must not flow into the index renderer; the tolerant fallback
    stamps the current time instead, so the README's "Last updated:" line is
    always a usable string."""
    m = manifest.Manifest.from_dict({"last_updated": 12345})
    assert m.last_updated
    assert isinstance(m.last_updated, str)
    assert m.last_updated != "12345"


def test_from_dict_newline_bearing_last_updated_falls_back_to_now():
    """A ``last_updated`` containing ``\\n`` or ``\\r`` would split the
    README's "Last updated:" header line and inject a stray line into the
    generated index, so it must be replaced by the current-time fallback."""
    m = manifest.Manifest.from_dict({"last_updated": "2026-01-01\ninjected line"})
    assert "\n" not in m.last_updated
    m2 = manifest.Manifest.from_dict({"last_updated": "2026-01-01\rX"})
    assert "\r" not in m2.last_updated


def test_from_dict_valid_last_updated_is_kept():
    """A well-formed string ``last_updated`` must survive the load
    unchanged -- the new validation only rejects values that would corrupt
    the rendered index, never legitimate timestamps."""
    m = manifest.Manifest.from_dict({"last_updated": "2026-01-01T00:00:00Z"})
    assert m.last_updated == "2026-01-01T00:00:00Z"


# --- version field handling ---------------------------------------------------


def test_manifest_version_round_trip():
    """A Manifest with a custom version must survive to_dict / from_dict."""
    m = manifest.Manifest(version="1.2.3")
    data = m.to_dict()
    assert data["version"] == "1.2.3"
    back = manifest.Manifest.from_dict(data)
    assert back.version == "1.2.3"


def test_manifest_version_default_and_fallback():
    """Missing, empty, non-string, or newline-bearing version must default to em-dash."""
    m_default = manifest.Manifest()
    assert m_default.version == "—"

    assert manifest.Manifest.from_dict({}).version == "—"
    assert manifest.Manifest.from_dict({"version": None}).version == "—"
    assert manifest.Manifest.from_dict({"version": 123}).version == "—"
    assert manifest.Manifest.from_dict({"version": "   "}).version == "—"
    assert manifest.Manifest.from_dict({"version": "1.0\ninjected"}).version == "—"
    assert manifest.Manifest.from_dict({"version": "1.0\r"}).version == "—"
