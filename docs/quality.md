# Qualidade e revisão de manutenção

A análise inicial apontou 56 itens de manutenção, sem bugs, vulnerabilidades ou
hotspots. Foram revisados por categoria:

| Categoria | Quantidade inicial | Tratamento |
| --- | ---: | --- |
| Respostas HTTP não documentadas | 17 | Melhorar contratos OpenAPI junto dos endpoints alterados. |
| Complexidade de funções | 13 | Separar autenticação, entrega de alertas e observação; priorizar funções críticas com testes. |
| Literais duplicados | 7 | Consolidar constantes durante a manutenção das funções. |
| Regex verbosa | 4 | Simplificar classes numéricas e limitar o padrão de perda de pacotes. |
| Parâmetros sem uso | 4 | Alguns fazem parte da interface de compatibilidade dos runners; não remover sem migração. |
| Exceções redundantes | 3 | Remover subclasses já cobertas em parser/probes e na nova entrega de alertas. |
| Endereços IP literais | 3 | São limites RFC1918 do verificador de privacidade, necessários para detectar vazamentos. |
| Timeout assíncrono | 2 | Aplicar limite total ao probe HTTPS e não reportar timeout como latência válida. |
| Outros ajustes | 3 | Simplificar condicionais e construção dos filtros. |

O quality gate continua exigindo cobertura e ausência de novos problemas;
as regras não foram desabilitadas. O backlog restante não significa ausência
de testes nem deve ser convertido automaticamente em defeito funcional.

Os testes novos cobrem autorização, CSRF, expiração, revogação, logout, reinício
da sessão, fila durável, concorrência e leases, limite de novas tentativas,
recuperação de incidentes, falhas de DNS/TCP/ICMP, parsers de runners, loop do
collector, digests, extração segura do código e retorno do deploy.
Os testes de navegador também validam login, perfis e exportação protegida.

A cobertura deve ser lida em duas dimensões: global e código novo. Não omitir
módulos de produção nem excluir caminhos difíceis para elevar o percentual.
Medições reais e a observação no staging complementam esses testes, sem substituir
a validação determinística. Não há conclusão de SLA usando um destino sem controle.
