# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Edson Angelo Carara
package main

import rego.v1

safe_service := {"read_only": true, "cap_drop": ["ALL"], "security_opt": ["no-new-privileges:true"],
    "mem_limit": 536870912, "cpus": 1, "pids_limit": 128, "user": "10001:10001"}

test_safe_stack if {
    count(deny) == 0 with input as {"services": {"api": object.union(safe_service,
        {"environment": {"API_REQUIRE_LOGIN": "true", "API_REQUIRE_ADMIN_TOKEN": "true"}})}}
}

test_privileged_and_host_mount_fail if {
    unsafe := object.union(safe_service, {"privileged": true, "volumes": [{"type": "bind", "target": "/host"}]})
    count(deny) >= 2 with input as {"services": {"collector": unsafe}}
}

test_unbounded_memory_fails if {
    "collector: memory limit must be positive and <= 1 GiB" in deny with input as {
        "services": {"collector": object.union(safe_service, {"mem_limit": 0})}}
}

test_login_disabled_fails if {
    "api: login and administrative authorization must stay enabled" in deny with input as {
        "services": {"api": object.union(safe_service, {"environment": {"API_REQUIRE_LOGIN": "false"}})}}
}
