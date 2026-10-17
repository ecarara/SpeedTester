# Client gráfico — prévia de desenvolvimento

A primeira implementação separa um assistente gráfico do serviço de coleta. A interface oferece **Instalar**, **Reparar** e **Desinstalar**, em português por padrão, inglês e espanhol. O código do Client é público; a integração com o Server continua testada no repositório privado.

Esta é uma **prévia experimental**, ainda sem certificação para instalação em workstations de produção. O download oficial de terminal Linux permanece inalterado. Os artefatos do workflow `Desktop Client preview` não substituem um release assinado.

## O que está implementado

- Assistente nativo com Tk e runtime empacotado pelo PyInstaller, sem depender de uma janela de navegador local. O pacote inclui certificados públicos de confiança para HTTPS; uma CA definida explicitamente pelo administrador continua respeitada.
- Serviço separado da interface, com adaptadores para systemd de sistema, LaunchDaemon e Windows Service de inicialização automática. Identidade dedicada, sem executar o runner como administrador/root.
- Comunicação somente por loopback, mensagens autenticadas por HMAC, proteção contra repetição e respostas vinculadas à solicitação. A interface não recebe access/refresh tokens ou chaves privadas do protocolo.
- Contribuição opcional, inicialmente desmarcada. Sem configuração/vínculo não há discovery, pareamento, transmissão de sistema operacional ou solicitação de medição. O serviço comunitário fica em espera; o standalone existente continua independente.
- “O que será enviado” abre uma lista local e rolável nos três idiomas, sem depender do navegador ou da rede. Ela descreve os campos públicos e excluídos, sem mostrar valores pessoais, tokens ou chaves. Consultar a lista não envia dados nem registra aceite. A consulta ao portal é opcional. Abrir a conta, o vínculo ou o portal sempre oferece também um endereço copiável, mesmo se o sistema informar sucesso sem mostrar o navegador.
- Pareamento pelo SDK real: código e impressão digital no assistente, login/aceite no portal, aprovação humana e tokens na fila cifrada. O assistente não aceita termos pelo participante.
- Após o aceite vigente e a autorização do pareamento, a agenda é ativada automaticamente para horários futuros. O Client valida credenciais, destino e ferramenta de medição; qualquer impedimento mantém os testes pausados e é exibido. Não há teste imediato.
- Reparo: parar o serviço, validar SQLite e autenticar o conteúdo cifrado, criar backup consistente, preservar identidade/histórico/fila e substituir arquivos do pacote. A agenda fica pausada; corrupção ou chave perdida interrompem o processo sem zerar dados.
- Desinstalação: parar/remover o serviço, preservar dados por padrão e oferecer exclusão local separada. A revogação central continua explícita no portal; exclusão local não é apresentada como revogação ou exclusão no Server.
- SQLite embutido, leitura da fila em lotes de até 256 registros e pausa de novas medições ao atingir 128 MiB de banco ou 10 mil pendências. A sincronização pode drenar pendências sem novos grants. Esses limites ainda não abrangem todo o espaço de backups/runtime, nem substituem a política futura de retenção.

## Agenda de medições

O Client programa **dois testes por período, oito por dia completo**, no fuso horário identificado na instalação: madrugada (00h–06h), manhã (06h–12h), tarde (12h–18h) e noite (18h–24h). O fuso aparece no assistente; não existe intervalo em horas a configurar. O serviço funciona com a interface fechada, enquanto o computador estiver ligado e com rede.

Os horários são sorteados, separados por pelo menos uma hora dentro de cada período, e persistidos no SQLite cifrado antes da execução. Reiniciar, reparar ou reabrir o assistente preserva o plano e a identidade. A migração da antiga agenda por intervalo pausa as medições e exige ativação explícita; não ativa testes durante a atualização.

Instalar, parear, atualizar e reparar não executam um teste imediato. O pareamento aprovado ativa a agenda; a ativação libera somente horários futuros, com pelo menos um minuto de antecedência. Cada horário tem uma tolerância de até dez minutos, limitada ao fim do próprio período e ao orçamento de duração do teste. Horários perdidos durante suspensão, desligamento, pausa ou indisponibilidade não são compensados. Uma tentativa interrompida não executa novamente o runner. Portanto, oito testes programados não garantem oito resultados concluídos.

Cada tentativa depende de token, consentimento e documentos vigentes, destino central autorizado e limites do Server. Testes usam banda e podem consumir franquia; falhas e métricas não suportadas mantêm seus estados, sem valores inventados. O cache de próximo horário não pode forçar um teste. Os testes automatizados verificam dias completos, horário de verão, reinícios, pausa e recuperação com relógio e runner sintéticos, sem medições externas.

## Desenvolvimento e testes sem medições

Use Python 3.11–3.13 e as dependências públicas. Para a interface, Tcl/Tk precisa estar disponível no ambiente de desenvolvimento; os pacotes gerados incluem esse runtime.

```bash
python -m pip install -r requirements-desktop.txt '.[desktop]'
python -m speedtester_protocol.desktop_entry --preview
python -m speedtester_protocol.desktop_entry --ui-smoke
python -m unittest discover -s tests -p 'test_desktop_*.py' -v
python scripts/build_desktop.py
```

`--preview` usa dados fictícios: não eleva privilégios, não instala serviços, não abre o portal e não faz chamadas ao Server. `--ui-smoke` instancia as telas reais nos três idiomas e encerra sem instalação/rede. Testes novos usam assinaturas e SQLite reais com transporte/runner sintéticos. O teste de independência inicia apenas um processo local em espera, sem pareamento ou coleta.

O helper administrativo só funciona em um aplicativo empacotado. Aceita operações fixas e não recebe caminhos de instalação, nomes de serviço ou comandos arbitrários. Segredos locais não passam pela linha de comando. Para o reparo desta prévia, abra o pacote baixado fora da pasta instalada. No Windows, arquivos em uso podem exigir reinicialização para concluir a remoção.

## Serviços e armazenamento previstos pelo código

| Sistema | Serviço | Dados privados do serviço |
| --- | --- | --- |
| Linux | `cararalab-speedtester-client.service`, usuário `speedtester-client` | `/var/lib/cararalab-speedtester-client` |
| macOS | `com.cararalab.speedtester.client`, usuário `_speedtester` | `/Library/Application Support/CararaLab/SpeedTesterClient` |
| Windows | `CararaLabSpeedTesterClient`, conta virtual `NT SERVICE\CararaLabSpeedTesterClient` | Pasta de dados comuns do sistema, `CararaLab\SpeedTesterClient` |

A interface guarda somente sua chave de controle local na configuração privada do usuário. O serviço guarda o SQLite cifrado e a chave de armazenamento sob sua própria identidade. No Windows são usadas ACLs; no POSIX, permissões e ownership. O conteúdo dos registros/estados é cifrado com autenticação; o arquivo SQLite ainda contém metadados de índices em claro. Administradores/root ou comprometimento da conta de serviço permanecem limites de confiança.

## Antes de disponibilizar aos participantes

1. Certificar elevação gráfica, logout, boot e manutenção nas máquinas/arquiteturas suportadas. O CI executa instalação, reinício, reparo, reinstalação e remoção reais em VMs descartáveis, além dos testes unitários com adaptadores simulados. Isso não certifica reinicialização física, diálogos UAC/polkit/macOS nem todas as distribuições.
2. Distribuir e verificar o runner nativo aprovado. O pacote incorpora iPerf3 3.22 compilado da fonte oficial fixada, com autenticação RSA e dependências inventariadas. O upstream não oferece suporte oficial em Windows; a compilação MSYS2 e as duas direções de transferência devem passar no CI nativo.
3. Produzir MSI/EXE, PKG e DEB/RPM, registrar desinstalação no sistema, resolver manutenção do aplicativo instalado e assinar/notarizar os pacotes. Os primeiros builds geram bundles ZIP/TAR experimentais com checksums e lista de componentes, sem assinatura de release.
4. Validar restauração/rollback completo, ACLs, restrições do helper e fila grande/disco cheio; implementar a retenção configurável sem descartar pendências silenciosamente.
5. Aprovar a integração privada com pareamento, renovação, suspensão/revogação, retirada de consentimento e nova versão legal; preservar os testes existentes e limitar o runner a fixtures descartáveis.
6. Somente então anunciar um instalador estável para participantes. Downloads de teste continuam explicitamente experimentais; contribuições exigem aceite e pareamento.

## Atualização em desenvolvimento: 0.3.0.dev2

O assistente e os novos pareamentos de terminal deixam de pedir host/porta iPerf3. O serviço central é responsável pelo destino; a configuração chega autenticada e assinada, vinculada à instalação, a uma solicitação e a um prazo de até cinco minutos. A identidade do destino vincula host, porta e classificação. O runner confere a correspondência com a autorização antes de executar. Não há sondagem do destino ao instalar ou parear, fallback para host informado pelo usuário, nem teste imediato. Após aceite e pareamento, a agenda futura é ativada conforme as verificações de autorização.

Sem destino central disponível, a instalação pode ser vinculada e manter a renovação normal com a agenda pausada. Ativar medições exige autorização vigente, destino válido e ferramenta disponível. O Server padrão bloqueia grants quando não há destino administrativo; compatibilidade manual antiga precisa de opção administrativa explícita. O coletor standalone existente não é alterado.

A versão fica no título/rodapé e no status. “Copiar dados para uma issue” inclui versão/build do aplicativo e serviço, plataforma e versão do Tk; exclui tokens, perfil, caminhos e endpoints. Os arquivos de download incluem a versão e um `build-info.json` vinculado ao manifesto do pacote.

O bundle Linux passa a incluir dados de composição/locale e os módulos dinâmicos Xlib encontrados no ambiente de build. O aplicativo usa esses recursos na sua própria execução, preservando idioma, ABNT2 e método de entrada do desktop. O smoke do pacote Linux usa teclas reais em Xvfb/ABNT2 para `São Paulo`, `ação`, `México` e `España`. Isso melhora a verificação do pacote; a confirmação no Omarchy real ainda depende do teste nessa distribuição. Não reescrever textos como `S~ao` por heurística nem alterar o teclado do usuário.


## Correção de composição no Client 0.3.0.dev3

O reteste no Omarchy confirmou que a versão 0.3.0.dev2 ainda recebia o acento separado, apesar do payload de locale. O teste anterior apenas comprovava o caminho com XIM funcionando. A nova regressão usa teclas reais num display descartável com XIM indisponível: o campo de controle sem correção deve produzir exatamente `S~ao`, enquanto o campo do instalador deve produzir `São`. O pacote continua testando também o caminho nativo com XIM ativo.

Os campos do formulário em X11/XWayland recebem um fallback local para as teclas mortas latinas de til, agudo, grave, circunflexo, trema e cedilha. Ele atua apenas quando esses eventos chegam sem composição; caracteres já compostos e métodos de entrada funcionando seguem o fluxo normal. Espaço/dobrar acento permitem pontuação literal. Backspace/Escape cancelam a composição; foco, mouse, atalhos e colagem limpam o estado pendente. Há testes de seleção/cursor, caixa alta e preservação de `ç`, Unicode e pontuação literal.

Não há substituição de textos como `S~ao`, alteração do layout ABNT2, mudança de idioma/XMODIFIERS, hook global nem registro de teclas. A aplicação mantém a composição nativa em Windows/macOS. O cenário automatizado reproduz a ausência de composição; a confirmação final no Omarchy permanece dependente do reteste da nova versão. Instalação/pareamento continuam sem medições.


## Verificação funcional do Client 0.3.0.dev6

O CI separa as verificações, preserva os relatórios `acceptance-*.json` e bloqueia a publicação se qualquer uma falhar:

| Camada | O que é exercitado | Limite |
| --- | --- | --- |
| Interface real Tk e IPC autenticado | Instalação com/sem contribuição; validação de campos; lista de dados e seus links; código de vínculo, nova tentativa, cancelamento e aprovação; status; configurar/salvar; ativação recusada/confirmada e pausa; conta; cópia de link/diagnóstico; navegação; confirmações de reparo/desinstalação, preservar/apagar dados; falhas e recuperação da interface | Respostas do Server assinadas e sintéticas; elevação e manutenção simuladas nesta camada; runner proibido |
| Todas as opções do formulário | Oito tecnologias, Ethernet/Wi-Fi e português/inglês/espanhol, com seleção real dos widgets e preservação do perfil | Não identifica automaticamente o equipamento físico |
| Navegador a partir do pacote congelado | O abridor do próprio sistema deve carregar uma página HTTP de loopback em navegador real; observar somente o retorno do abridor não é suficiente | Não autentica uma conta nem registra aceite; Linux usa Chrome isolado no display de CI |
| Serviços nativos reais nos três sistemas | Helper congelado, systemd/LaunchDaemon/SCM, identidade dedicada e configuração de autostart, IPC, parar/iniciar, reparar com backup, preservar bytes cifrados/chaves/fila, reinstalar, desinstalar preservando e excluir os dados depois | VMs descartáveis, helper já elevado; sem clique nos diálogos administrativos, logout ou reinicialização física |
| SDK/Server privado com PostgreSQL | Pareamento, renovação, métricas separadas, revogação, suspensão, retirada de consentimento e novo aceite legal | Runners sintéticos; não substitui o login/aceite humano da conta real |

A suíte gráfica usa `SPEEDTESTER_GUI_TESTS=1 python scripts/test_graphical_flows.py` (no Linux, dentro de `xvfb-run -a`). No PowerShell, defina `$env:SPEEDTESTER_GUI_TESTS='1'` antes de executar o script. Ela não chama o helper de manutenção real. Os scripts de navegador e lifecycle recusam execução fora de runners GitHub descartáveis e não devem ser usados para testar uma workstation com dados reais.

A conta usa o Server salvo na instalação, inclusive quando o assistente acaba de ser aberto. A abertura do navegador tem limite de tempo e não ocupa o bloqueio de manutenção. Bibliotecas e loaders de locale/Tk do pacote não devem interferir nos programas do sistema. Uma falha em um retorno da interface não encerra o processamento dos próximos cliques. Trocar o idioma preserva tecnologia, conexão e campos. A opção de apagar dados é desmarcada a cada nova operação de desinstalação; reinstalar após exclusão cria uma nova chave de controle persistida.

Os testes mantêm medições desativadas. Ativação e pausa na suíte gráfica usam somente um runner que falha se for chamado. A ausência do componente real de medição também é testada e deve manter a agenda pausada. Não há certificação de coleta nativa no Omarchy/Wayland real, de elevação interativa ou de recuperação após reboot físico nesta prévia.


## Código de vínculo no Client 0.3.0.dev7

Ao marcar a contribuição e concluir **Instalar e continuar** ou **Salvar**, o assistente solicita o código automaticamente e o exibe em destaque, antes de oferecer o portal. Use **Copiar código**, abra o portal, entre na conta, registre o aceite se solicitado e informe esse código. Confira a impressão digital e autorize a instalação; o Client confirma o vínculo sem iniciar medições. Abrir a conta no Server, por si só, não gera códigos.

Na tela **Seu serviço**, **Continuar vínculo / mostrar código** recupera o vínculo pendente. Reabrir a interface ou recuperar o código vigente preserva a autorização pendente. O horário de validade é mostrado no fuso do computador; após a expiração, o código desaparece e uma ação explícita gera outro. Falhas de conexão deixam uma mensagem com nova tentativa, sem exigir reinstalação. Sem contribuição selecionada, a instalação não solicita nenhum código nem contata o Server.

A regressão gráfica reproduz a ausência do código antes da correção e verifica geração automática, visibilidade no tamanho mínimo da janela, cópia, recuperação após reabrir a interface, expiração, nova tentativa e erro de conexão com recuperação. São 11 casos gráficos com widgets Tk e IPC autenticado reais; o Server usa respostas assinadas sintéticas e o runner de medições é proibido. A integração com o Server privado permanece ativa.

## Normalização e limite por máquina — 0.3.0.dev8

Operadora, país, estado/região e cidade aparecem em maiúsculas ao digitar ou colar. Envio e recebimento também consolidam espaços e normalizam Unicode sem retirar acentos: `são paulo` vira `SÃO PAULO`. Endereço do Server e opções técnicas não são alterados. A atualização incrementa a versão de perfis antigos quando necessário e preserva o histórico e as assinaturas originais.

Após aceite vigente e pareamento, o Client obtém uma agenda assinada do Server para a identificação pseudônima da máquina. Cópias e reinstalações no mesmo sistema compartilham essa agenda: duas tentativas por período e até oito no dia local. A autorização central impede que outra cópia execute o mesmo horário. Trocar conta, token, perfil ou fuso local não abre outra cota. A identidade bruta do sistema não sai da máquina e não é incluída no diagnóstico copiável; consulte o item 9 de **O que será enviado**.

Instalar, parear ou reparar continua sem executar testes. O Server exige uma versão de privacidade que divulgue a identificação pseudônima e novo aceite quando os documentos mudarem. Sem identificador disponível, vínculo/autorização válida ou slot central vigente, não há nova medição. O mecanismo não é attestation física; reinstalação/clonagem do sistema, Client modificado ou identificadores falsos são limites explícitos. A instalação gráfica e o serviço continuam experimentais.


### Status e confirmações — prévia 0.3.0.dev9

As confirmações de ativação, reparo e desinstalação usam o idioma selecionado no Client, incluindo Sim/Não, Yes/No e Sí/No. Escape, fechamento da janela e Enter no botão Não cancelam sem executar a operação; a ativação exige a escolha afirmativa. O texto de ativação descreve somente os próximos horários agendados e não inicia teste imediato.

A tela de status distingue instalação/configuração, vínculo salvo e testes ativos ou pausados. Mostra a última resposta do serviço, o próximo horário somente quando os testes estão habilitados, a última tentativa finalizada registrada nesta versão, registros com recebimento confirmado pelo Server e pendências. Esses contadores são de registros, não de testes bem-sucedidos; uma tentativa pode produzir várias métricas, inclusive erros. A falta de timestamp não afirma que nunca houve histórico. A última falha de ativação fica visível até uma nova tentativa bem-sucedida. Atualizar status consulta somente o IPC local: não faz discovery, renovação, envio ou medição. Se o serviço não responder, a interface não mantém o estado anterior como confirmação de funcionamento atual.

A ausência local da ferramenta de medição é informada antes de tentar ativar, e o botão de ativação fica indisponível enquanto ela faltar. Essa verificação usa somente a instalação local; não testa a conexão nem consulta destinos de rede.

## Atualização de uma instalação existente

Ao escolher Instalar, o assistente consulta o serviço local e carrega operadora, país, região, cidade, tecnologia, enlace, endereço do Server e fuso existentes. O upgrade substitui o runtime e preserva SQLite cifrado, chaves, credenciais de vínculo, filas, recibos e cotas consumidas. Um vínculo existente não exige novo pareamento. A escolha anterior de agenda ativa ou pausada é mantida; horários vencidos durante a atualização não são compensados, e a primeira execução só pode ocorrer em um horário futuro, com pelo menos um minuto de antecedência após o reinício. Se o serviço só responder após o upgrade, seus dados existentes prevalecem sobre o formulário inicialmente vazio.

Reparar continua sendo uma operação distinta: preserva os dados e pausa a agenda para revisão. Uma revogação, suspensão ou exigência de novo aceite não é removida por upgrade, reparo ou reinstalação.

## Ferramenta incorporada e destino autenticado

A prévia 0.3.0.dev11 inclui iPerf3 3.22 nos três sistemas, sem pedir que o participante instale ferramentas ou informe destinos. A fonte oficial tem checksum fixo; os binários, bibliotecas criptográficas, licenças, inventário de componentes e hashes acompanham os pacotes. No Windows, o runtime MSYS2 e seu código-fonte correspondente são identificados por checksum; o arquivo de fontes é distribuído no mesmo release. A assinatura/notarização Apple permanece pendente.

O Server assina a política de destino. Depois de validar token, prova de posse, consentimento, documentos vigentes, cota e início autorizado da tentativa, ele emite acesso efêmero de uso único para upload e download. A identidade do destino vincula também o modo de autenticação. Credenciais RSA de cada tentativa ficam apenas em memória/arquivos temporários protegidos e não aparecem no SQLite, nos argumentos dos processos ou nos diagnósticos. Não há fallback para um servidor público não autorizado.

Cada tentativa tem até 30 segundos e até 100.000.000 bytes de payload total (metade por direção, arredondada em blocos de 1.024). Até oito tentativas completas podem usar aproximadamente 800 MB/dia de payload, além de cabeçalhos, controle e retransmissões. Conexões rápidas podem completar o orçamento em pouco tempo: esse resultado não comprova SLA nem substitui uma campanha metrológica. Latência, jitter e perda não fornecidos por esse método permanecem explicitamente não suportados.

O CI compila o pacote real de cada plataforma e verifica autenticação RSA, upload/download, inventário e encerramento dos endpoints contra fixtures descartáveis em 127.0.0.1, com apenas 8.192 bytes de payload. A integração do Server repete o fluxo completo no Linux descartável e rejeita parâmetros fora do grant antes de criar fluxos de dados. Essas verificações não medem a conexão do usuário nem chamam destinos operacionais.

## Velocidade contratada

O formulário permite informar **download contratado** e **upload contratado**, separadamente, em Mbps (1 Gbps = 1.000 Mbps), nos três idiomas. Os campos são opcionais: vazio significa desconhecido; não se presume simetria. Valores decimais usam vírgula ou ponto, sem separadores de milhar. Os valores são enviados em bit/s no perfil versionado, sem perda por arredondamento. Upgrade carrega ambos, preservando o vínculo.

O status compara cada direção do resultado aceito mais recente com o valor declarado no mesmo perfil: medido ÷ contratado × 100. Resultados indisponíveis não viram zero, percentuais acima de 100 são mantidos e uma alteração do plano não recalcula o histórico. As métricas originais e suas assinaturas permanecem intactas.
