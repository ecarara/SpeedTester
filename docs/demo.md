# Demonstração e screenshots

A captura pública mostra o dashboard real do SpeedTester, servido pela API,
com sete dias de dados inteiramente sintéticos. Ela não representa a qualidade
de uma conexão real. O banco de staging e sua infraestrutura não são usados.

![Dashboard com dados fictícios](images/dashboard.png)

## Executar a demonstração

Na raiz do clone, prepare o ambiente descrito em [development.md](development.md).
Em Linux/macOS, crie um diretório temporário exclusivo e inicie apenas a API:

```bash
. .venv/bin/activate
DEMO_DIR=$(mktemp -d)
PYTHONPATH=app python scripts/seed_demo.py --db "$DEMO_DIR/demo.db"
PYTHONPATH=app DB_PATH="$DEMO_DIR/demo.db" TZ=America/Sao_Paulo \
  ISP_LOOKUP_ENABLED=false python -m uvicorn api.server:app \
  --host 127.0.0.1 --port 8000
```

Abra <http://localhost:8000>, selecione a data **10/10/2026** e o runner
**iPerf3**. A base contém 56 amostras, cobertura completa e um evento fictício
no dia anterior. O script recusa um caminho que já existe. Ele não consulta
a operadora, não inicia o collector e não executa medições de rede.

O heartbeat é uma observação fictícia única e fica desatualizado após 120
segundos; o indicador de collector pode mudar para indisponível. Isso é
esperado: a demonstração não executa um collector contínuo.

## Reproduzir a captura

Use uma janela de 1440 × 1200 pixels, selecione os filtros acima e capture
somente a página, sem a barra de endereços do navegador. O arquivo publicado
é [images/dashboard.png](images/dashboard.png). Os gráficos são gerados pela
própria API a partir do banco sintético, sem montagem ou geração por IA.

Para capturar automaticamente, com Node.js instalado e a API acima em execução:

```bash
SCREENSHOT_TOOLS=$(mktemp -d)
npm install --prefix "$SCREENSHOT_TOOLS" playwright
"$SCREENSHOT_TOOLS/node_modules/.bin/playwright" install chromium
NODE_PATH="$SCREENSHOT_TOOLS/node_modules" node scripts/capture_dashboard.cjs
```

O utilitário aceita apenas localhost e confere que as 56 amostras têm o nome
fictício do servidor. Ele salva o PNG no caminho usado pelo README.

Antes de compartilhar qualquer captura de uma instalação real, substitua os
dados na origem: endereços, hostnames, operadora, anotações, tokens e caminhos
internos. Mantenha `.env`, bancos, backups e logs fora do Git. Para o README,
prefira sempre esta demonstração reproduzível.
