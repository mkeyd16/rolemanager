import os
import tempfile
import datetime
import unittest
from unittest.mock import AsyncMock, MagicMock, patch
import discord

from bot.database import Database
from commands.moderation import Moderation


class TestModerationCommands(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.temp_dir.name, "test_bot.db")
        self.db = Database(self.db_path)

        self.bot = MagicMock()
        self.bot.db = self.db

        self.cog = Moderation(self.bot)

        # Setup standard roles config
        self.guild_id = 1000
        self.owner_role_id = 100
        self.staff_role_id = 101
        self.trainee_role_id = 102
        self.mod_role_id = 103
        self.senior_role_id = 104
        self.log_channel_id = 999

        self.db.set_guild_roles(
            guild_id=self.guild_id,
            owner_role_id=self.owner_role_id,
            staff_role_id=self.staff_role_id,
            trainee_role_id=self.trainee_role_id,
            moderator_role_id=self.mod_role_id,
            senior_mod_role_id=self.senior_role_id,
        )
        self.db.set_moderation_logs_channel(self.guild_id, self.log_channel_id)

        # Mock guild and interaction
        self.interaction = AsyncMock(spec=discord.Interaction)
        self.guild = MagicMock(spec=discord.Guild)
        self.guild.id = self.guild_id

        # Roles
        self.owner_role = self._create_role(self.owner_role_id, "Owner")
        self.staff_role = self._create_role(self.staff_role_id, "Staff")
        self.trainee_role = self._create_role(self.trainee_role_id, "Trainee")
        self.mod_role = self._create_role(self.mod_role_id, "Moderator")
        self.senior_role = self._create_role(self.senior_role_id, "Senior Mod")

        self.guild.roles = [
            self.owner_role,
            self.staff_role,
            self.trainee_role,
            self.mod_role,
            self.senior_role,
        ]
        self.guild.get_role = lambda rid: next((r for r in self.guild.roles if r.id == rid), None)

        # Log channel
        self.log_channel = AsyncMock(spec=discord.TextChannel)
        self.log_channel.id = self.log_channel_id
        self.guild.get_channel = lambda cid: self.log_channel if cid == self.log_channel_id else None

        self.interaction.guild = self.guild
        self.interaction.response = AsyncMock()
        self.interaction.followup = AsyncMock()

    async def asyncTearDown(self):
        self.temp_dir.cleanup()

    def _create_role(self, role_id, name):
        role = MagicMock(spec=discord.Role)
        role.id = role_id
        role.name = name
        return role

    def _create_member(self, user_id, role_ids, name="User"):
        member = AsyncMock(spec=discord.Member)
        member.id = user_id
        member.name = name
        member.display_name = name
        member.mention = f"<@{user_id}>"
        member.__str__ = lambda s: name
        roles = [r for r in self.guild.roles if r.id in role_ids]
        member.roles = roles
        member.add_roles = AsyncMock()
        member.remove_roles = AsyncMock()
        member.timeout = AsyncMock()
        return member

    async def test_warn_successful(self):
        actor = self._create_member(1, [self.trainee_role_id, self.staff_role_id], "TraineeUser")
        target = self._create_member(2, [], "TargetUser")
        self.interaction.user = actor

        cmd_channel = AsyncMock(spec=discord.TextChannel)
        cmd_channel.id = 888
        cmd_channel.mention = "<#888>"
        self.interaction.channel = cmd_channel

        await self.cog.warn.callback(self.cog, self.interaction, target, "Inappropriate language")

        # Public warning response sent via interaction.response.send_message
        self.interaction.response.send_message.assert_called_once()
        kwargs = self.interaction.response.send_message.call_args[1]
        self.assertEqual(kwargs.get("ephemeral"), False)
        self.assertIn("embed", kwargs)
        warn_embed = kwargs["embed"]
        self.assertEqual(warn_embed.title, "User Warning/Punishment")
        self.assertIn("**User:** <@2>", warn_embed.description)
        self.assertIn("**Moderator:** <@1>", warn_embed.description)
        self.assertIn("**Rank:** Trainee", warn_embed.description)
        self.assertIn("**Reason:** Inappropriate language", warn_embed.description)
        self.assertIn("Please be aware that further violations may result in additional moderation action.", warn_embed.description)

        # Logged in log_channel
        self.log_channel.send.assert_called_once()

    async def test_warn_hierarchy_prevention(self):
        trainee_actor = self._create_member(1, [self.trainee_role_id, self.staff_role_id], "TraineeUser")
        mod_target = self._create_member(2, [self.mod_role_id, self.staff_role_id], "ModUser")
        self.interaction.user = trainee_actor

        await self.cog.warn.callback(self.cog, self.interaction, mod_target, "Reason")

        self.interaction.response.send_message.assert_called_once()
        msg = self.interaction.response.send_message.call_args[0][0]
        self.assertIn("equal or higher staff rank", msg)

    async def test_punish_severity_restrictions_and_durations(self):
        trainee = self._create_member(1, [self.trainee_role_id, self.staff_role_id], "TraineeUser")
        mod = self._create_member(2, [self.mod_role_id, self.staff_role_id], "ModUser")
        senior = self._create_member(3, [self.senior_role_id, self.staff_role_id], "SeniorUser")
        target = self._create_member(4, [], "TargetUser")

        # 1. Trainee attempting moderate -> rejected (ephemeral error)
        self.interaction.user = trainee
        self.interaction.response.send_message.reset_mock()
        await self.cog.punish.callback(self.cog, self.interaction, target, "moderate", "Offense")
        target.timeout.assert_not_called()
        self.assertIn("do not have sufficient staff rank", self.interaction.response.send_message.call_args[0][0])
        self.assertEqual(self.interaction.response.send_message.call_args[1].get("ephemeral"), True)

        # 2. Trainee issuing minor -> 10m timeout applied (public)
        self.interaction.response.send_message.reset_mock()
        await self.cog.punish.callback(self.cog, self.interaction, target, "minor", "Minor Offense")
        target.timeout.assert_called_once_with(datetime.timedelta(seconds=600), reason="[MINOR] Minor Offense")
        kwargs = self.interaction.response.send_message.call_args[1]
        self.assertEqual(kwargs.get("ephemeral"), False)
        punish_embed = kwargs["embed"]
        self.assertEqual(punish_embed.title, "User Warning/Punishment")
        self.assertIn("**User:** <@4>", punish_embed.description)
        self.assertIn("**Moderator:** <@1>", punish_embed.description)
        self.assertIn("**Rank:** Trainee", punish_embed.description)
        self.assertIn("**Reason:** Minor Offense", punish_embed.description)
        self.assertIn("<@4> has been timed out for 10 minutes.", punish_embed.description)

        # 3. Moderator attempting major -> rejected (ephemeral error)
        self.interaction.user = mod
        target.timeout.reset_mock()
        self.interaction.response.send_message.reset_mock()
        await self.cog.punish.callback(self.cog, self.interaction, target, "major", "Major Offense")
        target.timeout.assert_not_called()
        self.assertIn("do not have sufficient staff rank", self.interaction.response.send_message.call_args[0][0])
        self.assertEqual(self.interaction.response.send_message.call_args[1].get("ephemeral"), True)

        # 4. Moderator issuing moderate -> 45m timeout applied (public)
        self.interaction.response.send_message.reset_mock()
        await self.cog.punish.callback(self.cog, self.interaction, target, "moderate", "Moderate Offense")
        target.timeout.assert_called_once_with(datetime.timedelta(seconds=2700), reason="[MODERATE] Moderate Offense")
        kwargs = self.interaction.response.send_message.call_args[1]
        self.assertEqual(kwargs.get("ephemeral"), False)
        punish_embed = kwargs["embed"]
        self.assertIn("<@4> has been timed out for 45 minutes.", punish_embed.description)

        # 5. Senior Mod issuing major -> 48h timeout applied (public)
        self.interaction.user = senior
        target.timeout.reset_mock()
        self.interaction.response.send_message.reset_mock()
        await self.cog.punish.callback(self.cog, self.interaction, target, "major", "Major Offense")
        target.timeout.assert_called_once_with(datetime.timedelta(seconds=172800), reason="[MAJOR] Major Offense")
        kwargs = self.interaction.response.send_message.call_args[1]
        self.assertEqual(kwargs.get("ephemeral"), False)
        punish_embed = kwargs["embed"]
        self.assertIn("<@4> has been timed out for 48 hours.", punish_embed.description)

    async def test_owner_role_punish_all_severities_without_senior_mod(self):
        owner_alone = self._create_member(10, [self.owner_role_id], "OwnerAlone")
        target = self._create_member(4, [], "TargetUser")
        self.interaction.user = owner_alone

        # Minor
        target.timeout.reset_mock()
        await self.cog.punish.callback(self.cog, self.interaction, target, "minor", "Minor")
        target.timeout.assert_called_once_with(datetime.timedelta(seconds=600), reason="[MINOR] Minor")

        # Moderate
        target.timeout.reset_mock()
        await self.cog.punish.callback(self.cog, self.interaction, target, "moderate", "Moderate")
        target.timeout.assert_called_once_with(datetime.timedelta(seconds=2700), reason="[MODERATE] Moderate")

        # Major
        target.timeout.reset_mock()
        await self.cog.punish.callback(self.cog, self.interaction, target, "major", "Major")
        target.timeout.assert_called_once_with(datetime.timedelta(seconds=172800), reason="[MAJOR] Major")

    async def test_hire_promote_fire_commands(self):
        owner = self._create_member(10, [self.owner_role_id, self.staff_role_id], "OwnerUser")
        non_owner = self._create_member(11, [self.mod_role_id, self.staff_role_id], "ModUser")
        candidate = self._create_member(20, [], "CandidateUser")

        # Non-owner hiring candidate -> rejected (ephemeral)
        self.interaction.user = non_owner
        self.interaction.response.send_message.reset_mock()
        await self.cog.hire.callback(self.cog, self.interaction, candidate)
        self.assertIn("Only the Server Owner can use `/hire`", self.interaction.response.send_message.call_args[0][0])
        self.assertEqual(self.interaction.response.send_message.call_args[1].get("ephemeral"), True)

        # Owner hiring candidate -> success (public)
        self.interaction.user = owner
        self.interaction.response.send_message.reset_mock()
        await self.cog.hire.callback(self.cog, self.interaction, candidate)
        candidate.add_roles.assert_called_once_with(self.staff_role, self.trainee_role, reason="Hired by OwnerUser")
        self.assertIn("has been hired as a Trainee", self.interaction.response.send_message.call_args[0][0])
        self.assertEqual(self.interaction.response.send_message.call_args[1].get("ephemeral"), False)

        # Hiring user who is already staff -> clear message (ephemeral)
        candidate.roles = [self.staff_role, self.trainee_role]
        self.interaction.response.send_message.reset_mock()
        await self.cog.hire.callback(self.cog, self.interaction, candidate)
        self.assertIn("is already a staff member", self.interaction.response.send_message.call_args[0][0])
        self.assertEqual(self.interaction.response.send_message.call_args[1].get("ephemeral"), True)

        # Owner promoting Trainee -> Moderator (public)
        candidate.remove_roles.reset_mock()
        candidate.add_roles.reset_mock()
        self.interaction.response.send_message.reset_mock()
        await self.cog.promote.callback(self.cog, self.interaction, candidate)
        candidate.remove_roles.assert_called_once_with(self.trainee_role, reason="Promoted to Moderator by OwnerUser")
        candidate.add_roles.assert_called_with(self.mod_role, reason="Promoted to Moderator by OwnerUser")
        self.assertIn("promoted from Trainee to Moderator", self.interaction.response.send_message.call_args[0][0])
        self.assertEqual(self.interaction.response.send_message.call_args[1].get("ephemeral"), False)

        # Owner promoting Moderator -> Senior Mod (public)
        candidate.roles = [self.staff_role, self.mod_role]
        candidate.remove_roles.reset_mock()
        candidate.add_roles.reset_mock()
        self.interaction.response.send_message.reset_mock()
        await self.cog.promote.callback(self.cog, self.interaction, candidate)
        candidate.remove_roles.assert_called_once_with(self.mod_role, reason="Promoted to Senior Mod by OwnerUser")
        candidate.add_roles.assert_called_with(self.senior_role, reason="Promoted to Senior Mod by OwnerUser")
        self.assertIn("promoted from Moderator to Senior Mod", self.interaction.response.send_message.call_args[0][0])
        self.assertEqual(self.interaction.response.send_message.call_args[1].get("ephemeral"), False)

        # Owner promoting Senior Mod -> no higher rank (ephemeral)
        candidate.roles = [self.staff_role, self.senior_role]
        self.interaction.response.send_message.reset_mock()
        await self.cog.promote.callback(self.cog, self.interaction, candidate)
        self.assertIn("is already a Senior Mod", self.interaction.response.send_message.call_args[0][0])
        self.assertEqual(self.interaction.response.send_message.call_args[1].get("ephemeral"), True)

        # Owner firing staff member -> removes staff roles (public)
        candidate.roles = [self.staff_role, self.senior_role]
        candidate.remove_roles.reset_mock()
        candidate.add_roles.reset_mock()
        self.interaction.response.send_message.reset_mock()
        await self.cog.fire.callback(self.cog, self.interaction, candidate)
        candidate.remove_roles.assert_called_once_with(self.staff_role, self.senior_role, reason="Fired by OwnerUser")
        self.assertIn("removed from the staff team", self.interaction.response.send_message.call_args[0][0])
        self.assertEqual(self.interaction.response.send_message.call_args[1].get("ephemeral"), False)

    async def test_graceful_handling_missing_configured_roles_or_channels(self):
        owner = self._create_member(10, [self.owner_role_id, self.staff_role_id], "OwnerUser")
        candidate = self._create_member(20, [], "CandidateUser")
        self.interaction.user = owner

        # Set config to non-existent role IDs in guild
        self.db.set_guild_roles(
            guild_id=self.guild_id,
            owner_role_id=self.owner_role_id,
            staff_role_id=99991,
            trainee_role_id=99992,
            moderator_role_id=99993,
            senior_mod_role_id=99994,
        )

        await self.cog.hire.callback(self.cog, self.interaction, candidate)
        self.assertIn("no longer exists in the server", self.interaction.response.send_message.call_args[0][0])


if __name__ == "__main__":
    unittest.main()
