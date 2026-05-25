from __future__ import annotations

import asyncio
from collections import defaultdict
from contextlib import suppress
from inspect import isawaitable
from typing import Any, Callable

import discord

from .exceptions import BotwrightStartupError
from .hub import MessageHub

StatusCallback = Callable[[str], None]
EventListener = Callable[..., Any]


class TesterBot(discord.Client):
    __test__ = False

    def __init__(self) -> None:
        intents = discord.Intents.none()
        intents.guilds = True
        intents.guild_messages = True
        intents.message_content = True
        super().__init__(intents=intents)
        self._botwright_ready = asyncio.Event()
        self._runner: asyncio.Task[None] | None = None
        self._status: StatusCallback | None = None
        self._listeners: dict[str, list[EventListener]] = defaultdict(list)
        self.message_hub = MessageHub()

    async def on_ready(self) -> None:
        self._botwright_ready.set()

    async def on_message(self, message: discord.Message) -> None:
        self.message_hub.dispatch(message)
        await self._notify_listeners("on_message", message)

    async def on_socket_event_type(self, event_type: str) -> None:
        self.message_hub.record_gateway_event(event_type)
        await self._notify_listeners("on_socket_event_type", event_type)

    def add_listener(self, func: EventListener, name: str | None = None) -> None:
        self._listeners[name or func.__name__].append(func)

    def remove_listener(self, func: EventListener, name: str | None = None) -> None:
        listeners = self._listeners.get(name or func.__name__)
        if listeners is None:
            return

        with suppress(ValueError):
            listeners.remove(func)

        if not listeners:
            self._listeners.pop(name or func.__name__, None)

    async def start_in_background(
        self,
        token: str,
        *,
        timeout: float = 30.0,
        status: StatusCallback | None = None,
    ) -> None:
        if self._runner is not None and not self._runner.done():
            raise RuntimeError("TesterBot is already running")

        self._status = status

        async def runner() -> None:
            self._emit("logging in to Discord")
            await self.login(token)
            self._emit("login accepted; connecting to Discord gateway")
            await self.connect()

        self._botwright_ready.clear()
        self._runner = asyncio.create_task(runner())
        self._runner.add_done_callback(self._log_runner_failure)
        ready_task = asyncio.create_task(self._botwright_ready.wait())
        done, pending = await asyncio.wait(
            {self._runner, ready_task},
            timeout=timeout,
            return_when=asyncio.FIRST_COMPLETED,
        )

        if not done:
            self._runner.cancel()
            ready_task.cancel()
            for task in (self._runner, ready_task):
                with suppress(asyncio.CancelledError):
                    await task
            raise BotwrightStartupError(f"Tester bot did not become ready within {timeout}s")

        if ready_task in pending:
            ready_task.cancel()
            with suppress(asyncio.CancelledError):
                await ready_task

        if self._runner in done:
            await self._runner

        self._emit("Discord ready event received")

    async def shutdown(self, *, timeout: float = 5.0) -> None:
        if not self.is_closed():
            await self.close()
        if self._runner is not None:
            try:
                await asyncio.wait_for(self._runner, timeout=timeout)
            except asyncio.CancelledError:
                pass
            except asyncio.TimeoutError:
                self._runner.cancel()
                self._emit(f"tester bot shutdown timed out after {timeout}s")

    def _emit(self, message: str) -> None:
        if self._status is not None:
            self._status(message)

    async def _notify_listeners(self, name: str, *args: object) -> None:
        for listener in list(self._listeners.get(name, ())):
            result = listener(*args)
            if isawaitable(result):
                await result

    def _log_runner_failure(self, task: asyncio.Task[None]) -> None:
        if task.cancelled():
            return
        try:
            exception = task.exception()
        except asyncio.CancelledError:
            return
        if exception is not None and not self.is_closed():
            self._emit(f"tester bot gateway task stopped: {exception!r}")
