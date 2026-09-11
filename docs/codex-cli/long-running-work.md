# Long-running work

> For the complete documentation index, see [llms.txt](https://learn.chatgpt.com/llms.txt). Markdown versions of documentation pages are available by appending `.md` to the page URL.

For work that may take many steps, give ChatGPT a clear outcome, constraints,
and definition of done. Keep related work in the same chat so
ChatGPT can use the same context to choose the next step and decide when the
work is complete.

**Surface: Desktop app**

In the ChatGPT desktop app, enter `/goal` to start Goal mode. The progress row
lets you pause, resume, edit, or clear the goal while ChatGPT works.

**Surface: Web**

For hosted long-running work in ChatGPT web, use ChatGPT Work and put the
outcome, constraints, and review criteria directly in your prompt.

Continue in the same web chat to add context, change constraints, or
ask for a status update. Use separate chats when independent tasks can run in
parallel, and avoid giving two tasks write access to the same connected source.
For related work, keep the chats and source files together in a
[project](./projects.md).

**Surface: CLI**

In an interactive Codex CLI session, enter `/goal` to start Goal mode. Continue
the same session to steer the work or ask for a status update.

**Surface: IDE extension**

In the IDE extension chat, enter `/goal` to start Goal mode for the open
workspace. Continue the same chat to steer the task while it runs.

**Surface: Desktop app**

> Illustration: ChatGPT desktop app goal progress controls above the composer

<a id="start-a-goal"></a>
<a id="define-what-done-means"></a>
<a id="steer-a-running-goal"></a>
<a id="run-goals-in-parallel"></a>
<a id="related-docs"></a>

<a id="app-start-a-goal"></a>
<a id="cli-start-a-goal"></a>
<a id="ide-start-a-goal"></a>

## Start a goal

Type `/goal` in the ChatGPT desktop app, Codex CLI, or the IDE extension. The
goal text becomes both the first prompt and the completion criteria for the
task.

If the outcome is still unclear, start with `/plan`. Ask ChatGPT to interview you,
identify constraints, and turn the result into a goal with measurable success
criteria. Then start the refined goal with `/goal`.

<a id="app-define-what-done-means"></a>
<a id="web-define-what-done-means"></a>
<a id="cli-define-what-done-means"></a>
<a id="ide-define-what-done-means"></a>

## Define what done means

Write a goal that lets ChatGPT verify its own progress. Include three things when
they apply:

| Goal element     | What to include                                                               |
| ---------------- | ----------------------------------------------------------------------------- |
| **Outcome**      | Describe the result you want, not only the activity ChatGPT should perform.   |
| **Constraints**  | Name required tools, boundaries, compatibility needs, or approaches to avoid. |
| **Verification** | Add tests, measurements, or review criteria that prove the work is complete.  |

For example:

```text
Migrate this codebase from JavaScript to TypeScript. Preserve existing behavior,
compile in strict mode without explicit `any` types, and make the full test suite pass.
```

**Surface: Desktop app**

<a id="app-steer-a-running-goal"></a>

## Steer a running goal

In the ChatGPT desktop app, the goal progress row appears above the composer. Use it to
pause or resume work, edit the goal, or clear it. You can also send follow-up
messages while the goal runs to add context or adjust constraints.

Use a side chat when you want a status recap or an explanation without
interrupting the main chat. Pause the goal before you expect to lose
connectivity, then resume it when you're ready for ChatGPT to continue.

**Surface: Web**

<a id="steer-a-running-task"></a>

<a id="web-steer-running-work"></a>

## Steer running work

Continue in the same chat to add context, adjust constraints, or ask
for a status recap. Start a separate chat when another task can run
independently.

**Surface: CLI**

<a id="cli-steer-a-running-goal"></a>

## Steer a running goal

Send a follow-up message in the same interactive session to add context or
adjust constraints. Ask for a status recap when you want Codex to summarize
progress before it continues.

**Surface: IDE extension**

<a id="ide-steer-a-running-goal"></a>

## Steer a running goal

Continue in the same IDE chat to add context, adjust constraints, or ask for a
status recap. Keep the workspace available while the goal is running.

Starting a goal doesn't grant ChatGPT broader access. It keeps the same
[sandbox and approval policy](./sandboxing.md) and pauses when it
needs a decision. With [automatic approval
reviews](./sandboxing/auto-review.md), a separate reviewer can
evaluate eligible requests without expanding those boundaries.

<a id="app-run-goals-in-parallel"></a>
<a id="cli-run-goals-in-parallel"></a>
<a id="ide-run-goals-in-parallel"></a>

## Run goals in parallel

Each chat keeps its own context, messages, results, and goal. Run chats
concurrently, but avoid letting two chats change the same files. Use
[worktrees](./environments/git-worktrees.md) to give parallel coding chats separate
checkouts.

**Surface: Desktop app**

For local work, turn on **Prevent sleep while running** in settings so your Mac
stays awake. Use [Pets](./pets.md) or [system
notifications](./notifications.md) to see when a chat needs input
or is ready for review.

<a id="app-related-docs"></a>
<a id="cli-related-docs"></a>
<a id="ide-related-docs"></a>

## Related docs

- [Projects and chats](./projects.md)
- [Goal mode and prompting](./prompting.md#goal-mode)
- [Git worktrees](./environments/git-worktrees.md)

**Surface: Web**

<a id="web-related-docs"></a>

## Related docs

- [Projects and chats](./projects.md)
- [Scheduled tasks](./automations.md)
- [Sandbox and permissions](./sandboxing.md)