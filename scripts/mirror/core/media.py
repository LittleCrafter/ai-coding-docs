"""Static-asset mirroring stage: download upstream images and fix local refs.

Some upstream docs embed relative image references that a mirror cannot
preserve verbatim.  kimi-code pages reference ``![...](../../media/x.jpg)``
(assets living in the ``docs/media/`` directory of MoonshotAI/kimi-code,
correct at the source) and opencode pages reference
``![...](../../assets/<relpath>)`` (assets in ``packages/web/src/assets/``
of anomalyco/opencode).  Those prefixes only resolve in the UPSTREAM tree:
pages there sit two directories above the asset roots, while the mirrored
tree relocates each page to ``docs/<source>/<slug>.md`` with no matching
sibling directories -- so every such image renders broken in the mirror.
This stage downloads each referenced asset into ``docs/<source>/<asset-dir>/``
and rewrites the in-text references to relative paths that resolve from the
page's mirrored location, making the mirror self-contained.

The stage is SOURCE-AGNOSTIC by design: ``core/`` never imports or
references a concrete source adapter.  Every per-source fact travels in an
`AssetSourceConfig`
(asset directory name, upstream raw base URL, and the exact ref prefixes to
rewrite); the source adapter that wants media mirroring exposes a
``MEDIA = media.AssetSourceConfig(...)`` module attribute and the pipeline
wires the stage when that attribute exists (the same getattr discovery
pattern ``pipeline`` already uses for a source's custom ``fetch_markdown``).
Four real sources fit this shape today (antigravity, claude-code, kimi-code,
opencode); a further source whose upstream images are structured differently
just means another config.

Pipeline integration point: the stage must run AFTER ``fetch_pages`` --
fresh texts (and the carried-forward / failed split) must already exist --
and BEFORE ``diff`` and ``write_docs``.  ``stage_pages`` rewrites each fresh
page text and REPLACES that entry's text + ``content_hash`` on the returned
``entries``/``texts`` (``dataclasses.replace`` style) so the change
detection downstream compares rewritten text against what is actually on
disk, and write_docs persists pages whose only change is the rewritten
reference.  Determinism is preserved end-to-end: the rewritten text is a
pure function of the fresh text (the ref prefixes are fixed per source), so
a page mirrored once is not "changed" again on the next run.

Safety properties enforced across the module:

  * writes are atomic (``utils.atomic_write_bytes``) and skip the
    filesystem when the on-disk bytes already match the downloaded ones --
    an unchanged asset costs no rename, keeping git noise at zero;
  * pruning only deletes files INSIDE the per-source asset directory, only
    on runs that carried every manifest entry forward with fresh text (a
    carried-forward page keeps its already-rewritten on-disk refs, which
    fresh text extraction cannot see, so pruning on such a run could orphan
    those pages' images), and NEVER when the reference set is empty (a
    transient failure mid-run would otherwise read as "no assets wanted"
    and wipe the whole directory);
  * reference traversal cannot escape the asset directory: refs whose
    remainder normalizes to ``..``/absolute paths are treated as unrelated
    text (never downloaded, never rewritten), mirroring the
    ``page.validate_slug`` traversal-guard culture.

Note on the config shape: `AssetSourceConfig` deliberately carries NO
filesystem paths (only the asset directory NAME).  The output base
(``docs/<source>``) is passed as ``source_dir`` at each call site, exactly
like ``pipeline.write_docs(base, ...)`` -- tests monkeypatch
``config.DOCS_DIR`` and run against isolated temp trees, and baking a
resolved ``Path`` into an import-time config would break that isolation.
"""

from __future__ import annotations

import hashlib
import os
import posixpath
import re
from collections.abc import Mapping, Set
from dataclasses import dataclass, replace
from pathlib import Path
from typing import TYPE_CHECKING

from . import fetch
from .utils import atomic_write_bytes

if TYPE_CHECKING:
    import httpx

    from .manifest import FileEntry


@dataclass(frozen=True)
class AssetSourceConfig:
    """Per-source rules describing how one mirror source references assets.

    All six fields together must describe EXACTLY one upstream layout: the
    directory the assets live in under the mirrored ``docs/<source>`` tree,
    the raw base URL the assets download from, and the reference prefixes
    (as written in upstream page text) that identify references to those
    assets.  A source whose pages reference assets through several depths
    (e.g. ``../../media/`` on one page level and ``../../../media/`` on a
    deeper one) lists one prefix per depth.

    Args:
        name: The source name (matches the docs/<source> directory and the
            pipeline's source registry), used in diagnostics only.
        asset_subdir: Name of the single directory under ``docs/<source>``
            that receives the assets.  Flat for kimi-code (``"media"``);
            nested upstream layouts are preserved automatically inside it.
        ref_prefixes: One or more exact string prefixes that mark an asset
            reference in page text (e.g. ``("../../media/",)``).  Each must
            end in ``/``.  When several prefixes are listed and one is a
            textual prefix of another, list the LONGER one first (the
            alternation tries them in order).
        raw_base_url: Absolute base URL the assets download from; must end
            in ``/``.  The asset's normalized path is appended verbatim.
            Empty for a source whose references are already absolute URLs
            (claude-code): the matched reference is then downloaded as
            written instead of being rebuilt from a base.
        strip_token_depth: Number of leading path segments to drop from every
            reference remainder before it becomes an asset path, for upstream
            URLs that carry a per-deployment token directory (claude-code's
            ``https://mintcdn.com/claude-code/<token>/<path>``).  ``0`` keeps
            the remainder whole.  A remainder with fewer segments than the
            configured depth yields no reference at all (see ``extract_refs``),
            so a malformed URL can never be reduced to a meaningless path.
        allowed_extensions: Lowercase extension whitelist (``.png``,
            ``.svg``, ...) applied to the reference remainder; ``None``
            accepts every extension.  Mirrors only the asset kinds the
            markdown readers render, so an inline data URL or a script source
            that happens to share a configured prefix is not downloaded.
    """

    name: str
    asset_subdir: str
    ref_prefixes: tuple[str, ...]
    raw_base_url: str = ""
    strip_token_depth: int = 0
    allowed_extensions: tuple[str, ...] | None = None

    def __post_init__(self) -> None:
        # Validate the immutable rules once at construction: a typo in any
        # field would otherwise surface only as silently-missed rewrites or
        # -- worse -- a remainder that escapes the asset directory.  The
        # asset_subdir checks keep it a single safe path segment, so the
        # download/prune trees can never leave ``docs/<source>`` itself.
        if not self.name.strip():
            raise ValueError("AssetSourceConfig.name must not be blank")
        if (
            not self.asset_subdir
            or self.asset_subdir in (".", "..")
            or "/" in self.asset_subdir
            or "\\" in self.asset_subdir
        ):
            raise ValueError(
                f"AssetSourceConfig.asset_subdir must be a single safe path "
                f"segment, got {self.asset_subdir!r}"
            )
        if not self.ref_prefixes or any(
            not prefix or not prefix.endswith("/") for prefix in self.ref_prefixes
        ):
            raise ValueError(
                "AssetSourceConfig.ref_prefixes must be non-empty and every "
                "prefix must end in '/'"
            )
        if self.raw_base_url and not self.raw_base_url.endswith("/"):
            raise ValueError(
                f"AssetSourceConfig.raw_base_url must end in '/', got "
                f"{self.raw_base_url!r}"
            )
        if self.strip_token_depth < 0:
            raise ValueError("AssetSourceConfig.strip_token_depth must be >= 0")


@dataclass(frozen=True)
class AssetRef:
    """One reference to an asset, as found in a page text.

    Attributes:
        raw: The exact matched substring of the page text (configured
            prefix + the reference remainder, e.g. ``"../../media/x.jpg"``).
        asset_path: The normalized POSIX path of the asset RELATIVE TO the
            asset directory (``"x.jpg"``, ``"web/y.png"``) -- the key used
            for deduplication, the download URL, the on-disk location, and
            pruning.  Traversal-carrying refs are never turned into
            ``AssetRef`` objects.
        download_url: The absolute URL to fetch the asset from. If empty,
            defaults to ``config.raw_base_url + asset_path``.
    """

    raw: str
    asset_path: str
    download_url: str = ""


@dataclass(frozen=True)
class AssetDownload:
    """One planned asset download: where it comes from and where it lands.

    Attributes:
        url: The absolute upstream URL (``raw_base_url + asset_path`` or
            resolved from ``AssetRef.download_url``).
        local_path: The destination under ``docs/<source>``
            (``source_dir / asset_subdir / asset_path``).
        asset_path: Same key as ``AssetRef.asset_path`` (kept here so
            download results and the prune reference set do not need the
            originating refs).
    """

    url: str
    local_path: Path
    asset_path: str


@dataclass(frozen=True)
class AssetDownloadResult:
    """Outcome of one ``download_assets`` pass, for the pipeline report.

    ``failed`` is an ordered tuple of ``(url, reason)`` pairs; a failure on
    one asset never aborts the others (a single renamed upstream file must
    not take the rest of the stage down with it -- the failed asset is
    simply retried on the next run).
    """

    written: int
    cached: int
    failed: tuple[tuple[str, str], ...] = ()


@dataclass(frozen=True)
class MediaStageResult:
    """Aggregate outcome of one ``stage_pages`` call, for the pipeline report.

    Attributes:
        assets_written: Assets written to disk (new or changed bytes).
        assets_cached: Assets already on disk with identical bytes (no write).
        assets_failed: ``(url, reason)`` pairs for assets that could not be
            fetched or written (the page refs for those are still rewritten
            deterministically; a healthy next run heals them).
        pages_rewritten: Pages whose text changed because their refs were
            rewritten to the mirrored relative paths.
        files_pruned: Files and emptied directories removed from the asset
            directory because no page referenced them this run.
    """

    assets_written: int
    assets_cached: int
    assets_failed: tuple[tuple[str, str], ...] = ()
    pages_rewritten: int = 0
    files_pruned: int = 0


def _ref_pattern(config: AssetSourceConfig) -> re.Pattern[str]:
    """Compile the extraction pattern for a config's reference prefixes.

    The pattern consumes BOTH the prefix and the reference remainder, so a
    substitution can replace the whole reference in one match.  The
    remainder charset is deliberately bounded to ``[^\\s)\\"'<>]+`` --
    whitespace, closing parens, quotes, and angle brackets terminate a
    Markdown image/link destination -- and the prefixes are literal
    ``re.escape``d text, so there is no unbounded/nested quantifier and the
    scan is linear in the page length (a page body is raw network input, so
    the house ReDoS rules apply).  A filename legitimately containing ``(``
    is fine: the charset only excludes the CLOSING paren.
    """
    alternation = "|".join(re.escape(prefix) for prefix in config.ref_prefixes)
    return re.compile(rf"({alternation})([^\s)\"'<>]+)")


def _normalized_asset_path(remainder: str) -> str | None:
    """Normalize a ref remainder to a safe asset-dir-relative POSIX path.

    The remainder is the text between the configured prefix and the first
    terminator character (whitespace, ``)``, quotes, angle brackets) --
    unchecked network input that may contain ``..`` segments, or even be
    absolute.  ``posixpath.normpath`` resolves the segment runs; a result of
    ``.``/``..``, one that still climbs above the asset directory
    (``../...``), or an absolute path would let a hostile or broken
    reference escape ``docs/<source>/<asset-dir>`` on download and prune, so
    such refs return ``None`` and are treated as unrelated text everywhere
    (never downloaded, never rewritten, never pruned-against).

    Args:
        remainder: Raw text captured after a configured ref prefix.

    Returns:
        The normalized POSIX path relative to the asset directory, or
        ``None`` when the reference would escape the directory.
    """
    if "\\" in remainder:
        # A backslash is a path separator on Windows, where ``Path`` would
        # interpret it and let a remainder like ``..\\..\\x.png`` escape the
        # asset directory. This stage targets POSIX paths only, so treat the
        # backslash as hostile input and refuse the reference outright.
        return None
    clean_remainder, _, _ = remainder.partition("?")
    clean_remainder, _, _ = clean_remainder.partition("#")
    normalized = posixpath.normpath(clean_remainder)
    if (
        normalized == "."
        or normalized == ".."
        or normalized.startswith("../")
        or posixpath.isabs(normalized)
    ):
        return None
    return normalized


def extract_refs(text: str, config: AssetSourceConfig) -> tuple[AssetRef, ...]:
    """Find every asset reference in a page text, in document order.

    Only references that start with one of the configured prefixes and whose
    remainder stays inside the asset directory (see
    ``_normalized_asset_path``) are returned.  Already-rewritten references
    (``../media/x.jpg``, ``assets/y.png``), absolute URLs, and unrelated
    prefixes pass through untouched -- which is also what makes the
    rewrite idempotent.

    Args:
        text: The page text to scan.
        config: The per-source asset rules.

    Returns:
        One ``AssetRef`` per occurrence (duplicates included; deduplication
        happens when downloads are planned), in document order.
    """
    pattern = _ref_pattern(config)
    refs = []
    for match in pattern.finditer(text):
        raw_prefix = match.group(1)
        raw_remainder = match.group(2)
        clean_remainder, _, _ = raw_remainder.partition("?")
        clean_remainder, _, _ = clean_remainder.partition("#")
        if config.allowed_extensions is not None:
            ext = posixpath.splitext(clean_remainder)[1].lower()
            if ext not in config.allowed_extensions:
                continue
        remainder = clean_remainder
        if config.strip_token_depth > 0:
            parts = clean_remainder.split("/", config.strip_token_depth)
            if len(parts) > config.strip_token_depth:
                remainder = parts[-1]
            else:
                continue
        normalized = _normalized_asset_path(remainder)
        if normalized is not None:
            download_url = "" if config.raw_base_url else (raw_prefix + clean_remainder)
            refs.append(
                AssetRef(
                    raw=match.group(0),
                    asset_path=normalized,
                    download_url=download_url,
                )
            )
    return tuple(refs)


def rewrite_refs(
    text: str, config: AssetSourceConfig, source_dir: Path, slug: str
) -> str:
    """Rewrite every asset reference in *text* to a mirrored-relative path.

    Each matched reference is replaced by the path of its asset file
    relative to the PAGE's mirrored directory -- ``os.path.relpath`` from
    ``source_dir / <slug-dir>`` to ``source_dir / asset_subdir / <path>`` --
    so the rewritten reference resolves when the page is rendered from its
    mirrored location.  Only references that exactly match a configured
    prefix are touched (see `extract_refs`); everything else -- absolute
    URLs, already-rewritten references, unrelated prefixes -- is left
    byte-identical.  Rewriting therefore never changes text that a previous
    run already rewrote (idempotent), never touches refs of other kinds,
    and the result is a pure function of *text*.

    Args:
        text: The page text to rewrite (normally a FRESH upstream text, but
            the function is safe on already-rewritten text).
        config: The per-source asset rules.
        source_dir: The ``docs/<source>`` base directory of the source.
        slug: The page's slug (``"guides/web"``, ``"web"``), used to locate
            the page's directory relative to ``source_dir``.

    Returns:
        *text* with every configured asset reference rewritten, or *text*
        unchanged when it contains none.
    """
    # The slug's on-disk file lives at ``source_dir/<slug>.md``; the page's
    # directory is what rewritten references must resolve from.  Slugs are
    # pre-validated (``page.validate_slug``) to be traversal-free, so the
    # ``/`` segments here are plain directory nesting.
    page_dir = (source_dir / slug).parent
    pattern = _ref_pattern(config)

    def _relative_replacement(match: re.Match[str]) -> str:
        raw_remainder = match.group(2)
        clean_remainder, _, _ = raw_remainder.partition("?")
        clean_remainder, _, _ = clean_remainder.partition("#")
        if config.allowed_extensions is not None:
            ext = posixpath.splitext(clean_remainder)[1].lower()
            if ext not in config.allowed_extensions:
                return match.group(0)
        remainder = clean_remainder
        if config.strip_token_depth > 0:
            parts = clean_remainder.split("/", config.strip_token_depth)
            if len(parts) > config.strip_token_depth:
                remainder = parts[-1]
            else:
                return match.group(0)
        normalized = _normalized_asset_path(remainder)
        if normalized is None:
            # Unsafe reference: leave the matched text byte-identical so a
            # traversal attempt cannot smuggle a rewrite that escapes the
            # asset directory.
            return match.group(0)
        target = source_dir / config.asset_subdir / normalized
        # os.path.relpath yields OS-native separators; the mirrored docs and
        # the emitted references must always use POSIX "/" (they are
        # rendered on the web and stored in git), so native backslashes are
        # converted on the platform that produces them.
        relative = os.path.relpath(target, page_dir)
        return relative.replace(os.sep, "/")

    return pattern.sub(_relative_replacement, text)


def plan_downloads(
    texts: Mapping[str, str], config: AssetSourceConfig, source_dir: Path
) -> tuple[AssetDownload, ...]:
    """Scan fresh page texts and plan the download set for this run.

    References are deduplicated by their normalized asset path -- two pages
    referencing the same image must produce exactly one download -- and the
    plan is deterministic: assets appear in first-reference order across
    *texts* (an insertion-ordered mapping).  Assets whose references failed
    extraction (traversal-carrying) are not planned at all.

    With ``strip_token_depth`` configured, two upstream URLs that differ only
    in the stripped CDN deployment-token segment normalize to the SAME asset
    path and merge into one download: the FIRST reference wins, and every
    page pointing at the losing URL is still rewritten to that single local
    file. This is deliberate -- the token is a deployment detail, not page
    content, and keying by raw URL would mirror the same image once per
    token -- but it means a run that sees pages from two different
    deployments serves the winning deployment's bytes everywhere.

    Args:
        texts: Mapping of slug to fresh page text (as returned by
            ``fetch_pages``); typically every text of the run.
        config: The per-source asset rules.
        source_dir: The ``docs/<source>`` base directory of the source.

    Returns:
        The ordered, deduplicated download plan.
    """
    planned: dict[str, AssetDownload] = {}
    for text in texts.values():
        for ref in extract_refs(text, config):
            if ref.asset_path not in planned:
                url = (
                    ref.download_url
                    if ref.download_url
                    else (config.raw_base_url + ref.asset_path)
                )
                planned[ref.asset_path] = AssetDownload(
                    url=url,
                    local_path=source_dir / config.asset_subdir / ref.asset_path,
                    asset_path=ref.asset_path,
                )
    return tuple(planned.values())


def _file_matches(path: Path, data: bytes) -> bool:
    """Return True when *path* exists and holds exactly the bytes of *data*.

    The comparison is deliberately two-stage: a size check rejects most
    mismatches for free (no I/O), and only a file of identical length is
    read for the sha256 comparison.  Hashing both sides -- rather than
    ``path.read_bytes() == data`` -- never holds a second full copy of the
    payload in memory.  Any ``OSError`` reading the file (permissions,
    vanished file) reads as "does not match", which routes the caller to the
    write path; if that write fails too, the write path reports it.

    Args:
        path: The on-disk file to compare (need not exist).
        data: The downloaded bytes to compare against.

    Returns:
        True when *path* exists and its bytes are identical to *data*.
    """
    try:
        if not path.is_file() or path.stat().st_size != len(data):
            return False
    except OSError:
        # Stat raced with a delete (or the path is unreadable): treat as a
        # mismatch so the caller (re)writes the file.
        return False
    expected = hashlib.sha256(data).digest()
    try:
        hasher = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(64 * 1024), b""):
                hasher.update(chunk)
        return hasher.digest() == expected
    except OSError:
        return False


def download_assets(
    client: httpx.Client, downloads: tuple[AssetDownload, ...]
) -> AssetDownloadResult:
    """Download every planned asset, writing only bytes that changed on disk.

    Each asset is fetched as raw binary (``fetch.fetch_binary`` -- no text
    decode, markdown validation is meaningless for an image), compared
    against the on-disk file, and written via ``utils.atomic_write_bytes``
    ONLY when the bytes differ or the file is missing.  An unchanged asset
    therefore costs a network fetch but no filesystem write and no rename,
    keeping successive runs git-clean even for binary content.  Failures are
    isolated per asset: a fetch error or a write error records
    ``(url, reason)`` in the result and the remaining downloads proceed --
    a single renamed upstream file must not abort the stage.

    Args:
        client: The shared httpx client (``fetch.make_client()``).
        downloads: The run's download plan (see ``plan_downloads``).

    Returns:
        The aggregated outcome (written/cached counts, per-asset failures).
    """
    written = 0
    cached = 0
    failed: list[tuple[str, str]] = []
    for download in downloads:
        try:
            data = fetch.fetch_binary(client, download.url)
        except fetch.FetchError as exc:
            failed.append((download.url, str(exc)))
            continue
        # Skip the write when the on-disk file already holds these exact
        # bytes: no write, no rename, no new git blob for an unchanged asset.
        if _file_matches(download.local_path, data):
            cached += 1
            continue
        try:
            # The destination directory (asset dir plus any nested upstream
            # subdirectories, e.g. opencode's ``web/``/``lander/``) may not
            # exist on the first run; normalized asset paths are validated
            # traversal-free, so mkdir stays inside the asset directory.
            download.local_path.parent.mkdir(parents=True, exist_ok=True)
            atomic_write_bytes(download.local_path, data)
            written += 1
        except OSError as exc:
            failed.append(
                (download.url, f"could not write {download.local_path}: {exc}")
            )
    return AssetDownloadResult(written=written, cached=cached, failed=tuple(failed))


def prune_assets(
    config: AssetSourceConfig, source_dir: Path, referenced: Set[str]
) -> int:
    """Delete files inside the asset dir that no page referenced this run.

    Assets whose pages dropped them upstream (or whose pages disappeared)
    would otherwise accumulate forever; pruning keeps the asset directory an
    exact image of what the CURRENT run's pages reference.  The walk is
    strictly confined to ``source_dir / config.asset_subdir`` -- files
    outside it (the pages themselves, other sources' files) are never
    touched -- and directories that the deletions empty are removed
    deepest-first, so a stale nested group (e.g. opencode's ``web/`` after a
    screenshot rename) disappears wholesale.

    Two guards make pruning safe against the failure modes that could
    otherwise wipe good files:

      * an EMPTY *referenced* set prunes nothing.  It is the module's
        last line of defense when a run stage sees no assets at all: that
        state is indistinguishable from "the run failed before it could
        collect references" and must never read as "delete everything";
      * *referenced* must be the COMPLETE reference set of the run (the
        caller derives it from the same texts that produced the rewrites).
        The stage_pages caller additionally refuses to prune at all on runs
        with carried-forward entries, whose already-rewritten on-disk refs
        this run's fresh texts cannot see.

    Args:
        config: The per-source asset rules.
        source_dir: The ``docs/<source>`` base directory of the source.
        referenced: Normalized asset paths (relative to the asset dir) that
            this run's pages reference; everything else is deleted.

    Returns:
        The number of files and emptied directories removed.
    """
    if not referenced:
        # See the docstring guard: an empty set must never be interpreted as
        # "no assets wanted, delete them all".
        return 0
    asset_dir = source_dir / config.asset_subdir
    if not asset_dir.is_dir():
        return 0
    removed = 0
    directories: list[Path] = []
    for path in sorted(asset_dir.rglob("*")):
        if path.is_dir():
            directories.append(path)
            continue
        # Match the on-disk file against the reference set via its
        # asset-dir-relative POSIX path (the same key downloads were keyed
        # on, so a file we wrote this run is never pruned right after).
        relative = path.relative_to(asset_dir).as_posix()
        if relative not in referenced:
            path.unlink(missing_ok=True)
            removed += 1
    # Remove directories the deletions emptied, deepest first, so a nested
    # subtree collapses bottom-up in one pass.  rmdir only succeeds on empty
    # directories; any residual file keeps its directory (and its parent).
    for directory in sorted(
        directories, key=lambda item: len(item.parts), reverse=True
    ):
        try:
            directory.rmdir()
            removed += 1
        except OSError:
            # Not empty (or otherwise not removable): keep it -- a directory
            # containing referenced files must survive.
            pass
    return removed


def stage_pages(
    client: httpx.Client,
    config: AssetSourceConfig,
    source_dir: Path,
    entries: dict[str, FileEntry],
    texts: dict[str, str],
) -> tuple[dict[str, FileEntry], dict[str, str], MediaStageResult]:
    """Run the whole media stage over one source's pages of one mirror run.

    Orchestrates the four steps in order:

      1. plan -- extract asset references from the fresh page texts and
         deduplicate them into the download set;
      2. download -- fetch every asset as binary, writing only when the
         on-disk bytes differ, isolating per-asset failures;
      3. rewrite -- replace each page's refs with mirrored-relative paths,
         and when a page's text changed, replace that page's entry hash
         with ``fetch.content_hash`` of the REWRITTEN text, so downstream
         change detection compares like with like (the on-disk text after
         write_docs will be the rewritten text);
      4. prune -- remove asset-dir files the run no longer references,
         ONLY when every manifest entry carried fresh text this run (no
         carry-forwards; see `prune_assets` for the reasoning) and never
         when the reference set is empty.

    Contract with the caller: *entries* and *texts* must be the direct
    output of ``fetch_pages`` -- every key of *texts* is a key of *entries*
    (fresh pages), and entries whose slug is absent from *texts* are
    carried-forward failures whose texts and hashes must be left untouched.
    The returned (entries, texts) pair is what the pipeline feeds to
    ``diff``/``write_docs`` in place of the fetched pair; pages whose text
    did not change are returned as the SAME objects (no copy), so only
    affected pages differ from the fetched state.

    Args:
        client: The shared httpx client (``fetch.make_client()``).
        config: The per-source asset rules (``source.MEDIA``).
        source_dir: The ``docs/<source>`` base directory of the source.
        entries: ``{slug: FileEntry}`` as returned by ``fetch_pages``.
        texts: ``{slug: fresh markdown text}`` as returned by
            ``fetch_pages``.

    Returns:
        The updated ``(entries, texts)`` pair plus the stage result for the
        pipeline's per-source report.
    """
    downloads = plan_downloads(texts, config, source_dir)
    downloaded = download_assets(client, downloads)

    # --- Rewrite refs page by page and re-hash the changed texts -----------
    # Only pages whose text ACTUALLY changed get a replaced entry; the hash
    # replacement keeps diff() from flagging (or write_docs from rewriting)
    # a page whose only difference from disk would be the rewritten refs.
    # fetch.content_hash is the SAME function fetch_pages hashed the fresh
    # texts with, so hashes stay comparable across the two stages.
    rewritten_texts = dict(texts)
    updated_entries = dict(entries)
    pages_rewritten = 0
    for slug, text in texts.items():
        rewritten = rewrite_refs(text, config, source_dir, slug)
        if rewritten != text:
            rewritten_texts[slug] = rewritten
            updated_entries[slug] = replace(
                updated_entries[slug], hash=fetch.content_hash(rewritten)
            )
            pages_rewritten += 1

    # --- Prune unreferenced assets (gated on a fully-fresh run) -------------
    # A slug present in entries but absent from texts is a carried-forward
    # page (failed fetch, old entry + old hash preserved): its on-disk page
    # still carries LAST run's already-rewritten refs, which fresh-text
    # extraction cannot see -- pruning against the fresh reference set
    # would delete the assets that page still displays.  When every entry
    # has fresh text the reference set is complete and pruning is safe.
    files_pruned = 0
    if all(slug in texts for slug in entries):
        files_pruned = prune_assets(
            config, source_dir, {download.asset_path for download in downloads}
        )

    result = MediaStageResult(
        assets_written=downloaded.written,
        assets_cached=downloaded.cached,
        assets_failed=downloaded.failed,
        pages_rewritten=pages_rewritten,
        files_pruned=files_pruned,
    )
    return updated_entries, rewritten_texts, result
