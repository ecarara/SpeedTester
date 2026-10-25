# Empacotamento macOS

O pacote macOS entrega um `SpeedTester.app` dentro de um `.dmg`. O launcher
abre o dashboard local e o cliente de medição é executado como `LaunchAgent`
do usuário, com o label `speedtester-client.service` para manter o contrato
comum de `app/desktop_launcher.py`.

## Build local

O build deve ser executado em macOS na arquitetura desejada, com CPython 3.14,
PyInstaller e as ferramentas nativas `hdiutil` e `plutil` disponíveis:

```bash
PYTHON=python3.14 APP_VERSION=0.3.0 OUTPUT_DIR=dist/macos ./packaging/macos/build-app.sh
```

Os artefatos são:

- `SpeedTester-<versão>-macos-<arquitetura>.dmg`;
- `SpeedTester-<versão>-macos-<arquitetura>.app.zip`.

O builder identifica a arquitetura do host (`arm64` ou `x86_64`). Para um
artefato universal real, o pipeline deve combinar builds das duas arquiteturas
com `lipo` e atualizar o nome somente depois da validação.

## Instalação e remoção

Abra o `.dmg`, arraste o aplicativo para `Applications` e instale o
LaunchAgent executando `Install SpeedTester.command` que acompanha a imagem,
ou com:

```bash
./packaging/macos/install-dmg.sh /Applications/SpeedTester.app
./packaging/macos/uninstall-app.sh
./packaging/macos/uninstall-app.sh --purge-data
```

O `.dmg` também inclui `Uninstall SpeedTester.command`, que remove o bundle e
o LaunchAgent sem apagar dados por padrão. Para remover dados, execute o
script do repositório com `--purge-data`.

O instalador usa `/Applications` quando gravável e, caso contrário,
`~/Applications`. A remoção preserva dados por padrão. O modo
`--purge-data` remove também preferências e dados em
`~/Library/Application Support/SpeedTester`.

Na primeira instalação, o comando detecta o fuso horário do macOS, mostra os
parâmetros do runner e pede confirmação. A configuração é persistida em
`~/Library/Application Support/SpeedTester/speedtester.env` e não é sobrescrita
durante atualizações.

O instalador registra dois `LaunchAgent`s por usuário: a API local e o
collector. O launcher aguarda a API responder antes de abrir o dashboard.

## Assinatura e notarização

O builder não exige segredo e, portanto, continua reproduzível em CI. Para
distribuição pública, assine o `.app` com Developer ID, valide o bundle e
notarize o `.dmg` usando uma conta Apple apropriada. Artefatos sem assinatura
podem ser bloqueados ou advertidos pelo Gatekeeper.

O `.tar.gz` de código-fonte continua sendo publicado separadamente por
`make source-tarball`.
