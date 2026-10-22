# Side question command (/btw)

Available on: Antigravity App, Antigravity CLI

Ask a quick contextual question without interrupting an in-progress agent turn or adding messages to your main conversation history.

## Overview

When you’re in the middle of a multi-step task, you might need a quick reminder about something the agent already discussed, such as a function signature it read earlier, a decision it made, or a command flag it used. Asking that question in the main chat adds extra turns to the conversation trajectory and consumes context window capacity on every subsequent turn.

The `/btw` command runs an ephemeral, single-turn side query in the background:

*   **Inherits your conversation context**: the side query is branched from your current conversation, so it can answer questions about anything already discussed in the active session.
*   **Answers without tools**: tools are disabled for the side query, so it can’t read files, run commands, or search your workspace. It answers from the conversation context and the model’s own knowledge in a single response.
*   **Ask while streaming**: you can invoke `/btw` even while the primary agent is actively generating a response, running tests, or executing long-running tools.
*   **No conversation history growth**: neither your `/btw` question nor its answer is added to the main conversation, so later turns don’t pay for it. The temporary branch is deleted once the answer arrives.

## Ask a side question

You can ask a side question across Antigravity surfaces.

### Antigravity App

Once a conversation is active (that is, after you’ve sent your first message), type `/btw` followed by your question in the composer:

```text
/btw Which file did you say defines the UserSession interface?
```

The answer opens in a floating **Side Question** panel above the composer and isn’t added to your conversation. From the panel you can:

*   Step through earlier side questions with the previous (`<`) and next (`>`) history controls, shown as `1/N`.
*   **Copy** the question and answer to your clipboard.
*   **Delete** the current side question.
*   **Minimize** the panel. Minimized side questions appear as an **N Side Question(s)** pill in the composer footer; select it to reopen the panel.

### Antigravity CLI

Type `/btw` followed by your question in the prompt box. If you haven’t started a conversation yet, the CLI creates one for you:

```text
/btw Which file did you say defines the UserSession interface?
```

The response appears in a collapsible `/btw` card above the prompt box while your main conversation continues uninterrupted. Only one `/btw` question can be in flight at a time; if you ask another before the first finishes, the CLI asks you to wait.

Note

`/btw` isn’t available in headless mode (`-p` or `--print`), because a one-shot run has no in-progress turn to ask alongside.

## Browse and manage `/btw` cards in the CLI

In the Antigravity CLI, `/btw` responses are stored in an ephemeral session history so you can revisit earlier side answers at any time during your conversation.

### Reopen previous `/btw` answers

To reopen the most recent `/btw` card without asking a new question, run `/btw` with no arguments:

```text
/btw
```

Note

If you haven’t asked any `/btw` questions in the current session yet, running bare `/btw` displays `Usage: /btw <question>`.

### Card navigation controls

When a `/btw` card is visible in the CLI, use the following keyboard shortcuts:

| Key | Action |
| :-- | :-- |
| Tab | Expand a truncated answer or collapse an expanded card. |
| ↑ / ↓ | Scroll up or down by one line inside an expanded card when the answer exceeds the viewport height. Otherwise, these keys keep their usual prompt-history behavior. |
| PgUp / PgDn | Scroll up or down by one page inside an expanded card. |
| ← / → | Cycle through previous and next `/btw` responses in the current session. |
| Esc | Dismiss the `/btw` card, or cancel an in-flight `/btw` generation. |
| Enter | Dismiss the `/btw` card when the prompt box is empty. If you’ve typed a prompt, Enter submits it as usual. |

## Copy a `/btw` response to the clipboard

In the Antigravity CLI, you can copy the most recent `/btw` answer directly to your system clipboard without copying the main agent’s last response.

Run the `/copy` command with the `btw` argument:

```text
/copy btw
```

The CLI copies the full Markdown text of the `/btw` answer that’s currently on screen (or the most recent answer if you’ve already dismissed the card), even if the card is collapsed or scrolled, and displays a confirmation message.

## Next steps

Explore related commands for managing your conversation context and workflow:

*   **[Context command (`/context`)](./context.md)**: visualize how your main conversation consumes the model’s context window.
*   **[Slash commands overview](https://antigravity.google/docs/slash-commands)**: browse all cross-surface slash commands in Google Antigravity.
*   **[CLI reference](../reference.md)**: view all available CLI slash commands and keyboard shortcuts.