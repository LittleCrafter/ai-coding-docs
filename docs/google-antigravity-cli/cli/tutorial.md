# Antigravity CLI Tutorial

Learn how to launch Antigravity CLI, collaborate with an autonomous local agent, review generated files, and execute terminal test commands.

## Overview

This guide walks you through a rapid onboarding exercise. You will direct an autonomous agent to create a Python utility script, review the changes, and verify its execution.

## Step-by-step

1.  **Create a clean project directory and launch the Antigravity TUI**
    
    ```
    mkdir agy-demo && cd agy-demo
    agy
    ```
    
    Note
    
    **First Launch**: If running `agy` for the first time, follow the terminal instructions to complete silent authentication. See [Installation & Auth](/docs/cli/install) for troubleshooting details.
    
2.  **Prompt the agent to generate a Python scraping script**
    
    Type the following instruction in the prompt box at the bottom of your screen and press Enter:
    
    ```
    Write a simple python script to fetch web page text
    ```
    
    The agent reads the workspace, determines that no files exist, and formulates a plan to create a script. You will see real-time updates as the agent performs reasoning and schedules actions.
    
3.  **Open the artifact review screen to inspect the proposed code**
    
    Once the agent finishes generating the file, a notification appears. Press Ctrl + R to enter the **Artifact Review** screen.
    
    *   Navigate to the newly created `main.py` using ↑/↓.
    *   Review the complete file content and diff.
    *   Press Y to approve the creation of `main.py`.
    *   Press Esc to close the review panel and return to the primary prompt.
4.  **Execute a test command with the agent to verify the output**
    
    Direct the agent to run the Python script to verify its behavior. Type the following command in the prompt box and press Enter:
    
    ```
    Run the python script and show me the output
    ```
    
    The agent proposes to run `python3 main.py`. Press Y to confirm and execute the command. The agent runs the script locally and streams the standard output directly into your terminal screen.
    
5.  **Exit the Antigravity session**
    
    Once you complete your task, press Ctrl + D (or type `/exit`) in the prompt box to close the TUI and restore your original shell session.
    

## Next steps

Now that you have executed your first agent-assisted workflow, learn how to configure the CLI and master core concepts:

*   **[Installation & Auth](/docs/cli/install)**: Detailed instructions on installing `agy` and setting up SSH profiles.
*   **[Prompting & Interaction](/docs/cli/prompting)**: Best practices for multiline inputs, pasting media files, and active interrupt controls.
*   **[Reviewing Artifacts](/docs/cli/artifacts)**: Deep dive into the “Trust through Transparency” architectural pattern.