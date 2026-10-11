# Changelog

Este arquivo registra mudanças relevantes do SpeedTester. O formato segue a
ideia de [Keep a Changelog](https://keepachangelog.com/pt-BR/1.1.0/) e
[Semantic Versioning](https://semver.org/lang/pt-BR/).

Projeto mantido por [Edson Angelo Carara (`ecarara`)](https://github.com/ecarara)
em <https://github.com/ecarara/SpeedTester>.

## [Unreleased]

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
