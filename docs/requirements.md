# Requisitos e regras de negócio

## Objetivo

Medir a banda larga de forma distribuída durante o dia e gerar evidência
comparável entre a capacidade contratada e o desempenho real. O resultado deve
permitir responder:

- quantas medições eram esperadas e quantas foram realizadas;
- qual foi a velocidade média, mediana, mínima e máxima de download/upload;
- em qual quadrante a conexão piora;
- por quanto tempo a conexão esteve indisponível;
- se uma indisponibilidade é compatível com falta de energia, operadora,
  rede interna ou erro do próprio teste.

## Quadrantes e agenda

O dia local é dividido em quatro quadrantes de seis horas:

| Quadrante | Horário local | Identificador |
|---|---|---|
| Madrugada | 00:00–05:59 | `madrugada` |
| Manhã | 06:00–11:59 | `manha` |
| Tarde | 12:00–17:59 | `tarde` |
| Noite | 18:00–23:59 | `noite` |

Em cada quadrante o scheduler deve criar pelo menos duas janelas de medição.
Os horários devem ser sorteados dentro do quadrante, com uma semente/registro
que permita auditoria. Cada banco local recebe uma semente aleatória persistida,
para evitar que instalações distintas iniciem todos os testes no mesmo instante.
Sementes independentes reduzem coincidências, mas não coordenam instalações na
mesma rede nem impedem sobreposições ocasionais. O sorteio precisa respeitar:

- distância mínima configurável entre as duas medições;
- duração do teste e uma margem para não ultrapassar o fim do quadrante;
- não duplicação de slots já persistidos;
- tolerância para reinício do processo, evitando gerar novos horários a cada
  restart;
- execução imediata ou replanejamento de uma tentativa quando o teste falhar,
  sem apagar o slot original.

Na atualização de versões com semente compartilhada, slots futuros pendentes
sem tentativa podem ser replanejados; slots em andamento, já vencidos, com
histórico ou classificados são preservados. Se não houver um novo horário
seguro dentro do quadrante, o horário anterior é mantido.

O mínimo recomendado é `2 slots × 4 quadrantes = 8 medições esperadas por dia`.
Mais medições são permitidas, mas a cobertura deve continuar informando quais
eram os slots mínimos.

## Estados de uma janela

Cada slot esperado deve terminar em exatamente um estado principal:

| Estado | Significado |
|---|---|
| `SUCCESS` | teste concluído com métricas válidas |
| `POWER_OUTAGE` | não executado porque o local estava sem energia |
| `NO_INTERNET_OPERATOR` | energia e rede local disponíveis, mas sem acesso externo atribuível à operadora |
| `NO_INTERNET_INTERNAL` | falha entre o agente, a LAN, o gateway ou o equipamento interno |
| `MEASUREMENT_ERROR` | o teste não pôde ser concluído por falha do software, timeout ou serviço de medição |
| `MISSED_UNKNOWN` | janela perdida sem evidência suficiente para outra classificação |
| `CANCELLED` | slot cancelado explicitamente por operação/manutenção |

O estado `SUCCESS` nunca deve ser preenchido com velocidades zero para
representar indisponibilidade. Zero é uma medição possível; indisponibilidade é
um estado separado.

## Medição anômala e reteste

Cada slot de velocidade tem uma primeira tentativa candidata. Quando o
download dessa tentativa fica abaixo de `ANOMALY_RETRY_RATIO ×
BANDWIDTH_CONTRACTED_MBP`, ou o upload abaixo de `ANOMALY_RETRY_RATIO ×
BANDWIDTH_CONTRACTED_UPLOAD_MBPS`, ela é considerada anômala, descartada e substituída
por uma segunda medição imediata. O limiar absoluto opcional
`ANOMALY_RETRY_MIN_DOWNLOAD_MBPS` também pode disparar o reteste, inclusive
quando não há banda contratada configurada.

Somente o resultado da segunda tentativa é persistido como representativo do
slot. A primeira tentativa fica na auditoria de tentativas, não aparece como
amostra representativa, não altera médias e não é
tratada como falha. Se a segunda tentativa também for baixa, ela ainda assim é
o resultado representativo e deve permanecer registrada para análise. Se não
houver contrato nem limiar absoluto válido, o reteste automático fica
desabilitado.

## Como diferenciar operadora de infraestrutura interna

O diagnóstico deve seguir uma cadeia de evidências, registrada no evento:

1. **Energia:** verificar sensor/UPS, agente ativo, equipamento ligado ou
   confirmação manual. Se não houver energia, classificar `POWER_OUTAGE`.
2. **Interface local:** verificar link da interface e conectividade com o
   gateway. Se falhar, classificar `NO_INTERNET_INTERNAL`.
3. **DNS:** consultar um resolvedor configurado e registrar sucesso/erro. DNS
   isoladamente não prova falha da operadora, pois pode ser um problema de
   configuração local.
4. **Destino externo:** testar pelo menos dois destinos independentes, por
   exemplo HTTPS e DNS. Se gateway/LAN funcionam e destinos externos falham,
   registrar uma ocorrência externa. As duas primeiras ocorrências consecutivas
   permanecem `UNKNOWN`; a terceira ocorrência consecutiva, incluindo timeout
   do teste seguido de falha externa, pode ser classificada como
   `NO_INTERNET_OPERATOR` com confiança alta.
5. **Teste de banda:** se a conectividade existe, mas o serviço de medição
   falha, usar `MEASUREMENT_ERROR`; não atribuir automaticamente à operadora.

Uma classificação com evidência insuficiente deve permanecer
`MISSED_UNKNOWN`, com `classification_confidence=low`, em vez de produzir uma
acusação incorreta. A UI deve mostrar “provável operadora” quando a regra for
atendida, mas manter a rastreabilidade dos testes que sustentaram a decisão.

## Falta de energia — modo atual manual

O coletor que está desligado não consegue registrar o evento durante a queda.
Nesta fase, a única estratégia habilitada é:

- **Manual:** após o retorno, o usuário informa início/fim ou seleciona os
  quadrantes perdidos e o sistema marca os slots sobrepostos como
  `POWER_OUTAGE`.

Integração com UPS, smart plug, roteador com telemetria ou outro monitor externo
fica reservada para uma fase futura e não deve ser usada como comportamento
atual.

Sem uma dessas fontes, o sistema só pode dizer “slot não observado”; não pode
afirmar que houve falta de energia.

## Banda contratada

O valor contratado deve ser configurado por dispositivo em Mbps. Cada amostra
deve guardar uma cópia do valor vigente para preservar a comparação histórica
quando o plano mudar. O percentual de entrega sugerido é:

```text
entrega_download_pct = download_mbps / banda_contratada_mbps × 100
entrega_upload_pct   = upload_mbps / banda_contratada_mbps × 100
```

Se o valor contratado estiver ausente, mostrar a velocidade real, mas não
inventar percentual nem concluir descumprimento.

## Requisitos não funcionais

- timestamps persistidos em UTC e exibidos no timezone configurado;
- idempotência para scheduler e registro de eventos;
- dados de falha auditáveis, com nota e evidências técnicas;
- retomada após reinício sem perder slots já planejados;
- retenção/backup documentados;
- dashboard legível em desktop e celular;
- nenhum segredo ou credencial de rede armazenado em uma amostra.
