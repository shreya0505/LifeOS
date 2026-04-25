"""Object-store adapters used by sync."""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Protocol

from core.sync.config import SyncConfig

logger = logging.getLogger(__name__)


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
        payload = self.objects.get(key)
        logger.info(
            "sync.store.memory.get key=%s hit=%s bytes=%s",
            key,
            payload is not None,
            len(payload) if payload else 0,
        )
        return payload

    async def put_bytes(self, key: str, data: bytes, content_type: str = "application/octet-stream") -> None:
        self.objects[key] = data
        logger.info("sync.store.memory.put key=%s bytes=%s content_type=%s", key, len(data), content_type)

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
        logger.info(
            "sync.store.r2.init bucket=%s prefix=%s endpoint=%s region=%s",
            self._bucket,
            self._prefix,
            config.endpoint,
            config.region,
        )
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
            full_key = self._key(key)
            logger.info("sync.store.r2.get.start bucket=%s key=%s", self._bucket, full_key)
            try:
                response = self._client.get_object(Bucket=self._bucket, Key=full_key)
            except Exception as exc:
                code = getattr(exc, "response", {}).get("Error", {}).get("Code")
                if code in {"NoSuchKey", "404", "NotFound"}:
                    logger.info("sync.store.r2.get.miss bucket=%s key=%s code=%s", self._bucket, full_key, code)
                    return None
                logger.exception("sync.store.r2.get.error bucket=%s key=%s", self._bucket, full_key)
                raise
            payload = response["Body"].read()
            logger.info("sync.store.r2.get.ok bucket=%s key=%s bytes=%s", self._bucket, full_key, len(payload))
            return payload

        return await asyncio.to_thread(_get)

    async def put_bytes(self, key: str, data: bytes, content_type: str = "application/octet-stream") -> None:
        def _put() -> None:
            full_key = self._key(key)
            logger.info(
                "sync.store.r2.put.start bucket=%s key=%s bytes=%s content_type=%s",
                self._bucket,
                full_key,
                len(data),
                content_type,
            )
            self._client.put_object(
                Bucket=self._bucket,
                Key=full_key,
                Body=data,
                ContentType=content_type,
            )
            logger.info("sync.store.r2.put.ok bucket=%s key=%s bytes=%s", self._bucket, full_key, len(data))

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
