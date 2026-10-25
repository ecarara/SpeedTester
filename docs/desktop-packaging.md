# Épico E-01 — Empacotamento desktop multiplataforma

Consulte a [matriz de suporte e build](desktop-installation.md): runtime alvo
CPython 3.14 e compatibilidade por código-fonte com 3.11–3.14 (`>=3.11,<3.15`).

| Campo | Definição |
| --- | --- |
| Status | Em execução |
| Prioridade | P1 |
| Owner | Edson Angelo Carara (`ecarara`) |
| Repositório | `ecarara/SpeedTester` |
| Distribuição inicial | GitHub Releases, sem dependência de lojas |
| Plataformas | Windows, Linux e macOS |

Este é um épico de produto. Cada plataforma, formato de pacote e integração do
serviço deve ser entregue em uma issue ou pull request filho, com testes e
evidência própria. Não será tratado como uma única alteração monolítica.

## Objetivo

Distribuir o SpeedTester Client como aplicativo instalável, com identidade
visual e entrada no menu do sistema operacional, sem misturar a interface de
controle com o processo que executa as medições.

O instalador atual é Linux/headless: instala o Client comunitário, cria o
serviço `speedtester-client.service` do usuário e exige Python, iPerf3 e uma
sessão `systemd --user`. Esta especificação define a evolução para Windows,
Linux e macOS.

## Decisão de arquitetura

O produto será dividido em duas camadas:

1. **Engine/serviço**: executa agenda, pareamento, renovação de credenciais e
   medições.
2. **Launcher desktop**: abre o dashboard ou portal de configuração e mostra o
   estado do serviço. O launcher não executa medições diretamente.

Essa separação preserva o modo headless existente e permite que a instalação
continue funcionando em servidores sem ambiente gráfico.

## Matriz de distribuição

| Plataforma | Artefato inicial | Registro visual | Serviço de fundo |
| --- | --- | --- | --- |
| Windows 10/11 amd64 | MSIX; instalador `.exe` como fallback | AppUserModelId e assets MSIX | Agendador de Tarefas ou serviço de usuário |
| Linux amd64/arm64 | `.deb`, `.rpm`, AppImage e Flatpak | FreeDesktop `.desktop` + tema `hicolor` | `systemd --user` |
| macOS Intel/Apple Silicon | `.app` dentro de `.dmg` | `Info.plist` + `.icns` | `LaunchAgent` do usuário |
| Código-fonte | `SpeedTester-<versão>.tar.gz` | não aplicável | instalação manual/documentada |

O pacote deve permitir distribuição direta por GitHub Releases sem depender
das lojas. A publicação em lojas será uma etapa posterior.

## Contrato inicial do launcher

O módulo `app/desktop_launcher.py` é o ponto de entrada comum dos pacotes. Ele
aceita `open`, `status`, `start`, `stop` e `restart` e não invoca shell
concatenado. O uso local é:

```bash
PYTHONPATH=app python -m desktop_launcher open
PYTHONPATH=app python -m desktop_launcher status
```

A URL e o nome do serviço podem ser definidos sem alterar o pacote:

```bash
SPEEDTESTER_DASHBOARD_URL=http://127.0.0.1:8000/ \
SPEEDTESTER_SERVICE_NAME=speedtester-client.service \
PYTHONPATH=app python -m desktop_launcher open
```

O launcher valida a URL, rejeita credenciais embutidas e mantém as ações de
serviço específicas do sistema encapsuladas. O pacote gráfico futuro chamará
esse mesmo contrato, evitando uma implementação diferente para cada menu.

## Entregas filhas do épico

| ID | Entrega | Resultado esperado |
| --- | --- | --- |
| E-01.1 | Contrato do launcher | Interface para abrir o dashboard e consultar/iniciar/parar o serviço — implementado em `app/desktop_launcher.py` |
| E-01.2 | Identidade visual | Símbolo quadrado, SVG, PNG, ICO e ICNS com licença registrada |
| E-01.3 | Pacote Linux | Integração FreeDesktop, instalação por usuário e builders `.deb`, `.rpm`, AppImage, Flatpak e pacman em preparação/validação |
| E-01.4 | Pacote Windows | Manifesto MSIX, Menu Iniciar, tarefa por usuário e desinstalação implementados; build Windows pendente |
| E-01.5 | Pacote macOS | `.app`, `.dmg`, LaunchAgent, instalação/remoção e preparação para assinatura/notarização — implementação inicial concluída; build macOS pendente |
| E-01.6 | Pipeline de release | Workflow por tag com quality gate, source archive, SBOM SPDX, checksums e builds Linux/Windows/macOS — implementação inicial |
| E-01.7 | Validação multiplataforma | Validador de conteúdo dos artefatos antes da publicação; testes de instalação real nos runners ainda pendentes |
| E-01.8 | Documentação de usuário | Guia de instalação, atualização, permissões, desinstalação e verificação por sistema — implementação inicial |

## Dependências e limites

- O launcher depende do contrato de controle do Client, mas não pode acoplar o
  dashboard à implementação de um único sistema operacional.
- O serviço Linux existente deve continuar funcionando sem interface gráfica.
- Assinatura de código e notarização serão ativadas quando os certificados e
  contas correspondentes estiverem disponíveis; o build público não deve
  depender de segredo local para ser reproduzível.
- A publicação em App Store, Google Play e Microsoft Store não faz parte da
  primeira entrega do épico.
- O épico não altera o modelo de medição, o scheduler, os runners ou as regras
  de classificação de falhas.

## Integração de identidade visual

O arquivo mestre é `assets/branding/speedtester-logo-v1.png`. Para os pacotes,
deve existir também um símbolo quadrado derivado da marca e os formatos:

- SVG mestre para documentação e geração;
- PNGs Linux de 16, 32, 48, 64, 128, 256 e 512 px;
- `.ico` para Windows;
- `.icns` para macOS.

O símbolo não deve conter texto pequeno. Todos os arquivos de marca devem ter
licença compatível com `GPL-3.0-or-later` e origem registrada no inventário de
terceiros quando não forem desenhados pelo projeto.

## Regras por plataforma

### Linux

A primeira implementação está em `packaging/linux/`. O instalador por usuário
cria o payload em `~/.local/share/speedtester`, instala o launcher e os ícones
FreeDesktop e habilita os serviços `speedtester-api.service` e
`speedtester-client.service` com `systemd --user`:

```bash
./packaging/linux/install-user.sh
./packaging/linux/uninstall-user.sh
# alternativa: o instalador também oferece a ação de remoção
./packaging/linux/install-user.sh uninstall
```

O histórico e a configuração são preservados por padrão na remoção. A
remoção completa exige `SPEEDTESTER_PURGE_DATA=1`. O instalador não habilita
`loginctl linger` automaticamente.

O pacote deve instalar, no modo por usuário:

```text
~/.local/share/applications/speedtester.desktop
~/.local/share/icons/hicolor/<tamanho>/apps/speedtester.png
```

O arquivo `.desktop` deve usar `Name=SpeedTester`, `Icon=speedtester`,
`Terminal=false` e categorias `Network;Utility;`. Isso atende GNOME, KDE,
Omarchy, Cinnamon, XFCE e outros ambientes que implementam FreeDesktop.

O pacote também deve oferecer instalação de sistema para administradores, sem
alterar a configuração privada do usuário. A atualização não pode duplicar
entradas no menu nem substituir silenciosamente o pareamento.

Os builders de `.deb`, `.rpm`, AppImage e Arch/pacman ficam em `packaging/linux/`. Eles
incluem CPython 3.14 congelado no caso de DEB/RPM; `PYTHON` ou
`SPEEDTESTER_VENV` seleciona o ambiente de build. AppImage usa uma venv e Arch
usa dependências da distribuição. Os builders falham explicitamente quando a
ferramenta do formato não está disponível. O AppImage
tem instalador e desinstalador próprios; o `.deb` e o `.rpm` usam o ciclo de
remoção do gerenciador de pacotes e preservam os dados do usuário.

O Flatpak também faz parte da distribuição Linux. Ele é um launcher sandboxed
do dashboard, com ID `io.github.ecarara.SpeedTester`; o collector continua no
serviço Linux nativo porque a sandbox não deve controlar `systemd --user` por
meio de comandos privilegiados. O build usa um manifest Flatpak e a remoção é
feita pelo mesmo ID.

### Windows

O pacote Windows está em `packaging/windows/`. O builder produz os executáveis
do launcher/cliente com PyInstaller e empacota o MSIX com `MakeAppx.exe`. A
instalação registra o cliente como tarefa por usuário; a remoção desfaz a
tarefa e remove o pacote, preservando os dados por padrão.

```powershell
.\packaging\windows\build-launchers.ps1
.\packaging\windows\build-msix.ps1 -Version 0.3.0.0 -Architecture x64
.\packaging\windows\install-msix.ps1 .\dist\windows\SpeedTester-0.3.0.0-x64.msix
.\packaging\windows\uninstall-msix.ps1
```

O MSIX deve definir identidade, nome visual, ícone e atalho no Menu Iniciar.
O instalador deve suportar upgrade e remoção limpa. O serviço não deve ser
executado com privilégios administrativos quando o modo por usuário for
suficiente.

Os artefatos devem ser assinados quando houver certificado disponível. Sem
assinatura, a documentação deve informar que o Windows pode exibir alerta do
SmartScreen.

### macOS

O `.app` deve conter `Info.plist`, `CFBundleIdentifier`, versão, arquitetura e
ícone `.icns`, e deve ser instalado em `/Applications` pelo `.dmg`.

O serviço deve usar `LaunchAgent`, com comandos idempotentes para instalação,
atualização, parada e remoção. A distribuição pública deve prever assinatura
Developer ID e notarização; sem elas, o usuário verá avisos do Gatekeeper.

A implementação inicial está em `packaging/macos/`. O builder cria o launcher e
o cliente com PyInstaller, monta o bundle, gera `.app.zip` e `.dmg` por
arquitetura. O instalador copia para `/Applications` quando gravável (ou para
`~/Applications`), instala `~/Library/LaunchAgents/speedtester-client.service.plist`
e habilita o cliente na sessão do usuário. A remoção desfaz o LaunchAgent e
preserva os dados por padrão; `--purge-data` remove as preferências e dados
locais documentados.

```bash
APP_VERSION=0.3.0 OUTPUT_DIR=dist/macos ./packaging/macos/build-app.sh
./packaging/macos/install-dmg.sh /Applications/SpeedTester.app
./packaging/macos/uninstall-app.sh
./packaging/macos/uninstall-app.sh --purge-data
```

Também é possível chamar o builder com `make macos-package` em um host macOS
com PyInstaller instalado.

O nome do artefato identifica a arquitetura detectada (`arm64` ou `x86_64`).
O builder não assina nem notariza automaticamente; essas operações ficam para
o pipeline de release que possuir credenciais Apple.

### Pipeline de release

O workflow `.github/workflows/release.yml` é acionado somente por tags SemVer
no formato `v<major>.<minor>.<patch>`. Antes de publicar, executa `make check`,
gera `SpeedTester-<versão>.tar.gz`, um SBOM SPDX 2.3 e `SHA256SUMS`. Em seguida,
produz pacotes Linux `.deb`/`.rpm`, MSIX Windows x64 e bundles macOS Intel/Apple Silicon sem assinatura;
o pipeline executa smoke tests de instalação/upgrade/remoção Linux, Windows e
macOS antes de publicar os artefatos no GitHub Releases usando o `GITHUB_TOKEN`.

Os helpers [`build_sbom.py`](../scripts/build_sbom.py) e
[`generate_checksums.py`](../scripts/generate_checksums.py) não dependem de
serviços externos. O SBOM descreve o projeto e as dependências diretas do
`app/requirements.txt`; a licença e a origem transitiva devem continuar sendo
revisadas antes de cada release.

Os builders Linux `.deb`, `.rpm`, AppImage, Flatpak e pacman continuam
disponíveis em `packaging/linux/`. O workflow já publica `.deb` e `.rpm`; os
formatos Flatpak e pacman também são construídos pelo workflow, com runtime
Flatpak `24.08` e imagem Arch `base-devel-20260925.0.599509` fixados. O
AppImage permanece pendente até que o `appimagetool` e seu runtime sejam
fixados por checksum.

## Segurança e privacidade

- Nenhum pacote pode conter token, banco, backup ou configuração privada.
- O launcher não deve imprimir credenciais, IP público ou tokens nos logs.
- Downloads devem ser fixados por versão e verificados por SHA-256.
- Releases devem publicar checksum, SBOM e origem da revisão.
- A atualização deve preservar credenciais e estado, salvo em uma operação
  explícita de reparo ou desinstalação completa.
- O pacote deve manter os avisos GPL e o texto da licença.

## Fases de implementação

1. Criar launcher desktop e contrato de controle do serviço.
2. Preparar o símbolo quadrado e os formatos de ícone.
3. Implementar integração FreeDesktop e pacote Linux.
4. Implementar MSIX e testes do Menu Iniciar.
5. Implementar bundle `.app`, `.dmg` e `LaunchAgent`.
6. Adicionar builds reproduzíveis em GitHub Actions para Linux, Windows e
   macOS.
7. Testar instalação, upgrade, reinicialização, reparo, desinstalação e
   preservação do pareamento.
8. Publicar os artefatos no GitHub Releases e documentar a instalação.

## Critérios de aceite

- O SpeedTester aparece no Menu Iniciar do Windows com o logo.
- O SpeedTester aparece no menu de aplicativos do GNOME, KDE e Omarchy.
- O SpeedTester aparece em `/Applications` e no Launchpad do macOS.
- O serviço inicia após reinicialização conforme a política do sistema.
- Upgrade não apaga credenciais nem cria entradas duplicadas.
- Desinstalação remove o serviço e informa claramente o que acontece com os
  dados do usuário.
- Cada artefato é testado na arquitetura suportada e acompanhado de checksum.
- A distribuição continua compatível com GPL-3.0-or-later.

## Definição de pronto do épico

O épico somente será encerrado quando todas as entregas E-01.1 a E-01.8
estiverem concluídas, os artefatos tiverem sido testados nas arquiteturas
suportadas e houver uma release pública contendo checksums, SBOM, instruções e
avisos sobre assinatura/notarização. O serviço headless existente deve
continuar aprovado no CI e nenhuma credencial de usuário pode aparecer nos
pacotes ou nos logs de instalação.
