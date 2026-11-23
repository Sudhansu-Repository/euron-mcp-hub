# Deploy to AWS

One Terraform deployment module builds everything; `aws-dev` and `aws-prod` only choose sizes and
safety switches.

| Resource         | aws-dev                                                             | aws-prod                                                 |
| ---------------- | ------------------------------------------------------------------- | -------------------------------------------------------- |
| Network          | 2 zones, one NAT gateway                                            | 3 zones, NAT per zone, KMS and Secrets Manager endpoints |
| Database         | RDS PostgreSQL 16, single zone, 3 days of backups                   | Multi-AZ, 14 days, deletion protection                   |
| Cache            | ElastiCache for Valkey, no replica                                  | one replica, automatic failover                          |
| Compute          | ECS Fargate: api, worker, web                                       | same, more tasks, autoscaling                            |
| Edge             | ALB with HTTPS                                                      | ALB with HTTPS and a WAF                                 |
| Keys and secrets | one KMS key (rotation on), generated app secrets in Secrets Manager | same, longer recovery windows                            |
| Observability    | CloudWatch logs, alarms to SNS, a dashboard                         | same, one year of logs                                   |

One host name serves the dashboard (`/`), the API (`/api/v1`), the docs and the gateway (`/mcp`), so the
session cookie is first-party. `/metrics` is not routed. stdio servers are disabled on Fargate: register
streamable HTTP servers.

## Prerequisites

Terraform 1.10 or newer, Docker with buildx, the AWS CLI, credentials for the target account, and a host name
(a Route 53 zone, or an issued ACM certificate you validate yourself).

## Deploy

```bash
cp infra/terraform/envs/aws-dev/terraform.tfvars.example infra/terraform/envs/aws-dev/terraform.tfvars
# edit: hostname, route53_zone_id (or certificate_arn), alarm_email
make aws-plan   ENV=aws-dev        # optional: review the plan
make aws-deploy ENV=aws-dev        # registries, arm64 images, infrastructure, rollout
```

`aws-deploy` applies the registries first, builds and pushes the images, applies everything else with the image
tag (the git commit) and waits for the services to become stable. Migrations run when the first API task starts,
under an advisory lock.

## First sign-in

Create the administrator before sharing the URL, as a one-off ECS task:

```bash
make aws-cli ENV=aws-dev ARGS="user create --email you@example.com --name 'You' --role admin --password 'a-long-passphrase'"
```

Then sign in, register a server and create a client key.

## Reaching servers inside your VPC

The gateway refuses private addresses by default. List the hosts it may reach in `upstream_allowed_hosts`
(for example `["*.internal.example.com"]`) and make sure the ECS security group may connect to them. Cloud
metadata addresses are never reachable.

## State and teardown

Copy `backend.tf.example` to `backend.tf` for remote state in a private, versioned S3 bucket (state contains the
generated secrets). `terraform destroy` in the environment removes everything except what has deletion
protection (production) or a recovery window.
