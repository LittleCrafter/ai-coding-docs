# Antigravity CLI Overview

The Antigravity CLI is the lightweight Terminal User Interface (TUI) surface of Antigravity. It brings the same core agentic capabilities as Antigravity 2.0 (such as multi-step reasoning, multi-file editing, tool calling, and conversation history) directly to your terminal.

## Why Antigravity CLI?

Antigravity CLI brings the reasoning, execution, and orchestration capabilities of our shared agent harness directly into your local shell. While Antigravity 2.0 offers a comprehensive visual editor interface, the CLI is custom-built for speed, lightweight operation, and seamless integration with terminal-first workflows.

### Platform comparison

| Feature | Antigravity CLI | Antigravity 2.0 |
| :-- | :-- | :-- |
| **Primary interface** | Keyboard-driven TUI | Visual desktop editor / IDE |
| **Performance overhead** | Near-zero, extremely lightweight | Standard desktop IDE footprint |
| **Workflow focus** | Fast local iterations, SSH, headless | Complete project management, visual workspace |
| **Navigation** | Universal keyboard shortcuts | Mouse and multi-panel layout |
| **Remote usability** | Native SSH, tmux, and terminal multiplexers | Local workspace or remote development containers |

## Integration features

Antigravity CLI operates in tandem with Antigravity 2.0, sharing configurations and enabling frictionless transitions between interfaces:

*   **Shared agent harness**: Both environments run on the exact same agent core. Any enhancements to multi-step reasoning, tool usage, or code comprehension apply across both platforms.
*   **Shared settings sync**: Your core preferences, permissions, and security configurations synchronize automatically across both interfaces. Updating a permission rule or standard configuration in one platform immediately updates the other.
*   **Conversation export**: Seamlessly move active conversations between platforms. If a terminal session grows in complexity and requires visual orchestration, export the conversation to Antigravity 2.0 to continue with the visual editor interface.

## Migrating from Gemini CLI

If you are transitioning from Gemini CLI, the onboarding process supports a one-time import to automatically migrate your existing Gemini CLI extensions, skills, and settings. To learn more, read [Migrating from Gemini CLI](/docs/cli/gcli-migration).

## Next steps

Explore the guides below to set up your environment and begin working with autonomous agents:

*   **[Installation & Auth](/docs/cli/install)**: Set up the CLI, configure enterprise parameters, and complete silent authentication.
*   **[Getting Started](/docs/cli/getting-started)**: Explore the onboarding roadmap, first-launch setups, and core conceptual models.
*   **[Tutorial](/docs/cli/tutorial)**: Run your first multi-file generation task with an active agent.
*   **[Prompting & Interaction](/docs/cli/prompting)**: Master multiline composing, prompt editing, and pasting terminal media.
*   **[Reviewing Artifacts](/docs/cli/artifacts)**: Leverage transparency and review agent plans, diffs, and test runs.
*   **[AI Credits](/docs/cli/credits)**: Configure and monitor AI Premium credits fallback, pricing links, and settings.
*   **[Plugins & Skills](/docs/cli/plugins)**: Create your own custom skills slash commands, manage hooks, and configure MCP servers.
*   **[Best Practices](/docs/cli/best-practices)**: Master workflow pipelines, verification loops, and session course-corrections.