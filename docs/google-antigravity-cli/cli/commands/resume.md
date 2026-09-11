# Resume Command (/resume)

Browse, search, and resume past conversation threads, or recover your last session instantly from the command line.

## Overview

Antigravity CLI allows you to maintain multiple ongoing development threads. The `/resume` command opens an interactive **Session Picker** TUI panel to browse and load your history. You can also resume sessions directly from your host terminal using command-line flags.

* * *

## Interactive Session Picker

To open the Session Picker inside the TUI:

1.  Type `/resume` (or aliases `/switch`, `/conversation`) in the prompt box.
2.  Press Enter.

```
/resume
```

### 1\. Navigating and Searching Conversations

The Session Picker displays a list of past conversations sorted by recency (newest first).

*   **Search**: Start typing to instantly filter conversations by their title, preview text, or unique ID.
*   **Navigate**: Use ↑/↓ to scroll through the filtered list.
*   **Page**: Use ←/→ to page backward and forward through older history blocks.
*   **Select**: Highlight your target session and press Enter to load it.
*   **Exit**: Press Esc to close the picker and return to the active prompt.

![Navigating Conversations](../../assets/image/docs/cli/resume-navigate.png)

### 2\. Renaming a Conversation

To keep your history organized, you can rename conversations directly within the picker:

1.  Use ↑/↓ to highlight the conversation you want to rename.
2.  Press F2. An input field opens at the bottom of the panel, prefilled with the current title.
3.  Type the new name and press Enter to save, or Esc to cancel.

![Renaming a Conversation](../../assets/image/docs/cli/resume-rename.png)

### 3\. Deleting a Conversation

To clean up obsolete threads:

1.  Highlight the target conversation in the list.
2.  Press Ctrl + Delete. A confirmation prompt appears.
3.  Press Enter (or Y) to confirm deletion, or Esc (or N) to cancel.

![Deleting a Conversation](../../assets/image/docs/cli/resume-delete.png)

### 4\. Importing from Antigravity 2.0

You can import and resume active threads initiated in the Antigravity 2.0 desktop application:

1.  With the Session Picker open, press Tab to switch from the **CLI** tab to the **Antigravity** tab.
2.  Highlight the desktop conversation you wish to import.
3.  Press Enter. A confirmation prompt `[Import this? (y/n)]` appears.
4.  Press Enter (or Y) to confirm. The CLI clones the history, context, and tool trajectories into your terminal session.

![Importing from Antigravity 2.0](../../assets/image/docs/cli/resume-antigravity.png)

* * *

## Command-Line Shortcuts

You can bypass the TUI picker and resume sessions directly when launching `agy` from your host shell.

### Quick Resume Last Session (`-c` / `--continue`)

To instantly resume the single most recent conversation associated with your active workspace:

```
agy -c
```

_(Alternative: `agy --continue`)_

### Resume Specific Session (`--conversation`)

To load a specific conversation directly by its unique ID:

```
agy --conversation <conversation-id>
```

* * *

## Under the Hood: The Session Cache

When you use the `-c` / `--continue` flag, the CLI resolves the target session using a local workspace-keyed cache.

### The Cache File

*   **Location**: `~/.gemini/antigravity-cli/cache/last_conversations.json`
*   **Format**: A JSON map associating absolute workspace directory paths with their most recently active conversation ID:
    
    ```
    {
        "/usr/local/google/home/username/Develop/my-project": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
        "/usr/local/google/home/username/Develop/another-repo": "f9e8d7c6-b5a4-3210-fedc-ba9876543210"
    }
    ```
    

### Resolution Workflow

1.  **Launch**: You run `agy -c` from `/path/to/workspace`.
2.  **Lookup**: The CLI reads `last_conversations.json` and looks up the key `/path/to/workspace`.
3.  **Verification**: If an ID is found, the CLI queries the backend to verify the conversation still exists.
4.  **Load**:
    *   If verified, it loads the session.
    *   If the conversation was deleted or the key is missing, it starts a fresh session for that workspace.

* * *

## See also

*   **[Managing Conversations](../conversations.md)**: Learn about workspace scoping and branching with `/fork`.
*   **[CLI Reference](../reference.md)**: See all available slash commands and default keybindings.
*   **[Settings & Keybindings](../settings.md)**: Configure rendering modes and customize keyboard shortcuts.