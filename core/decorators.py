from functools import wraps

from django.contrib import messages
from django.shortcuts import redirect

from core.models import TenantMembership


def require_workspace_role(*roles):
    def decorator(view):
        @wraps(view)
        def wrapped(request, *args, **kwargs):
            if TenantMembership.objects.filter(user=request.user, tenant_id=request.user.tenant_id, role__in=roles).exists():
                return view(request, *args, **kwargs)
            messages.error(request, 'Your workspace role does not allow this action.')
            return redirect('dashboard')
        return wrapped
    return decorator
