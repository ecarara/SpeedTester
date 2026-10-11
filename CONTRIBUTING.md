# Contribuindo com o SpeedTester

Obrigado por contribuir. O projeto aceita correções de bugs, melhorias de
documentação, testes, runners e evoluções do dashboard, desde que o impacto
nas métricas e na classificação de indisponibilidade seja explícito.

O projeto é mantido por [Edson Angelo Carara (`ecarara`)](https://github.com/ecarara)
no repositório oficial <https://github.com/ecarara/SpeedTester>.

## Antes de começar

1. Leia [SECURITY.md](SECURITY.md) para problemas de segurança.
2. Abra uma issue para mudanças de comportamento ou decisões que afetem o
   modelo de dados, o scheduler ou a API.
3. Verifique se já existe uma issue ou pull request para o mesmo assunto.

## Fluxo de trabalho

1. Crie uma branch a partir de `main`, com nome descritivo, como
   `fix/iperf-timeout` ou `docs/api-authentication`.
2. Mantenha cada pull request focado e explique motivação, mudança e riscos.
3. Atualize documentação e testes junto com o código.
4. Execute localmente:

   ```bash
   PYTHONPATH=app python -m unittest discover -s tests -v
   python -m compileall -q app
   git diff --check
   ```

5. Abra o pull request usando o template e aguarde o CI.

## Convenções de código

- Python 3.11 ou superior;
- funções públicas devem ter type hints e docstrings quando expõem regras de
  negócio, efeitos colaterais ou formatos de retorno;
- subprocessos devem usar listas de argumentos, nunca shell concatenado;
- não registrar tokens, credenciais, IPs desnecessários ou conteúdo de tráfego;
- não tratar slot perdido como velocidade zero;
- alterações no schema devem incluir migração compatível e teste de dados
  antigos;
- mudanças na API devem atualizar `docs/api.md` e os exemplos;
- alterações de contrato devem ser registradas em `CHANGELOG.md`.

## Pull requests

O PR deve informar o problema resolvido, arquivos afetados, testes executados,
alterações de configuração/migração, impacto de compatibilidade, privacidade e
segurança, além da documentação atualizada.

## Licenciamento das contribuições

Você mantém os direitos autorais sobre sua contribuição. Ao abrir um pull
request, confirme que tem autorização para distribuir o material e que aceita
licenciá-lo sob `GPL-3.0-or-later`, sem adicionar restrições incompatíveis.
Não envie código, documentação, imagens ou dados de terceiros sem verificar a
licença e registrar a atribuição necessária.
