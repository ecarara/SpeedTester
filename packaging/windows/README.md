# Empacotamento Windows

O pacote Windows usa MSIX para aparecer no Menu Iniciar e mantém o cliente de
medições como tarefa por usuário no Agendador de Tarefas. O launcher e o
cliente são executáveis independentes, produzidos com PyInstaller.

## Build

Em um runner Windows com Python, PyInstaller e Windows SDK:

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
