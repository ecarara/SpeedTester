# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Edson Angelo Carara

.PHONY: test compile docs dashboard license-check publication-check source-tarball macos-package check compose-config

PYTHON ?= python3

test:
	PYTHONPATH=app $(PYTHON) -m unittest discover -s tests -v

compile:
	$(PYTHON) -m compileall -q app scripts

docs:
	$(PYTHON) scripts/check_docs.py

dashboard:
	node -e 'const fs=require("fs"); const s=fs.readFileSync("app/dashboard/index.html","utf8"); for (const m of s.matchAll(/<script[^>]*>([\s\S]*?)<\/script>/g)) new Function(m[1]); new Function(fs.readFileSync("app/dashboard/charts.js","utf8")); console.log("dashboard-js-ok")'

license-check:
	$(PYTHON) scripts/check_license.py

publication-check:
	$(PYTHON) scripts/check_publication.py

source-tarball:
	./scripts/build-source-tarball.sh

macos-package:
	./packaging/macos/build-app.sh

check: test compile docs dashboard license-check publication-check
	git diff --check

compose-config:
	docker compose -f docker/compose.yaml config --quiet
