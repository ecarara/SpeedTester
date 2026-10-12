# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Edson Angelo Carara
package deployment

import rego.v1

deny contains sprintf("%s: deployed image must use a SHA-256 digest", [name]) if {
    some name, service in input.services
    not regex.match("^.+@sha256:[0-9a-f]{64}$", object.get(service, "image", ""))
}
