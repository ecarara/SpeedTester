#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Edson Angelo Carara
"""Build a small SPDX 2.3 SBOM for a SpeedTester source release."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
REQUIREMENT_LINE = re.compile(r"^\s*([A-Za-z0-9][A-Za-z0-9_.-]*)(?:\[[^]]+\])?\s*(.*)$")


def current_commit() -> str:
    """Return the checked-out revision, or a stable placeholder outside Git."""
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        return "UNKNOWN"


def parse_requirements(path: Path) -> list[tuple[str, str]]:
    """Read pinned or constrained direct Python dependencies."""
    dependencies: list[tuple[str, str]] = []
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.split("#", 1)[0].strip()
        if not line or line.startswith(("-", "--")):
            continue
        match = REQUIREMENT_LINE.match(line)
        if match:
            dependencies.append((match.group(1), match.group(2).strip() or "NOASSERTION"))
    return dependencies


def package(spdx_id: str, name: str, version: str, license_name: str) -> dict[str, object]:
    """Create an SPDX package entry without claiming transitive provenance."""
    entry: dict[str, object] = {
        "SPDXID": spdx_id,
        "name": name,
        "versionInfo": version,
        "downloadLocation": "NOASSERTION",
        "filesAnalyzed": False,
        "licenseConcluded": "NOASSERTION",
        "licenseDeclared": license_name,
        "copyrightText": "NOASSERTION",
    }
    if name != "SpeedTester" and version != "NOASSERTION":
        entry["externalRefs"] = [{
            "referenceCategory": "PACKAGE-MANAGER",
            "referenceType": "purl",
            "referenceLocator": f"pkg:pypi/{name.lower()}@{version.lstrip('=!<>~ ')}",
        }]
    return entry


def build_document(version: str, repository: str, commit: str) -> dict[str, object]:
    """Build the SPDX document from project metadata and app requirements."""
    project_id = "SPDXRef-Package-SpeedTester"
    project = package(project_id, "SpeedTester", version, "GPL-3.0-or-later")
    packages = [project]
    relationships: list[dict[str, str]] = []
    for index, (name, dependency_version) in enumerate(parse_requirements(ROOT / "app/requirements.txt"), start=1):
        dependency_id = f"SPDXRef-Package-Dependency-{index}"
        packages.append(package(dependency_id, name, dependency_version, "NOASSERTION"))
        relationships.append({
            "spdxElementId": project_id,
            "relationshipType": "DEPENDS_ON",
            "relatedSpdxElement": dependency_id,
        })

    created = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    return {
        "spdxVersion": "SPDX-2.3",
        "dataLicense": "CC0-1.0",
        "SPDXID": "SPDXRef-DOCUMENT",
        "name": f"SpeedTester-{version}",
        "documentNamespace": f"https://github.com/{repository}/sbom/{version}/{commit}",
        "creationInfo": {
            "created": created,
            "creators": ["Tool: SpeedTester release tooling"],
        },
        "packages": packages,
        "relationships": relationships,
        "annotations": [{
            "annotationDate": created,
            "annotationType": "OTHER",
            "annotator": "Tool: SpeedTester release tooling",
            "comment": f"Source revision: {commit}",
        }],
    }


def main(argv: list[str] | None = None) -> int:
    """Write an SPDX JSON document and return a shell-friendly status."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", required=True)
    parser.add_argument("--repository", default="ecarara/SpeedTester")
    parser.add_argument("--commit", default=None)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    document = build_document(args.version, args.repository, args.commit or current_commit())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
