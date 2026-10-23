import hashlib
import secrets

from django.db import models
from django.contrib.auth.models import AbstractUser

# Represents an independent business/tenant on our platform
class Tenant(models.Model):
    name = models.CharField(max_length=255, unique=True)
    stripe_customer_id = models.CharField(max_length=255, blank=True, null=True)
    stripe_subscription_id = models.CharField(max_length=255, blank=True, null=True)
    subscription_status = models.CharField(max_length=50, blank=True)
    plan_tier = models.CharField(
        max_length=20, 
        choices=[('trial', 'Trial'), ('paid', 'Paid')], 
        default='trial'
    )

    def __str__(self):
        return self.name

# Extends standard users so they belong strictly to one company (Tenant)
class User(AbstractUser):
    # `tenant` is the active workspace during this single-workspace release.
    # Memberships provide the authorization boundary and support a future workspace switcher.
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='users', null=True, blank=True)


class TenantMembership(models.Model):
    class Role(models.TextChoices):
        OWNER = 'owner', 'Owner'
        ADMIN = 'admin', 'Administrator'
        ANALYST = 'analyst', 'Analyst'
        VIEWER = 'viewer', 'Viewer'

    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='memberships')
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='memberships')
    role = models.CharField(max_length=20, choices=Role.choices, default=Role.VIEWER)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['tenant', 'user'], name='unique_tenant_membership')]
        indexes = [models.Index(fields=['tenant', 'role'])]

    def __str__(self):
        return f'{self.user.username} · {self.tenant.name} · {self.role}'

# The automated database filter to ensure cross-company data visibility never happens
class TenantManager(models.Manager):
    def get_queryset(self):
        import core.utils
        current_tenant = core.utils.get_current_tenant()
        if current_tenant:
            return super().get_queryset().filter(tenant=current_tenant)
        return super().get_queryset().none() # Blanket protection block

# A sample data table representing raw analytics information
class AnalyticsMetric(models.Model):
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE)
    metric_name = models.CharField(max_length=100)
    value = models.FloatField()
    timestamp = models.DateTimeField(auto_now_add=True)

    objects = TenantManager() # Safely filters data automatically
    unscoped_objects = models.Manager() # Explicit back-door bypass for stripe webhooks

    class Meta:
        indexes = [models.Index(fields=['tenant', '-timestamp'])]
        constraints = [
            models.UniqueConstraint(fields=['tenant', 'metric_name', 'timestamp'], name='unique_tenant_metric_timestamp')
        ]


class StripeEvent(models.Model):
    """Processed webhook ids: prevents duplicate Stripe deliveries changing state twice."""
    stripe_event_id = models.CharField(max_length=255, unique=True)
    event_type = models.CharField(max_length=100)
    processed_at = models.DateTimeField(auto_now_add=True)


class ApiKey(models.Model):
    """Tenant API key material is never stored; only its SHA-256 digest is persisted."""
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='api_keys')
    name = models.CharField(max_length=100)
    prefix = models.CharField(max_length=12, db_index=True)
    key_hash = models.CharField(max_length=64, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    last_used_at = models.DateTimeField(blank=True, null=True)
    revoked_at = models.DateTimeField(blank=True, null=True)

    @classmethod
    def issue(cls, tenant, name):
        secret = secrets.token_urlsafe(32)
        raw_key = f'nxr_{secret}'
        return raw_key, cls.objects.create(
            tenant=tenant, name=name, prefix=raw_key[:12], key_hash=hashlib.sha256(raw_key.encode()).hexdigest()
        )
