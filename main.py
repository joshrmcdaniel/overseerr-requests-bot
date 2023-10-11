import asyncio
import os

import discord
import sys
from discord.ext import commands

import loguru
from dotenv import load_dotenv


INTENTS = discord.Intents.default()
BOT = commands.Bot(command_prefix="?", case_insensitive=True, intents=INTENTS)
logger = loguru.logger
logger.remove()
logger.add(sys.stderr, level="TRACE")


def main():
    token = os.environ.get("DISCORD_TOKEN")
    assert token is not None, "No discord token specified"
    BOT.load_extension("overseerr")
    BOT.run(token)


@BOT.event
async def on_ready():
    await BOT.change_presence(
        activity=discord.Activity(
            type=discord.ActivityType.watching, name="For requests"
        )
    )


if __name__ == "__main__":
    load_dotenv()
    main()
