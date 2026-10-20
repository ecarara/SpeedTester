# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Edson Angelo Carara
[CmdletBinding()]
param([Parameter(Mandatory = $true)][string]$PackagePath)
$ErrorActionPreference = 'Stop'
Add-AppxPackage -Path (Resolve-Path $PackagePath).Path
$package = Get-AppxPackage -Name 'ecarara.SpeedTester' -ErrorAction SilentlyContinue
if ($package) {
    $configDirectory = Join-Path $env:APPDATA 'SpeedTester'
    $configPath = Join-Path $configDirectory 'speedtester.env'
    $configExists = Test-Path $configPath
    $needsConfigurationPrompt = $true
    if ($needsConfigurationPrompt) {
        $windowsTimezone = (& tzutil.exe /g 2>$null | Select-Object -First 1).Trim()
        $timezoneMap = @{
            'E. South America Standard Time' = 'America/Sao_Paulo'
            'Atlantic Standard Time' = 'America/Halifax'
            'Eastern Standard Time' = 'America/New_York'
            'Central Standard Time' = 'America/Chicago'
            'Mountain Standard Time' = 'America/Denver'
            'Pacific Standard Time' = 'America/Los_Angeles'
            'UTC' = 'UTC'
        }
        $timezone = if ($timezoneMap.ContainsKey($windowsTimezone)) { $timezoneMap[$windowsTimezone] } else { 'UTC' }
        $server = ''
        $port = '5201'
        if ($configExists) {
            $existingLines = Get-Content $configPath
            $timezoneLine = $existingLines | Where-Object { $_ -match '^TZ=' } | Select-Object -First 1
            $serverLine = $existingLines | Where-Object { $_ -match '^IPERF3_SERVER=' } | Select-Object -First 1
            $portLine = $existingLines | Where-Object { $_ -match '^IPERF3_PORT=' } | Select-Object -First 1
            if ($timezoneLine) { $timezone = $timezoneLine -replace '^TZ=', '' }
            if ($serverLine) { $server = $serverLine -replace '^IPERF3_SERVER=', '' }
            if ($portLine) { $port = $portLine -replace '^IPERF3_PORT=', '' }
        }
        $writeConfig = -not $configExists
        Write-Host ''
        Write-Host $(if ($configExists) { 'SpeedTester - confirmação da configuração atual' } else { 'SpeedTester - configuração inicial' })
        Write-Host "Fuso horário detectado: $windowsTimezone -> $timezone"
        Write-Host 'Runner: iperf3'
        Write-Host "Servidor iPerf3: $(if ($server) { $server } else { 'não configurado' })"
        Write-Host "Porta iPerf3: $port"
        if ($env:SPEEDTESTER_NONINTERACTIVE -ne '1') {
            $confirmation = Read-Host 'Confirmar esses parâmetros? [Y/n]'
            if ($confirmation -match '^[Nn]$') {
                $writeConfig = $true
                $timezoneInput = Read-Host "Fuso horário IANA [$timezone]"
                if ($timezoneInput) { $timezone = $timezoneInput }
                $server = Read-Host 'Servidor iPerf3 (vazio para configurar depois)'
                $portInput = Read-Host "Porta iPerf3 [$port]"
                if ($portInput) { $port = $portInput }
            } elseif ($configExists) {
                $writeConfig = $false
                Write-Host "Configuração confirmada: $configPath"
            }
        }
        if ($timezone -notmatch '^[A-Za-z0-9._+-]+(/[A-Za-z0-9._+-]+)*$') {
            throw "Fuso horário IANA inválido: $timezone"
        }
        if ($server -and $server -notmatch '^[A-Za-z0-9._:.-]+$') {
            throw "Servidor iPerf3 inválido: $server"
        }
        $portNumber = 0
        if (-not [int]::TryParse($port, [ref]$portNumber) -or $portNumber -lt 1 -or $portNumber -gt 65535) {
            throw "Porta iPerf3 inválida: $port"
        }
        if ($writeConfig) {
            New-Item -ItemType Directory -Force -Path $configDirectory | Out-Null
            $template = Join-Path $package.InstallLocation 'speedtester.env.example'
            $content = if ($configExists) { Get-Content $configPath -Raw } else { Get-Content $template -Raw }
            $content = $content -replace '(?m)^IPERF3_SERVER=.*$', "IPERF3_SERVER=$server"
            $content = $content -replace '(?m)^IPERF3_PORT=.*$', "IPERF3_PORT=$port"
            $content = $content -replace '(?m)^TZ=.*$', "TZ=$timezone"
            [System.IO.File]::WriteAllText($configPath, $content, [System.Text.UTF8Encoding]::new($false))
            Write-Host "Configuração criada/atualizada em $configPath"
        }
        if (-not $server) { Write-Warning 'IPERF3_SERVER não foi configurado; medições começarão após informar um servidor iPerf3.' }
    }
    $client = Join-Path $package.InstallLocation 'SpeedTesterClient.exe'
    $api = Join-Path $package.InstallLocation 'SpeedTesterAPI.exe'
    if ((Test-Path $client) -and (Test-Path $api)) {
        $trigger = New-ScheduledTaskTrigger -AtLogOn
        $apiAction = New-ScheduledTaskAction -Execute $api
        Register-ScheduledTask -TaskName 'speedtester-api.service' -Action $apiAction -Trigger $trigger -Description 'SpeedTester local dashboard API' -Force | Out-Null
        $clientAction = New-ScheduledTaskAction -Execute $client
        Register-ScheduledTask -TaskName 'speedtester-client.service' -Action $clientAction -Trigger $trigger -Description 'SpeedTester broadband measurements' -Force | Out-Null
        Unregister-ScheduledTask -TaskName 'SpeedTester' -Confirm:$false -ErrorAction SilentlyContinue
    }
}
Write-Output 'SpeedTester instalado. A remoção é feita por uninstall-msix.ps1 ou Configurações do Windows.'
