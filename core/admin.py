from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from core.models import AnalyticsMetric, ApiKey, Tenant, TenantMembership, User

admin.site.register(Tenant)
admin.site.register(AnalyticsMetric)
admin.site.register(TenantMembership)
admin.site.register(ApiKey)

class CustomUserAdmin(UserAdmin):
    # We use a list conversion to cleanly append the new field without typing issues
    def get_fieldsets(self, request, obj=None):
        fieldsets = list(super().get_fieldsets(request, obj))
        fieldsets.append(('Multi-Tenancy Info', {'fields': ('tenant',)}))
        return tuple(fieldsets)

    def get_add_fieldsets(self, request):
        fieldsets = list(super().get_add_fieldsets(request))
        fieldsets.append(('Multi-Tenancy Info', {'fields': ('tenant',)}))
        return tuple(fieldsets)

admin.site.register(User, CustomUserAdmin)
