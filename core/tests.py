from django.test import TestCase
from django.urls import reverse
from django.core.cache import cache
from rest_framework.test import APIClient

from core.models import AnalyticsMetric, Tenant, TenantMembership, User
from core.utils import clear_current_tenant, set_current_tenant


class TenantIsolationTests(TestCase):
    def setUp(self):
        self.alpha = Tenant.objects.create(name='Alpha')
        self.beta = Tenant.objects.create(name='Beta')
        self.user = User.objects.create_user(username='alpha-admin', password='safe-password', tenant=self.alpha)
        TenantMembership.objects.create(tenant=self.alpha, user=self.user, role=TenantMembership.Role.OWNER)
        AnalyticsMetric.unscoped_objects.create(tenant=self.alpha, metric_name='revenue', value=10)
        AnalyticsMetric.unscoped_objects.create(tenant=self.beta, metric_name='revenue', value=99)

    def tearDown(self):
        clear_current_tenant()

    def test_manager_never_exposes_a_second_tenant(self):
        token = set_current_tenant(self.alpha)
        self.assertEqual(list(AnalyticsMetric.objects.values_list('value', flat=True)), [10])
        clear_current_tenant(token)

    def test_dashboard_is_scoped_to_authenticated_tenant(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse('dashboard'))
        self.assertContains(response, '10.0')
        self.assertNotContains(response, '99.0')


class WorkspaceRoleAndThrottleTests(TestCase):
    def setUp(self):
        cache.clear()
        self.tenant = Tenant.objects.create(name='Northstar')
        self.user = User.objects.create_user(username='viewer', password='safe-password', tenant=self.tenant)
        self.client = APIClient()
        self.client.force_authenticate(self.user)
        self.url = reverse('analytics-list')

    def test_viewer_cannot_create_a_metric(self):
        TenantMembership.objects.create(tenant=self.tenant, user=self.user, role=TenantMembership.Role.VIEWER)
        response = self.client.post(self.url, {'metric_name': 'mrr', 'value': 100}, format='json')
        self.assertEqual(response.status_code, 403)

    def test_analyst_can_create_a_metric(self):
        TenantMembership.objects.create(tenant=self.tenant, user=self.user, role=TenantMembership.Role.ANALYST)
        response = self.client.post(self.url, {'metric_name': 'mrr', 'value': 100}, format='json')
        self.assertEqual(response.status_code, 201)
        self.assertEqual(AnalyticsMetric.unscoped_objects.get().tenant, self.tenant)

    def test_trial_workspace_is_throttled_by_shared_cache_key(self):
        TenantMembership.objects.create(tenant=self.tenant, user=self.user, role=TenantMembership.Role.VIEWER)
        for _ in range(60):
            self.assertEqual(self.client.get(self.url).status_code, 200)
        self.assertEqual(self.client.get(self.url).status_code, 429)
