# Security Policy

## Supported versions

| Version            | Supported |
| ------------------ | --------- |
| 0.x (latest minor) | Yes       |
| Older minors       | No        |

## Reporting a vulnerability

**Please do not open a public issue for security problems.**

Report privately through GitHub's
[private vulnerability reporting](https://docs.github.com/en/code-security/security-advisories/guidance-on-reporting-and-writing-information-about-vulnerabilities/privately-reporting-a-security-vulnerability)
on this repository ("Security" tab, "Report a vulnerability").

Please include:

- the affected component (`apps/api`, `apps/web`, `infra/docker`, `infra/terraform/...`) and
  the version or commit,
- a description of the issue and its impact,
- steps to reproduce, or a proof of concept,
- any suggested mitigation.

Do not include real credentials or other people's source code in a report. A reproduction that
uses the bundled sample repositories (`make demo`) or invented code is enough.

What to expect:

| Stage                                          | Target                                                               |
| ---------------------------------------------- | -------------------------------------------------------------------- |
| Acknowledgement                                | within 3 business days                                               |
| Initial assessment and severity                | within 7 business days                                               |
| Fix or mitigation for critical and high issues | within 30 days                                                       |
| Coordinated public disclosure                  | after a fix is released, credited to you unless you prefer otherwise |

## Safe harbour

We will not pursue or support legal action against people who find and report issues in good
faith under this policy: testing only against your own deployment (or the local stack from
`make up`), accessing no more data than needed to show the problem, not degrading a service
for others, and giving us reasonable time to fix before disclosing.

## Scope

In scope: the code in this repository and the infrastructure it provisions with its default
settings. The most important classes of issue for this project are:

- **Reading a secret.** Any way to obtain the value of an upstream secret or a client key from the API,
  the dashboard, logs, the call log, exports, error messages or results relayed to clients, after it was
  stored; or decrypting a ciphertext in another server's context.
- **Bypassing client policy.** Calling a tool a client's rules do not allow, passing arguments that break a
  constraint, seeing a tool in `tools/list` that the policy hides, or avoiding the rate limits and the audit
  record of a call.
- **Server-side request forgery through server URLs.** Making the gateway connect to an address its egress
  policy refuses (cloud metadata, link-local, private ranges that are not allow-listed), including through
  redirects, URL parsing tricks or DNS; and launching a stdio command that is not allow-listed.
- **Key or session forgery**, bypassing the cookie origin check, using a client key on the management API,
  and privilege escalation between the `viewer`, `operator` and `admin` roles.
- **Tampering with the audit log** by anyone who can use the application, or calls that leave no record.

Out of scope:

- **Content a viewer can already read.** Viewers see the call log, including recorded (redacted)
  arguments, by design.
- **What an upstream MCP server does.** The gateway enforces policy in front of a server; it cannot make
  a malicious server behave. A tool that returns hostile text is a prompt-injection concern for the agent.
- **A stdio server is code the gateway host runs.** Registering one is a code-execution grant that the
  operator makes by allow-listing its command.
- **DNS rebinding between the egress check and the connection** is a documented residual risk (see the
  threat model); network policy is the second layer.
- **The demo seed.** `make demo` creates well-known demo accounts and shared demo tokens; it refuses to run
  with `APP_ENV=production`.
- Findings that need a compromised host, a compromised AWS account or leaked deployment secrets.
- Denial of service through resource exhaustion of a deployment you operate yourself, and missing rate
  limits on routes that are already authenticated.

## Hardening checklist for operators

See [docs/architecture/security.md](docs/architecture/security.md).
