"""Tests for ``mirror.core.utils`` — the atomic_write / atomic_write_bytes pair.

``atomic_write`` is the single crash-safe write primitive every output path in
the pipeline delegates to (``index.write``, ``manifest.save``,
``whats_new.write_entry``, ``pipeline.write_docs`` /
``pipeline.write_top_index``); ``atomic_write_bytes`` is its binary twin for
downloaded media assets. Their happy paths are already exercised indirectly
all over the suite through those callers; this module pins the helpers' OWN
contract directly — in particular the failure branches that no caller test
reaches:

  * a failed write/rename must not leave orphaned ``.{pid}_{token}.tmp`` files behind
    (the ``finally`` cleanup), and
  * a failure DURING that cleanup must be logged to stderr and swallowed so it
    can never mask the original exception.

Losing either property silently would reintroduce exactly the problems the
helper was extracted to solve: stale temp files accumulating across failed
runs, or a secondary cleanup error hiding the real failure from the operator.
"""

from pathlib import Path

import pytest

from mirror.core.utils import atomic_write, atomic_write_bytes, extract_version


def test_atomic_write_happy_path(tmp_path: Path) -> None:
    """A successful write lands the exact content and leaves no temp file.

    This is the baseline contract every caller relies on: after the call,
    ``dest`` holds the full content (UTF-8) and the sibling
    ``.{pid}_{token}.tmp`` staging file is gone — on success ``Path.replace``
    has already consumed it, and the best-effort ``unlink(missing_ok=True)``
    in the ``finally`` block is a no-op.
    """
    dest = tmp_path / "out.md"
    atomic_write(dest, "full content ✓\n")
    assert dest.read_text(encoding="utf-8") == "full content ✓\n"
    # No staging file may survive a successful atomic write.
    assert list(tmp_path.glob("*.tmp")) == []


def test_atomic_write_cleans_up_temp_file_on_rename_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A failing rename propagates AND removes the staged temp file.

    Simulates the rename step failing (disk full, permission denied) by
    patching ``Path.replace`` to raise ``OSError``. Two properties are pinned:

      1. the original ``OSError`` propagates unchanged to the caller (the
         helper must never swallow the real failure), and
      2. the ``finally`` cleanup removes the staged ``.{pid}_{token}.tmp`` file,
         so failed runs do not litter the output tree with orphaned temp files.
    """

    def failing_replace(self: Path, target: Path) -> None:
        raise OSError("simulated rename failure")

    monkeypatch.setattr(Path, "replace", failing_replace)

    dest = tmp_path / "out.md"
    with pytest.raises(OSError, match="simulated rename failure"):
        atomic_write(dest, "content")
    assert list(tmp_path.glob("*.tmp")) == []


def test_atomic_write_cleanup_failure_is_logged_not_raised(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    """A cleanup failure is warned about, never raised over the real error.

    Patches BOTH ``Path.replace`` (the simulated real failure) and
    ``Path.unlink`` (the cleanup itself failing, e.g. the temp file was
    removed by another process between the failed rename and the cleanup).
    The contract under test: the ORIGINAL exception must reach the caller —
    a secondary ``OSError`` raised during best-effort cleanup would mask it
    and send the operator debugging the wrong failure — and the cleanup
    problem must still be visible as a stderr warning so it is loud rather
    than silent.
    """

    def failing_replace(self: Path, target: Path) -> None:
        raise OSError("simulated rename failure")

    def failing_unlink(self: Path, missing_ok: bool = False) -> None:
        raise OSError("simulated cleanup failure")

    monkeypatch.setattr(Path, "replace", failing_replace)
    monkeypatch.setattr(Path, "unlink", failing_unlink)

    dest = tmp_path / "out.md"
    # The rename error — not the cleanup error — is what propagates.
    with pytest.raises(OSError, match="simulated rename failure"):
        atomic_write(dest, "content")
    # The swallowed cleanup failure is still reported on stderr.
    assert "could not remove temporary file" in capsys.readouterr().err


def test_atomic_write_concurrent_threads(tmp_path: Path) -> None:
    """Concurrent writes across threads produce isolated files without collisions."""
    from concurrent.futures import ThreadPoolExecutor

    def write_worker(idx: int) -> None:
        target = tmp_path / f"worker_{idx}.md"
        atomic_write(target, f"content {idx}\n")

    with ThreadPoolExecutor(max_workers=8) as executor:
        list(executor.map(write_worker, range(30)))

    # All files exist with correct contents
    for idx in range(30):
        target = tmp_path / f"worker_{idx}.md"
        assert target.read_text(encoding="utf-8") == f"content {idx}\n"

    # No leftover temporary files
    assert list(tmp_path.glob("*.tmp")) == []


# --- atomic_write_bytes: the binary twin of atomic_write ---------------------


def test_atomic_write_bytes_happy_path(tmp_path: Path) -> None:
    """A binary payload lands byte-exact with no text round-trip and no temp file.

    Arbitrary content -- including bytes that are not valid UTF-8, which a
    text write could never represent -- must reach the destination verbatim;
    this is the contract the media stage's image downloads depend on."""
    dest = tmp_path / "logo.png"
    payload = b"\xff\xd8\xff\xe0\x00binary-content"
    atomic_write_bytes(dest, payload)
    assert dest.read_bytes() == payload
    # No staging file may survive a successful atomic write.
    assert list(tmp_path.glob("*.tmp")) == []


def test_atomic_write_bytes_replaces_existing_file(tmp_path: Path) -> None:
    """A second write replaces the previous file atomically (whole-file swap).

    Re-running the media stage over a changed upstream image must leave the
    old bytes fully replaced -- readers only ever see one version or the
    other, never a mix."""
    dest = tmp_path / "logo.png"
    dest.write_bytes(b"old bytes")
    atomic_write_bytes(dest, b"new bytes \xff\xfe")
    assert dest.read_bytes() == b"new bytes \xff\xfe"
    assert list(tmp_path.glob("*.tmp")) == []


def test_atomic_write_bytes_cleans_up_temp_file_on_rename_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The binary path shares the bytes twin's failure cleanup: a failing
    rename propagates AND removes the staged temp file (same contract as
    ``test_atomic_write_cleans_up_temp_file_on_rename_failure``)."""

    def failing_replace(self: Path, target: Path) -> None:
        raise OSError("simulated rename failure")

    monkeypatch.setattr(Path, "replace", failing_replace)

    dest = tmp_path / "out.png"
    with pytest.raises(OSError, match="simulated rename failure"):
        atomic_write_bytes(dest, b"content")
    assert list(tmp_path.glob("*.tmp")) == []


def test_extract_version_none_or_empty() -> None:
    """Non-string, empty, or whitespace-only inputs return None."""
    assert extract_version(None) is None
    assert extract_version("") is None
    assert extract_version("   ") is None
    assert extract_version("  \n\t  ") is None


def test_extract_version_semver_extraction() -> None:
    """Extracts valid SemVer strings with or without prefixes and surrounding text."""
    assert extract_version("1.2.3") == "1.2.3"
    assert extract_version("v1.2.3") == "1.2.3"
    assert extract_version("V1.2.3") == "1.2.3"
    assert extract_version("v2.1.0-rc.2") == "2.1.0-rc.2"
    assert extract_version("Release v0.153.4-alpha") == "0.153.4-alpha"
    assert extract_version("Antigravity CLI 1.1.27 (build 42)") == "1.1.27"


def test_extract_version_non_semver_prefix_strip() -> None:
    """Non-semver strings have leading 'v'/'V' stripped, or return None if empty."""
    assert extract_version("vNext") == "Next"
    assert extract_version("VPreview") == "Preview"
    assert extract_version("v") is None
    assert extract_version("V") is None
    assert extract_version("custom-build") == "custom-build"
