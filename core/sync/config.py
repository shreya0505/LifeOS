"""Sync configuration loaded from environment variables."""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path


class SyncConfigError(ValueError):
    """Raised when sync is enabled but required settings are missing."""


def _truthy(value: str | None) -> bool:
    return (value or "").strip().lower() in {"1", "true", "yes", "on"}


def _load_dotenv_values() -> dict[str, str]:
    env_path = Path(__file__).resolve().parents[2] / ".env"
    if not env_path.exists():
        return {}
    values: dict[str, str] = {}
    for raw_line in env_path.read_text().splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key:
            values[key] = value
    return values


def _merged_env(environ: dict[str, str] | None) -> dict[str, str]:
    if environ is not None:
        return dict(environ)
    values = _load_dotenv_values()
    values.update(os.environ)
    return values


@dataclass(frozen=True)
class SyncConfig:
    enabled: bool
    provider: str
    device_name: str
    bucket: str
    prefix: str
    endpoint: str
    region: str
    access_key_id: str
    secret_access_key: str
    encryption_passphrase: str
    auto_enabled: bool
    interval_seconds: int
    ui_poll_seconds: int
    show_prompts: bool


def load_sync_config(environ: dict[str, str] | None = None) -> SyncConfig:
    env = _merged_env(environ)
    enabled = _truthy(env.get("SYNC_ENABLED"))
    auto_enabled = _truthy(env.get("SYNC_AUTO_ENABLED"))
    provider = (env.get("SYNC_PROVIDER") or "r2").strip().lower()
    account_id = (env.get("R2_ACCOUNT_ID") or "").strip()
    endpoint = (env.get("R2_ENDPOINT") or "").strip()
    if not endpoint and account_id:
        endpoint = f"https://{account_id}.r2.cloudflarestorage.com"

    config = SyncConfig(
        enabled=enabled,
        provider=provider,
        device_name=(env.get("SYNC_DEVICE_NAME") or "").strip(),
        bucket=(env.get("R2_BUCKET") or "").strip(),
        prefix=(env.get("R2_PREFIX") or "lifeos/prod").strip().strip("/"),
        endpoint=endpoint,
        region=(env.get("R2_REGION") or "auto").strip(),
        access_key_id=(env.get("R2_ACCESS_KEY_ID") or "").strip(),
        secret_access_key=(env.get("R2_SECRET_ACCESS_KEY") or "").strip(),
        encryption_passphrase=env.get("SYNC_ENCRYPTION_PASSPHRASE") or "",
        auto_enabled=auto_enabled,
        interval_seconds=int(env.get("SYNC_INTERVAL_SECONDS") or "0"),
        ui_poll_seconds=max(5, int(env.get("SYNC_UI_POLL_SECONDS") or "60")),
        show_prompts=not _truthy(env.get("SYNC_HIDE_PROMPTS")),
    )
    validate_sync_config(config)
    return config


def validate_sync_config(config: SyncConfig) -> None:
    if not config.enabled:
        return
    if config.provider != "r2":
        raise SyncConfigError("Only SYNC_PROVIDER=r2 is supported.")
    missing = []
    for field in (
        "device_name",
        "bucket",
        "prefix",
        "endpoint",
        "access_key_id",
        "secret_access_key",
        "encryption_passphrase",
    ):
        if not getattr(config, field):
            missing.append(field)
    if missing:
        names = ", ".join(missing)
        raise SyncConfigError(f"Sync is enabled but missing: {names}.")
    if len(config.encryption_passphrase) < 24:
        raise SyncConfigError("SYNC_ENCRYPTION_PASSPHRASE must be at least 24 characters.")
