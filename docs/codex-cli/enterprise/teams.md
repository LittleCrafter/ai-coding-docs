# Set up and manage teams and Team Tasks

> For the complete documentation index, see [llms.txt](https://learn.chatgpt.com/llms.txt). Markdown versions of documentation pages are available by appending `.md` to the page URL.

Teams give people in ChatGPT a shared place to organize work and collaborate. With Team Tasks, members can set up work to run on a schedule or when a specific event occurs, such as preparing a weekly report or summarizing new project updates.

To get started, learn how to [set up a team](./teams.md#set-up-a-team) and [create a Team Task](./teams.md#create-a-team-task).

Enterprise admins control who can create teams and manage Team Tasks through two permissions: [Create teams and Create and manage team automations](./roles-and-workspace-permissions.md#set-the-workspace-default-then-create-targeted-custom-roles). Admins can also make [workspace connections](./shared-connections.md#create-a-workspace-connection) available to teams. Each team’s service account and configured connections determine which external accounts its tasks use.

For more on team membership and tasks, see [Teams in ChatGPT](https://help.openai.com/articles/20001541) and [Creating and managing team tasks in ChatGPT](https://help.openai.com/articles/20001540) in the Help Center.

<span
  id="plan-the-teams-access-and-responsibilities"
  data-localization-body-anchor
/>

## How teams and Team Tasks work

[Workspace connections](./shared-connections.md) let Team Tasks use company-managed app accounts so each team member doesn't need to connect their own account.

Teams can include people within a department or across functions who share a goal. A team in ChatGPT is separate from a [workspace group created manually or synced through SCIM](./groups-and-provisioning.md#compare-membership-sources).

Here are examples of scheduled and event-triggered Team Tasks:

| **Team**         | **Who works together**                                                                        | **Example Team Task**                                                                                           |
| ---------------- | --------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------- |
| Product launch   | Product, marketing, and support teams preparing a release.                                    | When a message arrives in the launch Slack channel, summarize launch progress, milestone changes, and blockers. |
| Customer success | Account managers and customer success teams supporting customers.                             | Each Monday, summarize the previous week's customer updates, follow-ups and open questions.                     |
| Sales            | Sales, solutions engineers, and customer success teams closing deals and onboarding customers | When a deal closes, prepare an onboarding brief with customer goals, commitments, and open questions.           |
| Marketing        | Project leads and contributors responsible for a shared project.                              | Each morning, summarize project progress, blockers, and upcoming deadlines.                                     |

Team Tasks run in the cloud with the team's service account and configured app connections.

### Before you begin

Before setting up a team or its tasks, a workspace owner should enable the following permissions for the intended users through workspace settings or custom roles:

- [Create teams](./roles-and-workspace-permissions.md#set-the-workspace-default-then-create-targeted-custom-roles): Required to create a team

- [Create and manage team tasks](./roles-and-workspace-permissions.md#set-the-workspace-default-then-create-targeted-custom-roles): Required to create or edit team tasks

See [Roles and workspace permissions](./roles-and-workspace-permissions.md#set-the-workspace-default-then-create-targeted-custom-roles).

- **Workspace admin:** Set up and authorize approved workspace connections, and choose who can find and use them. Check the external account’s data and action permissions. See [Workspace connections](./shared-connections.md#create-a-workspace-connection).

- **Team owner:** After creating the team, select the available connections it needs where your permissions allow. Before scheduling a Team Task, confirm which external account each connection uses.

<span
  id="2-configure-membership-and-assign-maintainers"
  data-localization-body-anchor
/>

### Set up a team

1. **Create the team**. In the intended workspace, open Settings &gt; Teams and select Create team. Enter a Name and optional Description, then select Create.

2. **Review access and invite colleagues**. Before inviting colleagues, review access to earlier runs and generated files; individual tasks and runs cannot have separate access restrictions. Select Invite, search by Name or email, and select Add member or Add members. Members can invite coworkers and remove non-owner members. Same-workspace join links do not require owner approval.

3. **Add the team’s connections.** Workspace connections use centrally managed accounts; team connections share an individually connected account with the team. As team owner, choose a connection you’re allowed to use. Review its data and action permissions, and complete any required sign-in before unattended work. Team ownership doesn’t grant workspace admin permissions. See [Workspace connections](./shared-connections.md#create-a-workspace-connection) for admin setup.

<span
  id="create-and-validate-the-first-team-task"
  data-localization-body-anchor
/>

<span
  id="2-review-the-schedule-actions-and-audience"
  data-localization-body-anchor
/>

<span
  id="3-validate-access-and-the-first-result"
  data-localization-body-anchor
/>

### Create a Team Task

1. Open **Scheduled** &gt; **+ New Task**. Select the **Team toggle** and the team that will own the task.

2. Choose a **Trigger**. For **Schedule**, check the timing and time zone. For a supported event trigger, check its conditions and required connection.

3. In **Instructions**, describe the goal and expected output. Include success criteria and guardrails. Link task-specific sources, and review shared instructions if the team has a designated [Space](../space.md). Tasks do not inherit the creator’s personal memories, custom instructions, or chat history.

4. Review **Plugins** and **Advanced** settings, including **Model**. Choose a model available to the team; this may differ from your personal account. Select **Create**.

5. Select **Run now** and inspect the result in **Previous runs**. Use **Edit** to change instructions or settings.

<span
  id="review-membership-connections-and-destinations"
  data-localization-body-anchor
/>

<span
  id="handle-departures-and-stop-work-when-needed"
  data-localization-body-anchor
/>

## Teams and Team Tasks FAQ

<details>
<summary>Can team membership be imported or kept in sync with workspace groups or Slack/Microsoft Teams channels?</summary>

No. ChatGPT team membership is separate from workspace groups and Slack or Microsoft Teams channels. It cannot be imported or synced; add and remove members in ChatGPT.

</details>

<details>
<summary>Who can create a team, change its membership, and manage its tasks?</summary>

[Workspace permissions](./roles-and-workspace-permissions.md#set-the-workspace-default-then-create-targeted-custom-roles) control team creation and task creation or updates. The creator becomes team owner without gaining workspace admin rights. Members can invite coworkers and remove non-owner members; same-workspace join links need no owner approval.

Only the team owner can delete the team. Workspace admins manage approved connections and who can use them.

</details>

<details>
<summary>Are these workspace controls enforced across every supported team and task creation or editing entry point?</summary>

Yes. Create teams governs team creation; Create and manage team automations governs task creation and updates across supported entry points. Team membership and connection permissions still apply.

</details>

<details>
<summary>What access does someone gain when they join a team?</summary>

New members can see all earlier runs and generated files; individual tasks and runs cannot have separate access restrictions. [Pages and Spaces retain their own sharing permissions](../space/collaboration.md#share-a-page-or-space). Joining a team, you’ll inherit any pages and spaces that are shared with the team. Joining does not share personal chats or connections. Workspace members opening a join link can see the team’s name and member list before joining.

</details>

<details>
<summary>How can workspace admins review activity without joining a team?</summary>

Admins can review activity through the [Compliance API](./compliance-api.md#get-started) and restrict access by role.

</details>

<details>
<summary>Whose account does a Team Task use?</summary>

Team Tasks use the team’s service account and [configured app connections](./shared-connections.md#understand-the-connected-accounts-permissions). A connection’s account determines its data and actions, which may differ from the creator’s or editor’s personal access. See [Connecting and managing app accounts](https://help.openai.com/en/articles/20001494-connecting-and-managing-app-accounts-in-chatgpt).

</details>

<details>
<summary>How do plugins and connections work together?</summary>

[Team plugins and connections](./shared-connections.md#connections-for-teams-and-workflows) serve different purposes: plugins provide tools or skills; connections supply app access. Members need not connect the same account individually.

</details>

<details>
<summary>Can workspace connections expose information beyond a member&#x27;s personal access?</summary>

Yes. Connected accounts may access information a member’s own account cannot. Review team membership alongside each connection’s resource access.

</details>

<details>
<summary>Can Team Tasks write to connected systems?</summary>

Yes, if the tool and connection allow it—for example, posting to Slack. Unattended runs cannot complete a new app sign-in and remain subject to action-approval requirements.

</details>

<details>
<summary>What happens when a task creator or team owner leaves?</summary>

Authorized teammates can edit, pause, or resume shared tasks. Before [offboarding a creator or owner](./user-lifecycle.md#remove-a-departing-employee), review team ownership and required connections.

Team-owned tasks are designed to persist after the creator leaves, but required connections may lose access.

Owners must transfer ownership before leaving. Connections the new owner cannot access become disabled for the entire team.

</details>

<details>
<summary>What happens to active and queued runs when a task is paused or deleted?</summary>

Pausing prevents future scheduled and event-triggered runs. Neither pausing nor deleting a task should be relied on to interrupt an active run.

</details>

<details>
<summary>What team and task activity can admins audit?</summary>

The team’s Activity view keeps track of changes. Authorized members can inspect individual runs and results.

Use supported [Compliance API](./compliance-api.md#confirm-the-administration-boundaries) records to investigate team activity. Confirm which team, task, and connection records are available before relying on them for an audit.

Use the current [Admin API reference](https://chatgpt.com/public/admin/api-reference) for each event’s exact fields and supported coverage.

</details>

<details>
<summary>How are Team Tasks billed?</summary>

Team Tasks use workspace credits. Team spending limits are separate from user limits.

</details>