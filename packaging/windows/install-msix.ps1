# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Edson Angelo Carara
[CmdletBinding()]
param([Parameter(Mandatory = $true)][string]$PackagePath)
$ErrorActionPreference = 'Stop'
Add-AppxPackage -Path (Resolve-Path $PackagePath).Path
$package = Get-AppxPackage -Name 'ecarara.SpeedTester' -ErrorAction SilentlyContinue
if ($package) {
    $client = Join-Path $package.InstallLocation 'SpeedTesterClient.exe'
    if (Test-Path $client) {
        $action = New-ScheduledTaskAction -Execute $client
        $trigger = New-ScheduledTaskTrigger -AtLogOn
        Register-ScheduledTask -TaskName 'SpeedTester' -Action $action -Trigger $trigger -Description 'SpeedTester broadband measurements' -Force | Out-Null
    }
}
Write-Output 'SpeedTester instalado. A remoção é feita por uninstall-msix.ps1 ou Configurações do Windows.'
