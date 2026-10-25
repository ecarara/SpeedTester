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
    $buildVersion = if ($env:APP_VERSION) { $env:APP_VERSION } else { '0.3.0' }
    & $Python scripts/stamp_version.py app $buildVersion
    if ($LASTEXITCODE -ne 0) { throw 'Falha ao definir a versão do pacote.' }
    & $Python -m PyInstaller --noconfirm --clean --onefile --name SpeedTesterLauncher app/desktop_launcher.py
    & $Python -m PyInstaller --noconfirm --clean --onefile --name SpeedTesterClient --paths app app/windows_client_entry.py
    & $Python -m PyInstaller --noconfirm --clean --onefile --name SpeedTesterAPI --paths app --add-data "app/dashboard:dashboard" app/native_api_entry.py
    New-Item -ItemType Directory -Force -Path $OutputDirectory | Out-Null
    Copy-Item dist/SpeedTesterLauncher.exe, dist/SpeedTesterClient.exe, dist/SpeedTesterAPI.exe $OutputDirectory -Force
    & $Python scripts/bundle_release_tools.py $OutputDirectory --version $buildVersion
    if ($LASTEXITCODE -ne 0) { throw 'Falha ao incorporar a ferramenta de medição.' }
}
finally {
    Pop-Location
}
