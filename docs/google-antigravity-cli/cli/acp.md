# Agent Client Protocol (ACP)

Available on: Antigravity CLI

Use Antigravity CLI as the coding agent inside your editor. The `agy acp` command starts an [Agent Client Protocol](https://agentclientprotocol.com) (ACP) server, so editors that support ACP, such as Zed, JetBrains IDEs, Android Studio, and Xcode, can run the agent in their own chat panel.

```bash
agy acp [flags]
```

Your editor launches `agy acp` as a subprocess and talks to it with JSON-RPC over `stdin` and `stdout`. You don’t run the command yourself. The agent, its tools, your sign-in, and your settings come from Antigravity CLI, so the agent behaves the same in the editor as it does in the terminal.

This video demo shows how to configure ACP in the Zed editor:

## Quick start

1.  [Install Antigravity CLI](https://antigravity.google/docs/install?tab=cli) and confirm that your version includes ACP:
    
    ```bash
    agy acp --help
    ```
    
2.  Sign in once with an interactive `agy` session, or run `agy acp --login`. `agy acp` reuses the cached credentials.
    
3.  Register `agy` with the argument `acp` as a custom agent in your editor. For example, in Zed’s `settings.json`:
    
    ```json
    {
      "agent_servers": {
        "Antigravity": {
          "type": "custom",
          "command": "agy",
          "args": ["acp"]
        }
      }
    }
    ```
    
4.  Start a new thread with **Antigravity** in your editor’s agent panel.
    

For setup steps for each editor, permissions, authentication methods, flags, and troubleshooting, refer to the full guide:

[Other editors (ACP)](https://antigravity.google/docs/ide/extensions/acp)Connect VS Code, Zed, JetBrains IDEs, Android Studio, Xcode, and other ACP clients to Antigravity CLI.

## Next steps

*   **[Headless mode](./headless.md)**: Run the agent non-interactively in scripts and CI.
*   **[Permissions](https://antigravity.google/docs/permissions)**: Configure which actions the agent can take without asking.
*   **[Reference](./reference.md)**: Full command and flag reference.