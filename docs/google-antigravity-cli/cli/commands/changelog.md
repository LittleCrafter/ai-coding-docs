# Changelog command (/changelog)

Browse versioned Antigravity CLI release notes and recent changes directly in your terminal.

## Overview

The `/changelog` command opens a scrollable Markdown viewer inside the Antigravity CLI that displays versioned release notes, new features, and bug fixes.

When you run `/changelog`, the CLI fetches the latest published release notes and caches them locally at `~/.gemini/antigravity-cli/cache/CHANGELOG.md`. If you’re working offline or behind a restricted network, the CLI automatically falls back to your cached copy or the release notes embedded in your installed `agy` binary.

## View release notes in the TUI

To open the interactive changelog viewer during a CLI session, run the following command:

```
/changelog
```

The viewer renders the release notes organized by version heading, with the most recent version first:

```
## 1.3.2

- Added `/plugin`, an interactive manager for the official Antigravity plugin
  marketplace: browse and install plugins that bundle skills, MCP servers,
  subagents, rules, and hooks...
```

### Navigation controls

Use the following keyboard shortcuts to scroll through the release history:

| Key | Action |
| :-- | :-- |
| ↑ / ↓ (or k / j) | Scroll up or down by one line. |
| PgUp / PgDn | Scroll up or down by one page. |
| Ctrl + U / Ctrl + D | Scroll up or down by half a page. |
| g / Shift + G | Jump to the top or bottom of the changelog. |
| Esc | Close the changelog viewer and return to the prompt. |

## Print release notes in headless mode

You can also run `/changelog` in headless mode (`-p` or `--print`) to output the release notes directly to `stdout` without starting an interactive session or consuming model quota.

To print the Markdown changelog to your terminal or pipe it to a pager, run the following command:

```
agy -p "/changelog"
```

To retrieve the changelog in structured JSON format for scripts or automation, pass `--output-format json`:

```
agy -p "/changelog" --output-format json
```

You can also print the release notes with the standalone `changelog` subcommand, which doesn’t require a prompt:

```
agy changelog
```

## Next steps

Explore the following resources to keep your CLI installation up to date and discover more commands:

*   **[Installation and auth](https://antigravity.google/docs/cli/install)**: update your CLI binary to the latest version using `agy update`.
*   **[Release changelog](https://antigravity.google/docs/changelog)**: view the full web changelog for Google Antigravity.
*   **[CLI reference](../reference.md)**: view all available slash commands and keyboard shortcuts.