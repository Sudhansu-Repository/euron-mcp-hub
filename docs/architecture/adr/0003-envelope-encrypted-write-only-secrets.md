# ADR 0003: Upstream secrets are write-only and envelope-encrypted with KMS, bound to their server

## Status

Accepted.

## Context

The gateway has to present credentials to upstream servers, so it has to be able to recover them. Storing them as plaintext, or encrypting them with a key sitting next to the ciphertext, makes a database dump a credential dump. Showing them again in the UI turns every viewer into a path to the secret.

## Decision

- A value is encrypted by AWS KMS (on AWS and on Floci) with an **encryption context** naming the server and the secret. A ciphertext copied into another row does not decrypt. The database holds only ciphertext.
- Alternatively one Secrets Manager secret per value (the database keeps the ARN), or, for laptops, AES-256-GCM under a key from the environment with associated data naming the secret. Each stored secret records its backend, so switching the setting does not strand existing values.
- No endpoint returns a value. The dashboard lists names, kinds and versions, and replacing a secret is the only way to change one.
- Plaintext lives in memory for the life of an upstream connection and is masked in logs, audit rows and relayed results.
- IAM policies tie the task roles to this context and to this deployment's secret names.

## Consequences

- Every connection opening costs a KMS decrypt per secret (cached for as long as the connection lives).
- A KMS outage stops new upstream connections (existing ones keep working); the error says the secret store is unavailable.
- Operators cannot recover a lost value: they set a new one.

## Alternatives considered

A single application-wide encryption key (one leak exposes everything, no per-secret audit trail in CloudTrail); showing secrets masked with a reveal button (a path for any viewer to exfiltrate); a vault server such as HashiCorp Vault (another service to run, no advantage over KMS here)..
