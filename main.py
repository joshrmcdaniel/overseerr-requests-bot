import os

import discord
from dotenv import load_dotenv
import logging


load_dotenv()
log = None


def init():
    """Validate env file and setup logging"""
    global log
    log_level = os.environ.get("LOG_LEVEL", "INFO")
    assert log_level in [
        "TRACE",
        "DEBUG",
        "INFO",
        "WARNING",
        "ERROR",
        "CRITICAL",
    ], "Invalid log level specified"
    log = setup_logging()
    log.debug("Validating environment file.")
    assert os.environ.get("OVERSEERR_URL") is not None, "No overseerr url specified"
    assert (
        os.environ.get("OVERSEERR_API_KEY") is not None
    ), "No overseerr api key specified"
    log.debug("Environment file validated.")


INTENTS = discord.Intents.default()
BOT = discord.Bot(
    debug_guilds=[int(os.environ.get("GUILD_ID"))],
    description="Manage requests for overseerr",
    indents=INTENTS,
)

from functools import partial, partialmethod


def setup_logging():
    log = logging.getLogger()
    logging.TRACE = 5
    logging.addLevelName(logging.TRACE, "TRACE")
    logging.Logger.trace = partialmethod(logging.Logger.log, logging.TRACE)
    logging.trace = partial(logging.log, logging.TRACE)

    log_level = os.environ.get("LOG_LEVEL", "INFO")
    log.setLevel(log_level)
    handler = logging.StreamHandler()
    handler.setLevel(log_level)
    formatter = logging.Formatter(
        "[{asctime}] [{levelname}] [{name}] {message}", style="{"
    )
    handler.setFormatter(formatter)
    log.addHandler(handler)
    logging.getLogger("discord").setLevel("ERROR")
    log.info("Logging initialized.")
    log.info("Log level set to %s", log_level)
    log.trace("Logging trace enabled.")
    return log


def main():
    init()
    token = os.environ.get("DISCORD_TOKEN")
    assert token is not None, "No discord token specified"
    BOT.load_extension(
        "overseerr",
    )
    BOT.run(token)


@BOT.event
async def on_ready():
    log.info("Bot ready.")
    await BOT.change_presence(
        activity=discord.Activity(
            type=discord.ActivityType.watching, name="For requests"
        )
    )
    log.debug("Bot presence set.")


if __name__ == "__main__":
    main()
