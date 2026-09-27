import os
import sqlite3
from typing import Optional, Dict, Any, Tuple

DEFAULT_DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "bot.db")


class Database:
    def __init__(self, db_path: str = DEFAULT_DB_PATH):
        self.db_path = db_path
        # Ensure parent directory exists
        db_dir = os.path.dirname(self.db_path)
        if db_dir and not os.path.exists(db_dir):
            os.makedirs(db_dir, exist_ok=True)
        self.init_db()

    def get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def init_db(self) -> None:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS guild_config (
                    guild_id INTEGER PRIMARY KEY,
                    owner_role_id INTEGER,
                    staff_role_id INTEGER,
                    trainee_role_id INTEGER,
                    moderator_role_id INTEGER,
                    senior_mod_role_id INTEGER,
                    moderation_logs_channel_id INTEGER,
                    join_leave_channel_id INTEGER
                )
                """
            )
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS user_tracking (
                    guild_id INTEGER,
                    user_id INTEGER,
                    latest_message_channel_id INTEGER,
                    join_timestamp REAL,
                    PRIMARY KEY (guild_id, user_id)
                )
                """
            )
            conn.commit()

    def get_guild_config(self, guild_id: int) -> Optional[Dict[str, Any]]:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM guild_config WHERE guild_id = ?", (guild_id,))
            row = cursor.fetchone()
            if row:
                return dict(row)
            return None

    def set_guild_roles(
        self,
        guild_id: int,
        owner_role_id: int,
        staff_role_id: int,
        trainee_role_id: int,
        moderator_role_id: int,
        senior_mod_role_id: int,
    ) -> None:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO guild_config (
                    guild_id, owner_role_id, staff_role_id, trainee_role_id, moderator_role_id, senior_mod_role_id
                ) VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(guild_id) DO UPDATE SET
                    owner_role_id = excluded.owner_role_id,
                    staff_role_id = excluded.staff_role_id,
                    trainee_role_id = excluded.trainee_role_id,
                    moderator_role_id = excluded.moderator_role_id,
                    senior_mod_role_id = excluded.senior_mod_role_id
                """,
                (
                    guild_id,
                    owner_role_id,
                    staff_role_id,
                    trainee_role_id,
                    moderator_role_id,
                    senior_mod_role_id,
                ),
            )
            conn.commit()

    def set_moderation_logs_channel(self, guild_id: int, channel_id: int) -> None:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO guild_config (guild_id, moderation_logs_channel_id)
                VALUES (?, ?)
                ON CONFLICT(guild_id) DO UPDATE SET
                    moderation_logs_channel_id = excluded.moderation_logs_channel_id
                """,
                (guild_id, channel_id),
            )
            conn.commit()

    def set_join_leave_channel(self, guild_id: int, channel_id: int) -> None:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO guild_config (guild_id, join_leave_channel_id)
                VALUES (?, ?)
                ON CONFLICT(guild_id) DO UPDATE SET
                    join_leave_channel_id = excluded.join_leave_channel_id
                """,
                (guild_id, channel_id),
            )
            conn.commit()

    def update_latest_message_channel(self, guild_id: int, user_id: int, channel_id: int) -> None:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO user_tracking (guild_id, user_id, latest_message_channel_id)
                VALUES (?, ?, ?)
                ON CONFLICT(guild_id, user_id) DO UPDATE SET
                    latest_message_channel_id = excluded.latest_message_channel_id
                """,
                (guild_id, user_id, channel_id),
            )
            conn.commit()

    def get_latest_message_channel(self, guild_id: int, user_id: int) -> Optional[int]:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT latest_message_channel_id FROM user_tracking WHERE guild_id = ? AND user_id = ?",
                (guild_id, user_id),
            )
            row = cursor.fetchone()
            if row and row["latest_message_channel_id"] is not None:
                return int(row["latest_message_channel_id"])
            return None

    def record_user_join(self, guild_id: int, user_id: int, join_timestamp: float) -> None:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO user_tracking (guild_id, user_id, join_timestamp)
                VALUES (?, ?, ?)
                ON CONFLICT(guild_id, user_id) DO UPDATE SET
                    join_timestamp = excluded.join_timestamp
                """,
                (guild_id, user_id, join_timestamp),
            )
            conn.commit()

    def get_user_join_timestamp(self, guild_id: int, user_id: int) -> Optional[float]:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT join_timestamp FROM user_tracking WHERE guild_id = ? AND user_id = ?",
                (guild_id, user_id),
            )
            row = cursor.fetchone()
            if row and row["join_timestamp"] is not None:
                return float(row["join_timestamp"])
            return None
