# -----------------------------------------------------------------------------
# Local environment on the Floci AWS emulator.
#
# The modules that build AWS run here unchanged; only the provider endpoints differ.
# `make up` applies this automatically (the compose `terraform` one-shot) before the API
# and the worker start, so upstream secrets are envelope-encrypted by a real KMS key and
# a Secrets Manager secret exists, exactly as on AWS. By hand, against a running emulator:
#
#   terraform -chdir=infra/terraform/envs/local-floci init
#   terraform -chdir=infra/terraform/envs/local-floci apply
#
# The database and the cache are containers in the compose stack, so the database,
# cache, network, edge and service modules are not used here.
# -----------------------------------------------------------------------------

module "kms" {
  source                  = "../../modules/kms"
  name_prefix             = var.name_prefix
  deletion_window_in_days = 7
  # The emulator does not report a rotation period back, which would show as a change on
  # every apply; AWS applies its 365-day default to a null period.
  rotation_period_in_days = null
}

# Generated secrets are an AWS-deployment concern; locally compose reads
# deploy/compose/.env (make env). Created here anyway so the module is exercised.
module "secrets" {
  source                  = "../../modules/secrets"
  name_prefix             = var.name_prefix
  secret_name             = "mcphub/local/app"
  kms_key_arn             = module.kms.key_arn
  recovery_window_in_days = 0
}
