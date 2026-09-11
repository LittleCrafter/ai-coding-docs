# AI Coding Docs

[![Lint & Test](https://github.com/LittleCrafter/ai-coding-docs/actions/workflows/lint.yml/badge.svg)](https://github.com/LittleCrafter/ai-coding-docs/actions/workflows/lint.yml)
[![Documentation Mirror](https://github.com/LittleCrafter/ai-coding-docs/actions/workflows/update-docs.yml/badge.svg)](https://github.com/LittleCrafter/ai-coding-docs/actions/workflows/update-docs.yml)
[![Python 3.14+](https://img.shields.io/badge/python-3.14%2B-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

Local and always-up-to-date mirror of the documentation for various **AI coding tools/CLIs**, maintained as Markdown in [`docs/`](./docs/).

<!-- SOURCES_TABLE:START -->

| Source                                                       | Version | Origin                                                           | How it is mirrored                                                                                | Whats-new |
| :----------------------------------------------------------- | :-----: | :--------------------------------------------------------------- | :------------------------------------------------------------------------------------------------ | :-------: |
| [**Google Antigravity CLI**](./docs/google-antigravity-cli/) | 1.1.13  | antigravity.google/docs/cli/                                     | scraping (sitemap → `<url>.md`)                                                                   |    ✅     |
| [**Claude Code**](./docs/claude-code/)                       | 2.1.268 | code.claude.com/docs/en/                                         | scraping (sitemap → `<url>.md`)                                                                   |     —     |
| [**Codex CLI**](./docs/codex-cli/)                           | 0.154.0 | learn.chatgpt.com (`/docs/`) + github.com/openai/codex (`docs/`) | scraping (learn.chatgpt.com pages listed in the codex/llms.txt index + the openai/codex git tree) |     —     |
| [**DeepSeek API**](./docs/deepseek-api/)                     |    —    | api-docs.deepseek.com                                            | scraping (HTML → Markdown via `html2text`)                                                        |     —     |
| [**Kimi Code**](./docs/kimi-code/)                           | 0.42.0  | github.com/MoonshotAI/kimi-code (`docs/en/`)                     | scraping (GitHub tree → VitePress `.md` → Markdown)                                               |     —     |
| [**OpenCode**](./docs/opencode/)                             | 1.18.30 | github.com/anomalyco/opencode (`packages/web/src/content/docs/`) | scraping (GitHub tree → raw `.mdx` → `.md` conversion)                                            |     —     |

<!-- SOURCES_TABLE:END -->

Each source is independent and pluggable; adding a new one is as simple as creating an adapter in [`scripts/mirror/sources/`](./scripts/mirror/sources/).

## Why it exists

- **Fast and offline access** to the documentation of these tools in pure Markdown (grep, reading in the terminal, LLM readers).
- **Track evolution** — for the Antigravity CLI, there is a structural log in [`docs/google-antigravity-cli/whats-new/`](./docs/google-antigravity-cli/whats-new/) that detects **added, modified, removed/deprecated, and renamed/moved** pages.
- A **versioned and self-describing** mirror (each source has a `manifest.json` + an index `README.md`; there is a general index in [`docs/README.md`](./docs/README.md)).

## How it works

Each source discovers its pages in its own way, but the pipeline is shared: **discover → download Markdown → validate → hash → diff against previous run → write only what changed**. Runs with no changes do not change any file content (clean git diff, no empty commits).

- **Antigravity CLI** — the site serves `<url>.md` for each page; we discover the `/docs/cli/` pages via the sitemap.
- **Claude Code** — the site serves `<url>.md` for each page; we use the sitemap.
- **Codex CLI** — dual discovery mirrors both GitHub repository files (`openai/codex@main:docs/`) and the full documentation catalog from `https://developers.openai.com/codex/llms.txt`. Reference stubs are resolved to rich `.md` twins, hybrid configuration guides are assembled dynamically, cross-documentation links are rewritten to local relative paths, and custom Astro/MDX components (overview landing pages, file trees, toggle sections, model details, pricing cards) are converted to clean CommonMark outlines and code blocks.
- **DeepSeek API** — the site is Docusaurus (HTML only, no `.md` or public repository); we discover pages via the sitemap and convert the content to Markdown with `html2text`. Guide/FAQ pages come out clean; tables and the API reference (`api/*`) remain a bit raw.
- **Kimi Code** — the documentation lives as Markdown in the public `MoonshotAI/kimi-code` repository (`docs/en/`); we list the tree via the GitHub API, download via raw, and normalise the VitePress page sources (YAML frontmatter, `<Badge />` components, `:::` container markers, layout wrappers) to plain standard Markdown.
- **OpenCode** — the documentation is MDX in the public `anomalyco/opencode` repository (`packages/web/src/content/docs/`); we list the tree via the GitHub API, download via raw, and convert MDX components (imports, callouts, JSX wrappers) to clean standard Markdown.

No headless browser is used. DeepSeek API is converted from HTML; OpenCode and Codex CLI are converted from MDX / Astro components (JSX components converted to standard Markdown headings, lists, tables, code blocks, or callouts); Kimi Code is converted from VitePress page sources (frontmatter, Vue components and container markers turned into standard Markdown headings, GitHub Alerts and plain text); Google Antigravity CLI and Claude Code already expose ready-made Markdown.

**Media assets**: Google Antigravity CLI, Claude Code, Kimi Code, and OpenCode mirror the images and diagrams their pages reference. Each referenced asset is downloaded into the source's own asset directory, in-page references are rewritten so they resolve locally, downloads are hashed and cached (only changed bytes are rewritten), and assets no longer referenced by any page are automatically pruned:

| Source                 | Asset directory                       | Referenced prefixes                |
| :--------------------- | :------------------------------------ | :--------------------------------- |
| Google Antigravity CLI | `docs/google-antigravity-cli/assets/` | `/assets/`                         |
| Claude Code            | `docs/claude-code/media/`             | `https://mintcdn.com/claude-code/` |
| Kimi Code              | `docs/kimi-code/media/`               | `../../media/`                     |
| OpenCode               | `docs/opencode/assets/`               | `../../assets/`                    |

Video demos (`.mp4`) in Claude Code changelogs remain external CDN links; only image and diagram assets are mirrored locally.

OpenCode additionally supports mirroring its non-English locale directories via `--locales` (see below); the default run stays English-only.

## Requirements

- [**uv**](https://docs.astral.sh/uv/) and **Python 3.14+** (3.14 pinned for development in [`.python-version`](./.python-version); `uv` installs/uses the latest 3.14.x automatically).

## Formatting

Python is formatted with [Ruff](https://docs.astral.sh/ruff/), and Markdown / JSON / YAML with [Prettier](https://prettier.io/). Both run as a **pre-commit gate**: a commit is rejected if any file is not formatted, and the same checks run in CI ([`.github/workflows/lint.yml`](./.github/workflows/lint.yml)). Mirrored content under [`docs/`](./docs/) is never reformatted (excluded via [`.prettierignore`](./.prettierignore)).

One-time setup (requires `uv` on `PATH`; `npx`/Node for the Prettier hook):

```bash
uv run pre-commit install   # wire the git hook into .git/hooks/
```

(`pre-commit` itself comes from the `dev` dependency group in `pyproject.toml` — no separate `uv tool install` needed.) After that, every `git commit` is checked automatically. To format manually:

```bash
uv run ruff format scripts/ tests/        # Python formatting
uv run ruff check --fix scripts/ tests/   # Python lint + safe auto-fixes
npx -y prettier@3.9.6 --write "**/*.md" "**/*.{yml,yaml,json}"
```

## Makefile

A `Makefile` at the repo root wraps every common operation so you don't need to remember the exact `uv` / `ruff` / `prettier` incantations. Type `make` (or `make help`) to see the full reference.

### One-time setup

```bash
make setup   # uv sync + pre-commit install (everything needed after cloning)
```

### Docs mirror

```bash
make mirror                           # update all sources
make mirror-source SOURCE=kimi-code   # only a single source
make mirror-dry-run                   # discover pages, write nothing (--dry-run)
make mirror-force                     # rewrite every file (--force)
make check-links                      # verify internal/relative links in docs/
```

### Testing & quality

```bash
make test                  # run full pytest suite
make test-quiet            # one line per passing test (-q)
make lint                  # ruff check (Python lint)
make pyright               # static type checking over all of scripts/
make format                # auto-format: ruff (Python) + prettier (Markdown/YAML/JSON)
make format-check          # check formatting without changing (CI mode)
make check                 # every CI gate: format-check + pyright + test-quiet + lock-check + shell-check
```

### Other

```bash
make lock                  # regenerate uv.lock
make lock-check            # verify uv.lock is current
make shell-check           # bash -n + shellcheck on scripts/run_local.sh (system shellcheck, else uvx, else skip; mandatory in CI)
make pre-commit            # run pre-commit on all files
make pre-commit-install    # wire the pre-commit hook into .git/hooks/
make lint-fix              # ruff check with safe auto-fixes
make test-verbose          # run pytest with verbose output (-v)
make clean                 # remove cache directories
make clean-all             # remove cache + .venv (fresh start; re-run 'make install' after)
make install               # sync virtualenv with pyproject.toml / uv.lock (uv sync)
```

---

## Tests

Unit tests for the pure logic — change detection (`diff`), HTTP retry/validation (`fetch`), the DeepSeek HTML→Markdown, OpenCode MDX and Kimi VitePress conversions, the Antigravity adapter (`antigravity`), config resolution, page-model validation, CLI argument parsing, pipeline orchestration (including the `--log-file` tee), media/static-asset staging (`media`), source-adapter discovery filtering and safety guards (`adapters`), internal Markdown link verification (`link_checker`), and the sitemap/manifest/index/whats-new/github helpers, plus atomic file writes (`utils`) and the shared HTML→Markdown converter (`html_markdown`) — live in [`tests/`](./tests/) and run with [pytest](https://docs.pytest.org/):

```bash
uv run pytest          # run the suite
uv run pytest -q       # one line per passing test
```

They also run in CI ([`.github/workflows/lint.yml`](./.github/workflows/lint.yml), `test` job) on every push and pull request.

## Usage

```bash
uv run mirror-docs                       # update all sources
uv run mirror-docs --source kimi-code    # only a single source
uv run mirror-docs --dry-run             # list pages only, do not write
uv run mirror-docs --force               # rewrite everything (bootstrap / fix)
uv run mirror-docs --workers 4           # concurrent page-fetch workers (alias: --concurrency)
uv run mirror-docs --locales pt-br,es    # also mirror those locales (OpenCode); "all" = all 17
uv run mirror-docs --check-links         # verify internal Markdown links in docs/
uv run mirror-docs --log-file mirror.log # also write all output to a file (short form: -l)
uv run mirror-docs --version             # print version and exit
```

## Structure

```
docs/
  README.md                    # general index (auto-generated)
  google-antigravity-cli/      # + README.md, manifest.json, SOURCE.md, cli/..., whats-new/
  claude-code/                 # + README.md, manifest.json, SOURCE.md, agent-sdk/, whats-new/ (upstream's own weekly changelog, mirrored — NOT the structural log), <pages>.md
  codex-cli/                   # + README.md, manifest.json, SOURCE.md, LICENSE, NOTICE, <pages>.md
  deepseek-api/                # + README.md, manifest.json, SOURCE.md, api/, api_samples/, guides/, news/, quick_start/, <pages>.md (HTML -> Markdown)
  kimi-code/                   # + README.md, manifest.json, LICENSE, SOURCE.md, configuration/, guides/, ...
  opencode/                    # + README.md, manifest.json, SOURCE.md, LICENSE, <pages>.md (MDX -> MD)
scripts/
  mirror/
    config.py                  # paths, HTTP tuning, tool version
    cli.py                     # argparse entry point (mirror-docs)
    __main__.py                # `python -m mirror` alias for the CLI
    pipeline.py                # per-source pipeline + cross-source orchestration
    reporting.py               # console output (presentation layer)
    core/                      # generic: page, fetch, manifest, diff, index, whats_new, sitemap, github, utils, html_markdown, link_checker, media
    sources/                   # base + one adapter per source: antigravity, claude_code, codex_cli, deepseek, kimi_code, opencode
  run_local.sh                 # local scheduling helper
tests/                         # pytest unit suite (core + sources)
.github/workflows/
  update-docs.yml              # scheduled + manual docs mirror
  lint.yml                     # formatting/lint gate on push & PR
Makefile                       # central command registry (type `make` for help)
pyproject.toml                 # uv: Python >=3.14, deps httpx + beautifulsoup4 + html2text (+ pytest/ruff/pre-commit dev); script `mirror-docs`
uv.lock                        # pinned dependency lockfile (kept current by `make lock`)
.pre-commit-config.yaml        # ruff + prettier pre-commit gate (blocks on error)
.prettierignore                # keeps mirrored docs/ out of Prettier
.python-version                # 3.14 (minor pin; uv resolves latest 3.14.x)
LICENSE                        # MIT (tooling only; docs/ content keeps its owners' licenses)
NOTICE                         # attribution for the mirrored docs/ content
```

## Scheduling

**GitHub Actions** ([`.github/workflows/update-docs.yml`](./.github/workflows/update-docs.yml)):
runs every 3 hours (at :00 UTC) and can be triggered manually; auto-commits changes as `github-actions[bot]` and opens an issue if the run fails. Requires `contents: write` + `issues: write` (already configured in the workflow). The optional `DOCS_MIRROR_SSH_KEY` secret can hold a deploy key for the push; when it is unset the checkout authenticates with the default `GITHUB_TOKEN`.

Failure behavior is deliberately granular: if a single source fails (e.g. an upstream site re-architecture), the healthy sources' updates are **still committed and pushed**, and only then is the run marked failed — one broken source never delays publishing the others. The failure opens (or comments on) a **deduplicated** issue titled "Docs mirror update failed", so a persistent outage produces one issue, not eight per day. GitHub may also e-mail you about each failed run depending on your notification settings (Settings → Notifications → Actions); a job-level timeout is the one case that produces only the e-mail, since a cancelled run cannot run the issue step.

**Local** ([`scripts/run_local.sh`](./scripts/run_local.sh) = `uv sync && uv run mirror-docs`):
schedule with cron (`crontab -e`):

```cron
0 */3 * * * cd /path/to/ai-coding-docs && ./scripts/run_local.sh >> /tmp/ai-coding-docs.log 2>&1
```

or with a _systemd user timer_ (`OnCalendar=*-*-* 00/3:00:00`, `Persistent=true`).

Both the local schedule and GitHub Actions run at `:00` for simplicity and to stay aligned with the 3-hour cadence; the exact minute is not load-critical. Running at `:00` coincides with peak aggregate cron load, so if you want to smooth load on upstream sites, shift the local cron to an off-zero minute (e.g. `7 */3 * * *`).

## Adding a new source

1. Create `scripts/mirror/sources/<name>.py` exporting `CONFIG` (`SourceConfig`) and `discover(client) -> list[Page]` (see [`base.py`](./scripts/mirror/sources/base.py)).
2. Register it in `SOURCES` in [`pipeline.py`](./scripts/mirror/pipeline.py).
3. Run `uv run mirror-docs --source <name>`.

## License and Attribution

There is a clear separation between the **tooling** and the **mirrored content**:

- **Tooling** ([`scripts/`](./scripts/), `pyproject.toml`, workflows, `run_local.sh`):
  **MIT**, Copyright © 2026 LittleCrafter — see [`LICENSE`](./LICENSE).
- **Content under [`docs/`](./docs/)**: **not** covered by this repository's MIT license. It remains the property of its respective owners and is redistributed here only for offline reference and change-tracking. Full attribution can be found in [`NOTICE`](./NOTICE) and in a `SOURCE.md` file within each source subfolder.

| Source                 | Content                           | License                                                                                              |
| ---------------------- | --------------------------------- | ---------------------------------------------------------------------------------------------------- |
| Google Antigravity CLI | public doc                        | © Google — no redistribution license (mirrored from the published pages)                             |
| Claude Code            | public doc                        | © Anthropic — no redistribution license (mirrored from the published pages)                          |
| Codex CLI              | docs portal + repo `openai/codex` | **Apache-2.0** for the repo files (license + NOTICE in `docs/codex-cli/`); portal pages as published |
| DeepSeek API           | public doc                        | © DeepSeek — no redistribution license (converted from HTML)                                         |
| Kimi Code              | repo `MoonshotAI/kimi-code`       | **MIT** (license included in `docs/kimi-code/`)                                                      |
| OpenCode               | repo `anomalyco/opencode`         | **MIT** (license included in `docs/opencode/`)                                                       |

Codex (Apache-2.0 for the files mirrored from `openai/codex`) and Kimi (MIT) are OSS: their content is redistributed in compliance, with license and notices included, and each source's `SOURCE.md` states the changes the mirror makes for it (such as component conversion and any link or asset-reference rewriting that source needs). Google, Anthropic, and DeepSeek are public documentations published without an explicit redistribution license, reproduced faithfully from the published pages (converted from HTML in the case of DeepSeek) with full attribution and links to the canonical source. Trademarks belong to their respective owners; if you are an owner and want content removed, please open an issue.
