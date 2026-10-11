# Changelog

Este arquivo registra mudanças relevantes do SpeedTester. O formato segue a
ideia de [Keep a Changelog](https://keepachangelog.com/pt-BR/1.1.0/) e
[Semantic Versioning](https://semver.org/lang/pt-BR/).

Projeto mantido por [Edson Angelo Carara (`ecarara`)](https://github.com/ecarara)
em <https://github.com/ecarara/SpeedTester>.

## [Unreleased]

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
