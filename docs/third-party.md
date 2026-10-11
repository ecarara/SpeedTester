# Dependências e licenças de terceiros

Este inventário descreve o uso direto conhecido. Antes de uma release, revise
as licenças efetivamente instaladas e gere um SBOM da imagem publicada.

| Componente | Uso | Licença/origem a revisar |
|---|---|---|
| Python | runtime | PSF License |
| FastAPI, Starlette, Pydantic, Uvicorn | API HTTP | MIT |
| pandas e NumPy | agregações e análise | BSD/permissivas |
| matplotlib | geração de PNG | Matplotlib License |
| aiohttp | runner fast.com e HTTP | Apache-2.0 |
| coverage.py, HTTPX | testes Python | Apache-2.0 / BSD-3-Clause |
| Playwright | testes do dashboard | Apache-2.0 |
| age / OpenSSH | criptografia e replicação opcional de backups | BSD-3-Clause / BSD |
| iPerf3 | medição TCP | BSD-3-Clause |
| Ookla Speedtest CLI | runner opcional | termos da Ookla |
| fast.com | endpoint de medição | termos do serviço Netflix |
| imagem Python/Debian | runtime dos containers | termos associados |
| Google Fonts | tipografia opcional | termos do Google Fonts |

O SpeedTester não redistribui o servidor iPerf3, o serviço fast.com ou os
termos proprietários da Ookla. A imagem instala o cliente Ookla em versão e
checksum fixos; atualizações devem revisar o checksum e este inventário.

GPL-3.0-or-later é a licença do SpeedTester, não uma afirmação de que cada
componente de terceiros use a mesma licença.
