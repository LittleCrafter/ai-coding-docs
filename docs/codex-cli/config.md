# Configuration

## Config basics
Codex reads configuration details from more than one location. Your personal defaults live in `~/.codex/config.toml`, and you can add project overrides with `.codex/config.toml` files. For security, Codex loads project `.codex/` layers only when you trust the project.

### Codex configuration file
Codex stores user-level configuration at `~/.codex/config.toml`. To scope settings to a specific project or subfolder, add a `.codex/config.toml` file in your repo.

To open the configuration file from the Codex IDE extension, select the gear icon in the top-right corner, then select **Codex Settings > Open config.toml**.

The CLI and IDE extension share the same configuration layers. You can use them to:

- Set the default model and provider.
- Configure [approval policies and sandbox settings](./agent-approvals-security.md#sandbox-and-approvals).
- Configure [MCP servers](./extend/mcp.md).

### Configuration precedence
Codex resolves values in this order (highest precedence first):

1. CLI flags and `--config` overrides
2. Project config files: `.codex/config.toml`, ordered from the project root down to your current working directory (closest wins; trusted projects only)
3. [Profile](./config-file/config-advanced.md#profiles) files selected with `--profile profile-name` (`~/.codex/profile-name.config.toml`)
4. User config: `~/.codex/config.toml`
5. Cloud-managed `config.toml` defaults, when delivered for the signed-in workspace
6. System config (if present): `/etc/codex/config.toml` on Unix
7. Built-in defaults

Use that precedence to set shared defaults in `config.toml` and keep [profile files](./config-file/config-advanced.md#profiles) focused on the values that differ.

Cloud-managed and system configuration can define plugin marketplaces and set
whether plugins are enabled by default. These are separate from enforced `requirements.toml`
policies. See [Configure plugin marketplaces and defaults](./enterprise/managed-configuration.md#configure-plugin-marketplaces-and-defaults).

If you mark a project as untrusted, Codex skips project-scoped `.codex/` layers, including project-local config, hooks, and rules. User and system config still load, including user/global hooks and rules.

For one-off overrides via `-c`/`--config` (including TOML quoting rules), see [Advanced Config](./config-file/config-advanced.md#one-off-overrides-from-the-cli).

On managed machines, your organization may also enforce constraints via
  `requirements.toml` (for example, disallowing `approval_policy = "never"` or
  `sandbox_mode = "danger-full-access"`). See [Managed
  configuration](./enterprise/managed-configuration.md) and [Admin-enforced
  requirements](./enterprise/managed-configuration.md#admin-enforced-requirements-requirementstoml).

### Common configuration options
Here are a few options people change most often:

##### Default model
Choose the model Codex uses by default in the CLI and IDE.

```toml
model = "gpt-5.6"
```

##### Approval prompts
Control when Codex pauses to ask before running generated commands.

```toml
approval_policy = "on-request"
```

For behavior differences between `on-request` and `never`, see [Run without approval prompts](./agent-approvals-security.md#run-without-approval-prompts) and [Common sandbox and approval combinations](./agent-approvals-security.md#common-sandbox-and-approval-combinations). If an existing configuration uses `approval_policy = "untrusted"`, see [Migrate from the retired `untrusted` approval policy](./agent-approvals-security.md#migrate-from-the-retired-untrusted-approval-policy).

##### Sandbox level
Adjust how much filesystem and network access Codex has while executing commands.

```toml
sandbox_mode = "workspace-write"
```

For mode-by-mode behavior (including protected `.git`/`.codex` paths and network defaults), see [Sandbox and approvals](./agent-approvals-security.md#sandbox-and-approvals), [Protected paths in writable roots](./agent-approvals-security.md#protected-paths-in-writable-roots), and [Network access](./agent-approvals-security.md#network-access).

##### Permission profiles
Codex also supports named permission profiles for reusable filesystem and
network policies. Built-in profiles are `:read-only`, `:workspace`, and
`:danger-full-access`. Custom profiles use `[permissions.<name>]` tables and a
matching `default_permissions` value. See [Permissions](./permissions.md).

##### Windows sandbox mode
When running Codex natively on Windows, set the native sandbox mode to `elevated` in the `windows` table. Use `unelevated` only if you don't have administrator permissions or if elevated setup fails.

```toml
[windows]
sandbox = "elevated"   # Recommended
# sandbox = "unelevated" # Fallback if admin permissions/setup are unavailable
```

##### Web search mode
Codex enables web search by default for local chats and serves results from a web search cache. The cache is an OpenAI-maintained index of web results, so cached mode returns pre-indexed results instead of fetching live pages. This reduces exposure to prompt injection from arbitrary live content, but you should still treat web results as untrusted. If you are using `--yolo` or another [full access sandbox setting](./agent-approvals-security.md#common-sandbox-and-approval-combinations), web search defaults to live results. Choose a mode with `web_search`:

- `"cached"` (default) serves results from the web search cache.
- `"indexed"` permits external web access only when the search index gates the request.
- `"live"` fetches the most recent data from the web (same as `--search`).
- `"disabled"` turns off the web search tool.

```toml
web_search = "cached"  # default; serves results from the web search cache
# web_search = "indexed" # gate external web access through the search index
# web_search = "live"  # fetch the most recent data from the web (same as --search)
# web_search = "disabled"
```

##### Reasoning effort
Tune how much reasoning effort the model applies when supported.

```toml
model_reasoning_effort = "high"
```

##### Communication style
Set a default communication style for supported models.

```toml
personality = "friendly" # or "pragmatic" or "none"
```

You can override this later in an active session with `/personality` or per thread/turn when using the app-server APIs.

##### TUI keymap
Customize terminal shortcuts under `tui.keymap`. Selected composer actions fall back to matching `tui.keymap.global` bindings; context-specific bindings take precedence when supported. An empty list unbinds the action.

```toml
[tui.keymap.global]
open_transcript = "ctrl-t"

[tui.keymap.composer]
submit = ["enter", "ctrl-m"]

[tui.keymap.chat]
interrupt_turn = "f12"
```

##### Command environment
Control which environment variables Codex forwards to spawned commands. Use
keyed filters to keep only the variables you need:

```toml
[shell_environment_policy]
ignore_default_excludes = false

[shell_environment_policy.filters]
"PATH" = "include"
"HOME" = "include"
```

`ignore_default_excludes` defaults to `true`, which skips automatic filtering
for variable names containing `KEY`, `SECRET`, or `TOKEN`. Set it to `false`
when you want that automatic filtering. For exclusion rules, precedence, and
legacy configuration, see [Shell environment
policy](./config-file/config-advanced.md#shell-environment-policy).

##### Log directory
Override where Codex writes local log files. Setting `log_dir` explicitly also
enables the opt-in plaintext TUI log, `codex-tui.log`, in that directory.

```toml
log_dir = "/absolute/path/to/codex-logs"
```

For one-off runs, you can also set it from the CLI:

```bash
codex -c log_dir=./.codex-log
```

### Feature flags
Use the `[features]` table in `config.toml` to toggle optional and experimental capabilities.

#### Common feature flags
| Key                  |        Default        | Maturity     | Description                                                                              |
| -------------------- | :-------------------: | ------------ | ---------------------------------------------------------------------------------------- |
| `apps`               |         true          | Stable       | Enable app (connector) integrations                                                      |
| `goals`              |         true          | Stable       | Enable persisted goals and automatic continuation                                        |
| `hooks`              |         true          | Stable       | Enable lifecycle hooks from `hooks.json` or inline `[hooks]`. See [Hooks](./hooks.md). |
| `fast_mode`          |         true          | Stable       | Enable Fast mode selection and the `service_tier = "fast"` path                          |
| `memories`           |         false         | Experimental | Enable [Memories](./customization/memories.md)                                         |
| `multi_agent`        |         true          | Stable       | Enable subagent collaboration tools                                                      |
| `personality`        |         true          | Stable       | Enable personality selection controls                                                    |
| `remote_plugin`      |         true          | Stable       | Enable the remote plugin catalog                                                         |
| `shell_snapshot`     |         true          | Stable       | Snapshot your shell environment to speed up repeated commands                            |
| `shell_tool`         |         true          | Stable       | Enable the default `shell` tool                                                          |
| `unified_exec`       | `true` except Windows | Stable       | Use the unified PTY-backed exec tool                                                     |
| `web_search`         |         true          | Deprecated   | Legacy toggle; prefer the top-level `web_search` setting                                 |
| `web_search_cached`  |         false         | Deprecated   | Legacy toggle that maps to `web_search = "cached"` when unset                            |
| `web_search_request` |         false         | Deprecated   | Legacy toggle that maps to `web_search = "live"` when unset                              |

This table lists common user-facing flags, not every internal or
  under-development feature. The Maturity column uses labels such as
  Experimental, Beta, and Stable. See [Feature
  Maturity](./feature-maturity.md) for how to interpret these labels.

Omit feature keys to keep their defaults.

For lifecycle hook configuration, see [Hooks](./hooks.md).

#### Enabling features
- In `config.toml`, add `feature_name = true` under `[features]`.
- From the CLI, run `codex --enable feature_name`.
- To enable more than one feature, run `codex --enable feature_a --enable feature_b`.
- To disable a feature, set the key to `false` in `config.toml`.

## Advanced Configuration
Use these options when you need more control over providers, policies, and integrations. For a quick start, see [Config basics](./config-file/config-basic.md).

For background on project guidance, reusable capabilities, custom slash commands, subagent workflows, and integrations, see [Customization](./customization/overview.md). For configuration keys, see [Configuration Reference](./config-file/config-reference.md).

### Profiles
Profiles let you save named configuration layers and switch between them from
the CLI. When you pass `--profile profile-name`, Codex loads
`~/.codex/config.toml`, then overlays `~/.codex/profile-name.config.toml`.
Profile names can contain letters, numbers, hyphens, and underscores.

Create a separate TOML file for each profile. Use top-level config keys in the
profile file; don't nest them under `[profiles.profile-name]`.

```toml
# ~/.codex/deep-review.config.toml
model = "gpt-5.5"
model_reasoning_effort = "xhigh"
approval_policy = "on-request"
model_catalog_json = "/Users/me/.codex/model-catalogs/deep-review.json"
```

```shell
codex --profile deep-review
codex exec --profile deep-review "review this change"
```

Because the profile file is a layer above your base user config and below
project and CLI config, it only needs the values that differ from your base
config. Profile files can also override `model_catalog_json`; Codex uses the
profile value when both files set it.

In Codex 0.134.0 and later, `--profile` no longer reads `[profiles.profile-name]`
from `config.toml`, and the top-level `profile = "profile-name"` selector is no
longer supported. Move legacy profile settings into
`~/.codex/profile-name.config.toml`, then remove the matching
`[profiles.profile-name]` table and `profile = "profile-name"` selector from
`config.toml`.

### One-off overrides from the CLI
In addition to editing `~/.codex/config.toml`, you can override configuration for a single run from the CLI:

- Prefer dedicated flags when they exist (for example, `--model`).
- Use `-c` / `--config` when you need to override an arbitrary key.

Examples:

```shell
# Dedicated flag
codex --model gpt-5.6-terra

# Generic key/value override (value is TOML, not JSON)
codex --config model='"gpt-5.6-terra"'
codex --config sandbox_workspace_write.network_access=true
codex --config 'shell_environment_policy.include_only=["PATH","HOME"]'
```

Notes:

- Keys can use dot notation to set nested values (for example, `mcp_servers.context7.enabled=false`).
- `--config` values are parsed as TOML. When in doubt, quote the value so your shell doesn't split it on spaces.
- If the value can't be parsed as TOML, Codex treats it as a string.

### Config and state locations
Codex stores its local state under `CODEX_HOME` (defaults to `~/.codex`).

Common files you may see there:

- `config.toml` (your local configuration)
- `auth.json` (if you use file-based credential storage) or your OS keychain/keyring
- `history.jsonl` (if history persistence is enabled)
- Other per-user state such as logs and caches

For authentication details (including credential storage modes), see [Authentication](./auth.md). For the full list of configuration keys, see [Configuration Reference](./config-file/config-reference.md).

For shared defaults, rules, and skills checked into repos or system paths, see [Team Config](./enterprise/admin-setup.md#step-4-standardize-local-configuration-with-team-config).

If you just need to point the built-in OpenAI provider at an LLM proxy, router, or data-residency enabled project, set `openai_base_url` in `config.toml` instead of defining a new provider. This changes the base URL for the built-in `openai` provider without requiring a separate `model_providers.<id>` entry.

```toml
openai_base_url = "https://us.api.openai.com/v1"
```

### Project config files (`.codex/config.toml`)
In addition to your user config, Codex reads project-scoped overrides from `.codex/config.toml` files inside your repo. Codex walks from the project root to your current working directory and loads every `.codex/config.toml` it finds. If multiple files define the same key, the closest file to your working directory wins.

For security, Codex loads project-scoped config files only when the project is trusted. If the project is untrusted, Codex ignores project `.codex/` layers, including `.codex/config.toml`, project-local hooks, and project-local rules. User and system layers remain separate and still load.

Relative paths inside a project config (for example, `model_instructions_file`) are resolved relative to the `.codex/` folder that contains the `config.toml`.

Project config files can't override settings that redirect credentials, alter
host-owned app request metadata, change provider auth, select config profiles,
or run machine-local notification/telemetry commands. Codex ignores the
following keys in project-local `.codex/config.toml` and prints a startup
warning when it sees them: `openai_base_url`, `chatgpt_base_url`,
`apps_mcp_product_sku`, `model_provider`, `model_providers`, `notify`,
`profile`, `profiles`, `experimental_realtime_ws_base_url`, and `otel`. Set
provider, notification, and telemetry keys in your user-level
`~/.codex/config.toml`; select config profiles with `--profile profile-name`
and `~/.codex/profile-name.config.toml`.

### Hooks
Codex can also load lifecycle hooks from either `hooks.json` files or inline
`[hooks]` tables in `config.toml` files that sit next to active config layers.

In practice, the four most useful locations are:

- `~/.codex/hooks.json`
- `~/.codex/config.toml`
- `<repo>/.codex/hooks.json`
- `<repo>/.codex/config.toml`

Project-local hooks load only when the project `.codex/` layer is trusted.
User-level hooks remain independent of project trust.

Inline TOML hooks use the same event structure as `hooks.json`:

```toml
[[hooks.PreToolUse]]
matcher = "^Bash$"

[[hooks.PreToolUse.hooks]]
type = "command"
command = '/usr/bin/python3 "$(git rev-parse --show-toplevel)/.codex/hooks/pre_tool_use_policy.py"'
timeout = 30
statusMessage = "Checking Bash command"
```

If a single layer contains both `hooks.json` and inline `[hooks]`, Codex loads
both and warns. Prefer one representation per layer.

For the current event list, input fields, output behavior, and limitations, see
[Hooks](./hooks.md).

### Agent roles (`[agents]` in `config.toml`)
For subagent role configuration (`[agents]` in `config.toml`), see [Subagents](./agent-configuration/subagents.md).

### Project root detection
Codex discovers project configuration (for example, `.codex/` layers and `AGENTS.md`) by walking up from the working directory until it reaches a project root.

By default, Codex treats a directory containing `.git` as the project root. To customize this behavior, set `project_root_markers` in `config.toml`:

```toml
# Treat a directory as the project root when it contains any of these markers.
project_root_markers = [".git", ".hg", ".sl"]
```

Set `project_root_markers = []` to skip searching parent directories and treat the current working directory as the project root.

### Custom model providers
A model provider defines how Codex connects to a model (base URL, wire API, authentication, and optional HTTP headers). Custom providers can't reuse the reserved built-in provider IDs: `openai`, `ollama`, and `lmstudio`.

Define additional providers and point `model_provider` at them:

```toml
model = "gpt-5.6-terra"
model_provider = "proxy"

[model_providers.proxy]
name = "OpenAI using LLM proxy"
base_url = "http://proxy.example.com"
env_key = "OPENAI_API_KEY"

[model_providers.local_ollama]
name = "Ollama"
base_url = "http://localhost:11434/v1"

[model_providers.mistral]
name = "Mistral"
base_url = "https://api.mistral.ai/v1"
env_key = "MISTRAL_API_KEY"
```

If a custom provider supports the standalone web search endpoint, advertise
that capability in its provider configuration:

```toml
[model_providers.proxy]
name = "OpenAI using LLM proxy"
base_url = "https://proxy.example.com/v1"
env_key = "OPENAI_API_KEY"
supports_standalone_web_search = true
```

The setting defaults to `false` for custom providers. Standalone web search is
under development and off by default. Setting the provider capability to `true`
doesn't enable it: the provider must support a compatible endpoint,
and the selected model and runtime must support standalone search. The
configured [`web_search` mode](./web-search.md) and
managed search restrictions still apply.

Add request headers when needed:

```toml
[model_providers.example]
http_headers = { "X-Example-Header" = "example-value" }
env_http_headers = { "X-Example-Features" = "EXAMPLE_FEATURES" }
```

Use command-backed authentication when a provider needs Codex to fetch bearer tokens from an external credential helper:

```toml
[model_providers.proxy]
name = "OpenAI using LLM proxy"
base_url = "https://proxy.example.com/v1"
wire_api = "responses"

[model_providers.proxy.auth]
command = "/usr/local/bin/fetch-codex-token"
args = ["--audience", "codex"]
timeout_ms = 5000
refresh_interval_ms = 300000
```

The auth command receives no `stdin` and must print the token to stdout. Codex trims surrounding whitespace, treats an empty token as an error, and refreshes proactively at `refresh_interval_ms`; set `refresh_interval_ms = 0` to refresh only after an authentication retry. Don't combine `[model_providers.<id>.auth]` with `env_key`, `experimental_bearer_token`, or `requires_openai_auth`.

#### Amazon Bedrock provider
Codex includes a built-in `amazon-bedrock` model provider. Set it directly as
`model_provider`; unlike custom providers, this built-in provider supports only
the nested AWS profile and region overrides.

```toml
model_provider = "amazon-bedrock"
model = "<bedrock-model-id>"

[model_providers.amazon-bedrock.aws]
profile = "default"
region = "eu-central-1"
```

If you omit `profile`, Codex uses the standard AWS credential chain. Set
`region` to the supported Bedrock region that should handle requests.

For the full setup flow, authentication options, supported models, and feature
availability, see [Use ChatGPT Work and Codex with Amazon
Bedrock](./amazon-bedrock.md).

### OSS mode (local providers)
Codex can run against a local "open source" provider such as Ollama or LM
Studio when you pass `--oss`. Choose one for a single run with
`--local-provider`, or set `oss_provider` as the default. If neither is set, the
interactive CLI prompts you to choose; `codex exec` exits with an error.

```toml
# Default local provider used with `--oss`
oss_provider = "ollama" # or "lmstudio"
```

### Azure provider and per-provider tuning
```toml
[model_providers.azure]
name = "Azure"
base_url = "https://YOUR_PROJECT_NAME.openai.azure.com/openai"
env_key = "AZURE_OPENAI_API_KEY"
query_params = { api-version = "2025-04-01-preview" }
wire_api = "responses"
request_max_retries = 4
stream_max_retries = 10
stream_idle_timeout_ms = 300000
```

To change the base URL for the built-in OpenAI provider, use `openai_base_url`; don't create `[model_providers.openai]`, because you can't override built-in provider IDs.

### API organizations using data residency
Projects created with [data residency](https://help.openai.com/en/articles/9903489-data-residency-and-inference-residency-for-chatgpt) enabled can create a model provider to update the `base_url` with the [correct prefix](https://developers.openai.com/api/docs/guides/your-data#which-models-and-features-are-eligible-for-data-residency). For ChatGPT workspaces with data residency, a custom provider isn't required; Codex respects workspace residency settings when you sign in with ChatGPT.

```toml
model_provider = "openaidr"
[model_providers.openaidr]
name = "OpenAI Data Residency"
base_url = "https://us.api.openai.com/v1" # Replace 'us' with domain prefix
```

### Model reasoning, verbosity, and limits
```toml
model_reasoning_summary = "none"          # Disable summaries
model_verbosity = "low"                   # Shorten responses
model_supports_reasoning_summaries = true # Force reasoning
model_context_window = 128000             # Context window size
```

`model_verbosity` applies only to providers using the Responses API. Chat Completions providers will ignore the setting.

### Approval policies and sandbox modes
Pick approval strictness (affects when Codex pauses) and sandbox level (affects file/network access).

For operational details to keep in mind while editing `config.toml`, see [Common sandbox and approval combinations](./agent-approvals-security.md#common-sandbox-and-approval-combinations), [Protected paths in writable roots](./agent-approvals-security.md#protected-paths-in-writable-roots), and [Network access](./agent-approvals-security.md#network-access).

Codex and ChatGPT Work no longer support `approval_policy = "untrusted"`. See
[Migrate from the retired `untrusted` approval policy](./agent-approvals-security.md#migrate-from-the-retired-untrusted-approval-policy)
for supported settings and stricter project-derived approvals.

For beta permission profiles that configure filesystem and network access together, see [Permissions](./permissions.md).

You can also use a granular approval policy (`approval_policy = { granular = { ... } }`) to allow or auto-reject individual prompt categories. This is useful when you want normal interactive approvals for some cases but want others, such as `request_permissions` or skill-script prompts, to fail closed automatically.

Set `approvals_reviewer = "auto_review"` to route eligible interactive approval
requests through automatic review. This changes the reviewer, not the sandbox
boundary.

Use `[auto_review].policy` for local reviewer policy instructions. Managed
`guardian_policy_config` takes precedence.

```toml
approval_policy = "on-request"  # Other options: never or { granular = { ... } }
approvals_reviewer = "user"     # Or "auto_review" for automatic review
sandbox_mode = "workspace-write"
allow_login_shell = false       # Optional hardening: disallow login shells for shell tools

# Example granular approval policy:
# approval_policy = { granular = {
#   sandbox_approval = true,
#   rules = true,
#   mcp_elicitations = true,
#   request_permissions = false,
#   skill_approval = false
# } }

[sandbox_workspace_write]
exclude_tmpdir_env_var = false  # Allow $TMPDIR
exclude_slash_tmp = false       # Allow /tmp
writable_roots = ["/Users/YOU/.pyenv/shims"]
network_access = false          # Opt in to outbound network

[auto_review]
policy = """
Use your organization's automatic review policy.
"""
```

#### Named permission profiles
For built-in profiles, custom profile syntax, and the full filesystem and
network configuration model, see [Permissions](./permissions.md).

For the complete key list and requirements constraints, see
[Configuration Reference](./config-file/config-reference.md) and
[Managed configuration](./enterprise/managed-configuration.md).

In workspace-write mode, some environments keep `.git/` and `.codex/`
  read-only even when the rest of the workspace is writable. This is why
  commands like `git commit` may still require approval to run outside the
  sandbox. If you want Codex to skip specific commands (for example, block `git
  commit` outside the sandbox), use
  [rules](./agent-configuration/rules.md).

Disable sandboxing entirely (use only if your environment already isolates processes):

```toml
sandbox_mode = "danger-full-access"
```

### Shell environment policy
`shell_environment_policy` controls which environment variables Codex passes to
spawned commands. Start with an empty environment using `inherit = "none"`, or
inherit a trimmed set using `inherit = "core"`. Add explicit values and keyed
filters to avoid passing unnecessary secrets to spawned commands.

```toml
[shell_environment_policy]
inherit = "core"
set = { MY_FLAG = "1" }
ignore_default_excludes = false

[shell_environment_policy.filters]
"AWS_*" = "exclude"
"AZURE_*" = "exclude"
```

Filter patterns are case-insensitive and support `*` and `?`. Use `"exclude"`
to remove matching variables. When any pattern uses `"include"`, Codex keeps
only variables matching an include pattern. Includes don't restore variables
that were already excluded. Filter keys merge case-insensitively across
configuration layers.

`ignore_default_excludes` defaults to `true`, so Codex doesn't automatically
remove variable names containing `KEY`, `SECRET`, or `TOKEN`. Set it to `false`
to apply those automatic exclusions before your explicit filters run.

Codex applies automatic exclusions first, then custom exclusions, values from
`set`, and finally the include-pattern allowlist. Because `set` runs after
exclusions, it can restore an excluded variable. An include-pattern allowlist
can still remove that restored value.

The older `exclude` and `include_only` arrays remain supported for existing
configurations. Don't combine either array with
`[shell_environment_policy.filters]` in the same configuration layer; Codex
rejects that combination.

### MCP servers
See the dedicated [MCP documentation](./extend/mcp.md) for configuration details.

### Observability and telemetry
Enable OpenTelemetry (OTel) log export to track Codex runs (API requests, SSE/events, prompts, tool approvals/results). Disabled by default; opt in via `[otel]`:

```toml
[otel]
environment = "staging"   # defaults to "dev"
exporter = "none"         # set to otlp-http or otlp-grpc to send events
log_user_prompt = false   # redact user prompts unless explicitly enabled
```

Choose an exporter:

```toml
[otel]
exporter = { otlp-http = {
  endpoint = "https://otel.example.com/v1/logs",
  protocol = "binary",
  headers = { "x-otlp-api-key" = "${OTLP_TOKEN}" }
}}
```

```toml
[otel]
exporter = { otlp-grpc = {
  endpoint = "https://otel.example.com:4317",
  headers = { "x-otlp-meta" = "abc123" }
}}
```

If `exporter = "none"` Codex records events but sends nothing. Exporters batch asynchronously and flush on shutdown. Event metadata includes service name, CLI version, env tag, conversation id, model, sandbox/approval settings, and per-event fields (see [Config Reference](./config-file/config-reference.md)).

#### What gets emitted
Codex emits structured log events for runs and tool usage. Representative event types include:

- `codex.conversation_starts` (model, reasoning settings, sandbox/approval policy)
- `codex.api_request` (attempt, status/success, duration, and error details)
- `codex.sse_event` (stream event kind, success/failure, duration, plus token counts on `response.completed`)
- `codex.websocket_request` and `codex.websocket_event` (request duration plus per-message kind/success/error)
- `codex.user_prompt` (length; content redacted unless explicitly enabled)
- `codex.tool_decision` (approved/denied and whether the decision came from config vs user)
- `codex.tool_result` (duration, success, output snippet)

#### OTel metrics emitted
When the OTel metrics pipeline is enabled, Codex emits counters and duration histograms for API, stream, and tool activity.

Each metric below also includes default metadata tags: `auth_mode`, `originator`, `session_source`, `model`, and `app.version`.

| Metric                                | Type      | Fields              | Description                                                       |
| ------------------------------------- | --------- | ------------------- | ----------------------------------------------------------------- |
| `codex.api_request`                   | counter   | `status`, `success` | API request count by HTTP status and success/failure.             |
| `codex.api_request.duration_ms`       | histogram | `status`, `success` | API request duration in milliseconds.                             |
| `codex.sse_event`                     | counter   | `kind`, `success`   | SSE event count by event kind and success/failure.                |
| `codex.sse_event.duration_ms`         | histogram | `kind`, `success`   | SSE event processing duration in milliseconds.                    |
| `codex.websocket.request`             | counter   | `success`           | WebSocket request count by success/failure.                       |
| `codex.websocket.request.duration_ms` | histogram | `success`           | WebSocket request duration in milliseconds.                       |
| `codex.websocket.event`               | counter   | `kind`, `success`   | WebSocket message/event count by type and success/failure.        |
| `codex.websocket.event.duration_ms`   | histogram | `kind`, `success`   | WebSocket message/event processing duration in milliseconds.      |
| `codex.tool.call`                     | counter   | `tool`, `success`   | Tool invocation count by tool name and success/failure.           |
| `codex.tool.call.duration_ms`         | histogram | `tool`, `success`   | Tool execution duration in milliseconds by tool name and outcome. |

For more security and privacy guidance around telemetry, see [Security](./agent-approvals-security.md#monitoring-and-telemetry).

#### Metrics
By default, Codex periodically sends a small amount of anonymous usage and health data back to OpenAI. This helps detect when Codex isn't working correctly and shows what features and configuration options are being used, so the Codex team can focus on what matters most. These metrics don't contain any personally identifiable information (PII). Metrics collection is independent of OTel log/trace export.

If you want to disable metrics collection entirely across the ChatGPT desktop app, Codex CLI, and IDE extension on a machine, set the analytics flag in your config:

```toml
[analytics]
enabled = false
```

Each metric includes its own fields plus the default context fields below.

##### Default context fields (applies to every event/metric)
- `auth_mode`: `swic` | `api` | `unknown`.
- `model`: name of the model used.
- `app.version`: Codex version.

##### Metrics catalog
Each metric includes the required fields plus the default context fields above. Metric names below omit the `codex.` prefix.
Most metric names are centralized in `codex-rs/otel/src/metrics/names.rs`; feature-specific metrics emitted outside that file are included here too.
If a metric includes the `tool` field, it reflects the internal tool used (for example, `apply_patch` or `shell`) and doesn't contain the actual shell command or patch `codex` is trying to apply.

##### Runtime and model transport
| Metric                                          | Type      | Fields               | Description                                                  |
| ----------------------------------------------- | --------- | -------------------- | ------------------------------------------------------------ |
| `api_request`                                   | counter   | `status`, `success`  | API request count by HTTP status and success/failure.        |
| `api_request.duration_ms`                       | histogram | `status`, `success`  | API request duration in milliseconds.                        |
| `sse_event`                                     | counter   | `kind`, `success`    | SSE event count by event kind and success/failure.           |
| `sse_event.duration_ms`                         | histogram | `kind`, `success`    | SSE event processing duration in milliseconds.               |
| `websocket.request`                             | counter   | `success`            | WebSocket request count by success/failure.                  |
| `websocket.request.duration_ms`                 | histogram | `success`            | WebSocket request duration in milliseconds.                  |
| `websocket.event`                               | counter   | `kind`, `success`    | WebSocket message/event count by type and success/failure.   |
| `websocket.event.duration_ms`                   | histogram | `kind`, `success`    | WebSocket message/event processing duration in milliseconds. |
| `responses_api_overhead.duration_ms`            | histogram |                      | Responses API overhead timing from WebSocket responses.      |
| `responses_api_inference_time.duration_ms`      | histogram |                      | Responses API inference timing from WebSocket responses.     |
| `responses_api_engine_iapi_ttft.duration_ms`    | histogram |                      | Responses API engine IAPI time-to-first-token timing.        |
| `responses_api_engine_service_ttft.duration_ms` | histogram |                      | Responses API engine service time-to-first-token timing.     |
| `responses_api_engine_iapi_tbt.duration_ms`     | histogram |                      | Responses API engine IAPI time-between-token timing.         |
| `responses_api_engine_service_tbt.duration_ms`  | histogram |                      | Responses API engine service time-between-token timing.      |
| `transport.fallback_to_http`                    | counter   | `from_wire_api`      | WebSocket-to-HTTP fallback count.                            |
| `remote_models.fetch_update.duration_ms`        | histogram |                      | Time to fetch remote model definitions.                      |
| `remote_models.load_cache.duration_ms`          | histogram |                      | Time to load the remote model cache.                         |
| `startup_prewarm.duration_ms`                   | histogram | `status`             | Startup prewarm duration by outcome.                         |
| `startup_prewarm.age_at_first_turn_ms`          | histogram | `status`             | Startup prewarm age when the first real turn resolves it.    |
| `cloud_requirements.fetch.duration_ms`          | histogram |                      | Workspace-managed cloud requirements fetch duration.         |
| `cloud_requirements.fetch_attempt`              | counter   | See note             | Workspace-managed cloud requirements fetch attempts.         |
| `cloud_requirements.fetch_final`                | counter   | See note             | Final workspace-managed cloud requirements fetch outcome.    |
| `cloud_requirements.load`                       | counter   | `trigger`, `outcome` | Workspace-managed cloud requirements load outcome.           |

The `cloud_requirements.fetch_attempt` metric includes `trigger`, `attempt`, `outcome`, and `status_code` fields. The `cloud_requirements.fetch_final` metric includes `trigger`, `outcome`, `reason`, `attempt_count`, and `status_code` fields.

##### Turn and tool activity
| Metric                                 | Type      | Fields                                                                    | Description                                                                                                      |
| -------------------------------------- | --------- | ------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------- |
| `turn.e2e_duration_ms`                 | histogram |                                                                           | End-to-end time for a full turn.                                                                                 |
| `turn.ttft.duration_ms`                | histogram |                                                                           | Time to first token for a turn.                                                                                  |
| `turn.ttfm.duration_ms`                | histogram |                                                                           | Time to first model output item for a turn.                                                                      |
| `turn.network_proxy`                   | counter   | `active`, `tmp_mem_enabled`                                               | Whether the managed network proxy was active for the turn.                                                       |
| `turn.memory`                          | counter   | `read_allowed`, `feature_enabled`, `config_use_memories`, `has_citations` | Per-turn memory read availability and memory citation usage.                                                     |
| `turn.tool.call`                       | histogram | `tmp_mem_enabled`                                                         | Number of tool calls in the turn.                                                                                |
| `turn.token_usage`                     | histogram | `token_type`, `tmp_mem_enabled`                                           | Per-turn token usage by token type (`total`, `input`, `cached_input`, `output`, or `reasoning_output`).          |
| `tool.call`                            | counter   | `tool`, `success`                                                         | Tool invocation count by tool name and success/failure.                                                          |
| `tool.call.duration_ms`                | histogram | `tool`, `success`                                                         | Tool execution duration in milliseconds by tool name and outcome.                                                |
| `tool.unified_exec`                    | counter   | `tty`                                                                     | Unified exec tool calls by TTY mode.                                                                             |
| `approval.requested`                   | counter   | `tool`, `approved`                                                        | Tool approval request result (`approved`, `approved_with_amendment`, `approved_for_session`, `denied`, `abort`). |
| `mcp.call`                             | counter   | See note                                                                  | MCP tool invocation result.                                                                                      |
| `mcp.call.duration_ms`                 | histogram | See note                                                                  | MCP tool invocation duration.                                                                                    |
| `mcp.tools.list.duration_ms`           | histogram | `cache`                                                                   | MCP tool-list duration, including cache hit/miss state.                                                          |
| `mcp.tools.fetch_uncached.duration_ms` | histogram |                                                                           | Duration of MCP tool fetches that miss the cache.                                                                |
| `mcp.tools.cache_write.duration_ms`    | histogram |                                                                           | Duration of Codex Apps MCP tool-cache writes.                                                                    |
| `hooks.run`                            | counter   | `hook_name`, `source`, `status`                                           | Hook run count by hook name, source, and status.                                                                 |
| `hooks.run.duration_ms`                | histogram | `hook_name`, `source`, `status`                                           | Hook run duration in milliseconds.                                                                               |

The `mcp.call` and `mcp.call.duration_ms` metrics include `status`; normal tool-call emissions also include `tool`, plus `connector_id` and `connector_name` when available. Blocked Codex Apps MCP calls may emit `mcp.call` with only `status`.

##### Threads, tasks, and features
| Metric                            | Type      | Fields                | Description                                                                      |
| --------------------------------- | --------- | --------------------- | -------------------------------------------------------------------------------- |
| `feature.state`                   | counter   | `feature`, `value`    | Feature values that differ from defaults (emit one row per non-default).         |
| `status_line`                     | counter   |                       | Session started with a configured status line.                                   |
| `model_warning`                   | counter   |                       | Warning sent to the model.                                                       |
| `thread.started`                  | counter   | `is_git`              | New thread created, tagged by whether the working directory is in a Git repo.    |
| `conversation.turn.count`         | counter   |                       | User/assistant turns per thread, recorded at the end of the thread.              |
| `thread.fork`                     | counter   | `source`              | New thread created by forking an existing thread.                                |
| `thread.rename`                   | counter   |                       | Thread renamed.                                                                  |
| `thread.side`                     | counter   | `source`              | Side conversation created.                                                       |
| `thread.skills.enabled_total`     | histogram |                       | Number of skills enabled for a new thread.                                       |
| `thread.skills.kept_total`        | histogram |                       | Number of enabled skills kept after prompt rendering.                            |
| `thread.skills.truncated`         | histogram |                       | Whether skill rendering truncated the enabled skills list (`1` or `0`).          |
| `task.compact`                    | counter   | `type`                | Number of compactions per type (`remote` or `local`), including manual and auto. |
| `task.review`                     | counter   |                       | Number of reviews triggered.                                                     |
| `task.undo`                       | counter   |                       | Number of undo actions triggered.                                                |
| `task.user_shell`                 | counter   |                       | Number of user shell actions (`!` in the TUI for example).                       |
| `shell_snapshot`                  | counter   | See note              | Whether taking a shell snapshot succeeded.                                       |
| `shell_snapshot.duration_ms`      | histogram | `success`             | Time to take a shell snapshot.                                                   |
| `skill.injected`                  | counter   | `status`, `skill`     | Skill injection outcomes by skill.                                               |
| `plugins.startup_sync`            | counter   | `transport`, `status` | Curated plugin startup sync attempts.                                            |
| `plugins.startup_sync.final`      | counter   | `transport`, `status` | Final curated plugin startup sync outcome.                                       |
| `multi_agent.spawn`               | counter   | `role`                | Agent spawns by role.                                                            |
| `multi_agent.resume`              | counter   |                       | Agent resumes.                                                                   |
| `multi_agent.nickname_pool_reset` | counter   |                       | Agent nickname pool resets.                                                      |

The `shell_snapshot` metric includes `success` and, on failures, `failure_reason`.

##### Memory and local state
| Metric                         | Type      | Fields                    | Description                                               |
| ------------------------------ | --------- | ------------------------- | --------------------------------------------------------- |
| `memory.phase1`                | counter   | `status`                  | Memory phase 1 job counts by status.                      |
| `memory.phase1.e2e_ms`         | histogram |                           | End-to-end duration for memory phase 1.                   |
| `memory.phase1.output`         | counter   |                           | Memory phase 1 outputs written.                           |
| `memory.phase1.token_usage`    | histogram | `token_type`              | Memory phase 1 token usage by token type.                 |
| `memory.phase2`                | counter   | `status`                  | Memory phase 2 job counts by status.                      |
| `memory.phase2.e2e_ms`         | histogram |                           | End-to-end duration for memory phase 2.                   |
| `memory.phase2.input`          | counter   |                           | Memory phase 2 input count.                               |
| `memory.phase2.token_usage`    | histogram | `token_type`              | Memory phase 2 token usage by token type.                 |
| `memories.usage`               | counter   | `kind`, `tool`, `success` | Memory usage by kind, tool, and success/failure.          |
| `external_agent_config.detect` | counter   | See note                  | External agent config detections by migration item type.  |
| `external_agent_config.import` | counter   | See note                  | External agent config imports by migration item type.     |
| `db.backfill`                  | counter   | `status`                  | Initial state DB backfill results (`upserted`, `failed`). |
| `db.backfill.duration_ms`      | histogram | `status`                  | Duration of the initial state DB backfill.                |
| `db.error`                     | counter   | `stage`                   | Errors during state DB operations.                        |

The `external_agent_config.detect` and `external_agent_config.import` metrics include `migration_type`; skills migrations also include `skills_count`.

##### Windows sandbox
| Metric                                           | Type      | Fields                                    | Description                                           |
| ------------------------------------------------ | --------- | ----------------------------------------- | ----------------------------------------------------- |
| `windows_sandbox.setup_success`                  | counter   | `originator`, `mode`                      | Windows sandbox setup successes.                      |
| `windows_sandbox.setup_failure`                  | counter   | `originator`, `mode`                      | Windows sandbox setup failures.                       |
| `windows_sandbox.setup_duration_ms`              | histogram | `result`, `originator`, `mode`            | Windows sandbox setup duration.                       |
| `windows_sandbox.elevated_setup_success`         | counter   |                                           | Elevated Windows sandbox setup successes.             |
| `windows_sandbox.elevated_setup_failure`         | counter   | See note                                  | Elevated Windows sandbox setup failures.              |
| `windows_sandbox.elevated_setup_canceled`        | counter   | See note                                  | Canceled elevated Windows sandbox setup attempts.     |
| `windows_sandbox.elevated_setup_duration_ms`     | histogram | `result`                                  | Elevated Windows sandbox setup duration.              |
| `windows_sandbox.elevated_prompt_shown`          | counter   |                                           | Elevated sandbox setup prompt shown.                  |
| `windows_sandbox.elevated_prompt_accept`         | counter   |                                           | Elevated sandbox setup prompt accepted.               |
| `windows_sandbox.elevated_prompt_use_legacy`     | counter   |                                           | User chose legacy sandbox from the elevated prompt.   |
| `windows_sandbox.elevated_prompt_quit`           | counter   |                                           | User quit from the elevated prompt.                   |
| `windows_sandbox.fallback_prompt_shown`          | counter   |                                           | Fallback sandbox prompt shown.                        |
| `windows_sandbox.fallback_retry_elevated`        | counter   |                                           | User retried elevated setup from the fallback prompt. |
| `windows_sandbox.fallback_use_legacy`            | counter   |                                           | User chose legacy sandbox from the fallback prompt.   |
| `windows_sandbox.fallback_prompt_quit`           | counter   |                                           | User quit from the fallback prompt.                   |
| `windows_sandbox.legacy_setup_preflight_failed`  | counter   | See note                                  | Legacy Windows sandbox setup preflight failure.       |
| `windows_sandbox.setup_elevated_sandbox_command` | counter   |                                           | Elevated sandbox setup command invoked.               |
| `windows_sandbox.createprocessasuserw_failed`    | counter   | `error_code`, `path_kind`, `exe`, `level` | Windows `CreateProcessAsUserW` failures.              |

The elevated setup failure metrics include `code` and `message` when Windows setup failure details are available, and may include `originator` when emitted from the shared setup path. The `windows_sandbox.legacy_setup_preflight_failed` metric includes `originator` when emitted from the shared setup path, but fallback-prompt preflight failures may not include any fields.

#### Feedback controls
By default, local clients let users send feedback from `/feedback`. To disable feedback collection across the ChatGPT desktop app, Codex CLI, and IDE extension on a machine, update your config:

```toml
[feedback]
enabled = false
```

When disabled, `/feedback` shows a disabled message and Codex rejects feedback submissions.

#### Hide or surface reasoning events
If you want to reduce noisy "reasoning" output (for example in CI logs), you can suppress it:

```toml
hide_agent_reasoning = true
```

If you want to surface raw reasoning content when a model emits it:

```toml
show_raw_agent_reasoning = true
```

Enable raw reasoning only if it's acceptable for your workflow. Some models/providers (like `gpt-oss`) don't emit raw reasoning; in that case, this setting has no visible effect.

### Notifications
Use `notify` to trigger an external program whenever Codex emits supported events (currently only `agent-turn-complete`). This is handy for desktop toasts, chat webhooks, CI updates, or any side-channel alerting that the built-in TUI notifications don't cover.

```toml
notify = ["python3", "/path/to/notify.py"]
```

Example `notify.py` (truncated) that reacts to `agent-turn-complete`:

```python
#!/usr/bin/env python3
import json, subprocess, sys

def main() -> int:
    notification = json.loads(sys.argv[1])
    if notification.get("type") != "agent-turn-complete":
        return 0
    title = f"Codex: {notification.get('last-assistant-message', 'Turn Complete!')}"
    message = " ".join(notification.get("input-messages", []))
    subprocess.check_output([
        "terminal-notifier",
        "-title", title,
        "-message", message,
        "-group", "codex-" + notification.get("thread-id", ""),
        "-activate", "com.googlecode.iterm2",
    ])
    return 0

if __name__ == "__main__":
    sys.exit(main())
```

The script receives a single JSON argument. Common fields include:

- `type` (currently `agent-turn-complete`)
- `thread-id` (session identifier)
- `turn-id` (turn identifier)
- `cwd` (working directory)
- `input-messages` (user messages that led to the turn)
- `last-assistant-message` (last assistant message text)

Place the script somewhere on disk and point `notify` to it.

##### `notify` vs `tui.notifications`
- `notify` runs an external program (good for webhooks, desktop notifiers, CI hooks).
- `tui.notifications` is built in to the TUI and can optionally filter by event type (for example, `agent-turn-complete` and `approval-requested`).
- `tui.notification_method` controls how the TUI emits terminal notifications (`auto`, `osc9`, or `bel`).
- `tui.notification_condition` controls whether TUI notifications fire only when
  the terminal is `unfocused` or `always`.

In `auto` mode, Codex prefers OSC 9 notifications (a terminal escape sequence some terminals interpret as a desktop notification) and falls back to BEL (`\x07`) otherwise.

See [Configuration Reference](./config-file/config-reference.md) for the exact keys.

### History persistence
By default, Codex saves local session transcripts under `CODEX_HOME` (for example, `~/.codex/history.jsonl`). To disable local history persistence:

```toml
[history]
persistence = "none"
```

To cap the history file size, set `history.max_bytes`. When the file exceeds the cap, Codex drops the oldest entries and compacts the file while keeping the newest records.

```toml
[history]
max_bytes = 104857600 # 100 MiB
```

### Clickable citations
If you use a terminal/editor integration that supports it, Codex can render file citations as clickable links. Configure `file_opener` to pick the URI scheme Codex uses:

```toml
file_opener = "vscode" # or cursor, windsurf, vscode-insiders, none
```

Example: a citation like `/home/user/project/main.py:42` can be rewritten into a clickable `vscode://file/...:42` link.

### Project instructions discovery
Codex reads `AGENTS.md` (and related files) and includes a limited amount of project guidance in the first turn of a session. Two knobs control how this works:

- `project_doc_max_bytes`: how much to read from each `AGENTS.md` file
- `project_doc_fallback_filenames`: additional filenames to try when `AGENTS.md` is missing at a directory level

For a detailed walkthrough, see [Custom instructions with AGENTS.md](./agent-configuration/agents-md.md).

### Desktop
Options in this section apply only to the ChatGPT desktop app.

#### Add custom file handlers
In your user-level `~/.codex/config.toml`, add entries under
`desktop.custom_file_handlers` to open files in editors or internal launchers
that the ChatGPT desktop app doesn't support by default. Each entry adds an
editor target to the app's **Open in** menus. The app lists the target when
`command` is an existing absolute path or resolves from the app's `PATH`.

The following example shows three ways to pass a file to a handler:

```toml
# Append the opened path directly after the command.
[desktop.custom_file_handlers.vscodium]
label = "VSCodium"
icon = "/Users/you/.codex/icons/vscodium.png"
command = "codium"

# Place fixed arguments before the opened path.
[desktop.custom_file_handlers.textedit]
label = "TextEdit"
icon = "/Users/you/.codex/icons/textedit.png"
command = "/usr/bin/open"
args = ["-a", "TextEdit"]

# Append one JSON argument with the path and editor context.
[desktop.custom_file_handlers.company_editor]
label = "Company Editor"
icon = "/opt/company/editor/icon.png"
command = "/opt/company/bin/editor"
input = "json_argument"
```

Save `config.toml`, then restart the ChatGPT desktop app.

The handler ID is the final segment of the TOML table header. It must contain
1–64 characters, start with an ASCII letter or number, and otherwise contain
only ASCII letters, numbers, periods, underscores, or hyphens. The app exposes
the ID with a `custom:` prefix; for example, `company_editor` becomes
`custom:company_editor`. Quote an ID that contains a period so TOML doesn't
interpret it as a nested table. For example:

```toml
[desktop.custom_file_handlers."company.editor"]
label = "Company Editor"
icon = "/opt/company/editor/icon.png"
command = "/opt/company/bin/editor"
```

Each handler supports these fields:

| Field          | Required | Description                                                                                                                                                              |
| -------------- | -------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `label`        | Yes      | Display name in the app.                                                                                                                                                 |
| `icon`         | Yes      | Bundled app icon such as `apps/vscode.png`, base64 `data:image/...` URL, `file:` URI, or absolute local image path. An unsupported source uses the default VS Code icon. |
| `command`      | Yes      | Executable path or command name to detect and launch.                                                                                                                    |
| `args`         | No       | String array inserted between `command` and the file input. Defaults to `[]`.                                                                                            |
| `input`        | No       | How the app sends file input: `path`, `json_argument`, or `json_stdin`. Defaults to `path`.                                                                              |
| `supports_ssh` | No       | Whether to offer the handler for files in SSH workspaces. Defaults to `false`. Use `json_stdin` when the handler needs remote host and path details.                     |

The `input` value controls what follows `args`:

- `path` appends the path as the final command argument.
- `json_argument` appends a JSON object with `target`, `path`, `appPath`, and
  `location`. The `location` value is an object with 1-based `line` and
  `column` values, or `null`.
- `json_stdin` writes the JSON object to standard input instead of adding an
  argument. It also includes `hostConfig`, `remoteWorkspaceRoot`, and
  `remotePath`; these fields are `null` when they don't apply.

For example, `company_editor` can receive this argument when the user opens a
specific source location:

```json
{
  "target": "custom:company_editor",
  "path": "/repo/src/index.ts",
  "appPath": null,
  "location": { "line": 12, "column": 3 }
}
```

Selecting a custom handler as the preferred editor persists the choice the same
way as selecting a built-in editor, including per-project preferences.

### TUI options
Running `codex` with no subcommand launches the interactive terminal UI (TUI). Codex exposes some TUI-specific configuration under `[tui]`, including:

- `tui.notifications`: enable/disable notifications (or restrict to specific types)
- `tui.notification_method`: choose `auto`, `osc9`, or `bel` for terminal notifications
- `tui.notification_condition`: choose `unfocused` or `always` for when
  notifications fire
- `tui.animations`: enable/disable ASCII animations and shimmer effects
- `tui.alternate_screen`: control alternate screen usage (set to `never` to keep terminal scrollback)
- `tui.show_tooltips`: show or hide onboarding tooltips on the welcome screen

`tui.notification_method` defaults to `auto`. In `auto` mode, Codex prefers OSC 9 notifications (a terminal escape sequence some terminals interpret as a desktop notification) when the terminal appears to support them, and falls back to BEL (`\x07`) otherwise.

See [Configuration Reference](./config-file/config-reference.md) for the full key list.

## Configuration Reference
Use this page as a searchable reference for Codex configuration files. For conceptual guidance and examples, start with [Config basics](./config-file/config-basic.md) and [Advanced Config](./config-file/config-advanced.md).

### `config.toml`
User-level configuration lives in `~/.codex/config.toml`. You can also add project-scoped overrides in `.codex/config.toml` files. Codex loads project-scoped config files only when you trust the project.

Project-scoped config can't override machine-local provider, auth,
host-owned app request metadata, notification, configuration profile selection,
or telemetry routing keys. Codex ignores `openai_base_url`,
`chatgpt_base_url`, `apps_mcp_product_sku`, `model_provider`,
`model_providers`, `notify`, `profile`, `profiles`,
`experimental_realtime_ws_base_url`, and `otel` when they appear in a
project-local `.codex/config.toml`; put provider, notification, and telemetry
keys in user-level config instead. Config [profile files](./config-file/config-advanced.md#profiles) live next to
`config.toml` as `$CODEX_HOME/profile-name.config.toml`; select one with
`--profile profile-name`.

For sandbox and approval keys (`approval_policy`, `sandbox_mode`, and `sandbox_workspace_write.*`), pair this reference with [Sandbox and approvals](./agent-approvals-security.md#sandbox-and-approvals), [Protected paths in writable roots](./agent-approvals-security.md#protected-paths-in-writable-roots), and [Network access](./agent-approvals-security.md#network-access). For beta permission profiles, see [Permissions](./permissions.md).

Codex and ChatGPT Work no longer support `approval_policy = "untrusted"`.
Remove the setting or choose a supported policy. Project entries with
`trust_level = "untrusted"` in user-level `~/.codex/config.toml` remain supported. See
[Migrate from the retired `untrusted` approval policy](./agent-approvals-security.md#migrate-from-the-retired-untrusted-approval-policy)
for examples and approval tradeoffs.

| Key | Type | Description |
| --- | --- | --- |
| `model` | `string` | Model to use (e.g., `gpt-5.5`). |
| `review_model` | `string` | Optional model override used by `/review` (defaults to the current session model). |
| `model_provider` | `string` | Provider id from `model_providers` (default: `openai`). |
| `openai_base_url` | `string` | Base URL override for the built-in `openai` model provider. |
| `model_context_window` | `number` | Context window tokens available to the active model. |
| `model_auto_compact_token_limit` | `number` | Token threshold that triggers automatic history compaction (unset uses model defaults). |
| `model_auto_compact_token_limit_scope` | `total \| body_after_prefix` | Controls whether the auto-compaction threshold counts the full active context (`total`, the default) or only growth after the carried compaction-window prefix (`body_after_prefix`). |
| `model_catalog_json` | `string (path)` | Optional path to a JSON model catalog loaded on startup. A selected `$CODEX_HOME/profile-name.config.toml` profile file can override this per profile. |
| `oss_provider` | `lmstudio \| ollama` | Default local provider used when running with `--oss` (defaults to prompting if unset). |
| `approval_policy` | `on-request \| never \| { granular = { sandbox_approval = bool, rules = bool, mcp_elicitations = bool, request_permissions = bool, skill_approval = bool } }` | Controls when Codex pauses for approval before executing commands. You can also use `approval_policy = { granular = { ... } }` to allow or auto-reject specific prompt categories while keeping other prompts interactive. `untrusted` is unsupported, and `on-failure` is deprecated; use `on-request` for interactive runs or `never` for non-interactive runs. |
| `approval_policy.granular.sandbox_approval` | `boolean` | When `true`, sandbox escalation approval prompts are allowed to surface. |
| `approval_policy.granular.rules` | `boolean` | When `true`, approvals triggered by execpolicy `prompt` rules are allowed to surface. |
| `approval_policy.granular.mcp_elicitations` | `boolean` | When `true`, MCP elicitation prompts are allowed to surface instead of being auto-rejected. |
| `approval_policy.granular.request_permissions` | `boolean` | When `true`, prompts from the `request_permissions` tool are allowed to surface. |
| `approval_policy.granular.skill_approval` | `boolean` | When `true`, skill-script approval prompts are allowed to surface. |
| `approvals_reviewer` | `user \| auto_review` | Who reviews eligible approval prompts under `on-request` or granular approval policies. Defaults to `user`; `auto_review` uses the reviewer subagent. This setting doesn't change sandboxing or review actions already allowed inside the sandbox. |
| `auto_review.policy` | `string` | Local Markdown policy instructions for automatic review. Managed `guardian_policy_config` takes precedence. Blank values are ignored. |
| `allow_login_shell` | `boolean` | Allow shell-based tools to use login-shell semantics. Defaults to `true`; when `false`, `login = true` requests are rejected and omitted `login` defaults to non-login shells. |
| `sandbox_mode` | `read-only \| workspace-write \| danger-full-access` | Sandbox policy for filesystem and network access during command execution. |
| `sandbox_workspace_write.writable_roots` | `array<string>` | Additional writable roots when `sandbox_mode = "workspace-write"`. |
| `sandbox_workspace_write.network_access` | `boolean` | Allow outbound network access inside the workspace-write sandbox. |
| `sandbox_workspace_write.exclude_tmpdir_env_var` | `boolean` | Exclude `$TMPDIR` from writable roots in workspace-write mode. |
| `sandbox_workspace_write.exclude_slash_tmp` | `boolean` | Exclude `/tmp` from writable roots in workspace-write mode. |
| `windows.sandbox` | `unelevated \| elevated` | Windows-only native sandbox mode when running Codex natively on Windows. |
| `windows.sandbox_private_desktop` | `boolean` | Run the final sandboxed child process on a private desktop by default on native Windows. Set `false` only for compatibility with the older `Winsta0\\Default` behavior. |
| `browser_use.allow_history_access` | `boolean` | Set to `false` to restrict browser-history access. Managed requirements can enforce this restriction. |
| `browser_use.default_origin_policy` | `table` | Fallback browser-origin restrictions. Supports `access`, `uploads`, `downloads`, and `full_cdp_access`, each set to `allow` or `deny`. |
| `browser_use.origins.<origin>` | `table` | Per-origin browser restrictions with the same fields as `browser_use.default_origin_policy`. Include an HTTP or HTTPS scheme and optional port; omit paths, queries, and fragments. Local values cannot relax managed denies. |
| `computer_use.default_app_access` | `allow \| deny` | Fallback native-app access policy for Computer Use. App-specific entries can supply a policy; local configuration cannot relax managed restrictions. |
| `computer_use.macos.bundle_ids` | `map<string, allow \| deny>` | Native macOS app access keyed by bundle identifier. |
| `computer_use.windows.aumids` | `map<string, allow \| deny>` | Packaged Windows app access keyed by Application User Model ID (AUMID). |
| `computer_use.windows.exes` | `array<table>` | Windows executable access rules. Each rule requires `publisher_name`, `product_name`, and `access` (`allow` or `deny`); `binary_name` is optional. |
| `computer_use.windows.always_allowed_app_ids` | `array<string>` | Windows app identifiers that Computer Use can open without prompting. Apps not in the list require approval; remove saved entries from the ChatGPT desktop app's Computer Use settings. |
| `notify` | `array<string>` | Command invoked for notifications; receives a JSON payload from Codex. |
| `check_for_update_on_startup` | `boolean` | Check for Codex updates on startup (set to false only when updates are centrally managed). |
| `feedback.enabled` | `boolean` | Enable feedback submission via `/feedback` across local clients (default: true). |
| `analytics.enabled` | `boolean` | Enable or disable analytics for this machine/profile. When unset, the client default applies. |
| `instructions` | `string` | Reserved for future use; prefer `model_instructions_file` or `AGENTS.md`. |
| `developer_instructions` | `string` | Additional developer instructions injected into the session (optional). |
| `log_dir` | `string (path)` | Directory where Codex writes log files; defaults to `$CODEX_HOME/log`. Setting this explicitly also enables the opt-in plaintext TUI log, `codex-tui.log`, in that directory. |
| `sqlite_home` | `string (path)` | Directory where Codex stores the SQLite-backed state DB used by agent jobs and other resumable runtime state. |
| `compact_prompt` | `string` | Inline override for the history compaction prompt. |
| `model_instructions_file` | `string (path)` | Replacement for built-in instructions instead of `AGENTS.md`. |
| `personality` | `none \| friendly \| pragmatic` | Default communication style for models that advertise `supportsPersonality`; can be overridden per thread/turn or via `/personality`. |
| `service_tier` | `string` | Preferred service tier for new turns. Use `fast` or another tier advertised by the active model; `fast` maps to the request value `priority`. |
| `experimental_compact_prompt_file` | `string (path)` | Load the compaction prompt override from a file (experimental). |
| `skills.max_context_tokens` | `integer (positive)` | Token budget for the available-skills catalog. Defaults to 2% of the model's context window. Explicit values are capped at `10000` tokens. |
| `skills.config` | `array<object>` | Per-skill enablement overrides stored in config.toml. |
| `skills.config.<index>.path` | `string (path)` | Path to a skill folder containing `SKILL.md`. |
| `skills.config.<index>.enabled` | `boolean` | Enable or disable the referenced skill. |
| `apps.<id>.enabled` | `boolean` | Enable or disable a specific app/connector by id (default: true). |
| `apps._default.enabled` | `boolean` | Default app enabled state for all apps unless overridden per app. |
| `apps._default.destructive_enabled` | `boolean` | Default allow/deny for app tools with `destructive_hint = true`. |
| `apps._default.open_world_enabled` | `boolean` | Default allow/deny for app tools with `open_world_hint = true`. |
| `apps._default.approvals_reviewer` | `user \| auto_review` | Default reviewer for app tool approval prompts unless overridden per app. When omitted, apps inherit the top-level `approvals_reviewer` value. |
| `apps._default.default_tools_approval_mode` | `auto \| prompt \| writes \| approve` | Default approval behavior for app tools without per-app or per-tool overrides. |
| `apps.<id>.destructive_enabled` | `boolean` | Allow or block tools in this app that advertise `destructive_hint = true`. |
| `apps.<id>.open_world_enabled` | `boolean` | Allow or block tools in this app that advertise `open_world_hint = true`. |
| `apps.<id>.default_tools_enabled` | `boolean` | Default enabled state for tools in this app unless a per-tool override exists. |
| `apps.<id>.approvals_reviewer` | `user \| auto_review` | Reviewer for this app's tool approval prompts. Overrides `apps._default.approvals_reviewer`. |
| `apps.<id>.default_tools_approval_mode` | `auto \| prompt \| writes \| approve` | Default approval behavior for tools in this app unless a per-tool override exists. |
| `apps.<id>.tools.<tool>.enabled` | `boolean` | Per-tool enabled override for an app tool (for example `repos/list`). |
| `apps.<id>.tools.<tool>.approval_mode` | `auto \| prompt \| writes \| approve` | Per-tool approval behavior override for a single app tool. |
| `tool_suggest.discoverables` | `array<table>` | Allow tool suggestions for additional discoverable connectors or plugins. Each entry uses `type = "connector"` or `"plugin"` and an `id`. |
| `tool_suggest.disabled_tools` | `array<table>` | Disable suggestions for specific discoverable connectors or plugins. Each entry uses `type = "connector"` or `"plugin"` and an `id`. |
| `features.apps` | `boolean` | Enable app (connector) integrations (stable; on by default). App and connector traffic is not controlled by the sandboxed-command network proxy or its domain allowlist. |
| `features.hooks` | `boolean` | Enable lifecycle hooks loaded from `hooks.json` or inline `[hooks]` config. `features.codex_hooks` is a deprecated alias. |
| `features.code_mode.enabled` | `boolean` | Enable code mode feature configuration. This feature is under development and off by default. |
| `features.code_mode.excluded_tool_namespaces` | `array<string>` | Tool namespaces code mode excludes from nested code-mode tool guidance and executor exposure. |
| `features.code_mode.direct_only_tool_namespaces` | `array<string>` | Tool namespaces code mode can use only through direct tool calls. |
| `features.context_management.experimental_mode` | `boolean` | Enable experimental context management (off by default). Rather than repeatedly compressing context into a single summary, it uses notes and searchable history to preserve accumulated details. Requires ChatGPT sign-in on Plus, Pro, or Pro Lite. |
| `features.rollout_budget.enabled` | `boolean` | Enable rollout budget tracking. This feature is under development and off by default. When enabled, `features.rollout_budget.limit_tokens` is required. |
| `features.rollout_budget.limit_tokens` | `integer` | Positive token limit for rollout budget tracking. Required when rollout budget is enabled. |
| `features.rollout_budget.reminder_interval_tokens` | `integer` | Positive token interval between rollout budget reminders. Defaults to 10% of `limit_tokens`, with a minimum of 1 token. |
| `features.rollout_budget.sampling_token_weight` | `number` | Finite non-negative multiplier for sampled tokens in rollout budget accounting. Defaults to `1.0`. |
| `features.rollout_budget.prefill_token_weight` | `number` | Finite non-negative multiplier for prefill tokens in rollout budget accounting. Defaults to `1.0`. |
| `hooks` | `table` | Lifecycle hooks configured inline in `config.toml`. Uses the same event schema as `hooks.json`; see the Hooks guide for examples and supported events. |
| `hooks.<Event>` | `array<table>` | Matcher groups for hook events such as `PreToolUse`, `PermissionRequest`, `PostToolUse`, `PreCompact`, `PostCompact`, `SessionStart`, `SessionEnd`, `SubagentStart`, `SubagentStop`, `UserPromptSubmit`, `Stop`, or `Interrupt`. |
| `hooks.<Event>[].hooks` | `array<table>` | Hook handlers for a matcher group. Command and MCP tool hooks are supported while prompt and agent hook handlers are parsed but skipped. |
| `hooks.<Event>[].hooks[].async` | `boolean` | Run a command hook in the background without delaying the triggering operation. Defaults to `false`; `SessionEnd` always runs synchronously. See [Run hooks in the background](./hooks.md#run-hooks-in-the-background). |
| `hooks.<Event>[].hooks[].additionalContextLimit` | `integer` | Approximate per-handler token threshold for saving oversized `additionalContext` to disk and showing the model a shorter preview. Defaults to `2500`; `0` passes the full context directly to the model. See [Large hook output](./hooks.md#large-hook-output). |
| `hooks.<Event>[].hooks[].commandWindows` | `string` | Windows-only command override for command hooks. The TOML alias `command_windows` is also accepted. |
| `features.memories` | `boolean` | Enable [Memories](./customization/memories.md) (off by default). |
| `mcp_optional_startup_grace_ms` | `integer (milliseconds)` | Shared wait for optional MCP servers when building the initial tool catalog. Defaults to `1000`. Set to `0` to wait for each server's `startup_timeout_sec` instead. |
| `mcp_servers.<id>.command` | `string` | Launcher command for an MCP stdio server. |
| `mcp_servers.<id>.args` | `array<string>` | Arguments passed to the MCP stdio server command. |
| `mcp_servers.<id>.env` | `map<string,string>` | Environment variables forwarded to the MCP stdio server. |
| `mcp_servers.<id>.env_vars` | `array<string \| { name = string, source = "local" \| "remote" }>` | Additional environment variables to whitelist for an MCP stdio server. String entries default to `source = "local"`; use `source = "remote"` only with executor-backed remote stdio. |
| `mcp_servers.<id>.cwd` | `string` | Working directory for the MCP stdio server process. |
| `mcp_servers.<id>.url` | `string` | Endpoint for an MCP streamable HTTP server. |
| `mcp_servers.<id>.auth` | `oauth \| chatgpt` | Authentication fallback for an MCP HTTP server after configured bearer tokens and authorization headers. `oauth` (default) uses stored MCP OAuth credentials when available. `chatgpt` uses the current ChatGPT session for the trusted first-party ChatGPT origin, then falls back to stored OAuth. Both modes can connect without authentication if no credential source resolves. |
| `mcp_servers.<id>.oauth.client_id` | `string` | Pre-registered OAuth client ID used for authorization and token exchange with this MCP server. |
| `mcp_servers.<id>.oauth.callback_url` | `string` | Server-specific OAuth callback. Pre-registered clients reuse it when issuer identification is supported or the URL already ends in the server-specific callback ID. Otherwise, Codex uses the global or default callback with that ID appended. Clients without a pre-registered ID use this callback during client registration. |
| `mcp_servers.<id>.oauth.callback_port` | `integer` | Fixed OAuth callback listener port for this MCP server. Overrides `mcp_oauth_callback_port`. For a direct loopback callback with an explicit URL port, configure the same listener port. |
| `mcp_servers.<id>.bearer_token_env_var` | `string` | Environment variable sourcing the bearer token for an MCP HTTP server. |
| `mcp_servers.<id>.http_headers` | `map<string,string>` | Static HTTP headers included with each MCP HTTP request. |
| `mcp_servers.<id>.http_headers_helper` | `string (command)` | Local command that prints a JSON object of HTTP header names and values. Supported only for locally connected HTTP MCP servers. Explicit bearer tokens and OAuth credentials take precedence over helper-provided Authorization headers. |
| `mcp_servers.<id>.env_http_headers` | `map<string,string>` | HTTP headers populated from environment variables for an MCP HTTP server. |
| `mcp_servers.<id>.enabled` | `boolean` | Disable an MCP server without removing its configuration. |
| `mcp_servers.<id>.required` | `boolean` | When true, fail startup/resume if this enabled MCP server cannot initialize. |
| `mcp_servers.<id>.startup_timeout_sec` | `number` | Override the default 10s startup timeout for an MCP server. |
| `mcp_servers.<id>.startup_timeout_ms` | `number` | Alias for `startup_timeout_sec` in milliseconds. |
| `mcp_servers.<id>.tool_timeout_sec` | `number` | Override the default 60s per-tool timeout for an MCP server. |
| `mcp_servers.<id>.enabled_tools` | `array<string>` | Allow list of tool names exposed by the MCP server. |
| `mcp_servers.<id>.disabled_tools` | `array<string>` | Deny list applied after `enabled_tools` for the MCP server. |
| `mcp_servers.<id>.default_tools_approval_mode` | `auto \| prompt \| writes \| approve` | Default approval behavior for MCP tools on this server unless a per-tool override exists. |
| `mcp_servers.<id>.tools.<tool>.approval_mode` | `auto \| prompt \| writes \| approve` | Per-tool approval behavior override for one MCP tool on this server. |
| `mcp_servers.<id>.tools.<tool>.output_token_limit` | `integer (positive)` | Token budget for one MCP tool's output, before the standard 20% serialization allowance. Overrides the model's default output truncation budget for that tool. |
| `mcp_servers.<id>.scopes` | `array<string>` | OAuth scopes to request when authenticating to that MCP server. |
| `mcp_servers.<id>.oauth_resource` | `string` | Optional RFC 8707 OAuth resource parameter to include during MCP login. |
| `mcp_servers.<id>.experimental_environment` | `local \| remote` | Experimental placement for an MCP server. `remote` starts stdio servers through a remote executor environment; streamable HTTP remote placement is not implemented. |
| `agents` | `table` | Multi-agent settings and custom role declarations. Scalar setting names are reserved and can't be used as custom role names. |
| `agents.enabled` | `boolean` | Enable or disable multi-agent tools (default: true). |
| `agents.max_concurrent_threads_per_session` | `number` | Maximum number of spawned-agent threads that can be open concurrently, excluding the primary thread. When unset, Codex chooses the default. |
| `agents.max_threads` | `number` | Legacy alias for `agents.max_concurrent_threads_per_session`. |
| `agents.default_subagent_model` | `string` | Default model for spawned agents. An explicit spawn model takes precedence. |
| `agents.default_subagent_reasoning_effort` | `string` | Default reasoning effort for spawned agents. An explicit spawn effort takes precedence. |
| `agents.interrupt_message` | `boolean` | Record a model-visible message when an agent turn is interrupted (default: true). |
| `agents.<name>.description` | `string` | Role guidance shown to Codex when choosing and spawning that agent type. |
| `agents.<name>.config_file` | `string (path)` | Path to a TOML config layer for that role; relative paths resolve from the config file that declares the role. |
| `memories.generate_memories` | `boolean` | When `false`, newly created threads are not stored as memory-generation inputs. Defaults to `true`. |
| `memories.use_memories` | `boolean` | When `false`, Codex skips injecting existing memories into future sessions. Defaults to `true`. |
| `memories.disable_on_external_context` | `boolean` | When `true`, threads that use external context such as MCP tool calls, web search, or tool search are kept out of memory generation. Defaults to `false`. Legacy alias: `memories.no_memories_if_mcp_or_web_search`. |
| `memories.max_raw_memories_for_consolidation` | `number` | Maximum recent raw memories retained for global consolidation. Defaults to `256` and is capped at `4096`. |
| `memories.max_unused_days` | `number` | Maximum days since a memory was last used before it becomes ineligible for consolidation. Defaults to `30` and is clamped to `0`-`365`. |
| `memories.max_rollout_age_days` | `number` | Maximum age of threads considered for memory generation. Defaults to `30` and is clamped to `0`-`90`. |
| `memories.max_rollouts_per_startup` | `number` | Maximum rollout candidates processed per startup pass. Defaults to `16` and is capped at `128`. |
| `memories.min_rollout_idle_hours` | `number` | Minimum idle time before a thread is considered for memory generation. Defaults to `6` and is clamped to `1`-`48`. |
| `memories.min_rate_limit_remaining_percent` | `number` | Minimum remaining percentage required in Codex rate-limit windows before memory generation starts. Defaults to `25` and is clamped to `0`-`100`. |
| `memories.extract_model` | `string` | Optional model override for per-thread memory extraction. |
| `memories.consolidation_model` | `string` | Optional model override for global memory consolidation. |
| `features.unified_exec` | `boolean` | Use the unified PTY-backed exec tool (stable; enabled by default except on Windows). |
| `features.shell_snapshot` | `boolean` | Snapshot shell environment to speed up repeated commands (stable; on by default). |
| `features.multi_agent` | `boolean` | Enable multi-agent collaboration tools (`spawn_agent`, `send_input`, `resume_agent`, `wait_agent`, and `close_agent`) (stable; on by default). |
| `features.goals` | `boolean` | Enable persisted goals and automatic continuation (stable; on by default). |
| `features.remote_plugin` | `boolean` | Enable the remote plugin catalog (stable; on by default). |
| `features.personality` | `boolean` | Enable personality selection controls (stable; on by default). |
| `features.network_proxy` | `boolean \| table` | Start the network proxy for sandboxed commands (experimental; off by default). Required to enforce permission-profile domain rules unless enabled administrator-managed `experimental_network` requirements start the proxy. Use a table when setting feature-level policy options such as `domains`. Does not filter web search, apps, MCP, or other hosted tools. |
| `features.network_proxy.enabled` | `boolean` | Start the sandboxed-command network proxy when command network access is enabled. Defaults to `false`; permission-profile domain rules are not enforced while the proxy is off. |
| `features.network_proxy.domains` | `map<string, allow \| deny>` | Domain policy for sandboxed networking. Unset by default, which means no external destinations are allowed until you add `allow` rules. Supports exact hosts, `*.example.com` for subdomains only, `**.example.com` for apex plus subdomains, and global `*` allow rules; prefer scoped rules because `*` broadly opens public outbound access. Add `deny` rules for blocked destinations; `deny` wins on conflicts. |
| `features.network_proxy.unix_sockets` | `map<string, allow \| deny>` | Unix socket policy for sandboxed networking. Unset by default; add `allow` entries for permitted sockets. |
| `features.network_proxy.allow_local_binding` | `boolean` | Allow broader local/private-network access. Defaults to `false`; exact local IP literal or `localhost` allow rules can still permit specific local targets. |
| `features.network_proxy.enable_socks5` | `boolean` | Expose SOCKS5 support. Defaults to `true`. |
| `features.network_proxy.enable_socks5_udp` | `boolean` | Allow UDP over SOCKS5. Defaults to `true`. |
| `features.network_proxy.allow_upstream_proxy` | `boolean` | Allow chaining through an upstream proxy from the environment. Defaults to `true`. |
| `features.network_proxy.dangerously_allow_non_loopback_proxy` | `boolean` | Permit non-loopback listener addresses. Defaults to `false`; enabling it can expose proxy listeners beyond localhost. |
| `features.network_proxy.dangerously_allow_all_unix_sockets` | `boolean` | Permit arbitrary Unix socket destinations instead of allowlist-only access. Defaults to `false`; use only in tightly controlled environments. |
| `features.network_proxy.proxy_url` | `string` | HTTP listener URL for sandboxed networking. Defaults to `"http://127.0.0.1:3128"`. |
| `features.network_proxy.socks_url` | `string` | SOCKS5 listener URL. Defaults to `"http://127.0.0.1:8081"`. |
| `features.web_search` | `boolean` | Deprecated legacy toggle; prefer the top-level `web_search` setting. |
| `features.web_search_cached` | `boolean` | Deprecated legacy toggle. When `web_search` is unset, true maps to `web_search = "cached"`. |
| `features.web_search_request` | `boolean` | Deprecated legacy toggle. When `web_search` is unset, true maps to `web_search = "live"`. |
| `features.shell_tool` | `boolean` | Enable the default `shell` tool for running commands (stable; on by default). |
| `features.enable_request_compression` | `boolean` | Compress streaming request bodies with zstd when supported (stable; on by default). |
| `features.skill_mcp_dependency_install` | `boolean` | Allow prompting and installing missing MCP dependencies for skills (stable; on by default). |
| `features.fast_mode` | `boolean` | Enable model-catalog service tier selection in the TUI, including Fast-tier commands when the active model advertises them (stable; on by default). |
| `features.prevent_idle_sleep` | `boolean` | Prevent the machine from sleeping while a turn is actively running (experimental; off by default). |
| `suppress_unstable_features_warning` | `boolean` | Suppress the warning that appears when under-development feature flags are enabled. |
| `model_providers.<id>` | `table` | Custom provider definition. Built-in provider IDs (`openai`, `ollama`, and `lmstudio`) are reserved and cannot be overridden. |
| `model_providers.<id>.name` | `string` | Display name for a custom model provider. |
| `model_providers.<id>.base_url` | `string` | API base URL for the model provider. |
| `model_providers.<id>.env_key` | `string` | Environment variable supplying the provider API key. |
| `model_providers.<id>.env_key_instructions` | `string` | Optional setup guidance for the provider API key. |
| `model_providers.<id>.experimental_bearer_token` | `string` | Direct bearer token for the provider (discouraged; use `env_key`). |
| `model_providers.<id>.requires_openai_auth` | `boolean` | The provider uses OpenAI authentication (defaults to false). |
| `model_providers.<id>.wire_api` | `responses` | Protocol used by the provider. `responses` is the only supported value, and it is the default when omitted. |
| `model_providers.<id>.query_params` | `map<string,string>` | Extra query parameters appended to provider requests. |
| `model_providers.<id>.http_headers` | `map<string,string>` | Static HTTP headers added to provider requests. |
| `model_providers.<id>.env_http_headers` | `map<string,string>` | HTTP headers populated from environment variables when present. |
| `model_providers.<id>.request_max_retries` | `number` | Retry count for HTTP requests to the provider (default: 4). |
| `model_providers.<id>.stream_max_retries` | `number` | Retry count for SSE streaming interruptions (default: 5). |
| `model_providers.<id>.stream_idle_timeout_ms` | `number` | Idle timeout for SSE streams in milliseconds (default: 300000). |
| `model_providers.<id>.supports_websockets` | `boolean` | Whether that provider supports the Responses API WebSocket transport. |
| `model_providers.<id>.supports_standalone_web_search` | `boolean` | Advertise support for a compatible standalone web search endpoint (default: false). Standalone search remains under development and off by default; provider compatibility alone doesn't enable it. |
| `model_providers.<id>.auth` | `table` | Command-backed bearer token configuration for a custom provider. Do not combine with `env_key`, `experimental_bearer_token`, or `requires_openai_auth`. |
| `model_providers.<id>.auth.command` | `string` | Command to run when Codex needs a bearer token. The command must print the token to stdout. |
| `model_providers.<id>.auth.args` | `array<string>` | Arguments passed to the token command. |
| `model_providers.<id>.auth.timeout_ms` | `number` | Maximum token command runtime in milliseconds (default: 5000). |
| `model_providers.<id>.auth.refresh_interval_ms` | `number` | How often Codex proactively refreshes the token in milliseconds (default: 300000). Set to `0` to refresh only after an authentication retry. |
| `model_providers.<id>.auth.cwd` | `string (path)` | Working directory for the token command. |
| `model_providers.amazon-bedrock.aws.profile` | `string` | AWS profile name used by the built-in `amazon-bedrock` provider. |
| `model_providers.amazon-bedrock.aws.region` | `string` | AWS region used by the built-in `amazon-bedrock` provider. |
| `model_reasoning_effort` | `minimal \| low \| medium \| high \| xhigh` | Adjust reasoning effort for supported models (Responses API only; `xhigh` is model-dependent). |
| `plan_mode_reasoning_effort` | `none \| minimal \| low \| medium \| high \| xhigh` | Plan-mode-specific reasoning override. When unset, Plan mode uses its built-in preset default. |
| `model_reasoning_summary` | `auto \| concise \| detailed \| none` | Select reasoning summary detail or disable summaries entirely. |
| `model_verbosity` | `low \| medium \| high` | Optional GPT-5 Responses API verbosity override; when unset, the selected model/preset default is used. |
| `model_supports_reasoning_summaries` | `boolean` | Force Codex to send or not send reasoning metadata. |
| `shell_environment_policy.inherit` | `all \| core \| none` | Baseline environment inheritance when spawning subprocesses. |
| `shell_environment_policy.ignore_default_excludes` | `boolean` | Keep variables containing KEY, SECRET, or TOKEN before other filters run (default: true). Set to false to apply automatic secret-name exclusions. |
| `shell_environment_policy.filters` | `map<string, include \| exclude>` | Canonical case-insensitive environment-variable pattern filters. Include entries create an allowlist and can't restore excluded values. Explicit `set` values apply after exclusions. Don't combine filters with legacy `exclude` or `include_only` arrays in the same layer. |
| `shell_environment_policy.exclude` | `array<string>` | Legacy environment-variable exclusion patterns. Use `shell_environment_policy.filters` for new configuration; don't combine both forms in the same layer. |
| `shell_environment_policy.include_only` | `array<string>` | Legacy allowlist of environment-variable patterns. Use `shell_environment_policy.filters` for new configuration; don't combine both forms in the same layer. |
| `shell_environment_policy.set` | `map<string,string>` | Explicit environment values injected after exclusions; include filters can still remove them. |
| `shell_environment_policy.experimental_use_profile` | `boolean` | Use the user shell profile when spawning subprocesses. |
| `project_root_markers` | `array<string>` | List of project root marker filenames; used when searching parent directories for the project root. |
| `project_doc_max_bytes` | `number` | Maximum bytes read from `AGENTS.md` when building project instructions. |
| `project_doc_fallback_filenames` | `array<string>` | Additional filenames to try when `AGENTS.md` is missing. |
| `history.persistence` | `save-all \| none` | Control whether Codex saves session transcripts to history.jsonl. |
| `tool_output_token_limit` | `number` | Token budget for storing individual tool/function outputs in history. |
| `background_terminal_max_timeout` | `number` | Maximum poll window in milliseconds for empty `write_stdin` polls (background terminal polling). Default: `300000` (5 minutes). Replaces the older `background_terminal_timeout` key. |
| `history.max_bytes` | `number` | If set, caps the history file size in bytes by dropping oldest entries. |
| `file_opener` | `vscode \| vscode-insiders \| windsurf \| cursor \| none` | URI scheme used to open citations from Codex output (default: `vscode`). |
| `otel.environment` | `string` | Environment tag applied to emitted OpenTelemetry events (default: `dev`). |
| `otel.exporter` | `none \| otlp-http \| otlp-grpc` | Select the OpenTelemetry exporter and provide any endpoint metadata. |
| `otel.trace_exporter` | `none \| otlp-http \| otlp-grpc` | Select the OpenTelemetry trace exporter and provide any endpoint metadata. |
| `otel.metrics_exporter` | `none \| statsig \| otlp-http \| otlp-grpc` | Select the OpenTelemetry metrics exporter (defaults to `statsig`). |
| `otel.log_user_prompt` | `boolean` | Opt in to exporting raw user prompts with OpenTelemetry logs. |
| `otel.exporter.<id>.endpoint` | `string` | Exporter endpoint for OTEL logs. |
| `otel.exporter.<id>.protocol` | `binary \| json` | Protocol used by the OTLP/HTTP exporter. |
| `otel.exporter.<id>.headers` | `map<string,string>` | Static headers included with OTEL exporter requests. |
| `otel.trace_exporter.<id>.endpoint` | `string` | Trace exporter endpoint for OTEL logs. |
| `otel.trace_exporter.<id>.protocol` | `binary \| json` | Protocol used by the OTLP/HTTP trace exporter. |
| `otel.trace_exporter.<id>.headers` | `map<string,string>` | Static headers included with OTEL trace exporter requests. |
| `otel.exporter.<id>.tls.ca-certificate` | `string` | CA certificate path for OTEL exporter TLS. |
| `otel.exporter.<id>.tls.client-certificate` | `string` | Client certificate path for OTEL exporter TLS. |
| `otel.exporter.<id>.tls.client-private-key` | `string` | Client private key path for OTEL exporter TLS. |
| `otel.trace_exporter.<id>.tls.ca-certificate` | `string` | CA certificate path for OTEL trace exporter TLS. |
| `otel.trace_exporter.<id>.tls.client-certificate` | `string` | Client certificate path for OTEL trace exporter TLS. |
| `otel.trace_exporter.<id>.tls.client-private-key` | `string` | Client private key path for OTEL trace exporter TLS. |
| `desktop.custom_file_handlers.<id>` | `table` | User-level only. Defines an additional **Open in** target for the ChatGPT desktop app. See [Add custom file handlers](./config-file/config-advanced.md#add-custom-file-handlers) for examples and handler ID constraints. |
| `desktop.custom_file_handlers.<id>.label` | `string` | Display name shown in **Open in** menus. Required. |
| `desktop.custom_file_handlers.<id>.icon` | `string` | Bundled asset path, Base64-encoded `data:image/...` URL, file URI, or absolute local path for the handler icon. Required; unsupported sources use the default VS Code icon. |
| `desktop.custom_file_handlers.<id>.command` | `string` | Executable path or command name to detect and launch. Required. |
| `desktop.custom_file_handlers.<id>.args` | `array<string>` | Arguments inserted between the command and file input (default: `[]`). |
| `desktop.custom_file_handlers.<id>.input` | `path \| json_argument \| json_stdin` | How the app sends file input to the handler (default: `path`). |
| `desktop.custom_file_handlers.<id>.supports_ssh` | `boolean` | Offer the handler for files in SSH workspaces (default: `false`). |
| `tui` | `table` | TUI-specific options such as enabling inline desktop notifications. |
| `tui.notifications` | `boolean \| array<string>` | Enable TUI notifications; optionally restrict to specific event types. |
| `tui.notification_method` | `auto \| osc9 \| bel` | Notification method for terminal notifications (default: auto). |
| `tui.notification_condition` | `unfocused \| always` | Control whether TUI notifications fire only when the terminal is unfocused or regardless of focus. Defaults to `unfocused`. |
| `tui.animations` | `boolean` | Enable terminal animations (welcome screen, shimmer, spinner) (default: true). |
| `tui.alternate_screen` | `auto \| always \| never` | Control alternate screen usage for the TUI (default: auto; auto skips it in Zellij to preserve scrollback). |
| `tui.resume_cwd` | `current \| session` | Working directory to use when resuming or forking a session. When unset, Codex asks you to choose if your current directory differs from the session's saved directory. |
| `tui.vim_mode_default` | `boolean` | Start the composer in Vim normal mode instead of insert mode (default: false). You can still toggle it per session with `/vim`. |
| `tui.raw_output_mode` | `boolean` | Start the TUI in raw scrollback mode for copy-friendly terminal selection (default: false). You can toggle it with `/raw` or the default `alt-r` key binding. |
| `tui.show_tooltips` | `boolean` | Show onboarding tooltips in the TUI welcome screen (default: true). |
| `tui.status_line` | `array<string> \| null` | Ordered list of TUI footer status-line item identifiers. `null` disables the status line. |
| `tui.terminal_title` | `array<string> \| null` | Ordered list of terminal window/tab title item identifiers. Defaults to `["spinner", "project"]`; `null` disables title updates. |
| `tui.theme` | `string` | Syntax-highlighting theme override (kebab-case theme name). |
| `tui.keymap.<context>.<action>` | `string \| array<string>` | Keyboard shortcut binding for a TUI action. Supported contexts include `global`, `chat`, `composer`, `editor`, `vim_normal`, `vim_operator`, `vim_text_object`, `pager`, `list`, and `approval`. Selected composer actions fall back to matching `tui.keymap.global` bindings; context-specific bindings take precedence when supported. |
| `tui.keymap.<context>.<action> = []` | `empty array` | Unbind the action in that keymap context. Key names use normalized strings such as `ctrl-a`, `shift-enter`, `page-down`, or `minus`. |
| `marketplaces.<name>.source_type` | `git \| local` | Source kind for a configured plugin marketplace. Marketplaces can be defined in system, cloud-managed, user, or trusted-project config.toml. |
| `marketplaces.<name>.source` | `string` | Git repository location or local marketplace root directory. Use an absolute path for a local source; the directory contains .agents/plugins/marketplace.json. |
| `marketplaces.<name>.ref` | `string` | Optional Git branch, tag, or commit for the marketplace. |
| `marketplaces.<name>.sparse_paths` | `array<string>` | Optional sparse checkout paths for a Git marketplace. Include the marketplace catalog and any local plugin directories it references. |
| `plugins.<plugin>.enabled` | `boolean` | Enable or disable a local-marketplace plugin using a `plugin-name@marketplace-name` key. Read from the effective merged config; trusted-project settings can override user, cloud-managed, and system defaults. Marketplace refresh can install or refresh configured plugins even when disabled. This does not override workspace-managed enabled states. |
| `plugins.<plugin>.mcp_servers.<server>.enabled` | `boolean` | Enable or disable an MCP server bundled by an installed plugin without changing the plugin manifest. |
| `plugins.<plugin>.mcp_servers.<server>.default_tools_approval_mode` | `auto \| prompt \| writes \| approve` | Default approval behavior for tools on a plugin-provided MCP server. |
| `plugins.<plugin>.mcp_servers.<server>.enabled_tools` | `array<string>` | Allow list of tools exposed from a plugin-provided MCP server. |
| `plugins.<plugin>.mcp_servers.<server>.disabled_tools` | `array<string>` | Deny list applied after `enabled_tools` for a plugin-provided MCP server. |
| `plugins.<plugin>.mcp_servers.<server>.tools.<tool>.approval_mode` | `auto \| prompt \| writes \| approve` | Per-tool approval behavior override for a plugin-provided MCP tool. |
| `tui.model_availability_nux.<model>` | `integer` | Internal startup-tooltip state keyed by model slug. |
| `hide_agent_reasoning` | `boolean` | Suppress reasoning events in both the TUI and `codex exec` output. |
| `show_raw_agent_reasoning` | `boolean` | Surface raw reasoning content when the active model emits it. |
| `disable_paste_burst` | `boolean` | Disable burst-paste detection in the TUI. |
| `windows_wsl_setup_acknowledged` | `boolean` | Track Windows onboarding acknowledgement (Windows only). |
| `chatgpt_base_url` | `string` | Override the base URL used during the ChatGPT login flow. |
| `cli_auth_credentials_store` | `file \| keyring \| auto \| ephemeral` | Control where the CLI stores cached credentials. |
| `mcp_oauth_credentials_store` | `auto \| file \| keyring` | Preferred store for MCP OAuth credentials. |
| `mcp_oauth_callback_port` | `integer` | Optional global fixed port for the local HTTP callback server used during MCP OAuth login. A server-specific `oauth.callback_port` takes precedence. When neither is set, Codex binds to an ephemeral port chosen by the OS. |
| `mcp_oauth_callback_url` | `string` | Optional base callback URL for MCP OAuth login, such as a devbox ingress URL. Newly added pre-registered clients use this URL unchanged when the authorization server supports issuer identification; existing clients without a saved callback append a server-specific callback ID. Without issuer support, any pre-registered MCP server whose configured callback lacks the required ID falls back to this URL with the ID appended. Callback URL ports don't select the listener port. |
| `experimental_use_unified_exec_tool` | `boolean` | Legacy name for enabling unified exec; prefer `[features].unified_exec` or `codex --enable unified_exec`. |
| `tools.web_search` | `boolean \| { context_size = "low\|medium\|high", allowed_domains = [string], location = { country, region, city, timezone } }` | Optional web search tool configuration. The object form can set search context size, allowed search domains, and approximate user location. These search-domain filters are separate from sandboxed-command network domain rules and do not restrict connectors or MCP servers. |
| `tools.view_image` | `boolean` | Enable the local-image attachment tool `view_image`. |
| `web_search` | `disabled \| cached \| indexed \| live` | Web search mode (default: `"cached"`; cached uses an OpenAI-maintained index without external web access; indexed permits external access only when gated by the search index; if you use `--yolo` or another full access sandbox setting, it defaults to `"live"`). Use `"live"` for unrestricted live retrieval, or `"disabled"` to remove the tool. |
| `default_permissions` | `string` | Name of the default permissions profile to apply to sandboxed tool calls. Built-ins are `:read-only`, `:workspace`, and `:danger-full-access`; custom profile names require matching `[permissions.<name>]` tables. Don't combine with `sandbox_mode` or `[sandbox_workspace_write]`. |
| `permissions.<name>.description` | `string` | Human-readable description for this named profile. A profile does not inherit its parent's description through `extends`. |
| `permissions.<name>.extends` | `string` | Optional parent profile applied before this named profile. Set it to another named profile, `:read-only`, or `:workspace`; `:danger-full-access`, undefined parents, and cycles are rejected. |
| `permissions.<name>.workspace_roots` | `table` | Profile-defined workspace roots that receive `:workspace_roots` filesystem rules alongside the session's runtime workspace roots. |
| `permissions.<name>.workspace_roots.<path>` | `boolean` | Opt a path into the profile's workspace root set when `true`. Disabled entries remain inactive. |
| `permissions.<name>.filesystem` | `table` | Named filesystem permission profile. Each key is an absolute path or special token such as `:minimal` or `:workspace_roots`. |
| `permissions.<name>.filesystem.glob_scan_max_depth` | `number` | Maximum depth for expanding deny-read glob patterns on platforms that snapshot matches before sandbox startup. Must be at least `1` when set. |
| `permissions.<name>.filesystem.<path-or-glob>` | `"read" \| "write" \| "deny" \| table` | Grant direct access for a path, glob pattern, or special token, or scope nested entries under that root. Use `"deny"` to deny reads for matching paths. |
| `permissions.<name>.filesystem.":workspace_roots".<subpath-or-glob>` | `"read" \| "write" \| "deny"` | Scoped filesystem access relative to each effective workspace root. Use `"."` for the root itself; glob subpaths such as `"**/*.env"` can deny reads with `"deny"`. |
| `permissions.<name>.network.enabled` | `boolean` | Enable network access for commands in this permission profile. This does not start the network proxy. Without `features.network_proxy` or enabled administrator-managed networking requirements, command network access is direct and profile domain rules are not enforced. |
| `permissions.<name>.network.proxy_url` | `string` | HTTP listener URL used when this permissions profile enables sandboxed networking. |
| `permissions.<name>.network.enable_socks5` | `boolean` | Expose SOCKS5 support when this permissions profile enables sandboxed networking. |
| `permissions.<name>.network.socks_url` | `string` | SOCKS5 proxy endpoint used by this permissions profile. |
| `permissions.<name>.network.enable_socks5_udp` | `boolean` | Allow UDP over the SOCKS5 listener when enabled. |
| `permissions.<name>.network.allow_upstream_proxy` | `boolean` | Allow sandboxed networking to chain through another upstream proxy. |
| `permissions.<name>.network.dangerously_allow_non_loopback_proxy` | `boolean` | Permit non-loopback bind addresses for sandboxed networking listeners. Enabling it can expose listeners beyond localhost. |
| `permissions.<name>.network.dangerously_allow_all_unix_sockets` | `boolean` | Allow arbitrary Unix socket destinations instead of the default restricted set. Use only in tightly controlled environments. |
| `permissions.<name>.network.mode` | `limited \| full` | Network proxy mode used for subprocess traffic. |
| `permissions.<name>.network.domains` | `table` | Domain rules for sandboxed commands. Enforced only when `features.network_proxy` or enabled administrator-managed networking requirements activate the proxy. Supports exact hosts, `*.example.com`, `**.example.com`, and global `*` allow rules; `deny` wins. Does not restrict web search, apps, or MCP servers. |
| `permissions.<name>.network.domains.<pattern>` | `allow \| deny` | Allow or deny an exact host or scoped wildcard pattern such as `*.example.com` or `**.example.com`. |
| `permissions.<name>.network.unix_sockets` | `table` | Unix socket allowlist overrides for sandboxed networking. Use socket paths as keys; `allow` adds a path, and `deny` rejects it. |
| `permissions.<name>.network.unix_sockets.<path>` | `allow \| deny` | Add an absolute Unix socket path to the effective allowlist with `allow`, or reject it with `deny`. Denied entries are omitted from the effective allowlist. |
| `permissions.<name>.network.allow_local_binding` | `boolean` | Permit broader local/private-network access through sandboxed networking. Exact local IP literal or `localhost` allow rules can still permit specific local targets when this stays `false`. |
| `projects.<path>.trust_level` | `string` | Mark a project or worktree as trusted or untrusted (`"trusted"` \| `"untrusted"`). Untrusted projects skip project-scoped `.codex/` layers, including project-local config, hooks, and rules. |
| `notice.hide_full_access_warning` | `boolean` | Track acknowledgement of the full access warning prompt. |
| `notice.hide_world_writable_warning` | `boolean` | Track acknowledgement of the Windows world-writable directories warning. |
| `notice.hide_rate_limit_model_nudge` | `boolean` | Track opt-out of the rate limit model switch reminder. |
| `notice.hide_gpt5_1_migration_prompt` | `boolean` | Track acknowledgement of the GPT-5.1 migration prompt. |
| `notice.hide_gpt-5.1-codex-max_migration_prompt` | `boolean` | Track acknowledgement of the gpt-5.1-codex-max migration prompt. |
| `notice.model_migrations` | `map<string,string>` | Track acknowledged model migrations as old->new mappings. |
| `forced_login_method` | `chatgpt \| api` | Restrict Codex to a specific authentication method. |
| `forced_chatgpt_workspace_id` | `string (uuid)` | Limit ChatGPT logins to a specific workspace identifier. |

You can find the latest JSON schema for `config.toml` [here](https://learn.chatgpt.com/docs/config-schema.json).

To get autocompletion and diagnostics when editing `config.toml` in VS Code or Cursor, you can install the [Even Better TOML](https://marketplace.visualstudio.com/items?itemName=tamasfe.even-better-toml) extension and add this line to the top of your `config.toml`:

```toml
#:schema https://developers.openai.com/codex/config-schema.json
```

Note: Rename `experimental_instructions_file` to `model_instructions_file`. Codex deprecates the old key; update existing configs to the new name.

### `requirements.toml`
`requirements.toml` is an admin-enforced configuration file that constrains security-sensitive settings users can't override. For details, locations, and examples, see [Admin-enforced requirements](./enterprise/managed-configuration.md#admin-enforced-requirements-requirementstoml).

For ChatGPT Business and Enterprise users, Codex can also apply cloud-fetched
requirements. See the security page for precedence details.

Use `[features]` in `requirements.toml` to pin runtime feature flags by the same
canonical keys that `config.toml` uses. Requirements can also include documented
app-only keys that don't belong in `config.toml`. Omitted keys remain
unconstrained.

Some managed requirements enforce an exact configuration value instead of an
allowlist. Users can't override an enforced path, update preference, login-shell
policy, feedback setting, or Windows private-desktop setting.

Managed permission-profile allowlists require Codex 0.138.0 or later. Codex
0.137.0 and earlier ignore `allowed_permission_profiles` and managed
`default_permissions`.

Use `allowed_sandbox_modes` with `sandbox_mode`. For permission-profile
deployments, use `allowed_permission_profiles` with managed
`default_permissions`.

An `untrusted` entry in `allowed_approval_policies` is still valid for the
stricter approval behavior Codex derives when a project uses
`trust_level = "untrusted"`. It does not permit explicitly setting
`approval_policy = "untrusted"`.

The `[models.new_thread]` table supplies managed defaults, not enforcement.
Explicit launch choices from dedicated CLI flags or `--config` overrides take
precedence. An explicit model or reasoning-effort override skips both managed
model fields; `service_tier` is independent.

The browser requirements cover three separate surfaces. `in_app_browser`
controls the browser pane that a person opens and uses directly. `browser_use`
controls agent-driven work in a browser. `computer_use` controls agent-driven
work in native desktop apps.

The nested Browser Use and Computer Use policy values do not grant access by
themselves. An origin- or app-specific `allow` can override the fallback for
the same policy source, but normal feature, approval, and other policy checks
still apply. Where managed requirements and `config.toml` both apply, a `deny`
from either one wins.

| Key | Type | Description |
| --- | --- | --- |
| `sqlite_home` | `string (path)` | Enforce the directory where Codex stores SQLite-backed runtime state. |
| `log_dir` | `string (path)` | Enforce the directory where Codex writes local log files. |
| `model_catalog_json` | `string (path)` | Enforce the JSON model catalog Codex uses at startup. |
| `check_for_update_on_startup` | `boolean` | Enforce whether Codex checks for updates when it starts. |
| `allow_login_shell` | `boolean` | Enforce whether shell tools can start a login shell. |
| `allowed_login_methods` | `array<string>` | Allow `chatgpt`, `api`, or both. If omitted, this setting doesn't restrict login methods. If set, the list must contain at least one method. `api` permits API authentication, including Amazon Bedrock. Set through the local system requirements file or macOS MDM. Cloud-managed values are ignored. |
| `allowed_chatgpt_workspaces` | `array<string>` | Restrict ChatGPT login, including Codex access tokens, to the listed workspace IDs. An empty list disables ChatGPT login; API authentication remains available when permitted. Set through the local system requirements file or macOS MDM; cloud-managed values are ignored. |
| `cli_auth_credentials_store` | `file \| keyring \| auto \| ephemeral` | Enforce the CLI credential store before authentication loads. `file` uses `CODEX_HOME/auth.json`; `keyring` requires the OS credential store; `auto` falls back to a file if the credential store is unavailable; `ephemeral` keeps credentials in memory for the current process. Set through the local system requirements file or macOS MDM; cloud-managed values are ignored. |
| `chatgpt_base_url` | `string` | Enforce the ChatGPT service base URL before authentication and cloud-policy retrieval. This doesn't configure every Codex network destination. Set through the local system requirements file or macOS MDM; cloud-managed values are ignored. |
| `feedback` | `table` | Managed feedback settings. |
| `feedback.enabled` | `boolean` | Enforce whether users can submit feedback across Codex clients. |
| `allowed_approval_policies` | `array<string>` | Allowed approval policies, such as `on-request`, `never`, and `granular`. Include `untrusted` to permit the stricter policy derived from an untrusted project; it cannot be selected directly with `approval_policy`. |
| `allowed_approvals_reviewers` | `array<string>` | Allowed values for `approvals_reviewer`, such as `user` and `auto_review`. |
| `guardian_policy_config` | `string` | Managed Markdown policy instructions for automatic review. This takes precedence over local `[auto_review].policy`. Blank values are ignored. |
| `allowed_permission_profiles` | `table<boolean>` | Complete list of allowed permission profiles. Profiles set to `true` are allowed. Profiles that are omitted or set to `false` are denied, including profiles added in future versions. When requirements sources are combined, entries are matched by profile name. |
| `allowed_permission_profiles.<name>` | `boolean` | Allow or deny a built-in or custom permission profile defined in a loaded config or requirements source. A later, higher-precedence requirements source can use `false` to turn off a profile allowed by an earlier, lower-precedence source. |
| `default_permissions` | `string` | Managed default permission profile. The profile must be allowed by `allowed_permission_profiles`. Set this explicitly for predictable behavior; if omitted, Codex defaults to `:workspace` only when both `:workspace` and `:read-only` are explicitly allowed. |
| `enforce_residency` | `string` | Require Codex service traffic to use a supported data residency. Currently accepts `us`. |
| `models` | `table` | Managed model defaults for new threads. These values take priority over user and project defaults, but an explicit selection for the new thread can override them. |
| `models.new_thread` | `table` | Defaults to apply when a new local thread starts. Each model setting is optional. |
| `models.new_thread.model` | `string` | Default model for new threads. An explicit `--model` or model/reasoning `--config` override takes precedence. |
| `models.new_thread.model_reasoning_effort` | `string` | Default reasoning effort for new threads. An explicit model or reasoning-effort override skips both managed model fields. |
| `models.new_thread.service_tier` | `string` | Default service tier for new threads. An explicit service-tier override takes precedence independently of the model fields. |
| `permissions` | `table` | Admin-defined permission profiles keyed by profile name. Uses the same profile fields as `config.toml`. |
| `permissions.<name>` | `table` | Admin-defined permission profile. The name can't start with `:`, use the reserved name `filesystem`, or duplicate a profile from a loaded config. Uses the same profile fields as `config.toml`; see the Permissions guide for the complete profile schema. |
| `allowed_sandbox_modes` | `array<string>` | Allowed values for `sandbox_mode`. |
| `windows` | `table` | Native Windows sandbox requirements. |
| `windows.allowed_sandbox_implementations` | `array<string>` | Allowed native Windows sandbox implementations for `windows.sandbox` (`elevated` and `unelevated`). The list must not be empty. When both are allowed and no mode is selected, Codex prefers `elevated`. |
| `windows.sandbox_private_desktop` | `boolean` | Enforce whether the native Windows sandbox starts its child process on a private desktop. |
| `remote_sandbox_config` | `array<table>` | Host-specific sandbox requirements. The first entry whose `hostname_patterns` match the resolved host name overrides top-level `allowed_sandbox_modes` for that requirements source. Host-specific entries currently override sandbox modes only. |
| `remote_sandbox_config[].hostname_patterns` | `array<string>` | Case-insensitive host name patterns. Supports `*` for any sequence of characters and `?` for one character. |
| `remote_sandbox_config[].allowed_sandbox_modes` | `array<string>` | Allowed sandbox modes to apply when this host-specific entry matches. |
| `allowed_web_search_modes` | `array<string>` | Allowed values for `web_search` (`disabled`, `cached`, `indexed`, `live`). `disabled` is always allowed; an empty list effectively allows only `disabled`. |
| `allow_managed_hooks_only` | `boolean` | When `true`, Codex skips user, project, session, and plugin hooks while still allowing managed hooks from `requirements.toml` and other managed config layers. |
| `allow_appshots` | `boolean` | Set to `false` to disable Appshots for managed users. If omitted, Appshots remain unconstrained by requirements and follow normal product availability. |
| `allow_remote_control` | `boolean` | Set to `false` to disable device remote control for managed users. If omitted, device remote control remains unconstrained by requirements and follows normal product availability. |
| `allow_browser_and_computer_use` | `boolean` | Set to `false` to block both agent-driven Browser Use and native-app Computer Use. Setting it to `true` or omitting it does not enable either feature; the remaining feature, policy, and approval checks still apply. |
| `features.plugin_sharing` | `boolean` | Set to `false` in cloud-managed `requirements.toml` to disable workspace sharing for locally built plugins. |
| `features` | `table` | Pinned feature values. Use canonical names from `config.toml` for runtime features; documented app-only requirement keys are also supported here. |
| `features.<name>` | `boolean` | Require a documented runtime or app feature to stay enabled or disabled. |
| `features.apps` | `boolean` | Pin Apps integration availability on or off for managed users. |
| `features.in_app_updates` | `boolean` | Set to `false` in `requirements.toml` to disable in-app updates. Updates remain enabled by default when this requirement is omitted. |
| `features.in_app_browser` | `boolean` | Set to `false` in `requirements.toml` to disable the built-in browser pane that users open and control directly. |
| `features.browser_use` | `boolean` | Set to `false` in `requirements.toml` to disable agent-driven Browser Use. |
| `features.browser_use_external` | `boolean` | Set to `false` in `requirements.toml` to prevent Codex from operating supported browsers through the ChatGPT browser extension, including existing tabs and signed-in sessions. |
| `features.browser_use_full_cdp_access` | `boolean` | Set to `false` in `requirements.toml` to disable full Chrome DevTools Protocol access in the local runtime, including Browser Developer mode, and prevent the ChatGPT desktop app from enabling the corresponding setting. If omitted, normal product availability applies. |
| `features.fast_mode` | `boolean` | Pin the canonical `fast_mode` feature on or off for managed users. |
| `features.guardian_approval` | `boolean` | Pin Guardian approval availability on or off for managed users. |
| `features.memories` | `boolean` | Pin Memories availability on or off for managed users. |
| `features.multi_agent` | `boolean` | Pin multi-agent availability on or off for managed users. |
| `features.plugins` | `boolean` | Pin plugin availability on or off for managed users. |
| `features.remote_plugin` | `boolean` | Pin remote plugin catalog availability on or off for managed users. |
| `features.computer_use` | `boolean` | Set to `false` in `requirements.toml` to disable Computer Use, Record & Replay, and related install or enablement flows. |
| `features.workspace_dependencies` | `boolean` | Pin bundled workspace-dependency runtime availability on or off for managed users. |
| `in_app_browser` | `table` | Requirements for the built-in browser pane. These settings do not control agent-driven Browser Use. |
| `in_app_browser.allow_external_browser_settings_import` | `boolean` | Set to `false` to prevent users from importing settings or browsing data from an external browser into the built-in browser. Setting it to `true` or omitting it leaves the import available when other product checks allow it. This is a managed-only setting with no `config.toml` override. |
| `browser_use` | `table` | Managed requirements for agent-driven Browser Use. |
| `browser_use.allow_history_access` | `boolean` | Set to `false` to prevent Browser Use from reading browser history. Setting it to `true` or omitting it leaves normal history settings and availability checks in place. |
| `browser_use.disable_auto_review` | `boolean` | Set to `true` to skip automatic review for Browser Use and ask the user for approval instead. Setting it to `false` or omitting it leaves automatic review available when other settings allow it. |
| `browser_use.allow_global_persistent_approval` | `boolean` | Set to `false` to prevent Browser Use from creating or honoring `Always allow` approvals that cover every site, such as allowing downloads from any site. Existing saved approvals are ignored, not deleted. Setting it to `true` or omitting it does not create an approval. |
| `browser_use.default_origin_policy` | `table` | Fallback for each Browser Use setting when no matching entry under `browser_use.origins` defines it. A matching origin rule replaces the fallback for that source. Codex then applies the stricter result from managed requirements and user configuration. |
| `browser_use.default_origin_policy.access` | `allow \| deny` | Use `deny` to block Browser Use on origins that use the fallback. A denied origin also blocks uploads, downloads, full browser debugging access, and automatic review there. `allow` only lets normal approval and policy checks continue. |
| `browser_use.default_origin_policy.downloads` | `allow \| deny` | Use `deny` to block Browser Use downloads on origins that use the fallback. `allow` only lets normal approval and policy checks continue. |
| `browser_use.default_origin_policy.uploads` | `allow \| deny` | Use `deny` to block Browser Use uploads on origins that use the fallback. `allow` only lets normal approval and policy checks continue. |
| `browser_use.default_origin_policy.full_cdp_access` | `allow \| deny` | Use `deny` to block full Chrome DevTools Protocol (CDP) access on origins that use the fallback. `allow` only lets normal opt-in and approval checks continue. |
| `browser_use.default_origin_policy.auto_review` | `allow \| deny` | Use `deny` to skip automatic review on origins that use the fallback and ask the user for approval instead. `allow` leaves automatic review available when other settings allow it. |
| `browser_use.default_origin_policy.persistent_approval` | `boolean` | Set to `false` to prevent Browser Use from saving or honoring an `Always allow` approval on origins that use the fallback. Approvals for the current turn or thread can still apply. `true` makes `Always allow` available when otherwise permitted but does not create an approval. |
| `browser_use.default_origin_policy.access_approval_lifetime` | `turn \| thread` | Set how long a non-persistent site-access approval lasts: `turn` limits it to the current turn, and `thread` keeps it for the rest of the current thread. `persistent_approval` separately controls whether `Always allow` is available. The product default is `thread`. |
| `browser_use.origins` | `map<string, table>` | Origin-specific Browser Use policies. Keys use `<scheme>://<host-pattern>[:<port>]` with `http` or `https`. Use an exact host, `*.example.com` for subdomains only, or `**.example.com` for the base domain and its subdomains. Other `*` wildcards can span dots, so `region*.example.com` also matches `region.api.example.com`; a host of `*` matches every host for that scheme. Schemes and nondefault ports are significant; explicit default ports are normalized away. Paths, queries, embedded usernames or passwords, and wildcard schemes or ports are invalid. Quote the pattern in TOML, for example `[browser_use.origins."https://**.example.com"]`. |
| `browser_use.origins.<pattern>` | `table` | Policy for origins matching this pattern. If several patterns match, Codex uses the most restrictive value for each capability: `deny` over `allow`, `false` over `true`, and `turn` over `thread`. |
| `browser_use.origins.<pattern>.access` | `allow \| deny` | Use `deny` to block Browser Use on matching origins. Denial also blocks uploads, downloads, full browser debugging access, and automatic review there. `allow` only lets normal approval and policy checks continue. |
| `browser_use.origins.<pattern>.downloads` | `allow \| deny` | Use `deny` to block Browser Use downloads on matching origins. `allow` only lets normal approval and policy checks continue. |
| `browser_use.origins.<pattern>.uploads` | `allow \| deny` | Use `deny` to block Browser Use uploads on matching origins. `allow` only lets normal approval and policy checks continue. |
| `browser_use.origins.<pattern>.full_cdp_access` | `allow \| deny` | Use `deny` to block full Chrome DevTools Protocol (CDP) access on matching origins. `allow` only lets normal opt-in and approval checks continue. |
| `browser_use.origins.<pattern>.auto_review` | `allow \| deny` | Use `deny` to skip automatic review on matching origins and ask the user for approval instead. `allow` leaves automatic review available when other settings allow it. |
| `browser_use.origins.<pattern>.persistent_approval` | `boolean` | Set to `false` to prevent Browser Use from saving or honoring an `Always allow` approval on matching origins. Approvals for the current turn or thread can still apply. `true` makes `Always allow` available when otherwise permitted but does not create an approval. |
| `browser_use.origins.<pattern>.access_approval_lifetime` | `turn \| thread` | Set how long a non-persistent site-access approval for matching origins lasts: `turn` limits it to the current turn, and `thread` keeps it for the rest of the current thread. `persistent_approval` separately controls whether `Always allow` is available. |
| `computer_use` | `table` | Managed requirements for agent-driven work in native desktop apps. Managed app rules and `config.toml` app rules are both enforced; an app must be allowed by each policy source. |
| `computer_use.allow_locked_computer_use` | `boolean` | Set to `false` to prevent users from enabling Locked Use on a managed macOS device. This requirement removes the enablement controls; it does not turn off Locked Use if it is already enabled. If omitted, normal product availability applies. |
| `computer_use.allow_persistent_approval` | `boolean` | Set to `false` to remove the option to save app approvals across sessions. Approvals for the current session remain available. Setting it to `true` or omitting it does not approve an app. |
| `computer_use.default_app_access` | `allow \| deny` | Fallback access for native apps that do not match a platform-specific rule. `deny` blocks access. `allow` only lets normal approval and policy checks continue. The product default is `allow`. |
| `computer_use.macos` | `table` | Computer Use app rules for macOS. |
| `computer_use.macos.bundle_ids` | `map<string, allow \| deny>` | Map exact macOS bundle identifiers to `allow` or `deny`. A matching rule replaces `computer_use.default_app_access` within the same policy source. A deny from either managed requirements or user configuration still blocks access. |
| `computer_use.macos.bundle_ids.<bundle-id>` | `allow \| deny` | Use `deny` to block the exact bundle identifier. `allow` overrides only this policy source's default and still requires any other policy source and the normal approval flow to allow the app. |
| `computer_use.windows` | `table` | Computer Use app rules for packaged and unpackaged Windows apps. |
| `computer_use.windows.aumids` | `map<string, allow \| deny>` | Map exact, registered Application User Model IDs (AUMIDs) for signed packaged apps to `allow` or `deny`. A matching rule replaces `computer_use.default_app_access` within the same policy source. |
| `computer_use.windows.aumids.<aumid>` | `allow \| deny` | Use `deny` to block the exact packaged-app identity. `allow` overrides only this policy source's default and still requires any other policy source and the normal approval flow to allow the app. |
| `computer_use.windows.exes` | `array<table>` | Rules for signed, unpackaged Windows executables. Rules match the executable's verified publisher and signed version information, not its path or current file name. A matching deny takes precedence over matching allows. Unsigned executables use `computer_use.default_app_access`; executables whose signed identity cannot be verified unambiguously are blocked. |
| `computer_use.windows.exes[].publisher_name` | `string` | Required exact publisher name from the executable's trusted signing certificate, formatted as a Windows X.500 distinguished name. |
| `computer_use.windows.exes[].product_name` | `string` | Required exact `ProductName` from the executable's signed version information. |
| `computer_use.windows.exes[].binary_name` | `string` | Optional `OriginalFilename` from the executable's signed version information. Matching is case-insensitive. If a matching publisher and product rule requires this value but the executable does not provide it, Computer Use blocks the executable. |
| `computer_use.windows.exes[].access` | `allow \| deny` | Required access decision for matching executables. `deny` blocks access. `allow` overrides only this policy source's default and still requires any other policy source and the normal approval flow to allow the app. |
| `experimental_network` | `table` | Administrator-managed network requirements for sandboxed local commands, enforced from `requirements.toml`. When enabled, these requirements can start the command network proxy without `features.network_proxy`. Browser tools separately check managed network denies and exclusive allowlists. These requirements do not route browser traffic through the proxy or control web search, apps, MCP servers, native-app traffic, or Codex cloud networking. |
| `experimental_network.enabled` | `boolean` | Enable sandboxed networking requirements. This does not grant network access when the active sandbox keeps command networking off. |
| `experimental_network.http_port` | `integer` | Loopback HTTP listener port to use for `[experimental_network]` requirements. |
| `experimental_network.socks_port` | `integer` | Loopback SOCKS5 listener port to use for `[experimental_network]` requirements. |
| `experimental_network.allow_upstream_proxy` | `boolean` | Allow sandboxed networking to chain through an upstream proxy from the environment. |
| `experimental_network.dangerously_allow_non_loopback_proxy` | `boolean` | Permit non-loopback listener addresses for `[experimental_network]` requirements. Enabling it can expose listeners beyond localhost. |
| `experimental_network.dangerously_allow_all_unix_sockets` | `boolean` | Permit arbitrary Unix socket destinations instead of allowlist-only access. Use only in tightly controlled environments. |
| `experimental_network.domains` | `map<string, allow \| deny>` | Map-shaped administrator domain policy for sandboxed networking. Supports exact hosts, `*.example.com` for subdomains only, `**.example.com` for apex plus subdomains, and global `*` allow rules; prefer scoped rules because `*` broadly opens public outbound access. `deny` wins on conflicts. Do not combine this with `experimental_network.allowed_domains` or `experimental_network.denied_domains`. |
| `experimental_network.allowed_domains` | `array<string>` | Administrator allow rules for sandboxed-command networking while the managed network proxy is enabled. These rules do not apply to web search, apps, or MCP servers. Do not combine this with `experimental_network.domains`. |
| `experimental_network.denied_domains` | `array<string>` | List-shaped administrator deny rules for sandboxed networking. Do not combine this with `experimental_network.domains`. |
| `experimental_network.managed_allowed_domains_only` | `boolean` | When `true`, only administrator-managed allow rules remain effective while sandboxed networking requirements are active; user allowlist additions are ignored. Without managed allow rules, user-added domain allow rules do not remain effective. |
| `experimental_network.unix_sockets` | `map<string, allow \| deny>` | Administrator-managed Unix socket policy for sandboxed networking. |
| `experimental_network.allow_local_binding` | `boolean` | Permit broader local/private-network access for sandboxed networking. Exact local IP literal or `localhost` allow rules can still permit specific local targets when this stays `false`. |
| `hooks` | `table` | Admin-enforced managed lifecycle hooks. Requires a managed hook directory and uses the same event schema as inline `[hooks]` in `config.toml`. |
| `hooks.managed_dir` | `string (absolute path)` | Directory containing managed hook scripts on macOS and Linux. Codex validates that it is absolute and exists before loading managed hooks. |
| `hooks.windows_managed_dir` | `string (absolute path)` | Directory containing managed hook scripts on Windows. Codex validates that it is absolute and exists before loading managed hooks. |
| `hooks.<Event>` | `array<table>` | Matcher groups for a hook event such as `PreToolUse`, `PermissionRequest`, `PostToolUse`, `PreCompact`, `PostCompact`, `SessionStart`, `SessionEnd`, `SubagentStart`, `SubagentStop`, `UserPromptSubmit`, or `Stop`. |
| `hooks.<Event>[].hooks` | `array<table>` | Hook handlers for a matcher group. Command and MCP tool hooks are supported while prompt and agent hook handlers are parsed but skipped. |
| `hooks.<Event>[].hooks[].async` | `boolean` | Run a command hook in the background without delaying the triggering operation. Defaults to `false`; `SessionEnd` always runs synchronously. See [Run hooks in the background](./hooks.md#run-hooks-in-the-background). |
| `hooks.<Event>[].hooks[].additionalContextLimit` | `integer` | Approximate per-handler token threshold for saving oversized `additionalContext` to disk and showing the model a shorter preview. Defaults to `2500`; `0` passes the full context directly to the model. See [Large hook output](./hooks.md#large-hook-output). |
| `hooks.<Event>[].hooks[].commandWindows` | `string` | Windows-only command override for command hooks. The TOML alias `command_windows` is also accepted. |
| `permissions.filesystem.deny_read` | `array<string>` | Admin-enforced filesystem read denials. Entries can be paths or glob patterns, and users cannot weaken them with local config. |
| `mcp_servers` | `table` | Allowlist of MCP servers that may be enabled. Both the server name (`<id>`) and its identity must match for the MCP server to be enabled. Any configured MCP server not in the allowlist (or with a mismatched identity) is disabled. |
| `mcp_servers.<id>.identity` | `table` | Identity rule for a single MCP server. Set either `command` (stdio) or `url` (streamable HTTP). |
| `mcp_servers.<id>.identity.command` | `string \| table` | Allow an MCP stdio server by exact command string, or use a matcher table to require an exact executable and ordered argument matchers. The string form doesn't inspect arguments, `cwd`, `env`, or `env_vars`. |
| `mcp_servers.<id>.identity.command.executable` | `string` | Executable that the stdio server's configured `command` must match exactly. |
| `mcp_servers.<id>.identity.command.args` | `array<table>` | Ordered argument matchers for a stdio server. The configured argument list must have the same length, and every position must match. Command matchers don't inspect `cwd`, `env`, or `env_vars`. |
| `mcp_servers.<id>.identity.command.args[].match` | `exact \| prefix \| regex` | Match operation for this argument position. |
| `mcp_servers.<id>.identity.command.args[].value` | `string` | Value used by an `exact` or `prefix` argument matcher. |
| `mcp_servers.<id>.identity.command.args[].expression` | `string` | Regular expression used by a `regex` argument matcher. The expression must be valid and match the complete argument value. |
| `mcp_servers.<id>.identity.url` | `string \| table` | Allow an MCP streamable HTTP server by exact URL string, or use an `exact`, `prefix`, or `regex` value matcher table. |
| `mcp_servers.<id>.identity.url.match` | `exact \| prefix \| regex` | Match operation for the configured MCP server URL. |
| `mcp_servers.<id>.identity.url.value` | `string` | Value used by an `exact` or `prefix` URL matcher. |
| `mcp_servers.<id>.identity.url.expression` | `string` | Regular expression used by a `regex` URL matcher. The expression must be valid and match the complete URL value. |
| `plugins` | `table` | Plugin-specific MCP server allowlists keyed by plugin identifier. When this table is present, plugin-bundled servers without a matching plugin and server entry are disabled. |
| `plugins.<plugin>.mcp_servers` | `table` | Allowlist for MCP servers bundled with one plugin. Plugin server requirements use the same exact identity and matcher forms as top-level `mcp_servers` requirements. |
| `plugins.<plugin>.mcp_servers.<server>.identity` | `table` | Identity rule for one plugin-bundled MCP server. Set either `command` (stdio) or `url` (streamable HTTP). |
| `plugins.<plugin>.mcp_servers.<server>.identity.command` | `string \| table` | Allow a plugin's stdio MCP server by exact command string, or use a matcher table to require an exact executable and ordered argument matchers. |
| `plugins.<plugin>.mcp_servers.<server>.identity.command.executable` | `string` | Executable that the plugin-bundled stdio server's configured command must match exactly. |
| `plugins.<plugin>.mcp_servers.<server>.identity.command.args` | `array<table>` | Ordered argument matchers for a plugin-bundled stdio server. The configured argument list must have the same length, and every position must match. |
| `plugins.<plugin>.mcp_servers.<server>.identity.command.args[].match` | `exact \| prefix \| regex` | Match operation for this argument position. |
| `plugins.<plugin>.mcp_servers.<server>.identity.command.args[].value` | `string` | Value used by an `exact` or `prefix` argument matcher. |
| `plugins.<plugin>.mcp_servers.<server>.identity.command.args[].expression` | `string` | Regular expression used by a `regex` argument matcher. The expression must match the complete argument value. |
| `plugins.<plugin>.mcp_servers.<server>.identity.url` | `string \| table` | Allow a plugin's streamable HTTP MCP server by exact URL string, or use an `exact`, `prefix`, or `regex` value matcher table. |
| `plugins.<plugin>.mcp_servers.<server>.identity.url.match` | `exact \| prefix \| regex` | Match operation for the plugin-bundled MCP server URL. |
| `plugins.<plugin>.mcp_servers.<server>.identity.url.value` | `string` | Value used by an `exact` or `prefix` URL matcher. |
| `plugins.<plugin>.mcp_servers.<server>.identity.url.expression` | `string` | Regular expression used by a `regex` URL matcher. The expression must match the complete URL value. |
| `marketplaces` | `table` | Admin requirements for plugin marketplace sources. Rules take effect when `restrict_to_allowed_sources` is `true`. |
| `marketplaces.restrict_to_allowed_sources` | `boolean` | When `true`, require configured marketplace sources to match `allowed_sources` for marketplace add, plugin install, refresh, and runtime loading. OpenAI-curated Git catalogs, including the API-key catalog, must also match the allowlist. Bundled and remotely installed workspace plugins are separate from this curated Git source policy. |
| `marketplaces.allowed_sources` | `table` | Allowed marketplace sources keyed by administrator-chosen rule name. Distinct names accumulate across requirements layers; fields under the same name use normal layer precedence. |
| `marketplaces.allowed_sources.<name>` | `table` | One allowed source rule. The final `source` value after requirements merge determines which sibling fields Codex interprets. |
| `marketplaces.allowed_sources.<name>.source` | `git \| host_pattern \| local` | Marketplace source matcher type. Use `git` for one repository, `host_pattern` for Git hosts matched by regular expression, or `local` for one directory. |
| `marketplaces.allowed_sources.<name>.url` | `string` | Git repository URL required when `source = "git"`. Codex normalizes the configured and allowed URLs before requiring an exact repository match. |
| `marketplaces.allowed_sources.<name>.ref` | `string` | Optional exact Git ref for a `git` rule. When omitted, the rule allows any ref for the matching repository. |
| `marketplaces.allowed_sources.<name>.host_pattern` | `string` | Regular expression required when `source = "host_pattern"`. Codex matches it against the lowercase hostname parsed from an HTTPS, SSH, or SCP-style Git source. Use `^` and `$` to require a whole-host match. |
| `marketplaces.allowed_sources.<name>.path` | `string (absolute path)` | Local marketplace directory required when `source = "local"`. Codex requires an absolute path and compares paths after normalization. |
| `apps` | `table` | Managed app requirements keyed by app identifier. Requirements can disable an app or constrain approval behavior for individual tools. |
| `apps.<id>.enabled` | `boolean` | Set to `false` to disable an app. A disabled requirement remains restrictive when multiple requirements sources are merged. |
| `apps.<id>.tools.<tool>.approval_mode` | `auto \| prompt \| writes \| approve` | Set the managed approval mode for one app tool. |
| `rules` | `table` | Admin-enforced command rules merged with `.rules` files. Requirements rules must be restrictive. |
| `rules.prefix_rules` | `array<table>` | List of enforced prefix rules. Each rule must include `pattern` and `decision`. |
| `rules.prefix_rules[].pattern` | `array<table>` | Command prefix expressed as pattern tokens. Each token sets either `token` or `any_of`. |
| `rules.prefix_rules[].pattern[].token` | `string` | A single literal token at this position. |
| `rules.prefix_rules[].pattern[].any_of` | `array<string>` | A list of allowed alternative tokens at this position. |
| `rules.prefix_rules[].decision` | `prompt \| forbidden` | Required. Requirements rules can only prompt or forbid (not allow). |
| `rules.prefix_rules[].justification` | `string` | Optional non-empty rationale surfaced in approval prompts or rejection messages. |

## Lifecycle hooks

Admins can set top-level `allow_managed_hooks_only = true` in
`requirements.toml` to ignore user, project, and session hook configs while
still allowing managed hooks from requirements and managed config layers. This
setting is only supported in `requirements.toml`; putting it in `config.toml`
does not enable managed-hooks-only mode.
