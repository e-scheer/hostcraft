"""S3-compatible upload for off-site backup sync.

Works with AWS S3, Backblaze B2 (S3 API), Wasabi, MinIO, DigitalOcean Spaces,
OVH Object Storage — anything that speaks the S3 API.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING

import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError

if TYPE_CHECKING:
    from .models import BackupDestination

logger = logging.getLogger(__name__)


class StorageError(RuntimeError):
    """Wraps any underlying boto/network failure with a user-facing message."""


def _client(dest: "BackupDestination"):
    config = Config(
        signature_version="s3v4",
        retries={"max_attempts": 3, "mode": "standard"},
        # Path-style URLs are needed for many S3-compatibles (B2, MinIO).
        s3={"addressing_style": "path"},
    )
    return boto3.client(
        "s3",
        endpoint_url=dest.endpoint_url or None,
        region_name=dest.region or "us-east-1",
        aws_access_key_id=dest.access_key,
        aws_secret_access_key=dest.secret_key,
        config=config,
    )


def _key(dest: "BackupDestination", filename: str) -> str:
    prefix = (dest.prefix or "").strip("/")
    return f"{prefix}/{filename}" if prefix else filename


def test_connection(dest: "BackupDestination") -> None:
    """Probe the bucket: list one object. Raises StorageError on any problem."""
    try:
        client = _client(dest)
        client.list_objects_v2(Bucket=dest.bucket, MaxKeys=1)
    except ClientError as exc:
        code = exc.response.get("Error", {}).get("Code", "Unknown")
        msg = exc.response.get("Error", {}).get("Message", str(exc))
        raise StorageError(f"{code}: {msg}") from exc
    except BotoCoreError as exc:
        raise StorageError(str(exc)) from exc


def upload(dest: "BackupDestination", local_path: Path) -> str:
    """Upload `local_path` to the destination, return the remote key."""
    if not local_path.is_file():
        raise StorageError(f"Local file missing: {local_path}")
    key = _key(dest, local_path.name)
    try:
        client = _client(dest)
        # `upload_file` does multipart automatically over ~8 MiB threshold,
        # so we don't need to special-case big tarballs.
        client.upload_file(str(local_path), dest.bucket, key)
    except ClientError as exc:
        code = exc.response.get("Error", {}).get("Code", "Unknown")
        msg = exc.response.get("Error", {}).get("Message", str(exc))
        raise StorageError(f"{code}: {msg}") from exc
    except BotoCoreError as exc:
        raise StorageError(str(exc)) from exc
    return key
