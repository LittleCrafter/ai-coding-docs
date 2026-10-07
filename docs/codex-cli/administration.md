# Administration

> For the complete documentation index, see [llms.txt](https://learn.chatgpt.com/llms.txt). Markdown versions of documentation pages are available by appending `.md` to the page URL.

Set access and policy boundaries for ChatGPT, Codex developer tools, APIs, plugins, and connected systems.

Start with workspace identity and access. Then configure local runtime policy for supported capabilities in the ChatGPT desktop app, Codex CLI, and IDE extension; Codex cloud eligibility; Platform API access; plugins and connectors; and permissions in connected systems.

> **Recommended:** [Explore authentication](./auth.md)

## Getting started

Plan your rollout and explore tools for routine administration.

- [Admin rollout guide](./enterprise/admin-setup.md) — Plan access, assign owners, configure controls, and verify the rollout.
- [Admin plugin](./enterprise/admin-plugin.md) — Use the Admin plugin for permissions, approvals, and supported administrative workflows.

## Feature setup

Choose a setup task, then review its access and security requirements.

- [Configure dots permissions](./dots/controls.md#for-workspace-admins) — Manage dots access, communication, computers, and custom rules.
- [Manage Space sharing and access](./space/collaboration.md#for-workspace-admins) — Control Library sharing permissions and help members share pages.
- [Set up teams and Team Tasks](./enterprise/teams.md#for-workspace-admins) — Set team permissions, connect shared accounts, and create recurring tasks.
- [Set up @ChatGPT in Slack or Teams](./enterprise/chatgpt-slack-and-teams.md) — Review administrator responsibilities and deployment prerequisites.
- [Set up a workspace connection](./enterprise/shared-connections.md#set-up-a-connection) — Prepare company-managed accounts and configure a workspace connection.
- [Local computer access for Work Cloud and dots](./enterprise/cloud-local-access.md#how-to-set-up-local-computer-access) — Review shared policies and compatibility, then enable local computer access separately for Work and dots.
- [Set up Sites and connected plugins](./enterprise/sites.md#enable-plugin-use-in-sites) — Enable tenant and plugin access so Sites can use visitors' connected accounts.

## Identity and access

Manage sign-in, provisioning, roles, and credentials.

- [Authentication overview](./auth.md) — Compare sign-in methods, credential storage, and enforcement controls.
- [Groups and provisioning](./enterprise/groups-and-provisioning.md) — Manage manual and SCIM groups, provisioning, and rollout cohorts.
- [User lifecycle management](./enterprise/user-lifecycle.md) — Provision employees, update group access, and revoke departing users' credentials.
- [Roles and workspace permissions](./enterprise/roles-and-workspace-permissions.md) — Find workspace, runtime, API, plugin, and source-system controls.
- [Personal access tokens](./enterprise/access-tokens.md) — Create and manage tokens for programmatic access.
- [Service accounts](./enterprise/service-accounts.md) — Create and manage workspace identities for automated workflows.

## Deployment and configuration

Deploy apps and configure updates, runtime settings, remote connections, and model access.

- [Windows app deployment](./enterprise/windows-deployment.md) — Choose an installation and update path for managed Windows devices.
- [Manage app updates](./enterprise/manage-app-updates.md) — Control desktop app updates and deploy approved versions through your device management platform.
- [Managed configuration](./enterprise/managed-configuration.md) — Review the global baseline in Agent Security, policy precedence for this feature, and supported runtime requirements.
- [Remote connections](./remote-connections.md) — Start and control work on connected computers.
- [Workspace model availability](./enterprise/workspace-model-availability.md) — Separate model access for ChatGPT, Codex in the ChatGPT desktop app, Codex CLI, the IDE extension, Codex cloud, and the Platform API.
- [Amazon Bedrock](./amazon-bedrock.md) — Configure supported local clients to use models available through Bedrock.
- [Bedrock GovCloud configuration](https://developers.openai.com/codex/enterprise/govcloud-configuration) — Configure local Codex workflows with Amazon Bedrock in AWS GovCloud.
- [Sign in with ChatGPT through a gateway](./enterprise/sign-in-with-chatgpt-through-a-gateway.md) — Keep your gateway for model requests while using your ChatGPT workspace identity.
- [Use API/provider credentials](./enterprise/connect-to-a-gateway.md) — Configure one Codex client to use your organization's model gateway and verify the connection.
- [Roll out a gateway](./enterprise/roll-out-a-gateway.md) — Configure model routes, issue credentials, and deploy Codex through your organization’s gateway.
- [Gateway compatibility](./enterprise/gateway-compatibility.md) — Check the Responses API behavior required for model requests, streaming, and tool calls.
- [Bedrock through LiteLLM](./enterprise/bedrock-through-litellm.md) — Configure a LiteLLM gateway to route Codex model requests to Amazon Bedrock.

## ChatGPT Work

Review the ChatGPT Work overview and administration reference.

- [Overview](./enterprise/chatgpt-work-overview.md) — Understand local and cloud execution, Local computer access with Work Cloud, network controls, and data boundaries.
- [Cloud security](./enterprise/chatgpt-work-cloud-security.md) — Review hosted execution, connected accounts, access controls, retention, and audit visibility.
- [Local security](./enterprise/chatgpt-work-local-security.md) — Review local execution, device and browser access, managed policies, data handling, and audit limitations.
- [Usage and cost](./enterprise/chatgpt-work-usage-and-cost.md) — Understand shared credits, billing impact, spending controls, and adoption planning.
- [Admin FAQ](./enterprise/work-admin-faq.md) — Review access, data, governance, usage, and incident controls for ChatGPT Work.

## Collaboration and sharing

Manage GPT sharing and ownership.

- [GPTs and sharing](./enterprise/gpts-and-sharing.md) — Manage GPT sharing, ownership, connected apps, and third-party actions across your workspace.

## Plugins and connections

Control plugin installation, bundled skills, connector-backed capabilities, and connected-service access.

- [Plugin controls](./enterprise/apps-and-connectors.md) — Manage plugin availability, connector access and actions, and source-system permissions.
- [Plugin management](./enterprise/plugin-management.md) — Import and sync workspace plugins from GitHub.
- [Skill controls](./enterprise/skills.md) — Compare ChatGPT workspace, local filesystem, and plugin skill controls.
- [Migrate custom GPTs to plugins](./migrate-custom-gpts.md) — Plan your workspace transition, migrate individual GPTs or eligible batches, and test and share replacement plugins.

## Usage and analytics

Review workspace usage and adoption, and automate reporting.

- [Workspace analytics](./enterprise/workspace-analytics.md) — Review workspace-level ChatGPT adoption and Codex usage.
- [Usage Insights](./enterprise/usage-insights.md) — Explore usage across ChatGPT Work and Codex and assess workflow results with your team.
- [Analytics API](./enterprise/analytics-api.md) — Automate developer activity and code review reporting with the Codex Analytics API.

## Security and compliance

Review workspace security policies, governance, and audit controls.

- [Governance](./enterprise/governance.md) — Choose the right analytics, spend, and audit surface for each question.
- [Agent security](./enterprise/agent-security.md) — Manage the Global policy baseline and supported Local and Codex Cloud environment settings.
- [Prisma AIRS](./enterprise/prisma-airs.md) — Apply workspace-wide security policies to Codex prompts.
- [HIPAA configuration](https://developers.openai.com/codex/hipaa-configuration) — Configure local runtime safeguards for workflows that may handle protected health information.
- [Compliance API and audit events](./enterprise/compliance-api.md) — Export activity records for audit and investigation workflows.