from typing import Optional, Dict, Any
from bot.config import (
    RANK_NONE,
    RANK_TRAINEE,
    RANK_MODERATOR,
    RANK_SENIOR_MOD,
    RANK_OWNER,
    RANK_NAMES,
)


def get_member_role_ids(member: Any) -> set:
    if not member or not hasattr(member, "roles"):
        return set()
    return {role.id for role in member.roles}


def get_member_staff_rank(member: Any, config: Optional[Dict[str, Any]]) -> int:
    """
    Determines member's staff rank based on configured role IDs.
    Returns highest rank found among member's roles.
    """
    if not member or not config:
        return RANK_NONE

    user_role_ids = get_member_role_ids(member)

    # Check from highest to lowest rank
    if config.get("owner_role_id") and config["owner_role_id"] in user_role_ids:
        return RANK_OWNER
    if config.get("senior_mod_role_id") and config["senior_mod_role_id"] in user_role_ids:
        return RANK_SENIOR_MOD
    if config.get("moderator_role_id") and config["moderator_role_id"] in user_role_ids:
        return RANK_MODERATOR
    if config.get("trainee_role_id") and config["trainee_role_id"] in user_role_ids:
        return RANK_TRAINEE

    return RANK_NONE


def is_staff(member: Any, config: Optional[Dict[str, Any]]) -> bool:
    if not member or not config:
        return False
    user_role_ids = get_member_role_ids(member)
    staff_role_id = config.get("staff_role_id")
    if staff_role_id and staff_role_id in user_role_ids:
        return True
    return get_member_staff_rank(member, config) > RANK_NONE


def can_moderate(
    actor: Any, target: Any, config: Optional[Dict[str, Any]]
) -> tuple[bool, str]:
    """
    Checks if actor can perform moderation action on target based on staff hierarchy safety.
    Returns (allowed: bool, reason: str).
    """
    if not config:
        return False, "Moderation system is not configured for this server."

    actor_rank = get_member_staff_rank(actor, config)
    if actor_rank == RANK_NONE:
        return False, "You do not have a moderation rank."

    target_rank = get_member_staff_rank(target, config)

    # Lower-ranked moderators cannot act on equal or higher-ranked staff
    if target_rank > RANK_NONE and actor_rank <= target_rank:
        return False, (
            f"You cannot perform moderation actions against {target.mention} "
            f"because they have an equal or higher staff rank ({RANK_NAMES[target_rank]})."
        )

    return True, ""
