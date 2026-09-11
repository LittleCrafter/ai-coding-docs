# Glossary

> For the complete documentation index, see [llms.txt](https://learn.chatgpt.com/llms.txt). Markdown versions of documentation pages are available by appending `.md` to the page URL.

Use this glossary as a quick reference for Codex terms across the app, CLI, IDE extension, cloud, SDK, and related integrations.

| Term | Applies to | Definition |
| --- | --- | --- |
| [Action](./agent-approvals-security.md) | Desktop app, Web, Mobile, CLI, IDE extension, Cloud | An operation performed by a person, ChatGPT, or Codex, such as editing a file, running a command, or using a connected service. |
| [Agent](https://developers.openai.com/codex) | Desktop app, CLI, IDE extension, Cloud | The Codex agent that reasons over context, uses tools, and completes a task. |
| [AGENTS.md](./agent-configuration/agents-md.md) | Desktop app, CLI, IDE extension, Cloud | Repository or user guidance file that gives Codex persistent instructions. |
| [Analytics dashboard](./enterprise/workspace-analytics.md) | Enterprise | Admin hub for ChatGPT workspace adoption and Codex-focused reporting. |
| [API key sign-in](./auth.md#sign-in-with-an-api-key) | Desktop app, CLI, IDE extension | Authentication using an OpenAI API key. |
| [Approval policy](./agent-approvals-security.md#sandbox-and-approvals) | Desktop app, CLI, IDE extension | Rules for when Codex must ask before taking an action. |
| [Approval request](./agent-approvals-security.md#automatic-approval-reviews) | Desktop app, CLI, IDE extension | Codex asking to allow a restricted action. |
| [Apps (configuration)](./plugins.md) | Desktop app, CLI, IDE extension | Codex configuration and app-server fields that store connector settings under the `apps` name. |
| [Appshot](./appshots.md) | Desktop app | Snapshot of the frontmost app window sent to a ChatGPT or Codex chat. |
| [Auth cache](./auth.md#login-caching) | Desktop app, CLI, IDE extension | Locally stored login credentials reused by Codex. |
| [Automatic approval review](./agent-approvals-security.md#automatic-approval-reviews) | Desktop app, CLI, IDE extension | Model-based review of eligible approval requests before they proceed. |
| [Scheduled task](./automations.md) | Desktop app, Web | A prompt ChatGPT runs at a future time or on a recurring schedule, with its own settings and run history. |
| [Scheduled run](./automations.md#managing-tasks) | Desktop app, Web | One execution of a scheduled task, including its status and any resulting findings. |
| [Computer Use in the browser](./browser.md) | Desktop app | Capability that lets ChatGPT operate the built-in browser directly. |
| [Chat](./projects.md#start-a-chat) | Desktop app, Web, Mobile, CLI, IDE extension, Cloud | A saved space for exchanging messages with ChatGPT or Codex, including shared context, results, and actions. Quick chat starts a ChatGPT chat from Codex. |
| [ChatGPT sign-in](./auth.md#sign-in-with-chatgpt) | Desktop app, CLI, IDE extension, Cloud | Authentication using a ChatGPT account and workspace permissions. |
| [Computer History](./customization/computer-history.md) | Desktop app | Opt-in macOS feature that builds memories and a timeline from interaction events across allowed apps and websites. |
| [Cloud](./cloud.md) | Desktop app, IDE extension, Web | Mode where Codex works remotely in an OpenAI-managed environment. |
| [Cloud environment](./environments/cloud-environment.md) | Cloud | Configured container setup used for Codex cloud chats. |
| [Cloud chat](./environments/cloud-environment.md#how-codex-cloud-tasks-run) | Cloud | A Codex chat that runs remotely in a cloud environment. |
| [Codex](https://developers.openai.com/codex) | Desktop app, CLI, IDE extension, Web, Cloud, SDK | OpenAI's coding agent for software development tasks. |
| [ChatGPT desktop app](./app.md) | Desktop | Desktop app with ChatGPT and Codex, including Chat and Work, projects, file previews, scheduled tasks, and developer tools. |
| [Codex app-server](./app-server.md) | Desktop app, IDE extension, SDK | Local JSON-RPC server for embedding Codex threads, turns, approvals, history, and streamed events in custom clients. |
| [Codex CLI](https://developers.openai.com/codex/cli) | Terminal | Terminal client for running Codex interactively or in scripts. |
| [Codex cloud](./cloud.md) | Web, Desktop app, IDE extension | OpenAI-managed execution environment where Codex can work on repository tasks remotely. |
| [codex exec](./non-interactive-mode.md) | CLI | CLI command for running Codex non-interactively from scripts or CI. |
| [Codex IDE extension](https://developers.openai.com/codex/ide) | IDE | Editor integration for using Codex inside IDEs like VS Code, JetBrains IDEs, Cursor, and Windsurf. |
| [Codex SDK](./codex-sdk.md) | SDK | Programmatic interface for building Codex-powered workflows or integrations. |
| [Codex-managed worktree](./environments/git-worktrees.md#codex-managed-and-permanent-worktrees) | Desktop app | A temporary worktree Codex creates and manages for a chat. |
| [Compaction](./prompting.md#context) | Desktop app, CLI, IDE extension, Cloud | Summarizing older context so long-running work can continue. |
| [Compliance API](./enterprise/compliance-api.md) | Enterprise | API for exporting supported ChatGPT workspace records and audit metadata. |
| [Computer Use](./computer-use.md) | Desktop app | Desktop capability that lets ChatGPT interact with other applications through the UI. |
| [config.toml](./config-file/config-reference.md#configtoml) | Desktop app, CLI, IDE extension | Local Codex configuration files. |
| [Connected host](./remote-connections.md#what-comes-from-the-connected-host) | Desktop app, Mobile | Computer or development environment that provides files, tools, and shell access for ChatGPT or Codex chats opened through Remote. |
| [Connector](./plugins.md) | Desktop app (ChatGPT Work, Codex), Web (ChatGPT Work) | A component of a plugin that connects ChatGPT or Codex to data and actions in an external service. |
| [Conversation](./projects.md#start-a-chat) | Desktop app, Web, Mobile, CLI, IDE extension, Cloud | The ongoing exchange of messages and shared context between a person and ChatGPT or Codex within a chat. |
| [Container cache](./environments/cloud-environment.md#container-caching) | Cloud | Saved cloud container state reused to speed up future cloud chats. |
| [Context](./prompting.md#context) | Desktop app, CLI, IDE extension, Cloud, SDK | Information Codex can use while working, such as files, prior messages, tool output, and instructions. |
| [Context window](https://developers.openai.com/api/docs/guides/conversation-state#managing-the-context-window) | Desktop app, CLI, IDE extension, Cloud, SDK | The maximum amount of information the model can consider at once. |
| [Custom agent](./agent-configuration/subagents.md#custom-agents) | Desktop app, CLI | User-defined agent role with its own instructions and settings. |
| [Deny-read rule](./permissions.md#deny-reads-with-exact-paths-or-globs) | Desktop app, CLI, IDE extension, Enterprise | Filesystem permission rule that prevents Codex from reading sensitive paths or glob matches. |
| [Diff](./code-review.md) | Desktop app, Git, Review | Set of Git file changes shown for inspection, comments, staging, or reverting. |
| [Domain allowlist](./cloud/internet-access.md#domain-allowlist) | Cloud | Set of domains Codex cloud can reach when agent internet access is enabled. |
| [Environment (local)](./environments/local-environment.md) | Desktop app, Worktree | Desktop app configuration that tells Codex how to set up worktrees for a project. |
| [Environment variable](./environments/cloud-environment.md#environment-variables-and-secrets) | Cloud, CLI, IDE extension | Runtime configuration value available during task execution. |
| [Ephemeral session](./non-interactive-mode.md#basic-usage) | CLI | Non-interactive run that skips saving session state after it completes. |
| [Fast mode](./agent-configuration/speed.md#fast-mode) | CLI, IDE extension | Speed setting that makes supported models respond faster at a higher credit cost. |
| [Filesystem permission](./permissions.md#filesystem-permissions) | Desktop app, CLI, IDE extension | Permission profile rule that grants or denies read and write access to paths. |
| [Finding](./automations.md#managing-tasks) | Desktop app | A notable result or issue surfaced by a scheduled task. |
| [Full access](./sandboxing.md#configure-defaults) | Desktop app, CLI, IDE extension | Mode where Codex runs without normal sandbox restrictions. |
| [Git worktree](./environments/git-worktrees.md#whats-a-worktree) | Desktop app, Git | A second checkout of the same repository for parallel branch work. |
| [Handoff](./environments/git-worktrees.md#working-between-local-and-worktree) | Desktop app | Moving a chat and its work between Local and Worktree. |
| [Heartbeat](./automations.md#schedule-a-task-inside-a-chat) | Desktop app | A recurring scheduled task that returns ChatGPT to the same chat. |
| [Hook](./hooks.md) | Desktop app, CLI, IDE extension | A lifecycle handler that runs when a Codex event matches, such as tool use, permission requests, or when a turn stops. |
| [Hook event](./hooks.md#config-shape) | Desktop app, CLI, IDE extension | Lifecycle point where configured hook handlers can run. |
| [Hunk](./code-review.md) | Desktop app, Git, Review | Contiguous section of a diff that can be staged, unstaged, or reverted independently. |
| [Inline comment](./code-review.md) | Desktop app | Line-specific feedback attached to a diff. |
| [Live web search](./config-file/config-basic.md#web-search-mode) | Desktop app, CLI, IDE extension | Real-time web lookup for current information. |
| [Local](./environments/git-worktrees.md#working-between-local-and-worktree) | Desktop app, CLI, IDE extension | Mode where Codex works on the user's computer. |
| [Local chat](./environments/modes.md) | Desktop app, CLI, IDE extension | A ChatGPT or Codex chat that runs on the user's machine. |
| [Maintenance script](./environments/cloud-environment.md#container-caching) | Cloud | Optional script run when a cached cloud container resumes. |
| [Managed configuration](./enterprise/managed-configuration.md) | Enterprise | Organization-controlled Codex defaults and restrictions. |
| [MCP](./extend/mcp.md) | Desktop app, CLI, IDE extension | Model Context Protocol, a standard for connecting Codex to external tools and context. |
| [MCP resource](./extend/mcp.md#supported-mcp-features) | Desktop app, CLI, IDE extension | Readable context exposed by an MCP server for Codex to inspect. |
| [MCP server](./extend/mcp.md#supported-mcp-features) | Desktop app, CLI, IDE extension | External tool or context provider exposed through MCP. |
| [MCP tool](./extend/mcp.md#supported-mcp-features) | Desktop app, CLI, IDE extension | Action exposed by an MCP server that Codex can call during a task. |
| [MDM](./enterprise/managed-configuration.md#macos-managed-preferences-mdm) | Enterprise | Mobile device management tooling for distributing device profiles and managed Codex settings. |
| [Memories](./customization/memories.md) | Desktop app, CLI, IDE extension | Locally stored context Codex can reuse across sessions. |
| [Model](./models.md) | Desktop app, CLI, IDE extension, Cloud, SDK | The AI model Codex uses for reasoning and tool work. |
| [Network access](./agent-approvals-security.md#network-access) | Desktop app, CLI, IDE extension, Cloud | Permission for commands or environments to reach the internet. |
| [Network policy](./agent-approvals-security.md#network-policy) | Desktop app, CLI, IDE extension | Domain-based allow and deny rules that constrain sandboxed outbound network traffic. |
| [Non-interactive mode](./non-interactive-mode.md) | CLI | CLI mode for running Codex from scripts or CI. |
| [Output schema](./non-interactive-mode.md#create-structured-outputs-with-a-schema) | CLI | JSON Schema passed to `codex exec` to constrain the final response. |
| [Permanent worktree](./environments/git-worktrees.md#codex-managed-and-permanent-worktrees) | Desktop app | A long-lived worktree kept as its own project. |
| [Permission profile](./permissions.md#define-and-select-a-profile) | Desktop app, CLI, IDE extension | Named least-privilege policy that combines filesystem and network rules for local command execution. |
| [Plan](https://developers.openai.com/codex/learn/best-practices#plan-first-for-difficult-tasks) | Desktop app, CLI, IDE extension, Cloud | Codex's proposed or tracked steps for completing a task. |
| [Plugin](./plugins.md) | Desktop app (ChatGPT Work, Codex), Web (ChatGPT Work), CLI | An installable bundle of capabilities, such as skills, connectors, and tools, distributed through the universal directory shared by ChatGPT and Codex. |
| [Plugin manifest](https://developers.openai.com/plugins/build/plugins#plugin-structure) | Plugin authoring | Plugin metadata file that identifies a plugin and points to bundled skills, connector mappings, MCP servers, hooks, and metadata. |
| [Prefix rule](./agent-configuration/rules.md#understand-the-rules-language) | Desktop app, CLI, IDE extension, Enterprise | Command-rule pattern that allows, prompts for, or forbids matching command prefixes. |
| [Profile](./config-file/config-advanced.md#profiles) | CLI, IDE extension | Named configuration preset for Codex. |
| [Progressive disclosure](./build-skills.md) | Desktop app, Web (ChatGPT Work), CLI, IDE extension | Loading skill details only when needed to preserve context. |
| [Project](./projects.md) | Desktop app | A group of related chats and shared sources, or a local folder used for file-based work. |
| [Prompt](./prompting.md) | Desktop app, CLI, IDE extension, Cloud, SDK | A question, instruction, or goal sent to ChatGPT or Codex. |
| [Pull request review](./code-review.md) | Desktop app, CLI, GitHub | Codex review of changes or feedback on a pull request. |
| [RBAC](./enterprise/roles-and-workspace-permissions.md) | Enterprise | Role-based access control for workspace permissions. |
| [Read-only mode](./sandboxing.md) | Desktop app, CLI, IDE extension | Mode where Codex can inspect but not modify without approval. |
| [Reasoning effort](./config-file/config-basic.md#reasoning-effort) | Desktop app, CLI, IDE extension, SDK | Setting that controls how much reasoning budget a model uses. |
| [Remote connection](./remote-connections.md) | Desktop app, Mobile | Connection that lets you access ChatGPT or Codex chats on another device through a connected host. |
| [requirements.toml](./config-file/config-reference.md#requirementstoml) | Enterprise | Admin-enforced requirements file for managed Codex setups. |
| [Review pane](./code-review.md) | Desktop app | Desktop app view for inspecting diffs, comments, and Git changes. |
| [Rules](./agent-configuration/rules.md) | Desktop app, CLI, IDE extension | Policies that allow, prompt for, or deny command prefixes or permission exceptions. |
| [Sandbox](./sandboxing.md) | Desktop app, CLI, IDE extension | Enforced boundary limiting what Codex commands can access or modify. |
| [Sandbox mode](./config-file/config-basic.md#sandbox-level) | Desktop app, CLI, IDE extension | Configuration that defines Codex's filesystem and network limits. |
| [Sandbox preset](./codex-sdk.md#sandbox-presets) | SDK | SDK shorthand for common sandbox policies such as read-only, workspace-write, or full access. |
| [Schedule](./automations.md) | Desktop app | The timing rule for a scheduled task. |
| [Secret](./environments/cloud-environment.md#environment-variables-and-secrets) | Cloud | Encrypted value available to setup scripts but removed before the agent phase. |
| [Setup script](./environments/local-environment.md#setup-scripts) | Desktop app worktrees | Script run before the agent starts to install dependencies or prepare tools. |
| [Skill](./build-skills.md) | Desktop app, Web (ChatGPT Work), CLI, IDE extension | Reusable workflow package with instructions and optional scripts or references. |
| [Skill invocation](./build-skills.md#how-codex-uses-skills) | Desktop app, Web (ChatGPT Work), CLI, IDE extension | Explicit or implicit activation of a skill. |
| [Slash command](./developer-commands.md) | CLI | Command entered with a leading slash to control or inspect a Codex CLI session. |
| [Standalone scheduled task](./automations.md) | Desktop app, Web | Scheduled task whose runs each start a new chat and report findings in Triage. |
| [STDIO MCP server](./extend/mcp.md#stdio-servers) | CLI, IDE extension | MCP server launched as a local process by a configured command and arguments. |
| [Streamable HTTP MCP server](./extend/mcp.md#streamable-http-servers) | CLI, IDE extension | MCP server reached over HTTP, optionally with bearer token or OAuth authentication. |
| [Subagent](./agent-configuration/subagents.md) | Desktop app, CLI | Specialized child agent spawned to work on part of a task. |
| [Subagent workflow](./agent-configuration/subagents.md#core-terms) | Desktop app, CLI | Workflow where Codex runs delegated agents in parallel and combines their results. |
| [Standalone task](./projects.md) | Desktop app, CLI, IDE extension, Cloud | A Codex task that isn't grouped within a project. |
| [Task](./projects.md) | Desktop app, Web, Mobile, CLI, IDE extension, Cloud | A defined outcome ChatGPT or Codex works toward, such as fixing a bug, creating a document, or researching a topic. |
| [Thread](./app-server.md#threads) | App-server, SDK | A technical object in Codex app-server APIs that contains turns and stored conversation history. |
| [Scheduled task in a chat](./automations.md#schedule-a-task-inside-a-chat) | Desktop app, Web | A scheduled task that uses an existing chat's context and returns each run's results to that chat. |
| [Thread fork](./app-server.md#start-or-resume-a-thread) | App-server, SDK | New thread branched from the stored history of an existing thread. |
| [Turn](./app-server.md#core-primitives) | Desktop app, CLI, IDE extension, Cloud, SDK | One exchange in a chat, usually a user prompt plus the agent's response and actions. |
| [Universal image](./environments/cloud-environment.md#default-universal-image) | Cloud | Default Codex cloud container image with common tools preinstalled. |
| [Web search cache](./config-file/config-basic.md#web-search-mode) | Desktop app, CLI, IDE extension | Pre-indexed search results Codex can use without live browsing. |
| [ChatGPT Work](./get-started-with-work.md) | Desktop app, Web | The agent in ChatGPT for research, analysis, and creating documents, presentations, spreadsheets, and other finished work. |
| [Worktree](./environments/git-worktrees.md) | Desktop app | Mode where Codex isolates changes in a separate Git worktree. |
| [Writable roots](./agent-approvals-security.md#protected-paths-in-writable-roots) | Desktop app, CLI, IDE extension | Directories Codex is allowed to modify. |