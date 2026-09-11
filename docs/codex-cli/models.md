# Models

> For the complete documentation index, see [llms.txt](https://learn.chatgpt.com/llms.txt). Markdown versions of documentation pages are available by appending `.md` to the page URL.

**Surface: Desktop app**

<a id="app-choose-a-model"></a>

## Choose a model

In the ChatGPT desktop app, use the model and reasoning control beneath the
composer to choose an available model and adjust its reasoning effort.

Higher reasoning effort can improve results for complex tasks, but it takes
longer and uses more tokens. Start with the default effort and increase it when
the task needs deeper planning or analysis.

**Ultra** mode goes
beyond a single-agent run. It uses
[subagents](./agent-configuration/subagents.md) to accelerate complex work,
making it useful for larger tasks that can be split across subagents.

**Surface: Web**

<a id="web-choose-a-model"></a>

## Choose a model

These recommendations apply to **ChatGPT Work** on the web. Use the
model and reasoning control beneath the composer to choose an available model
and adjust its reasoning effort.

Higher reasoning effort can improve results for complex tasks, but it takes
longer and uses more tokens. Start with the default effort and increase it when
the task needs deeper planning or analysis.

**Ultra** mode goes
beyond a single-agent run. It uses
[subagents](./agent-configuration/subagents.md) to accelerate complex work,
making it useful for larger tasks that can be split across subagents.

**Surface: CLI**

<a id="cli-choose-a-model"></a>

## Choose a model

In an interactive CLI session, use `/model` to switch models or adjust
reasoning effort. You can also choose a model when you launch Codex with
`--model` or its `-m` alias:

```bash
codex --model gpt-5.6
```

The same option works with non-interactive runs. For example:

```bash
codex exec -m gpt-5.6 "Review the current changes"
```

Higher reasoning effort can improve results for complex tasks, but it takes
longer and uses more tokens. Start with the default effort and increase it when
the task needs deeper planning or analysis.

**Ultra** mode goes
beyond a single-agent run. It uses
[subagents](./agent-configuration/subagents.md) to accelerate complex work,
making it useful for larger tasks that can be split across subagents.

**Surface: IDE extension**

<a id="ide-choose-a-model"></a>

## Choose a model

Use the model switcher below the composer to choose an available model and
reasoning effort.

Higher reasoning effort can improve results for complex tasks, but it takes
longer and uses more tokens. Start with the default effort and increase it when
the task needs deeper planning or analysis.

**Ultra** mode goes
beyond a single-agent run. It uses
[subagents](./agent-configuration/subagents.md) to accelerate complex work,
making it useful for larger tasks that can be split across subagents.

<a id="recommended-models"></a>
<a id="other-models"></a>
<a id="deprecated-codex-models"></a>
<a id="configure-your-default-local-model"></a>
<a id="choose-a-model-for-cloud-tasks"></a>
<a id="gpt-6-astra"></a>

<a id="app-recommended-models"></a>
<a id="web-recommended-models"></a>
<a id="cli-recommended-models"></a>
<a id="ide-recommended-models"></a>

## Recommended models

<a id="app-compare-models"></a>

  ### `gpt-6-astra`

Our most capable model for complex work across code, apps, and research, combining advanced reasoning, computer use, and stronger judgment.

- **ChatGPT desktop app**: Supported
- **ChatGPT web**: Supported
- **Codex CLI**: Supported
- **Codex IDE extension**: Supported
- **Codex cloud**: Not supported
- **ChatGPT Credits**: Supported
- **API Access**: Supported

### `gpt-5.6-sol`

The most capable GPT-5.6 model for complex coding, computer use, research, and cybersecurity.

- **ChatGPT desktop app**: Supported
- **ChatGPT web**: Supported
- **Codex CLI**: Supported
- **Codex IDE extension**: Supported
- **Codex cloud**: Supported
- **ChatGPT Credits**: Supported
- **API Access**: Supported

### `gpt-5.6-terra`

Balanced GPT-5.6 model for everyday work, with performance competitive with GPT-5.5 at a lower cost.

- **ChatGPT desktop app**: Supported
- **ChatGPT web**: Supported
- **Codex CLI**: Supported
- **Codex IDE extension**: Supported
- **Codex cloud**: Not supported
- **ChatGPT Credits**: Supported
- **API Access**: Supported

### `gpt-5.6-luna`

Fast and affordable GPT-5.6 model that delivers strong capability at the lowest cost in the family.

- **ChatGPT desktop app**: Supported
- **ChatGPT web**: Supported
- **Codex CLI**: Supported
- **Codex IDE extension**: Supported
- **Codex cloud**: Not supported
- **ChatGPT Credits**: Supported
- **API Access**: Supported

### `gpt-5.3-codex-spark`

Text-only research preview model optimized for near-instant, real-time coding iteration. Available to ChatGPT Pro users.

- **ChatGPT desktop app**: Supported
- **ChatGPT web**: Not supported
- **Codex CLI**: Supported
- **Codex IDE extension**: Supported
- **Codex cloud**: Not supported
- **ChatGPT Credits**: Not supported
- **API Access**: Not supported

Availability depends on the rollout, your sign-in method, and your client.
See [pricing](./pricing.md) for plan access and usage, and
[workspace model availability](./enterprise/workspace-model-availability.md#gpt-6-astra-in-enterprise)
for Enterprise access.

Start with the default Power setting available to your account. Move toward
  **Smarter** for deeper reasoning or **Faster** for faster, lower-cost work.
  Open **Advanced** when you want `gpt-5.6-luna` or a specific model, reasoning
  effort, or speed.

The picker illustrations show GPT-5.6 controls. For eligible Pro, Business
($100), and Enterprise accounts, the Astra rollout updates the Power options
to Terra Light, Sol Light, Sol Medium, Astra Light, Astra Medium, and Astra
Extra High. Options can differ by plan and rollout stage.

<a id="app-experimental-context-management"></a>
<a id="web-experimental-context-management"></a>
<a id="cli-experimental-context-management"></a>
<a id="ide-experimental-context-management"></a>

<a id="app-experimental-context-management-2"></a>
<a id="cli-experimental-context-management-2"></a>
<a id="ide-experimental-context-management-2"></a>

### Experimental context management

On supported Codex clients, users signed in with ChatGPT Plus or Pro can opt
in to experimental context management. Astra keeps notes across context
windows and can search earlier messages and tool results from the same task.
This experiment is off by default and isn't available with Business, Enterprise, or
API-key sign-in at launch.

To opt in, set `features.context_management.experimental_mode = true` in your
`config.toml`, then start a new task. See the [configuration reference](./config-file/config-reference.md)
for the setting and [configuration basics](./config-file/config-basic.md)
for the file location. Workspace requirements still apply.

<a id="choosing-sol-terra-and-luna"></a>

<a id="app-choosing-astra-sol-terra-and-luna"></a>
<a id="web-choosing-astra-sol-terra-and-luna"></a>
<a id="cli-choosing-astra-sol-terra-and-luna"></a>
<a id="ide-choosing-astra-sol-terra-and-luna"></a>

## Choosing Astra, Sol, Terra, and Luna

Choose **Astra** when a task needs the strongest capability across multiple
steps and tools. **Sol** offers depth and polish, **Terra** suits everyday work,
and **Luna** suits clear, repeatable tasks.

<a id="app-where-each-model-shines"></a>
<a id="web-where-each-model-shines"></a>
<a id="cli-where-each-model-shines"></a>
<a id="ide-where-each-model-shines"></a>

### Where each model shines

- **Astra, for the hardest end-to-end work.** Choose Astra for complete workflows
  across code, apps, and research that need sustained reasoning and judgment.
  Give it the sources, templates, constraints, and checks that define a useful
  result. Astra is better at asking focused questions and incorporating your
  guidance while keeping the original goal and constraints in view.
- **Sol, for complex, open-ended work.** Choose Sol for ambiguous, difficult, or
  high-value tasks that need extra analysis, judgment, or polish, such as
  complex code changes, deep research, or polished documents. For narrower
  tasks, define what done looks like to keep the work focused.
- **Terra, the pragmatic all-rounder.** Choose Terra for everyday work that
  needs strong reasoning and tool use when you do not need Sol's full depth. It
  is a natural starting point for work you previously gave GPT-5.5.
- **Luna, for clear, repeatable tasks.** Choose Luna for specific, high-volume
  tasks when you know what a good result looks like, such as extraction,
  classification, transformation, and structured summaries.

<a id="app-pick-a-reasoning-effort"></a>
<a id="web-pick-a-reasoning-effort"></a>
<a id="cli-pick-a-reasoning-effort"></a>
<a id="ide-pick-a-reasoning-effort"></a>

### Pick a reasoning effort

Use the lowest reasoning effort that produces the result you need. Increase it
for tasks that need more planning, analysis, or checking.

- **Light** in the ChatGPT desktop app, ChatGPT Work on the web, and IDE extension, or **Low** in the
  CLI, suits quick, well-scoped tasks.
- **Medium** balances speed and depth for tasks that need more planning.
- **High** and **Extra High** suit difficult work with multiple steps, sources,
  or tradeoffs.

There is no exact mapping from GPT-5.5 reasoning efforts to GPT-5.6. Try a
familiar task at a lower setting and adjust based on the result.

<a id="app-know-when-to-use-max-or-ultra"></a>
<a id="web-know-when-to-use-max-or-ultra"></a>
<a id="cli-know-when-to-use-max-or-ultra"></a>
<a id="ide-know-when-to-use-max-or-ultra"></a>

### Know when to use Max or Ultra

**Max** gives the selected model more time to reason about a single task. Use it
for the hardest problems, when depth matters more than speed or usage. If you
don't see Max in your options, you'll have to enable it in your app settings.

**Ultra** uses [subagents](./agent-configuration/subagents.md) to handle
separate parts of a complex task in parallel. Choose it when you can divide the
work into meaningful parts. Most tasks do not need Max or Ultra.

If Ultra doesn't appear in the desktop app's model slider, go to
**Settings** > **Configuration**, then turn on **Ultra in model picker slider**.

<a id="app-other-models"></a>
<a id="cli-other-models"></a>
<a id="ide-other-models"></a>

## Other models

When you sign in with ChatGPT, Codex works best with the recommended models listed above.

**
    GPT-5.4 and GPT-5.4 mini retire from Codex on August 31, 2026.
  ** 
  If you sign in with ChatGPT, replace `gpt-5.4` with `gpt-5.6-terra` and
  `gpt-5.4-mini` with `gpt-5.6-luna` in saved configurations, custom agents, and
  scheduled tasks. The OpenAI API and Codex authenticated with your own API key
  aren't affected.

<details>
<summary>View other models</summary>

### `gpt-5.5`

Previous-generation flagship model for complex coding, computer use, knowledge work, and research workflows.

- **ChatGPT desktop app**: Supported
- **ChatGPT web**: Supported
- **Codex CLI**: Supported
- **Codex IDE extension**: Supported
- **Codex cloud**: Not supported
- **ChatGPT Credits**: Supported
- **API Access**: Supported

### `gpt-5.4`

Flagship model for professional work with strong coding, reasoning, tool use, and agentic workflow capabilities.

- **ChatGPT desktop app**: Supported
- **ChatGPT web**: Supported
- **Codex CLI**: Supported
- **Codex IDE extension**: Supported
- **Codex cloud**: Not supported
- **ChatGPT Credits**: Supported
- **API Access**: Supported

### `gpt-5.4-mini`

Fast, efficient mini model for responsive coding tasks and subagents.

- **ChatGPT desktop app**: Supported
- **ChatGPT web**: Supported
- **Codex CLI**: Supported
- **Codex IDE extension**: Supported
- **Codex cloud**: Not supported
- **ChatGPT Credits**: Supported
- **API Access**: Supported

</details>

You can also point Codex at any model and provider that supports either the [Chat Completions](https://platform.openai.com/docs/api-reference/chat) or [Responses APIs](https://platform.openai.com/docs/api-reference/responses) to fit your specific use case.

Support for the Chat Completions API is deprecated and will be removed in
  future releases of Codex.

<a id="app-deprecated-codex-models"></a>
<a id="cli-deprecated-codex-models"></a>
<a id="ide-deprecated-codex-models"></a>

## Deprecated Codex models

The `gpt-5.4` and `gpt-5.4-mini` models retire from Codex with ChatGPT sign-in
on August 31, 2026. Replace `gpt-5.4` with `gpt-5.6-terra` and
`gpt-5.4-mini` with `gpt-5.6-luna` in workspace defaults, saved model
settings, managed configurations, custom agents, and scheduled tasks.

The `gpt-5.2` and `gpt-5.3-codex` models are already deprecated in Codex when
you sign in with ChatGPT. Update scripts, configuration files, and
`codex exec --model` commands that still reference those models.

The OpenAI API and Codex authenticated with your own API key aren't affected
by the GPT-5.4 retirement. For current API model availability, see the
[API models page](https://developers.openai.com/api/docs/models).

<a id="app-configure-your-default-local-model"></a>
<a id="cli-configure-your-default-local-model"></a>
<a id="ide-configure-your-default-local-model"></a>

## Configure your default local model

The ChatGPT desktop app, Codex CLI, and IDE extension use the same `config.toml`
[configuration file](./config-file/config-basic.md). To specify a model, add a
`model` entry to your configuration file. If you don't specify a model, the
ChatGPT desktop app, Codex CLI, or IDE extension uses a recommended model.

```toml
model = "gpt-5.6"
```

<a id="app-choose-a-model-for-cloud-chats"></a>
<a id="cli-choose-a-model-for-cloud-chats"></a>
<a id="ide-choose-a-model-for-cloud-chats"></a>

## Choose a model for cloud chats

Currently, you can't change the default model for Codex cloud chats.