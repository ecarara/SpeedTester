# Minimal Client operating-system metadata

`client-environment-v1` is an additive capability advertised by Server discovery. Older Servers remain supported: the Client does not send this record when the capability is absent. Existing measurement, profile and pairing schemas are unchanged.

After explicit acceptance and pairing, the Client may POST `/api/v1/client-environment` using the same revocable access token and DPoP proof. The request is signed by its measurement key in the `client-environment-v1` domain. Its strict `EnvironmentReport` contains an event ID, Client ID, reporting time and exactly four OS fields: system family, distribution ID, distribution version and architecture. Unknown values remain absent or `other`. The collector does not run uname or read hostname, account name, serial numbers, MAC addresses, environment variables or personal files. Linux distribution information is restricted to ID and VERSION_ID from the standard OS release metadata.

The Server returns a signed `EnvironmentReceipt` in the `environment-receipt-v1` domain, bound to the Client, event ID and payload digest. A wrong receipt or rejection preserves the same pending event in encrypted local state for an idempotent retry. Successful identical reports are not resent. A changed OS description creates a new immutable event; it does not rewrite earlier measurements. This is self-reported installation context, not hardware attestation or independent proof of the operating system.

The Server applies the same current-consent, account and installation gates before storing this data. No measurement grant or runner is invoked to report OS metadata. The inventory of transmitted data is available from the public Server `/data` page, alongside the applicable terms and privacy policy.
