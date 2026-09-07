# Prompting & interaction

Master primary interaction patterns, multiline composition workflows, session interruption controls, and terminal media pasting.

## The prompt box

Antigravity CLI features a sticky prompt panel positioned at the bottom of your terminal screen. This panel handles standard user entries, multiline scripts, and direct media pasting.

```
───────────────────────────────────────────────────────────────────────────
> Describe your next engineering task here...
───────────────────────────────────────────────────────────────────────────
```

### Submitting prompts

To initiate an agent turn, type your instruction into the prompt panel and press `Enter`. The agent immediately analyzes your current directory workspace, reads required configurations, and begins formulating an execution plan.

### Interrupting active sessions

If the agent initiates an undesired task or loops during command execution, press `Esc` to immediately halt the session.

Note

**Universal Escape**: The `Esc` key acts as a global escape hatch. Pressing `Esc` instantly cancels any active agent turn, closes overlay panels, and returns focus to a clean prompt box.

## Multiline composition

For complex directives, structured test scenarios, or multi-paragraph instructions, use our built-in multiline features.

### Shorthand newline insertions

*   **Standard**: Press `Shift+Enter` or `ctrl+j` to insert a clean newline within your active prompt window without submitting.
*   **macOS Terminal Fallback**: If using Apple Terminal (which does not forward `Shift+Enter` by default), press `Option+Enter`. Ensure you check **Use Option as Meta key** in your Terminal Preferences profile.
*   **Universal Slash Escape**: Type a trailing backslash `\` at the end of your active line and press `Enter`. The CLI automatically removes the backslash and inserts a newline.

### Editing prompts in `$EDITOR`

To draft or edit extensive prompt structures in your primary development editor:

1.  Press `ctrl+g` inside the empty prompt panel.
2.  The CLI launches your system’s default text editor (such as `vim`, `nano`, or `code`, configured via `/config` or your environment’s `$EDITOR` variable).
3.  Draft your multi-line instruction inside the temporary editor buffer.
4.  Save and exit the editor. The CLI automatically imports the edited buffer directly back into the terminal prompt.

## Attaching media

Antigravity CLI supports pasting rich media formats directly from your system clipboard. Press `ctrl+v` (or native terminal paste) inside the prompt panel to attach screenshot mockups or video recordings.

### Supported file types

*   **Images**: PNG, JPEG, GIF, WebP, BMP, TIFF, and SVG.
*   **Videos**: MP4, MOV, WebM, and AVI.

## Next steps

After mastering interaction patterns, explore how the agent presents actions and requests verification:

*   **[Reviewing Artifacts](/docs/cli/artifacts)**: Learn to inspect and manage file edits, plans, and test executions.
*   **[Managing Conversations](/docs/cli/conversations)**: Resume prior threads and fork active sessions.
*   **[Background Tasks & Subagents](/docs/cli/subagents)**: Monitor asynchronous background agents.