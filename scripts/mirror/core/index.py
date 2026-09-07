"""Per-source human-readable index (docs/<source>/README.md).

Groups the mirrored pages by their `group` field and links to both the local
Markdown file and the official source page.

Group ordering follows a fixed hierarchy so the output is deterministic
across runs (the README is git-tracked -- any ordering noise would produce
phantom diffs): a group literally named "root" is always promoted to the
leading section (and displayed under the source's own title, since a bare
"root" heading would mean nothing to a reader), all other groups follow in
alphabetical order, and pages within each group are sorted by slug.

This README is the human-facing counterpart of `manifest.json`: same data,
rendered as a browsable Markdown table so that anyone opening the docs folder
on GitHub gets a usable directory of the mirror without reading JSON. It is
fully regenerated from the manifest whenever a run changes something --
never edited by hand.
"""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path

from .manifest import FileEntry, Manifest
from .utils import atomic_write, safe_url

# Single-pass escaping table for page titles rendered inside Markdown table
# cells. ``str.translate`` applies every mapping in one left-to-right pass,
# which is both faster than a chain of twelve sequential ``str.replace``
# calls and immune to the classic double-escaping bug: a chained replace of
# ``\`` followed by the other escapes only works because it happens to run
# first, whereas translate maps each *original* character exactly once, so
# ordering can never be wrong. ``\n``/``\r`` map to a space because a
# newline inside a title would split the table row and corrupt the whole
# table (titles come from upstream Markdown, which can contain anything).
_TITLE_ESCAPES = str.maketrans(
    {
        "\\": "\\\\",
        "|": "\\|",
        "[": "\\[",
        "]": "\\]",
        "*": "\\*",
        "_": "\\_",
        "`": "\\`",
        "<": "&lt;",
        ">": "&gt;",
        "&": "&amp;",
        "\n": " ",
        "\r": " ",
    }
)

# Newline/carriage-return collapsing for group labels rendered as ``## ...``
# section headings. Group names are upstream-derived (URL path segments from
# sitemaps/manifests), so -- like titles -- they can in principle contain
# anything. A literal ``\n``/``\r`` in a label would split the heading across
# two lines and inject a stray, uncontrolled line into the generated README
# layout, so both are collapsed to a space, mirroring the ``\n``/``\r``
# entries of ``_TITLE_ESCAPES`` above. The full title-escape table is NOT
# reused here on purpose: a heading is not a table cell, so characters like
# ``|`` or ``*`` cannot corrupt the layout the way they would inside a row,
# and backslash-escaping them would only add raw-Markdown noise to the
# heading text.
_GROUP_LABEL_ESCAPES = str.maketrans({"\n": " ", "\r": " "})


def render(manifest: Manifest, source_title: str, source_home_url: str) -> str:
    """Render the full README Markdown for one source from its manifest.

    Pages with an empty `group` are bucketed under "Documentation" so they
    still get a section heading. Group order is deterministic -- alphabetical,
    except a group literally named "root" which always leads -- and pages
    within a group are sorted by slug. Determinism matters: the README is
    git-tracked, so any run-to-run ordering noise would produce phantom diffs.

    Args:
        manifest: The loaded (or freshly built) manifest for this source.
            Every entry in ``manifest.files`` becomes one table row: the
            entry's ``title`` is escaped via ``_TITLE_ESCAPES`` and its
            ``source_url`` is sanitised via ``safe_url`` before interpolation,
            because both values originate upstream and could carry characters
            that corrupt the table or the link destination. The entry's
            ``group`` names the ``## `` section the row is filed under; its
            newlines/carriage returns are collapsed to spaces via
            ``_GROUP_LABEL_ESCAPES`` before interpolation, because group
            names are upstream-derived (URL path segments) and a raw line
            break would split the section heading and corrupt the README
            layout.
        source_title: Human-readable source name (e.g. "Claude Code"),
            rendered raw into the ``# ... — Documentation Index`` header and
            used as the section heading for the promoted "root" group.
        source_home_url: Link to the source's official docs landing page.
            TRUST ASSUMPTION: unlike per-page ``source_url`` values (which
            come from sitemaps/manifests and therefore pass through
            ``safe_url``), this is a trusted per-source constant owned by the
            caller (the source adapter's config) and is interpolated RAW --
            unescaped -- into the Markdown header line. Never pass
            untrusted, upstream-derived data through this parameter.

    Returns:
        The complete README Markdown document, terminated by exactly one
        trailing newline.
    """
    files = list(manifest.files.values())
    groups: dict[str, list[FileEntry]] = defaultdict(list)
    for f in files:
        groups[f.group or "Documentation"].append(f)

    # Deterministic order: sort group names alphabetically, but promote a
    # group literally named "root" (case-sensitive) to always lead. The
    # case-sensitive comparison is intentional: only the exact lowercase
    # string "root" receives the special promotion. Variants like "Root"
    # or "ROOT" are ordinary group names that sort alphabetically alongside
    # the other groups -- this is by design, because a group name that
    # merely starts with those letters (e.g. a category of root-level
    # topics) should not be mistakenly promoted to the top.
    # Note: Python boolean sorting evaluates False < True, so False comes first.
    group_names = sorted(groups, key=lambda g: (g != "root", g))

    lines: list[str] = [
        f"# {source_title} — Documentation Index",
        "",
        (
            "Auto-generated mirror. Each entry links to the local Markdown copy "
            "and to the official page."
        ),
        "",
        f"- **Pages mirrored:** {len(files)}",
    ]
    if manifest.version and manifest.version != "—":
        lines.append(f"- **Version:** {manifest.version}")
    lines.extend(
        [
            f"- **Last updated:** {manifest.last_updated}",
            "- **Official docs:** " + source_home_url,
            "- **Machine-readable index:** [`manifest.json`](./manifest.json)",
            "",
        ]
    )

    for name in group_names:
        entries = sorted(groups[name], key=lambda e: e.slug)
        # The "root" group gets the source's own name as heading -- a bare
        # "root" would mean nothing to a reader. (Group names are never empty
        # here: falsy groups were remapped to "Documentation" above.)
        # Upstream-derived group names are passed through
        # ``_GROUP_LABEL_ESCAPES`` to collapse any embedded newlines/carriage
        # returns to spaces before they reach the ``## `` heading; the
        # "root" branch needs no such treatment because ``source_title`` is
        # a trusted per-source constant (see the Args section above), not
        # upstream-derived data.
        label = name.translate(_GROUP_LABEL_ESCAPES) if name != "root" else source_title
        lines.append(f"## {label}")
        lines.append("")
        lines.append("| Page | Local | Source |")
        lines.append("| --- | --- | --- |")
        for e in entries:
            title = e.title.translate(_TITLE_ESCAPES)
            # The link destination is wrapped in angle brackets
            # (``<...>``, valid CommonMark) because ``source_url`` is
            # interpolated raw: a URL containing a space or a ``)`` would
            # otherwise terminate the bare ``(...)`` destination early and
            # silently break the link. Inside angle brackets, spaces and
            # parentheses are legal destination characters. Angle brackets
            # do not cover everything, though -- ``<``, ``>``, and line
            # endings are still forbidden there -- so the URL first passes
            # through ``safe_url``, which percent-encodes exactly those.
            # ``safe_url`` ALSO percent-encodes ``|``: this very row is a GFM
            # table cell, so a raw ``|`` inside the URL would be read as a
            # column separator and split the cell in two. That keeps the URL
            # field's escaping consistent with the title field (escaped via
            # ``_TITLE_ESCAPES`` above) and the slug field (whose charset
            # excludes ``|`` at validation time).
            lines.append(
                f"| {title} | [{e.slug}.md](./{e.slug}.md) | "
                f"[source](<{safe_url(e.source_url)}>) |"
            )
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def write(
    path: Path, manifest: Manifest, source_title: str, source_home_url: str
) -> None:
    """Write the rendered index to `path`, creating parent dirs on first run.

    The write is atomic against process-level failures (Python exceptions and
    SIGTERM): the atomic-write mechanics are delegated to
    ``utils.atomic_write``, which stages the rendered payload in a
    uniquely-named sibling temp file (``README.md.<pid>_<token>.tmp``) and then
    ``Path.replace``s it over the target in one filesystem operation, so a
    crash or kill between write and rename can never leave a truncated README
    behind -- readers (and git) only ever see the old file or the new one. The
    temp file is not ``fsync``-ed before the rename, so this guarantee does NOT
    extend to power loss / kernel panic (rename is metadata-atomic only); the
    next mirror run regenerates the README, so a torn write self-heals. The
    best-effort temp-file cleanup on failure also lives inside
    ``utils.atomic_write`` (logged, never masking the original error);
    ``manifest.save`` and ``pipeline.write_top_index`` delegate to the same
    helper, so every call site shares identical crash-safe semantics.

    Args:
        path: Destination path (``docs/<source>/README.md``). Its parent
            directory is created here on first run, which also satisfies
            ``atomic_write``'s parent-must-exist precondition.
        manifest: The manifest for this source; every entry becomes one table
            row (see `render` for the per-field escaping contract).
        source_title: Human-readable source name, rendered raw into the
            header (see `render`).
        source_home_url: Trusted per-source constant interpolated RAW
            (unescaped) into the Markdown header -- see `render` for the
            trust assumption this relies on and why it is safe here.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = render(manifest, source_title, source_home_url)
    # Delegate the atomic write (temp file + rename + best-effort cleanup) to
    # the shared utility function so every call site uses the same crash-safe
    # pattern with identical semantics. The parent directory is guaranteed to
    # exist by the mkdir call above, satisfying atomic_write's precondition.
    atomic_write(path, payload)
