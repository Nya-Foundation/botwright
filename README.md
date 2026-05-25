# Botwright

<div align="center">

<pre>
 ____        _                  _       _     _
| __ )  ___ | |___      ___ __ (_) __ _| |__ | |_
|  _ \ / _ \| __\ \ /\ / / '__|| |/ _` | '_ \| __|
| |_) | (_) | |_ \ V  V /| |   | | (_| | | | | |_
|____/ \___/ \__| \_/\_/ |_|   |_|\__, |_| |_|\__|
                                  |___/

Discord bot e2e tests through real channels, real messages, real assertions.
</pre>

</div>

End-to-end testing for Discord bots, built on `discord.py` and pytest.

Botwright uses a real tester bot account to talk to your target bot in Discord.
Tests send real Discord messages, wait for target-bot responses, and assert on
real `discord.Message` objects.

```python
import pytest

from botwright import TestSession


@pytest.mark.asyncio
async def test_ping(session: TestSession):
    reply = await session.send_and_wait("!ping")

    assert reply.content == "pong"
    assert reply.author.id == session.target_bot_id
```

## Why Botwright?

Unit tests are useful, but Discord bots often fail at the boundary: intents,
permissions, channel routing, embeds, command prefixes, bot-to-bot behavior, and
Discord API timing.

Botwright tests that boundary directly:

- Runs inside pytest, so you keep normal `assert`, fixtures, parametrization, and
  reporting.
- Uses one tester bot per pytest session for fast startup.
- Uses one isolated temporary channel per test by default.
- Supports fixed-channel tests for bots that only monitor specific channels.
- Returns real `discord.py` objects instead of wrapping responses in a custom DSL.

## Installation

```bash
uv add botwright
```

For local development in this repository:

```bash
uv sync
```

## Discord Setup

Create two bots in the same dedicated test guild:

- **Target bot**: the bot you want to test.
- **Tester bot**: a separate bot account controlled by Botwright.

The tester bot needs:

- `Send Messages`
- `Read Message History`
- `View Channel`
- `Manage Channels` if Botwright will create temporary channels
- Message Content Intent enabled in the Discord Developer Portal

If your target bot ignores messages from bot accounts, add a test-mode bypass.
For example:

```python
if message.author.bot and os.getenv("TEST_MODE") != "1":
    return
```

## Configuration

Botwright reads environment variables and `.env` files through `python-dotenv`.

Required:

```bash
export BOTWRIGHT_TESTER_TOKEN="..."
export BOTWRIGHT_GUILD_ID="..."
export BOTWRIGHT_TARGET_BOT_ID="..."
```

Optional:

| Variable | Default | Description |
| --- | --- | --- |
| `BOTWRIGHT_CHANNEL_ID` | unset | Existing text channel to use instead of creating temporary channels. |
| `BOTWRIGHT_CHANNEL_PREFIX` | `botwright-` | Prefix for temporary channel names. |
| `BOTWRIGHT_DEFAULT_TIMEOUT` | `10` | Default seconds to wait for expected messages. |
| `BOTWRIGHT_READY_TIMEOUT` | `30` | Seconds to wait for the tester bot to connect. |
| `BOTWRIGHT_KEEP_CHANNELS` | `never` | `never`, `failed`, or `always`. |

Command-line options override environment variables:

```bash
pytest tests/e2e \
  --botwright-timeout=20 \
  --botwright-keep-channels=failed \
  --botwright-channel-prefix=mybot-
```

Available options:

- `--botwright-check`
- `--botwright-channel-id`
- `--botwright-channel-prefix`
- `--botwright-timeout`
- `--botwright-ready-timeout`
- `--botwright-keep-channels=never|failed|always`
- `--botwright-no-banner`

Validate Discord configuration without running tests:

```bash
botwright check
```

The same check is also available through pytest:

```bash
pytest --botwright-check
```

Both commands connect the tester bot, verify the guild, verify tester and target
membership, check fixed-channel permissions when `BOTWRIGHT_CHANNEL_ID` is set,
and then exit.

## Writing Tests

### Listener before sender

Use `expect_reply()` or `expect_message()` when the bot may reply immediately.
The listener is registered before the message is sent.

```python
@pytest.mark.asyncio
async def test_help_embed(session: TestSession):
    async with session.expect_reply() as reply:
        await session.send("!help")

    assert reply.value is not None
    assert reply.value.embeds
    assert reply.value.author.id == session.target_bot_id
```

### One-shot send and wait

Use `send_and_wait()` for simple request-response tests.

```python
@pytest.mark.asyncio
async def test_echo(session: TestSession):
    reply = await session.send_and_wait("!echo hello")

    assert reply.content == "hello"
```

### Passive waits

Use `wait_for_message()` when something else already triggered the response.

```python
@pytest.mark.asyncio
async def test_background_notification(session: TestSession):
    message = await session.wait_for_message(
        predicate=lambda msg: "done" in msg.content.lower(),
        timeout=30,
    )

    assert message.author.id == session.target_bot_id
```

By default, Botwright waits for messages from the configured target bot. Use
`ANY_AUTHOR` when a test should accept a message from any user or bot:

```python
from botwright import ANY_AUTHOR


@pytest.mark.asyncio
async def test_anyone_can_trigger_audit_log(session: TestSession):
    message = await session.wait_for_message(
        from_user_id=ANY_AUTHOR,
        predicate=lambda msg: "audit complete" in msg.content.lower(),
    )

    assert message.channel.id == session.channel.id
```

## Fixed-Channel Mode

By default, Botwright creates a temporary channel for each test and deletes it
after the test finishes. This gives strong isolation.

Some bots only monitor a specific channel. In that case, use fixed-channel mode:

```bash
pytest tests/e2e --botwright-channel-id=123456789012345678
```

or per test:

```python
@pytest.mark.botwright(channel_id=123456789012345678)
@pytest.mark.asyncio
async def test_channel_bound_bot(session: TestSession):
    reply = await session.send_and_wait("!status")

    assert reply.content
```

In fixed-channel mode:

- Botwright does not create or delete the channel.
- `Manage Channels` is not required.
- Botwright still filters messages by channel ID and target bot ID.
- Test isolation is your responsibility. Avoid parallel tests in the same fixed
  channel unless your predicates make each expected response unique.

## Ordered Flows

Discord e2e tests often describe workflows, and workflows are usually ordered.
Prefer writing those workflows as one explicit async test instead of relying on
cross-test ordering:

```python
@pytest.mark.asyncio
async def test_onboarding_flow(session: TestSession):
    welcome = await session.send_and_wait("!start")
    assert "welcome" in welcome.content.lower()

    next_step = await session.send_and_wait("!next")
    assert next_step.embeds
```

This keeps failures local: pytest reports the flow that failed, and the code
shows the exact sequence that led to the failure.

If you need ordered test functions, use an ordering plugin such as
`pytest-order`. Botwright does not provide its own ordering layer because pytest
already has good ecosystem support for that problem.

## Pytest Integration

Botwright registers a pytest plugin named `botwright`.

Installed packages are auto-discovered by pytest. If plugin auto-discovery is
disabled, load it explicitly:

```bash
pytest -p botwright.plugin
```

Fixtures:

| Fixture | Scope | Description |
| --- | --- | --- |
| `botwright_config` | session | Validated Botwright configuration. |
| `tester_bot` | session | Connected tester `discord.Client`. |
| `test_channel` | function | Temporary or configured text channel. |
| `session` | function | `TestSession` bound to the current channel. |

Botwright automatically runs tests using these fixtures on pytest-asyncio's
session event loop. This keeps Discord client, HTTP, and gateway state on the
same loop.

If you explicitly mark a Botwright test with `@pytest.mark.asyncio`, use
`loop_scope="session"`:

```python
@pytest.mark.asyncio(loop_scope="session")
async def test_ping(session: TestSession):
    ...
```

Botwright rejects conflicting loop scopes because `discord.py` clients and HTTP
sessions cannot be moved between event loops safely.

### Bot lifecycle

`tester_bot` is session-scoped. One pytest process starts one tester bot and
shares it across all Botwright tests in that process, even when those tests live
in multiple files:

```bash
pytest tests/e2e
```

Separate pytest invocations start separate tester bot sessions:

```bash
pytest tests/e2e/test_a.py
pytest tests/e2e/test_b.py
```

If you use `pytest-xdist`, each worker process has its own session-scoped
fixtures. That means each worker starts its own tester bot. For now, run
Botwright tests without xdist unless you intentionally partition channels and
bot accounts per worker.

### Per-test marker

Use `@pytest.mark.botwright(...)` to override settings for one test:

```python
@pytest.mark.botwright(timeout=30, keep_channel=True)
@pytest.mark.asyncio
async def test_slow_flow(session: TestSession):
    reply = await session.send_and_wait("!slow")

    assert reply.content == "complete"
```

Supported marker arguments:

- `timeout`: default wait timeout for that test's `session`
- `keep_channel`: keep or delete a temporary channel for that test
- `channel_id`: use an existing text channel for that test

## API Reference

### `TestSession`

`session.channel`
: The Discord text channel for the current test.

`session.target_bot_id`
: The configured target bot user ID.

`await session.send(content)`
: Send a message as the tester bot. Returns the tester bot's
`discord.Message`.

`await session.wait_for_message(from_user_id=None, predicate=None, timeout=None)`
: Wait for a matching message in the current channel. By default, waits for the
configured target bot.

`async with session.expect_message(...) as message`
: Register a message waiter before the code inside the context block runs.
The resulting message is available as `message.value` after the block exits.

`async with session.expect_reply(...) as reply`
: Convenience helper for the common target-bot reply case. It uses the same
waiter machinery as `expect_message()`, but reads better in request-response
tests.

`await session.send_and_wait(content, from_user_id=None, predicate=None, timeout=None)`
: Register a reply waiter, send a message, and return the matching response.

Predicates receive a real `discord.Message`:

```python
reply = await session.send_and_wait(
    "!help",
    predicate=lambda msg: bool(msg.embeds),
)

assert reply.embeds[0].title
```

## Debugging

Use verbose pytest output while developing:

```bash
pytest tests/e2e -s -v --botwright-keep-channels=failed
```

Use `--botwright-no-banner` in CI if you prefer compact logs:

```bash
pytest tests/e2e --botwright-no-banner
```

For the standalone check command, use:

```bash
botwright check --no-banner
```

Botwright prints setup diagnostics:

- Configuration loaded
- Tester bot connected
- Guild membership verified
- Channel selected or created
- Required permissions verified
- Temporary channel deleted or retained

Timeout errors include:

- Expected channel ID and author ID
- Gateway event counters
- Messages observed by the wait
- Recent channel history, including embed counts, titles, descriptions, and
  field counts when available

If a test fails, `--botwright-keep-channels=failed` leaves the Discord channel in
place so you can inspect the conversation.

Run the setup check before debugging individual tests:

```bash
botwright check
```

## Example Project

Run the included demo target bot:

```bash
TEST_MODE=1 TARGET_BOT_TOKEN="..." python examples/target_bot/bot.py
```

Run the example tests:

```bash
pytest examples/ -v
```

## Current Limitations

- Slash commands are not supported. Discord does not allow one bot account to
  invoke another bot's slash commands through the public bot API.
- Botwright currently focuses on text messages. Reactions, components, modals,
  and voice workflows are future API candidates.
- Fixed-channel tests are not isolated unless your test design makes them
  isolated.
