import unittest
from unittest.mock import MagicMock
from bot.config import (
    RANK_NONE,
    RANK_TRAINEE,
    RANK_MODERATOR,
    RANK_SENIOR_MOD,
    RANK_OWNER,
)
from bot.checks import get_member_staff_rank, is_staff, can_moderate


class TestHierarchyAndChecks(unittest.TestCase):
    def setUp(self):
        self.config = {
            "owner_role_id": 100,
            "staff_role_id": 101,
            "trainee_role_id": 102,
            "moderator_role_id": 103,
            "senior_mod_role_id": 104,
        }

    def _create_mock_member(self, role_ids, mention="@User"):
        member = MagicMock()
        member.mention = mention
        roles = []
        for rid in role_ids:
            role = MagicMock()
            role.id = rid
            roles.append(role)
        member.roles = roles
        return member

    def test_staff_hierarchy_ranks(self):
        owner = self._create_mock_member([100, 101])
        senior = self._create_mock_member([104, 101])
        mod = self._create_mock_member([103, 101])
        trainee = self._create_mock_member([102, 101])
        regular = self._create_mock_member([999])

        self.assertEqual(get_member_staff_rank(owner, self.config), RANK_OWNER)
        self.assertEqual(get_member_staff_rank(senior, self.config), RANK_SENIOR_MOD)
        self.assertEqual(get_member_staff_rank(mod, self.config), RANK_MODERATOR)
        self.assertEqual(get_member_staff_rank(trainee, self.config), RANK_TRAINEE)
        self.assertEqual(get_member_staff_rank(regular, self.config), RANK_NONE)

    def test_is_staff(self):
        staff_member = self._create_mock_member([101, 102])
        non_staff_member = self._create_mock_member([999])

        self.assertTrue(is_staff(staff_member, self.config))
        self.assertFalse(is_staff(non_staff_member, self.config))

    def test_prevention_of_lower_ranked_staff_acting_against_equal_or_higher_ranked_staff(self):
        owner = self._create_mock_member([100, 101], mention="@Owner")
        senior_1 = self._create_mock_member([104, 101], mention="@Senior1")
        senior_2 = self._create_mock_member([104, 101], mention="@Senior2")
        mod_1 = self._create_mock_member([103, 101], mention="@Mod1")
        mod_2 = self._create_mock_member([103, 101], mention="@Mod2")
        trainee = self._create_mock_member([102, 101], mention="@Trainee")
        regular = self._create_mock_member([999], mention="@Regular")

        # Trainee acting on regular user -> allowed
        allowed, _ = can_moderate(trainee, regular, self.config)
        self.assertTrue(allowed)

        # Trainee acting on Moderator -> prevented
        allowed, msg = can_moderate(trainee, mod_1, self.config)
        self.assertFalse(allowed)
        self.assertIn("equal or higher staff rank", msg)

        # Trainee acting on Senior Mod -> prevented
        allowed, _ = can_moderate(trainee, senior_1, self.config)
        self.assertFalse(allowed)

        # Moderator acting on another Moderator -> prevented
        allowed, msg = can_moderate(mod_1, mod_2, self.config)
        self.assertFalse(allowed)
        self.assertIn("equal or higher staff rank", msg)

        # Moderator acting on Senior Mod -> prevented
        allowed, _ = can_moderate(mod_1, senior_1, self.config)
        self.assertFalse(allowed)

        # Senior Mod acting on another Senior Mod -> prevented
        allowed, _ = can_moderate(senior_1, senior_2, self.config)
        self.assertFalse(allowed)

        # Senior Mod acting on Moderator -> allowed
        allowed, _ = can_moderate(senior_1, mod_1, self.config)
        self.assertTrue(allowed)

        # Owner acting on Senior Mod -> allowed
        allowed, _ = can_moderate(owner, senior_1, self.config)
        self.assertTrue(allowed)

        # Owner acting on another Owner -> prevented
        owner_2 = self._create_mock_member([100, 101], mention="@Owner2")
        allowed, _ = can_moderate(owner, owner_2, self.config)
        self.assertFalse(allowed)


if __name__ == "__main__":
    unittest.main()
