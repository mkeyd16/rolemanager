import os
import tempfile
import unittest
from unittest.mock import AsyncMock, MagicMock, patch
import discord

from bot.database import Database
from commands.verification import Verification
from events.verification_events import VerificationEvents
from events.member_events import MemberEvents


class TestVerificationSystem(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.temp_dir.name, "test_bot.db")
        self.db = Database(self.db_path)

        self.bot = MagicMock()
        self.bot.db = self.db

        self.ver_cog = Verification(self.bot)
        self.ver_events_cog = VerificationEvents(self.bot)
        self.member_events_cog = MemberEvents(self.bot)

        # Mock interaction and guild
        self.interaction = AsyncMock(spec=discord.Interaction)
        self.guild = MagicMock(spec=discord.Guild)
        self.guild.id = 123456
        self.guild.roles = []
        self.guild.channels = []
        self.guild.text_channels = []
        self.guild.members = []

        # Bot member
        self.bot_member = MagicMock(spec=discord.Member)
        self.bot_member.bot = True
        perms = MagicMock(spec=discord.Permissions)
        perms.manage_roles = True
        perms.manage_channels = True
        perms.view_channel = True
        perms.send_messages = True
        perms.embed_links = True
        perms.add_reactions = True
        self.bot_member.guild_permissions = perms

        # Role hierarchy
        self.bot_top_role = MagicMock(spec=discord.Role)
        self.bot_top_role.position = 100
        self.bot_member.top_role = self.bot_top_role

        self.guild.me = self.bot_member

        self.interaction.guild = self.guild
        self.interaction.response = AsyncMock()
        self.interaction.followup = AsyncMock()

    async def asyncTearDown(self):
        self.temp_dir.cleanup()

    def _create_role_mock(self, role_id, name, position=10):
        role = MagicMock(spec=discord.Role)
        role.id = role_id
        role.name = name
        role.position = position
        role.__gt__ = lambda self_role, other: self_role.position > getattr(other, "position", 0)
        role.__ge__ = lambda self_role, other: self_role.position >= getattr(other, "position", 0)
        role.__lt__ = lambda self_role, other: self_role.position < getattr(other, "position", 0)
        role.__le__ = lambda self_role, other: self_role.position <= getattr(other, "position", 0)
        return role

    def _create_channel_mock(self, channel_id, name):
        channel = AsyncMock(spec=discord.TextChannel)
        channel.id = channel_id
        channel.name = name
        channel.mention = f"<#{channel_id}>"
        channel.set_permissions = AsyncMock()
        channel.send = AsyncMock()
        return channel

    def _create_member_mock(self, user_id, name, is_bot=False):
        member = AsyncMock(spec=discord.Member)
        member.id = user_id
        member.display_name = name
        member.bot = is_bot
        member.roles = []
        member.joined_at = None
        member.created_at = None
        member.add_roles = AsyncMock()
        member.remove_roles = AsyncMock()
        return member

    async def test_verification_configuration_creation_and_persistence(self):
        # Setup channels and roles mocks
        next_id = 200

        async def mock_create_role(name, color=None, reason=None):
            nonlocal next_id
            next_id += 1
            role = self._create_role_mock(next_id, name, position=10)
            self.guild.roles.append(role)
            return role

        async def mock_create_text_channel(name, reason=None):
            nonlocal next_id
            next_id += 1
            channel = self._create_channel_mock(next_id, name)

            # Mock message creation
            async def mock_send(embed=None, content=None):
                msg = AsyncMock(spec=discord.Message)
                msg.id = 9999
                msg.add_reaction = AsyncMock()
                return msg

            channel.send = mock_send
            self.guild.channels.append(channel)
            self.guild.text_channels.append(channel)
            return channel

        self.guild.create_role = mock_create_role
        self.guild.create_text_channel = mock_create_text_channel

        # Add normal channel
        normal_ch = self._create_channel_mock(101, "general")
        self.guild.channels.append(normal_ch)
        self.guild.text_channels.append(normal_ch)

        # Run setup
        await self.ver_cog.verification_channel_setup.callback(self.ver_cog, self.interaction)

        # Check DB config
        cfg = self.db.get_guild_config(self.guild.id)
        self.assertIsNotNone(cfg)
        self.assertIsNotNone(cfg["verification_channel_id"])
        self.assertIsNotNone(cfg["verified_role_id"])
        self.assertIsNotNone(cfg["unverified_role_id"])
        self.assertEqual(cfg["verification_message_id"], 9999)

        # Confirm response
        self.interaction.followup.send.assert_called_once()
        msg = self.interaction.followup.send.call_args[0][0]
        self.assertIn("Verification system successfully configured!", msg)

    async def test_setup_idempotency_and_no_duplicates(self):
        # Create existing configuration in DB and Guild
        ver_role = self._create_role_mock(201, "Verified", position=10)
        unver_role = self._create_role_mock(202, "Unverified", position=10)
        ver_channel = self._create_channel_mock(301, "verification")

        msg_mock = AsyncMock(spec=discord.Message)
        msg_mock.id = 401
        ver_channel.fetch_message = AsyncMock(return_value=msg_mock)

        self.guild.roles = [ver_role, unver_role]
        self.guild.channels = [ver_channel]
        self.guild.text_channels = [ver_channel]
        self.guild.get_role = lambda rid: next((r for r in self.guild.roles if r.id == rid), None)
        self.guild.get_channel = lambda cid: next((c for c in self.guild.channels if c.id == cid), None)

        self.db.set_verification_config(
            guild_id=self.guild.id,
            verification_channel_id=301,
            verified_role_id=201,
            unverified_role_id=202,
            verification_message_id=401,
        )

        self.guild.create_role = AsyncMock()
        self.guild.create_text_channel = AsyncMock()

        # Re-run setup
        await self.ver_cog.verification_channel_setup.callback(self.ver_cog, self.interaction)

        # Ensure no new roles or channels created
        self.guild.create_role.assert_not_called()
        self.guild.create_text_channel.assert_not_called()
        ver_channel.send.assert_not_called()

        cfg = self.db.get_guild_config(self.guild.id)
        self.assertEqual(cfg["verified_role_id"], 201)
        self.assertEqual(cfg["unverified_role_id"], 202)
        self.assertEqual(cfg["verification_channel_id"], 301)
        self.assertEqual(cfg["verification_message_id"], 401)

    async def test_existing_members_given_verified_role(self):
        ver_role = self._create_role_mock(201, "Verified", position=10)
        unver_role = self._create_role_mock(202, "Unverified", position=10)
        ver_channel = self._create_channel_mock(301, "verification")

        msg_mock = AsyncMock(spec=discord.Message)
        msg_mock.id = 401
        ver_channel.fetch_message = AsyncMock(return_value=msg_mock)

        # Human member 1: no roles -> should get Verified
        m1 = self._create_member_mock(1001, "Human1")
        # Human member 2: has Unverified -> should NOT get Verified
        m2 = self._create_member_mock(1002, "Human2")
        m2.roles = [unver_role]
        # Bot member: should NOT get Verified
        m3 = self._create_member_mock(1003, "BotMember", is_bot=True)

        self.guild.roles = [ver_role, unver_role]
        self.guild.channels = [ver_channel]
        self.guild.text_channels = [ver_channel]
        self.guild.members = [m1, m2, m3]
        self.guild.get_role = lambda rid: next((r for r in self.guild.roles if r.id == rid), None)
        self.guild.get_channel = lambda cid: next((c for c in self.guild.channels if c.id == cid), None)

        self.db.set_verification_config(
            guild_id=self.guild.id,
            verification_channel_id=301,
            verified_role_id=201,
            unverified_role_id=202,
            verification_message_id=401,
        )

        await self.ver_cog.verification_channel_setup.callback(self.ver_cog, self.interaction)

        m1.add_roles.assert_called_once_with(ver_role, reason="Initial verification setup for existing member")
        m2.add_roles.assert_not_called()
        m3.add_roles.assert_not_called()

    async def test_new_member_join_assigned_unverified_role(self):
        unver_role = self._create_role_mock(202, "Unverified")
        self.guild.get_role = lambda rid: unver_role if rid == 202 else None

        self.db.set_verification_config(
            guild_id=self.guild.id,
            verification_channel_id=301,
            verified_role_id=201,
            unverified_role_id=202,
            verification_message_id=401,
        )

        member = self._create_member_mock(5001, "NewUser")
        member.guild = self.guild

        await self.member_events_cog.on_member_join(member)

        member.add_roles.assert_called_once_with(unver_role, reason="New member unverified assignment")

    async def test_reaction_verification_success_and_ignores(self):
        ver_role = self._create_role_mock(201, "Verified", position=10)
        unver_role = self._create_role_mock(202, "Unverified", position=10)

        self.guild.roles = [ver_role, unver_role]
        self.guild.get_role = lambda rid: next((r for r in self.guild.roles if r.id == rid), None)
        self.bot.get_guild = lambda gid: self.guild if gid == self.guild.id else None

        self.db.set_verification_config(
            guild_id=self.guild.id,
            verification_channel_id=301,
            verified_role_id=201,
            unverified_role_id=202,
            verification_message_id=401,
        )

        # 1. Valid reaction by unverified user
        member = self._create_member_mock(6001, "ReactingUser")
        member.roles = [unver_role]

        payload = MagicMock(spec=discord.RawReactionActionEvent)
        payload.guild_id = self.guild.id
        payload.channel_id = 301
        payload.message_id = 401
        payload.user_id = 6001
        payload.member = member
        payload.emoji = "✅"

        await self.ver_events_cog.on_raw_reaction_add(payload)

        member.add_roles.assert_called_once_with(ver_role, reason="Completed verification")
        member.remove_roles.assert_called_once_with(unver_role, reason="Completed verification")

        # 2. Ignore bot reaction
        bot_user = self._create_member_mock(6002, "BotReact", is_bot=True)
        payload.member = bot_user
        payload.user_id = 6002
        await self.ver_events_cog.on_raw_reaction_add(payload)
        bot_user.add_roles.assert_not_called()

        # 3. Ignore wrong emoji
        member.add_roles.reset_mock()
        payload.member = member
        payload.emoji = "❌"
        await self.ver_events_cog.on_raw_reaction_add(payload)
        member.add_roles.assert_not_called()

        # 4. Ignore wrong channel or message
        payload.emoji = "✅"
        payload.channel_id = 999
        await self.ver_events_cog.on_raw_reaction_add(payload)
        member.add_roles.assert_not_called()

        payload.channel_id = 301
        payload.message_id = 999
        await self.ver_events_cog.on_raw_reaction_add(payload)
        member.add_roles.assert_not_called()

    async def test_rehide_command(self):
        ver_role = self._create_role_mock(201, "Verified")
        unver_role = self._create_role_mock(202, "Unverified")
        ver_channel = self._create_channel_mock(301, "verification")
        normal_channel_1 = self._create_channel_mock(302, "general")
        normal_channel_2 = self._create_channel_mock(303, "announcements")

        self.guild.roles = [ver_role, unver_role]
        self.guild.channels = [ver_channel, normal_channel_1, normal_channel_2]
        self.guild.get_role = lambda rid: next((r for r in self.guild.roles if r.id == rid), None)
        self.guild.get_channel = lambda cid: next((c for c in self.guild.channels if c.id == cid), None)

        self.db.set_verification_config(
            guild_id=self.guild.id,
            verification_channel_id=301,
            verified_role_id=201,
            unverified_role_id=202,
            verification_message_id=401,
        )

        await self.ver_cog.rehide.callback(self.ver_cog, self.interaction)

        # Check permission overwrites on verification channel
        ver_channel.set_permissions.assert_any_call(unver_role, view_channel=True, read_message_history=True, reason="Rehide verification rules")
        ver_channel.set_permissions.assert_any_call(ver_role, view_channel=True, read_message_history=True, reason="Rehide verification rules")

        # Check permission overwrites on normal channels
        normal_channel_1.set_permissions.assert_any_call(unver_role, view_channel=False, reason="Rehide verification rules")
        normal_channel_1.set_permissions.assert_any_call(ver_role, view_channel=True, reason="Rehide verification rules")

        normal_channel_2.set_permissions.assert_any_call(unver_role, view_channel=False, reason="Rehide verification rules")
        normal_channel_2.set_permissions.assert_any_call(ver_role, view_channel=True, reason="Rehide verification rules")

    async def test_missing_permissions_and_role_hierarchy_failures(self):
        # 1. Missing permission test
        self.bot_member.guild_permissions.manage_roles = False

        await self.ver_cog.verification_channel_setup.callback(self.ver_cog, self.interaction)

        msg = self.interaction.followup.send.call_args[0][0]
        self.assertIn("Bot lacks required Discord permission(s): Manage Roles", msg)

        # Reset perms
        self.bot_member.guild_permissions.manage_roles = True

        # 2. Role hierarchy failure test
        low_bot_role = MagicMock(spec=discord.Role)
        low_bot_role.position = 5
        self.bot_member.top_role = low_bot_role

        ver_role = self._create_role_mock(201, "Verified", position=10)
        unver_role = self._create_role_mock(202, "Unverified", position=10)
        self.guild.roles = [ver_role, unver_role]
        self.guild.get_role = lambda rid: next((r for r in self.guild.roles if r.id == rid), None)

        self.db.set_verification_config(
            guild_id=self.guild.id,
            verification_channel_id=301,
            verified_role_id=201,
            unverified_role_id=202,
            verification_message_id=401,
        )

        await self.ver_cog.verification_channel_setup.callback(self.ver_cog, self.interaction)

        msg = self.interaction.followup.send.call_args[0][0]
        self.assertIn("Error: Bot role hierarchy is lower than or equal to Verified or Unverified roles", msg)


if __name__ == "__main__":
    unittest.main()
