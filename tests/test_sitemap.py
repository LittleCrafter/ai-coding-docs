"""Tests for the sitemap crawler and parser (mirror.core.sitemap)."""

from __future__ import annotations

import pytest
from conftest import _FakeClient, _Resp
from mirror.core import fetch
from mirror.core.sitemap import crawl_sitemap, extract_locs


def test_extract_locs_parses_flat_sitemap():
    xml = """<?xml version="1.0" encoding="UTF-8"?>
    <urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
      <url><loc>https://example.com/page1</loc></url>
      <url><loc>https://example.com/page2</loc></url>
    </urlset>
    """
    assert extract_locs(xml) == [
        "https://example.com/page1",
        "https://example.com/page2",
    ]


def test_extract_locs_ignores_media_locs_and_empty():
    xml = """<?xml version="1.0" encoding="UTF-8"?>
    <urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9" xmlns:image="http://www.google.com/schemas/sitemap-image/1.1">
      <url>
        <loc>https://example.com/page1</loc>
        <image:image><image:loc>https://example.com/image.png</image:loc></image:image>
      </url>
      <url><loc>   </loc></url>
    </urlset>
    """
    assert extract_locs(xml) == ["https://example.com/page1"]


def test_extract_locs_reads_cdata_wrapped_values():
    """URLs wrapped in ``<![CDATA[ ... ]]>`` (some upstreams wrap ``&``-heavy
    URLs) must be extracted with the CDATA wrapper stripped -- ``html.parser``
    keeps the section as a text node, so the same ``get_text`` path must
    surface exactly the URL."""
    xml = """<urlset>
      <url><loc><![CDATA[https://example.com/page?a=1&b=2]]></loc></url>
    </urlset>"""
    assert extract_locs(xml) == ["https://example.com/page?a=1&b=2"]


def test_extract_locs_matches_namespaced_loc_and_parent():
    """Namespaced sitemaps (``<sm:url><sm:loc>...``) are real-world common;
    the parent check and the loc matcher must accept any namespace prefix,
    case-insensitively."""
    xml = """<sm:urlset xmlns:sm="http://www.sitemaps.org/schemas/sitemap/0.9">
      <sm:url><sm:loc>https://example.com/ns-page</sm:loc></sm:url>
      <SM:url><SM:LOC>https://example.com/ns-page-upper</SM:LOC></SM:url>
    </sm:urlset>"""
    assert extract_locs(xml) == [
        "https://example.com/ns-page",
        "https://example.com/ns-page-upper",
    ]


def test_extract_locs_recovers_from_truncated_xml():
    """A truncated document (missing closing tags at EOF) must not lose the
    URLs already seen -- lenient recovery is the reason ``html.parser`` is
    used, and a hard parse error here would silently drop pages from the
    mirror."""
    xml = """<urlset>
      <url><loc>https://example.com/page1</loc></url>
      <url><loc>https://example.com/page2"""
    assert extract_locs(xml) == [
        "https://example.com/page1",
        "https://example.com/page2",
    ]


def test_extract_locs_preserves_document_order_across_parent_types():
    """Interleaved page and child-sitemap entries must come back in the exact
    document order they appear -- the BFS crawl relies on the order of index
    entries to fetch children deterministically."""
    xml = """<sitemapindex>
      <url><loc>https://example.com/page-1</loc></url>
      <sitemap><loc>https://example.com/child-a.xml</loc></sitemap>
      <url><loc>https://example.com/page-2</loc></url>
      <sitemap><loc>https://example.com/child-b.xml</loc></sitemap>
    </sitemapindex>"""
    assert extract_locs(xml) == [
        "https://example.com/page-1",
        "https://example.com/child-a.xml",
        "https://example.com/page-2",
        "https://example.com/child-b.xml",
    ]


def test_crawl_sitemap_flat_returns_pages():
    xml = """<?xml version="1.0" encoding="UTF-8"?>
    <urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
      <url><loc>https://example.com/page1</loc></url>
      <url><loc>https://example.com/page2?utm=test#frag</loc></url>
    </urlset>
    """
    client = _FakeClient([_Resp(200, xml)])
    pages = crawl_sitemap(client, "https://example.com/sitemap.xml")  # pyright: ignore[reportArgumentType]
    assert pages == ["https://example.com/page1", "https://example.com/page2"]


def test_crawl_sitemap_follows_nested_indexes():
    root = """<sitemapindex>
      <sitemap><loc>https://example.com/child.xml</loc></sitemap>
      <url><loc>https://example.com/root-page</loc></url>
    </sitemapindex>"""
    child = """<urlset>
      <url><loc>https://example.com/child-page</loc></url>
    </urlset>"""
    client = _FakeClient([_Resp(200, root), _Resp(200, child)])
    pages = crawl_sitemap(client, "https://example.com/sitemap.xml")  # pyright: ignore[reportArgumentType]
    assert pages == ["https://example.com/root-page", "https://example.com/child-page"]


def test_crawl_sitemap_enforces_origin_guard():
    root = """<sitemapindex>
      <sitemap><loc>https://foreign.example.com/child.xml</loc></sitemap>
      <sitemap><loc>https://example.com/child.xml</loc></sitemap>
    </sitemapindex>"""
    child = """<urlset>
      <url><loc>https://example.com/child-page</loc></url>
    </urlset>"""
    client = _FakeClient([_Resp(200, root), _Resp(200, child)])
    pages = crawl_sitemap(
        client,  # pyright: ignore[reportArgumentType]
        "https://example.com/sitemap.xml",
        allowed_origin="https://example.com",
    )
    assert pages == ["https://example.com/child-page"]


def test_crawl_sitemap_cycle_detection():
    root = """<sitemapindex>
      <sitemap><loc>https://example.com/sitemap.xml</loc></sitemap>
      <sitemap><loc>https://example.com/child.xml</loc></sitemap>
    </sitemapindex>"""
    child = """<sitemapindex>
      <sitemap><loc>https://example.com/sitemap.xml</loc></sitemap>
      <url><loc>https://example.com/page-1</loc></url>
    </sitemapindex>"""
    client = _FakeClient([_Resp(200, root), _Resp(200, child)])
    pages = crawl_sitemap(client, "https://example.com/sitemap.xml")  # pyright: ignore[reportArgumentType]
    assert pages == ["https://example.com/page-1"]


def test_crawl_sitemap_max_depth_skips_and_warns(capsys):
    level0 = "<sitemapindex><sitemap><loc>https://example.com/l1.xml</loc></sitemap></sitemapindex>"
    level1 = "<sitemapindex><sitemap><loc>https://example.com/l2.xml</loc></sitemap></sitemapindex>"
    client = _FakeClient([_Resp(200, level0), _Resp(200, level1)])
    pages = crawl_sitemap(client, "https://example.com/l0.xml", max_depth=1)  # pyright: ignore[reportArgumentType]
    assert pages == []
    captured = capsys.readouterr()
    assert "warning: sitemap index nested deeper than max_depth=1" in captured.err


def test_crawl_sitemap_root_failure_raises():
    client = _FakeClient([_Resp(404, "Not Found")])
    with pytest.raises(fetch.FetchError):
        crawl_sitemap(client, "https://example.com/sitemap.xml")  # pyright: ignore[reportArgumentType]


def test_crawl_sitemap_child_failure_warns_and_continues(capsys):
    root = """<sitemapindex>
      <sitemap><loc>https://example.com/broken.xml</loc></sitemap>
      <url><loc>https://example.com/good-page</loc></url>
    </sitemapindex>"""
    client = _FakeClient(
        [_Resp(200, root), _Resp(500, "Server Error"), _Resp(500), _Resp(500)]
    )
    pages = crawl_sitemap(client, "https://example.com/sitemap.xml")  # pyright: ignore[reportArgumentType]
    assert pages == ["https://example.com/good-page"]
    captured = capsys.readouterr()
    assert "warning: failed to fetch child sitemap" in captured.err
