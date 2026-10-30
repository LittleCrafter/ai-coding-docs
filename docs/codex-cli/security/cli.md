# Codex Security CLI quickstart

> For the complete documentation index, see [llms.txt](https://learn.chatgpt.com/llms.txt). Markdown versions of documentation pages are available by appending `.md` to the page URL.

Run a standard scan of a local repository with the standalone Codex Security
CLI. This quickstart ends with a saved report you can review and revisit.
For scans inside a Codex conversation, use the [Codex Security
plugin](./plugin.md).

## Check the prerequisites

Use Node.js 24 or 26, or Node.js 22 starting with 22.13.0.
You also need Python 3.10 or later.
If you use Python 3.10, install `tomli`. Some cybersecurity requests and
protected findings require [Trusted Access for Cyber](https://chatgpt.com/cyber).

The CLI runs with your operating-system permissions and doesn't pause for
approval.
Scan processes can inherit your environment, so remove unrelated credentials
before starting. See [Local scan
permissions](./cli/reference.md#local-scan-permissions).

## Set up and verify the CLI

Install the public package globally, then check its version:

```bash
npm install -g @openai/codex-security
codex-security --version
```

The package provides the `codex-security` command and its `cs` alias. Ensure
npm's global executable directory is on your `PATH`.

To run without a global installation, use `npx`:

```bash
npx @openai/codex-security --version
```

The examples below use `npx @openai/codex-security`. After a global
installation, you can use `codex-security` instead.

The command prints the installed package version. Use `info --json` to check
the bundled plugin version, or `--help` to list commands.

## Sign in

Sign in with your ChatGPT account:

```bash
npx @openai/codex-security login
```

On a machine without a browser, add `--device-auth` if your workspace allows
it, and follow the displayed sign-in instructions. If device authentication
is disabled, use the [SSH login instructions](https://github.com/openai/codex-security/blob/main/sdk/typescript/docs/cli.md#remote-login-with-ssh-forwarding).
Use `--auth chatgpt` in the scan commands below to select
that sign-in even when your environment also contains an API key.

For API keys and other providers, see [Select scan
authentication](./cli/reference.md#select-scan-authentication).
For Amazon Bedrock, use [AWS credentials and model
access](./cli/reference.md#use-amazon-bedrock) instead of a ChatGPT
sign-in or OpenAI API key.

## Prepare a scan

Replace these paths with your repository and a new results directory outside
its Git worktree:

```bash
REPOSITORY=/path/to/repository
SCAN_DIR=/path/outside/repository/codex-security-results
```

Results can include source excerpts and vulnerability details. Choose a private
location. If you omit `--output-dir`, the CLI uses its persistent state directory.

Check the target and output location:

```bash
npx @openai/codex-security scan "$REPOSITORY" \
  --auth chatgpt --output-dir "$SCAN_DIR" --dry-run
```

A successful dry run confirms the local inputs. It doesn't start a scan, load
credentials, or check the plugin's Python interpreter, so it doesn't establish
that authentication and runtime setup will succeed.

## Run your first scan

Remove `--dry-run` to start the scan:

```bash
npx @openai/codex-security scan "$REPOSITORY" \
  --auth chatgpt --output-dir "$SCAN_DIR"
```

An interactive terminal shows a live dashboard. Non-interactive terminals show progress
lines. Add `--headless` to use progress lines in an interactive terminal too.
The dashboard and saved logs can contain source code or credentials. Review
them before sharing.

When the scan finishes, stderr includes the report path, finding count, and
elapsed time. For example:

```text
  REPORT    /path/outside/repository/codex-security-results/report.md

  FINDINGS  2 (2 confirmed this scan; 0 previously found; 1 high, 1 medium)
  SCOPE     repository: .
  ELAPSED   42s
  RESULTS   /path/outside/repository/codex-security-results
```

By default, the severity of a finding doesn't cause a scan to fail. For
machine-readable stdout, add `--json`. To make findings fail a CI check, set a
[severity policy](./cli/ci.md#choose-a-severity-policy).

## Review the results

Open `report.md` from the results directory. Confirm the target and revision,
then review the findings. For the recorded status and scope, look at
`scan.status` and `scan.scope` in `scan-manifest.json`.

A completed scan exits with `0` unless findings meet a configured severity
threshold, which returns `1`. Exit `0` doesn't establish that every file was
reviewed. Input, execution, result-integrity, or required-output failures return `2`. The
[CLI reference](./cli/reference.md#exit-codes-and-signals) explains
the exit codes.

For each finding, check the affected code, attacker prerequisites, validation
evidence, and remaining uncertainty. A source-based finding doesn't necessarily
include a successful runtime reproduction. Select a finding for remediation
only after its evidence supports the claimed issue.

Keep the scan directory together when sharing or archiving it. It contains
`scan-manifest.json` and `findings.json` alongside the report
and supporting artifacts. See [Scan
artifacts](./cli/reference.md#scan-artifacts) for the full layout.

### Export the saved threat model

Standard, Deep, and Diff scans save their threat model with the results.
Export it as Markdown without signing in or making another model call:

```bash
npx @openai/codex-security export "$SCAN_DIR" \
  --artifact threat-model --output "$SCAN_DIR/exports/threatmodel.md"
```

If no threat model was saved, `export` returns an error. See the [export
reference](./cli/reference.md#codex-security-export) to select saved
scans and other output formats.

## Revisit a saved scan

List scans for the repository:

```bash
npx @openai/codex-security scans list "$REPOSITORY"
```

Copy a scan ID from the results:

```bash
npx @openai/codex-security scans show SCAN_ID
```

After a complete interactive scan with findings, the CLI also offers a finding
browser. Review the evidence there before choosing a fix. For saved findings,
use the [validate and patch
commands](./cli/reference.md#codex-security-validate-and-codex-security-patch).

## Choose the next scan

| Goal                                             | Guide                                                                                    |
| ------------------------------------------------ | ---------------------------------------------------------------------------------------- |
| Scan selected paths or a diff                    | [Select the scan target](./cli/reference.md#select-the-scan-target)           |
| Scan components of one repository in parallel    | [Component scans](./cli/reference.md#codex-security-scan-components)          |
| Use a test script to validate candidate findings | [Custom validation](./cli/reference.md#validate-findings-in-your-environment) |
| Use deep scans or limit their runtime            | [Configure deep scans](./cli/reference.md#configure-deep-scans)               |
| Supply architecture or security policies         | [Add security context](./cli/reference.md#add-security-context)               |
| Change the model or reasoning effort             | [Configure the runtime](./cli/reference.md#configure-the-runtime)             |
| Set an estimated cost limit                      | [Output and policy options](./cli/reference.md#set-output-and-policy-options) |
| Scan multiple repositories                       | [Bulk scans](./cli/bulk-scans.md)                                             |
| Scan GitHub pull requests or run scheduled scans | [GitHub Actions guide](./cli/ci/github.md)                                    |
| Choose another CI provider                       | [CI/CD overview](./cli/ci.md)                                                 |

For authentication problems, repeat-scan differences, or false-positive
feedback, see the [CLI FAQ](./cli/faq.md).