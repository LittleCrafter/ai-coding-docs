# Developer settings

> For the complete documentation index, see [llms.txt](https://learn.chatgpt.com/llms.txt). Markdown versions of documentation pages are available by appending `.md` to the page URL.

**Surface: Web**

ChatGPT web stores product and workspace preferences in ChatGPT settings. ChatGPT Work
chats run in a managed environment and don't read local Codex
configuration files. Use the controls your workspace exposes in ChatGPT
settings; workspace administrators may manage some settings for you.

**Surface: Desktop app**

The general [Settings](./reference/settings.md) page covers app preferences,
including profile, keyboard shortcuts, notifications, appearance,
personalization, memories, and archived chats.

<a id="app-project-and-terminal-behavior"></a>

## Project and terminal behavior

Choose where files open, how much command output appears in chats, and where
terminal tabs open by default.

<a id="app-code-review"></a>

## Code review

Under **Settings > Git**, use **Review delivery** to choose **Inline** to run
`/review` in the current chat when possible or **Detached** to start a separate
review chat.

<a id="app-ide-extension-sync"></a>

## IDE extension sync

When the ChatGPT desktop app and IDE extension are open in the same project,
they share active chats and editor context. Turn on **IDE context** from the app
composer to let Codex use files currently open in your editor. Turn it off when
you want the app prompt to exclude that editor context.

You can open an app chat from the IDE extension and continue an IDE chat in the
app. Both surfaces use the same project to determine which chats and context to
share.

<a id="app-agent-configuration"></a>

## Agent configuration

Codex agents in the app inherit the same configuration as the IDE extension and
CLI. Use the in-app controls for common settings, or edit `config.toml` for
advanced options. See [Agent approvals and security](./agent-approvals-security.md)
and [Config basics](./config-file/config-basic.md) for details.

<a id="app-git"></a>

## Git

Use Git settings to standardize branch naming and choose whether Codex uses
force pushes. You can also set prompts that Codex uses to generate commit
messages and pull request descriptions.

<a id="app-integrations-and-mcp"></a>

## Integrations and MCP

Connect external tools through Model Context Protocol (MCP). Enable recommended
servers or add your own. If a server requires OAuth, the app starts the
authentication flow. These settings also apply to the Codex CLI and IDE
extension because MCP configuration lives in `config.toml`. See
[Model Context Protocol](./extend/mcp.md) for details.

<a id="app-browser-developer-mode"></a>

## Browser developer mode

Under **Developer mode**, turn on **Enable full CDP access** to let ChatGPT use
the Chrome DevTools Protocol for performance profiling and deeper browser
debugging. If your organization has disabled full CDP access, you can't enable
it locally. See [Developer mode](./browser.md#app-developer-mode) for setup,
risk, approval, and administrator requirements.

**Surface: CLI**

Codex CLI reads your personal defaults from `~/.codex/config.toml`. Add a
`.codex/config.toml` file to a trusted project or subfolder when you need
project-specific overrides. The CLI and IDE extension share these configuration
layers.

<a id="cli-inspect-your-settings"></a>

## Inspect your settings

Use these commands to understand the effective settings for the current
session:

- Run `/status` to see the active model, approval policy, writable roots, and
  token usage.
- Run `/debug-config` to see the configuration layers in precedence order and
  the source of managed policy requirements.
- Start Codex with `--strict-config` to treat unrecognized `config.toml` keys as
  errors instead of ignoring them.

See [Developer commands](./developer-commands.md) for the full
interactive command reference.

<a id="cli-change-settings-for-one-run"></a>

## Change settings for one run

Use a dedicated flag when one exists. Common examples include `--model`,
`--sandbox`, `--ask-for-approval`, `--profile`, and `--search`. Use `-c` or
`--config` to override any supported configuration key for one run:

```shell
codex --model gpt-5.5
codex --profile deep-review
codex --config model_reasoning_effort='"high"'
```

Command-line flags and `--config` values have the highest precedence. For the
complete flag list, see [Developer commands](./developer-commands.md).

<a id="cli-configuration-layers"></a>

## Configuration layers

The CLI applies command-line flags and `--config` overrides before project,
profile, user, system, and built-in settings. Use that precedence to keep shared
defaults in configuration files and one-off changes on the command line.

For the complete order and common options, see [Config basics](./config-file/config-basic.md).

<a id="cli-change-settings-in-the-tui"></a>

## Change settings in the TUI

The interactive terminal UI provides pickers for common session and display
settings:

| Goal                      | Command                                      | Related configuration                         |
| ------------------------- | -------------------------------------------- | --------------------------------------------- |
| Choose a model            | `/model`                                     | `model`, `model_reasoning_effort`             |
| Change permissions        | `/permissions`                               | Approval and sandbox settings                 |
| Choose a response style   | `/personality`                               | `personality`                                 |
| Configure optional tools  | `/experimental`, `/memories`                 | Feature-specific `config.toml` keys           |
| Customize the terminal UI | `/keymap`, `/statusline`, `/title`, `/theme` | Keys under `[tui]`                            |
| Set editing defaults      | `/vim`, `/raw`                               | `tui.vim_mode_default`, `tui.raw_output_mode` |

Some commands apply only to the current session, while some pickers offer to
save the choice. Set the related configuration key when you want a default for
future sessions. For the terminal theme, editor, completions, and shortcut
workflows, see [CLI customization](./cli-customization.md).

<a id="cli-settings-references"></a>

## Settings references

- [Advanced configuration](./config-file/config-advanced.md) covers profiles, one-off overrides, and other advanced workflows.
- [Configuration reference](./config-file/config-reference.md) lists the available keys and values.
- [Sample configuration](./config-file/config-sample.md) provides a complete example file.
- [Environment variables](./config-file/environment-variables.md) documents variables used by the CLI and installer.

**Surface: IDE extension**

The Codex IDE extension has two settings layers:

- **Codex settings** control agent behavior shared with Codex CLI, including the
  model, reasoning effort, permissions, sandbox, MCP servers, and
  personalization. Codex reads these settings from `config.toml`.
- **Editor settings** control how the extension behaves inside VS Code and
  compatible editors. These settings use `chatgpt.*` keys in the editor's
  settings system.

<a id="ide-open-codex-settings"></a>

## Open Codex settings

Select the gear icon in the Codex sidebar, then select **Codex Settings**. Use
the settings panel for common agent controls, or select **Open config.toml** to
edit the active configuration layer directly.

For the configuration layer order and common keys, see [Config
basics](./config-file/config-basic.md). For every supported `config.toml` key, see the
[Configuration reference](./config-file/config-reference.md).

<a id="ide-change-an-editor-setting"></a>

## Change an editor setting

To change a setting, follow these steps:

1. Open your editor settings.
2. Search for `@ext:openai.chatgpt`, `Codex`, or the setting name.
3. Update the value.

The extension also honors VS Code's built-in chat font settings for Codex chat surfaces.

<a id="ide-editor-settings-reference"></a>

## Editor settings reference

| Setting                                      | Default        | Description                                                                                                                                                                                                                                                                                |
| -------------------------------------------- | -------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `chatgpt.commentCodeLensEnabled`             | `true`         | Show CodeLens above `TODO` comments so Codex can address them.                                                                                                                                                                                                                             |
| `chatgpt.openOnStartup`                      | `false`        | Focus the Codex sidebar when the extension finishes starting.                                                                                                                                                                                                                              |
| `chatgpt.followUpQueueMode`                  | `queue`        | Choose whether messages sent during a run wait for the next run (`queue`) or steer the current run (`steer`). The extension treats the legacy `interrupt` value as `steer`. Press <kbd>Cmd</kbd>/<kbd>Ctrl</kbd>+<kbd>Shift</kbd>+<kbd>Enter</kbd> to invert the behavior for one message. |
| `chatgpt.composerEnterBehavior`              | `enter`        | Choose whether <kbd>Enter</kbd> always sends (`enter`), <kbd>Cmd</kbd>/<kbd>Ctrl</kbd>+<kbd>Enter</kbd> sends multiline prompts (`cmdIfMultiline`), or the modifier is always required (`cmdAlways`).                                                                                      |
| `chatgpt.reviewDelivery`                     | `inline`       | Run `/review` in the current chat when possible (`inline`) or start a separate review chat (`detached`).                                                                                                                                                                                   |
| `chatgpt.localeOverride`                     | Auto           | Set the preferred language for the Codex UI. Leave empty to detect it automatically.                                                                                                                                                                                                       |
| `chatgpt.runCodexInWindowsSubsystemForLinux` | `false`        | Windows only: Run Codex in WSL when WSL is available. Use this when your repositories and tooling live in WSL2 or when you need Linux-native tooling. Changing this setting reloads VS Code.                                                                                               |
| `chatgpt.cliExecutable`                      | Unset          | Development only: Set the path to the Codex CLI executable. You don't need this setting unless you're developing the Codex CLI; manually overriding the bundled executable can prevent parts of the extension from working.                                                                |
| `chat.fontSize`                              | Editor default | Control chat text in the Codex sidebar, including chat content and the composer.                                                                                                                                                                                                           |
| `chat.editor.fontSize`                       | Editor default | Control code-rendered content in Codex chats, including code snippets and diffs.                                                                                                                                                                                                           |

The `chatgpt.*` keys above belong to the IDE extension and don't go in
`config.toml`. For shared agent settings, use [Config
basics](./config-file/config-basic.md), [Advanced configuration](./config-file/config-advanced.md),
and the [Configuration reference](./config-file/config-reference.md).