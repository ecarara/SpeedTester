# API

## Endpoints atuais

Base URL padrão: `http://localhost:8000`.

O FastAPI também publica documentação interativa em `/docs`, esquema OpenAPI
em `/openapi.json` e documentação alternativa em `/redoc`.

| Método | Rota | Comportamento |
|---|---|---|
| `GET` | `/` | dashboard HTML |
| `GET` | `/dashboard/index.html` | dashboard estático |
| `GET` | `/health` | `{status, rows, ts, collector}` com heartbeat do collector |
| `GET` | `/api/alerts` | alertas persistidos e estado de entrega opcional |
| `GET` | `/api/samples` | amostras com filtros em SQL, ordenação e paginação |
| `GET` | `/api/export` | CSV/JSON de todo o filtro, em streaming |
| `GET` | `/api/series` | série completa; acima de 2.000 registros, medianas diárias |
| `GET` | `/api/attempts` | tentativas auditadas; exige `slot_id` |
| `GET` | `/api/config` | timezone, data operacional, versão e contrato |
| `GET` | `/api/slots` | slots planejados para o dia local; aceita `date=YYYY-MM-DD` |
| `GET` | `/api/availability-events` | intervalos de indisponibilidade registrados |
| `POST` | `/api/availability-events` | registra energia/operadora/rede interna e reconcilia slots |
| `POST` | `/api/slots/{slot_id}/classify` | corrige manualmente o status de um slot com justificativa |
| `GET` | `/api/summary` | resumo, estatísticas por runner, última amostra, falhas, downtime calculado e outliers |
| `GET` | `/api/comparison` | comparação diária em um intervalo `from`, `to` e `runner` opcional |
| `GET` | `/api/chart.png` | PNG de download/upload da janela de até 24 horas; aceita `runner` |
| `POST` | `/api/reset` | apaga amostras, slots, eventos e alertas |

## Autenticação e limites

O dashboard e as consultas de leitura não enviam token; portanto, a API deve
ser mantida em localhost, LAN confiável ou atrás de VPN/proxy autenticado. As
rotas `/api/*` têm rate limit em memória por endereço cliente, configurado por
`API_RATE_LIMIT_PER_MINUTE`, com HTTP `429` quando excedido.

As operações administrativas (`POST /api/availability-events`,
`POST /api/slots/{slot_id}/classify` e `POST /api/reset`) exigem o header
`X-Admin-Token` quando `API_REQUIRE_ADMIN_TOKEN=true`. Sem token configurado, o
backend responde HTTP `503` (fail-closed); com token ausente ou incorreto,
responde HTTP `403`.

### `/api/samples`

Filtros atuais:

- `since`: timestamp UTC inclusivo, por exemplo
  `2026-08-26T00:00:00Z`;
- `minutes`: somente os últimos N minutos.
- `runner`: `fast`, `ookla` ou `iperf3`.
- `limit`: quantidade máxima de linhas, de 1 a 5.000; padrão 1.000;
- `offset`: deslocamento não negativo para paginação; padrão 0;
- `order`: `desc` (padrão, medições mais recentes primeiro) ou `asc`;
- `date`: dia local operacional, no formato `YYYY-MM-DD`;
- `from` / `to`: período local inclusivo, até 366 dias entre as datas;
- `quadrant`: `madrugada`, `manha`, `tarde` ou `noite`.

Os filtros são aplicados antes da paginação. `date` não pode ser combinado
com `from`/`to`; filtros inválidos retornam HTTP 422. Registros legados sem
`local_date` são convertidos conforme `TZ` para os limites de consulta.
`since` exige timezone; `minutes`, quando informado, substitui `since`.

`/api/export?format=json` e `format=csv` aceitam `date`, `from`, `to`, `runner`
e `quadrant`, e incluem todas as linhas do filtro, mesmo com mais de 1.000
registros. A exportação congela o maior ID observado no início; novas inserções
não prolongam o download. Texto CSV iniciado como fórmula é escapado.
O gráfico usa `/api/series`, independente da página visível da tabela.

O retorno é uma lista de objetos correspondentes às colunas de `samples`.

### `/api/summary`

O retorno atual inclui `count`, `first`, `last`, `latest`, médias e máximos de
download/upload, ISP, banda contratada, taxa de falhas, `downtime` e
`outliers`, além de `coverage` com slots esperados/concluídos por quadrante. As
médias excluem linhas com `is_failure=1`. O resumo aceita os mesmos filtros de
período e runner da listagem, sem paginação. Retorna também mediana, p10 e p95
para download/upload/ping, calculados por interpolação linear sobre resultados
representativos válidos, além de distribuição por quadrante.

`coverage.expected` conta apenas slots devidos; `future` informa os slots
futuros, `completed` os sucessos e `classified` os slots com um resultado ou
classificação terminal conhecida. `coverage_pct` mede sucessos/devidos;
`classified_pct` mede classificados/devidos. A agenda é comum aos runners.

Também retorna `ping_avg_ms`, `jitter_avg_ms`, `packet_loss_avg_pct` e
`tcp_retransmits_avg`. Cada objeto de `/api/samples` traz ainda
`latency_min_ms`, `latency_max_ms`, `packet_loss_pct` e
`tcp_retransmits`. Campos ficam nulos quando a métrica não é suportada pelo
destino ou quando o probe é bloqueado.

O campo `by_runner` contém estatísticas independentes para cada runner
persistido, incluindo quantidade, sucesso/falha, média/mediana/máximo de
download/upload e médias de qualidade. `?runner=ookla` restringe as métricas
principais e o gráfico ao runner escolhido, sem misturar resultados.

O campo `downtime` é calculado a partir de `availability_events`, unindo
intervalos sobrepostos no total e por origem, recortados ao período local
selecionado. `/api/availability-events` também aceita `date`, `from` e `to`. Ausência de amostra, por si só, não é contada
como queda.

### Comparação histórica

```text
GET /api/comparison?from=2026-08-20&to=2026-08-26&runner=iperf3
```

O retorno contém uma linha por dia, inclusive dias sem medições, com médias de
download/upload, percentual do contrato, falhas e cobertura dos slots. O
intervalo é limitado a 366 dias para evitar consultas acidentais muito pesadas.

### Saúde e alertas

`GET /health` inclui o heartbeat do collector, sua idade em segundos e
metadados do último slot. O status do serviço fica `degraded` quando o
heartbeat não existe, está parado ou ultrapassou
`COLLECTOR_HEARTBEAT_TIMEOUT_SECONDS`.

`GET /api/alerts?limit=50` retorna alertas deduplicados por janela de cooldown.
O collector registra `operator_outage` após três falhas externas consecutivas
e `speed_degraded` quando o download fica abaixo de
`ALERT_SPEED_THRESHOLD_PCT` do contrato. Se `ALERT_WEBHOOK_URL` estiver
configurado, o mesmo alerta é enviado como JSON e o resultado da entrega fica
registrado.

### Classificação manual de um slot

O dashboard disponibiliza essa operação para slots pendentes, não observados ou
com erro. Ela não cria uma medição artificial: apenas registra a interpretação
humana da obrigação de medir.

```http
POST /api/slots/42/classify
X-Admin-Token: seu-token
Content-Type: application/json
```

```json
{
  "status": "NO_INTERNET_OPERATOR",
  "note": "Modem ligado, gateway acessível, sem acesso externo"
}
```

Status aceitos: `POWER_OUTAGE`, `NO_INTERNET_OPERATOR`,
`NO_INTERNET_INTERNAL`, `MEASUREMENT_ERROR`, `MISSED_UNKNOWN` e `CANCELLED`.
O backend salva `classification_source=manual`, a justificativa truncada em
400 caracteres e o horário da alteração.

## Evoluções futuras da API

```text
GET /api/days?from=2026-08-01&to=2026-08-26
GET /api/days/2026-08-26
GET /api/measurements?date=2026-08-26&quadrant=tarde
GET /api/incidents?from=...&to=...
GET /api/charts/speed?date=2026-08-26&quadrant=all
```

`GET /api/slots` e `/api/availability-events` já estão disponíveis para
inspeção/registro; os demais endpoints acima continuam sendo API-alvo.

`GET /api/summary?date=YYYY-MM-DD` e `GET /api/chart.png?date=YYYY-MM-DD`
filtram os dados pelo dia local configurado. Sem `date`, o resumo considera o
histórico disponível.

O resumo diário deve conter, no mínimo:

```json
{
  "date": "2026-08-26",
  "contracted_mbps": 500,
  "coverage": {
    "expected": 8,
    "completed": 7,
    "missing": 1,
    "by_quadrant": {
      "madrugada": {"expected": 2, "completed": 2},
      "manha": {"expected": 2, "completed": 2},
      "tarde": {"expected": 2, "completed": 2},
      "noite": {"expected": 2, "completed": 1}
    }
  },
  "quadrants": {},
  "incidents": []
}
```

### Registro manual de energia

```text
POST /api/availability-events
```

Payload mínimo:

```json
{
  "started_at": "2026-08-26T02:10:00Z",
  "ended_at": "2026-08-26T04:45:00Z",
  "event_type": "POWER_OUTAGE",
  "source": "manual",
  "note": "Falta de energia informada pelo usuário"
}
```

O endpoint deve ser idempotente ou aceitar uma chave de idempotência para que
um retry não crie incidentes duplicados.

No modo atual, `POWER_OUTAGE` exige `source: "manual"`. Outras fontes poderão
ser habilitadas futuramente quando houver integração com um equipamento
independente de energia.

## Requisitos de segurança da API

- manter `/api/reset` protegido ou desabilitado fora do ambiente local;
- validar datas, quadrantes e enums no servidor;
- limitar tamanho de `failure_note`/`evidence_json`;
- não aceitar URLs arbitrárias de probe vindas do cliente;
- adicionar autenticação de leitura antes de expor a API na internet;
- usar HTTPS, VPN ou proxy reverso para qualquer acesso fora do host.
