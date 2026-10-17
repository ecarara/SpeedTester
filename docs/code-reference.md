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

`GET /api/network-map` usa `app/api/network_map.py` para agrupar amostras por
operadora, cidade e país, sem retornar IP público. A resposta inclui a origem
da coordenada (`city-centroid`, `country-centroid` ou `unavailable`) para que o
dashboard deixe explícito quando o ponto é aproximado.

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

### `app/api/network_map.py`

Normaliza nomes para selecionar centroides determinísticos de cidades e países
e calcula contagens de sucesso/falha e médias de velocidade por agrupamento.
O módulo não faz chamadas externas nem expõe o endereço IP persistido.

### `app/dashboard/network-map.js`

Renderiza o atlas SVG interativo, com marcadores acessíveis por teclado,
tooltips, filtros e lista de operadores. O componente é independente de tiles
ou CDN de mapas para continuar funcional em instalações sem acesso externo.

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

### `app/desktop_launcher.py`

Implementa o contrato inicial do launcher desktop do épico E-01. A interface
CLI oferece as ações `open`, `status`, `start`, `stop` e `restart`. A ação
`open` valida a URL do dashboard antes de delegar a abertura ao navegador; as
demais ações usam o mecanismo nativo da plataforma para controlar o serviço
configurado, sem concatenar comandos recebidos por entrada externa.

`SPEEDTESTER_DASHBOARD_URL` e `SPEEDTESTER_SERVICE_NAME` permitem ajustar a
instalação sem alterar o código. O nome padrão do serviço é
`speedtester-client.service`, que será fornecido pelos pacotes desktop; a
instalação atual pode informar outro nome durante a transição.

- `app/shared/settings.py`: lê ambiente, valida tipos simples e monta
  `Settings` imutável;
- `scripts/build_brand_assets.py`: monta ICO e ICNS usando somente PNGs
  versionados e a biblioteca padrão do Python;
- `packaging/linux/install-user.sh` e `uninstall-user.sh`: instalam ou removem
  o cliente Linux no escopo do usuário, preservando dados por padrão;
- `packaging/linux/build-deb.sh`, `build-rpm.sh` e `build-appimage.sh`:
  constroem os artefatos Linux a partir de uma virtualenv explícita;
- `packaging/linux/build-flatpak.sh`: gera o launcher Flatpak sandboxed e seu
  bundle com ID estável `io.github.ecarara.SpeedTester`;
- `packaging/linux/build-pacman.sh` e `packaging/linux/arch/PKGBUILD`:
  constroem o pacote Arch com `makepkg` e remoção pelo ciclo do pacman;
- `packaging/windows/build-launchers.ps1` e `build-msix.ps1`: produzem os
  executáveis Windows e o MSIX; `install-msix.ps1`/`uninstall-msix.ps1`
  controlam a instalação e a tarefa do cliente;
- `packaging/macos/build-app.sh`: produz o bundle `.app`, o `.app.zip` e o
  `.dmg` por arquitetura; `install-dmg.sh`/`uninstall-app.sh` controlam o
  aplicativo e o LaunchAgent do usuário;
- `scripts/build-source-tarball.sh`: preserva o source archive `.tar.gz` como
  artefato de release reproduzível a partir do Git;
- `scripts/build_sbom.py` e `scripts/generate_checksums.py`: geram SBOM SPDX
  2.3 e manifesto SHA-256 para a release;
- `scripts/validate_release_artifacts.py`: verifica checksums e o conteúdo
  mínimo de source archive, SBOM, pacotes nativos, MSIX e bundles macOS antes
  da publicação;
- `scripts/smoke_linux_install.sh`: executa instalação, upgrade e remoção do
  pacote por usuário Linux em um HOME temporário;
- `scripts/backup.sh`: cria cópia consistente do SQLite, verifica integridade
  e aplica retenção somente aos arquivos gerados pelo script;
- `scripts/compare_runners.py`: compara runners sem gravar amostras;
- `install.sh`: executa doctor, compila/valida o runner e inicia o stack Compose.

Alterações em runners, status, colunas SQLite, payloads HTTP ou semântica de
métricas são mudanças de contrato e exigem testes, documentação e changelog.
