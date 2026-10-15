# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Edson Angelo Carara
"""Native Service Control Manager host; imported only on Windows."""
import threading
import win32service
import win32serviceutil
from .native_services import SERVICE


class SpeedTesterWindowsService(win32serviceutil.ServiceFramework):
    _svc_name_ = SERVICE
    _svc_display_name_ = "CararaLab SpeedTester Client"

    def __init__(self, arguments):
        super().__init__(arguments)
        self.stop_event = threading.Event()

    def SvcStop(self):
        self.ReportServiceStatus(win32service.SERVICE_STOP_PENDING)
        self.stop_event.set()

    def SvcDoRun(self):
        from .desktop_entry import agent_main
        agent_main(self.stop_event)


def dispatch_service():
    import servicemanager
    servicemanager.Initialize()
    servicemanager.PrepareToHostSingle(SpeedTesterWindowsService)
    servicemanager.StartServiceCtrlDispatcher()
