# Modelo de dados

## Schema atual

O SQLite atual contém `samples`, `measurement_slots`, `availability_events`,
`service_heartbeats`, `alerts` e `schema_meta`. A tabela de medições é descrita
abaixo; as demais tabelas preservam a obrigação de medir, o contexto de
indisponibilidade, a saúde operacional e os alertas.

### `samples`

O código atual cria uma única tabela `samples` com os campos abaixo:

| Campo | Tipo | Significado |
|---|---|---|
| `id` | integer | identificador autoincremental |
| `started_at` | text | timestamp UTC em ISO-8601 com `Z` |
| `is_failure` | integer | `0` sucesso, `1` falha |
| `failure_cause` | text | etiqueta derivada da exceção, como `network`, `dns`, `timeout` |
| `failure_note` | text | detalhe livre truncado em 400 caracteres pelo collector |
| `download_mbps` / `upload_mbps` | real | velocidade em Mbps |
| `ping_ms` / `jitter_ms` | real | latência mediana e variação entre respostas |
| `latency_min_ms` / `latency_max_ms` | real | limites observados no lote de pings |
| `packet_loss_pct` | real | perda observada no lote ICMP; pode ser nula quando ICMP é filtrado |
| `tcp_retransmits` | integer | retransmissões TCP informadas pelo iPerf3, quando disponíveis |
| `server_id` / `server_name` | integer/text | metadata do destino; no runner atual o nome é `fast.com` e o id é nulo |
| `server_location` / `country` | text | localização, quando disponível |
| `interface` | text | interface local detectada |
| `isp` | text | operadora identificada best-effort |
| `bandwidth_contracted_mbps` | real | banda contratada vigente na coleta |
| `test_duration_sec` | real | duração observada do teste |
| `slot_id` | integer | slot esperado associado, quando aplicável |
| `local_date` / `quadrant` | text | dia e quadrante operacional |
| `runner` | text | `fast`, `ookla`, `iperf3` ou `NULL` em amostras legadas |
| `failure_origin` | text | `INTERNAL`, `OPERATOR`, `MEASUREMENT` ou `UNKNOWN` |
| `power_state` | text | estado conhecido da energia, atualmente `UNKNOWN` sem fonte externa |
| `gateway_reachable` / `external_reachable` | integer | resultados dos probes de conectividade |
| `classification_confidence` | text | confiança da classificação preliminar |
| `evidence_json` | text | evidências técnicas serializadas |

Para a regra de indisponibilidade externa consecutiva, os causes
`external_unreachable` e `external_timeout` formam a mesma sequência. A
sequência é lida das amostras persistidas e reinicia após sucesso, falha
interna, erro do runner ou troca de runner. A terceira ocorrência consecutiva
recebe `failure_origin=OPERATOR`; as duas anteriores permanecem
`failure_origin=UNKNOWN`.

## Limitações e invariantes

O slot esperado, seu estado, sua justificativa manual e os incidentes já
possuem estruturas próprias, e `samples` agora guarda o vínculo com slot, data
local, quadrante, runner, origem preliminar, energia, gateway, destino externo,
confiança e evidência JSON. A coluna histórica `is_failure` ainda mistura
causas de naturezas diferentes, mas a API e o dashboard já apresentam os
agregados operacionais principais. `SCHEMA_VERSION` deve ser incrementado a
cada alteração estrutural, e migrações devem ser aditivas e compatíveis com
bases existentes.

## Modelo recomendado

Uma migração incremental pode manter `samples` para compatibilidade e adicionar
os conceitos abaixo.

### `measurement_slots`

Representa a obrigação de testar, mesmo quando a tentativa não acontece.

| Campo | Exemplo |
|---|---|
| `id` | `42` |
| `local_date` | `2026-08-26` |
| `quadrant` | `tarde` |
| `scheduled_for` | `2026-08-26T15:37:00Z` |
| `slot_index` | `1` ou `2` |
| `status` | `PENDING`, `SUCCESS`, `POWER_OUTAGE`, ... |
| `attempt_count` | `1` |
| `created_at` / `updated_at` | UTC |
| `schedule_seed` | identificador auditável do sorteio |
| `classification_note` | justificativa manual, quando houver |
| `classification_source` | atualmente `manual` para correções humanas |
| `classification_updated_at` | horário UTC da última classificação |

Restrição recomendada: unicidade em `(local_date, quadrant, slot_index)`.

### `measurements`

Pode substituir ou estender `samples` com:

- `slot_id` e `attempt_number`;
- `measurement_status`;
- `failure_origin`: `POWER`, `OPERATOR`, `INTERNAL`, `MEASUREMENT`, `UNKNOWN`;
- `failure_cause`: `NO_POWER`, `GATEWAY_UNREACHABLE`, `DNS_FAILURE`,
  `EXTERNAL_UNREACHABLE`, `TIMEOUT`, `RUNNER_ERROR`, etc.;
- `power_state`, `interface_link`, `gateway_reachable`, `dns_reachable`,
  `external_reachable`;
- `classification_confidence`: `high`, `medium`, `low`;
- `evidence_json` com probes, destinos e tempos, sem segredos;
- as métricas já presentes em `samples`.

### `availability_events`

Representa intervalos, não apenas pontos:

| Campo | Significado |
|---|---|
| `id` | identificador |
| `started_at` / `ended_at` | intervalo UTC; `ended_at` pode ser nulo enquanto aberto |
| `event_type` | `POWER_OUTAGE`, `OPERATOR_OUTAGE`, `INTERNAL_OUTAGE`, `UNKNOWN` |
| `source` | `manual`, `ups`, `probe`, `import` |
| `confidence` | confiança da fonte |
| `note` | justificativa humana ou técnica |

Os slots são cruzados com esses intervalos. Um evento não deve apagar a
amostra nem mascarar o fato de que o slot foi esperado.

## Exemplo de registro de sucesso

```json
{
  "local_date": "2026-08-26",
  "quadrant": "tarde",
  "scheduled_for": "2026-08-26T15:37:00Z",
  "measurement_status": "SUCCESS",
  "download_mbps": 482.3,
  "upload_mbps": 103.7,
  "bandwidth_contracted_mbps": 500,
  "power_state": "ON",
  "gateway_reachable": true,
  "dns_reachable": true,
  "external_reachable": true
}
```

## Exemplo de falha atribuída à operadora

```json
{
  "local_date": "2026-08-26",
  "quadrant": "noite",
  "scheduled_for": "2026-08-26T21:12:00Z",
  "measurement_status": "NO_INTERNET_OPERATOR",
  "failure_origin": "OPERATOR",
  "failure_cause": "EXTERNAL_UNREACHABLE",
  "power_state": "ON",
  "interface_link": true,
  "gateway_reachable": true,
  "dns_reachable": false,
  "external_reachable": false,
  "classification_confidence": "medium",
  "evidence_json": {"probes": ["gateway", "resolver", "https"]}
}
```
