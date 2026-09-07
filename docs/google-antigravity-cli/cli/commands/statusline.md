# Status Line Command (/statusline)

Toggle the TUI status line or configure a custom rendering command.

## Overview

The `/statusline` command allows you to quickly enable or disable the status line at the bottom of your TUI, or configure a custom shell command to render it dynamically, without manually editing your settings file.

For details on how to write custom status line scripts and the JSON state payload schema, see the conceptual **[Status Line Customization Guide](/docs/cli/statusline)**.

## Usage

Run the `/statusline` command with the following arguments to control its behavior:

### Toggle Status Line

Type `/statusline` with no arguments to toggle the status line on and off:

```
/statusline
```

### Enable or Disable Explicitly

You can explicitly enable or disable the status line:

*   **Enable**: `/statusline on` or `/statusline enable`
*   **Disable**: `/statusline off` or `/statusline disable`

```
/statusline off
```

### Configure a Custom Command

To route the agent state JSON payload to a custom script and render its output in the status line, pass the command as an argument:

```
/statusline ~/.gemini/antigravity-cli/statusline.sh
```

This immediately updates your settings and starts running the script to render the status line.

### Revert to Default

To delete your custom command configuration and revert to the built-in default status line:

```
/statusline delete
```

_(Note: `/statusline reset` is also supported)._

### Show Help

To view the quick command reference:

```
/statusline help
```

## Next steps

*   **[Status Line Guide](/docs/cli/statusline)**: Learn how to write custom scripts and handle the JSON payload.
*   **[Window Title Command](/docs/cli/commands/title)**: Configure dynamic terminal window titles.
*   **[CLI Reference](/docs/cli/reference)**: See all available slash commands.