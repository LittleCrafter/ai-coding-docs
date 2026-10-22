# Effort command (/effort)

Available on: Antigravity CLI

Adjust your active model’s reasoning effort budget to balance response speed and reasoning depth.

## Overview

The `/effort` command controls how much thinking and reasoning effort your currently selected model applies to each turn in the Antigravity CLI. When you select a new effort level, the CLI switches to that model variant for the current session and persists your choice as the default for future sessions.

The CLI status line displays the active effort level beside your selected model name so you can monitor your configuration at a glance.

## Supported effort levels

The CLI recognizes the following effort levels, ordered from lightest to heaviest:

*   **`low`**: faster responses and lighter reasoning, well suited for quick lookups, syntax checks, and straightforward edits.
*   **`medium`**: balanced speed and reasoning quality for everyday software engineering tasks.
*   **`high`**: deeper reasoning for complex architecture, subtle bug investigations, and multi-file refactoring.
*   **`xhigh`**: extra-high reasoning, available only for models that publish an `xhigh` variant.
*   **`max`**: the highest reasoning budget, available only for models that publish a `max` variant.

Note

The set of levels you can choose from depends on your active model. Most adjustable models offer `low`, `medium`, and `high`; only some models also expose `xhigh` or `max`. If you run `/effort` while using a model with a fixed reasoning budget, the CLI reports that effort isn’t adjustable for the current model.

## Change effort interactively

Run `/effort` without arguments to open the interactive **Set Effort** timeline gauge, pre-positioned on your active effort level:

```text
/effort
```

### Navigation controls

Use the following keys to adjust the timeline gauge:

| Key | Action |
| :-- | :-- |
| ← / → | Slide the selector between the effort levels available for your model. |
| Enter | Confirm the highlighted effort level and save it as your default. |
| Esc | Cancel and return to the prompt without changing the effort level. |

## Set effort directly

To switch effort levels immediately without opening the interactive picker, pass the target level as an argument:

```text
/effort low
/effort medium
/effort high
```

The CLI validates the argument in two stages:

*   If the level isn’t a recognized effort name, the CLI lists the valid names (for example, `Invalid effort "turbo" (valid: low, medium, high, xhigh, max)`).
*   If the level is valid but your current model doesn’t offer it, the CLI lists the levels available for that model (for example, `<model> has no "max" effort (available: low, medium, high)`).

## Inspect or override effort in headless mode

In headless mode (`-p` or `--print`), you can inspect the active model’s reasoning effort configuration or override the effort level for a single run:

*   **Inspect current effort**: run `agy -p "/effort"` (or add `--output-format json`) to print whether the active model’s effort is adjustable along with the current and available effort tiers:
    
    ```bash
    agy -p "/effort"
    agy -p "/effort" --output-format json
    ```
    
    In headless mode, `/effort` is read-only and takes no arguments. Running `agy -p "/effort low"` fails with `/effort takes no arguments`.
    
*   **Override effort for one run**: pass the `--effort` flag when running a prompt from your shell:
    
    ```bash
    agy -p "Summarize the changes in the last commit" --effort low
    ```
    

Note

Unlike the interactive `/effort <level>` command, the `--effort` flag applies only to the current invocation and doesn’t change the default saved in your settings. You can also pass it when starting an interactive session (for example, `agy --effort low`) to use a different effort for that session only.

## Next steps

Explore related documentation on model selection and status bar customization:

*   **[Models](https://antigravity.google/docs/models)**: learn about supported models and reasoning capabilities.
*   **[Status line command (`/statusline`)](./statusline.md)**: customize how model and effort indicators appear in your status bar.
*   **[CLI reference](../reference.md)**: view all available slash commands and keyboard shortcuts.