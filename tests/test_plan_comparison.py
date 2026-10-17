# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Edson Angelo Carara
"""Declared speeds and immutable accepted-result comparisons, no measurement."""
import tempfile
import unittest
from pathlib import Path
from uuid import uuid4
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from speedtester_protocol.crypto import b64, digest
from speedtester_protocol.queue import EncryptedQueue
from speedtester_protocol.plan import parse_mbps, format_mbps, comparison


class ContractedPlanTests(unittest.TestCase):
    def test_decimal_mbps_conversion_without_guessing_or_truncation(self):
        for value, bps in [('',None),('  ',None),('1000',10**9),('250,5',250_500_000),('0.000001',1),('1000000',10**12),('0.10',100000)]:
            self.assertEqual(parse_mbps(value),bps)
            self.assertEqual(parse_mbps(format_mbps(bps)),bps)
        for value in ['0','-1','NaN','inf','1e3','1.000,5','1,000.5','1.2345678','1000001','1 Mbps','1,2,3']:
            with self.subTest(value=value),self.assertRaises(ValueError):parse_mbps(value)

    def test_separate_percentages_latest_attempt_only_and_profile_changes_do_not_rewrite_history(self):
        with tempfile.TemporaryDirectory() as temp:
            queue=EncryptedQueue(Path(temp),b'k'*32)
            server=Ed25519PrivateKey.generate();possession=Ed25519PrivateKey.generate()
            profile={'version':1,'contracted_download_bps':1_000_000_000,'contracted_upload_bps':200_000_000}
            installed={'origin':'https://server.example','server_key':b64(server.public_key().public_bytes_raw()),'possession_private':possession.private_bytes_raw().hex(),'profile':profile}
            destination=digest({'origin':installed['origin'],'server_key':server.public_key().public_bytes_raw().hex(),'possession_key':possession.public_key().public_bytes_raw().hex()})
            def save(attempt,metric,value,status='valid',accepted=True):
                record={'id':str(uuid4()),'kind':'observation','envelope':{'payload':{'attempt_id':attempt,'profile_digest':digest(profile),'metric':metric,'value':value,'status':status}}}
                queue.put(record,destination)
                if accepted:queue.acknowledge(record['id'],{'payload':{'kind':'observation'}})
                return record
            old=str(uuid4());save(old,'download',500_000_000);save(old,'upload',100_000_000)
            latest=str(uuid4());save(latest,'download',1_050_000_000);save(latest,'upload',None,'error')
            before=queue.records(destination,'accepted')
            actual=comparison(queue,installed)
            self.assertEqual(actual['download']['percent'],105)
            self.assertIsNone(actual['upload']['measured_bps'])
            self.assertIsNone(actual['upload']['percent'])
            save(str(uuid4()),'download',20_000_000,accepted=False)
            self.assertEqual(comparison(queue,installed),actual)
            profile['version']=2;profile['contracted_download_bps']=2_000_000_000
            changed=comparison(queue,installed)
            self.assertEqual(changed['download']['contracted_bps'],2_000_000_000)
            self.assertIsNone(changed['download']['measured_bps'])
            self.assertEqual(queue.records(destination,'accepted'),before)
