from django.db import connection

from core.utils import clear_current_tenant, set_current_tenant


class TenantMiddleware:
    """Sets both ORM and PostgreSQL tenant context for the complete request lifecycle."""
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        tenant = request.user.tenant if request.user.is_authenticated and request.user.tenant_id else None
        token = set_current_tenant(tenant)
        try:
            if connection.vendor == 'postgresql':
                with connection.cursor() as cursor:
                    cursor.execute("SELECT set_config('app.tenant_id', %s, false)", [str(tenant.id) if tenant else ''])
            return self.get_response(request)
        finally:
            if connection.vendor == 'postgresql':
                with connection.cursor() as cursor:
                    cursor.execute("SELECT set_config('app.tenant_id', '', false)")
            clear_current_tenant(token)
