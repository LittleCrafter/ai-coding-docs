"""Source: Claude Code.

Claude Code's docs site (https://code.claude.com) serves every page as raw
Markdown at ``<canonical-url>.md`` -- each HTML page has a ``.md`` twin
carrying the same content. This is a deliberate convention of Anthropic's
documentation server (mintlify-style "llms-friendly" serving): appending
``.md`` to ANY docs page URL returns the page's Markdown source instead of
the rendered HTML, so the Markdown endpoint needs no discovery of its own
-- it is derived mechanically from the canonical URL. It also publishes an
XML sitemap at ``/docs/sitemap.xml`` listing every page of every locale.

Discovery is therefore simple and robust: read the sitemap, keep only the
English pages (URLs whose path starts with ``/docs/en/``), and derive each
page's Markdown URL by appending ``.md``. No HTML parsing, no JavaScript, no
guessing at URL structure.

Fragility notes -- what breaks when the upstream site changes:

* If the site drops the ``.md`` twins, discovery still succeeds but every
  page fetch starts failing (404s).
* If the English tree moves off ``/docs/en/`` (e.g. a locale restructure),
  the filter below matches nothing, and the zero-page guard in ``discover``
  raises a RuntimeError loudly instead of letting the pipeline treat every
  mirrored slug as deleted upstream.

No whats-new for this source — just the up-to-date documentation.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING
from urllib.parse import urlsplit

from ..core import fetch, media
from ..core.page import Page
from ..core.sitemap import crawl_sitemap
from .base import (
    SourceConfig,
    ensure_discovered_pages,
    same_origin,
    try_make_page,
)

if TYPE_CHECKING:
    # Guard ``httpx.Client`` behind ``TYPE_CHECKING`` so that the ``httpx``
    # package is never imported at runtime — it is only needed for static type
    # checking performed by mypy, pyright, or similar tools.  The combination
    # of ``if TYPE_CHECKING`` and the top-level ``from __future__ import
    # annotations`` (PEP 563 / PEP 649) means that even the ``httpx.Client``
    # annotation strings are never actually evaluated by the CPython interpreter:
    # they exist purely as metadata for type checkers.  This avoids:
    #   - Import cycles (if ``httpx`` ever imports back into this package,
    #     the guard prevents a circular-import crash).
    #   - The runtime cost of importing ``httpx`` just for type hints.
    import httpx

SITE_URL = "https://code.claude.com"
SITEMAP_URL = f"{SITE_URL}/docs/sitemap.xml"
# Filter marker that isolates the English documentation tree from any other
# locale (e.g. ``/docs/ja/``, ``/docs/es/``, ``/docs/zh/``) that the upstream
# sitemap may list.  The filter is anchored on the URL's PARSED PATH:
# ``urlsplit(url).path`` must START WITH this prefix.  A bare substring test
# (``EN_PREFIX in url``) would also match a URL whose path merely CONTAINS
# the marker further along (e.g. ``/blog/docs/en/announcement``) and would
# then derive a bogus slug from whatever follows the marker; anchoring on the
# parsed path makes the marker's position meaningful and also immunises the
# filter against the marker appearing in a query string or fragment (those
# are stripped by ``crawl_sitemap`` before URLs reach ``discover`` anyway).
# Note that because this prefix ends with a slash, the English tree's ROOT
# page (``/docs/en``) does NOT match it; ``discover`` handles that one page
# explicitly (slug ``"index"``) before applying this prefix filter.
EN_PREFIX = "/docs/en/"

NPM_REGISTRY_URL = "https://registry.npmjs.org/@anthropic-ai/claude-code/latest"

MEDIA = media.AssetSourceConfig(
    name="claude-code",
    asset_subdir="media",
    ref_prefixes=("https://mintcdn.com/claude-code/",),
    raw_base_url="",
    strip_token_depth=1,
    allowed_extensions=(".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp"),
)

CONFIG = SourceConfig(
    name="claude-code",
    title="Claude Code",
    home_url=f"{SITE_URL}/docs/en/overview",
    generate_whats_new=False,
    version="2.1.233",
    origin="code.claude.com/docs/en/",
    how_mirrored="scraping (sitemap → `<url>.md`)",
)


def get_version(client: httpx.Client) -> str | None:
    """Query the npm registry for the latest published Claude Code version."""
    raw = fetch.get_with_retry(client, NPM_REGISTRY_URL)
    data = json.loads(raw)
    if isinstance(data, dict):
        version = data.get("version")
        if isinstance(version, str) and version.strip():
            return version.strip().removeprefix("v").removeprefix("V").strip()
    return None


def _sitemap_urls(client: httpx.Client, max_depth: int = 3) -> list[str]:
    """Fetch the sitemap, following nested sitemap indexes breadth-first."""
    return crawl_sitemap(
        client,
        SITEMAP_URL,
        max_depth=max_depth,
        allowed_origin=SITE_URL,
    )


def discover(client: httpx.Client) -> list[Page]:
    """Discover all English Claude Code docs pages from the sitemap.

    The slug is the URL path after ``/docs/en/`` (e.g. ``"hooks"`` or
    ``"agent-sdk/python"``); the group shown in the index is the slug's
    first path segment, or ``"root"`` for top-level pages. The English
    tree's root page itself (``/docs/en``, whose trailing slash the URL
    cleaner strips) is mirrored under the slug ``"index"``. Each page's
    ``source_md_url`` is the ``.md`` twin of its canonical URL. Results are
    deduplicated by slug (the sitemap can list a URL more than once) and
    sorted for deterministic output.
    """
    pages: list[Page] = []
    seen_slugs: set[str] = set()
    # ``_sitemap_urls`` already canonicalises every URL via ``crawl_sitemap``
    # (stripping the query string, fragment, and trailing slash), so ``url``
    # arrives here in canonical form -- no inline cleaning is needed (a
    # redundant ``urlsplit`` re-clean would only reproduce ``url`` itself).
    for url in _sitemap_urls(client):
        # Origin boundary: the URL must belong to the Claude Code origin
        # before any path-level filtering happens. The path-anchored
        # EN_PREFIX check below sees only the URL's parsed path and would
        # happily accept a foreign-host sitemap entry whose PATH starts
        # with ``/docs/en/`` -- see ``same_origin`` in ``core/utils.py``
        # for the full rationale (why a bare ``startswith(SITE_URL)`` is
        # insufficient); ``sources/base.py`` only re-exports the helper. ``_sitemap_urls`` applies the same check to child
        # sitemaps before fetching them; page URLs (non-.xml locs) are
        # passed through unchecked and are filtered here instead.
        if not same_origin(url, SITE_URL):
            continue  # foreign-origin URLs are not this adapter's docs
        # Anchor the English-tree filter on the URL's parsed PATH rather than
        # on the raw URL string: a path-anchored ``startswith`` cannot
        # false-match a URL whose path merely CONTAINS ``/docs/en/`` further
        # along (see the EN_PREFIX comment above), and slicing the slug off a
        # fixed-length prefix keeps slug derivation exact.
        path = urlsplit(url).path
        if path == EN_PREFIX.rstrip("/"):
            # The English tree's ROOT page.  The sitemap lists it as
            # ``https://code.claude.com/docs/en/`` and ``crawl_sitemap`` strips
            # the trailing slash, so it arrives here as the bare path
            # ``/docs/en`` -- which a plain ``startswith(EN_PREFIX)`` check
            # would REJECT, because EN_PREFIX itself ends with a slash.  The
            # root is therefore matched explicitly.  It is a real content
            # page (the English docs landing page) with a working Markdown
            # twin at ``/docs/en.md``, so it is mirrored like any other
            # page.  Having no path segment after the prefix, it takes the
            # conventional slug ``"index"`` -- the same slug the kimi_code
            # adapter derives for the root ``index.md`` of its docs tree --
            # and falls into the ``"root"`` group below.
            slug = "index"
        elif path.startswith(EN_PREFIX):
            # The path after ``/docs/en/`` becomes the page's slug —
            # the unique identifier used throughout the mirror pipeline for
            # file naming, index entries, and cross-references.  For a URL
            # ending in ``/docs/en/hooks`` the slug is ``"hooks"``; for
            # ``/docs/en/agent-sdk/python`` it is ``"agent-sdk/python"``
            # (a two-segment path preserved as-is).  The slice can never be
            # empty here: the bare root was handled by the branch above, and
            # ``crawl_sitemap`` has already stripped trailing slashes, so any
            # path that starts with EN_PREFIX carries at least one
            # non-slash character beyond it. For the same reason the slice
            # needs no trailing-slash cleanup of its own: every URL reaching
            # this point passed through ``crawl_sitemap``, which already strips
            # ``/`` suffixes, so no trailing slash can survive to this line.
            slug = path[len(EN_PREFIX) :]
        else:
            # The URL path does not begin with the English-docs marker
            # ``/docs/en/``, so it belongs to a different locale
            # (e.g. ``/docs/ja/``, ``/docs/es/``), or is outside the docs
            # tree entirely (e.g. a top-level homepage or a blog entry).
            # Both are irrelevant for this English-only mirror source and
            # are silently skipped — no warning is raised because it is
            # normal for a multi-locale sitemap to list many non-English
            # entries.
            continue
        # The group is the first path segment of the slug, used by the
        # index generator to organise pages into collapsible sections
        # (e.g. "agent-sdk", "deployment").  For slug ``"hooks"`` (no
        # slash) the group falls back to ``"root"``; for
        # ``"agent-sdk/python"`` it is ``"agent-sdk"``.
        group = slug.split("/", 1)[0] if "/" in slug else "root"
        # Per-entry guard: ``crawl_sitemap`` already canonicalises each URL
        # via ``clean_url``, but that cannot fix an entry whose PATH itself
        # contains characters outside the slug alphabet ``Page`` enforces
        # (a space, parentheses, unicode, ...). ``Page.__post_init__`` rejects
        # such slugs with a ValueError; without this guard that exception
        # would abort discovery for the entire source. ``try_make_page``
        # (see ``sources/base.py``) owns the guard/warning: the URL is named
        # in a stderr warning and discovery continues. The two layers are
        # complementary -- canonicalisation fixes fixable entries, this guard
        # skips unfixable ones -- and the zero-page guard below remains the
        # loud backstop if EVERY entry ends up skipped.
        if slug in seen_slugs:
            continue
        seen_slugs.add(slug)

        page = try_make_page(
            url,
            slug=slug,
            # ``url`` is already canonical: ``crawl_sitemap`` stripped
            # the query string, fragment, and any trailing slash, so it can
            # be used directly -- an inline ``rstrip("/")`` here would be
            # a dead defense that can never change the value.
            source_url=url,
            # The Markdown endpoint is derived, not discovered:
            # Anthropic's docs server serves every page's Markdown
            # source at ``<canonical-url>.md`` (see the module
            # docstring), so appending ".md" to the canonical URL is
            # the complete resolution logic -- no separate lookup
            # table or HTML scraping needed. The URL already carries
            # no trailing slash (see above), so the twin is always
            # ``.../overview.md``, never ``.../overview/.md``.
            source_md_url=f"{url}.md",
            source_id=slug,
            group=group,
        )
        if page is not None:
            pages.append(page)
    # Sort for deterministic output. Sorting by slug guarantees that the output
    # list has a stable order across runs, which matters for git diff
    # hygiene: if the list order changed between runs, the mirror tool
    # would produce spurious diffs even when no content changed.
    pages.sort(key=lambda p: p.slug)
    return ensure_discovered_pages(
        pages, "claude-code", f"English-tree filter {EN_PREFIX!r}"
    )
