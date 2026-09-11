# Pricing

> For the complete documentation index, see [llms.txt](https://learn.chatgpt.com/llms.txt). Markdown versions of documentation pages are available by appending `.md` to the page URL.

**ChatGPT Work and Codex share usage.** ChatGPT Work usage inside
  ChatGPT uses the same pricing, credits, and usage limits as Codex.

<h2 class="sr-only">Pricing options</h2>

### Free ($0/month)

Explore Codex capabilities on quick coding tasks.

[Get Free](https://chatgpt.com/plans/free/)
### Go ($8/month)

Use Codex for lightweight coding tasks.

[Get Go](https://chatgpt.com/plans/go)
### Plus ($20/month)

Power a few focused coding sessions each week.

[Get Plus](https://chatgpt.com/explore/plus?utm_internal_source=openai_developers_codex)

- Codex on the web, in the CLI, in the IDE extension, and on iOS
- Cloud-based integrations like automatic code review and Slack
  integration
- The GPT-5.6 model family, including Sol, Terra, and Luna
- GPT-5.6 Luna for higher usage limits on lighter-weight or high-volume
  workloads
- Flexibly extend usage with [ChatGPT credits](#credits-overview)
- Other [ChatGPT features](https://chatgpt.com/pricing) as part of the
  Plus plan
### Pro ($100/month)

Choose 5x or 20x higher rate limits than Plus.

[Get Pro](https://chatgpt.com/explore/pro?utm_internal_source=openai_developers_codex)

- Access to GPT-5.3-Codex-Spark (research preview), a fast Codex model
  for day-to-day coding tasks
- 5x or 20x more Codex usage than Plus*
- Unlimited ChatGPT Voice on the $200/month tier; tasks still draw from
  your Codex usage budget
- Other [ChatGPT features](https://chatgpt.com/pricing) as part of the
  Pro plan
### API Key

Great for automation in shared environments like CI.

[Learn more](./auth.md)

- Codex in the CLI, SDK, or IDE extension
- No cloud-based features (GitHub code review, Slack, etc.)
- Model availability follows the API models available to your key
- Pay for Codex usage based on [API pricing](https://developers.openai.com/api/docs/pricing)

### Business ($20/ user / month*)

Bring Codex into your startup or growing business.

[Get Business](https://chatgpt.com/team-sign-up)

- Access ChatGPT and Codex across desktop and mobile apps
- Larger virtual machines to run cloud chats faster
- Flexibly extend usage with [ChatGPT credits](#credits-overview)
- A secure, dedicated workspace with essential admin controls, SAML SSO,
  and MFA
- No training on your business data by default. [Learn
  more](https://openai.com/business-data/)
- Other [ChatGPT features](https://chatgpt.com/pricing) as part of the
  Business plan
### Enterprise & Edu

Unlock Codex for your entire organization with enterprise-grade functionality.

[Contact sales](https://chatgpt.com/contact-sales?utm_internal_source=openai_developers_codex)

- Priority request processing
- Enterprise-level security and controls, including SCIM, EKM, user
  analytics, domain verification, and role-based access control
  ([RBAC](https://help.openai.com/en/articles/11750701-rbac))
- Audit logs and usage monitoring via the [Compliance
  API](https://chatgpt.com/public/admin/api-reference#tag/Codex%20Tasks)
- Data retention and data residency controls
- Other [ChatGPT features](https://chatgpt.com/pricing) as part of the
  Enterprise plan

### API Key

Great for automation in shared environments like CI.

[Learn more](./auth.md)

- Codex in the CLI, SDK, or IDE extension
- No cloud-based features (GitHub code review, Slack, etc.)
- Model availability follows the API models available to your key
- Pay for Codex usage based on [API pricing](https://developers.openai.com/api/docs/pricing)

## Invite friends and coworkers

Eligible users can send Codex invitations from the profile menu in the
lower-left corner of the app. Choose **Invite a friend** on an eligible personal
plan or **Invite a coworker** in an eligible Business workspace, enter the
recipient's email address, and send the invitation.

The invitation dialog shows the current reward, recipient requirements, invite
limits, and when rewards expire for your plan or promotion. Personal and
Business referral programs have separate rewards and eligibility rules.
Referrals aren't currently available for ChatGPT Enterprise.

From June 11 through June 24, 2026, eligible Plus and Pro users can invite up to
three friends. When an eligible recipient sends their first Codex message, both
people receive a banked rate-limit reset. Banked rate-limit resets are usable for
30 days after they're granted. Business referrals use separate shared-workspace
credit rewards; review the
[current terms](https://help.openai.com/en/articles/20001271) before you send an
invitation.

## Frequently asked questions

### How much does Sites cost?

[Sites](./sites.md) is included with eligible ChatGPT plans during public
beta. Availability depends on your plan, region, and workspace settings.

### What are the usage limits for my plan?

The number of messages you can send depends on the model used, size and
complexity of your tasks, and whether you run them locally or in the cloud.
Small scripts or routine functions may consume only a fraction of your
allowance, while larger projects, long-running tasks, or extended sessions that
require the agent to hold more context will use significantly more per message.

Tasks that look similar can consume different amounts of your allowance. Model
choice, context, reasoning, tool use, retrieval, and caching all affect usage,
so prompt length alone isn't a reliable estimate.

Choose the GPT-5.6 model that best fits your work:

- **Sol** is built for the hardest work—complex reasoning, ambiguous problems,
  advanced coding, and high-stakes decisions.
- **Terra** is the everyday workhorse for production tasks, reporting, document
  analysis, coding, and work that requires sound judgment.
- **Luna** is optimized for fast, high-volume work such as routing,
  classification, extraction, support, background automation, and focused coding
  tasks.

The estimates below show local messages per five-hour period. Cloud chats on
ChatGPT plans use GPT-5.6 Sol and may use more of your allowance than local
messages. These estimates are not fixed message limits; check your
[usage dashboard](#where-can-i-see-my-current-usage-limits) for current limits
and reset times.

| Model | Plus | Pro 5x | Pro 20x | Standard Business | API Key |
| --- | :---: | :---: | :---: | :---: | :---: |
| GPT-6 Astra | 5-45 | 25-225 | 100-900 | 5-45 | [Usage-based](https://platform.openai.com/docs/pricing) |
| GPT-5.6 Sol | 10-100 | 50-500 | 200-2,000 | 10-100 | [Usage-based](https://platform.openai.com/docs/pricing) |
| GPT-5.6 Terra | 25-200 | 125-1,000 | 500-4,000 | 25-200 | [Usage-based](https://platform.openai.com/docs/pricing) |
| GPT-5.6 Luna | 250-2,000 | 1,250-10,000 | 5,000-40,000 | 250-2,000 | [Usage-based](https://platform.openai.com/docs/pricing) |
| GPT-5.5 | 15-80 | 75-400 | 300-1,600 | 15-80 | [Usage-based](https://platform.openai.com/docs/pricing) |
| GPT-5.4 | 20-100 | 100-500 | 400-2,000 | 20-100 | [Usage-based](https://platform.openai.com/docs/pricing) |
| GPT-5.4 mini | 60-350 | 300-1,750 | 1,200-7,000 | 60-350 | [Usage-based](https://platform.openai.com/docs/pricing) |
| Local messages and cloud chats share your plan's usage allowance. Weekly limits may also apply. |  |  |  |  |  |
| For Enterprise/Edu users with flexible pricing, there are no fixed rate limits—usage scales with [credits](#credits-overview). |  |  |  |  |  |
| Enterprise and Edu plans without flexible pricing have the same per-seat usage limits as Plus for most features. |  |  |  |  |  |

Business ($100) uses the Pro 5x estimates.

Usage limits are shared with other agentic features once pricing for those
features is effective. This currently includes [ChatGPT for
Excel](https://help.openai.com/articles/20001063) on Plus and Pro.

Speed configurations increase credit consumption for all applicable models, so
they also use included limits faster. Fast mode consumes credits at a higher
rate for supported models. See [Speed](./agent-configuration/speed.md) for supported models and
rates. Image generations also use included limits ~3-5x faster on average,
depending on image quality and size. GPT-5.3-Codex-Spark is in research preview
for ChatGPT Pro users only, and isn't available in the API at launch. Because it
runs on specialized low-latency hardware, usage is governed by a separate usage
limit that may adjust based on demand.

### ChatGPT Voice in Desktop

ChatGPT Voice on desktop uses a separate, plan-dependent allowance measured in
rolling five-hour windows. Tasks started through Voice use your existing Codex
usage budget. ChatGPT notifies you when you reach either limit.

GPT-Live manages the live conversation. When you use Voice in an existing
Codex task, the task's selected model handles the work. See
[ChatGPT Voice](./features/voice.md#start-talking) for availability and setup.

- **Plus:** Approximately 15–30 minutes
- **Pro 5x ($100/month):** Approximately 1–2.5 hours
- **Pro 20x ($200/month):** Unlimited voice access
- **Business:** Approximately 45 minutes
- **Enterprise / Edu (legacy):** Approximately 45 minutes

Unlimited voice access doesn't make Codex tasks unlimited. Tasks started through
ChatGPT Voice continue to use your existing Codex usage budget.

For Business, Edu, and Enterprise workspaces with credit-based or pay-as-you-go
billing, Desktop voice costs approximately 6 credits per minute. ChatGPT Voice
in Desktop is not available via API Key currently.

### What happens when you hit usage limits?

We want you to be able to complete work already in progress. If you reach your
usage limits during an active turn, the agent will be able to continue working
on that turn, subject to fair use limits.

ChatGPT Plus and Pro users who reach their usage limit can purchase additional
credits to continue working without needing to upgrade their existing plan.

Business, Edu, and Enterprise plans with [flexible
pricing](https://help.openai.com/en/articles/11487671-flexible-pricing-for-the-enterprise-edu-and-business-plans)
can purchase additional workspace credits to continue working.

If you are approaching usage limits, you can also switch to a smaller model to
make your usage limits last longer.

All users may also run extra local chats using an API key, with usage charged at
[standard API rates](https://platform.openai.com/docs/pricing).

<a id="image-generation-usage-limits"></a>

### How does image generation count toward usage limits?

Image generation counts toward the same general usage limits as local
messages and cloud chats. Image generations use included limits 3-5x faster on
average than similar turns without image generation, depending on
image quality and size. After you reach your included limits, image generation
also draws from [credits](#credits-overview).

Image generation isn't available on the Free plan. When you use Codex with an
API key, API pricing applies to image generation instead of included ChatGPT
usage limits.

### Where can I see my current usage limits?

You can find your current limits in the [usage
dashboard](https://chatgpt.com/codex/settings/usage). If you want to see your
remaining limits during an active Codex CLI session, you can use `/status`.

Check the dashboard every week or two to understand your pace and remaining
capacity. If usage is higher than expected, consider whether a smaller model or
tighter task scope would still produce a useful result.

### What are tokens and credits?

Tokens are small units of information that ChatGPT reads and writes. Your
prompt, files, chat history, tool results, and ChatGPT's response all
use tokens.

Credits are the unit used to pay for eligible usage on credit-based plans.
After you reach your included limits, available credits let you continue
working. Credit purchase prices and applicable discounts depend on your plan
or agreement.

#### Token rates

The token rates below are quoted in credits per million input tokens, cached
input tokens, and output tokens. [Learn more about
tokens](https://help.openai.com/en/articles/4936856-what-are-tokens-and-how-to-count-them).

Fast mode applies a 2.5x multiplier to Astra's Standard rate.

A small subset of Enterprise customers should continue using the legacy rate
card until we migrate you to the new token-based pricing. For more information,
[contact OpenAI
sales](https://chatgpt.com/contact-sales?utm_internal_source=openai_developers_codex).

  <table>
    <thead>
      <tr>
        <th scope="col">Credits per 1M tokens</th>
        <th scope="col" style="text-align:center">
          Input Tokens
        </th>
        <th scope="col" style="text-align:center">
          Cached input tokens
        </th>
        <th scope="col" style="text-align:center">
          Output Tokens
        </th>
      </tr>
    </thead>
    <tbody>
      <tr>
        <td>GPT-6 Astra</td>
        <td style="text-align:center">250 credits</td>
        <td style="text-align:center">25 credits</td>
        <td style="text-align:center">1,250 credits</td>
      </tr>
      <tr>
        <td>GPT-5.6 Sol</td>
        <td style="text-align:center">100 credits</td>
        <td style="text-align:center">10 credits</td>
        <td style="text-align:center">500 credits</td>
      </tr>
      <tr>
        <td>Daybreak Blue</td>
        <td style="text-align:center">100 credits</td>
        <td style="text-align:center">10 credits</td>
        <td style="text-align:center">500 credits</td>
      </tr>
      <tr>
        <td>Daybreak Red</td>
        <td style="text-align:center">312.5 credits</td>
        <td style="text-align:center">31.25 credits</td>
        <td style="text-align:center">1875 credits</td>
      </tr>
      <tr>
        <td>GPT-5.6 Terra</td>
        <td style="text-align:center">50 credits</td>
        <td style="text-align:center">5 credits</td>
        <td style="text-align:center">300 credits</td>
      </tr>
      <tr>
        <td>GPT-5.6 Luna</td>
        <td style="text-align:center">5 credits</td>
        <td style="text-align:center">0.5 credits</td>
        <td style="text-align:center">30 credits</td>
      </tr>
      <tr>
        <td>GPT-5.5</td>
        <td style="text-align:center">125 credits</td>
        <td style="text-align:center">12.50 credits</td>
        <td style="text-align:center">750 credits</td>
      </tr>
      <tr>
        <td>GPT-5.4</td>
        <td style="text-align:center">62.50 credits</td>
        <td style="text-align:center">6.250 credits</td>
        <td style="text-align:center">375 credits</td>
      </tr>
      <tr>
        <td>GPT-5.4 mini</td>
        <td style="text-align:center">18.75 credits</td>
        <td style="text-align:center">1.875 credits</td>
        <td style="text-align:center">113 credits</td>
      </tr>
      <tr>
        <td>GPT-5.3-Codex-Spark</td>
        <td colspan="3" style="text-align:center">
          research preview
        </td>
      </tr>
      <tr>
        <td>GPT-Image-2 (image)</td>
        <td style="text-align:center">200 credits</td>
        <td style="text-align:center">50 credits</td>
        <td style="text-align:center">750 credits</td>
      </tr>
      <tr>
        <td>GPT-Image-2 (text)</td>
        <td style="text-align:center">125 credits</td>
        <td style="text-align:center">31.25 credits</td>
        <td style="text-align:center">250 credits</td>
      </tr>
    </tbody>
    <tfoot>
      <tr>
        <td colspan="4" style="text-align:center">
          GPT-5.6 usage averages 5-30 credits per message.
        </td>
      </tr>
      <tr>
        <td colspan="4" style="text-align:center">
          Fast mode consumes credits at a higher rate for supported models. See
          [Speed](./agent-configuration/speed.md) for rates.
        </td>
      </tr>
      <tr>
        <td colspan="4" style="text-align:center">
          Daybreak access requires [Trusted Access for
          Cyber](./cyber-safety.md#trusted-access-for-cyber) approval.
          Daybreak Blue uses GPT-5.6 Sol credit rates. Daybreak Red requires
          separate approval and provisioning.
        </td>
      </tr>
    </tfoot>
  </table>

_GPT-5.6 Sol’s promotional pricing is available at least through November 21, 2026._

Speed configurations will increase credit consumption for all models that apply.
Fast mode consumes credits at a higher rate for supported models. See
[Speed](./agent-configuration/speed.md) for supported models and rates.

[Learn more about credits in ChatGPT Plus and
Pro.](https://help.openai.com/en/articles/12642688)

[Learn more about credits in ChatGPT Business, Enterprise, and
Edu.](https://help.openai.com/en/articles/11487671-flexible-pricing-for-the-enterprise-edu-and-business-plans)

For Business and Enterprise/Edu credit billing, use the [credit-based rate card](https://help.openai.com/en/articles/11481834-chatgpt-rate-card-business-enterpriseedu-credit-based-pricing). If your Enterprise agreement specifies usage-based billing in USD, use the [Enterprise USD rate card](https://help.openai.com/en/articles/20001415-chatgpt-rate-card-enterprise-token-based-pricing) and your agreement instead. Workspace administrators can also review [ChatGPT Work usage and cost](./enterprise/chatgpt-work-usage-and-cost.md#understand-tokens-and-credits).

### What counts as Code Review usage?

Code Review usage applies only when Codex runs reviews through GitHub—for
example, when you tag `@Codex` for review in a pull request or enable automatic
reviews on your repository. Reviews run locally or outside of GitHub count
toward your general usage limits.

### What can I do to make my usage limits last longer?

The usage limits and credits above are average rates. You can try the following
tips to maximize your limits:

- **Control the size of your prompts.** Be precise with the instructions you
  give the agent, but remove unnecessary context.
- **Limit source material.** Provide only relevant files and, when possible,
  narrow the sources or date range.
- **Match the output to the need.** Define the audience, format, and length, and
  separate required work from optional improvements.
- **Reduce the size of your AGENTS.md.** If you work on a larger project, you
  can control how much context you inject through AGENTS.md files by [nesting
  them within your repository](./agent-configuration/agents-md.md#layer-project-instructions).
- **Limit the number of MCP servers you use.** Every
  [MCP](./extend/mcp.md) server adds more context to your messages and uses
  more of your limit. Disable MCP servers when you don’t need them.
- **Switch to a smaller model for routine tasks.** Using GPT-5.6 Terra or
  GPT-5.6 Luna can extend your local-message usage limits, depending on the
  model you switch from.

For guidance on choosing and scoping tasks, see [Use Work
efficiently](./prompting.md#use-work-efficiently).

## Feature availability

### Access and surfaces

| Feature | ChatGPT Plus | ChatGPT Pro | ChatGPT Business | Enterprise / Education | API Key |
| --- | --- | --- | --- | --- | --- |
| [Codex cloud](./cloud.md) | Yes | Yes | Yes | Yes | No |
| [ChatGPT Work on the web](./get-started-with-work.md) | Yes | Yes | Yes | Yes | No |
| [ChatGPT desktop app for local chats](./app.md) | Yes | Yes | Yes | Yes | Yes |
| [Codex CLI](https://developers.openai.com/codex/cli) | Yes | Yes | Yes | Yes | Yes |
| [IDE extension](https://developers.openai.com/codex/ide) | Yes | Yes | Yes | Yes | Yes |
| [Codex SDK, `codex exec`, and scriptable workflows](./codex-sdk.md) | Yes | Yes | Yes | Yes | Yes |
| [Codex access tokens for trusted automation](./enterprise/access-tokens.md) | No | No | Yes | Yes | No |
| [ChatGPT for Excel](https://help.openai.com/articles/20001063) | Yes | Yes | Yes | Yes | No |
### Models and multimodal

| Feature | ChatGPT Plus | ChatGPT Pro | ChatGPT Business | Enterprise / Education | API Key |
| --- | --- | --- | --- | --- | --- |
| [GPT-5.6](./models.md) | Yes | Yes | Yes | Yes | Yes |
| [Fast mode](./agent-configuration/speed.md) | Yes | Yes | Yes | Yes | Yes |
| [Codex-Spark research preview](./models.md) | No | Yes | No | No | No |
| [Image generation and editing](./image-generation.md) | Yes | Yes | Yes | Yes | Yes |
| [Voice dictation](./prompting.md#use-voice-dictation) | Yes | Yes | Yes | Yes | No |
| [ChatGPT Voice](./features/voice.md) | Yes | Yes | Yes | Yes | No |
| [Web search](./web-search.md) | Yes | Yes | Yes | Yes | Yes |
### Local features

| Feature | ChatGPT Plus | ChatGPT Pro | ChatGPT Business | Enterprise / Education | API Key |
| --- | --- | --- | --- | --- | --- |
| [Local code review with `/review`](./prompting.md#do-a-local-code-review) | Yes | Yes | Yes | Yes | Yes |
| [Auto-review for approval requests](./sandboxing/auto-review.md) | Yes | Yes | Yes | Yes | Yes |
| [Sandboxing and permission controls](./permissions.md) | Yes | Yes | Yes | Yes | Yes |
| [Project and standalone scheduled tasks](./automations.md) | Yes | Yes | Yes | Yes | Yes |
| [Scheduled tasks](./automations.md) | Yes | Yes | Yes | Yes | Yes |
| [Worktrees and built-in Git tools](./environments/git-worktrees.md) | Yes | Yes | Yes | Yes | Yes |
| [Local environments and repeatable actions](./environments/local-environment.md) | Yes | Yes | Yes | Yes | Yes |
| [Appshots](./appshots.md) | Yes | Yes | Yes | No | Yes |
### Browser and remote control

| Feature | ChatGPT Plus | ChatGPT Pro | ChatGPT Business | Enterprise / Education | API Key |
| --- | --- | --- | --- | --- | --- |
| [Built-in browser previews and comments](./browser.md) | Yes | Yes | Yes | Yes | Yes |
| [Computer Use in the browser](./browser.md) | Limited | Limited | Limited | Limited | Limited |
| [Use ChatGPT with Chrome](./chrome-extension.md) | Limited | Limited | Limited | Limited | Limited |
| [Computer Use](./computer-use.md) | Limited | Limited | Limited | Limited | Limited |
| [Record & Replay (macOS)](./extend/record-and-replay.md) | Limited | Limited | Limited | Limited | Limited |
| [SSH remote connections](./remote-connections.md#connect-to-an-ssh-host) | Yes | Yes | Yes | Yes | Yes |
| [Mobile remote control](./remote-connections.md) | Yes | Yes | Yes | Yes | No |
| [Browser in ChatGPT Web](./browser.md) | Yes | Yes | Yes | Yes | No |
### Customization and extensions

| Feature | ChatGPT Plus | ChatGPT Pro | ChatGPT Business | Enterprise / Education | API Key |
| --- | --- | --- | --- | --- | --- |
| [Custom instructions with `AGENTS.md`](./agent-configuration/agents-md.md) | Yes | Yes | Yes | Yes | Yes |
| [Skills](./build-skills.md) | Yes | Yes | Yes | Yes | Yes |
| [Plugins](./plugins.md) | Yes | Yes | Yes | Yes | Limited |
| [Plugin sharing](https://developers.openai.com/plugins/build/plugins#share-a-local-plugin-with-your-workspace) | Yes | Yes | Yes | Yes | No |
| [Connectors](./plugins.md) | Yes | Yes | Yes | Yes | No |
| [MCP](./extend/mcp.md) | Yes | Yes | Yes | Yes | Yes |
| [Subagents and custom agents](./agent-configuration/subagents.md) | Yes | Yes | Yes | Yes | Yes |
| [Memories](./customization/memories.md) | Limited | Limited | Limited | Limited | Limited |
| [Computer History](./customization/computer-history.md) | No | Yes | Yes | Yes | No |
### Cloud and integrations

| Feature | ChatGPT Plus | ChatGPT Pro | ChatGPT Business | Enterprise / Education | API Key |
| --- | --- | --- | --- | --- | --- |
| [Codex cloud chats](./cloud.md) | Yes | Yes | Yes | Yes | No |
| [Cloud environments and setup scripts](./environments/cloud-environment.md) | Yes | Yes | Yes | Yes | No |
| [Cloud agent internet access controls](./cloud/internet-access.md) | Yes | Yes | Yes | Yes | No |
| [Sites](./sites.md) | No | No | Yes | Yes | No |
| [GitHub issue and PR delegation with `@codex`](./third-party/github.md#give-codex-other-tasks) | Yes | Yes | Yes | Yes | No |
| [GitHub code review and automatic PR reviews](./third-party/github.md) | Yes | Yes | Yes | Yes | No |
| [Slack cloud integration](./third-party/slack.md) | Yes | Yes | Yes | Yes | No |
| [Linear cloud integration](./third-party/linear.md) | Yes | Yes | Yes | Yes | No |
### Admin, security, and analytics

| Feature | ChatGPT Plus | ChatGPT Pro | ChatGPT Business | Enterprise / Education | API Key |
| --- | --- | --- | --- | --- | --- |
| [SAML SSO, MFA, and workspace user management](./enterprise/admin-setup.md) | No | No | Yes | Yes | No |
| [`requirements.toml` managed config](./enterprise/managed-configuration.md) | Yes | Yes | Yes | Yes | Yes |
| [Cloud-managed config policies](./enterprise/managed-configuration.md#cloud-managed-requirements) | No | No | Yes | Yes | No |
| [ChatGPT workspace RBAC and custom roles](./enterprise/roles-and-workspace-permissions.md) | No | No | No | Yes | No |
| [SCIM, EKM, and domain verification](./enterprise/admin-setup.md#enterprise-grade-security-and-privacy) | No | No | No | Yes | No |
| [Enterprise retention and residency controls](./enterprise/admin-setup.md#enterprise-grade-security-and-privacy) | No | No | No | Yes | No |
| [No training on API or business data by default](https://openai.com/business-data/) | No | No | Yes | Yes | Yes |
| [Analytics dashboard](./enterprise/workspace-analytics.md) | No | No | No | Yes | No |
| [Analytics API](./enterprise/analytics-api.md) | No | No | No | Yes | No |
| [Compliance API and audit logs](./enterprise/compliance-api.md) | No | No | No | Yes | No |
| [Codex Security for connected GitHub repositories](./security.md) | No | No | No | Yes | No |

<div
  id="codex-plan-region-limits"
  className="not-prose mt-3 text-sm text-secondary"
>
  <sup>*</sup> Feature is currently limited to only specific regions. Check the
  individual feature documentation to learn more about geo restrictions.

<div
  id="codex-plan-plugin-limits"
  className="not-prose mt-1 text-sm text-secondary"
>
  <sup>†</sup> Some first party plugins are not available.