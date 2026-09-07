"""Tests for the per-source index renderer (mirror.core.index)."""

from __future__ import annotations

import pytest
from conftest import make_entry
from mirror.core import index, manifest


def _entry(slug: str, group: str, title: str | None = None) -> manifest.FileEntry:
    """Thin wrapper over conftest.make_entry for index-renderer tests.

    The renderer only reads slug, group, and title, so each test states just
    those; the shared factory fills in valid URLs, ids, and hashes. The title
    defaults to a title-cased slug so tests that do not care about titles
    still get distinct, realistic ones."""
    return make_entry(slug, group=group, title=title or slug.title())


def test_render_groups_and_counts():
    """The rendered index must report the total page count, group pages under
    their group headings, and link each page with a relative path. The 'root'
    group is special: it is headed with the source title and sorted first."""
    m = manifest.Manifest(
        files={
            "guides/a": _entry("guides/a", "guides"),
            "guides/b": _entry("guides/b", "guides"),
            "intro": _entry("intro", "root"),
        }
    )
    out = index.render(m, "My Source", "https://home")
    assert "Pages mirrored:** 3" in out
    # The "root" group is headed with the source title and sorted first.
    assert out.index("## My Source") < out.index("## guides")
    assert "[intro.md](./intro.md)" in out
    assert "[guides/a.md](./guides/a.md)" in out


def test_render_empty_group_falls_back_to_documentation():
    """Entries with an empty/blank group name must not produce a broken empty
    heading; they are bucketed under a 'Documentation' heading instead."""
    m = manifest.Manifest(files={"a": _entry("a", "", title="A")})
    out = index.render(m, "S", "https://home")
    # An empty/blank group is bucketed under "Documentation".
    assert "## Documentation" in out
    assert "[a.md](./a.md)" in out


def test_render_empty_manifest_does_not_crash():
    """An empty manifest (zero files) must render a valid index document with a
    page count of 0 rather than crashing on an empty groups dict. The output
    must still contain the source title and the standard footer links."""
    m = manifest.Manifest(files={})
    out = index.render(m, "Empty Source", "https://home")
    assert "Empty Source" in out
    assert "Pages mirrored:** 0" in out
    assert "manifest.json" in out


def test_render_with_and_without_version():
    """A manifest with a non-default version must render the Version line in the header;
    a default/unversioned manifest ('—') must omit the Version line."""
    m_versioned = manifest.Manifest(files={}, version="1.2.3")
    out_versioned = index.render(m_versioned, "Versioned Source", "https://home")
    assert "- **Version:** 1.2.3" in out_versioned

    m_unversioned = manifest.Manifest(files={}, version="—")
    out_unversioned = index.render(m_unversioned, "Unversioned Source", "https://home")
    assert "**Version:**" not in out_unversioned


# --- Markdown-formatted titles ------------------------------------------------


def test_render_formatted_titles():
    """Titles containing backticks, asterisks, pipes, and brackets must render
    without breaking the Markdown table. All special Markdown characters are
    escaped so they appear literally in the table cell."""
    m = manifest.Manifest(
        files={
            "backtick": _entry("backtick", "root", title="`code` span"),
            "bold": _entry("bold", "root", title="**bold** text"),
            "pipe": _entry("pipe", "root", title="a | b"),
        }
    )
    out = index.render(m, "Formatted", "https://home")
    assert r"\`code\` span" in out  # backticks escaped
    assert r"\*\*bold\*\* text" in out  # asterisks escaped
    assert r"a \| b" in out  # pipe escaped


# --- source-link destinations ----------------------------------------------------


def test_render_source_link_angle_bracketed_for_special_chars():
    """The ``[source]`` link destination must be wrapped in angle brackets
    (``[source](<url>)``): ``source_url`` is interpolated raw, so a URL
    containing a space or ``)`` would terminate a bare ``(...)`` destination
    early and silently break the link. Inside angle brackets those characters
    are legal (CommonMark), so the full URL survives."""
    m = manifest.Manifest(
        files={
            "a": make_entry(
                "a",
                group="root",
                title="A",
                source_url="https://example.com/docs/v1 (stable)/guide",
            )
        }
    )
    out = index.render(m, "S", "https://home")
    assert "[source](<https://example.com/docs/v1 (stable)/guide>)" in out


# --- newline / carriage-return in titles -----------------------------------------


def test_render_title_newline_and_carriage_return():
    """Titles containing ``\\n`` or ``\\r`` must have those characters replaced
    by spaces in the rendered table — ``_TITLE_ESCAPES`` maps them both to
    space, since a newline inside a Markdown table cell would split the table
    row and corrupt the entire index."""
    m = manifest.Manifest(
        files={
            "a": _entry("a", "root", "Line1\nLine2\rLine3"),
        }
    )
    out = index.render(m, "S", "https://home")
    assert "| Line1 Line2 Line3 |" in out


def test_render_source_link_sanitizes_forbidden_destination_chars():
    """Angle brackets do NOT make every character safe in a link destination:
    CommonMark forbids unescaped ``<``, ``>``, and line endings inside
    ``<...>``. A ``source_url`` containing any of those must be
    percent-encoded at emission time -- a raw ``<``/``>`` would corrupt the
    destination, and a raw newline would split the table row and corrupt the
    whole index. Encoding (not stripping) keeps the emitted URL valid and
    decodable back to the original string."""
    m = manifest.Manifest(
        files={
            "a": make_entry(
                "a",
                group="root",
                title="A",
                source_url="https://example.com/a<b>\nc>d",
            )
        }
    )
    out = index.render(m, "S", "https://home")
    # The forbidden characters are percent-encoded, not dropped, so the link
    # is well-formed AND the URL still decodes to the original.
    assert "[source](<https://example.com/a%3Cb%3E%0Ac%3Ed>)" in out
    # The raw URL must not survive anywhere: an unencoded ``<`` or newline
    # in the destination is exactly the silent breakage being prevented.
    assert "https://example.com/a<b>" not in out


def test_render_source_link_percent_encodes_pipe_in_url():
    """A ``|`` inside ``source_url`` must be percent-encoded to ``%7C``:
    the ``[source]`` link is rendered inside a GFM table cell, where an
    unescaped ``|`` is interpreted as a column separator and would split
    the cell in two, corrupting the row layout for that page (and every
    row after it). Titles are already protected against ``|`` via
    ``_TITLE_ESCAPES`` and slugs via their charset; this test pins the same
    protection for the third rendered field, the URL, so the escaping
    contract stays consistent across all three cell fields. Real upstream
    URLs essentially never contain ``|``, but the corruption is silent and
    display-only when one does, so encoding it is cheap insurance.
    Percent-encoding is chosen over backslash-escaping because it is valid
    inside an angle-bracket destination and reversible."""
    m = manifest.Manifest(
        files={
            "a": make_entry(
                "a",
                group="root",
                title="A",
                source_url="https://example.com/path|with|pipes",
            )
        }
    )
    out = index.render(m, "S", "https://home")
    assert "[source](<https://example.com/path%7Cwith%7Cpipes>)" in out
    # The raw pipe must not survive in the destination: a literal ``|`` there
    # is exactly the column-splitting breakage being prevented.
    assert "path|with|pipes" not in out


# --- group-label sanitation -----------------------------------------------------


def test_render_group_label_newlines_collapsed():
    """A group name containing ``\\n`` or ``\\r`` must have those characters
    collapsed to spaces before it becomes a ``## `` section heading. Group
    names are upstream-derived (URL path segments), so they can in principle
    contain anything; a raw line break would split the heading across two
    lines and inject a stray line into the generated README layout. This
    mirrors the newline treatment titles already get via
    ``_TITLE_ESCAPES``."""
    m = manifest.Manifest(files={"a": _entry("a", "guides\ninjected\rline", title="A")})
    out = index.render(m, "S", "https://home")
    # The heading occupies exactly one line, with breaks collapsed to spaces.
    assert "## guides injected line" in out
    heading_lines = [ln for ln in out.splitlines() if ln.startswith("## ")]
    assert len(heading_lines) == 1
    # No fragment of the original multiline group name may leak onto its
    # own line as a pseudo-heading.
    assert "## injected" not in out


# --- write(): the failure path documented in its docstring ----------------------


def test_write_failure_propagates_and_leaves_no_temp_files(tmp_path):
    """``index.write``'s docstring promises that a failed write surfaces the
    ORIGINAL error and that the best-effort temp-file cleanup (inside
    ``utils.atomic_write``) never masks it. Pin that contract end to end:
    make the atomic rename fail by placing a DIRECTORY at the destination
    path (``Path.replace`` cannot rename a file over a non-empty directory),
    then assert the OSError propagates unchanged and no stale
    ``README.md.<pid>.tmp`` staging file is left behind."""
    dest = tmp_path / "README.md"
    dest.mkdir()  # the rename target is a directory -> replace() fails
    m = manifest.Manifest(files={"a": _entry("a", "root", title="A")})
    with pytest.raises(OSError):
        index.write(dest, m, "S", "https://home")
    # The staged temp file must have been cleaned up best-effort: no
    # ``*.{pid}.tmp`` staging file may remain in the destination's folder.
    # (The directory also holds the autouse fixture's ``isolated-docs``
    # subdir, so the assertion targets temp files specifically.)
    assert not list(tmp_path.glob("*.tmp"))
