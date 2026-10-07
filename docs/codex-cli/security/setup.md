# Codex Security Cloud setup

> For the complete documentation index, see [llms.txt](https://learn.chatgpt.com/llms.txt). Markdown versions of documentation pages are available by appending `.md` to the page URL.

Use the Codex Security Cloud plugin to scan connected GitHub repositories,
review findings, and monitor new commits.

Codex Security Cloud runs scans in [Codex cloud](../cloud.md). For scans of a
  local repository in the desktop app or CLI, use the separate [Codex Security
  plugin](./plugin.md).

## 1. Install and open the plugin

1. Open **Plugins** in ChatGPT on the web or in the desktop app.
2. Search the plugin marketplace for **Codex Security Cloud**.
3. Install and enable the plugin, then open **Security Cloud** from your
   installed plugins or sidebar.

[Open plugin marketplace](https://chatgpt.com/plugins/plugin_connector_1p_6317a32dbf5c81919acd66de6722daf5)

If access is unavailable, check with your workspace administrator.

## 2. Connect GitHub

Confirm that [Codex cloud](../cloud.md) is set up for your workspace. In the
plugin, select **Scan**. If prompted, select **Connect GitHub** and grant
access to the repositories you want to scan.

If a repository is missing, check its GitHub connection and permissions.

## 3. Start a repository scan

1. In **New Scan**, choose the repository.
2. Review the environment. **Auto** creates an environment when you start.
   Use **Customize** to choose an existing environment. See [Codex cloud
   environments](../environments/cloud-environment.md) for setup details.
3. Under **Scan Method**, select **One-Time Scan**.
4. Select **Create**.

Open the scan in **Scans** to follow its progress and review its findings and
artifacts.

## 4. Review findings and available fixes

Open **Findings**. Use **Open findings** to review findings with a **New**,
**Triaged**, or **In Progress** status. Search the list or use **Filters** to
narrow the results. The **Severity and status** chart summarizes the matching
findings.

<figure className="not-prose my-8">

  <figcaption className="mt-3 text-sm text-secondary">
    Filter and review open findings. Repositories, findings, and counts are
    fictional and match the overview example.
  </figcaption>
</figure>

Select an issue to review its affected code, validation evidence, and
remediation guidance.

When a finding offers **Fix with Codex**, select it to generate a proposed
patch. Review the patch before selecting **Create draft pull request**.

## 5. Monitor new commits

To review changes as new commits arrive:

1. Select **Scan**, then choose the repository and review the environment.
2. Under **Scan Method**, select **Continuous Scanning**. Codex Security scans
   the repository's default branch.
3. Choose **Scan commit history from**. Longer windows provide more context,
   but the initial scan takes longer.
4. Optionally add threat model scoping guidance.
5. Select **Create**.

<figure className="not-prose my-8">

  <figcaption className="mt-3 text-sm text-secondary">
    Configure continuous scanning. The repository shown is fictional.
  </figcaption>
</figure>

To adjust monitoring, open **Repositories**, select the repository, and open
**Monitoring settings**. You can change the Cloud environment, choose how
many days of history to review, and pause or enable monitoring.
Select **Save** to apply changes.

Review and edit the generated threat model under **Project context**, then
select **Save**. See [Improving the threat model](./threat-model.md)
for guidance.

## Related docs

- [Codex Security](../security.md) gives the product overview.
- [Codex Security Cloud FAQ](./faq.md) covers common Cloud questions.
- [Improving the threat model](./threat-model.md) explains how to improve scan context and finding prioritization.