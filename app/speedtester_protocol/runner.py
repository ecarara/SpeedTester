# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Edson Angelo Carara

"""Single-stream iPerf3 capture with grant-bound payload and wall-clock budgets."""
import json,math,os,re,signal,subprocess,tempfile,time,sys
from types import SimpleNamespace
from pathlib import Path
from .bundled_tools import iperf_binary


def _stop_process(process):
    if process.poll() is None:
        if os.name=="nt":process.kill()
        else:
            try:
                os.killpg(process.pid,signal.SIGKILL)
            except (ProcessLookupError, PermissionError):
                # It may have exited between poll and kill, or
                # the host may restrict process-group signals.
                if process.poll() is None:process.kill()
        process.wait()


class IperfRunner:
    def __init__(self,host,port=5201,*,binary=None,authorize=None,target_id="participant-configured",target_scope=None,expires_at=None):
        if not isinstance(host,str) or not re.fullmatch(r"[A-Za-z0-9:.\[\]-]{1,253}",host) or host.startswith("-") or not 1<=port<=65535:
            raise ValueError("invalid iPerf3 destination")
        tool = binary or iperf_binary()
        if tool is None and getattr(sys, "frozen", False):
            raise FileNotFoundError("iperf3_required")
        self.host,self.port,self.binary=host,port,tool or "iperf3"
        self.authorize=authorize
        self.target_id,self.target_scope,self.expires_at=target_id,target_scope,expires_at

    @staticmethod
    def _capture(command,deadline,max_duration_ms,environment=None):
        # Bound output without retaining operational addresses in memory/logs.
        with tempfile.TemporaryFile() as output,tempfile.TemporaryFile() as error:
            options={"start_new_session":True} if os.name!="nt" else {"creationflags":subprocess.CREATE_NO_WINDOW}
            with subprocess.Popen(command,stdout=output,stderr=error,env=environment,**options) as process:
                try:
                    while process.poll() is None:
                        if max(os.fstat(output.fileno()).st_size,os.fstat(error.fileno()).st_size)>65536:
                            raise RuntimeError("iperf_output_too_large")
                        remaining=deadline-time.monotonic()
                        if remaining<=0:raise subprocess.TimeoutExpired(command,max_duration_ms/1000)
                        time.sleep(min(.01,remaining))
                    if process.returncode:raise RuntimeError("iperf_failed")
                finally:
                    _stop_process(process)
            output.seek(0);raw=output.read(65537)
            if len(raw)>65536:raise RuntimeError("iperf_output_too_large")
        return raw

    @staticmethod
    def _summary(raw,reverse,budget):
        summary=json.loads(raw)["end"]["sum_received" if reverse else "sum_sent"]
        size,speed=summary["bytes"],summary["bits_per_second"]
        if type(size) is not int or not 0<=size<=budget or type(speed) not in (int,float) or not math.isfinite(speed) or speed<0:
            raise RuntimeError("invalid_runner_metrics")
        retransmits=summary.get("retransmits")
        if retransmits is not None and (type(retransmits) is not int or retransmits<0):raise RuntimeError("invalid_runner_metrics")
        return speed/1_000_000,size,retransmits

    def check_policy(self,grant):
        if (grant.runner!="iperf3" or grant.target_id!=self.target_id or grant.max_bytes<2048 or grant.max_duration_ms<1000
                or (self.target_scope is not None and grant.target_scope!=self.target_scope)
                or (self.expires_at is not None and time.time()>=self.expires_at)):
            raise ValueError("unsupported measurement policy")

    def _direction_command(self, reverse, budget, access, public_key):
        port = self.port
        if access:
            port = access.download_port if reverse else access.upload_port
        command = [self.binary, "--client", self.host, "--port", str(port), "--parallel", "1",
                   "--bytes", str(budget), "--length", "1024", "--json", "--connect-timeout", "5000"]
        if access:
            command.extend(("--username", access.username, "--rsa-public-key-path", public_key.as_posix()))
        if reverse:
            command.append("--reverse")
        return command

    def __call__(self,grant):
        self.check_policy(grant)
        started=time.monotonic();deadline=started+grant.max_duration_ms/1000
        # --bytes counts application payload, not retransmissions, headers or control traffic.
        # Bound each direction to whole blocks and use one stream without an omit phase.
        blocks=grant.max_bytes//2//1024;budget=blocks*1024
        access = self.authorize(grant) if self.authorize else None
        samples=[]
        # Credentials never enter command arguments, diagnostics, or the local queue.
        with tempfile.TemporaryDirectory(prefix="speedtester-target-") as temporary:
            environment = None
            public_key = Path(temporary) / "public.pem"
            if access:
                public_key.write_text(access.rsa_public_key)
                public_key.chmod(0o600)
                environment = os.environ.copy()
                environment["IPERF3_PASSWORD"] = access.password
            for reverse in (False,True):
                if deadline-time.monotonic()<=0 or (access and time.time() >= access.expires_at):
                    raise RuntimeError("measurement_deadline")
                command = self._direction_command(reverse, budget, access, public_key)
                raw=self._capture(command,deadline,grant.max_duration_ms,environment) if access else self._capture(command,deadline,grant.max_duration_ms)
                samples.append(self._summary(raw,reverse,budget))
        elapsed=time.monotonic()-started
        if elapsed*1000>grant.max_duration_ms:raise RuntimeError("measurement_deadline")
        return SimpleNamespace(upload_mbps=samples[0][0],download_mbps=samples[1][0],duration_sec=elapsed,
            transfer_bytes=sum(sample[1] for sample in samples),tcp_retransmits=sum(sample[2] for sample in samples) if all(sample[2] is not None for sample in samples) else None,
            ping_ms=None,jitter_ms=None,packet_loss_pct=None)
