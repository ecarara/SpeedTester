# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Edson Angelo Carara
"""Complete installer copy; Portuguese is always the initial language."""
TEXT = {
"pt-BR": {
"experimental":"VERSÃO EXPERIMENTAL · Instalação nativa ainda em homologação. Não usar em produção.",
"title":"SpeedTester Client · CararaLab", "tagline":"A sua conexão,\ncom evidências.",
"navigation":"INSTALAÇÃO E MANUTENÇÃO", "footer":"CararaLab · Software livre", "language":"Idioma",
"welcome":"Bem-vindo ao seu Client", "intro":"Instale o serviço uma vez. Ele funciona em segundo plano, mesmo sem esta janela aberta ou uma sessão de usuário.",
"install":"Instalar", "install_detail":"Preparar o serviço e escolher se deseja contribuir.",
"repair":"Reparar instalação", "repair_detail":"Recuperar arquivos e serviço, preservando banco, chaves e fila.",
"uninstall":"Desinstalar", "uninstall_detail":"Remover o serviço e escolher o destino dos dados locais.",
"preview":"PRÉVIA · Dados fictícios. Nenhuma instalação, rede ou medição.",
"configure":"Configure sua conexão", "configure_detail":"A contribuição é opcional. Sem vínculo, o componente comunitário fica em espera; sua instalação standalone existente não é modificada.",
"contribute":"Quero vincular este Client e contribuir com o Server",
"origin":"Endereço HTTPS do Server", "operator":"Operadora", "country":"País (código, ex.: BR)",
"region":"Estado / região", "city":"Cidade", "access":"Tecnologia de acesso", "link":"Conexão desta máquina",
"host":"Destino iPerf3", "port":"Porta",
"fiber":"Fibra", "coaxial":"Cabo coaxial", "radio":"Rádio", "satellite":"Satélite", "cellular":"Internet celular", "dsl":"DSL", "other":"Outra", "unknown":"Não sei",
"ethernet":"Cabeada / Ethernet", "wifi":"Wi-Fi", "choose":"Selecione",
"data":"O que será enviado", "data_detail":"Após aceite e vínculo: perfil da conexão, métricas separadas, sistema operacional/distribuição/versão/arquitetura e registros de autenticação e integridade. Consulte a lista completa antes de autorizar.",
"target_notice":"O servidor de teste é configurado automaticamente pelo serviço central. Instalar e vincular não inicia medições.",
"no_target":"O serviço central ainda não disponibilizou um servidor de teste autorizado. Sua instalação pode permanecer vinculada, com as medições pausadas.",
"continue":"Instalar e continuar", "save":"Salvar configuração", "back":"Voltar", "close":"Fechar",
"pair_title":"Vincule esta instalação", "pair_detail":"Entre pelo navegador, revise os documentos vigentes e registre seu aceite. Confira o código e a impressão digital antes de autorizar. Nenhum token precisa ser copiado.",
"pair":"Vincular agora", "open_pair":"Abrir o portal de vínculo", "fingerprint":"Impressão digital da instalação", "expires":"O código tem prazo limitado. Se expirar, solicite outro abaixo.",
"retry_pair":"Gerar / recuperar código", "later":"Concluir sem vincular agora", "paired":"Client vinculado", "waiting_pair":"Aguardando sua autorização no portal…",
"status":"Seu serviço", "running":"Serviço em execução", "unpaired":"Aguardando vínculo", "paused":"Agenda pausada", "enabled":"Agenda habilitada", "pending":"Registros aguardando envio", "quarantined":"Registros preservados para revisão",
"status_detail":"Você pode fechar esta janela. O serviço é independente da interface e inicia com o sistema.",
"enable":"Ativar agenda", "enable_confirm":"Deseja ativar os testes automáticos nos próximos horários agendados? Nenhum teste será executado agora.",
"pause":"Pausar agenda", "manage":"Configurar / vincular", "account":"Abrir minha conta no Server", "home":"Início",
"repair_confirm":"O serviço será parado, o banco verificado e um backup protegido será criado. Chaves, histórico, vínculo e pendências serão preservados. A agenda ficará pausada para revisão. Continuar?",
"remove_title":"Desinstalar com segurança", "remove_detail":"O serviço será interrompido e removido. Sem marcar a opção abaixo, banco cifrado, chaves e fila ficam preservados para reinstalação.",
"purge":"Apagar também todos os dados locais, chaves e registros ainda não enviados",
"revoke_notice":"Desinstalar não revoga o vínculo nem exclui dados já recebidos pelo Server. Para revogar esta instalação, conclua a ação no portal da conta. Sem conexão, a revogação não pode ser confirmada.",
"remove_confirm":"Remover o serviço? Se escolheu apagar os dados, registros pendentes e chaves serão perdidos. Os dados centrais não serão excluídos.",
"removed":"Client desinstalado", "preserved":"Os dados locais foram preservados para reinstalação.", "purged":"Os dados locais foram removidos. Isso não confirma revogação ou exclusão no Server.",
"reboot":"O Windows concluirá a remoção de arquivos em uso após reiniciar.",
"busy":"Aguarde. O sistema pode solicitar autorização de administrador.", "error":"Não foi possível concluir a operação. Os dados existentes foram preservados. Verifique a conexão e use um pacote compatível; para reparar, abra o instalador baixado, fora da pasta instalada.",
"invalid":"Revise os campos da conexão. Informe país com duas letras, tecnologia, cabeado/Wi-Fi.",
"offline":"Serviço indisponível. Instale o Client ou use Reparar instalação.", "blocked":"O Server exige uma ação na conta ou recusou a autorização. Confira o portal; reparar não remove revogações, suspensões ou exigência de novo aceite.",
"no_runner":"A ferramenta de medição não está disponível neste pacote. A agenda continuará pausada.",
},
"en": {
"experimental":"EXPERIMENTAL VERSION · Native installation is still under validation. Not for production use.",
"title":"SpeedTester Client · CararaLab", "tagline":"Your connection,\nbacked by evidence.",
"navigation":"INSTALLATION & MAINTENANCE", "footer":"CararaLab · Free software", "language":"Language",
"welcome":"Welcome to your Client", "intro":"Install the service once. It runs in the background, even with this window closed and no user signed in.",
"install":"Install", "install_detail":"Set up the service and choose whether to contribute.",
"repair":"Repair installation", "repair_detail":"Restore files and service while preserving the database, keys and queue.",
"uninstall":"Uninstall", "uninstall_detail":"Remove the service and choose what happens to local data.",
"preview":"PREVIEW · Fictional data. No installation, network or measurements.",
"configure":"Set up your connection", "configure_detail":"Contributing is optional. Without pairing, the community component stays idle; your existing standalone installation is unchanged.",
"contribute":"I want to pair this Client and contribute to the Server",
"origin":"Server HTTPS address", "operator":"Provider", "country":"Country code (e.g. BR)",
"region":"State / region", "city":"City", "access":"Access technology", "link":"This machine's connection",
"host":"iPerf3 destination", "port":"Port",
"fiber":"Fiber", "coaxial":"Coaxial cable", "radio":"Fixed wireless", "satellite":"Satellite", "cellular":"Mobile internet", "dsl":"DSL", "other":"Other", "unknown":"I don't know",
"ethernet":"Wired / Ethernet", "wifi":"Wi-Fi", "choose":"Select",
"data":"What will be sent", "data_detail":"After consent and pairing: connection profile, separate metrics, operating system/distribution/version/architecture, and authentication/integrity records. Read the full list before authorizing.",
"target_notice":"The central service configures the test server automatically. Installing and pairing do not start measurements.",
"no_target":"The central service has not provided an authorized test server yet. Your installation can remain paired with measurements paused.",
"continue":"Install and continue", "save":"Save configuration", "back":"Back", "close":"Close",
"pair_title":"Pair this installation", "pair_detail":"Sign in through your browser, review the current documents and record your consent. Check the code and fingerprint before authorizing. No tokens need to be copied.",
"pair":"Pair now", "open_pair":"Open the pairing portal", "fingerprint":"Installation fingerprint", "expires":"The code expires. Request another below if needed.",
"retry_pair":"Create / recover code", "later":"Finish without pairing now", "paired":"Client paired", "waiting_pair":"Waiting for your authorization in the portal…",
"status":"Your service", "running":"Service running", "unpaired":"Waiting for pairing", "paused":"Schedule paused", "enabled":"Schedule enabled", "pending":"Records awaiting delivery", "quarantined":"Records preserved for review",
"status_detail":"You can close this window. The service runs independently and starts with the operating system.",
"enable":"Enable schedule", "enable_confirm":"Enable automatic tests at the next scheduled times? No test will run now.",
"pause":"Pause schedule", "manage":"Configure / pair", "account":"Open my Server account", "home":"Home",
"repair_confirm":"The service will stop, the database will be checked and a protected backup created. Keys, history, pairing and pending records will be preserved. The schedule will stay paused for review. Continue?",
"remove_title":"Uninstall safely", "remove_detail":"The service will be stopped and removed. Unless you select the option below, the encrypted database, keys and queue remain available for reinstallation.",
"purge":"Also delete all local data, keys and records not yet delivered",
"revoke_notice":"Uninstalling does not revoke pairing or delete data already received by the Server. Revoke this installation through your account portal. Revocation cannot be confirmed while offline.",
"remove_confirm":"Remove the service? If you chose to delete data, pending records and keys will be lost. Central data will not be deleted.",
"removed":"Client uninstalled", "preserved":"Local data was preserved for reinstallation.", "purged":"Local data was removed. This does not confirm revocation or deletion on the Server.",
"reboot":"Windows will finish removing files in use after restarting.",
"busy":"Please wait. The operating system may request administrator authorization.", "error":"The operation could not be completed. Existing data was preserved. Check connectivity and use a compatible package; for repair, open the downloaded installer outside the installed folder.",
"invalid":"Review the connection fields. Enter a two-letter country code, technology, wired/Wi-Fi.",
"offline":"Service unavailable. Install the Client or choose Repair installation.", "blocked":"The Server requires an account action or rejected authorization. Check the portal; repair does not remove revocations, suspensions or a requirement for renewed consent.",
"no_runner":"The measurement tool is unavailable in this package. The schedule will stay paused.",
},
"es": {
"experimental":"VERSIÓN EXPERIMENTAL · Instalación nativa en validación. No usar en producción.",
"title":"SpeedTester Client · CararaLab", "tagline":"Tu conexión,\ncon evidencias.",
"navigation":"INSTALACIÓN Y MANTENIMIENTO", "footer":"CararaLab · Software libre", "language":"Idioma",
"welcome":"Bienvenido a tu Client", "intro":"Instala el servicio una vez. Funciona en segundo plano, incluso con esta ventana cerrada y sin sesión de usuario.",
"install":"Instalar", "install_detail":"Preparar el servicio y elegir si deseas contribuir.",
"repair":"Reparar instalación", "repair_detail":"Restaurar archivos y servicio conservando la base de datos, claves y cola.",
"uninstall":"Desinstalar", "uninstall_detail":"Eliminar el servicio y decidir qué hacer con los datos locales.",
"preview":"VISTA PREVIA · Datos ficticios. Sin instalación, red ni mediciones.",
"configure":"Configura tu conexión", "configure_detail":"Contribuir es opcional. Sin vínculo, el componente comunitario queda en espera; la instalación standalone existente no cambia.",
"contribute":"Quiero vincular este Client y contribuir al Server",
"origin":"Dirección HTTPS del Server", "operator":"Operadora", "country":"Código del país (p. ej., BR)",
"region":"Estado / región", "city":"Ciudad", "access":"Tecnología de acceso", "link":"Conexión de este equipo",
"host":"Destino iPerf3", "port":"Puerto",
"fiber":"Fibra", "coaxial":"Cable coaxial", "radio":"Radio", "satellite":"Satélite", "cellular":"Internet móvil", "dsl":"DSL", "other":"Otra", "unknown":"No lo sé",
"ethernet":"Por cable / Ethernet", "wifi":"Wi-Fi", "choose":"Seleccionar",
"data":"Qué se enviará", "data_detail":"Tras aceptar y vincular: perfil de conexión, métricas separadas, sistema operativo/distribución/versión/arquitectura y registros de autenticación e integridad. Lee la lista completa antes de autorizar.",
"target_notice":"El servicio central configura automáticamente el servidor de prueba. Instalar y vincular no inicia mediciones.",
"no_target":"El servicio central todavía no ha proporcionado un servidor de prueba autorizado. La instalación puede permanecer vinculada con las mediciones pausadas.",
"continue":"Instalar y continuar", "save":"Guardar configuración", "back":"Volver", "close":"Cerrar",
"pair_title":"Vincula esta instalación", "pair_detail":"Inicia sesión en el navegador, revisa los documentos vigentes y registra tu aceptación. Comprueba el código y la huella antes de autorizar. No necesitas copiar tokens.",
"pair":"Vincular ahora", "open_pair":"Abrir el portal de vinculación", "fingerprint":"Huella de la instalación", "expires":"El código caduca. Solicita otro abajo si es necesario.",
"retry_pair":"Generar / recuperar código", "later":"Finalizar sin vincular ahora", "paired":"Client vinculado", "waiting_pair":"Esperando tu autorización en el portal…",
"status":"Tu servicio", "running":"Servicio en ejecución", "unpaired":"Esperando vínculo", "paused":"Agenda en pausa", "enabled":"Agenda habilitada", "pending":"Registros pendientes de envío", "quarantined":"Registros conservados para revisión",
"status_detail":"Puedes cerrar esta ventana. El servicio es independiente y se inicia con el sistema operativo.",
"enable":"Activar agenda", "enable_confirm":"¿Quieres activar las pruebas automáticas en los próximos horarios programados? No se ejecutará ninguna prueba ahora.",
"pause":"Pausar agenda", "manage":"Configurar / vincular", "account":"Abrir mi cuenta en el Server", "home":"Inicio",
"repair_confirm":"Se detendrá el servicio, se verificará la base de datos y se creará una copia protegida. Se conservarán claves, historial, vínculo y pendientes. La agenda quedará en pausa para revisión. ¿Continuar?",
"remove_title":"Desinstalar con seguridad", "remove_detail":"Se detendrá y eliminará el servicio. Si no seleccionas la opción siguiente, la base cifrada, las claves y la cola se conservarán para reinstalar.",
"purge":"Eliminar también todos los datos locales, claves y registros aún no enviados",
"revoke_notice":"Desinstalar no revoca el vínculo ni elimina datos ya recibidos por el Server. Revoca esta instalación desde el portal de tu cuenta. Sin conexión no se puede confirmar la revocación.",
"remove_confirm":"¿Eliminar el servicio? Si elegiste borrar los datos, se perderán los registros pendientes y las claves. Los datos centrales no se eliminarán.",
"removed":"Client desinstalado", "preserved":"Los datos locales se conservaron para reinstalar.", "purged":"Los datos locales se eliminaron. Esto no confirma revocación ni eliminación en el Server.",
"reboot":"Windows terminará de eliminar los archivos en uso después de reiniciar.",
"busy":"Espera. El sistema puede solicitar autorización de administrador.", "error":"No se pudo completar la operación. Los datos existentes se conservaron. Comprueba la conexión y usa un paquete compatible; para reparar, abre el instalador descargado fuera de la carpeta instalada.",
"invalid":"Revisa los campos. Indica un país de dos letras, tecnología, cable/Wi-Fi.",
"offline":"Servicio no disponible. Instala el Client o elige Reparar instalación.", "blocked":"El Server requiere una acción en la cuenta o rechazó la autorización. Revisa el portal; reparar no elimina revocaciones, suspensiones ni la exigencia de un nuevo consentimiento.",
"no_runner":"La herramienta de medición no está disponible en este paquete. La agenda seguirá en pausa.",
}}

LANGUAGES = {"Português": "pt-BR", "English": "en", "Español": "es"}

# Build identification is available in every supported language.
for _code,_copy,_label in (("pt-BR","Copiar dados para uma issue","Versão"),("en","Copy issue information","Version"),("es","Copiar datos para una issue","Versión")):
    TEXT[_code].update(copy_info=_copy,version_label=_label)

for _code,_short,_periods in (
    ("pt-BR","Agenda automática: 2 testes por período — 8 por dia. Fuso: {timezone}.","Madrugada 00–06h · Manhã 06–12h · Tarde 12–18h · Noite 18–24h."),
    ("en","Automatic schedule: 2 tests per period — 8 per day. Time zone: {timezone}.","Overnight 00–06 · Morning 06–12 · Afternoon 12–18 · Evening 18–24."),
    ("es","Agenda automática: 2 pruebas por período — 8 al día. Zona horaria: {timezone}.","Madrugada 00–06 · Mañana 06–12 · Tarde 12–18 · Noche 18–24.")):
    TEXT[_code].update(schedule_short=_short,schedule_notice=_short+"\n"+_periods)

for _code, _values in {
    "pt-BR": {"data_offline":"Esta lista está incluída no Client e pode ser lida sem internet. Consultá-la não envia dados, registra aceite ou inicia medições.",
        "data_portal":"Consultar no Server", "portal_link":"Link do portal", "copy_link":"Copiar link", "link_copied":"Link copiado.",
        "browser_requested":"A abertura foi solicitada ao navegador padrão.",
        "browser_unavailable":"Não foi possível abrir o navegador automaticamente. Copie este link e abra-o no navegador de sua preferência.",
        "invalid_portal":"Informe um endereço HTTPS válido do Server para abrir o portal. A lista local de dados continua disponível."},
    "en": {"data_offline":"This list is included in the Client and works offline. Reading it sends no data, records no acceptance and starts no measurements.",
        "data_portal":"Read on the Server", "portal_link":"Portal link", "copy_link":"Copy link", "link_copied":"Link copied.",
        "browser_requested":"An open request was sent to your default browser.",
        "browser_unavailable":"The browser could not be opened automatically. Copy this link and open it in your preferred browser.",
        "invalid_portal":"Enter a valid HTTPS Server address to open the portal. The local data list remains available."},
    "es": {"data_offline":"Esta lista está incluida en el Client y puede consultarse sin internet. Leerla no envía datos, registra aceptación ni inicia mediciones.",
        "data_portal":"Consultar en el Server", "portal_link":"Enlace del portal", "copy_link":"Copiar enlace", "link_copied":"Enlace copiado.",
        "browser_requested":"Se solicitó la apertura al navegador predeterminado.",
        "browser_unavailable":"No se pudo abrir el navegador automáticamente. Copie este enlace y ábralo en el navegador de su preferencia.",
        "invalid_portal":"Indique una dirección HTTPS válida del Server para abrir el portal. La lista local de datos sigue disponible."},
}.items():
    TEXT[_code].update(_values)

for _code, _message in {
    "pt-BR": "Abrindo no navegador padrão. Se a página não aparecer, copie este link e abra no seu navegador.",
    "en": "Opening in your default browser. If the page does not appear, copy this link into your browser.",
    "es": "Abriendo en el navegador predeterminado. Si no aparece la página, copie este enlace en su navegador.",
}.items():
    TEXT[_code]["browser_opening"] = _message

for _code, _message in {
    "pt-BR": "Consultando o endereço do Server desta instalação para abrir sua conta…",
    "en": "Looking up this installation's Server address to open your account…",
    "es": "Consultando la dirección del Server de esta instalación para abrir su cuenta…",
}.items():
    TEXT[_code]["account_opening"] = _message


# Pairing always displays a code in the Client before opening the browser.
_PAIRING_TEXT = {
    "pt-BR": {
        "pair_detail": "1. Copie o código exibido abaixo. 2. Abra o portal, entre na sua conta e aceite os documentos, se solicitado. 3. Informe o código e confira a impressão digital antes de autorizar. Volte ao Client para ver a confirmação. Nenhuma medição será iniciada.",
        "pair_code": "Seu código de vínculo — informe este código no portal",
        "copy_code": "Copiar código", "code_copied": "Código copiado. Cole-o no portal de vínculo.",
        "code_deadline": "Válido até {time} (horário deste computador). Se expirar, gere outro código aqui.",
        "generating_code": "Gerando seu código de vínculo… Aguarde antes de abrir o portal.",
        "code_needed": "Gere o código neste Client para vincular esta instalação à sua conta.",
        "code_expired": "O código expirou. Clique em Gerar código de vínculo para obter um novo. O vínculo ainda não foi concluído.",
        "code_failed": "Não foi possível obter o código. Verifique a conexão e tente gerar novamente. Abrir sua conta não gera um código.",
        "pair": "Gerar código de vínculo", "retry_pair": "Recuperar código vigente", "resume_pair": "Continuar vínculo / mostrar código",
    },
    "en": {
        "pair_detail": "1. Copy the code below. 2. Open the portal, sign in and accept the documents if requested. 3. Enter the code and compare the fingerprint before authorizing. Return to the Client for confirmation. No measurements will start.",
        "pair_code": "Your pairing code — enter this code in the portal",
        "copy_code": "Copy code", "code_copied": "Code copied. Paste it into the pairing portal.",
        "code_deadline": "Valid until {time} (this computer's local time). Generate another code here if it expires.",
        "generating_code": "Generating your pairing code… Wait before opening the portal.",
        "code_needed": "Generate a code in this Client to link this installation to your account.",
        "code_expired": "The code expired. Click Generate pairing code to get a new one. Pairing has not completed.",
        "code_failed": "Could not obtain a code. Check connectivity and try generating it again. Opening your account does not generate a code.",
        "pair": "Generate pairing code", "retry_pair": "Recover current code", "resume_pair": "Continue pairing / show code",
    },
    "es": {
        "pair_detail": "1. Copia el código de abajo. 2. Abre el portal, inicia sesión y acepta los documentos si se solicita. 3. Introduce el código y compara la huella antes de autorizar. Vuelve al Client para ver la confirmación. No se iniciarán mediciones.",
        "pair_code": "Tu código de vinculación — introduce este código en el portal",
        "copy_code": "Copiar código", "code_copied": "Código copiado. Pégalo en el portal de vinculación.",
        "code_deadline": "Válido hasta las {time} (hora local de este equipo). Si caduca, genera otro código aquí.",
        "generating_code": "Generando tu código de vinculación… Espera antes de abrir el portal.",
        "code_needed": "Genera un código en este Client para vincular esta instalación a tu cuenta.",
        "code_expired": "El código caducó. Pulsa Generar código de vinculación para obtener otro. La vinculación aún no ha terminado.",
        "code_failed": "No se pudo obtener un código. Comprueba la conexión y vuelve a intentarlo. Abrir tu cuenta no genera un código.",
        "pair": "Generar código de vinculación", "retry_pair": "Recuperar código vigente", "resume_pair": "Continuar vinculación / mostrar código",
    },
}
for _locale, _messages in _PAIRING_TEXT.items():
    TEXT[_locale].update(_messages)


# New machine data is explicitly disclosed before optional contribution.
TEXT['pt-BR']["data_detail"] = 'Após aceite e vínculo: perfil, métricas separadas, sistema operacional, identificador pseudônimo da máquina, fuso e registros de autenticação e integridade. Consulte a lista completa antes de autorizar.'
TEXT['en']["data_detail"] = 'After consent and pairing: profile, separate metrics, operating system, pseudonymous machine identifier, time zone, and authentication/integrity records. Read the full list before authorizing.'
TEXT['es']["data_detail"] = 'Tras aceptar y vincular: perfil, métricas separadas, sistema operativo, identificador seudónimo del equipo, zona horaria y registros de autenticación e integridad. Lee la lista completa antes de autorizar.'


# Confirmation buttons and status follow the selected app language, not the OS.
_STATUS_TEXT = {'pt-BR': {'yes': 'Sim',
           'no': 'Não',
           'status': 'Estado do Client',
           'status_detail': 'Consulte o serviço, a agenda e os envios. Você pode fechar esta janela; o '
                            'serviço funciona em segundo plano.',
           'setup_complete': 'Instalação e vínculo concluídos · testes pausados',
           'setup_complete_detail': 'Não é necessário instalar nem vincular novamente. Ative os testes '
                                    'automáticos quando quiser habilitar os próximos horários da agenda.',
           'tests_active': 'Testes automáticos ativados',
           'tests_active_detail': 'O Client aguarda os horários agendados. O computador precisa estar ligado '
                                  'e conectado; perder um horário não gera teste extra.',
           'setup_needed': 'Serviço instalado · configuração pendente',
           'setup_needed_detail': 'Preencha os dados da conexão para concluir a configuração.',
           'local_ready': 'Instalação concluída · contribuição desativada',
           'local_ready_detail': 'O Client não enviará medições comunitárias. Para contribuir, revise a '
                                 'configuração e conclua o vínculo.',
           'pair_needed': 'Configuração salva · vínculo pendente',
           'pair_needed_detail': 'Conclua o vínculo com sua conta para habilitar os testes automáticos.',
           'status_unknown': 'Status ainda não consultado',
           'status_unknown_detail': 'Atualize o status para consultar o serviço instalado.',
           'service_response': 'Última resposta do serviço',
           'next_test': 'Próximo teste agendado',
           'next_paused': 'Testes automáticos pausados',
           'last_attempt': 'Última tentativa finalizada',
           'accepted_records': 'Registros confirmados pelo servidor',
           'not_recorded': 'Sem registro disponível',
           'last_notice': 'Último aviso:',
           'connection_notice': 'Não foi possível comunicar com o servidor. Confira a conexão e atualize o '
                                'status.',
           'storage_notice': 'O limite de armazenamento foi atingido. Os dados existentes foram preservados '
                             'para envio.',
           'refresh_status': 'Atualizar status',
           'enable': 'Ativar testes automáticos',
           'pause': 'Pausar testes automáticos',
           'manage': 'Revisar configuração',
           'account': 'Minha conta no servidor',
           'copy_info': 'Copiar diagnóstico',
           'home': 'Instalação e manutenção'},
 'en': {'yes': 'Yes',
        'no': 'No',
        'status': 'Client status',
        'status_detail': 'Check the service, schedule and deliveries. You can close this window; the service '
                         'runs in the background.',
        'setup_complete': 'Installation and pairing complete · tests paused',
        'setup_complete_detail': 'You do not need to install or pair again. Enable automatic tests when you '
                                 'want to activate future scheduled times.',
        'tests_active': 'Automatic tests enabled',
        'tests_active_detail': 'The Client is waiting for scheduled times. The computer must be on and '
                               'connected; missed times do not trigger extra tests.',
        'setup_needed': 'Service installed · configuration needed',
        'setup_needed_detail': 'Enter your connection details to complete configuration.',
        'local_ready': 'Installation complete · contribution disabled',
        'local_ready_detail': 'The Client will not submit community measurements. To contribute, review '
                              'configuration and complete pairing.',
        'pair_needed': 'Configuration saved · pairing needed',
        'pair_needed_detail': 'Complete pairing with your account to enable automatic tests.',
        'status_unknown': 'Status not checked yet',
        'status_unknown_detail': 'Refresh status to check the installed service.',
        'service_response': 'Last service response',
        'next_test': 'Next scheduled test',
        'next_paused': 'Automatic tests paused',
        'last_attempt': 'Last finalized attempt',
        'accepted_records': 'Records confirmed by the server',
        'not_recorded': 'No record available',
        'last_notice': 'Last notice:',
        'connection_notice': 'Could not communicate with the server. Check connectivity and refresh status.',
        'storage_notice': 'The storage limit was reached. Existing records are preserved for delivery.',
        'refresh_status': 'Refresh status',
        'enable': 'Enable automatic tests',
        'pause': 'Pause automatic tests',
        'manage': 'Review configuration',
        'account': 'My server account',
        'copy_info': 'Copy diagnostics',
        'home': 'Installation & maintenance'},
 'es': {'yes': 'Sí',
        'no': 'No',
        'status': 'Estado del Client',
        'status_detail': 'Consulta el servicio, la agenda y los envíos. Puedes cerrar esta ventana; el '
                         'servicio funciona en segundo plano.',
        'setup_complete': 'Instalación y vínculo completos · pruebas en pausa',
        'setup_complete_detail': 'No es necesario instalar ni vincular de nuevo. Activa las pruebas '
                                 'automáticas cuando quieras habilitar los próximos horarios programados.',
        'tests_active': 'Pruebas automáticas activadas',
        'tests_active_detail': 'El Client espera los horarios programados. El equipo debe estar encendido y '
                               'conectado; los horarios perdidos no generan pruebas adicionales.',
        'setup_needed': 'Servicio instalado · falta configuración',
        'setup_needed_detail': 'Introduce los datos de tu conexión para completar la configuración.',
        'local_ready': 'Instalación completa · contribución desactivada',
        'local_ready_detail': 'El Client no enviará mediciones comunitarias. Para contribuir, revisa la '
                              'configuración y completa el vínculo.',
        'pair_needed': 'Configuración guardada · falta vinculación',
        'pair_needed_detail': 'Completa el vínculo con tu cuenta para habilitar las pruebas automáticas.',
        'status_unknown': 'Estado aún no consultado',
        'status_unknown_detail': 'Actualiza el estado para consultar el servicio instalado.',
        'service_response': 'Última respuesta del servicio',
        'next_test': 'Próxima prueba programada',
        'next_paused': 'Pruebas automáticas en pausa',
        'last_attempt': 'Último intento finalizado',
        'accepted_records': 'Registros confirmados por el servidor',
        'not_recorded': 'Sin registro disponible',
        'last_notice': 'Último aviso:',
        'connection_notice': 'No se pudo comunicar con el servidor. Comprueba la conexión y actualiza el '
                             'estado.',
        'storage_notice': 'Se alcanzó el límite de almacenamiento. Los datos existentes se conservan para su '
                          'envío.',
        'refresh_status': 'Actualizar estado',
        'enable': 'Activar pruebas automáticas',
        'pause': 'Pausar pruebas automáticas',
        'manage': 'Revisar configuración',
        'account': 'Mi cuenta en el servidor',
        'copy_info': 'Copiar diagnóstico',
        'home': 'Instalación y mantenimiento'}}
for _locale, _messages in _STATUS_TEXT.items():
    TEXT[_locale].update(_messages)

for _locale, _title, _detail in (("pt-BR", "Não foi possível consultar o serviço", "O status anterior não confirma que o serviço continua ativo. Tente atualizar; se o problema persistir, use Reparar instalação."), ("en", "Could not check the service", "The previous status does not confirm the service is still active. Try refreshing; if the problem persists, use Repair installation."), ("es", "No se pudo consultar el servicio", "El estado anterior no confirma que el servicio siga activo. Intenta actualizar; si el problema persiste, usa Reparar instalación.")):
    TEXT[_locale].update(service_unavailable=_title, service_unavailable_detail=_detail)

# Pairing authorizes future scheduling; upgrades recover the existing installation.
for _locale, _copy in {
    "pt-BR": {
        "upgrade": "Atualizar instalação",
        "upgrade_detail": "Instalação existente encontrada. Dados da conexão, vínculo com o Server e estado ativo ou pausado serão preservados. Não é necessário parear novamente.",
        "install_detail": "Instalar o serviço ou atualizar uma instalação existente, preservando seus dados e vínculo.",
        "target_notice": "Após seu aceite e a autorização do vínculo, os testes automáticos são ativados nos próximos horários: 2 por período, 8 por dia. Nenhum teste imediato. O Server define o destino; falhas de autorização ou ferramenta ausente impedem a ativação.",
        "pair_detail": "1. Copie o código abaixo. 2. Abra o portal, entre e aceite os documentos vigentes. 3. Confira o código e a impressão digital e autorize. Os testes serão ativados apenas nos próximos horários: 2 por período, 8 por dia. Nenhum teste imediato.",
        "setup_complete_detail": "Seu vínculo está salvo. Os testes estão pausados; consulte o aviso abaixo, se houver. Retome a agenda quando desejar, sem reinstalar nem parear novamente.",
    },
    "en": {
        "upgrade": "Update installation",
        "upgrade_detail": "Existing installation found. Connection details, Server pairing and active or paused state will be preserved. You do not need to pair again.",
        "install_detail": "Install the service or update an existing installation, preserving its data and pairing.",
        "target_notice": "After acceptance and pairing approval, automatic tests are enabled for future slots: 2 per period, 8 per day. No immediate test. The Server selects the target; missing authorization or measurement tools prevent activation.",
        "pair_detail": "1. Copy the code below. 2. Open the portal, sign in and accept the current documents. 3. Check the code and fingerprint and approve. Tests are enabled for future slots only: 2 per period, 8 per day. No immediate test.",
        "setup_complete_detail": "Your pairing is saved. Tests are paused; check any notice below. Resume the schedule when ready, without reinstalling or pairing again.",
    },
    "es": {
        "upgrade": "Actualizar instalación",
        "upgrade_detail": "Se encontró una instalación existente. Se conservarán los datos de conexión, el vínculo con el Server y el estado activo o en pausa. No es necesario vincular de nuevo.",
        "install_detail": "Instalar el servicio o actualizar una instalación existente, conservando sus datos y vínculo.",
        "target_notice": "Tras aceptar y autorizar el vínculo, se activan las pruebas para horarios futuros: 2 por período, 8 al día. Ninguna prueba inmediata. El Server elige el destino; la falta de autorización o de herramientas impide la activación.",
        "pair_detail": "1. Copia el código de abajo. 2. Abre el portal, inicia sesión y acepta los documentos vigentes. 3. Comprueba el código y la huella y autoriza. Las pruebas se activan solo para horarios futuros: 2 por período, 8 al día. Ninguna prueba inmediata.",
        "setup_complete_detail": "Tu vínculo está guardado. Las pruebas están en pausa; revisa los avisos. Reanuda la agenda cuando quieras, sin reinstalar ni vincular de nuevo.",
    },
}.items():
    TEXT[_locale].update(_copy)

for _locale, _strings in {
    "pt-BR": {"contracted_download":"Download contratado (Mbps, opcional)", "contracted_upload":"Upload contratado (Mbps, opcional)",
        "plan_notice":"Informe as velocidades do seu plano, separadamente. 1 Gbps = 1.000 Mbps. Deixe em branco se não souber. A comparação não comprova SLA.",
        "metric_download":"Download", "metric_upload":"Upload", "plan_result":"{measured} de {contracted} Mbps contratados ({percent}%)", "plan_waiting":"{contracted} Mbps contratados · aguardando resultado aceito deste perfil"},
    "en": {"contracted_download":"Contracted download (Mbps, optional)", "contracted_upload":"Contracted upload (Mbps, optional)",
        "plan_notice":"Enter each speed from your plan separately. 1 Gbps = 1,000 Mbps. Leave blank if unknown. This comparison does not establish an SLA.",
        "metric_download":"Download", "metric_upload":"Upload", "plan_result":"{measured} of {contracted} contracted Mbps ({percent}%)", "plan_waiting":"{contracted} contracted Mbps · waiting for an accepted result for this profile"},
    "es": {"contracted_download":"Descarga contratada (Mbps, opcional)", "contracted_upload":"Subida contratada (Mbps, opcional)",
        "plan_notice":"Indica cada velocidad de tu plan por separado. 1 Gbps = 1.000 Mbps. Déjalo vacío si no lo sabes. La comparación no demuestra un SLA.",
        "metric_download":"Descarga", "metric_upload":"Subida", "plan_result":"{measured} de {contracted} Mbps contratados ({percent}%)", "plan_waiting":"{contracted} Mbps contratados · esperando un resultado aceptado de este perfil"}
}.items():
    TEXT[_locale].update(_strings)

TEXT["pt-BR"]["invalid"] += " Para Mbps, use números positivos com vírgula ou ponto decimal, sem separador de milhar, ou deixe em branco."
TEXT["en"]["invalid"] += " For Mbps, use positive numbers with a decimal comma or point, without thousands separators, or leave blank."
TEXT["es"]["invalid"] += " Para Mbps, usa números positivos con coma o punto decimal, sin separador de miles, o deja el campo vacío."


# Stable protocol codes select the reason; never infer suspension from an unknown error.
AUTHORIZATION_PROBLEMS = {
    **dict.fromkeys(("terms_acceptance_required", "legal_acceptance_required", "acceptance_required",
                     "documents_changed", "legal_context_changed"), "acceptance_notice"),
    **dict.fromkeys(("consent_required", "consent_withdrawn", "contribution_consent_required"), "consent_notice"),
    **dict.fromkeys(("account_suspended", "account_disabled"), "suspension_notice"),
    **dict.fromkeys(("client_revoked", "token_revoked"), "revocation_notice"),
    **dict.fromkeys(("credential_expired", "invalid_token"), "credential_notice"),
    **dict.fromkeys(("machine_privacy_not_ready", "invalid_machine_policy", "invalid_machine_permission",
                     "machine_identity_unavailable", "machine_identity_required", "machine_identity_changed"), "machine_notice"),
    "schedule_update_required": "update_notice",
    "server_rejected": "authorization_notice",
}

for _locale, _strings in {
    "pt-BR": {
        "accept_action": "Registrar aceite e autorização",
        "acceptance_notice": "Falta aceitar os termos de uso e a política de privacidade vigentes.\n\n1. Clique em «{account}» e entre na sua conta.\n2. Revise os documentos, marque as três caixas e clique em «{accept}».\n3. Volte ao Client e clique em «{enable}».\n\nSeu vínculo está preservado. A ativação vale para os próximos horários; nenhum teste imediato.",
        "consent_notice": "A autorização para contribuir está ausente ou foi retirada.\n\nSe quiser voltar a contribuir, clique em «{account}», revise os documentos, marque as três caixas e clique em «{accept}». Depois volte ao Client e clique em «{enable}». Seu vínculo está preservado; nenhum teste imediato.",
        "suspension_notice": "Sua conta está suspensa. As medições, os envios e a criação de novos tokens estão bloqueados.\n\nSolicite uma revisão pelo e-mail fale.conosco@cararalab.com.br. Reinstalar ou reparar o Client não remove a suspensão.",
        "revocation_notice": "A autorização desta instalação foi revogada. O Client não pode renovar tokens nem enviar medições.\n\nClique em «{account}» para conferir a situação. Se precisar de ajuda, contate fale.conosco@cararalab.com.br. Reparar ou reinstalar não restaura a autorização.",
        "credential_notice": "O Server não aceitou o token desta instalação.\n\nClique em «{account}» para verificar o aceite dos documentos e a situação da instalação. Resolva as pendências e tente «{enable}» novamente. Se continuar bloqueado, use «{copy_info}» e contate fale.conosco@cararalab.com.br. Não envie senhas ou tokens.",
        "machine_notice": "Não foi possível validar a identificação desta máquina ou a permissão da agenda.\n\nUse «{copy_info}» e contate fale.conosco@cararalab.com.br. Seu vínculo e os dados locais estão preservados; não é necessário apagar a instalação.",
        "update_notice": "Esta versão do Client precisa ser atualizada para usar a agenda autorizada.\n\nBaixe o instalador atual no site do Server e escolha «{upgrade}», preservando seus dados e vínculo. Depois tente «{enable}» novamente.",
        "authorization_notice": "Não foi possível confirmar a autorização com o Server.\n\nVerifique sua conexão e a situação em «{account}». Se o problema persistir, use «{copy_info}» e contate fale.conosco@cararalab.com.br. Não envie senhas ou tokens.",
    },
    "en": {
        "accept_action": "Record acceptance and authorization",
        "acceptance_notice": "Acceptance of the current Terms of Use and Privacy Policy is required.\n\n1. Click “{account}” and sign in.\n2. Review the documents, select all three checkboxes and click “{accept}”.\n3. Return to the Client and click “{enable}”.\n\nYour pairing is preserved. Activation applies to future scheduled times; no immediate test.",
        "consent_notice": "Contribution authorization is missing or has been withdrawn.\n\nIf you want to contribute again, click “{account}”, review the documents, select all three checkboxes and click “{accept}”. Then return to the Client and click “{enable}”. Your pairing is preserved; no immediate test.",
        "suspension_notice": "Your account is suspended. Measurements, uploads and new tokens are blocked.\n\nRequest a review at fale.conosco@cararalab.com.br. Repairing or reinstalling the Client does not remove the suspension.",
        "revocation_notice": "Authorization for this installation has been revoked. The Client cannot renew tokens or send measurements.\n\nClick “{account}” to check its status. For help, contact fale.conosco@cararalab.com.br. Repairing or reinstalling does not restore authorization.",
        "credential_notice": "The Server did not accept this installation's token.\n\nClick “{account}” to check document acceptance and installation status. Resolve any pending actions and try “{enable}” again. If still blocked, use “{copy_info}” and contact fale.conosco@cararalab.com.br. Do not send passwords or tokens.",
        "machine_notice": "The machine identity or schedule permission could not be validated.\n\nUse “{copy_info}” and contact fale.conosco@cararalab.com.br. Your pairing and local data are preserved; you do not need to delete the installation.",
        "update_notice": "This Client version must be updated to use the authorized schedule.\n\nDownload the current installer from the Server website and choose “{upgrade}”, preserving your data and pairing. Then try “{enable}” again.",
        "authorization_notice": "Authorization could not be confirmed with the Server.\n\nCheck your connection and status in “{account}”. If the problem persists, use “{copy_info}” and contact fale.conosco@cararalab.com.br. Do not send passwords or tokens.",
    },
    "es": {
        "accept_action": "Registrar aceptación y autorización",
        "acceptance_notice": "Falta aceptar los Términos de Uso y la Política de Privacidad vigentes.\n\n1. Haz clic en «{account}» e inicia sesión.\n2. Revisa los documentos, marca las tres casillas y haz clic en «{accept}».\n3. Vuelve al Client y haz clic en «{enable}».\n\nTu vínculo se conserva. La activación se aplica a horarios futuros; ninguna prueba inmediata.",
        "consent_notice": "Falta la autorización para contribuir o se ha retirado.\n\nSi quieres volver a contribuir, haz clic en «{account}», revisa los documentos, marca las tres casillas y haz clic en «{accept}». Después vuelve al Client y haz clic en «{enable}». Tu vínculo se conserva; ninguna prueba inmediata.",
        "suspension_notice": "Tu cuenta está suspendida. Las mediciones, los envíos y los nuevos tokens están bloqueados.\n\nSolicita una revisión en fale.conosco@cararalab.com.br. Reparar o reinstalar el Client no elimina la suspensión.",
        "revocation_notice": "Se ha revocado la autorización de esta instalación. El Client no puede renovar tokens ni enviar mediciones.\n\nHaz clic en «{account}» para comprobar su estado. Si necesitas ayuda, contacta con fale.conosco@cararalab.com.br. Reparar o reinstalar no restablece la autorización.",
        "credential_notice": "El Server no aceptó el token de esta instalación.\n\nHaz clic en «{account}» para comprobar la aceptación de documentos y el estado de la instalación. Resuelve las acciones pendientes e intenta «{enable}» de nuevo. Si sigue bloqueado, usa «{copy_info}» y contacta con fale.conosco@cararalab.com.br. No envíes contraseñas ni tokens.",
        "machine_notice": "No se pudo validar la identidad de esta máquina o el permiso de la agenda.\n\nUsa «{copy_info}» y contacta con fale.conosco@cararalab.com.br. Tu vínculo y los datos locales se conservan; no es necesario eliminar la instalación.",
        "update_notice": "Debes actualizar esta versión del Client para usar la agenda autorizada.\n\nDescarga el instalador actual del sitio del Server y elige «{upgrade}», conservando tus datos y vínculo. Después intenta «{enable}» de nuevo.",
        "authorization_notice": "No se pudo confirmar la autorización con el Server.\n\nComprueba la conexión y el estado en «{account}». Si el problema persiste, usa «{copy_info}» y contacta con fale.conosco@cararalab.com.br. No envíes contraseñas ni tokens.",
    },
}.items():
    TEXT[_locale].update(_strings)


def problem_text(locale, key, *, compact=False):
    """Use the selected language and the exact current button labels."""
    copy = TEXT[locale]
    selected = key + "_summary" if compact and key + "_summary" in copy else key
    return copy[selected].format(account=copy["account"], accept=copy["accept_action"],
                                 enable=copy["enable"], copy_info=copy["copy_info"], upgrade=copy["upgrade"])


# Keep the persistent status readable at the minimum window size.
for _locale, _strings in {
    "pt-BR": {
        "acceptance_notice_summary": "Novo aceite necessário. Em «{account}», revise os documentos, marque as três caixas e clique em «{accept}». Depois volte e clique em «{enable}». Nenhum teste imediato.",
        "consent_notice_summary": "Contribuição sem autorização ou com consentimento retirado. Se quiser contribuir, abra «{account}», revise os documentos e registre sua autorização. Depois clique em «{enable}».",
        "revocation_notice_summary": "Autorização desta instalação revogada. Confira «{account}» ou contate fale.conosco@cararalab.com.br. Reparar não restaura a autorização.",
        "credential_notice_summary": "Token não aceito. Confira as pendências em «{account}» e tente «{enable}». Se persistir, use «{copy_info}» e contate fale.conosco@cararalab.com.br. Não envie senhas ou tokens.",
        "authorization_notice_summary": "Autorização não confirmada. Confira a conexão e «{account}». Se persistir, use «{copy_info}» e contate fale.conosco@cararalab.com.br.",
    },
    "en": {
        "acceptance_notice_summary": "New acceptance required. In “{account}”, review the documents, select all three checkboxes and click “{accept}”. Then return and click “{enable}”. No immediate test.",
        "consent_notice_summary": "Contribution authorization is missing or withdrawn. If you want to contribute, open “{account}”, review the documents and record authorization. Then click “{enable}”.",
        "revocation_notice_summary": "Installation authorization revoked. Check “{account}” or contact fale.conosco@cararalab.com.br. Repair does not restore authorization.",
        "credential_notice_summary": "Token not accepted. Check pending actions in “{account}” and try “{enable}”. If it persists, use “{copy_info}” and contact fale.conosco@cararalab.com.br. Do not send passwords or tokens.",
        "authorization_notice_summary": "Authorization not confirmed. Check your connection and “{account}”. If it persists, use “{copy_info}” and contact fale.conosco@cararalab.com.br.",
    },
    "es": {
        "acceptance_notice_summary": "Nueva aceptación necesaria. En «{account}», revisa los documentos, marca las tres casillas y haz clic en «{accept}». Después vuelve y haz clic en «{enable}». Ninguna prueba inmediata.",
        "consent_notice_summary": "Falta autorización para contribuir o se ha retirado. Si quieres contribuir, abre «{account}», revisa los documentos y registra tu autorización. Después haz clic en «{enable}».",
        "revocation_notice_summary": "Autorización de esta instalación revocada. Revisa «{account}» o contacta con fale.conosco@cararalab.com.br. Reparar no restablece la autorización.",
        "credential_notice_summary": "Token no aceptado. Revisa las acciones pendientes en «{account}» e intenta «{enable}». Si persiste, usa «{copy_info}» y contacta con fale.conosco@cararalab.com.br. No envíes contraseñas ni tokens.",
        "authorization_notice_summary": "Autorización no confirmada. Comprueba la conexión y «{account}». Si persiste, usa «{copy_info}» y contacta con fale.conosco@cararalab.com.br.",
    },
}.items():
    TEXT[_locale].update(_strings)
