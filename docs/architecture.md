# Arquitetura

## Arquitetura implementada hoje

```text
┌──────────────┐      INSERT       ┌──────────────────┐      SELECT/PNG      ┌────────────┐
│ collector    │ ─────────────────▶│ SQLite           │◀────────────────────│ FastAPI    │
│ loop fixo    │                   │ samples          │                     │ api/server │
└──────┬───────┘                   └──────────────────┘                     └─────┬──────┘
       │ iPerf3 TCP + ICMP                                                         │ HTTP
       └───────────────────────────────────────────────────────────────────────────▼
                                                                                dashboard
```

Componentes confirmados no código:

| Componente | Responsabilidade atual |
|---|---|
| `collector/collector.py` | cria slots, executa os slots devidos, coleta probes, classifica falhas preliminares e grava o resultado |
| `collector/speedtest_runner.py` | mede download/upload com conexões fast.com, qualidade ICMP e identifica interface/ISP best-effort |
| `collector/ookla_runner.py` | adapta o JSON do cliente oficial Ookla Speedtest e complementa a qualidade da rota |
| `collector/iperf3_runner.py` | executa upload/download reverso, coleta retransmissões TCP e qualidade ICMP |
| `collector/network_metrics.py` | probe comum de ping, latência mínima/máxima, jitter e perda de pacotes |
| `collector/runner_dispatch.py` | seleciona o runner configurado |
| `api/store.py` | cria/migra tabelas, grava e consulta SQLite por thread |
| `api/server.py` | expõe health, amostras, resumo, comparação, alertas, gráfico PNG e reset |
| `dashboard/index.html` | consulta resumo/gráfico a cada 10 segundos |
| `docker/compose.yaml` | compartilha o volume SQLite entre `db`, `api`, `collector` e backup |

## Arquitetura-alvo

```text
                           ┌─────────────────────┐
                           │ scheduler de slots  │
                           │ 2+ por quadrante    │
                           └──────────┬──────────┘
                                      │ expected slots
┌───────────────┐   probes            ▼
│ energia/UPS   │──────────────▶┌───────────────┐
└───────────────┘               │ diagnóstico   │──▶ gateway/DNS/HTTPS
                                └──────┬────────┘
                                       │ contexto + motivo
                                       ▼
                                ┌───────────────┐      ┌───────────────┐
                                │ speed runner  │─────▶│ SQLite        │
                                └───────────────┘      │ slots/events  │
                                                        └──────┬────────┘
                                                               │
                                                        ┌──────▼────────┐
                                                        │ API + gráficos│
                                                        └───────────────┘
```

### Fluxo normal de um slot

1. O scheduler cria ou recupera os slots do dia local de forma idempotente.
2. No horário sorteado, o collector registra `started_at` e contexto de
   energia/rede.
3. O diagnóstico verifica gateway, DNS e destinos externos.
4. Com internet disponível, o runner configurado mede download, upload, ping e
   jitter quando suportados.
5. Se o primeiro download estiver abaixo do limiar configurado, o runner faz
   uma única medição imediata adicional; a primeira não é persistida.
6. O resultado final é gravado com quadrante, banda contratada, interface e
   status. Quando houve reteste, ele é o resultado representativo do slot.
7. Em falha, o sistema preserva o slot esperado, a tentativa, a evidência e a
   classificação.
8. A API agrega por dia/quadrante e o dashboard evidencia cobertura, entrega e
   indisponibilidade.

## Fronteiras de responsabilidade

- O **collector** coleta evidências e aplica uma classificação preliminar; não
  deve decidir “operadora” apenas por uma exceção genérica.
- O **classificador** transforma sinais em uma categoria explicável e deve
  permitir `unknown`.
- O **store** garante persistência, idempotência e ordenação temporal.
- A **API** calcula agregados e oferece filtros por data, quadrante e origem da
  falha.
- O **dashboard** comunica incerteza; não deve exibir slot perdido como zero.

## Pontos de atenção técnicos

- O runner usa `aiohttp`, que deve permanecer declarado e versionado em
  `app/requirements.txt`.
- O runner padrão usa iPerf3. O Dockerfile também inclui o cliente oficial
  Ookla e fast.com para comparação e operação alternativa.
- O container `db` não é um servidor SQLite: ele só mantém o volume. O acesso é
  concorrente por arquivo entre API e collector.
- Extensões futuras do scheduler devem preservar os horários persistidos e não
  depender apenas de `sleep(interval)`, para sobreviver a reinícios.
- O serviço `backup` usa cópia consistente do SQLite e volume próprio; ele não
  substitui replicação externa nem criptografia em repouso.
- A API de leitura é intencionalmente simples para o dashboard. O limite de
  rede deve ser aplicado pelo bind privado, firewall, VPN ou proxy reverso.
