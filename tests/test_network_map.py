# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Edson Angelo Carara

"""Unit coverage for privacy-preserving network map aggregation."""
import unittest

from api.network_map import build_network_map


class NetworkMapTests(unittest.TestCase):
    def test_aggregates_city_country_fallback_and_unavailable_points(self):
        rows = [
            {
                "started_at": "2026-10-01T12:00:00Z", "isp": "Operadora A",
                "isp_organization": "Grupo A", "country": "Brasil",
                "country_code": "BR", "city": "São Paulo", "is_failure": False,
                "download_mbps": 900, "upload_mbps": 450,
            },
            {
                "started_at": "2026-10-01T13:00:00Z", "isp": "Operadora A",
                "isp_organization": "Grupo A", "country": "Brasil",
                "country_code": "BR", "city": "São Paulo", "is_failure": True,
                "download_mbps": None, "upload_mbps": None,
            },
            {
                "started_at": "2026-10-01T14:00:00Z", "isp": None,
                "isp_organization": "Operadora B", "country": "Portugal",
                "country_code": "PT", "city": "Porto", "is_failure": False,
                "download_mbps": 700, "upload_mbps": 300,
            },
            {
                "started_at": "2026-10-01T15:00:00Z", "isp": None,
                "isp_organization": None, "country": None,
                "country_code": "ZZ", "city": None, "is_failure": False,
                "download_mbps": None, "upload_mbps": None,
            },
        ]

        result = build_network_map(rows)

        self.assertEqual(result["totals"], {
            "samples": 4, "operators": 3, "cities": 3, "countries": 3, "unmapped": 1,
        })
        city_point, country_point, unavailable = result["points"]
        self.assertEqual(city_point["coordinate_source"], "city-centroid")
        self.assertEqual(city_point["success_count"], 1)
        self.assertEqual(city_point["failure_count"], 1)
        self.assertEqual(city_point["avg_download_mbps"], 900.0)
        self.assertEqual(city_point["avg_upload_mbps"], 450.0)
        self.assertEqual(city_point["latest_at"], "2026-10-01T13:00:00Z")
        self.assertEqual(country_point["operator"], "Operadora B")
        self.assertEqual(country_point["coordinate_source"], "country-centroid")
        self.assertIsNone(unavailable["latitude"])
        self.assertEqual(unavailable["operator"], "Operadora não identificada")
        self.assertEqual(unavailable["city"], "Cidade não identificada")
        self.assertEqual(unavailable["country"], "País não identificado")
        self.assertNotIn("public_ip", city_point)

    def test_known_city_names_are_accent_insensitive_and_empty_input_is_stable(self):
        result = build_network_map([{
            "started_at": "2026-10-01T12:00:00Z", "isp": "Operadora",
            "country": "Brasil", "country_code": "br", "city": "São Paulo",
            "is_failure": False, "download_mbps": 1, "upload_mbps": 2,
        }])
        self.assertEqual(result["points"][0]["coordinate_source"], "city-centroid")
        self.assertEqual(result["points"][0]["country_code"], "BR")
        self.assertEqual(build_network_map([]), {
            "points": [],
            "totals": {"samples": 0, "operators": 0, "cities": 0, "countries": 0, "unmapped": 0},
        })


if __name__ == "__main__":
    unittest.main()
