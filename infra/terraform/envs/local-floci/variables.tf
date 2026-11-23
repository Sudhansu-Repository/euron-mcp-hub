variable "endpoint" {
  description = "Emulator endpoint. http://localhost:4615 from the host, http://floci:4566 inside compose."
  type        = string
  default     = "http://localhost:4615"
}

variable "name_prefix" {
  description = "Must match SECRETS_KMS_KEY_ID (alias/<name_prefix>) in deploy/compose/compose.floci.yaml."
  type        = string
  default     = "mcphub-local"
}
