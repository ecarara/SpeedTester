# Protocolo de contribuição: referência de integração

Esta é uma referência técnica do SDK de contribuição e de suas credenciais;
não é uma segunda edição do produto. Instalações de usuários usam os pacotes
da [mesma release SpeedTester](https://speedtester.cararalab.com.br/client) ou
`install-speedtester-client.py`, com [destino automático ou manual](server-selection.md).
O nome de compatibilidade `install-community.sh` encaminha ao mesmo instalador.

## Integração do SDK em ambientes de desenvolvimento

Suporte: Linux amd64/arm64, CPython 3.11–3.14 (`>=3.11,<3.15`) com módulo `venv`, iPerf3 e uma sessão systemd do usuário. CPython 3.14 é o runtime alvo; 3.15 não é suportado. Instale os pré-requisitos pelo gerenciador de pacotes da distribuição. Execute o instalador a partir de uma revisão verificada do repositório, como usuário normal:

```bash
speedtester-client setup --server https://speedtester.cararalab.com.br
```

O assistente pede operadora, país, região, cidade, tecnologia de acesso e cabeado/Ethernet ou Wi-Fi. Não tenta inferir fibra pelo endereço IP. O destino de teste é configurado automaticamente pelo Server. A agenda fixa programa dois testes por período (00h–06h, 06h–12h, 12h–18h e 18h–24h), oito por dia completo, no fuso da instalação, sujeita à autorização e às cotas centrais. Não existe intervalo em horas a configurar.

O terminal exibe um código, endereço HTTPS e impressão digital. Abra o endereço no seu navegador, entre pelo provedor disponível, revise os Termos e a Política de Privacidade e registre a autorização de contribuição. Na página de pareamento, digite o código e confirme a impressão digital da instalação que você iniciou. Não aprove códigos enviados por terceiros.

A instalação termina automaticamente após a aprovação. Não é necessário copiar tokens, escolher chaves criptográficas nem editar `.env`. Nenhuma medição é executada pelo instalador; apenas horários futuros podem ser executados, sem compensar horários perdidos. A agenda do instalador gráfico começa pausada e depende de ativação explícita. Veja os detalhes de [agenda e consumo](desktop-client.md#agenda-de-medições).

O instalador usa `~/.local/lib/speedtester-client/venv`, estado privado em `~/.local/share/speedtester-client` e `speedtester-client.service` do usuário. Não instala daemon como root. Para executar após boot sem login, um administrador pode habilitar `loginctl enable-linger USUARIO` explicitamente. Sem linger, o serviço segue o ciclo da sessão do usuário.

## Operação

```bash
systemctl --user status speedtester-client.service
journalctl --user -u speedtester-client.service
~/.local/lib/speedtester-client/venv/bin/speedtester-client status
systemctl --user stop speedtester-client.service
```

A conta autenticada pode listar e revogar seus clients na página de participação. Revogar ou retirar a contribuição bloqueia novos grants e envios; renovar um token não remove esse bloqueio. Atualização de documentos obrigatórios exige novo aceite no portal. O client registra códigos de estado nos logs sem imprimir tokens, documentos, endereços de medição ou métricas.

Access tokens duram 15 minutos. O serviço renova antes da expiração, troca access/refresh token e vincula a renovação à chave de posse. Refresh tokens têm janela de inatividade de 30 dias, estendida pela rotação válida. Reutilizar um refresh token com outra identificação de renovação revoga a família. Recuperação da mesma renovação, assinada pela mesma instalação, fica limitada a 120 segundos e não restaura uma geração já substituída.

Depois de inatividade prolongada ou perda da janela de recuperação, pare o serviço e repareie explicitamente:

```bash
systemctl --user stop speedtester-client.service
~/.local/lib/speedtester-client/venv/bin/speedtester-client setup --repair --server https://speedtester.cararalab.com.br
systemctl --user start speedtester-client.service
```

Somente a mesma conta pode recuperar uma instalação ativa com ambas as chaves originais. O fluxo não reativa um client revogado. Mudar o Server ou sua chave pública exige revisão explícita; a instalação rejeita alteração silenciosa do destino.

## Medições e limites

O modo comunitário usa seu próprio serviço e exige autorização central antes de iniciar iPerf3. O coletor standalone continua independente e não é habilitado para replicação automaticamente.

O adaptador inicial mede upload e download TCP, duração, payload transferido e retransmissões quando disponíveis. Latência, jitter e perda não são obtidos por esse adaptador e são enviados como `not-supported`, sem valores artificiais. Adaptadores futuros de qualidade precisam preservar método e unidade por métrica.

O grant limita o tempo total e o payload de upload/download. O adaptador usa uma única conexão de dados por direção, `--bytes` e blocos limitados, sem período omitido. O contador de payload não inclui headers, retransmissões ou conexão de controle; não é limite exato do tráfego físico. Tentativas interrompidas podem não ter contador final. Consulte a [documentação do iPerf3](https://software.es.net/iperf/invoking.html) para a semântica dos parâmetros.

Um alvo na LAN mede a rede local. Um destino externo sem controle confirmado produz medições exploratórias; falha desse destino não demonstra falha da operadora nem SLA.

## Estado e testes

Fila, chaves privadas, perfil, tokens e estado de renovação ficam cifrados com autenticação. O diretório é `0700` e a chave local é `0600`. A chave de cifragem precisa permanecer acessível ao processo; root ou comprometimento do usuário pode acessá-la. Criptografia detecta alteração dos dados e protege uma cópia isolada do banco, mas não garante veracidade física de um participante hostil.

Os unitários públicos exercitam pareamento, assinatura, DPoP, rotação, persistência, concorrência de processos, serviço e runner usando dados sintéticos. A suíte privada testa o client real contra o Server e PostgreSQL descartável, incluindo o assistente, reinício, revogação e resposta perdida. Nenhum teste usa medições externas ou credenciais de participantes.

O instalador de código-fonte seleciona automaticamente CPython 3.14, com
fallback para 3.13, 3.12 ou 3.11. Se `python3` apontar para 3.15, instale também
3.14; não é necessário mudar o Python do sistema. A seleção validada é passada
ao instalador Linux por `SPEEDTESTER_PYTHON`, que também pode indicar um caminho
explícito para um interpretador suportado. Uma seleção explícita inválida
interrompe a instalação em vez de usar outro Python silenciosamente.
