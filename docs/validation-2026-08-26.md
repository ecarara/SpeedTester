# Validação de banda — 26/08/2026

## Ambiente

- Ambiente: servidor de validação em rede local (identidade omitida)
- Interface: Ethernet no host; `eth0` dentro do container
- Endereços do host e gateway, hostname e caminho de instalação omitidos
  da versão pública para preservar a infraestrutura interna.
- Cliente observado: Ookla Speedtest `1.2.0.84`
- Contrato de referência: 1 Gbps de download

## Resultado das medições

Conversão usada: `Mbps = bandwidth_bytes_per_second × 8 / 1_000_000`.

| Medição | Servidor | Download | Upload | Ping | Perda |
|---|---|---:|---:|---:|---:|
| 1 | Amigo internet / Guarulhos | 945,35 Mbps | 564,79 Mbps | 5,78 ms | 0% |
| 2 | IX.COA Systems / Cotia | 9,51 Mbps | 24,25 Mbps | 5,82 ms | não reportada |
| 3 | GR FAST NET / Guarulhos | 825,83 Mbps | 560,86 Mbps | 5,84 ms | 0% |
| 4 | Portal Telecom / Bayeux, ID 29564 | 912,51 Mbps | 431,69 Mbps | 43,59 ms | 0% |

## Histórico disponível no servidor

O dashboard retornou 43 medições, todas marcadas como sucesso:

- download médio: `767,60 Mbps`;
- download mediano: `913,70 Mbps`;
- download mínimo/máximo: `23,35 / 935,64 Mbps`;
- upload médio: `269,92 Mbps`;
- upload mediano: `232,65 Mbps`;
- upload mínimo/máximo: `6,63 / 583,64 Mbps`.

## Conclusão

O download é coerente com uma contratação de 1 Gbps quando o teste usa um
servidor adequado: os testes bons ficaram entre aproximadamente 826 e 945
Mbps, ou 82,6% a 94,5% do nominal. O resultado de 9,5 Mbps é uma anomalia de
servidor/rota ou saturação momentânea, não evidência suficiente de que a linha
inteira esteja limitada a 9,5 Mbps.

O histórico confirma capacidade próxima de 1 Gbps pela mediana, mas a média é
reduzida por pontos muito baixos. Por isso o projeto deve manter servidor/CDN,
horário, quadrante e evidências do teste, além de usar mediana e percentis na
análise.

## Escopo e validade

Este é um relatório histórico do baseline obtido em 26/08/2026. Ele valida a
coerência de alguns destinos Ookla com uma contratação de 1 Gbps, mas não é um
relatório de SLA nem substitui a série histórica do scheduler por quadrantes.
Após cada mudança de runner, destino ou configuração de rede, repita pelo menos
oito medições distribuídas em um dia e compare mediana, percentis, cobertura e
falhas com este baseline.
