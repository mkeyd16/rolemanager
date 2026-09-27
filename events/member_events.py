import datetime
import logging
import discord
from discord.ext import commands
from bot.utils import format_date, format_days_between

logger = logging.getLogger(__name__)


class MemberEvents(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        guild = member.guild
        if not guild:
            return

        db = self.bot.db
        now = datetime.datetime.now(datetime.timezone.utc)
        join_ts = member.joined_at.timestamp() if member.joined_at else now.timestamp()

        # Store join date in database
        db.record_user_join(guild.id, member.id, join_ts)

        config = db.get_guild_config(guild.id)
        if not config or not config.get("join_leave_channel_id"):
            return

        channel_id = config["join_leave_channel_id"]
        channel = guild.get_channel(channel_id)
        if not channel:
            try:
                channel = await guild.fetch_channel(channel_id)
            except Exception:
                return

        created_at = member.created_at
        account_age = format_days_between(created_at, now) if created_at else "Unknown"
        join_date_str = format_date(member.joined_at or now)

        msg = (
            f"**User has joined the server.**\n"
            f"@{member.name} ({member.display_name})\n"
            f"Account age: {account_age} days\n"
            f"Join date: {join_date_str}"
        )

        try:
            await channel.send(msg)
        except Exception as e:
            logger.warning(f"Failed to send join message in guild {guild.id}: {e}")

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        guild = member.guild
        if not guild:
            return

        db = self.bot.db
        now = datetime.datetime.now(datetime.timezone.utc)

        join_ts = db.get_user_join_timestamp(guild.id, member.id)
        join_dt = None
        if join_ts:
            join_dt = datetime.datetime.fromtimestamp(join_ts, tz=datetime.timezone.utc)
        elif member.joined_at:
            join_dt = member.joined_at

        if join_dt:
            join_date_str = format_date(join_dt)
            time_in_server = f"{format_days_between(join_dt, now)} days"
        else:
            join_date_str = "Unknown"
            time_in_server = "Unknown"

        leave_date_str = format_date(now)

        config = db.get_guild_config(guild.id)
        if not config or not config.get("join_leave_channel_id"):
            return

        channel_id = config["join_leave_channel_id"]
        channel = guild.get_channel(channel_id)
        if not channel:
            try:
                channel = await guild.fetch_channel(channel_id)
            except Exception:
                return

        msg = (
            f"**User has left the server.**\n"
            f"@{member.name} ({member.display_name})\n"
            f"Join date: {join_date_str}\n"
            f"Leave date: {leave_date_str}\n"
            f"Time in server: {time_in_server}"
        )

        try:
            await channel.send(msg)
        except Exception as e:
            logger.warning(f"Failed to send leave message in guild {guild.id}: {e}")


async def setup(bot):
    await bot.add_cog(MemberEvents(bot))
