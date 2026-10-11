# Conformidade de licenciamento

## Licença do SpeedTester

O código original do SpeedTester é distribuído por Edson Angelo Carara sob a
**GNU General Public License, versão 3 ou posterior** (`GPL-3.0-or-later`). O
texto integral está em [`LICENSE`](../LICENSE), e os arquivos de código mantêm
identificação SPDX. O catálogo SPDX reconhece `GPL-3.0-or-later` como uma
expressão válida para permitir versões posteriores da GPL.

O repositório também inclui `REUSE.toml` para associar licença e copyright a
arquivos de documentação e configuração que não comportam cabeçalho de
comentário. A autoria das contribuições permanece com seus autores, mas as
contribuições aceitas devem ser licenciáveis sob GPL-3.0-or-later, conforme
[`CONTRIBUTING.md`](../CONTRIBUTING.md).

## O que é distribuído

- O repositório contém o código-fonte correspondente, testes, documentação,
  scripts, Dockerfiles e Compose necessários para estudar, modificar e
  reconstruir o projeto.
- O projeto não incorpora código-fonte de dependências Python; elas são
  declaradas com versões fixadas em `app/requirements.txt` e instaladas no
  build.
- iPerf3, Python/Debian e demais componentes do sistema são obras separadas,
  com suas próprias licenças. O inventário está em
  [`third-party.md`](third-party.md).
- O cliente oficial Ookla é opcional do ponto de vista funcional, possui
  termos próprios e é instalado durante o build do collector. Ele não é código
  GPL do SpeedTester e não deve ser apresentado como parte relicenciada do
  projeto.

Essa separação não substitui a revisão das condições de redistribuição do
artefato Docker. Antes de publicar uma imagem, gere o SBOM e os avisos das
dependências efetivamente incluídas, preserve suas licenças e confirme os
termos do cliente Ookla.

## Regras para distribuição

Ao distribuir o repositório ou uma imagem construída a partir dele:

1. mantenha `LICENSE`, os avisos de copyright e os avisos de terceiros;
2. informe que o SpeedTester está sob GPL-3.0-or-later e que houve
   modificações, quando aplicável;
3. disponibilize o código-fonte correspondente e as instruções de build;
4. não adicione termos que restrinjam os direitos concedidos pela GPL;
5. não publique segredos, bancos de produção, backups ou tokens como parte de
   um artefato de distribuição.

Para o fluxo deste projeto, o código-fonte correspondente é o próprio
repositório Git, incluindo `app/`, `docker/`, `scripts/`, `tests/`,
`requirements.txt`, `env.example` e a documentação necessária para reconstruir
o ambiente. O checklist operacional está em
[`publishing.md`](publishing.md).

## Verificações antes da release

- `make check` — testes, compilação, links da documentação, JavaScript,
  metadados GPL e whitespace;
- `make compose-config` — sintaxe do Compose em uma máquina com Docker;
- revisão manual de `LICENSE`, `REUSE.toml`, `docs/third-party.md` e do SBOM;
- confirmação de que o artefato contém o código-fonte correspondente e não
  impõe restrições adicionais;
- revisão de copyright de novos arquivos e das licenças de qualquer trecho
  copiado de terceiros.

Este documento é uma orientação de engenharia para a publicação do projeto e
não substitui aconselhamento jurídico sobre um artefato ou distribuição
específica.
