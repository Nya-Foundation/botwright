from __future__ import annotations

import uuid
from typing import Any, AsyncIterator

import discord
import pytest
import pytest_asyncio

from .branding import BOTWRIGHT_BANNER
from .client import TesterBot
from .config import BotwrightConfig
from .exceptions import BotwrightConfigError
from .runtime import (
    require_permissions,
    tester_channel_permissions,
    verify_environment,
)
from .session import TestSession


def _sanitize(name: str) -> str:
    safe = "".join(c if c.isalnum() else "-" for c in name).strip("-").lower()
    return safe[:60] or "test"


def _channel_name(prefix: str, test_name: str) -> str:
    suffix = uuid.uuid4().hex[:6]
    max_test_name = max(1, 100 - len(prefix) - len(suffix) - 1)
    return f"{prefix}{_sanitize(test_name)[:max_test_name]}-{suffix}"


def _line(request: pytest.FixtureRequest, message: str) -> None:
    reporter = request.config.pluginmanager.get_plugin("terminalreporter")
    if reporter is not None:
        reporter.write_line(f"[botwright] {message}")
    else:
        print(f"[botwright] {message}", flush=True)


def _botwright_marker(request: pytest.FixtureRequest) -> pytest.Mark | None:
    return request.node.get_closest_marker("botwright")


def _marker_value(request: pytest.FixtureRequest, name: str) -> Any:
    marker = _botwright_marker(request)
    if marker is None:
        return None
    return marker.kwargs.get(name)


def _call_failed(request: pytest.FixtureRequest) -> bool:
    report = getattr(request.node, "_botwright_report_call", None)
    return bool(report and report.failed)


def _node_default_timeout(
    request: pytest.FixtureRequest,
    botwright_config: BotwrightConfig,
) -> float:
    value = _marker_value(request, "timeout")
    if value is None:
        return botwright_config.default_timeout

    try:
        return float(value)
    except (TypeError, ValueError) as e:
        raise BotwrightConfigError(
            "botwright marker timeout must be a number"
        ) from e


def _node_channel_id(
    request: pytest.FixtureRequest,
    botwright_config: BotwrightConfig,
) -> int | None:
    value = _marker_value(request, "channel_id")
    if value is None:
        return botwright_config.channel_id

    try:
        return int(value)
    except (TypeError, ValueError) as e:
        raise BotwrightConfigError(
            "botwright marker channel_id must be an integer snowflake"
        ) from e


def _keep_channel(
    request: pytest.FixtureRequest,
    botwright_config: BotwrightConfig,
) -> bool:
    marker_value = _marker_value(request, "keep_channel")
    if marker_value is not None:
        return bool(marker_value)

    if botwright_config.keep_channels == "always":
        return True
    if botwright_config.keep_channels == "failed":
        return _call_failed(request)
    return False


def _should_keep_channel(
    request: pytest.FixtureRequest,
    botwright_config: BotwrightConfig,
) -> bool:
    try:
        return _keep_channel(request, botwright_config)
    except Exception as e:
        _line(
            request,
            f"failed to evaluate keep-channel policy; deleting channel: {e}",
        )
        return False


@pytest.fixture(scope="session")
def botwright_config(request: pytest.FixtureRequest) -> BotwrightConfig:
    reporter = request.config.pluginmanager.get_plugin("terminalreporter")
    if not request.config.getoption("--botwright-no-banner"):
        if reporter is not None:
            reporter.write_line(BOTWRIGHT_BANNER.rstrip())
        else:
            print(BOTWRIGHT_BANNER.rstrip(), flush=True)

    _line(request, "loading configuration from environment")
    config = BotwrightConfig.from_env(
        channel_id=request.config.getoption("--botwright-channel-id"),
        channel_prefix=request.config.getoption("--botwright-channel-prefix"),
        ready_timeout=request.config.getoption("--botwright-ready-timeout"),
        default_timeout=request.config.getoption("--botwright-timeout"),
        keep_channels=request.config.getoption("--botwright-keep-channels"),
    )
    _line(
        request,
        f"config loaded: guild_id={config.guild_id}, "
        f"target_bot_id={config.target_bot_id}, "
        f"channel_id={config.channel_id}, "
        f"channel_prefix={config.channel_prefix!r}, "
        f"default_timeout={config.default_timeout}, "
        f"keep_channels={config.keep_channels}",
    )
    return config


@pytest_asyncio.fixture(scope="session", loop_scope="session")
async def tester_bot(
    botwright_config: BotwrightConfig,
    request: pytest.FixtureRequest,
) -> AsyncIterator[TesterBot]:
    bot = TesterBot()
    _line(
        request,
        f"starting tester bot and waiting up to {botwright_config.ready_timeout}s for ready",
    )
    await bot.start_in_background(
        botwright_config.tester_token,
        timeout=botwright_config.ready_timeout,
        status=lambda message: _line(request, message),
    )
    if bot.user is None:
        raise BotwrightConfigError("Tester bot connected but bot.user is not available")
    _line(
        request,
        f"tester bot ready: user={bot.user} id={bot.user.id} "
        f"intents={bot.intents.value}",
    )
    try:
        yield bot
    finally:
        _line(request, "shutting down tester bot")
        await bot.shutdown()


@pytest_asyncio.fixture(loop_scope="session")
async def test_channel(
    tester_bot: TesterBot,
    botwright_config: BotwrightConfig,
    request: pytest.FixtureRequest,
) -> AsyncIterator[discord.TextChannel]:
    _line(request, f"verifying tester bot is in guild {botwright_config.guild_id}")
    configured_channel_id = _node_channel_id(request, botwright_config)
    env = await verify_environment(
        tester_bot,
        botwright_config,
        channel_id=configured_channel_id,
    )
    guild = env.guild
    tester_member = env.tester_member
    target_member = env.target_member
    _line(
        request,
        f"tester bot guild membership verified: guild={guild.name!r} ({guild.id})",
    )
    _line(
        request,
        f"target bot guild membership verified: user={target_member} id={target_member.id}",
    )

    created_channel = env.created_channel

    if created_channel:
        _line(request, "tester bot has guild permission: manage_channels")

        name = _channel_name(botwright_config.channel_prefix, request.node.name)
        _line(request, f"creating temporary channel #{name}")
        try:
            channel = await guild.create_text_channel(name=name)
        except discord.Forbidden as e:
            raise BotwrightConfigError(
                f"Tester bot was forbidden from creating text channels in guild {guild.id}"
            ) from e
    else:
        assert env.channel is not None
        channel = env.channel
        _line(
            request,
            f"using configured channel #{channel.name} ({channel.id}); "
            "Botwright will not delete it",
        )

    tester_permissions = channel.permissions_for(tester_member)
    required_tester_permissions = tester_channel_permissions(created_channel)
    require_permissions(
        tester_permissions,
        required_tester_permissions,
        f"#{channel.name}",
    )
    _line(
        request,
        "tester bot channel permissions verified: "
        f"{', '.join(required_tester_permissions)}",
    )

    target_channel_permissions = channel.permissions_for(target_member)
    require_permissions(
        target_channel_permissions,
        ("view_channel", "send_messages", "read_message_history"),
        f"target bot in #{channel.name}",
    )
    _line(
        request,
        "target bot channel permissions verified: "
        "view_channel, send_messages, read_message_history",
    )

    try:
        yield channel
    finally:
        if not created_channel:
            return

        if _should_keep_channel(request, botwright_config):
            _line(request, f"keeping temporary channel #{channel.name}")
            return

        try:
            _line(request, f"deleting temporary channel #{channel.name}")
            await channel.delete()
        except discord.HTTPException:
            _line(request, f"failed to delete temporary channel #{channel.name}")


@pytest_asyncio.fixture(loop_scope="session")
async def session(
    tester_bot: TesterBot,
    test_channel: discord.TextChannel,
    botwright_config: BotwrightConfig,
    request: pytest.FixtureRequest,
) -> TestSession:
    return TestSession(
        bot=tester_bot,
        channel=test_channel,
        target_bot_id=botwright_config.target_bot_id,
        default_timeout=_node_default_timeout(request, botwright_config),
    )
