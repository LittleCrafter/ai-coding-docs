# ChatGPT usage limits and spend controls

> For the complete documentation index, see [llms.txt](https://learn.chatgpt.com/llms.txt). Markdown versions of documentation pages are available by appending `.md` to the page URL.

ChatGPT workspace usage limits and spend controls apply to eligible activity
under your workspace plan, which can include some Codex activity. They don't
cover all Codex usage or govern OpenAI API Platform billing.

For the complete administration model, see
[Roles and workspace permissions](./roles-and-workspace-permissions.md).

## Know when these controls apply

Review ChatGPT workspace usage controls when:

- The organization's agreement uses shared or purchased ChatGPT workspace
  credits.
- Eligible Codex activity can consume those credits.
- Administrators need user guardrails, workspace-level spend controls, or usage
  notifications supported by the current plan.

Usage controls don't configure feature entitlement or permissions, although
exhausted limits can pause access to eligible features. They don't affect
source-system permissions or govern Platform API usage or billing.

## Ultrafast mode

GPT-6 Astra Ultrafast is off by default in eligible Enterprise workspaces.
Workspace owners can enable it through
[workspace permissions](./roles-and-workspace-permissions.md).
Existing per-user spend limits apply to eligible Ultrafast usage. Review
those limits before enabling access because the higher usage rates can
consume a user's budget faster.

See [Ultrafast mode](../agent-configuration/speed.md#ultrafast-mode) for plan
eligibility and billing details.

## Use current procedures

- [Manage usage limits and overages in ChatGPT Enterprise and Edu](https://help.openai.com/en/articles/20001001)
- [Manage credits and spend controls in ChatGPT Business](https://help.openai.com/en/articles/20001155-managing-credits-and-spend-controls-in-chatgpt-business)

## Related docs

- [ChatGPT Work: usage and cost](./chatgpt-work-usage-and-cost.md)
- [Admin rollout guide](./admin-setup.md)
- [Governance](./governance.md)
- [Workspace analytics](./workspace-analytics.md)
- [Codex pricing](../pricing.md)