import logging
import discord
from discord import app_commands
from discord.ext import commands

logger = logging.getLogger(__name__)


class Setup(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    setup_group = app_commands.Group(name="setup", description="Configure bot settings for this server")
    moderation_group = app_commands.Group(name="moderation", description="Configure moderation settings", parent=setup_group)

    @moderation_group.command(name="roles", description="Setup or refresh moderation roles")
    @app_commands.checks.has_permissions(administrator=True)
    async def setup_moderation_roles(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        guild = interaction.guild
        if not guild:
            await interaction.followup.send("This command can only be used in a server.", ephemeral=True)
            return

        db = self.bot.db
        config = db.get_guild_config(guild.id) or {}

        role_definitions = [
            ("owner_role_id", "Owner", discord.Color.gold()),
            ("staff_role_id", "Staff", discord.Color.blue()),
            ("trainee_role_id", "Trainee", discord.Color.light_grey()),
            ("moderator_role_id", "Moderator", discord.Color.green()),
            ("senior_mod_role_id", "Senior Mod", discord.Color.purple()),
        ]

        configured_roles = {}
        created_or_reused = []

        for key, name, color in role_definitions:
            role = None
            existing_id = config.get(key)

            if existing_id:
                role = guild.get_role(existing_id)

            if not role:
                # Find role by exact name if it exists in guild
                role = discord.utils.get(guild.roles, name=name)

            if not role:
                # Create the role if not found
                try:
                    role = await guild.create_role(name=name, color=color, reason="Bot setup moderation roles")
                    created_or_reused.append(f"Created role: **{role.name}**")
                except discord.Forbidden:
                    await interaction.followup.send(
                        "Error: Bot lacks 'Manage Roles' permission to create moderation roles.", ephemeral=True
                    )
                    return
                except Exception as e:
                    await interaction.followup.send(f"Error creating role '{name}': {e}", ephemeral=True)
                    return
            else:
                created_or_reused.append(f"Reused role: **{role.name}**")

            configured_roles[key] = role.id

        db.set_guild_roles(
            guild_id=guild.id,
            owner_role_id=configured_roles["owner_role_id"],
            staff_role_id=configured_roles["staff_role_id"],
            trainee_role_id=configured_roles["trainee_role_id"],
            moderator_role_id=configured_roles["moderator_role_id"],
            senior_mod_role_id=configured_roles["senior_mod_role_id"],
        )

        msg = "Moderation roles have been configured successfully:\n" + "\n".join(
            [f"• {line}" for line in created_or_reused]
        )
        await interaction.followup.send(msg, ephemeral=True)

    @moderation_group.command(name="logs", description="Setup or refresh moderation logs channel")
    @app_commands.checks.has_permissions(administrator=True)
    async def setup_moderation_logs(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        guild = interaction.guild
        if not guild:
            await interaction.followup.send("This command can only be used in a server.", ephemeral=True)
            return

        db = self.bot.db
        config = db.get_guild_config(guild.id) or {}
        existing_id = config.get("moderation_logs_channel_id")

        channel = None
        if existing_id:
            channel = guild.get_channel(existing_id)

        if not channel:
            channel = discord.utils.get(guild.text_channels, name="moderation-logs") or discord.utils.get(guild.text_channels, name="Moderation logs")

        if not channel:
            try:
                channel = await guild.create_text_channel(name="moderation-logs", reason="Bot setup moderation logs channel")
                msg = f"Created moderation logs channel: {channel.mention}"
            except discord.Forbidden:
                await interaction.followup.send(
                    "Error: Bot lacks 'Manage Channels' permission to create moderation logs channel.", ephemeral=True
                )
                return
            except Exception as e:
                await interaction.followup.send(f"Error creating moderation logs channel: {e}", ephemeral=True)
                return
        else:
            msg = f"Reused moderation logs channel: {channel.mention}"

        db.set_moderation_logs_channel(guild.id, channel.id)
        await interaction.followup.send(f"Moderation logs channel configured successfully. {msg}", ephemeral=True)

    @setup_group.command(name="join-leave", description="Set the channel for join and leave notifications")
    @app_commands.describe(channel="The channel where join/leave messages will be posted")
    @app_commands.checks.has_permissions(administrator=True)
    async def setup_join_leave(self, interaction: discord.Interaction, channel: discord.TextChannel):
        await interaction.response.defer(ephemeral=True)
        guild = interaction.guild
        if not guild:
            await interaction.followup.send("This command can only be used in a server.", ephemeral=True)
            return

        db = self.bot.db
        db.set_join_leave_channel(guild.id, channel.id)
        await interaction.followup.send(
            f"Join/leave notifications channel successfully set to {channel.mention}.", ephemeral=True
        )

    @setup_moderation_roles.error
    @setup_moderation_logs.error
    @setup_join_leave.error
    async def setup_error_handler(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        if isinstance(error, app_commands.MissingPermissions):
            msg = "You do not have Administrator permissions to run this setup command."
        else:
            msg = f"An error occurred during setup: {error}"

        if interaction.response.is_done():
            await interaction.followup.send(msg, ephemeral=True)
        else:
            await interaction.response.send_message(msg, ephemeral=True)


async def setup(bot):
    await bot.add_cog(Setup(bot))
