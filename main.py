import os

import discord
import shared
from dotenv import load_dotenv


load_dotenv()
logger = None


def init():
    """Validate env file and setup logging"""
    global logger
    logger = shared.get_logger()
    logger.info("Logging initialized.")
    logger.debug("Logging level set to {}", os.environ.get("LOG_LEVEL", "INFO"))
    logger.trace("Logging trace enabled.")
    logger.debug("Validating environment file.")
    assert os.environ.get("OVERSEERR_URL") is not None, "No overseerr url specified"
    assert (
        os.environ.get("OVERSEERR_API_KEY") is not None
    ), "No overseerr api key specified"
    logger.debug("Environment file validated.")


INTENTS = discord.Intents.default()
BOT = discord.Bot(
    debug_guilds=[int(os.environ.get("GUILD_ID"))],
    description="Manage requests for overseerr",
    indents=INTENTS,
)


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
    logger.success("Bot ready.")
    await BOT.change_presence(
        activity=discord.Activity(
            type=discord.ActivityType.watching, name="For requests"
        )
    )
    logger.debug("Bot presence set.")


if __name__ == "__main__":
    main()
