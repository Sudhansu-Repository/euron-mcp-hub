"""boto3 clients configured the same way for AWS and for the local emulator.

`AWS_ENDPOINT_URL` (set only for the emulator) is the one difference; everything else is
identical, which is the point of running against an emulator.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import boto3
from botocore.config import Config

from mcphub.core.config import Settings

if TYPE_CHECKING:
    from mypy_boto3_kms import KMSClient
    from mypy_boto3_secretsmanager import SecretsManagerClient


def _config(settings: Settings) -> Config:
    return Config(
        region_name=settings.aws_region,
        retries={"max_attempts": 5, "mode": "standard"},
        connect_timeout=5,
        read_timeout=15,
    )


def kms_client(settings: Settings) -> KMSClient:
    return boto3.client(
        "kms", endpoint_url=settings.aws_endpoint_url or None, config=_config(settings)
    )


def secrets_client(settings: Settings) -> SecretsManagerClient:
    return boto3.client(
        "secretsmanager", endpoint_url=settings.aws_endpoint_url or None, config=_config(settings)
    )
