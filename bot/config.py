import os
from dotenv import load_dotenv

load_dotenv()

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN", "")

# Hierarchy Ranks
RANK_NONE = 0
RANK_TRAINEE = 1
RANK_MODERATOR = 2
RANK_SENIOR_MOD = 3
RANK_OWNER = 4

RANK_NAMES = {
    RANK_NONE: "None",
    RANK_TRAINEE: "Trainee",
    RANK_MODERATOR: "Moderator",
    RANK_SENIOR_MOD: "Senior Mod",
    RANK_OWNER: "Owner",
}

# Punishment durations in seconds
PUNISHMENT_DURATIONS = {
    "minor": 10 * 60,       # 10 minutes
    "moderate": 45 * 60,    # 45 minutes
    "major": 48 * 3600,     # 48 hours
}

# Maximum severity allowed per rank
ALLOWED_SEVERITIES = {
    RANK_TRAINEE: ["minor"],
    RANK_MODERATOR: ["minor", "moderate"],
    RANK_SENIOR_MOD: ["minor", "moderate", "major"],
    RANK_OWNER: ["minor", "moderate", "major"],
}
