#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Edson Angelo Carara
set -euo pipefail

CONFIG_DIR="${SPEEDTESTER_CONFIG_DIR:-${XDG_CONFIG_HOME:-$HOME/.config}/speedtester}"
ENV_FILE="${SPEEDTESTER_ENV_FILE:-$CONFIG_DIR/speedtester.env}"
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
  if [[ "${SPEEDTESTER_NONINTERACTIVE:-0}" == "1" || ! -r /dev/tty || ! -w /dev/tty ]]; then
    printf '%s\n' "$default"
    return 0
  fi
  printf '%s' "$prompt" > /dev/tty
  answer=$(read_tty)
  printf '%s\n' "${answer:-$default}"
}

read_setting() {
  local key="$1"
  awk -F= -v key="$key" '$1 == key { sub(/^[^=]*=/, ""); print; exit }' "$ENV_FILE"
}

[[ -f "$TEMPLATE" ]] || die "modelo de configuração não encontrado: $TEMPLATE"
existing=0
overridden=0
if [[ -e "$ENV_FILE" ]]; then
  [[ -f "$ENV_FILE" ]] || die "caminho de configuração não é um arquivo: $ENV_FILE"
  existing=1
fi

timezone=$(detect_timezone)
runner="iperf3"
server="${SPEEDTESTER_IPERF3_SERVER:-}"
port="${SPEEDTESTER_IPERF3_PORT:-5201}"
country="${SPEEDTESTER_COUNTRY_CODE:-}"
city="${SPEEDTESTER_CITY:-}"

if (( existing )); then
  timezone="$(read_setting TZ || true)"
  runner="$(read_setting SPEEDTEST_RUNNER || true)"
  server="$(read_setting IPERF3_SERVER || true)"
  port="$(read_setting IPERF3_PORT || true)"
  country="$(read_setting SPEEDTESTER_COUNTRY_CODE || true)"
  city="$(read_setting SPEEDTESTER_CITY || true)"
  timezone="${timezone:-$(detect_timezone)}"
  runner="${runner:-iperf3}"
  port="${port:-5201}"
  if [[ -n "${SPEEDTESTER_IPERF3_SERVER+x}" && "$server" != "$SPEEDTESTER_IPERF3_SERVER" ]]; then
    server="$SPEEDTESTER_IPERF3_SERVER"
    overridden=1
  fi
  if [[ -n "${SPEEDTESTER_IPERF3_PORT+x}" && "$port" != "$SPEEDTESTER_IPERF3_PORT" ]]; then
    port="$SPEEDTESTER_IPERF3_PORT"
    overridden=1
  fi
  if [[ "${SPEEDTESTER_CONFIRM_EXISTING:-0}" != "1" && "$overridden" == "0" ]]; then
    echo "[speedtester] configuração existente preservada: $ENV_FILE"
    exit 0
  fi
fi

if [[ "${SPEEDTESTER_NONINTERACTIVE:-0}" != "1" && -r /dev/tty && -w /dev/tty ]]; then
  {
    if (( existing )); then
      printf '\nSpeedTester — confirmação da configuração atual\n'
    else
      printf '\nSpeedTester — configuração inicial\n'
    fi
    printf 'Fuso horário detectado: %s\n' "$timezone"
    printf 'Runner: %s\n' "$runner"
    if [[ -n "$server" ]]; then
      printf 'Servidor de medição escolhido: %s (porta %s)\n' "$server" "$port"
    else
      printf 'Servidor de medição: automático pela localização geográfica\n'
    fi
    printf 'Localização: %s\n' "${city:-detectar automaticamente pela conexão}${country:+, $country}"
    printf 'O servidor é opcional. Deixe vazio para seleção automática; informe um para usar sua escolha.\n'
    printf 'Confirmar esses parâmetros? [Y/n] '
  } > /dev/tty
  confirmation=$(read_tty)
  if [[ "$confirmation" =~ ^[Nn]$ ]]; then
    timezone=$(ask "Fuso horário IANA [$timezone]: " "$timezone")
    country=$(ask "País (código, ex.: BR; vazio para detectar): " "$country")
    city=$(ask "Cidade (vazio para detectar): " "$city")
    printf 'Servidor opcional [%s; digite auto para seleção automática]: ' "${server:-automático}" > /dev/tty
    selected_server=$(read_tty)
    if [[ "$selected_server" == "auto" ]]; then server=""; elif [[ -n "$selected_server" ]]; then server="$selected_server"; fi
    if [[ -n "$server" ]]; then port=$(ask "Porta [$port]: " "$port"); fi
  elif (( existing && ! overridden )); then
    echo "[speedtester] configuração confirmada: $ENV_FILE"
    exit 0
  fi
fi

[[ "$timezone" =~ ^[A-Za-z0-9._+-]+(/[A-Za-z0-9._+-]+)*$ ]] || die "fuso horário inválido: $timezone"
[[ "$server" =~ ^[A-Za-z0-9._:-]*$ ]] || die "servidor iPerf3 inválido: $server"
[[ "$port" =~ ^[0-9]+$ ]] && (( port >= 1 && port <= 65535 )) || die "porta iPerf3 inválida: $port"
[[ "$country" =~ ^[A-Za-z]{2}$ || -z "$country" ]] || die "país deve ter duas letras"
[[ -z "$city" || -n "$country" ]] || die "confirme também o país ao informar a cidade"
[[ "$city" != *$'\n'* && "$city" != *$'\r'* && "$city" != *'"'* && "$city" != *"'"* && "$city" != *'\\'* ]] || die "cidade inválida"

mkdir -p "$CONFIG_DIR"
chmod 0700 "$CONFIG_DIR"
if (( ! existing )); then
  install -m 0600 "$TEMPLATE" "$ENV_FILE"
fi
temporary_env="${ENV_FILE}.tmp.$$"
awk -v server="$server" -v port="$port" -v timezone="$timezone" -v country="$country" -v city="$city" '
  /^IPERF3_SERVER=/ { print "IPERF3_SERVER=" server; next }
  /^IPERF3_PORT=/ { print "IPERF3_PORT=" port; next }
  /^TZ=/ { print "TZ=" timezone; next }
  /^SPEEDTESTER_COUNTRY_CODE=/ { next }
  /^SPEEDTESTER_CITY=/ { next }
  { print }
  END { print "SPEEDTESTER_COUNTRY_CODE=" country; print "SPEEDTESTER_CITY=" city }
' "$ENV_FILE" > "$temporary_env"
chmod 0600 "$temporary_env"
mv "$temporary_env" "$ENV_FILE"

echo "[speedtester] configuração criada: $ENV_FILE"
if [[ -z "$server" ]]; then
  echo "[speedtester] seleção automática por localização habilitada; nenhum servidor precisa ser informado."
fi
