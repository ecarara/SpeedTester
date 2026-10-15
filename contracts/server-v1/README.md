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
