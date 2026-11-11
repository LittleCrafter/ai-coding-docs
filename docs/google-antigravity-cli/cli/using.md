# CLI settings and tips

### Settings

Antigravity CLI provides a flexible configuration system to customize workspace behavior, safety restrictions, editor preferences, visual style, and performance:

*   **Configuration file**: Stored in a plain JSON file at `~/.gemini/antigravity-cli/settings.json`.
*   **Settings panel**: Type `/config` or `/settings` to open a full-screen overlay menu listing all available options:
    *   Select a setting to open its list of options or a text input field.
    *   Immediately save your selection to the disk and return to the main list.
*   **Overrides**: Certain settings can be overridden at launch using CLI flags (such as `--sandbox` or `--dangerously-skip-permissions`):
    *   The settings menu displays an indicator showing where the override came from (for example, _Sandbox Mode on overridden by `--sandbox`_).
    *   You can still edit the persistent setting on disk, but the current session enforces the command-line override until restarted.

### Quick tips

The following table summarizes common shortcuts and commands:

| Action/Feature | Tip/Command |
| :-- | :-- |
| **Auto-complete to file paths** | `@` triggers path suggestions |
| **Clear prompt** | Press Esc twice to clear your prompt box (when no streaming is active) |
| **Terminal commands** | Use `!` at the start of your prompt to run terminal commands directly |
| **Help** | Type `?` to get help and list all slash commands |
| **Reduce noise from tool calls** | Set verbosity to **low** in `/config` to minimize outputs from numerous tool calls |
| **Manage permissions** | Control permissions using `/config` or `/permissions` |
| **Go back in conversation** | Use `/rewind` or `/undo` to rewind the conversation history |
| **Fork conversation** | Use `/fork` to branch the conversation at the current point while keeping the existing workspace |
| **Clear conversation** | Use `/clear` to clear the prompt and start a new conversation session |
| **Resume conversation** | Use `/resume` to list and resume previous conversation logs |
| **Auto-save resume** | When you close the CLI, it automatically prints the exact command needed to resume that specific session |

### Keybindings

Antigravity CLI supports custom keybindings. You can edit them by typing `/keybindings` or modifying the JSON file directly:

*   **File location**: `~/.gemini/antigravity-cli/keybindings.json`.
*   **Reset**: To reset to default, delete the `keybindings.json` file.

**Default keybindings**

These keybindings apply to Antigravity CLI only. They don’t work in the Antigravity App.

| Action/Command | Keys | Purpose |
| :-- | :-- | :-- |
| **Clear TUI screen** | Ctrl + L | Clear terminal output |
| **Enter / submit** | Enter | Submit prompts or choices |
| **Submit (alternate)** | Alt + M | Send one message the opposite way from your **Queued Messages** setting: right away instead of queued, or queued instead of right away (`prompt.submit_alternate`) |
| **Escape / cancel** | Esc / Ctrl + C | Esc stops the stream, closes menus, or clears the prompt. Ctrl + C interrupts a running turn, or exits when you press it twice. |
| **Exit CLI** | Ctrl + D | Terminate CLI TUI session |
| **Suspend CLI** | Ctrl + Z | Push CLI session to terminal background |
| **Cycle mode** | Shift + Tab | Cycle between execution modes (`cli.cycle_mode`) |
| **Edit command** | Ctrl + G | When the agent asks to run a command, expand the command into a full-screen editor inside the CLI so you can change it before you approve it. This key is fixed and doesn’t open your external editor. |
| **Confirm no** | n | Decline terminal command execution |
| **Confirm yes** | y | Approve terminal command execution |
| **Open editor** | Ctrl + G | Open your prompt in your external editor (for example, `vim` or `nano`), which you choose with the [`editor` setting](https://antigravity.google/docs/settings?tab=cli) or `$EDITOR`. CLI only: Ctrl + G doesn’t open an editor in the Antigravity App. |
| **Review artifacts** | Ctrl + R | Open the Artifact Review panel |
| **Toggle tool details** | Ctrl + O | Expand or collapse detailed tool reasoning outputs |
| **Jump to waiting subagent** | Alt + J | Switch to the next subagent awaiting confirmation |
| **Approve subagent action** | Ctrl + K | Approve the pending subagent action in the status alert |
| **Voice dictation** | F5 | Start or stop [voice dictation](./commands/voice.md) |
| **Rename conversation** | F2 | Rename the highlighted conversation in the conversation picker (`item.rename`) |
| **Delete conversation** | F4 | Delete the highlighted conversation in the conversation picker (`item.delete`) |
| **Paste text** | Ctrl + V / Alt + V | Paste text or media from your clipboard |
| **Redo text edit** | Ctrl + Shift + Z | Redo last undone text change |
| **Undo text edit** | Ctrl + \_ / Ctrl + Shift + \- | Undo last text change |
| **Yank (copy)** | Ctrl + Y | Yank/copy selected text |
| **Navigate down** | ↓ | Scroll down in menu lists |
| **Go to bottom** | Ctrl + End | Jump TUI view directly to the bottom |
| **Go to top** | Ctrl + Home | Jump TUI view directly to the top |
| **Navigate left** | ← | Move prompt cursor left |
| **Page down** | PgDn | Scroll TUI one page down |
| **Half page down** | Shift + ↓ | Scroll TUI half a page down |
| **Page up** | PgUp | Scroll TUI one page up |
| **Half page up** | Shift + ↑ | Scroll TUI half a page up |
| **Navigate right** | → | Move prompt cursor right |
| **Tab / focus** | Tab | Auto-complete choices or switch component focus |
| **Navigate up** | ↑ | Scroll up in menu lists |
| **Insert newline** | Alt + Enter / Ctrl + J / Shift + Enter | Add newline to prompt without submitting |

You can map a single action to many keybindings in the JSON file. To disable keybindings, set the list to empty (for example, `[]`). If the file is malformed, the CLI uses the valid parts and falls back to defaults for the broken actions.

Note

**Important**: Keybindings `cli.exit`, `cli.escape`, and `cli.enter` can’t be disabled.