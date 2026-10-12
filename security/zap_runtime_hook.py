# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Edson Angelo Carara
"""Bind the packaged scanner control API to IPv4 loopback before startup."""


def start_zap(port, extra_zap_params):
    import zap_common
    original = zap_common.create_start_options

    def loopback_options(mode, selected_port, extra):
        options = original(mode, selected_port, extra)
        for index, option in enumerate(options[:-1]):
            if option == '-host':
                options[index + 1] = '127.0.0.1'
        return options

    zap_common.create_start_options = loopback_options
