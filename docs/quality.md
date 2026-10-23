# Qualidade e revisão de manutenção

## Quality Gate e cobertura reproduzível

A análise de 23/10/2026 do commit `701cf9780910e1625b99f6aaf95a50556351a207`
reprovou duas condições: cobertura do código novo de 65,2% (mínimo de 80%) e
109 ocorrências novas (máximo de zero). Duplicação estava em 0%, aprovada.
Não se tratava de timeout, autenticação ou indisponibilidade do scanner.

A correção mantém o mesmo gate e a mesma definição de código novo. Funções
grandes foram separadas por responsabilidade; contratos, confirmações gráficas,
validações de entrada e testes de exceção passaram por refatoração com regressões.
Os testes gráficos existentes agora executam com Xvfb na análise. A configuração
`.coveragerc` inclui também processos Python filhos, e os dados paralelos são
combinados antes de gerar o XML enviado ao SonarQube. Nenhum módulo de produção
foi omitido da cobertura para elevar o percentual.

Para reproduzir em Linux, depois de instalar as dependências de desenvolvimento
e disponibilizar Tk/Xvfb:

```sh
python -m coverage erase
SPEEDTESTER_GUI_TESTS=1 PYTHONPATH=app xvfb-run -a python -m coverage run -m unittest discover -s tests -v
python -m coverage combine
python -m coverage report
python -m coverage xml
```

No macOS ou Windows com sessão gráfica, remova apenas `xvfb-run -a`. Os testes
usam respostas assinadas sintéticas e adaptadores de sistema simulados; não
executam medições operacionais nem instalam serviços na estação. Os testes
destrutivos de ciclo de vida continuam restritos às VMs descartáveis da CI.
Na análise Linux, a CI também compila o iPerf3 de fonte com checksum fixado e
executa o contrato RSA já existente, exclusivamente em loopback com 8 KiB de
payload. Essa cobertura de empacotamento é combinada com a suíte; não é uma
medição da conexão do usuário nem uma autorização para testar destinos externos.

### Revisões de aplicabilidade

Dez alertas receberam comentários e classificação individual de falso positivo
na API do SonarQube. Não foram desativadas regras nem aceitas falhas em bloco:

| Regra | Quantidade | Evidência da revisão |
| --- | ---: | --- |
| S1313 | 7 | Destinos públicos de teste pertencentes ao catálogo geográfico versionado, com fonte documentada; não são endereços internos ou credenciais. |
| S5332 | 1 | IPC vinculado somente ao loopback, sem credenciais de pareamento/medição, com HMAC nas duas direções, proteção contra replay, rejeição de Origin e bypass de proxy. |
| S2245 | 1 | PRNG determinístico somente para horários reproduzíveis; não gera chaves, identificadores ou autorizações. |
| S2612 | 1 | Fixture protegida da CI restaura `/opt` para root:root/0755: leitura/execução pública, sem escrita pública; nenhuma permissão de dados privados é relaxada. |

Alterações futuras nesses limites de confiança exigem nova revisão, não a
reutilização automática dessa classificação. Para investigar outra reprovação,
consulte `api/qualitygates/project_status?projectKey=speedtester` e os achados da
mesma revisão analisada. Tokens ficam fora do código e dos relatórios.

## Histórico da revisão inicial

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
