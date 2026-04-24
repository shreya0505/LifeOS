"""Object-store adapters used by sync."""

from __future__ import annotations

import asyncio
import json
from typing import Protocol

from core.sync.config import SyncConfig


class ObjectStore(Protocol):
    async def get_bytes(self, key: str) -> bytes | None: ...
    async def put_bytes(self, key: str, data: bytes, content_type: str = "application/octet-stream") -> None: ...

    async def get_json(self, key: str) -> dict | None:
        payload = await self.get_bytes(key)
        if payload is None:
            return None
        return json.loads(payload.decode("utf-8"))

    async def put_json(self, key: str, data: dict) -> None:
        await self.put_bytes(
            key,
            json.dumps(data, sort_keys=True, separators=(",", ":")).encode("utf-8"),
            "application/json",
        )


class MemoryObjectStore:
    """In-memory object store for tests."""

    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}

    async def get_bytes(self, key: str) -> bytes | None:
        return self.objects.get(key)

    async def put_bytes(self, key: str, data: bytes, content_type: str = "application/octet-stream") -> None:
        self.objects[key] = data

    async def get_json(self, key: str) -> dict | None:
        payload = await self.get_bytes(key)
        if payload is None:
            return None
        return json.loads(payload.decode("utf-8"))

    async def put_json(self, key: str, data: dict) -> None:
        await self.put_bytes(
            key,
            json.dumps(data, sort_keys=True, separators=(",", ":")).encode("utf-8"),
            "application/json",
        )


class R2ObjectStore:
    """Cloudflare R2 adapter using the S3-compatible API."""

    def __init__(self, config: SyncConfig) -> None:
        import boto3

        self._bucket = config.bucket
        self._prefix = config.prefix.strip("/")
        self._client = boto3.client(
            "s3",
            endpoint_url=config.endpoint,
            aws_access_key_id=config.access_key_id,
            aws_secret_access_key=config.secret_access_key,
            region_name=config.region,
        )

    def _key(self, key: str) -> str:
        key = key.strip("/")
        return f"{self._prefix}/{key}" if self._prefix else key

    async def get_bytes(self, key: str) -> bytes | None:
        def _get() -> bytes | None:
            try:
                response = self._client.get_object(Bucket=self._bucket, Key=self._key(key))
            except Exception as exc:
                code = getattr(exc, "response", {}).get("Error", {}).get("Code")
                if code in {"NoSuchKey", "404", "NotFound"}:
                    return None
                raise
            return response["Body"].read()

        return await asyncio.to_thread(_get)

    async def put_bytes(self, key: str, data: bytes, content_type: str = "application/octet-stream") -> None:
        def _put() -> None:
            self._client.put_object(
                Bucket=self._bucket,
                Key=self._key(key),
                Body=data,
                ContentType=content_type,
            )

        await asyncio.to_thread(_put)

    async def get_json(self, key: str) -> dict | None:
        payload = await self.get_bytes(key)
        if payload is None:
            return None
        return json.loads(payload.decode("utf-8"))

    async def put_json(self, key: str, data: dict) -> None:
        await self.put_bytes(
            key,
            json.dumps(data, sort_keys=True, separators=(",", ":")).encode("utf-8"),
            "application/json",
        )


def build_store(config: SyncConfig) -> ObjectStore:
    return R2ObjectStore(config)
