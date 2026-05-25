from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from dataclasses import dataclass
from enum import Enum
from typing import AsyncIterator, Callable, Iterable, TypeAlias

import discord

from .client import TesterBot
from .exceptions import BotwrightTimeout
from .hub import MessageWaiter, ObservedMessage

MessagePredicate = Callable[[discord.Message], bool]


class AuthorFilter(Enum):
    ANY = "any"


ANY_AUTHOR = AuthorFilter.ANY
AuthorId: TypeAlias = int | AuthorFilter | None


@dataclass
class MessageHandle:
    value: discord.Message | None = None


ReplyHandle = MessageHandle


class TestSession:
    __test__ = False

    def __init__(
        self,
        bot: TesterBot,
        channel: discord.TextChannel,
        target_bot_id: int,
        default_timeout: float = 10.0,
    ) -> None:
        self.bot = bot
        self.channel = channel
        self.target_bot_id = target_bot_id
        self.default_timeout = default_timeout

    async def send(self, content: str) -> discord.Message:
        return await self.channel.send(content)

    async def wait_for_message(
        self,
        from_user_id: AuthorId = None,
        predicate: MessagePredicate | None = None,
        timeout: float | None = None,
    ) -> discord.Message:
        waiter = self._register_waiter(from_user_id, predicate)
        try:
            return await self._await_waiter(
                waiter,
                kind="message",
                timeout=self._timeout(timeout),
                from_user_id=from_user_id,
            )
        finally:
            self.bot.message_hub.unregister(waiter)

    @asynccontextmanager
    async def expect_message(
        self,
        from_user_id: AuthorId = None,
        predicate: MessagePredicate | None = None,
        timeout: float | None = None,
    ) -> AsyncIterator[MessageHandle]:
        handle = MessageHandle()
        async with self._expect(
            kind="message",
            handle=handle,
            from_user_id=from_user_id,
            predicate=predicate,
            timeout=self._timeout(timeout),
        ):
            yield handle

    @asynccontextmanager
    async def expect_reply(
        self,
        from_user_id: AuthorId = None,
        predicate: MessagePredicate | None = None,
        timeout: float | None = None,
    ) -> AsyncIterator[ReplyHandle]:
        handle = ReplyHandle()
        async with self._expect(
            kind="reply",
            handle=handle,
            from_user_id=from_user_id,
            predicate=predicate,
            timeout=self._timeout(timeout),
        ):
            yield handle

    async def send_and_wait(
        self,
        content: str,
        from_user_id: AuthorId = None,
        predicate: MessagePredicate | None = None,
        timeout: float | None = None,
    ) -> discord.Message:
        async with self.expect_reply(
            from_user_id=from_user_id,
            predicate=predicate,
            timeout=timeout,
        ) as reply:
            await self.send(content)
        assert reply.value is not None
        return reply.value

    def _timeout(self, timeout: float | None) -> float:
        return self.default_timeout if timeout is None else timeout

    @asynccontextmanager
    async def _expect(
        self,
        *,
        kind: str,
        handle: MessageHandle,
        from_user_id: AuthorId,
        predicate: MessagePredicate | None,
        timeout: float,
    ) -> AsyncIterator[None]:
        waiter = self._register_waiter(from_user_id, predicate)
        try:
            yield
            handle.value = await self._await_waiter(
                waiter,
                kind=kind,
                timeout=timeout,
                from_user_id=from_user_id,
            )
        finally:
            self.bot.message_hub.unregister(waiter)

    def _register_waiter(
        self,
        from_user_id: AuthorId,
        predicate: MessagePredicate | None,
    ) -> MessageWaiter:
        return self.bot.message_hub.register(
            self.channel.id,
            lambda message: self._reject_reason(message, from_user_id, predicate),
        )

    async def _await_waiter(
        self,
        waiter: MessageWaiter,
        *,
        kind: str,
        timeout: float,
        from_user_id: AuthorId,
    ) -> discord.Message:
        try:
            return await asyncio.wait_for(waiter.future, timeout=timeout)
        except asyncio.TimeoutError as e:
            message = await self._timeout_message(
                kind=kind,
                timeout=timeout,
                from_user_id=from_user_id,
                observed=waiter.observed,
            )
            raise BotwrightTimeout(message) from e

    def _reject_reason(
        self,
        message: discord.Message,
        from_user_id: AuthorId,
        predicate: MessagePredicate | None,
    ) -> str | None:
        expected_author = self._expected_author(from_user_id)

        if message.channel.id != self.channel.id:
            return f"wrong channel: expected {self.channel.id}, got {message.channel.id}"
        if expected_author is not ANY_AUTHOR and message.author.id != expected_author:
            return f"wrong author: expected {expected_author}, got {message.author.id}"
        if predicate is not None and not predicate(message):
            return "predicate returned False"
        return None

    def _expected_author(self, from_user_id: AuthorId) -> int | AuthorFilter:
        if from_user_id is ANY_AUTHOR:
            return ANY_AUTHOR
        if from_user_id is None:
            return self.target_bot_id
        return from_user_id

    def _format_author(self, author: int | AuthorFilter) -> str:
        if author is ANY_AUTHOR:
            return "any"
        return str(author)

    async def _timeout_message(
        self,
        *,
        kind: str,
        timeout: float,
        from_user_id: AuthorId,
        observed: Iterable[ObservedMessage],
    ) -> str:
        expected_author = self._expected_author(from_user_id)
        stats = self.bot.message_hub.stats
        observed_messages = list(observed)
        lines = [
            f"No matching {kind} in #{self.channel.name} within {timeout}s",
            f"Expected channel_id={self.channel.id}, "
            f"author_id={self._format_author(expected_author)}",
            "Gateway counters: "
            f"events={stats.gateway_event_count}, "
            f"message_create={stats.gateway_message_create_count}, "
            f"on_message={stats.message_count}, "
            f"matched_waiters={stats.matched_count}",
            f"Recent gateway events: {', '.join(stats.recent_gateway_events) or 'none'}",
            f"Gateway messages observed for this wait: {len(observed_messages)}",
        ]

        for item in observed_messages[-5:]:
            lines.append(f"- {item.reason}: {self._describe_message(item.message)}")

        recent = await self._recent_channel_history()
        if recent:
            lines.append("Recent channel history:")
            for message in recent:
                lines.append(f"- {self._describe_message(message)}")
        else:
            lines.append("Recent channel history: unavailable or empty")

        return "\n".join(lines)

    async def _recent_channel_history(self, limit: int = 5) -> list[discord.Message]:
        try:
            return [message async for message in self.channel.history(limit=limit)]
        except (AttributeError, discord.HTTPException):
            return []

    def _describe_message(self, message: discord.Message) -> str:
        channel = getattr(message, "channel", None)
        author = getattr(message, "author", None)
        content = getattr(message, "content", "").replace("\n", "\\n")
        embeds = getattr(message, "embeds", ())

        if len(content) > 160:
            content = f"{content[:157]}..."

        channel_name = getattr(channel, "name", "?")
        channel_id = getattr(channel, "id", "?")
        author_id = getattr(author, "id", "?")
        author_name = str(author) if author is not None else "?"

        description = (
            f"#{channel_name} ({channel_id}) from {author_name} ({author_id}): "
            f"{content!r}"
        )

        if embeds:
            description += f" embeds={self._describe_embeds(embeds)}"

        return description

    def _describe_embeds(self, embeds: object) -> str:
        try:
            embed_list = list(embeds)
        except TypeError:
            return "[unavailable]"

        parts: list[str] = []
        for index, embed in enumerate(embed_list[:3]):
            title = getattr(embed, "title", None)
            description = getattr(embed, "description", None)
            fields = getattr(embed, "fields", ())
            summary = f"#{index}"
            if title:
                summary += f" title={self._preview(str(title))!r}"
            if description:
                summary += f" description={self._preview(str(description))!r}"
            if fields:
                summary += f" fields={self._safe_len(fields)}"
            parts.append(summary)

        extra = len(embed_list) - len(parts)
        if extra > 0:
            parts.append(f"+{extra} more")
        return "[" + "; ".join(parts) + "]"

    def _safe_len(self, value: object) -> int:
        try:
            return len(value)  # type: ignore[arg-type]
        except TypeError:
            return 0

    def _preview(self, value: str, limit: int = 80) -> str:
        value = value.replace("\n", "\\n")
        if len(value) <= limit:
            return value
        return f"{value[: limit - 3]}..."
