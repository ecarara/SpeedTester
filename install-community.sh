#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Edson Angelo Carara
set -euo pipefail
if [[ "$(uname -s)" != Linux ]]; then echo 'Use Linux amd64 ou arm64 com systemd.' >&2; exit 1; fi
case "$(uname -m)" in x86_64|aarch64|arm64) ;; *) echo 'Arquitetura não suportada.' >&2; exit 1;; esac
if [[ $EUID -eq 0 ]]; then echo 'Execute como usuário normal, sem sudo.' >&2; exit 1; fi
if [[ ${1:-} != --server || $# -ne 2 ]]; then echo 'Uso: ./install-community.sh --server https://seu-server' >&2; exit 1; fi
command -v python3 >/dev/null || { echo 'Instale Python 3.11 ou superior.' >&2; exit 1; }
python3 -c 'import sys; assert sys.version_info >= (3,11), "Python 3.11+ requerido"'
command -v iperf3 >/dev/null || { echo 'Instale iperf3 pelo gerenciador de pacotes da distribuição.' >&2; exit 1; }
systemctl --user show-environment >/dev/null || { echo 'É necessária uma sessão systemd do usuário.' >&2; exit 1; }
project_dir="$(cd "$(dirname "$0")" && pwd)"
runtime_dir="$HOME/.local/lib/speedtester-client"
state_dir="$HOME/.local/share/speedtester-client"
unit_dir="$HOME/.config/systemd/user"
for task_dir in "$runtime_dir" "$state_dir" "$unit_dir"; do
  if [[ -L "$task_dir" ]]; then echo 'Diretório de instalação não pode ser um link simbólico.' >&2; exit 1; fi
done
if systemctl --user is-active --quiet speedtester-client.service; then
  echo 'O client já está ativo. Use o comando status; pare o serviço antes de reinstalar.' >&2; exit 1
fi
umask 077
mkdir -p "$runtime_dir" "$state_dir" "$unit_dir"
python3 -m venv "$runtime_dir/venv"
"$runtime_dir/venv/bin/python" -m pip install -r "$project_dir/app/requirements-community.txt" "$project_dir"
"$runtime_dir/venv/bin/speedtester-client" setup --server "$2" --state "$state_dir"
"$runtime_dir/venv/bin/speedtester-client" service-file --executable "$runtime_dir/venv/bin/speedtester-client" --state "$state_dir" > "$unit_dir/speedtester-client.service"
systemctl --user daemon-reload
systemctl --user enable --now speedtester-client.service
echo 'Client instalado. Consulte: systemctl --user status speedtester-client.service'
echo 'Para iniciar no boot sem login, o administrador pode habilitar linger para este usuário.'
