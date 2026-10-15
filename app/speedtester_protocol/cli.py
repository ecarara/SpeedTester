# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Edson Angelo Carara

"""Guided headless installation and unattended community synchronization."""
import argparse,json,secrets,sys,time,unicodedata
from contextlib import contextmanager,ExitStack
from pathlib import Path
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey,Ed25519PublicKey
from .crypto import b64,unb64,public_bytes,digest
from .client import HTTPS,ProtocolError
from .enrollment import Credentials,PairingClient
from .installation import protected_queue,systemd_unit
from .models import Profile
from .agent import CommunityAgent
from .runner import IperfRunner
from .environment import sync_environment
from .local_security import process_lock
from .schedule import DailySchedule, migrate_installation, policy

DEFAULT_STATE=Path.home()/".local/share/speedtester-client"


@contextmanager
def exclusive(queue):
    with ExitStack() as stack:
        try:stack.enter_context(process_lock(queue.directory/"process.lock"))
        except BlockingIOError as exc:raise ProtocolError("client_already_running") from exc
        yield


def discover(origin,transport=None):
    origin=HTTPS(origin).origin
    status,_,body=(transport or HTTPS(origin))("GET","/.well-known/speedtester-server",{},None)
    if status!=200 or not isinstance(body,dict) or body.get("protocol_version")!="1" or body.get("origin")!=origin:
        raise ProtocolError("server_configuration_invalid")
    try:key=Ed25519PublicKey.from_public_bytes(unb64(body["signing_key"]))
    except Exception as exc:raise ProtocolError("server_configuration_invalid") from exc
    return key


def context(queue,config,transport=None):
    possession=Ed25519PrivateKey.from_private_bytes(bytes.fromhex(config["possession_private"]))
    measurement=Ed25519PrivateKey.from_private_bytes(bytes.fromhex(config["measurement_private"]))
    server=Ed25519PublicKey.from_public_bytes(unb64(config["server_key"]))
    credentials=Credentials(config["origin"],possession,server,queue,transport=transport)
    return credentials,measurement


def prompt_profile(input_fn=input):
    def required(label):return unicodedata.normalize("NFC"," ".join(input_fn(label+": ").split()))
    kinds={"1":"fiber","2":"coaxial","3":"radio","4":"satellite","5":"cellular","6":"dsl","7":"other","8":"unknown"}
    operator=required("Operadora");country=required("Código do país (ex.: BR)").upper()
    region=required("Estado/região");city=required("Cidade")
    print("Acesso: 1 fibra, 2 coaxial, 3 rádio, 4 satélite, 5 celular, 6 DSL, 7 outro, 8 não sei")
    access=kinds.get(required("Tipo de acesso"))
    print("Enlace local: 1 cabeado/Ethernet, 2 Wi-Fi")
    link={"1":"ethernet","2":"wifi"}.get(required("Enlace"))
    return Profile(version=1,operator=operator,country_code=country,region=region,city=city,access_type=access,link_type=link)


def installation_config(queue,origin,server,input_fn):
    config=queue.state("installation")
    if config:
        if config["origin"]!=origin or config["server_key"]!=b64(public_bytes(server)):
            raise ProtocolError("installation_server_changed")
        return migrate_installation(queue,config)[0]
    profile=prompt_profile(input_fn)
    config={"origin":origin,"server_key":b64(public_bytes(server)),"possession_private":Ed25519PrivateKey.generate().private_bytes_raw().hex(),
        "measurement_private":Ed25519PrivateKey.generate().private_bytes_raw().hex(),"profile":profile.model_dump(),"target_mode":"automatic","schedule":policy()}
    queue.state("installation",config)
    return config


def await_pairing(pairing_client,pairing,sleep):
    delay=pairing.interval
    while int(time.time())<pairing.expires_at:
        try:
            pairing_client.poll(pairing)
            return
        except ProtocolError as exc:
            if exc.code not in {"authorization_pending","slow_down"}:raise
            if exc.code=="slow_down":delay=min(60,delay+5)
        sleep(delay)
    raise ProtocolError("pairing_expired")


def setup(queue,origin,*,transport=None,input_fn=input,sleep=time.sleep,repair=False):
    origin=HTTPS(origin).origin
    server=discover(origin,transport)
    print("Dados enviados após aceite e pareamento: perfil da conexão, métricas separadas e sistema operacional/distribuição/versão/arquitetura. Detalhes: "+origin+"/data")
    config=installation_config(queue,origin,server,input_fn)
    credentials,measurement=context(queue,config,transport)
    if credentials.bundle and not repair:
        credentials.ensure_current();print("Client já pareado; credenciais verificadas.")
    else:
        pairing_client=PairingClient(credentials,measurement);pairing=pairing_client.begin(reset=repair)
        print("Abra "+pairing.verification_uri+" e entre com seu provedor de login.")
        print("Código: "+pairing.user_code)
        print("Impressão digital: "+digest(credentials.identity))
        print("Revise os termos e confirme apenas esta instalação. Aguardando aprovação…",flush=True)
        await_pairing(pairing_client,pairing,sleep)
        DailySchedule(queue,config["schedule"]).refresh(int(time.time()),activate=True)
        print("Pareamento concluído. Tokens guardados na fila cifrada; nenhum token precisa ser copiado.")
    sync_environment(credentials,measurement)
    return config


def cycle(queue,*,transport=None,runner=None,now=None,clock=time.time):
    config=queue.state("installation")
    if not config:raise ProtocolError("setup_required")
    config,_=migrate_installation(queue,config)
    current=int(clock()) if now is None else int(now)
    schedule=DailySchedule(queue,config["schedule"])
    schedule.refresh(current)
    credentials,measurement=context(queue,config,transport)
    client=credentials.client()
    sync_environment(credentials,measurement)
    agent=CommunityAgent(client,queue,measurement,Profile.model_validate(config["profile"]),"iperf3")
    sent=agent.sync()
    if agent.state("active_attempt"):
        # Recovery may preserve error evidence, but cannot authorize another test.
        agent.run_once(None,allow_new=False)
        return "attempt_recovered"
    slot=schedule.claim(current,agent.destination+":grant_request")
    if slot is None:
        return "synchronized" if sent else "waiting"
    attempt_id=None
    try:
        if config.get("target_mode")=="automatic":
            from .targets import automatic_runner
            execute=automatic_runner(client,credentials.bundle.client_id,runner)
        else:
            execute=runner or IperfRunner(config["host"],config["port"])
        def validate(grant):
            moment=int(clock())
            if not slot["at"]<=moment<=slot["deadline"] or moment+(grant.max_duration_ms+999)//1000+60>slot["end_at"]:
                raise ProtocolError("schedule_slot_expired")
            guard=getattr(execute,"__dict__",{}).get("validate_grant")
            if guard:guard(grant)
        def checked(grant):
            validate(grant)
            return execute(grant)
        checked.validate_grant=validate
        attempt_id=agent.run_once(checked)
        return "attempt_completed"
    finally:
        schedule.finish(slot,attempt_id=attempt_id)


def arguments(argv):
    parser=argparse.ArgumentParser(description="SpeedTester Client comunitário")
    commands=parser.add_subparsers(dest="command",required=True)
    for command in ("setup","run","status","service-file"):
        sub=commands.add_parser(command);sub.add_argument("--state",type=Path,default=DEFAULT_STATE)
        if command=="setup":sub.add_argument("--server",required=True);sub.add_argument("--repair",action="store_true")
        if command=="run":sub.add_argument("--once",action="store_true")
        if command=="service-file":sub.add_argument("--executable",type=Path,required=True)
    return parser.parse_args(argv)


def report_blocked(exc):
    # Codes only: never serialize credentials, bodies or operational records.
    code=exc.code if isinstance(exc,ProtocolError) else "local_or_network_failure"
    print("client_blocked: "+code,file=sys.stderr,flush=True)


def run_loop(queue,once):
    while True:
        try:print(cycle(queue),flush=True)
        except (ProtocolError,OSError,ValueError) as exc:
            report_blocked(exc)
            if once:return 1
        if once:return 0
        time.sleep(60)


def show_status(queue):
    config=queue.state("installation")
    if not config:raise ProtocolError("setup_required")
    credentials,_=context(queue,config)
    print(json.dumps({"paired":bool(credentials.bundle),"access_expires_at":credentials.bundle.expires_at if credentials.bundle else None,"next_due":queue.state("next_due")},sort_keys=True))


def dispatch(args,queue):
    if args.command=="setup":
        setup(queue,args.server,repair=args.repair)
    elif args.command=="service-file":print(systemd_unit(args.executable,args.state),end="")
    elif args.command=="status":show_status(queue)
    else:return run_loop(queue,args.once)
    return 0


def main(argv=None):
    args=arguments(argv)
    try:
        queue=protected_queue(args.state)
        with exclusive(queue):return dispatch(args,queue)
    except (ProtocolError,OSError,ValueError) as exc:
        report_blocked(exc)
        return 1
    except KeyboardInterrupt:
        print("Operação interrompida.",file=sys.stderr);return 130


if __name__=="__main__":raise SystemExit(main())
