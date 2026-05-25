from __future__ import annotations

import asyncio
from typing import Any

import pytest

from .branding import BOTWRIGHT_BANNER
from .config import BotwrightConfig
from .exceptions import BotwrightConfigError
from .fixtures import botwright_config, session, test_channel, tester_bot
from .preflight import run_preflight

__all__ = ["botwright_config", "session", "test_channel", "tester_bot"]

_BOTWRIGHT_FIXTURES = {"botwright_config", "tester_bot", "test_channel", "session"}


def pytest_addoption(parser: pytest.Parser) -> None:
    group = parser.getgroup("botwright")
    group.addoption(
        "--botwright-no-banner",
        action="store_true",
        default=False,
        help="Do not print the Botwright ASCII banner.",
    )
    group.addoption(
        "--botwright-check",
        action="store_true",
        default=False,
        help="Validate Botwright Discord configuration and exit without running tests.",
    )
    group.addoption(
        "--botwright-channel-id",
        action="store",
        type=int,
        default=None,
        help="Existing Discord text channel ID to use instead of creating temporary channels.",
    )
    group.addoption(
        "--botwright-channel-prefix",
        action="store",
        default=None,
        help="Prefix for temporary Discord channels.",
    )
    group.addoption(
        "--botwright-ready-timeout",
        action="store",
        type=float,
        default=None,
        help="Seconds to wait for the tester bot to become ready.",
    )
    group.addoption(
        "--botwright-timeout",
        action="store",
        type=float,
        default=None,
        help="Default seconds to wait for Botwright message expectations.",
    )
    group.addoption(
        "--botwright-keep-channels",
        action="store",
        choices=("never", "failed", "always"),
        default=None,
        help="Keep temporary Discord channels never, on failed tests, or always.",
    )


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers",
        "botwright(timeout=None, keep_channel=None, channel_id=None): "
        "configure a Botwright e2e test.",
    )


def pytest_cmdline_main(config: pytest.Config) -> int | None:
    if not config.getoption("--botwright-check"):
        return None

    if not config.getoption("--botwright-no-banner"):
        print(BOTWRIGHT_BANNER.rstrip())
    try:
        cfg = _config_from_pytest(config)
        _emit_config(cfg)
        asyncio.run(run_preflight(cfg, _emit))
    except BotwrightConfigError as e:
        _emit(f"check failed: {e}")
        return 1

    _emit("check passed")
    return 0


def _uses_botwright_fixture(item: pytest.Item) -> bool:
    # Pytest has no public API for "does this collected item resolve to this
    # plugin's fixture implementation?". This private fixture graph inspection
    # keeps Botwright's session-loop handling automatic for users.
    fixtureinfo = getattr(item, "_fixtureinfo", None)
    fixturedefs_by_name: dict[str, Any] = getattr(fixtureinfo, "name2fixturedefs", {})

    for name in _BOTWRIGHT_FIXTURES:
        fixturedefs = fixturedefs_by_name.get(name) or ()
        for fixturedef in fixturedefs:
            fixture_func = getattr(fixturedef, "func", None)
            if getattr(fixture_func, "__module__", None) == "botwright.fixtures":
                return True

    return False


def _config_from_pytest(config: pytest.Config) -> BotwrightConfig:
    return BotwrightConfig.from_env(
        channel_id=config.getoption("--botwright-channel-id"),
        channel_prefix=config.getoption("--botwright-channel-prefix"),
        ready_timeout=config.getoption("--botwright-ready-timeout"),
        default_timeout=config.getoption("--botwright-timeout"),
        keep_channels=config.getoption("--botwright-keep-channels"),
    )


def _emit(message: str) -> None:
    print(f"[botwright] {message}", flush=True)


def _emit_config(config: BotwrightConfig) -> None:
    _emit(
        f"config loaded: guild_id={config.guild_id}, "
        f"target_bot_id={config.target_bot_id}, "
        f"channel_id={config.channel_id}, "
        f"default_timeout={config.default_timeout}, "
        f"keep_channels={config.keep_channels}"
    )


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    for item in items:
        if _uses_botwright_fixture(item):
            marker = item.get_closest_marker("asyncio")
            if marker is not None:
                loop_scope = marker.kwargs.get("loop_scope")
                if loop_scope == "session":
                    continue
                if loop_scope is not None:
                    raise pytest.UsageError(
                        "Botwright tests must use pytest.mark.asyncio(loop_scope='session') "
                        "because the Discord client is session-scoped."
                    )
            item.add_marker(pytest.mark.asyncio(loop_scope="session"), append=False)


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(
    item: pytest.Item,
    call: pytest.CallInfo[None],
) -> Any:
    outcome = yield
    report = outcome.get_result()
    setattr(item, f"_botwright_report_{report.when}", report)
