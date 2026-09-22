# Use ChatGPT Work and Codex with Amazon Bedrock

> For the complete documentation index, see [llms.txt](https://learn.chatgpt.com/llms.txt). Markdown versions of documentation pages are available by appending `.md` to the page URL.

Configure local ChatGPT Work and Codex surfaces to use OpenAI models available
through Amazon Bedrock. In this setup, the local client sends model requests to
Bedrock using AWS-managed authentication and access controls.

## How it works

When you configure a local ChatGPT Work or Codex surface with Amazon Bedrock as
the model provider, the OpenAI-hosted Responses API isn't in the request path.
The local client sends model requests to Amazon Bedrock, and Bedrock provides an
OpenAI-compatible Responses API implementation for supported OpenAI models.

Authentication is AWS-native. Users authenticate with a Bedrock API key or AWS
  IAM credentials. They do not use ChatGPT sign-in or `OPENAI_API_KEY` for this
  provider.

## Before you start

Make sure you have:

- Credentials for the AWS account you want to use
- Access to supported OpenAI models in Amazon Bedrock.
- Access to an AWS Region where the selected model is available.

## Configure the provider

Codex allows you to configure the provider by setting `model_provider` in `~/.codex/config.toml`. The ChatGPT desktop app, Codex CLI, IDE extension, and SDK read the same local configuration layers.

Choose the provider for the Amazon Bedrock endpoint you want to use: Bedrock
Runtime for cross-Region inference (CRIS), or Bedrock Mantle for in-Region inference.

For the Bedrock Runtime endpoint:

```toml
model_provider = "amazon-bedrock-runtime"
```

For the Bedrock Mantle endpoint:

```toml
model_provider = "amazon-bedrock"
```

### Choose a model

Codex uses the configured `model_provider` to choose which models appear in the
model picker: models supported through the Bedrock Runtime endpoint for
`amazon-bedrock-runtime`, or through the Bedrock Mantle endpoint for
`amazon-bedrock`.

You can optionally specify a [supported model](#supported-models) in the
configuration file.

Model availability varies by AWS Region. Refer to AWS [Regional availability by models](https://docs.aws.amazon.com/bedrock/latest/userguide/models-region-compatibility.html#model-regions-openai). Local ChatGPT Work and Codex surfaces don't support Bedrock Mantle endpoints in AWS GovCloud Regions.

## Authentication options

Local ChatGPT Work and Codex surfaces support two Bedrock authentication paths.
They check them in this order:

1. Bedrock API key.
2. AWS SDK credential chain.

### Option 1: Bedrock API key

Set the Bedrock API key in the environment the local client reads. You must
specify a Region when using API-key authentication.

```shell
export AWS_BEARER_TOKEN_BEDROCK=<your-bedrock-api-key>
export AWS_REGION=us-east-2
```

### Option 2: AWS SDK credentials

Use this path when your organization manages Bedrock access through the AWS SDK
credential chain. The local client can use these standard AWS SDK credential
sources:

#### Shared AWS configuration files

Configure the shared AWS `config` and `credentials` files:

```shell
aws configure
```

#### Environment variables

Set the standard AWS SDK credential environment variables:

```shell
export AWS_ACCESS_KEY_ID=<your-access-key-id>
export AWS_SECRET_ACCESS_KEY=<your-secret-access-key>
export AWS_SESSION_TOKEN=<your-session-token>
```

#### AWS Management Console credentials

Log in with AWS Management Console credentials:

```shell
aws login
```

#### AWS SSO or a named profile

Log in with AWS SSO and select the named profile:

```shell
aws sso login --profile codex-bedrock
export AWS_PROFILE=codex-bedrock
```

#### Federated identity

For corporate SSO or OIDC federation, configure a federated identity with
`credential_process` outside the local client and let the AWS SDK resolve
credentials. Put browser login, token exchange, caching, and refresh in your
AWS profile's `credential_process` helper.

## Desktop app and IDE extension

Desktop apps and IDE extensions may not inherit environment variables from the
shell. Put required values in `~/.codex/.env`, then restart the app or
extension.

```shell
export AWS_BEARER_TOKEN_BEDROCK=<your-bedrock-api-key>
export AWS_REGION=us-east-2
```

## Verify setup

- In Codex CLI, open `/status` and confirm the model provider matches your
  endpoint: `amazon-bedrock` for Mantle in-Region inference, or
  `amazon-bedrock-runtime` for Runtime Global or Geo cross-Region inference.
- In the ChatGPT desktop app, select Work or Codex and start a new task after
  restarting the app.
- In the IDE extension, start a new session after restarting the extension.
- Confirm the selected model is available in the configured AWS Region and that
  the AWS identity has permission to access it.

## Supported models

Use an inference profile ID for Bedrock Runtime provider or a model ID for Bedrock Mantle provider.
The selected model or profile must be available in your AWS Region and accessible to your
AWS identity.

### Global and Geo cross-Region inference using the Bedrock Runtime endpoint

Global CRIS can route requests to supported
commercial AWS Regions worldwide, whereas Geo CRIS routes requests within the profile's geography.

Use `model_provider = "amazon-bedrock-runtime"` with the optional `model` configuration set to an inference profile ID from the following lists. The provider uses
`https://bedrock-runtime.{region}.amazonaws.com/openai/v1`, where `{region}` is
the supported source AWS Region from which you send requests. Both Global and Geo CRIS use this endpoint address.

#### Global CRIS

Supported models and inference profile IDs:

- GPT-6 Astra: `global.openai.gpt-6-astra`
- GPT-5.6 Sol: `global.openai.gpt-5.6-sol`
- GPT-5.6 Terra: `global.openai.gpt-5.6-terra`
- GPT-5.6 Luna: `global.openai.gpt-5.6-luna`

For example, configure Astra with Global CRIS in `~/.codex/config.toml`:

```toml
model_provider = "amazon-bedrock-runtime"
model = "global.openai.gpt-6-astra"
```

#### United States Geo CRIS

Supported models and inference profile IDs:

- GPT-6 Astra: `us.openai.gpt-6-astra`
- GPT-5.6 Sol: `us.openai.gpt-5.6-sol`
- GPT-5.6 Terra: `us.openai.gpt-5.6-terra`
- GPT-5.6 Luna: `us.openai.gpt-5.6-luna`

Codex's built-in Runtime model picker lists the United States Geo and Global
variants. AWS also lists India geographic inference profile IDs `in.openai.gpt-5.6-terra` and
`in.openai.gpt-5.6-luna` for `ap-south-1` (Mumbai) and `ap-south-2` (Hyderabad).
See the AWS [Terra](https://docs.aws.amazon.com/bedrock/latest/userguide/model-card-openai-gpt-56-terra.html) and [Luna](https://docs.aws.amazon.com/bedrock/latest/userguide/model-card-openai-gpt-56-luna.html) model pages for details.

Model and CRIS availability vary by source AWS Region. See AWS [Supported Regions and models for inference profiles](https://docs.aws.amazon.com/bedrock/latest/userguide/inference-profiles-support.html), which links to each model's exact inference profile IDs and regional
availability, and AWS [Regional availability by models](https://docs.aws.amazon.com/bedrock/latest/userguide/models-region-compatibility.html#model-regions-openai) before selecting a provider and a model.

### In-Region inference using the Bedrock Mantle endpoint

Use `model_provider = "amazon-bedrock"` with an optional model ID. The provider uses
`https://bedrock-mantle.{region}.api.aws/openai/v1`.

Supported models and model IDs:

- GPT-6 Astra: `openai.gpt-6-astra`
- GPT-5.6 Sol: `openai.gpt-5.6-sol`
- GPT-5.6 Terra: `openai.gpt-5.6-terra`
- GPT-5.6 Luna: `openai.gpt-5.6-luna`
- GPT-5.5: `openai.gpt-5.5`
- GPT-5.4: `openai.gpt-5.4`

Model availability varies by AWS Region. See AWS [Regional availability by models](https://docs.aws.amazon.com/bedrock/latest/userguide/models-region-compatibility.html#model-regions-openai) before selecting a provider and a model. For GPT-6 Astra, refer to the [Bedrock model page for GPT-6 Astra](https://docs.aws.amazon.com/bedrock/latest/userguide/model-card-openai-gpt-6-astra.html).

## Feature availability

This configuration supports local ChatGPT Work and Codex workflows. Hosted
ChatGPT Work on the web, Codex cloud, and features that depend on OpenAI-hosted
cloud services, hosted tools, or cloud-managed discovery aren't currently
available.

Fast Mode isn't available with Amazon Bedrock. Fast Mode uses priority
  processing, and the initial Amazon Bedrock offering supports on-demand
  inference only.

<details>
<summary>Detailed feature availability</summary>

### Access and surfaces

| Feature | Amazon Bedrock |
| --- | --- |
| [ChatGPT Work on the web](./get-started-with-work.md) | No |
| [Codex cloud](./cloud.md) | No |
| [ChatGPT Work or Codex in the ChatGPT desktop app](./app.md) | Yes |
| [Codex CLI](https://developers.openai.com/codex/cli) | Yes |
| [Codex Security CLI](./security/cli.md) | Yes |
| [IDE extension](https://developers.openai.com/codex/ide) | Yes |
| [Codex SDK, `codex exec`, and scriptable workflows](./codex-sdk.md) | Yes |
### Models and multimodal

| Feature | Amazon Bedrock |
| --- | --- |
| [Bedrock-backed inference with supported OpenAI models](./amazon-bedrock.md) | Yes |
| [Fast mode](./agent-configuration/speed.md) | No |
| [Image generation and editing](./image-generation.md) | No |
| [Voice dictation](./prompting.md#use-voice-dictation) | No |
| [Web search](./web-search.md) | No |
### Local features

| Feature | Amazon Bedrock |
| --- | --- |
| [Codex Security plugin and local scans](./security/plugin.md) | Yes |
| [Local code review with `/review`](./prompting.md#do-a-local-code-review) | Yes |
| [Auto-review for approval requests](./sandboxing/auto-review.md) | Yes |
| [Sandboxing and permission controls](./permissions.md) | Yes |
| [Project and standalone scheduled tasks](./automations.md) | Yes |
| [Scheduled tasks](./automations.md) | Yes |
| [Worktrees and built-in Git tools](./environments/git-worktrees.md) | Yes |
| [Local environments and repeatable actions](./environments/local-environment.md) | Yes |
| [Appshots](./appshots.md) | Yes |
### Browser and remote control

| Feature | Amazon Bedrock |
| --- | --- |
| [Built-in browser previews and comments](./browser.md) | Yes |
| [Computer Use in the browser](./browser.md) | Limited |
| [Use ChatGPT with Chrome](./chrome-extension.md) | Limited |
| [Computer Use](./computer-use.md) | Limited |
| [SSH remote connections](./remote-connections.md#connect-to-an-ssh-host) | Yes |
| [Mobile remote control](./remote-connections.md) | No |
### Customization and extensions

| Feature | Amazon Bedrock |
| --- | --- |
| [Custom instructions with `AGENTS.md`](./agent-configuration/agents-md.md) | Yes |
| [Skills](./build-skills.md) | Yes |
| [Plugins](./plugins.md) | Limited |
| [Plugin sharing](https://developers.openai.com/plugins/build/plugins#share-a-local-plugin-with-your-workspace) | No |
| [Connectors](./plugins.md) | No |
| [MCP](./extend/mcp.md) | Yes |
| [Subagents and custom agents](./agent-configuration/subagents.md) | Yes |
| [Memories](./customization/memories.md) | Limited |
| [Computer History](./customization/computer-history.md) | No |
### Cloud and integrations

| Feature | Amazon Bedrock |
| --- | --- |
| [Codex cloud chats](./cloud.md) | No |
| [Sites](./sites.md) | No |
| [GitHub issue and PR delegation with `@codex`](./third-party/github.md#give-codex-other-tasks) | No |
| [GitHub code review and automatic PR reviews](./third-party/github.md) | No |
| [Slack cloud integration](./third-party/slack.md) | No |
| [Linear cloud integration](./third-party/linear.md) | No |
### Admin, security, and analytics

| Feature | Amazon Bedrock |
| --- | --- |
| [SAML SSO, MFA, and workspace user management](./enterprise/admin-setup.md) | No |
| [`requirements.toml` managed config](./enterprise/managed-configuration.md) | Yes |
| [Cloud-managed config policies](./enterprise/managed-configuration.md#cloud-managed-requirements) | No |
| [ChatGPT workspace RBAC and custom roles](./enterprise/roles-and-workspace-permissions.md) | No |
| [SCIM, EKM, and domain verification](./enterprise/admin-setup.md#enterprise-grade-security-and-privacy) | No |
| [Enterprise retention and residency controls](./enterprise/admin-setup.md#enterprise-grade-security-and-privacy) | No |
| [No training on API or business data by default](https://openai.com/business-data/) | Yes |
| [Analytics dashboard](./enterprise/workspace-analytics.md) | No |
| [Analytics API](./enterprise/analytics-api.md) | No |
| [Compliance API and audit logs](./enterprise/compliance-api.md) | No |
| [Codex Security cloud for connected GitHub repositories](./security/setup.md) | No |

<div
  id="codex-plan-region-limits"
  className="not-prose mt-3 text-sm text-secondary"
>
  <sup>*</sup> Feature is currently limited to only specific regions. Check
  the individual feature documentation to learn more about geo restrictions.

<div
  id="codex-plan-plugin-limits"
  className="not-prose mt-1 text-sm text-secondary"
>
  <sup>†</sup> Local plugin bundles and OpenAI-curated plugins that don't
  require ChatGPT authentication, including Codex Security, are available.
  Plugins that require ChatGPT authentication, connectors, or cloud-hosted
  sharing aren't available.

</details>

## Troubleshooting

If setup fails, check the following:

- The model ID exactly matches a supported model.
- You use the correct model provider for the endpoint: `amazon-bedrock-runtime` for Runtime endpoint or `amazon-bedrock` for Mantle endpoint.
- You specify an AWS Region where the model is available.
- The Bedrock API key or AWS credentials are valid and not expired.
- The AWS identity has permission to access the selected Bedrock model.
- `AWS_BEARER_TOKEN_BEDROCK` isn't set to an expired or unintended key.
- For desktop app or IDE extension usage, required environment variables are
  present in `~/.codex/.env`.

## Support boundaries

OpenAI Support can help with ChatGPT Work and Codex client setup,
configuration, local CLI behavior, desktop app behavior, IDE extension behavior,
and the local product experience.

For AWS credentials, IAM permissions, Bedrock model access, quotas, billing,
regional availability, Bedrock request failures, AWS service logs, or Bedrock
service behavior, contact the customer's AWS administrator or AWS Support.