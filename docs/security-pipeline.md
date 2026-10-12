# Segurança no pipeline e no deploy

O deploy exige sucesso de CI, Container images, SonarQube e Security para o
mesmo commit de `main`. Falhas ou evidências ausentes impedem a atualização.

| Controle | Execução | Bloqueio |
| --- | --- | --- |
| Grype | API, collector e backup; PR em amd64, publicação em amd64 e arm64 | Todas as Critical e High com correção disponível |
| Conftest | Compose normalizado no CI e configuração final no host | Violação de política |
| ZAP ativo | API descartável no GitHub Actions, com OpenAPI autenticado | Alertas High e falhas de execução |
| Attestation | Cada digest antes de executar a imagem no staging | Proveniência inválida, ausente ou de outro commit/workflow |
| ZAP Baseline | Após iniciar a versão no staging | Alertas High e falhas de execução; rollback |

O Grype mantém todos os achados no JSON, inclusive High sem correção ou
`wont-fix`. Esses achados devem ser acompanhados; uma execução aprovada não
significa ausência de vulnerabilidades. `scripts/check_image_report.py` aplica
a política aprovada e exige evidência de banco de vulnerabilidades válido.
Relatórios e resumos do CI ficam como artifacts por 14 dias.

O Conftest exige filesystem somente leitura, limites de memória/CPU/processos,
`no-new-privileges`, descarte de capabilities e UID 10001 na API e collector.
Permissões excepcionais são restritas a CHOWN na inicialização do volume,
NET_RAW no collector e DAC_OVERRIDE no backup. Redes host, containers
privilegiados, mounts arbitrários e autenticação desativada são rejeitados.
No deploy, imagens também precisam estar fixadas por digest.

O ambiente do ZAP ativo contém somente API e um volume SQLite novo, preenchido
com dados sintéticos. Sua rede Docker é interna, sem saída para os destinos de
medição. O wrapper verifica nome do projeto, volume, rede, marcador de fixture
e modo demo antes de iniciar. O token usado é público e exclusivo da fixture.
O volume é destruído ao final, inclusive em falhas. O staging usa exclusivamente
`zap-baseline.py`, sem scan ativo nem credenciais administrativas no scanner.
Baseline faz requisições de descoberta e análise passiva das respostas.

As imagens recebem proveniência assinada pelo GitHub Actions após o Grype
aprovar o digest publicado. O host usa `gh attestation verify`, exigindo o
repositório oficial, `.github/workflows/images.yml`, `refs/heads/main`, o SHA
esperado e runner hospedado no GitHub. Bundles públicos permitem verificação
sem token GitHub no staging. A label de revisão permanece como checagem
adicional. Releases por tag não sobrescrevem a tag `sha-...` usada pelo deploy.
O inicializador do volume usa a mesma imagem verificada do backup, sem rede;
assim não há um runtime auxiliar fora dos scans e da verificação de proveniência.

## Instalação no host

Python 3.12+, Docker Compose, GitHub CLI e Conftest são necessários.
`scripts/install_security_tools.py` instala binários das versões fixadas em
`security/tools.json` e verifica SHA-256 antes de extrair o binário. A imagem
ZAP também é fixada por digest. Instale os executáveis em um PATH confiável do
serviço systemd e atualize o script de deploy antes de reativar o timer.

Além dos campos descritos em [Operações](operations.md), configure no arquivo
privado `/etc/speedtester-deploy.conf`:

```ini
STAGING_BASELINE_URL=http://staging.example.invalid:8000/
SECURITY_REPORT_ROOT=/var/lib/speedtester-security
BACKUP_REMOTE_ENABLED=false
```

Use a URL real apenas no host. Quando o backup remoto estiver configurado,
ative `BACKUP_REMOTE_ENABLED=true`; o overlay é preservado no deploy e rollback.
A configuração Compose renderizada contém credenciais: ela é avaliada em
arquivo temporário privado e não é publicada nos logs. Relatórios do Baseline
ficam em diretório privado no host e podem conter endereços internos; não os
publique como artifacts do repositório. Bind mounts dedicados usam `:Z` em
hosts SELinux.

Antes da migração, o deploy para os clientes SQLite e cria snapshot usando a
imagem anterior. Após subir a candidata, valida o collector e executa Baseline.
Uma falha restaura o banco e os serviços anteriores; o estado de deploy só é
atualizado após aprovação. Preserve snapshots, relatórios e imagens anteriores.

## Verificação após publicação

O deploy executa Grype novamente sobre os digests candidatos antes de parar os
serviços, usando um banco válido de no máximo 24 horas. O timer semanal também
reavalia os digests em execução. Falhas viram incidentes operacionais sem parar
serviços existentes. Veja [operational-hardening.md](operational-hardening.md).
