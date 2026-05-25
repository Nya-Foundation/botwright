from types import SimpleNamespace

import pytest

from botwright.config import BotwrightConfig
from botwright.exceptions import BotwrightConfigError
from botwright.fixtures import _node_channel_id
from botwright.runtime import tester_channel_permissions as channel_permissions


def config(channel_id: int | None = None) -> BotwrightConfig:
    return BotwrightConfig(
        tester_token="token",
        guild_id=1,
        target_bot_id=2,
        channel_id=channel_id,
    )


def request_with_marker(**kwargs: object) -> SimpleNamespace:
    marker = SimpleNamespace(kwargs=kwargs)
    node = SimpleNamespace(get_closest_marker=lambda name: marker)
    return SimpleNamespace(node=node)


def request_without_marker() -> SimpleNamespace:
    node = SimpleNamespace(get_closest_marker=lambda name: None)
    return SimpleNamespace(node=node)


def test_node_channel_id_defaults_to_config_channel() -> None:
    assert _node_channel_id(request_without_marker(), config(channel_id=123)) == 123


def test_node_channel_id_marker_overrides_config_channel() -> None:
    assert _node_channel_id(request_with_marker(channel_id="456"), config(123)) == 456


def test_node_channel_id_rejects_invalid_marker_value() -> None:
    with pytest.raises(BotwrightConfigError, match="channel_id"):
        _node_channel_id(request_with_marker(channel_id="not-a-channel"), config())


def test_tester_channel_permissions_depend_on_channel_ownership() -> None:
    assert channel_permissions(created_channel=True) == (
        "view_channel",
        "send_messages",
        "read_message_history",
        "manage_channels",
    )
    assert channel_permissions(created_channel=False) == (
        "view_channel",
        "send_messages",
        "read_message_history",
    )
