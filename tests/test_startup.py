import unittest
from unittest.mock import AsyncMock, MagicMock, patch
import discord

from bot.main import MultipurposeBot


class TestStartupSync(unittest.IsolatedAsyncioTestCase):
    async def test_on_ready_synchronization(self):
        bot = MultipurposeBot()
        bot._connection = MagicMock()
        bot._connection.user = MagicMock()
        bot._connection.user.id = 12345
        bot._connection.user.__str__ = lambda s: "TestBot#0000"

        guild1 = MagicMock(spec=discord.Guild)
        guild1.id = 1001
        guild1.name = "Guild One"

        guild2 = MagicMock(spec=discord.Guild)
        guild2.id = 1002
        guild2.name = "Guild Two"

        bot._connection._guilds = {1001: guild1, 1002: guild2}
        bot._connection.guilds = [guild1, guild2]

        bot._tree = MagicMock()
        bot.tree.get_commands = MagicMock(return_value=[])
        bot.tree.sync = AsyncMock(return_value=[])
        bot.tree.copy_global_to = MagicMock()

        await bot.on_ready()

        # Check that tree.sync was called for global and for both guilds
        self.assertEqual(bot.tree.sync.call_count, 3)
        self.assertEqual(bot.tree.copy_global_to.call_count, 2)
        bot.tree.copy_global_to.assert_any_call(guild=guild1)
        bot.tree.copy_global_to.assert_any_call(guild=guild2)

    async def test_on_ready_idempotency(self):
        bot = MultipurposeBot()
        bot._connection = MagicMock()
        bot._connection.user = MagicMock()
        bot._connection.user.id = 12345
        bot._connection.user.__str__ = lambda s: "TestBot#0000"

        guild1 = MagicMock(spec=discord.Guild)
        guild1.id = 1001
        guild1.name = "Guild One"

        bot._connection._guilds = {1001: guild1}
        bot._connection.guilds = [guild1]

        cmd = MagicMock()
        cmd.name = "warn"
        bot._tree = MagicMock()
        bot.tree.get_commands = MagicMock(return_value=[cmd])
        bot.tree.sync = AsyncMock(return_value=[cmd])
        bot.tree.copy_global_to = MagicMock()

        # Run on_ready twice
        await bot.on_ready()
        await bot.on_ready()

        # Global sync + 1 guild sync per on_ready call = 2 * 2 = 4 sync calls
        self.assertEqual(bot.tree.sync.call_count, 4)
        self.assertEqual(bot.tree.copy_global_to.call_count, 2)


if __name__ == "__main__":
    unittest.main()
