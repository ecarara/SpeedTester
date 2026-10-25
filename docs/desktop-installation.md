# Instalação desktop do SpeedTester

Este guia cobre os artefatos publicados no GitHub Releases. O SpeedTester é
distribuído sob `GPL-3.0-or-later`; os pacotes não incluem banco, token ou
configuração privada.

## Suporte e build

| Caminho | Python |
| --- | --- |
| Código-fonte / instalador Linux | CPython `>=3.11,<3.15`; preferência por 3.14 |
| Matriz de testes CI | 3.11, 3.12, 3.13 e 3.14 |
| Builds nativos Windows, macOS, DEB/RPM | CPython 3.14 |
| Arch | Python e bibliotecas da distribuição, `>=3.11,<3.15` |
| Flatpak | Launcher do dashboard; collector instalado no host |

Python 3.15 ainda não é suportado. Cada release exige build e smoke test dos
artefatos nativos no sistema e arquitetura de destino.

DEB/RPM incluem CPython 3.14 e não dependem do Python do host. Os builds
oficiais usam Ubuntu 22.04 como baseline de glibc; glibc não é incorporada ao
runtime. A instalação por código-fonte aceita CPython 3.11–3.14.

## Escolha do artefato

| Sistema | Artefato recomendado | Entrada no menu | Serviço de medições |
| --- | --- | --- | --- |
| Windows 10/11 x64 | `.msix` | Menu Iniciar | Tarefa por usuário |
| Debian/Ubuntu | `.deb` | GNOME/KDE/FreeDesktop | `systemd --user` |
| Fedora/RHEL compatível | `.rpm` | GNOME/KDE/FreeDesktop | `systemd --user` |
| Arch | `.pkg.tar.zst` | GNOME/KDE/Omarchy/FreeDesktop | `systemd --user` |
| Linux portátil | AppImage ou Flatpak | Menu do ambiente gráfico | Flatpak é apenas launcher |
| macOS Intel | `.dmg` `x86_64` | Applications/Launchpad | LaunchAgent do usuário |
| macOS Apple Silicon | `.dmg` `arm64` | Applications/Launchpad | LaunchAgent do usuário |
| Qualquer sistema com Python | `SpeedTester-<versão>.tar.gz` | manual | instalação manual |

## Windows

No PowerShell, instale o MSIX:

```powershell
Add-AppxPackage .\SpeedTester-<versao>-x64.msix
```

Para configurar o fuso horário, o servidor iPerf3 e confirmar os parâmetros
antes de registrar a tarefa, use o instalador incluído:

```powershell
.\packaging\windows\install-msix.ps1 .\SpeedTester-<versao>-x64.msix
```

O aplicativo aparece no Menu Iniciar. A remoção pode ser feita em
Configurações > Aplicativos ou com:

```powershell
.\uninstall-msix.ps1
```

O instalador registra a API local e o collector como tarefas do usuário. O
launcher aguarda a API ficar saudável antes de abrir o dashboard.

Sem assinatura de código, o Windows pode exibir aviso do SmartScreen. O
certificado usado para uma release nunca deve ser incluído no repositório.

## Linux

Para `.deb` e `.rpm`, use o gerenciador da distribuição. Para instalação por
usuário sem pacote nativo:

```bash
./packaging/linux/install-user.sh
./packaging/linux/install-user.sh uninstall
```

O instalador seleciona 3.14 preferencialmente, com fallback para 3.13–3.11,
mesmo quando `python3` aponta para 3.15. Para fixar o interpretador, defina
`SPEEDTESTER_PYTHON=/caminho/python3.14`. O bootstrap e o script Linux usam o
mesmo caminho validado. Arch usa as dependências da distribuição dentro dos
limites `>=3.11,<3.15`. Consulte os [builders Linux](../packaging/linux/README.md)
para preparar os artefatos.

O arquivo `.desktop` e os ícones hicolor fazem o aplicativo aparecer em GNOME,
KDE, Omarchy, Cinnamon, XFCE e ambientes compatíveis com FreeDesktop. A
desinstalação remove serviços e atalhos, preservando configuração e histórico.
Ao abrir o aplicativo pelo menu, o launcher inicia o `speedtester-api.service`
quando necessário e aguarda o endpoint local `/health` antes de abrir o
navegador. Assim, a primeira execução não deve abrir uma página inacessível em
`127.0.0.1:8000`.
Para remover também os dados:

```bash
SPEEDTESTER_PURGE_DATA=1 ./packaging/linux/uninstall-user.sh
```

O CI também executa um smoke test com `HOME`, configuração, dados e serviços
em um diretório temporário. Esse teste cobre instalação, upgrade idempotente,
preservação de configuração e remoção completa sem tocar no usuário real.

O Flatpak é um launcher sandboxed do dashboard. O collector precisa ser
instalado como serviço nativo para executar medições e controlar
`systemd --user`.

## macOS

Abra o `.dmg`, arraste `SpeedTester.app` para `Applications` e execute
`Install SpeedTester.command` que acompanha a imagem. O script instala o
LaunchAgent do usuário e inicia o cliente após o login. A remoção pode ser
feita executando `Uninstall SpeedTester.command` no `.dmg` ou:

```bash
./packaging/macos/uninstall-app.sh
./packaging/macos/uninstall-app.sh --purge-data
```

A remoção normal preserva dados. O modo `--purge-data` remove preferências e
dados locais documentados. Artefatos sem assinatura/notarização podem exigir
confirmação adicional do Gatekeeper.

Na primeira instalação, `Install SpeedTester.command` detecta o fuso horário,
mostra os parâmetros e pede confirmação. A configuração fica em
`~/Library/Application Support/SpeedTester/speedtester.env`.

O parâmetro interno `SPEEDTESTER_SKIP_LAUNCHCTL=1` existe apenas para o smoke
test do CI, que valida cópia, upgrade, plist e remoção em um HOME temporário;
instalações reais não devem usá-lo.

## Código-fonte `.tar.gz`

O formato de código-fonte continua disponível:

```bash
tar -xzf SpeedTester-<versao>.tar.gz
cd SpeedTester-<versao>
python3.14 -m venv .venv
. .venv/bin/activate
python -m pip install -r app/requirements.txt
```

Consulte [Operação](operations.md) para configuração de `IPERF3_SERVER`,
`API_ADMIN_TOKEN`, banco e diagnóstico de conectividade.

## Verificação de integridade

Baixe `SHA256SUMS` junto com os artefatos e valide antes da instalação:

```bash
sha256sum -c SHA256SUMS
```

O projeto também publica um SBOM SPDX para registrar a versão das dependências
diretas incluídas na release.
