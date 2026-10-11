# Operação

## Pré-requisitos

- Docker Engine e Docker Compose plugin para o modo container;
- conectividade de saída para o servidor iPerf3 configurado e ICMP opcional;
- volume persistente para `/data`;
- relógio do host sincronizado;
- timezone operacional definido, normalmente `America/Sao_Paulo`;
- para execução local, Python compatível e todas as dependências instaladas.

## Instalação com Compose

```bash
cp env.example .env
docker compose --env-file .env -f docker/compose.yaml -p speedtester up -d --build
docker compose --env-file .env -f docker/compose.yaml -p speedtester ps
curl http://127.0.0.1:8000/health
```

O banco lógico fica em um volume nomeado. Para listar volumes:

```bash
docker volume ls | grep db_data
```

Não remover o volume sem backup: ele contém o histórico.

## Instalação no servidor

`install.sh` espera o projeto em `$HOME/SpeedTester`, verifica Docker,
executa `docker compose --env-file .env -f docker/compose.yaml -p speedtester up -d --build` e cria um único
serviço systemd user para o stack completo. Depois da instalação:

```bash
systemctl --user status speedtester.service
docker compose --env-file .env -f docker/compose.yaml -p speedtester logs -f collector
```

Para uma instalação remota, configure `API_ADMIN_TOKEN` em `.env`. O mesmo
token deve ser enviado no header `X-Admin-Token` para registrar a justificativa
manual de energia ou limpar dados.

O Compose publica a porta somente em `127.0.0.1` por padrão. Se o dashboard
precisar ser acessado pela LAN, defina `API_BIND_ADDRESS` explicitamente para
o endereço privado da interface, restrinja a porta no firewall e prefira uma
VPN ou proxy reverso com HTTPS.

`API_REQUIRE_ADMIN_TOKEN=true` é o padrão de falha fechada. Sem
`API_ADMIN_TOKEN`, as operações administrativas ficam indisponíveis até que o
token seja configurado; não deixe essa proteção desativada em um host remoto.
O limite padrão é de 120 requisições por minuto por cliente, e pode ser
ajustado por `API_RATE_LIMIT_PER_MINUTE`.

As imagens da API e do collector executam como o usuário não-root
`speedtester` (UID 10001), com `no-new-privileges` no Compose. O serviço de
backup mantém o banco montado somente para leitura.

## Configuração

As variáveis são lidas por `app/shared/settings.py` e injetadas no Compose.
O nome atual `BANDWIDTH_CONTRACTED_MBP` tem uma sigla provavelmente incorreta,
mas é o contrato efetivo do código; uma mudança para `..._MBPS` deve oferecer
compatibilidade durante a migração.

O `TZ` está presente no ambiente, mas o armazenamento e boa parte dos cálculos
atuais operam em UTC. A implementação dos quadrantes deve converter
explicitamente para o timezone configurado antes de obter data/hora local.

O runner principal é o iPerf3. `IPERF3_SERVER` e `IPERF3_PORT` devem apontar
para um servidor iPerf3 controlado ou confiável. Servidores públicos servem
para validação, mas podem impor limites ou ficar indisponíveis.

Cada medição iPerf3 tem um limite total de 60 segundos por padrão
(`MEASUREMENT_TIMEOUT_SECONDS`). Ao exceder esse limite, o processo é
encerrado e a tentativa não é gravada. Antes de repetir, o collector revalida
o gateway e destinos externos independentes. Se o gateway estiver acessível
mas a internet não estiver, o slot é registrado como `external_unreachable`,
com origem `UNKNOWN` nas duas primeiras ocorrências consecutivas. A terceira
ocorrência consecutiva é registrada com origem `OPERATOR` e confiança alta,
sem desperdiçar uma nova tentativa de velocidade. Se a conectividade continuar
disponível, uma nova execução é iniciada como primeira tentativa. Esse valor
inclui upload, download reverso e o probe de qualidade da rota.

Para evitar que uma leitura transitória muito baixa seja usada como evidência,
o coletor aplica por padrão um reteste quando o download da primeira tentativa
fica abaixo de 50% de `BANDWIDTH_CONTRACTED_MBP`. Ajuste
`ANOMALY_RETRY_RATIO` para alterar a fração ou use
`ANOMALY_RETRY_MIN_DOWNLOAD_MBPS` para adicionar um limiar absoluto. O reteste
é único e imediato; somente a segunda leitura é gravada. Sem contrato e sem
limiar absoluto, essa regra fica desabilitada.

### Comparar os três runners

O runner agendado é o `iperf3`; o cliente oficial Ookla e o fast.com são
executados no container do collector para comparação.
Configure `IPERF3_SERVER` e, se necessário, `IPERF3_PORT`.
Sem um servidor acessível, o resultado será reportado como erro, sem impedir a
comparação dos demais runners. Execute:

```bash
docker compose --env-file .env -f docker/compose.yaml -p speedtester exec -T collector \
  python /opt/speedtester-scripts/compare_runners.py
```

O script não persiste amostras: retorna JSON separado por runner para evitar
misturar destinos diferentes no histórico do collector.

## Logs e diagnóstico

```bash
docker compose --env-file .env -f docker/compose.yaml -p speedtester logs --tail=200 api
docker compose --env-file .env -f docker/compose.yaml -p speedtester logs --tail=200 collector
curl http://127.0.0.1:8000/api/summary
```

Sinais úteis:

- `rows` cresce em `/health` quando o collector grava;
- logs do collector exibem `down`, `up`, `ping`, interface e duração;
- quando necessário, os logs exibem `discarding anomalous first result` e
  `retry selected as representative`; a primeira leitura não é amostra no
  banco;
- após timeout, os logs exibem a revalidação da conectividade e distinguem
  `OPERATOR` de `MEASUREMENT`;
- `FAILURE cause=...` é uma classificação técnica preliminar, não uma causa de
  operadora validada;
- resposta sem dados não significa que a internet está fora: pode ser o
  processo recém-iniciado ou um banco diferente via `DB_PATH`.

## Testes locais

Os testes de scheduler e persistência usam apenas a biblioteca padrão e podem
ser executados assim:

```bash
PYTHONPATH=app python3 -m unittest discover -s tests -v
```

## Backup e restauração

Com o stack parado, copie o arquivo SQLite do volume para um local seguro. O
procedimento exato depende do nome do volume Docker; valide o caminho antes de
copiar. Uma rotina de produção deve:

1. criar cópia consistente do banco;
2. guardar data, host e versão do schema;
3. testar restauração em outro arquivo;
4. manter retenção e pelo menos uma cópia fora do host.

Não executar `POST /api/reset` como limpeza operacional: ele apaga todas as
amostras e executa `VACUUM`.

O backup recomendado usa o script versionado:

```bash
DB_PATH=/data/speedtester.db BACKUP_DIR=./backups RETENTION_DAYS=30 ./scripts/backup.sh
```

O script usa o mecanismo de backup do SQLite, cria um arquivo com timestamp e
executa `PRAGMA integrity_check` antes de considerar a cópia válida, removendo
somente backups `speedtester-*.db` mais antigos que `RETENTION_DAYS`.
O diretório de backups não deve ser versionado. Em produção, execute-o
diariamente por systemd timer/cron e mantenha ao menos uma cópia fora do host.

O Compose já inclui o serviço `backup`, que executa essa rotina em um volume
separado (`backup_data`) e repete a operação conforme `BACKUP_INTERVAL_SECONDS`.
O volume local ainda não substitui uma cópia fora do servidor; sincronize os
arquivos válidos para outro host ou storage regularmente.

### Saúde e alertas

O collector grava um heartbeat no mesmo SQLite. A API expõe a situação em
`/health`; `status=degraded` indica heartbeat ausente, parado ou atrasado. O
limite padrão é 120 segundos e pode ser ajustado por
`COLLECTOR_HEARTBEAT_TIMEOUT_SECONDS`.

Alertas são persistidos no banco, com cooldown padrão de seis horas. Configure
`ALERT_WEBHOOK_URL` para enviar notificações HTTP JSON, além de ajustar
`ALERT_SPEED_THRESHOLD_PCT` e `ALERT_COOLDOWN_SECONDS`. O histórico de alertas
pode ser consultado em `/api/alerts`.

## Troubleshooting

### Collector não inicia

Verificar dependências Python, especialmente `aiohttp`, `PYTHONPATH`,
`DB_PATH` gravável, `IPERF3_SERVER` configurado e acesso ao destino. O runner
principal não depende do binário Ookla.

### API abre, mas não há pontos

Consultar os logs do collector, confirmar que API e collector usam o mesmo
volume/`DB_PATH` e conferir se o teste está demorando mais que o intervalo.

### Resultado muito baixo

Registrar interface, horário, destino e ocupação da rede. Comparar mais de um
quadrante; um único ponto não caracteriza a linha. O iPerf3 mede a capacidade
TCP até o servidor configurado; valide também com Ookla ou fast.com quando
quiser separar limitação do servidor de limitação da conexão.

### Falta de energia não apareceu

Isso é esperado sem fonte independente: um processo sem energia não consegue
gravar. Registrar manualmente o intervalo ou integrar UPS/sensor e depois
reconciliar com os slots esperados.

## Segurança e privacidade

- não expor a porta 8000 diretamente à internet; use LAN privada, VPN ou proxy
  reverso com HTTPS;
- manter `API_REQUIRE_ADMIN_TOKEN=true` e configurar um token longo em `.env`;
- preservar o limite de requisições e a paginação da API;
- evitar registrar IP público, credenciais ou conteúdo de tráfego;
- manter destinos externos e timeouts definidos no servidor;
- validar backups fora do host e atualizar dependências, digests e checksums;
- consultar [SECURITY.md](../SECURITY.md) para o checklist e os riscos residuais.
