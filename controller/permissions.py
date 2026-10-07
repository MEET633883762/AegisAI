"""Permission helpers for the controller boundary."""
from __future__ import annotations

from environment.actions import Role


def role_can_submit(role: Role, expected: Role) -> bool:
    """Strict role separation. There is no implicit cross-role permission."""
    return role is expected
