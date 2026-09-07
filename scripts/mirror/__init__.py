"""ai-coding-docs — multi-source coding-tool docs mirror.

This package turns the public documentation of several AI coding tools/CLIs
(Antigravity, Claude Code, Codex CLI, DeepSeek, Kimi Code, OpenCode) into a local,
git-versioned Markdown mirror under ``docs/``.

The package is layered, with dependencies pointing strictly downward:

* :mod:`mirror.cli` -- argument parsing and exit codes (the thin top layer);
* :mod:`mirror.pipeline` -- orchestration: discover -> fetch -> diff -> write;
* :mod:`mirror.reporting` -- all console output, kept separate from logic;
* ``mirror.core`` -- the mechanics (fetch, manifest, diff, index, whats-new);
* ``mirror.sources`` -- one module per mirrored site (discovery + config);
* :mod:`mirror.config` -- shared constants imported by every layer above.

Two public names are re-exported here:

* :func:`mirror.cli.main` -- the command-line entry point. The project's
  ``[project.scripts]`` table declares ``mirror-docs = "mirror.cli:main"``,
  pointing straight at the submodule; the package-level re-export exists
  purely as a convenience for programmatic use (``from mirror import main``)
  so embedders do not have to reach into a submodule themselves. The
  re-export is LAZY (see ``__getattr__`` below): importing the package must
  not pull in the CLI and, with it, the whole pipeline. ``main`` is also
  imported under ``TYPE_CHECKING`` so static type checkers see it as a real
  module member (the ``__all__`` contract below stays fully checkable)
  while runtime behavior remains lazy.
* ``__version__`` -- a re-export of :data:`mirror.config.TOOL_VERSION`, so
  the package answers version introspection from the same single source of
  truth.
"""

from typing import TYPE_CHECKING

from . import config

if TYPE_CHECKING:
    # Type-space declaration only (see the docstring above): this import is
    # never executed at runtime, so the lazy ``__getattr__`` re-export below
    # stays the only thing that ever imports ``mirror.cli``.
    from .cli import main

__all__ = ["__version__", "main"]

# Package version, re-exported from ``config.TOOL_VERSION`` so there is
# exactly one resolution site. See :data:`config.TOOL_VERSION` for the full
# resolution chain (``importlib.metadata`` -> parse ``pyproject.toml`` at
# ``REPO_ROOT`` -> hardcoded fallback). Importing ``config`` here is
# cycle-safe: ``config`` is a leaf module with no package imports. ``main``
# is deliberately NOT imported eagerly -- see ``__getattr__`` below.
__version__ = config.TOOL_VERSION


def __getattr__(name: str):
    """Resolve the ``main`` re-export lazily on first access.

    ``main`` is the CLI entry point, and importing ``mirror.cli`` pulls in
    the whole pipeline (source adapters, httpx, beautifulsoup4, html2text)
    -- a cost the ``--version`` fast path must never pay. The re-export
    exists purely as a convenience for programmatic callers
    (``from mirror import main``), who trigger the import at call time;
    any other missing attribute raises the standard AttributeError.
    """
    if name == "main":
        from .cli import main

        return main
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
