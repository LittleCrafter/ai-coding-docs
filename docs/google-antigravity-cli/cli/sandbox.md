# Sandbox

Run agent shell commands in an isolated environment that protects your filesystem and workstation.

## How it works

With the terminal sandbox enabled, Antigravity CLI executes commands inside an OS-level isolation boundary. Commands can write to your workspace, temp directories, and common build caches, and read system directories like `/usr` and `/etc` so your tools keep working. Sensitive files like `~/.ssh` and `.env` are blocked, anything not explicitly mounted is invisible inside the sandbox, and network access is limited to domains you’ve approved.

The sandbox is built on native operating system primitives, so there are no virtual machines or Docker images to manage and no startup delay:

| Operating System | Technology | Details |
| :-- | :-- | :-- |
| **Linux** | Namespaces | Kernel namespaces isolate the filesystem, hide host processes, and cut off networking. |
| **macOS** | `sandbox-exec` | Seatbelt profiles (SBPL) restrict filesystem access and socket connections. |

## Configuration

Enable the sandbox in `~/.gemini/antigravity-cli/settings.json`, or interactively via `/config`:

```
{
    "enableTerminalSandbox": true,
    "toolPermission": "proceed-in-sandbox"
}
```

*   **`enableTerminalSandbox`** (boolean, default: `false`): Runs agent commands inside the sandbox.
*   **`toolPermission`** (string, default: `"request-review"`): Setting this to `"proceed-in-sandbox"` lets sandboxed commands run automatically, while commands that need to run outside the sandbox still prompt for review. See [Settings](./settings.md) for the other modes.

### CLI flags

You can also control sandboxing when launching the CLI:

```
# Force the sandbox on for this session
antigravity --sandbox
```

*   **`--sandbox`**: Turns the sandbox on for the session, overriding `settings.json`.

## Permissions integration

The sandbox derives its access boundaries from your **[Permissions](./permissions.md)** configuration:

*   **Filesystem**: Workspace folders and paths allowed under `write_file` are mounted read-write. Paths allowed under `read_file` are mounted read-only, on top of the default system mounts. Denied paths are blocked, and everything else is inaccessible.
*   **Network**: Sandboxed commands run without network access by default. Domains allowed under `read_url` are added to the sandbox’s outbound allowlist.
*   **Escape hatches (`unsandboxed`)**: Commands matching an `unsandboxed` allow rule run outside the sandbox without prompting. This is useful for tools that can’t work inside the isolation boundary, like Docker or commands that talk to system services.

The agent can also request to run a command outside the sandbox on its own—for example, to retry a command that failed due to sandbox restrictions. These requests always require your approval unless the command matches an `unsandboxed` allow rule.

### Example

```
{
    "permissions": {
        "allow": [
            "command(npm test)",
            "command(git diff)",
            "unsandboxed(git push)",
            "read_file(/var/log/app)",
            "write_file(src/)"
        ],
        "deny": [
            "command(rm -rf /)",
            "command(sudo *)",
            "write_file(/home/user/.ssh)"
        ]
    }
}
```

With this configuration:

*   `npm test` and `git diff` run inside the sandbox.
*   `git push` runs outside the sandbox via `unsandboxed(git push)`.
*   `rm -rf /` and `sudo` are always blocked.

## Interactive prompts

When a command needs review, you can approve it once or turn the approval into a standing rule:

```
Do you want to proceed?
1. Yes
2. Yes, and always allow in this conversation for commands that start with 'npm test'
3. Yes, and always allow for commands that start with 'npm test' (Persist to settings.json)
4. No
```

When the agent asks to bypass the sandbox, the prompt calls it out explicitly so you can judge the risk:

```
🔓 Allow sandbox bypass for command execution?
⚠️ Confirm the command is safe to run outside of the sandbox with full network and disk access.
```

Approving “always allow” here records an `unsandboxed(...)` rule instead of a plain `command(...)` rule.

## See also

*   **[Hub Sandbox](https://antigravity.google/docs/sandbox)**: How sandboxing works in Antigravity 2.0.
*   **[Permissions](./permissions.md)**: Configure allow, deny, and ask rules.
*   **[Settings](./settings.md)**: Global CLI preferences and configuration.