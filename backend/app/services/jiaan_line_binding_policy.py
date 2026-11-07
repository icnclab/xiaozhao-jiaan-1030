"""Authorization rules for assigning one-time LINE binding codes.

Keeps the existing caregiver code workflow and adds supervisor/director/admin
LINE onboarding without granting permission to bind somebody else's LINE.
"""

BINDABLE_ROLES = frozenset({'caregiver', 'supervisor', 'director', 'admin'})


def can_issue_binding_code(actor_role: str, actor_id, target_role: str, target_id) -> bool:
    if target_role not in BINDABLE_ROLES:
        return False
    if actor_role == 'admin':
        return True
    if target_role == 'caregiver' and actor_role in ('supervisor', 'director'):
        return True
    if actor_role == 'director':
        return target_role == 'supervisor' or (target_role == 'director' and actor_id == target_id)
    if actor_role == 'supervisor':
        return target_role == 'supervisor' and actor_id == target_id
    return False


def requires_verified_real_line(role: str) -> bool:
    return role in {'supervisor', 'director', 'admin'}
