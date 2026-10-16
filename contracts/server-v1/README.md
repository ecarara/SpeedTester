# SpeedTester Server protocol v1

Public consumer contract. The private Server implementation is not required to run Client unit tests.

- Tokens use the `Authorization: DPoP <access-token>` header and an RFC 9449 proof.
- Requests require current account-linked legal acceptance and contribution consent.
- Grant/receipt envelopes use domain-separated Ed25519 signatures over RFC 8785 canonical JSON.
- Each typed metric observation is signed and acknowledged separately; a complete manifest binds their hashes.
- Missing metrics are explicit states, never zero. Profiles include declared access technology and Ethernet/Wi-Fi context.
- Same IDs and content are idempotent; changed replays are conflicts.
- `terms_acceptance_required`, `contribution_consent_required`, `client_revoked`, `token_expired`, `proof_replayed` and `invalid_signed_record` pause/refuse contribution.

Schemas are generated from `speedtester_protocol.models` and checked by the public unit suite. The private Server runs provider and real integration tests against this contract. Consumers verify signatures, exact IDs/digests, version and HTTPS origin.

## Pairing and rotating credentials

`POST /api/v1/pairings` accepts a signed `PairingRequest` (`pairing-request-v1`) and returns a signed `Pairing` (`pairing-v1`). The user follows the exact HTTPS verification URI and explicitly confirms the code and installation fingerprint in the authenticated portal. `POST /api/v1/pairings/token` uses the device secret in an Authorization header plus a DPoP proof bound to the installation key, URI and nonce. `authorization_pending`, `slow_down` and expiry enforce bounded polling. No token appears in a URL.

`CredentialBundle` envelopes (`credentials-v1`) bind client identity, possession key, request ID and expirations. `POST /api/v1/credentials/rotate` takes a `RotationRequest`, with the refresh token in the Authorization header and its bound DPoP proof. The client durably saves the pending request before transmission and only replaces tokens after signature/binding verification. Same-request recovery is bounded; different-request reuse revokes the family.

This is the SpeedTester application protocol, inspired by [device authorization](https://www.rfc-editor.org/rfc/rfc8628), [OAuth security guidance](https://www.rfc-editor.org/rfc/rfc9700) and [DPoP](https://www.rfc-editor.org/rfc/rfc9449). The pairing/renewal JSON routes are not generic OAuth token endpoints and do not claim full OAuth wire compatibility.

See the [installation guide](../../docs/community-client.md). Public aggregate queries and operator awards remain subsequent work. The existing standalone collector is unaffected.

### Automatic test targets (additive capability)

`automatic-test-target-v1` adds authenticated `POST /api/v1/test-target` with `TargetRequest` and a `TestTarget` envelope signed under `test-target-v1`. Access token, DPoP, active account/client and current legal authorization are required. The response binds the request/client IDs, endpoint, scope, deterministic target ID, and a lifetime no longer than 300 seconds. Fetching this policy is not a measurement grant and does not contact the destination. Never substitute a local/manual endpoint if this capability is unavailable or its signature/context is invalid. Grants retain their unchanged v1 schema; the runner must enforce the matching central target ID/scope before execution.

## Normalized profiles and machine schedules

Human-entered `operator`, `country_code`, `region` and `city` are normalized to Unicode NFC, collapsed spaces and uppercase before transmission and again at the provider boundary. Accents remain intact. URLs, technical enums, keys and signatures are unchanged. A profile correction creates a new profile version; original signed records are never rewritten to change their case.

Before reading or deriving the local machine identifier, the Client sends only a random `MachinePermissionRequest` to authenticated `POST /api/v1/machine/permission`. The signed `MachinePermission` (`machine-permission-v1`) must match its request and client, and be fresh (at most five minutes). The provider checks current account-linked consent and the explicitly selected published privacy version before issuing it. Refusal or an invalid reply causes no local identity read or machine report transmission. The provider rechecks these gates when receiving the report.

A Server advertising `machine-schedule-v1` requires authenticated `POST /api/v1/machine` with a measurement-key-signed `MachineReport` (`machine-report-v1`). It requires current contribution consent and a privacy version explicitly configured to disclose this new category. The signed `MachinePolicy` (`machine-policy-v1`) binds request, client and pseudonymous machine identity to the central time zone and schedule seed. The Client verifies the signature and bindings before storing the policy in its encrypted state.

The Client derives its machine pseudonym with HMAC-SHA256, using the persistent OS identifier as the local key and `CararaLab-SpeedTester-machine-v1\0<canonical HTTPS origin>\0<identifier basis>` as the ASCII message. The origin folds host case and the default HTTPS port. The raw OS identifier, hostname, MAC, serial number and private keys are never sent as this report. There is no random identifier fallback when a system identity cannot be obtained. This follows the application-specific approach described in [systemd's machine identifier API](https://www.freedesktop.org/software/systemd/man/sd_id128_get_machine.html).

Ordinary application reinstalls, repairs, uninstall/reinstall and separate state directories on the same OS installation retain this pseudonym. This is **not hardware attestation**: OS reinstallation, improperly cloned OS identities and a hostile administrator are explicit limitations. A machine pseudonym is restricted, account-linked data, not a claim of irreversible anonymization or independent hardware certification.

`quadrants-server-v1` has four local periods, 00–06 / 06–12 / 12–18 / 18–24, with exactly two planned slots (indices 1 and 2) per period, at least one hour apart. The Server fixes the time zone and seed for the shared machine identity. Changing a Client's account, token, connection profile, local time zone or installation state does not reset the central quota. Each `GrantRequest` carries the typed `schedule_slot` (local date, quadrant, index). No old hourly interval is accepted as an alternative schedule.

Central plan v1 fixes `timezone_database` to the bundled `tzdata` version `2026.5`, without using the host OS time-zone database. It is runtime-independent: use the 32-byte seed as the HMAC-SHA256 key and `<YYYY-MM-DD>:<quadrant>:<counter>` (UTF-8, counter starting at zero in each period) as the message; interpret the digest as an unsigned big-endian integer modulo the available seconds plus one. Available seconds exclude the 30-second test and 60-second end margin. Accept two offsets at least 3,600 seconds apart and sort them. The published fixed test vector protects compatibility across Client/Server runtime versions.

The provider reserves the machine/day/period/index atomically before issuing a grant. Simultaneous copies cannot obtain another attempt for the same slot, and failed/interrupted attempts do not free it. An identical request recovers the same grant; a duplicate from another installation receives `slot_already_reserved` without another accepted profile or measurement. This quota counts attempts, not individual metric records. Pending uploads reuse their existing grant and receipt chain; they do not consume another slot or run another test.

`machine_identity_required`, `schedule_update_required`, `machine_identity_changed`, `machine_privacy_not_ready`, `slot_not_due`, `slot_expired` and `slot_already_reserved` are stable refusal codes. The Server checks current legal/account/credential state independently of these limits. Client installation and pairing still do not start measurements.
