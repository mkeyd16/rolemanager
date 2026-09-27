import datetime
import logging
from typing import Optional, Any
import discord

logger = logging.getLogger(__name__)


def format_date(dt: Optional[datetime.datetime]) -> str:
    if not dt:
        return "Unknown"
    return dt.strftime("%d/%m/%Y")


def format_days_between(start_dt: datetime.datetime, end_dt: datetime.datetime) -> int:
    delta = end_dt - start_dt
    return max(0, delta.days)


async def send_mod_log(guild: Any, db: Any, content: Optional[str] = None, embed: Optional[discord.Embed] = None) -> bool:
    """
    Sends a message to the configured moderation log channel for the given guild.
    Gracefully handles missing configuration or deleted channels.
    """
    if not guild:
        return False

    config = db.get_guild_config(guild.id)
    if not config or not config.get("moderation_logs_channel_id"):
        return False

    channel_id = config["moderation_logs_channel_id"]
    channel = guild.get_channel(channel_id)
    if not channel:
        try:
            channel = await guild.fetch_channel(channel_id)
        except Exception as e:
            logger.warning(f"Could not fetch mod log channel {channel_id} for guild {guild.id}: {e}")
            return False

    try:
        if embed:
            await channel.send(content=content, embed=embed)
        else:
            await channel.send(content=content)
        return True
    except Exception as e:
        logger.warning(f"Failed to send mod log to channel {channel_id}: {e}")
        return False
