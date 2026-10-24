# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Edson Angelo Carara
[CmdletBinding()]
param([Parameter(Mandatory = $true)][string]$PackagePath)
$ErrorActionPreference = 'Stop'

function ConvertTo-ContractedSpeed([string]$Value) {
    if ([string]::IsNullOrWhiteSpace($Value)) { return '' }
    $normalized = $Value.Trim().Replace(',', '.')
    $number = 0.0
    if ($normalized.Length -gt 32 -or $normalized -notmatch '^[0-9]+(\.[0-9]+)?$' -or
        -not [double]::TryParse($normalized, [System.Globalization.NumberStyles]::AllowDecimalPoint,
            [System.Globalization.CultureInfo]::InvariantCulture, [ref]$number) -or
        [double]::IsNaN($number) -or [double]::IsInfinity($number) -or $number -le 0) {
        throw 'Velocidade contratada inválida: informe um número positivo em Mbps.'
    }
    return $normalized
}

function Read-ContractedSpeed([string]$Label, [string]$Current) {
    if ($env:SPEEDTESTER_NONINTERACTIVE -eq '1') { return (ConvertTo-ContractedSpeed $Current) }
    while ($true) {
        $value = Read-Host "$Label contratado em Mbps [$Current; Enter mantém]"
        if (-not $value) { $value = $Current }
        try {
            $value = ConvertTo-ContractedSpeed $value
            if ($value) { return $value }
        } catch { Write-Host $_.Exception.Message }
        Write-Host 'Informe a velocidade em Mbps (ex.: 1000 ou 500).'
    }
}
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
        $download = ''
        $upload = ''
        if ($configExists) {
            $existingLines = Get-Content $configPath
            $timezoneLine = $existingLines | Where-Object { $_ -match '^TZ=' } | Select-Object -First 1
            $serverLine = $existingLines | Where-Object { $_ -match '^IPERF3_SERVER=' } | Select-Object -First 1
            $portLine = $existingLines | Where-Object { $_ -match '^IPERF3_PORT=' } | Select-Object -First 1
            if ($timezoneLine) { $timezone = $timezoneLine -replace '^TZ=', '' }
            if ($serverLine) { $server = $serverLine -replace '^IPERF3_SERVER=', '' }
            if ($portLine) { $port = $portLine -replace '^IPERF3_PORT=', '' }
            $downloadLine = $existingLines | Where-Object { $_ -match '^BANDWIDTH_CONTRACTED_MBP=' } | Select-Object -First 1
            $uploadLine = $existingLines | Where-Object { $_ -match '^BANDWIDTH_CONTRACTED_UPLOAD_MBPS=' } | Select-Object -First 1
            if ($downloadLine) { $download = $downloadLine -replace '^BANDWIDTH_CONTRACTED_MBP=', '' }
            if ($uploadLine) { $upload = $uploadLine -replace '^BANDWIDTH_CONTRACTED_UPLOAD_MBPS=', '' }
        }
        $writeConfig = -not $configExists
        Write-Host ''
        Write-Host $(if ($configExists) { 'SpeedTester - confirmação da configuração atual' } else { 'SpeedTester - configuração inicial' })
        Write-Host "Fuso horário detectado: $windowsTimezone -> $timezone"
        Write-Host 'Runner: iperf3'
        Write-Host "Servidor de medição: $(if ($server) { "$server (porta $port)" } else { 'automático pela localização geográfica' })"
        Write-Host 'Servidor opcional: deixe vazio para seleção automática ou informe sua escolha.'
        if ($env:SPEEDTESTER_NONINTERACTIVE -ne '1') {
            $confirmation = Read-Host 'Confirmar esses parâmetros? [Y/n]'
            if ($confirmation -match '^[Nn]$') {
                $writeConfig = $true
                $timezoneInput = Read-Host "Fuso horário IANA [$timezone]"
                if ($timezoneInput) { $timezone = $timezoneInput }
                $serverInput = Read-Host "Servidor opcional [$server; digite auto para seleção automática]"
                if ($serverInput -eq 'auto') { $server = '' }
                elseif ($serverInput) { $server = $serverInput }
                if ($server) {
                    $portInput = Read-Host "Porta [$port]"
                    if ($portInput) { $port = $portInput }
                }
            } elseif ($configExists) {
                $writeConfig = $false
                Write-Host "Configuração confirmada: $configPath"
            }
        }
        if (Test-Path Env:SPEEDTESTER_CONTRACTED_DOWNLOAD_MBPS) { $download = $env:SPEEDTESTER_CONTRACTED_DOWNLOAD_MBPS }
        if (Test-Path Env:SPEEDTESTER_CONTRACTED_UPLOAD_MBPS) { $upload = $env:SPEEDTESTER_CONTRACTED_UPLOAD_MBPS }
        $download = Read-ContractedSpeed 'Download' $download
        $upload = Read-ContractedSpeed 'Upload' $upload
        # Always persist both keys, including migration of existing installations.
        $writeConfig = $true
        if (-not $download -or -not $upload) {
            Write-Warning 'Informe as velocidades contratadas para habilitar a repetição por percentual nas duas direções.'
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
            $content = $content -replace '(?m)^BANDWIDTH_CONTRACTED_(MBP|UPLOAD_MBPS)=.*\r?\n?', ''
            $content = $content.TrimEnd() + "`nBANDWIDTH_CONTRACTED_MBP=$download`nBANDWIDTH_CONTRACTED_UPLOAD_MBPS=$upload`n"
            $temporaryConfig = Join-Path $configDirectory ('.contract-' + [guid]::NewGuid().ToString('N') + '.tmp')
            try {
                [System.IO.File]::WriteAllText($temporaryConfig, $content, [System.Text.UTF8Encoding]::new($false))
                if (Test-Path $configPath) { [System.IO.File]::Replace($temporaryConfig, $configPath, [NullString]::Value) }
                else { [System.IO.File]::Move($temporaryConfig, $configPath) }
            } finally {
                if (Test-Path $temporaryConfig) { Remove-Item -LiteralPath $temporaryConfig -Force }
            }
            Write-Host "Configuração criada/atualizada em $configPath"
        }
        if (-not $server) { Write-Host 'Seleção automática por localização habilitada; nenhum servidor precisa ser informado.' }
    }
    $client = Join-Path $package.InstallLocation 'SpeedTesterClient.exe'
    $api = Join-Path $package.InstallLocation 'SpeedTesterAPI.exe'
    if ((Test-Path $client) -and (Test-Path $api)) {
        foreach ($taskName in @('speedtester-client.service', 'speedtester-api.service')) {
            if (Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue) {
                Stop-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
            }
        }
        $trigger = New-ScheduledTaskTrigger -AtLogOn
        $apiAction = New-ScheduledTaskAction -Execute $api
        Register-ScheduledTask -TaskName 'speedtester-api.service' -Action $apiAction -Trigger $trigger -Description 'SpeedTester local dashboard API' -Force | Out-Null
        $clientAction = New-ScheduledTaskAction -Execute $client
        Register-ScheduledTask -TaskName 'speedtester-client.service' -Action $clientAction -Trigger $trigger -Description 'SpeedTester broadband measurements' -Force | Out-Null
        Unregister-ScheduledTask -TaskName 'SpeedTester' -Confirm:$false -ErrorAction SilentlyContinue
        Start-ScheduledTask -TaskName 'speedtester-api.service'
        Start-ScheduledTask -TaskName 'speedtester-client.service'
    }
}
Write-Output 'SpeedTester instalado. A remoção é feita por uninstall-msix.ps1 ou Configurações do Windows.'
