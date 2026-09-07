"""Tests for Page data validation (mirror.core.page)."""

from __future__ import annotations

import pytest
from mirror.core.page import Page

# Shared valid kwargs reused across tests to keep each test focused on its one
# assertion without repeating boilerplate.
_VALID_KWARGS = {
    "source_url": "https://x/pg",
    "source_md_url": "https://x/pg.md",
}


def test_page_empty_slug_raises():
    """An empty slug must raise ``ValueError`` — without this guard the
    manifest would silently overwrite entries and files."""
    with pytest.raises(ValueError, match="Page.slug must be non-empty"):
        Page(slug="", source_id="x", **_VALID_KWARGS)


def test_page_whitespace_slug_raises():
    """A whitespace-only slug (truthy in Python but useless as a filename)
    must also raise — stripping first catches this case. The message names
    BOTH rejectable shapes ("non-empty and not whitespace-only"), because a
    whitespace-only value IS non-empty: a bare "must be non-empty" message
    would misdescribe why it was rejected, and the distinct "must be
    stripped" branch (for padded values like " x") never fires for it."""
    with pytest.raises(
        ValueError, match="Page.slug must be non-empty and not whitespace-only"
    ):
        Page(slug="   ", source_id="x", **_VALID_KWARGS)


def test_page_empty_source_id_raises():
    """An empty ``source_id`` must raise — without this guard rename
    detection would falsely match unrelated pages via empty-string equality."""
    with pytest.raises(ValueError, match="Page.source_id must be non-empty"):
        Page(slug="x", source_id="", **_VALID_KWARGS)


def test_page_whitespace_source_id_raises():
    """A whitespace-only ``source_id`` must also raise — trimming before the
    truthiness check catches this case at discovery time rather than silently
    producing bogus rename matches."""
    with pytest.raises(ValueError, match="Page.source_id must be non-empty"):
        Page(slug="x", source_id="   ", **_VALID_KWARGS)


def test_slug_rejects_spaces():
    """Page rejects slugs containing spaces. The match is pinned to the
    character-alphabet message (not the bare word "slug", which would also
    pass on any *other* slug-validation error such as the empty-slug guard)
    so the test fails loudly if the rejection ever moves to a different
    validation branch."""
    with pytest.raises(
        ValueError, match="contains characters that would break Markdown rendering"
    ):
        Page(
            slug="getting started",
            source_url="https://x.com",
            source_md_url="https://x.com/x.md",
            source_id="x",
            group="x",
        )


def test_slug_rejects_trailing_slash():
    """Page rejects slugs ending with a trailing slash."""
    with pytest.raises(ValueError, match="trailing slash"):
        Page(
            slug="foo/",
            source_url="https://x.com",
            source_md_url="https://x.com/x.md",
            source_id="x",
            group="x",
        )


def test_slug_rejects_consecutive_slashes():
    """A slug like ``category//page`` contains an empty path segment after
    splitting on ``/``, which would produce an invalid file path on disk and
    a broken Markdown link in generated indexes.  The check is deliberately
    placed *after* the trailing-slash guard so that ``foo/`` produces the
    more specific "trailing slash" message rather than the generic "empty
    path segments" one."""
    with pytest.raises(ValueError, match="empty path segments"):
        Page(
            slug="cat//page",
            source_url="https://x.com",
            source_md_url="https://x.com/x.md",
            source_id="x",
            group="x",
        )


def test_slug_rejects_absolute_path():
    """A slug starting with ``/`` would make ``Path(base) / slug`` resolve to an
    absolute path outside the per-source docs tree (``PurePath.__truediv__``
    discards the left operand once the right operand is absolute), so it must
    be rejected at construction time rather than silently written outside the
    mirror. The match is pinned to the absolute-path message rather than the
    bare word "slug" so the test fails loudly if the rejection ever shifts to a
    different validation branch (e.g. the character-alphabet guard, which a
    leading "/" actually passes)."""
    with pytest.raises(ValueError, match="relative path, not absolute"):
        Page(slug="/foo", source_id="x", **_VALID_KWARGS)


def test_slug_rejects_dotdot_path_segment():
    """A slug containing a ``..`` segment would walk out of the per-source docs
    directory when joined onto ``base`` -- the same path-traversal shape as a
    leading ``/`` -- so it must be rejected at construction. The match is pinned
    to the ``'..' path segments`` message so the test fails if that specific
    guard is removed (the slug below passes the character-alphabet and
    leading-slash checks and only trips this one)."""
    with pytest.raises(ValueError, match=r"'\.\.' path segments"):
        Page(slug="../etc/x", source_id="x", **_VALID_KWARGS)


def test_page_unstripped_slug_raises():
    """A slug with leading/trailing whitespace must be REJECTED, not silently
    normalized: an unstripped value is almost always a discovery bug (a
    missing ``.strip()`` in a source adapter), and quietly fixing it here
    would both hide that bug and risk two distinct discoveries colliding
    onto the same stripped key."""
    with pytest.raises(ValueError, match="must be stripped"):
        Page(slug=" x", source_id="x", **_VALID_KWARGS)
    with pytest.raises(ValueError, match="must be stripped"):
        Page(slug="x ", source_id="x", **_VALID_KWARGS)


def test_page_unstripped_source_id_raises():
    """An unstripped ``source_id`` is rejected for the same reason as an
    unstripped slug -- and it is worse than cosmetic: rename detection
    matches on ``source_id`` *equality*, so ``"x"`` and ``"x "`` would be
    treated as two different upstream identities, splitting one page's
    history into a fabricated add/remove pair."""
    with pytest.raises(ValueError, match="must be stripped"):
        Page(slug="x", source_id=" x", **_VALID_KWARGS)


@pytest.mark.parametrize("field", ["source_url", "source_md_url"])
@pytest.mark.parametrize("value", ["", "   "])
def test_page_empty_or_whitespace_url_raises(field, value):
    """Both URLs must be non-empty and non-whitespace: they are rendered as
    links in the generated README and whats-new logs, so an empty URL would
    produce a broken link on every mirrored page listing. Whitespace-only
    values are truthy in Python, so the guard must strip before checking."""
    kwargs = {**_VALID_KWARGS, field: value}
    with pytest.raises(ValueError, match=f"Page.{field} must be non-empty"):
        Page(slug="x", source_id="x", **kwargs)


def test_slug_at_max_length_is_accepted():
    """A slug of exactly ``_MAX_SLUG_LENGTH`` (200) characters must be
    accepted: the cap is an inclusive upper bound, and the filesystem filename
    limit (255 bytes per component) leaves room for it plus the ``.md``
    suffix because the character whitelist keeps slugs ASCII (1 char = 1
    byte). The assertion is made explicit (rather than relying on "construction
    did not raise") so that if the length check were ever inverted the test
    would fail loudly instead of passing by accident."""
    page = Page(slug="a" * 200, source_id="x", **_VALID_KWARGS)
    assert page.slug == "a" * 200


def test_slug_over_max_length_raises():
    """A slug longer than 200 characters must be rejected at discovery time:
    without the length cap it would sail through character validation and
    then crash the whole source run later with an unhandled ``OSError: [Errno
    36] File name too long`` when the pipeline writes ``<slug>.md``."""
    with pytest.raises(ValueError, match="at most 200 characters"):
        Page(slug="a" * 201, source_id="x", **_VALID_KWARGS)


def test_nested_slug_over_max_length_raises():
    """The length cap applies to the WHOLE slug, not just one path segment:
    many short segments that add up past the limit still produce an over-long
    relative path and must be rejected the same way."""
    with pytest.raises(ValueError, match="at most 200 characters"):
        Page(slug="/".join(["a" * 40] * 6), source_id="x", **_VALID_KWARGS)


def test_page_non_string_group_raises():
    """A non-string ``group`` (e.g. ``None`` from a buggy adapter) must be
    rejected at discovery time with a clear ``ValueError``, mirroring the
    ``FileEntry`` guard.  Without this check the bad value would only blow up
    much later -- deep inside index rendering when groups are sorted -- far
    from the adapter that produced it, making the root cause hard to trace."""
    with pytest.raises(ValueError, match="Page.group must be a string"):
        Page(slug="x", source_id="x", group=None, **_VALID_KWARGS)
