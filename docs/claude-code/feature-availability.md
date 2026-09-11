> ## Documentation Index
> Fetch the complete documentation index at: https://code.claude.com/docs/llms.txt
> Use this file to discover all available pages before exploring further.

# Feature availability

> Compare which Claude Code features are available across Anthropic subscription plans, the Anthropic Console, Amazon Bedrock, Claude Platform on AWS, Google Cloud's Agent Platform, and Microsoft Foundry.

The Claude Code CLI and everything that runs locally work on every provider. For setup instructions per provider, see the [Enterprise deployment overview](./third-party-integrations.md). To skip straight to what is missing on your provider, see the [summary by provider](#summary-by-provider) tabs.

In the tables below, ✓ means available, ✗ means not available, and "See note" links to a footnote for partial support. A qualifier after ✓ narrows availability to that subset, and "Admin-enabled" means the feature is off until an organization admin turns it on.

## Availability by model provider

How you authenticate determines which features Claude Code can reach. For a single list of what is missing on your provider, see the [summary by provider](#summary-by-provider) tabs. To find your column in the tables:

* **Claude subscription**: you sign in with a claude.ai account on the Pro, Max, Team, or Enterprise plan
* **Anthropic Console**: you authenticate with an Anthropic API key or by [signing in to a Console account without one](./authentication.md#sign-in-without-an-api-key)
* **Amazon Bedrock**: you use Claude models from the Amazon Bedrock model catalog and set `CLAUDE_CODE_USE_BEDROCK`. The [Mantle endpoint](./amazon-bedrock.md#use-the-mantle-endpoint) (`CLAUDE_CODE_USE_MANTLE`) is covered by this column
* **Claude Platform on AWS**: you bought Claude through AWS Marketplace but call the Anthropic API, and set `CLAUDE_CODE_USE_ANTHROPIC_AWS`
* **Google Cloud's Agent Platform**: Google-operated; you set `CLAUDE_CODE_USE_VERTEX`
* **Microsoft Foundry**: Anthropic-operated; you set `CLAUDE_CODE_USE_FOUNDRY`

### Features available on every provider

These work on every provider:

* [CLI](./quickstart.md) and [Agent SDK](./agent-sdk/overview.md)
* [VS Code](./vs-code.md) and [JetBrains](./jetbrains.md) extensions
* [Subagents](./sub-agents.md), [hooks](./hooks-guide.md), [commands](./commands.md), and [skills](./skills.md)
* [CLAUDE.md memory](./memory.md), [plugins](./plugins.md), and [MCP servers](./mcp.md)
* [Checkpoints](./checkpointing.md), [sandboxing](./sandboxing.md), and [Workflows](./workflows.md)
* [OpenTelemetry metrics](./monitoring-usage.md) and the [managed settings file](./managed-settings.md#delivery-mechanisms)

Three of these have provider-specific differences:

* **MCP servers**: [connectors from claude.ai](./mcp.md#use-mcp-servers-from-claude-ai) load only when your claude.ai subscription is the active authentication method. [Tool search](./mcp.md#configure-tool-search) is off by default when `ANTHROPIC_BASE_URL` points to a non-first-party host, and isn't supported on Google Cloud's Agent Platform models earlier than the Claude 4.5 generation or on Microsoft Foundry [deployments hosted on Azure](https://platform.claude.com/docs/en/build-with-claude/claude-in-microsoft-foundry#hosting-options)
* **Subagents**: the built-in [Explore subagent](./sub-agents.md#built-in-subagents) caps its inherited model at Opus on the Claude API, and inherits the main conversation's model directly on any other provider, including Claude Platform on AWS
* **[Commands](./commands.md#all-commands)**:
  * `/design-sync` and `/import` with its `claude import` subcommand form are unavailable on Amazon Bedrock, Google Cloud's Agent Platform, Microsoft Foundry, and Claude Platform on AWS
  * `/voice` requires a claude.ai account
  * `/list-agents` and its alias `/peers` are available only in sessions where [cross-session messaging is enabled](./cross-session-messaging.md#availability)

### Features that require a Claude subscription

These require signing in with a claude.ai account and are not reachable with an Anthropic Console API key or from a third-party provider:

* [Claude Code on the web](./claude-code-on-the-web.md), Claude Code on mobile, and [Claude Code in Slack](./slack.md)
* [Claude Code Desktop](./desktop.md)
* [Routines](./routines.md) (`/schedule`)
* [Ultrareview](./ultrareview.md)
* [Code Review](./code-review.md): Team and Enterprise plans
* [Remote Control](./remote-control.md)
* [Chrome extension](./chrome.md)
* [Computer use](./computer-use.md): Pro and Max plans
* [Artifacts](./artifacts.md): Pro, Max, Team, and Enterprise plans
* [Voice dictation](./voice-dictation.md)

Desktop is the partial exception: [gateway routing can be configured in the app or by an administrator](./llm-gateway-connect.md#desktop-app), Enterprise deployments can route Desktop to Google Cloud's Agent Platform or a gateway provider via [managed settings](https://claude.com/docs/third-party/claude-desktop/configuration), and [Claude Desktop on 3P](https://claude.com/docs/third-party/claude-desktop/overview) runs the Code tab on Amazon Bedrock, Google Cloud's Agent Platform, Microsoft Foundry, or a self-hosted LLM gateway. For per-plan availability of these features, see [Availability by subscription plan](#availability-by-subscription-plan).

### CLI capabilities that vary by provider

These features work in the local CLI but depend on a server-side capability that not every provider exposes.

<table>
  <thead>
    <tr>
      <th>Feature</th>
      <th>Claude subscription</th>
      <th>Anthropic Console</th>
      <th>Amazon Bedrock</th>
      <th>Claude Platform on AWS</th>
      <th>Google Cloud's Agent Platform</th>
      <th>Microsoft Foundry</th>
    </tr>
  </thead>

  <tbody>
    <tr>
      <td>[Web search](./tools-reference.md#websearch-tool-behavior)</td>
      <td>✓</td>
      <td>✓</td>
      <td>✗</td>
      <td>✓</td>
      <td>See note <sup><a href="#fn1">1</a></sup></td>
      <td>✓ ([deployments hosted on Anthropic](https://platform.claude.com/docs/en/build-with-claude/claude-in-microsoft-foundry#hosting-options))</td>
    </tr>

    <tr>
      <td>[Fast mode](./fast-mode.md)</td>
      <td>✓ ([Owner-enabled](./fast-mode.md#enable-fast-mode-for-your-organization) on Team and Enterprise)</td>
      <td>✓ (provisioned organizations)</td>
      <td>✗</td>
      <td>✗</td>
      <td>✗</td>
      <td>✗</td>
    </tr>

    <tr>
      <td>[Auto mode](./auto-mode-config.md)</td>
      <td>✓</td>
      <td>✓</td>
      <td>See note <sup><a href="#fn2">2</a></sup></td>
      <td>✓</td>
      <td>See note <sup><a href="#fn2">2</a></sup></td>
      <td>See note <sup><a href="#fn2">2</a></sup></td>
    </tr>

    <tr>
      <td>[Advisor](./advisor.md)</td>
      <td>✓</td>
      <td>✓</td>
      <td>✗</td>
      <td>✗</td>
      <td>✗</td>
      <td>✗</td>
    </tr>

    <tr>
      <td>[Cross-session messaging](./cross-session-messaging.md)</td>
      <td>✓ <sup><a href="#fn5">5</a></sup></td>
      <td>✓ (same machine) <sup><a href="#fn5">5</a></sup></td>
      <td>✓ (same machine) <sup><a href="#fn5">5</a></sup></td>
      <td>✓ (same machine) <sup><a href="#fn5">5</a></sup></td>
      <td>✓ (same machine) <sup><a href="#fn5">5</a></sup></td>
      <td>✓ (same machine) <sup><a href="#fn5">5</a></sup></td>
    </tr>

    <tr>
      <td>[Channels](./channels.md)</td>
      <td>✓</td>
      <td>✓</td>
      <td>✗</td>
      <td>✗</td>
      <td>✗</td>
      <td>✗</td>
    </tr>

    <tr>
      <td>[GitHub Actions](./github-actions.md)</td>
      <td>✓</td>
      <td>✓</td>
      <td>✓</td>
      <td>✗</td>
      <td>✓</td>
      <td>✓</td>
    </tr>

    <tr>
      <td>[GitLab CI/CD](./gitlab-ci-cd.md)</td>
      <td>✓</td>
      <td>✓</td>
      <td>✓</td>
      <td>✓</td>
      <td>✓</td>
      <td>✗</td>
    </tr>
  </tbody>
</table>

### Admin and analytics

Organization-level controls and usage visibility.

<table>
  <thead>
    <tr>
      <th>Feature</th>
      <th>Claude subscription</th>
      <th>Anthropic Console</th>
      <th>Amazon Bedrock</th>
      <th>Claude Platform on AWS</th>
      <th>Google Cloud's Agent Platform</th>
      <th>Microsoft Foundry</th>
    </tr>
  </thead>

  <tbody>
    <tr>
      <td>[Analytics dashboard and API](./analytics.md)</td>
      <td>✓ (dashboard: Team and Enterprise; API: Enterprise)</td>
      <td>✓ <sup><a href="#fn4">4</a></sup></td>
      <td>✗</td>
      <td>✗</td>
      <td>✗</td>
      <td>✗</td>
    </tr>

    <tr>
      <td>[Server-managed settings](./server-managed-settings.md)</td>
      <td>✓ (Team and Enterprise)</td>
      <td>✓ (Team and Enterprise)</td>
      <td>✗</td>
      <td>✗</td>
      <td>✗</td>
      <td>✗</td>
    </tr>

    <tr>
      <td>[Zero Data Retention](./zero-data-retention.md)</td>
      <td>✓ (qualified Enterprise accounts)</td>
      <td>✓ (qualified accounts)</td>
      <td>See note <sup><a href="#fn3">3</a></sup></td>
      <td>✓ (qualified accounts)</td>
      <td>See note <sup><a href="#fn3">3</a></sup></td>
      <td>See note <sup><a href="#fn3">3</a></sup></td>
    </tr>
  </tbody>
</table>

<a id="fn1"></a><sup>1</sup> On Google Cloud's Agent Platform, web search is available for Claude 4 models and later.<br />
<a id="fn2"></a><sup>2</sup> On these providers, auto mode supports only Claude Sonnet 5, Opus 4.7 or later, and the Fable models. See [Auto mode configuration](./auto-mode-config.md). The built-in starting permission mode on these providers is Manual. See [which mode a session starts in](./permission-modes.md#which-mode-a-session-starts-in). In v2.1.158 through v2.1.206, auto mode on these providers also required setting `CLAUDE_CODE_ENABLE_AUTO_MODE=1`; v2.1.207 removed the requirement.<br />
<a id="fn3"></a><sup>3</sup> Subject to your agreement with the cloud provider.<br />
<a id="fn4"></a><sup>4</sup> Dashboard and API only. [Contribution metrics](./analytics.md#enable-contribution-metrics) requires a claude.ai Team or Enterprise organization.<br />
<a id="fn5"></a><sup>5</sup> Requires Claude Code v2.1.224 or later on macOS and Linux, including Linux inside WSL 2. On native Windows, requires Claude Code v2.1.234 or later. With API key authentication, messaging is same-machine only. On Amazon Bedrock, Claude Platform on AWS, Google Cloud's Agent Platform, and Microsoft Foundry, messaging is same-machine only and requires Claude Code v2.1.248 or later. Claude can find your [Claude Code on the web](./claude-code-on-the-web.md) sessions and your sessions on other machines only from a session that is connected to [Remote Control](./remote-control.md). To connect, you need a claude.ai sign-in and the other [Remote Control requirements](./remote-control.md#requirements). See [Message sessions on other machines](./cross-session-messaging.md#message-sessions-on-other-machines).

> [!NOTE]
> If you authenticate through an [LLM gateway](./llm-gateway.md), feature availability matches the underlying provider the gateway forwards to, except for the features Claude Code itself turns off. Whenever `ANTHROPIC_BASE_URL` points at a host other than `api.anthropic.com`, Claude Code turns off features such as [Remote Control](./remote-control.md#requirements) and [server-managed settings](./server-managed-settings.md#platform-availability), whatever the gateway forwards. Some Anthropic-only features such as the [Advisor](./advisor.md) work only if the gateway forwards requests intact to the Anthropic API.

### Summary by provider

Each tab lists what is unavailable or partially supported on that provider, with alternatives where one exists. Everything not listed works the same as on a Claude subscription, apart from the [provider-specific differences](#features-available-on-every-provider) noted above. On Amazon Bedrock, Google Cloud's Agent Platform, Microsoft Foundry, and Claude Platform on AWS, error reporting and telemetry to Anthropic are off by default. See [default behaviors by API provider](./data-usage.md#default-behaviors-by-api-provider) for what traffic still reaches Anthropic and how to opt out.

**Amazon Bedrock**

**Not available:** all [features that require a Claude subscription](#features-that-require-a-claude-subscription), plus [web search](./tools-reference.md#websearch-tool-behavior), [fast mode](./fast-mode.md), [Advisor](./advisor.md), [Channels](./channels.md), the [analytics dashboard](./analytics.md), [server-managed settings](./server-managed-settings.md), and the [`/design-sync` and `/import` commands](./commands.md#all-commands).

**Partial support:**

* [Desktop](./desktop.md): only via [Claude Desktop on 3P](https://claude.com/docs/third-party/claude-desktop/overview)
* [Auto mode](./auto-mode-config.md): Sonnet 5, Opus 4.7 or later, and Fable models only
* [Cross-session messaging](./cross-session-messaging.md): between your sessions on this machine only <sup><a href="#fn5">5</a></sup>
* [Zero Data Retention](./zero-data-retention.md): subject to your AWS agreement

**Alternatives:** for scheduling, use [`/loop`](./scheduled-tasks.md) instead of `/schedule`. For cloud sessions, use [GitHub Actions](./github-actions.md) or [GitLab CI/CD](./gitlab-ci-cd.md). For web lookups, use the [WebFetch tool](./tools-reference.md#webfetch-tool-behavior) with a specific URL.

**Claude Platform on AWS**

**Not available:** all [features that require a Claude subscription](#features-that-require-a-claude-subscription), plus [fast mode](./fast-mode.md), [Advisor](./advisor.md), [Channels](./channels.md), [GitHub Actions](./github-actions.md), the [analytics dashboard](./analytics.md), [server-managed settings](./server-managed-settings.md), and the [`/design-sync` and `/import` commands](./commands.md#all-commands).

**Available where Amazon Bedrock is not:** [web search](./tools-reference.md#websearch-tool-behavior).

**Partial support:**

* [Cross-session messaging](./cross-session-messaging.md): between your sessions on this machine only <sup><a href="#fn5">5</a></sup>

**Alternatives:** for scheduling, use [`/loop`](./scheduled-tasks.md) instead of `/schedule`. For cloud sessions, use [GitLab CI/CD](./gitlab-ci-cd.md).

**Google Cloud's Agent Platform**

**Not available:** all [features that require a Claude subscription](#features-that-require-a-claude-subscription), plus [fast mode](./fast-mode.md), [Advisor](./advisor.md), [Channels](./channels.md), the [analytics dashboard](./analytics.md), [server-managed settings](./server-managed-settings.md), and the [`/design-sync` and `/import` commands](./commands.md#all-commands).

**Partial support:**

* [Desktop](./desktop.md): via [managed settings](https://claude.com/docs/third-party/claude-desktop/configuration) or [Claude Desktop on 3P](https://claude.com/docs/third-party/claude-desktop/overview)
* [Web search](./tools-reference.md#websearch-tool-behavior): Claude 4 models and later
* [Auto mode](./auto-mode-config.md): Sonnet 5, Opus 4.7 or later, and Fable models only
* [Cross-session messaging](./cross-session-messaging.md): between your sessions on this machine only <sup><a href="#fn5">5</a></sup>
* [Zero Data Retention](./zero-data-retention.md): subject to your Google Cloud agreement

**Alternatives:** for scheduling, use [`/loop`](./scheduled-tasks.md) instead of `/schedule`. For cloud sessions, use [GitHub Actions](./github-actions.md) or [GitLab CI/CD](./gitlab-ci-cd.md).

**Microsoft Foundry**

**Not available:** all [features that require a Claude subscription](#features-that-require-a-claude-subscription), plus [fast mode](./fast-mode.md), [Advisor](./advisor.md), [Channels](./channels.md), [GitLab CI/CD](./gitlab-ci-cd.md), the [analytics dashboard](./analytics.md), [server-managed settings](./server-managed-settings.md), and the [`/design-sync` and `/import` commands](./commands.md#all-commands).

**Partial support:**

* [Desktop](./desktop.md): only via [Claude Desktop on 3P](https://claude.com/docs/third-party/claude-desktop/overview)
* [Web search](./tools-reference.md#websearch-tool-behavior): [deployments hosted on Anthropic](https://platform.claude.com/docs/en/build-with-claude/claude-in-microsoft-foundry#hosting-options) only
* [Auto mode](./auto-mode-config.md): Sonnet 5, Opus 4.7 or later, and Fable models only
* [Cross-session messaging](./cross-session-messaging.md): between your sessions on this machine only <sup><a href="#fn5">5</a></sup>
* [Zero Data Retention](./zero-data-retention.md): subject to your Azure agreement

**Alternatives:** for scheduling, use [`/loop`](./scheduled-tasks.md) instead of `/schedule`. For cloud sessions, use [GitHub Actions](./github-actions.md).

**Anthropic Console**

**Not available:** all [features that require a Claude subscription](#features-that-require-a-claude-subscription).

Everything in [CLI capabilities that vary by provider](#cli-capabilities-that-vary-by-provider) is available, except that [fast mode](./fast-mode.md) requires [provisioned access](./fast-mode.md#enable-fast-mode-for-your-organization). [Server-managed settings](./server-managed-settings.md) are also available when your API key belongs to a Team or Enterprise organization.

## Availability by subscription plan

If you authenticate through Amazon Bedrock, Google Cloud's Agent Platform, Microsoft Foundry, or an Anthropic Console API key, this section does not apply to you. When you sign in with a claude.ai account, your plan determines which of the features below are available.

| Feature                                                                     | Pro | Max | Team          | Enterprise                        |
| :-------------------------------------------------------------------------- | :-- | :-- | :------------ | :-------------------------------- |
| [Claude Code on the web](./claude-code-on-the-web.md)                        | ✓   | ✓   | ✓             | ✓ <sup><a href="#fn6">6</a></sup> |
| [Routines](./routines.md)                                                    | ✓   | ✓   | ✓             | ✓                                 |
| [Remote Control](./remote-control.md)                                        | ✓   | ✓   | Admin-enabled | Admin-enabled                     |
| [Channels](./channels.md)                                                    | ✓   | ✓   | Admin-enabled | Admin-enabled                     |
| [Computer use](./computer-use.md)                                            | ✓   | ✓   | ✗             | ✗                                 |
| Dispatch ([Desktop](./desktop.md#sessions-from-dispatch))                    | ✓   | ✓   | ✗             | ✗                                 |
| [Code Review](./code-review.md)                                              | ✗   | ✗   | ✓             | ✓                                 |
| [Artifacts](./artifacts.md)                                                  | ✓   | ✓   | ✓             | Admin-enabled                     |
| [Analytics dashboard and contribution metrics](./analytics.md)               | ✗   | ✗   | ✓             | ✓                                 |
| [Enterprise Analytics API](./analytics.md#access-data-programmatically)      | ✗   | ✗   | ✗             | ✓                                 |
| [Server-managed settings](./server-managed-settings.md)                      | ✗   | ✗   | ✓             | ✓                                 |
| [SSO](https://support.claude.com/en/articles/9266767-what-is-the-team-plan) | ✗   | ✗   | ✓             | ✓                                 |
| SCIM                                                                        | ✗   | ✗   | ✗             | ✓                                 |
| [Compliance API](https://platform.claude.com/docs/en/api/compliance)        | ✗   | ✗   | ✗             | ✓                                 |
| [Zero Data Retention](./zero-data-retention.md)                              | ✗   | ✗   | ✗             | ✓ <sup><a href="#fn7">7</a></sup> |

<a id="fn6"></a><sup>6</sup> On Enterprise, requires a premium seat or a Chat + Claude Code seat. See [Claude Code on the web](./claude-code-on-the-web.md).<br />
<a id="fn7"></a><sup>7</sup> Not included in the standard Enterprise plan. Requires separate enablement by Anthropic for qualified accounts. See [Zero Data Retention](./zero-data-retention.md).

For pricing and the full plan comparison, see [Team plans](https://support.claude.com/en/articles/9266767-what-is-the-team-plan) and [Enterprise plans](https://support.claude.com/en/articles/9797531-what-is-the-enterprise-plan).

## Model availability

For which Claude models and context-window sizes are available per provider and region, see [Model configuration](./model-config.md) and the [Models overview](https://platform.claude.com/docs/en/about-claude/models/overview). Vision, PDF input, and extended thinking are model capabilities rather than Claude Code features and work on every provider that offers the model. [Prompt caching](./prompt-caching.md) works the same way on most providers; on Amazon Bedrock, support varies by model.

## Related resources

* [Enterprise deployment overview](./third-party-integrations.md): compare authentication, billing, and regions across providers
* Provider setup guides: [Amazon Bedrock](./amazon-bedrock.md), [Claude Platform on AWS](./claude-platform-on-aws.md), [Google Cloud's Agent Platform](./google-vertex-ai.md), [Microsoft Foundry](./microsoft-foundry.md)
* [Platforms and integrations](./platforms.md): where Claude Code runs, including the CLI, Desktop, IDE extensions, web, mobile, and CI/CD
