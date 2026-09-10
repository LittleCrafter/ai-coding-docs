# Codex cloud

> For the complete documentation index, see [llms.txt](https://learn.chatgpt.com/llms.txt). Markdown versions of documentation pages are available by appending `.md` to the page URL.

## Run coding tasks in parallel cloud environments

Run tasks in isolated cloud environments, work in parallel, and start work from the web, GitHub, GitLab, Linear, or Slack.

> Illustration: Codex cloud chat composer and chat list with interactive archiving

### Start here

- [Open Codex cloud](https://chatgpt.com/codex)
- [Set up Codex cloud](#getting-started)

### Why use Codex cloud

- **Run work in parallel:** Give longer tasks dedicated environments and let them continue while you work on something else.
- **Reproduce the environment:** Configure the dependencies, tools, variables, and setup steps each repository needs.
- **Review before you merge:** Inspect the summary and diff, request a follow-up, or open a pull request when the result is ready.

## Getting started

**Set up Codex cloud.**

Connect GitHub or GitLab, create an environment, and start your first cloud chat.

### 1. Open Codex and sign in

Go to [Codex](https://chatgpt.com/codex) and sign in with your ChatGPT account.

### 2. Connect GitHub or GitLab

Connect GitHub or GitLab (Beta) when prompted. For GitHub, choose the repositories Codex can access; for GitLab, select a project when you create the environment. For GitLab setup, webhook permissions, and merge request reviews, see [Use Codex with GitLab (Beta)](./third-party/gitlab.md).

### 3. Create an environment

Open [environment settings](https://chatgpt.com/codex/settings/environments) and create an environment for the repository you selected. Configure any dependencies, tools, environment variables, or secrets the task needs.

For configuration details, see [Cloud environments](./environments/cloud-environment.md).

### 4. Start your first task

Return to [Codex](https://chatgpt.com/codex), choose your environment, and describe the result you want. You can watch the task logs or let the task run in the background.

### 5. Review the result

Review the summary and diff. Ask Codex to make follow-up changes, or open a pull request when the work is ready.

### Next steps

- [Customize the cloud environment](./environments/cloud-environment.md)
- [Configure agent internet access](./cloud/internet-access.md)
- [Use Codex with GitHub](./third-party/github.md)
- [Use Codex with GitLab (Beta)](./third-party/gitlab.md)
- [Use Codex in Linear](./third-party/linear.md)
- [Use Codex in Slack](./third-party/slack.md)

## See what Codex cloud can do

Give each task the environment it needs, then review the result on your schedule.

- [Delegate several tasks](./environments/cloud-environment.md): Start work in parallel and return as each task reaches a reviewable result.
- [Build a reproducible environment](./environments/cloud-environment.md): Configure the dependencies, tools, variables, and setup steps a repository needs.
- [Delegate from your integrations](./developers.md): Start work in Codex cloud from GitHub pull requests, GitLab merge requests and issues, Linear issues, or Slack channels and threads.

## Use Codex cloud when…

- [Work needs to run in the background](./environments/cloud-environment.md): Delegate a longer task and return when it is ready.
- [You want to compare several attempts](./environments/cloud-environment.md): Run tasks in parallel without tying up your local machine.
- [Work starts in GitHub, GitLab, Linear, or Slack](./developers.md): Use integrations to hand off work without leaving the pull request, merge request, issue, channel, or thread.
- [You are away from your development machine](./environments/cloud-environment.md): Start and review work from the web or Codex CLI.