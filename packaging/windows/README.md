# Empacotamento Windows

O pacote Windows usa MSIX para aparecer no Menu Iniciar e mantém o cliente de
medições como tarefa por usuário no Agendador de Tarefas. O launcher e o
cliente são executáveis independentes, produzidos com PyInstaller.

## Build

Em um runner Windows com CPython 3.14, PyInstaller e Windows SDK:

```powershell
.\packaging\windows\build-launchers.ps1
.\packaging\windows\build-msix.ps1 -Version 0.3.0.0 -Architecture x64
```

Para assinar, forneça um certificado cujo Subject corresponda ao Publisher do
manifesto:

```powershell
.\packaging\windows\build-msix.ps1 -Sign `
  -CertificatePath .\certs\speedtester.pfx
```

Sem assinatura, o Windows pode bloquear a instalação ou exibir alerta do
SmartScreen. Certificados e senhas não pertencem ao repositório.

## Instalação e remoção

```powershell
.\packaging\windows\install-msix.ps1 .\dist\windows\SpeedTester-0.3.0.0-x64.msix
.\packaging\windows\uninstall-msix.ps1
```

O instalador detecta o fuso horário do Windows, converte-o para um identificador
IANA, mostra os parâmetros e pede confirmação antes de registrar a tarefa. A
configuração é persistida em `%APPDATA%\SpeedTester\speedtester.env` e é
preservada em atualizações. Para instalação gráfica direta pelo MSIX, execute
o instalador PowerShell uma vez antes de abrir o aplicativo.

Em cada instalação/atualização, o script pede também download e upload
contratados em Mbps, mesmo quando os demais parâmetros são confirmados.
Enter mantém valores existentes; campos ausentes são solicitados. A gravação
é atômica e preserva outras opções. Depois, as tarefas da API e do collector
são iniciadas novamente para carregar a configuração. Para execução não
interativa, use `$env:SPEEDTESTER_CONTRACTED_DOWNLOAD_MBPS` e
`$env:SPEEDTESTER_CONTRACTED_UPLOAD_MBPS`; valores desconhecidos geram aviso,
não uma estimativa inventada do contrato.

São registradas duas tarefas por usuário: a API local e o collector. O launcher
usa essas tarefas para abrir o dashboard e as medições compartilham a mesma
configuração e banco local.

O desinstalador remove a tarefa e o pacote, mas preserva dados por padrão.
Para uma remoção completa:

```powershell
.\packaging\windows\uninstall-msix.ps1 -PurgeData
```

O source archive `.tar.gz` continua sendo publicado para instalações e
auditorias que não usam um instalador nativo:

```bash
./scripts/build-source-tarball.sh
```
