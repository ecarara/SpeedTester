# Desenvolvimento

## Pré-requisitos

- CPython 3.14 como runtime alvo; compatibilidade com 3.11–3.13
  (`>=3.11,<3.15`), sem suporte a 3.15;
- `pip` e ambiente virtual;
- Node.js para validar o JavaScript embutido no dashboard;
- Docker Compose para testar imagens e o stack;
- servidor iPerf3 somente quando for executar medição real.

## Estrutura

```text
app/api/          API HTTP e persistência SQLite
app/collector/    agenda, probes, runners e classificação
app/dashboard/    HTML/CSS/JavaScript do painel
app/shared/       configuração comum
tests/            testes de regras de domínio
docs/             documentação funcional e técnica
docker/           imagens e Compose
scripts/          backup e utilitários operacionais
```

Consulte [code-reference.md](code-reference.md) para o contrato de cada módulo.

## Ambiente local

```bash
python3.14 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements-dev.txt
```

Os imports usam `app` como raiz:

```bash
PYTHONPATH=app DB_PATH=/tmp/speedtester-dev.db \
  python -m uvicorn api.server:app --host 127.0.0.1 --port 8000
```

## Testes e verificações

```bash
make check
PYTHONPATH=app python -m coverage run -m unittest discover -s tests -v
python -m coverage combine
python -m coverage xml
npm ci --ignore-scripts
npx playwright install chromium
npm run test:ui
```

Os testes de integração exercitam filtros com mais de 1.000 linhas, autorização,
migração, gravações concorrentes, recuperação de slots e restauração. O teste
Playwright inicia uma API isolada com dados sintéticos e verifica períodos,
runner, exportação, teclado, timezone e largura móvel.
O CI está configurado para Python 3.11/3.12/3.13/3.14, aceitação da interface,
smoke test Compose e builds AMD64/ARM64. Os workflows de build nativo usam
CPython 3.14; consulte a [matriz de suporte e build](desktop-installation.md).
A análise Sonar em `main` recebe `coverage.xml` (Python) e
`coverage-js/lcov.info` (JavaScript realmente executado no Chromium).

Testes dependentes de internet real devem permanecer fora do CI determinístico.

## Alterações no schema

1. Atualize `SCHEMA_VERSION` e a migração incremental em `app/api/store.py`.
2. Preserve a leitura de bases existentes.
3. Adicione teste com banco temporário e valide a migração.
4. Atualize [data-model.md](data-model.md), [api.md](api.md) e o changelog.
5. Faça backup antes de migrar uma instalação real.

## Releases

Antes de publicar:

- execute o CI e os testes locais;
- atualize `CHANGELOG.md`;
- revise dependências e licenças em [third-party.md](third-party.md);
- execute `python scripts/check_license.py` para validar a metainformação GPL;
- verifique `LICENSE`, `SECURITY.md` e `env.example`;
- gere uma tag SemVer e registre migrações;
- confirme que o build Docker não inclui `.env`, bancos ou backups.
