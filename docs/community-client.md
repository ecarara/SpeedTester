# Client comunitário: instalação e pareamento

Este fluxo está implementado no branch de integração. O serviço central precisa estar implantado, com login OIDC configurado e documentos vigentes publicados, para aceitar instalações. A existência do domínio não confirma essa implantação.

## Instalação Linux

Suporte inicial: Linux amd64/arm64, Python 3.11 ou superior com módulo `venv`, iPerf3 e uma sessão systemd do usuário. Instale os pré-requisitos pelo gerenciador de pacotes da distribuição. Execute o instalador a partir de uma revisão verificada do repositório, como usuário normal:

```bash
./install-community.sh --server https://speedtester.cararalab.com.br
```

O assistente pede operadora, país, região, cidade, tecnologia de acesso, cabeado/Ethernet ou Wi-Fi, destino iPerf3 e intervalo. Não tenta inferir fibra pelo endereço IP. O intervalo inicial é de uma a 24 horas e permanece sujeito às cotas do Server.

O terminal exibe um código, endereço HTTPS e impressão digital. Abra o endereço no seu navegador, entre pelo provedor disponível, revise os Termos e a Política de Privacidade e registre a autorização de contribuição. Na página de pareamento, digite o código e confirme a impressão digital da instalação que você iniciou. Não aprove códigos enviados por terceiros.

A instalação termina automaticamente após a aprovação. Não é necessário copiar tokens, escolher chaves criptográficas nem editar `.env`. Nenhuma medição é executada pelo instalador; o primeiro slot é reservado para um intervalo após o pareamento.

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
