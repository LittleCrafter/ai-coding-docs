"""Tests for the OpenCode source adapter (mirror.sources.opencode)."""

from __future__ import annotations


import pytest
from conftest import _FakeClient, _Resp, blob_entry, tree_client
from mirror.core import fetch
from mirror.core.page import Page
from mirror.sources import opencode


# --- Discovery: tree-entry filtering ------------------------------------------


def test_discover_keeps_english_mdx_under_docs_prefix():
    """Only ``.mdx`` and ``.md`` files under the docs prefix are kept.
    Non-Markdown files, files outside the prefix, and directory entries
    must all be dropped."""
    prefix = "packages/web/src/content/docs"
    client = tree_client(
        [
            blob_entry(f"{prefix}/index.mdx"),  # keep -> "intro"
            blob_entry(f"{prefix}/getting-started/overview.mdx"),  # keep
            blob_entry(f"{prefix}/configuration/settings.md"),  # keep (.md)
            blob_entry(f"{prefix}/notes.txt"),  # drop: not Markdown
            blob_entry("src/main.ts"),  # drop: outside prefix
            {"type": "tree", "path": prefix},  # drop: directory entry
        ]
    )
    pages = opencode.discover(client)
    assert {p.slug for p in pages} == {
        "intro",
        "getting-started/overview",
        "configuration/settings",
    }


def test_discover_maps_root_index_to_intro():
    """Root ``index.mdx`` must map to slug ``"intro"``, and its group must
    be ``"root"`` -- this is the landing / home page."""
    prefix = "packages/web/src/content/docs"
    client = tree_client([blob_entry(f"{prefix}/index.mdx")])
    pages = opencode.discover(client)
    assert len(pages) == 1
    page = pages[0]
    assert page.slug == "intro"
    assert page.group == "root"
    assert page.source_url == "https://opencode.ai/docs/intro"
    assert page.source_id == f"{prefix}/index.mdx"


def test_discover_maps_root_readme_to_intro():
    """Root ``README.md`` must also map to slug ``"intro"``."""
    prefix = "packages/web/src/content/docs"
    client = tree_client([blob_entry(f"{prefix}/README.md")])
    pages = opencode.discover(client)
    assert len(pages) == 1
    assert pages[0].slug == "intro"


def test_discover_excludes_locale_subdirectories():
    """Paths under the known non-English locale directories (``bs/``,
    ``zh-cn/``, ``fr/``, ``pt-br/`` -- all members of the explicit
    ``KNOWN_LOCALE_DIRS`` set) must be filtered out on a default run.
    Locale detection is set-based, not name-shape-based, and applies only
    to the FIRST segment of a multi-segment path: single-segment slugs pass
    through even when their name is locale-shaped (e.g. the English page
    ``go.mdx``), and English content directories with descriptive names
    (``getting-started/``) are never touched. Only the English (unprefixed)
    docs are mirrored."""
    prefix = "packages/web/src/content/docs"
    client = tree_client(
        [
            blob_entry(f"{prefix}/index.mdx"),  # keep -> "intro"
            blob_entry(
                f"{prefix}/bs/index.mdx"
            ),  # drop: Bosnian locale (multi-segment, short code)
            blob_entry(f"{prefix}/zh-cn/getting-started.mdx"),  # drop: Chinese locale
            blob_entry(f"{prefix}/fr/overview.mdx"),  # drop: French locale
            blob_entry(
                f"{prefix}/go.mdx"
            ),  # keep: English page (single-segment, looks like locale code but isn't)
            blob_entry(
                f"{prefix}/getting-started/overview.mdx"
            ),  # keep: English content directory (descriptive name)
            blob_entry(f"{prefix}/pt-br/config.mdx"),  # drop: Portuguese locale
        ]
    )
    pages = opencode.discover(client)
    assert {p.slug for p in pages} == {"intro", "go", "getting-started/overview"}


def test_discover_keeps_short_named_english_directories():
    """English directories whose names LOOK like locale codes must NOT be
    dropped: the upstream tree carries short-named English pages
    (``cli.mdx``, ``go.mdx``, ``tui.mdx``, ...), and if upstream restructures
    one into a directory (``cli.mdx`` -> ``cli/index.mdx``), the whole
    subtree must still be mirrored. This is exactly the failure mode the
    explicit ``KNOWN_LOCALE_DIRS`` set exists to prevent -- a name-shape
    regex would silently delete these pages."""
    prefix = "packages/web/src/content/docs"
    client = tree_client(
        [
            blob_entry(f"{prefix}/index.mdx"),  # keep -> "intro"
            blob_entry(f"{prefix}/cli/index.mdx"),  # keep -> "cli" (not a locale)
            blob_entry(f"{prefix}/go/advanced.mdx"),  # keep -> "go/advanced"
        ]
    )
    pages = opencode.discover(client)
    assert {p.slug for p in pages} == {"intro", "cli", "go/advanced"}


def test_discover_default_run_reports_excluded_locales_as_single_info_line(
    monkeypatch, capsys
):
    """A default (English-only) run over a tree that contains locale
    directories must NOT emit one stderr warning per excluded directory --
    the old per-directory warnings made every default run noisy. The
    exclusion is reported as exactly ONE informational stdout line (3-space
    progress indent, the reporting module's style) naming the excluded
    directories, and stderr stays clean. GITHUB_TOKEN is set so the
    git-tree client builds an authenticated request and cannot emit its own
    one-time unauthenticated-API warning on stderr (which would otherwise
    make the no-warning assertion order-dependent)."""
    prefix = "packages/web/src/content/docs"
    monkeypatch.setenv("GITHUB_TOKEN", "test-token")
    client = tree_client(
        [
            blob_entry(f"{prefix}/index.mdx"),  # keep -> "intro"
            blob_entry(f"{prefix}/ja/index.mdx"),  # excluded: Japanese locale
            blob_entry(f"{prefix}/zh-cn/getting-started.mdx"),  # excluded: Chinese
        ]
    )
    pages = opencode.discover(client)
    assert [p.slug for p in pages] == ["intro"]
    captured = capsys.readouterr()
    assert captured.out.splitlines() == [
        "   excluding non-English locale directories: ja, zh-cn (English-only mirror)"
    ]
    assert "warning" not in captured.err


def test_discover_mirrors_selected_locale_pages(monkeypatch, capsys):
    """With locales=("pt-br",) the pages under the ``pt-br`` directory are
    mirrored in addition to the English pages, each namespaced under its
    locale code (``pt-br/cli``), while an unrequested locale directory that
    IS present in the tree (``es/``) stays excluded. The locale's own
    ``index.mdx`` is the translated landing page and maps to
    ``pt-br/intro`` (mirroring the English root index -> ``intro`` rule);
    every locale page groups under its locale code, keeps the English
    ``source_url`` scheme with the locale slug appended, and points its
    ``source_md_url`` at the raw file in the locale directory. One
    informational line reports the mirrored directory; stderr stays clean."""
    prefix = "packages/web/src/content/docs"
    monkeypatch.setenv("GITHUB_TOKEN", "test-token")
    client = tree_client(
        [
            blob_entry(f"{prefix}/config.mdx"),  # keep -> "config"
            blob_entry(f"{prefix}/index.mdx"),  # keep -> "intro"
            blob_entry(f"{prefix}/cli.mdx"),  # keep -> "cli"
            blob_entry(f"{prefix}/es/index.mdx"),  # excluded: not requested
            blob_entry(f"{prefix}/es/overview.mdx"),  # excluded: not requested
            blob_entry(f"{prefix}/pt-br/index.mdx"),  # keep -> "pt-br/intro"
            blob_entry(f"{prefix}/pt-br/cli.mdx"),  # keep -> "pt-br/cli"
            blob_entry(f"{prefix}/pt-br/config.mdx"),  # keep -> "pt-br/config"
        ]
    )
    pages = opencode.discover(client, locales=("pt-br",))
    assert [p.slug for p in pages] == [
        "cli",
        "config",
        "intro",
        "pt-br/cli",
        "pt-br/config",
        "pt-br/intro",
    ]
    by_slug = {p.slug: p for p in pages}
    ptbr_cli = by_slug["pt-br/cli"]
    assert ptbr_cli.group == "pt-br"
    assert ptbr_cli.source_url == "https://opencode.ai/docs/pt-br/cli"
    assert ptbr_cli.source_id == f"{prefix}/pt-br/cli.mdx"
    assert ptbr_cli.source_md_url == (
        "https://raw.githubusercontent.com/anomalyco/opencode/dev/"
        f"{prefix}/pt-br/cli.mdx"
    )
    assert by_slug["pt-br/intro"].group == "pt-br"
    assert by_slug["pt-br/intro"].source_id == f"{prefix}/pt-br/index.mdx"
    assert all(not p.slug.startswith("es/") for p in pages)
    captured = capsys.readouterr()
    assert captured.out.splitlines() == ["   mirroring locale directories: pt-br"]
    assert "warning" not in captured.err


def test_discover_partial_locale_translation_is_graceful(monkeypatch, capsys):
    """A locale directory that translates only PART of the English docs
    (upstream omits pages it has not translated yet) must not fail or warn:
    with only ``pt-br/cli.mdx`` present -- no ``pt-br/index.mdx`` -- the
    run still mirrors the English pages plus the one translated page."""
    prefix = "packages/web/src/content/docs"
    monkeypatch.setenv("GITHUB_TOKEN", "test-token")
    client = tree_client(
        [
            blob_entry(f"{prefix}/index.mdx"),  # keep -> "intro"
            blob_entry(f"{prefix}/cli.mdx"),  # keep -> "cli"
            blob_entry(f"{prefix}/pt-br/cli.mdx"),  # the only translated page
        ]
    )
    pages = opencode.discover(client, locales=("pt-br",))
    assert [p.slug for p in pages] == ["cli", "intro", "pt-br/cli"]
    captured = capsys.readouterr()
    assert "mirroring locale directories: pt-br" in captured.out
    assert "warning" not in captured.err


def test_discover_warns_when_requested_locale_is_absent(monkeypatch, capsys):
    """A requested locale with NO directory in the upstream tree must be
    called out with a stderr warning -- the request silently mirrored
    nothing for it -- without failing the run or disturbing the English
    pages, and without claiming anything was mirrored."""
    prefix = "packages/web/src/content/docs"
    monkeypatch.setenv("GITHUB_TOKEN", "test-token")
    client = tree_client([blob_entry(f"{prefix}/index.mdx")])
    pages = opencode.discover(client, locales=("ja",))
    assert [p.slug for p in pages] == ["intro"]
    captured = capsys.readouterr()
    assert "mirroring locale directories" not in captured.out
    assert "warning" in captured.err
    assert "'ja'" in captured.err


def test_discover_locale_pages_support_extra_nesting_and_nested_indexes():
    """Pages nested deeper inside a locale directory follow the English
    slug rules with the locale prefix prepended: a nested directory route
    (``pt-br/guides/index.mdx`` -> ``pt-br/guides``), its pages
    (``pt-br/guides/install.mdx`` -> ``pt-br/guides/install``), and a
    deeper page (``pt-br/advanced/usage.mdx`` -> ``pt-br/advanced/usage``)
    are all mirrored, and the group of every locale page is its locale
    code."""
    prefix = "packages/web/src/content/docs"
    client = tree_client(
        [
            blob_entry(f"{prefix}/index.mdx"),  # keep -> "intro"
            blob_entry(f"{prefix}/pt-br/index.mdx"),  # keep -> "pt-br/intro"
            blob_entry(f"{prefix}/pt-br/guides/index.mdx"),  # -> "pt-br/guides"
            blob_entry(
                f"{prefix}/pt-br/guides/install.mdx"
            ),  # -> "pt-br/guides/install"
            blob_entry(
                f"{prefix}/pt-br/advanced/usage.mdx"
            ),  # -> "pt-br/advanced/usage"
        ]
    )
    pages = opencode.discover(client, locales=("pt-br",))
    assert [p.slug for p in pages] == [
        "intro",
        "pt-br/advanced/usage",
        "pt-br/guides",
        "pt-br/guides/install",
        "pt-br/intro",
    ]
    assert all(p.group == "pt-br" for p in pages if "/" in p.slug)


def test_discover_reads_run_scoped_locale_selection_from_config(monkeypatch, capsys):
    """``discover(client)`` without an explicit ``locales`` argument falls
    back to the run-scoped holder ``config.ACTIVE_LOCALES`` -- the channel
    the CLI's ``--locales`` flag writes before calling ``pipeline.run``.
    This is the exact plumbing a live ``mirror-docs --locales pt-br`` run
    uses, and the reset fixture in conftest keeps the holder at ``None``
    between tests."""
    from mirror import config

    prefix = "packages/web/src/content/docs"
    monkeypatch.setenv("GITHUB_TOKEN", "test-token")
    monkeypatch.setattr(config, "ACTIVE_LOCALES", ("pt-br",))
    client = tree_client(
        [
            blob_entry(f"{prefix}/index.mdx"),  # keep -> "intro"
            blob_entry(f"{prefix}/pt-br/cli.mdx"),  # keep -> "pt-br/cli"
            blob_entry(f"{prefix}/pt-br/index.mdx"),  # keep -> "pt-br/intro"
        ]
    )
    pages = opencode.discover(client)
    assert [p.slug for p in pages] == ["intro", "pt-br/cli", "pt-br/intro"]
    captured = capsys.readouterr()
    assert "mirroring locale directories: pt-br" in captured.out
    assert "warning" not in captured.err


def test_discover_explicit_locales_argument_overrides_config_holder(monkeypatch):
    """The explicit ``locales`` argument must always win over the run-scoped
    config holder -- the precedence promised by the discover docstring's
    call contract, so the future pipeline wiring that passes the selection
    explicitly can never be disturbed by a stale holder."""
    from mirror import config

    prefix = "packages/web/src/content/docs"
    monkeypatch.setattr(config, "ACTIVE_LOCALES", ("pt-br",))
    client = tree_client(
        [
            blob_entry(f"{prefix}/index.mdx"),  # keep -> "intro"
            blob_entry(f"{prefix}/es/overview.mdx"),  # keep (es requested below)
        ]
    )
    pages = opencode.discover(client, locales=("es",))
    assert [p.slug for p in pages] == ["es/overview", "intro"]


def test_discover_empty_locales_tuple_mirrors_english_only(monkeypatch, capsys):
    """``locales=()`` is equivalent to ``locales=None``: an empty selection
    cannot request anything, so the run stays English-only and reports the
    excluded locale directories with the standard informational line."""
    prefix = "packages/web/src/content/docs"
    monkeypatch.setenv("GITHUB_TOKEN", "test-token")
    client = tree_client(
        [
            blob_entry(f"{prefix}/index.mdx"),  # keep -> "intro"
            blob_entry(f"{prefix}/pt-br/cli.mdx"),  # excluded: empty selection
        ]
    )
    pages = opencode.discover(client, locales=())
    assert [p.slug for p in pages] == ["intro"]
    captured = capsys.readouterr()
    assert "excluding non-English locale directories: pt-br" in captured.out
    assert "warning" not in captured.err


def test_discover_dedupes_colliding_slugs(capsys):
    """``foo.md`` and ``foo.mdx`` both map to slug ``foo`` -- the slug IS the
    output path, so two ``Page`` objects for it would fight over one
    mirrored file. Only the first tree entry may win; the later one is
    skipped with a loud stderr warning naming the slug."""
    prefix = "packages/web/src/content/docs"
    client = tree_client(
        [
            blob_entry(f"{prefix}/foo.md"),
            blob_entry(f"{prefix}/foo.mdx"),
        ]
    )
    pages = opencode.discover(client)
    assert [p.slug for p in pages] == ["foo"]
    err = capsys.readouterr().err
    assert "warning" in err
    assert "duplicate slug" in err
    assert "'foo'" in err


def test_discover_normalises_nested_index_and_readme_to_directory_route():
    """A nested ``cli/index.mdx`` must collapse to slug ``cli`` (the site
    serves that page at ``/docs/cli`` -- keeping the trailing ``/index``
    segment would produce a ``source_url`` that 404s). The same
    normalisation applies to a nested ``README.md``, mirroring the root
    ``index`` / ``README`` -> ``"intro"`` mapping. The group, however, is
    derived from the RAW path, so a section landing page stays grouped
    with its own section (``cli``) rather than being hoisted into the
    ``root`` group by the normalisation."""
    prefix = "packages/web/src/content/docs"
    client = tree_client(
        [
            blob_entry(f"{prefix}/cli/index.mdx"),
            blob_entry(f"{prefix}/sdk/README.md"),
        ]
    )
    pages = opencode.discover(client)
    by_slug = {p.slug: p for p in pages}
    assert set(by_slug) == {"cli", "sdk"}
    assert by_slug["cli"].source_url == "https://opencode.ai/docs/cli"
    assert by_slug["sdk"].source_url == "https://opencode.ai/docs/sdk"
    assert by_slug["cli"].group == "cli"


def test_discover_nested_slugs_get_correct_group():
    """Nested paths (e.g. ``getting-started/overview``) must have their
    first segment as the group, while root-level slugs get ``"root"``."""
    prefix = "packages/web/src/content/docs"
    client = tree_client(
        [
            blob_entry(f"{prefix}/getting-started/overview.mdx"),
            blob_entry(f"{prefix}/configuration/settings.mdx"),
            blob_entry(f"{prefix}/index.mdx"),
        ]
    )
    pages = opencode.discover(client)
    by_slug = {p.slug: p for p in pages}
    assert by_slug["getting-started/overview"].group == "getting-started"
    assert by_slug["configuration/settings"].group == "configuration"
    assert by_slug["intro"].group == "root"


def test_discover_source_md_url_points_to_raw_github():
    """The ``source_md_url`` must point to ``raw.githubusercontent.com`` so
    the pipeline can download the raw file content."""
    prefix = "packages/web/src/content/docs"
    client = tree_client([blob_entry(f"{prefix}/index.mdx")])
    pages = opencode.discover(client)
    assert pages[0].source_md_url == (
        "https://raw.githubusercontent.com/anomalyco/opencode/dev/"
        "packages/web/src/content/docs/index.mdx"
    )


def test_discover_source_url_points_to_docs_site():
    """The human-facing ``source_url`` must point to ``opencode.ai/docs``,
    not to a GitHub blob URL -- that is where readers consume these docs."""
    prefix = "packages/web/src/content/docs"
    client = tree_client([blob_entry(f"{prefix}/getting-started/overview.mdx")])
    pages = opencode.discover(client)
    assert pages[0].source_url == ("https://opencode.ai/docs/getting-started/overview")


def test_discover_sorts_pages_by_slug():
    """Pages must be returned sorted by slug so the output is deterministic
    across runs."""
    prefix = "packages/web/src/content/docs"
    client = tree_client(
        [
            blob_entry(f"{prefix}/configuration/settings.mdx"),
            blob_entry(f"{prefix}/getting-started/overview.mdx"),
            blob_entry(f"{prefix}/index.mdx"),
        ]
    )
    pages = opencode.discover(client)
    slugs = [p.slug for p in pages]
    # Assert the exact expected list rather than a self-referential
    # sortedness check: comparing against the literal list pins BOTH the
    # completeness of the result (a missing or extra page fails) AND the
    # ascending sort order in a single assertion.
    assert slugs == ["configuration/settings", "getting-started/overview", "intro"]


# --- Zero-page guard ----------------------------------------------------------


def test_discover_raises_on_zero_pages():
    """When no file matches the filter (e.g. the upstream moved its docs
    tree), discovery must raise ``RuntimeError`` -- returning ``[]`` would
    make the pipeline delete every mirrored file."""
    client = tree_client([blob_entry("README.md")])  # outside DOCS_PREFIX
    with pytest.raises(RuntimeError, match="zero-page"):
        opencode.discover(client)


def test_discover_raises_on_truncated_tree():
    """A ``"truncated": true`` git-trees response must raise, not return a
    partial page list: incomplete discovery would delete pages from disk."""
    prefix = "packages/web/src/content/docs"
    client = tree_client([blob_entry(f"{prefix}/index.mdx")], truncated=True)
    with pytest.raises(RuntimeError, match="anomalyco/opencode"):
        opencode.discover(client)


# --- Fetch error propagation --------------------------------------------------


def test_discover_surfaces_fetch_error_on_404():
    """A 404 on the tree-listing call must surface as a ``FetchError``
    carrying the structured status code -- not as a confusing downstream
    crash. A 404 (renamed repo or branch) is NOT a rate limit, so it must
    come back without the GITHUB_TOKEN hint appended."""
    client = _FakeClient([_Resp(404)])
    with pytest.raises(fetch.FetchError) as exc_info:
        opencode.discover(client)
    assert exc_info.value.status_code == 404
    assert "GITHUB_TOKEN" not in str(exc_info.value)


# --- MDX-to-Markdown conversion -----------------------------------------------


def test_mdx_to_md_strips_import_statements():
    """Top-level ``import`` and ``export`` statements must be removed
    from the output -- they are Astro/Starlight component wiring with
    no meaning in a plain Markdown reader."""
    mdx = """---
title: Getting Started
---
import { Tabs, TabItem } from '@/components/tabs';
import Callout from '@/components/callout.astro';

## Overview

This is a guide.
"""
    md = opencode._mdx_to_md(mdx)
    assert "import" not in md
    assert "export" not in md
    assert "title: Getting Started" in md  # frontmatter preserved
    assert "## Overview" in md
    assert "This is a guide." in md


def test_mdx_to_md_strips_only_first_line_of_multiline_import_export_blocks():
    """A multiline import/export block is stripped only up to its first line:
    the statement-opening line (``import {`` / ``export const foo = {``) is
    removed while the continuation lines survive as ordinary text. The strip
    is deliberately single-line (each candidate line is matched and removed
    in one bounded pass) so the regex stays linear on adversarial input --
    see the comment on ``_IMPORT_EXPORT_RE`` and the
    ``test_import_export_strip_is_linear_on_adversarial_input`` regression
    test. Upstream wiring statements are always single-line
    (``import { Tabs } from '@/components';``), which are removed whole."""
    mdx = """---
title: Getting Started
---
import {
  Tabs,
  TabItem
} from '@/components/tabs';

export const foo = {
  bar: "baz"
};

## Overview

This is a guide.
"""
    md = opencode._mdx_to_md(mdx)
    # The opening lines of both statements are removed ...
    assert "import {" not in md
    assert "export const foo" not in md
    # ... while the continuation lines survive as literal text.
    assert "Tabs" in md
    assert 'bar: "baz"' in md
    assert "title: Getting Started" in md
    assert "## Overview" in md
    assert "This is a guide." in md


def test_mdx_to_md_converts_callout_to_github_alert():
    """``<Callout type="note">`` must become ``> [!NOTE]`` and
    ``<Callout type="warning">`` must become ``> [!WARNING]``."""
    mdx = """## Section

<Callout type="note">
This is important information.
</Callout>

<Callout type="warning">
Be careful with this step.
</Callout>

More text.
"""
    md = opencode._mdx_to_md(mdx)
    assert "> [!NOTE]" in md
    assert "> [!WARNING]" in md
    assert "This is important information." in md
    assert "Be careful with this step." in md
    assert "</Callout>" not in md
    assert "## Section" in md
    assert "More text." in md


def test_mdx_to_md_converts_callout_with_reordered_attributes():
    """``<Callout title="..." type="warning">`` (type NOT the first
    attribute) must convert exactly like the canonical attribute order: the
    block regex matches the opening tag whatever its attribute list, and
    ``type`` / ``title`` are extracted order-independently. Without this,
    the callout body would leak through as unformatted text once the
    generic JSX tag strips removed the tags."""
    mdx = """## Section

<Callout title="Heads up" type="warning">
Be careful with this step.
</Callout>

More text.
"""
    md = opencode._mdx_to_md(mdx)
    assert "> [!WARNING]" in md
    assert "> **Heads up**" in md
    assert "> Be careful with this step." in md
    assert "</Callout>" not in md
    assert "More text." in md


def test_mdx_to_md_converts_callout_with_gt_inside_quoted_attribute():
    """A ``>`` character inside a quoted attribute value (e.g.
    ``title="A > B"``) must NOT terminate the opening-tag match: the block
    regex consumes quoted attribute values whole, so both double- and
    single-quoted values containing ``>`` convert correctly. With a naive
    ``[^>]*`` attribute pattern the tag match would stop at the ``>``
    inside the value, leaking raw JSX fragments (``B" type="warning">``)
    into the Markdown and losing the ``type`` attribute entirely."""
    mdx = """## Section

<Callout title="A > B" type="warning">
Be careful with this step.
</Callout>

<Callout title='x > y' type='tip'>
Single quotes work too.
</Callout>

More text.
"""
    md = opencode._mdx_to_md(mdx)
    assert "> [!WARNING]" in md
    assert "> **A > B**" in md
    assert "> Be careful with this step." in md
    assert "> [!TIP]" in md
    assert "> **x > y**" in md
    assert "> Single quotes work too." in md
    # No raw JSX fragment may leak: the part of the attribute value that
    # follows the embedded ``>`` must never appear as bare text.
    assert 'B" type="warning">' not in md
    assert "</Callout>" not in md
    assert "More text." in md


def test_mdx_to_md_jsx_callout_dedents_common_indent_preserving_nesting():
    """An indented ``<Callout>`` body must be dedented by its COMMON leading
    whitespace only -- never stripped line-by-line. A naive per-line
    ``strip()`` would collapse nested lists and indented code inside the
    callout to column zero, destroying their structure; the dedent (the same
    algorithm the Starlight ``:::`` converter uses) removes only the shared
    baseline indent, so lines indented DEEPER keep their relative
    indentation. Blank body lines become a bare ``>`` (no trailing
    whitespace), preserving paragraph breaks inside the blockquote."""
    mdx = """- Step one
  <Callout type="warning">
  Watch out:
    - nested bullet
        indented code line

  trailing line
  </Callout>
"""
    md = opencode._mdx_to_md(mdx)
    assert "> [!WARNING]" in md
    assert "> Watch out:" in md
    # The nested bullet keeps its 4-space indent relative to the baseline --
    # a stripping implementation would emit "> - nested bullet" instead.
    assert ">     - nested bullet" in md
    # The indented code line keeps its 8-space relative indent.
    assert ">         indented code line" in md
    # The blank body line becomes a bare ">" with no trailing whitespace.
    assert "\n>\n" in md
    assert "</Callout>" not in md


def test_mdx_to_md_jsx_callout_normalises_mixed_tabs_and_spaces():
    """A ``<Callout>`` body that mixes tabs and spaces must be measured on a
    consistent column basis: every body line goes through ``expandtabs()``
    before the common indent is computed, so a tab counts as several columns
    rather than a single character. The dedented output then contains the
    tab EXPANDED to spaces (a raw tab would survive untouched if the
    expansion were missing)."""
    mdx = (
        '<Callout type="note">\n'
        "\tTabbed line\n"
        "    \t- mixed indent bullet\n"
        "</Callout>\n"
    )
    md = opencode._mdx_to_md(mdx)
    assert "> [!NOTE]" in md
    assert "> Tabbed line" in md
    # "    \t" expands to 8 columns; the bullet keeps that relative indent
    # and no raw tab character survives in the output.
    assert ">         - mixed indent bullet" in md
    assert "        " in md


def test_mdx_to_md_strips_self_closing_jsx():
    """Self-closing JSX tags (``<Card title="X" />``, ``<Link href="Y" />``)
    must be removed."""
    mdx = """## Section
<Card title="Quickstart" />
<Link href="/docs/overview" />

Some text.
"""
    md = opencode._mdx_to_md(mdx)
    assert "<Card" not in md
    assert "<Link" not in md
    assert "Some text." in md


def test_mdx_to_md_strips_jsx_tags_with_gt_inside_quoted_attribute():
    """A ``>`` inside a quoted attribute value must NOT terminate the tag
    match: the shared quote-aware attribute pattern consumes quoted values
    whole, so a self-closing ``<Card title="A > B" />`` and an open/close
    pair ``<Card title="A > B">...</Card>`` are stripped completely.  With
    a naive ``[^>]*`` attribute pattern the match would stop at the ``>``
    inside the value, leaking the remainder (``B" />`` / ``B">``) as raw
    JSX fragments in the Markdown output."""
    mdx = """## Section

<Card title="A > B" />

<Card title="A > B">
Inner text survives.
</Card>

After.
"""
    md = opencode._mdx_to_md(mdx)
    assert "<Card" not in md
    assert "</Card>" not in md
    # No raw JSX fragment may leak: the part of the attribute value that
    # follows the embedded ``>`` must never appear as bare text.
    assert 'B" />' not in md
    assert 'B">' not in md
    # The open/close pair is stripped while its inner text is preserved.
    assert "Inner text survives." in md
    assert "After." in md


def test_mdx_to_md_strips_generic_jsx_wrappers_preserving_text():
    """Generic JSX wrapper tags (``<Tabs>``, ``<TabItem>``) must be stripped
    while their inner text content is preserved."""
    mdx = """## Installation

<Tabs>
<TabItem label="npm">

```bash
npm install opencode
```

</TabItem>
<TabItem label="yarn">

```bash
yarn add opencode
```

</TabItem>
</Tabs>

Done.
"""
    md = opencode._mdx_to_md(mdx)
    assert "## Installation" in md
    assert "npm install opencode" in md
    assert "yarn add opencode" in md
    assert "Done." in md
    # Wrapper tags must be gone and labels preserved.
    assert "**npm**" in md
    assert "**yarn**" in md
    for tag in ("<Tabs>", "</Tabs>", "<TabItem", "</TabItem>"):
        assert tag not in md


def test_mdx_to_md_strips_jsx_tags_with_double_braced_style_attributes():
    """Tags with double-braced attributes (e.g. style={{ color: 'red' }}) must be stripped.

    Verifies both self-closing (<Card style={{ ... }} />) and open/close pairs.
    """
    mdx = """## Styling

<Card style={{ marginTop: "1rem", color: "var(--sl-color-accent)" }} />

<Card style={{ padding: "20px", display: { sm: "block", md: "flex" } }}>
Styled text survives.
</Card>
"""
    md = opencode._mdx_to_md(mdx)
    assert "<Card" not in md
    assert "</Card>" not in md
    assert "style=" not in md
    assert "Styled text survives." in md


def test_mdx_to_md_converts_jsx_comments_to_html():
    """JSX comments (``{/* ... */}``) must be converted to HTML comments
    (``<!-- ... -->``)."""
    mdx = """## Section

Some text. {/* This is a note for editors */}

More text.
"""
    md = opencode._mdx_to_md(mdx)
    assert "<!-- This is a note for editors -->" in md
    assert "{/*" not in md


def test_mdx_to_md_sanitizes_double_hyphen_inside_jsx_comment():
    """A JSX comment whose body contains ``--`` must not produce an invalid
    HTML comment: the HTML spec forbids a double hyphen inside comment
    text, so wrapping ``{/* note -- draft */}`` naively would yield
    ``<!-- note -- draft -->``, which strict HTML parsers terminate early
    or reject. The converter rewrites every ``--`` in the body to ``==``
    (visible and plain-text safe; character references such as ``&#45;``
    are NOT decoded inside HTML comments, so they would read as literal
    gibberish in the Markdown source)."""
    mdx = """## Section

Some text. {/* note -- draft */}

More text.
"""
    md = opencode._mdx_to_md(mdx)
    assert "<!-- note == draft -->" in md
    assert "<!-- note -- draft -->" not in md
    assert "{/*" not in md


def test_mdx_to_md_collapses_excess_blank_lines():
    """After stripping import blocks and JSX wrappers, runs of 3+ blank
    lines must be collapsed to at most 2, keeping the output tidy."""
    mdx = """---
title: Test
---
import { Foo } from 'bar';



## Heading



Paragraph.
"""
    md = opencode._mdx_to_md(mdx)
    assert "\n\n\n\n" not in md
    assert "## Heading" in md
    assert "Paragraph." in md


def test_mdx_to_md_preserves_code_blocks():
    """Fenced code blocks and their content must survive the conversion
    completely intact -- backticks, language tags, and content."""
    mdx = """## Example

```python
def hello():
    print("Hello, world!")
```

```bash
echo "test"
```
"""
    md = opencode._mdx_to_md(mdx)
    assert '```python\ndef hello():\n    print("Hello, world!")\n```' in md
    assert '```bash\necho "test"\n```' in md


def test_mdx_to_md_preserves_fenced_code_with_imports_exports_and_jsx():
    """Fenced code blocks must be preserved verbatim even when their contents
    look like MDX wiring -- a JS/TS sample containing top-level ``import`` /
    ``export`` lines, and a JSX tag such as ``<MyComponent/>``, are CODE, so
    they must not be stripped or rewritten by the import/export pass or the
    JSX tag strips.  Both the triple-backtick and triple-tilde fence styles
    are covered, and a top-level (non-fenced) import is still stripped in the
    same document to confirm the protection is scoped to fenced blocks only.
    """
    mdx = """## Example

```js
import express from "express";
export default function() {}
const x = 1;
```

~~~tsx
<MyComponent/>
~~~

import { TopLevel } from '@/components';

After.
"""
    md = opencode._mdx_to_md(mdx)
    # The fenced JS sample survives byte-for-byte: the import/export strip
    # must not reach inside the triple-backtick fence.
    assert 'import express from "express";' in md
    assert "export default function() {}" in md
    assert "const x = 1;" in md
    # The fenced JSX tag survives verbatim: the self-closing JSX strip must
    # not reach inside the triple-tilde fence.
    assert "<MyComponent/>" in md
    # The top-level (non-fenced) import is still stripped, confirming the
    # protection is scoped to fenced blocks only.
    assert "TopLevel" not in md
    assert "After." in md


def test_mdx_to_md_preserves_blank_runs_and_indent_only_lines_inside_code():
    """A fenced code block containing 2+ consecutive blank lines AND an
    indentation-only line must round-trip byte-identical: the trailing
    whitespace cleanup (steps 7-8) runs while the code is still lifted out
    into placeholders, so it can never blank an indentation-only line or
    collapse a blank run that is semantically significant inside a sample.
    Prose OUTSIDE the fence is still cleaned (the 3-blank-line gap before
    the trailing paragraph collapses to one blank line)."""
    code_block = (
        "```python\nimport os\n\n\n\ndef f():\n    pass\n    \n    return 1\n```"
    )
    mdx = f"## Example\n\n{code_block}\n\n\n\nAfter.\n"
    md = opencode._mdx_to_md(mdx)
    # The code block survives byte-for-byte: the blank run and the
    # indentation-only line inside the fence are untouched.
    assert code_block in md
    # The prose cleanup still applies outside the fence: the 3-blank-line
    # gap between the fence and the trailing paragraph collapses to one.
    assert "```\n\nAfter." in md


def test_mdx_to_md_preserves_frontmatter():
    """YAML frontmatter delimited by ``---`` must survive intact --
    the mirror preserves it for downstream consumers."""
    mdx = """---
title: Configuration Guide
description: Learn how to configure OpenCode
---

## Getting Started
"""
    md = opencode._mdx_to_md(mdx)
    assert md.startswith("---\ntitle: Configuration Guide\n")
    assert "description: Learn how to configure OpenCode" in md


def test_mdx_to_md_preserves_standard_html():
    """Standard HTML elements (``<div>``, ``<a>``, ``<code>``, ``<img>``)
    must NOT be stripped -- only JSX components (capitalised tag names)
    are removed."""
    mdx = """## Section

<div class="container">

Some text with a <a href="/link">link</a> and
<code>inline code</code>.

</div>
"""
    md = opencode._mdx_to_md(mdx)
    assert '<div class="container">' in md
    assert '<a href="/link">link</a>' in md
    assert "<code>inline code</code>" in md
    assert "</div>" in md


# --- Starlight ``:::`` callout conversion -------------------------------------


def test_mdx_to_md_converts_starlight_note_to_github_alert():
    """A ``:::note`` block must become a ``> [!NOTE]`` GitHub Alert block
    quote with every body line prefixed by ``> ``."""
    mdx = """## Section

:::note
This is a note with important information.
It can span multiple lines.
:::

After the callout.
"""
    md = opencode._mdx_to_md(mdx)
    assert "> [!NOTE]" in md
    assert "> This is a note with important information." in md
    assert "> It can span multiple lines." in md
    assert ":::" not in md
    assert "After the callout." in md
    assert "## Section" in md


def test_mdx_to_md_converts_starlight_tip_with_title():
    """A ``:::tip[Title]`` block must produce ``> [!TIP]`` followed by
    ``> **Title**`` as a bold heading line."""
    mdx = """## Section

:::tip[Recommended Approach]
Use the install script for the easiest setup experience.
:::

Done.
"""
    md = opencode._mdx_to_md(mdx)
    assert "> [!TIP]" in md
    assert "> **Recommended Approach**" in md
    assert "> Use the install script" in md
    assert "Done." in md


def test_mdx_to_md_converts_starlight_warning():
    """A ``:::warning`` block must become ``> [!WARNING]``."""
    mdx = """:::warning
Be careful with this step. You might delete data.
:::
"""
    md = opencode._mdx_to_md(mdx)
    assert "> [!WARNING]" in md
    assert "> Be careful with this step." in md


def test_mdx_to_md_converts_danger_callouts_to_caution_alert():
    """GitHub Alerts support only NOTE/TIP/IMPORTANT/WARNING/CAUTION, so
    Starlight's ``danger`` type -- in BOTH the ``:::danger`` fence syntax
    and the ``<Callout type="danger">`` JSX form -- must map to the closest
    supported label, ``CAUTION``.  Emitting ``> [!DANGER]`` would render as
    a plain blockquote on GitHub and the alert would be silently lost."""
    mdx = """## Section

:::danger
This action is irreversible.
:::

<Callout type="danger">
Think twice before running this.
</Callout>

After.
"""
    md = opencode._mdx_to_md(mdx)
    assert md.count("> [!CAUTION]") == 2
    assert "[!DANGER]" not in md
    assert "> This action is irreversible." in md
    assert "> Think twice before running this." in md
    assert "After." in md


def test_mdx_to_md_preserves_import_line_inside_callout_body():
    """An unfenced ``import ...`` line inside a ``:::note`` body is content
    (a snippet quoted for the reader), not component wiring, and must
    survive: the callout conversion runs BEFORE the import/export strip, so
    by the time the line-anchored import pattern runs, the line already
    carries a ``> `` blockquote prefix and no longer matches.  A top-level
    wiring import in the same document is still stripped, confirming the
    strip itself remains active."""
    mdx = """import { Callout } from '@/components';

## Section

:::note
import { defineConfig } from 'opencode';
Use this import in your config file.
:::

After.
"""
    md = opencode._mdx_to_md(mdx)
    # The import quoted inside the note survives, wrapped as alert content.
    assert "> import { defineConfig } from 'opencode';" in md
    assert "> [!NOTE]" in md
    # The top-level wiring import is still stripped.
    assert "@/components" not in md
    assert "After." in md


def test_mdx_to_md_handles_multiple_starlight_callouts():
    """Multiple ``:::`` callout blocks in the same page must each be
    converted independently."""
    mdx = """## Section

:::note
First note.
:::

Some prose.

:::tip[Pro Tip]
Second callout with a title.
:::
"""
    md = opencode._mdx_to_md(mdx)
    assert md.count("> [!NOTE]") == 1
    assert md.count("> [!TIP]") == 1
    assert "> First note." in md
    assert "> **Pro Tip**" in md
    assert "Some prose." in md


def test_mdx_to_md_starlight_callout_preserves_blank_lines():
    """Blank lines inside a ``:::`` callout must be preserved as empty
    ``>`` quote lines (``>``), maintaining paragraph separation."""
    mdx = """:::note
Paragraph one.

Paragraph two.
:::
"""
    md = opencode._mdx_to_md(mdx)
    assert "> Paragraph one." in md
    assert "> Paragraph two." in md
    # There must be an empty ``>`` line between the two paragraphs.
    assert "\n>\n>" in md or "> \n>" in md


def test_mdx_to_md_converts_indented_starlight_callout():
    """A ``:::note`` block indented inside a list item must still be
    converted -- the closing ``:::`` may have leading whitespace."""
    mdx = """- Point one.
- Point two.
  :::note
  This is an indented note inside a list.
  :::
- Point three.
"""
    md = opencode._mdx_to_md(mdx)
    assert "> [!NOTE]" in md
    assert "> This is an indented note inside a list." in md
    assert ":::" not in md
    assert "- Point three." in md


def test_mdx_to_md_converts_multi_level_nested_starlight_callout():
    """A :::note block deeply indented (e.g. multi-level list) must correctly
    deduce indentation via min() to strip the baseline whitespace, preserving
    relative inner indentation."""
    mdx = """- Level 1
  - Level 2
    - Level 3
      :::note
      This is a nested note.
      
        This line is intentionally indented further.
      
      Back to normal.
      :::
- End.
"""
    md = opencode._mdx_to_md(mdx)
    assert "> [!NOTE]" in md
    assert "> This is a nested note." in md
    assert ">\n>   This line is intentionally indented further." in md
    assert "> Back to normal." in md
    assert ":::" not in md
    assert "- Level 3" in md
    assert "- End." in md


def test_mdx_to_md_converts_four_colon_callout():
    """A ``::::tip`` block (4 colons, used by Starlight for nested callouts)
    must be converted exactly like the 3-colon variant."""
    mdx = """## Section

::::tip
If you are new, we recommend starting here.
::::

After.
"""
    md = opencode._mdx_to_md(mdx)
    assert "> [!TIP]" in md
    assert "> If you are new, we recommend starting here." in md
    assert ":::" not in md
    assert "After." in md


def test_mdx_to_md_converts_starlight_callout_at_eof_without_trailing_newline():
    """A ``:::`` callout whose closing fence is the very last line of the
    file (no trailing newline before EOF) must still be converted: the raw
    fences must never leak into the mirrored Markdown just because the file
    ends abruptly."""
    mdx = "## Section\n\n:::note\nThis note ends the file.\n:::"
    md = opencode._mdx_to_md(mdx)
    assert "> [!NOTE]" in md
    assert "> This note ends the file." in md
    assert ":::" not in md


def test_mdx_to_md_converts_unclosed_starlight_callout_terminated_by_eof():
    """A callout that runs to the end of the file with NO closing fence at
    all is terminated by end-of-string (the ``\\Z`` fallback in the block
    pattern) and converted, rather than leaking its raw opening fence.
    ``\\Z`` -- not ``$`` -- is used for this so the fallback can only fire
    at the true end of the document: under ``re.MULTILINE``, ``$`` matches
    before every newline, which would let an unclosed callout in the MIDDLE
    of a page swallow text one line at a time."""
    mdx = "## Section\n\n:::warning\nThis warning is cut off by EOF."
    md = opencode._mdx_to_md(mdx)
    assert "> [!WARNING]" in md
    assert "> This warning is cut off by EOF." in md
    assert ":::" not in md


# --- Whitespace-only line cleanup ---------------------------------------------


def test_mdx_to_md_strips_whitespace_only_lines():
    """Lines containing only spaces/tabs (a common artefact after stripping
    indented JSX wrappers) must be removed from the output."""
    mdx = """## Installation

<Tabs>
<TabItem label="npm">

```bash
npm install opencode
```

</TabItem>
</Tabs>

Done.
"""
    md = opencode._mdx_to_md(mdx)
    # Whitespace-only lines must be gone.
    for line in md.splitlines():
        if line:
            assert line.strip(), f"whitespace-only line survived: {line!r}"
    assert "npm install opencode" in md
    assert "Done." in md


# --- fetch_markdown hook ------------------------------------------------------


def _make_opencode_page(slug="getting-started"):
    """Build a real ``Page`` for use in ``fetch_markdown`` tests."""
    prefix = "packages/web/src/content/docs"
    return Page(
        slug=slug,
        source_url=f"https://opencode.ai/docs/{slug}",
        source_md_url=(
            f"https://raw.githubusercontent.com/anomalyco/opencode/dev/"
            f"{prefix}/{slug}.mdx"
        ),
        source_id=f"{prefix}/{slug}.mdx",
        group="root",
    )


def test_fetch_markdown_returns_markdown_and_hash():
    """The happy path: raw MDX is fetched, converted to Markdown, and
    returned as a ``(markdown, sha256_hash)`` tuple."""
    mdx_body = """---
title: Overview
---
import { Callout } from '@/components';

## Getting Started

<Callout type="note">
This is a note.
</Callout>

Some prose.
"""
    client = _FakeClient([_Resp(200, mdx_body)])
    page = _make_opencode_page("overview")
    md, digest = opencode.fetch_markdown(client, page)
    assert "## Getting Started" in md
    assert "> [!NOTE]" in md
    assert "Some prose." in md
    assert "import" not in md
    assert digest == fetch.content_hash(md)


def test_import_export_strip_is_linear_on_adversarial_input():
    r"""A large body whose lines ALL start with ``import``/``export`` and
    carry no terminating semicolon must be stripped in linear time. The
    earlier cross-line lazy pattern (``[\s\S]*?``) re-scanned the whole
    document tail from every candidate line -- quadratic on N such lines,
    i.e. minutes on this input; the single-line pattern bounds every match
    attempt to its own line. Like the other pathological-input tests in the
    suite, no timing is asserted: a regression to the quadratic form would
    fail by extreme slowness rather than by a wrong assertion."""
    body = "\n".join(["import { Component } from '@/components'"] * 20_000)
    md = opencode._mdx_to_md(body)
    assert "import" not in md
    assert "Component" not in md


def test_fetch_markdown_rejects_non_markdown():
    """If the converted text fails Markdown validation (e.g. an empty or
    garbage response), ``FetchError`` must be raised so the pipeline carries
    the previous manifest entry forward instead of writing garbage."""
    client = _FakeClient([_Resp(200, "not markdown at all")])
    page = _make_opencode_page("bad")
    with pytest.raises(fetch.FetchError):
        opencode.fetch_markdown(client, page)
