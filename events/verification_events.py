import logging
import discord
from discord.ext import commands

logger = logging.getLogger(__name__)


class VerificationEvents(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent):
        # Ignore bot's own reactions or reactions without guild_id
        if not payload.guild_id:
            return

        # Check emoji
        if str(payload.emoji) != "✅":
            return

        db = self.bot.db
        config = db.get_guild_config(payload.guild_id)
        if not config:
            return

        ver_channel_id = config.get("verification_channel_id")
        ver_msg_id = config.get("verification_message_id")
        verified_role_id = config.get("verified_role_id")
        unverified_role_id = config.get("unverified_role_id")

        if not ver_channel_id or not ver_msg_id or not verified_role_id or not unverified_role_id:
            return

        # Confirm channel and message match configuration
        if payload.channel_id != ver_channel_id or payload.message_id != ver_msg_id:
            return

        guild = self.bot.get_guild(payload.guild_id)
        if not guild:
            try:
                guild = await self.bot.fetch_guild(payload.guild_id)
            except Exception:
                return

        member = payload.member
        if not member:
            try:
                member = await guild.fetch_member(payload.user_id)
            except Exception:
                return

        # Ignore bots
        if member.bot:
            return

        verified_role = guild.get_role(verified_role_id)
        unverified_role = guild.get_role(unverified_role_id)

        if not verified_role or not unverified_role:
            logger.warning(f"Verification roles missing in guild {guild.id}")
            return

        bot_member = guild.me
        if bot_member and bot_member.top_role <= verified_role:
            logger.warning(f"Bot role hierarchy too low to assign Verified role in guild {guild.id}")
            return

        try:
            # Grant Verified role if not already assigned
            if verified_role not in member.roles:
                await member.add_roles(verified_role, reason="Completed verification")

            # Remove Unverified role if assigned
            if unverified_role in member.roles:
                await member.remove_roles(unverified_role, reason="Completed verification")
        except discord.Forbidden:
            logger.warning(f"Bot lacks permission to modify roles for member {member.id} in guild {guild.id}")
        except Exception as e:
            logger.error(f"Error verifying member {member.id} in guild {guild.id}: {e}")


async def setup(bot):
    await bot.add_cog(VerificationEvents(bot))
