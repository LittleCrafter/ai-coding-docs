> ## Documentation Index
> Fetch the complete documentation index at: https://code.claude.com/docs/llms.txt
> Use this file to discover all available pages before exploring further.

# Prompt library

> Copy-paste prompts for Claude Code, tagged by task and role.

## Prompts

### Discover - Onboard

#### Get oriented in a new repository

*Start here: 1*

```text
give me an overview of this codebase: architecture, key directories, and how the pieces connect
```

* **Why this works**: Describe what you want to know, not which files to read. Claude explores the project on its own and returns a summary of how it fits together.
* **Make it stick**: Run `/init` to set up `CLAUDE.md` so Claude remembers this every session
* **From**: [Common workflows](./common-workflows.md)

### Discover - Understand

#### Explain unfamiliar code

```text
explain what src/scheduler/queue.ts does and how data flows through it. write it up as an HTML page with a diagram, then open it in my browser
```

* **Why this works**: Name the file and say what format you want the answer in. Swap the HTML page for a diagram, bullet points, or whatever fits how you learn.
* **Make it stick**: Set an output style so Claude always explains in your preferred format
* **From**: [Common workflows](./common-workflows.md)

#### Find where something happens

*Start here: 2*

```text
where do we validate uploaded file types?
```

* **Why this works**: Search by behavior instead of by filename. The search works even when you don't know what the file is called or which directory it lives in.
* **From**: [Common workflows](./common-workflows.md)

#### Check what breaks before you delete

```text
what would break if I deleted the retryWithBackoff helper?
```

* **Why this works**: Ask before you remove anything. The list of callers and downstream effects tells you whether you're looking at a one-line cleanup or a change you need to coordinate.
* **From**: [Common workflows](./common-workflows.md)

#### Trace how code evolved

```text
look through the commit history of internal/auth/session.go and summarize how it evolved and why
```

* **Why this works**: Point at commit history when the question is why, not what. Claude reads the log and blame for whatever version control you use and explains the decisions behind the current implementation.
* **From**: [Best practices](./best-practices.md)

#### Scope a change before you start

*Tags: Product, Design*

```text
which files would I need to touch to add a dark mode toggle to settings?
```

* **Why this works**: Size the work before you commit it to a roadmap. The file list tells you whether you're looking at one component or a cross-cutting change.
* **From**: [How Anthropic teams use Claude Code](https://claude.com/blog/how-anthropic-teams-use-claude-code)

#### Ask the codebase a product question

*Tags: Product*

```text
I am a PM. walk me through what happens when a user clicks Export to PDF, from the UI down to the result
```

* **Why this works**: State your role so the answer is pitched at the right level. Claude explains what the product actually does from the source code, without you needing to read it.
* **Make it stick**: Set an output style so Claude always pitches answers at this level
* **From**: [How Anthropic teams use Claude Code](https://claude.com/blog/how-anthropic-teams-use-claude-code)

### Design - Plan

#### Plan a multi-file change before touching code

*Tags: Product, Design*

```text
plan how to refactor the payment module to support multiple currencies. list the files you would change, but don't edit anything yet
```

* **Why this works**: Adding "don't edit yet" separates exploration from changes, so you see the approach before any code moves. To make plan-first the default on every prompt, press Shift+Tab for [plan mode](./permission-modes.md#analyze-before-you-edit-with-plan-mode).
* **From**: [Common workflows](./common-workflows.md)

#### Draft a spec by interview

*Tags: Product*

```text
I want to build per-workspace rate limits. interview me about implementation, UX, edge cases, and tradeoffs until we have covered everything, then write the spec to SPEC.md
```

* **Why this works**: Ask to be interviewed instead of writing the spec yourself. Claude asks you structured questions until the requirements are complete, then writes the result to a file.
* **Make it stick**: Save your interview questions as a `/spec` skill so every spec starts the same way
* **From**: [Best practices](./best-practices.md)

#### Turn a meeting into tickets

*Tags: Product*

```text
read @meeting-notes.md and write up the action items, then create a Linear ticket for each with acceptance criteria
```

* **Why this works**: Skip the transcription step. Claude pulls action items from the unstructured input and writes them straight into your tracker via [MCP](./mcp.md), so you review the tickets, not the transcript.
* **Make it stick**: Save this as a `/tickets` skill
* **Needs**: your issue tracker added as a [claude.ai connector](./mcp.md#use-mcp-servers-from-claude-ai) or [MCP server](./mcp.md).
* **From**: [How Anthropic teams use Claude Code](https://claude.com/blog/how-anthropic-teams-use-claude-code)

#### Map edge cases before building

*Tags: Design, Product*

```text
list the error states, empty states, and edge cases for the file upload flow that the design needs to cover
```

* **Why this works**: Ask for what's missing, not what's there. Claude lists the error states, empty states, and edge cases a happy-path design tends to skip.
* **From**: [How Anthropic teams use Claude Code](https://claude.com/blog/how-anthropic-teams-use-claude-code)

### Design - Prototype

#### Turn a mockup into a working prototype

*Tags: Design, Product, Marketing*

*Paste, drag, or @-mention your mockup image, then send this:*

```text
here is a mockup. build a working prototype I can click through, matching the layout and states shown
```

* **Why this works**: A clickable prototype answers questions a static mockup can't. Hand the working code to engineering instead of explaining the interactions in a doc.
* **From**: [How Anthropic teams use Claude Code](https://claude.com/blog/how-anthropic-teams-use-claude-code)

#### Implement from a screenshot and self-check

*Tags: Design*

*Paste, drag, or @-mention your design image, then send this:*

```text
implement this design, then take a screenshot of the result, compare it to the original, and fix any differences
```

* **Why this works**: This gives Claude a verification loop: it renders, compares against the source image, and iterates without you pointing out each gap.
* **Make it stick**: Use `/goal` to keep Claude iterating toward matching screenshots
* **Needs**: a way for Claude to render and screenshot the result. The [Desktop app](./desktop.md#preview-your-app) has this built in. In the terminal, install the [Chrome extension](./chrome.md) or a Playwright [MCP](./mcp.md) server.
* **From**: [Best practices](./best-practices.md)

### Build - Implement

#### Follow an existing pattern

```text
look at how the GitHub webhook handler is implemented to understand the pattern, then build a Stripe webhook handler the same way
```

* **Why this works**: Point at code you already like. Without a reference, Claude defaults to general best practices. With one, it matches the conventions your codebase actually uses.
* **Make it stick**: Ask Claude to write the pattern it followed into `CLAUDE.md` so future sessions match it without the reference
* **From**: [Best practices](./best-practices.md)

#### Generate docs for undocumented code

*Tags: Docs*

```text
find the public functions in src/auth/ without JSDoc comments and add them, matching the style already used in the file
```

* **Why this works**: Name the scope and the format. Claude finds what's missing and matches the comment style already in the file, so the new docs read like the rest.
* **From**: [Common workflows](./common-workflows.md)

#### Add a small, well-defined feature

```text
add a /health endpoint that returns the app version and uptime
```

* **Why this works**: State the inputs and outputs, not how to build it. Claude finds where similar code lives and adds yours alongside it.
* **From**: [Common workflows](./common-workflows.md)

#### Build a small internal tool from scratch

*Tags: Product, Design, Marketing, Docs*

```text
create a drag-and-drop Kanban board with three columns using HTML, CSS, and vanilla JavaScript, then open it in my browser
```

* **Why this works**: You don't need a project, a framework, or a build step. Describe the tool and ask Claude to open it so you see it working immediately.
* **From**: [How Anthropic teams use Claude Code](https://claude.com/blog/how-anthropic-teams-use-claude-code)

#### Work an issue end to end

```text
read issue #312, implement the fix, and run the tests
```

* **Why this works**: Give the issue number, not a summary. Claude reads the full ticket itself, so requirements you'd forget to mention come through, and it validates the change before reporting back.
* **Needs**: the [gh CLI](https://cli.github.com) authenticated, or GitHub added as a [claude.ai connector](./mcp.md#use-mcp-servers-from-claude-ai).
* **From**: [Common workflows](./common-workflows.md)

#### Find and update copy across the codebase

*Tags: Design, Docs, Marketing*

```text
find every place we say "Sign up free" or a close variant, show me each one in context, then update them all to "Start free trial". leave tests and the changelog alone
```

* **Why this works**: Ask for variants and say what to skip. Claude finds phrasings a literal search would miss and leaves test fixtures and history untouched, so you review only the copy users actually see.
* **From**: [How Anthropic teams use Claude Code](https://claude.com/blog/how-anthropic-teams-use-claude-code)

#### Draft a document from past examples

*Tags: Docs, Marketing, Product*

```text
read the privacy impact assessments in legal/pia/ to learn the structure and voice, then draft a new one for the new analytics integration
```

* **Why this works**: Point at a folder of finished work instead of describing your style. Claude learns the structure and voice from what you've already shipped, so the first draft reads like one of yours.
* **Make it stick**: Save the voice as a skill so every draft starts there
* **From**: [How Anthropic uses Claude in Legal](https://claude.com/blog/how-anthropic-uses-claude-legal)

### Build - Test

#### Write tests, run them, fix failures

*Start here: 4*

```text
write tests for app/parsers/feed.py, run them, and fix any failures
```

* **Why this works**: Ask for write, run, and fix together so Claude iterates without stopping for instructions.
* **Make it stick**: Run `/init` so Claude learns your test command automatically
* **From**: [Common workflows](./common-workflows.md)

#### Drive implementation from tests

```text
write tests for the password reset flow first, then implement it until they pass
```

* **Why this works**: Test-driven development: the tests define when the work is complete, and Claude iterates on the implementation until they pass.
* **From**: [Scaling agentic coding guide](https://resources.anthropic.com/hubfs/Scaling%20agentic%20coding%20across%20your%20organization.pdf)

#### Fill gaps from a coverage report

```text
read coverage/coverage-summary.json and add tests for the lowest-covered files until each is above 80%
```

* **Why this works**: Point at the coverage report instead of guessing what's untested. Claude reads the actual numbers and writes tests for the files that need them most.
* **Make it stick**: Set this as a `/goal` so Claude keeps writing tests toward the coverage target
* **From**: [Common workflows](./common-workflows.md)

### Build - Refactor

#### Migrate a pattern across the codebase

```text
migrate everything from the old logging API to the structured logger: identify every place that needs to change, then make the changes
```

* **Why this works**: Describe the old pattern and the new one. Asking Claude to identify every place first means the call sites are listed in the response, so you can check none were missed. For a migration across many files, run [/batch](./commands.md). Claude splits the work into units for you to approve, then background subagents make the changes and open one pull request per unit.
* **From**: [Common workflows](./common-workflows.md)

#### Port code to another language

```text
port this Python module to Rust, keeping the same public API and test behavior
```

* **Why this works**: Say what to preserve, not just the target language. Naming the API or behavior that must stay the same gives Claude a contract to check the port against.
* **From**: [How Anthropic teams use Claude Code](https://claude.com/blog/how-anthropic-teams-use-claude-code)

#### Optimize against a measurable target

*Tags: Data*

```text
optimize the search query to bring p95 latency from 2s down to under 500ms
```

* **Why this works**: Stating the metric and target gives Claude a clear definition of done.
* **Make it stick**: Set this as a `/goal` so Claude keeps measuring and iterating toward the number
* **From**: [Scaling agentic coding guide](https://resources.anthropic.com/hubfs/Scaling%20agentic%20coding%20across%20your%20organization.pdf)

#### Fix a precise visual bug

*Tags: Design*

```text
the login button extends 20px beyond the card border on mobile. fix it.
```

* **Why this works**: Precise visual feedback gets a precise fix. State the exact element, measurement, and viewport.
* **Make it stick**: Add a preview tool so Claude screenshots and verifies the fix itself
* **From**: [Scaling agentic coding guide](https://resources.anthropic.com/hubfs/Scaling%20agentic%20coding%20across%20your%20organization.pdf)

### Build - Review

#### Review your changes before you commit

*Start here: 5*

```text
review my uncommitted changes and flag anything that looks risky before I commit
```

* **Why this works**: Catch problems while they're still cheap to fix. Claude reads the changed files in full, not just the diff lines, so it spots issues a quick self-review misses.
* **Make it stick**: Run `/code-review` for the same check in one command
* **From**: [Common workflows](./common-workflows.md)

#### Review a pull request

```text
review PR #247 and summarize what changed, then list any concerns
```

* **Why this works**: Claude reviews with the whole codebase in context, not just the diff. It reads the changed code and what it calls, so it catches problems a diff-only review would miss.
* **Make it stick**: Run `/code-review <pr#>` in one command, or turn on Code Review for every PR
* **Needs**: the [gh CLI](https://cli.github.com) authenticated, or GitHub added as a [claude.ai connector](./mcp.md#use-mcp-servers-from-claude-ai).
* **From**: [Common workflows](./common-workflows.md)

#### Review infrastructure changes before applying

*Tags: Security, On-call*

*Paste your plan output into the prompt first, then send this:*

```text
here is my Terraform plan output. what is this going to do, and is anything here going to cause problems?
```

* **Why this works**: Plan output is dense and hard to scan. Pasting it gets you a plain-language summary of what's actually going to change before you apply it.
* **From**: [How Anthropic teams use Claude Code](https://claude.com/blog/how-anthropic-teams-use-claude-code)

#### Run a security review with a subagent

*Tags: Security*

```text
use a subagent to review src/api/ for security issues and report what it finds
```

* **Why this works**: A [subagent](./sub-agents.md) runs the audit in its own context window and reports back a summary, so a long security review doesn't fill up your main session. The built-in general-purpose subagent handles this without extra setup.
* **Make it stick**: Set up a dedicated security-review subagent your whole team can use
* **From**: [Best practices](./best-practices.md)

#### Catch issues before formal review

*Tags: Marketing, Docs*

```text
review launch-post.md for unsupported claims, missing attributions, and brand-guideline issues and list anything I should fix before it goes to legal
```

* **Why this works**: Get a first pass before a human spends time on it. Name the concerns you want checked so the review is focused, then fix what it finds and send a cleaner draft.
* **Make it stick**: Capture your review checklist as a skill your whole team can run
* **From**: [How Anthropic uses Claude in Legal](https://claude.com/blog/how-anthropic-uses-claude-legal)

### Build - Steer

#### Course-correct a wrong approach

```text
that is not right: the function signature needs to stay backward-compatible. try a different approach
```

* **Why this works**: Name the constraint Claude missed, not just that it's wrong. A specific reason gives Claude a concrete constraint to satisfy on the retry, instead of guessing again.
* **Make it stick**: Press `Esc` twice to open the rewind menu and restore code and conversation so the retry starts clean
* **From**: [Best practices](./best-practices.md)

#### Narrow the scope of a change

```text
that is too much. keep only the changes to the validation logic in src/forms/ and undo your other edits
```

* **Why this works**: When the direction is right but the change went too broad, ask Claude to keep part of it rather than rewinding everything. A stated boundary keeps a small fix from becoming a refactor.
* **From**: [Best practices](./best-practices.md)

#### Turn a correction into a rule

```text
you keep using default exports when this project uses named exports. add a rule to CLAUDE.md so this stops happening
```

* **Why this works**: A correction in chat isn't shared with your team. A rule in the project's [CLAUDE.md](./memory.md) is shared once you commit it, and Claude reads it at the start of every session.
* **Make it stick**: Open `/memory` to review what Claude wrote
* **From**: [Best practices](./best-practices.md)

### Ship - Git

#### Resolve merge conflicts

```text
resolve the merge conflicts in this branch and explain what you kept from each side
```

* **Why this works**: Say what state you want, not which markers to keep. Asking for the reasoning makes the merge reviewable instead of a black box.
* **From**: [Common workflows](./common-workflows.md)

#### Commit with a generated message

```text
commit these changes with a message that summarizes what I did
```

* **Why this works**: Let Claude derive the message from the diff. It matches your repository's existing commit style.
* **From**: [Common workflows](./common-workflows.md)

#### Open a pull request from a ticket

```text
find the Linear ticket about the login timeout and open a PR that implements it
```

* **Why this works**: Skip the context switch between tracker, editor, and GitHub. One prompt reads the spec, makes the change, and opens the PR.
* **Needs**: your issue tracker added as a [claude.ai connector](./mcp.md#use-mcp-servers-from-claude-ai) or [MCP server](./mcp.md).
* **From**: [Common workflows](./common-workflows.md)

### Ship - Release

#### Draft release notes from git history

*Tags: Product, Docs, Marketing*

```text
compare v2.3.0 to v2.4.0 and draft release notes grouped by feature, fix, and breaking change
```

* **Why this works**: Give two reference points and the structure you want. Claude reads the commit log between them and drafts a changelog you can edit.
* **Make it stick**: Save this as a `/changelog` skill
* **From**: [Common workflows](./common-workflows.md)

#### Write a CI workflow

*Tags: On-call*

```text
write a GitHub Actions workflow that runs the tests and deploys to staging on every push to main
```

* **Why this works**: Describe when it should run and what it should do; the YAML is generated for you, matched to your project's build and test commands.
* **From**: [Common workflows](./common-workflows.md)

### Operate - Debug

#### Find and fix a failing test

*Start here: 3*

```text
the UserAuth test is failing, find out why and fix it
```

* **Why this works**: Describe the symptom; you don't need to know which file is broken. Claude runs the test to see the failure, traces it into source, and fixes it.
* **From**: [Common workflows](./common-workflows.md)

#### Investigate a reported error

*Tags: On-call*

```text
users are seeing 500 errors on /api/settings. investigate and tell me what is going on
```

* **Why this works**: Describe the symptom and location; Claude reads the relevant code path and traces likely causes. Paste stack traces or logs if you have them.
* **Make it stick**: Put a deeplink in your runbook that opens Claude with this prompt pre-filled
* **From**: [Common workflows](./common-workflows.md)

#### Fix a build error at the root

*Tags: On-call*

*Paste the error output into the prompt first, then send this:*

```text
here is a build error. fix the root cause and verify the build succeeds
```

* **Why this works**: Asking for root cause and verification prevents surface-level patches that suppress the error without fixing it.
* **From**: [Best practices](./best-practices.md)

### Operate - Incident

#### Investigate a production incident

*Tags: On-call, Security*

```text
the checkout endpoint started returning 500s an hour ago. check the logs, recent deploys, and config changes, then tell me the most likely cause
```

* **Why this works**: List the evidence sources to correlate, not the steps to take. Claude reads logs, git history, and config together to narrow the cause.
* **Make it stick**: Connect Sentry or your log store via MCP
* **From**: [Common workflows](./common-workflows.md)

#### Diagnose from a console screenshot

*Tags: On-call, Data*

*Paste, drag, or @-mention your screenshot, then send this:*

```text
here is a screenshot of the GCP Kubernetes dashboard. walk me through why this pod is failing and give me the exact commands to fix it
```

* **Why this works**: Cloud consoles show you the problem but not the commands to fix it. Claude reads the screenshot and translates the dashboard into the kubectl, gcloud, or aws commands to run.
* **From**: [How Anthropic teams use Claude Code](https://claude.com/blog/how-anthropic-teams-use-claude-code)

#### Query logs in plain English

*Tags: Security, On-call, Data*

```text
show me all failed logins for the auth service over the past 24 hours. write the query, run it, and tell me what stands out
```

* **Why this works**: Ask the question instead of writing the SQL. Claude builds the query, runs it against your connected logs, and shows both the query and the result so you can check what ran.
* **Needs**: your data warehouse or log store added as a [claude.ai connector](./mcp.md#use-mcp-servers-from-claude-ai) or [MCP server](./mcp.md).
* **From**: [How Anthropic uses Claude in Cybersecurity](https://claude.com/blog/how-anthropic-uses-claude-cybersecurity)

### Operate - Data

#### Analyze a data file

*Tags: Data, Product, Marketing*

*Drag your file into the prompt, or replace the path below with an @-mention of your own:*

```text
read @reports/q1-signups.csv, summarize the key patterns, and write the results to an HTML page with charts, then open it in my browser
```

* **Why this works**: A one-off question doesn't need a one-off script. Point at a file in your project folder and Claude reads it directly, finds the patterns, and writes the output where you ask.
* **Make it stick**: Connect the data source via MCP instead of exporting files
* **From**: [How Anthropic teams use Claude Code](https://claude.com/blog/how-anthropic-teams-use-claude-code)

#### Generate variations from performance data

*Tags: Marketing, Data*

*Drag your file into the prompt, or replace the path below with an @-mention of your own:*

```text
read @ads-performance.csv, find the underperforming headlines, and generate 20 new variations that stay under 90 characters
```

* **Why this works**: State the constraint at the start so generation stays within the limit. Claude reads the metrics, picks what to replace, and produces alternatives that fit.
* **Make it stick**: Connect the ad platform via MCP instead of exporting a file
* **From**: [How Anthropic teams use Claude Code](https://claude.com/blog/how-anthropic-teams-use-claude-code)

### Operate - Automate

#### Turn a recurring task into a skill

```text
create a /ship skill for this project that runs the linter and tests, then drafts a commit message
```

* **Why this works**: Name the steps once; reuse them as a command. Claude writes a [skill](./skills.md) anyone on your team can run.
* **From**: [Common workflows](./common-workflows.md)

#### Add a hook for repeat behavior

```text
write a hook that runs prettier after every edit to a .ts or .tsx file
```

* **Why this works**: Hooks make a behavior automatic instead of something you have to remember to ask for. Describe the trigger and action and Claude writes the [hook](./hooks.md) configuration.
* **From**: [Best practices](./best-practices.md)

#### Connect a tool with MCP

```text
set up the Sentry MCP server so you can read my error reports directly
```

* **Why this works**: Connect the source once instead of pasting data every session. After [MCP](./mcp.md) setup, Claude reads from the tool directly when you ask about it.
* **From**: [Common workflows](./common-workflows.md)

#### Capture what to remember for next time

*Tags: Product, Docs*

```text
summarize what we did this session and suggest what to add to CLAUDE.md
```

* **Why this works**: Ask before you forget. Claude knows what it had to figure out this session and proposes [CLAUDE.md](./memory.md) entries so the next session starts with that context.
* **From**: [How Anthropic teams use Claude Code](https://claude.com/blog/how-anthropic-teams-use-claude-code)

This is a library of prompts to copy into Claude Code. Use it to explore ways of working you haven't tried, or when you're not sure where to start.

The prompts are collected from various Anthropic guides, including [Common workflows](./common-workflows.md), [Best practices](./best-practices.md), and [How Anthropic teams use Claude Code](https://claude.com/blog/how-anthropic-teams-use-claude-code). They're starting points rather than scripts. Open **Why this works** under any prompt to see the pattern behind it so you can write your own.

## What makes these prompts work

The prompts above share a few patterns. Recognizing them helps you adapt any prompt here to your own task.

**Describe the outcome, not the steps.** Say what you want and let Claude find the files. The prompt below works without naming a single file path.

```text wrap theme={null}
add rate limiting to the public API and make sure existing tests still pass
```

**Give it a way to check its own work.** Ask for run, test, compare, or verify in the same prompt so Claude iterates instead of stopping after one attempt. To check the finished change against the running app, run [`/verify`](./skills.md#run-and-verify-your-app).

```text wrap theme={null}
write the migration, run it against the dev database, and confirm the schema matches
```

**Point at a reference.** Name an existing file, test, or pattern to match so the new code is consistent with what you already have.

```text wrap theme={null}
add a settings page that follows the same layout as the profile page
```

**State the measurable target.** When the goal is performance or coverage, give the metric and threshold so completion is unambiguous.

```text wrap theme={null}
get the bundle size under 200KB and show me what you removed
```

**Give it the artifact.** Paste errors, logs, screenshots, and plan output directly in the prompt, or type `@` to reference a file. Claude reads the source instead of your description of it.

```text wrap theme={null}
why is the build failing? @build.log
```

**Say how you want the answer.** Name the format, length, or audience so the explanation fits how you'll use it. To make a format the default for every response, set an [output style](./output-styles.md).

```text wrap theme={null}
explain how the payment retry logic works as an HTML page with a diagram, then open it in my browser
```

For more on each pattern, see [best practices](./best-practices.md).

## Where these come from

These prompts are based on patterns from published Anthropic resources. Each card links to its source:

* [Common workflows](./common-workflows.md): step-by-step guides for the core tasks
* [Best practices](./best-practices.md): prompting patterns and project setup
* [How Anthropic teams use Claude Code](https://claude.com/blog/how-anthropic-teams-use-claude-code): real workflows from engineering, product, design, and data teams, with deep dives on [legal](https://claude.com/blog/how-anthropic-uses-claude-legal), [marketing](https://claude.com/blog/how-anthropic-uses-claude-marketing), and [cybersecurity](https://claude.com/blog/how-anthropic-uses-claude-cybersecurity)
* [Scaling agentic coding guide](https://resources.anthropic.com/hubfs/Scaling%20agentic%20coding%20across%20your%20organization.pdf): the enterprise adoption guide

For video walkthroughs of these patterns, see the free [Claude Code in Action](https://anthropic.skilljar.com/claude-code-in-action) course on Anthropic Academy.

## Related resources

The prompts on this page are starting points. Once one works for your project, the next step is making it repeatable: save it as a [skill](./skills.md) so anyone on your team can run it as a `/command`, and record the conventions Claude learned in [CLAUDE.md](./memory.md) so every session starts with that context instead of Claude relearning it. For larger or riskier changes, [plan mode](./permission-modes.md#analyze-before-you-edit-with-plan-mode) shows you the file list before any edits happen.

If you're introducing Claude Code across a team, see [administration](./admin-setup.md) for managed settings and policy, and [costs and usage](./costs.md) for how this work is billed on your plan.
