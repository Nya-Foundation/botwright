from __future__ import annotations

from dataclasses import dataclass

import discord

from .client import TesterBot
from .config import BotwrightConfig
from .exceptions import BotwrightConfigError


@dataclass(frozen=True)
class VerifiedEnvironment:
    guild: discord.Guild
    tester_member: discord.Member
    target_member: discord.Member
    channel: discord.TextChannel | None
    created_channel: bool


async def verify_environment(
    bot: TesterBot,
    config: BotwrightConfig,
    *,
    channel_id: int | None = None,
) -> VerifiedEnvironment:
    if bot.user is None:
        raise BotwrightConfigError("Tester bot connected but bot.user is unavailable")

    guild = await fetch_guild(bot, config.guild_id)
    tester_member = await fetch_member(guild, bot.user.id, "tester bot")
    target_member = await fetch_member(guild, config.target_bot_id, "target bot")
    resolved_channel_id = config.channel_id if channel_id is None else channel_id
    created_channel = resolved_channel_id is None
    channel = None

    if created_channel:
        require_permissions(
            tester_member.guild_permissions,
            ("manage_channels",),
            f"guild {guild.name!r} ({guild.id})",
        )
    else:
        channel = await fetch_text_channel(bot, guild, resolved_channel_id)
        require_permissions(
            channel.permissions_for(tester_member),
            tester_channel_permissions(created_channel=False),
            f"#{channel.name}",
        )
        require_permissions(
            channel.permissions_for(target_member),
            ("view_channel", "send_messages", "read_message_history"),
            f"target bot in #{channel.name}",
        )

    return VerifiedEnvironment(
        guild=guild,
        tester_member=tester_member,
        target_member=target_member,
        channel=channel,
        created_channel=created_channel,
    )


async def fetch_guild(bot: TesterBot, guild_id: int) -> discord.Guild:
    guild = bot.get_guild(guild_id)
    if guild is not None:
        return guild

    try:
        return await bot.fetch_guild(guild_id)
    except discord.NotFound as e:
        raise BotwrightConfigError(f"Guild {guild_id} was not found") from e
    except discord.Forbidden as e:
        raise BotwrightConfigError(
            f"Tester bot is not allowed to access guild {guild_id}"
        ) from e


async def fetch_member(
    guild: discord.Guild,
    user_id: int,
    label: str,
) -> discord.Member:
    member = guild.get_member(user_id)
    if member is not None:
        return member

    try:
        return await guild.fetch_member(user_id)
    except discord.NotFound as e:
        raise BotwrightConfigError(
            f"{label} ({user_id}) is not in guild {guild.id}"
        ) from e
    except discord.Forbidden as e:
        raise BotwrightConfigError(
            f"Could not verify {label} ({user_id}) in guild {guild.id}; "
            "the tester bot was forbidden from fetching guild members"
        ) from e


async def fetch_text_channel(
    bot: TesterBot,
    guild: discord.Guild,
    channel_id: int,
) -> discord.TextChannel:
    channel = guild.get_channel(channel_id)
    if channel is None:
        try:
            channel = await bot.fetch_channel(channel_id)  # type: ignore[assignment]
        except discord.NotFound as e:
            raise BotwrightConfigError(f"Channel {channel_id} was not found") from e
        except discord.Forbidden as e:
            raise BotwrightConfigError(
                f"Tester bot is not allowed to access channel {channel_id}"
            ) from e

    if not isinstance(channel, discord.TextChannel):
        raise BotwrightConfigError(
            f"Channel {channel_id} must be a text channel, got {type(channel).__name__}"
        )
    if channel.guild.id != guild.id:
        raise BotwrightConfigError(
            f"Channel {channel_id} is in guild {channel.guild.id}, "
            f"but BOTWRIGHT_GUILD_ID is {guild.id}"
        )

    return channel


def require_permissions(
    permissions: discord.Permissions,
    required: tuple[str, ...],
    context: str,
) -> None:
    missing = [name for name in required if not getattr(permissions, name)]
    if missing:
        formatted = ", ".join(missing)
        raise BotwrightConfigError(f"Tester bot is missing {formatted} in {context}")


def tester_channel_permissions(created_channel: bool) -> tuple[str, ...]:
    permissions = ("view_channel", "send_messages", "read_message_history")
    if created_channel:
        return (*permissions, "manage_channels")
    return permissions
