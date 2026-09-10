# Administration

> For the complete documentation index, see [llms.txt](https://learn.chatgpt.com/llms.txt). Markdown versions of documentation pages are available by appending `.md` to the page URL.

Set access and policy boundaries for ChatGPT, Codex developer tools, APIs, plugins, and connected systems.

Administration covers six related boundaries: ChatGPT workspace access; local runtime policy for covered capabilities in the ChatGPT desktop app, Codex CLI, and IDE extension; Codex cloud eligibility; Platform API access; plugin availability and connector permissions; and permissions in connected systems. Start with workspace identity and access, then apply the runtime and source-system controls required for each deployment.

> **Recommended:** [Explore authentication](./auth.md)

## Getting started

Start with the rollout guide, then use the reference pages for each control boundary.

- [Admin rollout guide](./enterprise/admin-setup.md) — Plan access, assign owners, configure controls, and verify the rollout.

## ChatGPT Work

Review the ChatGPT Work overview and administration reference.

- [ChatGPT Work Overview](./enterprise/chatgpt-work-overview.md) — Understand hosted execution, network controls, data boundaries, and audit visibility.
- [ChatGPT Work cloud security](./enterprise/chatgpt-work-cloud-security.md) — Review hosted execution, connected accounts, access controls, retention, and audit visibility.
- [ChatGPT Work local security](./enterprise/chatgpt-work-local-security.md) — Review local execution, device and browser access, managed policies, data handling, and audit limitations.
- [ChatGPT Work admin FAQ](./enterprise/work-admin-faq.md) — Review access, data, governance, usage, and incident controls for ChatGPT Work.
- [ChatGPT Work: usage and cost](./enterprise/chatgpt-work-usage-and-cost.md) — Understand shared credits, billing impact, spending controls, and adoption planning.

## Identity and authentication

Choose how people sign in and issue credentials for programmatic workflows.

- [Authentication overview](./auth.md) — Compare sign-in methods, credential storage, and enforcement controls.
- [Workload identity](./enterprise/workload-identity.md) — Let trusted workloads use Codex without long-lived credentials.
- [Personal Access Tokens](./enterprise/access-tokens.md) — Create and manage tokens for programmatic access.
- [Service accounts](./enterprise/service-accounts.md) — Create and manage workspace identities for automated workflows.

## Workspace access, policy, and models

Assign ChatGPT workspace access and keep it separate from local runtime policy, Codex cloud access, and Platform API access.

- [Groups and provisioning](./enterprise/groups-and-provisioning.md) — Manage manual and SCIM groups, provisioning, and rollout cohorts.
- [User lifecycle management](./enterprise/user-lifecycle.md) — Provision employees, update group access, and revoke departing users' credentials.
- [Roles and workspace permissions](./enterprise/roles-and-workspace-permissions.md) — Use the canonical map of workspace, runtime, API, plugin, and source-system controls.
- [GPTs and Sharing](./enterprise/gpts-and-sharing.md) — Manage GPT sharing, ownership, connected apps, and third-party actions across your workspace.
- [Managed configuration](./enterprise/managed-configuration.md) — Distribute managed settings where supported and enforce runtime requirements for covered capabilities in the ChatGPT desktop app, Codex CLI, and IDE extension.
- [Prisma AIRS](./enterprise/prisma-airs.md) — Apply workspace-wide security policies to Codex prompts.
- [HIPAA configuration](https://developers.openai.com/codex/hipaa-configuration) — Configure local runtime safeguards for workflows that may handle protected health information.
- [Workspace model availability](./enterprise/workspace-model-availability.md) — Separate model access for ChatGPT, Codex in the ChatGPT desktop app, Codex CLI, the IDE extension, Codex cloud, and the Platform API.

## Plugin and connector controls

Control plugin installation, bundled skills, connector-backed capabilities, and connected-service access.

- [Plugin controls](./enterprise/apps-and-connectors.md) — Manage plugin availability, connector access and actions, and source-system permissions.
- [Plugin management](./enterprise/plugin-management.md) — Import and sync workspace plugins from GitHub.
- [Skill controls](./enterprise/skills.md) — Compare ChatGPT workspace, local filesystem, and plugin skill controls.

## Usage, governance, and compliance

Measure adoption and route reporting or audit data to the system that owns it.

- [Governance](./enterprise/governance.md) — Choose the right analytics, spend, and audit surface for each question.
- [Admin plugin](./enterprise/admin-plugin.md) — Use the Admin plugin for permissions, approvals, and supported administrative workflows.
- [Workspace analytics](./enterprise/workspace-analytics.md) — Review workspace-level ChatGPT adoption and Codex usage.
- [Analytics API](./enterprise/analytics-api.md) — Automate developer activity and code review reporting with the Codex Analytics API.
- [Compliance API and audit events](./enterprise/compliance-api.md) — Export activity records for audit and investigation workflows.

## Deployment and model providers

Deploy and update desktop apps, connect managed hosts, or configure a supported external model provider.

- [Manage app updates](./enterprise/manage-app-updates.md) — Control desktop app updates and deploy approved versions through your device management platform.
- [Windows app deployment](./enterprise/windows-deployment.md) — Choose an installation and update path for managed Windows devices.
- [Remote connections](./remote-connections.md) — Start and control work on connected computers.
- [Amazon Bedrock](./amazon-bedrock.md) — Configure supported local clients to use models available through Bedrock.