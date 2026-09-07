"""Source: Google Antigravity CLI.

The docs site (https://antigravity.google) serves every page as raw
Markdown at ``<canonical-url>.md`` -- appending ``.md`` to any documentation
page URL returns the page's original Markdown source directly. It also
publishes an XML sitemap at ``/sitemap.xml`` listing every page, including the
whole CLI documentation tree under ``/docs/cli/``.

Discovery is simple, fast, and robust: read the sitemap, keep only the CLI
documentation pages (URLs on the ``antigravity.google`` origin whose path starts
with ``/docs/cli/`` or equals ``/docs/cli``), and derive each page's Markdown URL
by appending ``.md``. No HTML parsing, no JavaScript, and no fragile CSS
selectors.

Fragility notes -- what breaks when the upstream site changes:

* If the site drops the ``.md`` endpoints, page fetches fail (404s).
* If the CLI documentation tree moves off ``/docs/cli/`` (e.g. a restructuring),
  the filter below matches nothing, and the zero-page guard in ``discover``
  raises a RuntimeError loudly instead of letting the pipeline treat every
  mirrored slug as deleted upstream.

This source opts into whats-new (structural change tracking):
additions/removals/renames of CLI pages are recorded over time.
"""

from __future__ import annotations

import shutil
import subprocess
from typing import TYPE_CHECKING
from urllib.parse import urlsplit

from ..core import fetch, media
from ..core.page import Page
from ..core.sitemap import extract_locs
from ..core.utils import extract_version
from .base import SourceConfig, ensure_discovered_pages, same_origin, try_make_page

if TYPE_CHECKING:
    import httpx

SITE_URL = "https://antigravity.google"
SITEMAP_URL = f"{SITE_URL}/sitemap.xml"
CLI_PREFIX = "/docs/cli/"
DOCS_PREFIX = "/docs/"

MEDIA = media.AssetSourceConfig(
    name="google-antigravity-cli",
    asset_subdir="assets",
    ref_prefixes=("/assets/",),
    raw_base_url=f"{SITE_URL}/assets/",
)

CONFIG = SourceConfig(
    name="google-antigravity-cli",
    title="Google Antigravity CLI",
    home_url=f"{SITE_URL}/docs/cli/overview",
    generate_whats_new=True,
    version="1.1.13",
    origin="antigravity.google/docs/cli/",
    how_mirrored="scraping (sitemap → `<url>.md`)",
)


def get_version(client: httpx.Client) -> str | None:
    """Return the Antigravity CLI version.

    Attempts to query the local ``agy --version`` CLI if available in the
    environment; falls back to ``CONFIG.version``.
    """
    agy_bin = shutil.which("agy") or shutil.which("antigravity")
    if agy_bin:
        try:
            res = subprocess.run(
                [agy_bin, "--version"],
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            )
            if res.returncode == 0 and res.stdout.strip():
                version = extract_version(res.stdout)
                if version:
                    return version
        except subprocess.SubprocessError, OSError:
            pass
    return CONFIG.version


def discover(client: httpx.Client) -> list[Page]:
    """Discover all Antigravity CLI docs pages from the sitemap.

    Every sitemap URL on the ``antigravity.google`` origin whose path starts
    with ``/docs/cli/`` or equals ``/docs/cli`` becomes a page. The slug is the
    URL path after ``/docs/`` (e.g. ``"cli/overview"`` or
    ``"cli/commands/agents"``), the index group is the slug's directory
    part (``"cli"`` for top-level pages, ``"cli/commands"`` for command
    references), and ``source_id`` is the full slug: unique per page and stable
    across deploys for rename detection. Each page's ``source_md_url`` is the
    ``.md`` twin of its canonical URL.

    Origin boundary: Only URLs belonging to ``SITE_URL`` are considered (via
    ``same_origin``).

    Query strings and fragments are stripped from each URL before deriving the
    slug so parameter variants deduplicate to a single page.

    Per-entry error isolation: URLs with invalid slug characters are skipped with
    a stderr warning rather than aborting discovery for the whole source.

    Zero-page guard: Two failure modes raise ``RuntimeError`` instead of returning
    an empty list:
    1. The sitemap contains zero ``<loc>`` entries.
    2. The CLI-prefix filter matched nothing.

    Results are deduplicated by slug and sorted alphabetically for deterministic,
    reproducible output.
    """
    xml = fetch.get_with_retry(client, SITEMAP_URL)
    locs = extract_locs(xml)
    if not locs:
        raise RuntimeError(
            f"Sitemap {SITEMAP_URL} contained no <loc> entries. "
            "A zero-page discovery would delete all mirrored files. "
            "If the upstream sitemap moved, update SITEMAP_URL in this "
            "source module."
        )

    pages: list[Page] = []
    seen: set[str] = set()

    for url in locs:
        parsed = urlsplit(url)
        clean = parsed._replace(query="", fragment="").geturl().rstrip("/")

        if not same_origin(clean, SITE_URL):
            continue

        path = parsed.path.rstrip("/")
        if not (path == CLI_PREFIX.rstrip("/") or path.startswith(CLI_PREFIX)):
            continue

        slug = path[len(DOCS_PREFIX) :]
        if slug in seen:
            continue
        seen.add(slug)

        group = slug.rsplit("/", 1)[0] if "/" in slug else "root"
        page = try_make_page(
            url,
            slug=slug,
            source_url=clean,
            source_md_url=f"{clean}.md",
            source_id=slug,
            group=group,
        )
        if page is not None:
            pages.append(page)

    pages.sort(key=lambda p: p.slug)
    return ensure_discovered_pages(
        pages, "google-antigravity-cli", f"CLI docs prefix {CLI_PREFIX!r}"
    )
