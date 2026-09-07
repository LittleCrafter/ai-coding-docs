"""Source: Codex CLI.

The official Codex CLI documentation lives as Markdown in the open-source repo
`openai/codex` under `docs/` (getting-started, install, config, sandbox,
slash_commands, agents_md, authentication, ...). The folder is no longer
*only* CLI guides: upstream also keeps repo meta/legal Markdown there -- the
Contributor License Agreement, the license text, the contributing guide, and
the open-source-fund pages. We mirror those too, deliberately: they are part
of the upstream `docs/` tree, they version together with the CLI docs they
govern, and dropping them would require extra filter rules whose only effect
would be to hide accurate upstream content from the mirror. We list that
directory via the GitHub API and download each `.md` from
raw.githubusercontent.com -- the same approach as the Kimi source.

How discovery works:

* The GitHub "git trees" API returns the repo's entire file tree in a single
  call (``?recursive=1``) as a flat list of entries; each file is a
  ``{"type": "blob", "path": ...}`` object. One API call replaces what would
  otherwise be a crawl of directory listings. That call -- including its
  rate-limit error mapping and its truncation guard -- is shared with the
  Kimi adapter via ``core.github.fetch_git_tree``; this module keeps only
  the Codex-specific filtering on top of it.
* We keep only Markdown files that are *direct* children of ``docs/`` -- the
  CLI docs are a flat folder, so a ``/`` in the remainder of the path means
  the file belongs to some other area of the repo.
* Content is downloaded from ``raw.githubusercontent.com`` rather than via
  the API's blob endpoint: raw file serving is not subject to the API rate
  limit (60 requests/hour anonymous), which matters because the pipeline
  fetches every page. The single tree-listing call itself is rate-limited --
  see ``core/github.py`` for how a token raises that ceiling.

We deliberately use the repo's `docs/` rather than the learn.chatgpt.com /
developers.openai.com markdown twins: those twins are inconsistent (different
slugs returning identical content) and cover the whole ChatGPT/Codex
documentation tree, whereas this folder is the CLI's own, tightly-scoped documentation.
No whats-new for this source.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from ..core import fetch
from ..core.github import fetch_git_tree, fetch_latest_release_tag
from ..core.page import Page
from .base import SourceConfig, try_make_page, warn_duplicate_slug

if TYPE_CHECKING:
    # Annotation-only import: ``from __future__ import annotations`` keeps the
    # ``httpx.Client`` annotations from being evaluated at runtime.
    import httpx

REPO = "openai/codex"
BRANCH = "main"
DOCS_PREFIX = "docs"  # CLI docs live directly under docs/
# raw.githubusercontent.com serves the unprocessed file content -- this is
# what the pipeline actually downloads for each page.
RAW_BASE = f"https://raw.githubusercontent.com/{REPO}/{BRANCH}"
# Human-facing page URL (used for the "source" link in the mirrored files),
# as opposed to RAW_BASE which is the machine-facing download URL.
BLOB_BASE = f"https://github.com/{REPO}/blob/{BRANCH}"

CONFIG = SourceConfig(
    name="codex-cli",
    title="Codex CLI",
    home_url=f"https://github.com/{REPO}",
    generate_whats_new=False,
    version="0.147.0",
    origin=f"github.com/{REPO} (`docs/`)",
    how_mirrored="scraping (GitHub tree → `raw.githubusercontent.com`)",
)


def get_version(client: httpx.Client) -> str | None:
    """Query the GitHub API for the latest release tag of Codex CLI."""
    return fetch_latest_release_tag(client, repo=REPO)


def discover(client: httpx.Client) -> list[Page]:
    """Discover all CLI docs pages from the repo's git tree.

    Lists the full tree of ``openai/codex@main`` in one API call (via
    ``core.github.fetch_git_tree``, which also enforces the rate-limit and
    truncation safety guards) and keeps Markdown files that are direct
    children of ``docs/``. The slug is the filename without ``.md``
    (e.g. ``docs/config.md`` -> ``"config"``), and ``source_id`` is the full
    repo path, which is stable across content edits and therefore serves as
    the pipeline's rename-detection key. Slugs are deduplicated with a
    ``seen`` set (first entry wins, later duplicates are skipped with a
    stderr warning) as defense in depth against duplicate paths in the git
    tree listing.

    Raises ``RuntimeError`` when discovery finds zero pages: an empty result
    would make the pipeline diff "nothing discovered" against the previous
    manifest and delete every mirrored file, so a total filter miss (e.g.
    the upstream moved its docs out of ``docs/``) must be a loud error, not
    silent data loss.
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
        # Only direct Markdown children of docs/ (e.g. docs/config.md). Two
        # boundaries isolate the CLI docs from the rest of the repo:
        #
        #   * The ``docs/`` prefix keeps repository-root Markdown OUT: the
        #     repo's own README.md, CHANGELOG.md, SECURITY.md, etc. are
        #     project meta-files, not CLI documentation, and without the
        #     prefix filter they would be mirrored into docs/codex-cli/
        #     alongside the real docs.
        #   * The no-``/`` test on the remainder keeps nested paths OUT:
        #     anything under a subdirectory of docs/ (or elsewhere in the
        #     repo) belongs to a different area -- the upstream CLI docs are
        #     a deliberately flat folder, so nesting is the signal that a
        #     file is not part of it.
        if not path.startswith(DOCS_PREFIX + "/"):
            continue
        rest = path[len(DOCS_PREFIX) + 1 :]
        # Only target .md because Codex CLI documentation exclusively uses
        # the .md extension.
        if not rest.endswith(".md") or "/" in rest:
            continue
        # Strip the trailing ".md" file extension to derive the slug.
        # ``rest`` is guaranteed to end with ".md" by the endswith check
        # on the line immediately above (``rest.endswith(".md")``), so the
        # ``-3`` slice always removes exactly the three extension
        # characters -- there is no risk of slicing into the slug itself.
        slug = rest[:-3]
        # A repo file named exactly ".md" (no basename) would yield an empty
        # slug, which Page rejects with a ValueError (caught by
        # try_make_page below, where it would surface as a spurious warning).
        # Such a file carries no usable page identity, so skip it quietly
        # instead -- it is a known-degenerate filename, not a data problem.
        if not slug:
            continue
        # Duplicate-slug guard (defense in depth).  Here the slug is derived
        # 1:1 from the repo path and the git-trees API is not expected to
        # list the same blob twice, so a collision "cannot happen" -- but the
        # slug IS the on-disk output path, so if a duplicate ever did slip
        # through (a malformed API response, or a future slug-normalisation
        # step that collapses two distinct paths onto one slug), two ``Page``
        # objects would fight over a single mirrored file and the later
        # write would silently overwrite the earlier one.  The sibling
        # adapters guard the same invariant in different ways: opencode and
        # kimi_code apply this same keep-the-first guard with a loud stderr
        # warning, while claude_code deduplicates by slug silently in-loop
        # via a seen-slug set (its duplicates are repeat listings of the same
        # sitemap URL -- an expected shape, so there is nothing to warn
        # about).  Keep the FIRST entry and skip the later one with the
        # shared loud stderr warning (``warn_duplicate_slug`` in
        # ``sources/base.py``).
        if slug in seen:
            warn_duplicate_slug(slug, path)
            continue
        seen.add(slug)
        # Per-entry guard: a file path whose name falls outside the slug
        # alphabet (parentheses, unicode, spaces, ...) raises ValueError from
        # ``Page.__post_init__``. Without this guard, ONE such entry would
        # crash discovery for the entire Codex CLI source. ``try_make_page``
        # (see ``sources/base.py``) owns the guard/warning: the path is named
        # in a stderr warning and discovery continues with the remaining
        # entries.
        page = try_make_page(
            path,
            slug=slug,
            source_url=f"{BLOB_BASE}/{path}",
            source_md_url=f"{RAW_BASE}/{path}",
            source_id=path,  # stable upstream GitHub path -> rename key
            group="root",  # Codex CLI docs live directly under docs/, so all pages belong to "root"
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
            f"No Markdown files found directly under {DOCS_PREFIX!r}/ in "
            f"{REPO}@{BRANCH}. A zero-page discovery would delete all "
            "mirrored files. If the upstream moved its docs tree, update "
            "DOCS_PREFIX in this source module."
        )
    return pages


def _rewrite_root_link(match: re.Match[str]) -> str:
    """Rebuild a matched ``](../<file>#anchor)`` link as its canonical GitHub URL.

    The optional ``#anchor`` fragment is preserved verbatim so section links
    such as ``../SECURITY.md#policy`` keep resolving after the rewrite.
    """
    return (
        f"](https://github.com/{REPO}/blob/{BRANCH}/{match.group(1)}"
        f"{match.group(2) or ''})"
    )


def fetch_markdown(client: httpx.Client, page: Page) -> tuple[str, str]:
    """Fetch raw markdown from GitHub and rewrite relative root links.

    Rewrites relative links pointing to repository root files outside docs/
    (`../SECURITY.md` and `../LICENSE`, with or without a `#anchor`) to
    canonical upstream GitHub URLs, preserving any anchor.
    """
    text, _ = fetch.fetch_validated(client, page.source_md_url)
    text = re.sub(
        r"\]\(\.\./(SECURITY\.md|LICENSE)(#[^)]*)?\)",
        _rewrite_root_link,
        text,
    )
    return text, fetch.content_hash(text)
