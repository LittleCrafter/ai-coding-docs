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

The published Markdown is written for the docs site, so its cross-references
are site-absolute (``](/docs/cli/commands/agents)``): correct on
antigravity.google, dead everywhere else -- including in this mirror, where a
leading ``/`` resolves to the file system root of whoever is reading the
repository. The adapter therefore defines the optional ``fetch_markdown`` hook
to route every such link through :func:`_rewrite_docs_links`, which repoints it
at the mirrored page it names (a relative ``.md`` link) or at its upstream URL
when the target is not part of this mirror.

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

import posixpath
import re
import shutil
import subprocess
from bisect import bisect_right
from collections.abc import Iterator
from typing import TYPE_CHECKING
from urllib.parse import urlsplit

from ..core import fetch, media
from ..core.html_markdown import iter_code_block_spans
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
    version="1.2.0",
    origin="antigravity.google/docs/cli/",
    how_mirrored="scraping (sitemap → `<url>.md`)",
)


def get_version(client: httpx.Client) -> str | None:
    """Return the Antigravity CLI version.

    Attempts to query the locally installed CLI -- ``agy``, or its
    ``antigravity`` executable alias -- via ``--version`` when either is
    available on ``PATH``; falls back to ``CONFIG.version``.
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


# ---------------------------------------------------------------------------
# Link rewriting: site-absolute ``/docs/...`` references
# ---------------------------------------------------------------------------
# The upstream Markdown addresses every other documentation page by its
# site-absolute path. In the mirror that path means nothing -- a leading ``/``
# resolves against the file system root, not against ``docs/google-antigravity-cli/``
# -- so every reference is rewritten to the file it names, or to its upstream
# URL when the target is not mirrored.

# A Markdown link whose destination is a site-absolute ``/docs/...`` path.
# Matched as ``](...)`` (the destination half of a link, in either inline or
# reference-free form) rather than as a bare path, so a ``/docs/...`` string
# quoted in prose is left exactly as the page wrote it.
#
# The destination is captured with ``[^)\s]*``: it stops at the closing
# parenthesis of the link and at the first whitespace, so the match can never
# run past the end of one link. A destination containing a space is therefore
# not matched at all and stays untouched -- such a link is malformed Markdown
# (a destination with a space must be written ``<...>``) and rewriting a guess
# at where it ends would corrupt the page.
#
# This pattern is ONLY ever applied through ``_iter_docs_links`` (never via
# ``re.sub`` or a bare ``.finditer()``), because the substitution is
# O(N x body length) on input with N ``](/docs`` openers and no closing
# parenthesis: the greedy ``[^)\s]*`` expands to end-of-string from every
# candidate, fails to find its ``)``, and the engine retries the whole scan
# from the next candidate (measured: 18/36/72 KB of ``](/docs/a`` took
# 0.44/1.77/7.14 s, the classic 4x-per-2x quadratic signature). The pass runs
# on raw Markdown fetched from the network, so this is a remotely-triggerable
# hang. ``_iter_docs_links`` keeps this pattern for the actual matching (so
# group semantics are untouched) but drives it with a linear ``str.find``
# scan -- see that function for the monotonicity argument.
_DOCS_LINK_RE = re.compile(r"\]\((?P<href>/docs(?:/[^)\s]*)?)\)")

# Largest indentation, in columns, a fenced code block may carry and still be
# a fence: CommonMark reads four or more leading spaces as an indented code
# block instead, with the ``` line as literal text. The shared
# ``iter_code_block_spans`` scanner mirrors the column-zero fence rule only,
# so the shielding below widens that rule for this adapter.
_MAX_FENCE_INDENT = 3

# Placeholder token for a shielded fenced code block. Uppercase, with no
# characters a Markdown document would produce around a link, so it passes
# through the link pass untouched and cannot be mistaken for page content.
_FENCE_PLACEHOLDER = "ANTIGRAVITYFENCEBLOCK{}PLACEHOLDER"

# Slugs of the pages discovered by the current run; populated by ``discover``
# and read by the link pass in ``fetch_markdown``. The pipeline discovers
# every page of a source before it fetches the first one, so the set is
# already complete when the first page is converted. A module-level set is
# what carries the information between the two hooks: the pipeline calls them
# separately, with nothing but the module itself in between.
_KNOWN_SLUGS: set[str] = set()


def _iter_fence_spans(text: str) -> Iterator[tuple[int, int]]:
    """Yield the ``(start, end)`` span of every fenced code block in *text*.

    Same spans as the shared :func:`iter_code_block_spans` scanner, with one
    difference: a fence indented by up to three columns is recognised here,
    where the shared scanner sees column-zero fences only. Upstream indents a
    sample that sits inside a list item -- the list marker pushes the whole
    item's content right -- and CommonMark still reads a fence indented that
    far as a fence. Those blocks need shielding exactly like a top-level one:
    a sample in a list item quotes documentation URLs just as often, and
    rewriting it would change what the sample says.

    The fence semantics stay with the shared scanner, which is fed a copy of
    *text* with up to three leading spaces removed from every line -- exactly
    the transformation that turns an indented fence into a column-zero one.
    A line indented four columns or more is an indented code block, not a
    fence, in either form: removing three of its spaces leaves it indented,
    so the copy can neither gain nor lose a fence there. A tab is left alone:
    it advances to the next multiple of four columns, which is out of fence
    range however it is written, and its width is not knowable here.

    Each span the scanner reports in that copy is mapped back through the
    per-line offsets, so the caller receives the original text of the block.
    The span starts where the opening fence character sits in *text*: at the
    line start for a column-zero fence, and past the indentation for an
    indented one, so a shielded block keeps the column the page wrote it at.
    """
    lines = text.split("\n")
    shifts = [
        min(len(line) - len(line.lstrip(" ")), _MAX_FENCE_INDENT) for line in lines
    ]
    starts: list[int] = []
    indented_starts: list[int] = []
    offset = 0
    indented_offset = 0
    for line, shift in zip(lines, shifts):
        starts.append(offset)
        indented_starts.append(indented_offset)
        offset += len(line) + 1
        indented_offset += len(line) - shift + 1
    indented = "\n".join(line[shift:] for line, shift in zip(lines, shifts))

    def to_source(index: int) -> int:
        """Map an offset of the de-indented copy back to one of *text*."""
        line = bisect_right(indented_starts, index) - 1
        return starts[line] + shifts[line] + (index - indented_starts[line])

    for start, end in iter_code_block_spans(indented):
        yield to_source(start), to_source(end)


def _iter_docs_links(text: str) -> Iterator[re.Match[str]]:
    """Yield every ``](/docs...)`` link in *text*, in document order.

    Semantics-identical to ``_DOCS_LINK_RE.finditer(text)`` but LINEAR on
    adversarial input (see the hazard comment on ``_DOCS_LINK_RE``). The
    scan is decomposed into:

    1. ``str.find("](/docs", ...)`` to locate the next candidate -- the
       literal opener plus the fixed ``/docs`` head the pattern requires, so
       no position that cannot match is ever handed to the regex engine;
    2. ``str.find(")", ...)`` to locate the first closing parenthesis after
       it. The destination class excludes ``)``, so the match can only ever
       end at that first parenthesis; passing it to the engine as ``endpos``
       is what bounds every attempt to one link's worth of text instead of
       letting it scan to end-of-string and backtrack one character at a
       time;
    3. ``_DOCS_LINK_RE.match`` on the proven window, so the group semantics
       are produced by the original pattern itself, not reimplemented.

    LINEAR-TIME ARGUMENT: every ``str.find`` resumes where the previous one
    stopped -- the candidate cursor only moves forward, and the parenthesis
    search is reused while it still sits ahead of the candidate and is
    otherwise restarted from a strictly later position -- so each character
    of the document is scanned a bounded number of times. When no closing
    parenthesis exists, the loop STOPS rather than retrying from the next
    candidate: a ``)`` for any later link would sit after this candidate too
    and would have been found, so no later link can match either.
    """
    pos = 0
    closer = -1  # cached first ")" at or after the candidate cursor
    while True:
        start = text.find("](/docs", pos)
        if start == -1:
            break
        if closer < start + 2:
            closer = text.find(")", start + 2)
            if closer == -1:
                # No ")" anywhere after this candidate -- and therefore
                # after ANY later one either (see the docstring).
                break
        match = _DOCS_LINK_RE.match(text, start, closer + 1)
        if match is None:
            # The destination does not continue the way the pattern needs
            # (a bare ``/docsomething`` head, a space before the closer), so
            # this candidate is not a link. A later one starts after it.
            pos = start + 1
            continue
        yield match
        pos = closer = match.end()


def _protect_fenced_code(text: str) -> tuple[str, list[str]]:
    """Replace every fenced code block in *text* with an opaque placeholder.

    Returns the placeholder-embedded text plus the original fenced blocks in
    document order; :func:`_restore_fenced_code` splices them back verbatim.
    A code sample is not prose: a shell snippet, a JSON payload, or a
    configuration example may contain a documentation URL, and rewriting it
    would change what the sample says. Lifting the blocks out of the text for
    the duration of the pass keeps every rewrite confined to the prose the
    link was written for.

    The blocks are located by :func:`_iter_fence_spans`, which delegates the
    fence semantics -- matching fence characters and lengths, an opener with
    no closer not being a block at all -- to the shared
    :func:`iter_code_block_spans` scanner (the same one the ``opencode``
    adapter uses), so those rules live in exactly one place.
    """
    blocks: list[str] = []
    segments: list[str] = []
    pos = 0
    for start, end in _iter_fence_spans(text):
        segments.append(text[pos:start])
        index = len(blocks)
        blocks.append(text[start:end])
        segments.append(_FENCE_PLACEHOLDER.format(index))
        pos = end
    segments.append(text[pos:])
    return "".join(segments), blocks


def _restore_fenced_code(text: str, blocks: list[str]) -> str:
    """Splice the fenced code blocks lifted by :func:`_protect_fenced_code` back.

    Each placeholder token is replaced by the exact block it stands for, so
    the samples reappear byte for byte -- no pass ever saw them.
    """
    for index, block in enumerate(blocks):
        text = text.replace(_FENCE_PLACEHOLDER.format(index), block)
    return text


def _resolve_docs_href(href: str, current_slug: str, known_slugs: set[str]) -> str:
    """Resolve a site-absolute ``/docs/...`` destination for the mirror.

    Returns a link the mirrored page can follow: a relative ``.md`` path when
    the destination names a page this run discovered, or the upstream URL of
    the page when it does not (the site documents far more than the CLI tree
    this source mirrors, so ``/docs/plans`` and friends are real pages that
    simply live outside the mirror's scope).

    Only ever called with a destination the caller's pattern has already
    proved to be a documentation path: ``_DOCS_LINK_RE`` requires the literal
    ``/docs`` head, and either ends the path there or continues it with ``/``.
    The two shapes the branches below distinguish -- the bare ``/docs`` root
    and a path under it -- are therefore the only ones that can arrive, and
    the function has no third answer to give.

    The anchor is preserved on both branches: a fragment is resolved by the
    reader's browser against the target page, so it keeps working whether the
    target is a mirrored file or the upstream page. A query string is not
    preserved on the mirrored branch -- a mirrored file is a static document
    with nothing to parameterise -- but is kept verbatim on the upstream one,
    where it still selects what the site would have selected.
    """
    path, _, anchor = href.partition("#")
    suffix = f"#{anchor}" if anchor else ""
    path, _, query = path.partition("?")

    slug = path[len(DOCS_PREFIX) :].strip("/")
    if slug in known_slugs:
        # ``current_slug`` is the on-disk path of the page being rewritten, so
        # the relative path is derived the same way for every page, whatever
        # depth it sits at.
        current_dir = posixpath.dirname(current_slug) or "."
        relative = posixpath.relpath(f"{slug}.md", current_dir)
        if not relative.startswith((".", "/")):
            relative = f"./{relative}"
        return f"{relative}{suffix}"

    query_suffix = f"?{query}" if query else ""
    return f"{SITE_URL}{path.rstrip('/')}{query_suffix}{suffix}"


def _rewrite_docs_links(
    text: str, current_slug: str, known_slugs: set[str] | None = None
) -> str:
    """Repoint every site-absolute documentation link at something that resolves.

    Each ``](/docs/...)`` destination is routed through
    :func:`_resolve_docs_href`: a mirrored target becomes a relative ``.md``
    link, an unmirrored one becomes its upstream URL. Both branches fix a
    link that is dead in the mirror, and both leave the anchor alone.

    Only links are touched. A destination that is not a documentation path --
    an external URL, a mail address, an asset reference, an intra-page
    ``#anchor`` -- does not match the pattern and is copied through unchanged,
    so this pass can never break a link that already worked.

    Fenced code blocks are shielded for the duration of the pass (see
    :func:`_protect_fenced_code`), and the pass is idempotent: its output
    holds relative ``.md`` links and absolute ``https://`` URLs, neither of
    which matches the site-absolute pattern, so a second application is a
    no-op.
    """
    if known_slugs is None:
        known_slugs = _KNOWN_SLUGS

    protected, blocks = _protect_fenced_code(text)
    out: list[str] = []
    pos = 0
    for match in _iter_docs_links(protected):
        out.append(protected[pos : match.start()])
        out.append(
            f"]({_resolve_docs_href(match.group('href'), current_slug, known_slugs)})"
        )
        pos = match.end()
    out.append(protected[pos:])
    return _restore_fenced_code("".join(out), blocks)


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

    The slugs of the returned pages are also published to the module-level
    ``_KNOWN_SLUGS`` set, which is what the link pass in ``fetch_markdown``
    consults to decide whether a cross-reference can point at a mirrored file.
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
    # Publish the slugs of this run for the link pass in ``fetch_markdown``:
    # it can only point a reference at a mirrored page if it knows which pages
    # this run actually mirrors. Replacing the set wholesale (rather than
    # adding to it) keeps a run's view exact even when a page disappeared
    # upstream, so a reference to it falls back to the upstream URL instead of
    # a relative link to a file that no longer exists.
    _KNOWN_SLUGS.clear()
    _KNOWN_SLUGS.update(page.slug for page in pages)
    return ensure_discovered_pages(
        pages, "google-antigravity-cli", f"CLI docs prefix {CLI_PREFIX!r}"
    )


def fetch_markdown(client: httpx.Client, page: Page) -> tuple[str, str]:
    """Pipeline hook: fetch one page and return ``(markdown, hash)``.

    This is the optional ``fetch_markdown`` hook described in
    ``sources/base.py``. It exists for the link pass: the upstream Markdown
    is downloaded as published, every site-absolute ``/docs/...`` reference in
    it is repointed at the mirrored page (or at its upstream URL) by
    :func:`_rewrite_docs_links`, and the result is validated before the
    content hash is computed -- so the manifest hash covers exactly the
    rewritten text that is written to disk, and an unchanged page stops
    producing a diff.
    """
    raw = fetch.get_with_retry(client, page.source_md_url)
    try:
        markdown = _rewrite_docs_links(raw, page.slug)
    except Exception as exc:
        # Deliberate catch-all, re-raised as ``FetchError``: the pipeline
        # isolates failures PER PAGE only for that exception type, so anything
        # else escaping this hook would abort the whole source's run. Chaining
        # with ``from`` keeps a genuine programming error visible on
        # ``__cause__`` instead of being flattened into the FetchError.
        raise fetch.FetchError(f"link rewriting failed for {page.slug}: {exc}") from exc
    if not fetch.validate_markdown(markdown):
        raise fetch.FetchError(f"validation failed for {page.slug} (not Markdown?)")
    return markdown, fetch.content_hash(markdown)
