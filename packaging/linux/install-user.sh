#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Edson Angelo Carara
set -euo pipefail

SOURCE_DIR="${SPEEDTESTER_SOURCE_DIR:-$(cd "$(dirname "$0")/../.." && pwd)}"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
DATA_HOME="${XDG_DATA_HOME:-$HOME/.local/share}"
CONFIG_HOME="${XDG_CONFIG_HOME:-$HOME/.config}"
INSTALL_ROOT="${SPEEDTESTER_INSTALL_ROOT:-$DATA_HOME/speedtester}"
CONFIG_DIR="$CONFIG_HOME/speedtester"
BIN_DIR="$DATA_HOME/speedtester/bin"
APPLICATION_DIR="$DATA_HOME/applications"
SYSTEMD_DIR="$CONFIG_HOME/systemd/user"
ICON_ROOT="$DATA_HOME/icons/hicolor"
ENV_FILE="$CONFIG_DIR/speedtester.env"

die() { echo "[speedtester] $*" >&2; exit 1; }

case "${1:-}" in
  uninstall|--uninstall)
    shift
    [[ $# -eq 0 ]] || die "uso: $0 [uninstall|--uninstall]"
    exec "$SCRIPT_DIR/uninstall-user.sh"
    ;;
  "")
    ;;
  *)
    die "uso: $0 [uninstall|--uninstall]"
    ;;
esac

command -v python3 >/dev/null || die "python3 não encontrado"
command -v iperf3 >/dev/null || die "iperf3 não encontrado; instale-o antes de continuar"
[[ -d "$SOURCE_DIR/app" ]] || die "fonte inválida: $SOURCE_DIR"

mkdir -p "$INSTALL_ROOT" "$CONFIG_DIR" "$BIN_DIR" "$APPLICATION_DIR" "$SYSTEMD_DIR"
rm -rf "$INSTALL_ROOT/app"
cp -R "$SOURCE_DIR/app" "$INSTALL_ROOT/app"
python3 -m venv "$INSTALL_ROOT/venv"
"$INSTALL_ROOT/venv/bin/python" -m pip install --disable-pip-version-check --no-input -r "$SOURCE_DIR/app/requirements.txt"
install -m 0755 "$SOURCE_DIR/packaging/linux/speedtester-launcher" "$BIN_DIR/speedtester-launcher"

if [[ ! -e "$ENV_FILE" ]]; then
  umask 077
  cat > "$ENV_FILE" <<'EOF'
# SpeedTester per-user configuration. Set IPERF3_SERVER before starting measurements.
DB_PATH=%h/.local/share/speedtester/data/speedtester.db
SPEEDTEST_RUNNER=iperf3
IPERF3_SERVER=
IPERF3_PORT=5201
IPERF3_DURATION_SECONDS=10
IPERF3_PARALLEL_STREAMS=5
MEASUREMENT_TIMEOUT_SECONDS=60
MEASUREMENTS_PER_QUADRANT=2
TZ=America/Sao_Paulo
API_BIND_ADDRESS=127.0.0.1
API_PORT=8000
API_REQUIRE_LOGIN=false
API_REQUIRE_ADMIN_TOKEN=true
EOF
fi
mkdir -p "$DATA_HOME/speedtester/data"

for unit in speedtester-api.service speedtester-client.service; do
  install -m 0644 "$SOURCE_DIR/packaging/linux/$unit" "$SYSTEMD_DIR/$unit"
done

for size in 16 32 48 64 128 256 512; do
  target="$ICON_ROOT/$size/apps"
  mkdir -p "$target"
  install -m 0644 "$SOURCE_DIR/assets/icons/hicolor/$size/apps/speedtester.png" "$target/speedtester.png"
done

launcher="$BIN_DIR/speedtester-launcher"
escaped_launcher=$(printf '%s' "$launcher" | sed 's/[&|]/\\&/g')
sed "s|@SPEEDTESTER_LAUNCHER@|$escaped_launcher|g" \
  "$SOURCE_DIR/packaging/linux/speedtester.desktop.in" > "$APPLICATION_DIR/speedtester.desktop"
chmod 0644 "$APPLICATION_DIR/speedtester.desktop"

if command -v update-desktop-database >/dev/null; then
  update-desktop-database "$APPLICATION_DIR" >/dev/null 2>&1 || true
fi

if [[ "${SPEEDTESTER_SKIP_SYSTEMD:-0}" != "1" ]] && command -v systemctl >/dev/null && systemctl --user show-environment >/dev/null 2>&1; then
  if systemctl --user daemon-reload && systemctl --user enable --now speedtester-api.service speedtester-client.service; then
    echo "[speedtester] serviços systemd do usuário habilitados"
  else
    echo "[speedtester] sessão systemd --user não aceitou os serviços; arquivos instalados, ative-os depois" >&2
  fi
else
  echo "[speedtester] sessão systemd --user indisponível; arquivos instalados, ative-os depois"
fi

echo "[speedtester] instalado em $INSTALL_ROOT"
echo "[speedtester] configure IPERF3_SERVER em $ENV_FILE e execute o launcher pelo menu"
