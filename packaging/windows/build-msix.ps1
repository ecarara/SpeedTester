# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Edson Angelo Carara
[CmdletBinding()]
param(
    [string]$Version = $(if ($env:APP_VERSION) { $env:APP_VERSION } else { '0.3.0.0' }),
    [ValidateSet('x64', 'arm64')][string]$Architecture = 'x64',
    [string]$LauncherPath = "$(Join-Path $PSScriptRoot '..\..\dist\windows\SpeedTesterLauncher.exe')",
    [string]$ClientPath = "$(Join-Path $PSScriptRoot '..\..\dist\windows\SpeedTesterClient.exe')",
    [string]$OutputDirectory = "$(Join-Path $PSScriptRoot '..\..\dist\windows')",
    [switch]$Sign,
    [string]$CertificatePath,
    [string]$CertificatePassword
)
$ErrorActionPreference = 'Stop'
$makeAppx = Get-Command MakeAppx.exe -ErrorAction SilentlyContinue
if (-not $makeAppx) {
    $windowsKitBin = Join-Path ${env:ProgramFiles(x86)} 'Windows Kits\10\bin'
    if (Test-Path $windowsKitBin) {
        $makeAppx = Get-ChildItem -Path $windowsKitBin -Filter MakeAppx.exe -Recurse -File -ErrorAction SilentlyContinue |
            Sort-Object FullName -Descending |
            Select-Object -First 1
    }
}
if (-not $makeAppx) { throw 'MakeAppx.exe não encontrado; instale o Windows SDK.' }
$makeAppxPath = $makeAppx.Path
if (-not $makeAppxPath) { $makeAppxPath = $makeAppx.FullName }
if (-not $makeAppxPath) { $makeAppxPath = $makeAppx.Source }
if (-not $makeAppxPath) { throw 'Não foi possível determinar o caminho do MakeAppx.exe.' }
if (-not (Test-Path $LauncherPath)) { throw "Launcher não encontrado: $LauncherPath" }
if (-not (Test-Path $ClientPath)) { throw "Cliente não encontrado: $ClientPath" }
$repo = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$stage = Join-Path $env:TEMP ("speedtester-msix-" + [guid]::NewGuid().ToString('N'))
$assets = Join-Path $stage 'Assets'
New-Item -ItemType Directory -Force -Path $assets | Out-Null
try {
    Copy-Item $LauncherPath (Join-Path $stage 'SpeedTesterLauncher.exe')
    Copy-Item $ClientPath (Join-Path $stage 'SpeedTesterClient.exe')
    $apiPath = Join-Path (Split-Path $ClientPath -Parent) 'SpeedTesterAPI.exe'
    if (-not (Test-Path $apiPath)) { throw "API não encontrado: $apiPath" }
    Copy-Item $apiPath (Join-Path $stage 'SpeedTesterAPI.exe')
    $runtimeRoot = Split-Path $ClientPath -Parent
    foreach ($name in @('tools', 'THIRD-PARTY-LICENSES', 'iperf-components.json', 'runtime-components.json', 'native-sbom.cdx.json', 'LICENSE')) {
        $payload = Join-Path $runtimeRoot $name
        if (-not (Test-Path $payload)) { throw "Componente nativo ausente: $name" }
        Copy-Item $payload (Join-Path $stage $name) -Recurse -Force
    }
    Copy-Item (Join-Path $repo 'packaging\linux\speedtester.env.example') (Join-Path $stage 'speedtester.env.example')
    Copy-Item (Join-Path $repo 'assets\packaging\windows\msix\*.png') $assets
    $manifest = (Get-Content (Join-Path $PSScriptRoot 'AppxManifest.xml.in') -Raw).Replace('@VERSION@', $Version).Replace('@ARCH@', $Architecture)
    [System.IO.File]::WriteAllText((Join-Path $stage 'AppxManifest.xml'), $manifest, (New-Object System.Text.UTF8Encoding($false)))
    New-Item -ItemType Directory -Force -Path $OutputDirectory | Out-Null
    $output = Join-Path $OutputDirectory ("SpeedTester-$Version-$Architecture.msix")
    & $makeAppxPath pack /d $stage /p $output /o
    if ($Sign) {
        $signTool = Get-Command SignTool.exe -ErrorAction SilentlyContinue
        if (-not $signTool) { throw 'SignTool.exe não encontrado; instale o Windows SDK.' }
        if (-not $CertificatePath) { throw 'CertificatePath é obrigatório quando -Sign é usado.' }
        $args = @('sign', '/fd', 'SHA256', '/f', $CertificatePath)
        if ($CertificatePassword) { $args += @('/p', $CertificatePassword) }
        $args += $output
        & $signTool.Source @args
    }
    Write-Output $output
}
finally {
    Remove-Item $stage -Recurse -Force -ErrorAction SilentlyContinue
}
