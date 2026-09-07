"""Core building blocks shared across all documentation sources.

This package holds the *source-agnostic* half of the mirror pipeline:

  * :mod:`~.page`        -- the `Page` discovery record every source produces;
  * :mod:`~.fetch`       -- download, validate and hash a Markdown URL;
  * :mod:`~.manifest`    -- the machine-readable, git-tracked run state;
  * :mod:`~.diff`        -- compare two manifests into an added/removed/
                            modified/renamed `ChangeSet`;
  * :mod:`~.index`       -- render the per-source human-readable README;
  * :mod:`~.whats_new`   -- render the per-day change log;
  * :mod:`~.sitemap`     -- parse sitemap XML for sitemap-based sources;
  * :mod:`~.github`      -- auth/headers for GitHub-API-based sources;
  * :mod:`~.html_markdown` -- shared HTML-to-Markdown conversion pipeline
                            (html2text config, Cf stripping, blank-line collapse,
                            code-block splicing) consumed by the Antigravity and
                            DeepSeek source adapters;
  * :mod:`~.link_checker` -- verify internal/relative Markdown links across
                            the mirrored documentation tree;
  * :mod:`~.media`       -- static media/asset mirroring shared by every
                            source that mirrors images (config-driven ref
                            extraction, download, in-page rewrite, pruning);
  * :mod:`~.utils`       -- shared helpers consumed across the core package
                            and source adapters: URL canonicalization/sanitation
                            (`clean_url`, `safe_url`, `same_origin`), SemVer
                            extraction (`extract_version`), and atomic file
                            writes (`atomic_write`, `atomic_write_bytes`).

Source-specific logic (URL discovery, upstream-site quirks) lives under
``scripts/mirror/sources/`` and is registered in ``scripts/mirror/pipeline.py``;
nothing in this package should ever reference a concrete source.

The modules are imported explicitly (e.g. ``from ..core import fetch``)
to keep dependencies visible at the call site instead of hiding them behind a
star import. Consequently the package defines no ``__all__``: there is
nothing a star import should re-export, and an empty ``__all__: list[str] = []``
declaration would only pretend otherwise.
"""
