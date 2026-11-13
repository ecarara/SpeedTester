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
da release privada, confere o sha256 publicado ao lado do asset e instala o
helper `speedtester-agent`. O serviço fica **desabilitado** até o opt-in; o
próprio `pacman` imprime o comando de ativação no final da instalação.

Cada release também publica o pacote pronto (gerado no CI a partir do bundle
daquela release), então não é preciso rodar `makepkg` para atualizar:

```bash
gh release download v0.4.52 -R ecarara/SpeedTester -p "speedtester-agent-*.pkg.tar.zst" -D /tmp/speedtester-agent
sudo pacman -U /tmp/speedtester-agent/*.pkg.tar.zst
```

## Opt-in

```bash
sudo speedtester-agent enable
```

O helper usa o helper nativo do bundle para instalar o runtime em
`/opt/cararalab-speedtester-client`, criar/atualizar o serviço de sistema e
preservar `/var/lib/cararalab-speedtester-client` (fila cifrada). Só nesse
momento o atalho “SpeedTester Client” aparece no menu; abra-o para parear e
aceitar os documentos. Antes do `enable` nada é instalado em `/opt`, nenhum
serviço é habilitado e nenhum dado sai da máquina.

## Atualizações

O `pacman -U` substitui o bundle em `/usr/lib/speedtester-agent`; o
`post_upgrade` executa `speedtester-agent repair` **somente se o agente já
estiver instalado e não tiver sido desativado**: a operação `upgrade` atualiza
`/opt`, reinicia o serviço e **preserva a escolha anterior** de compartilhamento
(não pausa a agenda). O `disable` continua valendo entre atualizações.

## Desativar/remover

```bash
sudo speedtester-agent disable   # para o compartilhamento; dados preservados
sudo speedtester-agent status    # estado do serviço
sudo speedtester-agent remove    # remove runtime/serviço/atalho; dados preservados
```

`disable` grava um marcador em `/var/lib/cararalab-speedtester-client/disabled`
e uma atualização do pacote **não** reativa o agente nesse estado.

A instalação manual antiga em `/opt` (preview de 16/10) é reconhecida pelo
bootstrap existente; o primeiro `enable` faz a atualização para este bundle,
mantém a fila/pareamento e alinha o `control.json` do usuário à chave do
serviço.
