> ## Documentation Index
> Fetch the complete documentation index at: https://code.claude.com/docs/llms.txt
> Use this file to discover all available pages before exploring further.

# Deploy managed settings

> Deploy managed settings to every developer's machine: delivery mechanisms per OS, how Claude Code combines managed sources, and how to verify enforcement.

Managed settings are the settings your organization deploys to every developer's machine. Claude Code applies them above every other level, so no user, project, local, or `--settings` value overrides them, apart from a few [security-sensitive exceptions](./settings.md#exceptions-to-managed-settings-precedence) where a stricter value from a lower level still counts.

This page is for the administrator who deploys managed settings or debugs why one isn't applying. To decide what to enforce, start with the [Decide what to enforce](./admin-setup.md#decide-what-to-enforce) table. For the claude.ai console path, see [Server-managed settings](./server-managed-settings.md). For which file a developer's own values go in, see [Settings](./settings.md).

## Deploy a managed settings file

This is the quickest way to put a policy on each machine: a `managed-settings.json` file. If you haven't picked how to deliver managed settings yet, or your devices are under MDM or developers run cloud sessions, read [Choose a delivery mechanism](#choose-a-delivery-mechanism) first.

1. **Write managed-settings.json**

   Write a `managed-settings.json` that holds the keys you've decided to enforce, in the same JSON shape as `settings.json`. The [Decide what to enforce](./admin-setup.md#decide-what-to-enforce) table lists the keys behind each control, and each entry in the [settings reference](./settings-reference.md) says whether a managed source can set it. This file blocks two file reads, turns off bypass mode, and makes Claude Code ignore permission rules from user, project, and local files and from `--allowedTools`:

   ```json managed-settings.json theme={null}
   {
     "permissions": {
       "deny": [
         "Read(./.env)",
         "Read(./secrets/**)"
       ],
       "disableBypassPermissionsMode": "disable"
     },
     "allowManagedPermissionRulesOnly": true
   }
   ```

   For a fuller example that shows the shape of more managed keys, including the login method, models, MCP servers, and marketplaces, see [An organization's managed settings](./settings-example.md#an-organizations-managed-settings).
2. **Place the file on each machine**

   Save the file as `managed-settings.json` in the system directory for the operating system, using whatever tooling already places files on your fleet:

   * **macOS**: `/Library/Application Support/ClaudeCode/managed-settings.json`
   * **Linux and WSL**: `/etc/claude-code/managed-settings.json`
   * **Windows**: `C:\Program Files\ClaudeCode\managed-settings.json`
3. **Confirm the policy applied**

   On one machine, run `/status` inside Claude Code. The `Setting sources` line shows `Enterprise managed settings (file)`. Roll out to the rest of the fleet after that; [Check that a policy is in force](#check-that-a-policy-is-in-force) covers what to look at when the line is missing.

<a id="managed-settings-delivery"></a>

<a id="delivery-mechanisms"></a>

## Choose a delivery mechanism

The file in the steps above is one of four ways to get managed settings onto a machine. Every mechanism carries the same policy keys as a `settings.json` file, so the [settings reference](./settings-reference.md) applies to all of them. A few keys are tied to particular sources, and each entry's Scope line says which:

* **Delivery controls**: [`policyHelper`](./settings-reference.md#policyhelper), [`wslInheritsWindowsSettings`](./settings-reference.md#wslinheritswindowssettings), and [`managedSourcesBehavior`](./settings-reference.md#managedsourcesbehavior)
* **Gateway login keys**: [`forceLoginGatewayUrl`](./settings-reference.md#forcelogingatewayurl) and the `"gateway"` value of [`forceLoginMethod`](./settings-reference.md#forceloginmethod)

A managed settings file, an MDM profile, or the claude.ai console applies one policy to everyone it reaches. To give one group of developers a different policy, deploy a different file or profile to that group; the claude.ai console [can't target a group yet](./server-managed-settings.md#current-limitations), while a self-hosted [Claude apps gateway](./claude-apps-gateway.md) delivers managed settings per IdP group.

When more than one mechanism delivers a policy to the same machine, Claude Code by default uses one and ignores the others. [How Claude Code combines managed sources](#how-claude-code-combines-managed-sources) gives the order and the opt-in that applies every source.

The MDM and file rows are together called endpoint-managed settings, because the policy is stored on the developer's device, as opposed to the server-managed row, where Claude Code fetches it.

Pick a mechanism by how you already manage devices, using the table below.

| Mechanism                                              | How you deliver it                                                                                                                                                                                                | When Claude Code reads it                                                                                                                                                                                                                | Use it when                                                                                    |
| :----------------------------------------------------- | :---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | :--------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | :--------------------------------------------------------------------------------------------- |
| [Server-managed settings](./server-managed-settings.md) | In the claude.ai admin console, or on a self-hosted [Claude apps gateway](./claude-apps-gateway.md)                                                                                                                | Fetched at startup and polled hourly; see [changes that need approval](#where-and-when-a-policy-applies)                                                                                                                                 | You want one place to change policy for a claude.ai organization without touching each machine |
| MDM or OS-level policy                                 | As a macOS configuration profile or a Windows `HKLM` registry value, through Jamf, Intune, Group Policy, or a similar tool; see [where each mechanism stores the policy](#where-each-mechanism-stores-the-policy) | Read at startup and checked for changes every 30 minutes                                                                                                                                                                                 | You already manage devices with MDM or Group Policy                                            |
| File-based                                             | As `managed-settings.json` in a system directory on each machine; see [where each mechanism stores the policy](#where-each-mechanism-stores-the-policy)                                                           | Read at startup and reloaded when a file changes                                                                                                                                                                                         | Machines without MDM, Linux hosts, or images you build yourself                                |
| HKCU registry, Windows and WSL                         | As a Windows `HKCU` registry value; see [where each mechanism stores the policy](#where-each-mechanism-stores-the-policy)                                                                                         | Read at startup and checked for changes every 30 minutes; Claude Code uses it only when no other managed source delivers a policy key and no [host-supplied parent settings](#let-an-embedding-host-add-policy) supply a restrictive key | You can't write the machine-level `HKLM` key                                                   |

Starter templates for Jamf, Iru, Intune, and Group Policy are in the [MDM examples repository](https://github.com/anthropics/claude-code/tree/main/examples/mdm).

For managed MCP servers, which you deploy alongside any of these through `managed-mcp.json` or provide through the [`managedMcpServers`](./settings-reference.md#managedmcpservers) key, see [Managed MCP configuration](./managed-mcp.md).

### Where and when a policy applies

A deployed policy reaches the developer's sessions as follows:

* **Surfaces**: on the developer's machine, the terminal, the VS Code and JetBrains extensions, the desktop app's Code tab, and [Agent SDK](./agent-sdk/typescript.md) sessions read all of these sources. Agent SDK sessions load managed settings even when `settingSources` excludes the user, project, and local files.
* **Cloud sessions**: a session in an Anthropic-hosted environment doesn't read a device's MDM profile or file, so policy for it has to come from server-managed settings. A session in a [self-hosted environment](./self-hosted-environments.md) also reads the managed settings file in its runner image, by default only when server-managed settings deliver no policy key, apart from the [keys Claude Code reads from every admin source](#keys-read-from-every-admin-source). [How Claude Code combines managed sources](#how-claude-code-combines-managed-sources) covers the opt-in that applies both.
* **Cowork sessions**: [Cowork](https://claude.com/docs/cowork/overview) in the Claude Desktop app runs its sessions on Claude Code. In a Cowork session, Claude Code never fetches server-managed settings from the claude.ai admin console, even when the user signs in with a Team or Enterprise account, so which policy applies depends on where the session runs:

  * **On the user's machine**: by default, Claude Code in a Cowork session reads the MDM or OS-level policy and the managed settings file on that device, so deploy policy there.
  * **In a full VM sandbox**: when your Claude Desktop managed configuration sets [`requireCoworkFullVmSandbox`](https://claude.com/docs/third-party/claude-desktop/configuration#requirecoworkfullvmsandbox), Claude Code runs inside a virtual machine where the device's MDM policy and managed settings file aren't present.
  * **Remote Cowork sessions**: these run on Anthropic-managed VMs, where Claude Code has no device policy to read.

  The [surface coverage](./model-config.md#surface-coverage) table compares Cowork with the other surfaces.
* **Running sessions**: most changes reach a running session on the schedule in the [delivery mechanism table](#choose-a-delivery-mechanism), without a restart.
  * Changes to [`forceRemoteSettingsRefresh`](./settings-reference.md#forceremotesettingsrefresh), [`requiredMinimumVersion`](./settings-reference.md#requiredminimumversion), and [some user-editable keys](./settings.md#when-edits-take-effect) take effect at the next session start.
  * A new or changed [`policyHelper`](./settings-reference.md#policyhelper) entry takes effect at the next launch. If server-managed settings shadow the helper at that launch, the helper runs as soon as a fetch reports those settings removed.
* **Changes that need approval**: apart from the [updates that wait for the next launch](./server-managed-settings.md#fetch-and-caching-behavior), a server-managed change to a setting that [needs approval](./server-managed-settings.md#security-approval-dialogs), such as a hook or an `env` variable, waits for the developer to accept the dialog in an interactive session, and applies for the current run in a session an IDE extension or the Agent SDK hosts. Other server-managed changes apply on the next poll.
* **Long-lived sessions**: a session left open for weeks can still lag a rollout. [`requiredMinimumVersion`](./settings-reference.md#requiredminimumversion) blocks an outdated binary from starting and doesn't end a session that's already running.

<a id="format-the-policy-for-each-platform"></a>

### Where each mechanism stores the policy

The keys are the same everywhere, but each mechanism stores them in a different place and shape:

* **Server-managed**: Anthropic's servers, or your gateway, hold the policy. Claude Code keeps a local cache that it applies at startup and [replaces on each successful fetch](./server-managed-settings.md#security-considerations).
* **macOS configuration profile**: the `com.anthropic.claudecode` managed preferences domain. Use the same top-level keys as `managed-settings.json`, with nested settings as dictionaries and lists as plist arrays.
* **Windows HKLM registry**: the JSON as a `REG_SZ` or `REG_EXPAND_SZ` value named `Settings` under `HKLM\SOFTWARE\Policies\ClaudeCode`.
* **File-based**: `managed-settings.json`, an optional `managed-settings.d/` directory, and `managed-mcp.json` in the system directory: `/Library/Application Support/ClaudeCode/` on macOS, `/etc/claude-code/` on Linux and WSL, and `C:\Program Files\ClaudeCode\` on Windows. Claude Code doesn't read the legacy Windows path `C:\ProgramData\ClaudeCode\managed-settings.json`.
* **Windows HKCU registry**: the same `Settings` value under `HKCU\SOFTWARE\Policies\ClaudeCode`.

### Split a file-based policy across teams

If several teams own parts of one policy, put each part in its own file in `managed-settings.d/`, next to `managed-settings.json` in the same system directory, instead of editing one shared file.

Claude Code merges `managed-settings.json` first, then every `*.json` file in the directory in alphabetical order. Name the files with numeric prefixes to control the order, such as `10-telemetry.json` and `20-security.json`. Claude Code ignores hidden files and files that don't end in `.json`.

When two files set the same key, Claude Code combines them by these rules:

* **Single values**, such as `"model": "opus"` or `"cleanupPeriodDays": 7`: the later file's value replaces the earlier one
* **Lists**, such as `permissions.deny` or `sandbox.network.allowedDomains`: the two lists combine, with duplicates removed
* **Nested blocks**, such as `env` or `sandbox`: the two blocks merge key by key, and each key inside follows these same rules
* **`fallbackModel`**: the later chain replaces the earlier one whole
* **[`extraKnownMarketplaces`](./settings-reference.md#extraknownmarketplaces) and [`managedMcpServers`](./settings-reference.md#managedmcpservers)**: a later entry with the same name replaces the earlier one whole
* **[`modelPicker`](./settings-reference.md#modelpicker)**: the later lineup replaces the earlier one whole

<a id="precedence-within-the-managed-tier"></a>

<a id="which-managed-source-claude-code-uses"></a>

## How Claude Code combines managed sources

When your organization delivers more than one managed source to the same machine, the [`managedSourcesBehavior`](./settings-reference.md#managedsourcesbehavior) key decides what Claude Code does with the others:

* **`"first-wins"`, the default**: Claude Code uses the highest-ranked source that delivers at least one policy key and ignores the rest rather than merging them, apart from the few keys in [Keys read from every admin source](#keys-read-from-every-admin-source). Claude Code shows no warning for the sources it skips; `/status` [names the source it used and the ones it skipped](#read-the-source-in-/status).
* **`"merge"`**: Claude Code applies every admin source that delivers a policy key and combines them by kind of key: on most keys the higher-ranked source's value applies, lists union, and locks take the strictest value. [Compose every managed source](#compose-every-managed-source) says where to set the key and how each kind of key combines. Requires Claude Code v2.1.242 or later.

Both settings rank the sources the same way. Two terms recur in this section:

* **Policy key**: any settings key other than the two control keys, [`wslInheritsWindowsSettings`](./settings-reference.md#wslinheritswindowssettings) and [`managedSourcesBehavior`](./settings-reference.md#managedsourcesbehavior). A managed settings file or MDM policy that contains only those doesn't count, and Claude Code moves on to the next source.
* **Admin source**: one of the first three sources below. The HKCU registry is user-writable and isn't one.

Claude Code checks the sources in this order, highest priority first:

1. Remote settings, delivered from claude.ai as [server-managed settings](./server-managed-settings.md) or by a [Claude apps gateway](./claude-apps-gateway.md). Claude Code fetches this source only when the session authenticates to Anthropic's API directly with an [eligible login or key](./server-managed-settings.md#platform-availability), or signs in to a gateway with `/login`. On other providers, or when `ANTHROPIC_BASE_URL` points somewhere other than Anthropic's API, it starts at the next source
2. MDM or OS-level policies: the macOS plist or the HKLM registry key
3. Managed settings files, `managed-settings.d/*.json` and `managed-settings.json` merged together
4. The HKCU registry, on Windows, and on WSL once the HKLM registry or the Windows managed settings file turns [`wslInheritsWindowsSettings`](./settings-reference.md#wslinheritswindowssettings) on and the HKCU value also sets it. Claude Code reads it only when no source above it delivers a policy key and no [host-supplied parent settings](#let-an-embedding-host-add-policy) supply a restrictive key

This diagram shows the ranking, with examples of the cross-source keys Claude Code reads from the first three sources under either setting:

<img src="media/images/managed-source-precedence.svg" alt="Diagram showing the four managed settings sources ranked from remote settings at the top through MDM, managed settings files, and the HKCU registry at the bottom. By default the first source with a policy key supplies the policy and the rest are skipped; with managedSourcesBehavior set to merge, every admin source with a policy key contributes, combined by kind of key, and the HKCU registry stays out. A side panel shows that cross-source keys such as the sandbox locks, forceRemoteSettingsRefresh, and the per-variable env merge are read from every admin source, which excludes the HKCU registry." width="680" height="330" />

<img src="media/images/managed-source-precedence-dark.svg" alt="Diagram showing the four managed settings sources ranked from remote settings at the top through MDM, managed settings files, and the HKCU registry at the bottom. By default the first source with a policy key supplies the policy and the rest are skipped; with managedSourcesBehavior set to merge, every admin source with a policy key contributes, combined by kind of key, and the HKCU registry stays out. A side panel shows that cross-source keys such as the sandbox locks, forceRemoteSettingsRefresh, and the per-variable env merge are read from every admin source, which excludes the HKCU registry." width="680" height="330" />

### Keys read from every admin source

Under the default `"first-wins"` setting, Claude Code reads most keys only from the [source it selected](#how-claude-code-combines-managed-sources), and ignores a value in a lower-ranked source even when the selected source leaves that key unset.

A few keys work differently. Claude Code reads them from every admin source, so a lower-ranked MDM policy or managed settings file can still set them when the selected source doesn't. Claude Code leaves the user-writable HKCU registry out of that scan; when HKCU is the only source and no host supplies parent settings, HKCU applies like any selected source.

The cross-source keys include:

* `sandbox.network.allowManagedDomainsOnly` and `sandbox.filesystem.allowManagedReadPathsOnly`: a `true` in any admin source turns the lock on. While a lock is on, Claude Code unions the allowlist it locks, `sandbox.network.allowedDomains` together with `WebFetch(domain:...)` allow rules, or `sandbox.filesystem.allowRead`, across every admin source. Without the lock, Claude Code treats the allowlist like any other key, so under `"first-wins"` an unselected admin source's allowlist is ignored
* `allowAllClaudeAiMcps`
* The sandbox binary paths `sandbox.bwrapPath` and `sandbox.socatPath`
* The sandbox `ripgrep` binary, [`sandbox.ripgrep`](./settings-reference.md#sandbox-ripgrep)
* `sandbox.filesystem.disabled` and `sandbox.network.strictAllowlist`
* [`useAutoModeDuringPlan`](./settings-reference.md#useautomodeduringplan) and [`syncClaudeAiSkills`](./settings-reference.md#syncclaudeaiskills), where a `false` from any admin source turns the behavior off. A `false` in the developer's user or local settings turns it off too; each key can only deny
* [`enableArtifact`](./settings-reference.md#enableartifact), where a `false` from any admin source turns the [Artifact tool](./artifacts.md) off. A `false` in the developer's user, project, or local settings turns it off too, and no source turns it back on; see [which lower-level values still count](./settings.md#exceptions-to-managed-settings-precedence). Requires Claude Code v2.1.242 or later
* [`maxEffortLevel`](./settings-reference.md#maxeffortlevel), where the lowest cap in any admin source applies. If a developer sets a lower cap in their own settings or with `--settings`, Claude Code applies that one; no source can raise the cap. Requires Claude Code v2.1.267 or later
* A commit-trailer opt-out in `attribution`, or in the deprecated `includeCoAuthoredBy`, from any tier
* [`forceRemoteSettingsRefresh`](./server-managed-settings.md)
* `env`, merged per variable across the admin sources: each variable comes from the highest-priority source that defines it, so lower sources fill in variables the higher ones leave unset. A few variables follow their own rules; [Per-key exceptions across managed sources](./server-managed-settings.md#per-key-exceptions-across-managed-sources) names each one. Requires Claude Code v2.1.223 or later. Before v2.1.223, Claude Code applied the selected source's whole `env` block only

### Compose every managed source

To have Claude Code apply every admin source your organization delivers, set [`managedSourcesBehavior`](./settings-reference.md#managedsourcesbehavior) to `"merge"` in the highest-ranked source you deploy. Claude Code reads the key only from the highest-ranked source that carries either the key or a policy key, so a lower source can't opt itself into merging with the source above it, and a machine that never receives server-managed settings needs the key in its MDM profile too. The user-writable HKCU registry never merges with another source. Requires Claude Code v2.1.242 or later.

Under `"merge"`, Claude Code adds a lower source's list entries, such as `permissions.allow` rules and hooks, to the policy, so turn it on only when every source ranked below your highest one is under an administrator's control.

This table shows how Claude Code combines each kind of key under `"merge"`. The [`managedSourcesBehavior` entry](./settings-reference.md#managedsourcesbehavior) names every key in three of the rows: restriction allowlists, values taken whole, and keys read from the highest-ranked source only.

| Kind of key                                   | How Claude Code combines it                                                                                                                         | Examples                                                                                                                    |
| :-------------------------------------------- | :-------------------------------------------------------------------------------------------------------------------------------------------------- | :-------------------------------------------------------------------------------------------------------------------------- |
| Lists                                         | Combines the entries from every source                                                                                                              | `permissions.allow`, `hooks`, `sandbox.network.allowedDomains`, `deniedMcpServers`                                          |
| Locks                                         | Applies the strictest value any source sets; a looser value applies only from the highest-ranked source                                             | `allowManagedHooksOnly`, `permissions.disableBypassPermissionsMode`, `crossSessionInbound`                                  |
| Restriction allowlists                        | Takes the list whole from the highest-ranked source that sets it, without adding entries from lower sources                                         | `availableModels`, `allowedMcpServers`, `strictKnownMarketplaces`, `allowedChannelPlugins`, and the `fallbackModel` chain   |
| Values taken whole                            | Takes the value whole from the highest-ranked source that sets it, without combining entries or fields from lower sources                           | `sandbox.credentials.awsPairs`, `sandbox.ripgrep`                                                                           |
| Provided MCP servers                          | Combines the server names from every source; when two sources set the same name, applies the higher-ranked source's whole entry                     | `managedMcpServers`                                                                                                         |
| Keys read from the highest-ranked source only | Ignores the key in every lower source, even when the highest-ranked source leaves it unset                                                          | Credential helpers such as `apiKeyHelper`, login pins such as `forceLoginOrgUUID`, `modelPicker`, `permissions.defaultMode` |
| `env`                                         | Merges per variable across admin sources under either setting, as [Keys read from every admin source](#keys-read-from-every-admin-source) describes |                                                                                                                             |
| Every other key                               | Takes the value from the highest-ranked source that sets it                                                                                         | `model`, `cleanupPeriodDays`                                                                                                |

To confirm which sources combined on a machine, [read the `Setting sources` line in `/status`](#read-the-source-in-/status); that section says what each label means.

### Compute the policy with a helper program

A [`policyHelper`](./settings-reference.md#policyhelper) is an executable your MDM policy or managed settings file names, and Claude Code runs it to compute managed settings at startup. When the selected source configures one and the helper emits a `managedSettings` object, that output changes what Claude Code reads:

* **The emitted `managedSettings` object is the only managed settings for the session**, including for the [keys it otherwise reads from every admin source](#keys-read-from-every-admin-source), apart from [`forceRemoteSettingsRefresh`, which has its own startup rule](./settings-reference.md#forceremotesettingsrefresh)

For which helper runs fail, and what Claude Code does when one does, see [Helper failures](./settings-reference.md#helper-failures).

<a id="parent-settings-from-embedding-hosts"></a>

<a id="control-policy-from-an-embedding-host"></a>

<a id="merge-policy-from-an-embedding-host"></a>

### Let an embedding host add policy

When another application launches Claude Code, such as Claude Desktop, an IDE extension, or an Agent SDK app, that host can pass its own managed settings through the SDK `managedSettings` option. Claude Code calls these parent settings.

By default, Claude Code ignores parent settings whenever an admin source is present: server-managed settings, an MDM or OS-level policy, or a managed settings file.

To have Claude Code merge parent settings alongside an admin source, set [`parentSettingsBehavior`](./settings-reference.md#parentsettingsbehavior) to `"merge"` in the highest-priority managed source; Claude Code reads the key from that source only.

Claude Code then keeps only the host's values that restrict what Claude can do, with one gap to know about: unless you also set the `allowManaged*Only` locks, the host's permission allow rules and sandbox allowlists still apply. See [Restrict parent settings](./claude-apps-gateway.md#restrict-parent-settings) for the locks.

A [`policyHelper`](./settings-reference.md#policyhelper) can turn parent merging off regardless of this key; its entry says when.

Claude Code also applies these checks to parent-supplied values on their own:

* When any admin source sets `allowManagedPermissionRulesOnly`, Claude Code drops [parent-supplied](./claude-apps-gateway.md#restrict-parent-settings) permission allow rules and `additionalDirectories` as it reads them, even when a higher-priority source leaves the key unset. The key's effect on your own permission rules comes from the managed settings Claude Code applies, or from parent settings you've chosen to merge
* Claude Code enforces the `forceLoginOrgUUID` or `allowedMcpServers` value in the managed settings it applies and blocks a parent-supplied one. A value in a lower admin source that Claude Code doesn't apply neither applies nor blocks the parent's. The [`managedSourcesBehavior`](./settings-reference.md#managedsourcesbehavior) entry says which source supplies each key under `"merge"`. Before v2.1.223, a value in any admin source blocked the parent's
* An `availableModels` value follows the same rule as `allowedMcpServers`

#### Keep Cowork folder access when only managed rules apply

[Cowork](https://claude.com/docs/cowork/overview) in the Claude Desktop app runs its sessions on Claude Code and grants each session access to its working folders, such as the folder the user connects, through allow rules it supplies when it launches the session. When your managed policy sets [`allowManagedPermissionRulesOnly`](./settings-reference.md#allowmanagedpermissionrulesonly), Claude Code keeps only the allow rules in the managed policy: it drops allow rules a host supplies as parent settings, as `--allowedTools`, or in a settings file, so writes to those folders lose their pre-approval. In a Cowork session that asks before edits, Cowork can't show the prompt, and Claude reports each write as blocked because the path resolves to a protected location or a path outside the connected folder.

To restore the writes, add allow rules for those folders to the managed source Claude Code [selects](#precedence-within-the-managed-tier) on those machines: on an MDM-managed fleet, that's the MDM policy rather than a separate managed settings file. This example uses the file form, and an MDM policy takes the same keys. It keeps `allowManagedPermissionRulesOnly` set and allows edits under a `CoworkProjects` folder in each user's home directory; replace the path with the folders your users connect:

```json managed-settings.json theme={null}
{
  "allowManagedPermissionRulesOnly": true,
  "permissions": {
    "allow": [
      "Edit(~/CoworkProjects/**)"
    ]
  }
}
```

After you deploy the policy, Claude can save files under that folder in a new Cowork session. [Read and Edit rules](./permissions.md#read-and-edit) cover the path syntax, including the `//` form for absolute paths.

### What a developer can change

A developer's own settings files, `--settings` values, and project files never override a managed value; the [exceptions](./settings.md#exceptions-to-managed-settings-precedence) only let a stricter lower-level value count. Four things sit outside that rule:

* **The model for a session**: a managed `model` is a default, not a lock. `--model` and `ANTHROPIC_MODEL` still pick the model for that session, so deploy [`availableModels`](./settings-reference.md#availablemodels) to restrict the choice.
* **Local admin rights**: a developer who is an administrator on the machine can edit the managed source itself, which is why MDM tooling can redeploy the profile or file on a schedule and why the HKLM registry and the macOS managed preferences domain exist.
* **The server-managed cache**: server-managed settings come from Anthropic's servers, and an edit to the local cache [lasts only until the next successful fetch](./server-managed-settings.md#security-considerations).
* **Other tools**: managed settings bind Claude Code only. A developer who calls the API from another tool isn't under them.

<a id="verify-enforcement"></a>

<a id="verify-that-a-policy-is-in-force"></a>

## Check that a policy is in force

A developer reports that a policy isn't applying, or you want to confirm a rollout landed before pushing it to the fleet. Two commands on that machine answer it: `/status` shows which managed source Claude Code selected, and `claude doctor` lists what it dropped.

### Read the source in /status

On the developer's machine, run `/status` inside Claude Code and read the `Setting sources` line. When a managed source is in effect, the line lists `Enterprise managed settings` with the source Claude Code selected in parentheses:

* `(remote)`: server-managed settings from claude.ai or a gateway
* `(plist)` or `(HKLM)`: an MDM or OS policy
* `(file)`, `(drop-ins)`, or `(file + drop-ins)`: `managed-settings.json`, the drop-in directory, or both
* `(remote + file, merged)`, or another list ending in `, merged`: your organization [composes every managed source](#compose-every-managed-source), and Claude Code merged the listed sources into the policy. A lower source can still supply `env` variables without appearing in the list. Requires Claude Code v2.1.242 or later
* `(HKCU)`: the user-writable registry fallback
* `(parent process)`: an [embedding host](#let-an-embedding-host-add-policy) supplied restrictive settings
* `(helper)`: a [`policyHelper`](./settings-reference.md#policyhelper) configured by the selected MDM or file source

When Claude Code found a managed source on the machine and didn't select it, a second line, `Skipped sources`, names each such source. Read it to distinguish a policy that never reached the machine from one that reached it and that a higher-priority source overrode. Requires Claude Code v2.1.242 or later.

When the policy isn't applying, the `Setting sources` line tells you which of two problems you have:

* **The line is missing**: Claude Code found no managed source that delivers a policy key.

  If you deployed a managed settings file, check that it sits at the path for the OS and that it contains a [policy key](#how-claude-code-combines-managed-sources) rather than only the control keys. A file that isn't valid JSON doesn't produce this state; Claude Code [refuses to start](#find-entries-claude-code-dropped) instead.

  When you deployed through server-managed settings instead, run `claude doctor`, which reports the [fetch outcome](./server-managed-settings.md#verify-settings-delivery).
* **The line names a source other than the one you deployed**: a higher-priority source is present and Claude Code ignored yours, and `Skipped sources` lists it. [How Claude Code combines managed sources](#how-claude-code-combines-managed-sources) gives the order.

<a id="invalid-entries-in-managed-settings"></a>

### Find entries Claude Code dropped

When a managed settings file, MDM profile, registry value, or server-managed payload fails schema validation, Claude Code first skips the individual entries it can repair, such as one invalid permission rule, with a warning for each, then drops any top-level key whose value still fails and keeps enforcing every remaining valid key.

Claude Code is stricter with the `managedSettings` a [`policyHelper`](./settings-reference.md#policyhelper) emits: it makes the same entry repairs, but any schema violation that survives fails the whole helper run, and at startup Claude Code refuses to start, the same as for a helper that exits non-zero.

When a managed settings file, drop-in file, MDM plist, or HKLM registry value is present but can't be parsed as a JSON object, Claude Code refuses to start and prints [an error naming the source](./errors.md#managed-settings-document-could-not-be-parsed), even when another admin source delivers a valid policy. Each source fails this way when:

* **Managed settings file or drop-in file**: the file isn't valid JSON, or its top level isn't an object
* **MDM plist**: macOS's `plutil` reports the plist malformed, or its converted content isn't a JSON object
* **HKLM registry value**: the `Settings` value isn't a string, is empty, or doesn't hold a JSON object

Three source states don't cause this refusal:

* An absent file, profile, or registry value isn't a failure; Claude Code runs without that source.
* An empty managed settings file counts as `{}`.
* A malformed value in the user-writable HKCU registry key never blocks launch. Claude Code reports it as a notice in `/status` and `claude doctor` instead.

If a managed settings file, drop-in file, or `managed-settings.d/` directory can't be read and no admin source supplies a policy, sessions signed in with claude.ai or Claude Console credentials exit at startup with a message to contact an administrator.

To find a dropped entry, look in one of three places:

* Interactive sessions show a dialog at startup listing the invalid entries.
* Non-interactive runs with `-p` print a summary to stderr.
* [`claude doctor`](./debug-your-config.md) lists each invalid entry with its source and field.

#### Keys that fail closed

A few enforcement keys aren't dropped when invalid. Claude Code enforces a stricter fallback until the value is fixed; the table shows what it enforces for each key:

| Field                         | Behavior when present but invalid                                                                                                                                                                                                                                                                                                                                                                                        |
| :---------------------------- | :----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `allowedMcpServers`           | Enforced as an empty allowlist until the value is fixed, so no MCP servers that users add are admitted. Servers your organization delivers through [`managedMcpServers`](./settings-reference.md#managedmcpservers) still load, and `managed-mcp.json` servers load per [How a server is evaluated](./managed-mcp.md#how-a-server-is-evaluated). An individual invalid entry is stripped and the valid subset is enforced. |
| `allowedHttpHookUrls`         | Claude Code enforces an empty managed [allowlist](./settings-reference.md#allowedhttphookurls) until you fix the value, so an HTTP hook runs only if another settings file lists its URL. If only an individual entry is invalid, Claude Code strips that entry and enforces the rest.                                                                                                                                    |
| `httpHookAllowedEnvVars`      | Claude Code enforces an empty managed [allowlist](./settings-reference.md#httphookallowedenvvars) until you fix the value, so a header variable is interpolated only if another settings file names it. If only an individual entry is invalid, Claude Code strips that entry and enforces the rest.                                                                                                                      |
| `allowedChannelPlugins`       | Claude Code enforces an empty allowlist until you fix the value, so no channel plugin passed to `--channels` is admitted. If only an individual entry is invalid, it strips that entry and enforces the rest.                                                                                                                                                                                                            |
| `allowManagedHooksOnly`       | Treated as `true` until fixed: the [hook restrictions](./settings-reference.md#allowmanagedhooksonly) apply and, unless `disableCommandPluginSources` is explicitly `false`, command-sourced plugins are disabled.                                                                                                                                                                                                        |
| `allowManagedMcpServersOnly`  | Treated as `true`.                                                                                                                                                                                                                                                                                                                                                                                                       |
| `disableCommandPluginSources` | Treated as `true`, so command-sourced plugins stay disabled until the value is fixed.                                                                                                                                                                                                                                                                                                                                    |
| `availableModels`             | Enforced as an empty allowlist until fixed, so only the Default model is available; a non-string entry is stripped and the valid subset enforced.                                                                                                                                                                                                                                                                        |
| `enforceAvailableModels`      | Treated as `true`.                                                                                                                                                                                                                                                                                                                                                                                                       |
| `forceLoginOrgUUID`           | No organization is permitted to log in until the value is fixed.                                                                                                                                                                                                                                                                                                                                                         |
| `crossSessionInbound`         | Treated as `refuse`, the most restrictive value, so inbound [cross-session messages](./cross-session-messaging.md#control-inbound-messages) are refused until the value is fixed. The developer sees [a warning](./errors.md#crosssessioninbound-must-be-one-of-accept-hold-refuse).                                                                                                                                       |
| `deniedMcpServers`            | An individual invalid entry is stripped and the valid subset is enforced. A wholly invalid value is dropped with a warning, since denying every server would block servers the policy never named.                                                                                                                                                                                                                       |
| `sandbox.credentials`         | A recoverable invalid entry is degraded to `mode: "deny"` with a warning; an unrecoverable one is stripped; valid entries stay enforced. See [invalid credential entries](./settings-reference.md#invalid-credential-entries-in-managed-settings)                                                                                                                                                                         |

`allowedHttpHookUrls` and `httpHookAllowedEnvVars` merge across settings files, so entries in your user, project, or local settings still apply while the managed list is empty. The fallbacks for those two keys and for `allowedChannelPlugins` require Claude Code v2.1.267 or later; earlier versions drop the whole key when its value or any entry is invalid.

`requiredMinimumVersion` and `requiredMaximumVersion` fail open by design: an invalid value is dropped rather than enforced.

This tolerance applies only to managed settings. User, project, and local settings files remain strict: a file whose JSON or top-level shape fails validation is rejected as a whole and reported, and an individual entry that fails, such as a malformed permission rule, is skipped with a warning while the rest of the file applies.

<a id="managed-only-settings"></a>

## Keys only a managed source can set

Claude Code reads the following keys only from a managed source; placing them in user or project settings files has no effect.

Most of them are locks: the value a lock governs, such as permission rules or `sandbox.network.allowedDomains`, is an ordinary key that any level can set, and the lock tells Claude Code to honor only the managed value.

The table covers the permission, plugin, and delivery controls. For any key not listed here, the Scope column of the [settings reference](./settings-reference.md#all-settings) index says whether it's managed-only; the remaining managed-only keys there include the gateway login URL, version, browser, mobile-simulator, SSH host, Desktop local-session, sandbox binary path, model pricing, and CLAUDE.md controls.

| Setting                                                                                                               | Description                                                                                                                                                                                                                                                                                                                                                                                                                                                                    |
| :-------------------------------------------------------------------------------------------------------------------- | :----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| [`allowAllClaudeAiMcps`](./settings-reference.md#allowallclaudeaimcps)                                                 | Load the claude.ai connectors Claude Code fetches itself alongside a deployed `managed-mcp.json` instead of suppressing them                                                                                                                                                                                                                                                                                                                                                   |
| [`allowedChannelPlugins`](./settings-reference.md#allowedchannelplugins)                                               | Allowlist of channel plugins that may push messages. Replaces the default Anthropic allowlist when set. Requires `channelsEnabled: true`. See [Restrict which channel plugins can run](./channels.md#restrict-which-channel-plugins-can-run)                                                                                                                                                                                                                                    |
| [`allowManagedHooksOnly`](./settings-reference.md#allowmanagedhooksonly)                                               | When `true`, restricts which hooks run; see [what runs under `allowManagedHooksOnly`](./settings-reference.md#what-runs-under-allowmanagedhooksonly) for the full effect list                                                                                                                                                                                                                                                                                                   |
| [`allowManagedMcpServersOnly`](./settings-reference.md#allowmanagedmcpserversonly)                                     | When `true`, only `allowedMcpServers` from managed settings are respected. `deniedMcpServers` still merges from all sources. See [Managed MCP configuration](./managed-mcp.md)                                                                                                                                                                                                                                                                                                  |
| [`allowManagedPermissionRulesOnly`](./settings-reference.md#allowmanagedpermissionrulesonly)                           | Makes managed settings the only settings source of permission rules. The entry lists every source it ignores                                                                                                                                                                                                                                                                                                                                                                   |
| [`blockedMarketplaces`](./settings-reference.md#blockedmarketplaces)                                                   | Blocklist of marketplace sources. Blocked sources are checked before downloading, so they never touch the filesystem. See [managed marketplace restrictions](./plugin-marketplaces.md#managed-marketplace-restrictions)                                                                                                                                                                                                                                                         |
| [`channelsEnabled`](./settings-reference.md#channelsenabled)                                                           | Allow [channels](./channels.md) for the organization. See [enterprise controls](./channels.md#enterprise-controls) for the default on each plan                                                                                                                                                                                                                                                                                                                                  |
| [`disableCommandPluginSources`](./settings-reference.md#disablecommandpluginsources)                                   | When `true`, blocks [`command` plugin sources](./plugin-marketplaces.md#command-sources) entirely, so the marketplace-declared command never runs. Also blocks marketplace [`headersHelper` commands](./plugin-marketplaces.md#authenticate-archive-downloads), except for a marketplace that managed settings themselves declare. When unset, follows `allowManagedHooksOnly`. Requires Claude Code v2.1.229 or later, and the `headersHelper` block requires v2.1.238 or later |
| [`disableSideloadFlags`](./settings-reference.md#disablesideloadflags)                                                 | Reject the `--plugin-dir`, `--plugin-url`, `--agents`, and `--mcp-config` flags at startup. In cloud sessions, Claude Code drops the MCP servers the server delivered through `--mcp-config`, other than in-process `type: "sdk"` entries, and starts the session. Requires Claude Code v2.1.193 or later                                                                                                                                                                      |
| [`forceRemoteSettingsRefresh`](./settings-reference.md#forceremotesettingsrefresh)                                     | When `true`, blocks CLI startup until remote managed settings are freshly fetched and exits if the fetch fails. See [fail-closed enforcement](./server-managed-settings.md#enforce-fail-closed-startup)                                                                                                                                                                                                                                                                         |
| [`managedMcpServers`](./settings-reference.md#managedmcpservers)                                                       | Remote MCP servers provided to every user alongside their own. It provides servers rather than locking anything down. See [Provide servers through managed settings](./managed-mcp.md#provide-servers-through-managed-settings). Requires Claude Code v2.1.259 or later                                                                                                                                                                                                         |
| [`managedSourcesBehavior`](./settings-reference.md#managedsourcesbehavior)                                             | Whether Claude Code applies only the highest-priority managed source or [composes every one of them](#compose-every-managed-source)                                                                                                                                                                                                                                                                                                                                            |
| [`parentSettingsBehavior`](./settings-reference.md#parentsettingsbehavior)                                             | Whether host-supplied parent settings merge under the managed policy                                                                                                                                                                                                                                                                                                                                                                                                           |
| [`pluginSuggestionMarketplaces`](./settings-reference.md#pluginsuggestionmarketplaces)                                 | Marketplaces whose plugins Claude Code may suggest to users                                                                                                                                                                                                                                                                                                                                                                                                                    |
| [`pluginTrustMessage`](./settings-reference.md#plugintrustmessage)                                                     | Custom message appended to the plugin trust warning shown before installation                                                                                                                                                                                                                                                                                                                                                                                                  |
| [`policyHelper`](./settings-reference.md#policyhelper)                                                                 | Executable that computes managed settings at startup; see [Compute managed settings with a policy helper](./settings-reference.md#policyhelper)                                                                                                                                                                                                                                                                                                                                 |
| [`sandbox.filesystem.allowManagedReadPathsOnly`](./settings-reference.md#sandbox-filesystem-allowmanagedreadpathsonly) | When `true`, only `filesystem.allowRead` paths from managed settings are respected. `denyRead` still merges from all sources                                                                                                                                                                                                                                                                                                                                                   |
| [`sandbox.network.allowManagedDomainsOnly`](./settings-reference.md#sandbox-network-allowmanageddomainsonly)           | Honor only managed `allowedDomains` and `WebFetch(domain:...)` allow rules; block other domains without prompting                                                                                                                                                                                                                                                                                                                                                              |
| [`strictKnownMarketplaces`](./settings-reference.md#strictknownmarketplaces)                                           | Controls which plugin marketplace sources users can add and install plugins from. See [managed marketplace restrictions](./plugin-marketplaces.md#managed-marketplace-restrictions)                                                                                                                                                                                                                                                                                             |
| [`strictPluginOnlyCustomization`](./settings-reference.md#strictpluginonlycustomization)                               | Block skills, agents, hooks, and MCP servers from user and project sources; `true` locks all four, an array names which                                                                                                                                                                                                                                                                                                                                                        |
| [`wslInheritsWindowsSettings`](./settings-reference.md#wslinheritswindowssettings)                                     | When set in the HKLM registry or a file under `C:\Program Files\ClaudeCode`, have WSL read the Windows policy chain, and read `/etc/claude-code` only when no managed settings file or drop-in under that directory delivers a [policy key](#how-claude-code-combines-managed-sources); the entry gives the order                                                                                                                                                              |

> [!NOTE]
> On Team and Enterprise plans, an Owner enables or disables [Remote Control](./remote-control.md) and [web sessions](./claude-code-on-the-web.md) organization-wide in [Claude Code admin settings](https://claude.ai/admin-settings/claude-code). Remote Control can additionally be disabled per device with the [`disableRemoteControl`](./settings-reference.md#disableremotecontrol) setting. Web sessions have no per-device managed settings key.
>
> To check whether these organization settings reached a given machine, run `claude doctor` there and read the `Organization policy` line, which says where Claude Code loaded the policy from or why it didn't load. Requires Claude Code v2.1.261 or later. In a running session, `/status` shows the same line when the policy didn't load.

## Turn telemetry off for your organization

Claude Code sends Anthropic operational [telemetry](./data-usage.md#telemetry-services) by default on sessions that use the Anthropic API, whether directly, through an LLM gateway, or through a custom `ANTHROPIC_BASE_URL`; [Default behaviors by API provider](./data-usage.md#default-behaviors-by-api-provider) says which providers send it. To turn it off for every developer without relying on each person's shell, deliver `DISABLE_TELEMETRY` through the `env` block of your managed settings. This example sets `DISABLE_TELEMETRY` for everyone the policy reaches:

```json theme={null}
{
  "env": {
    "DISABLE_TELEMETRY": "1"
  }
}
```

Claude Code applies a value of `1` without showing the user the [approval dialog](./server-managed-settings.md#environment-variables-and-the-approval-dialog).

If you turn telemetry off, Claude Code stops sending the usage data that feeds your organization's [analytics dashboard](./analytics.md) for the developers the policy reaches. The variable also turns off feature-flag fetching, which makes Remote Control, default auto mode, and the other [features that need feature-flag fetching](./env-vars.md#features-that-need-feature-flag-fetching) unavailable for those developers.

[Where and when a policy applies](#where-and-when-a-policy-applies) says which delivery mechanism reaches each surface, and [Platform availability](./server-managed-settings.md#platform-availability) says which sessions skip the server-managed settings fetch.

If your organization uses customer-managed encryption keys and routes Claude Code through a gateway, [Configure proxies and gateways](./third-party-integrations.md#configure-proxies-and-gateways) says why those sessions need this variable.

## See also

* [Set up Claude Code for your organization](./admin-setup.md): decide what to enforce and how
* [Server-managed settings](./server-managed-settings.md): deliver policy from the claude.ai console or a gateway
* [Managed MCP configuration](./managed-mcp.md): control which MCP servers developers can use
* [All settings](./settings-reference.md): every key, with whether a managed source can set it
* [Example settings files](./settings-example.md#an-organizations-managed-settings): a complete `managed-settings.json` showing the shape of the managed keys
