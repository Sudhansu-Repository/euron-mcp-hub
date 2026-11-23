## What and why

<!-- One paragraph: the problem, and how this change solves it. Link the issue. -->

## How it was verified

- [ ] `make lint typecheck test`
- [ ] `make test-integration` (if the API, the gateway, policy, secrets, the worker or the database changed)
- [ ] `make e2e` (if a user flow, the web app or the infrastructure changed)
- [ ] `make tf-validate tf-lint tf-security` (if Terraform changed)

## Checklist

- [ ] Docs updated (`docs/`, the configuration reference) for any behavior or config change
- [ ] `make openapi` re-run if a route changed
- [ ] New migration instead of editing an applied one
- [ ] A new route has a role dependency, and a test shows a viewer and an anonymous caller are refused where they should be
- [ ] Nothing returns, logs or records a secret value or a client key; new log fields and audit text go through the scrubbers
- [ ] A change to the egress policy or to what the gateway may launch has a test for the refused case and an update to the threat model
- [ ] A changed policy rule, constraint or cache key has unit tests with worked examples
- [ ] No secrets, account ids, real emails or hostnames (`make sanitize` is clean)
- [ ] Security-relevant change? Described the threat and mitigation above
