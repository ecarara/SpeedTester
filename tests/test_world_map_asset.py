# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Edson Angelo Carara
"""Asset provenance, projection and safe serialization of offline geography."""
import hashlib
import json
from pathlib import Path
import runpy
import tempfile
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET

from scripts import build_world_map


class WorldMapAssetTests(unittest.TestCase):
    def test_projection_holes_and_country_names_survive_generation(self):
        name = 'Example "<land>" & country'
        data = {"features": [
            {"properties": {"ADMIN": name}, "geometry": {"type": "Polygon", "coordinates": [
                [[-180, 90], [0, 90], [0, 0], [-180, 0], [-180, 90]],
                [[-90, 60], [-60, 60], [-60, 30], [-90, 30], [-90, 60]],
            ]}},
            {"properties": {"ADMIN": "Islands"}, "geometry": {"type": "MultiPolygon", "coordinates": [
                [[[0, 0], [10, 0], [10, -10], [0, 0]]],
                [[[30, -30], [40, -30], [40, -40], [30, -30]]],
            ]}},
        ]}
        raw = json.dumps(data).encode()
        with tempfile.TemporaryDirectory() as temporary:
            source, target = Path(temporary) / "source.json", Path(temporary) / "map.svg"
            source.write_bytes(raw)
            with patch.object(build_world_map, "SOURCE_SHA256", hashlib.sha256(raw).hexdigest()):
                build_world_map.build(source, target)
                original = target.read_bytes()
                build_world_map.build(source, target)
            self.assertEqual(target.read_bytes(), original)
            root = ET.fromstring(original)
            group = root.find("{http://www.w3.org/2000/svg}g")
            self.assertEqual(root.attrib["viewBox"], "0 0 1000 500")
            self.assertEqual(group.attrib["fill-rule"], "evenodd")
            self.assertEqual(group[0].attrib["data-country"], name)
            self.assertTrue(group[0].attrib["d"].startswith("M50.00,28.00"))
            self.assertIn("500.00,250.00", group[0].attrib["d"])
            self.assertEqual(group[0].attrib["d"].count("Z"), 2)
            self.assertEqual(group[1].attrib["d"].count("Z"), 2)
            self.assertNotIn(b"<land>", original)

    def test_unpinned_source_cannot_replace_the_geography_asset(self):
        with tempfile.TemporaryDirectory() as temporary:
            source, target = Path(temporary) / "source.json", Path(temporary) / "map.svg"
            source.write_bytes(b"untrusted source")
            target.write_text("keep existing asset")
            with self.assertRaisesRegex(ValueError, "Natural Earth"):
                build_world_map.build(source, target)
            script = Path(build_world_map.__file__)
            with patch("sys.argv", [str(script), str(source), "--output", str(target)]):
                with self.assertRaisesRegex(ValueError, "Natural Earth"):
                    runpy.run_path(str(script), run_name="__main__")
            self.assertEqual(target.read_text(), "keep existing asset")


if __name__ == "__main__":
    unittest.main()
