from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from botwright.exceptions import BotwrightTimeout
from botwright.hub import MessageHub
from botwright.session import ANY_AUTHOR, TestSession


def message(channel_id: int, author_id: int, content: str = "") -> SimpleNamespace:
    return SimpleNamespace(
        channel=SimpleNamespace(id=channel_id, name=f"channel-{channel_id}"),
        author=SimpleNamespace(id=author_id),
        content=content,
    )


class FakeBot:
    def __init__(self) -> None:
        self.message_hub = MessageHub()

    async def dispatch(self, candidate: SimpleNamespace) -> None:
        self.message_hub.dispatch(candidate)


class FakeChannel:
    def __init__(self, bot: FakeBot) -> None:
        self.id = 10
        self.name = "botwright-test"
        self.bot = bot
        self.history_items: list[SimpleNamespace] = []

    async def send(self, content: str) -> SimpleNamespace:
        sent = message(self.id, 1, content)
        await self.bot.dispatch(message(self.id, 20, "pong"))
        return sent

    async def history(
        self,
        *,
        limit: int = 5,
        after: SimpleNamespace | None = None,
        oldest_first: bool = False,
    ):
        del after
        items = self.history_items[:limit]
        if not oldest_first:
            items = list(reversed(items))
        for item in items:
            yield item


@pytest.mark.asyncio
async def test_send_and_wait_registers_listener_before_sending() -> None:
    bot = FakeBot()
    channel = FakeChannel(bot)
    session = TestSession(bot, channel, target_bot_id=20)

    reply = await session.send_and_wait("!ping")

    assert reply.content == "pong"
    assert bot.message_hub.stats.matched_count == 1


@pytest.mark.asyncio
async def test_send_and_wait_can_match_any_author() -> None:
    bot = FakeBot()
    channel = FakeChannel(bot)
    session = TestSession(bot, channel, target_bot_id=99)

    reply = await session.send_and_wait("!ping", from_user_id=ANY_AUTHOR)

    assert reply.author.id == 20
    assert reply.content == "pong"


@pytest.mark.asyncio
async def test_expect_message_registers_listener_before_sending() -> None:
    bot = FakeBot()
    channel = FakeChannel(bot)
    session = TestSession(bot, channel, target_bot_id=20)

    async with session.expect_message(from_user_id=20) as msg:
        await session.send("!ping")

    assert msg.value is not None
    assert msg.value.content == "pong"
    assert bot.message_hub.stats.matched_count == 1


@pytest.mark.asyncio
async def test_wait_for_message_filters_channel_author_and_predicate() -> None:
    bot = FakeBot()
    session = TestSession(bot, FakeChannel(bot), target_bot_id=20)
    task = asyncio.create_task(
        session.wait_for_message(predicate=lambda msg: msg.content == "take")
    )
    await asyncio.sleep(0)

    await bot.dispatch(message(11, 20, "wrong channel"))
    await bot.dispatch(message(10, 21, "wrong author"))
    await bot.dispatch(message(10, 20, "skip"))
    await bot.dispatch(message(10, 20, "take"))

    reply = await task
    assert reply.content == "take"


@pytest.mark.asyncio
async def test_wait_for_message_can_match_any_author() -> None:
    bot = FakeBot()
    session = TestSession(bot, FakeChannel(bot), target_bot_id=20)
    task = asyncio.create_task(session.wait_for_message(from_user_id=ANY_AUTHOR))
    await asyncio.sleep(0)

    await bot.dispatch(message(10, 21, "from someone else"))

    reply = await task
    assert reply.author.id == 21
    assert reply.content == "from someone else"


@pytest.mark.asyncio
async def test_wait_for_message_raises_botwright_timeout() -> None:
    bot = FakeBot()
    session = TestSession(bot, FakeChannel(bot), target_bot_id=20)

    with pytest.raises(BotwrightTimeout, match="No matching message"):
        await session.wait_for_message(timeout=0.01)


def test_session_accepts_default_timeout() -> None:
    bot = FakeBot()
    session = TestSession(bot, FakeChannel(bot), target_bot_id=20, default_timeout=2.5)

    assert session.default_timeout == 2.5
    assert session._timeout(None) == 2.5
    assert session._timeout(1.0) == 1.0


def test_describe_message_includes_embed_summary() -> None:
    bot = FakeBot()
    session = TestSession(bot, FakeChannel(bot), target_bot_id=20)
    embed = SimpleNamespace(
        title="Help",
        description="Available commands",
        fields=[SimpleNamespace(name="ping")],
    )
    candidate = message(10, 20, "")
    candidate.embeds = [embed]

    text = session._describe_message(candidate)

    assert "embeds=[#0" in text
    assert "title='Help'" in text
    assert "description='Available commands'" in text
    assert "fields=1" in text


def test_describe_message_tolerates_non_iterable_embeds() -> None:
    bot = FakeBot()
    session = TestSession(bot, FakeChannel(bot), target_bot_id=20)
    candidate = message(10, 20, "")
    candidate.embeds = object()

    text = session._describe_message(candidate)

    assert "embeds=[unavailable]" in text


@pytest.mark.asyncio
async def test_expect_reply_timeout_reports_observed_rejections() -> None:
    bot = FakeBot()
    session = TestSession(bot, FakeChannel(bot), target_bot_id=20)

    with pytest.raises(BotwrightTimeout) as excinfo:
        async with session.expect_reply(timeout=0.01):
            await bot.dispatch(message(10, 21, "not the target"))

    text = str(excinfo.value)
    assert "Gateway messages observed for this wait: 1" in text
    assert "wrong author: expected 20, got 21" in text
    assert "not the target" in text


@pytest.mark.asyncio
async def test_observed_messages_are_bounded() -> None:
    bot = FakeBot()
    session = TestSession(bot, FakeChannel(bot), target_bot_id=20)

    with pytest.raises(BotwrightTimeout) as excinfo:
        async with session.expect_reply(timeout=0.01):
            for index in range(75):
                await bot.dispatch(message(10, 21, f"noise {index}"))

    assert "Gateway messages observed for this wait: 50" in str(excinfo.value)


@pytest.mark.asyncio
async def test_expect_message_timeout_reports_recent_channel_history() -> None:
    bot = FakeBot()
    channel = FakeChannel(bot)
    session = TestSession(bot, channel, target_bot_id=20)

    with pytest.raises(BotwrightTimeout) as excinfo:
        async with session.expect_message(timeout=0.01) as msg:
            del msg
            channel.history_items.append(message(10, 20, "history reply"))

    text = str(excinfo.value)
    assert "Recent channel history:" in text
    assert "history reply" in text


@pytest.mark.asyncio
async def test_expect_message_returns_gateway_message_not_history() -> None:
    bot = FakeBot()
    channel = FakeChannel(bot)
    session = TestSession(bot, channel, target_bot_id=20)

    async with session.expect_message(timeout=0.01) as msg:
        channel.history_items.append(message(10, 20, "history reply"))
        await bot.dispatch(message(10, 20, "gateway reply"))

    assert msg.value is not None
    assert msg.value.content == "gateway reply"
