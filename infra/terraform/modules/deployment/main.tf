# -----------------------------------------------------------------------------
# One complete MCPHub deployment: network, keys, data, cache and services.
#
#   https://<hostname>/            dashboard (web)
#   https://<hostname>/mcp         the MCP gateway (clients send a client API key)
#   https://<hostname>/api/v1/...  management API; reference at /docs; /metrics is not public
#   worker                         health checks, scheduled discovery and audit retention;
#                                  no inbound traffic, elected across tasks through Valkey
#
# The dashboard, the API and the gateway share one host name and one origin, so the session
# cookie is first-party and the API needs no CORS exceptions. envs/aws-dev and envs/aws-prod
# call this module with different sizes and safety switches; everything else is identical
# by construction.
#
# Fargate has no host to launch processes on for you, so stdio servers are disabled there
# (STDIO_ALLOWED_COMMANDS is empty): register streamable HTTP servers. Upstream secrets are
# encrypted with the deployment key (envelope encryption) and the roles may use it only with
# MCPHub's encryption context.
#
# First sign-in: the first account created becomes the instance administrator, and the
# first-run page in the dashboard will create it for whoever opens it first. Create the
# administrator right after the first deploy (`make aws-cli ARGS="user create ..."`),
# before sharing the URL.
# -----------------------------------------------------------------------------
data "aws_region" "current" {}
data "aws_caller_identity" "current" {}
data "aws_partition" "current" {}

locals {
  region   = data.aws_region.current.region
  site_url = "https://${var.hostname}"
  urls = {
    web     = local.site_url
    api     = "${local.site_url}/api/v1"
    gateway = "${local.site_url}/mcp"
    docs    = "${local.site_url}/docs"
  }
  images = { for k, url in module.ecr.repository_urls : k => "${url}:${var.image_tag}" }
}

# --- Foundation --------------------------------------------------------------

module "network" {
  source                     = "../network"
  name_prefix                = var.name_prefix
  cidr_block                 = var.vpc_cidr
  az_count                   = var.az_count
  single_nat_gateway         = var.single_nat_gateway
  enable_interface_endpoints = var.enable_interface_endpoints
  flow_log_retention_days    = var.flow_log_retention_days
  logs_kms_key_arn           = module.kms.key_arn
}

module "kms" {
  source                  = "../kms"
  name_prefix             = var.name_prefix
  deletion_window_in_days = var.kms_deletion_window_days
  admin_principal_arns    = var.kms_admin_principal_arns
}

module "secrets" {
  source                  = "../secrets"
  name_prefix             = var.name_prefix
  kms_key_arn             = module.kms.key_arn
  recovery_window_in_days = var.secret_recovery_window_days
}

module "database" {
  source                = "../database"
  name_prefix           = var.name_prefix
  vpc_id                = module.network.vpc_id
  subnet_ids            = module.network.private_subnet_ids
  kms_key_arn           = module.kms.key_arn
  instance_class        = var.db_instance_class
  allocated_storage     = var.db_allocated_storage
  max_allocated_storage = var.db_max_allocated_storage
  multi_az              = var.db_multi_az
  backup_retention_days = var.db_backup_retention_days
  deletion_protection   = var.deletion_protection
  skip_final_snapshot   = !var.deletion_protection
  monitoring_interval   = var.db_monitoring_interval
}

module "cache" {
  source                  = "../cache"
  name_prefix             = var.name_prefix
  vpc_id                  = module.network.vpc_id
  subnet_ids              = module.network.private_subnet_ids
  kms_key_arn             = module.kms.key_arn
  node_type               = var.cache_node_type
  replicas                = var.cache_replicas
  apply_immediately       = !var.deletion_protection
  recovery_window_in_days = var.secret_recovery_window_days
}

module "ecr" {
  source       = "../ecr"
  name_prefix  = var.name_prefix
  repositories = ["api", "web"]
  kms_key_arn  = module.kms.key_arn
  force_delete = !var.deletion_protection
}

# --- Edge --------------------------------------------------------------------

module "edge" {
  source               = "../edge"
  name_prefix          = var.name_prefix
  vpc_id               = module.network.vpc_id
  public_subnet_ids    = module.network.public_subnet_ids
  hostname             = var.hostname
  route53_zone_id      = var.route53_zone_id
  certificate_arn      = var.certificate_arn
  access_logs_bucket   = var.alb_access_logs_bucket
  idle_timeout_seconds = var.alb_idle_timeout_seconds
  enable_waf           = var.enable_waf
  waf_rate_limit       = var.waf_rate_limit
  deletion_protection  = var.deletion_protection
}

resource "aws_ecs_cluster" "this" {
  name = var.name_prefix
  setting {
    name  = "containerInsights"
    value = "enhanced"
  }
}

# --- Shared application configuration ----------------------------------------

locals {
  # Everything Settings.production_problems() insists on is set here: secrets from Secrets
  # Manager (and distinct), secure cookies, explicit CORS origins, KMS for upstream secrets,
  # an https gateway address and no emulator endpoint.
  app_environment = merge({
    APP_ENV      = "production"
    TZ           = "UTC"
    LOG_FORMAT   = "json"
    PRODUCT_NAME = var.product_name
    AWS_REGION   = local.region
    CORS_ORIGINS = local.site_url
    WEB_URL      = local.site_url
    API_URL      = local.site_url
    GATEWAY_URL  = "${local.site_url}/mcp"
    # No password in the environment: the app reads it from the RDS-managed secret for
    # each new connection, so a rotation needs no redeploy.
    DATABASE_URL        = "postgresql+asyncpg://${module.database.master_username}@${module.database.address}:${module.database.port}/${module.database.database_name}?ssl=require"
    DATABASE_SECRET_ARN = module.database.master_user_secret_arn
    COOKIE_SECURE       = "true"
    # Upstream secrets: ciphertext in Postgres, encrypted by the deployment key.
    SECRETS_BACKEND     = "kms"
    SECRETS_KMS_KEY_ID  = module.kms.key_arn
    SECRETS_NAME_PREFIX = "${var.name_prefix}/upstream"
    # Egress policy: public hosts are reachable, cloud metadata never, private networks
    # only where listed. No stdio servers on Fargate.
    UPSTREAM_ALLOWED_HOSTS = join(",", var.upstream_allowed_hosts)
    STDIO_ALLOWED_COMMANDS = ""
    AUDIT_RETENTION_DAYS   = tostring(var.audit_retention_days)
    # Trust X-Forwarded-For only from inside the VPC (the load balancer), so the per-address
    # sign-in limit sees the real client and not whatever a client claims to be.
    FORWARDED_ALLOW_IPS = module.network.vpc_cidr_block
  }, var.extra_environment)

  app_secrets = concat(
    [for k in module.secrets.keys : { name = k, valueFrom = "${module.secrets.secret_arn}:${k}::" }],
    [{ name = "REDIS_URL", valueFrom = "${module.cache.url_secret_arn}:REDIS_URL::" }],
  )
}

# --- Task roles (least privilege, one per application) ------------------------

data "aws_iam_policy_document" "common" {
  statement {
    sid       = "DatabasePassword"
    actions   = ["secretsmanager:GetSecretValue"]
    resources = [module.database.master_user_secret_arn]
  }
  statement {
    sid       = "ReadSecretsViaSecretsManager"
    actions   = ["kms:Decrypt"]
    resources = [module.kms.key_arn]
    condition {
      test     = "StringEquals"
      variable = "kms:ViaService"
      values   = ["secretsmanager.${local.region}.amazonaws.com"]
    }
  }
}

# Upstream secrets. The deployment key encrypts them directly, and the key policy lets a
# role use it only with MCPHub's encryption context (the server and the secret a value
# belongs to), so a role cannot be turned into a general-purpose decryption oracle. The
# Secrets Manager backend, when an operator selects it, is limited to this deployment's
# secret names.
data "aws_iam_policy_document" "vault" {
  statement {
    sid       = "UpstreamSecretsKey"
    actions   = ["kms:Encrypt", "kms:Decrypt"]
    resources = [module.kms.key_arn]
    condition {
      test     = "Null"
      variable = "kms:EncryptionContext:mcphub:server"
      values   = ["false"]
    }
  }
  statement {
    sid       = "UpstreamSecretsKeyDescribe"
    actions   = ["kms:DescribeKey"]
    resources = [module.kms.key_arn]
  }
  statement {
    sid = "UpstreamSecretsInSecretsManager"
    actions = [
      "secretsmanager:CreateSecret", "secretsmanager:PutSecretValue", "secretsmanager:GetSecretValue",
      "secretsmanager:DeleteSecret", "secretsmanager:RestoreSecret", "secretsmanager:TagResource",
    ]
    resources = ["arn:${data.aws_partition.current.partition}:secretsmanager:${local.region}:${data.aws_caller_identity.current.account_id}:secret:${var.name_prefix}/upstream/*"]
  }
  statement {
    sid       = "ListSecretsForHealthChecks"
    actions   = ["secretsmanager:ListSecrets"]
    resources = ["*"]
  }
}

# The API registers servers, stores their secrets and relays tool calls.
data "aws_iam_policy_document" "api" {
  source_policy_documents = [
    data.aws_iam_policy_document.common.json,
    data.aws_iam_policy_document.vault.json,
  ]
}

# The worker connects to every server to check it, so it reads the same secrets.
data "aws_iam_policy_document" "worker" {
  source_policy_documents = [
    data.aws_iam_policy_document.common.json,
    data.aws_iam_policy_document.vault.json,
  ]
}

# One-off commands (migrate, user create, discover, demo seed) touch the database and the secrets.
data "aws_iam_policy_document" "cli" {
  source_policy_documents = [
    data.aws_iam_policy_document.common.json,
    data.aws_iam_policy_document.vault.json,
  ]
}

locals {
  python_health = ["CMD-SHELL", "python -c \"import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/livez', timeout=3)\""]
  worker_health = ["CMD-SHELL", "python -c \"import urllib.request; urllib.request.urlopen('http://127.0.0.1:${local.worker_metrics_port}/metrics', timeout=3)\""]
  # Same value as WORKER_METRICS_PORT in the compose stack, so dashboards read one number.
  worker_metrics_port = 9100
}

# --- Services ----------------------------------------------------------------

# The API owns the schema: it migrates under an advisory lock on boot, so any number of
# tasks can start together and the migrations still run once.
module "api" {
  source                   = "../service"
  name_prefix              = var.name_prefix
  name                     = "api"
  image                    = local.images.api
  environment              = merge(local.app_environment, { MIGRATE_ON_BOOT = tostring(var.migrate_on_boot) })
  secrets                  = local.app_secrets
  cluster_arn              = aws_ecs_cluster.this.arn
  vpc_id                   = module.network.vpc_id
  subnet_ids               = module.network.private_subnet_ids
  listener_arn             = module.edge.https_listener_arn
  lb_security_group_id     = module.edge.security_group_id
  listener_priority        = 100
  path_patterns            = ["/api/*", "/mcp", "/docs", "/openapi.json", "/livez"]
  health_check_path        = "/livez"
  connect_to_database      = true
  db_security_group_id     = module.database.security_group_id
  db_port                  = module.database.port
  connect_to_cache         = true
  cache_security_group_id  = module.cache.security_group_id
  kms_key_arn              = module.kms.key_arn
  has_task_policy          = true
  task_policy_json         = data.aws_iam_policy_document.api.json
  cpu                      = var.api_cpu
  memory                   = var.api_memory
  min_count                = var.api_min_count
  max_count                = var.api_max_count
  log_retention_days       = var.log_retention_days
  logs_kms_key_arn         = module.kms.key_arn
  container_health_command = local.python_health
}

module "worker" {
  source      = "../service"
  name_prefix = var.name_prefix
  name        = "worker"
  image       = local.images.api
  command     = ["python", "-m", "mcphub.worker"]
  environment = merge(local.app_environment, {
    MIGRATE_ON_BOOT     = "false"
    WORKER_METRICS_PORT = tostring(local.worker_metrics_port)
  })
  container_health_command = local.worker_health
  # On SIGTERM the worker finishes its round, releases the leader lease and exits; the stop
  # timeout leaves room for a round that is still checking servers.
  stop_timeout            = 60
  secrets                 = local.app_secrets
  attach_to_load_balancer = false
  cluster_arn             = aws_ecs_cluster.this.arn
  vpc_id                  = module.network.vpc_id
  subnet_ids              = module.network.private_subnet_ids
  connect_to_database     = true
  db_security_group_id    = module.database.security_group_id
  db_port                 = module.database.port
  connect_to_cache        = true
  cache_security_group_id = module.cache.security_group_id
  kms_key_arn             = module.kms.key_arn
  has_task_policy         = true
  task_policy_json        = data.aws_iam_policy_document.worker.json
  cpu                     = var.worker_cpu
  memory                  = var.worker_memory
  min_count               = var.worker_min_count
  max_count               = var.worker_max_count
  log_retention_days      = var.log_retention_days
  logs_kms_key_arn        = module.kms.key_arn
}

# One-off tasks on the API image: migrations, accounts, discovery (make aws-cli).
# Nothing here needs a terminal: pass every argument on the command line.
module "cli" {
  source                  = "../service"
  name_prefix             = var.name_prefix
  name                    = "cli"
  image                   = local.images.api
  command                 = ["mcphub", "--help"]
  environment             = merge(local.app_environment, { MIGRATE_ON_BOOT = "false" })
  secrets                 = local.app_secrets
  create_service          = false
  cluster_arn             = aws_ecs_cluster.this.arn
  vpc_id                  = module.network.vpc_id
  subnet_ids              = module.network.private_subnet_ids
  connect_to_database     = true
  db_security_group_id    = module.database.security_group_id
  db_port                 = module.database.port
  connect_to_cache        = true
  cache_security_group_id = module.cache.security_group_id
  kms_key_arn             = module.kms.key_arn
  has_task_policy         = true
  task_policy_json        = data.aws_iam_policy_document.cli.json
  cpu                     = 512
  memory                  = 1024
  log_retention_days      = var.log_retention_days
  logs_kms_key_arn        = module.kms.key_arn
}

# The dashboard: a Next.js server that reads API_URL and PRODUCT_NAME when it starts
# (/env.js), so one image serves every environment. It claims every path the API does not.
module "web" {
  source               = "../service"
  name_prefix          = var.name_prefix
  name                 = "web"
  image                = local.images.web
  environment          = { API_URL = local.site_url, PRODUCT_NAME = var.product_name, PORT = "8080", HOSTNAME = "0.0.0.0" }
  cluster_arn          = aws_ecs_cluster.this.arn
  vpc_id               = module.network.vpc_id
  subnet_ids           = module.network.private_subnet_ids
  listener_arn         = module.edge.https_listener_arn
  lb_security_group_id = module.edge.security_group_id
  listener_priority    = 900
  path_patterns        = ["/*"]
  health_check_path    = "/env.js"
  kms_key_arn          = module.kms.key_arn
  cpu                  = var.web_cpu
  memory               = var.web_memory
  min_count            = var.web_min_count
  max_count            = var.web_max_count
  log_retention_days   = var.log_retention_days
  logs_kms_key_arn     = module.kms.key_arn
}

# --- Observability -----------------------------------------------------------

module "observability" {
  source                     = "../observability"
  name_prefix                = var.name_prefix
  kms_key_arn                = module.kms.key_arn
  alarm_email                = var.alarm_email
  alb_arn_suffix             = module.edge.arn_suffix
  ecs_cluster_name           = aws_ecs_cluster.this.name
  db_instance_identifier     = module.database.instance_identifier
  db_max_connections         = var.db_max_connections
  cache_replication_group_id = module.cache.replication_group_id
  cache_node_count           = module.cache.node_count
  services = {
    api    = module.api.service_name
    worker = module.worker.service_name
    web    = module.web.service_name
  }
  target_groups = {
    api = module.api.target_group_arn_suffix
    web = module.web.target_group_arn_suffix
  }
}
