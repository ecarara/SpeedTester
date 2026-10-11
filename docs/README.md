# Documentação do SpeedTester

Projeto mantido por **Edson Angelo Carara** (`ecarara`). Repositório oficial:
<https://github.com/ecarara/SpeedTester>.

## Finalidade

O SpeedTester deve produzir uma série histórica confiável da conexão de banda
larga: medir a velocidade contratada versus a velocidade observada, mostrar a
variação ao longo do dia e explicar se um ponto ausente ou uma falha ocorreu
por falta de energia, por indisponibilidade da operadora, pela infraestrutura
interna ou pelo próprio sistema de medição.

## Documentos

| Documento | Responde a |
|---|---|
| [Demonstração e screenshots](demo.md) | Como abrir o painel com dados fictícios e reproduzir a captura pública |
| [Requisitos](requirements.md) | O que o sistema deve fazer e quais regras definem cada quadrante e cada falha |
| [Arquitetura](architecture.md) | Como os componentes atuais se relacionam e como evoluir o sistema |
| [Modelo de dados](data-model.md) | O que é uma amostra, uma janela esperada, um incidente e uma causa |
| [API](api.md) | Endpoints existentes e contratos necessários para a evolução |
| [Métricas e gráficos](analytics-and-charts.md) | Como calcular e apresentar velocidade, cobertura e indisponibilidade |
| [Operação](operations.md) | Instalação, configuração, logs, backup e diagnóstico |
| [Desenvolvimento](development.md) | Ambiente local, testes, schema e releases |
| [Referência de código](code-reference.md) | Módulos, invariantes e contratos internos |
| [Dependências](third-party.md) | Componentes externos e licenças a revisar |
| [Conformidade GPL](license-compliance.md) | Licença do projeto, componentes externos e obrigações de distribuição |
| [Publicação](publishing.md) | Checklist para configurar e liberar o projeto no GitHub |
| [Segurança](../SECURITY.md) | Controles implementados, configuração segura e riscos residuais |
| [Roadmap](roadmap.md) | Ordem recomendada de implementação e critérios de aceite |
| [Validação de 26/08/2026](validation-2026-08-26.md) | Resultado real no servidor e coerência com 1 Gbps |

## Como ler a documentação

Os documentos descrevem o comportamento implementado no código atual. Quando
uma seção mencionar “alvo”, “futuro” ou “evolução”, trata-se explicitamente de
uma funcionalidade ainda não garantida pela versão presente no repositório.

## Decisões de produto registradas

1. O dia operacional usa o timezone configurado, por padrão
   `America/Sao_Paulo`; o banco continua armazenando timestamps em UTC.
2. Os quadrantes são janelas de seis horas, com fronteiras simples e
   configuráveis: madrugada `00:00–05:59`, manhã `06:00–11:59`, tarde
   `12:00–17:59` e noite `18:00–23:59`.
3. Uma medição não executada não deve ser confundida com uma medição de zero
   Mbps. A ausência precisa aparecer como estado e motivo.
4. “Falha da operadora” só é atribuída quando há evidência de que o equipamento
   local está energizado e alcançável, mas a conectividade externa falha.
5. Métricas de velocidade devem excluir falhas e estados sem medição; métricas
   de cobertura devem incluir as janelas esperadas.

## Licença

O SpeedTester usa a **GNU GPL versão 3 ou posterior**, identificada como
`GPL-3.0-or-later`. O texto integral está em [../LICENSE](../LICENSE). Novos
arquivos devem manter o aviso de copyright de Edson Angelo Carara e não devem
introduzir dependências com licença incompatível sem revisão.
