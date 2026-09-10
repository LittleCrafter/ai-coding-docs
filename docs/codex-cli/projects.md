# Projects and chats

> For the complete documentation index, see [llms.txt](https://learn.chatgpt.com/llms.txt). Markdown versions of documentation pages are available by appending `.md` to the page URL.

Use a project to organize related chats and give ChatGPT the context it needs.
The **Projects** view in the ChatGPT desktop app includes ChatGPT projects and
local projects that connect to folders on your computer.

## Choose a project or start without one

Create a project when work will continue over time, produce more than one
output, or depend on the same files and sources. Start a chat without a project
when the work is self-contained and doesn't need shared project context.

Use a project to keep related chats, files, instructions, and sources together.
The same project can contain chats started with Chat or ChatGPT Work.

## Choose a project or chat without one

Create a project when work will continue over time, produce more than one
output, or depend on the same files and sources. Start a chat without a project
when the work is self-contained and doesn't need shared project context.

Each project has a **Chats** section that lists project chats and a **Sources**
section for uploaded files and connected context. Project instructions apply
across its chats. A ChatGPT project doesn't provide direct access to a folder on
your computer, so upload or connect the sources you want ChatGPT to use.

With either option, start a new chat from the project to use its shared files and
instructions, then return to it under **Chats**.

Codex CLI treats the directory where you start it as the project for the chat.
Run `codex` from the directory you want Codex to work in, or pass
`--cd <directory>` (`-C`) to set it explicitly. The CLI doesn't expose the
ChatGPT Projects view.

The IDE extension treats the folder or workspace open in your IDE as the local
project. In a multi-root workspace, select the workspace root for the chat. The
extension doesn't expose the ChatGPT Projects view from the web or desktop app.

<a id="work-in-a-project"></a>

## Work in a project

The **Projects** view brings ChatGPT projects and local projects into one place.
ChatGPT projects carry project files and context across related chats. A local
project gives chats access to one or more folders on your computer, such as a
collection of source files or a codebase.

Start a separate chat for each distinct outcome so its messages and results stay
focused while the project keeps related work organized.

  

> Illustration: ChatGPT desktop app showing multiple projects in the sidebar and chats in the main pane

## Work in a project

A ChatGPT project gives its chats access to the same uploaded files, project
instructions, and connected sources. Use Chat for a quick chat or
ChatGPT Work for a larger deliverable; both appear as chats in the project's
**Chats** section. Start a separate chat for each distinct outcome so its
messages and results stay focused while the project preserves shared context.

## Work in a project directory

Start Codex from the directory that should provide the chat's file context. Use
`/new` to start a separate chat for each distinct outcome. Use `/resume` while
Codex is open, or run `codex resume`, to continue a saved chat.

The chat keeps its transcript and recorded working directory, while Codex reads
files from the current working tree. Keep durable project guidance in
`AGENTS.md` or checked-in documentation so it is available to future chats.

## Work in a workspace

Open the folder or workspace that should provide the chat's file context. Start
a new chat for each distinct outcome, then select it from **Recent chats** to
continue it. Chats in the same project can work with the same files, while each
chat keeps its own transcript.

The current selection and open files provide context for the current turn. Keep
durable project guidance in `AGENTS.md` or checked-in documentation so it is
available to future chats.

<a id="manage-project-threads"></a>
<a id="organize-projects-and-chats"></a>

<a id="organize-projects-and-tasks"></a>

## Organize projects and chats

Keep active work visible and move finished work out of the way:

- **Pin a project** to keep it near the top of the sidebar. You can also pin it
  from the Projects view.
- **Pin a chat** when you return to it often, even if newer chats appear in the
  project.
- **Rename a chat** with a short title that describes its outcome, such as “Q3
  launch brief” or “Checkout accessibility review.”
- **Search projects** from the Projects view. Open **Search chats** from the
  sidebar to find a past chat when you remember a phrase or branch name but not
  the title. Search chats doesn't have a default shortcut, but you can assign
  one under **Settings > Keyboard Shortcuts**.
- **Archive a chat** when you finish the work. From a project's menu, select
  **Archive chats** to archive its chats together.

Pinning doesn't add context or change what ChatGPT can access. It only changes
where the project or chat appears in the sidebar.

Restore archived chats from **Settings > Archived chats**.

<a id="organize-projects-and-tasks-1"></a>

## Organize projects and chats

Keep active work visible and move finished work out of the way:

- **Pin a project** to keep it near the top of the sidebar. You can also pin it
  from the Projects view.
- **Pin a chat** when you return to it often, even if newer chats appear in the
  project.
- **Rename a chat** with a short title that describes its outcome, such as “Q3
  launch brief” or “Checkout accessibility review.”
- **Search projects** from the Projects view. Search past chats with
  <kbd>Cmd</kbd>/<kbd>Ctrl</kbd>+<kbd>K</kbd> when you remember a phrase or
  branch name but not the title.
- **Archive a chat** when you finish the work.

Pinning doesn't add context or change what ChatGPT can access. It only changes
where the project or chat appears in the sidebar.

Restore archived chats from **Settings > Data Controls > Archived chats**.

<a id="use-local-projects-for-folders-and-codebases"></a>

## Use local projects for folders and codebases

Add a local project when ChatGPT needs to read or change files on your computer.
Projects don’t need a folder, but you can attach folders as needed.

To add or change folders, open the project's menu and select **Edit project**.
Select **Add folder** to attach multiple folders. ChatGPT can read and change files
in every attached folder. To change the default working directory, point to a
folder and select **Make primary**.

New chats start in the primary folder. Codex also uses that folder as the
default for Git operations and automatic discovery of `AGENTS.md`, skills, and
`config.toml`. Secondary folders remain available for file search, reading, and
editing, but Codex doesn't automatically discover those project files from
secondary folders.

Use multiple folders when related work lives in different places, like an app and
its documentation or a website and its backend. Create separate projects for
unrelated work or when each chat should access only one part of a repository.
This keeps the working context focused. Remote projects currently support one
folder.

Use [local environments](./environments/local-environment.md) to define setup
actions and common commands for a project. The [review
pane](./code-review.md) can show changes across repositories
attached to the same project. Pull request and
[worktree](./environments/git-worktrees.md) actions target the primary
repository. When you start a chat in a worktree, the other folders remain
attached.

Projects and worktrees organize work, but the [sandbox](./sandboxing.md)
enforces what local commands can read, change, or access over the network.

<a id="start-without-a-project"></a>

<a id="start-a-task-without-a-project"></a>

## Start a chat without a project

Select **New chat** when the work is self-contained and doesn't need shared
project files, instructions, or folder access. Create a project first when
several chats will depend on the same context.

<a id="start-a-task-without-a-project-1"></a>

## Start a chat without a project

Start a chat from ChatGPT Home when the chat doesn't need shared project
files, instructions, or sources. You can use Chat or ChatGPT Work; on the web,
both create chats.

If the work grows, move it into a project and use clear chat names for each
outcome. A project can hold parallel chats for research, drafting, review, and
follow-up without mixing every message into one context.

<a id="start-a-chat"></a>
<a id="start-a-standalone-chat"></a>

<a id="use-quick-chat-for-a-quick-conversation"></a>

## Use Quick chat for a quick question

Quick chat opens an ordinary ChatGPT chat. ChatGPT chats don't appear in the
Codex sidebar, which contains your Codex chats and projects.

Point to **New chat**, then select the **Quick chat** icon on its right. You can
also press

<kbd>Cmd+Option+N</kbd> on macOS or <kbd>Ctrl+Alt+N</kbd> on Windows and Linux.
From **New chat**, you can open an existing ChatGPT chat and add it to a Codex
chat.

## Bring in other tools and context

- Attach files or [image inputs](./image-inputs.md) directly to a chat
  when they apply only to that request.
- Install [plugins](./plugins.md) to bring in context and actions from other
  services.
- Configure [MCP](./extend/mcp.md) servers when your organization or developer setup
  exposes tools through Model Context Protocol.
- Use [memories](./customization/memories.md), where available, to carry useful context from
  past work into future chats.

- Pass [image inputs](./image-inputs.md) to a chat when visual context applies
  only to that request.
- Install [plugins](./plugins.md) to bring in context and actions from other
  services.
- Configure [MCP](./extend/mcp.md) servers when your organization or developer setup
  exposes tools through Model Context Protocol.
- Use [memories](./customization/memories.md), where available, to carry useful context from
  past work into future chats.

- Reference open files or select code in the editor to add context for the
  current turn.
- Configure [MCP](./extend/mcp.md) servers when your organization or developer setup
  exposes tools through Model Context Protocol.
- Use [memories](./customization/memories.md) from the connected Codex host, where
  available, to carry useful context into future chats.

- Add files and connected sources to the project's **Sources** section when they
  should be available across its chats.
- Attach files or [image inputs](./image-inputs.md) directly to a chat when
  they apply only to that chat.
- In ChatGPT Work, install [plugins](./plugins.md) to bring in context and
  actions from other services.
- Use [memories](./customization/memories.md), where available, to carry useful context from
  past work into future chats.

## Next steps

- [Learn how to write and refine prompts](./prompting.md)
- [Learn how to use ChatGPT](./use-chatgpt.md)
- [Continue long-running work](./long-running-work.md)