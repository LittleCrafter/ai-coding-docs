"""Documentation-source adapters.

Each module in this package is one *source*: an adapter that knows how to
discover the pages of a single upstream documentation site. The shared
pipeline (``scripts/mirror/pipeline.py``) treats every source module as a
``Source`` (see ``base.py``) and drives all of them through the same stages:

    discover -> download Markdown -> validate -> hash -> diff -> write changed

Contract for a source module:

* ``CONFIG: SourceConfig`` -- identity and display metadata. ``CONFIG.name``
  doubles as the ``docs/<name>/`` output folder.
* ``discover(client) -> list[Page]`` -- enumerate every page the upstream
  site currently publishes, sorted by slug. Discovery must be cheap and
  *complete*: the pipeline diffs the discovered set against the previous
  manifest, so a page missing here looks like an upstream removal (and its
  mirrored file gets deleted).
* ``fetch_markdown(client, page) -> (text, hash)`` -- OPTIONAL hook. Most
  sites serve ready Markdown, so by default the pipeline downloads
  ``page.source_md_url`` directly. A source whose pages are not ready
  Markdown (e.g. a site needing conversion first, like ``deepseek``
  (HTML) or ``opencode`` (raw MDX)) defines this hook instead; the
  pipeline picks it up via ``getattr``. The hook IS
  declared as a member of the ``Source`` Protocol in ``base.py`` -- but
  only so static type checkers and IDEs can type-check the pipeline's
  call site: the Protocol is never checked at runtime, so the hook stays
  optional in practice (modules that omit it fall back to the default
  download). See the NOTE in ``base.py`` for the full rationale.

To add a new source: create a module here implementing the contract, import
it below, and register it in the ``SOURCES`` list in
``scripts/mirror/pipeline.py`` (that list is what actually runs).
"""

from . import antigravity, claude_code, codex_cli, deepseek, kimi_code, opencode

# ``Source`` and ``SourceConfig`` are re-exported here purely as a public
# convenience surface: callers may spell the imports as
# ``from mirror.sources import Source`` instead of reaching into
# ``mirror.sources.base`` directly, and ``__all__`` documents the pair as
# part of the package's intended API. Nothing inside this repository
# currently imports them through the package (all consumers use
# ``mirror.sources.base``), so they only exist for external/embedder use
# and for typing -- they are intentional re-exports, not dead exports.
from .base import Source, SourceConfig

__all__ = [
    "Source",
    "SourceConfig",
    "antigravity",
    "claude_code",
    "codex_cli",
    "deepseek",
    "kimi_code",
    "opencode",
]
