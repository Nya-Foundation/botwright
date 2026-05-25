import asyncio


class BotwrightConfigError(Exception):
    pass


class BotwrightStartupError(Exception):
    pass


class BotwrightTimeout(asyncio.TimeoutError):
    pass
