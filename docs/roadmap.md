# Roadmap e critérios de aceite

## P0 — tornar a base executável e documentada

- [x] adicionar `aiohttp` a `app/requirements.txt`;
- [x] alinhar Dockerfile, README e runner quanto a fast.com/Ookla;
- [x] adicionar testes automatizados para persistência e scheduler;
- [x] proteger o reset no modo não local;
- [x] instalar com preflight, validação de saúde e reinício pelo Docker;
- [x] calcular downtime a partir de eventos explícitos, sem usar gaps entre
  amostras como queda.

## P1 — agenda e domínio de disponibilidade

- [x] criar `measurement_slots` com dois slots mínimos por quadrante;
- [x] implementar sorteio determinístico/auditável e idempotente;
- [x] persistir data local e quadrante em cada slot/medição;
- [x] adicionar estados e origem preliminar da falha;
- [x] permitir registro manual de falta de energia;
- [x] criar probes de gateway, DNS e destinos externos;
- [x] cruzar slot com evento de energia e registrar evidências.
- [x] descartar a primeira leitura anômala e persistir o segundo teste como
      resultado representativo.

## P2 — API e dashboard de decisão

- [x] endpoint de slots e incidentes/registro manual;
- [x] gráfico de contrato versus real;
- [x] visão por quadrante;
- [x] cobertura esperada versus realizada;
- [x] linha do tempo de energia/operadora/rede interna;
- [x] filtros por dia/runner e exportação CSV/JSON;
- [x] classificação manual de slots diretamente no dashboard;
- [x] dashboard responsivo com atualização automática e estados de erro.

## P3 — robustez operacional

- [x] registrar versão do schema e manter migração incremental;
- [x] disponibilizar backup consistente do SQLite;
- [x] backup agendado e verificação de integridade;
- [x] heartbeat e métricas básicas de saúde do collector;
- [x] alertas opcionais para repetição de falhas e degradação de velocidade;
- [x] retenção configurável;
- [x] autenticação administrativa e autorização das operações de escrita;
- [x] documentação de segurança, contribuição, suporte e licenças de terceiros.

## Critérios de aceite do objetivo principal

O requisito estará atendido quando todos os itens forem verdadeiros:

- [x] Para cada dia local, existem pelo menos oito slots esperados, dois em
      cada quadrante.
- [x] Os horários de cada quadrante são aleatórios, persistidos e não mudam
      com um restart do collector.
- [x] Um slot concluído mostra download/upload, ping/jitter, horário,
      quadrante, contrato e percentual de entrega.
- [x] Um slot perdido aparece explicitamente e não é convertido em zero Mbps.
- [x] O usuário consegue registrar uma falta de energia e os slots afetados
      passam a `POWER_OUTAGE` com fonte e nota.
- [x] Com energia e gateway disponíveis, mas sem destinos externos, a falha é
      classificada como `NO_INTERNET_OPERATOR` ou “provável operadora”, com
      evidências e confiança.
- [x] Falha de link/gateway é `NO_INTERNET_INTERNAL`.
- [x] Timeout/erro do runner é `MEASUREMENT_ERROR`.
- [x] O dashboard compara contrato versus real e separa os quatro quadrantes.
- [x] A comparação histórica mostra dias sem medição sem convertê-los em zero.
- [x] O relatório mostra cobertura e indisponibilidade por origem, sem contar
      duas vezes intervalos sobrepostos.

## Licenciamento

- [x] Adotar `GPL-3.0-or-later` como licença do projeto.
- [x] Incluir o texto integral da licença em `LICENSE`.
- [x] Definir Edson Angelo Carara (`ecarara`) como titular do copyright e
      aplicar avisos SPDX aos arquivos-fonte.
- [x] Inventariar as licenças das dependências e imagens base.

## Melhorias de confiabilidade e publicação

- [x] atualizar dependências vulneráveis e remover dependências sem uso;
- [x] filtrar em SQL antes de paginar, priorizar registros recentes e exportar todo o filtro;
- [x] recuperar slots interrompidos e persistir resultado/conclusão atomicamente;
- [x] auditar retestes descartados e registrar o horário real da tentativa;
- [x] usar evidência externa/ICMP quando o gateway recusa portas TCP;
- [x] testar API, reinício, autorização, migração, restauração e interface;
- [x] adicionar períodos 7/30/90, gráficos interativos e medianas/p10/p95;
- [x] separar sucessos, slots classificados, devidos e futuros;
- [x] fornecer doctor, ARM64, publicação GHCR e backup externo criptografado;
- [x] integrar SonarQube e cobertura ao CI da branch principal.

## Próxima etapa aprovada

- [x] login com perfis administrador e visualizador, leitura/exportação protegidas;
- [x] sessões persistidas com expiração, revogação e proteção CSRF;
- [x] fila de alertas persistida, retentativas, recuperação e estado de entrega;
- [x] relatório de observação com cobertura, tentativas e tráfego conhecido;
- [x] deploy por imagens fixadas por digest, condicionado a CI/Sonar/build;
- [x] snapshot antes da migração e retorno automático quando a validação falha;
- [x] ampliar testes de falhas de rede, runners, acesso e operação;
- [ ] concluir observação contínua de 21 dias no staging.

O destino iPerf3 existente será mantido: não há servidor externo sob controle
confirmado. As medições não comprovam SLA. O tráfego reportado inclui tentativas
com contadores disponíveis; timeouts e runners sem contador ficam explicitamente
como consumo desconhecido, sem estimar zero.

Integração com UPS/sensor foi retirada desta etapa porque esse equipamento não
está disponível. Faltas de energia continuam sendo informadas manualmente.
