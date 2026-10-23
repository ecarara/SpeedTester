# Seleção do servidor de medição

O SpeedTester tem um único cliente, distribuído nos formatos de cada sistema.
O servidor de medição é opcional: `IPERF3_SERVER` vazio ativa a seleção
geográfica; preenchido usa exatamente o host e a porta escolhidos pelo usuário.
Uma falha no host manual não muda a escolha silenciosamente.

## Seleção automática

No horário da medição, o coletor identifica a localização aproximada da conexão
com a mesma consulta de metadados IP já usada para operadora/cidade/país. As
coordenadas são usadas em memória para calcular a distância de grande círculo
(Haversine) até os centroides das cidades do catálogo público finito. Seleciona
o destino de menor distância, usando a capacidade anunciada apenas para
desempatar destinos na mesma cidade. Não mede todos os destinos nem escolhe
o resultado mais alto. A resolução de localização participa do limite total
de 60 segundos; instalar não executa teste de banda.

Se o destino automático recusar a conexão ou informar que está ocupado antes
de produzir o primeiro resultado de upload, o coletor tenta o próximo da mesma
ordenação. São no máximo três destinos por tentativa, incluindo o primeiro,
todos compartilhando o mesmo orçamento de 60 segundos, inclusive geolocalização,
upload, download e ping. Não há varredura de hosts nem comparação de velocidades
para escolher um resultado favorável.

Depois de um upload bem-sucedido, o download usa obrigatoriamente o mesmo
destino. Uma falha posterior não mistura resultados entre servidores. Velocidade
baixa não provoca troca de destino: continua submetida à regra de anomalia já
existente. Timeouts mantêm a política de diagnóstico de conectividade e nova
primeira tentativa; não são convertidos em conexão recusada. Um servidor manual
nunca é substituído automaticamente.

O catálogo inicial fica em `app/collector/target_selection.py`, com data e
fonte explícitas: [catálogo público iPerf3](https://github.com/R0GGER/public-iperf3-servers).
Os hosts/portas e suporte a upload/download foram conferidos nos metadados
publicados em 23/10/2026. Os endpoints são públicos e externos ao SpeedTester;
capacidade anunciada, disponibilidade e proximidade geográfica não garantem
roteamento, velocidade ou SLA. O destino efetivo é persistido com cada
resultado; modo de seleção, distância estimada e revisão do catálogo ficam
no registro de tentativa.
O histórico de destinos tentados (`target_attempts`) também é persistido nos
metadados da tentativa e na evidência da amostra, inclusive quando todos falham.
Os erros mostram host/porta e a mensagem do iPerf3 sem o envelope de informações
do sistema. Conexão recusada/servidor ocupado permanece erro de medição, não
prova de indisponibilidade da operadora. Registros antigos são preservados.

Se a consulta retornar somente cidade/país, o resultado registra explicitamente
a precisão reduzida (`automatic-city` ou `automatic-country`). Se não houver
localização utilizável, registra uma falha de seleção e orienta confirmar a
localização ou informar um destino. Não atribui essa falha à operadora.

## Escolha opcional

O configurador do pacote confirma fuso horário e modo de seleção. Ao editar os
parâmetros, é possível informar host/porta ou digitar `auto` para voltar ao modo
automático. A configuração existente é preservada ao atualizar.

No Linux, também é possível editar `~/.config/speedtester/speedtester.env`:

```ini
# Automático
IPERF3_SERVER=
IPERF3_PORT=5201
# Localização confirmada opcional; vazia usa a localização da conexão.
SPEEDTESTER_COUNTRY_CODE=
SPEEDTESTER_CITY=
```

Para fixar um destino, preencha `IPERF3_SERVER` com o hostname/IP e
`IPERF3_PORT` com a porta. Depois reinicie `speedtester-client.service`.
O mesmo código de seleção está nos pacotes Linux, Windows e macOS.
