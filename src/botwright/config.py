from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Literal
from .exceptions import BotwrightConfigError

KeepChannels = Literal["never", "failed", "always"]


@dataclass(frozen=True)
class BotwrightConfig:
    tester_token: str
    guild_id: int
    target_bot_id: int
    channel_id: int | None = None
    channel_prefix: str = "botwright-"
    ready_timeout: float = 30.0
    default_timeout: float = 10.0
    keep_channels: KeepChannels = "never"

    @classmethod
    def from_env(
        cls,
        *,
        channel_id: int | None = None,
        channel_prefix: str | None = None,
        ready_timeout: float | None = None,
        default_timeout: float | None = None,
        keep_channels: KeepChannels | None = None,
    ) -> "BotwrightConfig":
        token = os.getenv("BOTWRIGHT_TESTER_TOKEN")
        guild = os.getenv("BOTWRIGHT_GUILD_ID")
        target = os.getenv("BOTWRIGHT_TARGET_BOT_ID")

        missing = [
            name
            for name, value in (
                ("BOTWRIGHT_TESTER_TOKEN", token),
                ("BOTWRIGHT_GUILD_ID", guild),
                ("BOTWRIGHT_TARGET_BOT_ID", target),
            )
            if not value
        ]
        if missing:
            raise BotwrightConfigError(
                f"Missing required environment variables: {', '.join(missing)}"
            )

        try:
            guild_id = int(guild)  # type: ignore[arg-type]
            target_id = int(target)  # type: ignore[arg-type]
            resolved_channel_id = _int_setting(
                "BOTWRIGHT_CHANNEL_ID",
                override=channel_id,
            )
            resolved_ready_timeout = _float_setting(
                "BOTWRIGHT_READY_TIMEOUT",
                "30",
                override=ready_timeout,
            )
            resolved_default_timeout = _float_setting(
                "BOTWRIGHT_DEFAULT_TIMEOUT",
                "10",
                override=default_timeout,
            )
        except ValueError as e:
            raise BotwrightConfigError(
                "BOTWRIGHT_GUILD_ID, BOTWRIGHT_TARGET_BOT_ID, and BOTWRIGHT_CHANNEL_ID "
                "must be integer snowflakes; "
                "BOTWRIGHT_READY_TIMEOUT and BOTWRIGHT_DEFAULT_TIMEOUT must be numbers"
            ) from e

        resolved_keep_channels = keep_channels or os.getenv(
            "BOTWRIGHT_KEEP_CHANNELS",
            "never",
        )
        if resolved_keep_channels not in ("never", "failed", "always"):
            raise BotwrightConfigError(
                "BOTWRIGHT_KEEP_CHANNELS must be one of: never, failed, always"
            )

        return cls(
            tester_token=token,  # type: ignore[arg-type]
            guild_id=guild_id,
            target_bot_id=target_id,
            channel_id=resolved_channel_id,
            channel_prefix=channel_prefix or os.getenv("BOTWRIGHT_CHANNEL_PREFIX", "botwright-"),
            ready_timeout=resolved_ready_timeout,
            default_timeout=resolved_default_timeout,
            keep_channels=resolved_keep_channels,
        )


def _int_setting(env_name: str, *, override: int | None) -> int | None:
    if override is not None:
        return override

    value = os.getenv(env_name)
    if value is None or value == "":
        return None

    return int(value)


def _float_setting(
    env_name: str,
    default: str,
    *,
    override: float | None,
) -> float:
    if override is not None:
        return override
    return float(os.getenv(env_name, default))
