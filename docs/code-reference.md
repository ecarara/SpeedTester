# Referência de código

Esta página descreve os módulos usados como referência por contribuidores.
Helpers internos podem mudar sem compatibilidade retroativa; os invariantes
abaixo não devem mudar sem atualização da API e dos requisitos.

## API e persistência

### `app/api/server.py`

Cria a aplicação FastAPI, serve o dashboard, expõe health, amostras, slots,
eventos, resumo, comparação, alertas, gráfico PNG e reset. Também concentra a
autenticação administrativa, rate limit, cabeçalhos HTTP e agregações sem
transformar ausência em zero.

### `app/api/store.py`

Define `Sample` e `MeasurementSlot`, inicializa/migra o SQLite, grava amostras,
slots, eventos, heartbeats e alertas, e fornece consultas ordenadas e
paginação. O plano é idempotente por `(local_date, quadrant, slot_index)`.

O store deve usar parâmetros SQL. Não introduza SQL construído com entrada de
usuário sem validação e parametrização.

## Collector

### `app/collector/collector.py`

`Collector.run_forever()` mantém a agenda, marca slots atrasados, reivindica
slots, executa diagnóstico, persiste resultados, atualiza heartbeat e avalia
alertas. A ordem é:

```text
probe inicial → runner → reteste se anômalo → persistência → status do slot
```

Tentativas anômalas e tentativas que excedem timeout não são gravadas como
amostras representativas. O reteste é uma nova execução independente.

### `app/collector/quadrants.py`

`plan_day_slots()` cria horários pseudoaleatórios usando semente estável por
dia. Os limites são locais e o resultado é persistido em UTC.

### `app/collector/connectivity.py`

`probe_connectivity()` coleta gateway, interface, DNS e destinos externos. A
função fornece evidência, não prova jurídica de falha da operadora.

### `app/collector/network_metrics.py`

`measure_ping()` mede RTT mediano, jitter médio das diferenças consecutivas,
limites de latência e perda. ICMP bloqueado resulta em métricas nulas.

### `app/collector/network_identity.py`

Consulta, de forma best-effort, o IP público e os metadados de rede retornados
por `ipwho.is` — operadora, organização, ASN, país e cidade. Mantém cache de
processo por seis horas e nunca transforma falha de enriquecimento em falha de
medição.

## Runners

### `app/collector/iperf3_runner.py`

Executa upload e download reverso contra `IPERF3_SERVER`, converte bits por
segundo em Mbps, soma retransmissões disponíveis e usa o mesmo destino para o
probe de qualidade. O timeout é um orçamento total; após uma medição concluída,
os metadados de identidade da conexão são anexados sem exceder o orçamento.

### `app/collector/ookla_runner.py`

Executa o cliente oficial Ookla, converte `bandwidth` de bytes por segundo para
Mbps e preserva metadata de servidor, cliente e ISP quando retornada.

### `app/collector/speedtest_runner.py`

Implementa o runner assíncrono fast.com e o resultado comum `SpeedTestResult`.
Também fornece detecção de interface e lookup best-effort da identidade da
conexão.

### `app/collector/runner_dispatch.py`

`run_named_runner()` é o ponto único de seleção. Valores permitidos: `fast`,
`ookla` e `iperf3`; qualquer outro valor falha cedo.

## Configuração e scripts

- `app/shared/settings.py`: lê ambiente, valida tipos simples e monta
  `Settings` imutável;
- `scripts/backup.sh`: cria cópia consistente do SQLite, verifica integridade
  e aplica retenção somente aos arquivos gerados pelo script;
- `scripts/compare_runners.py`: compara runners sem gravar amostras;
- `install.sh`: executa doctor, compila/valida o runner e inicia o stack Compose.

Alterações em runners, status, colunas SQLite, payloads HTTP ou semântica de
métricas são mudanças de contrato e exigem testes, documentação e changelog.
