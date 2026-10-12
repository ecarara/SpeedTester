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

`install.sh` usa o diretório do próprio checkout (ou `PROJECT_DIR`), executa
`python3 scripts/doctor.py --env-file .env`, compila as imagens e valida o runner
no container antes de iniciar. A instalação falha quando a API não fica saudável.
Docker Engine e Compose precisam estar instalados e acessíveis ao usuário.
Os serviços usam `restart: unless-stopped`; configure o daemon Docker para
iniciar no boot conforme o sistema operacional.

```bash
python3 scripts/doctor.py --env-file .env
# Opcional: verifica TCP do servidor configurado, sem medir velocidade.
python3 scripts/doctor.py --env-file .env --network
./install.sh
docker compose --env-file .env -f docker/compose.yaml -p speedtester logs -f collector
```

O preflight lê valores literais de `.env`, sem executar shell. Ele valida
runner, timezone, portas, limites e acesso ao daemon. A validação de binários
ocorre na imagem. AMD64 inclui o cliente Ookla; ARM64 suporta iPerf3 e fast.com.
Imagens são publicadas em GHCR como `main`, `sha-<commit>` e tags de release.
Use o SHA da revisão para uma instalação reproduzível; `up --no-build` usa as
imagens obtidas com `docker compose pull`.

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
encerrado e a tentativa fica auditada como `timeout`. Antes de repetir, o collector revalida
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
é único e imediato; a primeira leitura fica auditada como `discarded` e
somente a segunda entra nas estatísticas representativas. Sem contrato e sem
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
  conjunto representativo; consulte `/api/attempts?slot_id=...` para auditá-la;
- após timeout, os logs exibem a revalidação da conectividade e distinguem
  `OPERATOR` de `MEASUREMENT`;
- `FAILURE cause=...` é uma classificação técnica preliminar, não uma causa de
  operadora validada;
- resposta sem dados não significa que a internet está fora: pode ser o
  processo recém-iniciado ou um banco diferente via `DB_PATH`.

## Testes locais

```bash
python3 -m pip install -r requirements-dev.txt
PYTHONPATH=app python3 -m coverage run --source=app,scripts -m unittest discover -s tests -v
python3 -m coverage xml
npm ci --ignore-scripts
npx playwright install chromium
npm run test:ui
```

Os testes usam bancos temporários e dados fictícios, sem executar medições reais.

## Backup e restauração

O Compose inclui backup diário em `backup_data`, com retenção configurável.
`scripts/backup.sh` usa o mecanismo consistente do SQLite e executa
`PRAGMA integrity_check`. Falhas de backup ou replicação fazem o container
encerrar com erro e ficam visíveis em seus logs/restarts. A retenção remove
somente arquivos `speedtester-*.db` e `.db.age` antigos no diretório configurado.

```bash
DB_PATH=/data/speedtester.db BACKUP_DIR=./backups RETENTION_DAYS=30 ./scripts/backup.sh
```

Para replicação externa, configure em `.env` `BACKUP_REMOTE` com destino SSH
(ex.: `backup@backup.example.com:/srv/speedtester/`), `BACKUP_AGE_RECIPIENT` com
a chave pública age e `BACKUP_SSH_DIR` com um diretório privado contendo chave
SSH e `known_hosts` verificado. A chave privada age para descriptografia deve
ficar fora do servidor. O envio usa apenas o arquivo `.db.age`, autenticação
SSH em BatchMode e verificação obrigatória do host; falhas não são ignoradas.

```bash
docker compose --env-file .env -f docker/compose.yaml \
  -f docker/compose.backup-remote.yaml -p speedtester up -d --build backup
```

Teste a recuperação regularmente. Para uma cópia criptografada, primeiro use
`age --decrypt -i /caminho/privado/identity.txt -o snapshot.db snapshot.db.age`.
Depois pare todos os clientes do banco. Exemplo com backup local do volume:

```bash
docker compose --env-file .env -f docker/compose.yaml -p speedtester stop api collector backup
# Substitua snapshot.db pelo nome existente no volume de backups.
docker compose --env-file .env -f docker/compose.yaml -p speedtester run --rm --no-deps \
  -v speedtester_backup_data:/restore:ro api \
  python /opt/speedtester-scripts/restore.py /restore/snapshot.db \
  --destination /data/speedtester.db --services-stopped
docker compose --env-file .env -f docker/compose.yaml -p speedtester up -d --wait
```

O script valida a integridade e a tabela `samples`, recusa sidecars ativos,
constrói a cópia num arquivo temporário e substitui o destino atomicamente.
Quando existe um banco anterior, ele é preservado em `.before-restore-<data>`.
O flag `--services-stopped` é uma confirmação operacional: o script não pode
verificar todos os processos em outro container. Não remova WAL/SHM de um
banco ativo. Confirme o nome do volume com `docker volume ls`.

Ao atualizar para schema 9, o banco migra automaticamente de forma aditiva.
Slots abandonados em `RUNNING` são recuperados após `SLOT_LEASE_SECONDS`
(padrão 300s), renovada a cada 20s durante medições. Dentro da tolerância
retornam a `PENDING`; fora dela ficam `MISSED_UNKNOWN`. Não use `/api/reset`
como procedimento de atualização ou restauração.

## SonarQube

O projeto usa `sonar-project.properties`, cobertura Python/JavaScript e o workflow
`.github/workflows/sonarqube.yml`. Configure os secrets `SONAR_TOKEN` e
`SONAR_HOST_URL`, a variável `SONAR_ENABLED=true` e opcionalmente
`SONAR_PROJECT_KEY`. Prefira um token restrito à análise do projeto.
A edição Community analisa somente `main`; PRs de forks não recebem segredos.
A URL interna do servidor não fica nos arquivos públicos. O workflow aguarda
o quality gate e falha quando ele não é aprovado.

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

## Login e perfis

`API_REQUIRE_LOGIN=true` protege consultas, exportações e documentação da API.
O usuário `admin` administra dados; `viewer` só consulta e exporta. Configure
`API_ADMIN_PASSWORD_HASH` e `API_VIEWER_PASSWORD_HASH` com hashes scrypt.
Sem hash administrativo, `admin` usa o `API_ADMIN_TOKEN` existente como senha
inicial, mantendo acesso durante a migração. Não compartilhe esse token com
visualizadores. Credenciais nunca são enviadas por query string.

```bash
python3 scripts/password_hash.py
# Copie a linha gerada para .env. Para admin, altere o nome da variável.
```

Mantenha os hashes entre aspas simples em `.env`: Compose interpreta `$` em
valores sem aspas. Sessões duram oito horas (`API_SESSION_SECONDS`), usam cookie
HttpOnly/SameSite=Strict e são armazenadas como hash no banco. Logout, expiração
e rotação de credenciais revogam acesso. Escritas por sessão exigem CSRF e perfil
admin. O header `X-Admin-Token` permanece para automação administrativa.
`API_COOKIE_SECURE=true` exige HTTPS; em LAN HTTP confiável, mantenha false.
Somente modo local/demonstração pode desabilitar login explicitamente.
`/health` sem autenticação revela apenas liveness/versão, sem histórico ou rede.

## Deploy automático no staging

`scripts/deploy.py` consulta a revisão atual de `main` e exige sucesso dos
workflows CI, Container images, SonarQube e Security nessa revisão. O staging busca a
versão; não há chave SSH do staging nos secrets do repositório público.
As imagens precisam ter label da revisão, digest e attestation verificada.
Consulte [Segurança no pipeline](security-pipeline.md) para instalação dos
verificadores e configuração do Baseline obrigatório.
O script preserva volumes, para API/collector/backup, cria snapshot consistente,
sobe a versão e aguarda liveness real do collector. Uma falha restaura o snapshot
e sobe as imagens anteriores; arquivos da versão anterior são preservados.
Não remova os volumes nem use reset como procedimento de deploy.

Instale as unidades `docker/speedtester-deploy.service` e `.timer` em
`/etc/systemd/system/` e configure `/etc/speedtester-deploy.conf` com os caminhos
e nomes reais da instalação:

```ini
DEPLOY_ROOT=/opt/speedtester
COMPOSE_PROJECT=speedtester
DB_VOLUME=speedtester_db_data
BACKUP_VOLUME=speedtester_backup_data
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now speedtester-deploy.timer
sudo systemctl start speedtester-deploy.service
sudo journalctl -u speedtester-deploy.service
```

A checagem ocorre a cada dez minutos. Python 3.12+ e Docker Compose são
necessários no host. A configuração `.env` fica no host; o script não a sobrescreve
nem a envia ao GitHub. A revisão aplicada e digests ficam em `deployment.json`;
snapshots ficam em `deployment-backups` com permissões restritas. Em hosts com
SELinux, essa pasta dedicada usa rotulagem privada `:Z` nos bind mounts; não é
necessário desativar SELinux nem alterar o contexto do restante do projeto. Preserve espaço
para imagens/versões anteriores e snapshots. A API pública do GitHub tem limite
de requisições; falhas de acesso interrompem a checagem sem modificar serviços.

## Observação contínua

`/api/observation?days=14` apresenta dias efetivamente observados, sucessos,
falhas, cobertura dos slots devidos, tentativas descartadas e percentis.
A observação começa no primeiro startup desta versão e reinicia se o destino ou
runner mudar. Reiniciar o processo mantém a janela. `known_transfer_bytes`
inclui bytes informados nas tentativas iPerf3, inclusive retestes descartados;
`unknown_transfer_attempts` identifica tentativas sem contador completo.
Isso não é uma medição completa do tráfego da interface.

O destino atual não tem controle confirmado: mantenha
`MEASUREMENT_TARGET_CONTROLLED=false`. Mesmo num destino controlado, resultados
de velocidade isolados não certificam SLA. Avalie pelo menos 21 dias e verifique
lacunas de agenda, heartbeat, erros de medição e distribuição dos resultados.
Alertas permanecem locais enquanto `ALERT_WEBHOOK_URL` estiver vazio.

A entrega por webhook acontece em segundo plano, com seis tentativas e atraso
exponencial (30, 60, 120, 240 e 480 segundos). A fila sobrevive a reinícios; leases
expiradas voltam a ser tentadas. O destinatário deve deduplicar pelo header
`Idempotency-Key` ou ID do alerta: a entrega é pelo menos uma vez. Depois de seis
falhas, o alerta fica visível como `failed`. Recuperação de conectividade e
velocidade gera alerta informativo; nunca se envia uma notificação externa sem
um destino configurado pelo operador.
