# ADR 0006: Develop against an AWS emulator (Floci), provisioned by the production Terraform

## Status

Accepted.

## Context

In production MCPHub depends on KMS (upstream secrets), Secrets Manager, RDS and ElastiCache. Local development that swaps KMS for a different mechanism leaves the path that protects every credential untested until it meets a real account: encryption contexts, key aliases and the Terraform itself.

## Decision

- `make up` runs the Floci emulator (`floci/floci:2.3.0`, MIT licence) next to Postgres, Valkey and the application images.
- A one-shot Terraform container applies `infra/terraform/envs/local-floci` against it before the API and the worker start. That environment uses the same `kms` and `secrets` modules as production, with only the endpoint and a few emulator switches changed. The database and cache are compose containers, so the other modules are not used locally.
- The API and the worker run with `SECRETS_BACKEND=kms` and `SECRETS_KMS_KEY_ID=alias/mcphub-local`, pointed at the emulator with `AWS_ENDPOINT_URL`. The application has no emulator-specific branches.
- Terraform state for the local environment lives in a volume and is wiped with the emulator by `make down`.
- The integration suite creates its own key and uniquely named secrets on a throwaway emulator (`scripts/test-deps.sh`, ports 5455, 6415 and 4615).

## Consequences

- The emulator is a dependency to track and can differ from AWS in corners; the integration tests pin the behaviour the application relies on, and the real Terraform is validated, linted and scanned.
- The first `make up` takes minutes while Terraform applies and images build.

## Alternatives considered

Mocking boto3 (tests the mock); localstack (a different licence and a heavier footprint); developing against a real account (needs one, and costs money)..
