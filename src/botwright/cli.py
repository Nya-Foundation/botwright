from __future__ import annotations

import argparse
import asyncio

from .branding import BOTWRIGHT_BANNER
from .config import BotwrightConfig
from .exceptions import BotwrightConfigError
from .preflight import run_preflight


def main() -> int:
    parser = argparse.ArgumentParser(prog="botwright")
    subparsers = parser.add_subparsers(dest="command", required=True)

    check = subparsers.add_parser("check", help="Validate Discord configuration.")
    check.add_argument("--channel-id", type=int, default=None)
    check.add_argument("--channel-prefix", default=None)
    check.add_argument("--ready-timeout", type=float, default=None)
    check.add_argument("--timeout", type=float, default=None)
    check.add_argument(
        "--keep-channels",
        choices=("never", "failed", "always"),
        default=None,
    )
    check.add_argument("--no-banner", action="store_true", default=False)

    args = parser.parse_args()
    if args.command == "check":
        return _check(args)

    parser.error(f"unknown command: {args.command}")
    return 2


def _check(args: argparse.Namespace) -> int:
    if not args.no_banner:
        print(BOTWRIGHT_BANNER.rstrip())

    try:
        config = BotwrightConfig.from_env(
            channel_id=args.channel_id,
            channel_prefix=args.channel_prefix,
            ready_timeout=args.ready_timeout,
            default_timeout=args.timeout,
            keep_channels=args.keep_channels,
        )
        _emit_config(config)
        asyncio.run(run_preflight(config, _emit))
    except BotwrightConfigError as e:
        _emit(f"check failed: {e}")
        return 1

    _emit("check passed")
    return 0


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


if __name__ == "__main__":
    raise SystemExit(main())
