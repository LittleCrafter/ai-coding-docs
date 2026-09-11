> ## Documentation Index
> Fetch the complete documentation index at: https://code.claude.com/docs/llms.txt
> Use this file to discover all available pages before exploring further.

# Explore the .claude directory

> Where Claude Code reads CLAUDE.md, settings.json, hooks, skills, commands, subagents, workflows, rules, and auto memory. Explore the .claude directory in your project and ~/.claude in your home directory.

## your-project/

### CLAUDE.md

*Project instructions Claude reads every session* (committed)

*When it loads: Loaded into context at the start of every session*

Project-specific instructions that shape how Claude works in this repository. Put your conventions, common commands, and architectural context here so Claude operates with the same assumptions your team does.

**Tips**

* Target under 200 lines. Longer files still load in full but may reduce adherence
* CLAUDE.md loads into every session. If something only matters for specific tasks, move it to a [skill](./skills.md) or a path-scoped [rule](./memory.md#organize-rules-with-claude/rules/) so it loads only when needed
* List the commands you run most, like build, test, and format, so Claude knows them without you spelling them out each time
* Run `/memory` to open and edit CLAUDE.md from within a session
* Also works at `.claude/CLAUDE.md` if you prefer to keep the project root clean

This example is for a TypeScript and React project. It lists the build and test commands, the framework conventions Claude should follow, and project-specific rules like export style and file layout.

```markdown
# Project conventions

## Commands
- Build: `npm run build`
- Test: `npm test`
- Lint: `npm run lint`

## Stack
- TypeScript with strict mode
- React 19, functional components only

## Rules
- Named exports, never default exports
- Tests live next to source: `foo.ts` -> `foo.test.ts`
- All API routes return `{ data, error }` shape
```

[Full docs](./memory.md)

### .mcp.json

*Project-scoped MCP servers, shared with your team* (committed)

*When it loads: Servers connect when the session begins. Tool schemas are deferred by default and load on demand via [tool search](./mcp.md#scale-with-mcp-tool-search)*

Configures Model Context Protocol (MCP) servers that give Claude access to external tools: databases, APIs, browsers, and more. This file holds the project-scoped servers your whole team uses. Personal servers you want to keep to yourself go in `~/.claude.json` instead.

**Tips**

* Use environment variable references for secrets: `${NOTION_TOKEN}`
* Lives at the project root, not inside `.claude/`
* For servers only you need, run `claude mcp add --scope user`. This writes to `~/.claude.json` instead of `.mcp.json`

This example configures the Notion MCP server so Claude can read and update pages in your workspace. The `${NOTION_TOKEN}` reference is read from your shell environment when Claude Code starts the server, so the token never lands in the file.

```json
{
  "mcpServers": {
    "notion": {
      "command": "npx",
      "args": ["-y", "@notionhq/notion-mcp-server"],
      "env": {
        "NOTION_TOKEN": "${NOTION_TOKEN}"
      }
    }
  }
}
```

[Full docs](./mcp.md)

### .worktreeinclude

*Gitignored files to copy into new worktrees* (committed)

*When it loads: Read when Claude creates a git worktree via `--worktree`, the `EnterWorktree` tool, or subagent `isolation: worktree`*

Lists gitignored files to copy from your main repository into each new worktree. Worktrees are fresh checkouts, so untracked files like `.env` are missing by default. Patterns here use `.gitignore` syntax. Only files that match a pattern and are also gitignored get copied, so tracked files are never duplicated.

**Tips**

* Lives at the project root, not inside `.claude/`
* Git-only: if you configure a [WorktreeCreate hook](./hooks.md#worktreecreate) for a different VCS, this file is not read. Copy files inside your hook script instead
* Also applies to parallel sessions in the [desktop app](./desktop.md#work-in-parallel-with-sessions)

This example copies your local environment files and a secrets config into every worktree Claude creates. Comments start with # and blank lines are ignored, same as .gitignore.

```markdown
# Local environment
.env
.env.local

# API credentials
config/secrets.json
```

[Full docs](./worktrees.md#copy-gitignored-files-into-worktrees)

### .claude/

*Project-level configuration, rules, and extensions*

Everything Claude Code reads that is specific to this project. If you use git, commit most files here so your team shares them; a few, like settings.local.json, are gitignored when Claude Code saves settings to them. Each file badge shows which.

#### settings.json

*Permissions, hooks, and configuration* (committed)

*When it loads: Overrides global `~/.claude/settings.json`. Local settings, CLI flags, and managed settings override this*

Settings that Claude Code applies directly. Permissions control which commands and tools Claude can use; hooks run your scripts at specific points in a session. Unlike CLAUDE.md, which Claude reads as guidance, these are enforced whether Claude follows them or not.

**Tips**

* Bash permission patterns support wildcards: `Bash(npm test *)` matches any command starting with `npm test`
* Array settings like `permissions.allow` combine across all scopes; scalar settings like `model` use the most specific value

**Common keys**

* [permissions](./permissions.md): allow, deny, or prompt before Claude uses specific tools or commands
* [hooks](./hooks.md): run your own scripts on events like before a tool call or after a file edit
* [statusLine](./statusline.md): customize the line shown at the bottom while Claude works
* [model](./settings-reference.md#available-settings): pick a default model for this project
* [env](./settings-reference.md#environment-variables): environment variables set in every session
* [outputStyle](./output-styles.md): select a custom output style from output-styles/

This example allows `npm test` and `npm run` commands without prompting, blocks `rm -rf`, and runs Prettier on files after Claude edits or writes them.

```json
{
  "permissions": {
    "allow": [
      "Bash(npm test *)",
      "Bash(npm run *)"
    ],
    "deny": [
      "Bash(rm -rf *)"
    ]
  },
  "hooks": {
    "PostToolUse": [{
      "matcher": "Edit|Write",
      "hooks": [{
        "type": "command",
        "command": "jq -r '.tool_input.file_path' | xargs npx prettier --write"
      }]
    }]
  }
}
```

[Full docs](./settings.md)

#### settings.local.json

*Your personal settings overrides for this project* (gitignored)

*When it loads: Highest of the user-editable settings files; CLI flags and managed settings still take precedence*

Personal settings that take precedence over the project defaults. Same JSON format as settings.json, gitignored when Claude Code saves a setting to it. Use this when you need different permissions or defaults than the team config.

**Tips**

* Same schema as settings.json. Array settings like `permissions.allow` combine across scopes; scalar settings like `model` use the local value
* When Claude Code saves a setting to this file in a repository that doesn't already ignore it, it adds `**/.claude/settings.local.json` to your global git excludes file: `core.excludesFile` from your global git config when it's set to an absolute or `~`-prefixed path, otherwise `$XDG_CONFIG_HOME/git/ignore`, or `~/.config/git/ignore`. To share the ignore rule with your team, also add it to the project `.gitignore`

This example adds Docker permissions on top of whatever the team settings.json allows.

```json
{
  "permissions": {
    "allow": [
      "Bash(docker *)"
    ]
  }
}
```

[Full docs](./settings.md)

#### rules/

*Topic-scoped instructions, optionally gated by file paths*

*When it loads: Rules without `paths:` load at session start. Rules with `paths:` load when a matching file enters context*

Project instructions split into topic files that can load conditionally based on file paths. A rule without `paths:` frontmatter loads at session start like CLAUDE.md; a rule with `paths:` loads only when Claude reads a matching file.

Like CLAUDE.md, rules are guidance Claude reads, not configuration Claude Code enforces. For guaranteed behavior use [hooks](./hooks.md) or [permissions](./permissions.md).

**Tips**

* Use `paths:` frontmatter with globs to scope rules to directories or file types
* Subdirectories work: `.claude/rules/frontend/react.md` is discovered automatically
* When CLAUDE.md approaches 200 lines, start splitting into rules

[Full docs](./memory.md#organize-rules-with-claude/rules/)

##### testing.md

*Test conventions scoped to test files* (committed)

*When it loads: Loaded when Claude reads a file matching the `paths:` globs below*

An example rule that only loads when Claude is working on test files. The `paths:` globs in the frontmatter define which files trigger it; here, anything ending in .test.ts or .test.tsx. For other files, this rule is not loaded into context.

```markdown
---
paths:
  - "**/*.test.ts"
  - "**/*.test.tsx"
---

# Testing Rules

- Use descriptive test names: "should [expected] when [condition]"
- Mock external dependencies, not internal modules
- Clean up side effects in afterEach
```

##### api-design.md

*API conventions scoped to backend code* (committed)

*When it loads: Loaded when Claude reads a file matching the `paths:` glob below*

A second example showing a rule scoped to backend code. The `paths:` glob matches files under src/api/, so these conventions load only when Claude is editing API routes.

```markdown
---
paths:
  - "src/api/**/*.ts"
---

# API Design Rules

- All endpoints must validate input with Zod schemas
- Return shape: { data: T } | { error: string }
- Rate limit all public endpoints
```

#### skills/

*Reusable prompts you or Claude invoke by name*

*When it loads: Invoked with `/skill-name` or when Claude matches the task to a skill*

Each skill is a folder with a SKILL.md file plus any supporting files it needs. By default, both you and Claude can invoke a skill. Use frontmatter to control that: `disable-model-invocation: true` for user-only workflows like `/deploy`, or `user-invocable: false` to hide from the `/` menu while Claude can still invoke it.

**Tips**

* Skills accept arguments: `/deploy staging` passes "staging" as `$ARGUMENTS`. Use `$0`, `$1`, and so on for positional access
* The `description` frontmatter determines when Claude auto-invokes the skill
* Bundle reference docs alongside SKILL.md. Claude knows the skill directory path and can read supporting files when you mention them

[Full docs](./skills.md)

##### security-review/

*A skill bundling SKILL.md with supporting files*

###### SKILL.md

*Entrypoint: trigger, invocability, instructions* (committed)

*When it loads: User types `/security-review &lt;target&gt;`; Claude cannot auto-invoke this skill*

This skill uses `disable-model-invocation: true` so only you can trigger it; Claude never invokes it on its own.

The `!`...`` line runs a shell command and injects its output into the prompt. `$ARGUMENTS` substitutes whatever you typed after the skill name. Claude sees the skill directory path, so mentioning a bundled file like checklist.md lets Claude read it.

```markdown
---
description: Reviews code changes for security vulnerabilities, authentication gaps, and injection risks
disable-model-invocation: true
argument-hint: <branch-or-path>
---

## Diff to review

!`git diff $ARGUMENTS`

Audit the changes above for:

1. Injection vulnerabilities (SQL, XSS, command)
2. Authentication and authorization gaps
3. Hardcoded secrets or credentials

Use checklist.md in this skill directory for the full review checklist.

Report findings with severity ratings and remediation steps.
```

###### checklist.md

*Supporting file bundled with the skill* (committed)

*When it loads: Claude reads it on demand while running the skill*

Skills can bundle any supporting files: reference docs, templates, scripts. The skill directory path is prepended to SKILL.md, so Claude can read bundled files by name. For scripts in bash injection commands, use the `${CLAUDE_SKILL_DIR}` placeholder.

```markdown
# Security Review Checklist

## Input Validation
- [ ] All user input sanitized before DB queries
- [ ] File upload MIME types validated
- [ ] Path traversal prevented on file operations

## Authentication
- [ ] JWT tokens expire after 24 hours
- [ ] API keys stored in environment variables
- [ ] Passwords hashed with bcrypt or argon2
```

#### commands/

*Single-file prompts invoked with `/name`*

*When it loads: User types `/command-name`*

A file at `commands/deploy.md` creates `/deploy` the same way a skill at `skills/deploy/SKILL.md` does, and both can be auto-invoked by Claude. Skills use a directory with SKILL.md, letting you bundle reference docs, templates, or scripts alongside the prompt.

**Tips**

* Use `$ARGUMENTS` in the file to accept parameters: `/fix-issue 123`
* If a skill and command share a name, the skill takes precedence
* New commands should usually be skills instead; commands remain supported

[Full docs](./skills.md)

##### fix-issue.md

*Invoked as `/fix-issue &lt;number&gt;`* (committed)

An example command for fixing a GitHub issue. Type `/fix-issue 123` and the `!`...`` line runs `gh issue view 123` in your shell, injecting the output into the prompt before Claude sees it.

`$ARGUMENTS` substitutes whatever you typed after the command name. For positional access, use `$0` `$1` and so on.

```markdown
---
argument-hint: <issue-number>
---

!`gh issue view $ARGUMENTS`

Investigate and fix the issue above.

1. Trace the bug to its root cause
2. Implement the fix
3. Write or update tests
4. Summarize what you changed and why
```

#### output-styles/

*Project-scoped output styles, if your team shares any*

*When it loads: Files read at startup; the style you select with outputStyle applies to every response*

Output styles are usually personal, so most live in `~/.claude/output-styles/`. Put one here if your team shares a style, like a review mode everyone uses. See [the Global tab](#ce-global-output-styles) for the full explanation and example.

[Full docs](./output-styles.md)

#### agents/

*Specialized subagents with their own context window*

*When it loads: Runs in its own context window when you or Claude invoke it*

Each markdown file defines a subagent with its own system prompt, tool access, and optionally its own model. Subagents run in a fresh context window, keeping the main conversation clean. Useful for parallel work or isolated tasks.

**Tips**

* Each agent gets a fresh context window, separate from your main session
* Restrict tool access per agent with the `tools:` frontmatter field
* Type @ and pick an agent from the autocomplete to delegate directly

[Full docs](./sub-agents.md)

##### code-reviewer.md

*Subagent for isolated code review* (committed)

*When it loads: Claude spawns it for review tasks, or you @-mention it from the autocomplete*

An example subagent restricted to read-only tools. The `description` frontmatter tells Claude when to delegate to it automatically; `tools:` limits it to Read, Grep, and Glob so it can inspect code but never edit. The body becomes the subagent's system prompt.

```markdown
---
name: code-reviewer
description: Reviews code for correctness, security, and maintainability
tools: Read, Grep, Glob
---

You are a senior code reviewer. Review for:

1. Correctness: logic errors, edge cases, null handling
2. Security: injection, auth bypass, data exposure
3. Maintainability: naming, complexity, duplication

Every finding must include a concrete fix.
```

#### workflows/

*Dynamic workflow scripts that orchestrate many subagents*

*When it loads: Loaded at startup; each file becomes a /<name> command*

Each `.js` file is a [dynamic workflow](./workflows.md): a script the runtime executes to spawn and coordinate many subagents. Workflows are written by Claude and saved here from `/workflows` rather than authored from scratch.

**Tips**

* Save a run from `/workflows` with `s` to create one of these
* A project workflow takes precedence over a personal one in `~/.claude/workflows/` with the same name

[Full docs](./workflows.md)

#### agent-memory/

*Subagent persistent memory, separate from your main session auto memory* (Claude writes)

*When it loads: First 200 lines (capped at 25KB) of MEMORY.md loaded into the subagent system prompt when it runs*

Subagents with `memory: project` in their frontmatter get a dedicated memory directory here. This is distinct from your [main session auto memory](./memory.md#auto-memory) at `~/.claude/projects/`: each subagent reads and writes its own MEMORY.md, not yours.

**Tips**

* Only created for subagents that set the `memory:` frontmatter field
* This directory holds project-scoped subagent memory, meant to be shared with your team. To keep memory out of version control use `memory: local`, which writes to `.claude/agent-memory-local/` instead. For cross-project memory use `memory: user`, which writes to `~/.claude/agent-memory/`
* The main session auto memory is a different feature; see `~/.claude/projects/` in the Global tab

[Full docs](./sub-agents.md#enable-persistent-memory)

##### <agent-name>/

###### MEMORY.md

*The subagent writes and maintains this file automatically* (Claude writes)

*When it loads: Loaded into the subagent system prompt when the subagent starts*

Works the same as your [main auto memory](./memory.md#auto-memory): the subagent creates and updates this file itself. You do not write it. The subagent reads it at the start of each task and writes back what it learns.

```markdown
# code-reviewer memory

## Patterns seen
- Project uses custom Result<T, E> type, not exceptions
- Auth middleware expects Bearer token in Authorization header
- Tests use factory functions in test/factories/

## Recurring issues
- Missing null checks on API responses (src/api/*)
- Unhandled promise rejections in background jobs
```

## ~/

### .claude.json

*App state and UI preferences* (local only)

*When it loads: Read at session start for your preferences and MCP servers. Claude Code writes back to it when you change settings in `/config` or approve trust prompts*

Holds state that does not belong in settings.json: theme, OAuth session, per-project trust decisions, your personal MCP servers, and UI toggles. Mostly managed through `/config` rather than editing directly.

**Tips**

* IDE toggles like `autoConnectIde` and `externalEditorContext` live here, not in settings.json
* The `projects` key tracks per-project state like trust-dialog acceptance and last-session metrics. Permission rules you approve in-session go to `.claude/settings.local.json` instead
* MCP servers here are yours only: user scope applies across all projects, local scope is per-project but not committed. Team-shared servers go in `.mcp.json` at the project root instead

```json
{
  "autoConnectIde": true,
  "externalEditorContext": true,
  "mcpServers": {
    "my-tools": {
      "command": "npx",
      "args": ["-y", "@example/mcp-server"]
    }
  }
}
```

[Full docs](./settings-reference.md#global-config-settings)

### .claude/

*Your personal configuration across all projects*

The global counterpart to your project .claude/ directory. Files here apply to every project you work in and are never committed to any repository.

#### CLAUDE.md

*Personal preferences across every project* (local only)

*When it loads: Loaded at the start of every session, in every project*

Your global instruction file. Loaded alongside the project CLAUDE.md at session start, so both are in context together. When instructions conflict, project-level instructions take priority. Keep this to preferences that apply everywhere: response style, commit format, personal conventions.

**Tips**

* Keep it short since it loads into context for every project, alongside that project's own CLAUDE.md
* Good for response style, commit format, and personal conventions

```markdown
# Global preferences

- Keep explanations concise
- Use conventional commit format
- Show the terminal command to verify changes
- Prefer composition over inheritance
```

[Full docs](./memory.md)

#### settings.json

*Default settings for all projects* (local only)

*When it loads: Your defaults. Project and local settings.json override any keys you also set there*

Same keys as project `settings.json`: permissions, hooks, model, environment variables, and the rest. Put settings here that you want in every project, like permissions you always allow, a preferred model, or a notification hook that runs regardless of which project you're in.

Settings follow a precedence order: project `settings.json` overrides any matching keys you set here. This is different from CLAUDE.md, where global and project files are both loaded into context rather than merged key by key.

```json
{
  "permissions": {
    "allow": [
      "Bash(git log *)",
      "Bash(git diff *)"
    ]
  }
}
```

[Full docs](./settings.md)

#### keybindings.json

*Custom keyboard shortcuts* (local only)

*When it loads: Read at session start and hot-reloaded when you edit the file*

Rebind keyboard shortcuts in the interactive CLI. Run `/keybindings` to create or open this file with a schema reference. Ctrl+C, Ctrl+D, Ctrl+M, and Caps Lock are reserved and cannot be rebound.

This example binds `Ctrl+E` to open your external editor and unbinds `Ctrl+U` by setting it to `null`. The `context` field scopes bindings to a specific part of the CLI, here the main chat input.

```json
{
  "$schema": "https://www.schemastore.org/claude-code-keybindings.json",
  "$docs": "https://code.claude.com/docs/en/keybindings",
  "bindings": [
    {
      "context": "Chat",
      "bindings": {
        "ctrl+e": "chat:externalEditor",
        "ctrl+u": null
      }
    }
  ]
}
```

[Full docs](./keybindings.md)

#### themes/

*Custom color themes*

*When it loads: Read at session start and hot-reloaded when files change. Listed in `/theme`*

Each `.json` file defines a custom color theme: a built-in `base` preset plus an `overrides` map of color tokens. Create one interactively with `/theme` or write the JSON by hand. Selecting a custom theme stores `custom:&lt;slug&gt;` as your theme preference.

```text
{
  "name": "Dracula",
  "base": "dark",
  "overrides": {
    "claude": "#bd93f9",
    "error": "#ff5555",
    "success": "#50fa7b"
  }
}
```

[Full docs](./terminal-config.md#create-a-custom-theme)

#### projects/

*Auto memory: Claude's notes to itself, per project* (Claude writes)

*When it loads: MEMORY.md loaded at session start; topic files read on demand*

Auto memory lets Claude accumulate knowledge across sessions without you writing anything. Claude saves notes as it works: build commands, debugging insights, architecture notes. Each project gets its own memory directory keyed by the repository path.

**Tips**

* On by default. Toggle with `/memory` or `autoMemoryEnabled` in settings
* MEMORY.md is the index loaded each session. The first 200 lines, or 25KB, whichever comes first, are read
* Topic files like debugging.md are read on demand, not at startup
* These are plain markdown. Edit or delete them anytime

[Full docs](./memory.md#auto-memory)

##### <project>/memory/

*Claude's accumulated knowledge for one project* (Claude writes)

###### MEMORY.md

*Claude writes and maintains this file automatically* (Claude writes)

*When it loads: First 200 lines (capped at 25KB) loaded at session start*

Claude creates and updates this file as it works; you do not write it yourself. It acts as an index that Claude reads at the start of every session, pointing to topic files for detail. You can edit or delete it, but Claude will keep updating it.

```markdown
# Memory Index

## Project
- [build-and-test.md](build-and-test.md): npm run build (~45s), Vitest, dev server on 3001
- [architecture.md](architecture.md): API client singleton, refresh-token auth

## Reference
- [debugging.md](debugging.md): auth token rotation and DB connection troubleshooting
```

[Full docs](./memory.md)

###### debugging.md

*Topic notes Claude writes when MEMORY.md gets long* (Claude writes)

*When it loads: Claude reads this when a related task comes up*

An example of a topic file Claude creates when MEMORY.md grows too long. Claude picks the filename based on what it splits out: debugging.md, architecture.md, build-commands.md, or similar. You never create these yourself. Claude reads a topic file back only when the current task relates to it.

```markdown
---
name: Debugging patterns
description: Auth token rotation and database connection troubleshooting for this project
type: reference
---

## Auth Token Issues
- Refresh token rotation: old token invalidated immediately
- If 401 after refresh: check clock skew between client and server

## Database Connection Drops
- Connection pool: max 10 in dev, 50 in prod
- Always check `docker compose ps` first
```

#### rules/

*User-level rules that apply to every project*

*When it loads: Rules without `paths:` load at session start. Rules with `paths:` load when a matching file enters context*

Same as project .claude/rules/ but applies everywhere. Use this for conventions you want across all your work, like personal code style or commit message format.

[Full docs](./memory.md#organize-rules-with-claude/rules/)

#### skills/

*Personal skills available in every project*

*When it loads: Invoked with `/skill-name` in any project*

Skills you built for yourself that work everywhere. Same structure as project skills: each is a folder with SKILL.md, scoped to your user account instead of a single project.

[Full docs](./skills.md)

#### commands/

*Personal single-file commands available in every project*

*When it loads: User types `/command-name` in any project*

Same as project commands/ but scoped to your user account. Each markdown file becomes a command available everywhere.

[Full docs](./skills.md)

#### output-styles/

*Custom instruction sets that adjust how Claude works*

*When it loads: Files read at startup; the style you select with outputStyle applies to every response*

Each markdown file defines an output style: a set of instructions for Claude that, by default, also replaces the built-in software-engineering task instructions. Use this to adapt Claude Code for uses beyond coding, or to add teaching or review modes.

Select a built-in or custom style with `/config` or the `outputStyle` key in settings. Styles here are available in every project; project-level styles with the same name take precedence.

**Tips**

* Built-in styles Default, Proactive, Concise, Explanatory, and Learning are included with Claude Code; custom styles go here
* Set `keep-coding-instructions: true` in frontmatter to keep the default task instructions alongside your additions
* Switching styles mid-session applies from your next message; in the terminal, a style file you create or edit mid-session is picked up after a restart

[Full docs](./output-styles.md)

##### teaching.md

*Example style that adds explanations and leaves small changes for you* (local only)

*When it loads: Active when `outputStyle` in settings is set to `teaching`*

With this style, Claude adds a "Why this approach" note after each task and leaves TODO(human) markers for changes under 10 lines instead of writing them itself. Select it by setting `outputStyle` to the filename without .md, or to the `name` field if you set one in frontmatter.

```markdown
---
description: Explains reasoning and asks you to implement small pieces
keep-coding-instructions: true
---

After completing each task, add a brief "Why this approach" note
explaining the key design decision.

When a change is under 10 lines, ask the user to implement it
themselves by leaving a TODO(human) marker instead of writing it.
```

#### agents/

*Personal subagents available in every project*

*When it loads: Claude delegates or you @-mention in any project*

Subagents defined here are available across all your projects. Same format as project agents.

[Full docs](./sub-agents.md)

#### workflows/

*Personal dynamic workflows available in every project*

*When it loads: Loaded at startup; each file becomes a /<name> command*

Workflow scripts saved here are available across all your projects. A project workflow with the same name in `.claude/workflows/` takes precedence.

[Full docs](./workflows.md)

#### agent-memory/

*Persistent memory for subagents with `memory: user`* (Claude writes)

*When it loads: Loaded into the subagent system prompt when the subagent starts*

Subagents with `memory: user` in their frontmatter store knowledge here that persists across all projects. For project-scoped subagent memory, see `.claude/agent-memory/` instead.

[Full docs](./sub-agents.md#enable-persistent-memory)

Claude Code reads instructions, settings, skills, subagents, and memory from your project directory and from `~/.claude` in your home directory. Commit project files to git to share them with your team; files in `~/.claude` are personal configuration that applies across all your projects.

On Windows, `~/.claude` resolves to `%USERPROFILE%\.claude`. If you set [`CLAUDE_CONFIG_DIR`](./env-vars.md), every `~/.claude` path on this page lives under that directory instead.

Most users only edit `CLAUDE.md` and `settings.json`. The rest of the directory is optional: add skills, rules, or subagents as you need them.

## Explore the directory

Click files in the tree to see what each one does, when it loads, and an example.

## What's not shown

The explorer covers files you author and edit. A few related files live elsewhere:

| File                    | Location                   | Purpose                                                                                                                                                                                                                                                                                                                                                                                                                                                                  |
| ----------------------- | -------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `managed-settings.json` | System-level, varies by OS | Enterprise-enforced settings that you can't override, apart from [narrow exceptions](./settings.md#security-keys-where-the-stricter-value-applies). See [where to save the file](./managed-settings.md#deploy-a-managed-settings-file) and [which managed source Claude Code uses](./managed-settings.md#precedence-within-the-managed-tier).                                                                                                                               |
| `CLAUDE.local.md`       | Project root               | Your private preferences for this project, loaded alongside CLAUDE.md. Create it manually and add it to `.gitignore`.                                                                                                                                                                                                                                                                                                                                                    |
| Installed plugins       | `~/.claude/plugins`        | Cloned marketplaces, installed plugin versions, and per-plugin data, managed by `claude plugin` commands. For a plugin installed from a marketplace [`command` source](./plugin-marketplaces.md#command-sources) in link mode, Claude Code stores links here instead of a copy, and the plugin's files stay in the directory the command prints. See [plugin caching](./plugins-reference.md#plugin-caching-and-file-resolution) for how orphaned versions are cleaned up. |

`~/.claude` also holds data Claude Code writes as you work: transcripts, prompt history, file snapshots, caches, and logs. See [application data](#application-data) below.

## Choose the right file

Different kinds of customization live in different files. Use this table to find where a change belongs.

| You want to                                        | Edit                                     | Scope             | Reference                                           |
| :------------------------------------------------- | :--------------------------------------- | :---------------- | :-------------------------------------------------- |
| Give Claude project context and conventions        | `CLAUDE.md`                              | project or global | [Memory](./memory.md)                                |
| Allow or block specific tool calls                 | `settings.json` `permissions` or `hooks` | project or global | [Permissions](./permissions.md), [Hooks](./hooks.md)  |
| Run a script before or after tool calls            | `settings.json` `hooks`                  | project or global | [Hooks](./hooks.md)                                  |
| Set environment variables for the session          | `settings.json` `env`                    | project or global | [Settings](./settings-reference.md#all-settings)     |
| Keep personal overrides out of git                 | `settings.local.json`                    | project only      | [Settings scopes](./settings.md#where-settings-live) |
| Add a prompt or capability you invoke with `/name` | `skills/<name>/SKILL.md`                 | project or global | [Skills](./skills.md)                                |
| Define a specialized subagent with its own tools   | `agents/*.md`                            | project or global | [Subagents](./sub-agents.md)                         |
| Orchestrate many subagents from a script           | `workflows/*.js`                         | project or global | [Dynamic workflows](./workflows.md)                  |
| Connect external tools over MCP                    | `.mcp.json`                              | project only      | [MCP](./mcp.md)                                      |
| Change how Claude formats responses                | `output-styles/*.md`                     | project or global | [Output styles](./output-styles.md)                  |

## File reference

This table lists every file the explorer covers. Project-scope files live in your repo under `.claude/` (or at the root for `CLAUDE.md`, `.mcp.json`, and `.worktreeinclude`). Global-scope files live in `~/.claude/` and apply across all projects.

> [!NOTE]
> Several things can override what you put in these files:
>
> * [Managed settings](./server-managed-settings.md) deployed by your organization take precedence over everything, apart from the [exceptions under Settings precedence](./settings.md#exceptions-to-managed-settings-precedence)
> * CLI flags like `--permission-mode` or `--settings` override `settings.json` for that session
> * Some environment variables take precedence over their equivalent setting, but this varies: check the [environment variables reference](./env-vars.md) for each one
>
> See [settings precedence](./settings.md#settings-precedence) for the full order.

Click a filename to open that node in the explorer above.

| File                                                | Scope              | Commit | What it does                                                                                                  | Reference                                                       |
| --------------------------------------------------- | ------------------ | ------ | ------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------- |
| [`CLAUDE.md`](#ce-claude-md)                        | Project and global | ✓      | Instructions loaded every session                                                                             | [Memory](./memory.md)                                            |
| [`rules/*.md`](#ce-rules)                           | Project and global | ✓      | Topic-scoped instructions, optionally path-gated                                                              | [Rules](./memory.md#organize-rules-with-claude/rules/)           |
| [`settings.json`](#ce-settings-json)                | Project and global | ✓      | Permissions, hooks, env vars, model defaults                                                                  | [Settings](./settings.md)                                        |
| [`settings.local.json`](#ce-settings-local-json)    | Project only       |        | Your personal overrides, gitignored when Claude Code saves a setting to it                                    | [Settings scopes](./settings.md#where-settings-live)             |
| [`.mcp.json`](#ce-mcp-json)                         | Project only       | ✓      | Team-shared MCP servers                                                                                       | [MCP scopes](./mcp.md#mcp-installation-scopes)                   |
| [`.worktreeinclude`](#ce-worktreeinclude)           | Project only       | ✓      | Gitignored files to copy into new worktrees                                                                   | [Worktrees](./worktrees.md#copy-gitignored-files-into-worktrees) |
| [`skills/<name>/SKILL.md`](#ce-skills)              | Project and global | ✓      | Reusable prompts invoked with `/name` or auto-invoked                                                         | [Skills](./skills.md)                                            |
| [`commands/*.md`](#ce-commands)                     | Project and global | ✓      | Single-file prompts; same mechanism as skills                                                                 | [Skills](./skills.md)                                            |
| [`output-styles/*.md`](#ce-output-styles)           | Project and global | ✓      | Custom instruction sets that adjust how Claude works                                                          | [Output styles](./output-styles.md)                              |
| [`agents/*.md`](#ce-agents)                         | Project and global | ✓      | Subagent definitions with their own prompt and tools                                                          | [Subagents](./sub-agents.md)                                     |
| [`workflows/*.js`](#ce-workflows)                   | Project and global | ✓      | Dynamic workflow scripts written by Claude and saved from `/workflows`; each file becomes a `/<name>` command | [Dynamic workflows](./workflows.md)                              |
| [`agent-memory/<name>/`](#ce-agent-memory)          | Project and global | ✓      | Persistent memory for subagents                                                                               | [Persistent memory](./sub-agents.md#enable-persistent-memory)    |
| [`~/.claude.json`](#ce-claude-json)                 | Global only        |        | App state, OAuth, UI toggles, personal MCP servers                                                            | [Global config](./settings-reference.md#global-config-settings)  |
| [`projects/<project>/memory/`](#ce-global-projects) | Global only        |        | Auto memory: Claude's notes to itself across sessions                                                         | [Auto memory](./memory.md#auto-memory)                           |
| [`keybindings.json`](#ce-keybindings)               | Global only        |        | Custom keyboard shortcuts                                                                                     | [Keybindings](./keybindings.md)                                  |
| [`themes/*.json`](#ce-themes)                       | Global only        |        | Custom color themes                                                                                           | [Custom themes](./terminal-config.md#create-a-custom-theme)      |

## Troubleshoot configuration

If a setting, hook, or file isn't taking effect, see [Debug your configuration](./debug-your-config.md) for the inspection commands and a symptom-first lookup table.

## Application data

Beyond the config you author, `~/.claude` holds data Claude Code writes during sessions. These files are plaintext. Anything that passes through a tool lands in a transcript on disk: file contents, command output, pasted text.

### Cleaned up automatically

Claude Code deletes the files in the paths below once they're older than [`cleanupPeriodDays`](./settings-reference.md#cleanupperioddays), as long as it can safely determine the retention period. The default is 30 days and the minimum is 1; setting `0` fails with a validation error. The same age cutoff applies to automatic removal of [orphaned worktrees](./worktrees.md#clean-up-subagent-and-background-session-worktrees).

| Path under `~/.claude/`                                                                                                         | Contents                                                                                                                                                                                                                                                                                             |
| ------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `projects/<project>/<session>.jsonl`                                                                                            | Full conversation transcript: every message, tool call, and tool result                                                                                                                                                                                                                              |
| `projects/<project>/<session>.orphaned-<timestamp>-<suffix>.jsonl`, `projects/<project>/<session>.jsonl.superseded-<timestamp>` | A previous transcript for the session that Claude Code set aside instead of overwriting or deleting it. It doesn't appear in the session picker                                                                                                                                                      |
| `projects/<project>/<session>/subagents/`                                                                                       | [Subagent](./sub-agents.md) conversation transcripts, removed with the parent session transcript when it ages out                                                                                                                                                                                     |
| `projects/<project>/<session>/tool-results/`                                                                                    | Large tool outputs spilled to separate files                                                                                                                                                                                                                                                         |
| `file-history/<session>/`                                                                                                       | Pre-edit snapshots of files Claude changed, used for [checkpoint restore](./checkpointing.md). Holds snapshots for the 100 most recent checkpoints; snapshot files that no retained checkpoint references are deleted, except each file's first snapshot                                              |
| `plans/`                                                                                                                        | Plan files written during [plan mode](./permission-modes.md#analyze-before-you-edit-with-plan-mode)                                                                                                                                                                                                   |
| `debug/`                                                                                                                        | Per-session debug logs, written while debug logging is on, such as when you start with [`--debug`](./cli-reference.md#cli-flags) or run `/debug`                                                                                                                                                      |
| `paste-cache/`                                                                                                                  | Contents of large pastes                                                                                                                                                                                                                                                                             |
| `image-cache/<session>/`                                                                                                        | Attached images. On each sweep, Claude Code removes the directories of all other sessions, whatever their age.                                                                                                                                                                                       |
| `uploads/<session>/`                                                                                                            | Files you attach from the web or mobile app, and photos you attach from the mobile app, when messaging a [Remote Control](./remote-control.md) session. An attachment to a [cloud session](./claude-code-on-the-web.md) is saved in that session's own cloud environment instead, not on your machine. |
| `session-env/`                                                                                                                  | Per-session environment metadata                                                                                                                                                                                                                                                                     |
| `tasks/`                                                                                                                        | Task lists written by the task tools, one directory per list                                                                                                                                                                                                                                         |
| `shell-snapshots/`                                                                                                              | Aliases, functions, and shell options captured at startup and applied by the [Bash tool](./tools-reference.md#bash-tool-behavior) to each command. Removed on clean exit. The sweep clears any left after a crash.                                                                                    |
| `backups/`                                                                                                                      | Earlier versions of `~/.claude.json`, copied when Claude Code rewrites the file. Claude Code keeps the five newest, plus a copy of any version it couldn't parse.                                                                                                                                    |
| `feedback-bundles/`                                                                                                             | Redacted transcript archives written by `/feedback` on third-party providers or when no Anthropic credentials are configured, for sending to your Anthropic account team                                                                                                                             |
| `feedback/drafts/`                                                                                                              | Queued [Claude-drafted feedback](./tools-reference.md#sendfeedback-tool-behavior) awaiting your review in `/feedback`. Swept after `cleanupPeriodDays` or 30 days, whichever is shorter. When the queue is at its 10-draft limit, Claude Code deletes the oldest draft to make room.                  |
| `usage-data/`                                                                                                                   | `report.html` and timestamped report copies written by [`/insights`](./costs.md#analyze-your-usage-patterns), plus cached per-session analysis data used to build them                                                                                                                                |
| `todos/`, `statsig/`, `logs/`                                                                                                   | Legacy directories from older versions. No longer written. The sweep removes their contents and then the empty directory.                                                                                                                                                                            |

Session files in `sessions/`, auto memory, and Claude Desktop and Cowork transcripts each follow their own retention rule:

* **`sessions/`**: holds one small file per running session, used to detect concurrent sessions and crashes. It isn't part of the age-based sweep: Claude Code removes each file when its session exits and clears crash leftovers on the next launch.
* **Auto memory**: the sweep doesn't delete the memory files in a project's [auto memory](./memory.md#auto-memory) directory, `projects/<project>/memory/`. Claude Code removes that directory only if it has been empty for the whole retention period. Before v2.1.228, the sweep treated folders inside the memory directory as session data and could delete old files beneath it.
* **Claude Desktop and Cowork transcripts**: Claude Code keeps the transcript of a session you started or most recently continued in Claude Desktop or Cowork at any age. To give these transcripts an age limit, set [`desktopSessionCleanupPeriodDays`](./settings-reference.md#desktopsessioncleanupperioddays). When [managed settings](./managed-settings.md) set `cleanupPeriodDays`, Claude Code deletes these transcripts after that period instead. Requires Claude Code v2.1.248 or later; earlier versions delete them after `cleanupPeriodDays`.

Claude Code skips the sweep entirely in these cases:

* **Bare mode**: when you run `claude -p` with [`--bare`](./headless.md#start-faster-with-bare-mode), Claude Code doesn't run the sweep in that session.
* **Paused sweep**: if Claude Code can't safely determine the retention period, it pauses the retention cleanup sweep; the [`retention_sweep` event](./monitoring-usage.md#retention-sweep-event) lists each configuration that pauses it. When the cause is a settings file that can't be read or parsed, or settings errors with `cleanupPeriodDays` or `desktopSessionCleanupPeriodDays` explicitly set, Claude Code also shows a warning in `/status` until you fix the settings errors. When [managed settings](./server-managed-settings.md) provide `cleanupPeriodDays`, Claude Code runs the sweep at the managed value in either case.

### Kept until you delete them

The retention cleanup sweep doesn't remove the paths below. Claude Code keeps them until you delete them, apart from the two caches it deletes when you log out.

| Path under `~/.claude/` | Contents                                                                                                                                                                                                                                                                                                                                                          |
| ----------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `history.jsonl`         | Every prompt you've typed, with timestamp and project path. Used for up-arrow recall, `Ctrl+R` history search, and `!` shell-command completion.                                                                                                                                                                                                                  |
| `stats-cache.json`      | Aggregated token and cost counts shown by `/usage`                                                                                                                                                                                                                                                                                                                |
| `remote-settings.json`  | Cached copy of [server-managed settings](./server-managed-settings.md) for your organization, or `{}` when your organization has configured none. Only present when the session [fetches them](./server-managed-settings.md#platform-availability). Claude Code checks for updates at startup and hourly during a session. Claude Code deletes it when you log out. |
| `cache/changelog.md`    | Cached copy of the Claude Code changelog, shown by `/release-notes`. Refreshed in the background.                                                                                                                                                                                                                                                                 |
| `policy-limits.json`    | Cached feature policy settings for your organization. Only present for some account types. Refreshed automatically. Claude Code deletes it when you log out.                                                                                                                                                                                                      |

<a id="state-files-to-keep"></a>

Other files appear depending on which features you use. Caches and lock files are safe to delete. Keep these state files:

* `.credentials.json`: your [login credentials](./authentication.md#credential-management)
* `agent-memory/`: [subagent memory](./sub-agents.md#enable-persistent-memory)
* `jobs/` and `daemon/`: [background session](./agent-view.md#where-state-is-stored) state

### Plaintext storage

Transcripts and history are not encrypted at rest. OS file permissions are the only protection. If a tool reads a `.env` file or a command prints a credential, that value is written to `projects/<project>/<session>.jsonl`. To reduce exposure:

* Lower `cleanupPeriodDays` to shorten how long Claude Code keeps transcripts
* Set [`desktopSessionCleanupPeriodDays`](./settings-reference.md#desktopsessioncleanupperioddays) to give Claude Desktop and Cowork transcripts an age limit too
* Set the [`CLAUDE_CODE_SKIP_PROMPT_HISTORY`](./env-vars.md) environment variable to skip writing transcripts and prompt history in any mode. In non-interactive mode, you can instead pass `--no-session-persistence` alongside `-p`, or set `persistSession: false` in the TypeScript Agent SDK; the Python SDK has no equivalent option.
* Use [permission rules](./permissions.md) to deny reads of credential files

### Clear local data

Run `claude project purge` to delete the state Claude Code holds for one project. It deletes:

* Transcripts and auto memory under `projects/`
* Per-session `tasks/`, `debug/`, and `file-history/` entries
* Matching prompt lines in `history.jsonl`
* The project's entry in `~/.claude.json`

The command prints the full deletion plan and asks for confirmation before removing anything.

The examples below use `~/work/my-repo` as a placeholder. Replace it with the path to your project. If no state matches the path, the command prints an error and exits with status 1.

Preview the plan without deleting anything:

```bash theme={null}
claude project purge ~/work/my-repo --dry-run
```

The plan lists each matching item and why it is included:

```text theme={null}
Purge plan for /home/user/work/my-repo:

  dir:    /home/user/.claude/projects/-home-user-work-my-repo
           project transcripts (.jsonl) and memory/
  config: projects["/home/user/work/my-repo"]
           project entry in ~/.claude.json (trust, history, MCP servers)
  filter: /home/user/.claude/history.jsonl
           12 prompt(s) typed in this project

shell-snapshots/ are not project-scoped and will not be touched
backups/ may still contain this project entry in old .claude.json snapshots (/home/user/.claude/backups); at most 5 are kept and they rotate out automatically
Dry run: 3 item(s) would be deleted.
```

Delete with a single confirmation prompt:

```bash theme={null}
claude project purge ~/work/my-repo
```

The command prints the same plan, then asks `Delete 3 item(s) for /home/user/work/my-repo? This cannot be undone. [y/N]` and deletes only if you answer `y`.

Omit the path to pick a project from an interactive list.

Skip the confirmation prompt for use in scripts:

```bash theme={null}
claude project purge ~/work/my-repo --yes
```

Pass `--all` instead of a path to purge state for every project at once, which deletes `history.jsonl` outright rather than filtering it. Pass `-i` to step through the deletion plan one item at a time.

The command leaves `shell-snapshots/` and `backups/` alone because those are not project-scoped, and warns about them in the plan output.

You can also delete any of the application-data paths above by hand, apart from the [state files to keep](#state-files-to-keep). New sessions are unaffected. The table below shows what you lose for past sessions.

| Delete                                                                                                                                         | You lose                                                                                                          |
| ---------------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------- |
| `~/.claude/projects/`                                                                                                                          | Resume, continue, and rewind for past sessions, and auto memory for every project                                 |
| `~/.claude/history.jsonl`                                                                                                                      | Up-arrow prompt recall, `Ctrl+R` history search, and `!` shell-command completion                                 |
| `~/.claude/paste-cache/`                                                                                                                       | Pasted text in recalled prompts; see [paste large content](./terminal-config.md#paste-large-content)               |
| `~/.claude/uploads/`                                                                                                                           | Attachments that past [Remote Control](./remote-control.md) sessions refer to by path                              |
| `~/.claude/file-history/`                                                                                                                      | Checkpoint restore for past sessions                                                                              |
| `~/.claude/stats-cache.json`                                                                                                                   | Historical totals shown by `/usage`                                                                               |
| `~/.claude/usage-data/`                                                                                                                        | Past [`/insights`](./costs.md#analyze-your-usage-patterns) reports and the cached analysis data used to build them |
| `~/.claude/feedback-bundles/`                                                                                                                  | Feedback and bug-report archives you haven't yet sent to your Anthropic account team                              |
| `~/.claude/feedback/drafts/`                                                                                                                   | [Claude-drafted feedback](./tools-reference.md#sendfeedback-tool-behavior) you haven't sent                        |
| `~/.claude/remote-settings.json`                                                                                                               | Nothing. Re-fetched on next launch.                                                                               |
| `~/.claude/cache/changelog.md`                                                                                                                 | Nothing. Refreshed in the background.                                                                             |
| `~/.claude/policy-limits.json`                                                                                                                 | Nothing. Refreshed automatically.                                                                                 |
| `~/.claude/tasks/`                                                                                                                             | Task lists that a resumed session would pick up                                                                   |
| `~/.claude/debug/`, `~/.claude/plans/`, `~/.claude/image-cache/`, `~/.claude/session-env/`, `~/.claude/shell-snapshots/`, `~/.claude/backups/` | Nothing user-facing                                                                                               |
| `~/.claude/todos/`, `~/.claude/statsig/`, `~/.claude/logs/`                                                                                    | Nothing. Legacy directories not written by current versions.                                                      |

Don't delete `~/.claude.json`, `~/.claude/settings.json`, or `~/.claude/plugins/`: those hold your auth, preferences, and installed plugins.

## Related resources

* [Manage Claude's memory](./memory.md): write and organize CLAUDE.md, rules, and auto memory
* [Configure settings](./settings.md): set permissions, hooks, environment variables, and model defaults
* [Create skills](./skills.md): build reusable prompts and workflows
* [Configure subagents](./sub-agents.md): define specialized agents with their own context
