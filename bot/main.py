import asyncio
import logging
import os
import sys
import discord
from discord.ext import commands
from bot.config import DISCORD_TOKEN
from bot.database import Database

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("bot")


class MultipurposeBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.members = True
        intents.message_content = True
        super().__init__(command_prefix="!", intents=intents)
        self.db = Database()

    async def setup_hook(self):
        # Load command cogs
        initial_extensions = [
            "commands.setup",
            "commands.moderation",
            "events.member_events",
            "events.message_tracking",
        ]

        for ext in initial_extensions:
            try:
                await self.load_extension(ext)
                logger.info(f"Loaded extension: {ext}")
            except Exception as e:
                logger.error(f"Failed to load extension {ext}: {e}")

        # Register tree error handler
        self.tree.on_error = self.on_app_command_error

        # Sync app commands
        try:
            synced = await self.tree.sync()
            logger.info(f"Synced {len(synced)} application slash command(s).")
        except Exception as e:
            logger.error(f"Failed to sync slash commands: {e}")

    async def on_ready(self):
        logger.info(f"Logged in successfully as {self.user} (ID: {self.user.id})")

    async def on_app_command_error(self, interaction: discord.Interaction, error: discord.app_commands.AppCommandError):
        logger.error(f"Application command error in {interaction.command}: {error}", exc_info=error)
        msg = "An unexpected error occurred while executing the command."
        if isinstance(error, discord.app_commands.MissingPermissions):
            msg = "You do not have the required permissions to perform this action."
        elif isinstance(error, discord.app_commands.BotMissingPermissions):
            msg = "The bot lacks the necessary permissions to execute this command."

        try:
            if interaction.response.is_done():
                await interaction.followup.send(msg, ephemeral=True)
            else:
                await interaction.response.send_message(msg, ephemeral=True)
        except Exception as e:
            logger.error(f"Failed to send error response to user: {e}")


def main():
    if not DISCORD_TOKEN or DISCORD_TOKEN == "your_bot_token_here":
        logger.error("DISCORD_TOKEN environment variable is missing or not set in .env!")
        logger.error("Please configure DISCORD_TOKEN in your .env file before running the bot.")
        sys.exit(1)

    bot = MultipurposeBot()
    try:
        bot.run(DISCORD_TOKEN)
    except Exception as e:
        logger.critical(f"Bot failed to launch: {e}")


if __name__ == "__main__":
    main()
