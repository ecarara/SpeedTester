# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Edson Angelo Carara
[CmdletBinding()]
param(
    [string]$Python = "python",
    [string]$OutputDirectory = "$(Join-Path $PSScriptRoot '..\..\dist\windows')"
)
$ErrorActionPreference = 'Stop'
$repo = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
Push-Location $repo
try {
    & $Python -m PyInstaller --noconfirm --clean --onefile --name SpeedTesterLauncher app/desktop_launcher.py
    & $Python -m PyInstaller --noconfirm --clean --onefile --name SpeedTesterClient --paths app app/windows_client_entry.py
    & $Python -m PyInstaller --noconfirm --clean --onefile --name SpeedTesterAPI --paths app app/windows_api_entry.py
    New-Item -ItemType Directory -Force -Path $OutputDirectory | Out-Null
    Copy-Item dist/SpeedTesterLauncher.exe, dist/SpeedTesterClient.exe, dist/SpeedTesterAPI.exe $OutputDirectory -Force
}
finally {
    Pop-Location
}
