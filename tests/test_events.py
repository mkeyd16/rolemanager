import os
import tempfile
import datetime
import unittest
from unittest.mock import AsyncMock, MagicMock
import discord

from bot.database import Database
from events.member_events import MemberEvents


class TestEvents(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.temp_dir.name, "test_bot.db")
        self.db = Database(self.db_path)

        self.bot = MagicMock()
        self.bot.db = self.db

        self.member_cog = MemberEvents(self.bot)

        self.guild_id = 2000
        self.join_leave_channel_id = 2001

        self.db.set_join_leave_channel(self.guild_id, self.join_leave_channel_id)

    async def asyncTearDown(self):
        self.temp_dir.cleanup()

    async def test_member_join_and_leave_events(self):
        guild = MagicMock(spec=discord.Guild)
        guild.id = self.guild_id

        channel = AsyncMock(spec=discord.TextChannel)
        channel.id = self.join_leave_channel_id
        guild.get_channel = lambda cid: channel if cid == self.join_leave_channel_id else None

        now = datetime.datetime.now(datetime.timezone.utc)
        created_at = now - datetime.timedelta(days=100)
        joined_at = now - datetime.timedelta(days=10)

        member = MagicMock(spec=discord.Member)
        member.id = 555
        member.guild = guild
        member.name = "JohnDoe"
        member.display_name = "Johnny"
        member.mention = "<@555>"
        member.created_at = created_at
        member.joined_at = joined_at

        # Test on_member_join
        await self.member_cog.on_member_join(member)

        # Ensure join timestamp recorded in DB
        db_ts = self.db.get_user_join_timestamp(self.guild_id, 555)
        self.assertIsNotNone(db_ts)

        # Ensure join message embed sent to channel
        channel.send.assert_called_once()
        kwargs = channel.send.call_args[1]
        self.assertIn("embed", kwargs)
        join_embed = kwargs["embed"]
        self.assertEqual(join_embed.title, "User has joined the server.")
        self.assertIn("<@555> (Johnny)", join_embed.description)
        self.assertIn("Account age: 100 days", join_embed.description)

        # Test on_member_remove with recorded join timestamp
        channel.send.reset_mock()
        await self.member_cog.on_member_remove(member)

        channel.send.assert_called_once()
        kwargs = channel.send.call_args[1]
        self.assertIn("embed", kwargs)
        leave_embed = kwargs["embed"]
        self.assertEqual(leave_embed.title, "User has left the server.")
        self.assertIn("<@555> (Johnny)", leave_embed.description)
        self.assertIn("Time in server: 10 days", leave_embed.description)

    async def test_member_leave_without_recorded_join_timestamp(self):
        guild = MagicMock(spec=discord.Guild)
        guild.id = self.guild_id

        channel = AsyncMock(spec=discord.TextChannel)
        channel.id = self.join_leave_channel_id
        guild.get_channel = lambda cid: channel if cid == self.join_leave_channel_id else None

        member = MagicMock(spec=discord.Member)
        member.id = 777
        member.guild = guild
        member.name = "UnknownUser"
        member.display_name = "Unknown"
        member.mention = "<@777>"
        member.joined_at = None

        await self.member_cog.on_member_remove(member)

        channel.send.assert_called_once()
        kwargs = channel.send.call_args[1]
        self.assertIn("embed", kwargs)
        leave_embed = kwargs["embed"]
        self.assertEqual(leave_embed.title, "User has left the server.")
        self.assertIn("Join date: Unknown", leave_embed.description)
        self.assertIn("Time in server: Unknown", leave_embed.description)


if __name__ == "__main__":
    unittest.main()
