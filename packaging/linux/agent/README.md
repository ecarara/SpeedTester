<!-- SPDX-License-Identifier: GPL-3.0-or-later -->
<!-- Copyright (C) 2026 Edson Angelo Carara -->
# speedtester-agent (opt-in)

Pacote separado para **compartilhar medições com o SpeedTester Server**.
O pacote `speedtester` é o app/coletor local e **não** ativa esse agente.

## Construir e instalar

```bash
cd packaging/linux/agent
makepkg -si
```

O pacote baixa o bundle congelado `SpeedTesterClient-0.4.52-linux-x86_64.tar.gz`
da release privada e instala o helper `speedtester-agent`. O serviço fica
**desabilitado** até o opt-in.

## Opt-in

```bash
sudo speedtester-agent enable
```

O helper usa o helper nativo do bundle para instalar o runtime em
`/opt/cararalab-speedtester-client`, criar/atualizar o serviço de sistema e
preservar `/var/lib/cararalab-speedtester-client` (fila cifrada). Em seguida,
abra “SpeedTester Client” no menu para parear e aceitar os documentos.

## Atualizações

O `pacman -U` substitui o bundle em `/usr/lib/speedtester-agent`; o
`post_upgrade` executa `speedtester-agent repair`, que atualiza `/opt` e
reinicia o serviço **somente se o agente já estiver instalado**. Nenhuma
atualização do app/coletor habilita o compartilhamento.

## Desativar/remover

```bash
sudo speedtester-agent disable   # para o compartilhamento; dados preservados
sudo speedtester-agent remove    # remove runtime/serviço; dados preservados
```

A instalação manual antiga em `/opt` (preview de 16/10) é reconhecida pelo
bootstrap existente; o primeiro `enable` faz a atualização para este bundle e
mantém a fila/pareamento.
