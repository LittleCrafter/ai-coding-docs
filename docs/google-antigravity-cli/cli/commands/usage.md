# Model Quotas (/usage)

View your active model quota usage and refresh your configuration.

## Overview

Antigravity CLI provides the `/usage` command (alias `/quota`) to help you monitor your resource consumption. When run, the command refreshes your model configuration and quota status from the backend and opens an interactive TUI panel.

## Viewing your usage

To open the Model Quotas panel:

1.  Type `/usage` (or `/quota`) in the prompt box.
2.  Press Enter.

```
/usage
```

![Quota & Credits TUI](../../assets/image/docs/cli/usage-tui.png)

### Interactive Panel Features

The panel displays:

*   **Model Quotas**: A breakdown of your usage limits and remaining requests/tokens for each supported model (e.g., Gemini 3.5 Flash, Gemini 3.1 Pro).
*   **Active Refresh**: The CLI automatically triggers a fresh check of your quotas on disk and from the backend service when you open this panel.

### Navigation Controls

Use the following keyboard shortcuts to navigate the panel:

| Key | Action |
| :-- | :-- |
| ↑ / ↓ (or J / K) | Scroll up or down by one line. |
| PgUp / PgDn | Scroll up or down by one page. |
| G / Shift + G | Jump to the top or bottom of the list. |
| Esc (or Q) | Close the panel and return to the prompt. |

## Next steps

*   **[CLI Reference](/docs/cli/reference)**: See all available slash commands and keybindings.
*   **[Settings & Rendering](/docs/cli/settings)**: Configure your default models and credit usage preferences.