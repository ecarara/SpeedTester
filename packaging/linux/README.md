# Integração Linux

Esta pasta contém a primeira implementação da integração desktop Linux do
SpeedTester. Ela usa somente padrões FreeDesktop e `systemd --user`, portanto
é compatível com GNOME, KDE, Omarchy, Cinnamon, XFCE e ambientes equivalentes.

## Instalação por usuário

Na raiz do checkout:

```bash
./packaging/linux/install-user.sh
```

O instalador:

- cria uma cópia isolada em `~/.local/share/speedtester`;
- cria um ambiente Python privado e instala `app/requirements.txt`;
- instala o launcher, o arquivo `.desktop` e os ícones hicolor;
- instala e habilita `speedtester-api.service` e `speedtester-client.service`;
- cria a configuração inicial em
  `~/.config/speedtester/speedtester.env`, detecta o fuso horário local e pede
  confirmação dos parâmetros antes de iniciar os serviços;
- preserva um arquivo de configuração existente em
  `~/.config/speedtester/speedtester.env`.

Requisitos: Python 3, `python3-venv`, `iperf3`, `systemd --user` e acesso de
rede para instalar as dependências Python. O instalador confirma o fuso e o
modo de seleção. `IPERF3_SERVER` vazio seleciona o destino por localização
geográfica; preencher host/porta fixa a escolha do usuário. Atualizações
preservam essa escolha. Consulte [seleção do servidor](../../docs/server-selection.md).

Para remover o aplicativo sem apagar histórico e configuração:

```bash
./packaging/linux/uninstall-user.sh
# alternativa equivalente
./packaging/linux/install-user.sh uninstall
```

Para remover também configuração e banco local, use explicitamente
`SPEEDTESTER_PURGE_DATA=1`. O instalador não habilita `loginctl linger`
automaticamente: em máquinas sem sessão gráfica, o administrador deve decidir
se quer manter um serviço de usuário após logout.

## Integração FreeDesktop

O arquivo instalado em `~/.local/share/applications/speedtester.desktop` usa
`Icon=speedtester` e os PNGs em `~/.local/share/icons/hicolor/<tamanho>/apps`.
Não há dependência de GNOME ou KDE específicos.

Os formatos `.deb`, `.rpm` e AppImage são montados sobre este mesmo payload
com builders reproduzíveis. O Flatpak usa um launcher sandboxed separado. Os
builders exigem uma virtualenv preparada em
`SPEEDTESTER_VENV` e a ferramenta nativa de cada formato:

```bash
SPEEDTESTER_VENV=.venv ./packaging/linux/build-deb.sh
SPEEDTESTER_VENV=.venv ./packaging/linux/build-rpm.sh
SPEEDTESTER_VENV=.venv ./packaging/linux/build-appimage.sh
./packaging/linux/build-pacman.sh
```

O `.deb` e o `.rpm` removem arquivos de sistema e recarregam o serviço do
usuário durante a remoção, mas preservam os dados do usuário. O pacote Arch
usa `makepkg` e a remoção é feita por `pacman -R speedtester`, com configuração
e histórico preservados. O AppImage pode
ser integrado ao menu com:

```bash
./packaging/linux/appimage/install-appimage.sh dist/SpeedTester-*.AppImage
./packaging/linux/appimage/install-appimage.sh --uninstall
```

Os builders não baixam dependências silenciosamente nem inventam um runtime:
o ambiente Python deve ser criado pelo pipeline de build e então é incorporado
ao artefato correspondente.

O launcher verifica o dashboard local antes de abrir o navegador. Se
`speedtester-api.service` ainda não estiver ativo, ele o inicia e aguarda
`http://127.0.0.1:8000/health`; em caso de falha, informa que o serviço não
ficou saudável em vez de abrir uma página inacessível.

O dashboard local não exige usuário ou senha: os serviços são limitados a
`127.0.0.1` e ativam `SPEEDTESTER_LOCAL_MODE`. A autenticação continua
obrigatória no Server de produção; operações administrativas locais continuam
protegidas pelo token administrativo.

## Flatpak

O Flatpak é um launcher gráfico do dashboard. Ele segue o modelo sandboxed e
não tenta controlar `systemd --user` de dentro da sandbox; o cliente de
medições continua sendo instalado pelo fluxo nativo Linux. O manifest está em
`packaging/linux/flatpak/io.github.ecarara.SpeedTester.yml` e usa o portal
desktop para abrir o dashboard.

```bash
./packaging/linux/build-flatpak.sh
./packaging/linux/flatpak/install-flatpak.sh \
  dist/io.github.ecarara.SpeedTester-0.3.0.flatpak
./packaging/linux/flatpak/uninstall-flatpak.sh
```

O identificador estável é `io.github.ecarara.SpeedTester`. A instalação e a
remoção usam os comandos oficiais `flatpak install` e `flatpak uninstall`.
