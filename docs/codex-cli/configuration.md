# Configuration

> For the complete documentation index, see [llms.txt](https://learn.chatgpt.com/llms.txt). Markdown versions of documentation pages are available by appending `.md` to the page URL.

Set defaults, add durable context, and customize how ChatGPT and Codex developer tools work.

Configuration shapes how ChatGPT and Codex developer tools behave across chats, repositories, and machines. Durable context, config files, repository guidance, subagents, external connections, and Linux and Windows setup work together to keep those workflows consistent for individuals and teams.

> **Recommended:** [Explore customization](./customization/overview.md)

## Customization

Adapt the experience and carry useful context between chats.

- [Customization overview](./customization/overview.md) — Customize ChatGPT and Codex with guidance, skills, MCP, and subagents.
- [Memories](./customization/memories.md) — Let ChatGPT retain useful context across chats.
- [Computer History](./customization/computer-history.md) — Use recent computer activity as context and manage what is included.

## Config file

Control models, tools, environments, and defaults with configuration files and variables.

- [Config basics](./config-file/config-basic.md) — Understand configuration layers and create a config file.
- [Advanced config](./config-file/config-advanced.md) — Use profiles, providers, policies, and advanced options.
- [Config reference](./config-file/config-reference.md) — Look up every supported configuration key.
- [Environment variables](./config-file/environment-variables.md) — Set values that change across systems and sessions.
- [Sample config](./config-file/config-sample.md) — Start from a complete, annotated configuration example.

## Agent configuration

Shape how agents collaborate and follow project guidance.

- [AGENTS.md](./agent-configuration/agents-md.md) — Give Codex durable instructions for a repository.
- [Subagents](./agent-configuration/subagents.md) — Delegate focused tasks to specialized agents.
- [Speed](./agent-configuration/speed.md) — Control how quickly and deeply Codex works.
- [Rules](./agent-configuration/rules.md) — Define commands Codex can run automatically.

## Extend ChatGPT and Codex

Package knowledge, connect services, and add capabilities.

- [Record & Replay](./extend/record-and-replay.md) — Show ChatGPT or Codex a workflow and turn it into a reusable skill.
- [MCP](./extend/mcp.md) — Connect Codex developer tools to external tools and context.

## Linux

Install and update ChatGPT on a supported Linux desktop.

- [ChatGPT desktop app](./linux/linux-app.md) — Install the Linux preview on Ubuntu, Debian, or Fedora.

## Windows

Run Codex natively on Windows or inside WSL.

- [ChatGPT desktop app](./windows/windows-app.md) — Use the ChatGPT desktop app with PowerShell or WSL workflows.
- [Windows sandbox](./windows/windows-sandbox.md) — Run Codex with native filesystem and command isolation.
- [WSL](./windows/wsl.md) — Use Codex in a Linux environment managed by Windows.