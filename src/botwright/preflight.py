from __future__ import annotations

from collections.abc import Callable

from .client import TesterBot
from .config import BotwrightConfig
from .exceptions import BotwrightConfigError
from .runtime import (
    tester_channel_permissions,
    verify_environment,
)

Emit = Callable[[str], None]


async def run_preflight(config: BotwrightConfig, emit: Emit) -> None:
    bot = TesterBot()
    emit(f"starting tester bot; ready timeout={config.ready_timeout}s")
    await bot.start_in_background(
        config.tester_token,
        timeout=config.ready_timeout,
        status=emit,
    )

    try:
        if bot.user is None:
            raise BotwrightConfigError("Tester bot connected but bot.user is missing")

        emit(f"tester bot ready: user={bot.user} id={bot.user.id}")

        env = await verify_environment(bot, config)
        guild = env.guild
        emit(f"guild verified: {guild.name!r} ({guild.id})")

        tester_member = env.tester_member
        emit(f"tester membership verified: {tester_member} ({tester_member.id})")

        target_member = env.target_member
        emit(f"target membership verified: {target_member} ({target_member.id})")

        if env.created_channel:
            emit("temporary-channel mode verified: tester has manage_channels")
            return

        assert env.channel is not None
        channel = env.channel
        emit(f"fixed channel verified: #{channel.name} ({channel.id})")

        required_tester_permissions = tester_channel_permissions(created_channel=False)
        emit(
            "tester channel permissions verified: "
            f"{', '.join(required_tester_permissions)}"
        )

        emit(
            "target channel permissions verified: "
            "view_channel, send_messages, read_message_history"
        )
    finally:
        emit("shutting down tester bot")
        await bot.shutdown()
