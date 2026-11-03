from rest_framework.permissions import BasePermission

from core.models import TenantMembership


class HasTenantRole(BasePermission):
    """Require a membership in the authenticated user's active tenant."""
    message = 'Your workspace role does not allow this action.'

    def has_permission(self, request, view):
        tenant_id = getattr(request.user, 'tenant_id', None)
        if not request.user.is_authenticated or not tenant_id:
            return False
        allowed_roles = getattr(view, 'allowed_roles', TenantMembership.Role.values)
        return TenantMembership.objects.filter(
            tenant_id=tenant_id, user=request.user, role__in=allowed_roles
        ).exists()
