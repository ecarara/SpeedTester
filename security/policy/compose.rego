# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Edson Angelo Carara
package main

import rego.v1

deny contains sprintf("%s: root filesystem must be read-only", [name]) if {
    some name, service in input.services
    object.get(service, "read_only", false) != true
}

deny contains sprintf("%s: drop all capabilities", [name]) if {
    some name, service in input.services
    not "ALL" in object.get(service, "cap_drop", [])
}

deny contains sprintf("%s: no-new-privileges is required", [name]) if {
    some name, service in input.services
    not "no-new-privileges:true" in object.get(service, "security_opt", [])
}

deny contains sprintf("%s: memory limit must be positive and <= 1 GiB", [name]) if {
    some name, service in input.services
    limit := object.get(service, "mem_limit", 0)
    not valid_memory(limit)
}

valid_memory(limit) if {
    is_number(limit)
    limit > 0
    limit <= 1073741824
}

deny contains sprintf("%s: PID limit is required", [name]) if {
    some name, service in input.services
    object.get(service, "pids_limit", 0) <= 0
}

deny contains sprintf("%s: privileged mode is forbidden", [name]) if {
    some name, service in input.services
    object.get(service, "privileged", false)
}

deny contains sprintf("%s: host networking is forbidden", [name]) if {
    some name, service in input.services
    object.get(service, "network_mode", "") == "host"
}

deny contains sprintf("%s: host PID namespace is forbidden", [name]) if {
    some name, service in input.services
    object.get(service, "pid", "") == "host"
}

deny contains sprintf("%s: unexpected capability %s", [name, capability]) if {
    some name, service in input.services
    some capability in object.get(service, "cap_add", [])
    allowed := {"db": {"CHOWN"}, "collector": {"NET_RAW"}, "backup": {"DAC_OVERRIDE"}}
    not capability in object.get(allowed, name, set())
}

deny contains sprintf("%s: UID 10001 is required", [name]) if {
    name in {"api", "collector"}
    service := input.services[name]
    object.get(service, "user", "") != "10001:10001"
}

deny contains sprintf("%s: host bind mount is forbidden", [name]) if {
    some name, service in input.services
    some volume in object.get(service, "volumes", [])
    volume.type == "bind"
    not allowed_ssh_mount(name, volume)
}

allowed_ssh_mount(name, volume) if {
    name == "backup"
    volume.target == "/root/.ssh"
    volume.read_only == true
}

deny contains "api: login and administrative authorization must stay enabled" if {
    some key in {"API_REQUIRE_LOGIN", "API_REQUIRE_ADMIN_TOKEN"}
    env := object.get(input.services.api, "environment", {})
    lower(sprintf("%v", [object.get(env, key, "")])) != "true"
}

deny contains sprintf("%s: CPU limit must be positive and <= 2", [name]) if {
    some name, service in input.services
    not valid_cpu(object.get(service, "cpus", 0))
}

valid_cpu(limit) if {
    to_number(limit) > 0
    to_number(limit) <= 2
}

deny contains sprintf("unexpected service: %s", [name]) if {
    some name, _ in input.services
    not name in {"api", "collector", "db", "backup"}
}

deny contains "backup: database must be mounted read-only" if {
    some volume in input.services.backup.volumes
    volume.target == "/data"
    object.get(volume, "read_only", false) != true
}
