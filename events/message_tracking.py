import logging
import discord
from discord.ext import commands

logger = logging.getLogger(__name__)


class MessageTracking(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot:
            return

        if not message.guild:
            return

        db = self.bot.db
        db.update_latest_message_channel(message.guild.id, message.author.id, message.channel.id)


async def setup(bot):
    await bot.add_cog(MessageTracking(bot))
