## Resumo

Descreva o problema e a solução em poucas linhas.

## Tipo de mudança

- [ ] correção de bug
- [ ] funcionalidade
- [ ] documentação
- [ ] segurança
- [ ] alteração de schema/API
- [ ] manutenção de build/deploy

## Validação

- [ ] `PYTHONPATH=app python -m unittest discover -s tests -v`
- [ ] `python -m compileall -q app`
- [ ] JavaScript do dashboard validado
- [ ] `git diff --check`
- [ ] teste Docker/endpoint executado, se aplicável

## Compatibilidade e operação

- Migração de banco necessária? Descreva.
- Variáveis de ambiente novas ou alteradas?
- Documentação e `CHANGELOG.md` atualizados?
- Algum risco de perda de dados, privacidade ou segurança?

## Checklist

- [ ] Não há segredos, bancos, backups ou artefatos gerados no commit.
- [ ] Testes cobrem o comportamento alterado.
- [ ] A mudança preserva a distinção entre ausência e zero Mbps.
- [ ] O PR está focado e pronto para revisão.
