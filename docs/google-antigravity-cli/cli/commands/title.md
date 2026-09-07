# Window Title Command (/title)

Configure dynamic terminal window titles interactively.

## Overview

The `/title` command allows you to toggle the terminal window title feature on and off, or set its state explicitly. When enabled, the terminal title bar dynamically updates to show the active model, workspace, and agent state.

For details on how to write custom scripts to format the window title, see the conceptual **[Terminal Title Customization Guide](/docs/cli/title)**.

## Interactive Toggling

You can control the window title feature by running the `/title` command.

To toggle the feature on and off:

```
/title
```

To enable it explicitly:

```
/title on
```

To disable it explicitly:

```
/title off
```

## Next steps

*   **[Terminal Title Guide](/docs/cli/title)**: Learn how to write custom scripts to format the window title.
*   **[Status Line Command](/docs/cli/commands/statusline)**: Customize your TUI status line.
*   **[CLI Reference](/docs/cli/reference)**: See all available slash commands.