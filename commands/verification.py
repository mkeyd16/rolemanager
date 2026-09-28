import logging
import discord
from discord import app_commands
from discord.ext import commands

logger = logging.getLogger(__name__)


class Verification(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    verification_group = app_commands.Group(name="verification", description="Configure verification system")
    channel_group = app_commands.Group(name="channel", description="Verification channel configuration", parent=verification_group)

    @channel_group.command(name="setup", description="Setup or refresh the server verification system")
    @app_commands.checks.has_permissions(administrator=True)
    async def verification_channel_setup(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        guild = interaction.guild
        if not guild:
            await interaction.followup.send("This command can only be used in a server.", ephemeral=True)
            return

        bot_member = guild.me
        if not bot_member:
            await interaction.followup.send("Error: Bot member details not found in guild.", ephemeral=True)
            return

        # Check required bot permissions
        required_perms = [
            ("manage_roles", "Manage Roles"),
            ("manage_channels", "Manage Channels"),
            ("view_channel", "View Channels"),
            ("send_messages", "Send Messages"),
            ("embed_links", "Embed Links"),
            ("add_reactions", "Add Reactions"),
        ]
        missing_perms = [
            name for flag, name in required_perms if not getattr(bot_member.guild_permissions, flag, False)
        ]
        if missing_perms:
            await interaction.followup.send(
                f"Error: Bot lacks required Discord permission(s): {', '.join(missing_perms)}.",
                ephemeral=True,
            )
            return

        db = self.bot.db
        config = db.get_guild_config(guild.id) or {}

        # 1. Reuse or create Verified role
        verified_role = None
        verified_role_id = config.get("verified_role_id")
        if verified_role_id:
            verified_role = guild.get_role(verified_role_id)
        if not verified_role:
            verified_role = discord.utils.get(guild.roles, name="Verified")
        if not verified_role:
            try:
                verified_role = await guild.create_role(name="Verified", color=discord.Color.blue(), reason="Verification setup")
            except discord.Forbidden:
                await interaction.followup.send("Error: Bot lacks permission to create the Verified role.", ephemeral=True)
                return
            except Exception as e:
                await interaction.followup.send(f"Error creating Verified role: {e}", ephemeral=True)
                return

        # 2. Reuse or create Unverified role
        unverified_role = None
        unverified_role_id = config.get("unverified_role_id")
        if unverified_role_id:
            unverified_role = guild.get_role(unverified_role_id)
        if not unverified_role:
            unverified_role = discord.utils.get(guild.roles, name="Unverified")
        if not unverified_role:
            try:
                unverified_role = await guild.create_role(name="Unverified", color=discord.Color.light_grey(), reason="Verification setup")
            except discord.Forbidden:
                await interaction.followup.send("Error: Bot lacks permission to create the Unverified role.", ephemeral=True)
                return
            except Exception as e:
                await interaction.followup.send(f"Error creating Unverified role: {e}", ephemeral=True)
                return

        # Check role hierarchy
        if bot_member.top_role <= verified_role or bot_member.top_role <= unverified_role:
            await interaction.followup.send(
                "Error: Bot role hierarchy is lower than or equal to Verified or Unverified roles. Cannot manage roles.",
                ephemeral=True,
            )
            return

        # 3. Reuse or create verification channel
        verification_channel = None
        verification_channel_id = config.get("verification_channel_id")
        if verification_channel_id:
            verification_channel = guild.get_channel(verification_channel_id)
        if not verification_channel:
            verification_channel = discord.utils.get(guild.text_channels, name="verification")
        if not verification_channel:
            try:
                verification_channel = await guild.create_text_channel(name="verification", reason="Verification setup")
            except discord.Forbidden:
                await interaction.followup.send("Error: Bot lacks permission to create the verification channel.", ephemeral=True)
                return
            except Exception as e:
                await interaction.followup.send(f"Error creating verification channel: {e}", ephemeral=True)
                return

        # 4. Apply channel permission overwrites
        try:
            for ch in guild.channels:
                if ch.id == verification_channel.id:
                    await ch.set_permissions(unverified_role, view_channel=True, read_message_history=True, reason="Verification setup")
                    await ch.set_permissions(verified_role, view_channel=True, read_message_history=True, reason="Verification setup")
                else:
                    await ch.set_permissions(unverified_role, view_channel=False, reason="Verification setup")
                    await ch.set_permissions(verified_role, view_channel=True, reason="Verification setup")
        except discord.Forbidden:
            await interaction.followup.send("Error: Bot lacks permission to set channel permission overwrites.", ephemeral=True)
            return
        except Exception as e:
            await interaction.followup.send(f"Error setting channel permissions: {e}", ephemeral=True)
            return

        # 5. Handle existing human members
        for member in guild.members:
            if member.bot:
                continue
            if unverified_role in member.roles:
                continue
            if verified_role not in member.roles:
                try:
                    await member.add_roles(verified_role, reason="Initial verification setup for existing member")
                except Exception as e:
                    logger.warning(f"Failed to assign Verified role to {member}: {e}")

        # 6. Setup or reuse verification message
        verification_msg = None
        verification_msg_id = config.get("verification_message_id")
        if verification_msg_id and verification_channel_id == verification_channel.id:
            try:
                verification_msg = await verification_channel.fetch_message(verification_msg_id)
            except Exception:
                verification_msg = None

        if not verification_msg:
            embed = discord.Embed(
                title="Server Verification",
                description=(
                    "Welcome to the server.\n\n"
                    "Access to the remainder of this server is restricted to verified members.\n\n"
                    "To complete verification, please react to this message with ✅. "
                    "Once completed, your access will be updated automatically."
                ),
                color=discord.Color.blue(),
            )
            try:
                verification_msg = await verification_channel.send(embed=embed)
                await verification_msg.add_reaction("✅")
            except discord.Forbidden:
                await interaction.followup.send("Error: Bot lacks permission to send messages or add reactions in the verification channel.", ephemeral=True)
                return
            except Exception as e:
                await interaction.followup.send(f"Error sending verification message: {e}", ephemeral=True)
                return

        # Store IDs in SQLite
        db.set_verification_config(
            guild_id=guild.id,
            verification_channel_id=verification_channel.id,
            verified_role_id=verified_role.id,
            unverified_role_id=unverified_role.id,
            verification_message_id=verification_msg.id,
        )

        await interaction.followup.send(
            f"Verification system successfully configured!\n"
            f"• Channel: {verification_channel.mention}\n"
            f"• Verified Role: {verified_role.mention}\n"
            f"• Unverified Role: {unverified_role.mention}",
            ephemeral=True,
        )

    @app_commands.command(name="rehide", description="Reapply verification visibility rules across all current channels")
    @app_commands.checks.has_permissions(administrator=True)
    async def rehide(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        guild = interaction.guild
        if not guild:
            await interaction.followup.send("This command can only be used in a server.", ephemeral=True)
            return

        db = self.bot.db
        config = db.get_guild_config(guild.id) or {}

        ver_channel_id = config.get("verification_channel_id")
        verified_role_id = config.get("verified_role_id")
        unverified_role_id = config.get("unverified_role_id")

        if not ver_channel_id or not verified_role_id or not unverified_role_id:
            await interaction.followup.send("Verification system is not configured. Please run `/verification channel setup` first.", ephemeral=True)
            return

        ver_channel = guild.get_channel(ver_channel_id)
        verified_role = guild.get_role(verified_role_id)
        unverified_role = guild.get_role(unverified_role_id)

        if not verified_role or not unverified_role:
            await interaction.followup.send("Configured verification roles no longer exist. Please re-run `/verification channel setup`.", ephemeral=True)
            return

        bot_member = guild.me
        if bot_member and not getattr(bot_member.guild_permissions, "manage_channels", False):
            await interaction.followup.send("Error: Bot lacks 'Manage Channels' permission.", ephemeral=True)
            return

        updated_count = 0
        try:
            for ch in guild.channels:
                if ver_channel and ch.id == ver_channel.id:
                    await ch.set_permissions(unverified_role, view_channel=True, read_message_history=True, reason="Rehide verification rules")
                    await ch.set_permissions(verified_role, view_channel=True, read_message_history=True, reason="Rehide verification rules")
                else:
                    await ch.set_permissions(unverified_role, view_channel=False, reason="Rehide verification rules")
                    await ch.set_permissions(verified_role, view_channel=True, reason="Rehide verification rules")
                updated_count += 1
        except discord.Forbidden:
            await interaction.followup.send("Error: Bot lacks permission to update channel permission overwrites.", ephemeral=True)
            return
        except Exception as e:
            await interaction.followup.send(f"Error reapplying channel permissions: {e}", ephemeral=True)
            return

        await interaction.followup.send(f"Verification visibility rules reapplied across {updated_count} channel(s).", ephemeral=True)

    @verification_channel_setup.error
    @rehide.error
    async def verification_error_handler(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        if isinstance(error, app_commands.MissingPermissions):
            msg = "You do not have Administrator permissions to execute this command."
        else:
            msg = f"An error occurred: {error}"

        if interaction.response.is_done():
            await interaction.followup.send(msg, ephemeral=True)
        else:
            await interaction.response.send_message(msg, ephemeral=True)


async def setup(bot):
    await bot.add_cog(Verification(bot))
