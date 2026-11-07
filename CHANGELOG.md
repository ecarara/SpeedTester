# Changelog

Este arquivo registra mudanças relevantes do SpeedTester. O formato segue a
ideia de [Keep a Changelog](https://keepachangelog.com/pt-BR/1.1.0/) e
[Semantic Versioning](https://semver.org/lang/pt-BR/).

Projeto mantido por [Edson Angelo Carara (`ecarara`)](https://github.com/ecarara)
em <https://github.com/ecarara/SpeedTester>.

## [Unreleased]

## [0.4.50] - 2026-11-07

### Corrigido

- backup e deploy compatíveis com SQLite em WAL: o volume do banco é montado
  em leitura/escrita durante o snapshot e as conexões de origem usam `mode=rw`,
  permitindo criar o arquivo `-shm` quando necessário;
- backup nativo e verificação de integridade do Client também aceitam bancos em
  WAL sem falhar com `unable to open database file`.

## [0.4.49] - 2026-11-07

### Alterado

- SQLite do painel/coletor usa WAL, `busy_timeout` e conexão persistente por
  thread, reduzindo bloqueios entre leitura e gravação;
- dashboard reduz o polling para 30 segundos e pausa quando a aba não está
  visível;
- configuração da API rejeita modo local com bind não-loopback, exige cookie
  seguro quando `API_PUBLIC_ORIGIN` é HTTPS e remove o antigo `API_HOST` morto.

## [0.4.48] - 2026-11-07

### Corrigido

- corrigidos dois bugs bloqueadores em `scripts/compare_runners.py`: o script
  agora usa `Iperf3Target` em vez dos parâmetros removidos `iperf3_server` e
  `iperf3_port`;
- reduzida a complexidade cognitiva de nove funções em `server.py`,
  `collector.py`, `speedtest_runner.py`, `ookla_runner.py`, `settings.py`,
  `check_license.py`, `check_publication.py` e `doctor.py`;
- literais duplicados substituídos por constantes, parâmetros não usados
  removidos e timeouts convertidos para `asyncio.timeout`;
- IPs privados de `check_publication.py` derivados de inteiros, eliminando os
  achados S1313 sem suprimir a verificação;
- simplificado o retry de download de fontes nativas do iPerf3;
- atualizado o digest fixado de `python:3.14.10-slim-trixie` para corrigir
  CVE-2026-109518 em `apt`/`libapt-pkg7.0` (3.0.3 → 3.0.4).

### Qualidade e atualização

- SonarQube com Quality Gate aprovado: zero bugs, vulnerabilidades, code smells
  e hotspots; ratings **A** em Reliability, Security e Maintainability;
- cobertura de 83,6% no total, 84,8% no código novo e 0% de duplicação;
- adicionados testes de higiene para os scripts refatorados, além da validação
  de GUI e do fluxo E2E do dashboard;
- atualização sem migração de schema; instalação, configuração e dados são
  preservados. Distribuição GPL-3.0-or-later nos mesmos formatos.

## [0.4.47] - 2026-11-01

### Corrigido

- instaladores POSIX (Linux/macOS) e PowerShell perguntam e persistem download
  e upload contratados em Mbps também na atualização; preservam opções anteriores,
  validam os valores e recarregam os serviços gerenciados;
- anomalias de download **ou upload** disparam um único reteste completo nos três
  runners; só a segunda tentativa é representativa, mesmo se continuar baixa;
- contrato de upload é persistido com a amostra e as tentativas, exposto na API
  e acrescentado por migração aditiva para schema 11, sem alterar o histórico;
- seleção automática iPerf3 recupera também recusa/servidor ocupado no download:
  descarta o upload parcial e repete ambas as direções no próximo destino
  geográfico, sem misturar métricas nem reiniciar o prazo total de 60 segundos;
- recusa/servidor iPerf3 ocupado é classificado como falha do destino de medição
  (`MEASUREMENT · server`), sem atribuir a falha à conexão da operadora;
- launcher desktop inicia o `speedtester-api.service` e aguarda o healthcheck
  local antes de abrir o navegador, evitando a página inacessível em
  `127.0.0.1:8000` na primeira execução;

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

## [0.4.38] - 2026-10-23

### Corrigido

- Seleção automática tenta até três destinos iPerf3 em ordem geográfica quando
  há conexão recusada ou servidor ocupado antes do primeiro upload, dentro do
  mesmo limite de 60 segundos por tentativa. O destino manual é preservado.
- Upload e download permanecem no mesmo servidor; resultado baixo, timeout ou
  falha posterior ao upload não provocam escolha de um resultado mais favorável.
- Erros mostram host/porta e mensagem concisa; os destinos tentados ficam
  persistidos na tentativa e na evidência da amostra, sem atribuir recusa do
  servidor à operadora e sem apagar o histórico existente.
- A detecção auxiliar da interface respeita o tempo restante da medição.

### Qualidade e atualização

- Quality Gate restaurado sem reduzir critérios ou alterar o baseline:
  cobertura de código novo de 84,8%, zero novos problemas e 0% de duplicação.
- 380 testes aprovados; regressões de escolha geográfica, persistência,
  orçamento de tempo e interface, além de validação nativa nos três sistemas.
- Atualização sem migração de schema: preserva configurações e dados existentes.
  Distribuição GPL-3.0-or-later com os mesmos formatos de instalador, código-fonte,
  SBOM e SHA-256. As limitações de assinatura/notarização continuam documentadas.

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
