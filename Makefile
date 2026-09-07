# ==============================================================================
# AI Coding Docs — Makefile
# ==============================================================================
# Centralised command registry for the project. Every common operation lives
# here so a new contributor (or your future self) can type `make` and see what
# is available, without reading pyproject.toml or the CI workflow YAML.
#
# Design rules:
#   * Every target is .PHONY (no file outputs at the repo root).
#   * `help` is the default goal.
#   * Self-documenting: `## <description>` comments are parsed by `help`.
#   * Variables at the top keep tool pins and paths in one place.
# ==============================================================================

# --- Tool invocations ---------------------------------------------------------
# ruff: the version is pinned EXACTLY in ONE place -- pyproject.toml's `dev`
# dependency group (ruff==0.16.0, resolved through uv.lock). `uv run ruff`
# always picks up that pinned version, and .github/workflows/lint.yml and
# .pre-commit-config.yaml invoke ruff the same way, so local hooks, this
# Makefile, and CI can never drift apart. Do NOT pin a ruff version here.
# prettier: there is no project-local prettier (no package.json), so the
# version is pinned at each call site and must stay in sync in all FOUR
# places: Makefile (here), .github/workflows/lint.yml,
# .pre-commit-config.yaml, and README.md (the npx command shown to
# contributors).
RUFF     := uv run ruff
PRETTIER := npx -y prettier@3.9.6

# --- File / directory groups used by multiple targets -------------------------
# PY_SRC: Python source trees passed to ruff for format, check, and lint
# commands. These are the only directories that contain project-authored
# Python code; generated or vendored directories (docs/, .venv/, build/)
# are never passed to ruff so formatting stays scoped to authored code.
# MD_YAML_JSON: glob patterns for Prettier formatting (Markdown, YAML,
# JSON). Mirrored docs under docs/ are excluded from Prettier via
# .prettierignore (the mirror preserves upstream formatting exactly), so
# these globs only reach the project's own .md, .yml, .yaml, and .json
# files (README.md, .github/workflows/*.yml, .pre-commit-config.yaml, etc.).
PY_SRC       := scripts/ tests/
MD_YAML_JSON := "**/*.md" "**/*.{yml,yaml,json}"

# All targets are phony (no file outputs at the repo root).
.PHONY: help install setup mirror mirror-source mirror-dry-run mirror-force \
        check-links test test-quiet test-verbose lint lint-fix format format-check \
        pyright check lock lock-check shell-check pre-commit pre-commit-install \
        clean clean-all

# ==============================================================================
# Default target: print the help summary.
# ==============================================================================
.DEFAULT_GOAL := help

# The recipe below generates this target list automatically, so `make help`
# can never drift out of sync with the Makefile itself. It works in three
# stages, all reading the Makefile via the built-in $(MAKEFILE_LIST) variable:
#   1. grep -E '^[a-zA-Z_-]+:.*?## .*$$' keeps only lines that define a target
#      AND carry a `## description` comment on the same line (the `$$` is an
#      escaped literal `$` -- make would otherwise swallow a single `$`);
#   2. sort alphabetises the surviving lines by target name;
#   3. awk splits each line on the ':.*?## ' separator and prints the target
#      name in cyan followed by its description. (`$$1`/`$$2` are awk's $1/$2
#      fields, again dollar-escaped for make.)
help: ## Show this help (list every target with its description)
	@echo "AI Coding Docs — Makefile reference"
	@echo ""
	@echo "Usage: make [target]"
	@echo ""
	@echo "Available targets:"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
		| sort \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-22s\033[0m %s\n", $$1, $$2}'
	@echo ""
	@echo "Examples:"
	@echo "  make                  # show this help"
	@echo "  make install          # sync dependencies"
	@echo "  make mirror           # update all docs sources"
	@echo "  make mirror-source SOURCE=kimi-code   # update only the kimi-code source"
	@echo "  make check            # run every CI check locally"
	@echo "  make test             # run test suite"
	@echo ""

# ==============================================================================
# Setup / install
# ==============================================================================

install: ## Sync virtualenv with pyproject.toml / uv.lock (uv sync)
	uv sync

# `pre-commit-install` is a make prerequisite rather than an inline recipe
# line so that the hook installation lives in exactly ONE target: running
# `make pre-commit-install` on its own and running `make setup` can never
# drift apart (previously the same `uv run pre-commit install` command was
# written out in both places). Make runs the prerequisites first, so the
# dependency's own "pre-commit hook installed." message appears just before
# the banner below and the output still reads as one coherent setup sequence.
setup: install pre-commit-install ## Full one-time setup: install deps + pre-commit hooks
	@echo ""
	@echo "Setup complete. The pre-commit gate is now active."
	@echo "Run 'make' to see available commands."

# ==============================================================================
# Docs mirror
# ==============================================================================

mirror: ## Run the docs mirror (update all sources)
	uv run mirror-docs

# SOURCE is validated with a native GNU Make conditional instead of a shell
# `if [ -z ... ]` inside the recipe: the shell variant only fails AFTER make
# has started executing recipe lines, whereas `ifndef` + `$(error ...)` aborts
# while make is expanding the recipe -- before any shell is spawned. That gives
# a clearer failure (make's own "SOURCE variable is required" message, not a
# shell exit status) and keeps the guard next to the variable it checks.
mirror-source: ## Run mirror for a single source (e.g. make mirror-source SOURCE=kimi-code)
ifndef SOURCE
	$(error SOURCE variable is required (e.g. make mirror-source SOURCE=kimi-code))
endif
	uv run mirror-docs --source "$(SOURCE)"

mirror-dry-run: ## Discover pages without fetching or writing (--dry-run)
	uv run mirror-docs --dry-run

mirror-force: ## Rewrite every file even if unchanged (--force)
	uv run mirror-docs --force

check-links: ## Verify internal/relative links in docs/ (--check-links)
	uv run mirror-docs --check-links

# ==============================================================================
# Testing
# ==============================================================================

test: ## Run the full pytest suite
	uv run pytest

test-quiet: ## Run pytest, one line per passing test (-q)
	uv run pytest -q

test-verbose: ## Run pytest with verbose output (-v)
	uv run pytest -v

# ==============================================================================
# Linting & formatting (Python)
# ==============================================================================

lint: ## Run ruff check on scripts/ and tests/
	$(RUFF) check $(PY_SRC)

lint-fix: ## Run ruff check with safe auto-fixes
	$(RUFF) check --fix $(PY_SRC)

format: ## Auto-format: ruff (Python) + prettier (Markdown / YAML / JSON)
	$(RUFF) format $(PY_SRC)
	$(PRETTIER) --write $(MD_YAML_JSON)

pyright: ## Run pyright static type check over all of scripts/
	uv run pyright scripts/

format-check: ## Check formatting + lint without changing files (CI mode)
	$(RUFF) format --check $(PY_SRC)
	$(RUFF) check $(PY_SRC)
	$(PRETTIER) --check $(MD_YAML_JSON)

# ==============================================================================
# Full quality gate (what CI runs)
# ==============================================================================
# NOTE: `lint` is deliberately NOT a prerequisite -- format-check already runs
# `ruff check` as its second step, so depending on both would run the same
# lint twice.

check: format-check pyright test-quiet lock-check shell-check ## Run every CI check locally
	@echo ""
	@echo "All checks passed."

# ==============================================================================
# Lockfile
# ==============================================================================

lock: ## Regenerate uv.lock from pyproject.toml
	uv lock

lock-check: ## Verify uv.lock is current (fails if stale)
	uv lock --check

# ==============================================================================
# Shell script
# ==============================================================================

# bash -n (syntax check) always runs -- bash is guaranteed wherever make is.
# shellcheck runs when available: the system binary is preferred, and when it
# is missing the tool is fetched on demand via `uvx --from shellcheck-py`
# (the PyPI distribution of the shellcheck binary). Only when neither works
# does the target degrade to a skip message -- the mandatory shellcheck pass
# stays enforced in CI (.github/workflows/lint.yml runs it on the
# GitHub-hosted Ubuntu runner image, which ships shellcheck preinstalled).
shell-check: ## Syntax-check + shellcheck the shell helper (system shellcheck, else uvx, else skip)
	bash -n scripts/run_local.sh
	@echo "scripts/run_local.sh: syntax OK"
	@if command -v shellcheck >/dev/null 2>&1; then \
		shellcheck scripts/run_local.sh \
			&& echo "scripts/run_local.sh: shellcheck OK"; \
	elif uvx --from shellcheck-py shellcheck --version >/dev/null 2>&1; then \
		uvx --from shellcheck-py shellcheck scripts/run_local.sh \
			&& echo "scripts/run_local.sh: shellcheck OK (via uvx)"; \
	else \
		echo "shellcheck not available locally; skipping (CI runs it in lint.yml)"; \
	fi

# ==============================================================================
# Pre-commit
# ==============================================================================

pre-commit: ## Run pre-commit on all files (same gate as git commit)
	uv run pre-commit run --all-files

pre-commit-install: ## Wire the pre-commit hook into .git/hooks/
	uv run pre-commit install
	@echo "pre-commit hook installed."

# ==============================================================================
# Housekeeping
# ==============================================================================

clean: ## Remove cache directories and Python build artifacts
	rm -rf .ruff_cache/ .pytest_cache/
	rm -rf build/ dist/ .eggs/ *.egg-info/
	# Recursively remove every __pycache__/ directory that the Python
	# interpreter may have created anywhere under the repository root
	# importing test modules outside of pytest. The ``-path ./.venv -prune``
	# and ``-path ./.git -prune`` clauses cut the virtualenv and git tree
	# out of the traversal entirely: .venv holds
	# hundreds of interpreter-owned __pycache__ directories that uv simply
	# regenerates on the next ``uv run``, so deleting them only makes the
	# next command slower while achieving nothing. Pruning (rather than
	# filtering matches afterwards) also skips the walk itself, keeping
	# ``make clean`` fast even with a fully populated .venv. The
	# ``-exec rm -rf {} +`` form batches directory paths so rm is invoked
	# once per batch rather than once per directory. The ``|| true``
	# suffix prevents make from failing on ``find``'s exit status: find
	# returns 0 when there is simply nothing to remove, but returns
	# non-zero on traversal errors (e.g. a permission-denied or vanished
	# directory), which are a no-op success for a clean target.
	# (.ruff_cache/ and .pytest_cache/ above are removed by explicit
	# top-level path, so they never descend into .venv and need no prune.)
	find . -path ./.venv -prune -o -path ./.git -prune -o -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	@echo "Cache and build artifacts removed."

clean-all: clean ## Remove cache + .venv (fresh start; re-run 'make install' after)
	rm -rf .venv/
	@echo ".venv removed. Run 'make install' to rebuild."
