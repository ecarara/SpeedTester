# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Edson Angelo Carara

"""Single-stream iPerf3 capture with grant-bound payload and wall-clock budgets."""
import json,math,os,re,signal,subprocess,tempfile,time
from types import SimpleNamespace


class IperfRunner:
    def __init__(self,host,port=5201,*,binary="iperf3"):
        if not isinstance(host,str) or not re.fullmatch(r"[A-Za-z0-9:.\[\]-]{1,253}",host) or host.startswith("-") or not 1<=port<=65535:
            raise ValueError("invalid iPerf3 destination")
        self.host,self.port,self.binary=host,port,binary

    @staticmethod
    def _capture(command,deadline,max_duration_ms):
        # Bound output without retaining operational addresses in memory/logs.
        with tempfile.TemporaryFile() as output,tempfile.TemporaryFile() as error:
            options={"start_new_session":True} if os.name!="nt" else {"creationflags":subprocess.CREATE_NO_WINDOW}
            with subprocess.Popen(command,stdout=output,stderr=error,**options) as process:
                try:
                    while process.poll() is None:
                        if max(os.fstat(output.fileno()).st_size,os.fstat(error.fileno()).st_size)>65536:
                            raise RuntimeError("iperf_output_too_large")
                        remaining=deadline-time.monotonic()
                        if remaining<=0:raise subprocess.TimeoutExpired(command,max_duration_ms/1000)
                        time.sleep(min(.01,remaining))
                    if process.returncode:raise RuntimeError("iperf_failed")
                finally:
                    if process.poll() is None:
                        if os.name=="nt":process.kill()
                        else:os.killpg(process.pid,signal.SIGKILL)
                        process.wait()
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

    def __call__(self,grant):
        if grant.runner!="iperf3" or grant.target_id!="participant-configured" or grant.max_bytes<2048 or grant.max_duration_ms<1000:
            raise ValueError("unsupported measurement policy")
        started=time.monotonic();deadline=started+grant.max_duration_ms/1000
        # --bytes counts application payload, not retransmissions, headers or control traffic.
        # Bound each direction to whole blocks and use one stream without an omit phase.
        blocks=grant.max_bytes//2//1024;budget=blocks*1024
        samples=[]
        for reverse in (False,True):
            if deadline-time.monotonic()<=0:raise RuntimeError("measurement_deadline")
            command=[self.binary,"--client",self.host,"--port",str(self.port),"--parallel","1","--bytes",str(budget),"--length","1024","--json"]
            if reverse:command.append("--reverse")
            raw=self._capture(command,deadline,grant.max_duration_ms)
            samples.append(self._summary(raw,reverse,budget))
        elapsed=time.monotonic()-started
        if elapsed*1000>grant.max_duration_ms:raise RuntimeError("measurement_deadline")
        return SimpleNamespace(upload_mbps=samples[0][0],download_mbps=samples[1][0],duration_sec=elapsed,
            transfer_bytes=sum(sample[1] for sample in samples),tcp_retransmits=sum(sample[2] for sample in samples) if all(sample[2] is not None for sample in samples) else None,
            ping_ms=None,jitter_ms=None,packet_loss_pct=None)
