"""Tests for the mirror orchestration layer (mirror.pipeline).

These cover the guarantees the pipeline itself makes -- fetch carry-forward,
write-only-what-changed (including the missing-file guard), structural
deletion, per-source failure isolation, and ``only`` validation -- using
small fake source objects and a fake HTTP client. No network, no real docs/
tree: anything path-shaped is redirected to ``tmp_path``.
"""

from __future__ import annotations

import concurrent.futures
import json
import os
import sys
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest
from conftest import _FakeClient, _Resp, make_entry
from mirror import config, pipeline, reporting
from mirror.core import diff, fetch
from mirror.core.manifest import Manifest
from mirror.core.page import Page

# --- fakes / helpers (local to this file) ------------------------------------


def _cfg(name: str) -> SimpleNamespace:
    """Minimal stand-in for a source's CONFIG dataclass.

    The pipeline reads exactly four attributes off CONFIG (name, title,
    home_url, generate_whats_new), so a namespace carrying just those is a
    faithful double for the real dataclass.
    """
    return SimpleNamespace(
        name=name,
        title=name.replace("-", " ").title(),
        home_url=f"https://example.com/{name}",
        generate_whats_new=False,
    )


def _fake_source_module(cfg, pages: list | tuple) -> SimpleNamespace:
    """Minimal fake source module: CONFIG + discover, duck-typed like the
    real entries in ``pipeline.SOURCES`` but with caller-supplied ``cfg``
    so tests can use a ``SourceConfig`` with specific attributes. The
    ``pages`` argument is required: callers pass ``()`` to discover zero
    pages so the fetch stage runs empty (see the ``_source`` wrapper, which
    makes that zero-page case its own default)."""
    return SimpleNamespace(CONFIG=cfg, discover=lambda client: list(pages))


def _source(name: str, pages: tuple = ()) -> SimpleNamespace:
    """Build a fake source module from just a name, deriving a minimal CONFIG
    via ``_cfg``. The construction itself lives in ``_fake_source_module`` so
    there is exactly one fake-source factory to keep duck-compatible with the
    real entries in ``pipeline.SOURCES``."""
    return _fake_source_module(_cfg(name), pages)


def _page(
    slug: str,
    source_url: str = "",
    source_md_url: str = "",
    source_id: str = "",
    group: str = "docs",
) -> Page:
    """Build a discovered Page for fetch_pages tests.

    ``Page`` has no ``title`` field (titles are extracted from the fetched
    Markdown and only live on ``manifest.FileEntry``), so this factory
    deliberately does not accept one either -- a ``title`` parameter here
    would be silently dropped and mislead readers into thinking the pipeline
    sees titles at discovery time."""
    return Page(
        slug=slug,
        source_url=source_url or f"https://example/{slug}",
        source_md_url=source_md_url or f"https://example/{slug}.md",
        source_id=source_id or slug,
        group=group,
    )


# --- fetch_pages: carry-forward ----------------------------------------------


@pytest.mark.parametrize(
    "exception_or_resp",
    [
        _Resp(404),
        httpx.ConnectError("connection failed"),
    ],
)
def test_fetch_pages_carries_forward_known_page_on_failure(exception_or_resp):
    """Pin the carry-forward invariant: when a *known* page (present in the
    previous manifest) fails to fetch, its old entry must survive as an
    equivalent copy in ``entries`` -- so the diff sees no removal and the
    file is not deleted -- while staying absent from ``texts`` (nothing new
    to write) and appearing in ``failed``. The copy (dataclasses.replace)
    prevents write_docs mutations from leaking into the old manifest. This
    is what keeps a transient network blip from being recorded as a
    structural change."""
    old_entry = make_entry("guide/intro", hash="oldhash")
    old = Manifest(files={"guide/intro": old_entry})
    entries, texts, failed = pipeline.fetch_pages(
        _FakeClient([exception_or_resp] * 5),
        _source("fake"),
        [_page("guide/intro")],
        old,
    )
    assert failed == ["guide/intro"]
    # The carry-forward entry must be equivalent to the old entry (same
    # slug, hash, title, etc.) but is now a COPY, not the same object --
    # pipeline.fetch_pages uses dataclasses.replace() to avoid mutating
    # the old manifest when write_docs later stamps last_updated.
    assert entries["guide/intro"] == old_entry
    assert entries["guide/intro"] is not old_entry  # defensive copy
    assert "guide/intro" not in texts


def test_fetch_pages_unknown_page_failure_is_not_carried_forward():
    """Pin the flip side of carry-forward: a page that is NOT in the previous
    manifest and fails to fetch gets no protection -- it must land in
    ``failed`` but be absent from both ``entries`` (there is no old entry to
    carry forward, and fabricating one would record a hash for content we
    never saw) and ``texts`` (nothing was downloaded to write). Without this
    asymmetry a brand-new page failing on its first appearance would either
    crash the run or persist a bogus manifest entry."""
    entries, texts, failed = pipeline.fetch_pages(
        _FakeClient([_Resp(404)]),
        _source("fake"),
        [_page("brand-new")],
        Manifest(files={}),
    )
    assert failed == ["brand-new"]
    assert "brand-new" not in entries
    assert "brand-new" not in texts


# --- write_docs ---------------------------------------------------------------


def test_write_docs_skips_unchanged_but_rewrites_missing_file(tmp_path):
    """Pin the "write only what changed" rule *and* the exists() guard on the
    hash-skip path:

    * a page whose hash matches the manifest and whose file exists must be
      left completely untouched -- content, mtime, and the old last_updated
      timestamp all preserved (this is what keeps a no-op run's git diff
      empty);
    * a page whose hash matches but whose .md was deleted from disk must be
      rewritten from the fresh text -- without the guard the mirror would
      keep a manifest entry with no file behind it until the next --force;
    * a genuinely new page is written.
    """
    base = tmp_path / "docs"
    base.mkdir()
    keep = base / "keep.md"
    keep.write_text("on-disk keep text", encoding="utf-8")
    keep_mtime = keep.stat().st_mtime_ns
    # Note: "gone" deliberately has NO file on disk -- that is the scenario.
    same = fetch.content_hash("same text")
    old = Manifest(
        files={
            "keep": make_entry("keep", hash=same, last_updated="2020-01-01T00:00:00Z"),
            "gone": make_entry("gone", hash=same),
        }
    )
    entries = {
        "keep": make_entry("keep", hash=same, last_updated=""),
        "gone": make_entry("gone", hash=same, last_updated=""),
        "new": make_entry("new", hash=fetch.content_hash("new text"), last_updated=""),
    }
    texts = {"keep": "same text", "gone": "same text", "new": "new text"}
    written, deleted = pipeline.write_docs(
        base,
        entries,
        texts,
        old,
        set(entries),
        force=False,
        now_iso="2026-01-01T00:00:00Z",
    )
    # "gone" (missing despite matching hash) and "new" are written; "keep"
    # is skipped; nothing was removed from discovery.
    assert (written, deleted) == (2, 0)
    assert keep.read_text(encoding="utf-8") == "on-disk keep text"
    assert keep.stat().st_mtime_ns == keep_mtime
    assert entries["keep"].last_updated == "2020-01-01T00:00:00Z"
    assert (base / "gone.md").read_text(encoding="utf-8") == "same text"
    assert (base / "new.md").read_text(encoding="utf-8") == "new text"


def test_write_docs_deletes_vanished_slugs(tmp_path):
    """A slug in the previous manifest but absent from this run's discovery
    was removed upstream, so its local file must be deleted. The
    still-discovered sibling must survive untouched (matching hash + existing
    file -> skip path), proving deletion is scoped to vanished slugs only."""
    base = tmp_path / "docs"
    base.mkdir()
    stale = base / "removed.md"
    stale.write_text("stale", encoding="utf-8")
    stays = base / "stays.md"
    stays.write_text("stays text", encoding="utf-8")
    h = fetch.content_hash("stays text")
    old = Manifest(
        files={"removed": make_entry("removed"), "stays": make_entry("stays", hash=h)}
    )
    entries = {"stays": make_entry("stays", hash=h, last_updated="")}
    written, deleted = pipeline.write_docs(
        base,
        entries,
        {"stays": "stays text"},
        old,
        {"stays"},
        force=False,
        now_iso="2026-01-01T00:00:00Z",
    )
    assert (written, deleted) == (0, 1)
    assert not stale.exists()
    assert stays.read_text(encoding="utf-8") == "stays text"


def test_write_docs_removes_empty_parent_dirs_but_never_base(tmp_path):
    """When a nested slug (``sub/dir/page``) vanishes from discovery, its file
    is deleted and the empty-directory cleanup must walk upward: ``sub/dir/``
    and then ``sub/`` are both removed once emptied, but the walk must stop
    at the source base itself -- and a non-empty sibling elsewhere in the
    tree (``other.md`` at the base) must be left completely untouched. Without
    the upward walk, removed upstream subtrees would leave a trail of empty
    directories behind; without the ``parent != base`` stop condition, the
    walk could rmdir the source's own root from under the run."""
    base = tmp_path / "docs"
    (base / "sub" / "dir").mkdir(parents=True)
    nested = base / "sub" / "dir" / "page.md"
    nested.write_text("nested", encoding="utf-8")
    sibling = base / "other.md"
    sibling.write_text("other text", encoding="utf-8")

    h = fetch.content_hash("other text")
    old = Manifest(
        files={
            "sub/dir/page": make_entry("sub/dir/page"),
            "other": make_entry("other", hash=h),
        }
    )
    entries = {"other": make_entry("other", hash=h, last_updated="")}
    written, deleted = pipeline.write_docs(
        base,
        entries,
        {"other": "other text"},
        old,
        {"other"},
        force=False,
        now_iso="2026-01-01T00:00:00Z",
    )
    assert (written, deleted) == (0, 1)
    # The vanished file is gone, and both now-empty ancestor directories
    # (sub/dir/, then sub/) were removed by the upward cleanup walk.
    assert not nested.exists()
    assert not (base / "sub" / "dir").exists()
    assert not (base / "sub").exists()
    # The walk stopped at the source base, and the non-empty sibling -- a
    # still-discovered page whose hash matched and whose file exists -- was
    # neither rewritten nor deleted.
    assert base.is_dir()
    assert sibling.read_text(encoding="utf-8") == "other text"


def test_write_docs_safety_guard_blocks_mass_deletion(tmp_path):
    """When discovery drops more than half of the previously-known pages,
    write_docs must refuse to touch the disk AT ALL: the >50% threshold is
    a safety guard against a transient upstream outage or a broken
    discovery being interpreted as a mass upstream removal. The error
    names the counts. The guard is evaluated before the write loop, so a
    tripped guard must leave every file byte-identical -- including the one
    surviving page, whose freshly-fetched text (different hash) would have
    been written by a loop that ran before the guard."""
    base = tmp_path / "docs"
    base.mkdir()
    originals = {
        "page0": "old page0 text",
        "page1": "page1 text",
        "page2": "page2 text",
        "page3": "page3 text",
    }
    for slug, content in originals.items():
        (base / f"{slug}.md").write_text(content, encoding="utf-8")
    # Old manifest entries carry the hash of what is actually on disk, so
    # the hashes differ exactly for page0 below -- a write loop running
    # BEFORE the guard (the ordering this guard was moved ahead of) would
    # rewrite page0.md with the fresh text, which the assertions detect.
    old = Manifest(
        files={
            slug: make_entry(slug, hash=fetch.content_hash(content))
            for slug, content in originals.items()
        }
    )
    # Only 1 of the 4 known pages is still discovered; its new content has
    # a different hash, so it is a candidate for rewriting once the guard
    # has passed (which it never does here).
    entries = {"page0": make_entry("page0", hash=fetch.content_hash("fresh text"))}
    texts = {"page0": "fresh text"}
    with pytest.raises(RuntimeError, match="Safety guard"):
        pipeline.write_docs(
            base,
            entries,
            texts,
            old,
            discovered_slugs={"page0"},
            force=False,
            now_iso="2026-01-01T00:00:00Z",
        )
    # Nothing was deleted and nothing was written: the guard aborts before
    # any side effect, so every file still holds its original content --
    # page0.md must NOT contain the fresh text, and page1..page3 must still
    # exist.
    for slug, content in originals.items():
        assert (base / f"{slug}.md").read_text(encoding="utf-8") == content


def test_write_docs_safety_guard_allows_exactly_half_deletion(tmp_path):
    """The deletion guard must trip only STRICTLY above 50%: dropping
    exactly half of the known pages (e.g. a section removed upstream) is
    plausible upstream churn and must proceed normally."""
    base = tmp_path / "docs"
    base.mkdir()
    old = Manifest(files={f"page{i}": make_entry(f"page{i}") for i in range(4)})
    for i in range(2, 4):
        (base / f"page{i}.md").write_text("x", encoding="utf-8")
    entries = {f"page{i}": make_entry(f"page{i}") for i in range(2)}
    texts = {f"page{i}": "x" for i in range(2)}
    written, deleted = pipeline.write_docs(
        base,
        entries,
        texts,
        old,
        discovered_slugs={"page0", "page1"},
        force=False,
        now_iso="2026-01-01T00:00:00Z",
    )
    # The two surviving pages have no file on disk, so they are written by
    # the missing-file restore path; the two vanished pages are deleted.
    assert (written, deleted) == (2, 2)
    assert not (base / "page2.md").exists()
    assert not (base / "page3.md").exists()


def test_write_docs_force_bypasses_safety_guard(tmp_path):
    """``force=True`` must bypass the >50% deletion safety guard: the
    operator explicitly accepted the risk of a mass removal (e.g. after an
    upstream restructure), so the vanished files are deleted normally."""
    base = tmp_path / "docs"
    base.mkdir()
    old = Manifest(files={f"page{i}": make_entry(f"page{i}") for i in range(4)})
    for i in range(4):
        (base / f"page{i}.md").write_text("x", encoding="utf-8")
    entries = {"page0": make_entry("page0")}
    texts = {"page0": "x"}
    written, deleted = pipeline.write_docs(
        base,
        entries,
        texts,
        old,
        discovered_slugs={"page0"},
        force=True,
        now_iso="2026-01-01T00:00:00Z",
    )
    # page0 is (re)written -- force bypasses the hash skip too -- and the
    # three vanished pages are deleted without the guard firing.
    assert (written, deleted) == (1, 3)
    assert not (base / "page1.md").exists()


def test_write_docs_preserves_sibling_nested_directory_when_another_is_emptied(
    tmp_path,
):
    """When a deeply nested slug vanishes and its ancestor directories are
    emptied and removed by the upward cleanup walk, a SIBLING nested
    directory tree that still contains pages must survive untouched.

    The cleanup walk stops at the first non-empty directory it encounters
    on the way up -- but that "first non-empty" could be a sibling branch
    at ANY level, not just a file at the source base. This test sets up
    TWO separate nested trees (``sub-a/...`` and ``sub-b/...``), deletes
    only one of them, and asserts that the other survives with its file
    content intact while the deleted tree's parent directories are cleaned
    up all the way to the branch point.

    Without this guard the cleanup walk could over-delete: if the walk
    logic blindly walked to the base without checking that every removed
    directory was TRULY empty (i.e. also had no sibling branches), it
    could rmdir a shared ancestor and corrupt the surviving sibling tree.
    The ``rmdir()`` call itself is safe (it raises OSError on a non-empty
    directory, caught by the except), but this test proves the overall
    behaviour is correct: the surviving sibling is never touched, its
    ancestor directories all remain, and only the vanished tree's empty
    ancestors are removed."""
    base = tmp_path / "docs"

    # Given: two separate nested trees -- sub-a/dir/page.md (will be
    # deleted) and sub-b/other/page.md (will survive) -- plus a base-level
    # file, and an old manifest that still records all three pages.
    (base / "sub-a" / "dir").mkdir(parents=True)
    (base / "sub-b" / "other").mkdir(parents=True)

    deleted_file = base / "sub-a" / "dir" / "page.md"
    deleted_file.write_text("deleted", encoding="utf-8")

    surviving_file = base / "sub-b" / "other" / "page.md"
    surviving_file.write_text("surviving text", encoding="utf-8")

    # Also a file at the base level so the cleanup definitely does not
    # reach the source base (an additional protection).
    base_file = base / "root-page.md"
    base_file.write_text("root text", encoding="utf-8")

    h_root = fetch.content_hash("root text")
    h_surv = fetch.content_hash("surviving text")

    old = Manifest(
        files={
            "sub-a/dir/page": make_entry("sub-a/dir/page"),
            "sub-b/other/page": make_entry("sub-b/other/page", hash=h_surv),
            "root-page": make_entry("root-page", hash=h_root),
        }
    )
    # Only "sub-b/other/page" and "root-page" are still discovered --
    # "sub-a/dir/page" vanished upstream.
    entries = {
        "sub-b/other/page": make_entry(
            "sub-b/other/page", hash=h_surv, last_updated=""
        ),
        "root-page": make_entry("root-page", hash=h_root, last_updated=""),
    }
    texts = {"sub-b/other/page": "surviving text", "root-page": "root text"}

    # When: write_docs runs with "sub-a/dir/page" vanished upstream.
    written, deleted = pipeline.write_docs(
        base,
        entries,
        texts,
        old,
        set(entries),
        force=False,
        now_iso="2026-01-01T00:00:00Z",
    )

    # Then: exactly one file is deleted, the vanished tree's empty ancestors
    # are cleaned up, and the sibling tree plus base-level file survive.
    assert (written, deleted) == (0, 1)

    # The vanished file and its empty ancestors (sub-a/dir/, then sub-a/)
    # are gone. The directory walk should clean them up.
    assert not deleted_file.exists()
    assert not (base / "sub-a" / "dir").exists()
    assert not (base / "sub-a").exists()

    # The surviving sibling tree is completely untouched: its file still
    # exists with the original content, and BOTH ancestor directories
    # (sub-b/other/ and sub-b/) remain.
    assert surviving_file.read_text(encoding="utf-8") == "surviving text"
    assert (base / "sub-b" / "other").is_dir()
    assert (base / "sub-b").is_dir()

    # The base-level sibling still exists and the source base itself was
    # never reached by the cleanup walk.
    assert base_file.read_text(encoding="utf-8") == "root text"
    assert base.is_dir()


# --- run(): orchestration guarantees ------------------------------------------


def test_run_continues_after_one_source_fails(isolated_docs, monkeypatch, capsys):
    """Pin the per-source failure isolation guarantee: a source whose
    discover() raises must not abort the run -- the failure is reported to
    stderr, the remaining sources still mirror to completion, and the exit
    code is 1 (a partial run must not look successful). The docs tree and the
    source registry are redirected to fakes so the test touches neither the
    real docs/ nor the network (the healthy source discovers zero pages, so
    the shared real HTTP client never issues a request)."""

    def _boom(client):
        raise RuntimeError("discovery exploded")

    bad = SimpleNamespace(CONFIG=_cfg("bad-source"), discover=_boom)
    good = _source("good-source")
    monkeypatch.setattr(pipeline, "SOURCES", [bad, good])

    assert pipeline.run() == 1
    # The healthy source ran to completion and persisted its baseline.
    assert (isolated_docs / "good-source" / "manifest.json").exists()
    # The failure was loud on stderr with the exact log message structure,
    # not silently absorbed by the isolation.  Checking the full prefix
    # (``!! [bad-source] source failed:``) rather than a bare substring
    # match proves the error was formatted by ``reporting.source_error``
    # (which uses the ``!!`` marker for whole-source failures) and not by
    # some other stderr path that happens to include the source name.
    err = capsys.readouterr().err
    assert "!! [bad-source] source failed:" in err


def test_run_continues_after_one_source_fails_with_keyerror(
    isolated_docs, monkeypatch, capsys
):
    """Pin the per-source failure isolation guarantee for non-RuntimeError exceptions
    (e.g. KeyError, AttributeError). The pipeline must catch Exception generically,
    so ANY source crash is isolated and remaining sources still mirror to completion."""

    def _boom_keyerror(client):
        raise KeyError("missing-key")

    bad = SimpleNamespace(CONFIG=_cfg("bad-source-keyerror"), discover=_boom_keyerror)
    good = _source("good-source")
    monkeypatch.setattr(pipeline, "SOURCES", [bad, good])

    assert pipeline.run() == 1
    assert (isolated_docs / "good-source" / "manifest.json").exists()
    err = capsys.readouterr().err
    assert "!! [bad-source-keyerror] source failed:" in err


def test_run_isolates_top_index_write_failure(isolated_docs, monkeypatch, capsys):
    """Pin the top-index failure isolation guarantee: an OSError escaping
    ``write_top_index()`` must not propagate out of ``run()`` as an unhandled
    traceback. Instead the failure is reported as a one-line ``warning:`` on
    stderr and the exit code is 1 -- a stale index must not look like a
    fully successful run. The docs tree and the source registry are
    redirected to fakes so the test touches neither the real docs/ nor the
    network (the source discovers zero pages, so the shared real HTTP client
    never issues a request)."""

    def _boom():
        raise OSError("docs/README.md is not writable")

    monkeypatch.setattr(pipeline, "SOURCES", [_source("good-source")])
    monkeypatch.setattr(pipeline, "write_top_index", _boom)

    assert pipeline.run() == 1
    # The source itself mirrored to completion; only the index write failed.
    assert (isolated_docs / "good-source" / "manifest.json").exists()
    # The failure surfaced through reporting.warning (the "warning:" prefix
    # with the leading two-space indentation), not as a "!!" source failure
    # or a raw traceback.
    err = capsys.readouterr().err
    assert "  warning: failed to write top index:" in err
    assert "Traceback" not in err


def test_run_isolates_root_readme_update_failure(isolated_docs, monkeypatch, capsys):
    """An OSError or UnicodeDecodeError escaping ``update_root_readme()`` must not
    propagate as an unhandled traceback. Instead the failure is logged as a
    warning on stderr and the run exits with code 1.
    """
    monkeypatch.setattr(pipeline, "SOURCES", [_source("good-source")])

    def _boom():
        raise UnicodeDecodeError("utf-8", b"\xff\xfe", 0, 1, "invalid start byte")

    monkeypatch.setattr(pipeline, "update_root_readme", _boom)

    assert pipeline.run() == 1
    assert (isolated_docs / "good-source" / "manifest.json").exists()
    err = capsys.readouterr().err
    assert "  warning: failed to update root readme:" in err
    assert "Traceback" not in err


def test_run_rejects_unknown_only():
    """Defense in depth below the CLI's argparse ``choices=``: a programmatic
    caller passing an unknown ``only`` name must get a loud ValueError
    instead of a silent no-op run that matches nothing. Validation happens
    before the HTTP client is built, so this test needs no fixtures."""
    with pytest.raises(ValueError, match="nope"):
        pipeline.run(only="nope")


# --- force=True path ----------------------------------------------------------


def test_write_docs_force_rewrites_even_when_hash_matches(tmp_path):
    """``force=True`` must bypass the hash-equality skip: a page whose content
    hash matches the previous manifest AND whose file exists on disk must still
    be rewritten when force is set. This is how --force recovers a corrupted
    local tree without needing to manually delete files first.

    The rewrite is proven by content, not by the filesystem clock: the
    on-disk file deliberately holds text that differs from the fetched text,
    so the final read-back equality can only hold if write_docs actually
    wrote the file (on the hash-skip path the old bytes would survive).
    An mtime assertion (``st_mtime_ns != old_mtime``) is deliberately NOT
    used: on filesystems with coarse mtime granularity the initial write
    and the forced rewrite can land in the same tick, so such an assertion
    would pass or fail by clock luck -- a latent flake, not a signal."""
    base = tmp_path / "docs"
    base.mkdir()
    keep = base / "keep.md"
    keep.write_text("forced overwrite will replace this", encoding="utf-8")
    h = fetch.content_hash("fresh text")
    old = Manifest(
        files={"keep": make_entry("keep", hash=h, last_updated="2020-01-01T00:00:00Z")}
    )
    entries = {"keep": make_entry("keep", hash=h, last_updated="")}
    written, _deleted = pipeline.write_docs(
        base,
        entries,
        {"keep": "fresh text"},
        old,
        {"keep"},
        force=True,
        now_iso="2026-01-01T00:00:00Z",
    )
    assert written == 1
    assert keep.read_text(encoding="utf-8") == "fresh text"


def test_write_docs_uses_pid_for_atomic_temp_file(tmp_path, monkeypatch):
    """The atomic file write must stage to a .tmp file that incorporates
    os.getpid() in its name to prevent collisions during concurrent writes."""
    base = tmp_path / "docs"
    base.mkdir()
    entries = {"page": make_entry("page", hash=fetch.content_hash("text"))}
    texts = {"page": "text"}

    # Record every Path.write_text target without touching the filesystem.
    # Both Path methods are stubbed via monkeypatch (the fixture used by the
    # rest of the suite), which also guarantees the originals are restored
    # after the test; stubbing ``replace`` as well keeps the final rename
    # from failing on the never-written temp file.
    write_text_calls: list[Path] = []

    def fake_write_text(self, *args, **kwargs):
        write_text_calls.append(self)

    monkeypatch.setattr(Path, "write_text", fake_write_text)
    monkeypatch.setattr(Path, "replace", lambda self, target: None)

    pipeline.write_docs(
        base,
        entries,
        texts,
        old=None,
        discovered_slugs={"page"},
        force=False,
        now_iso="2025-01-01T12:00:00Z",
    )

    assert len(write_text_calls) == 1
    tmp_path_used = write_text_calls[0]
    assert tmp_path_used.name.endswith(".tmp")
    assert f".{os.getpid()}_" in tmp_path_used.name


def test_summary_force_run_with_unchanged_content_reports_no_changes(
    isolated_docs, capsys
):
    """A --force run against unchanged upstream content rewrites files
    (``written > 0``) but produces an empty structural diff. The per-source
    summary must key its "no changes detected" wording off the empty diff
    alone -- otherwise such a run would print a meaningless
    ``changes: +0 ~0 >0 -0`` line, falsely implying something structural
    happened. The written count on the summary's first line already conveys
    that files were (re)written."""
    src = SimpleNamespace(
        CONFIG=SimpleNamespace(
            name="force-src",
            title="Force Src",
            home_url="https://x",
            generate_whats_new=False,
        ),
        discover=lambda client: [
            Page(
                slug="pg",
                source_url="https://x/pg",
                source_md_url="https://x/pg.md",
                source_id="pg",
            )
        ],
    )
    text = "# Page\n\ncontent with enough bytes to clear minimum checks\n" * 10
    # Baseline run, so the second run has a previous manifest to diff against.
    pipeline.run_source(
        src, _FakeClient([_Resp(200, text)]), force=False, dry_run=False
    )
    capsys.readouterr()  # flush baseline-run output

    ret = pipeline.run_source(
        src, _FakeClient([_Resp(200, text)]), force=True, dry_run=False
    )
    assert ret is not None
    assert ret.written == 1  # file rewritten despite identical content
    out = capsys.readouterr().out
    assert "no changes detected" in out
    assert "changes: +0" not in out


# --- dry_run path -------------------------------------------------------------


def test_run_dry_run_does_not_write(isolated_docs, monkeypatch, capsys):
    """``dry_run=True`` must discover pages and report them, but write nothing
    to disk: the manifest and any Markdown files must not be created. The exit
    code must be 0 (nothing failed, nothing was attempted)."""
    good = _source("dry-source", pages=(_page("a"), _page("b")))
    monkeypatch.setattr(pipeline, "SOURCES", [good])
    assert pipeline.run(dry_run=True) == 0
    captured = capsys.readouterr()
    assert "discovered 2 page(s)" in captured.out
    assert not (isolated_docs / "dry-source" / "manifest.json").exists()
    assert not (isolated_docs / "dry-source" / "a.md").exists()
    assert not (isolated_docs / "README.md").exists()


def test_run_dry_run_announces_missing_manifest(isolated_docs, monkeypatch, capsys):
    """A dry run against a source with NO previous manifest must say so
    explicitly: without the notice, a baseline run's output is
    indistinguishable from a run whose structural diff simply found nothing
    new, and the operator cannot tell "first run, everything will be
    created" from "no drift detected". Once a manifest exists (even an
    empty one), the notice must disappear and the structural diff lines
    take over."""
    src = _source("fresh-source", pages=(_page("a"),))
    monkeypatch.setattr(pipeline, "SOURCES", [src])

    # Baseline: no manifest on disk -> the notice is printed.
    assert pipeline.run(dry_run=True) == 0
    out = capsys.readouterr().out
    assert "no previous manifest found" in out

    # With a manifest on disk (even an empty one), the notice must NOT
    # appear -- the structural diff output takes over instead.
    from mirror.core import manifest as mf_mod

    base = isolated_docs / "fresh-source"
    base.mkdir(parents=True)
    mf_mod.save(Manifest(files={}), base / "manifest.json")
    assert pipeline.run(dry_run=True) == 0
    out = capsys.readouterr().out
    assert "no previous manifest found" not in out
    assert "structurally new" in out  # "a" is new vs the empty manifest


# --- zero-page discovery ------------------------------------------------------


def test_run_zero_page_source_creates_empty_manifest(isolated_docs, monkeypatch):
    """When a source discovers zero pages, the pipeline must produce an empty
    manifest (zero entries, no errors) rather than crash or skip the source.
    An empty manifest on disk is the ground truth that the upstream currently
    publishes nothing -- it prevents the next run from treating the source as
    brand-new (baseline)."""
    empty = _source("empty-source")
    monkeypatch.setattr(pipeline, "SOURCES", [empty])
    assert pipeline.run() == 0
    mp = isolated_docs / "empty-source" / "manifest.json"
    assert mp.exists()
    data = json.loads(mp.read_text(encoding="utf-8"))
    assert data["files"] == {}
    assert data["fetch_metadata"]["total_pages_discovered"] == 0


# --- write_top_index ----------------------------------------------------------


def test_write_top_index(isolated_docs, monkeypatch):
    """``write_top_index()`` must generate ``docs/README.md`` with a row for
    every registered source, using each source's on-disk manifest for the page
    count and last-updated timestamp."""
    src_a = SimpleNamespace(
        CONFIG=SimpleNamespace(
            name="source-a",
            title="Source A",
            home_url="https://a",
            generate_whats_new=False,
        )
    )
    src_b = SimpleNamespace(
        CONFIG=SimpleNamespace(
            name="source-b",
            title="Source B",
            home_url="https://b",
            generate_whats_new=True,
        )
    )
    monkeypatch.setattr(pipeline, "SOURCES", [src_a, src_b])

    docs_dir = isolated_docs
    for name, count in [("source-a", 3), ("source-b", 5)]:
        base = docs_dir / name
        base.mkdir(parents=True)
        manifest_data = {
            "last_updated": "2026-01-15T00:00:00Z",
            "files": {f"page{i}": {} for i in range(count)},
        }
        (base / "manifest.json").write_text(json.dumps(manifest_data), encoding="utf-8")

    pipeline.write_top_index()

    text = (isolated_docs / "README.md").read_text(encoding="utf-8")
    assert "**Total pages mirrored:** 8" in text
    assert "| [Source A](./source-a/) | — | 3 | 2026-01-15T00:00:00Z | no |" in text
    assert "| [Source B](./source-b/) | — | 5 | 2026-01-15T00:00:00Z | yes |" in text


# --- whats-new integration ----------------------------------------------------


def test_whats_new_integration(isolated_docs):
    """A source with ``generate_whats_new=True`` must produce a whats-new file
    when the run has a non-empty diff vs the previous manifest.  On a baseline
    run (no previous manifest) no whats-new file is written."""
    # Given: a source with generate_whats_new=True and a previous manifest
    # recording its only page under an old hash, so re-mirroring produces a
    # real diff.
    base = isolated_docs / "test-wn"
    base.mkdir(parents=True)
    old_manifest = Manifest(
        files={
            "pg": make_entry(
                "pg",
                title="Pg",
                group="root",
                source_url="https://x/pg",
                source_md_url="https://x/pg.md",
                hash="oldhash",
                last_updated="2026-01-01T00:00:00Z",
            )
        }
    )
    (base / "manifest.json").write_text(
        json.dumps(old_manifest.to_dict()), encoding="utf-8"
    )

    src = SimpleNamespace(
        CONFIG=SimpleNamespace(
            name="test-wn",
            title="Test WN",
            home_url="https://x",
            generate_whats_new=True,
        ),
        discover=lambda client: [
            Page(
                slug="pg",
                source_url="https://x/pg",
                source_md_url="https://x/pg.md",
                source_id="pg",
            )
        ],
    )

    # When: the source is mirrored -- the page's content no longer matches
    # the hash stored in the previous manifest.
    text = "# Page\n\ncontent with enough bytes to clear the minimum check\n" * 10
    client = _FakeClient([_Resp(200, text)])
    ret = pipeline.run_source(src, client, force=False, dry_run=False)
    assert ret is not None
    assert ret.name == "test-wn"

    # Then: a whats-new file exists (non-empty diff + old is not None).
    # Only ``.md`` files are counted: the ``.lock`` file is a persistent mutex
    # sibling created by ``write_entry`` that should be ignored here.
    wn_dir = base / "whats-new"
    wn_files = sorted(p for p in wn_dir.iterdir() if p.suffix == ".md")
    assert len(wn_files) == 1
    content = wn_files[0].read_text(encoding="utf-8")
    assert "What's New — Test WN" in content

    # Given (baseline phase): the previous manifest is removed, so the next
    # run is a baseline with old=None.
    (base / "manifest.json").unlink()
    # When: the same source is mirrored again.
    client2 = _FakeClient([_Resp(200, text)])
    pipeline.run_source(src, client2, force=False, dry_run=False)
    # Then: a baseline run produces no whats-new file -- the directory is
    # unchanged.
    assert sorted(p for p in wn_dir.iterdir() if p.suffix == ".md") == wn_files


def test_whats_new_skipped_when_previous_manifest_has_zero_files(isolated_docs):
    """A baseline run where EVERY fetch fails still saves a (zero-file)
    manifest, so the source is not re-baselined forever. The next, recovered
    run must treat that empty manifest as a baseline for whats-new purposes:
    without that, the recovered run would see a non-None previous manifest
    and emit a giant "everything is new" entry that carries no signal."""
    base = isolated_docs / "test-wn-empty"
    base.mkdir(parents=True)
    src = SimpleNamespace(
        CONFIG=SimpleNamespace(
            name="test-wn-empty",
            title="Test WN Empty",
            home_url="https://x",
            generate_whats_new=True,
        ),
        discover=lambda client: [
            Page(
                slug="pg",
                source_url="https://x/pg",
                source_md_url="https://x/pg.md",
                source_id="pg",
            )
        ],
    )

    # Run 1 (baseline): the only fetch fails, and a page failing on its first
    # appearance is not carried forward -- so an empty manifest is saved.
    ret1 = pipeline.run_source(
        src, _FakeClient([_Resp(404)]), force=False, dry_run=False
    )
    assert ret1 is not None
    assert ret1.mirrored == 0
    saved = json.loads((base / "manifest.json").read_text(encoding="utf-8"))
    assert saved["files"] == {}

    # Run 2 (recovered): the fetch now succeeds. The zero-file previous
    # manifest must count as a baseline, so NO whats-new entry is written --
    # even though the diff is non-empty (one added page).
    text = "# Page\n\ncontent with enough bytes to clear the minimum check\n" * 10
    ret2 = pipeline.run_source(
        src, _FakeClient([_Resp(200, text)]), force=False, dry_run=False
    )
    assert ret2 is not None
    assert ret2.whats_new_path is None
    assert not (base / "whats-new").exists()
    # ...while the page itself was mirrored and recorded normally.
    saved2 = json.loads((base / "manifest.json").read_text(encoding="utf-8"))
    assert set(saved2["files"]) == {"pg"}


# --- no-op invariant ----------------------------------------------------------


def test_noop_invariant(isolated_docs, monkeypatch):
    """A second run against an unchanged source must leave the manifest
    untouched — this is what keeps a no-op run's git diff empty.

    The invariant is verified by mocking ``manifest.save`` and asserting it
    is NOT called on the second run (the diff is empty, so nothing changed).
    This is independent of filesystem timestamp granularity: on fast SSDs or
    filesystems with coarse mtime resolution, two consecutive writes to the
    same file can land in the same nanosecond tick and produce identical
    ``st_mtime_ns`` values, making an mtime-based assertion pass by luck
    rather than by correctness.  Asserting that ``manifest.save`` is never
    called proves the invariant directly: unchanged content produces no
    rewrite, regardless of what the clock says.
    """
    # Given: a single-page source mirrored once, establishing a baseline
    # manifest whose bytes are recorded for later comparison.
    src = SimpleNamespace(
        CONFIG=SimpleNamespace(
            name="noop",
            title="Noop Source",
            home_url="https://x",
            generate_whats_new=False,
        ),
        discover=lambda client: [
            Page(
                slug="pg",
                source_url="https://x/pg",
                source_md_url="https://x/pg.md",
                source_id="pg",
            )
        ],
    )

    text = "# Page\n\ncontent with enough bytes to clear minimum checks\n" * 10
    client = _FakeClient([_Resp(200, text)])
    ret1 = pipeline.run_source(src, client, force=False, dry_run=False)
    assert ret1 is not None
    assert ret1.discovered == 1

    mp = isolated_docs / "noop" / "manifest.json"
    first_bytes = mp.read_bytes()

    # When: ``manifest.save`` is wrapped with a call tracker and the source
    # is mirrored a second time with a fresh client returning the same
    # response.  Mocking ``manifest.save`` lets us assert it is never called
    # (empty diff → nothing to persist), which proves the no-op invariant
    # independently of filesystem mtime granularity.
    import mirror.core.manifest as mf_mod

    save_called = False
    # Keep the real ``save`` in a plain local variable so the wrapper below
    # can delegate to it. Using a local (rather than stashing the function on
    # the imported module's namespace) leaves the module untouched: the
    # temporary replacement is installed and removed exclusively by
    # ``monkeypatch``, which restores the original attribute after the test.
    original_save = mf_mod.save

    def _track_save(*args, **kwargs):
        nonlocal save_called
        save_called = True
        # Call the real save so the on-disk manifest bytes test below still
        # passes (the manifest stays byte-identical after the first run).
        return original_save(*args, **kwargs)

    monkeypatch.setattr(mf_mod, "save", _track_save)

    client2 = _FakeClient([_Resp(200, text)])
    ret2 = pipeline.run_source(src, client2, force=False, dry_run=False)
    assert ret2 is not None
    # Then: save was never called (empty diff → nothing to persist) and the
    # on-disk manifest is byte-identical to the baseline.
    assert not save_called, (
        "manifest.save must not be called on a no-op run "
        "(empty diff → no manifest changes to persist)"
    )
    second_bytes = mp.read_bytes()
    assert first_bytes == second_bytes


# --- fetch_markdown dispatch --------------------------------------------------


def test_fetch_markdown_preferred_over_fetch_validated():
    """When a source module exposes ``fetch_markdown``, ``fetch_pages`` must
    call it instead of the default ``fetch_validated`` path."""
    called_with: list[str] = []

    def custom_fetch(client, page):
        called_with.append(page.slug)
        return ("# Custom\n\ncontent\n" * 10, "dummyhash")

    src = SimpleNamespace(fetch_markdown=custom_fetch)
    page = Page(
        slug="test",
        source_url="https://x/test",
        source_md_url="https://x/test.md",
        source_id="test",
    )
    _entries, texts, _failed = pipeline.fetch_pages(
        _FakeClient([]), src, [page], Manifest(files={})
    )
    assert called_with == ["test"]
    assert "test" in texts


def test_fetch_pages_falls_back_to_fetch_validated():
    """When a source lacks ``fetch_markdown``, ``fetch_pages`` must fall back
    to the generic ``fetch.fetch_validated`` path."""
    src = SimpleNamespace()  # no fetch_markdown attribute
    page = Page(
        slug="test",
        source_url="https://x/test",
        source_md_url="https://x/test.md",
        source_id="test",
    )
    client = _FakeClient([_Resp(200, "# Valid\n\ncontent\n" * 10)])
    _entries, texts, _failed = pipeline.fetch_pages(
        client, src, [page], Manifest(files={})
    )
    assert "test" in texts


# --- rate-limiting delay between pages ---------------------------------------


def test_rate_limit_delay_between_pages(monkeypatch):
    """``fetch_pages`` must sleep for ``config.RATE_LIMIT_DELAY`` BETWEEN page
    fetches but never before the first page nor after the last — so N pages
    produce exactly N-1 sleep calls. Without this invariant the very first
    page would incur an unnecessary delay and the last page's delay would
    serve no purpose."""
    sleeps: list[float] = []
    monkeypatch.setattr(fetch.time, "sleep", sleeps.append)

    pages = [
        Page(
            slug="a",
            source_url="https://x/a",
            source_md_url="https://x/a.md",
            source_id="a",
        ),
        Page(
            slug="b",
            source_url="https://x/b",
            source_md_url="https://x/b.md",
            source_id="b",
        ),
        Page(
            slug="c",
            source_url="https://x/c",
            source_md_url="https://x/c.md",
            source_id="c",
        ),
    ]

    text = "# Valid\n\ncontent here with enough bytes to clear the minimum\n" * 10
    client = _FakeClient([_Resp(200, text), _Resp(200, text), _Resp(200, text)])
    src = SimpleNamespace()  # no fetch_markdown → falls back to fetch_validated

    _entries, texts, failed = pipeline.fetch_pages(client, src, pages, None)

    assert len(sleeps) == 2  # 3 pages → 2 delays
    assert sleeps[0] == pytest.approx(config.RATE_LIMIT_DELAY, rel=1e-2)
    assert sleeps[1] == pytest.approx(config.RATE_LIMIT_DELAY * 2, rel=1e-2)
    assert len(texts) == 3  # all pages fetched successfully
    assert not failed


# --- run_source safety guards -------------------------------------------------


def test_run_source_rejects_duplicate_slugs(isolated_docs):
    """run_source raises ValueError when discover() returns duplicate slugs.
    Without this guard two pages would collapse onto one manifest key and one
    file on disk, silently mirroring only the last-fetched of the pair."""
    from mirror.sources.base import SourceConfig

    cfg = SourceConfig(
        name="test-src",
        title="Test",
        home_url="https://example.com",
        generate_whats_new=False,
    )
    fake_source = _fake_source_module(
        cfg,
        [_page("a"), _page("a"), _page("b")],
    )

    # The match must pin the FULL message shape, not just the "Duplicate
    # slugs" prefix: the whole point of the Counter-based counting in
    # run_source is to NAME the offending slugs (and the source) in the error
    # so the operator can find the bad discovery output without reproducing
    # the run. A prefix-only match would still pass if a refactor dropped the
    # slug list from the message, silently degrading the error back to an
    # unactionable bare "Duplicate slugs". The "$" anchor additionally
    # guarantees that "a" is the complete slug list, not a prefix of one.
    with pytest.raises(ValueError, match=r"Duplicate slugs in source 'test-src': a$"):
        pipeline.run_source(fake_source, _FakeClient([]), force=False, dry_run=False)


def test_run_source_runs_media_stage_between_fetch_and_diff(isolated_docs, monkeypatch):
    """run_source invokes media.stage_pages for sources that declare MEDIA.

    The wiring order matters: the stage must receive the entries/texts
    produced by fetch_pages (so carried-forward texts are included and the
    rewrite stays idempotent) and its rewritten output must be what the diff
    and manifest consume. A spy double checks both halves -- the call
    receives the freshly fetched page, and the media config passed is exactly
    the source's ``MEDIA`` attribute (the getattr discovery mirrors the
    fetch_markdown hook convention)."""
    from mirror.core.media import MediaStageResult
    from mirror.sources.base import SourceConfig

    cfg = SourceConfig(
        name="test-src",
        title="Test",
        home_url="https://example.com",
        generate_whats_new=False,
    )
    body = "# Title\n\nbody text here with enough content to pass validation\n" * 5
    source = _fake_source_module(cfg, [_page("a")])
    source.MEDIA = "media-config-sentinel"

    captured: dict[str, object] = {}

    def spy_stage_pages(client, media_config, source_dir, entries, texts):
        captured["config"] = media_config
        captured["entry_slugs"] = list(entries)
        captured["texts"] = dict(texts)
        return entries, texts, MediaStageResult(assets_written=0, assets_cached=0)

    monkeypatch.setattr(pipeline.media, "stage_pages", spy_stage_pages)

    pipeline.run_source(
        source, _FakeClient([_Resp(200, body)]), force=False, dry_run=False
    )

    # The media config is forwarded verbatim (the pipeline only discovers it),
    # and the entries handed to the stage are the post-fetch entries -- keyed
    # by the fetched slug, carrying the fetched text, not an empty pre-fetch
    # state.
    assert captured["config"] == "media-config-sentinel"
    assert captured["entry_slugs"] == ["a"]
    assert captured["texts"]["a"].startswith("# Title")


def test_path_traversal_slug_rejected_at_construction():
    """A slug containing '..' path segments raises ValueError at construction.

    Slug safety is enforced single-layer by design: ``core.page.Page``
    validates its slug in ``__post_init__`` (raising "must not contain '..'
    path segments"), so an unsafe discovery fails loudly the moment the
    source adapter builds the Page and can never reach the pipeline's write
    stage -- the pipeline itself deliberately does not re-check what Page
    already guarantees. This test exercises that delegated slug-safety
    check directly: constructing a Page with a traversal slug is the
    expected failure point, so it is the only call inside the ``raises``
    block.
    """
    with pytest.raises(ValueError, match=r"path segments|path traversal"):
        _page("../evil")


def test_backslash_slug_rejected_at_construction():
    """A slug containing a backslash raises ValueError at construction.

    A backslash is a path separator on Windows, so a slug like
    ``"..\\evil"`` would slip past a POSIX-style ``..`` check (which splits
    on ``/``) and still escape ``docs/`` there. The rejection happens at
    construction time: a backslash is outside ``core.page.Page``'s slug
    character alphabet, so ``__post_init__`` raises before the pipeline ever
    sees the page. As with the '..' guard, the pipeline relies on that Page
    invariant instead of re-checking. This test exercises that delegated
    slug-safety check directly: constructing a Page with a backslash slug is
    the expected failure point, so it is the only call inside the ``raises``
    block.
    """
    with pytest.raises(ValueError, match=r"backslash|characters that would break"):
        _page("..\\evil")


def test_run_source_aborts_on_zero_pages_with_existing_manifest(
    isolated_docs,
):
    """run_source raises RuntimeError when discovery returns 0 pages but a
    non-empty manifest already exists."""
    from mirror.core import manifest as mf_mod
    from mirror.sources.base import SourceConfig

    cfg = SourceConfig(
        name="test-src",
        title="Test",
        home_url="https://example.com",
        generate_whats_new=False,
    )
    fake_source = _fake_source_module(cfg, [])

    # Pre-seed a manifest on disk so 'old' is non-empty.
    base = isolated_docs / cfg.name
    base.mkdir(parents=True)
    old_mf = Manifest(
        files={
            "some-page": make_entry(
                "some-page",
                title="Old",
                group="root",
                hash="deadbeef",
                last_updated="2026-01-01T00:00:00Z",
            )
        }
    )
    mf_mod.save(old_mf, base / "manifest.json")

    with pytest.raises(RuntimeError, match="discovered 0 pages"):
        pipeline.run_source(fake_source, _FakeClient([]), force=False, dry_run=False)


def test_run_source_dry_run_tolerates_zero_pages_with_existing_manifest(
    isolated_docs,
):
    """A dry run must NOT trip the zero-page guard: it writes nothing, so the
    on-disk state the guard protects is never at risk -- and dry-run mode is
    exactly the diagnostic tool an operator reaches for when an upstream
    outage is suspected. With a non-empty manifest on disk and zero
    discovered pages, the dry run must complete (returning None, as dry runs
    do) and leave the manifest byte-identical."""
    from mirror.core import manifest as mf_mod
    from mirror.sources.base import SourceConfig

    cfg = SourceConfig(
        name="test-src",
        title="Test",
        home_url="https://example.com",
        generate_whats_new=False,
    )
    fake_source = _fake_source_module(cfg, [])

    # Pre-seed a non-empty manifest on disk: the exact setup that makes a
    # real (non-dry) run abort with the zero-page guard.
    base = isolated_docs / cfg.name
    base.mkdir(parents=True)
    old_mf = Manifest(
        files={
            "some-page": make_entry(
                "some-page",
                title="Old",
                group="root",
                hash="deadbeef",
                last_updated="2026-01-01T00:00:00Z",
            )
        }
    )
    mf_mod.save(old_mf, base / "manifest.json")
    before = (base / "manifest.json").read_bytes()

    # Must not raise, must return None (the dry-run contract), and must not
    # have written anything -- the manifest is byte-identical afterwards.
    result = pipeline.run_source(
        fake_source, _FakeClient([]), force=False, dry_run=True
    )
    assert result is None
    assert (base / "manifest.json").read_bytes() == before


# --- write_top_index fallback behaviour ---------------------------------------


def test_write_top_index_missing_and_corrupt_manifests(
    isolated_docs,
    monkeypatch,
    capsys,
):
    """write_top_index handles missing and corrupt manifests gracefully."""
    from mirror.sources.base import SourceConfig

    # Given: one fake source module (discovers zero pages) installed as the
    # only entry in pipeline.SOURCES.
    cfg = SourceConfig(
        name="good-src",
        title="Good Source",
        home_url="https://example.com",
        generate_whats_new=False,
    )
    fake = _fake_source_module(cfg, [])
    monkeypatch.setattr(pipeline, "SOURCES", [fake])

    # Given (scenario 1): no manifest on disk at all.
    # When: write_top_index runs without it.
    pipeline.write_top_index()
    capsys.readouterr()  # flush
    index_text = isolated_docs.joinpath("README.md").read_text(encoding="utf-8")
    # Then: the source is listed with the em-dash placeholder for its date.
    assert "Good Source" in index_text
    assert "—" in index_text  # em-dash placeholder for date

    # Given (scenario 2): a corrupt manifest (valid JSON but a list, not a
    # dict).
    base = isolated_docs / cfg.name
    base.mkdir(parents=True, exist_ok=True)
    (base / "manifest.json").write_text("[]", encoding="utf-8")
    capsys.readouterr()  # flush
    # When: write_top_index runs against the corrupt manifest.
    pipeline.write_top_index()
    stderr = capsys.readouterr().err
    # Then: a warning is emitted instead of the run aborting.
    assert "warning" in stderr.lower()

    # Given (scenario 3): a corrupt manifest that is a valid JSON object but
    # whose "files" value is explicitly null. ``dict.get("files", {})``
    # returns the default ONLY for a missing key, not for a present-but-null
    # one, so ``len(None)`` would raise TypeError and -- because
    # write_top_index runs outside per-source isolation -- abort the whole
    # run after every source already mirrored. The isinstance guard must
    # treat a non-dict "files" as empty instead.
    (base / "manifest.json").write_text(
        '{"files": null, "last_updated": null}', encoding="utf-8"
    )
    capsys.readouterr()  # flush
    # When: write_top_index runs against the null-"files" manifest -- it
    # must not raise.
    pipeline.write_top_index()
    index_text = isolated_docs.joinpath("README.md").read_text(encoding="utf-8")
    # Then: 0 pages for the corrupt source, and the null last_updated falls
    # back to the em-dash placeholder rather than rendering the string
    # "None".
    assert "| 0 |" in index_text
    assert "None" not in index_text


def test_write_top_index_tolerates_non_utf8_manifest(
    isolated_docs, monkeypatch, capsys
):
    """A manifest whose bytes are not valid UTF-8 raises
    ``UnicodeDecodeError`` inside ``read_text(encoding="utf-8")`` -- a
    ``ValueError`` subclass, NOT a ``json.JSONDecodeError`` -- before
    ``json.loads`` ever runs. ``write_top_index()`` must tolerate that
    shape (fall back to the 0-pages / em-dash defaults with a warning)
    rather than let the exception escape and abort the whole run after
    every source already mirrored; ``core.manifest.load`` treats the same
    shape as "no baseline"."""
    from mirror.sources.base import SourceConfig

    cfg = SourceConfig(
        name="bad-bytes",
        title="Bad Bytes",
        home_url="https://example.com",
        generate_whats_new=False,
    )
    fake = _fake_source_module(cfg, [])
    monkeypatch.setattr(pipeline, "SOURCES", [fake])

    base = isolated_docs / cfg.name
    base.mkdir(parents=True)
    # 0xFF/0xFE is not decodable as UTF-8, so read_text raises
    # UnicodeDecodeError before json.loads is reached.
    (base / "manifest.json").write_bytes(b'{"files": {}, "x": "\xff\xfe"}')

    pipeline.write_top_index()  # must not raise UnicodeDecodeError
    err = capsys.readouterr().err
    assert "warning" in err.lower()
    index_text = isolated_docs.joinpath("README.md").read_text(encoding="utf-8")
    assert "| [Bad Bytes](./bad-bytes/) | — | 0 | — | no |" in index_text


# --- run(only=...) source filtering -------------------------------------------


def test_run_only_filters_sources(isolated_docs, monkeypatch):
    """run(only=...) mirrors only the selected source."""
    from mirror.sources.base import SourceConfig

    cfg_a = SourceConfig(
        name="src-a",
        title="Source A",
        home_url="https://a.example.com",
        generate_whats_new=False,
    )
    cfg_b = SourceConfig(
        name="src-b",
        title="Source B",
        home_url="https://b.example.com",
        generate_whats_new=False,
    )
    # Zero-page sources so no real HTTP fetch is attempted.
    fake_a = _fake_source_module(cfg_a, [])
    fake_b = _fake_source_module(cfg_b, [])
    monkeypatch.setattr(pipeline, "SOURCES", [fake_a, fake_b])

    exit_code = pipeline.run(only="src-a")
    assert exit_code == 0
    # Only src-a's manifest should exist.
    assert (isolated_docs / "src-a" / "manifest.json").exists()
    assert not (isolated_docs / "src-b" / "manifest.json").exists()


# --- log-file tee (--log-file) ------------------------------------------------


def test_run_log_file_tees_output_to_console_and_file(
    isolated_docs, monkeypatch, tmp_path, capsys
):
    """Pin the --log-file / -l contract: ``pipeline.run(log_file=path)`` must
    write EVERY console output to the given path IN ADDITION to the real
    stdout/stderr (a tee, not a redirect). Cron and systemd timer runs rely on
    this -- the operator reads the same bytes from the persistent log file as
    appear on the captured console. A zero-page source is enough to exercise
    the path: ``run_source`` still prints the source banner via
    ``reporting.header`` before the empty manifest is saved, so that banner
    must land in BOTH places. The tee wrappers must also be torn down on exit
    so the redirection stays scoped to one run instead of persisting for the
    lifetime of the process (which would double every later print() into a
    closed file)."""
    # Zero-page source: no network fetch, but run_source still prints its header.
    src = _source("log-src")
    monkeypatch.setattr(pipeline, "SOURCES", [src])

    log_path = tmp_path / "mirror.log"
    # Capture the stream objects active right before the run so the teardown
    # can be checked by identity (any surviving wrapper would fail `is`).
    original_stdout = sys.stdout
    original_stderr = sys.stderr

    assert pipeline.run(log_file=str(log_path)) == 0

    captured = capsys.readouterr()
    # The console (capsys) received the source banner ...
    assert "== Log Src ==" in captured.out
    # ... and so did the log file (the tee copy appended by _Tee.write).
    assert "== Log Src ==" in log_path.read_text(encoding="utf-8")
    # Streams restored to the exact objects active before the run -- the tee
    # wrappers must not leak past pipeline.run().
    assert sys.stdout is original_stdout
    assert sys.stderr is original_stderr


def test_tee_disables_log_copy_after_first_write_failure(monkeypatch):
    """The _Tee log copy is BEST-EFFORT: the first OSError while writing to
    the log file must latch ``_log_failed`` so every later write skips the
    log copy instead of re-raising, and the latch must be one-shot -- the
    warning reaches the console exactly once."""
    from io import StringIO

    original = StringIO()
    log = StringIO()
    tee = pipeline._Tee(original, log)

    def _boom(data):
        raise OSError("disk full")

    monkeypatch.setattr(log, "write", _boom)

    tee.write("first")
    # The console copy went through; the log copy failed and latched.
    assert original.getvalue().startswith("first")
    assert "warning: log file write failed" in original.getvalue()
    assert tee._log_failed

    # Later writes still reach the original stream but skip the log copy,
    # and the warning is never repeated.
    tee.write("second")
    assert original.getvalue().endswith("second")
    assert original.getvalue().count("warning: log file write failed") == 1
    assert tee._log_failed


def test_tee_disables_log_copy_after_flush_failure(monkeypatch):
    """The flush path carries the same best-effort latch: an OSError while
    flushing the log file disables the copy for the rest of the run, while
    the original stream's flush always happens."""
    from io import StringIO

    original = StringIO()
    log = StringIO()
    tee = pipeline._Tee(original, log)

    def _boom():
        raise OSError("disk full")

    monkeypatch.setattr(log, "flush", _boom)

    tee.write("data")  # the write itself succeeds
    tee.flush()  # the log flush fails and latches
    assert original.getvalue().startswith("data")
    assert "warning: log file write failed" in original.getvalue()
    assert tee._log_failed

    # After the latch, a flush no longer touches the log file at all.
    log_before = log.getvalue()
    original.truncate(0)
    original.seek(0)
    tee.flush()
    assert original.getvalue() == ""
    assert log.getvalue() == log_before  # nothing new reached the log


def test_log_file_context_restores_streams_even_on_exception(tmp_path):
    """The ``_log_file_context`` finally block must restore ``sys.stdout`` and
    ``sys.stderr`` even when an exception escapes its body. Without this, a
    single crash mid-run (disk full during a write, a bug in an adapter after
    the client was built, a KeyboardInterrupt-style escape routed through
    here) would leave every subsequent print() in the process teed into a
    half-open log file -- corrupting stream state for the whole process, not
    just the failed run. The finally block is the only thing standing between
    a transient failure and that corrupted state, so it is pinned directly
    against the private context manager (the unit that owns the try/finally)
    rather than by engineering a realistic pipeline.run() failure, which
    would couple the test to whichever call happens to raise."""
    log_path = tmp_path / "crash.log"
    original_stdout = sys.stdout
    original_stderr = sys.stderr

    class _Boom(Exception):
        pass

    with pytest.raises(_Boom):
        with pipeline._log_file_context(str(log_path)):
            # Simulate a failure that escapes the whole pipeline body (the
            # exact shape does not matter -- the finally must run regardless).
            raise _Boom("simulated mid-run crash")

    # The wrappers were torn down even though the body raised: identity
    # comparison is the strictest check (any surviving wrapper object, or a
    # restored-but-different object, would fail it).
    assert sys.stdout is original_stdout
    assert sys.stderr is original_stderr


# --- reporting output pins ----------------------------------------------------


def test_fetch_start_output_format(capsys):
    """Pin the exact stdout format of ``reporting.fetch_start``: a 3-space
    indent followed by ``fetching N page(s)...``. This line is the operator's
    cue that the run has moved from discovery into the slow, rate-limited
    network stage, and its indent level is part of the presentation layer's
    visual hierarchy (3 spaces = progress line under the ``== Title ==``
    banner). The full-line equality pin (including the trailing newline)
    guards against silent wording or indentation drift in cron/CI logs, where
    this line is the only progress signal between the banner and the summary.
    """
    reporting.fetch_start(7)
    assert capsys.readouterr().out == "   fetching 7 page(s)...\n"


def test_fetch_error_output_format(capsys):
    """Pin the exact stderr format of ``reporting.fetch_error``: a 4-space
    indent (per-item detail, one level deeper than the 3-space progress
    lines), the single-``!`` per-page failure marker, the bracketed source
    name, the slug, and the exception message in parentheses. The ``!`` vs
    ``!!`` distinction is deliberate and greppable -- ``!!`` marks a
    whole-source failure while ``!`` marks a single page recovered via
    carry-forward -- so a drift here would silently break log searches that
    operators run across runs to spot repeated failures of the same slug."""
    reporting.fetch_error("my-source", "guide/intro", ValueError("boom"))
    captured = capsys.readouterr()
    assert captured.err == "    ! [my-source] failed: guide/intro (boom)\n"
    assert captured.out == ""  # per-page failures never touch stdout


# --- Concurrency & Workers parameter tests -------------------------------------


def test_fetch_pages_workers_validation():
    """fetch_pages, run_source, and run must reject workers < 1 with ValueError."""
    client = SimpleNamespace()
    src = _source("dummy")
    pages = [_page("p1")]
    with pytest.raises(ValueError, match="workers must be >= 1"):
        pipeline.fetch_pages(client, src, pages, old=None, workers=0)

    with pytest.raises(ValueError, match="workers must be >= 1"):
        pipeline.run_source(src, client, force=False, dry_run=False, workers=-1)

    with pytest.raises(ValueError, match="workers must be >= 1"):
        pipeline.run(workers=0)


def test_fetch_pages_concurrent_execution(monkeypatch):
    """fetch_pages with workers > 1 fetches pages concurrently and produces exact entries."""
    pages = [_page("p1"), _page("p2"), _page("p3")]
    src = _source("concurrent-src")
    client = SimpleNamespace()

    def fake_fetch_validated(client, url):
        return f"# Title for {url}\n\nContent", fetch.content_hash(f"Content {url}")

    monkeypatch.setattr(fetch, "fetch_validated", fake_fetch_validated)

    entries, texts, failed = pipeline.fetch_pages(
        client, src, pages, old=None, workers=3
    )
    assert failed == []
    assert len(entries) == 3
    assert len(texts) == 3
    assert list(entries.keys()) == ["p1", "p2", "p3"]
    assert "Title for https://example/p1.md" in entries["p1"].title


def test_fetch_pages_concurrent_error_isolation_and_carry_forward(monkeypatch, capsys):
    """Under concurrent fetching, a failed page is carried forward without breaking other pages."""
    pages = [_page("good1"), _page("bad"), _page("good2")]
    src = _source("mixed-src")
    client = SimpleNamespace()

    old_entry = make_entry("bad", title="Old Bad Page", hash="oldhash")
    old_manifest = Manifest(files={"bad": old_entry})

    def fake_fetch_validated(client, url):
        if "bad" in url:
            raise fetch.FetchError("simulated network glitch")
        return f"# Title for {url}\n\nOK", fetch.content_hash("OK")

    monkeypatch.setattr(fetch, "fetch_validated", fake_fetch_validated)

    entries, texts, failed = pipeline.fetch_pages(
        client, src, pages, old=old_manifest, workers=3
    )

    assert failed == ["bad"]
    assert "good1" in entries and "good1" in texts
    assert "good2" in entries and "good2" in texts
    assert "bad" in entries
    assert "bad" not in texts
    assert entries["bad"].title == "Old Bad Page"
    assert "simulated network glitch" in capsys.readouterr().err


def test_fetch_pages_scrambled_completion_maps_results_by_slug(monkeypatch):
    """fetch_pages must associate every worker outcome with the slug that
    submitted it and report results in deterministic discovery order, no
    matter the order in which the futures complete.

    The concurrent path consumes futures via ``concurrent.futures.as_completed``
    (completion order), so the property under test is the slug-keyed
    re-aggregation: this test forces an ARRIVAL order that differs from the
    submission order — gamma finishes first, alpha second, and beta (the page
    whose fetch fails) LAST, i.e. the "slowest" completer — and asserts the
    aggregated outputs are exactly what the sequential branch would produce.
    A re-implementation that leaked completion order into ``entries``/
    ``texts``/``failed`` (e.g. consuming results positionally as they arrive)
    would fail the ordering assertions below, and one that re-associated
    results with the wrong slug (e.g. zipping arrivals back onto the page
    list positionally) would fail the per-slug content/hash assertions. No
    timing is involved: the executor completes every future synchronously at
    submit time, and the patched ``as_completed`` dictates the arrival order,
    so the test is deterministic.
    """
    pages = [_page("alpha"), _page("beta"), _page("gamma")]

    def custom_fetch(client, page):
        # Per-slug payload: any positional mis-association between arrivals
        # and slugs would surface as wrong text/hash pairs below.
        if page.slug == "beta":
            raise fetch.FetchError("simulated failure for beta")
        text = f"# {page.slug}\n\nbody of {page.slug}\n" * 5
        return text, fetch.content_hash(text)

    # CONFIG is read by reporting.fetch_error when a page fails, so the
    # failing "beta" page forces the source double to carry one.
    src = SimpleNamespace(CONFIG=_cfg("scrambled-src"), fetch_markdown=custom_fetch)
    old_entry = make_entry("beta", title="Old Beta", hash="oldhash")
    old = Manifest(files={"beta": old_entry})

    class _InstantExecutor:
        """``ThreadPoolExecutor`` double that completes every future at submit
        time: each job runs synchronously on the calling thread and its
        outcome (or exception) is stored on a REAL
        ``concurrent.futures.Future``, so ``as_completed`` can inspect it.
        Real futures matter — ``fetch_pages`` hands them to the stdlib
        ``as_completed``, which reads their internal state — and eager
        completion keeps the test free of threads: the arrival order seen by
        ``fetch_pages`` is then dictated solely by the patched
        ``as_completed`` below, never by thread scheduling.
        """

        def __init__(self, max_workers: int = 1) -> None:
            """Record the pool size for interface compatibility with the real
            executor; jobs run on the calling thread, so the value is
            irrelevant."""
            self.max_workers = max_workers

        def submit(self, fn, *args):
            """Run *fn* immediately and return a Future already holding its
            result, or its exception when the job raised."""
            future = concurrent.futures.Future()
            try:
                future.set_result(fn(*args))
            except Exception as exc:
                future.set_exception(exc)
            return future

        def __enter__(self):
            """Return self so the ``with`` statement works as with the real
            executor."""
            return self

        def __exit__(self, *exc_info):
            """No-op teardown: no worker threads were ever started."""
            self.shutdown(wait=True)
            return False

        def shutdown(self, wait: bool = True, cancel_futures: bool = False) -> None:
            """No-op shutdown: no worker threads or background tasks exist."""
            pass

    def _scrambled_as_completed(futures, *args, **kwargs):
        """Deterministic stand-in for ``concurrent.futures.as_completed``.

        The real implementation yields futures in completion order, which
        under real threads depends on scheduling; this stand-in yields a FIXED
        order that differs from the submission order: the submitted sequence
        [alpha, beta, gamma] arrives as [gamma, alpha, beta], so beta — the
        page whose fetch fails — is the last outcome ``fetch_pages``
        consumes. Pinning the arrival order keeps the test deterministic and
        lets it assert the properties that must hold for ANY completion order.
        """
        listed = list(futures)
        return iter([listed[2], listed[0], listed[1]])

    monkeypatch.setattr(concurrent.futures, "ThreadPoolExecutor", _InstantExecutor)
    monkeypatch.setattr(concurrent.futures, "as_completed", _scrambled_as_completed)

    entries, texts, failed = pipeline.fetch_pages(
        SimpleNamespace(), src, pages, old, workers=4
    )

    # The failed page is reported under its own slug even though its outcome
    # arrived LAST, and in the deterministic discovery order.
    assert failed == ["beta"]

    # Aggregated dicts keep the discovery (submission) order — not the
    # arrival order [gamma, alpha, beta] — byte-for-byte the same result the
    # sequential branch produces.
    assert list(entries.keys()) == ["alpha", "beta", "gamma"]
    assert list(texts.keys()) == ["alpha", "gamma"]

    # beta's failed fetch is carried forward as a defensive copy of the old
    # manifest entry, and nothing new was fetched for it.
    assert entries["beta"] == old_entry
    assert entries["beta"] is not old_entry
    assert "beta" not in texts

    # alpha and gamma keep their OWN content and matching hash: a positional
    # re-association of the scrambled arrivals would mix these pairs up.
    # The body is generated from the slug verbatim ("# alpha", "# gamma").
    assert texts["alpha"].startswith("# alpha")
    assert texts["gamma"].startswith("# gamma")
    assert entries["alpha"].hash == fetch.content_hash(texts["alpha"])
    assert entries["gamma"].hash == fetch.content_hash(texts["gamma"])


def test_fetch_pages_keyboard_interrupt_graceful_shutdown(monkeypatch):
    """When a KeyboardInterrupt occurs during concurrent fetch collection,
    the ThreadPoolExecutor must be shut down with wait=False and cancel_futures=True."""
    shutdown_calls = []

    class _MockExecutor:
        def __init__(self, max_workers):
            self.max_workers = max_workers

        def submit(self, fn, *args, **kwargs):
            return concurrent.futures.Future()

        def shutdown(self, wait=True, cancel_futures=False):
            shutdown_calls.append({"wait": wait, "cancel_futures": cancel_futures})

    def _interrupted_as_completed(futures):
        raise KeyboardInterrupt("simulated SIGINT")

    monkeypatch.setattr(concurrent.futures, "ThreadPoolExecutor", _MockExecutor)
    monkeypatch.setattr(concurrent.futures, "as_completed", _interrupted_as_completed)

    pages = [_page("alpha"), _page("beta")]
    src = SimpleNamespace(CONFIG=SimpleNamespace(name="test-src"))
    with pytest.raises(KeyboardInterrupt):
        pipeline.fetch_pages(SimpleNamespace(), src, pages, old=None, workers=2)

    assert len(shutdown_calls) == 1
    assert shutdown_calls[0] == {"wait": False, "cancel_futures": True}


# --- update_root_readme -------------------------------------------------------


def test_update_root_readme_replaces_table_between_markers(
    isolated_docs, monkeypatch, tmp_path
):
    """update_root_readme must replace the content between markers with the generated table."""
    src_a = SimpleNamespace(
        CONFIG=SimpleNamespace(
            name="tool-a",
            title="Tool A",
            home_url="https://a",
            generate_whats_new=True,
            version="1.0.0",
            origin="example.com/a",
            how_mirrored="scraping",
        )
    )
    src_b = SimpleNamespace(
        CONFIG=SimpleNamespace(
            name="tool-b",
            title="Tool B",
            home_url="https://b",
            generate_whats_new=False,
            version="—",
            origin="example.com/b",
            how_mirrored="API",
        )
    )
    monkeypatch.setattr(pipeline, "SOURCES", [src_a, src_b])

    root_readme = tmp_path / "README.md"
    monkeypatch.setattr(config, "ROOT_README_PATH", root_readme)

    initial_content = (
        "# Main README\n\n"
        "<!-- SOURCES_TABLE:START -->\n"
        "old table content\n"
        "<!-- SOURCES_TABLE:END -->\n\n"
        "Footer content\n"
    )
    root_readme.write_text(initial_content, encoding="utf-8")

    pipeline.update_root_readme()

    result = root_readme.read_text(encoding="utf-8")
    assert "# Main README" in result
    assert "Footer content" in result
    assert "old table content" not in result
    assert (
        "| [**Tool A**](./docs/tool-a/) |  1.0.0  | example.com/a | scraping           |    ✅     |"
        in result
    )
    assert (
        "| [**Tool B**](./docs/tool-b/) |    —    | example.com/b | API                |     —     |"
        in result
    )


def test_update_root_readme_no_op_when_markers_missing(monkeypatch, tmp_path):
    """If markers are missing, update_root_readme leaves the file untouched."""
    root_readme = tmp_path / "README.md"
    monkeypatch.setattr(config, "ROOT_README_PATH", root_readme)
    initial_content = "# No markers here\n"
    root_readme.write_text(initial_content, encoding="utf-8")

    pipeline.update_root_readme()
    assert root_readme.read_text(encoding="utf-8") == initial_content


def test_update_root_readme_no_op_when_file_missing(monkeypatch, tmp_path):
    """If ROOT_README_PATH does not exist, update_root_readme returns cleanly without error."""
    root_readme = tmp_path / "non_existent_README.md"
    monkeypatch.setattr(config, "ROOT_README_PATH", root_readme)
    pipeline.update_root_readme()
    assert not root_readme.exists()


# --- dynamic version discovery integration -----------------------------------


def test_run_source_dynamic_version_hook_success(isolated_docs, monkeypatch):
    """run_source uses version from get_version hook when available."""
    src = _fake_source_module(_cfg("tool-dyn"), [_page("p1")])
    src.get_version = lambda client: "v3.4.5"
    monkeypatch.setattr(
        fetch,
        "fetch_validated",
        lambda client, url: ("# Page\n\nContent", "hash1"),
    )
    client = _FakeClient([])
    res = pipeline.run_source(src, client, force=False, dry_run=False)
    assert res is not None

    manifest_path = isolated_docs / "tool-dyn" / "manifest.json"
    m = Manifest.from_dict(json.loads(manifest_path.read_text(encoding="utf-8")))
    assert m.version == "3.4.5"


def test_run_source_dynamic_version_fallback_to_old_manifest(
    isolated_docs, monkeypatch
):
    """When get_version raises an exception, run_source retains old.version."""
    manifest_path = isolated_docs / "tool-dyn" / "manifest.json"
    old_m = Manifest(files={"p1": make_entry("p1", hash="hash1")}, version="3.4.0")
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(old_m.to_dict()), encoding="utf-8")
    (isolated_docs / "tool-dyn" / "p1.md").write_text(
        "# Page\n\nContent", encoding="utf-8"
    )

    src = _fake_source_module(_cfg("tool-dyn"), [_page("p1")])

    def failing_get_version(client):
        raise fetch.FetchError("API down")

    src.get_version = failing_get_version
    monkeypatch.setattr(
        fetch,
        "fetch_validated",
        lambda client, url: ("# Page\n\nContent", "hash1"),
    )
    client = _FakeClient([])
    pipeline.run_source(src, client, force=False, dry_run=False)

    m = Manifest.from_dict(json.loads(manifest_path.read_text(encoding="utf-8")))
    assert m.version == "3.4.0"


def test_run_source_triggers_changed_on_version_bump(isolated_docs, monkeypatch):
    """When old.version != new_manifest.version, run_source marks changed and saves."""
    manifest_path = isolated_docs / "tool-dyn" / "manifest.json"
    old_m = Manifest(files={"p1": make_entry("p1", hash="hash1")}, version="1.0.0")
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(old_m.to_dict()), encoding="utf-8")
    (isolated_docs / "tool-dyn" / "p1.md").write_text(
        "# Page\n\nContent", encoding="utf-8"
    )

    src = _fake_source_module(_cfg("tool-dyn"), [_page("p1")])
    src.get_version = lambda client: "1.0.1"
    monkeypatch.setattr(
        fetch,
        "fetch_validated",
        lambda client, url: ("# Page\n\nContent", "hash1"),
    )
    client = _FakeClient([])
    pipeline.run_source(src, client, force=False, dry_run=False)

    m = Manifest.from_dict(json.loads(manifest_path.read_text(encoding="utf-8")))
    assert m.version == "1.0.1"


def test_source_result_all_ten_fields_contract(isolated_docs, monkeypatch):
    """SourceResult exposes all 10 fields matching execution outcomes."""
    manifest_path = isolated_docs / "tool-allfields" / "manifest.json"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    src = _fake_source_module(_cfg("tool-allfields"), [_page("p1"), _page("p2")])
    monkeypatch.setattr(
        fetch,
        "fetch_validated",
        lambda client, url: ("# Page\n\nContent", "hash1"),
    )
    client = _FakeClient([])

    # 1. Baseline run
    res = pipeline.run_source(src, client, force=False, dry_run=False)
    assert isinstance(res, pipeline.SourceResult)
    assert res.name == "tool-allfields"
    assert res.title == "Tool Allfields"
    assert res.discovered == 2
    assert res.mirrored == 2
    assert res.written == 2
    assert res.deleted == 0
    assert res.failed == []
    assert isinstance(res.changes, diff.ChangeSet)
    assert res.whats_new_path is None
    assert res.is_baseline is True

    # 2. Update run with deletion
    src2 = _fake_source_module(_cfg("tool-allfields"), [_page("p1")])
    res2 = pipeline.run_source(src2, client, force=False, dry_run=False)
    assert res2.discovered == 1
    assert res2.mirrored == 1
    assert res2.written == 0
    assert res2.deleted == 1
    assert res2.failed == []
    assert len(res2.changes.removed) == 1
    assert res2.is_baseline is False

    # 3. Update run with fetch failure on known page (carried forward)
    src3 = _fake_source_module(_cfg("tool-allfields"), [_page("p1")])

    def _failing_fetch(client, url):
        raise fetch.FetchError("network down")

    monkeypatch.setattr(fetch, "fetch_validated", _failing_fetch)
    res3 = pipeline.run_source(src3, client, force=False, dry_run=False)
    assert res3.discovered == 1
    assert res3.mirrored == 1  # Carried forward
    assert res3.written == 0
    assert res3.deleted == 0
    assert res3.failed == ["p1"]


def test_run_source_dynamic_version_fallback_on_invalid_return_types(
    isolated_docs, monkeypatch
):
    """When get_version returns None, empty, or non-string, run_source retains fallback version."""
    manifest_path = isolated_docs / "tool-dyn-fallback" / "manifest.json"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    old_m = Manifest(files={"p1": make_entry("p1", hash="hash1")}, version="2.5.0")
    manifest_path.write_text(json.dumps(old_m.to_dict()), encoding="utf-8")
    (isolated_docs / "tool-dyn-fallback" / "p1.md").write_text(
        "# Page", encoding="utf-8"
    )

    src = _fake_source_module(_cfg("tool-dyn-fallback"), [_page("p1")])
    monkeypatch.setattr(
        fetch,
        "fetch_validated",
        lambda client, url: ("# Page", "hash1"),
    )
    client = _FakeClient([])

    for invalid_val in (None, "", "   ", 12345, ["1.0.0"]):
        src.get_version = lambda c, val=invalid_val: val  # type: ignore[assignment]
        pipeline.run_source(src, client, force=False, dry_run=False)
        m = Manifest.from_dict(json.loads(manifest_path.read_text(encoding="utf-8")))
        assert m.version == "2.5.0"


def test_update_root_readme_handles_corrupt_or_unreadable_manifest(
    tmp_path: Path, monkeypatch
):
    """update_root_readme safely tolerates malformed JSON and decode errors in manifests."""
    readme = tmp_path / "README.md"
    readme.write_text(
        f"Intro\n{config.SOURCES_TABLE_START}\nOld Table\n{config.SOURCES_TABLE_END}\nOutro",
        encoding="utf-8",
    )
    monkeypatch.setattr(config, "ROOT_README_PATH", readme)
    docs_dir = tmp_path / "docs"
    monkeypatch.setattr(config, "DOCS_DIR", docs_dir)

    # First source has corrupt JSON
    bad_json_dir = docs_dir / pipeline.SOURCES[0].CONFIG.name
    bad_json_dir.mkdir(parents=True, exist_ok=True)
    (bad_json_dir / "manifest.json").write_text("{corrupt json", encoding="utf-8")

    # Second source has non-UTF8 bytes
    if len(pipeline.SOURCES) > 1:
        bad_utf8_dir = docs_dir / pipeline.SOURCES[1].CONFIG.name
        bad_utf8_dir.mkdir(parents=True, exist_ok=True)
        (bad_utf8_dir / "manifest.json").write_bytes(b"\xff\xfe\x00\x00")

    pipeline.update_root_readme()
    updated = readme.read_text(encoding="utf-8")
    assert "Intro" in updated
    assert config.SOURCES_TABLE_START in updated
    assert config.SOURCES_TABLE_END in updated
    assert "Outro" in updated


def test_write_docs_carry_forward_and_empty_last_updated_repair(tmp_path: Path):
    """write_docs repairs missing or empty last_updated timestamp on carried forward entries."""
    base = tmp_path / "docs" / "test-source"
    base.mkdir(parents=True, exist_ok=True)
    (base / "page1.md").write_text("page 1 text", encoding="utf-8")

    h = fetch.content_hash("page 1 text")
    old_entry = make_entry("page1", hash=h, last_updated="")
    old = Manifest(files={"page1": old_entry})

    # Carried forward: entry in entries, but omitted from texts
    entries = {"page1": old_entry}
    texts = {}

    written, deleted = pipeline.write_docs(
        base=base,
        entries=entries,
        texts=texts,
        old=old,
        discovered_slugs={"page1"},
        force=False,
        now_iso="2026-09-06T12:00:00Z",
    )
    assert written == 0
    assert deleted == 0
    assert entries["page1"].last_updated == "2026-09-06T12:00:00Z"


def test_write_docs_deletion_stops_parent_cleanup_at_non_empty_dir(tmp_path: Path):
    """write_docs bottom-up rmdir removes empty child dirs but preserves non-empty parents."""
    base = tmp_path / "docs" / "test-source"
    deep_dir = base / "parent" / "child"
    deep_dir.mkdir(parents=True, exist_ok=True)
    to_delete = deep_dir / "obsolete.md"
    to_delete.write_text("obsolete", encoding="utf-8")

    # Sibling in parent directory that must keep parent alive
    sibling = base / "parent" / "surviving.txt"
    sibling.write_text("keep me", encoding="utf-8")

    # Have 3 old files so 1 deletion is 33% <= 50% threshold to avoid tripping safety guard
    old = Manifest(
        files={
            "parent/child/obsolete": make_entry("parent/child/obsolete"),
            "kept1": make_entry("kept1"),
            "kept2": make_entry("kept2"),
        }
    )
    written, deleted = pipeline.write_docs(
        base=base,
        entries={"kept1": make_entry("kept1"), "kept2": make_entry("kept2")},
        texts={},
        old=old,
        discovered_slugs={"kept1", "kept2"},
        force=False,
        now_iso="2026-09-06T12:00:00Z",
    )
    assert deleted == 1
    assert not to_delete.exists()
    assert not deep_dir.exists()  # Empty child dir was removed
    assert (base / "parent").is_dir()  # Non-empty parent was preserved
    assert sibling.exists()


def test_pipeline_concurrent_fetch_real_execution():
    """fetch_pages fetches pages concurrently with real worker pool preserving order."""
    client = _FakeClient(
        [
            _Resp(200, "# Alpha\n\nBody A"),
            _Resp(200, "# Beta\n\nBody B"),
            _Resp(200, "# Gamma\n\nBody C"),
        ]
    )
    pages = [
        Page(
            slug="alpha",
            group="",
            source_id="alpha",
            source_url="https://example.com/a",
            source_md_url="https://example.com/a.md",
        ),
        Page(
            slug="beta",
            group="",
            source_id="beta",
            source_url="https://example.com/b",
            source_md_url="https://example.com/b.md",
        ),
        Page(
            slug="gamma",
            group="",
            source_id="gamma",
            source_url="https://example.com/c",
            source_md_url="https://example.com/c.md",
        ),
    ]
    src = _fake_source_module(_cfg("concurrent-tool"), pages)
    entries, texts, failed = pipeline.fetch_pages(
        client=client,
        source=src,
        pages=pages,
        old=None,
        workers=3,
    )
    assert list(entries.keys()) == ["alpha", "beta", "gamma"]
    assert list(texts.keys()) == ["alpha", "beta", "gamma"]
    assert failed == []
