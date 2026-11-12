# Codex Security

> For the complete documentation index, see [llms.txt](https://learn.chatgpt.com/llms.txt). Markdown versions of documentation pages are available by appending `.md` to the page URL.

Codex Security reviews code for vulnerabilities and reports evidence you can
use to investigate and fix them. Choose how to run it based on where your code
lives and how you want to review the results.

The **Overview** in Daybreak Defense Factory shows proposed fixes and tracks [open and fixed findings](./security/findings-and-fixes.md) across your repositories.

> Illustration: Daybreak Overview with proposed fixes across three repositories, open findings by severity, and the daily trend for new and fixed findings.

## Choose where to start

| Use                      | When you want to                                                                              | Start here                                          |
| ------------------------ | --------------------------------------------------------------------------------------------- | --------------------------------------------------- |
| Daybreak Defense Factory | Scan a GitHub repository, review findings from other tools, and propose fixes with your team. | [Set up Daybreak](./security/setup.md)            |
| Codex Security plugin    | Scan a local repository in Codex and work through findings interactively.                     | [Run your first local scan](./security/plugin.md) |
| Codex Security CLI       | Run repeatable terminal scans or add checks to CI.                                            | [CLI quickstart](./security/cli.md)               |
| Codex Security SDK       | Run scans and handle results in an application or developer tool.                             | [SDK guide](./security/sdk.md)                    |

## Choose the next task

After a local scan, review its scope and findings before deciding what to do next.

| Task                                                  | Guide                                                               |
| ----------------------------------------------------- | ------------------------------------------------------------------- |
| Focus a scan on a service or add security context     | [Run a security scan](./security/plugin/scans.md)                 |
| Run repeated reviews of the same repository or folder | [Run a deep scan](./security/plugin/deep-scans.md)                |
| Check a pull request, commit, or local diff           | [Review code changes](./security/plugin/code-changes.md)          |
| Assess findings from another scanner or issue tracker | [Triage a backlog](./security/plugin/triage-backlog.md)           |
| Generate a patch and check whether it fixes the issue | [Fix and verify findings](./security/plugin/fix-findings.md)      |
| Share results or assign remediation work              | [Export and track findings](./security/plugin/export-findings.md) |

For automation, use the CLI guides to [scan repositories in
bulk](./security/cli/bulk-scans.md) or [run scans in
CI](./security/cli/ci.md). Look up commands and defaults in the
[CLI reference](./security/cli/reference.md).

Codex Security scans application code. For permissions and sandbox controls
that govern Codex itself, see [Agent approvals and
security](./agent-approvals-security.md).