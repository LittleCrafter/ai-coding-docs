"""Source abstraction.

A `Source` knows how to *discover* the pages of one documentation site. The
generic fetch/validate/hash/write pipeline is shared in the orchestrator
(``scripts/mirror/pipeline.py``); each source only implements ``discover()``
(returning ``Page`` objects) plus its ``CONFIG``.

This module defines the things every source shares:

* :class:`SourceConfig` -- the static metadata a source declares;
* :class:`Source` -- a structural ``Protocol`` describing what the pipeline
  expects a source *module* to look like;
* the small discovery helpers :func:`same_origin`,
  :func:`warn_duplicate_slug`, and :func:`try_make_page` -- the identical
  guard logic every adapter's ``discover()`` loop needs, kept here so the
  security and robustness rationale lives in exactly one place.

Sources are plain modules, not classes: the pipeline reads ``module.CONFIG``
and calls ``module.discover(client)`` directly. The Protocol exists for
documentation and type checking, not for inheritance -- no source subclasses
anything.

Lifecycle contract every source adapter follows:

1. **Discovery** -- the pipeline calls ``discover(client)`` ONCE per run.
   The adapter enumerates its upstream documentation (sitemap, git tree,
   ...) and returns the complete, slug-sorted list of ``Page`` objects.
   "Complete" is a hard requirement: the pipeline diffs the list against
   the previous manifest, so a missing page is treated as deleted upstream
   and its mirrored file is removed -- which is why every adapter raises
   instead of returning an empty list (the zero-page guard).
2. **Fetching** -- for each discovered page the pipeline obtains
   ``(markdown_text, content_hash)``. By default it downloads
   ``page.source_md_url`` as ready Markdown. A source defines the optional
   ``fetch_markdown(client, page)`` hook instead when the download needs
   work before it is Markdown the mirror can store; the pipeline picks the
   hook up via ``getattr`` and calls it per page. Fetch failures surface as
   ``fetch.FetchError`` so the pipeline can isolate them per page (carrying
   the previous manifest entry forward) rather than aborting the whole
   source.
3. **Steady state** -- unchanged pages hash identically and are neither
   rewritten nor re-dated; only discoveries, removals, renames, and content
   edits touch the disk and the whats-new log.
"""

from __future__ import annotations

import sys
from collections.abc import Collection
from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol
from ..core import fetch
from ..core.page import Page
from ..core.utils import clean_url, same_origin

__all__ = [
    "Page",
    "Source",
    "SourceConfig",
    "clean_url",
    "ensure_discovered_pages",
    "ensure_known_slugs",
    "same_origin",
    "try_make_page",
    "warn_duplicate_slug",
]

if TYPE_CHECKING:
    # Only needed for the ``httpx.Client`` type annotations below; thanks to
    # ``from __future__ import annotations`` those are never evaluated at
    # runtime, so importing httpx here avoids a hard import cost for a name
    # the module never calls.
    import httpx


# ``slots=True`` (in addition to ``frozen=True``) gives each instance a
# fixed ``__slots__`` layout instead of a per-instance ``__dict__``: the
# config is written once at import time and only ever read afterwards, so
# there is no legitimate reason to attach ad-hoc attributes to it, and the
# smaller/faster attribute access is a free bonus. Should a future field
# need a default, remember that slotted dataclasses reject mutable defaults
# exactly like frozen ones -- use ``field(default_factory=...)``.
@dataclass(frozen=True, slots=True)
class SourceConfig:
    """Static identity and display metadata for one source.

    Every source module declares exactly one of these as its module-level
    ``CONFIG``. The pipeline reads it to decide where output goes
    (``docs/<name>/``), what to call the source in indexes and console
    output, and whether to keep a structural changelog (whats-new).
    """

    name: str  # short id, also the docs/<name>/ folder
    title: str  # human-readable, used in indexes
    home_url: str  # official docs root, shown in the index
    # When True, the pipeline appends a dated whats-new entry under
    # docs/<name>/whats-new/ whenever the diff against the previous manifest
    # is non-empty (pages added/removed/renamed/modified). This tracks
    # *structural* change of the upstream docs over time. Currently only the
    # Antigravity source opts in; other sources opt out.
    generate_whats_new: bool
    version: str = "—"  # upstream target version (or "—" when not versioned)
    origin: str = ""  # upstream documentation path or repository
    how_mirrored: str = ""  # mirroring mechanism description
    # Relative link destinations this source's pages use ILLUSTRATIVELY, i.e.
    # as part of a documentation sample rather than as a real cross-reference.
    # The link checker (``core.link_checker``) reports every relative
    # destination that does not resolve on disk, which is the right default:
    # a dead link in the mirror is a defect. A sample is the one legitimate
    # exception -- a page that shows readers the shape of a memory index or a
    # config file necessarily names files that exist only in the reader's own
    # project -- and only the source knows which of its destinations are of
    # that kind, so the list lives here rather than in the checker.
    #
    # Semantics: each entry is an exact, cleaned relative destination (the
    # path part of the link, query and fragment stripped, as the checker
    # compares it). The exemption covers the WHOLE source, so an entry must
    # name a destination that appears exclusively inside samples -- a
    # genuinely broken link spelled the same way elsewhere in the source
    # would be silenced too.
    illustrative_link_targets: tuple[str, ...] = ()


class Source(Protocol):
    """Structural shape every source *module* exposes.

    A source module exposes a ``CONFIG`` attribute plus a ``discover()``
    function and the optional ``fetch_markdown()`` / ``get_version()``
    hooks. The orchestrator (``scripts/mirror/pipeline.py``) treats each
    source module as a ``Source`` and reads ``module.CONFIG`` / calls
    ``module.discover(client)``.

    Example (module-level duck-typing inspection):
    ```python
    import my_source_module
    _module_is_source: Source = my_source_module
    ```

    NOTE on ``self``: the objects checked against this Protocol are
    *modules*, not class instances, and ``self`` never exists at runtime --
    attribute access on a module yields the plain module-level function and
    the pipeline calls it with ``client`` only. The parameter is declared
    anyway, as a STATIC modeling convention: static type checkers (pyright)
    check a module value against a Protocol by treating the module as an
    instance of its own interface, binding that instance to the ``self``
    slot. Declaring ``self`` therefore makes ``module.discover(client)``
    type-check with ``client`` landing on the correct parameter, exactly as
    the pipeline calls it; omitting it (as an instance-method declaration
    would otherwise require) makes the checker try to bind the module onto
    the ``client`` parameter instead.

    ``fetch_markdown`` and ``get_version`` below are declared as Protocol
    members even though both are OPTIONAL at runtime: a source declares
    ``fetch_markdown`` only when its pages need per-source work after the
    download -- HTML converted to Markdown (deepseek), MDX or VitePress
    sources normalised (claude_code, kimi_code, opencode), cross-links
    repointed at the mirrored tree (antigravity), reference stubs resolved
    (codex_cli) -- and ``get_version`` exists only on some sources. Python's
    Protocol has no notion of an optional member, so declaring them makes
    them *required* members as far as static checkers are concerned -- but
    nothing here ever performs a runtime structural check (the Protocol is
    not ``@runtime_checkable`` and no ``isinstance`` call targets it), and
    the pipeline looks both hooks up defensively with
    ``getattr(source, "fetch_markdown", None)`` /
    ``getattr(source, "get_version", None)``. Declaring them anyway buys
    real value: static type checkers and IDEs can autocomplete and
    type-check each hook's signature at the pipeline's call site, and the
    method docstrings below keep the hook contracts next to the rest of the
    source contract instead of only in a comment. Runtime behavior is
    unchanged: a module that omits a hook simply falls back to the default
    path (plain ``source_md_url`` download / ``CONFIG.version``).
    """

    CONFIG: SourceConfig

    def discover(self, client: httpx.Client) -> list[Page]:
        """Return the current set of pages for this source, sorted by slug.

        ``client`` is the pipeline's shared ``httpx.Client`` (with retries,
        timeouts, and polite headers already configured) -- sources must use
        it rather than creating their own, so rate limiting and auth stay
        centralized.

        The returned list must be complete and stable: the pipeline diffs it
        against the previous manifest, so a page absent from the result is
        treated as removed upstream (and its mirrored file is deleted), while
        an unstable slug looks like a remove+add pair. Sorting by slug keeps
        the output deterministic across runs.
        """
        ...

    def fetch_markdown(self, client: httpx.Client, page: Page) -> tuple[str, str]:
        """OPTIONAL hook: fetch one page and return ``(markdown, hash)``.

        When a source module defines this, the pipeline calls it for each
        page instead of downloading ``page.source_md_url`` as ready
        Markdown. It is the escape hatch for any source whose downloaded
        text is not yet what the mirror should store: ``deepseek.py`` fetches
        rendered HTML and converts it to Markdown, the MDX/VitePress sources
        (``claude_code.py``, ``kimi_code.py``, ``opencode.py``) normalise the
        upstream page sources to plain Markdown, ``codex_cli.py`` resolves
        reference stubs to their richer twins, and ``antigravity.py``
        repoints the page's site-absolute cross-links at the mirrored tree.

        The returned hash is what the pipeline stores in the manifest for
        change detection, so it must be ``fetch.content_hash`` of the exact
        returned text. Failures must be raised as ``fetch.FetchError``: the
        pipeline isolates failures PER PAGE only for that exception type,
        so anything else escaping the hook aborts the source's entire run.

        A hook that needs run-scoped state discovery produced (the set of
        slugs this run mirrors, say) reads it from its own module and should
        refuse to run without it -- see
        :func:`ensure_known_slugs` for the guard and why an empty set is
        not a harmless default.
        """
        ...

    def get_version(self, client: httpx.Client) -> str | None:
        """OPTIONAL hook: query upstream dynamically for the latest target version.

        When defined, the pipeline calls this during a run to dynamically
        discover the upstream version string (e.g. from an npm registry or
        GitHub release API). Returning ``None`` or raising an exception causes
        the pipeline to fall back gracefully to the previous manifest's
        version (if available) or ``CONFIG.version``.
        """
        ...


def warn_duplicate_slug(slug: str, path: str) -> None:
    """Print the standard duplicate-slug warning to stderr.

    The slug IS the on-disk output path (``docs/<source>/<slug>.md``), so
    two entries collapsing onto one slug would make two ``Page`` objects
    fight over a single mirrored file and the later write would silently
    overwrite the earlier one. The repo-tree adapters (codex_cli, kimi_code,
    opencode) keep the FIRST entry and skip the later one with this loud
    warning naming both the slug and the skipped path -- a collision "cannot
    happen" in theory (the git-trees API is not expected to list a blob
    twice), but a malformed API response or a slug-normalisation step that
    maps two distinct paths onto one slug must surface loudly instead of
    corrupting the mirror silently. The warning goes to stderr, the
    conventional channel for the mirror tooling's non-fatal diagnostics,
    keeping stdout clean for the pipeline's formatted report output.
    """
    print(
        f"  warning: duplicate slug {slug!r} from {path!r}; "
        "skipping (an earlier tree entry already claimed this "
        "output path)",
        file=sys.stderr,
    )


def try_make_page(
    label: str,
    *,
    slug: str,
    source_url: str,
    source_md_url: str,
    source_id: str,
    group: str,
) -> Page | None:
    """Build a ``Page``, or warn on stderr and return None if it is invalid.

    ``Page.__post_init__`` rejects entries whose slug falls outside the slug
    alphabet (a space, parentheses, unicode punctuation, ...). Discovery
    processes upstream listings the adapter does not control -- sitemap
    ``<loc>`` entries or git-tree paths -- so ONE malformed entry must never
    abort discovery for the whole source: a source-level failure mirrors
    nothing at all, and the pipeline would then treat every previously
    mirrored page as deleted upstream. Catching the ``ValueError`` here
    isolates the irreducibly-bad entry: it is skipped with a loud stderr
    warning naming *label* (the upstream URL or repo path the operator needs
    to find the offending entry) and the rejection reason, while the
    remaining entries are still discovered. Each adapter's zero-page guard
    remains the loud backstop for the case where EVERY entry ends up
    skipped.

    Returns the constructed ``Page`` on success, ``None`` when the entry
    was skipped, so the caller's loop stays a simple
    ``if page is not None: pages.append(page)``.
    """
    try:
        return Page(
            slug=slug,
            source_url=source_url,
            source_md_url=source_md_url,
            source_id=source_id,
            group=group,
        )
    except ValueError as exc:
        print(
            f"  warning: skipping invalid page entry {label!r}: {exc}",
            file=sys.stderr,
        )
        return None


def ensure_known_slugs(source_name: str, slugs: Collection[str], slug: str) -> None:
    """Guard a link-rewriting fetch hook against running without discovery.

    Several adapters resolve their pages' site-absolute cross-links against
    the set of slugs the CURRENT run mirrors. That set travels as module-level
    state, because the pipeline calls ``discover()`` and ``fetch_markdown()``
    separately with nothing but the source module in between. The state is
    written by discovery and read by the fetch hook, so a hook invoked on its
    own -- a direct call in a test, a future caller that skips discovery, a
    refactor that reorders the two stages -- would read an EMPTY set.

    An empty set is not a harmless degradation: every cross-link would miss
    the mirrored-tree branch and be rewritten to its upstream URL, so the run
    would silently produce a page whose internal navigation points off-site,
    and the manifest would record that text as the page's correct content.
    Absence of knowledge and knowledge that nothing is mirrored are therefore
    NOT the same thing, and this guard makes the difference loud: it raises
    before any rewriting happens.

    The failure type is ``fetch.FetchError`` so it takes the pipeline's
    ordinary per-page path. Every page of the source fails the same way, all
    of them are carried forward from the previous manifest, and nothing on
    disk is touched -- a loud, inert failure rather than silent link
    corruption.

    Args:
        source_name: The source reporting the problem, for the message.
        slugs: The discovered-slug collection as the hook sees it.
        slug: The page being converted, so the message names a real page.

    Raises:
        fetch.FetchError: When *slugs* is empty.
    """
    if not slugs:
        raise fetch.FetchError(
            f"{source_name}: no discovered slugs are available while converting "
            f"{slug!r}. This source resolves its cross-links against the pages "
            "the current run mirrors, so converting without that set would "
            "rewrite every internal link to its upstream URL. Run discovery "
            "before fetching."
        )


def ensure_discovered_pages(
    pages: list[Page], source_name: str, details: str = ""
) -> list[Page]:
    """Validate that at least one page was discovered; raise RuntimeError if empty.

    This safety guard prevents an empty discovery result from reaching the
    pipeline and triggering unintended mass-deletion of existing mirror files.
    """
    if not pages:
        msg = (
            f"{source_name}: discovery returned 0 pages. "
            "A zero-page discovery would delete all mirrored files."
        )
        if details:
            msg += f" ({details})"
        raise RuntimeError(msg)
    return pages
