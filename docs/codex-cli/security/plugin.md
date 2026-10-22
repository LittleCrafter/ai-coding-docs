# Codex Security plugin quickstart

> For the complete documentation index, see [llms.txt](https://learn.chatgpt.com/llms.txt). Markdown versions of documentation pages are available by appending `.md` to the page URL.

Install the Codex Security plugin, run a standard scan of a local repository,
and review its findings. The scan leaves your source unchanged and saves a
report with evidence and remediation guidance.

This page covers the Codex Security plugin in the desktop app or Codex CLI. To
  scan a connected GitHub repository in Codex cloud, install the separate
  **Codex Security Cloud** plugin from the plugin marketplace. See [Cloud
  setup](./setup.md).

## Install the plugin

**Surface: Desktop app**

1. Open [Codex in the ChatGPT desktop app](../app.md).
2. Open **Plugins**, search for **Codex Security**, or use the button below:

     [Install the Codex Security plugin](https://developers.openai.comcodex://plugins/install/codex-security?marketplace=openai-curated)

3. Confirm the plugin is enabled, then open **Security** in the sidebar.

If plugin installation shows "Disabled by admin" in a managed workspace,
ask your workspace owner to [check plugin access](../enterprise/apps-and-connectors.md#troubleshoot-disabled-by-admin).
For a personal account, see [plugin and app troubleshooting](https://help.openai.com/en/articles/20001497-troubleshooting-plugins-apps-in-chatgpt).

**Surface: CLI**

1. In your terminal, go to the repository you want to assess and start Codex:

```bash
   codex
```

2. Enter `/plugins`, search for **Codex Security**, and select **Install
   plugin**.
3. Enter `/new` to start a new chat for the repository.

If **Security** doesn't appear in the desktop-app sidebar, confirm that
  **Codex** is selected and the plugin is enabled. Update the app and plugin if
  needed, and check whether your workspace administrator allows the plugin.

## Run your first scan

For the best scan quality, use `gpt-5.6-sol`
with `xhigh` reasoning effort.

**Surface: Desktop app**

<figure className="not-prose my-8">

  <figcaption className="mt-3 text-sm text-secondary">
    Choose a repository and configure a new security scan before you start it.
  </figcaption>
</figure>

1. Open the scan setup

   Select **Security** in the sidebar, open **Scans**, and select **+ Scan**.

2. Choose the codebase and scan area

   Select an existing repository or use another folder. Choose **Codebase**,
   leave **Deep scan** off, and select the entire repository or one folder.
   Confirm that the branch and revision identify the code you intended to scan.

3. Add security context

   Choose the model and reasoning effort. Open **Additional context** only when
   you need to describe an attack vector, security-sensitive area, or
   repository detail that should guide the review.

   <figure className="not-prose my-6">

     <figcaption className="mt-3 text-sm text-secondary">
       Turn on additional context to describe attack vectors, focus areas, and
       relevant security guidance.
     </figcaption>
   </figure>

4. Start the scan

   Select **Start scan** and follow the scan phases in the Security workbench.
   Select **View activity** to inspect the Codex task that performs the scan.

5. Review the result

   Open the completed scan to inspect findings, coverage, and available report
   artifacts. Use **Findings** to review issues across scans or **Repositories**
   to inspect a repository's scan history.

   <figure className="not-prose my-6">

     <figcaption className="mt-3 text-sm text-secondary">
       Review scan results, findings, and coverage in the Security workbench.
     </figcaption>
   </figure>

**Surface: CLI**

1. Ask for a standard scan

   Send this prompt in the new chat:

```text
   Run a Codex Security scan on this repository.
```

2. Let the scan finish

   Codex runs the scan in the terminal without opening a setup workspace. Keep
   the task running until Codex reports that it is complete. If Codex identifies
   a configuration limitation, review the limitation and the exact proposed
   change before you approve a configuration update.

3. Review the result

   Review the summary in the terminal, then open the generated `report.md` for
   the complete result.

## Interpret the result

Check the target and revision first. Then read which areas were reviewed and
which were deferred. A completed scan can still have coverage gaps. A review
that reports no findings hasn't necessarily ruled out every vulnerability.

Open a finding and read its source evidence, attacker prerequisites, validation,
and remaining uncertainty. Validation can use source analysis without running
a reproducer. Use the recorded method and evidence to decide whether the issue
applies to your system.

## What the scan creates

In the desktop app, completed scans remain in **Scans**. In Codex CLI, use the
scan directory reported in the conversation. Open `report.md` for the readable
result. Detailed vulnerability reports under `findings/` and design proposals
under `hardening/` are optional outputs you can request.

The directory also contains `scan-manifest.json`, `findings.json`, and
`coverage.json` for tools and automation. Keep it together when sharing or
archiving results so the report's links continue to work.

## Choose your next workflow

- [Configure scope and security context](./plugin/scans.md) for the
  next scan, or [review a code change](./plugin/code-changes.md).
- [Fix and verify a finding](./plugin/fix-findings.md) after you
  accept its evidence, or [track it in an issue](./plugin/export-findings.md).

For other scan modes and workflows, return to the [Codex Security
overview](../security.md).