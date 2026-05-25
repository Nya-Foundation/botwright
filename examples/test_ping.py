import pytest

from botwright import TestSession


@pytest.mark.asyncio
async def test_ping(session: TestSession):
    async with session.expect_reply(timeout=5) as reply:
        await session.send("!ping")

    assert reply.value is not None
    assert reply.value.content == "pong"
    assert reply.value.author.id == session.target_bot_id


@pytest.mark.asyncio
async def test_echo(session: TestSession):
    reply = await session.send_and_wait("!echo hello", timeout=5)

    assert reply.content == "hello"
    assert reply.author.id == session.target_bot_id


@pytest.mark.asyncio
async def test_help(session: TestSession):
    async with session.expect_message(from_user_id=session.target_bot_id) as msg:
        await session.send("!help")

    # expecing a discord.Message with embed(s) in the content, but we won't check the content here
    assert msg.value is not None
    assert len(msg.value.embeds) > 0
