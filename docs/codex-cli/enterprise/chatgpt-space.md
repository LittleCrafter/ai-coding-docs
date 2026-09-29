# Manage ChatGPT Space and shared pages

> For the complete documentation index, see [llms.txt](https://learn.chatgpt.com/llms.txt). Markdown versions of documentation pages are available by appending `.md` to the page URL.

<span
  id="does-turning-off-library-file-sharing-remove-existing-access"
  data-localization-body-anchor
/>

<span
  id="how-should-we-handle-malicious-incoming-content"
  data-localization-body-anchor
/>

<span
  id="how-can-we-reduce-data-exfiltration-risk"
  data-localization-body-anchor
/>

<span
  id="is-enterprise-data-used-to-train-models"
  data-localization-body-anchor
/>

<span
  id="what-if-information-was-shared-unintentionally"
  data-localization-body-anchor
/>

## What is ChatGPT Space?

ChatGPT Space (formerly Library) brings together pages, uploaded files, and shared content so people and agents can collaborate. Teams can draft documents, [edit pages](../space/pages.md#revise-the-content), or [ask ChatGPT for revisions](../space/agents.md#start-with-a-bounded-request).

For product guidance, see the [ChatGPT Space guide](../space.md) and [Help Center guidance on Library files](https://help.openai.com/en/articles/20001052-using-library-to-manage-files-in-chatgpt).

## Enterprise sharing controls

Use [Share Library files and folders](https://help.openai.com/en/articles/10128477-chatgpt-enterprise-and-edu-release-notes) to manage sharing at the [workspace and role level](./roles-and-workspace-permissions.md#set-the-workspace-default-then-create-targeted-custom-roles). Disabling sharing blocks new shares and permission changes, but existing shared access remains. Users can still create and view private content.

An Admin role alone does not grant [sensitive compliance access](https://help.openai.com/en/articles/20001067-data-access-for-your-managed-chatgpt-account). [Compliance API permissions](./compliance-api.md#get-started) are required to [export or delete eligible saved Library files](https://help.openai.com/en/articles/20001052-using-library-to-manage-files-in-chatgpt) through supported endpoints.

<span
  id="what-if-a-file-will-not-save-or-upload"
  data-localization-body-anchor
/>

## Help users create and share pages

Users can [create a page](../space/getting-started.md#draft-your-first-page) and [share it with people or available workspace teams](../space/collaboration.md#share-a-page-or-space), choosing view or edit access.

Sharing a page keeps private chats and saved memory private. Private details added to the page are visible to its collaborators.

Uploads follow the page’s permissions. Linked source files retain their own permissions. Content copied or summarized onto a page is visible to its collaborators.

## Plugins and connected accounts

[Plugins](../plugins.md#overview) can provide apps, skills, or both. Installing a plugin does not authorize its apps.

Set [app availability, role access, and allowed actions](./apps-and-connectors.md#step-2-manage-capabilities). The connected account’s permissions determine what it can access; [approval settings](https://help.openai.com/en/articles/20001495-managing-app-permissions-in-chatgpt) determine when ChatGPT asks before an action.

## Governance and data protection

OpenAI does not train on ChatGPT Enterprise data by default. Saved Library files follow the workspace’s [retention policy](https://help.openai.com/en/articles/8983778-chat-and-file-retention-in-chatgpt).

Limit sharing and app actions, and require approval for consequential actions where supported. [Read-only queries](https://developers.openai.com/api/docs/mcp#risks-and-safety) can still disclose data to external services. Pages, files, and tool results may contain [prompt injections](https://openai.com/safety/prompt-injections/) that redirect ChatGPT or disclose information. Safeguards reduce, but do not eliminate, this risk.

## FAQ

<details>
<summary>Can a shared project use personal Space files?</summary>

Sharing a project removes personal Space files from its sources without deleting the originals. Files uploaded directly to the project remain available to members. See [Projects in ChatGPT](https://help.openai.com/en/articles/10169521-projects-in-chatgpt).

</details>

<details>
<summary>What happens when content is deleted?</summary>

Deleting a page or Space moves it and its nested pages to Trash. Files saved separately in Space remain when a chat or project is deleted. See [Library file management](https://help.openai.com/en/articles/20001052-using-library-to-manage-files-in-chatgpt) for saved-file deletion details.

</details>

<details>
<summary>What happens when someone leaves the workspace?</summary>

[Removing a member](https://help.openai.com/en/articles/8266418-data-retention-when-a-member-is-removed-from-a-workspace) 
immediately revokes workspace access; retained Enterprise chats and files
follow workspace retention policy. 
[Disconnecting an app](https://help.openai.com/en/articles/20001494-connecting-and-managing-app-accounts-in-chatgpt) 
stops future access through that connection but does not automatically delete
saved content.

</details>