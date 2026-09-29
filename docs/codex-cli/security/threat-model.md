# Improving the threat model

> For the complete documentation index, see [llms.txt](https://learn.chatgpt.com/llms.txt). Markdown versions of documentation pages are available by appending `.md` to the page URL.

Review and update the threat model for a repository monitored by Codex Security Cloud.

## What a threat model is

A threat model is a short security summary of how your repository works. Codex Security creates the first draft from the code and uses it to guide future commit scans and prioritize findings.

A useful threat model calls out:

- entry points and untrusted inputs
- trust boundaries and auth assumptions
- sensitive data paths or privileged actions
- the areas your team wants reviewed first

For example:

> Public API for account changes. Accepts JSON requests and file uploads. Uses an internal auth service for identity checks and writes billing changes through an internal service. Focus review on auth checks, upload parsing, and service-to-service trust boundaries.

## Improving and revisiting the threat model

Update the threat model when your architecture or priorities change, or when findings miss the areas you care about.

### Where to edit

1. Open the Codex Security Cloud plugin. See [Cloud setup](./setup.md)
   if you haven't installed it or configured commit monitoring.
2. Open **Repositories** and select the monitored repository.
3. Open **Monitoring settings**.
4. Under **Project context**, edit **Threat model**, then select **Save**.

Changes apply to future scans.

## Related docs

- [Codex Security Cloud setup](./setup.md) covers repository setup and findings review.
- [Codex Security](../security.md) gives the product overview.
- [Codex Security Cloud FAQ](./faq.md) covers common cloud questions.