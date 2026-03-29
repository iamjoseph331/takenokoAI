"""Group: Permissions

Tests for interface/permissions.py — PermissionAction enum, PermissionGrant
dataclass, and PermissionManager with default grants, check, grant, revoke,
and list_grants.
"""

from __future__ import annotations

import pytest

from interface.bus import FamilyPrefix
from interface.permissions import (
    PermissionAction,
    PermissionGrant,
    PermissionManager,
)


# ── PermissionAction ──


class TestPermissionAction:
    def test_expected_values(self):
        expected = {
            "WRITE_SELF_MD",
            "READ_CROSS_FAMILY",
            "SEND_CROSS_FAMILY",
            "CHANGE_PROMPT",
            "CHANGE_MODEL",
            "RESTART_MODULE",
        }
        actual = {a.value for a in PermissionAction}
        assert actual == expected


# ── PermissionGrant ──


class TestPermissionGrant:
    def test_frozen_dataclass(self):
        grant = PermissionGrant(
            grantee=FamilyPrefix.Re,
            action=PermissionAction.WRITE_SELF_MD,
            target="Re",
            granted_by=FamilyPrefix.Pr,
        )
        assert grant.grantee == FamilyPrefix.Re
        assert grant.action == PermissionAction.WRITE_SELF_MD
        assert grant.target == "Re"
        assert grant.granted_by == FamilyPrefix.Pr

        with pytest.raises(AttributeError):
            grant.target = "Pr"  # type: ignore[misc]


# ── PermissionManager ──


class TestPermissionManagerDefaults:
    def test_pr_has_all_actions_on_wildcard(self, mock_permissions: PermissionManager):
        for action in PermissionAction:
            assert mock_permissions.check(FamilyPrefix.Pr, action, "*")

    def test_pr_has_all_actions_on_specific_targets(self, mock_permissions: PermissionManager):
        for action in PermissionAction:
            for prefix in FamilyPrefix:
                assert mock_permissions.check(FamilyPrefix.Pr, action, prefix.value)

    def test_each_family_has_own_scope_write_self_md(self, mock_permissions: PermissionManager):
        for prefix in FamilyPrefix:
            assert mock_permissions.check(
                prefix, PermissionAction.WRITE_SELF_MD, prefix.value
            )

    def test_each_family_has_own_scope_change_prompt(self, mock_permissions: PermissionManager):
        for prefix in FamilyPrefix:
            assert mock_permissions.check(
                prefix, PermissionAction.CHANGE_PROMPT, prefix.value
            )

    def test_each_family_has_own_scope_change_model(self, mock_permissions: PermissionManager):
        for prefix in FamilyPrefix:
            assert mock_permissions.check(
                prefix, PermissionAction.CHANGE_MODEL, prefix.value
            )

    def test_each_family_has_own_scope_restart_module(self, mock_permissions: PermissionManager):
        for prefix in FamilyPrefix:
            assert mock_permissions.check(
                prefix, PermissionAction.RESTART_MODULE, prefix.value
            )


class TestPermissionManagerCheck:
    def test_returns_true_for_valid(self, mock_permissions: PermissionManager):
        assert mock_permissions.check(
            FamilyPrefix.Re, PermissionAction.WRITE_SELF_MD, "Re"
        )

    def test_returns_false_for_cross_family_write(self, mock_permissions: PermissionManager):
        # Re should not be able to write Ev's section by default
        assert not mock_permissions.check(
            FamilyPrefix.Re, PermissionAction.WRITE_SELF_MD, "Ev"
        )

    def test_returns_false_for_no_read_cross_family(self, mock_permissions: PermissionManager):
        # Non-Pr families don't have READ_CROSS_FAMILY by default
        assert not mock_permissions.check(
            FamilyPrefix.Mo, PermissionAction.READ_CROSS_FAMILY, "Re"
        )


class TestPermissionManagerGrant:
    def test_grant_adds_permission(self, mock_permissions: PermissionManager):
        # Re cannot write Ev's section initially
        assert not mock_permissions.check(
            FamilyPrefix.Re, PermissionAction.WRITE_SELF_MD, "Ev"
        )
        # Pr grants it
        mock_permissions.grant(
            FamilyPrefix.Re,
            PermissionAction.WRITE_SELF_MD,
            "Ev",
            granted_by=FamilyPrefix.Pr,
        )
        assert mock_permissions.check(
            FamilyPrefix.Re, PermissionAction.WRITE_SELF_MD, "Ev"
        )

    def test_grant_raises_for_unauthorized_grantor(self, mock_permissions: PermissionManager):
        with pytest.raises(PermissionError, match="cannot grant"):
            mock_permissions.grant(
                FamilyPrefix.Re,
                PermissionAction.WRITE_SELF_MD,
                "Ev",
                granted_by=FamilyPrefix.Mo,  # Mo cannot grant on Ev's scope
            )

    def test_target_owner_can_grant(self, mock_permissions: PermissionManager):
        # Ev can grant permissions on its own scope
        mock_permissions.grant(
            FamilyPrefix.Re,
            PermissionAction.WRITE_SELF_MD,
            "Ev",
            granted_by=FamilyPrefix.Ev,
        )
        assert mock_permissions.check(
            FamilyPrefix.Re, PermissionAction.WRITE_SELF_MD, "Ev"
        )


class TestPermissionManagerRevoke:
    def test_revoke_removes_permission(self, mock_permissions: PermissionManager):
        # Re can write its own section by default
        assert mock_permissions.check(
            FamilyPrefix.Re, PermissionAction.WRITE_SELF_MD, "Re"
        )
        mock_permissions.revoke(
            FamilyPrefix.Re,
            PermissionAction.WRITE_SELF_MD,
            "Re",
            revoked_by=FamilyPrefix.Pr,
        )
        assert not mock_permissions.check(
            FamilyPrefix.Re, PermissionAction.WRITE_SELF_MD, "Re"
        )

    def test_revoke_raises_for_unauthorized_revoker(self, mock_permissions: PermissionManager):
        with pytest.raises(PermissionError, match="cannot revoke"):
            mock_permissions.revoke(
                FamilyPrefix.Re,
                PermissionAction.WRITE_SELF_MD,
                "Re",
                revoked_by=FamilyPrefix.Mo,  # Mo cannot revoke on Re's scope
            )


class TestPermissionManagerListGrants:
    def test_list_all_grants(self, mock_permissions: PermissionManager):
        grants = mock_permissions.list_grants()
        assert len(grants) > 0
        assert all(isinstance(g, PermissionGrant) for g in grants)

    def test_list_grants_with_family_filter(self, mock_permissions: PermissionManager):
        re_grants = mock_permissions.list_grants(family=FamilyPrefix.Re)
        assert all(g.grantee == FamilyPrefix.Re for g in re_grants)
        assert len(re_grants) > 0

    def test_list_grants_pr_has_most(self, mock_permissions: PermissionManager):
        pr_grants = mock_permissions.list_grants(family=FamilyPrefix.Pr)
        re_grants = mock_permissions.list_grants(family=FamilyPrefix.Re)
        # Pr has universal grants (all actions on "*") plus own-scope
        assert len(pr_grants) > len(re_grants)
