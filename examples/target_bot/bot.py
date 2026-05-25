from __future__ import annotations

import os

import discord
from discord.ext import commands

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)


@bot.command()
async def ping(ctx: commands.Context[commands.Bot]) -> None:
    await ctx.send("pong")


@bot.command()
async def echo(ctx: commands.Context[commands.Bot], *, text: str) -> None:
    await ctx.send(text)


@bot.event
async def on_message(message: discord.Message) -> None:
    if bot.user is not None and message.author.id == bot.user.id:
        return
    if message.author.bot and os.getenv("TEST_MODE") != "1":
        return

    ctx = await bot.get_context(message)
    await bot.invoke(ctx)


def main() -> None:
    token = os.getenv("TARGET_BOT_TOKEN")
    if not token:
        raise RuntimeError("TARGET_BOT_TOKEN is required")
    bot.run(token)


if __name__ == "__main__":
    main()
