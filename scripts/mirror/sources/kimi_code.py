"""Source: Kimi Code.

Kimi Code's documentation is already Markdown in the public GitHub repo
`MoonshotAI/kimi-code` under `docs/en/` (it's a VitePress site). We list that
tree via the GitHub API (one call) and download each `.md` from
`raw.githubusercontent.com`. No whats-new for this source.

This adapter shares its discovery mechanics with ``codex_cli.py``: both list
a GitHub repo's file tree via ``core.github.fetch_git_tree`` (which owns the
rate-limited API call, the rate-limit error mapping, and the truncation
guard) and download raw file content from ``raw.githubusercontent.com``. What
differs is only the per-source configuration and filtering:

* the docs tree is *nested* (e.g. ``docs/en/configuration/config-files.md``),
  so discovery recurses into subfolders instead of keeping only direct
  children, and the slug's first path segment becomes the index group;
* the human-facing ``source_url`` is the public site
  (https://www.kimi.com/code/docs/en/...) rather than a GitHub blob URL,
  because that is where readers actually consume these docs.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from ..core.github import fetch_git_tree, fetch_latest_release_tag
from ..core.media import AssetSourceConfig
from ..core.page import Page
from .base import SourceConfig, try_make_page, warn_duplicate_slug

if TYPE_CHECKING:
    # Annotation-only import: ``from __future__ import annotations`` keeps the
    # ``httpx.Client`` annotations from being evaluated at runtime.
    import httpx

# Upstream repository + derived URLs. Kept local to this source rather than
# in the shared config.py, so config.py stays source-agnostic.
REPO = "MoonshotAI/kimi-code"
BRANCH = "main"
DOCS_PREFIX = "docs/en"  # English docs live here in the upstream repo
# raw.githubusercontent.com serves the unprocessed file content -- this is
# what the pipeline actually downloads for each page.
# Using raw.githubusercontent.com for content fetching is a deliberate
# choice to avoid GitHub REST API rate limits. The Git Blob REST API endpoint
# imposes strict rate limits (e.g., 60 requests per hour for unauthenticated
# users). In contrast, raw.githubusercontent.com is largely unmetered for
# fetching static file content, allowing us to download hundreds of markdown
# files rapidly without hitting API caps or requiring authentication tokens.
RAW_BASE = f"https://raw.githubusercontent.com/{REPO}/{BRANCH}"
# Human-facing docs site; mirrored files link here as their "source".
SOURCE_URL_BASE = "https://www.kimi.com/code/docs/en"

# Static-asset rules for the pipeline's media stage. Several docs pages embed
# screenshots via relative refs of the shape ``../../media/<file>`` -- those
# resolve upstream to ``docs/media/`` (a sibling of ``docs/en/``), but in the
# mirror they point nowhere. The media stage downloads each referenced asset
# into ``docs/kimi-code/media/`` (write-only-what-changed, hashed), rewrites
# the in-page refs to resolve from the mirrored page location, and prunes
# assets no page references anymore.
MEDIA = AssetSourceConfig(
    name="kimi-code",
    asset_subdir="media",
    ref_prefixes=("../../media/",),
    raw_base_url=f"{RAW_BASE}/docs/media/",
)

CONFIG = SourceConfig(
    name="kimi-code",
    title="Kimi Code",
    home_url=SOURCE_URL_BASE,
    generate_whats_new=False,
    version="0.36.1",
    origin=f"github.com/{REPO} (`docs/en/`)",
    how_mirrored="scraping (GitHub tree → `raw.githubusercontent.com`)",
)


def get_version(client: httpx.Client) -> str | None:
    """Query the GitHub API for the latest release tag of Kimi Code."""
    return fetch_latest_release_tag(client, repo=REPO)


def discover(client: httpx.Client) -> list[Page]:
    """Discover all English docs pages from the repo's git tree.

    Lists the full tree of ``MoonshotAI/kimi-code@main`` in one API call
    (via ``core.github.fetch_git_tree``, which also enforces the rate-limit
    and truncation safety guards) and keeps every Markdown file anywhere
    under ``docs/en/`` (unlike the Codex adapter, nesting is expected:
    subfolders map to index groups). The slug is the path relative to
    ``docs/en/`` without ``.md`` (e.g. ``"configuration/config-files"``),
    and ``source_id`` is the full repo path -- stable across content edits,
    so it doubles as the pipeline's rename-detection key. The human-facing
    ``source_url`` follows the site's VitePress routing: an ``index.md``
    page (root or nested) maps to its directory route
    (``.../docs/en/`` or ``.../docs/en/<dir>/``) rather than a literal
    ``.../index`` URL. Slugs are deduplicated with a ``seen`` set (first
    entry wins, later duplicates are skipped with a stderr warning) as
    defense in depth against duplicate paths in the git tree listing --
    the same guard the Codex adapter applies.

    Raises ``RuntimeError`` when discovery finds zero pages: an empty result
    would make the pipeline diff "nothing discovered" against the previous
    manifest and delete every mirrored file, so a total filter miss (e.g.
    the upstream moved its docs out of ``docs/en/``) must be a loud error,
    not silent data loss.
    """
    tree = fetch_git_tree(client, repo=REPO, branch=BRANCH)

    pages: list[Page] = []
    # Slugs already claimed by an earlier tree entry, backing the duplicate
    # guard below.  Distinct from ``pages`` membership so the lookup stays
    # O(1) regardless of how many pages have been collected.
    seen: set[str] = set()
    for entry in tree:
        if entry.get("type") != "blob":
            continue  # skip directories ("tree" entries) and submodules
        path = entry.get("path", "")
        if not path.startswith(DOCS_PREFIX + "/") or not path.endswith(".md"):
            continue
        rel = path[len(DOCS_PREFIX) + 1 :]  # e.g. "configuration/config-files.md"
        # Strip the trailing ".md" file extension to derive the slug.
        # ``rel`` is guaranteed to end with ".md" by the combined guard
        # on the line above (``path.startswith(...) and path.endswith(".md")``),
        # so the ``-3`` slice always removes exactly the three extension
        # characters. The resulting slug preserves the upstream directory
        # structure (e.g. "configuration/config-files" from
        # "configuration/config-files.md") so the mirrored tree mirrors
        # the VitePress sidebar grouping one level down.
        slug = rel[:-3]
        # The slug IS the on-disk layout: the pipeline writes each page to
        # ``docs/kimi-code/<slug>.md``, so a nested upstream path like
        # ``docs/en/configuration/config-files.md`` lands at
        # ``docs/kimi-code/configuration/config-files.md`` -- the upstream
        # category directory structure is preserved one level down in the
        # mirror, and readers browsing the mirrored tree see the same
        # grouping the VitePress sidebar shows. The first slug segment
        # doubles as the index group (the section header in docs/README.md),
        # which is why nested categories matter here while the Codex adapter
        # (flat docs folder) can reject them outright.
        # A repo file named exactly ".md" (no basename) at the docs root
        # would yield an empty slug, which Page rejects with a ValueError
        # (caught by try_make_page below, where it would surface as a
        # spurious warning). Such a file carries no usable page identity, so
        # skip it quietly instead.
        if not slug:
            continue
        # Duplicate-slug guard (defense in depth), matching the codex_cli
        # adapter.  Here the slug is derived 1:1 from the repo path and the
        # git-trees API is not expected to list the same blob twice, so a
        # collision "cannot happen" -- but the slug IS the on-disk output
        # path, so if a duplicate ever did slip through (a malformed API
        # response, or a future slug-normalisation step that collapses two
        # distinct paths onto one slug), two ``Page`` objects would fight
        # over a single mirrored file.  Without this guard the duplicate
        # would instead trip the pipeline-level duplicate-slug check and
        # fail the whole source.  Keep the FIRST entry and skip the later
        # one with the shared loud stderr warning (``warn_duplicate_slug``
        # in ``sources/base.py``).
        if slug in seen:
            warn_duplicate_slug(slug, path)
            continue
        seen.add(slug)
        group = slug.split("/", 1)[0] if "/" in slug else "root"
        # The human-facing source URL follows the site's VitePress routing:
        # an ``index.md`` file is served at its DIRECTORY route (a clean
        # URL), not at a literal ``.../index`` path.  Upstream renders
        # ``docs/en/index.md`` at ``https://www.kimi.com/code/docs/en/`` and
        # a nested ``docs/en/guide/index.md`` at
        # ``https://www.kimi.com/code/docs/en/guide/`` -- a ``source_url``
        # built naively as ``base + "/" + slug`` would end in ``/index`` and
        # 404 (or redirect) on the live site.  Only the displayed source
        # link is normalised here; the SLUG itself is left untouched because
        # it keys the mirrored file layout (``docs/kimi-code/index.md``) and
        # the manifest, where the upstream path shape must stay visible.
        if slug == "index":
            source_url = f"{SOURCE_URL_BASE}/"
        elif slug.endswith("/index"):
            source_url = f"{SOURCE_URL_BASE}/{slug[: -len('/index')]}/"
        else:
            source_url = f"{SOURCE_URL_BASE}/{slug}"
        # Per-entry guard: a file path whose name falls outside the slug
        # alphabet (parentheses, unicode, spaces, ...) raises ValueError from
        # ``Page.__post_init__``. Without this guard, ONE such entry would
        # crash discovery for the entire Kimi Code source. ``try_make_page``
        # (see ``sources/base.py``) owns the guard/warning: the path is named
        # in a stderr warning and discovery continues with the remaining
        # entries.
        page = try_make_page(
            path,
            slug=slug,
            source_url=source_url,
            source_md_url=f"{RAW_BASE}/{path}",
            source_id=path,  # stable upstream GitHub path -> rename key
            group=group,
        )
        if page is not None:
            pages.append(page)
    pages.sort(key=lambda p: p.slug)
    # Zero-page guard (see the docstring): if every tree entry was filtered
    # out, the upstream almost certainly moved or renamed its docs tree.
    # Raising here -- with the exact filter values in the message -- beats
    # letting the pipeline delete the whole mirrored tree.
    if not pages:
        raise RuntimeError(
            f"No Markdown files found under {DOCS_PREFIX!r}/ in "
            f"{REPO}@{BRANCH}. A zero-page discovery would delete all "
            "mirrored files. If the upstream moved its docs tree, update "
            "DOCS_PREFIX in this source module."
        )
    return pages
