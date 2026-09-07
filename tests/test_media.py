"""Tests for the source-agnostic media/static-asset stage (mirror.core.media).

The stage is exercised at every level: reference extraction and rewriting as
pure functions, download planning/dedup, the download + cache + failure-
isolation behavior of ``download_assets``, the guarded pruning, and the
``stage_pages`` orchestration (rewrite + re-hash + prune) against the real
mirror layout ``docs/<source>/<slug>.md``.  The two configs below mirror the
real upstream shapes the stage was built for -- kimi-code's flat
``docs/media/`` images and opencode's nested ``packages/web/src/assets/``
tree -- so the tests double as documentation of the supported layouts.

All fetches run against ``_FakeClient`` scripts (no network), all file I/O
happens under ``tmp_path`` (isolated per test), and the pipeline's
``config.DOCS_DIR`` monkeypatch from conftest is irrelevant here: the stage
takes its output base explicitly as ``source_dir``.
"""

import hashlib
import os
from pathlib import Path

import pytest
from conftest import _FakeClient, _Resp, make_entry
from mirror.core import media

# kimi-code: images referenced as ``../../media/<file>`` from pages two
# directories deep, served from the upstream ``docs/media/`` directory.
KIMI = media.AssetSourceConfig(
    name="kimi-code",
    asset_subdir="media",
    ref_prefixes=("../../media/",),
    raw_base_url="https://raw.githubusercontent.com/MoonshotAI/kimi-code/main/docs/media/",
)

# opencode: images referenced as ``../../assets/<relpath>`` from pages at
# the docs root, served from ``packages/web/src/assets/`` (nested
# subdirectories preserved in the mirrored asset dir).
OPENCODE = media.AssetSourceConfig(
    name="opencode",
    asset_subdir="assets",
    ref_prefixes=("../../assets/",),
    raw_base_url="https://raw.githubusercontent.com/anomalyco/opencode/dev/packages/web/src/assets/",
)

# Arbitrary non-UTF-8 payloads standing in for real images: the stage must
# never decode asset bytes, so the test fixtures must not be valid UTF-8
# text either (a JPEG header opens each blob).
IMAGE_A = b"\xff\xd8\xff\xe0jpeg-a"
IMAGE_B = b"\xff\xd8\xff\xe1jpeg-b"
IMAGE_C = b"\x89PNG\r\n\x1a\nc"


class _BinaryResp:
    """Minimal response stub whose body is raw binary rather than UTF-8 text.

    Conftest's ``_Resp`` encodes its text body on ``iter_bytes()``, which
    cannot carry non-UTF-8 payloads; the media downloads must round-trip
    arbitrary bytes, so the binary tests script this stub instead.  Only the
    members the fetch path reads are implemented (same contract as
    ``_Resp``: status_code, headers, iter_bytes).
    """

    encoding = "utf-8"

    def __init__(self, status: int, body: bytes) -> None:
        self.status_code = status
        self.headers: dict[str, str] = {}
        self._body = body

    def iter_bytes(self):
        """Yield the whole binary body as one chunk."""
        yield self._body


def _source_dir(tmp_path: Path, name: str = "kimi-code") -> Path:
    """Build the ``docs/<source>`` base directory a test mirrors into."""
    return tmp_path / "docs" / name


def _sha256(text: str) -> str:
    """Independent sha256 hex digest of a (rewritten) page text."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


# --- AssetSourceConfig validation --------------------------------------------


def test_asset_source_config_rejects_invalid_values():
    """Every config field is validated at construction time.

    A typo in one of these immutable rules would otherwise surface only as
    silently-missed rewrites (bad prefix/base URL) or -- for an unsafe
    asset_subdir -- downloads and pruning that escape ``docs/<source>``."""
    valid = dict(
        name="src",
        asset_subdir="media",
        ref_prefixes=("../../media/",),
        raw_base_url="https://example.com/base/",
    )
    with pytest.raises(ValueError, match="name"):
        media.AssetSourceConfig(**{**valid, "name": "   "})
    for bad_subdir in ("", ".", "..", "a/b", "a\\b"):
        with pytest.raises(ValueError, match="asset_subdir"):
            media.AssetSourceConfig(**{**valid, "asset_subdir": bad_subdir})
    with pytest.raises(ValueError, match="ref_prefixes"):
        media.AssetSourceConfig(**{**valid, "ref_prefixes": ()})
    with pytest.raises(ValueError, match="ref_prefixes"):
        media.AssetSourceConfig(**{**valid, "ref_prefixes": ("no-trailing-slash",)})
    with pytest.raises(ValueError, match="raw_base_url"):
        media.AssetSourceConfig(**{**valid, "raw_base_url": "https://e/no-slash"})


# --- Reference extraction ----------------------------------------------------


def test_extract_refs_kimi_finds_only_configured_prefix_refs():
    """Only references starting with the configured prefix are extracted.

    Already-rewritten refs, refs of other sources/prefixes, and absolute
    URLs share the file-extension shape but must not be mistaken for asset
    references -- extraction drives downloads AND the prune reference set,
    so a false positive would download (and keep alive) a file no page uses.
    """
    text = (
        "![a](../../media/provider-manager.jpg) real ref\n"
        "![b](../media/provider-manager.jpg) already rewritten\n"
        "![c](../../assets/lander/screenshot.png) other source\n"
        "![d](https://example.com/x.png) absolute URL\n"
        "![e](../assets/web/y.png) other already-rewritten\n"
    )
    assert media.extract_refs(text, KIMI) == (
        media.AssetRef(
            raw="../../media/provider-manager.jpg",
            asset_path="provider-manager.jpg",
        ),
    )


def test_extract_refs_opencode_keeps_nested_subdirectories():
    """opencode's refs carry a subdirectory; the asset_path preserves it.

    ``lander/screenshot.png`` and ``web/web-homepage-new-session.png`` both
    live under ``docs/opencode/assets/`` in subdirectories that must survive
    extraction, downloading, and pruning."""
    text = (
        "![web](../../assets/web/web-homepage-new-session.png)\n"
        "![lander](../../assets/lander/screenshot.png)\n"
    )
    assert media.extract_refs(text, OPENCODE) == (
        media.AssetRef(
            raw="../../assets/web/web-homepage-new-session.png",
            asset_path="web/web-homepage-new-session.png",
        ),
        media.AssetRef(
            raw="../../assets/lander/screenshot.png",
            asset_path="lander/screenshot.png",
        ),
    )


def test_extract_refs_ignores_remainders_that_escape_the_asset_dir():
    """Refs whose remainder climbs above the asset dir are not asset refs.

    Page text is raw network input, so ``..`` segments (or an absolute
    remainder) inside a ref must never become a download target or a prune
    key -- an escaped download would write outside ``docs/<source>`` and an
    escaped prune key would silently fail to protect an in-dir file."""
    text = (
        "![a](../../media/ok.jpg)\n"
        "![b](../../media/../escape.jpg)\n"
        "![c](../../media/../../escape.jpg)\n"
        "![d](../../media/..)\n"
        "![e](../../media//abs.png)\n"
    )
    assert media.extract_refs(text, KIMI) == (
        media.AssetRef(raw="../../media/ok.jpg", asset_path="ok.jpg"),
    )


def test_extract_refs_rejects_backslash_remainders():
    """A backslash inside a remainder is refused outright.

    ``posixpath.normpath`` treats ``\\`` as an ordinary character, so a
    remainder like ``..\\..\\x.png`` would look safe to the POSIX normalizer
    while escaping the asset directory on Windows (where ``Path`` reads it
    as a separator). Rejecting backslashes keeps the confinement guarantee
    platform-independent."""
    text = (
        "![a](../../media/ok.jpg)\n"
        "![b](../../media/..\\..\\escape.jpg)\n"
        "![c](../../media/sub\\dir.png)\n"
    )
    assert media.extract_refs(text, KIMI) == (
        media.AssetRef(raw="../../media/ok.jpg", asset_path="ok.jpg"),
    )


def test_extract_refs_normalizes_safe_dot_segments():
    """Dot segments that stay INSIDE the asset dir normalize to one path.

    ``web/../web/logo.png`` is a roundabout but harmless way to write
    ``web/logo.png``; both the download target and the prune key must use
    the normalized form so the same file is never fetched or tracked twice.
    """
    text = "![x](../../media/web/../web/logo.png)\n"
    assert media.extract_refs(text, KIMI) == (
        media.AssetRef(
            raw="../../media/web/../web/logo.png",
            asset_path="web/logo.png",
        ),
    )


# --- Reference rewriting -----------------------------------------------------


def test_rewrite_refs_emits_paths_that_resolve_from_the_page_directory(tmp_path: Path):
    """Each rewritten ref must point at the asset from the PAGE's location.

    The mirrored layout relocates pages to ``docs/<source>/<slug>.md`` while
    assets land in ``docs/<source>/<asset-dir>/``; a ref rewritten with
    ``os.path.relpath`` between those two directories renders correctly no
    matter how deep the page sits.  Two real layouts are pinned: kimi-code's
    one-level-deep pages and opencode's root-level pages."""
    source_dir = _source_dir(tmp_path)
    cases = (
        (
            KIMI,
            "configuration/providers",
            "![Manager](../../media/provider-manager.jpg)\n",
            "![Manager](../media/provider-manager.jpg)\n",
        ),
        (
            KIMI,
            "guides/remote-control",
            "![Ctrl](../../media/remote.jpg)\n",
            "![Ctrl](../media/remote.jpg)\n",
        ),
        (
            OPENCODE,
            "web",
            "![Web](../../assets/web/web-homepage-new-session.png)\n",
            "![Web](assets/web/web-homepage-new-session.png)\n",
        ),
        (
            OPENCODE,
            "intro",
            "![Lander](../../assets/lander/screenshot.png)\n",
            "![Lander](assets/lander/screenshot.png)\n",
        ),
    )
    for config, slug, raw_text, expected in cases:
        rewritten = media.rewrite_refs(raw_text, config, source_dir, slug)
        assert rewritten == expected
        # The rewritten reference must lexically resolve to the asset file
        # when joined onto the page's mirrored directory.
        page_dir = (source_dir / slug).parent
        asset_path = media.extract_refs(raw_text, config)[0].asset_path
        target = source_dir / config.asset_subdir / asset_path
        relative = rewritten.split("](", 1)[1].rstrip(")\n")
        joined = os.path.normpath(os.path.join(str(page_dir), relative))
        assert joined == os.path.normpath(str(target))


def test_rewrite_refs_is_idempotent(tmp_path: Path):
    """Rewriting an already-rewritten page is a byte-for-byte no-op.

    The mirror runs repeatedly over the same upstream texts; if the rewrite
    were not idempotent every run would change the page (new hash, new diff,
    rewritten file, git churn) forever.  Rewritten refs no longer match the
    upstream prefixes, so the second pass leaves the text untouched."""
    source_dir = _source_dir(tmp_path)
    raw = "# Providers\n\n![p](../../media/provider-manager.jpg)\n"
    once = media.rewrite_refs(raw, KIMI, source_dir, "configuration/providers")
    twice = media.rewrite_refs(once, KIMI, source_dir, "configuration/providers")
    assert once == "# Providers\n\n![p](../media/provider-manager.jpg)\n"
    assert twice == once


def test_rewrite_refs_touches_only_configured_prefixes(tmp_path: Path):
    """Unrelated text -- including refs of other shapes -- stays verbatim.

    The rewrite must be surgical: absolute URLs, refs of other sources,
    already-rewritten refs, and bare mentions in prose all survive
    byte-identical.  Only the one real opencode ref changes."""
    source_dir = _source_dir(tmp_path)
    text = (
        "![ok](../../assets/web/x.png)\n"
        "![rewritten](../media/y.jpg)\n"
        "![foreign](../../media/y.jpg)\n"
        "![abs](https://example.com/z.png)\n"
        "mention: assets/web/x.png\n"
    )
    rewritten = media.rewrite_refs(text, OPENCODE, source_dir, "web")
    assert rewritten == (
        "![ok](assets/web/x.png)\n"
        "![rewritten](../media/y.jpg)\n"
        "![foreign](../../media/y.jpg)\n"
        "![abs](https://example.com/z.png)\n"
        "mention: assets/web/x.png\n"
    )


# --- Download planning -------------------------------------------------------


def test_plan_downloads_deduplicates_and_builds_urls(tmp_path: Path):
    """Two pages sharing an asset produce exactly one download.

    Dedup is keyed on the normalized asset path (two refs of the same file,
    even via different dot-segment spellings, collapse to one), and the plan
    order is deterministic -- first-reference order across the pages."""
    source_dir = _source_dir(tmp_path)
    texts = {
        "guides/web": "![a](../../media/x.jpg)\n![b](../../media/y.jpg)\n",
        "configuration/providers": "![c](../../media/x.jpg)\n",
    }
    downloads = media.plan_downloads(texts, KIMI, source_dir)
    assert [download.asset_path for download in downloads] == ["x.jpg", "y.jpg"]
    assert downloads[0].url == (
        "https://raw.githubusercontent.com/MoonshotAI/kimi-code/main/docs/media/x.jpg"
    )
    assert downloads[0].local_path == source_dir / "media" / "x.jpg"


def test_plan_downloads_skips_unsafe_refs(tmp_path: Path):
    """Traversal-carrying refs are excluded from the plan entirely."""
    source_dir = _source_dir(tmp_path)
    texts = {"web": "![a](../../assets/ok.png)\n![b](../../assets/../nope.png)\n"}
    downloads = media.plan_downloads(texts, OPENCODE, source_dir)
    assert [download.asset_path for download in downloads] == ["ok.png"]


# --- Downloading -------------------------------------------------------------


def test_download_assets_writes_missing_files(tmp_path: Path):
    """First-run downloads land byte-exact, creating nested directories.

    The asset subdirectory does not exist yet; the download must create it
    (including opencode-style nested subdirs) and never leave a staging
    ``.tmp`` file behind."""
    source_dir = _source_dir(tmp_path)
    downloads = (
        media.AssetDownload(
            url=KIMI.raw_base_url + "a.png",
            local_path=source_dir / "media" / "a.png",
            asset_path="a.png",
        ),
        media.AssetDownload(
            url=OPENCODE.raw_base_url + "web/x.png",
            local_path=source_dir / "assets" / "web" / "x.png",
            asset_path="web/x.png",
        ),
    )
    client = _FakeClient([_BinaryResp(200, IMAGE_A), _BinaryResp(200, IMAGE_B)])
    result = media.download_assets(client, downloads)
    assert result.written == 2
    assert result.cached == 0
    assert result.failed == ()
    assert (source_dir / "media" / "a.png").read_bytes() == IMAGE_A
    assert (source_dir / "assets" / "web" / "x.png").read_bytes() == IMAGE_B
    assert list(source_dir.rglob("*.tmp")) == []


def test_download_assets_skips_unchanged_on_disk_bytes(tmp_path: Path, monkeypatch):
    """Identical on-disk bytes are never written again; changed bytes replace.

    The write-only-what-changed contract is what keeps consecutive mirror
    runs git-clean for binary files: an unchanged asset costs a fetch and a
    digest comparison but NO write and NO rename (pinned here by spying on
    ``atomic_write_bytes`` -- a cache hit must not call it at all)."""
    source_dir = _source_dir(tmp_path)
    target = source_dir / "media" / "a.png"
    target.parent.mkdir(parents=True)
    target.write_bytes(IMAGE_A)
    written_to: list[Path] = []
    real_write = media.atomic_write_bytes

    def spy_write(dest: Path, content: bytes) -> None:
        written_to.append(dest)

    monkeypatch.setattr(media, "atomic_write_bytes", spy_write)
    downloads = (
        media.AssetDownload(
            url=KIMI.raw_base_url + "a.png",
            local_path=target,
            asset_path="a.png",
        ),
    )
    # Same bytes on disk as upstream: cache hit, zero writes.
    result = media.download_assets(_FakeClient([_BinaryResp(200, IMAGE_A)]), downloads)
    assert result.cached == 1
    assert result.written == 0
    assert written_to == []
    # Upstream changed the bytes: the write path is taken and the spy called.
    result = media.download_assets(_FakeClient([_BinaryResp(200, IMAGE_B)]), downloads)
    assert result.written == 1
    assert result.cached == 0
    assert written_to == [target]
    # The spy records but does not write; restore the real helper and re-run
    # the same fetch so the changed bytes actually replace the file on disk.
    monkeypatch.setattr(media, "atomic_write_bytes", real_write)
    result = media.download_assets(_FakeClient([_BinaryResp(200, IMAGE_B)]), downloads)
    assert result.written == 1
    assert target.read_bytes() == IMAGE_B
    assert list(source_dir.rglob("*.tmp")) == []


def test_download_assets_isolates_failures_per_asset(tmp_path: Path):
    """A failed download is recorded and never aborts the remaining assets.

    A single upstream file that was renamed or removed must not take the
    whole stage down: the healthy assets still download, and the failed one
    stays in the report (the deterministic page rewrite means a healthy next
    run retries it naturally)."""
    source_dir = _source_dir(tmp_path)
    gone_url = KIMI.raw_base_url + "gone.jpg"
    downloads = (
        media.AssetDownload(
            url=KIMI.raw_base_url + "a.png",
            local_path=source_dir / "media" / "a.png",
            asset_path="a.png",
        ),
        media.AssetDownload(
            url=gone_url,
            local_path=source_dir / "media" / "gone.jpg",
            asset_path="gone.jpg",
        ),
        media.AssetDownload(
            url=KIMI.raw_base_url + "c.png",
            local_path=source_dir / "media" / "c.png",
            asset_path="c.png",
        ),
    )
    client = _FakeClient(
        [_BinaryResp(200, IMAGE_A), _Resp(404), _BinaryResp(200, IMAGE_C)]
    )
    result = media.download_assets(client, downloads)
    assert result.written == 2
    assert len(result.failed) == 1
    url, reason = result.failed[0]
    assert url == gone_url
    assert "404" in reason
    assert (source_dir / "media" / "a.png").read_bytes() == IMAGE_A
    assert (source_dir / "media" / "c.png").read_bytes() == IMAGE_C
    assert not (source_dir / "media" / "gone.jpg").exists()


# --- Pruning -----------------------------------------------------------------


def test_prune_assets_removes_unreferenced_files_and_emptied_dirs(tmp_path: Path):
    """Unreferenced files vanish; referenced ones (incl. nested) survive.

    The asset dir must be an exact image of what the current pages
    reference: stale files are deleted, the subdirectories they emptied are
    removed bottom-up, and nothing OUTSIDE the asset dir (pages, other
    files) is ever touched."""
    source_dir = _source_dir(tmp_path)
    asset_dir = source_dir / "media"
    (asset_dir / "sub").mkdir(parents=True)
    (asset_dir / "sub2").mkdir(parents=True)
    (asset_dir / "keep.jpg").write_bytes(b"1")
    (asset_dir / "stale.jpg").write_bytes(b"2")
    (asset_dir / "sub" / "deep.png").write_bytes(b"3")
    (asset_dir / "sub2" / "keep2.png").write_bytes(b"4")
    (source_dir / "page.md").write_text("page", encoding="utf-8")

    removed = media.prune_assets(KIMI, source_dir, {"keep.jpg", "sub2/keep2.png"})

    # stale.jpg, sub/deep.png, and the emptied sub/ directory itself.
    assert removed == 3
    assert (asset_dir / "keep.jpg").exists()
    assert (asset_dir / "sub2" / "keep2.png").exists()
    assert not (asset_dir / "stale.jpg").exists()
    assert not (asset_dir / "sub").exists()
    assert (source_dir / "page.md").exists()


def test_prune_assets_empty_reference_set_prunes_nothing(tmp_path: Path):
    """An empty reference set must never read as "delete everything".

    The guard is the stage's last line of defense against a run that failed
    before collecting its references: pruning on an empty set would wipe an
    asset directory whose pages still reference every file in it."""
    source_dir = _source_dir(tmp_path)
    asset_dir = source_dir / "media"
    asset_dir.mkdir(parents=True)
    (asset_dir / "only.jpg").write_bytes(IMAGE_A)

    assert media.prune_assets(KIMI, source_dir, set()) == 0
    assert (asset_dir / "only.jpg").exists()


def test_prune_assets_without_asset_dir_is_a_noop(tmp_path: Path):
    """A source that never had an asset dir prunes nothing (and does not create it)."""
    source_dir = _source_dir(tmp_path)
    assert media.prune_assets(KIMI, source_dir, {"x.jpg"}) == 0
    assert not (source_dir / "media").exists()


# --- stage_pages orchestration -----------------------------------------------


def test_stage_pages_full_flow(tmp_path: Path):
    """End-to-end: download + rewrite + re-hash + prune in one call.

    Pins the stage's contract with the pipeline: the returned texts carry
    the rewritten refs, the rewritten page's entry hash is replaced with the
    sha256 of the REWRITTEN text (so diff() compares like with like against
    what write_docs will put on disk), unaffected entries keep their object
    identity, the asset lands on disk, and the unreferenced stale file is
    pruned."""
    source_dir = _source_dir(tmp_path)
    (source_dir / "media").mkdir(parents=True)
    (source_dir / "media" / "stale.jpg").write_bytes(b"stale")
    (source_dir / "guides").mkdir(parents=True)
    entries = {
        "configuration/providers": make_entry(
            slug="configuration/providers", group="config", hash="old-hash-a"
        ),
        "guides/remote-control": make_entry(
            slug="guides/remote-control", group="guides", hash="old-hash-b"
        ),
    }
    raw = "# Providers\n\n![Provider manager](../../media/provider-manager.jpg)\n"
    texts = {
        "configuration/providers": raw,
        "guides/remote-control": "# Remote control\n\nno assets here\n",
    }
    client = _FakeClient([_BinaryResp(200, IMAGE_A)])

    new_entries, new_texts, result = media.stage_pages(
        client, KIMI, source_dir, entries, texts
    )

    expected = "# Providers\n\n![Provider manager](../media/provider-manager.jpg)\n"
    assert new_texts["configuration/providers"] == expected
    assert new_texts["guides/remote-control"] == texts["guides/remote-control"]
    assert new_entries["configuration/providers"].hash == _sha256(expected)
    assert new_entries["guides/remote-control"] is entries["guides/remote-control"]
    assert (source_dir / "media" / "provider-manager.jpg").read_bytes() == IMAGE_A
    assert not (source_dir / "media" / "stale.jpg").exists()
    assert result.assets_written == 1
    assert result.assets_cached == 0
    assert result.assets_failed == ()
    assert result.pages_rewritten == 1
    assert result.files_pruned == 1


def test_stage_pages_second_run_is_fully_cached_and_stable(tmp_path: Path):
    """Re-running the stage over the same input writes nothing and prunes nothing.

    Simulates the next mirror run after a successful one: the page text
    (already rewritten on disk, fresh upstream text identical) is rewritten
    to the same string, the asset bytes match, and the referenced file is
    not pruned -- the whole stage is a no-op apart from the fetch."""
    source_dir = _source_dir(tmp_path)
    (source_dir / "media").mkdir(parents=True)
    (source_dir / "media" / "pic.jpg").write_bytes(IMAGE_A)
    slug = "guides/web"
    entries = {slug: make_entry(slug=slug, hash="abc123")}
    texts = {slug: "![p](../../media/pic.jpg)\n"}

    new_entries, new_texts, result = media.stage_pages(
        client=_FakeClient([_BinaryResp(200, IMAGE_A)]),
        config=KIMI,
        source_dir=source_dir,
        entries=entries,
        texts=texts,
    )

    assert new_texts[slug] == "![p](../media/pic.jpg)\n"
    # The rewrite is deterministic, so the re-hash lands on the same value
    # as the first run -- the page never looks "changed" again.
    assert new_entries[slug].hash == _sha256("![p](../media/pic.jpg)\n")
    assert (source_dir / "media" / "pic.jpg").exists()
    assert result.assets_cached == 1
    assert result.assets_written == 0
    assert result.pages_rewritten == 1
    assert result.files_pruned == 0
    assert result.assets_failed == ()


def test_stage_pages_does_not_prune_with_carried_forward_entries(tmp_path: Path):
    """Prune is skipped when any manifest entry was carried forward.

    A carried-forward page (failed fetch, entry kept with its OLD hash, no
    fresh text) still displays last run's already-rewritten refs on disk --
    refs this run's fresh-text extraction cannot see.  Pruning against the
    fresh reference set alone would delete the assets that page still
    references, so the whole prune step is gated off; the fresh page still
    downloads and rewrites normally, and the carried entry keeps its object
    identity and hash."""
    source_dir = _source_dir(tmp_path)
    (source_dir / "media").mkdir(parents=True)
    (source_dir / "media" / "carried-only.jpg").write_bytes(b"still needed")
    fresh_slug = "guides/web"
    carried_slug = "guides/remote-control"
    entries = {
        fresh_slug: make_entry(slug=fresh_slug, hash="old-fresh"),
        carried_slug: make_entry(slug=carried_slug, hash="old-carried"),
    }
    texts = {fresh_slug: "![p](../../media/pic.jpg)\n"}
    client = _FakeClient([_BinaryResp(200, IMAGE_A)])

    new_entries, new_texts, result = media.stage_pages(
        client, KIMI, source_dir, entries, texts
    )

    assert new_texts[fresh_slug] == "![p](../media/pic.jpg)\n"
    assert new_entries[carried_slug] is entries[carried_slug]
    assert new_entries[carried_slug].hash == "old-carried"
    # The stale-looking asset the carried-forward page still references
    # survives, because the run never pruned.
    assert (source_dir / "media" / "carried-only.jpg").exists()
    assert result.files_pruned == 0


def test_stage_pages_rewrites_despite_asset_download_failure(tmp_path: Path):
    """A failed asset fetch does not block the deterministic page rewrite.

    The rewritten text and its re-hash are pure functions of the fresh text,
    so the page is made consistent with the asset dir even when the asset
    itself could not be fetched this run (404 from a renamed upstream file);
    the failure is reported for the operator and heals on a later run."""
    slug = "configuration/providers"
    source_dir = _source_dir(tmp_path)
    entries = {slug: make_entry(slug=slug, hash="old")}
    raw = "![x](../../media/gone.jpg)\n"
    texts = {slug: raw}

    new_entries, new_texts, result = media.stage_pages(
        client=_FakeClient([_Resp(404)]),
        config=KIMI,
        source_dir=source_dir,
        entries=entries,
        texts=texts,
    )

    expected = "![x](../media/gone.jpg)\n"
    assert new_texts[slug] == expected
    assert new_entries[slug].hash == _sha256(expected)
    assert len(result.assets_failed) == 1
    assert result.assets_failed[0][0] == KIMI.raw_base_url + "gone.jpg"
    assert "404" in result.assets_failed[0][1]
    assert result.pages_rewritten == 1


def test_stage_pages_without_refs_changes_nothing(tmp_path: Path):
    """Pages with no asset refs pass through with no downloads and no pruning.

    No reference set means no download plan (the fake client is scripted
    empty -- any fetch would raise), no rewrite, no re-hash, and -- via the
    empty-reference-set guard -- no pruning of whatever already sits in the
    asset dir."""
    source_dir = _source_dir(tmp_path)
    (source_dir / "media").mkdir(parents=True)
    (source_dir / "media" / "kept.jpg").write_bytes(b"keep")
    slug = "intro"
    entry = make_entry(slug=slug, hash="h")
    text = "# Intro\n\nplain page, no images\n"

    new_entries, new_texts, result = media.stage_pages(
        client=_FakeClient([]),
        config=KIMI,
        source_dir=source_dir,
        entries={slug: entry},
        texts={slug: text},
    )

    assert new_texts[slug] == text
    assert new_entries[slug] is entry
    assert (source_dir / "media" / "kept.jpg").exists()
    assert result.assets_written == 0
    assert result.assets_cached == 0
    assert result.pages_rewritten == 0
    assert result.files_pruned == 0


def test_asset_source_config_validation():
    """AssetSourceConfig validates strip_token_depth and raw_base_url."""
    with pytest.raises(ValueError, match="strip_token_depth must be >= 0"):
        media.AssetSourceConfig(
            name="invalid",
            asset_subdir="media",
            ref_prefixes=("https://cdn.example.com/",),
            strip_token_depth=-1,
        )

    with pytest.raises(ValueError, match="raw_base_url must end in '/'"):
        media.AssetSourceConfig(
            name="invalid",
            asset_subdir="media",
            ref_prefixes=("https://cdn.example.com/",),
            raw_base_url="https://cdn.example.com/no-slash",
        )


def test_extract_and_rewrite_refs_with_tokens_and_queries(tmp_path: Path):
    """Media extraction strips deployment tokens, query parameters, and filters by extension."""
    cdn_config = media.AssetSourceConfig(
        name="cdn-source",
        asset_subdir="media",
        ref_prefixes=("https://mintcdn.com/test/",),
        raw_base_url="",
        strip_token_depth=1,
        allowed_extensions=(".png", ".svg"),
    )

    text = (
        '<img src="https://mintcdn.com/test/TOKEN123/images/diagram.svg?fit=max&q=80" alt="diag" />\n'
        '<img src="https://mintcdn.com/test/TOKEN456/images/photo.png#frag" alt="photo" />\n'
        '<video src="https://mintcdn.com/test/TOKEN789/images/demo.mp4?fit=max" />\n'
    )

    refs = media.extract_refs(text, cdn_config)
    assert len(refs) == 2
    assert (
        refs[0].raw
        == "https://mintcdn.com/test/TOKEN123/images/diagram.svg?fit=max&q=80"
    )
    assert refs[0].asset_path == "images/diagram.svg"
    assert (
        refs[0].download_url == "https://mintcdn.com/test/TOKEN123/images/diagram.svg"
    )

    assert refs[1].raw == "https://mintcdn.com/test/TOKEN456/images/photo.png#frag"
    assert refs[1].asset_path == "images/photo.png"
    assert refs[1].download_url == "https://mintcdn.com/test/TOKEN456/images/photo.png"

    source_dir = _source_dir(tmp_path)
    rewritten = media.rewrite_refs(text, cdn_config, source_dir, "guides/page")
    assert '<img src="../media/images/diagram.svg" alt="diag" />' in rewritten
    assert '<img src="../media/images/photo.png" alt="photo" />' in rewritten
    # Unmatched extension .mp4 remains untouched:
    assert (
        '<video src="https://mintcdn.com/test/TOKEN789/images/demo.mp4?fit=max" />'
        in rewritten
    )

    # Test download planning
    downloads = media.plan_downloads({"guides/page": text}, cdn_config, source_dir)
    assert len(downloads) == 2
    assert downloads[0].url == "https://mintcdn.com/test/TOKEN123/images/diagram.svg"
    assert downloads[0].local_path == source_dir / "media" / "images/diagram.svg"
