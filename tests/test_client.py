from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from botwright.client import TesterBot


@pytest.mark.asyncio
async def test_tester_bot_dispatches_messages_to_hub() -> None:
    bot = TesterBot()

    waiter = bot.message_hub.register(10, lambda message: None)
    await bot.on_message(SimpleNamespace(channel=SimpleNamespace(id=10), content="hello"))

    assert waiter.future.result().content == "hello"
    assert bot.message_hub.stats.message_count == 1


@pytest.mark.asyncio
async def test_tester_bot_supports_message_listeners() -> None:
    bot = TesterBot()
    observed: list[str] = []

    async def listener(message: SimpleNamespace) -> None:
        observed.append(message.content)

    bot.add_listener(listener, "on_message")
    await bot.on_message(SimpleNamespace(channel=SimpleNamespace(id=10), content="hello"))
    bot.remove_listener(listener, "on_message")
    await bot.on_message(SimpleNamespace(channel=SimpleNamespace(id=10), content="ignored"))

    assert observed == ["hello"]


@pytest.mark.asyncio
async def test_start_in_background_keeps_gateway_task_running() -> None:
    class FakeTesterBot(TesterBot):
        def __init__(self) -> None:
            super().__init__()
            self.closed = asyncio.Event()

        async def login(self, token: str) -> None:
            assert token == "token"

        async def connect(self, *, reconnect: bool = True) -> None:
            del reconnect
            await self.on_ready()
            await self.closed.wait()

        async def close(self) -> None:
            self.closed.set()

        def is_closed(self) -> bool:
            return self.closed.is_set()

    bot = FakeTesterBot()

    await bot.start_in_background("token")

    assert bot._runner is not None
    assert not bot._runner.done()

    await bot.shutdown()


@pytest.mark.asyncio
async def test_shutdown_times_out_and_cancels_gateway_task() -> None:
    class StuckCloseBot(TesterBot):
        def __init__(self) -> None:
            super().__init__()
            self.status_messages: list[str] = []

        async def login(self, token: str) -> None:
            assert token == "token"

        async def connect(self, *, reconnect: bool = True) -> None:
            del reconnect
            await self.on_ready()
            await asyncio.Event().wait()

        async def close(self) -> None:
            return None

        def is_closed(self) -> bool:
            return False

    bot = StuckCloseBot()
    await bot.start_in_background("token", status=bot.status_messages.append)

    await bot.shutdown(timeout=0.01)

    assert bot._runner is not None
    assert bot._runner.cancelled()
    assert "tester bot shutdown timed out after 0.01s" in bot.status_messages


@pytest.mark.asyncio
async def test_tester_bot_records_gateway_message_create_events() -> None:
    bot = TesterBot()

    await bot.on_socket_event_type("READY")
    await bot.on_socket_event_type("PRESENCE_UPDATE")
    await bot.on_socket_event_type("MESSAGE_CREATE")

    assert bot.message_hub.stats.gateway_event_count == 3
    assert bot.message_hub.stats.gateway_message_create_count == 1
    assert list(bot.message_hub.stats.recent_gateway_events) == [
        "READY",
        "MESSAGE_CREATE",
    ]
