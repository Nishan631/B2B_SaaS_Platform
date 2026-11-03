from rest_framework.throttling import SimpleRateThrottle

class TieredRateThrottle(SimpleRateThrottle):
    """Uses the shared Django cache (Redis in deployed settings), keyed per workspace."""
    scope = 'tenant_tier'

    def get_cache_key(self, request, view):
        if not request.user.is_authenticated or not getattr(request.user, 'tenant_id', None):
            return None 

        tenant = request.user.tenant
        if tenant.plan_tier == 'paid':
            return None # Paid tier gets zero speed limits!

        return self.cache_format % {'scope': self.scope, 'ident': f"tenant_{tenant.id}"}

