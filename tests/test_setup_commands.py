import os
import tempfile
import unittest
from unittest.mock import AsyncMock, MagicMock, patch
import discord

from bot.database import Database
from commands.setup import Setup


class TestSetupCommands(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.temp_dir.name, "test_bot.db")
        self.db = Database(self.db_path)

        self.bot = MagicMock()
        self.bot.db = self.db

        self.cog = Setup(self.bot)

        # Mock interaction and guild
        self.interaction = AsyncMock(spec=discord.Interaction)
        self.guild = MagicMock(spec=discord.Guild)
        self.guild.id = 123456
        self.guild.roles = []
        self.guild.text_channels = []

        self.interaction.guild = self.guild
        self.interaction.response = AsyncMock()
        self.interaction.followup = AsyncMock()

    async def asyncTearDown(self):
        self.temp_dir.cleanup()

    def _create_role_mock(self, role_id, name):
        role = MagicMock(spec=discord.Role)
        role.id = role_id
        role.name = name
        return role

    def _create_channel_mock(self, channel_id, name):
        channel = MagicMock(spec=discord.TextChannel)
        channel.id = channel_id
        channel.name = name
        channel.mention = f"<#{channel_id}>"
        return channel

    async def test_setup_moderation_roles_initial_creation(self):
        # Guild has no roles initially
        self.guild.roles = []

        # Simulated role creation
        created_roles = {}
        next_id = 100

        async def mock_create_role(name, color=None, reason=None):
            nonlocal next_id
            next_id += 1
            role = self._create_role_mock(next_id, name)
            self.guild.roles.append(role)
            return role

        self.guild.create_role = mock_create_role

        # Execute setup roles command callback
        await self.cog.setup_moderation_roles.callback(self.cog, self.interaction)

        # Verify DB configured role IDs
        config = self.db.get_guild_config(self.guild.id)
        self.assertIsNotNone(config)
        self.assertIsNotNone(config["owner_role_id"])
        self.assertIsNotNone(config["staff_role_id"])
        self.assertIsNotNone(config["trainee_role_id"])
        self.assertIsNotNone(config["moderator_role_id"])
        self.assertIsNotNone(config["senior_mod_role_id"])

        # Verify 5 roles were created
        self.assertEqual(len(self.guild.roles), 5)
        self.interaction.followup.send.assert_called_once()
        sent_msg = self.interaction.followup.send.call_args[0][0]
        self.assertIn("Created role:", sent_msg)

    async def test_setup_moderation_roles_idempotency(self):
        # Populate DB with existing role IDs
        self.db.set_guild_roles(
            guild_id=self.guild.id,
            owner_role_id=1,
            staff_role_id=2,
            trainee_role_id=3,
            moderator_role_id=4,
            senior_mod_role_id=5,
        )

        owner_role = self._create_role_mock(1, "Owner")
        staff_role = self._create_role_mock(2, "Staff")
        trainee_role = self._create_role_mock(3, "Trainee")
        mod_role = self._create_role_mock(4, "Moderator")
        senior_role = self._create_role_mock(5, "Senior Mod")

        self.guild.roles = [owner_role, staff_role, trainee_role, mod_role, senior_role]
        self.guild.get_role = lambda rid: next((r for r in self.guild.roles if r.id == rid), None)

        self.guild.create_role = AsyncMock()

        # Run setup again
        await self.cog.setup_moderation_roles.callback(self.cog, self.interaction)

        # Ensure NO new roles were created
        self.guild.create_role.assert_not_called()

        sent_msg = self.interaction.followup.send.call_args[0][0]
        self.assertIn("Reused role:", sent_msg)

    async def test_setup_moderation_roles_deleted_role_recreation(self):
        # Populate DB where role 3 (Trainee) was deleted from server
        self.db.set_guild_roles(
            guild_id=self.guild.id,
            owner_role_id=1,
            staff_role_id=2,
            trainee_role_id=3,
            moderator_role_id=4,
            senior_mod_role_id=5,
        )

        owner_role = self._create_role_mock(1, "Owner")
        staff_role = self._create_role_mock(2, "Staff")
        mod_role = self._create_role_mock(4, "Moderator")
        senior_role = self._create_role_mock(5, "Senior Mod")

        # Trainee role 3 is missing from guild.roles
        self.guild.roles = [owner_role, staff_role, mod_role, senior_role]
        self.guild.get_role = lambda rid: next((r for r in self.guild.roles if r.id == rid), None)

        new_trainee_role = self._create_role_mock(99, "Trainee")

        async def mock_create_role(name, color=None, reason=None):
            if name == "Trainee":
                return new_trainee_role
            return None

        self.guild.create_role = mock_create_role

        # Run setup
        await self.cog.setup_moderation_roles.callback(self.cog, self.interaction)

        # Check DB was updated with new trainee role ID (99)
        config = self.db.get_guild_config(self.guild.id)
        self.assertEqual(config["trainee_role_id"], 99)

    async def test_setup_moderation_logs_initial_and_idempotent(self):
        self.guild.text_channels = []
        self.guild.get_channel = lambda cid: next((c for c in self.guild.text_channels if c.id == cid), None)

        new_channel = self._create_channel_mock(555, "moderation-logs")

        async def mock_create_text_channel(name, reason=None):
            self.guild.text_channels.append(new_channel)
            return new_channel

        self.guild.create_text_channel = mock_create_text_channel

        # Initial run
        await self.cog.setup_moderation_logs.callback(self.cog, self.interaction)

        config = self.db.get_guild_config(self.guild.id)
        self.assertEqual(config["moderation_logs_channel_id"], 555)

        sent_msg_1 = self.interaction.followup.send.call_args[0][0]
        self.assertIn("Created moderation logs channel", sent_msg_1)

        # Re-run setup
        self.interaction.followup.send.reset_mock()
        await self.cog.setup_moderation_logs.callback(self.cog, self.interaction)

        sent_msg_2 = self.interaction.followup.send.call_args[0][0]
        self.assertIn("Reused moderation logs channel", sent_msg_2)

    async def test_setup_join_leave(self):
        channel = self._create_channel_mock(777, "welcome")
        await self.cog.setup_join_leave.callback(self.cog, self.interaction, channel)

        config = self.db.get_guild_config(self.guild.id)
        self.assertEqual(config["join_leave_channel_id"], 777)


if __name__ == "__main__":
    unittest.main()
