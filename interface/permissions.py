"""Permission management for cross-family access and self.md writes."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from interface.bus import FamilyPrefix
from interface.logging import LogCategory, ModuleLogger


class PermissionAction(StrEnum):
    """Actions that require permission checks."""

    WRITE_SELF_MD = "WRITE_SELF_MD"
    READ_CROSS_FAMILY = "READ_CROSS_FAMILY"
    SEND_CROSS_FAMILY = "SEND_CROSS_FAMILY"
    CHANGE_PROMPT = "CHANGE_PROMPT"
    CHANGE_MODEL = "CHANGE_MODEL"
    RESTART_MODULE = "RESTART_MODULE"
    SET_STATE = "SET_STATE"


@dataclass(frozen=True)
class PermissionGrant:
    """A single permission grant record."""

    grantee: FamilyPrefix
    action: PermissionAction
    target: str  # family prefix or "*" for all
    granted_by: FamilyPrefix


class PermissionManager:
    """Manages permission grants for cross-family operations.

    By default, <Pr> holds authority to write to any part of the project.
    Each family can access resources within its own scope freely.
    """

    def __init__(self, logger: ModuleLogger) -> None:
        self._logger = logger
        self._grants: list[PermissionGrant] = []
        self._init_defaults()

    def _init_defaults(self) -> None:
        """Set up default permissions.

        - Pr gets all actions on all targets.
        - Each family gets own-scope permissions.
        """
        # Pr has universal access
        for action in PermissionAction:
            self._grants.append(
                PermissionGrant(
                    grantee=FamilyPrefix.Pr,
                    action=action,
                    target="*",
                    granted_by=FamilyPrefix.Pr,
                )
            )

        # Ev has authority to set state on all families
        self._grants.append(
            PermissionGrant(
                grantee=FamilyPrefix.Ev,
                action=PermissionAction.SET_STATE,
                target="*",
                granted_by=FamilyPrefix.Pr,
            )
        )

        # Each family can write its own self.md section and manage itself
        for prefix in FamilyPrefix:
            for action in (
                PermissionAction.WRITE_SELF_MD,
                PermissionAction.CHANGE_PROMPT,
                PermissionAction.CHANGE_MODEL,
                PermissionAction.RESTART_MODULE,
            ):
                self._grants.append(
                    PermissionGrant(
                        grantee=prefix,
                        action=action,
                        target=prefix.value,
                        granted_by=FamilyPrefix.Pr,
                    )
                )

    def check(
        self, requester: FamilyPrefix, action: PermissionAction, target: str
    ) -> bool:
        """Check whether requester has permission for action on target."""
        for grant in self._grants:
            if (
                grant.grantee == requester
                and grant.action == action
                and grant.target in (target, "*")
            ):
                self._logger.log(
                    10,
                    LogCategory.PERMISSION,
                    f"GRANTED: {requester} -> {action} on {target}",
                )
                return True
        self._logger.log(
            30,
            LogCategory.PERMISSION,
            f"DENIED: {requester} -> {action} on {target}",
        )
        return False

    def grant(
        self,
        grantee: FamilyPrefix,
        action: PermissionAction,
        target: str,
        granted_by: FamilyPrefix,
    ) -> None:
        """Grant a permission. Only Pr or the target owner can grant."""
        if granted_by != FamilyPrefix.Pr and granted_by.value != target:
            raise PermissionError(
                f"{granted_by} cannot grant permissions on {target}. "
                f"Only Pr or {target} can grant."
            )
        new_grant = PermissionGrant(
            grantee=grantee, action=action, target=target, granted_by=granted_by
        )
        if new_grant not in self._grants:
            self._grants.append(new_grant)
            self._logger.log(
                20,
                LogCategory.PERMISSION,
                f"GRANT: {granted_by} granted {grantee} -> {action} on {target}",
            )

    def revoke(
        self,
        grantee: FamilyPrefix,
        action: PermissionAction,
        target: str,
        revoked_by: FamilyPrefix,
    ) -> None:
        """Revoke a permission. Only Pr or the target owner can revoke."""
        if revoked_by != FamilyPrefix.Pr and revoked_by.value != target:
            raise PermissionError(
                f"{revoked_by} cannot revoke permissions on {target}."
            )
        self._grants = [
            g
            for g in self._grants
            if not (
                g.grantee == grantee and g.action == action and g.target == target
            )
        ]
        self._logger.log(
            20,
            LogCategory.PERMISSION,
            f"REVOKE: {revoked_by} revoked {grantee} -> {action} on {target}",
        )

    def list_grants(
        self, family: FamilyPrefix | None = None
    ) -> list[PermissionGrant]:
        """List all grants, optionally filtered by grantee family."""
        if family is None:
            return list(self._grants)
        return [g for g in self._grants if g.grantee == family]
