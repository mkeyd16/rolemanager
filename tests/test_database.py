import os
import tempfile
import unittest
from bot.database import Database


class TestDatabase(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.temp_dir.name, "test_bot.db")
        self.db = Database(self.db_path)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_database_initialization(self):
        # Database tables should exist and be queryable
        config = self.db.get_guild_config(12345)
        self.assertIsNone(config)

    def test_per_guild_configuration(self):
        guild_1 = 1001
        guild_2 = 1002

        self.db.set_guild_roles(
            guild_id=guild_1,
            owner_role_id=10,
            staff_role_id=11,
            trainee_role_id=12,
            moderator_role_id=13,
            senior_mod_role_id=14,
        )

        self.db.set_guild_roles(
            guild_id=guild_2,
            owner_role_id=20,
            staff_role_id=21,
            trainee_role_id=22,
            moderator_role_id=23,
            senior_mod_role_id=24,
        )

        cfg_1 = self.db.get_guild_config(guild_1)
        cfg_2 = self.db.get_guild_config(guild_2)

        self.assertIsNotNone(cfg_1)
        self.assertIsNotNone(cfg_2)

        self.assertEqual(cfg_1["owner_role_id"], 10)
        self.assertEqual(cfg_1["senior_mod_role_id"], 14)

        self.assertEqual(cfg_2["owner_role_id"], 20)
        self.assertEqual(cfg_2["senior_mod_role_id"], 24)

    def test_role_id_storage_and_retrieval(self):
        guild_id = 555
        self.db.set_guild_roles(
            guild_id=guild_id,
            owner_role_id=101,
            staff_role_id=102,
            trainee_role_id=103,
            moderator_role_id=104,
            senior_mod_role_id=105,
        )

        cfg = self.db.get_guild_config(guild_id)
        self.assertEqual(cfg["owner_role_id"], 101)
        self.assertEqual(cfg["staff_role_id"], 102)
        self.assertEqual(cfg["trainee_role_id"], 103)
        self.assertEqual(cfg["moderator_role_id"], 104)
        self.assertEqual(cfg["senior_mod_role_id"], 105)

    def test_channel_id_storage(self):
        guild_id = 777
        self.db.set_moderation_logs_channel(guild_id, 9001)
        self.db.set_join_leave_channel(guild_id, 9002)

        cfg = self.db.get_guild_config(guild_id)
        self.assertEqual(cfg["moderation_logs_channel_id"], 9001)
        self.assertEqual(cfg["join_leave_channel_id"], 9002)


    def test_join_timestamp_recording_and_retrieval(self):
        guild_id = 999
        user_id = 123
        timestamp = 1600000000.0

        self.assertIsNone(self.db.get_user_join_timestamp(guild_id, user_id))

        self.db.record_user_join(guild_id, user_id, timestamp)
        self.assertEqual(self.db.get_user_join_timestamp(guild_id, user_id), timestamp)


if __name__ == "__main__":
    unittest.main()
