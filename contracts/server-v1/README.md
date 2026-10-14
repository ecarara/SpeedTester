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

This is the first integration foundation. Headless pairing, automatic renewal, the end-user installer and public comparison are subsequent deliveries. The existing standalone collector is unaffected.
