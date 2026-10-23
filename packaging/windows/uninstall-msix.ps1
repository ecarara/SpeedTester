# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Edson Angelo Carara
[CmdletBinding()]
param([switch]$PurgeData)
$ErrorActionPreference = 'Stop'
Stop-ScheduledTask -TaskName 'SpeedTester' -ErrorAction SilentlyContinue
Unregister-ScheduledTask -TaskName 'SpeedTester' -Confirm:$false -ErrorAction SilentlyContinue
Stop-ScheduledTask -TaskName 'speedtester-api.service' -ErrorAction SilentlyContinue
Stop-ScheduledTask -TaskName 'speedtester-client.service' -ErrorAction SilentlyContinue
Unregister-ScheduledTask -TaskName 'speedtester-api.service' -Confirm:$false -ErrorAction SilentlyContinue
Unregister-ScheduledTask -TaskName 'speedtester-client.service' -Confirm:$false -ErrorAction SilentlyContinue
Get-AppxPackage -Name 'ecarara.SpeedTester' -ErrorAction SilentlyContinue |
    Remove-AppxPackage
if ($PurgeData) {
    Remove-Item "$env:LOCALAPPDATA\SpeedTester" -Recurse -Force -ErrorAction SilentlyContinue
    Write-Output 'SpeedTester removido com os dados locais.'
} else {
    Write-Output 'SpeedTester removido; dados locais preservados.'
}
