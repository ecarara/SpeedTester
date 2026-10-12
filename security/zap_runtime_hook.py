# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Edson Angelo Carara
"""Bind the packaged scanner control API to IPv4 loopback before startup."""


def start_zap(port, extra_zap_params):
    import zap_common
    from zapv2 import ZAPv2
    original = zap_common.create_start_options
    original_client = ZAPv2.__init__

    def loopback_client(self, *args, **kwargs):
        if 'proxies' in kwargs:
            kwargs['proxies'] = {scheme: address.replace('://localhost:', '://127.0.0.1:')
                                 for scheme, address in kwargs['proxies'].items()}
        original_client(self, *args, **kwargs)

    def loopback_options(mode, selected_port, extra):
        options = original(mode, selected_port, extra)
        for index, option in enumerate(options[:-1]):
            if option == '-host':
                options[index + 1] = '127.0.0.1'
        return options

    zap_common.create_start_options = loopback_options
    # Packaged scripts use localhost, which can select IPv6 independently of
    # the explicitly bound IPv4 listener. Keep the client on the same address.
    ZAPv2.__init__ = loopback_client
