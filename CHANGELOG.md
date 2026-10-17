# Changelog

Este arquivo registra mudanças relevantes do SpeedTester. O formato segue a
ideia de [Keep a Changelog](https://keepachangelog.com/pt-BR/1.1.0/) e
[Semantic Versioning](https://semver.org/lang/pt-BR/).

Projeto mantido por [Edson Angelo Carara (`ecarara`)](https://github.com/ecarara)
em <https://github.com/ecarara/SpeedTester>.

## [Unreleased]

### Adicionado

- contrato inicial do launcher desktop multiplataforma, com abertura segura do
  dashboard e controle nativo do serviço em Linux, Windows e macOS;
- símbolo quadrado, SVG, PNGs FreeDesktop, ICO Windows e ICNS macOS para o
  empacotamento desktop;
- integração Linux inicial com arquivo FreeDesktop, serviços `systemd --user`,
  instalador e desinstalador por usuário;
- opção `uninstall`/`--uninstall` exposta diretamente pelo instalador Linux;
- manifests e builders para `.deb`, `.rpm` e AppImage, com caminhos de remoção
  que preservam os dados do usuário;
- manifest, builder e instalação/remoção de Flatpak para o launcher do
  dashboard;
- `PKGBUILD` Arch/pacman, builder e callback de remoção preservando dados do
  usuário;
- manifesto MSIX, assets Windows, builder PowerShell e scripts de instalação/
  desinstalação com tarefa por usuário;
- bundle macOS com `Info.plist`, `.icns`, builder `.app`/`.dmg`, LaunchAgent e
  scripts de instalação/desinstalação preservando dados por padrão;
- workflow de release por tag com quality gate, SBOM SPDX 2.3, checksums,
  source archive e builds Linux `.deb`/`.rpm`, Flatpak, pacman, Windows/macOS;
- validador de conteúdo dos artefatos antes da publicação e guia de instalação
  desktop por sistema operacional;
- smoke test Linux isolado cobrindo instalação, upgrade idempotente e remoção
  completa sem tocar nos dados do usuário real;
- smoke tests Windows/macOS cobrindo instalação, upgrade e remoção com
  certificado temporário e HOME isolado, sem publicar credenciais de teste;
- builder do source archive `.tar.gz`, preservando o formato de distribuição
  existente;
- documentação do épico E-01 e testes unitários do launcher.

## [0.2.1] - 2026-10-11

- Snapshot e restauração do deploy usam rotulagem privada de bind mounts em
  hosts com SELinux, preservando as proteções do host.
- Validado no staging: backup consistente do banco persistente e integridade SQLite.

## [0.2.0] - 2026-10-11

- Login e perfis com sessões persistidas, expiração, CSRF e exportação protegida.
- Fila durável de webhooks, retentativas, avisos de recuperação e estados de entrega.
- Relatórios de observação sem alegação de SLA, com contadores reais de tráfego iPerf3.
- Deploy com gates CI/Sonar, digests, backup antes da migração e retorno automático.
- Ampliação de testes das falhas de rede e dos fluxos de operação.

### Adicionado

- análise SonarQube com cobertura Python e quality gate no CI da branch principal;
- auditoria de tentativas/retestes, recuperação de slots interrompidos e lease;
- gráficos interativos de 7/30/90 dias, distribuição e percentis p10/mediana/p95;
- testes de integração, restauração, interface responsiva e containers;
- diagnóstico de instalação, imagens AMD64/ARM64 e publicação em GHCR;
- backup externo criptografado com age/SSH e restauração validada com cópia anterior.

### Corrigido

- filtros antes da paginação, ordem por medições recentes e exportação completa;
- horário real da tentativa, escrita idempotente e conclusão atômica do slot;
- falso diagnóstico interno quando o gateway recusa probes TCP;
- cobertura separa slots futuros, sucessos e classificações; downtime une sobreposições;
- validação de configuração e liberação das conexões SQLite por transação.

### Segurança e migração

- aiohttp e FastAPI/Starlette atualizados; dependência requests sem uso removida;
- ações do GitHub fixadas por commit e segredos Sonar mantidos fora do código;
- schema 8 aditivo, preservando o histórico existente; faça backup antes da atualização.

## [0.1.0] - 2026-10-11

Primeira publicação pública, disponibilizada como pré-release para validação
de instalações e coleta em ambientes reais.

### Adicionado

- scheduler por quadrantes, reteste de anomalia e classificação de falhas;
- iPerf3 como runner principal, com métricas de qualidade e retransmissões;
- API, dashboard, comparação histórica, exportação e alertas;
- heartbeat do collector e backups consistentes do SQLite;
- documentação de arquitetura, operação, código, segurança e contribuição.
- screenshot do dashboard e demonstração local com dados sintéticos;
- exemplos de configuração e relatório de validação anonimizados para publicação.

### Segurança

- autenticação administrativa fail-closed, rate limit, execução sem root e
  imagens base fixadas por digest.

## Política de versões

Até a primeira versão estável, mudanças podem ser agrupadas em `Unreleased`.
Uma release deve atualizar este arquivo, documentar migrações e indicar as
versões suportadas de Python e Docker.
