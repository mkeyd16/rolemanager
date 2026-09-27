import datetime
import logging
from typing import Literal, Optional
import discord
from discord import app_commands
from discord.ext import commands

from bot.config import (
    RANK_NONE,
    RANK_TRAINEE,
    RANK_MODERATOR,
    RANK_SENIOR_MOD,
    RANK_OWNER,
    RANK_NAMES,
    PUNISHMENT_DURATIONS,
    ALLOWED_SEVERITIES,
)
from bot.checks import get_member_staff_rank, can_moderate, is_staff
from bot.utils import send_mod_log

logger = logging.getLogger(__name__)


class Moderation(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="warn", description="Warn a user in their last active channel")
    @app_commands.describe(user="The user to warn", reason="Reason for the warning")
    async def warn(self, interaction: discord.Interaction, user: discord.Member, reason: str):
        await interaction.response.defer(ephemeral=True)
        guild = interaction.guild
        if not guild:
            await interaction.followup.send("This command can only be used in a server.", ephemeral=True)
            return

        db = self.bot.db
        config = db.get_guild_config(guild.id)
        if not config:
            await interaction.followup.send("Server is not configured. An administrator must run `/setup` first.", ephemeral=True)
            return

        actor = interaction.user
        actor_rank = get_member_staff_rank(actor, config)

        if actor_rank < RANK_TRAINEE:
            await interaction.followup.send("You do not have permission to warn users.", ephemeral=True)
            return

        allowed, hierarchy_reason = can_moderate(actor, user, config)
        if not allowed:
            await interaction.followup.send(hierarchy_reason, ephemeral=True)
            return

        channel_id = db.get_latest_message_channel(guild.id, user.id)
        if not channel_id:
            await interaction.followup.send(
                f"Could not determine {user.mention}'s last active message channel. The user has no recorded messages.",
                ephemeral=True,
            )
            return

        channel = guild.get_channel(channel_id)
        if not channel:
            try:
                channel = await guild.fetch_channel(channel_id)
            except Exception:
                channel = None

        if not channel:
            await interaction.followup.send(
                f"The target user's last active channel (ID: {channel_id}) is no longer accessible.",
                ephemeral=True,
            )
            return

        warn_text = f"{user.mention} has received a warning: {reason}"
        try:
            await channel.send(warn_text)
        except discord.Forbidden:
            await interaction.followup.send(f"Bot lacks permission to send messages in {channel.mention}.", ephemeral=True)
            return
        except Exception as e:
            await interaction.followup.send(f"Failed to send warning message: {e}", ephemeral=True)
            return

        now = datetime.datetime.now(datetime.timezone.utc)
        embed = discord.Embed(
            title="Moderation Action: WARN",
            color=discord.Color.gold(),
            timestamp=now,
        )
        embed.add_field(name="Target", value=f"{user.mention} (`{user.id}`)", inline=True)
        embed.add_field(name="Moderator", value=f"{actor.mention} (`{actor.id}`)", inline=True)
        embed.add_field(name="Moderator Rank", value=RANK_NAMES.get(actor_rank, "Unknown"), inline=True)
        embed.add_field(name="Channel", value=channel.mention, inline=True)
        embed.add_field(name="Reason", value=reason, inline=False)

        await send_mod_log(guild, db, embed=embed)
        await interaction.followup.send(f"Warning issued to {user.mention} in {channel.mention}.", ephemeral=True)

    @app_commands.command(name="punish", description="Issue a timeout punishment to a user")
    @app_commands.describe(
        user="The user to punish",
        severity="Severity level: minor (10m), moderate (45m), major (48h)",
        reason="Reason for punishment",
    )
    async def punish(
        self,
        interaction: discord.Interaction,
        user: discord.Member,
        severity: Literal["minor", "moderate", "major"],
        reason: str,
    ):
        await interaction.response.defer(ephemeral=True)
        guild = interaction.guild
        if not guild:
            await interaction.followup.send("This command can only be used in a server.", ephemeral=True)
            return

        db = self.bot.db
        config = db.get_guild_config(guild.id)
        if not config:
            await interaction.followup.send("Server is not configured. An administrator must run `/setup` first.", ephemeral=True)
            return

        actor = interaction.user
        actor_rank = get_member_staff_rank(actor, config)

        if actor_rank < RANK_TRAINEE:
            await interaction.followup.send("You do not have permission to punish users.", ephemeral=True)
            return

        # Check severity permission before attempting timeout
        allowed_severities = ALLOWED_SEVERITIES.get(actor_rank, [])
        if severity not in allowed_severities:
            await interaction.followup.send(
                f"You do not have sufficient staff rank ({RANK_NAMES[actor_rank]}) to issue a '{severity}' punishment.",
                ephemeral=True,
            )
            return

        allowed, hierarchy_reason = can_moderate(actor, user, config)
        if not allowed:
            await interaction.followup.send(hierarchy_reason, ephemeral=True)
            return

        seconds = PUNISHMENT_DURATIONS[severity]
        duration = datetime.timedelta(seconds=seconds)

        try:
            await user.timeout(duration, reason=f"[{severity.upper()}] {reason}")
        except discord.Forbidden:
            await interaction.followup.send(
                f"Failed to timeout {user.mention}. The bot lacks required permissions or role hierarchy advantage.",
                ephemeral=True,
            )
            return
        except Exception as e:
            await interaction.followup.send(f"Failed to apply punishment: {e}", ephemeral=True)
            return

        rank_name = RANK_NAMES.get(actor_rank, "Moderator")

        if severity == "minor":
            response_msg = f"{user.mention} has been punished by {actor.mention}, {rank_name}, for a minor offense. A 10-minute timeout has been applied. Reason: {reason}"
        elif severity == "moderate":
            response_msg = f"{user.mention} has been punished by {actor.mention}, {rank_name}, for a moderate offense. A 45-minute timeout has been applied. Reason: {reason}"
        else:  # major
            response_msg = f"{user.mention} has been issued a 48-hour timeout by {actor.mention}, {rank_name}, for a major offense. For further information regarding this action, please contact the server owner. Reason: {reason}"

        now = datetime.datetime.now(datetime.timezone.utc)
        embed = discord.Embed(
            title=f"Moderation Action: PUNISH ({severity.upper()})",
            color=discord.Color.red(),
            timestamp=now,
        )
        embed.add_field(name="Target", value=f"{user.mention} (`{user.id}`)", inline=True)
        embed.add_field(name="Moderator", value=f"{actor.mention} (`{actor.id}`)", inline=True)
        embed.add_field(name="Moderator Rank", value=rank_name, inline=True)
        embed.add_field(name="Severity", value=severity.capitalize(), inline=True)
        embed.add_field(name="Duration", value=f"{seconds // 60} minutes" if seconds < 86400 else f"{seconds // 3600} hours", inline=True)
        embed.add_field(name="Reason", value=reason, inline=False)

        await send_mod_log(guild, db, embed=embed)
        await interaction.followup.send(response_msg, ephemeral=False)

    @app_commands.command(name="hire", description="Hire a user as a Trainee (Owner only)")
    @app_commands.describe(user="The user to hire")
    async def hire(self, interaction: discord.Interaction, user: discord.Member):
        await interaction.response.defer(ephemeral=True)
        guild = interaction.guild
        if not guild:
            await interaction.followup.send("This command can only be used in a server.", ephemeral=True)
            return

        db = self.bot.db
        config = db.get_guild_config(guild.id)
        if not config:
            await interaction.followup.send("Server is not configured. An administrator must run `/setup` first.", ephemeral=True)
            return

        actor = interaction.user
        actor_rank = get_member_staff_rank(actor, config)
        if actor_rank < RANK_OWNER:
            await interaction.followup.send("Only the Server Owner can use `/hire`.", ephemeral=True)
            return

        if is_staff(user, config) or get_member_staff_rank(user, config) > RANK_NONE:
            await interaction.followup.send(f"{user.mention} is already a staff member.", ephemeral=True)
            return

        staff_role_id = config.get("staff_role_id")
        trainee_role_id = config.get("trainee_role_id")

        if not staff_role_id or not trainee_role_id:
            await interaction.followup.send("Staff or Trainee role is not configured. Run `/setup moderation roles`.", ephemeral=True)
            return

        staff_role = guild.get_role(staff_role_id)
        trainee_role = guild.get_role(trainee_role_id)

        if not staff_role or not trainee_role:
            await interaction.followup.send("Configured Staff/Trainee role no longer exists in the server.", ephemeral=True)
            return

        roles_to_add = [role for role in [staff_role, trainee_role] if role not in user.roles]

        try:
            if roles_to_add:
                await user.add_roles(*roles_to_add, reason=f"Hired by {actor}")
        except discord.Forbidden:
            await interaction.followup.send("Bot lacks permission to add roles to this user.", ephemeral=True)
            return
        except Exception as e:
            await interaction.followup.send(f"Failed to assign staff roles: {e}", ephemeral=True)
            return

        now = datetime.datetime.now(datetime.timezone.utc)
        embed = discord.Embed(
            title="Staff Action: HIRE",
            color=discord.Color.blue(),
            timestamp=now,
        )
        embed.add_field(name="Target", value=f"{user.mention} (`{user.id}`)", inline=True)
        embed.add_field(name="Hired By", value=f"{actor.mention} (`{actor.id}`)", inline=True)
        embed.add_field(name="Previous Status", value="Member", inline=True)
        embed.add_field(name="New Status", value="Trainee", inline=True)

        await send_mod_log(guild, db, embed=embed)
        await interaction.followup.send(f"{user.mention} has been hired as a Trainee.", ephemeral=True)

    @app_commands.command(name="promote", description="Promote a staff member to the next rank (Owner only)")
    @app_commands.describe(user="The staff member to promote")
    async def promote(self, interaction: discord.Interaction, user: discord.Member):
        await interaction.response.defer(ephemeral=True)
        guild = interaction.guild
        if not guild:
            await interaction.followup.send("This command can only be used in a server.", ephemeral=True)
            return

        db = self.bot.db
        config = db.get_guild_config(guild.id)
        if not config:
            await interaction.followup.send("Server is not configured. An administrator must run `/setup` first.", ephemeral=True)
            return

        actor = interaction.user
        actor_rank = get_member_staff_rank(actor, config)
        if actor_rank < RANK_OWNER:
            await interaction.followup.send("Only the Server Owner can use `/promote`.", ephemeral=True)
            return

        current_rank = get_member_staff_rank(user, config)
        if current_rank == RANK_NONE:
            await interaction.followup.send(f"{user.mention} is not a staff member or has no valid moderation rank.", ephemeral=True)
            return

        if current_rank == RANK_SENIOR_MOD:
            await interaction.followup.send(f"{user.mention} is already a Senior Mod. There is no higher moderation rank.", ephemeral=True)
            return

        if current_rank == RANK_TRAINEE:
            old_role_id = config.get("trainee_role_id")
            new_role_id = config.get("moderator_role_id")
            new_rank_name = "Moderator"
        elif current_rank == RANK_MODERATOR:
            old_role_id = config.get("moderator_role_id")
            new_role_id = config.get("senior_mod_role_id")
            new_rank_name = "Senior Mod"
        else:
            await interaction.followup.send(f"Cannot promote user with current rank: {RANK_NAMES.get(current_rank)}", ephemeral=True)
            return

        if not new_role_id:
            await interaction.followup.send(f"{new_rank_name} role is not configured. Run `/setup moderation roles`.", ephemeral=True)
            return

        new_role = guild.get_role(new_role_id)
        if not new_role:
            await interaction.followup.send(f"Configured {new_rank_name} role no longer exists in the server.", ephemeral=True)
            return

        old_role = guild.get_role(old_role_id) if old_role_id else None

        staff_role_id = config.get("staff_role_id")
        staff_role = guild.get_role(staff_role_id) if staff_role_id else None

        try:
            if old_role and old_role in user.roles:
                await user.remove_roles(old_role, reason=f"Promoted to {new_rank_name} by {actor}")
            if new_role not in user.roles:
                await user.add_roles(new_role, reason=f"Promoted to {new_rank_name} by {actor}")
            if staff_role and staff_role not in user.roles:
                await user.add_roles(staff_role, reason=f"Ensure staff role for {actor}")
        except discord.Forbidden:
            await interaction.followup.send("Bot lacks permission to modify roles for this user.", ephemeral=True)
            return
        except Exception as e:
            await interaction.followup.send(f"Failed to promote user: {e}", ephemeral=True)
            return

        old_rank_name = RANK_NAMES.get(current_rank, "Unknown")
        now = datetime.datetime.now(datetime.timezone.utc)
        embed = discord.Embed(
            title="Staff Action: PROMOTION",
            color=discord.Color.green(),
            timestamp=now,
        )
        embed.add_field(name="Target", value=f"{user.mention} (`{user.id}`)", inline=True)
        embed.add_field(name="Promoted By", value=f"{actor.mention} (`{actor.id}`)", inline=True)
        embed.add_field(name="Previous Rank", value=old_rank_name, inline=True)
        embed.add_field(name="New Rank", value=new_rank_name, inline=True)

        await send_mod_log(guild, db, embed=embed)
        await interaction.followup.send(f"{user.mention} has been promoted from {old_rank_name} to {new_rank_name}.", ephemeral=True)

    @app_commands.command(name="fire", description="Remove a user's staff status (Owner only)")
    @app_commands.describe(user="The staff member to fire")
    async def fire(self, interaction: discord.Interaction, user: discord.Member):
        await interaction.response.defer(ephemeral=True)
        guild = interaction.guild
        if not guild:
            await interaction.followup.send("This command can only be used in a server.", ephemeral=True)
            return

        db = self.bot.db
        config = db.get_guild_config(guild.id)
        if not config:
            await interaction.followup.send("Server is not configured. An administrator must run `/setup` first.", ephemeral=True)
            return

        actor = interaction.user
        actor_rank = get_member_staff_rank(actor, config)
        if actor_rank < RANK_OWNER:
            await interaction.followup.send("Only the Server Owner can use `/fire`.", ephemeral=True)
            return

        current_rank = get_member_staff_rank(user, config)
        if current_rank == RANK_NONE and not is_staff(user, config):
            await interaction.followup.send(f"{user.mention} is not a staff member.", ephemeral=True)
            return

        staff_roles_ids = [
            config.get("staff_role_id"),
            config.get("trainee_role_id"),
            config.get("moderator_role_id"),
            config.get("senior_mod_role_id"),
        ]

        roles_to_remove = [
            role for role in user.roles
            if role.id in staff_roles_ids and role.id is not None
        ]

        try:
            if roles_to_remove:
                await user.remove_roles(*roles_to_remove, reason=f"Fired by {actor}")
        except discord.Forbidden:
            await interaction.followup.send("Bot lacks permission to remove roles from this user.", ephemeral=True)
            return
        except Exception as e:
            await interaction.followup.send(f"Failed to remove staff status: {e}", ephemeral=True)
            return

        prev_rank_name = RANK_NAMES.get(current_rank, "Staff")
        now = datetime.datetime.now(datetime.timezone.utc)
        embed = discord.Embed(
            title="Staff Action: FIRE",
            color=discord.Color.dark_red(),
            timestamp=now,
        )
        embed.add_field(name="Target", value=f"{user.mention} (`{user.id}`)", inline=True)
        embed.add_field(name="Fired By", value=f"{actor.mention} (`{actor.id}`)", inline=True)
        embed.add_field(name="Previous Rank", value=prev_rank_name, inline=True)

        await send_mod_log(guild, db, embed=embed)
        await interaction.followup.send(f"{user.mention} has been removed from the staff team.", ephemeral=True)


async def setup(bot):
    await bot.add_cog(Moderation(bot))
