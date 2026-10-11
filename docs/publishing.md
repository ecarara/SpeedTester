# Checklist de publicação no GitHub

Este checklist separa o que está versionado no repositório do que precisa ser
ativado nas configurações da organização ou do repositório.

## Antes do primeiro push

- [x] Confirmar o nome, descrição, proprietário do copyright e URL oficial:
      Edson Angelo Carara (`ecarara`), <https://github.com/ecarara/SpeedTester>.
- [x] Revisar `LICENSE`, `SECURITY.md`, `CONTRIBUTING.md`,
      `CODE_OF_CONDUCT.md`, `SUPPORT.md` e `CHANGELOG.md`.
- [x] Excluir dados locais, `.env`, bancos, backups, caches e credenciais
      do conteúdo público; revisar com `python scripts/check_publication.py`.
- [x] Anonimizar exemplos e relatório de validação; gerar a captura a partir
      de uma base inteiramente sintética, conforme [demo.md](demo.md).
- [x] Executar `make check` em um ambiente com as dependências declaradas.
- [ ] Validar Compose e build das imagens no CI (Docker indisponível no
      ambiente local de preparação).
- [x] Revisar [third-party.md](third-party.md), `REUSE.toml` e atualizar
      versões/licenças antes de cada release.
- [ ] Criar a primeira tag seguindo SemVer somente após uma validação limpa.

## Configurações recomendadas do repositório

- habilitar Issues e, se desejado, Discussions;
- manter `Allow merge commits` conforme a política do projeto e exigir pull
  request para `main`;
- exigir o workflow `CI` aprovado antes do merge;
- exigir branch atualizada e resolver conversas antes do merge;
- ativar Dependabot alerts, security updates e agrupamento controlado de
  atualizações;
- ativar secret scanning e push protection quando disponíveis no plano;
- definir `SECURITY.md` como política de segurança nas configurações;
- configurar descrição, tópicos como `internet-monitoring`, `iperf3`,
  `broadband`, `fastapi` e `docker`, e uma página de releases;
- limitar permissões padrão de GitHub Actions a leitura, como já definido no
  workflow.

## Histórico público e privacidade

A publicação inicial usa um commit raiz contendo o código e a documentação
revisados. O histórico de desenvolvimento anterior é preservado somente no
checkout local porque contém referências de infraestrutura interna. Não
publique todas as branches ou tags desse checkout; envie apenas a branch
pública revisada. Para trabalhar a partir do histórico público, prefira um
clone novo do repositório oficial.

`scripts/check_publication.py` verifica arquivos que podem ser versionados,
incluindo IPs privados, artefatos locais e alguns formatos comuns de segredos.
Essa checagem não substitui a revisão de texto, imagens e histórico antes de
uma publicação. O screenshot usa exclusivamente o banco fictício gerado por
`scripts/seed_demo.py`.

## Primeiro release

1. Faça merge do código em `main` com o CI verde.
2. Atualize a seção correspondente em `CHANGELOG.md`.
3. Crie uma tag anotada, por exemplo `v0.1.0`.
4. Gere as notas com mudanças, limitações, migrações e instruções de upgrade.
5. Não inclua banco de produção, `.env`, token, backup ou capturas com dados
   reais no artefato da release. A captura sintética documentada pode ser incluída.
6. Publique checksums dos artefatos distribuídos e a licença aplicável.

## Pós-publicação

- testar o clone anônimo em uma máquina limpa;
- testar o fluxo Docker sem o `.env` original;
- testar o fluxo de contribuição e o template de issue;
- monitorar o primeiro build do CI e os alertas do Dependabot;
- registrar vulnerabilidades somente pelo processo privado de segurança;
- revisar este checklist a cada release principal.

## Identidade do projeto

- **Nome:** SpeedTester
- **Mantenedor e titular do copyright:** Edson Angelo Carara
- **Conta GitHub:** [`ecarara`](https://github.com/ecarara)
- **Repositório oficial:** <https://github.com/ecarara/SpeedTester>
- **Licença:** GNU GPL-3.0-or-later
