#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Edson Angelo Carara
set -euo pipefail

CONFIG_HOME="${XDG_CONFIG_HOME:-$HOME/.config}"
CONFIG_DIR="$CONFIG_HOME/speedtester"
ENV_FILE="$CONFIG_DIR/speedtester.env"
TEMPLATE="${SPEEDTESTER_ENV_TEMPLATE:-$(cd "$(dirname "$0")" && pwd)/speedtester.env.example}"

die() { echo "[speedtester] $*" >&2; exit 1; }

detect_timezone() {
  local timezone=""
  if command -v timedatectl >/dev/null 2>&1; then
    timezone=$(timedatectl show --property=Timezone --value 2>/dev/null || true)
  fi
  if [[ -z "$timezone" && -r /etc/timezone ]]; then
    timezone=$(head -n 1 /etc/timezone 2>/dev/null || true)
  fi
  if [[ -z "$timezone" && -L /etc/localtime ]]; then
    timezone=$(readlink /etc/localtime | sed 's#^.*/zoneinfo/##')
  fi
  [[ "$timezone" =~ ^[A-Za-z0-9._+-]+(/[A-Za-z0-9._+-]+)*$ ]] || timezone="UTC"
  printf '%s\n' "$timezone"
}

read_tty() {
  local answer
  if [[ -r /dev/tty && -w /dev/tty ]]; then
    IFS= read -r answer < /dev/tty || true
    printf '%s' "$answer"
  fi
}

ask() {
  local prompt="$1" default="$2" answer
  if [[ ! -r /dev/tty || ! -w /dev/tty ]]; then
    printf '%s\n' "$default"
    return 0
  fi
  printf '%s' "$prompt" > /dev/tty
  answer=$(read_tty)
  printf '%s\n' "${answer:-$default}"
}

[[ -f "$TEMPLATE" ]] || die "modelo de configuração não encontrado: $TEMPLATE"
if [[ -e "$ENV_FILE" ]]; then
  echo "[speedtester] configuração existente preservada: $ENV_FILE"
  exit 0
fi

timezone=$(detect_timezone)
runner="iperf3"
server="${SPEEDTESTER_IPERF3_SERVER:-}"
port="${SPEEDTESTER_IPERF3_PORT:-5201}"

if [[ -r /dev/tty && -w /dev/tty ]]; then
  {
    printf '\nSpeedTester — configuração inicial\n'
    printf 'Fuso horário detectado: %s\n' "$timezone"
    printf 'Runner: %s\n' "$runner"
    printf 'Servidor iPerf3: %s\n' "${server:-não configurado}"
    printf 'Porta iPerf3: %s\n' "$port"
    printf 'O servidor iPerf3 precisa executar "iperf3 -s" e ser alcançável pela estação.\n'
    printf 'Confirmar esses parâmetros? [Y/n] '
  } > /dev/tty
  confirmation=$(read_tty)
  if [[ "$confirmation" =~ ^[Nn]$ ]]; then
    timezone=$(ask "Fuso horário IANA [$timezone]: " "$timezone")
    server=$(ask "Servidor iPerf3 (vazio para configurar depois): " "$server")
    port=$(ask "Porta iPerf3 [$port]: " "$port")
  fi
fi

[[ "$timezone" =~ ^[A-Za-z0-9._+-]+(/[A-Za-z0-9._+-]+)*$ ]] || die "fuso horário inválido: $timezone"
[[ "$server" =~ ^[A-Za-z0-9._:-]*$ ]] || die "servidor iPerf3 inválido: $server"
[[ "$port" =~ ^[0-9]+$ ]] && (( port >= 1 && port <= 65535 )) || die "porta iPerf3 inválida: $port"

mkdir -p "$CONFIG_DIR"
chmod 0700 "$CONFIG_DIR"
install -m 0600 "$TEMPLATE" "$ENV_FILE"
temporary_env="${ENV_FILE}.tmp.$$"
awk -v server="$server" -v port="$port" -v timezone="$timezone" '
  /^IPERF3_SERVER=/ { print "IPERF3_SERVER=" server; next }
  /^IPERF3_PORT=/ { print "IPERF3_PORT=" port; next }
  /^TZ=/ { print "TZ=" timezone; next }
  { print }
' "$ENV_FILE" > "$temporary_env"
chmod 0600 "$temporary_env"
mv "$temporary_env" "$ENV_FILE"

echo "[speedtester] configuração criada: $ENV_FILE"
if [[ -z "$server" ]]; then
  echo "[speedtester] atenção: IPERF3_SERVER não foi configurado; medições começarão após informar um servidor iPerf3."
fi
