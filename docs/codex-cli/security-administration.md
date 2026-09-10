# Security

> For the complete documentation index, see [llms.txt](https://learn.chatgpt.com/llms.txt). Markdown versions of documentation pages are available by appending `.md` to the page URL.

Control what ChatGPT and Codex developer tools can access, understand how work is isolated, and apply safeguards for security-sensitive tasks.

Security controls define what ChatGPT and Codex developer tools can access and how sensitive actions are reviewed. Permissions, sandboxing, approvals, and network access establish trust boundaries. Codex Security helps find and remediate vulnerabilities, and cyber safety guidance explains how security-sensitive work is handled.

> **Recommended:** [Explore permissions](./permissions.md)

## Permissions

Control filesystem, network, command, approval, and review behavior.

- [Permissions](./permissions.md) — Choose a profile for filesystem, command, and network access.
- [Sandboxing](./sandboxing.md) — Understand how Codex isolates commands and file changes.
- [Auto-review](./sandboxing/auto-review.md) — Review actions automatically against your configured policy.
- [Agent approvals and security](./agent-approvals-security.md) — Decide when Codex must ask before taking an action.
- [Internet access](./cloud/internet-access.md) — Control which domains cloud chats can reach.

## Codex Security

Find, understand, and remediate vulnerabilities.

- [Codex Security overview](./security.md) — Assess code and turn reviewed findings into focused fixes.
- [Codex Security plugin](./security/plugin.md) — Run security workflows from the ChatGPT desktop app and Codex CLI.
- [Codex Security CLI](./security/cli.md) — Run local security scans and automate repository reviews.
- [Codex Security TypeScript SDK](./security/sdk.md) — Integrate security scanning and progress reporting into developer tools.
- [Codex Security cloud setup](./security/setup.md) — Connect repositories and configure cloud security scans.
- [Security Review](./security/security-review.md) — Run in-depth security reviews on GitHub pull requests.
- [Threat model](./security/threat-model.md) — Review and improve the threat model for your codebase.
- [Codex Security cloud FAQ](./security/faq.md) — Get answers about cloud scans, findings, privacy, and access.

## Cyber safety

Choose approved models and configure safe engagements.

- [Models & Trusted Access](./cyber-safety.md) — Choose a cybersecurity model and request Trusted Access.
- [Recommended configuration](./cyber-safety/recommended-configuration.md) — Isolate the environment, enforce scope, and review sensitive actions.