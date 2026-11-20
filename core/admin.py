from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from core.models import AnalyticsMetric, ApiKey, Tenant, TenantMembership, User


@admin.register(Tenant)
class TenantAdmin(admin.ModelAdmin):
    list_display = ('name', 'plan_tier', 'subscription_status', 'stripe_customer_id', 'stripe_subscription_id')
    list_filter = ('plan_tier', 'subscription_status')
    search_fields = ('name', 'stripe_customer_id', 'stripe_subscription_id')


@admin.register(AnalyticsMetric)
class AnalyticsMetricAdmin(admin.ModelAdmin):
    list_display = ('metric_name', 'value', 'tenant', 'timestamp')
    list_filter = ('metric_name', 'tenant')
    search_fields = ('metric_name', 'tenant__name')


@admin.register(TenantMembership)
class TenantMembershipAdmin(admin.ModelAdmin):
    list_display = ('user', 'tenant', 'role', 'created_at')
    list_filter = ('role', 'tenant')
    search_fields = ('user__username', 'tenant__name')


@admin.register(ApiKey)
class ApiKeyAdmin(admin.ModelAdmin):
    list_display = ('name', 'tenant', 'prefix', 'created_at', 'last_used_at', 'revoked_at')
    list_filter = ('tenant', 'revoked_at')
    search_fields = ('name', 'prefix', 'tenant__name')
    readonly_fields = ('prefix', 'key_hash', 'created_at', 'last_used_at')


class CustomUserAdmin(UserAdmin):
    list_display = ('username', 'email', 'tenant', 'is_staff', 'is_active')
    list_filter = ('is_staff', 'is_superuser', 'is_active', 'tenant')

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
