# Conexão local de cada medição

O coletor local registra automaticamente o tipo da conexão em cada execução
iPerf3, Ookla ou fast.com. O painel mostra **Conexão local**, com o nome da
interface e o vínculo da evidência. API de amostras, exportações CSV/JSON e
auditoria das tentativas preservam essa informação. Não há pergunta ao usuário
ou preferência automática por cabo sobre Wi-Fi.

## Evidências e prioridade

1. Ookla: interface e endereço interno retornados pelo próprio CLI.
2. iPerf3: endereço de origem e destino de `start.connected` do JSON nativo.
   Os endereços são usados em memória para encontrar a interface; não são
   adicionados à evidência persistida. Upload e download com interfaces
   diferentes produzem `mixed`, sem escolher uma delas arbitrariamente.
3. Sem esses dados: rota do sistema até o IP literal do destino, se disponível.
4. Sem destino literal: rota padrão observada, marcada `default_route`.
   O painel a identifica como **Rota padrão · estimativa**. É o contexto
   disponível para fast.com; não é rastreamento dos seus múltiplos sockets.

Rotas IPv4 e IPv6 ou rotas de mesma prioridade que apontem para interfaces
diferentes deixam o caminho desconhecido. Um endereço de origem conhecido mas
não mapeável não é substituído pela rota padrão de outra interface.

Linux consulta `ip -j` e `/sys/class/net`; a ferramenta `ip` faz parte de
`iproute2` e já integra o container do collector. Wi-Fi é identificado pelos
metadados wireless, Ethernet exige evidência de dispositivo físico. Interfaces
veth, bridges e outras interfaces virtuais não são chamadas de cabo.
macOS usa as rotas, o endereço local e `networksetup -listallhardwareports`,
sem pressupor que `en0` seja Ethernet. Windows usa as rotas e os atributos de
[MSFT_NetAdapter](https://learn.microsoft.com/en-us/windows/win32/fwp/wmi/netadaptercimprov/msft-netadapter),
incluindo `NdisPhysicalMedium`, `HardwareInterface` e `Virtual`.

## Tipos e escopo

| Valor persistido | Exibição | Evidência disponível |
|---|---|---|
| `wifi` | Wi-Fi | interface wireless nativa |
| `ethernet` | Cabeada (Ethernet) | interface Ethernet física |
| `cellular` | Celular | WWAN reconhecido pelo sistema |
| `bluetooth` | Bluetooth | adaptador/porta Bluetooth reconhecido |
| `usb` | USB | porta USB identificada, sem inferir a rede a montante |
| `virtual` | Virtual | interface virtual, bridge, bond, VLAN ou veth reconhecido |
| `tunnel` | Túnel | dispositivo de túnel reconhecido; não revela sua saída física |
| `point_to_point` | Ponto a ponto | interface PPP/ponto a ponto reconhecida |
| `loopback` | Loopback | interface local de retorno |
| `mixed` | Mista | upload e download associados a interfaces diferentes |
| `unknown` / `NULL` legado | Desconhecida | informação insuficiente ou histórico anterior à detecção |

Os tipos dependem dos metadados disponíveis em cada sistema, driver e ambiente.
Não se mede a tecnologia de última milha da operadora: Ethernet até o roteador
pode usar internet celular; Wi-Fi até um hotspot continua sendo Wi-Fi. Dentro
de containers/VMs, a interface pode ser virtual mesmo com cabo no host. Não se
inspeciona o host nem se eleva privilégio para tentar adivinhar o meio físico.
A observação ocorre ao concluir a execução e não prova que o caminho permaneceu
inalterado durante todo o teste.

## Persistência e limites

O schema 12 acrescenta `connection_type`, `connection_source`,
`connection_scope` e `connection_observed_at` a `samples`. A evidência
normalizada é anexada em `evidence_json.connection`. A conexão de cada tentativa
fica em `measurement_attempts.metrics_json`, inclusive quando uma leitura
anômala é descartada. A primeira tentativa não sobrescreve o contexto do reteste.
Falhas sem resultado do runner e registros antigos permanecem sem identificação;
nenhuma medição antiga é reclassificada pelo nome da interface.

As consultas são locais, somente leitura, sem DNS, sem novos testes de banda e
sem persistir SSID, MAC ou IP local. Subprocessos compartilham um orçamento de
até cinco segundos; no iPerf3, esse tempo faz parte dos 60 segundos existentes.
Ausência das ferramentas, permissão negada e metadados desconhecidos retornam
`unknown`, sem impedir o resultado de velocidade. Não há decisão de falha da
operadora baseada apenas no meio local.

Este registro pertence à API e ao dashboard do coletor local dos pacotes
publicados. O protocolo assinado da prévia gráfica, seus perfis declarados e o
Server central não recebem campos extras por esta alteração. `Profile.link_type`
continua sendo declaração de perfil, não evidência automática por medição.
