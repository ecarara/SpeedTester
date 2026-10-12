# Segurança e manutenção operacional

As rotinas abaixo complementam os gates descritos em [security-pipeline.md](security-pipeline.md).
Todas as configurações, credenciais e evidências reais permanecem no servidor.

## Limites de requisição

A API conta os bytes efetivamente recebidos antes de autenticar ou interpretar JSON.
`API_MAX_BODY_BYTES=65536` limita o corpo a 64 KiB; exceder esse valor retorna HTTP 413.
O limite também vale sem `Content-Length`, com valor subestimado e em envio por chunks.
Valores inválidos de Content-Length retornam 400. Configure o mesmo limite no proxy.

`API_RATE_LIMIT_MAX_CLIENTS=10000` limita os clientes ativos em cada tabela do rate
limiter. Quando todos os espaços estão ocupados, clientes novos recebem 429;
clientes ativos conservam seus limites. Slots expirados são reutilizados.
O limite é por processo; mantenha um worker ou use um limitador compartilhado ao escalar.

## HTTPS e identidade do cliente

Use [nginx-https.conf.example](../docker/nginx-https.conf.example), substituindo o
hostname e os caminhos do certificado/chave. Configure o DNS interno para o servidor,
valide certificado, cadeia e hostname, execute `nginx -t` e recarregue Nginx.
Uma CA local requer que os dispositivos clientes confiem nessa CA.
Nunca distribua a chave privada da CA ou do certificado no repositório.

Depois de validar HTTPS, defina `API_BIND_ADDRESS=127.0.0.1` e
`API_COOKIE_SECURE=true` no `.env`. Configure `API_TRUSTED_PROXY_IPS` com os
endereços exatos pelos quais o proxy chega ao container (incluindo o gateway da
rede Docker quando houver NAT). Não use `*` nem confie em toda a LAN.
O proxy substitui X-Forwarded-For por seu cliente imediato, evitando identidade
forjada. A porta 8000 fica disponível apenas no loopback do host.
Mantenha o `.env` com modo 0600 e faça o rollout pelo deploy verificado.
O Baseline pode usar o backend loopback. Configure `HTTPS_HEALTH_URL` e
`HTTPS_CA_FILE` na configuração operacional para monitorar a cadeia TLS e o hostname.

## Reavaliação das imagens

`scripts/recheck_images.py` lê os três digests de `deployment.json`, verifica
amd64 e arm64, exige banco Grype válido e com idade máxima de 24 horas, e guarda
os relatórios completos. O timer `speedtester-image-recheck` roda semanalmente.
Falhas ou novos achados bloqueantes viram incidentes operacionais; os containers
existentes continuam em execução. O deploy também exige uma nova avaliação dos
digests candidatos **antes de parar qualquer serviço**, além dos gates e attestations.
A política permanece: todas as Critical e High com correção disponível bloqueiam.
ZAP ativo continua restrito ao ambiente descartável do GitHub Actions.

## Backup, recuperação e pasta para OneDrive

O backup publica `.last-success.json` somente após validar integridade e concluir
qualquer transporte externo configurado. A rotina diária `speedtester-backup-check`
copia esse snapshot para `BACKUP_OUTBOX`, com pasta 0700 e arquivos 0600, e restaura
uma cópia em armazenamento temporário sem rede nem acesso ao banco de produção.
Compara todas as tabelas, número de amostras e assinatura dos dados. O relatório
privado fica em `OPERATIONS_STATE_DIR/restore.json`. O espaço temporário é 256 MiB;
aumente-o com o limite de memória quando o banco ultrapassar esse tamanho.

A pasta local ainda está no mesmo servidor e **não protege contra perda do host**.
O script [sync_onedrive.py](../scripts/sync_onedrive.py) fica preparado para ativação:

1. Instale rclone e configure um remote OneDrive com a conta desejada.
2. Configure um remote `crypt` sobre uma pasta dedicada desse OneDrive.
3. Guarde o rclone.conf com modo 0600 e preserve uma cópia independente da
   configuração/chaves de criptografia para recuperação após perda do servidor.
4. Configure `RCLONE_CONFIG` e `ONEDRIVE_REMOTE` em `/etc/speedtester-operations.conf`.
5. Execute a rotina diária e confirme status `passed` de cópia e `cryptcheck`.

O script exige remote crypt, copia apenas snapshots, usa `--immutable`, verifica
o conteúdo criptografado e não remove arquivos remotos. A retenção remota deve
ser definida separadamente. Para testar a recuperação externa, baixe e decifre
um arquivo em outro host com a configuração preservada e execute
`python3 scripts/check_restore.py snapshot.db`. A validação local diária não
substitui esse teste externo. Enquanto a conta não estiver configurada, a rotina
exporta e valida backups locais, sem declarar sucesso de upload.

## Monitoramento e e-mail

`speedtester-monitor` verifica a cada cinco minutos: heartbeat, ausência de
amostras por oito horas, backup atrasado mais de 26 horas, disco abaixo de 5 GiB
ou 10%, três reinícios por hora/serviço parado, deploy com erro ou bloqueado mais
de duas horas e evidências vencidas/falhas de scan e recuperação.
Três observações consecutivas confirmam uma falha. Um incidente gera alerta no
dashboard; a recuperação gera outro registro. Persistência no host mantém estado,
fila e deduplicação entre execuções. Repetições do mesmo incidente têm intervalo
mínimo de seis horas. Entregas falhas recebem retry com atraso crescente; a fila
é limitada a 100 eventos recentes e não contém credenciais.

Para e-mail, configure no arquivo privado `/etc/speedtester-operations.conf`:

```ini
ALERT_EMAIL_TO=operator@example.com
ALERT_EMAIL_FROM=alerts@example.com
SMTP_HOST=smtp.example.com
SMTP_PORT=587
SMTP_USER=alerts@example.com
SMTP_PASSWORD_FILE=/etc/speedtester/smtp-password
```

A senha fica em arquivo 0600. Porta 465 usa TLS desde a conexão; outras portas
exigem STARTTLS com validação do certificado. O e-mail não contém IP interno,
URLs secretas ou dados das medições. Uma falha do dashboard não impede o envio
por e-mail; os dois destinos têm estado de entrega separado. Sem SMTP configurado,
os alertas ficam no dashboard e nos registros privados.

## Instalação das rotinas no host

Instale Grype pela ferramenta com checksum já adotada e copie os scripts novos
para o diretório de scripts do host junto com suas dependências locais.
Instale os pares `.service`/`.timer` de monitor, backup-check e image-recheck de
`docker/` em `/etc/systemd/system`. Os arquivos de configuração devem ser 0600:

```ini
OPERATIONS_STATE_DIR=/var/lib/speedtester-operations
BACKUP_OUTBOX=/var/lib/speedtester-backups/outbox
SECURITY_REPORT_ROOT=/var/lib/speedtester-security
ARTIFACT_RETENTION_DAYS=30
```

Execute as verificações de backup e imagens antes de habilitar os timers, então
`systemctl daemon-reload` e habilite os três timers. Os scripts usam a trava de
deploy para impedir manutenção concorrente com rollout ou rollback. Execuções
que encontram a trava ocupada são adiadas para a próxima ativação do timer.

## Retenção e atualização de dependências

A rotina diária remove artefatos reconhecidos com mais de 30 dias. Sempre preserva
release, snapshot e Baseline da implantação atual e da anterior, arquivos fora dos
padrões e links simbólicos. Exportações pendentes de envio não são apagadas;
somente arquivos anteriores a uma cópia OneDrive verificada ficam elegíveis.
A retenção do volume de backup permanece controlada por BACKUP_RETENTION_DAYS.

Dependabot acompanha semanalmente as bases Docker, inclusive Go e seus digests.
`Native dependency updates` verifica semanalmente releases estáveis de OpenSSH,
iPerf3 e age, calcula SHA256 dos arquivos nas origens oficiais e atualiza caminhos
de compilação/licenças. O PR é revisável e não faz merge automático.
Use `NATIVE_UPDATES_TOKEN` com permissão de conteúdo e PR neste repositório para
que os PRs do bot acionem os workflows obrigatórios; o GITHUB_TOKEN padrão não
aciona workflows por eventos gerados por ele. Sem token e havendo atualização,
a rotina falha explicitamente. Todos os gates continuam exigidos no deploy.
