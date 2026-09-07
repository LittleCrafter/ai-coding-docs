# Managing AI Credits & Quotas

The Antigravity CLI integrates with your subscription to monitor and manage your AI Premium credits and usage quotas.

For a detailed explanation of baseline quotas, how credits are consumed, and plan eligibility, please refer to the main **[Plans](/docs/plans)** page.

## Quota Tracking

You can monitor your active quota and credit consumption directly inside the CLI:

*   **Statusline Indicator**: The right side of the CLI statusline displays your remaining credit count (e.g., `AI Credits: 42`).
*   **Low Quota Alert**: When your remaining AI credits drop below the warning threshold, the statusline indicator highlights to warn you that your limits are near.

## Slash Commands & Managing Balance

You can query your credits or buy additional quota directly from the CLI:

*   **Query Balance**: Run the **[AI Credits Command](/docs/cli/commands/credits)** to open the dedicated credits panel. This panel displays your detailed credit usage statistics.
*   **Managing Credits**: You can easily purchase AI credits or upgrade your subscription, which opens a panel containing direct pricing and subscription portal links.

## Settings Configuration

To control when and how your AI credits are used, you can toggle credit settings in your `settings.json` file:

```
{
    "useG1Credits": true
}
```

*   **Use AI Credits Option**: Run `/config` or `/settings` to open the CLI settings panel. Set the **Use G1 Credits** field to **on** to allow the CLI to use your personal credits when plan quotas are exhausted, or set it to **off** to restrict fallback billing. (To learn more, see the **[Plans](/docs/plans#overages)** overages section).

## See also

*   **[AI Credits Command](/docs/cli/commands/credits)**: View and manage your credits interactively in the TUI.
*   **[Model Quotas Command](/docs/cli/commands/usage)**: Monitor your model-specific API quotas.