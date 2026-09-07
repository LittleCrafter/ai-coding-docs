# Permissions Command (/permissions)

Manage your fine-grained agent permission rules interactively within the TUI.

## Overview

Antigravity CLI uses a fine-grained permissions engine to secure your workstation. While you can configure these rules manually in your settings file, the `/permissions` command opens an interactive **Permissions Manager** TUI panel to view, add, edit, and delete rules live.

For details on how the permission engine works, supported actions, and manual configuration, see the conceptual **[Permissions Guide](/docs/cli/permissions)**.

## Managing permissions interactively

To open the Permissions Manager:

1.  Type `/permissions` in the prompt box.
2.  Press Enter.

```
/permissions
```

### Navigation and controls

The Permissions Manager operates in three panels:

1.  **Scope Picker**: Select the configuration scope you want to edit:
    
    *   **Project**: Rules applying only to the active project (disabled if no project is open).
    *   **Shared**: Rules shared across all Antigravity products.
    *   **Global**: Global rules applying to all your sessions.
    
    Use ↑/↓ (or J/K) to navigate, Enter to select, and Esc to exit.
    
2.  **Rule Viewer**: View the rules configured for the selected scope.
    
    *   Switch between **allowlist**, **denylist**, and **asklist** tabs using ←/→ (or Tab).
    *   Scroll through the rules using ↑/↓ (or J/K).
    *   Press A to add a new rule.
    *   Press E (or Ctrl + G) to edit the highlighted rule.
    *   Press D (or Backspace) to delete the highlighted rule.
    *   Press Esc to return to the Scope Picker.
3.  **Add/Edit Rule**: Type or edit a rule in the input field.
    
    *   Rules must follow the `action(target)` format (e.g., `command(git)`).
    *   Press Enter to validate and save the rule.
    *   Press Esc to cancel.

* * *

## Step-by-step walkthrough

Here is how to view, add, edit, and delete rules live in the TUI.

### 1\. Selecting a scope and viewing rules

When you run `/permissions`, you first see the **Scope Picker**. Select **Global** to manage your global rules:

![Selecting Global Scope](../../assets/image/docs/cli/permissions-scope.png)

Press Enter to open the **Rule Viewer** for the selected scope. You can use ←/→ to switch between the **allow**, **deny**, and **ask** tabs:

![Global Rule Viewer](../../assets/image/docs/cli/permissions-viewer.png)

### 2\. Adding a permission rule

To allow the agent to run `git` commands automatically without prompting:

1.  In the Rule Viewer, press A. The **Add Rule** panel opens at the bottom:
    
    ![Add Rule Panel](../../assets/image/docs/cli/permissions-add.png)
    
2.  Type `command(git)` in the input field:
    
    ![Typing the Rule](../../assets/image/docs/cli/permissions-add-typed.png)
    
3.  Press Enter. The rule is validated and saved. You are returned to the Rule Viewer, and `command(git)` now appears in your allowlist:
    
    ![Rule Saved Successfully](../../assets/image/docs/cli/permissions-viewer-with-rule.png)
    

### 3\. Editing a permission rule

If you want to restrict the agent so it can only run `git diff` automatically, you can edit the rule:

1.  In the Rule Viewer, use ↑/↓ to highlight `command(git)`.
2.  Press E (or Ctrl + G). The input panel opens, prefilled with `command(git)`.
3.  Modify the text to `command(git diff)`.
4.  Press Enter to save. The old rule is replaced by the new one.

### 4\. Deleting a permission rule

To remove a rule and revert to prompting for those actions:

1.  In the Rule Viewer, highlight the rule you want to delete (e.g., `command(git diff)`).
2.  Press D (or Backspace).
3.  The rule is immediately removed from the list.

## Next steps

*   **[Permissions Guide](/docs/cli/permissions)**: Learn about the security model, action types, and wildcard matching.
*   **[Sandbox & Security](/docs/cli/sandbox)**: Configure the native OS container for running commands.
*   **[CLI Reference](/docs/cli/reference)**: See all available slash commands and keybindings.