#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Edson Angelo Carara
"""Build the offline world SVG from pinned public-domain Natural Earth data."""
import argparse
import hashlib
import html
import json
from pathlib import Path

SOURCE_SHA256 = "6866c877d39cba9c357620878839b336d569f8c662d3cfab4cb1dbe2d39c977f"


def build(source, destination):
    """Keep geography in the same equirectangular coordinate system as markers."""
    data = Path(source).read_bytes()
    if hashlib.sha256(data).hexdigest() != SOURCE_SHA256:
        raise ValueError("Expected Natural Earth v5.1.2 countries source")
    features = json.loads(data)["features"]
    lines = [
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1000 500">',
        '<!-- Natural Earth v5.1.2, 1:110m countries; public domain. -->',
        '<!-- Rebuild with scripts/build_world_map.py. See docs/analytics-and-charts.md. -->',
        '<g fill="#294940" stroke="#668578" stroke-opacity=".65" stroke-width=".65" stroke-linejoin="round" fill-rule="evenodd">',
    ]
    for feature in features:
        geometry = feature["geometry"]
        polygons = [geometry["coordinates"]] if geometry["type"] == "Polygon" else geometry["coordinates"]
        parts = []
        for polygon in polygons:
            for ring in polygon:
                points = [(50 + (longitude + 180) * 2.5, 28 + (90 - latitude) * (444 / 180))
                          for longitude, latitude in ring]
                parts.append("M" + "L".join(f"{x:.2f},{y:.2f}" for x, y in points) + "Z")
        name = html.escape(feature["properties"]["ADMIN"], quote=True)
        lines.append('<path data-country="' + name + '" d="' + "".join(parts) + '"/>')
    lines.extend(["</g>", "</svg>"])
    Path(destination).write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", help="ne_110m_admin_0_countries.geojson from Natural Earth v5.1.2")
    parser.add_argument("--output", default="app/dashboard/world-map.svg")
    args = parser.parse_args()
    build(args.source, args.output)
