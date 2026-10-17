#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Edson Angelo Carara
set -euo pipefail
if [[ "$(uname -s)" != Linux ]]; then echo 'Use Linux amd64 ou arm64 com systemd.' >&2; exit 1; fi
case "$(uname -m)" in x86_64|aarch64|arm64) ;; *) echo 'Arquitetura não suportada.' >&2; exit 1;; esac
if [[ $EUID -eq 0 ]]; then echo 'Execute como usuário normal, sem sudo.' >&2; exit 1; fi
if [[ ${1:-} != --server || $# -ne 2 ]]; then echo 'Uso: ./install-community.sh --server https://seu-server' >&2; exit 1; fi
python_bin=''
for candidate in python3 python3.13 python3.12 python3.11; do
  if command -v "$candidate" >/dev/null && "$candidate" -c 'import sys; assert (3,11) <= sys.version_info[:2] <= (3,13)' >/dev/null 2>&1; then
    python_bin="$candidate"
    break
  fi
done
if [[ -z "$python_bin" ]]; then echo 'Instale Python 3.11, 3.12 ou 3.13 com venv (ex.: python3.13).' >&2; exit 1; fi
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
"$python_bin" -m venv "$runtime_dir/venv"
"$runtime_dir/venv/bin/python" -m pip install -r "$project_dir/app/requirements-community.txt" "$project_dir"
"$runtime_dir/venv/bin/speedtester-client" setup --server "$2" --state "$state_dir"
"$runtime_dir/venv/bin/speedtester-client" service-file --executable "$runtime_dir/venv/bin/speedtester-client" --state "$state_dir" > "$unit_dir/speedtester-client.service"
systemctl --user daemon-reload
systemctl --user enable --now speedtester-client.service
echo 'Client instalado. Consulte: systemctl --user status speedtester-client.service'
echo 'Para iniciar no boot sem login, o administrador pode habilitar linger para este usuário.'
