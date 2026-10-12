# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Edson Angelo Carara
package deployment

import rego.v1

test_mutable_image_tag_is_rejected if {
    count(deny) == 1 with input as {"services": {"api": {"image": "ghcr.io/ecarara/speedtester-api:main"}}}
}

test_digest_is_accepted if {
    count(deny) == 0 with input as {"services": {"api": {"image":
        "ghcr.io/ecarara/speedtester-api@sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"}}}
}
