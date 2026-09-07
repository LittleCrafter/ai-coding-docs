"""Robust sitemap (<loc>) extraction shared by sitemap-based sources.

A sitemap document (either a sitemap index pointing at other ``.xml`` files, or
a flat URL set) lists each entry inside a ``<loc>`` element. Earlier versions of
this project pulled those URLs out with a regex (``<loc>\\s*([^<]+?)\\s*</loc>``),
which is brittle: real-world XML may carry namespaces, attributes, case
variations or ``CDATA`` sections that a regex silently mishandles.

BeautifulSoup is already a project dependency, so we delegate to it. The
``html.parser`` backend is used (rather than ``xml``) for two reasons: it
ships with bs4 itself, so no third-party XML parser such as lxml is required;
and it is deliberately *lenient* -- where a strict XML parser aborts on a
missing declaration, an unbound namespace, a stray ``&``, or the slightly
malformed markup real-world sitemaps occasionally ship, the HTML5 parser
recovers and keeps going. For the single job of "give me the text of every
``<loc>`` tag" that resilience is exactly what a mirror needs: a sitemap
that fails to parse strictly must not silently zero out a source's
discovered pages (which the pipeline would read as a mass upstream
deletion). We never re-serialize the document, so the parser's
error-correction can never leak back into the mirror.
"""

from __future__ import annotations

import re
import sys
import warnings
from collections import deque

import bs4
import httpx

from . import fetch
from .utils import clean_url, same_origin

# bs4 emits XMLParsedAsHTMLWarning whenever its HTML parser is fed XML. We parse
# sitemaps with the html.parser backend on purpose (it ships with bs4; the "xml"
# backend would require lxml), so that warning is expected for every sitemap we
# touch. Rather than mutating the process-global warning filters at module scope
# (which is not thread-safe and would suppress the warning for every other
# caller in the process), we wrap the suppression in a context manager inside
# extract_locs() so it is scoped to exactly the parses we intend.
#
# The class is referenced directly (no getattr fallback): pyproject.toml pins
# ``beautifulsoup4>=4.12``, the release that introduced XMLParsedAsHTMLWarning,
# so its existence is guaranteed by the dependency specification.

# Tag-name matcher for ``find_all`` below: matches tag names that end with
# ":loc" (the namespaced form such as <sitemap:loc> or <url:loc>) OR are
# exactly "loc" (the bare form <loc>), case-insensitive.
#
# The pattern is compiled ONCE at module import time rather than on every
# extract_locs() call (the precompile convention already used by the
# heading/frontmatter patterns in fetch.py and the slug pattern in page.py):
# compilation produces the same immutable regex object every time, so paying
# that cost per call would be pure waste, and ``re``'s internal cache is an
# implementation detail we do not rely on.
#
# Breakdown of the r"(?:^|:)loc$" pattern:
#   (?:^|:)  -- non-capturing group matching either the START of the tag
#               name (bare "loc") OR a literal colon (the XML namespace
#               separator in "sitemap:loc" / "url:loc" / any-ns:loc);
#   loc      -- the literal element local-name "loc";
#   $        -- end of the tag name anchor, so "loc" does not false-match
#               longer element names like "location" or "local";
#   re.I     -- case-insensitive matching: XML is case-sensitive by spec
#               but real-world sitemaps occasionally vary the casing of
#               the "loc" element (LOC, Loc, loc), and being lenient here
#               costs nothing while preventing silent page loss from a
#               harmless upstream casing quirk.
#
# The non-capturing group (?:...) is used instead of a capturing group
# (...) because only the FULL tag name matters for find_all() -- the
# namespace prefix alone is never needed. Avoiding capture groups keeps
# the regex engine from storing unnecessary submatch state for every tag
# in the document.
#
# This single pattern catches every known sitemap ``<loc>`` shape without
# a hardcoded list of namespace prefixes (which can differ between sitemap
# versions or across upstream sites), and the start/end anchors prevent it
# from matching unrelated elements whose name merely *contains* "loc".
_LOC_TAG_RE = re.compile(r"(?:^|:)loc$", re.I)

# Parent-tag matcher for the ``extract_locs`` parent check: accepts ``url``
# (a page entry) or ``sitemap`` (an index entry) -- the only two elements
# that legitimately carry a sitemap ``<loc>`` child -- in bare or
# namespaced form, case-insensitively, with the same ``(?:^|:)`` prefix
# convention as ``_LOC_TAG_RE``.
_PARENT_TAG_RE = re.compile(r"(?:^|:)(?:url|sitemap)$", re.I)


def extract_locs(xml_text: str) -> list[str]:
    """Return every ``<loc>`` URL in a sitemap document, in document order.

    Whitespace is stripped from each value. Empty entries are dropped.
    Entries whose parent element is neither ``<url>`` nor ``<sitemap>`` --
    e.g. the media URLs inside sitemap-extension ``<image:image>`` /
    ``<video:video>`` blocks -- are ignored, so only real page and index
    locations are returned. The returned list preserves the order the URLs
    appear in the document, which matters for sources that follow a sitemap
    index's nested ``.xml`` entries.

    ``html.parser`` is lenient by design: unlike a strict XML parser it does
    not choke on missing declarations, unbound namespaces or the slightly
    malformed markup real-world sitemaps occasionally ship. For the single
    job of "give me the text of every <loc> tag" that leniency is a feature,
    not a risk -- we never re-serialize the document.

    One notable leniency: ``html.parser`` treats self-closing XML tags
    (``<loc/>``) using HTML5 open-tag semantics, meaning a self-closing
    ``<loc/>`` is treated as an opening tag without content rather than an
    error. This is acceptable for sitemap parsing because real-world sitemaps
    always use paired ``<loc>...</loc>`` elements, and a self-closing loc
    would have no text to extract either way.
    """
    # Suppress the XML-parsed-as-HTML warning inside a context manager so the
    # filter is scoped to exactly this parse -- not leaked to every other
    # caller in the process (thread-safe, and a future threaded pipeline won't
    # accidentally suppress the warning for a caller that needs it).
    # NOTE: bs4.XMLParsedAsHTMLWarning is guaranteed to exist without getattr()
    # fallbacks because pyproject.toml enforces beautifulsoup4 >= 4.12.
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", category=bs4.XMLParsedAsHTMLWarning)
        soup = bs4.BeautifulSoup(xml_text, "html.parser")
    locs: list[str] = []
    # ``_LOC_TAG_RE`` (module level, with a full pattern breakdown) matches
    # both the bare ``<loc>`` form and any namespaced ``<ns:loc>`` variant,
    # case-insensitively.
    for loc in soup.find_all(_LOC_TAG_RE):
        # Only ``<loc>`` elements whose parent is a page entry (``<url>``)
        # or a child-sitemap reference (``<sitemap>``) are real sitemap
        # locations. Sitemap extension namespaces also define a ``<loc>``
        # child -- ``<image:image>`` and ``<video:video>`` carry
        # ``<image:loc>`` / ``<video:loc>`` -- which points at a media
        # asset rather than a page; without this parent check those URLs
        # would be extracted as bogus pages and mirrored.
        parent = loc.parent
        # ``search`` rather than ``match``: the pattern accepts a namespace
        # prefix (``sm:url``), which can only appear AFTER position 0 --
        # ``match`` anchors at the start and would silently drop every loc
        # nested under a namespaced parent.
        if parent is None or not _PARENT_TAG_RE.search(parent.name):
            continue
        # loc.get_text(strip=True) automatically decodes HTML entities such
        # as &amp; back to &. This is expected and correct for sitemap URLs:
        # a real-world sitemap may encode & as &amp; in its <loc> elements,
        # and the decoded form is the actual URL the mirror should fetch.
        text = loc.get_text(strip=True)
        if text:
            locs.append(text)
    return locs


def crawl_sitemap(
    client: httpx.Client,
    seed_url: str,
    *,
    max_depth: int = 3,
    allowed_origin: str | None = None,
) -> list[str]:
    """Fetch the sitemap, following nested sitemap indexes breadth-first.

    A sitemap index lists nested ``.xml`` sitemaps instead of (or alongside)
    page URLs; every ``<loc>`` whose path ends with ``.xml`` is treated as a
    child sitemap reference: it is enqueued, fetched, and its URLs are
    merged into the result. Any non-``.xml`` locs in the same document are
    real page URLs and are collected as-is.

    The crawl is an explicit breadth-first queue rather than recursion or a
    single hardcoded follow-one-level step, because a sitemap index can nest
    to ANY depth (e.g. ``sitemap-index.xml`` -> ``sitemap-category.xml`` ->
    ``sitemap-pages.xml``) and can also form cycles (two indexes referencing
    each other, or an index referencing itself).

    Guards:
    * ``visited``: every sitemap URL is fetched at most once, preventing cycles.
    * ``max_depth``: maximum number of index hops followed from seed_url.
    * ``allowed_origin``: if provided, child sitemaps must belong to this origin.
    """
    pages: list[str] = []
    root_cleaned = clean_url(seed_url)
    visited: set[str] = {root_cleaned}
    queue: deque[tuple[str, int]] = deque([(root_cleaned, 0)])

    while queue:
        sitemap_url, depth = queue.popleft()
        try:
            locs = extract_locs(fetch.get_with_retry(client, sitemap_url))
        except fetch.FetchError as exc:
            if depth == 0:
                raise
            print(
                f"  warning: failed to fetch child sitemap {sitemap_url!r}: {exc}",
                file=sys.stderr,
            )
            continue
        for loc in locs:
            try:
                url = clean_url(loc)
            except ValueError as exc:
                print(
                    f"  warning: skipping malformed sitemap entry {loc!r}: {exc}",
                    file=sys.stderr,
                )
                continue
            if not url.endswith(".xml"):
                pages.append(url)
                continue
            if allowed_origin is not None and not same_origin(url, allowed_origin):
                continue
            if url in visited:
                continue
            if depth + 1 > max_depth:
                print(
                    f"  warning: sitemap index nested deeper than "
                    f"max_depth={max_depth}, skipping {url!r}; pages listed "
                    "there are NOT mirrored -- raise max_depth in "
                    "crawl_sitemap if this is a legitimate upstream "
                    "restructure",
                    file=sys.stderr,
                )
                continue
            visited.add(url)
            queue.append((url, depth + 1))

    return pages
