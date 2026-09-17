# Deploy the Windows app

> For the complete documentation index, see [llms.txt](https://learn.chatgpt.com/llms.txt). Markdown versions of documentation pages are available by appending `.md` to the page URL.

Choose how your organization installs apps.

<a id="deploy-the-app-with-an-enterprise-management-tool"></a>

Package source

### Deploy through Microsoft Store

Use Intune's Microsoft Store integration to install and update the app.

1. In the Intune admin center, go to **Apps** > **All apps** >
   **Create**. Select **Microsoft Store app (new)**.
2. Search for **ChatGPT** from **OpenAI**, or enter the Store
   product ID `9PLM9XGG6VKS`. Select the app and review its installation settings.
3. Under **Required**, add your target group so Intune installs the app
   automatically, then select **Create**.

For optional installation through Company Portal, use **Available for enrolled
devices** instead.

Devices need access to the Microsoft Store and Windows Update endpoints in
Microsoft's [network requirements](https://learn.microsoft.com/en-us/intune/fundamentals/endpoints#microsoft-store).
If your network blocks these endpoints, select **Offline MSIX**.

For installation context, network requirements, and deployment monitoring, see
Microsoft's [Intune Store app guide](https://learn.microsoft.com/en-us/intune/app-management/deployment/add-microsoft-store).

### Deploy an offline package with Intune

Use a downloaded MSIX when devices can't use Microsoft's distribution services
or you need to deploy a specific approved version. Choose a **Required**
assignment so Intune installs the app automatically.

> [!WARNING]
> If you've only blocked access to the Microsoft Store app, you can still deploy
> through Intune's Microsoft Store integration. Select **Microsoft Store
> (recommended)** above.

Assignment

1. Download the [x64 MSIX](https://persistent.oaistatic.com/codex-app-prod/ChatGPT-x64.msix) or [Arm64 MSIX](https://persistent.oaistatic.com/codex-app-prod/ChatGPT-arm64.msix) for your devices.
2. In the Intune admin center, go to **Apps** > **All apps** > **Create**.
   Select **Line-of-business app**, upload the MSIX, and review the package
   information.
3. On **Assignments**, add your target device group under **Required**.
4. In that assignment's **Install Context** column, select **User context**,
   change it to **Device context**, and save.
5. Review and create the app. Confirm successful installation in **Device
   install status**, then have employees launch ChatGPT normally.

If the app doesn't appear, have users sign out and back in.

For more information, see Microsoft's [LOB app deployment guide](https://learn.microsoft.com/en-us/intune/app-management/deployment/add-lob-windows).

To let users choose when to install the offline package, use a **Windows app
(Win32)** with an **Available for enrolled devices** assignment:

1. Download the [x64 MSIX](https://persistent.oaistatic.com/codex-app-prod/ChatGPT-x64.msix) or [Arm64 MSIX](https://persistent.oaistatic.com/codex-app-prod/ChatGPT-arm64.msix), plus the [offline license](https://persistent.oaistatic.com/codex-app-prod/ChatGPT-License.xml). Rename the package to `ChatGPT.msix` and keep both files in the same
   folder.
2. Save the following as `Install-ChatGPT.ps1`
   beside the downloaded files:

```powershell
   #Requires -RunAsAdministrator
   $ErrorActionPreference = 'Stop'

   Add-AppxProvisionedPackage -Online `
     -PackagePath "$PSScriptRoot\ChatGPT.msix" `
     -LicensePath "$PSScriptRoot\ChatGPT-License.xml" `
     -Regions all
```

3. Use Microsoft's [Win32 app workflow](https://learn.microsoft.com/en-us/intune/app-management/deployment/add-win32) to package these files and add a **Windows app (Win32)** in Intune. Set
   **Install behavior** to **System**, target the package's architecture, and
   run the script with 64-bit Windows PowerShell. Assign it as
   **Available for enrolled devices**.

<details>
<summary>Win32 installation and detection settings</summary>

Use this install command:

```text
%SystemRoot%\Sysnative\WindowsPowerShell\v1.0\powershell.exe -NoProfile -File .\Install-ChatGPT.ps1
```

For the custom detection rule, run the following script in 64-bit PowerShell.
It reports success when Windows has provisioned the app on the device. If you deploy a
specific version, also compare its `Version` with your approved version.

```powershell
$package = Get-AppxProvisionedPackage -Online -ErrorAction Stop |
  Where-Object DisplayName -eq 'OpenAI.Codex'

if ($package) {
  Write-Output $package.PackageName
  exit 0
}
exit 1
```

For the uninstall command, package an `Uninstall-ChatGPT.ps1` script with these
commands and run it in the same System context. This removes the provisioned
package and the app registrations for all users on the device.

```powershell
#Requires -RunAsAdministrator
$ErrorActionPreference = 'Stop'

Get-AppxProvisionedPackage -Online |
  Where-Object DisplayName -eq 'OpenAI.Codex' |
  Remove-AppxProvisionedPackage -Online -AllUsers

Get-AppxPackage -AllUsers -Name 'OpenAI.Codex' |
  Remove-AppxPackage -AllUsers
```

Follow your organization's PowerShell script-signing policy for both scripts.

The app becomes available to users when Windows registers the provisioned
package at sign-in. Have users sign out and back in if it doesn't appear.

</details>

### Deploy with Microsoft Configuration Manager (SCCM)

Deploy the downloaded MSIX through Configuration Manager and Software Center.

1. Download the [x64 MSIX](https://persistent.oaistatic.com/codex-app-prod/ChatGPT-x64.msix) or [Arm64 MSIX](https://persistent.oaistatic.com/codex-app-prod/ChatGPT-arm64.msix) for your devices. Put it on a network share accessible to Configuration
   Manager.
2. Go to **Software Library** > **Application
   Management** > **Applications** > **Create Application**. Select **Windows app
   package** and enter the MSIX path. Review the detected package information and
   enable **Provision this application for all users on the device**.
3. Distribute the content to your distribution points
   and deploy to a device collection. Choose **Required** to install
   automatically, or **Available** to let users install from Software Center.

Use the Windows app package deployment type, rather than the Store-link
deployment type. For package requirements and all-user provisioning, see
Microsoft's [Configuration Manager guide](https://learn.microsoft.com/en-us/intune/configmgr/apps/get-started/creating-windows-applications).

If your deployment workflow requires it, download the [offline license](https://persistent.oaistatic.com/codex-app-prod/ChatGPT-License.xml) alongside the package.

### Deploy with another management tool

Use your management tool's MSIX deployment workflow to install the app on managed
Windows devices.

1. Download the [x64 MSIX](https://persistent.oaistatic.com/codex-app-prod/ChatGPT-x64.msix) or [Arm64 MSIX](https://persistent.oaistatic.com/codex-app-prod/ChatGPT-arm64.msix) for your devices.
2. Add the MSIX to your deployment tool. Configure installation for the device,
   using Local System or administrator privileges.
3. Assign automatic installation to a pilot device group. Confirm that employees
   can open ChatGPT under their normal Windows accounts before expanding deployment.

If the app doesn't appear, have users sign out and back in.

<details>
<summary>Install with a PowerShell script</summary>

If your tool requires an installation command, download the [offline license](https://persistent.oaistatic.com/codex-app-prod/ChatGPT-License.xml) alongside the MSIX.
Rename the package to `ChatGPT.msix` and save this script as
`Install-ChatGPT.ps1` in the same folder:

```powershell
#Requires -RunAsAdministrator
$ErrorActionPreference = 'Stop'

Add-AppxProvisionedPackage -Online `
  -PackagePath "$PSScriptRoot\ChatGPT.msix" `
  -LicensePath "$PSScriptRoot\ChatGPT-License.xml" `
  -Regions all
```

Package the script and both files together. Configure your tool to run the script
with 64-bit Windows PowerShell as Local System or an administrator.

</details>

<a id="let-users-install-and-update-the-app"></a>

Package source

### Let users install the app

Use this option when users can install applications themselves or get help
from an administrator.

1. Direct users to the [ChatGPT Windows installer](https://get.microsoft.com/installer/download/9PLM9XGG6VKS?cid=website_cta_psi).
2. Run the installer and follow the Windows installation
   prompts. An administrator must approve the installation.
3. Open ChatGPT and sign in with a work account to get started.

Users can also install from the command line:

```powershell
winget install --id 9PLM9XGG6VKS -s msstore
```

The installer provides automatic updates. Microsoft Store components may appear
during installation or updates, but users don't need to browse the Store.

<a id="install-without-microsoft-distribution-services"></a>

### Install from an offline package

Download the files on a connected machine, then copy them to the target device.
An administrator must perform the installation.

1. Download the [x64 MSIX](https://persistent.oaistatic.com/codex-app-prod/ChatGPT-x64.msix) or [Arm64 MSIX](https://persistent.oaistatic.com/codex-app-prod/ChatGPT-arm64.msix), plus the [offline license](https://persistent.oaistatic.com/codex-app-prod/ChatGPT-License.xml). Rename the package to `ChatGPT.msix` and keep both files in the same
   folder.
2. Open Windows PowerShell as an administrator in that
   folder and run:

```powershell
   Add-AppxProvisionedPackage -Online `
     -PackagePath .\ChatGPT.msix `
     -LicensePath .\ChatGPT-License.xml `
     -Regions all
```

3. Sign out and back in if the app doesn't appear, then open
   ChatGPT and sign in with a work account.

These links provide the latest Store-signed package for each architecture.
Offline installation doesn't provide offline access to ChatGPT. Standalone
MSI and non-Store EXE packages aren't available.

<a id="manage-in-app-updates"></a>

## Manage app updates

The app checks for updates by default, including after an offline
installation. To enable automatic updates, allow devices to reach
`persistent.oaistatic.com`. If you disable automatic updates, deploy newer
packages through your management tool.

For update policy and rollout guidance, see
[Manage app updates](./manage-app-updates.md). Disabling the built-in
updater doesn't disable updates from the Microsoft Store or your management tool.

## Troubleshooting

<details>
<summary>Installation fails with error `0x80073D28`</summary>

Windows returns `0x80073D28` (`ERROR_PACKAGED_SERVICE_REQUIRES_ADMIN_PRIVILEGES`)
when it can't install a packaged service without administrator privileges.
Run the installation as an administrator, or configure your deployment tool to
install in device or System context.

For an existing SCCM deployment:

1. Open the application's **Properties** > **Deployment Types**.
2. Edit the **Windows app package** deployment type and open **User Experience**.
3. Enable **Provision this application for all users on the device** and save.
4. Refresh the client's machine policy, then retry the installation in Software
   Center.

For more information about the provisioning setting, see Microsoft's [application deployment settings](https://learn.microsoft.com/en-us/intune/configmgr/apps/deploy-use/create-applications#automatically-detect-application-information).

</details>

## Related resources

- [Managed configuration](./managed-configuration.md)
- [ChatGPT desktop app for Windows](../windows/windows-app.md)