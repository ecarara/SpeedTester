# Client gráfico — prévia de desenvolvimento

A primeira implementação separa um assistente gráfico do serviço de coleta. A interface oferece **Instalar**, **Reparar** e **Desinstalar**, em português por padrão, inglês e espanhol. O código do Client é público; a integração com o Server continua testada no repositório privado.

Esta é uma **prévia experimental**, ainda sem certificação para instalação em workstations de produção. O download oficial de terminal Linux permanece inalterado. Os artefatos do workflow `Desktop Client preview` não substituem um release assinado.

## O que está implementado

- Assistente nativo com Tk e runtime empacotado pelo PyInstaller, sem depender de uma janela de navegador local. O pacote inclui certificados públicos de confiança para HTTPS; uma CA definida explicitamente pelo administrador continua respeitada.
- Serviço separado da interface, com adaptadores para systemd de sistema, LaunchDaemon e Windows Service de inicialização automática. Identidade dedicada, sem executar o runner como administrador/root.
- Comunicação somente por loopback, mensagens autenticadas por HMAC, proteção contra repetição e respostas vinculadas à solicitação. A interface não recebe access/refresh tokens ou chaves privadas do protocolo.
- Contribuição opcional, inicialmente desmarcada. Sem configuração/vínculo não há discovery, pareamento, transmissão de sistema operacional ou solicitação de medição. O serviço comunitário fica em espera; o standalone existente continua independente.
- Pareamento pelo SDK real: código e impressão digital no assistente, login/aceite no portal, aprovação humana e tokens na fila cifrada. O assistente não aceita termos pelo participante.
- Agenda inicialmente pausada; ativação explícita valida credenciais centrais e reserva o primeiro slot para um intervalo futuro. Instalar, parear ou reparar não executa teste de velocidade.
- Reparo: parar o serviço, validar SQLite e autenticar o conteúdo cifrado, criar backup consistente, preservar identidade/histórico/fila e substituir arquivos do pacote. A agenda fica pausada; corrupção ou chave perdida interrompem o processo sem zerar dados.
- Desinstalação: parar/remover o serviço, preservar dados por padrão e oferecer exclusão local separada. A revogação central continua explícita no portal; exclusão local não é apresentada como revogação ou exclusão no Server.
- SQLite embutido, leitura da fila em lotes de até 256 registros e pausa de novas medições ao atingir 128 MiB de banco ou 10 mil pendências. A sincronização pode drenar pendências sem novos grants. Esses limites ainda não abrangem todo o espaço de backups/runtime, nem substituem a política futura de retenção.

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

1. Certificar instalação, privilégios, parada/recuperação, logout, boot e manutenção nos sistemas/arquiteturas reais. Os testes de lifecycle atuais substituem os adaptadores do sistema por mocks; não constituem essa certificação.
2. Distribuir e verificar o runner nativo aprovado. **iPerf3 não está incluído nesta prévia**, e o upstream não oferece suporte oficial em Windows. Não anunciar coleta pronta nessa plataforma antes da validação do adaptador e da distribuição escolhida.
3. Produzir MSI/EXE, PKG e DEB/RPM, registrar desinstalação no sistema, resolver manutenção do aplicativo instalado e assinar/notarizar os pacotes. Os primeiros builds geram bundles ZIP/TAR experimentais com checksums e lista de componentes, sem assinatura de release.
4. Validar restauração/rollback completo, ACLs, restrições do helper e fila grande/disco cheio; implementar a retenção configurável sem descartar pendências silenciosamente.
5. Aprovar a integração privada com pareamento, renovação, suspensão/revogação, retirada de consentimento e nova versão legal; preservar os testes existentes e limitar o runner a fixtures descartáveis.
6. Somente então trocar os botões do site pelos pacotes efetivamente aprovados.

## Atualização em desenvolvimento: 0.3.0.dev2

O assistente e os novos pareamentos de terminal deixam de pedir host/porta iPerf3. O serviço central é responsável pelo destino; a configuração chega autenticada e assinada, vinculada à instalação, a uma solicitação e a um prazo de até cinco minutos. A identidade do destino vincula host, porta e classificação. O runner confere a correspondência com a autorização antes de executar. Não há sondagem do destino ao instalar ou parear, fallback para host informado pelo usuário, nem início automático da agenda.

Sem destino central disponível, a instalação pode ser vinculada e manter a renovação normal com a agenda pausada. Ativar medições exige autorização vigente, destino válido e ferramenta disponível. O Server padrão bloqueia grants quando não há destino administrativo; compatibilidade manual antiga precisa de opção administrativa explícita. O coletor standalone existente não é alterado.

A versão fica no título/rodapé e no status. “Copiar dados para uma issue” inclui versão/build do aplicativo e serviço, plataforma e versão do Tk; exclui tokens, perfil, caminhos e endpoints. Os arquivos de download incluem a versão e um `build-info.json` vinculado ao manifesto do pacote.

O bundle Linux passa a incluir dados de composição/locale e os módulos dinâmicos Xlib encontrados no ambiente de build. O aplicativo usa esses recursos na sua própria execução, preservando idioma, ABNT2 e método de entrada do desktop. O smoke do pacote Linux usa teclas reais em Xvfb/ABNT2 para `São Paulo`, `ação`, `México` e `España`. Isso melhora a verificação do pacote; a confirmação no Omarchy real ainda depende do teste nessa distribuição. Não reescrever textos como `S~ao` por heurística nem alterar o teclado do usuário.
