# Modelo de dados

## Schema atual

O SQLite atual contém `samples`, `measurement_slots`, `availability_events`,
`service_heartbeats`, `alerts`, `measurement_attempts` e `schema_meta` (versão 12). A tabela de medições é descrita
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
| `server_location` / `country` | text | localização do servidor e país da conexão, quando disponível |
| `country_code` | text | código ISO-3166-1 alpha-2 da conexão |
| `city` | text | cidade estimada pelo endereço IP público no momento da medição |
| `public_ip` | text | endereço IP público observado, quando disponível |
| `interface` | text | interface local associada ao teste ou à rota observada; nula se ambígua |
| `connection_type` | text | tipo local detectado: `wifi`, `ethernet`, `cellular`, `bluetooth`, `usb`, `virtual`, `tunnel`, `point_to_point`, `loopback`, `mixed` ou `unknown` |
| `connection_source` | text | metadado nativo usado para classificar a interface, como `linux-sysfs` |
| `connection_scope` | text | vínculo da observação: `runner_interface`, `runner_address`, `runner_addresses`, `destination_route`, `default_route` ou `unknown` |
| `connection_observed_at` | text | instante UTC da observação da interface |
| `isp` | text | operadora identificada best-effort |
| `isp_organization` | text | organização anunciada pelo ASN |
| `asn` | text | ASN anunciado pela conexão |
| `isp_source` | text | fonte da identificação, como `ipwho.is` ou runner |
| `isp_confidence` | text | confiança declarada pelo enriquecimento |
| `isp_observed_at` | text | instante UTC em que a identidade foi consultada |
| `bandwidth_contracted_mbps` | real | download contratado vigente na coleta |
| `bandwidth_contracted_upload_mbps` | real | upload contratado vigente na coleta; nulo em registros antigos ou quando desconhecido |
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

### `measurement_attempts`

Cada execução do runner preserva `slot_id`, `started_at` real, `ended_at`,
`outcome`, `reason` e `metrics_json`. Os outcomes são `candidate`, `selected`,
`discarded`, `timeout` e `error`. O reteste mantém a primeira leitura descartada
nesta tabela; somente o resultado representativo entra em `samples` e nas
estatísticas. A API decodifica `metrics_json` como `metrics`. Cada tentativa guarda também
`interface`, os quatro campos `connection_*` e `connection_evidence`. A evidência
normalizada da amostra representativa fica em `evidence_json.connection`.
Uma troca de conexão entre a primeira tentativa descartada e o reteste não
reescreve o histórico; apenas a conexão do reteste entra na amostra final.

A migração 11 → 12 é aditiva e idempotente. Amostras anteriores conservam os
valores existentes, inclusive `interface`; os campos novos permanecem nulos.
Não se deduz conexão cabeada de um nome antigo como `eth0` ou `en0`.
Consulte [detecção da conexão local](network-link.md).

A gravação representativa e a conclusão do slot `RUNNING` são atômicas.
Chamadas concorrentes de `add_sample` para o mesmo slot retornam o mesmo ID.
`updated_at` renova a lease a cada 20 segundos durante testes longos. Após
`SLOT_LEASE_SECONDS` sem renovação, o slot retorna a `PENDING` quando ainda
está dentro da tolerância; slots antigos passam a `MISSED_UNKNOWN`. Um resultado
já gravado é reconciliado antes de iniciar outra execução.

A migração para versão 10 é aditiva: conserva amostras e classificações antigas,
cria a auditoria e índices de data/runner/slot, e pode ser executada novamente.
Tentativas antigas não são reconstruídas retroativamente.

## Identidade da conexão

Após uma medição bem-sucedida, o collector consulta o `ipwho.is` de forma
best-effort e persiste operadora, organização, ASN, IP público, país e cidade.
A consulta usa cache de processo de seis horas e seu timeout não falha nem
invalida uma medição de banda. Os valores representam a rede de saída naquele
instante; VPN, CGNAT, proxy e geolocalização imprecisa podem alterar o resultado.
Registros legados permanecem com esses campos nulos.

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

## Schema 9: sessões e entrega de alertas

`auth_sessions` armazena somente hash do token de sessão, perfil, CSRF, expiração
e impressão da credencial; alterar a credencial revoga sessões anteriores.
`alert_states` registra incidentes ativos. Recuperação e criação da mensagem são
atômicas. `alerts` ganha estado, contagem de tentativas, próxima tentativa e lease;
a fila permanece após reinício. Migrações são aditivas e serializadas por uma
transação SQLite para API e collector iniciando simultaneamente.
`schema_meta.observation` guarda início da observação e impressão do destino,
sem devolver endereço no endpoint de relatórios.

## Schema 10: identidade da conexão

A versão 10 adiciona os campos de identidade de rede descritos acima. A
migração é aditiva, não reconsulta registros antigos e não substitui valores
históricos já persistidos.
