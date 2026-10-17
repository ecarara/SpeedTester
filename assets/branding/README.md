# Identidade visual

Os arquivos desta pasta fazem parte da identidade visual do SpeedTester e são
distribuídos sob `GPL-3.0-or-later`, como o restante do projeto.

- `speedtester-logo-v1.png`: lockup horizontal original, com símbolo e nome;
- `speedtester-symbol-master.png`: mestre raster quadrado transparente para
  os pacotes;
- `speedtester-symbol-master.svg`: versão vetorial para documentação e
  ferramentas que aceitam SVG;
- `speedtester-logo-v1-prompt.txt`: briefing de origem da marca.

O símbolo quadrado não contém texto para permanecer legível em tamanhos
pequenos. As imagens de pacote ficam em `assets/icons/hicolor/` e os
contêineres Windows/macOS em `assets/packaging/`. Para recriá-los:

```bash
python3 scripts/build_brand_assets.py
```

O PNG quadrado foi produzido a partir da marca existente com o gerador visual
do projeto e deve ser revisado pelo proprietário antes de uma publicação
comercial ou registro de marca.
