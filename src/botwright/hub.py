from __future__ import annotations

import asyncio
from collections import defaultdict, deque
from contextlib import suppress
from dataclasses import dataclass, field
from typing import Callable

import discord

MessageCheck = Callable[[discord.Message], str | None]
RECENT_GATEWAY_EVENTS = {
    "READY",
    "RESUMED",
    "MESSAGE_CREATE",
    "MESSAGE_UPDATE",
    "MESSAGE_DELETE",
    "MESSAGE_DELETE_BULK",
}


@dataclass
class ObservedMessage:
    message: discord.Message
    reason: str


@dataclass
class MessageHubStats:
    gateway_event_count: int = 0
    gateway_message_create_count: int = 0
    message_count: int = 0
    matched_count: int = 0
    recent_gateway_events: deque[str] = field(
        default_factory=lambda: deque(maxlen=20)
    )


@dataclass
class MessageWaiter:
    channel_id: int
    check: MessageCheck
    future: asyncio.Future[discord.Message]
    observed: deque[ObservedMessage] = field(
        default_factory=lambda: deque(maxlen=50)
    )

    def inspect(self, message: discord.Message) -> bool:
        reason = self.check(message)
        self.observed.append(ObservedMessage(message, reason or "matched"))
        return reason is None


class MessageHub:
    def __init__(self) -> None:
        self.stats = MessageHubStats()
        self._waiters: dict[int, list[MessageWaiter]] = defaultdict(list)

    def record_gateway_event(self, event_type: str) -> None:
        self.stats.gateway_event_count += 1
        if event_type in RECENT_GATEWAY_EVENTS:
            self.stats.recent_gateway_events.append(event_type)
        if event_type == "MESSAGE_CREATE":
            self.stats.gateway_message_create_count += 1

    def register(self, channel_id: int, check: MessageCheck) -> MessageWaiter:
        waiter = MessageWaiter(
            channel_id=channel_id,
            check=check,
            future=asyncio.get_running_loop().create_future(),
        )
        self._waiters[channel_id].append(waiter)
        return waiter

    def unregister(self, waiter: MessageWaiter) -> None:
        waiters = self._waiters.get(waiter.channel_id)
        if waiters is None:
            return

        with suppress(ValueError):
            waiters.remove(waiter)

        if not waiters:
            self._waiters.pop(waiter.channel_id, None)

    def dispatch(self, message: discord.Message) -> None:
        self.stats.message_count += 1
        waiters = list(self._waiters.get(message.channel.id, ()))

        for waiter in waiters:
            if waiter.future.done():
                continue

            try:
                matched = waiter.inspect(message)
            except Exception as e:
                waiter.future.set_exception(e)
                continue

            if matched:
                self.stats.matched_count += 1
                waiter.future.set_result(message)
