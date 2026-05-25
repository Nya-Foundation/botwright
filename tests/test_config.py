import pytest

from botwright.config import BotwrightConfig
from botwright.exceptions import BotwrightConfigError


@pytest.fixture(autouse=True)
def no_env_var(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("BOTWRIGHT_CHANNEL_ID", raising=False)
    monkeypatch.delenv("BOTWRIGHT_CHANNEL_PREFIX", raising=False)
    monkeypatch.delenv("BOTWRIGHT_READY_TIMEOUT", raising=False)
    monkeypatch.delenv("BOTWRIGHT_DEFAULT_TIMEOUT", raising=False)
    monkeypatch.delenv("BOTWRIGHT_KEEP_CHANNELS", raising=False)


def test_config_loads_required_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BOTWRIGHT_TESTER_TOKEN", "tester-token")
    monkeypatch.setenv("BOTWRIGHT_GUILD_ID", "123")
    monkeypatch.setenv("BOTWRIGHT_TARGET_BOT_ID", "456")

    config = BotwrightConfig.from_env()

    assert config.tester_token == "tester-token"
    assert config.guild_id == 123
    assert config.target_bot_id == 456
    assert config.channel_id is None
    assert config.channel_prefix == "botwright-"
    assert config.ready_timeout == 30.0
    assert config.default_timeout == 10.0
    assert config.keep_channels == "never"


def test_config_applies_environment_options(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BOTWRIGHT_TESTER_TOKEN", "tester-token")
    monkeypatch.setenv("BOTWRIGHT_GUILD_ID", "123")
    monkeypatch.setenv("BOTWRIGHT_TARGET_BOT_ID", "456")
    monkeypatch.setenv("BOTWRIGHT_CHANNEL_ID", "789")
    monkeypatch.setenv("BOTWRIGHT_CHANNEL_PREFIX", "suite-")
    monkeypatch.setenv("BOTWRIGHT_READY_TIMEOUT", "7")
    monkeypatch.setenv("BOTWRIGHT_DEFAULT_TIMEOUT", "11")
    monkeypatch.setenv("BOTWRIGHT_KEEP_CHANNELS", "failed")

    config = BotwrightConfig.from_env()

    assert config.channel_id == 789
    assert config.channel_prefix == "suite-"
    assert config.ready_timeout == 7.0
    assert config.default_timeout == 11.0
    assert config.keep_channels == "failed"


def test_config_cli_overrides_environment_options(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("BOTWRIGHT_TESTER_TOKEN", "tester-token")
    monkeypatch.setenv("BOTWRIGHT_GUILD_ID", "123")
    monkeypatch.setenv("BOTWRIGHT_TARGET_BOT_ID", "456")
    monkeypatch.setenv("BOTWRIGHT_CHANNEL_ID", "789")
    monkeypatch.setenv("BOTWRIGHT_CHANNEL_PREFIX", "env-")
    monkeypatch.setenv("BOTWRIGHT_READY_TIMEOUT", "7")
    monkeypatch.setenv("BOTWRIGHT_DEFAULT_TIMEOUT", "11")
    monkeypatch.setenv("BOTWRIGHT_KEEP_CHANNELS", "failed")

    config = BotwrightConfig.from_env(
        channel_id=999,
        channel_prefix="cli-",
        ready_timeout=3.0,
        default_timeout=4.0,
        keep_channels="always",
    )

    assert config.channel_id == 999
    assert config.channel_prefix == "cli-"
    assert config.ready_timeout == 3.0
    assert config.default_timeout == 4.0
    assert config.keep_channels == "always"


def test_config_reports_missing_required_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("BOTWRIGHT_TESTER_TOKEN", raising=False)
    monkeypatch.delenv("BOTWRIGHT_GUILD_ID", raising=False)
    monkeypatch.delenv("BOTWRIGHT_TARGET_BOT_ID", raising=False)

    with pytest.raises(BotwrightConfigError) as excinfo:
        BotwrightConfig.from_env()

    message = str(excinfo.value)
    assert "BOTWRIGHT_TESTER_TOKEN" in message
    assert "BOTWRIGHT_GUILD_ID" in message
    assert "BOTWRIGHT_TARGET_BOT_ID" in message


def test_config_rejects_non_integer_ids(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BOTWRIGHT_TESTER_TOKEN", "tester-token")
    monkeypatch.setenv("BOTWRIGHT_GUILD_ID", "not-an-int")
    monkeypatch.setenv("BOTWRIGHT_TARGET_BOT_ID", "456")

    with pytest.raises(BotwrightConfigError, match="integer snowflakes"):
        BotwrightConfig.from_env()


def test_config_rejects_invalid_keep_channels(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("BOTWRIGHT_TESTER_TOKEN", "tester-token")
    monkeypatch.setenv("BOTWRIGHT_GUILD_ID", "123")
    monkeypatch.setenv("BOTWRIGHT_TARGET_BOT_ID", "456")
    monkeypatch.setenv("BOTWRIGHT_KEEP_CHANNELS", "sometimes")

    with pytest.raises(BotwrightConfigError, match="never, failed, always"):
        BotwrightConfig.from_env()
