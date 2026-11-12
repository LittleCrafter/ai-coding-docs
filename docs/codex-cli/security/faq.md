# Daybreak Defense Factory FAQ

> For the complete documentation index, see [llms.txt](https://learn.chatgpt.com/llms.txt). Markdown versions of documentation pages are available by appending `.md` to the page URL.

[Set up Daybreak Defense Factory](./setup.md) walks you through your first cloud scan. Local scans have separate
[plugin](./plugin.md) and [CLI](./cli.md) guides.

## Billing

### How are cloud scans billed?

Repository scans and continuous monitoring are billed by token usage at your
plan’s rates, in credits or USD. Your plan’s included usage allowance does
not cover these scans.

Repository scans and continuous monitoring draw from the same credit balance.
In a workspace, everyone shares that balance. Free scanning credits don’t
expire. When they run out, further scans are billed at your plan’s rates.

### Where can I see scan costs?

Open **Usage** to compare costs by repository over a date range. **Scan cost**
shows the cost before credits and exemptions. **Billable remainder** shows
the amount remaining after credits and exemptions apply.

## Scanning

### Does the project need to be built for scanning?

Daybreak can analyze source without a successful build. Validation may
need dependencies or a working build to reproduce an issue. Configure those
requirements in the [Codex cloud
environment](../environments/cloud-environment.md).

If validation can't run, inspect what the finding establishes from source and
what still depends on runtime or deployment behavior.

### What languages are supported?

Daybreak analyzes source across languages. Results depend on the model's
ability to reason about the language and framework, and on the available
repository context. A successful scan doesn't imply equal coverage across
languages or components. Check the report for the scope actually reviewed.

### Which scan should I use?

Use a repository scan to look for issues already in the code, continuous
monitoring to check new commits on the default branch, or a scheduled scan for
recurring repository reviews. You can check changes before they merge with
[PR reviews](./security-review.md#enable-pr-reviews-in-daybreak).

### Can I pause commit monitoring?

Yes. Open **Repositories**, select the repository, and open **Continuous scanning settings**.
Turn off **Continuous monitoring** and save your changes. You can turn it back on in the same settings.

### Can I edit the threat model?

Yes. Open **Threat model** in the monitored repository and update it when the
architecture, deployment, or security assumptions change. Your edits apply to
future scans. The [threat model guide](./threat-model.md) explains what to include.

### Can I scan code hosted on GitLab?

Cloud scans use a connected GitHub repository. For GitLab, scan a [local
checkout](./setup.md#scan-your-local-checkout) or run the
[Codex Security CLI in GitLab CI/CD](./cli/ci/gitlab.md).

## Findings and validation

### What does validation establish?

Read the evidence attached to the particular finding. Source analysis can
establish a vulnerable code path. Execution evidence can show that a specific
reproducer or test demonstrated the issue.

A finding's recorded status and severity help organize review. Use the
underlying evidence and prerequisites to decide whether it applies to your
system and what to fix.

### What happens if validation fails?

Inspect the attempted validation and any available logs. A failed reproducer
can mean the issue doesn't apply, but it can also mean the environment or test
was unsuitable. Resolve the stated gap before dismissing the finding or
claiming that it was reproduced.

### What if the scan reports no findings?

Confirm that the scan completed and reviewed the intended repository and
revision. Read any recorded limits or unfinished work. A scan that reports no
findings can still miss vulnerabilities.

## Fixes

### Does Daybreak apply patches automatically?

Daybreak saves a proposed patch for review. **Fix with Codex** lets you
discuss or refine it. **Create PR** opens a draft pull request on GitHub.
See [Review a proposed fix](./findings-and-fixes.md#review-a-proposed-fix).

### How do I know whether a patch fixed the issue?

Review the patch's validation evidence, including whether the original issue
still reproduces and whether legitimate behavior still works. If validation
wasn't completed, keep that uncertainty with the finding. A proposed patch,
draft pull request, or status change alone doesn't verify a fix.