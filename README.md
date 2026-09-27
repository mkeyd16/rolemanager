# Multipurpose Discord Bot

A simple, production-ready, modular Discord bot written in Python using `discord.py 2.x` and SQLite.

## Features

- **Slash Commands**: Modern Discord slash command interface.
- **SQLite Database**: Persistent per-guild configuration and tracking using parameterized queries.
- **Role & Channel Configuration**: Persistent role and channel ID storage resilient to role/channel renames, position changes, or color edits.
- **Staff Hierarchy**: Enforces moderation authority hierarchy (`Owner` > `Senior Mod` > `Moderator` > `Trainee`). Lower-ranked staff cannot moderate equal or higher-ranked staff.
- **Moderation Tools**: `/warn` (targets user's last active message channel) and `/punish` with severity-restricted timeouts (`minor` 10m, `moderate` 45m, `major` 48h).
- **Staff Management**: Owner-only `/hire`, `/promote`, and `/fire` commands.
- **Join/Leave Logging**: Tracks member joins (with account age) and leaves (calculating time in server).
- **Moderation Audit Logs**: Posts embeds for all moderation and staff actions in the configured moderation logs channel.

---

## Staff Hierarchy & Permissions

The bot uses configured role IDs stored in SQLite rather than role names.

### Hierarchy
```
Owner
  ↓
Senior Mod
  ↓
Moderator
  ↓
Trainee
```

`Staff` is an umbrella role assigned to all active staff members. A staff member normally has the `Staff` role plus exactly one moderation rank.

### Permissions Matrix

| Command / Severity | Trainee | Moderator | Senior Mod | Owner | Admin |
| :--- | :---: | :---: | :---: | :---: | :---: |
| `/setup` | ❌ | ❌ | ❌ | ❌ | ✅ |
| `/warn` | ✅ | ✅ | ✅ | ✅ | ❌ |
| `/punish` (minor - 10m) | ✅ | ✅ | ✅ | ✅ | ❌ |
| `/punish` (moderate - 45m) | ❌ | ✅ | ✅ | ✅ | ❌ |
| `/punish` (major - 48h) | ❌ | ❌ | ✅ | ✅ | ❌ |
| `/hire` | ❌ | ❌ | ❌ | ✅ | ❌ |
| `/promote` | ❌ | ❌ | ❌ | ✅ | ❌ |
| `/fire` | ❌ | ❌ | ❌ | ✅ | ❌ |

---

## Slash Commands Overview

### Setup Commands (Administrator Only)
- `/setup moderation roles`: Automatically creates or reuses the required staff roles (`Owner`, `Staff`, `Trainee`, `Moderator`, `Senior Mod`) and saves their IDs in SQLite. Re-running this command is idempotent and will not create duplicate roles.
- `/setup moderation logs`: Creates or reuses a text channel for moderation logs and stores its ID in SQLite.
- `/setup join-leave [channel]`: Configures the text channel for member join and leave notifications.

### Moderation Commands
- `/warn [user] [reason]`: Sends a warning message to the target user in the last text channel where they spoke, and logs the action in the moderation logs channel.
- `/punish [user] [severity] [reason]`: Applies a Discord timeout based on severity (`minor`: 10m, `moderate`: 45m, `major`: 48h) according to staff rank permissions. Only sends confirmation after timeout is successfully applied.

### Staff Management Commands (Owner Only)
- `/hire [user]`: Assigns `Staff` and `Trainee` roles to a user.
- `/promote [user]`: Promotes a staff member along the path `Trainee -> Moderator -> Senior Mod`.
- `/fire [user]`: Removes all staff roles from a user (does not kick or ban).

---

## Setup & Configuration

### Requirements
- Python 3.10 or higher
- Discord Bot Token with Privileged Gateway Intents enabled

### Privileged Gateway Intents Required
In the [Discord Developer Portal](https://discord.com/developers/applications):
1. Navigate to your Application -> **Bot**.
2. Enable **Server Members Intent**.
3. Enable **Message Content Intent**.

### Environment Variables
Copy `.env.example` to `.env` and fill in your bot token:
```bash
cp .env.example .env
```

`.env` content:
```env
DISCORD_TOKEN=your_actual_bot_token_here
```

---

## Running Locally on Windows

Double-click `START.bat` or run it from the command prompt:
```cmd
START.bat
```
`START.bat` will automatically create a virtual environment, install dependencies from `requirements.txt`, and launch the bot.

---

## Running Tests

Run the automated test suite with Python:
```bash
python -m unittest discover -s tests
```

---

## Cloud Deployment

The bot is designed to run cleanly on any cloud server or platform supporting Python (e.g. VPS, Render, Railway, Fly.io, Heroku):

1. Clone or upload the repository to your host.
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
3. Set the `DISCORD_TOKEN` environment variable in your provider's dashboard or environment config.
4. Set the start command to:
   ```bash
   python -m bot.main
   ```
5. Ensure persistent storage is available for `data/bot.db` if database state must survive container rebuilds.
