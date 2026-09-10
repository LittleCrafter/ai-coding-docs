# Configuration

## Config basics
Codex reads configuration details from more than one location. Your personal defaults live in `~/.codex/config.toml`, and you can add project overrides with `.codex/config.toml` files. For security, Codex loads project `.codex/` layers only when you trust the project.

### Codex configuration file
Codex stores user-level configuration at `~/.codex/config.toml`. To scope settings to a specific project or subfolder, add a `.codex/config.toml` file in your repo.

To open the configuration file from the Codex IDE extension, select the gear icon in the top-right corner, then select **Codex Settings > Open config.toml**.

The CLI and IDE extension share the same configuration layers. You can use them to:

- Set the default model and provider.
- Configure [approval policies and sandbox settings](https://learn.chatgpt.com/docs/agent-approvals-security#sandbox-and-approvals).
- Configure [MCP servers](https://learn.chatgpt.com/docs/extend/mcp).

### Configuration precedence
Codex resolves values in this order (highest precedence first):

1. CLI flags and `--config` overrides
2. Project config files: `.codex/config.toml`, ordered from the project root down to your current working directory (closest wins; trusted projects only)
3. [Profile](https://learn.chatgpt.com/docs/config-file/config-advanced#profiles) files selected with `--profile profile-name` (`~/.codex/profile-name.config.toml`)
4. User config: `~/.codex/config.toml`
5. Cloud-managed `config.toml` defaults, when delivered for the signed-in workspace
6. System config (if present): `/etc/codex/config.toml` on Unix
7. Built-in defaults

Use that precedence to set shared defaults in `config.toml` and keep [profile files](https://learn.chatgpt.com/docs/config-file/config-advanced#profiles) focused on the values that differ.

Cloud-managed and system configuration can define plugin marketplaces and set
whether plugins are enabled by default. These are separate from enforced `requirements.toml`
policies. See [Configure plugin marketplaces and defaults](https://learn.chatgpt.com/docs/enterprise/managed-configuration#configure-plugin-marketplaces-and-defaults).

If you mark a project as untrusted, Codex skips project-scoped `.codex/` layers, including project-local config, hooks, and rules. User and system config still load, including user/global hooks and rules.

For one-off overrides via `-c`/`--config` (including TOML quoting rules), see [Advanced Config](https://learn.chatgpt.com/docs/config-file/config-advanced#one-off-overrides-from-the-cli).

On managed machines, your organization may also enforce constraints via
  `requirements.toml` (for example, disallowing `approval_policy = "never"` or
  `sandbox_mode = "danger-full-access"`). See [Managed
  configuration](https://learn.chatgpt.com/docs/enterprise/managed-configuration) and [Admin-enforced
  requirements](https://learn.chatgpt.com/docs/enterprise/managed-configuration#admin-enforced-requirements-requirementstoml).

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

For behavior differences between `on-request` and `never`, see [Run without approval prompts](https://learn.chatgpt.com/docs/agent-approvals-security#run-without-approval-prompts) and [Common sandbox and approval combinations](https://learn.chatgpt.com/docs/agent-approvals-security#common-sandbox-and-approval-combinations). If an existing configuration uses `approval_policy = "untrusted"`, see [Migrate from the retired `untrusted` approval policy](https://learn.chatgpt.com/docs/agent-approvals-security#migrate-from-the-retired-untrusted-approval-policy).

##### Sandbox level
Adjust how much filesystem and network access Codex has while executing commands.

```toml
sandbox_mode = "workspace-write"
```

For mode-by-mode behavior (including protected `.git`/`.codex` paths and network defaults), see [Sandbox and approvals](https://learn.chatgpt.com/docs/agent-approvals-security#sandbox-and-approvals), [Protected paths in writable roots](https://learn.chatgpt.com/docs/agent-approvals-security#protected-paths-in-writable-roots), and [Network access](https://learn.chatgpt.com/docs/agent-approvals-security#network-access).

##### Permission profiles
Codex also supports named permission profiles for reusable filesystem and
network policies. Built-in profiles are `:read-only`, `:workspace`, and
`:danger-full-access`. Custom profiles use `[permissions.<name>]` tables and a
matching `default_permissions` value. See [Permissions](https://learn.chatgpt.com/docs/permissions).

##### Windows sandbox mode
When running Codex natively on Windows, set the native sandbox mode to `elevated` in the `windows` table. Use `unelevated` only if you don't have administrator permissions or if elevated setup fails.

```toml
[windows]
sandbox = "elevated"   # Recommended
# sandbox = "unelevated" # Fallback if admin permissions/setup are unavailable
```

##### Web search mode
Codex enables web search by default for local chats and serves results from a web search cache. The cache is an OpenAI-maintained index of web results, so cached mode returns pre-indexed results instead of fetching live pages. This reduces exposure to prompt injection from arbitrary live content, but you should still treat web results as untrusted. If you are using `--yolo` or another [full access sandbox setting](https://learn.chatgpt.com/docs/agent-approvals-security#common-sandbox-and-approval-combinations), web search defaults to live results. Choose a mode with `web_search`:

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
policy](https://learn.chatgpt.com/docs/config-file/config-advanced#shell-environment-policy).

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
| `hooks`              |         true          | Stable       | Enable lifecycle hooks from `hooks.json` or inline `[hooks]`. See [Hooks](https://learn.chatgpt.com/docs/hooks). |
| `fast_mode`          |         true          | Stable       | Enable Fast mode selection and the `service_tier = "fast"` path                          |
| `memories`           |         false         | Experimental | Enable [Memories](https://learn.chatgpt.com/docs/customization/memories)                                         |
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
  Maturity](https://learn.chatgpt.com/docs/feature-maturity) for how to interpret these labels.

Omit feature keys to keep their defaults.

For lifecycle hook configuration, see [Hooks](https://learn.chatgpt.com/docs/hooks).

#### Enabling features
- In `config.toml`, add `feature_name = true` under `[features]`.
- From the CLI, run `codex --enable feature_name`.
- To enable more than one feature, run `codex --enable feature_a --enable feature_b`.
- To disable a feature, set the key to `false` in `config.toml`.

## Advanced Configuration
Use these options when you need more control over providers, policies, and integrations. For a quick start, see [Config basics](https://learn.chatgpt.com/docs/config-file/config-basic).

For background on project guidance, reusable capabilities, custom slash commands, subagent workflows, and integrations, see [Customization](https://learn.chatgpt.com/docs/customization/overview). For configuration keys, see [Configuration Reference](https://learn.chatgpt.com/docs/config-file/config-reference).

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

For authentication details (including credential storage modes), see [Authentication](https://learn.chatgpt.com/docs/auth). For the full list of configuration keys, see [Configuration Reference](https://learn.chatgpt.com/docs/config-file/config-reference).

For shared defaults, rules, and skills checked into repos or system paths, see [Team Config](https://learn.chatgpt.com/docs/enterprise/admin-setup#step-4-standardize-local-configuration-with-team-config).

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
[Hooks](https://learn.chatgpt.com/docs/hooks).

### Agent roles (`[agents]` in `config.toml`)
For subagent role configuration (`[agents]` in `config.toml`), see [Subagents](https://learn.chatgpt.com/docs/agent-configuration/subagents).

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
configured [`web_search` mode](https://learn.chatgpt.com/docs/web-search) and
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
Bedrock](https://learn.chatgpt.com/docs/amazon-bedrock).

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

For operational details to keep in mind while editing `config.toml`, see [Common sandbox and approval combinations](https://learn.chatgpt.com/docs/agent-approvals-security#common-sandbox-and-approval-combinations), [Protected paths in writable roots](https://learn.chatgpt.com/docs/agent-approvals-security#protected-paths-in-writable-roots), and [Network access](https://learn.chatgpt.com/docs/agent-approvals-security#network-access).

Codex and ChatGPT Work no longer support `approval_policy = "untrusted"`. See
[Migrate from the retired `untrusted` approval policy](https://learn.chatgpt.com/docs/agent-approvals-security#migrate-from-the-retired-untrusted-approval-policy)
for supported settings and stricter project-derived approvals.

For beta permission profiles that configure filesystem and network access together, see [Permissions](https://learn.chatgpt.com/docs/permissions).

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
network configuration model, see [Permissions](https://learn.chatgpt.com/docs/permissions).

For the complete key list and requirements constraints, see
[Configuration Reference](https://learn.chatgpt.com/docs/config-file/config-reference) and
[Managed configuration](https://learn.chatgpt.com/docs/enterprise/managed-configuration).

In workspace-write mode, some environments keep `.git/` and `.codex/`
  read-only even when the rest of the workspace is writable. This is why
  commands like `git commit` may still require approval to run outside the
  sandbox. If you want Codex to skip specific commands (for example, block `git
  commit` outside the sandbox), use
  [rules](https://learn.chatgpt.com/docs/agent-configuration/rules).

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
See the dedicated [MCP documentation](https://learn.chatgpt.com/docs/extend/mcp) for configuration details.

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

If `exporter = "none"` Codex records events but sends nothing. Exporters batch asynchronously and flush on shutdown. Event metadata includes service name, CLI version, env tag, conversation id, model, sandbox/approval settings, and per-event fields (see [Config Reference](https://learn.chatgpt.com/docs/config-file/config-reference)).

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

For more security and privacy guidance around telemetry, see [Security](https://learn.chatgpt.com/docs/agent-approvals-security#monitoring-and-telemetry).

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

See [Configuration Reference](https://learn.chatgpt.com/docs/config-file/config-reference) for the exact keys.

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

For a detailed walkthrough, see [Custom instructions with AGENTS.md](https://learn.chatgpt.com/docs/agent-configuration/agents-md).

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

See [Configuration Reference](https://learn.chatgpt.com/docs/config-file/config-reference) for the full key list.

## Configuration Reference
Use this page as a searchable reference for Codex configuration files. For conceptual guidance and examples, start with [Config basics](https://learn.chatgpt.com/docs/config-file/config-basic) and [Advanced Config](https://learn.chatgpt.com/docs/config-file/config-advanced).

### `config.toml`
User-level configuration lives in `~/.codex/config.toml`. You can also add project-scoped overrides in `.codex/config.toml` files. Codex loads project-scoped config files only when you trust the project.

Project-scoped config can't override machine-local provider, auth,
host-owned app request metadata, notification, configuration profile selection,
or telemetry routing keys. Codex ignores `openai_base_url`,
`chatgpt_base_url`, `apps_mcp_product_sku`, `model_provider`,
`model_providers`, `notify`, `profile`, `profiles`,
`experimental_realtime_ws_base_url`, and `otel` when they appear in a
project-local `.codex/config.toml`; put provider, notification, and telemetry
keys in user-level config instead. Config [profile files](https://learn.chatgpt.com/docs/config-file/config-advanced#profiles) live next to
`config.toml` as `$CODEX_HOME/profile-name.config.toml`; select one with
`--profile profile-name`.

For sandbox and approval keys (`approval_policy`, `sandbox_mode`, and `sandbox_workspace_write.*`), pair this reference with [Sandbox and approvals](https://learn.chatgpt.com/docs/agent-approvals-security#sandbox-and-approvals), [Protected paths in writable roots](https://learn.chatgpt.com/docs/agent-approvals-security#protected-paths-in-writable-roots), and [Network access](https://learn.chatgpt.com/docs/agent-approvals-security#network-access). For beta permission profiles, see [Permissions](https://learn.chatgpt.com/docs/permissions).

Codex and ChatGPT Work no longer support `approval_policy = "untrusted"`.
Remove the setting or choose a supported policy. Project entries with
`trust_level = "untrusted"` in user-level `~/.codex/config.toml` remain supported. See
[Migrate from the retired `untrusted` approval policy](https://learn.chatgpt.com/docs/agent-approvals-security#migrate-from-the-retired-untrusted-approval-policy)
for examples and approval tradeoffs.

<ConfigTable
  options={[
    {
      key: "model",
      type: "string",
      description: "Model to use (e.g., `gpt-5.5`).",
    },
    {
      key: "review_model",
      type: "string",
      description:
        "Optional model override used by `/review` (defaults to the current session model).",
    },
    {
      key: "model_provider",
      type: "string",
      description: "Provider id from `model_providers` (default: `openai`).",
    },
    {
      key: "openai_base_url",
      type: "string",
      description:
        "Base URL override for the built-in `openai` model provider.",
    },
    {
      key: "model_context_window",
      type: "number",
      description: "Context window tokens available to the active model.",
    },
    {
      key: "model_auto_compact_token_limit",
      type: "number",
      description:
        "Token threshold that triggers automatic history compaction (unset uses model defaults).",
    },
    {
      key: "model_auto_compact_token_limit_scope",
      type: "total | body_after_prefix",
      description:
        "Controls whether the auto-compaction threshold counts the full active context (`total`, the default) or only growth after the carried compaction-window prefix (`body_after_prefix`).",
    },
    {
      key: "model_catalog_json",
      type: "string (path)",
      description:
        "Optional path to a JSON model catalog loaded on startup. A selected `$CODEX_HOME/profile-name.config.toml` profile file can override this per profile.",
    },
    {
      key: "oss_provider",
      type: "lmstudio | ollama",
      description:
        "Default local provider used when running with `--oss` (defaults to prompting if unset).",
    },
    {
      key: "approval_policy",
      type: "on-request | never | { granular = { sandbox_approval = bool, rules = bool, mcp_elicitations = bool, request_permissions = bool, skill_approval = bool } }",
      description:
        "Controls when Codex pauses for approval before executing commands. You can also use `approval_policy = { granular = { ... } }` to allow or auto-reject specific prompt categories while keeping other prompts interactive. `untrusted` is unsupported, and `on-failure` is deprecated; use `on-request` for interactive runs or `never` for non-interactive runs.",
    },
    {
      key: "approval_policy.granular.sandbox_approval",
      type: "boolean",
      description:
        "When `true`, sandbox escalation approval prompts are allowed to surface.",
    },
    {
      key: "approval_policy.granular.rules",
      type: "boolean",
      description:
        "When `true`, approvals triggered by execpolicy `prompt` rules are allowed to surface.",
    },
    {
      key: "approval_policy.granular.mcp_elicitations",
      type: "boolean",
      description:
        "When `true`, MCP elicitation prompts are allowed to surface instead of being auto-rejected.",
    },
    {
      key: "approval_policy.granular.request_permissions",
      type: "boolean",
      description:
        "When `true`, prompts from the `request_permissions` tool are allowed to surface.",
    },
    {
      key: "approval_policy.granular.skill_approval",
      type: "boolean",
      description:
        "When `true`, skill-script approval prompts are allowed to surface.",
    },
    {
      key: "approvals_reviewer",
      type: "user | auto_review",
      description:
        "Who reviews eligible approval prompts under `on-request` or granular approval policies. Defaults to `user`; `auto_review` uses the reviewer subagent. This setting doesn't change sandboxing or review actions already allowed inside the sandbox.",
    },
    {
      key: "auto_review.policy",
      type: "string",
      description:
        "Local Markdown policy instructions for automatic review. Managed `guardian_policy_config` takes precedence. Blank values are ignored.",
    },
    {
      key: "allow_login_shell",
      type: "boolean",
      description:
        "Allow shell-based tools to use login-shell semantics. Defaults to `true`; when `false`, `login = true` requests are rejected and omitted `login` defaults to non-login shells.",
    },
    {
      key: "sandbox_mode",
      type: "read-only | workspace-write | danger-full-access",
      description:
        "Sandbox policy for filesystem and network access during command execution.",
    },
    {
      key: "sandbox_workspace_write.writable_roots",
      type: "array<string>",
      description:
        'Additional writable roots when `sandbox_mode = "workspace-write"`.',
    },
    {
      key: "sandbox_workspace_write.network_access",
      type: "boolean",
      description:
        "Allow outbound network access inside the workspace-write sandbox.",
    },
    {
      key: "sandbox_workspace_write.exclude_tmpdir_env_var",
      type: "boolean",
      description:
        "Exclude `$TMPDIR` from writable roots in workspace-write mode.",
    },
    {
      key: "sandbox_workspace_write.exclude_slash_tmp",
      type: "boolean",
      description:
        "Exclude `/tmp` from writable roots in workspace-write mode.",
    },
    {
      key: "windows.sandbox",
      type: "unelevated | elevated",
      description:
        "Windows-only native sandbox mode when running Codex natively on Windows.",
    },
    {
      key: "windows.sandbox_private_desktop",
      type: "boolean",
      description:
        "Run the final sandboxed child process on a private desktop by default on native Windows. Set `false` only for compatibility with the older `Winsta0\\\\Default` behavior.",
    },
    {
      key: "browser_use.allow_history_access",
      type: "boolean",
      description:
        "Set to `false` to restrict browser-history access. Managed requirements can enforce this restriction.",
    },
    {
      key: "browser_use.default_origin_policy",
      type: "table",
      description:
        "Fallback browser-origin restrictions. Supports `access`, `uploads`, `downloads`, and `full_cdp_access`, each set to `allow` or `deny`.",
    },
    {
      key: "browser_use.origins.<origin>",
      type: "table",
      description:
        "Per-origin browser restrictions with the same fields as `browser_use.default_origin_policy`. Include an HTTP or HTTPS scheme and optional port; omit paths, queries, and fragments. Local values cannot relax managed denies.",
    },
    {
      key: "computer_use.default_app_access",
      type: "allow | deny",
      description:
        "Fallback native-app access policy for Computer Use. App-specific entries can supply a policy; local configuration cannot relax managed restrictions.",
    },
    {
      key: "computer_use.macos.bundle_ids",
      type: "map<string, allow | deny>",
      description: "Native macOS app access keyed by bundle identifier.",
    },
    {
      key: "computer_use.windows.aumids",
      type: "map<string, allow | deny>",
      description:
        "Packaged Windows app access keyed by Application User Model ID (AUMID).",
    },
    {
      key: "computer_use.windows.exes",
      type: "array<table>",
      description:
        "Windows executable access rules. Each rule requires `publisher_name`, `product_name`, and `access` (`allow` or `deny`); `binary_name` is optional.",
    },
    {
      key: "computer_use.windows.always_allowed_app_ids",
      type: "array<string>",
      description:
        "Windows app identifiers that Computer Use can open without prompting. Apps not in the list require approval; remove saved entries from the ChatGPT desktop app's Computer Use settings.",
    },
    {
      key: "notify",
      type: "array<string>",
      description:
        "Command invoked for notifications; receives a JSON payload from Codex.",
    },
    {
      key: "check_for_update_on_startup",
      type: "boolean",
      description:
        "Check for Codex updates on startup (set to false only when updates are centrally managed).",
    },
    {
      key: "feedback.enabled",
      type: "boolean",
      description:
        "Enable feedback submission via `/feedback` across local clients (default: true).",
    },
    {
      key: "analytics.enabled",
      type: "boolean",
      description:
        "Enable or disable analytics for this machine/profile. When unset, the client default applies.",
    },
    {
      key: "instructions",
      type: "string",
      description:
        "Reserved for future use; prefer `model_instructions_file` or `AGENTS.md`.",
    },
    {
      key: "developer_instructions",
      type: "string",
      description:
        "Additional developer instructions injected into the session (optional).",
    },
    {
      key: "log_dir",
      type: "string (path)",
      description:
        "Directory where Codex writes log files; defaults to `$CODEX_HOME/log`. Setting this explicitly also enables the opt-in plaintext TUI log, `codex-tui.log`, in that directory.",
    },
    {
      key: "sqlite_home",
      type: "string (path)",
      description:
        "Directory where Codex stores the SQLite-backed state DB used by agent jobs and other resumable runtime state.",
    },
    {
      key: "compact_prompt",
      type: "string",
      description: "Inline override for the history compaction prompt.",
    },
    {
      key: "model_instructions_file",
      type: "string (path)",
      description:
        "Replacement for built-in instructions instead of `AGENTS.md`.",
    },
    {
      key: "personality",
      type: "none | friendly | pragmatic",
      description:
        "Default communication style for models that advertise `supportsPersonality`; can be overridden per thread/turn or via `/personality`.",
    },
    {
      key: "service_tier",
      type: "string",
      description:
        "Preferred service tier for new turns. Use `fast` or another tier advertised by the active model; `fast` maps to the request value `priority`.",
    },
    {
      key: "experimental_compact_prompt_file",
      type: "string (path)",
      description:
        "Load the compaction prompt override from a file (experimental).",
    },
    {
      key: "skills.max_context_tokens",
      type: "integer (positive)",
      description:
        "Token budget for the available-skills catalog. Defaults to 2% of the model's context window. Explicit values are capped at `10000` tokens.",
    },
    {
      key: "skills.config",
      type: "array<object>",
      description: "Per-skill enablement overrides stored in config.toml.",
    },
    {
      key: "skills.config.<index>.path",
      type: "string (path)",
      description: "Path to a skill folder containing `SKILL.md`.",
    },
    {
      key: "skills.config.<index>.enabled",
      type: "boolean",
      description: "Enable or disable the referenced skill.",
    },
    {
      key: "apps.<id>.enabled",
      type: "boolean",
      description:
        "Enable or disable a specific app/connector by id (default: true).",
    },
    {
      key: "apps._default.enabled",
      type: "boolean",
      description:
        "Default app enabled state for all apps unless overridden per app.",
    },
    {
      key: "apps._default.destructive_enabled",
      type: "boolean",
      description:
        "Default allow/deny for app tools with `destructive_hint = true`.",
    },
    {
      key: "apps._default.open_world_enabled",
      type: "boolean",
      description:
        "Default allow/deny for app tools with `open_world_hint = true`.",
    },
    {
      key: "apps._default.approvals_reviewer",
      type: "user | auto_review",
      description:
        "Default reviewer for app tool approval prompts unless overridden per app. When omitted, apps inherit the top-level `approvals_reviewer` value.",
    },
    {
      key: "apps._default.default_tools_approval_mode",
      type: "auto | prompt | writes | approve",
      description:
        "Default approval behavior for app tools without per-app or per-tool overrides.",
    },
    {
      key: "apps.<id>.destructive_enabled",
      type: "boolean",
      description:
        "Allow or block tools in this app that advertise `destructive_hint = true`.",
    },
    {
      key: "apps.<id>.open_world_enabled",
      type: "boolean",
      description:
        "Allow or block tools in this app that advertise `open_world_hint = true`.",
    },
    {
      key: "apps.<id>.default_tools_enabled",
      type: "boolean",
      description:
        "Default enabled state for tools in this app unless a per-tool override exists.",
    },
    {
      key: "apps.<id>.approvals_reviewer",
      type: "user | auto_review",
      description:
        "Reviewer for this app's tool approval prompts. Overrides `apps._default.approvals_reviewer`.",
    },
    {
      key: "apps.<id>.default_tools_approval_mode",
      type: "auto | prompt | writes | approve",
      description:
        "Default approval behavior for tools in this app unless a per-tool override exists.",
    },
    {
      key: "apps.<id>.tools.<tool>.enabled",
      type: "boolean",
      description:
        "Per-tool enabled override for an app tool (for example `repos/list`).",
    },
    {
      key: "apps.<id>.tools.<tool>.approval_mode",
      type: "auto | prompt | writes | approve",
      description: "Per-tool approval behavior override for a single app tool.",
    },
    {
      key: "tool_suggest.discoverables",
      type: "array<table>",
      description:
        'Allow tool suggestions for additional discoverable connectors or plugins. Each entry uses `type = "connector"` or `"plugin"` and an `id`.',
    },
    {
      key: "tool_suggest.disabled_tools",
      type: "array<table>",
      description:
        'Disable suggestions for specific discoverable connectors or plugins. Each entry uses `type = "connector"` or `"plugin"` and an `id`.',
    },
    {
      key: "features.apps",
      type: "boolean",
      description:
        "Enable app (connector) integrations (stable; on by default). App and connector traffic is not controlled by the sandboxed-command network proxy or its domain allowlist.",
    },
    {
      key: "features.hooks",
      type: "boolean",
      description:
        "Enable lifecycle hooks loaded from `hooks.json` or inline `[hooks]` config. `features.codex_hooks` is a deprecated alias.",
    },
    {
      key: "features.code_mode.enabled",
      type: "boolean",
      description:
        "Enable code mode feature configuration. This feature is under development and off by default.",
    },
    {
      key: "features.code_mode.excluded_tool_namespaces",
      type: "array<string>",
      description:
        "Tool namespaces code mode excludes from nested code-mode tool guidance and executor exposure.",
    },
    {
      key: "features.code_mode.direct_only_tool_namespaces",
      type: "array<string>",
      description:
        "Tool namespaces code mode can use only through direct tool calls.",
    },
    {
      key: "features.context_management.experimental_mode",
      type: "boolean",
      description:
        "Enable experimental context management (off by default). Rather than repeatedly compressing context into a single summary, it uses notes and searchable history to preserve accumulated details. Requires ChatGPT sign-in on Plus, Pro, or Pro Lite.",
    },
    {
      key: "features.rollout_budget.enabled",
      type: "boolean",
      description:
        "Enable rollout budget tracking. This feature is under development and off by default. When enabled, `features.rollout_budget.limit_tokens` is required.",
    },
    {
      key: "features.rollout_budget.limit_tokens",
      type: "integer",
      description:
        "Positive token limit for rollout budget tracking. Required when rollout budget is enabled.",
    },
    {
      key: "features.rollout_budget.reminder_interval_tokens",
      type: "integer",
      description:
        "Positive token interval between rollout budget reminders. Defaults to 10% of `limit_tokens`, with a minimum of 1 token.",
    },
    {
      key: "features.rollout_budget.sampling_token_weight",
      type: "number",
      description:
        "Finite non-negative multiplier for sampled tokens in rollout budget accounting. Defaults to `1.0`.",
    },
    {
      key: "features.rollout_budget.prefill_token_weight",
      type: "number",
      description:
        "Finite non-negative multiplier for prefill tokens in rollout budget accounting. Defaults to `1.0`.",
    },
    {
      key: "hooks",
      type: "table",
      description:
        "Lifecycle hooks configured inline in `config.toml`. Uses the same event schema as `hooks.json`; see the Hooks guide for examples and supported events.",
    },
    {
      key: "hooks.<Event>",
      type: "array<table>",
      description:
        "Matcher groups for hook events such as `PreToolUse`, `PermissionRequest`, `PostToolUse`, `PreCompact`, `PostCompact`, `SessionStart`, `SessionEnd`, `SubagentStart`, `SubagentStop`, `UserPromptSubmit`, `Stop`, or `Interrupt`.",
    },
    {
      key: "hooks.<Event>[].hooks",
      type: "array<table>",
      description:
        "Hook handlers for a matcher group. Command and MCP tool hooks are supported while prompt and agent hook handlers are parsed but skipped.",
    },
    {
      key: "hooks.<Event>[].hooks[].async",
      type: "boolean",
      description:
        "Run a command hook in the background without delaying the triggering operation. Defaults to `false`; `SessionEnd` always runs synchronously. See [Run hooks in the background](https://learn.chatgpt.com/docs/hooks#run-hooks-in-the-background).",
    },
    {
      key: "hooks.<Event>[].hooks[].additionalContextLimit",
      type: "integer",
      description:
        "Approximate per-handler token threshold for saving oversized `additionalContext` to disk and showing the model a shorter preview. Defaults to `2500`; `0` passes the full context directly to the model. See [Large hook output](https://learn.chatgpt.com/docs/hooks#large-hook-output).",
    },
    {
      key: "hooks.<Event>[].hooks[].commandWindows",
      type: "string",
      description:
        "Windows-only command override for command hooks. The TOML alias `command_windows` is also accepted.",
    },
    {
      key: "features.memories",
      type: "boolean",
      description:
        "Enable [Memories](https://learn.chatgpt.com/docs/customization/memories) (off by default).",
    },
    {
      key: "mcp_optional_startup_grace_ms",
      type: "integer (milliseconds)",
      description:
        "Shared wait for optional MCP servers when building the initial tool catalog. Defaults to `1000`. Set to `0` to wait for each server's `startup_timeout_sec` instead.",
    },
    {
      key: "mcp_servers.<id>.command",
      type: "string",
      description: "Launcher command for an MCP stdio server.",
    },
    {
      key: "mcp_servers.<id>.args",
      type: "array<string>",
      description: "Arguments passed to the MCP stdio server command.",
    },
    {
      key: "mcp_servers.<id>.env",
      type: "map<string,string>",
      description: "Environment variables forwarded to the MCP stdio server.",
    },
    {
      key: "mcp_servers.<id>.env_vars",
      type: 'array<string | { name = string, source = "local" | "remote" }>',
      description:
        'Additional environment variables to whitelist for an MCP stdio server. String entries default to `source = "local"`; use `source = "remote"` only with executor-backed remote stdio.',
    },
    {
      key: "mcp_servers.<id>.cwd",
      type: "string",
      description: "Working directory for the MCP stdio server process.",
    },
    {
      key: "mcp_servers.<id>.url",
      type: "string",
      description: "Endpoint for an MCP streamable HTTP server.",
    },
    {
      key: "mcp_servers.<id>.auth",
      type: "oauth | chatgpt",
      description:
        "Authentication fallback for an MCP HTTP server after configured bearer tokens and authorization headers. `oauth` (default) uses stored MCP OAuth credentials when available. `chatgpt` uses the current ChatGPT session for the trusted first-party ChatGPT origin, then falls back to stored OAuth. Both modes can connect without authentication if no credential source resolves.",
    },
    {
      key: "mcp_servers.<id>.oauth.client_id",
      type: "string",
      description:
        "Pre-registered OAuth client ID used for authorization and token exchange with this MCP server.",
    },
    {
      key: "mcp_servers.<id>.oauth.callback_url",
      type: "string",
      description:
        "Server-specific OAuth callback. Pre-registered clients reuse it when issuer identification is supported or the URL already ends in the server-specific callback ID. Otherwise, Codex uses the global or default callback with that ID appended. Clients without a pre-registered ID use this callback during client registration.",
    },
    {
      key: "mcp_servers.<id>.oauth.callback_port",
      type: "integer",
      description:
        "Fixed OAuth callback listener port for this MCP server. Overrides `mcp_oauth_callback_port`. For a direct loopback callback with an explicit URL port, configure the same listener port.",
    },
    {
      key: "mcp_servers.<id>.bearer_token_env_var",
      type: "string",
      description:
        "Environment variable sourcing the bearer token for an MCP HTTP server.",
    },
    {
      key: "mcp_servers.<id>.http_headers",
      type: "map<string,string>",
      description: "Static HTTP headers included with each MCP HTTP request.",
    },
    {
      key: "mcp_servers.<id>.http_headers_helper",
      type: "string (command)",
      description:
        "Local command that prints a JSON object of HTTP header names and values. Supported only for locally connected HTTP MCP servers. Explicit bearer tokens and OAuth credentials take precedence over helper-provided Authorization headers.",
    },
    {
      key: "mcp_servers.<id>.env_http_headers",
      type: "map<string,string>",
      description:
        "HTTP headers populated from environment variables for an MCP HTTP server.",
    },
    {
      key: "mcp_servers.<id>.enabled",
      type: "boolean",
      description: "Disable an MCP server without removing its configuration.",
    },
    {
      key: "mcp_servers.<id>.required",
      type: "boolean",
      description:
        "When true, fail startup/resume if this enabled MCP server cannot initialize.",
    },
    {
      key: "mcp_servers.<id>.startup_timeout_sec",
      type: "number",
      description:
        "Override the default 10s startup timeout for an MCP server.",
    },
    {
      key: "mcp_servers.<id>.startup_timeout_ms",
      type: "number",
      description: "Alias for `startup_timeout_sec` in milliseconds.",
    },
    {
      key: "mcp_servers.<id>.tool_timeout_sec",
      type: "number",
      description:
        "Override the default 60s per-tool timeout for an MCP server.",
    },
    {
      key: "mcp_servers.<id>.enabled_tools",
      type: "array<string>",
      description: "Allow list of tool names exposed by the MCP server.",
    },
    {
      key: "mcp_servers.<id>.disabled_tools",
      type: "array<string>",
      description:
        "Deny list applied after `enabled_tools` for the MCP server.",
    },
    {
      key: "mcp_servers.<id>.default_tools_approval_mode",
      type: "auto | prompt | writes | approve",
      description:
        "Default approval behavior for MCP tools on this server unless a per-tool override exists.",
    },
    {
      key: "mcp_servers.<id>.tools.<tool>.approval_mode",
      type: "auto | prompt | writes | approve",
      description:
        "Per-tool approval behavior override for one MCP tool on this server.",
    },
    {
      key: "mcp_servers.<id>.tools.<tool>.output_token_limit",
      type: "integer (positive)",
      description:
        "Token budget for one MCP tool's output, before the standard 20% serialization allowance. Overrides the model's default output truncation budget for that tool.",
    },
    {
      key: "mcp_servers.<id>.scopes",
      type: "array<string>",
      description:
        "OAuth scopes to request when authenticating to that MCP server.",
    },
    {
      key: "mcp_servers.<id>.oauth_resource",
      type: "string",
      description:
        "Optional RFC 8707 OAuth resource parameter to include during MCP login.",
    },
    {
      key: "mcp_servers.<id>.experimental_environment",
      type: "local | remote",
      description:
        "Experimental placement for an MCP server. `remote` starts stdio servers through a remote executor environment; streamable HTTP remote placement is not implemented.",
    },
    {
      key: "agents",
      type: "table",
      description:
        "Multi-agent settings and custom role declarations. Scalar setting names are reserved and can't be used as custom role names.",
    },
    {
      key: "agents.enabled",
      type: "boolean",
      description: "Enable or disable multi-agent tools (default: true).",
    },
    {
      key: "agents.max_concurrent_threads_per_session",
      type: "number",
      description:
        "Maximum number of spawned-agent threads that can be open concurrently, excluding the primary thread. When unset, Codex chooses the default.",
    },
    {
      key: "agents.max_threads",
      type: "number",
      description:
        "Legacy alias for `agents.max_concurrent_threads_per_session`.",
    },
    {
      key: "agents.default_subagent_model",
      type: "string",
      description:
        "Default model for spawned agents. An explicit spawn model takes precedence.",
    },
    {
      key: "agents.default_subagent_reasoning_effort",
      type: "string",
      description:
        "Default reasoning effort for spawned agents. An explicit spawn effort takes precedence.",
    },
    {
      key: "agents.interrupt_message",
      type: "boolean",
      description:
        "Record a model-visible message when an agent turn is interrupted (default: true).",
    },
    {
      key: "agents.<name>.description",
      type: "string",
      description:
        "Role guidance shown to Codex when choosing and spawning that agent type.",
    },
    {
      key: "agents.<name>.config_file",
      type: "string (path)",
      description:
        "Path to a TOML config layer for that role; relative paths resolve from the config file that declares the role.",
    },
    {
      key: "memories.generate_memories",
      type: "boolean",
      description:
        "When `false`, newly created threads are not stored as memory-generation inputs. Defaults to `true`.",
    },
    {
      key: "memories.use_memories",
      type: "boolean",
      description:
        "When `false`, Codex skips injecting existing memories into future sessions. Defaults to `true`.",
    },
    {
      key: "memories.disable_on_external_context",
      type: "boolean",
      description:
        "When `true`, threads that use external context such as MCP tool calls, web search, or tool search are kept out of memory generation. Defaults to `false`. Legacy alias: `memories.no_memories_if_mcp_or_web_search`.",
    },
    {
      key: "memories.max_raw_memories_for_consolidation",
      type: "number",
      description:
        "Maximum recent raw memories retained for global consolidation. Defaults to `256` and is capped at `4096`.",
    },
    {
      key: "memories.max_unused_days",
      type: "number",
      description:
        "Maximum days since a memory was last used before it becomes ineligible for consolidation. Defaults to `30` and is clamped to `0`-`365`.",
    },
    {
      key: "memories.max_rollout_age_days",
      type: "number",
      description:
        "Maximum age of threads considered for memory generation. Defaults to `30` and is clamped to `0`-`90`.",
    },
    {
      key: "memories.max_rollouts_per_startup",
      type: "number",
      description:
        "Maximum rollout candidates processed per startup pass. Defaults to `16` and is capped at `128`.",
    },
    {
      key: "memories.min_rollout_idle_hours",
      type: "number",
      description:
        "Minimum idle time before a thread is considered for memory generation. Defaults to `6` and is clamped to `1`-`48`.",
    },
    {
      key: "memories.min_rate_limit_remaining_percent",
      type: "number",
      description:
        "Minimum remaining percentage required in Codex rate-limit windows before memory generation starts. Defaults to `25` and is clamped to `0`-`100`.",
    },
    {
      key: "memories.extract_model",
      type: "string",
      description: "Optional model override for per-thread memory extraction.",
    },
    {
      key: "memories.consolidation_model",
      type: "string",
      description: "Optional model override for global memory consolidation.",
    },
    {
      key: "features.unified_exec",
      type: "boolean",
      description:
        "Use the unified PTY-backed exec tool (stable; enabled by default except on Windows).",
    },
    {
      key: "features.shell_snapshot",
      type: "boolean",
      description:
        "Snapshot shell environment to speed up repeated commands (stable; on by default).",
    },
    {
      key: "features.multi_agent",
      type: "boolean",
      description:
        "Enable multi-agent collaboration tools (`spawn_agent`, `send_input`, `resume_agent`, `wait_agent`, and `close_agent`) (stable; on by default).",
    },
    {
      key: "features.goals",
      type: "boolean",
      description:
        "Enable persisted goals and automatic continuation (stable; on by default).",
    },
    {
      key: "features.remote_plugin",
      type: "boolean",
      description: "Enable the remote plugin catalog (stable; on by default).",
    },
    {
      key: "features.personality",
      type: "boolean",
      description:
        "Enable personality selection controls (stable; on by default).",
    },
    {
      key: "features.network_proxy",
      type: "boolean | table",
      description:
        "Start the network proxy for sandboxed commands (experimental; off by default). Required to enforce permission-profile domain rules unless enabled administrator-managed `experimental_network` requirements start the proxy. Use a table when setting feature-level policy options such as `domains`. Does not filter web search, apps, MCP, or other hosted tools.",
    },
    {
      key: "features.network_proxy.enabled",
      type: "boolean",
      description:
        "Start the sandboxed-command network proxy when command network access is enabled. Defaults to `false`; permission-profile domain rules are not enforced while the proxy is off.",
    },
    {
      key: "features.network_proxy.domains",
      type: "map<string, allow | deny>",
      description:
        "Domain policy for sandboxed networking. Unset by default, which means no external destinations are allowed until you add `allow` rules. Supports exact hosts, `*.example.com` for subdomains only, `**.example.com` for apex plus subdomains, and global `*` allow rules; prefer scoped rules because `*` broadly opens public outbound access. Add `deny` rules for blocked destinations; `deny` wins on conflicts.",
    },
    {
      key: "features.network_proxy.unix_sockets",
      type: "map<string, allow | deny>",
      description:
        "Unix socket policy for sandboxed networking. Unset by default; add `allow` entries for permitted sockets.",
    },
    {
      key: "features.network_proxy.allow_local_binding",
      type: "boolean",
      description:
        "Allow broader local/private-network access. Defaults to `false`; exact local IP literal or `localhost` allow rules can still permit specific local targets.",
    },
    {
      key: "features.network_proxy.enable_socks5",
      type: "boolean",
      description: "Expose SOCKS5 support. Defaults to `true`.",
    },
    {
      key: "features.network_proxy.enable_socks5_udp",
      type: "boolean",
      description: "Allow UDP over SOCKS5. Defaults to `true`.",
    },
    {
      key: "features.network_proxy.allow_upstream_proxy",
      type: "boolean",
      description:
        "Allow chaining through an upstream proxy from the environment. Defaults to `true`.",
    },
    {
      key: "features.network_proxy.dangerously_allow_non_loopback_proxy",
      type: "boolean",
      description:
        "Permit non-loopback listener addresses. Defaults to `false`; enabling it can expose proxy listeners beyond localhost.",
    },
    {
      key: "features.network_proxy.dangerously_allow_all_unix_sockets",
      type: "boolean",
      description:
        "Permit arbitrary Unix socket destinations instead of allowlist-only access. Defaults to `false`; use only in tightly controlled environments.",
    },
    {
      key: "features.network_proxy.proxy_url",
      type: "string",
      description:
        'HTTP listener URL for sandboxed networking. Defaults to `"http://127.0.0.1:3128"`.',
    },
    {
      key: "features.network_proxy.socks_url",
      type: "string",
      description:
        'SOCKS5 listener URL. Defaults to `"http://127.0.0.1:8081"`.',
    },
    {
      key: "features.web_search",
      type: "boolean",
      description:
        "Deprecated legacy toggle; prefer the top-level `web_search` setting.",
    },
    {
      key: "features.web_search_cached",
      type: "boolean",
      description:
        'Deprecated legacy toggle. When `web_search` is unset, true maps to `web_search = "cached"`.',
    },
    {
      key: "features.web_search_request",
      type: "boolean",
      description:
        'Deprecated legacy toggle. When `web_search` is unset, true maps to `web_search = "live"`.',
    },
    {
      key: "features.shell_tool",
      type: "boolean",
      description:
        "Enable the default `shell` tool for running commands (stable; on by default).",
    },
    {
      key: "features.enable_request_compression",
      type: "boolean",
      description:
        "Compress streaming request bodies with zstd when supported (stable; on by default).",
    },
    {
      key: "features.skill_mcp_dependency_install",
      type: "boolean",
      description:
        "Allow prompting and installing missing MCP dependencies for skills (stable; on by default).",
    },
    {
      key: "features.fast_mode",
      type: "boolean",
      description:
        "Enable model-catalog service tier selection in the TUI, including Fast-tier commands when the active model advertises them (stable; on by default).",
    },
    {
      key: "features.prevent_idle_sleep",
      type: "boolean",
      description:
        "Prevent the machine from sleeping while a turn is actively running (experimental; off by default).",
    },
    {
      key: "suppress_unstable_features_warning",
      type: "boolean",
      description:
        "Suppress the warning that appears when under-development feature flags are enabled.",
    },
    {
      key: "model_providers.<id>",
      type: "table",
      description:
        "Custom provider definition. Built-in provider IDs (`openai`, `ollama`, and `lmstudio`) are reserved and cannot be overridden.",
    },
    {
      key: "model_providers.<id>.name",
      type: "string",
      description: "Display name for a custom model provider.",
    },
    {
      key: "model_providers.<id>.base_url",
      type: "string",
      description: "API base URL for the model provider.",
    },
    {
      key: "model_providers.<id>.env_key",
      type: "string",
      description: "Environment variable supplying the provider API key.",
    },
    {
      key: "model_providers.<id>.env_key_instructions",
      type: "string",
      description: "Optional setup guidance for the provider API key.",
    },
    {
      key: "model_providers.<id>.experimental_bearer_token",
      type: "string",
      description:
        "Direct bearer token for the provider (discouraged; use `env_key`).",
    },
    {
      key: "model_providers.<id>.requires_openai_auth",
      type: "boolean",
      description:
        "The provider uses OpenAI authentication (defaults to false).",
    },
    {
      key: "model_providers.<id>.wire_api",
      type: "responses",
      description:
        "Protocol used by the provider. `responses` is the only supported value, and it is the default when omitted.",
    },
    {
      key: "model_providers.<id>.query_params",
      type: "map<string,string>",
      description: "Extra query parameters appended to provider requests.",
    },
    {
      key: "model_providers.<id>.http_headers",
      type: "map<string,string>",
      description: "Static HTTP headers added to provider requests.",
    },
    {
      key: "model_providers.<id>.env_http_headers",
      type: "map<string,string>",
      description:
        "HTTP headers populated from environment variables when present.",
    },
    {
      key: "model_providers.<id>.request_max_retries",
      type: "number",
      description:
        "Retry count for HTTP requests to the provider (default: 4).",
    },
    {
      key: "model_providers.<id>.stream_max_retries",
      type: "number",
      description: "Retry count for SSE streaming interruptions (default: 5).",
    },
    {
      key: "model_providers.<id>.stream_idle_timeout_ms",
      type: "number",
      description:
        "Idle timeout for SSE streams in milliseconds (default: 300000).",
    },
    {
      key: "model_providers.<id>.supports_websockets",
      type: "boolean",
      description:
        "Whether that provider supports the Responses API WebSocket transport.",
    },
    {
      key: "model_providers.<id>.supports_standalone_web_search",
      type: "boolean",
      description:
        "Advertise support for a compatible standalone web search endpoint (default: false). Standalone search remains under development and off by default; provider compatibility alone doesn't enable it.",
    },
    {
      key: "model_providers.<id>.auth",
      type: "table",
      description:
        "Command-backed bearer token configuration for a custom provider. Do not combine with `env_key`, `experimental_bearer_token`, or `requires_openai_auth`.",
    },
    {
      key: "model_providers.<id>.auth.command",
      type: "string",
      description:
        "Command to run when Codex needs a bearer token. The command must print the token to stdout.",
    },
    {
      key: "model_providers.<id>.auth.args",
      type: "array<string>",
      description: "Arguments passed to the token command.",
    },
    {
      key: "model_providers.<id>.auth.timeout_ms",
      type: "number",
      description:
        "Maximum token command runtime in milliseconds (default: 5000).",
    },
    {
      key: "model_providers.<id>.auth.refresh_interval_ms",
      type: "number",
      description:
        "How often Codex proactively refreshes the token in milliseconds (default: 300000). Set to `0` to refresh only after an authentication retry.",
    },
    {
      key: "model_providers.<id>.auth.cwd",
      type: "string (path)",
      description: "Working directory for the token command.",
    },
    {
      key: "model_providers.amazon-bedrock.aws.profile",
      type: "string",
      description:
        "AWS profile name used by the built-in `amazon-bedrock` provider.",
    },
    {
      key: "model_providers.amazon-bedrock.aws.region",
      type: "string",
      description: "AWS region used by the built-in `amazon-bedrock` provider.",
    },
    {
      key: "model_reasoning_effort",
      type: "minimal | low | medium | high | xhigh",
      description:
        "Adjust reasoning effort for supported models (Responses API only; `xhigh` is model-dependent).",
    },
    {
      key: "plan_mode_reasoning_effort",
      type: "none | minimal | low | medium | high | xhigh",
      description:
        "Plan-mode-specific reasoning override. When unset, Plan mode uses its built-in preset default.",
    },
    {
      key: "model_reasoning_summary",
      type: "auto | concise | detailed | none",
      description:
        "Select reasoning summary detail or disable summaries entirely.",
    },
    {
      key: "model_verbosity",
      type: "low | medium | high",
      description:
        "Optional GPT-5 Responses API verbosity override; when unset, the selected model/preset default is used.",
    },
    {
      key: "model_supports_reasoning_summaries",
      type: "boolean",
      description: "Force Codex to send or not send reasoning metadata.",
    },
    {
      key: "shell_environment_policy.inherit",
      type: "all | core | none",
      description:
        "Baseline environment inheritance when spawning subprocesses.",
    },
    {
      key: "shell_environment_policy.ignore_default_excludes",
      type: "boolean",
      description:
        "Keep variables containing KEY, SECRET, or TOKEN before other filters run (default: true). Set to false to apply automatic secret-name exclusions.",
    },
    {
      key: "shell_environment_policy.filters",
      type: "map<string, include | exclude>",
      description:
        "Canonical case-insensitive environment-variable pattern filters. Include entries create an allowlist and can't restore excluded values. Explicit `set` values apply after exclusions. Don't combine filters with legacy `exclude` or `include_only` arrays in the same layer.",
    },
    {
      key: "shell_environment_policy.exclude",
      type: "array<string>",
      description:
        "Legacy environment-variable exclusion patterns. Use `shell_environment_policy.filters` for new configuration; don't combine both forms in the same layer.",
    },
    {
      key: "shell_environment_policy.include_only",
      type: "array<string>",
      description:
        "Legacy allowlist of environment-variable patterns. Use `shell_environment_policy.filters` for new configuration; don't combine both forms in the same layer.",
    },
    {
      key: "shell_environment_policy.set",
      type: "map<string,string>",
      description:
        "Explicit environment values injected after exclusions; include filters can still remove them.",
    },
    {
      key: "shell_environment_policy.experimental_use_profile",
      type: "boolean",
      description: "Use the user shell profile when spawning subprocesses.",
    },
    {
      key: "project_root_markers",
      type: "array<string>",
      description:
        "List of project root marker filenames; used when searching parent directories for the project root.",
    },
    {
      key: "project_doc_max_bytes",
      type: "number",
      description:
        "Maximum bytes read from `AGENTS.md` when building project instructions.",
    },
    {
      key: "project_doc_fallback_filenames",
      type: "array<string>",
      description: "Additional filenames to try when `AGENTS.md` is missing.",
    },
    {
      key: "history.persistence",
      type: "save-all | none",
      description:
        "Control whether Codex saves session transcripts to history.jsonl.",
    },
    {
      key: "tool_output_token_limit",
      type: "number",
      description:
        "Token budget for storing individual tool/function outputs in history.",
    },
    {
      key: "background_terminal_max_timeout",
      type: "number",
      description:
        "Maximum poll window in milliseconds for empty `write_stdin` polls (background terminal polling). Default: `300000` (5 minutes). Replaces the older `background_terminal_timeout` key.",
    },
    {
      key: "history.max_bytes",
      type: "number",
      description:
        "If set, caps the history file size in bytes by dropping oldest entries.",
    },
    {
      key: "file_opener",
      type: "vscode | vscode-insiders | windsurf | cursor | none",
      description:
        "URI scheme used to open citations from Codex output (default: `vscode`).",
    },
    {
      key: "otel.environment",
      type: "string",
      description:
        "Environment tag applied to emitted OpenTelemetry events (default: `dev`).",
    },
    {
      key: "otel.exporter",
      type: "none | otlp-http | otlp-grpc",
      description:
        "Select the OpenTelemetry exporter and provide any endpoint metadata.",
    },
    {
      key: "otel.trace_exporter",
      type: "none | otlp-http | otlp-grpc",
      description:
        "Select the OpenTelemetry trace exporter and provide any endpoint metadata.",
    },
    {
      key: "otel.metrics_exporter",
      type: "none | statsig | otlp-http | otlp-grpc",
      description:
        "Select the OpenTelemetry metrics exporter (defaults to `statsig`).",
    },
    {
      key: "otel.log_user_prompt",
      type: "boolean",
      description:
        "Opt in to exporting raw user prompts with OpenTelemetry logs.",
    },
    {
      key: "otel.exporter.<id>.endpoint",
      type: "string",
      description: "Exporter endpoint for OTEL logs.",
    },
    {
      key: "otel.exporter.<id>.protocol",
      type: "binary | json",
      description: "Protocol used by the OTLP/HTTP exporter.",
    },
    {
      key: "otel.exporter.<id>.headers",
      type: "map<string,string>",
      description: "Static headers included with OTEL exporter requests.",
    },
    {
      key: "otel.trace_exporter.<id>.endpoint",
      type: "string",
      description: "Trace exporter endpoint for OTEL logs.",
    },
    {
      key: "otel.trace_exporter.<id>.protocol",
      type: "binary | json",
      description: "Protocol used by the OTLP/HTTP trace exporter.",
    },
    {
      key: "otel.trace_exporter.<id>.headers",
      type: "map<string,string>",
      description: "Static headers included with OTEL trace exporter requests.",
    },
    {
      key: "otel.exporter.<id>.tls.ca-certificate",
      type: "string",
      description: "CA certificate path for OTEL exporter TLS.",
    },
    {
      key: "otel.exporter.<id>.tls.client-certificate",
      type: "string",
      description: "Client certificate path for OTEL exporter TLS.",
    },
    {
      key: "otel.exporter.<id>.tls.client-private-key",
      type: "string",
      description: "Client private key path for OTEL exporter TLS.",
    },
    {
      key: "otel.trace_exporter.<id>.tls.ca-certificate",
      type: "string",
      description: "CA certificate path for OTEL trace exporter TLS.",
    },
    {
      key: "otel.trace_exporter.<id>.tls.client-certificate",
      type: "string",
      description: "Client certificate path for OTEL trace exporter TLS.",
    },
    {
      key: "otel.trace_exporter.<id>.tls.client-private-key",
      type: "string",
      description: "Client private key path for OTEL trace exporter TLS.",
    },
    {
      key: "desktop.custom_file_handlers.<id>",
      type: "table",
      description:
        "User-level only. Defines an additional **Open in** target for the ChatGPT desktop app. See [Add custom file handlers](https://learn.chatgpt.com/docs/config-file/config-advanced#add-custom-file-handlers) for examples and handler ID constraints.",
    },
    {
      key: "desktop.custom_file_handlers.<id>.label",
      type: "string",
      description: "Display name shown in **Open in** menus. Required.",
    },
    {
      key: "desktop.custom_file_handlers.<id>.icon",
      type: "string",
      description:
        "Bundled asset path, Base64-encoded `data:image/...` URL, file URI, or absolute local path for the handler icon. Required; unsupported sources use the default VS Code icon.",
    },
    {
      key: "desktop.custom_file_handlers.<id>.command",
      type: "string",
      description:
        "Executable path or command name to detect and launch. Required.",
    },
    {
      key: "desktop.custom_file_handlers.<id>.args",
      type: "array<string>",
      description:
        "Arguments inserted between the command and file input (default: `[]`).",
    },
    {
      key: "desktop.custom_file_handlers.<id>.input",
      type: "path | json_argument | json_stdin",
      description:
        "How the app sends file input to the handler (default: `path`).",
    },
    {
      key: "desktop.custom_file_handlers.<id>.supports_ssh",
      type: "boolean",
      description:
        "Offer the handler for files in SSH workspaces (default: `false`).",
    },
    {
      key: "tui",
      type: "table",
      description:
        "TUI-specific options such as enabling inline desktop notifications.",
    },
    {
      key: "tui.notifications",
      type: "boolean | array<string>",
      description:
        "Enable TUI notifications; optionally restrict to specific event types.",
    },
    {
      key: "tui.notification_method",
      type: "auto | osc9 | bel",
      description:
        "Notification method for terminal notifications (default: auto).",
    },
    {
      key: "tui.notification_condition",
      type: "unfocused | always",
      description:
        "Control whether TUI notifications fire only when the terminal is unfocused or regardless of focus. Defaults to `unfocused`.",
    },
    {
      key: "tui.animations",
      type: "boolean",
      description:
        "Enable terminal animations (welcome screen, shimmer, spinner) (default: true).",
    },
    {
      key: "tui.alternate_screen",
      type: "auto | always | never",
      description:
        "Control alternate screen usage for the TUI (default: auto; auto skips it in Zellij to preserve scrollback).",
    },
    {
      key: "tui.resume_cwd",
      type: "current | session",
      description:
        "Working directory to use when resuming or forking a session. When unset, Codex asks you to choose if your current directory differs from the session's saved directory.",
    },
    {
      key: "tui.vim_mode_default",
      type: "boolean",
      description:
        "Start the composer in Vim normal mode instead of insert mode (default: false). You can still toggle it per session with `/vim`.",
    },
    {
      key: "tui.raw_output_mode",
      type: "boolean",
      description:
        "Start the TUI in raw scrollback mode for copy-friendly terminal selection (default: false). You can toggle it with `/raw` or the default `alt-r` key binding.",
    },
    {
      key: "tui.show_tooltips",
      type: "boolean",
      description:
        "Show onboarding tooltips in the TUI welcome screen (default: true).",
    },
    {
      key: "tui.status_line",
      type: "array<string> | null",
      description:
        "Ordered list of TUI footer status-line item identifiers. `null` disables the status line.",
    },
    {
      key: "tui.terminal_title",
      type: "array<string> | null",
      description:
        'Ordered list of terminal window/tab title item identifiers. Defaults to `["spinner", "project"]`; `null` disables title updates.',
    },
    {
      key: "tui.theme",
      type: "string",
      description:
        "Syntax-highlighting theme override (kebab-case theme name).",
    },
    {
      key: "tui.keymap.<context>.<action>",
      type: "string | array<string>",
      description:
        "Keyboard shortcut binding for a TUI action. Supported contexts include `global`, `chat`, `composer`, `editor`, `vim_normal`, `vim_operator`, `vim_text_object`, `pager`, `list`, and `approval`. Selected composer actions fall back to matching `tui.keymap.global` bindings; context-specific bindings take precedence when supported.",
    },
    {
      key: "tui.keymap.<context>.<action> = []",
      type: "empty array",
      description:
        "Unbind the action in that keymap context. Key names use normalized strings such as `ctrl-a`, `shift-enter`, `page-down`, or `minus`.",
    },
    {
      key: "marketplaces.<name>.source_type",
      type: "git | local",
      description:
        "Source kind for a configured plugin marketplace. Marketplaces can be defined in system, cloud-managed, user, or trusted-project config.toml.",
    },
    {
      key: "marketplaces.<name>.source",
      type: "string",
      description:
        "Git repository location or local marketplace root directory. Use an absolute path for a local source; the directory contains .agents/plugins/marketplace.json.",
    },
    {
      key: "marketplaces.<name>.ref",
      type: "string",
      description: "Optional Git branch, tag, or commit for the marketplace.",
    },
    {
      key: "marketplaces.<name>.sparse_paths",
      type: "array<string>",
      description:
        "Optional sparse checkout paths for a Git marketplace. Include the marketplace catalog and any local plugin directories it references.",
    },
    {
      key: "plugins.<plugin>.enabled",
      type: "boolean",
      description:
        "Enable or disable a local-marketplace plugin using a `plugin-name@marketplace-name` key. Read from the effective merged config; trusted-project settings can override user, cloud-managed, and system defaults. Marketplace refresh can install or refresh configured plugins even when disabled. This does not override workspace-managed enabled states.",
    },
    {
      key: "plugins.<plugin>.mcp_servers.<server>.enabled",
      type: "boolean",
      description:
        "Enable or disable an MCP server bundled by an installed plugin without changing the plugin manifest.",
    },
    {
      key: "plugins.<plugin>.mcp_servers.<server>.default_tools_approval_mode",
      type: "auto | prompt | writes | approve",
      description:
        "Default approval behavior for tools on a plugin-provided MCP server.",
    },
    {
      key: "plugins.<plugin>.mcp_servers.<server>.enabled_tools",
      type: "array<string>",
      description:
        "Allow list of tools exposed from a plugin-provided MCP server.",
    },
    {
      key: "plugins.<plugin>.mcp_servers.<server>.disabled_tools",
      type: "array<string>",
      description:
        "Deny list applied after `enabled_tools` for a plugin-provided MCP server.",
    },
    {
      key: "plugins.<plugin>.mcp_servers.<server>.tools.<tool>.approval_mode",
      type: "auto | prompt | writes | approve",
      description:
        "Per-tool approval behavior override for a plugin-provided MCP tool.",
    },
    {
      key: "tui.model_availability_nux.<model>",
      type: "integer",
      description: "Internal startup-tooltip state keyed by model slug.",
    },
    {
      key: "hide_agent_reasoning",
      type: "boolean",
      description:
        "Suppress reasoning events in both the TUI and `codex exec` output.",
    },
    {
      key: "show_raw_agent_reasoning",
      type: "boolean",
      description:
        "Surface raw reasoning content when the active model emits it.",
    },
    {
      key: "disable_paste_burst",
      type: "boolean",
      description: "Disable burst-paste detection in the TUI.",
    },
    {
      key: "windows_wsl_setup_acknowledged",
      type: "boolean",
      description: "Track Windows onboarding acknowledgement (Windows only).",
    },
    {
      key: "chatgpt_base_url",
      type: "string",
      description: "Override the base URL used during the ChatGPT login flow.",
    },
    {
      key: "cli_auth_credentials_store",
      type: "file | keyring | auto | ephemeral",
      description: "Control where the CLI stores cached credentials.",
    },
    {
      key: "mcp_oauth_credentials_store",
      type: "auto | file | keyring",
      description: "Preferred store for MCP OAuth credentials.",
    },
    {
      key: "mcp_oauth_callback_port",
      type: "integer",
      description:
        "Optional global fixed port for the local HTTP callback server used during MCP OAuth login. A server-specific `oauth.callback_port` takes precedence. When neither is set, Codex binds to an ephemeral port chosen by the OS.",
    },
    {
      key: "mcp_oauth_callback_url",
      type: "string",
      description:
        "Optional base callback URL for MCP OAuth login, such as a devbox ingress URL. Newly added pre-registered clients use this URL unchanged when the authorization server supports issuer identification; existing clients without a saved callback append a server-specific callback ID. Without issuer support, any pre-registered MCP server whose configured callback lacks the required ID falls back to this URL with the ID appended. Callback URL ports don't select the listener port.",
    },
    {
      key: "experimental_use_unified_exec_tool",
      type: "boolean",
      description:
        "Legacy name for enabling unified exec; prefer `[features].unified_exec` or `codex --enable unified_exec`.",
    },
    {
      key: "tools.web_search",
      type: 'boolean | { context_size = "low|medium|high", allowed_domains = [string], location = { country, region, city, timezone } }',
      description:
        "Optional web search tool configuration. The object form can set search context size, allowed search domains, and approximate user location. These search-domain filters are separate from sandboxed-command network domain rules and do not restrict connectors or MCP servers.",
    },
    {
      key: "tools.view_image",
      type: "boolean",
      description: "Enable the local-image attachment tool `view_image`.",
    },
    {
      key: "web_search",
      type: "disabled | cached | indexed | live",
      description:
        'Web search mode (default: `"cached"`; cached uses an OpenAI-maintained index without external web access; indexed permits external access only when gated by the search index; if you use `--yolo` or another full access sandbox setting, it defaults to `"live"`). Use `"live"` for unrestricted live retrieval, or `"disabled"` to remove the tool.',
    },
    {
      key: "default_permissions",
      type: "string",
      description:
        "Name of the default permissions profile to apply to sandboxed tool calls. Built-ins are `:read-only`, `:workspace`, and `:danger-full-access`; custom profile names require matching `[permissions.<name>]` tables. Don't combine with `sandbox_mode` or `[sandbox_workspace_write]`.",
    },
    {
      key: "permissions.<name>.description",
      type: "string",
      description:
        "Human-readable description for this named profile. A profile does not inherit its parent's description through `extends`.",
    },
    {
      key: "permissions.<name>.extends",
      type: "string",
      description:
        "Optional parent profile applied before this named profile. Set it to another named profile, `:read-only`, or `:workspace`; `:danger-full-access`, undefined parents, and cycles are rejected.",
    },
    {
      key: "permissions.<name>.workspace_roots",
      type: "table",
      description:
        "Profile-defined workspace roots that receive `:workspace_roots` filesystem rules alongside the session's runtime workspace roots.",
    },
    {
      key: "permissions.<name>.workspace_roots.<path>",
      type: "boolean",
      description:
        "Opt a path into the profile's workspace root set when `true`. Disabled entries remain inactive.",
    },
    {
      key: "permissions.<name>.filesystem",
      type: "table",
      description:
        "Named filesystem permission profile. Each key is an absolute path or special token such as `:minimal` or `:workspace_roots`.",
    },
    {
      key: "permissions.<name>.filesystem.glob_scan_max_depth",
      type: "number",
      description:
        "Maximum depth for expanding deny-read glob patterns on platforms that snapshot matches before sandbox startup. Must be at least `1` when set.",
    },
    {
      key: "permissions.<name>.filesystem.<path-or-glob>",
      type: '"read" | "write" | "deny" | table',
      description:
        'Grant direct access for a path, glob pattern, or special token, or scope nested entries under that root. Use `"deny"` to deny reads for matching paths.',
    },
    {
      key: 'permissions.<name>.filesystem.":workspace_roots".<subpath-or-glob>',
      type: '"read" | "write" | "deny"',
      description:
        'Scoped filesystem access relative to each effective workspace root. Use `"."` for the root itself; glob subpaths such as `"**/*.env"` can deny reads with `"deny"`.',
    },
    {
      key: "permissions.<name>.network.enabled",
      type: "boolean",
      description:
        "Enable network access for commands in this permission profile. This does not start the network proxy. Without `features.network_proxy` or enabled administrator-managed networking requirements, command network access is direct and profile domain rules are not enforced.",
    },
    {
      key: "permissions.<name>.network.proxy_url",
      type: "string",
      description:
        "HTTP listener URL used when this permissions profile enables sandboxed networking.",
    },
    {
      key: "permissions.<name>.network.enable_socks5",
      type: "boolean",
      description:
        "Expose SOCKS5 support when this permissions profile enables sandboxed networking.",
    },
    {
      key: "permissions.<name>.network.socks_url",
      type: "string",
      description: "SOCKS5 proxy endpoint used by this permissions profile.",
    },
    {
      key: "permissions.<name>.network.enable_socks5_udp",
      type: "boolean",
      description: "Allow UDP over the SOCKS5 listener when enabled.",
    },
    {
      key: "permissions.<name>.network.allow_upstream_proxy",
      type: "boolean",
      description:
        "Allow sandboxed networking to chain through another upstream proxy.",
    },
    {
      key: "permissions.<name>.network.dangerously_allow_non_loopback_proxy",
      type: "boolean",
      description:
        "Permit non-loopback bind addresses for sandboxed networking listeners. Enabling it can expose listeners beyond localhost.",
    },
    {
      key: "permissions.<name>.network.dangerously_allow_all_unix_sockets",
      type: "boolean",
      description:
        "Allow arbitrary Unix socket destinations instead of the default restricted set. Use only in tightly controlled environments.",
    },
    {
      key: "permissions.<name>.network.mode",
      type: "limited | full",
      description: "Network proxy mode used for subprocess traffic.",
    },
    {
      key: "permissions.<name>.network.domains",
      type: "table",
      description:
        "Domain rules for sandboxed commands. Enforced only when `features.network_proxy` or enabled administrator-managed networking requirements activate the proxy. Supports exact hosts, `*.example.com`, `**.example.com`, and global `*` allow rules; `deny` wins. Does not restrict web search, apps, or MCP servers.",
    },
    {
      key: "permissions.<name>.network.domains.<pattern>",
      type: "allow | deny",
      description:
        "Allow or deny an exact host or scoped wildcard pattern such as `*.example.com` or `**.example.com`.",
    },
    {
      key: "permissions.<name>.network.unix_sockets",
      type: "table",
      description:
        "Unix socket allowlist overrides for sandboxed networking. Use socket paths as keys; `allow` adds a path, and `deny` rejects it.",
    },
    {
      key: "permissions.<name>.network.unix_sockets.<path>",
      type: "allow | deny",
      description:
        "Add an absolute Unix socket path to the effective allowlist with `allow`, or reject it with `deny`. Denied entries are omitted from the effective allowlist.",
    },
    {
      key: "permissions.<name>.network.allow_local_binding",
      type: "boolean",
      description:
        "Permit broader local/private-network access through sandboxed networking. Exact local IP literal or `localhost` allow rules can still permit specific local targets when this stays `false`.",
    },
    {
      key: "projects.<path>.trust_level",
      type: "string",
      description:
        'Mark a project or worktree as trusted or untrusted (`"trusted"` | `"untrusted"`). Untrusted projects skip project-scoped `.codex/` layers, including project-local config, hooks, and rules.',
    },
    {
      key: "notice.hide_full_access_warning",
      type: "boolean",
      description: "Track acknowledgement of the full access warning prompt.",
    },
    {
      key: "notice.hide_world_writable_warning",
      type: "boolean",
      description:
        "Track acknowledgement of the Windows world-writable directories warning.",
    },
    {
      key: "notice.hide_rate_limit_model_nudge",
      type: "boolean",
      description: "Track opt-out of the rate limit model switch reminder.",
    },
    {
      key: "notice.hide_gpt5_1_migration_prompt",
      type: "boolean",
      description: "Track acknowledgement of the GPT-5.1 migration prompt.",
    },
    {
      key: "notice.hide_gpt-5.1-codex-max_migration_prompt",
      type: "boolean",
      description:
        "Track acknowledgement of the gpt-5.1-codex-max migration prompt.",
    },
    {
      key: "notice.model_migrations",
      type: "map<string,string>",
      description: "Track acknowledged model migrations as old->new mappings.",
    },
    {
      key: "forced_login_method",
      type: "chatgpt | api",
      description: "Restrict Codex to a specific authentication method.",
    },
    {
      key: "forced_chatgpt_workspace_id",
      type: "string (uuid)",
      description: "Limit ChatGPT logins to a specific workspace identifier.",
    },
  ]}
  client:load
/>

You can find the latest JSON schema for `config.toml` [here](https://learn.chatgpt.com/docs/config-schema.json).

To get autocompletion and diagnostics when editing `config.toml` in VS Code or Cursor, you can install the [Even Better TOML](https://marketplace.visualstudio.com/items?itemName=tamasfe.even-better-toml) extension and add this line to the top of your `config.toml`:

```toml
#:schema https://developers.openai.com/codex/config-schema.json
```

Note: Rename `experimental_instructions_file` to `model_instructions_file`. Codex deprecates the old key; update existing configs to the new name.

### `requirements.toml`
`requirements.toml` is an admin-enforced configuration file that constrains security-sensitive settings users can't override. For details, locations, and examples, see [Admin-enforced requirements](https://learn.chatgpt.com/docs/enterprise/managed-configuration#admin-enforced-requirements-requirementstoml).

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

<ConfigTable
  options={[
    {
      key: "sqlite_home",
      type: "string (path)",
      description:
        "Enforce the directory where Codex stores SQLite-backed runtime state.",
    },
    {
      key: "log_dir",
      type: "string (path)",
      description: "Enforce the directory where Codex writes local log files.",
    },
    {
      key: "model_catalog_json",
      type: "string (path)",
      description: "Enforce the JSON model catalog Codex uses at startup.",
    },
    {
      key: "check_for_update_on_startup",
      type: "boolean",
      description: "Enforce whether Codex checks for updates when it starts.",
    },
    {
      key: "allow_login_shell",
      type: "boolean",
      description: "Enforce whether shell tools can start a login shell.",
    },
    {
      key: "allowed_login_methods",
      type: "array<string>",
      description:
        "Allow `chatgpt`, `api`, or both. If omitted, this setting doesn't restrict login methods. If set, the list must contain at least one method. `api` permits API authentication, including Amazon Bedrock. Set through the local system requirements file or macOS MDM. Cloud-managed values are ignored.",
    },
    {
      key: "allowed_chatgpt_workspaces",
      type: "array<string>",
      description:
        "Restrict ChatGPT login, including Codex access tokens, to the listed workspace IDs. An empty list disables ChatGPT login; API authentication remains available when permitted. Set through the local system requirements file or macOS MDM; cloud-managed values are ignored.",
    },
    {
      key: "cli_auth_credentials_store",
      type: "file | keyring | auto | ephemeral",
      description:
        "Enforce the CLI credential store before authentication loads. `file` uses `CODEX_HOME/auth.json`; `keyring` requires the OS credential store; `auto` falls back to a file if the credential store is unavailable; `ephemeral` keeps credentials in memory for the current process. Set through the local system requirements file or macOS MDM; cloud-managed values are ignored.",
    },
    {
      key: "chatgpt_base_url",
      type: "string",
      description:
        "Enforce the ChatGPT service base URL before authentication and cloud-policy retrieval. This doesn't configure every Codex network destination. Set through the local system requirements file or macOS MDM; cloud-managed values are ignored.",
    },
    {
      key: "feedback",
      type: "table",
      description: "Managed feedback settings.",
    },
    {
      key: "feedback.enabled",
      type: "boolean",
      description:
        "Enforce whether users can submit feedback across Codex clients.",
    },
    {
      key: "allowed_approval_policies",
      type: "array<string>",
      description:
        "Allowed approval policies, such as `on-request`, `never`, and `granular`. Include `untrusted` to permit the stricter policy derived from an untrusted project; it cannot be selected directly with `approval_policy`.",
    },
    {
      key: "allowed_approvals_reviewers",
      type: "array<string>",
      description:
        "Allowed values for `approvals_reviewer`, such as `user` and `auto_review`.",
    },
    {
      key: "guardian_policy_config",
      type: "string",
      description:
        "Managed Markdown policy instructions for automatic review. This takes precedence over local `[auto_review].policy`. Blank values are ignored.",
    },
    {
      key: "allowed_permission_profiles",
      type: "table<boolean>",
      description:
        "Complete list of allowed permission profiles. Profiles set to `true` are allowed. Profiles that are omitted or set to `false` are denied, including profiles added in future versions. When requirements sources are combined, entries are matched by profile name.",
    },
    {
      key: "allowed_permission_profiles.<name>",
      type: "boolean",
      description:
        "Allow or deny a built-in or custom permission profile defined in a loaded config or requirements source. A later, higher-precedence requirements source can use `false` to turn off a profile allowed by an earlier, lower-precedence source.",
    },
    {
      key: "default_permissions",
      type: "string",
      description:
        "Managed default permission profile. The profile must be allowed by `allowed_permission_profiles`. Set this explicitly for predictable behavior; if omitted, Codex defaults to `:workspace` only when both `:workspace` and `:read-only` are explicitly allowed.",
    },
    {
      key: "enforce_residency",
      type: "string",
      description:
        "Require Codex service traffic to use a supported data residency. Currently accepts `us`.",
    },
    {
      key: "models",
      type: "table",
      description:
        "Managed model defaults for new threads. These values take priority over user and project defaults, but an explicit selection for the new thread can override them.",
    },
    {
      key: "models.new_thread",
      type: "table",
      description:
        "Defaults to apply when a new local thread starts. Each model setting is optional.",
    },
    {
      key: "models.new_thread.model",
      type: "string",
      description:
        "Default model for new threads. An explicit `--model` or model/reasoning `--config` override takes precedence.",
    },
    {
      key: "models.new_thread.model_reasoning_effort",
      type: "string",
      description:
        "Default reasoning effort for new threads. An explicit model or reasoning-effort override skips both managed model fields.",
    },
    {
      key: "models.new_thread.service_tier",
      type: "string",
      description:
        "Default service tier for new threads. An explicit service-tier override takes precedence independently of the model fields.",
    },
    {
      key: "permissions",
      type: "table",
      description:
        "Admin-defined permission profiles keyed by profile name. Uses the same profile fields as `config.toml`.",
    },
    {
      key: "permissions.<name>",
      type: "table",
      description:
        "Admin-defined permission profile. The name can't start with `:`, use the reserved name `filesystem`, or duplicate a profile from a loaded config. Uses the same profile fields as `config.toml`; see the Permissions guide for the complete profile schema.",
    },
    {
      key: "allowed_sandbox_modes",
      type: "array<string>",
      description: "Allowed values for `sandbox_mode`.",
    },
    {
      key: "windows",
      type: "table",
      description: "Native Windows sandbox requirements.",
    },
    {
      key: "windows.allowed_sandbox_implementations",
      type: "array<string>",
      description:
        "Allowed native Windows sandbox implementations for `windows.sandbox` (`elevated` and `unelevated`). The list must not be empty. When both are allowed and no mode is selected, Codex prefers `elevated`.",
    },
    {
      key: "windows.sandbox_private_desktop",
      type: "boolean",
      description:
        "Enforce whether the native Windows sandbox starts its child process on a private desktop.",
    },
    {
      key: "remote_sandbox_config",
      type: "array<table>",
      description:
        "Host-specific sandbox requirements. The first entry whose `hostname_patterns` match the resolved host name overrides top-level `allowed_sandbox_modes` for that requirements source. Host-specific entries currently override sandbox modes only.",
    },
    {
      key: "remote_sandbox_config[].hostname_patterns",
      type: "array<string>",
      description:
        "Case-insensitive host name patterns. Supports `*` for any sequence of characters and `?` for one character.",
    },
    {
      key: "remote_sandbox_config[].allowed_sandbox_modes",
      type: "array<string>",
      description:
        "Allowed sandbox modes to apply when this host-specific entry matches.",
    },
    {
      key: "allowed_web_search_modes",
      type: "array<string>",
      description:
        "Allowed values for `web_search` (`disabled`, `cached`, `indexed`, `live`). `disabled` is always allowed; an empty list effectively allows only `disabled`.",
    },
    {
      key: "allow_managed_hooks_only",
      type: "boolean",
      description:
        "When `true`, Codex skips user, project, session, and plugin hooks while still allowing managed hooks from `requirements.toml` and other managed config layers.",
    },
    {
      key: "allow_appshots",
      type: "boolean",
      description:
        "Set to `false` to disable Appshots for managed users. If omitted, Appshots remain unconstrained by requirements and follow normal product availability.",
    },
    {
      key: "allow_remote_control",
      type: "boolean",
      description:
        "Set to `false` to disable device remote control for managed users. If omitted, device remote control remains unconstrained by requirements and follows normal product availability.",
    },
    {
      key: "allow_browser_and_computer_use",
      type: "boolean",
      description:
        "Set to `false` to block both agent-driven Browser Use and native-app Computer Use. Setting it to `true` or omitting it does not enable either feature; the remaining feature, policy, and approval checks still apply.",
    },
    {
      key: "features.plugin_sharing",
      type: "boolean",
      description:
        "Set to `false` in cloud-managed `requirements.toml` to disable workspace sharing for locally built plugins.",
    },
    {
      key: "features",
      type: "table",
      description:
        "Pinned feature values. Use canonical names from `config.toml` for runtime features; documented app-only requirement keys are also supported here.",
    },
    {
      key: "features.<name>",
      type: "boolean",
      description:
        "Require a documented runtime or app feature to stay enabled or disabled.",
    },
    {
      key: "features.apps",
      type: "boolean",
      description:
        "Pin Apps integration availability on or off for managed users.",
    },
    {
      key: "features.in_app_updates",
      type: "boolean",
      description:
        "Set to `false` in `requirements.toml` to disable in-app updates. Updates remain enabled by default when this requirement is omitted.",
    },
    {
      key: "features.in_app_browser",
      type: "boolean",
      description:
        "Set to `false` in `requirements.toml` to disable the built-in browser pane that users open and control directly.",
    },
    {
      key: "features.browser_use",
      type: "boolean",
      description:
        "Set to `false` in `requirements.toml` to disable agent-driven Browser Use.",
    },
    {
      key: "features.browser_use_external",
      type: "boolean",
      description:
        "Set to `false` in `requirements.toml` to prevent Codex from operating supported browsers through the ChatGPT browser extension, including existing tabs and signed-in sessions.",
    },
    {
      key: "features.browser_use_full_cdp_access",
      type: "boolean",
      description:
        "Set to `false` in `requirements.toml` to disable full Chrome DevTools Protocol access in the local runtime, including Browser Developer mode, and prevent the ChatGPT desktop app from enabling the corresponding setting. If omitted, normal product availability applies.",
    },
    {
      key: "features.fast_mode",
      type: "boolean",
      description:
        "Pin the canonical `fast_mode` feature on or off for managed users.",
    },
    {
      key: "features.guardian_approval",
      type: "boolean",
      description:
        "Pin Guardian approval availability on or off for managed users.",
    },
    {
      key: "features.memories",
      type: "boolean",
      description: "Pin Memories availability on or off for managed users.",
    },
    {
      key: "features.multi_agent",
      type: "boolean",
      description: "Pin multi-agent availability on or off for managed users.",
    },
    {
      key: "features.plugins",
      type: "boolean",
      description: "Pin plugin availability on or off for managed users.",
    },
    {
      key: "features.remote_plugin",
      type: "boolean",
      description:
        "Pin remote plugin catalog availability on or off for managed users.",
    },
    {
      key: "features.computer_use",
      type: "boolean",
      description:
        "Set to `false` in `requirements.toml` to disable Computer Use, Record & Replay, and related install or enablement flows.",
    },
    {
      key: "features.workspace_dependencies",
      type: "boolean",
      description:
        "Pin bundled workspace-dependency runtime availability on or off for managed users.",
    },
    {
      key: "in_app_browser",
      type: "table",
      description:
        "Requirements for the built-in browser pane. These settings do not control agent-driven Browser Use.",
    },
    {
      key: "in_app_browser.allow_external_browser_settings_import",
      type: "boolean",
      description:
        "Set to `false` to prevent users from importing settings or browsing data from an external browser into the built-in browser. Setting it to `true` or omitting it leaves the import available when other product checks allow it. This is a managed-only setting with no `config.toml` override.",
    },
    {
      key: "browser_use",
      type: "table",
      description: "Managed requirements for agent-driven Browser Use.",
    },
    {
      key: "browser_use.allow_history_access",
      type: "boolean",
      description:
        "Set to `false` to prevent Browser Use from reading browser history. Setting it to `true` or omitting it leaves normal history settings and availability checks in place.",
    },
    {
      key: "browser_use.disable_auto_review",
      type: "boolean",
      description:
        "Set to `true` to skip automatic review for Browser Use and ask the user for approval instead. Setting it to `false` or omitting it leaves automatic review available when other settings allow it.",
    },
    {
      key: "browser_use.allow_global_persistent_approval",
      type: "boolean",
      description:
        "Set to `false` to prevent Browser Use from creating or honoring `Always allow` approvals that cover every site, such as allowing downloads from any site. Existing saved approvals are ignored, not deleted. Setting it to `true` or omitting it does not create an approval.",
    },
    {
      key: "browser_use.default_origin_policy",
      type: "table",
      description:
        "Fallback for each Browser Use setting when no matching entry under `browser_use.origins` defines it. A matching origin rule replaces the fallback for that source. Codex then applies the stricter result from managed requirements and user configuration.",
    },
    {
      key: "browser_use.default_origin_policy.access",
      type: "allow | deny",
      description:
        "Use `deny` to block Browser Use on origins that use the fallback. A denied origin also blocks uploads, downloads, full browser debugging access, and automatic review there. `allow` only lets normal approval and policy checks continue.",
    },
    {
      key: "browser_use.default_origin_policy.downloads",
      type: "allow | deny",
      description:
        "Use `deny` to block Browser Use downloads on origins that use the fallback. `allow` only lets normal approval and policy checks continue.",
    },
    {
      key: "browser_use.default_origin_policy.uploads",
      type: "allow | deny",
      description:
        "Use `deny` to block Browser Use uploads on origins that use the fallback. `allow` only lets normal approval and policy checks continue.",
    },
    {
      key: "browser_use.default_origin_policy.full_cdp_access",
      type: "allow | deny",
      description:
        "Use `deny` to block full Chrome DevTools Protocol (CDP) access on origins that use the fallback. `allow` only lets normal opt-in and approval checks continue.",
    },
    {
      key: "browser_use.default_origin_policy.auto_review",
      type: "allow | deny",
      description:
        "Use `deny` to skip automatic review on origins that use the fallback and ask the user for approval instead. `allow` leaves automatic review available when other settings allow it.",
    },
    {
      key: "browser_use.default_origin_policy.persistent_approval",
      type: "boolean",
      description:
        "Set to `false` to prevent Browser Use from saving or honoring an `Always allow` approval on origins that use the fallback. Approvals for the current turn or thread can still apply. `true` makes `Always allow` available when otherwise permitted but does not create an approval.",
    },
    {
      key: "browser_use.default_origin_policy.access_approval_lifetime",
      type: "turn | thread",
      description:
        "Set how long a non-persistent site-access approval lasts: `turn` limits it to the current turn, and `thread` keeps it for the rest of the current thread. `persistent_approval` separately controls whether `Always allow` is available. The product default is `thread`.",
    },
    {
      key: "browser_use.origins",
      type: "map<string, table>",
      description:
        'Origin-specific Browser Use policies. Keys use `<scheme>://<host-pattern>[:<port>]` with `http` or `https`. Use an exact host, `*.example.com` for subdomains only, or `**.example.com` for the base domain and its subdomains. Other `*` wildcards can span dots, so `region*.example.com` also matches `region.api.example.com`; a host of `*` matches every host for that scheme. Schemes and nondefault ports are significant; explicit default ports are normalized away. Paths, queries, embedded usernames or passwords, and wildcard schemes or ports are invalid. Quote the pattern in TOML, for example `[browser_use.origins."https://**.example.com"]`.',
    },
    {
      key: "browser_use.origins.<pattern>",
      type: "table",
      description:
        "Policy for origins matching this pattern. If several patterns match, Codex uses the most restrictive value for each capability: `deny` over `allow`, `false` over `true`, and `turn` over `thread`.",
    },
    {
      key: "browser_use.origins.<pattern>.access",
      type: "allow | deny",
      description:
        "Use `deny` to block Browser Use on matching origins. Denial also blocks uploads, downloads, full browser debugging access, and automatic review there. `allow` only lets normal approval and policy checks continue.",
    },
    {
      key: "browser_use.origins.<pattern>.downloads",
      type: "allow | deny",
      description:
        "Use `deny` to block Browser Use downloads on matching origins. `allow` only lets normal approval and policy checks continue.",
    },
    {
      key: "browser_use.origins.<pattern>.uploads",
      type: "allow | deny",
      description:
        "Use `deny` to block Browser Use uploads on matching origins. `allow` only lets normal approval and policy checks continue.",
    },
    {
      key: "browser_use.origins.<pattern>.full_cdp_access",
      type: "allow | deny",
      description:
        "Use `deny` to block full Chrome DevTools Protocol (CDP) access on matching origins. `allow` only lets normal opt-in and approval checks continue.",
    },
    {
      key: "browser_use.origins.<pattern>.auto_review",
      type: "allow | deny",
      description:
        "Use `deny` to skip automatic review on matching origins and ask the user for approval instead. `allow` leaves automatic review available when other settings allow it.",
    },
    {
      key: "browser_use.origins.<pattern>.persistent_approval",
      type: "boolean",
      description:
        "Set to `false` to prevent Browser Use from saving or honoring an `Always allow` approval on matching origins. Approvals for the current turn or thread can still apply. `true` makes `Always allow` available when otherwise permitted but does not create an approval.",
    },
    {
      key: "browser_use.origins.<pattern>.access_approval_lifetime",
      type: "turn | thread",
      description:
        "Set how long a non-persistent site-access approval for matching origins lasts: `turn` limits it to the current turn, and `thread` keeps it for the rest of the current thread. `persistent_approval` separately controls whether `Always allow` is available.",
    },
    {
      key: "computer_use",
      type: "table",
      description:
        "Managed requirements for agent-driven work in native desktop apps. Managed app rules and `config.toml` app rules are both enforced; an app must be allowed by each policy source.",
    },
    {
      key: "computer_use.allow_locked_computer_use",
      type: "boolean",
      description:
        "Set to `false` to prevent users from enabling Locked Use on a managed macOS device. This requirement removes the enablement controls; it does not turn off Locked Use if it is already enabled. If omitted, normal product availability applies.",
    },
    {
      key: "computer_use.allow_persistent_approval",
      type: "boolean",
      description:
        "Set to `false` to remove the option to save app approvals across sessions. Approvals for the current session remain available. Setting it to `true` or omitting it does not approve an app.",
    },
    {
      key: "computer_use.default_app_access",
      type: "allow | deny",
      description:
        "Fallback access for native apps that do not match a platform-specific rule. `deny` blocks access. `allow` only lets normal approval and policy checks continue. The product default is `allow`.",
    },
    {
      key: "computer_use.macos",
      type: "table",
      description: "Computer Use app rules for macOS.",
    },
    {
      key: "computer_use.macos.bundle_ids",
      type: "map<string, allow | deny>",
      description:
        "Map exact macOS bundle identifiers to `allow` or `deny`. A matching rule replaces `computer_use.default_app_access` within the same policy source. A deny from either managed requirements or user configuration still blocks access.",
    },
    {
      key: "computer_use.macos.bundle_ids.<bundle-id>",
      type: "allow | deny",
      description:
        "Use `deny` to block the exact bundle identifier. `allow` overrides only this policy source's default and still requires any other policy source and the normal approval flow to allow the app.",
    },
    {
      key: "computer_use.windows",
      type: "table",
      description:
        "Computer Use app rules for packaged and unpackaged Windows apps.",
    },
    {
      key: "computer_use.windows.aumids",
      type: "map<string, allow | deny>",
      description:
        "Map exact, registered Application User Model IDs (AUMIDs) for signed packaged apps to `allow` or `deny`. A matching rule replaces `computer_use.default_app_access` within the same policy source.",
    },
    {
      key: "computer_use.windows.aumids.<aumid>",
      type: "allow | deny",
      description:
        "Use `deny` to block the exact packaged-app identity. `allow` overrides only this policy source's default and still requires any other policy source and the normal approval flow to allow the app.",
    },
    {
      key: "computer_use.windows.exes",
      type: "array<table>",
      description:
        "Rules for signed, unpackaged Windows executables. Rules match the executable's verified publisher and signed version information, not its path or current file name. A matching deny takes precedence over matching allows. Unsigned executables use `computer_use.default_app_access`; executables whose signed identity cannot be verified unambiguously are blocked.",
    },
    {
      key: "computer_use.windows.exes[].publisher_name",
      type: "string",
      description:
        "Required exact publisher name from the executable's trusted signing certificate, formatted as a Windows X.500 distinguished name.",
    },
    {
      key: "computer_use.windows.exes[].product_name",
      type: "string",
      description:
        "Required exact `ProductName` from the executable's signed version information.",
    },
    {
      key: "computer_use.windows.exes[].binary_name",
      type: "string",
      description:
        "Optional `OriginalFilename` from the executable's signed version information. Matching is case-insensitive. If a matching publisher and product rule requires this value but the executable does not provide it, Computer Use blocks the executable.",
    },
    {
      key: "computer_use.windows.exes[].access",
      type: "allow | deny",
      description:
        "Required access decision for matching executables. `deny` blocks access. `allow` overrides only this policy source's default and still requires any other policy source and the normal approval flow to allow the app.",
    },
    {
      key: "experimental_network",
      type: "table",
      description:
        "Administrator-managed network requirements for sandboxed local commands, enforced from `requirements.toml`. When enabled, these requirements can start the command network proxy without `features.network_proxy`. Browser tools separately check managed network denies and exclusive allowlists. These requirements do not route browser traffic through the proxy or control web search, apps, MCP servers, native-app traffic, or Codex cloud networking.",
    },
    {
      key: "experimental_network.enabled",
      type: "boolean",
      description:
        "Enable sandboxed networking requirements. This does not grant network access when the active sandbox keeps command networking off.",
    },
    {
      key: "experimental_network.http_port",
      type: "integer",
      description:
        "Loopback HTTP listener port to use for `[experimental_network]` requirements.",
    },
    {
      key: "experimental_network.socks_port",
      type: "integer",
      description:
        "Loopback SOCKS5 listener port to use for `[experimental_network]` requirements.",
    },
    {
      key: "experimental_network.allow_upstream_proxy",
      type: "boolean",
      description:
        "Allow sandboxed networking to chain through an upstream proxy from the environment.",
    },
    {
      key: "experimental_network.dangerously_allow_non_loopback_proxy",
      type: "boolean",
      description:
        "Permit non-loopback listener addresses for `[experimental_network]` requirements. Enabling it can expose listeners beyond localhost.",
    },
    {
      key: "experimental_network.dangerously_allow_all_unix_sockets",
      type: "boolean",
      description:
        "Permit arbitrary Unix socket destinations instead of allowlist-only access. Use only in tightly controlled environments.",
    },
    {
      key: "experimental_network.domains",
      type: "map<string, allow | deny>",
      description:
        "Map-shaped administrator domain policy for sandboxed networking. Supports exact hosts, `*.example.com` for subdomains only, `**.example.com` for apex plus subdomains, and global `*` allow rules; prefer scoped rules because `*` broadly opens public outbound access. `deny` wins on conflicts. Do not combine this with `experimental_network.allowed_domains` or `experimental_network.denied_domains`.",
    },
    {
      key: "experimental_network.allowed_domains",
      type: "array<string>",
      description:
        "Administrator allow rules for sandboxed-command networking while the managed network proxy is enabled. These rules do not apply to web search, apps, or MCP servers. Do not combine this with `experimental_network.domains`.",
    },
    {
      key: "experimental_network.denied_domains",
      type: "array<string>",
      description:
        "List-shaped administrator deny rules for sandboxed networking. Do not combine this with `experimental_network.domains`.",
    },
    {
      key: "experimental_network.managed_allowed_domains_only",
      type: "boolean",
      description:
        "When `true`, only administrator-managed allow rules remain effective while sandboxed networking requirements are active; user allowlist additions are ignored. Without managed allow rules, user-added domain allow rules do not remain effective.",
    },
    {
      key: "experimental_network.unix_sockets",
      type: "map<string, allow | deny>",
      description:
        "Administrator-managed Unix socket policy for sandboxed networking.",
    },
    {
      key: "experimental_network.allow_local_binding",
      type: "boolean",
      description:
        "Permit broader local/private-network access for sandboxed networking. Exact local IP literal or `localhost` allow rules can still permit specific local targets when this stays `false`.",
    },
    {
      key: "hooks",
      type: "table",
      description:
        "Admin-enforced managed lifecycle hooks. Requires a managed hook directory and uses the same event schema as inline `[hooks]` in `config.toml`.",
    },
    {
      key: "hooks.managed_dir",
      type: "string (absolute path)",
      description:
        "Directory containing managed hook scripts on macOS and Linux. Codex validates that it is absolute and exists before loading managed hooks.",
    },
    {
      key: "hooks.windows_managed_dir",
      type: "string (absolute path)",
      description:
        "Directory containing managed hook scripts on Windows. Codex validates that it is absolute and exists before loading managed hooks.",
    },
    {
      key: "hooks.<Event>",
      type: "array<table>",
      description:
        "Matcher groups for a hook event such as `PreToolUse`, `PermissionRequest`, `PostToolUse`, `PreCompact`, `PostCompact`, `SessionStart`, `SessionEnd`, `SubagentStart`, `SubagentStop`, `UserPromptSubmit`, or `Stop`.",
    },
    {
      key: "hooks.<Event>[].hooks",
      type: "array<table>",
      description:
        "Hook handlers for a matcher group. Command and MCP tool hooks are supported while prompt and agent hook handlers are parsed but skipped.",
    },
    {
      key: "hooks.<Event>[].hooks[].async",
      type: "boolean",
      description:
        "Run a command hook in the background without delaying the triggering operation. Defaults to `false`; `SessionEnd` always runs synchronously. See [Run hooks in the background](https://learn.chatgpt.com/docs/hooks#run-hooks-in-the-background).",
    },
    {
      key: "hooks.<Event>[].hooks[].additionalContextLimit",
      type: "integer",
      description:
        "Approximate per-handler token threshold for saving oversized `additionalContext` to disk and showing the model a shorter preview. Defaults to `2500`; `0` passes the full context directly to the model. See [Large hook output](https://learn.chatgpt.com/docs/hooks#large-hook-output).",
    },
    {
      key: "hooks.<Event>[].hooks[].commandWindows",
      type: "string",
      description:
        "Windows-only command override for command hooks. The TOML alias `command_windows` is also accepted.",
    },
    {
      key: "permissions.filesystem.deny_read",
      type: "array<string>",
      description:
        "Admin-enforced filesystem read denials. Entries can be paths or glob patterns, and users cannot weaken them with local config.",
    },
    {
      key: "mcp_servers",
      type: "table",
      description:
        "Allowlist of MCP servers that may be enabled. Both the server name (`<id>`) and its identity must match for the MCP server to be enabled. Any configured MCP server not in the allowlist (or with a mismatched identity) is disabled.",
    },
    {
      key: "mcp_servers.<id>.identity",
      type: "table",
      description:
        "Identity rule for a single MCP server. Set either `command` (stdio) or `url` (streamable HTTP).",
    },
    {
      key: "mcp_servers.<id>.identity.command",
      type: "string | table",
      description:
        "Allow an MCP stdio server by exact command string, or use a matcher table to require an exact executable and ordered argument matchers. The string form doesn't inspect arguments, `cwd`, `env`, or `env_vars`.",
    },
    {
      key: "mcp_servers.<id>.identity.command.executable",
      type: "string",
      description:
        "Executable that the stdio server's configured `command` must match exactly.",
    },
    {
      key: "mcp_servers.<id>.identity.command.args",
      type: "array<table>",
      description:
        "Ordered argument matchers for a stdio server. The configured argument list must have the same length, and every position must match. Command matchers don't inspect `cwd`, `env`, or `env_vars`.",
    },
    {
      key: "mcp_servers.<id>.identity.command.args[].match",
      type: "exact | prefix | regex",
      description: "Match operation for this argument position.",
    },
    {
      key: "mcp_servers.<id>.identity.command.args[].value",
      type: "string",
      description: "Value used by an `exact` or `prefix` argument matcher.",
    },
    {
      key: "mcp_servers.<id>.identity.command.args[].expression",
      type: "string",
      description:
        "Regular expression used by a `regex` argument matcher. The expression must be valid and match the complete argument value.",
    },
    {
      key: "mcp_servers.<id>.identity.url",
      type: "string | table",
      description:
        "Allow an MCP streamable HTTP server by exact URL string, or use an `exact`, `prefix`, or `regex` value matcher table.",
    },
    {
      key: "mcp_servers.<id>.identity.url.match",
      type: "exact | prefix | regex",
      description: "Match operation for the configured MCP server URL.",
    },
    {
      key: "mcp_servers.<id>.identity.url.value",
      type: "string",
      description: "Value used by an `exact` or `prefix` URL matcher.",
    },
    {
      key: "mcp_servers.<id>.identity.url.expression",
      type: "string",
      description:
        "Regular expression used by a `regex` URL matcher. The expression must be valid and match the complete URL value.",
    },
    {
      key: "plugins",
      type: "table",
      description:
        "Plugin-specific MCP server allowlists keyed by plugin identifier. When this table is present, plugin-bundled servers without a matching plugin and server entry are disabled.",
    },
    {
      key: "plugins.<plugin>.mcp_servers",
      type: "table",
      description:
        "Allowlist for MCP servers bundled with one plugin. Plugin server requirements use the same exact identity and matcher forms as top-level `mcp_servers` requirements.",
    },
    {
      key: "plugins.<plugin>.mcp_servers.<server>.identity",
      type: "table",
      description:
        "Identity rule for one plugin-bundled MCP server. Set either `command` (stdio) or `url` (streamable HTTP).",
    },
    {
      key: "plugins.<plugin>.mcp_servers.<server>.identity.command",
      type: "string | table",
      description:
        "Allow a plugin's stdio MCP server by exact command string, or use a matcher table to require an exact executable and ordered argument matchers.",
    },
    {
      key: "plugins.<plugin>.mcp_servers.<server>.identity.command.executable",
      type: "string",
      description:
        "Executable that the plugin-bundled stdio server's configured command must match exactly.",
    },
    {
      key: "plugins.<plugin>.mcp_servers.<server>.identity.command.args",
      type: "array<table>",
      description:
        "Ordered argument matchers for a plugin-bundled stdio server. The configured argument list must have the same length, and every position must match.",
    },
    {
      key: "plugins.<plugin>.mcp_servers.<server>.identity.command.args[].match",
      type: "exact | prefix | regex",
      description: "Match operation for this argument position.",
    },
    {
      key: "plugins.<plugin>.mcp_servers.<server>.identity.command.args[].value",
      type: "string",
      description: "Value used by an `exact` or `prefix` argument matcher.",
    },
    {
      key: "plugins.<plugin>.mcp_servers.<server>.identity.command.args[].expression",
      type: "string",
      description:
        "Regular expression used by a `regex` argument matcher. The expression must match the complete argument value.",
    },
    {
      key: "plugins.<plugin>.mcp_servers.<server>.identity.url",
      type: "string | table",
      description:
        "Allow a plugin's streamable HTTP MCP server by exact URL string, or use an `exact`, `prefix`, or `regex` value matcher table.",
    },
    {
      key: "plugins.<plugin>.mcp_servers.<server>.identity.url.match",
      type: "exact | prefix | regex",
      description: "Match operation for the plugin-bundled MCP server URL.",
    },
    {
      key: "plugins.<plugin>.mcp_servers.<server>.identity.url.value",
      type: "string",
      description: "Value used by an `exact` or `prefix` URL matcher.",
    },
    {
      key: "plugins.<plugin>.mcp_servers.<server>.identity.url.expression",
      type: "string",
      description:
        "Regular expression used by a `regex` URL matcher. The expression must match the complete URL value.",
    },
    {
      key: "marketplaces",
      type: "table",
      description:
        "Admin requirements for plugin marketplace sources. Rules take effect when `restrict_to_allowed_sources` is `true`.",
    },
    {
      key: "marketplaces.restrict_to_allowed_sources",
      type: "boolean",
      description:
        "When `true`, require configured marketplace sources to match `allowed_sources` for marketplace add, plugin install, refresh, and runtime loading. OpenAI-curated Git catalogs, including the API-key catalog, must also match the allowlist. Bundled and remotely installed workspace plugins are separate from this curated Git source policy.",
    },
    {
      key: "marketplaces.allowed_sources",
      type: "table",
      description:
        "Allowed marketplace sources keyed by administrator-chosen rule name. Distinct names accumulate across requirements layers; fields under the same name use normal layer precedence.",
    },
    {
      key: "marketplaces.allowed_sources.<name>",
      type: "table",
      description:
        "One allowed source rule. The final `source` value after requirements merge determines which sibling fields Codex interprets.",
    },
    {
      key: "marketplaces.allowed_sources.<name>.source",
      type: "git | host_pattern | local",
      description:
        "Marketplace source matcher type. Use `git` for one repository, `host_pattern` for Git hosts matched by regular expression, or `local` for one directory.",
    },
    {
      key: "marketplaces.allowed_sources.<name>.url",
      type: "string",
      description:
        'Git repository URL required when `source = "git"`. Codex normalizes the configured and allowed URLs before requiring an exact repository match.',
    },
    {
      key: "marketplaces.allowed_sources.<name>.ref",
      type: "string",
      description:
        "Optional exact Git ref for a `git` rule. When omitted, the rule allows any ref for the matching repository.",
    },
    {
      key: "marketplaces.allowed_sources.<name>.host_pattern",
      type: "string",
      description:
        'Regular expression required when `source = "host_pattern"`. Codex matches it against the lowercase hostname parsed from an HTTPS, SSH, or SCP-style Git source. Use `^` and `$` to require a whole-host match.',
    },
    {
      key: "marketplaces.allowed_sources.<name>.path",
      type: "string (absolute path)",
      description:
        'Local marketplace directory required when `source = "local"`. Codex requires an absolute path and compares paths after normalization.',
    },
    {
      key: "apps",
      type: "table",
      description:
        "Managed app requirements keyed by app identifier. Requirements can disable an app or constrain approval behavior for individual tools.",
    },
    {
      key: "apps.<id>.enabled",
      type: "boolean",
      description:
        "Set to `false` to disable an app. A disabled requirement remains restrictive when multiple requirements sources are merged.",
    },
    {
      key: "apps.<id>.tools.<tool>.approval_mode",
      type: "auto | prompt | writes | approve",
      description: "Set the managed approval mode for one app tool.",
    },
    {
      key: "rules",
      type: "table",
      description:
        "Admin-enforced command rules merged with `.rules` files. Requirements rules must be restrictive.",
    },
    {
      key: "rules.prefix_rules",
      type: "array<table>",
      description:
        "List of enforced prefix rules. Each rule must include `pattern` and `decision`.",
    },
    {
      key: "rules.prefix_rules[].pattern",
      type: "array<table>",
      description:
        "Command prefix expressed as pattern tokens. Each token sets either `token` or `any_of`.",
    },
    {
      key: "rules.prefix_rules[].pattern[].token",
      type: "string",
      description: "A single literal token at this position.",
    },
    {
      key: "rules.prefix_rules[].pattern[].any_of",
      type: "array<string>",
      description: "A list of allowed alternative tokens at this position.",
    },
    {
      key: "rules.prefix_rules[].decision",
      type: "prompt | forbidden",
      description:
        "Required. Requirements rules can only prompt or forbid (not allow).",
    },
    {
      key: "rules.prefix_rules[].justification",
      type: "string",
      description:
        "Optional non-empty rationale surfaced in approval prompts or rejection messages.",
    },
  ]}
  client:load
/>

## Lifecycle hooks

Admins can set top-level `allow_managed_hooks_only = true` in
`requirements.toml` to ignore user, project, and session hook configs while
still allowing managed hooks from requirements and managed config layers. This
setting is only supported in `requirements.toml`; putting it in `config.toml`
does not enable managed-hooks-only mode.
