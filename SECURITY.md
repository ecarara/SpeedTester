# Segurança

Este projeto é mantido por [Edson Angelo Carara (`ecarara`)](https://github.com/ecarara).
O repositório oficial é <https://github.com/ecarara/SpeedTester>.

## Escopo

O SpeedTester coleta métricas de conectividade e velocidade em uma rede
privada. Ele não deve ser exposto diretamente à internet: a porta HTTP foi
projetada para uso local, LAN confiável, VPN ou atrás de um proxy reverso com
HTTPS e autenticação.

## Controles implementados

- a autenticação administrativa é fail-closed por padrão (`API_REQUIRE_ADMIN_TOKEN=true`);
- `POST /api/reset` e alterações manuais exigem `X-Admin-Token`;
- as rotas `/api/*` têm limite por cliente e `/api/samples` tem paginação;
- respostas recebem cabeçalhos básicos contra MIME sniffing, framing e
  referrer leakage;
- API e collector executam como `speedtester` UID 10001 e com
  `no-new-privileges`;
- imagens base são fixadas por digest e o pacote oficial Ookla é verificado por
  SHA-256 durante o build;
- backups usam o mecanismo consistente do SQLite, `integrity_check`, retenção
  limitada e banco montado como somente leitura no serviço de backup;
- destinos de teste, comandos subprocessados e timeouts são definidos pelo
  servidor, não recebidos livremente do navegador.

## Configuração mínima segura

1. Gere um token longo e aleatório e salve-o no `.env` com permissões restritas:

   ```bash
   umask 077
   openssl rand -hex 32
   ```

2. Defina `API_ADMIN_TOKEN` com o valor gerado e mantenha
   `API_REQUIRE_ADMIN_TOKEN=true`.
3. Mantenha `API_BIND_ADDRESS=127.0.0.1` quando o acesso for somente local.
   Para a LAN, use apenas um IP privado específico e firewall; para acesso
   remoto, prefira VPN ou proxy reverso com HTTPS.
4. Sincronize os backups válidos para outro host ou storage. O volume local
   `backup_data` não protege contra perda do servidor inteiro.
5. Atualize periodicamente as dependências e revise o digest e o checksum do
   cliente Ookla quando houver troca de versão.

## Riscos residuais

- As rotas de leitura ainda são deliberadamente simples para o dashboard;
  proteção de acesso à internet deve ser feita por rede privada ou proxy
  autenticado.
- O backup local não é criptografado nem replicado automaticamente para fora
  do host.
- O serviço auxiliar que inicializa o volume do banco precisa executar como
  root para ajustar a propriedade do volume; API e collector não executam como
  root.
- A identificação de falha da operadora é uma classificação operacional
  baseada em evidências de conectividade, não uma prova contratual definitiva.

## Comunicação de vulnerabilidades

Não publique credenciais, endereços privados, bancos de dados ou uma prova de
conceito destrutiva em uma issue pública. Informe a pessoa responsável pelo
ambiente, inclua versão, configuração afetada, impacto e passos mínimos de
reprodução. Em caso de suspeita de exposição de token, revogue-o e gere outro
imediatamente.
