# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Edson Angelo Carara
"""Exercise Windows ACL policy with synthetic SIDs; never changes host ACLs."""
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
from speedtester_protocol import local_security as security


class FakeACL:
    def __init__(self, entries=()):
        self.entries = list(entries)

    def GetAceCount(self):
        return len(self.entries)

    def GetAce(self, index):
        return self.entries[index]

    def AddAccessAllowedAceEx(self, _revision, inherit, access, sid):
        self.entries.append(((1, inherit), access, sid))


class WindowsSecurityTests(unittest.TestCase):
    def test_acl_validation_rejects_missing_untrusted_and_unreadable_permissions(self):
        api = SimpleNamespace(SE_FILE_OBJECT=1, DACL_SECURITY_INFORMATION=2, ACCESS_ALLOWED_ACE_TYPE=1)
        rights = SimpleNamespace(FILE_GENERIC_READ=1)
        descriptor = SimpleNamespace(GetSecurityDescriptorDacl=Mock())
        api.GetNamedSecurityInfo = Mock(return_value=descriptor)
        path = Path('synthetic')
        invalid = [None, FakeACL(), FakeACL([((2, 0), 1, 'service')]),
                   FakeACL([((1, 0), 1, 'untrusted')]), FakeACL([((1, 0), 0, 'service')])]
        for acl in invalid:
            with self.subTest(acl=acl):
                descriptor.GetSecurityDescriptorDacl.return_value = acl
                with self.assertRaisesRegex(ValueError, 'insecure_state_acl|state_owner_mismatch'):
                    security._validate_windows_acl(path, 'service', ['service', 'system', 'admin'], api, rights)
        descriptor.GetSecurityDescriptorDacl.return_value = FakeACL([((1, 0), 1, 'service')])
        security._validate_windows_acl(path, 'service', ['service', 'system', 'admin'], api, rights)

    def test_owner_reassignment_requires_the_current_owner_and_elevation(self):
        import ctypes
        descriptor = SimpleNamespace(GetSecurityDescriptorOwner=Mock(return_value='intruder'))
        api = SimpleNamespace(SE_FILE_OBJECT=1, OWNER_SECURITY_INFORMATION=4,
            GetNamedSecurityInfo=Mock(return_value=descriptor), SetNamedSecurityInfo=Mock())
        path = Path('synthetic')
        allowed = ['service', 'system', 'admin']
        with patch.object(security, 'windows_identity', return_value='caller'), \
                patch.object(ctypes, 'windll', SimpleNamespace(shell32=SimpleNamespace(IsUserAnAdmin=lambda: True)), create=True):
            with self.assertRaisesRegex(ValueError, 'state_owner_mismatch'):
                security._ensure_windows_owner(path, allowed, True, api)
            descriptor.GetSecurityDescriptorOwner.return_value = 'caller'
            with self.assertRaisesRegex(ValueError, 'state_owner_mismatch'):
                security._ensure_windows_owner(path, allowed, False, api)
            security._ensure_windows_owner(path, allowed, True, api)
            self.assertEqual(api.SetNamedSecurityInfo.call_args.args[3], 'admin')
            descriptor.GetSecurityDescriptorOwner.return_value = 'service'
            api.SetNamedSecurityInfo.reset_mock()
            security._ensure_windows_owner(path, allowed, False, api)
            api.SetNamedSecurityInfo.assert_not_called()

    def test_windows_acl_applies_only_service_system_and_administrator_access(self):
        acl = FakeACL([((1, 0), 1, 'service')])
        descriptor = SimpleNamespace(GetSecurityDescriptorOwner=lambda: 'service', GetSecurityDescriptorDacl=lambda: acl)
        api = SimpleNamespace(SE_FILE_OBJECT=1, OWNER_SECURITY_INFORMATION=2, DACL_SECURITY_INFORMATION=4,
            PROTECTED_DACL_SECURITY_INFORMATION=8, WinLocalSystemSid='system', WinBuiltinAdministratorsSid='admin',
            ACCESS_ALLOWED_ACE_TYPE=1, ACL_REVISION_DS=2, ACL=FakeACL,
            CreateWellKnownSid=lambda sid: sid, GetNamedSecurityInfo=lambda *_: descriptor,
            SetNamedSecurityInfo=Mock())
        modules = {'win32security': api, 'win32con': SimpleNamespace(OBJECT_INHERIT_ACE=1, CONTAINER_INHERIT_ACE=2),
                   'ntsecuritycon': SimpleNamespace(FILE_GENERIC_READ=1, FILE_GENERIC_EXECUTE=2, FILE_ALL_ACCESS=7)}
        with patch.dict(sys.modules, modules):
            security.windows_acl(Path('synthetic'), principal='service', apply=True, directory=True, read_only=True)
        actual = api.SetNamedSecurityInfo.call_args.args[-2].entries
        self.assertEqual({entry[-1] for entry in actual}, {'service', 'system', 'admin'})
        self.assertEqual(actual[0][1], 3)
        self.assertEqual(actual[0][0][1], 3)
