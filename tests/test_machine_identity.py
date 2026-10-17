# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Edson Angelo Carara
"""No hardware telemetry or measurements: stable pseudonyms and canonical text."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, mock_open
from speedtester_protocol.machine import machine_identity, persistent_identifier
from speedtester_protocol.client import ProtocolError
from speedtester_protocol.models import Profile
from speedtester_protocol.profile_text import normalize_text
from speedtester_protocol.schedule import migrate_installation, DailySchedule, policy
from speedtester_protocol.installation import protected_queue


class MachineIdentityTests(unittest.TestCase):
    def test_a_thousand_installations_share_one_origin_scoped_id_without_raw_os_identifier(self):
        raw='12345678123456781234567812345678'
        with patch('speedtester_protocol.machine.persistent_identifier',return_value=('linux-machine-id',raw)):
            identities=[machine_identity('https://server.example') for _ in range(1000)]
            self.assertEqual(len({i['machine_id'] for i in identities}),1)
            self.assertEqual(identities[0],machine_identity('https://SERVER.example:443/'))
            self.assertNotEqual(identities[0],machine_identity('https://another.example'))
            self.assertNotIn(raw,json.dumps(identities[0]))
        with patch('speedtester_protocol.machine.persistent_identifier',return_value=('linux-machine-id','87654321876543218765432187654321')):
            self.assertNotEqual(identities[0],machine_identity('https://server.example'))

    def test_linux_missing_or_placeholder_identity_has_no_random_fallback(self):
        with patch('speedtester_protocol.machine.platform.system',return_value='Linux'):
            for value in ('','0'*32,'f'*32,'uninitialized','hostname'):
                with self.subTest(value=value),patch('pathlib.Path.open',mock_open(read_data=value)):
                    with self.assertRaises(ProtocolError) as error:persistent_identifier()
                    self.assertEqual(error.exception.code,'machine_identity_unavailable')
            with patch('pathlib.Path.open',side_effect=PermissionError):
                with self.assertRaises(ProtocolError):persistent_identifier()

    def test_profile_normalizes_case_spacing_and_unicode_before_it_can_be_signed(self):
        profile=Profile(version=1,operator='  opéradora   Exemplo ',country_code=' br ',region=' sa\u0303o  paulo ',city=' guarulhos ',access_type='fiber',link_type='wifi')
        self.assertEqual((profile.operator,profile.country_code,profile.region,profile.city),('OPÉRADORA EXEMPLO','BR','SÃO PAULO','GUARULHOS'))
        for text in ('vivo','VIVO','ViVo'):
            self.assertEqual(normalize_text(text),'VIVO')
        with self.assertRaises(ValueError):normalize_text('hidden\x00value')
        self.assertEqual((profile.access_type,profile.link_type),('fiber','wifi'))

    def test_profile_upgrade_increments_version_without_touching_original_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            queue=protected_queue(Path(directory).resolve()/'queue')
            old={'profile':{'version':7,'operator':'Example','country_code':'BR','region':'São Paulo','city':'Guarulhos','access_type':'fiber','link_type':'ethernet','contracted_download_bps':None,'contracted_upload_bps':None},'schedule':policy('America/Sao_Paulo'),'possession_private':'unchanged'}
            queue.state('installation',old)
            queue.state('signed-evidence',{'digest':'original','text':'São Paulo'})
            migrated,changed=migrate_installation(queue,old)
            self.assertTrue(changed);self.assertEqual(migrated['profile']['version'],8)
            self.assertEqual(migrated['profile']['region'],'SÃO PAULO')
            self.assertEqual(migrated['possession_private'],'unchanged')
            self.assertEqual(queue.state('signed-evidence'),{'digest':'original','text':'São Paulo'})
            again,changed=migrate_installation(queue,migrated)
            self.assertFalse(changed);self.assertEqual(again,migrated)

    def test_server_schedule_uses_new_namespace_and_preserves_local_history(self):
        with tempfile.TemporaryDirectory() as directory:
            queue=protected_queue(Path(directory).resolve()/'queue')
            old=DailySchedule(queue,policy('America/Sao_Paulo'))
            days=old.refresh(1792140000)
            key=old.day_key(__import__('datetime').date.fromisoformat(days[0]['date']))
            before=queue.state(key)
            central=DailySchedule(queue,{'format':'quadrants-server-v1','timezone':'America/Sao_Paulo','seed':'a'*64})
            central.refresh(1792140000)
            self.assertEqual(queue.state(key),before)
            self.assertNotEqual(old.header_key,central.header_key)


class MachineProtocolTests(unittest.TestCase):
    def setUp(self):
        from test_desktop_client import SignedProvider, configuration
        from speedtester_protocol.desktop_service import DesktopEngine
        from speedtester_protocol.crypto import sign, verify
        from speedtester_protocol.models import MachineReport, MachinePolicy, MachinePermission
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.provider=SignedProvider();self.supported=False;self.tamper=False;self.requests=[];self.permission_denied=False;self.permission_tamper=False
        self.queue=protected_queue(Path(self.temp.name).resolve()/'queue')
        def transport(method,path,headers,payload):
            if path=='/.well-known/speedtester-server':
                status,reply_headers,body=self.provider(method,path,headers,payload)
                return status,reply_headers,{**body,'capabilities':['machine-schedule-v1'] if self.supported else []}
            if path=='/api/v1/machine/permission':
                if self.permission_denied:
                    return 403,{}, {'code':'terms_acceptance_required'}
                import time
                value=MachinePermission(request_id=payload['request_id'],client_id=str(__import__('uuid').uuid4()) if self.permission_tamper else self.provider.client_id,
                    legal_digest='c'*64,privacy_version='synthetic-privacy',issued_at=int(time.time()),expires_at=int(time.time())+300)
                return 200,{},sign(value.model_dump(),self.provider.key,'machine-permission-v1')
            if path=='/api/v1/machine':
                from speedtester_protocol.crypto import public_bytes
                from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
                _,measurement=self.engine.credentials()
                request=MachineReport.model_validate(verify(payload,Ed25519PublicKey.from_public_bytes(public_bytes(measurement)),'machine-report-v1'))
                self.requests.append(request.model_dump())
                policy=MachinePolicy(request_id=request.request_id,client_id=request.client_id,
                    machine_id='b'*64 if self.tamper else request.machine_id,timezone='UTC',seed='f'*64)
                return 200,{},sign(policy.model_dump(),self.provider.key,'machine-policy-v1')
            return self.provider(method,path,headers,payload)
        self.engine=DesktopEngine(self.queue,transport=transport,runner=lambda *_:self.fail('No measurements'))
        self.engine.dispatch('configure',configuration());self.engine.dispatch('pair',{})
        self.provider.approved=True;self.engine.next_poll=0
        self.assertEqual(self.engine.tick(),'paired')
        self.credentials,self.measurement=self.engine.credentials()

    def test_signed_policy_is_cached_and_central_timezone_replaces_only_the_active_plan(self):
        from speedtester_protocol.machine import sync_machine
        self.supported=True
        installed=self.queue.state('installation')
        with patch('speedtester_protocol.machine.machine_identity',return_value={'machine_id':'a'*64,'basis':'linux-machine-id'}) as collect:
            changed=sync_machine(self.credentials,self.measurement,installed)
            self.assertEqual(changed['schedule'],{'format':'quadrants-server-v1','timezone':'UTC','seed':'f'*64})
            self.assertEqual(sync_machine(self.credentials,self.measurement,changed),changed)
            collect.assert_called_once()
        self.assertEqual(len(self.requests),1)
        self.assertTrue(self.engine.status()['measurements_enabled'])
        self.assertNotIn(b'"machine_id"',self.queue.path.read_bytes())

    def test_pending_acceptance_blocks_identifier_collection_and_transmission(self):
        from speedtester_protocol.machine import sync_machine
        self.supported=True;self.permission_denied=True
        with patch('speedtester_protocol.machine.machine_identity',side_effect=AssertionError('No machine identifier before current consent')) as collect:
            with self.assertRaises(ProtocolError) as error:sync_machine(self.credentials,self.measurement,self.queue.state('installation'))
            self.assertEqual(error.exception.code,'terms_acceptance_required')
            collect.assert_not_called()
        self.assertEqual(self.requests,[])
        self.assertIsNone(self.queue.state(self.credentials.scope+':machine:pending'))

    def test_permission_for_another_client_is_rejected_before_reading_identity(self):
        from speedtester_protocol.machine import sync_machine
        self.supported=True;self.permission_tamper=True
        with patch('speedtester_protocol.machine.machine_identity',side_effect=AssertionError('No identifier from an unbound permission')) as collect:
            with self.assertRaises(ProtocolError) as error:sync_machine(self.credentials,self.measurement,self.queue.state('installation'))
            self.assertEqual(error.exception.code,'invalid_machine_permission')
            collect.assert_not_called()
        self.assertEqual(self.requests,[])

    def test_unadvertised_feature_collects_nothing_and_tampered_policy_is_rejected(self):
        from speedtester_protocol.machine import sync_machine
        installed=self.queue.state('installation')
        with patch('speedtester_protocol.machine.machine_identity',side_effect=AssertionError('No identifier without advertised capability')):
            self.assertEqual(sync_machine(self.credentials,self.measurement,installed),installed)
        self.supported=True;self.tamper=True
        with patch('speedtester_protocol.machine.machine_identity',return_value={'machine_id':'a'*64,'basis':'linux-machine-id'}):
            with self.assertRaises(ProtocolError) as error:sync_machine(self.credentials,self.measurement,installed)
        self.assertEqual(error.exception.code,'invalid_machine_policy')
        self.assertEqual(self.queue.state('installation'),installed)
        self.assertIsNone(self.queue.state(self.credentials.scope+':machine:policy'))


class CentralPlanContractTests(unittest.TestCase):
    def test_central_offsets_have_a_fixed_cross_runtime_wire_vector(self):
        from datetime import date
        from speedtester_protocol.central_slots import plan_central_day_slots
        planned=plan_central_day_slots(date(2026,10,16),'UTC','a'*64)
        self.assertEqual([s.scheduled_for for s in planned],[
            '2026-10-16T04:06:52Z','2026-10-16T05:31:42Z','2026-10-16T07:37:01Z','2026-10-16T11:48:28Z',
            '2026-10-16T14:34:55Z','2026-10-16T17:17:58Z','2026-10-16T22:33:48Z','2026-10-16T23:50:54Z'])
        self.assertEqual([s.slot_index for s in planned],[1,2]*4)

    def test_dst_days_keep_two_slots_per_period_inside_local_boundaries(self):
        from datetime import date,datetime
        from zoneinfo import ZoneInfo
        from speedtester_protocol.central_slots import plan_central_day_slots
        for day in (date(2026,3,8),date(2026,11,1)):
            planned=plan_central_day_slots(day,'America/New_York','b'*64)
            self.assertEqual(len(planned),8)
            hours=[datetime.fromisoformat(s.scheduled_for.replace('Z','+00:00')).astimezone(ZoneInfo('America/New_York')).hour for s in planned]
            self.assertTrue(all(start<=h<start+6 for start,h in zip([0,0,6,6,12,12,18,18],hours)))
