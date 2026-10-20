# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Edson Angelo Carara
"""Tests for release metadata helpers."""
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
import hashlib
import json
import sys
import tarfile


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from build_sbom import build_document  # noqa: E402
from generate_checksums import main as checksums_main  # noqa: E402
from validate_release_artifacts import main as validate_main  # noqa: E402


class ReleaseArtifactTests(TestCase):
    def test_release_workflow_has_tag_gate_and_supply_chain_outputs(self):
        workflow = (ROOT / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8")
        self.assertIn("tags: ['v*']", workflow)
        self.assertIn("make check", workflow)
        self.assertIn("build_sbom.py", workflow)
        self.assertIn("generate_checksums.py", workflow)
        self.assertIn("format: [deb, rpm]", workflow)
        self.assertIn("build-deb.sh", workflow)
        self.assertIn("build-rpm.sh", workflow)
        self.assertIn("build-flatpak.sh", workflow)
        self.assertIn("build-pacman.sh", workflow)
        self.assertIn("validate_release_artifacts.py", workflow)
        self.assertIn("macos-install-smoke", workflow)
        self.assertIn("needs: [metadata, source, macos, windows, linux, flatpak, pacman, linux-install-smoke, windows-install-smoke, macos-install-smoke, validate]", workflow)
        self.assertIn("gh release create", workflow)

    def test_sbom_is_spdx_and_contains_direct_dependencies(self):
        document = build_document("0.3.0", "ecarara/SpeedTester", "abc123")
        self.assertEqual(document["spdxVersion"], "SPDX-2.3")
        names = {item["name"] for item in document["packages"]}
        self.assertIn("SpeedTester", names)
        self.assertIn("fastapi", names)
        self.assertIn("aiohttp", names)

    def test_checksum_manifest_is_sorted_and_reproducible(self):
        with TemporaryDirectory() as temporary:
            directory = Path(temporary)
            first = directory / "b.txt"
            second = directory / "a.txt"
            first.write_text("b", encoding="utf-8")
            second.write_text("a", encoding="utf-8")
            self.assertEqual(checksums_main([str(directory)]), 0)
            lines = (directory / "SHA256SUMS").read_text(encoding="utf-8").splitlines()
            self.assertEqual([line.rsplit("  ", 1)[1] for line in lines], ["a.txt", "b.txt"])
            self.assertTrue(lines[0].startswith(hashlib.sha256(b"a").hexdigest()))

    def test_release_validator_accepts_source_and_sbom_artifacts(self):
        with TemporaryDirectory() as temporary:
            directory = Path(temporary)
            archive_path = directory / "SpeedTester-0.3.0.tar.gz"
            with tarfile.open(archive_path, "w:gz") as archive:
                for name, content in {
                    "SpeedTester-0.3.0/LICENSE": "GPL",
                    "SpeedTester-0.3.0/README.md": "SpeedTester",
                    "SpeedTester-0.3.0/app/main.py": "main",
                    "SpeedTester-0.3.0/docs/README.md": "docs",
                }.items():
                    source = directory / name.split("/", 1)[1]
                    source.parent.mkdir(parents=True, exist_ok=True)
                    source.write_text(content, encoding="utf-8")
                    archive.add(source, arcname=name)
            (directory / "SpeedTester-0.3.0.spdx.json").write_text(
                json.dumps(build_document("0.3.0", "ecarara/SpeedTester", "abc123")),
                encoding="utf-8",
            )
            checksums_main([str(directory)])
            self.assertEqual(validate_main([str(directory)]), 0)
