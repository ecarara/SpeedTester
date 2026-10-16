# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Edson Angelo Carara
"""Offline copy of the public data inventory; no participant values or I/O."""

DISCLOSURE_CATALOG = {'pt-BR': {'intro': 'Veja o que o Client comunitário transmite e por quê. O envio de medições e de '
                    'sistema operacional só ocorre após login, aceite vigente, autorização de '
                    'contribuição e pareamento. Consultar esta lista não executa testes.',
           'sections': [['1. Perfil da conexão',
                         'Operadora, país, estado/região, cidade, tecnologia de acesso (fibra, coaxial, '
                         'rádio, satélite, celular, DSL, outra ou desconhecida), enlace '
                         'cabeado/Ethernet ou Wi-Fi e velocidades contratadas de download e upload '
                         'quando informadas. O perfil tem versão e hash; uma correção não reescreve '
                         'medições antigas.'],
                        ['2. Métricas separadas',
                         'Download e upload em bit/s; latência e jitter em microssegundos; perda de '
                         'pacotes em partes por milhão; duração em milissegundos; tráfego transferido '
                         'em bytes; retransmissões TCP em contagem. Cada registro inclui método, '
                         'data/hora, unidade e estado (válido, não suportado, não coletado ou erro). '
                         'Uma métrica ausente não vira zero.'],
                        ['3. Sistema operacional do Client',
                         'Família do sistema operacional, identificador da distribuição, versão da '
                         'distribuição quando disponível e arquitetura (por exemplo, amd64 ou arm64). O '
                         'Client coleta esses campos automaticamente após o pareamento e os envia '
                         'somente enquanto autorizado, quando o Server oferece esse recurso. Alterações '
                         'geram novos registros; não alteram medições anteriores. São informações '
                         'reportadas pelo equipamento do participante, não uma certificação '
                         'independente.'],
                        ['4. Autenticação e integridade',
                         'Identificadores da conta, instalação, eventos e tentativas; rótulo da '
                         'instalação; chaves públicas, provas de posse, nonces, autorizações de '
                         'medição, hashes, assinaturas, manifestos e recibos. Credenciais são '
                         'transmitidas sob HTTPS nos locais previstos pelo protocolo e protegidas '
                         'localmente; o Server mantém hashes de credenciais e respostas cifradas de '
                         'entrega/recuperação. Chaves privadas da instalação não são enviadas.'],
                        ['5. Aceite e consentimento',
                         'Conta e sessão associadas ao aceite; versões e hashes completos dos '
                         'documentos em português, inglês e espanhol; idioma consultado; data/hora '
                         'central; eventos de autorização, retirada e moderação. O login usa o Casdoor '
                         'e os provedores efetivamente habilitados. O SpeedTester armazena o '
                         'identificador do provedor e seu identificador de conta, sem copiar '
                         'automaticamente todos os atributos do login.'],
                        ['6. Conexão e registros técnicos',
                         'Os serviços de rede recebem o IP de origem para estabelecer a conexão HTTPS, '
                         'e ele pode constar nos logs técnicos do proxy, de erro ou segurança. O IP não '
                         'é um campo das observações de métricas. O limitador de pareamento usa um '
                         'identificador derivado. O site utiliza a sessão de autenticação e, quando '
                         'você escolhe outro idioma, um cookie funcional para lembrar a preferência.'],
                        ['7. O que fica fora desse envio',
                         'O registro de sistema operacional não inclui hostname, nome do usuário local, '
                         'número de série, MAC, inventário de hardware, variáveis de ambiente, arquivos '
                         'pessoais ou versão completa do kernel. Não solicitamos endereço residencial '
                         'exato, GPS, contatos, mensagens ou publicações sociais. O identificador '
                         'persistente bruto é usado apenas localmente para derivar o pseudônimo '
                         'descrito no item 9. O Server define e guarda o fuso e a agenda sorteada; '
                         'recebe a referência do horário e o contexto da autorização, sem dump de '
                         'configuração.'],
                        ['8. Uso e controle',
                         'As finalidades, o armazenamento, a retenção, os destinatários e seus direitos '
                         'estão na Política de Privacidade. Resultados públicos serão agregados, '
                         'conforme metodologia e avaliação de risco; contas, instalações e sistema '
                         'operacional não são divulgados individualmente. A suspensão administrativa de '
                         'um token por abuso suspende também a conta e suas credenciais; criar novas '
                         'chaves não contorna o bloqueio da mesma conta. Revogar sua própria '
                         'instalação, retirar consentimento e pedir eliminação são ações distintas. '
                         'Contato: fale.conosco@cararalab.com.br.'],
                        ['9. Identificação pseudônima da máquina e limite de testes',
                         'Após o aceite vigente e o pareamento, o Client deriva localmente um '
                         'identificador pseudônimo por máquina e por Server, usando um identificador '
                         'persistente do sistema e HMAC-SHA256. Envia somente esse resultado, o tipo de '
                         'origem do identificador, o fuso solicitado e os identificadores de '
                         'conta/instalação e de requisição vinculados à assinatura. O identificador '
                         'bruto do sistema não é enviado nem incluído nos diagnósticos. A finalidade é '
                         'reconhecer reinstalações e cópias na mesma máquina para aplicar uma cota '
                         'compartilhada: dois testes em cada um dos quatro períodos e até oito '
                         'tentativas por dia local. O Server mantém o fuso e a agenda sorteada e recusa '
                         'autorizações duplicadas antes do teste; mudar de token, conta ou perfil não '
                         'cria nova cota para a mesma identificação. Reinstalação/clonagem do sistema e '
                         'adulteração por administrador são limites desse mecanismo; ele não é '
                         'certificação física de hardware. O identificador pseudônimo e os vínculos '
                         'entre instalações não são publicados nos comparativos.']],
           'publication': {'title': 'O que poderá aparecer nos resultados públicos',
                           'text': 'Os comparativos reunirão medições de vários participantes em '
                                   'estatísticas por operadora, região, período, tecnologia e métrica. '
                                   'Eles não mostrarão a medição identificada de uma pessoa ou '
                                   'instalação.',
                           'example': 'Exemplo ilustrativo, sem dados reais: “latência mediana da '
                                      'operadora em uma cidade durante um mês”. A estatística resume um '
                                      'grupo; não mostra a conexão de uma residência.',
                           'protection': 'Antes de divulgar um resultado, será necessário avaliar '
                                         'quantas instalações independentes contribuíram e se a '
                                         'combinação dos filtros permite reconhecer uma pessoa ou '
                                         'conexão. Muitos testes da mesma instalação não equivalem a '
                                         'vários participantes. Se o grupo for pequeno ou '
                                         'identificável, será necessário ampliar a região ou o período, '
                                         'reduzir os filtros ou não publicar aquele resultado.',
                           'status': 'Os comparativos e esses critérios de publicação ainda estão em '
                                     'desenvolvimento. A metodologia, incluindo os critérios mínimos de '
                                     'participação e proteção, será publicada antes de ativar as '
                                     'comparações. Não há um número mínimo já definido ou comparativos '
                                     'disponíveis nesta versão.'}},
 'en': {'intro': 'See what the community Client transmits and why. Measurements and OS information are '
                 'sent only after sign-in, current document acceptance, contribution authorization and '
                 'pairing. Reading this list does not run tests.',
        'sections': [['1. Connection profile',
                      'Provider, country, state/region, city, access technology (fiber, coaxial, radio, '
                      'satellite, cellular, DSL, other or unknown), wired/Ethernet or Wi-Fi link, and '
                      'contracted download/upload rates when supplied. The profile has a version and '
                      'hash; a correction does not rewrite earlier measurements.'],
                     ['2. Separate metrics',
                      'Download and upload in bit/s; latency and jitter in microseconds; packet loss in '
                      'parts per million; duration in milliseconds; transferred traffic in bytes; TCP '
                      'retransmissions as a count. Each record includes method, date/time, unit and '
                      'status (valid, not supported, not collected or error). Missing metrics are not '
                      'converted to zero.'],
                     ['3. Client operating system',
                      'OS family, distribution identifier, distribution version when available and '
                      'architecture (for example, amd64 or arm64). The Client collects these fields '
                      'automatically after pairing and sends them only while authorized, when the '
                      'Server advertises this capability. Changes create new records and do not alter '
                      'earlier measurements. This is participant-device reporting, not independent '
                      'certification.'],
                     ['4. Authentication and integrity',
                      'Account, installation, event and attempt identifiers; installation label; public '
                      'keys, possession proofs, nonces, measurement authorizations, hashes, signatures, '
                      'manifests and receipts. Credentials are transmitted over HTTPS where required by '
                      'the protocol and protected locally; the Server stores credential hashes and '
                      'encrypted delivery/recovery responses. Installation private keys are not sent.'],
                     ['5. Acceptance and consent',
                      'Account and session associated with acceptance; full document versions and '
                      'hashes covering Portuguese, English and Spanish; viewed language; central '
                      'date/time; authorization, withdrawal and moderation events. Sign-in uses Casdoor '
                      'and providers actually enabled. SpeedTester stores provider and account '
                      'identifiers without automatically copying all sign-in attributes.'],
                     ['6. Connection and technical logs',
                      'Network services receive the source IP to establish HTTPS connections; it may '
                      'appear in proxy, error or security logs. IP is not a field in metric '
                      'observations. The pairing limiter uses a derived identifier. The site uses an '
                      'authentication session and, when you choose a language, a functional preference '
                      'cookie.'],
                     ['7. What is excluded',
                      'The OS record does not include hostname, local username, serial number, MAC '
                      'address, hardware inventory, environment variables, personal files or the full '
                      'kernel version. We do not request exact home addresses, GPS, contacts, messages '
                      'or social posts. The raw persistent identifier is used only locally to derive '
                      'the pseudonym described in item 9. The Server defines and retains the time zone '
                      'and randomized schedule; it receives the slot reference and authorization '
                      'context, not a configuration dump.'],
                     ['8. Use and control',
                      'Purposes, storage, retention, recipients and your rights are described in the '
                      'Privacy Policy. Public results will be aggregated according to methodology and '
                      'risk assessment; accounts, installations and OS details are not published '
                      'individually. Administrative token suspension for abuse also suspends the '
                      "account and its credentials; new keys cannot bypass that same account's block. "
                      'Revoking your own installation, withdrawing consent and requesting deletion are '
                      'separate actions. Contact: fale.conosco@cararalab.com.br.'],
                     ['9. Pseudonymous machine identity and test limits',
                      'After current consent and pairing, the Client locally derives a pseudonymous '
                      'identifier per machine and Server using a persistent system identifier and '
                      'HMAC-SHA256. It sends only the derived value, its identifier-source category, '
                      'the requested time zone and the signed account/installation and request '
                      'identifiers. The raw system identifier is not sent or included in diagnostics. '
                      'This recognizes reinstalls and copies on the same machine to share a quota: two '
                      'tests in each of four periods and up to eight attempts per local day. The Server '
                      'retains the time zone and randomized plan and rejects duplicate authorizations '
                      'before testing; changing tokens, accounts or profiles does not create a new '
                      'quota for the same identity. OS reinstallation/cloning and administrator '
                      'tampering are limitations; this is not physical hardware certification. The '
                      'pseudonym and links between installations are not published in comparisons.']],
        'publication': {'title': 'What may appear in public results',
                        'text': 'Comparisons will combine measurements from multiple participants into '
                                'statistics by provider, region, period, technology and metric. They '
                                'will not display an identified measurement from a person or '
                                'installation.',
                        'example': 'Illustrative example, with no real data: “the provider’s median '
                                   'latency in a city during a month”. The statistic summarizes a '
                                   'group; it does not display a household connection.',
                        'protection': 'Before publishing a result, we must assess how many independent '
                                      'installations contributed and whether combined filters could '
                                      'identify a person or connection. Many tests from one '
                                      'installation do not equal multiple participants. If the group is '
                                      'small or identifiable, we must broaden the region or period, '
                                      'reduce the filters or withhold that result.',
                        'status': 'Comparisons and these publication criteria are still being '
                                  'developed. The methodology, including minimum participation and '
                                  'protection criteria, will be published before comparisons are '
                                  'enabled. No minimum number has been defined and no comparisons are '
                                  'available in this release.'}},
 'es': {'intro': 'Consulta qué transmite el cliente comunitario y por qué. Las mediciones y la '
                 'información del sistema operativo solo se envían tras iniciar sesión, aceptar los '
                 'documentos vigentes, autorizar la contribución y vincular la instalación. Consultar '
                 'esta lista no ejecuta pruebas.',
        'sections': [['1. Perfil de la conexión',
                      'Operadora, país, estado/región, ciudad, tecnología de acceso (fibra, coaxial, '
                      'radio, satélite, celular, DSL, otra o desconocida), enlace por cable/Ethernet o '
                      'Wi-Fi y velocidades contratadas de descarga y subida cuando se indiquen. El '
                      'perfil tiene versión y hash; una corrección no reescribe las mediciones '
                      'anteriores.'],
                     ['2. Métricas separadas',
                      'Descarga y subida en bit/s; latencia y jitter en microsegundos; pérdida de '
                      'paquetes en partes por millón; duración en milisegundos; tráfico transferido en '
                      'bytes; retransmisiones TCP como recuento. Cada registro incluye método, '
                      'fecha/hora, unidad y estado (válido, no compatible, no recogido o error). Una '
                      'métrica ausente no se convierte en cero.'],
                     ['3. Sistema operativo del cliente',
                      'Familia del sistema operativo, identificador de la distribución, versión de la '
                      'distribución cuando esté disponible y arquitectura (por ejemplo, amd64 o arm64). '
                      'El cliente recoge estos campos automáticamente tras la vinculación y los envía '
                      'solo mientras esté autorizado, cuando el servidor anuncia esta capacidad. Los '
                      'cambios crean nuevos registros y no alteran mediciones anteriores. Son datos '
                      'declarados por el equipo del participante, no una certificación independiente.'],
                     ['4. Autenticación e integridad',
                      'Identificadores de cuenta, instalación, eventos e intentos; etiqueta de '
                      'instalación; claves públicas, pruebas de posesión, nonces, autorizaciones de '
                      'medición, hashes, firmas, manifiestos y recibos. Las credenciales se transmiten '
                      'mediante HTTPS donde lo exige el protocolo y se protegen localmente; el servidor '
                      'guarda hashes de credenciales y respuestas cifradas de entrega/recuperación. No '
                      'se envían las claves privadas de la instalación.'],
                     ['5. Aceptación y consentimiento',
                      'Cuenta y sesión asociadas a la aceptación; versiones y hashes completos de los '
                      'documentos en portugués, inglés y español; idioma consultado; fecha/hora '
                      'central; eventos de autorización, retirada y moderación. El inicio de sesión '
                      'utiliza Casdoor y los proveedores habilitados. SpeedTester guarda los '
                      'identificadores del proveedor y de la cuenta sin copiar automáticamente todos '
                      'los atributos de acceso.'],
                     ['6. Conexión y registros técnicos',
                      'Los servicios de red reciben la IP de origen para establecer la conexión HTTPS; '
                      'puede aparecer en registros técnicos del proxy, de errores o seguridad. La IP no '
                      'es un campo de las observaciones de métricas. El limitador de vinculación usa un '
                      'identificador derivado. El sitio utiliza una sesión de autenticación y, cuando '
                      'eliges un idioma, una cookie funcional de preferencia.'],
                     ['7. Datos excluidos',
                      'El registro del sistema operativo no incluye hostname, nombre de usuario local, '
                      'número de serie, dirección MAC, inventario de hardware, variables de entorno, '
                      'archivos personales ni la versión completa del kernel. No solicitamos dirección '
                      'residencial exacta, GPS, contactos, mensajes ni publicaciones sociales. El '
                      'identificador persistente bruto se usa solo localmente para derivar el seudónimo '
                      'descrito en el apartado 9. El Server define y conserva la zona horaria y la '
                      'programación aleatoria; recibe la referencia del horario y el contexto de '
                      'autorización, sin una copia completa de la configuración.'],
                     ['8. Uso y control',
                      'La Política de Privacidad describe las finalidades, el almacenamiento, la '
                      'conservación, los destinatarios y tus derechos. Los resultados públicos serán '
                      'agregados según la metodología y la evaluación de riesgos; las cuentas, '
                      'instalaciones y detalles del sistema operativo no se publican individualmente. '
                      'La suspensión administrativa de un token por abuso también suspende la cuenta y '
                      'sus credenciales; crear nuevas claves no elude el bloqueo de esa misma cuenta. '
                      'Revocar tu instalación, retirar el consentimiento y solicitar la eliminación son '
                      'acciones distintas. Contacto: fale.conosco@cararalab.com.br.'],
                     ['9. Identificación seudónima del equipo y límites de pruebas',
                      'Tras la aceptación vigente y la vinculación, el Client deriva localmente un '
                      'identificador seudónimo por equipo y Server mediante un identificador '
                      'persistente del sistema y HMAC-SHA256. Envía solo el resultado, la categoría de '
                      'origen del identificador, la zona horaria solicitada y los identificadores '
                      'firmados de cuenta/instalación y solicitud. El identificador bruto del sistema '
                      'no se envía ni se incluye en los diagnósticos. Esto reconoce reinstalaciones y '
                      'copias en el mismo equipo para compartir un límite: dos pruebas en cada uno de '
                      'cuatro períodos y hasta ocho intentos por día local. El Server conserva la zona '
                      'horaria y el plan aleatorio y rechaza autorizaciones duplicadas antes de probar; '
                      'cambiar tokens, cuentas o perfiles no crea otra cuota para la misma '
                      'identificación. Reinstalar/clonar el sistema y la manipulación administrativa '
                      'son limitaciones; no es certificación física de hardware. El seudónimo y los '
                      'vínculos entre instalaciones no se publican en las comparaciones.']],
        'publication': {'title': 'Qué podrá aparecer en los resultados públicos',
                        'text': 'Las comparaciones reunirán mediciones de varios participantes en '
                                'estadísticas por operadora, región, período, tecnología y métrica. No '
                                'mostrarán una medición identificada de una persona o instalación.',
                        'example': 'Ejemplo ilustrativo, sin datos reales: «latencia mediana de la '
                                   'operadora en una ciudad durante un mes». La estadística resume un '
                                   'grupo; no muestra la conexión de una vivienda.',
                        'protection': 'Antes de publicar un resultado, habrá que evaluar cuántas '
                                      'instalaciones independientes contribuyeron y si la combinación '
                                      'de filtros permite identificar a una persona o conexión. Muchas '
                                      'pruebas de una instalación no equivalen a varios participantes. '
                                      'Si el grupo es pequeño o identificable, habrá que ampliar la '
                                      'región o el período, reducir los filtros o no publicar ese '
                                      'resultado.',
                        'status': 'Las comparaciones y estos criterios de publicación siguen en '
                                  'desarrollo. La metodología, incluidos los criterios mínimos de '
                                  'participación y protección, se publicará antes de activar las '
                                  'comparaciones. Todavía no hay un número mínimo definido ni '
                                  'comparaciones disponibles en esta versión.'}}}
