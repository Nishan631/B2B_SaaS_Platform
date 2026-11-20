import hashlib
from unittest.mock import patch

from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse
from rest_framework.test import APIClient

from core.models import AnalyticsMetric, ApiKey, StripeEvent, Tenant, TenantMembership, User
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

    def test_paid_workspace_is_not_throttled(self):
        self.tenant.plan_tier = 'paid'
        self.tenant.save(update_fields=['plan_tier'])
        TenantMembership.objects.create(tenant=self.tenant, user=self.user, role=TenantMembership.Role.ANALYST)
        for _ in range(65):
            self.assertEqual(self.client.get(self.url).status_code, 200)


class WorkspaceAuthAndLifecycleTests(TestCase):
    def test_registration_creates_tenant_user_and_owner_membership(self):
        response = self.client.post(reverse('register_view'), {
            'tenant_name': 'Acme Global',
            'username': 'acme_founder',
            'password': 'StrongPassword123!',
        })
        self.assertRedirects(response, reverse('dashboard'))

        tenant = Tenant.objects.get(name='Acme Global')
        self.assertEqual(tenant.plan_tier, 'trial')
        user = User.objects.get(username='acme_founder')
        self.assertEqual(user.tenant, tenant)
        membership = TenantMembership.objects.get(tenant=tenant, user=user)
        self.assertEqual(membership.role, TenantMembership.Role.OWNER)

    def test_registration_rejects_duplicate_tenant(self):
        Tenant.objects.create(name='Existing Corp')
        response = self.client.post(reverse('register_view'), {
            'tenant_name': 'Existing Corp',
            'username': 'new_user',
            'password': 'StrongPassword123!',
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'already in use')

    def test_login_and_logout_flow(self):
        tenant = Tenant.objects.create(name='LoginCorp')
        user = User.objects.create_user(username='login_user', password='MyPassword123', tenant=tenant)
        TenantMembership.objects.create(tenant=tenant, user=user, role=TenantMembership.Role.OWNER)

        # Failed login
        fail_response = self.client.post(reverse('login_view'), {'username': 'login_user', 'password': 'WrongPassword'})
        self.assertEqual(fail_response.status_code, 200)
        self.assertContains(fail_response, 'Invalid combination')

        # Successful login
        success_response = self.client.post(reverse('login_view'), {'username': 'login_user', 'password': 'MyPassword123'})
        self.assertRedirects(success_response, reverse('dashboard'))

        # Logout
        logout_response = self.client.get(reverse('logout_view'))
        self.assertRedirects(logout_response, reverse('login_view'))

    def test_dashboard_autolinks_membership_when_user_tenant_unset(self):
        tenant = Tenant.objects.create(name='UnsetCorp')
        user = User.objects.create_user(username='unset_user', password='password123', tenant=None)
        TenantMembership.objects.create(tenant=tenant, user=user, role=TenantMembership.Role.ADMIN)

        self.client.force_login(user)
        response = self.client.get(reverse('dashboard'))
        self.assertEqual(response.status_code, 200)
        user.refresh_from_db()
        self.assertEqual(user.tenant, tenant)

    def test_billing_autolinks_membership_when_user_tenant_unset(self):
        tenant = Tenant.objects.create(name='BillingUnsetCorp')
        user = User.objects.create_user(username='unset_billing_user', password='password123', tenant=None)
        TenantMembership.objects.create(tenant=tenant, user=user, role=TenantMembership.Role.ADMIN)

        self.client.force_login(user)
        response = self.client.get(reverse('billing'))
        self.assertEqual(response.status_code, 200)
        user.refresh_from_db()
        self.assertEqual(user.tenant, tenant)


class MemberManagementTests(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(name='TeamCorp')
        self.owner = User.objects.create_user(username='team_owner', password='password123', tenant=self.tenant)
        TenantMembership.objects.create(tenant=self.tenant, user=self.owner, role=TenantMembership.Role.OWNER)

        self.member = User.objects.create_user(username='teammate', password='password123', tenant=None)

    def test_owner_can_assign_member_role_and_links_active_tenant(self):
        self.client.force_login(self.owner)
        response = self.client.post(reverse('members'), {
            'username': 'teammate',
            'role': TenantMembership.Role.ANALYST,
        })
        self.assertRedirects(response, reverse('members'))

        membership = TenantMembership.objects.get(tenant=self.tenant, user=self.member)
        self.assertEqual(membership.role, TenantMembership.Role.ANALYST)
        self.member.refresh_from_db()
        self.assertEqual(self.member.tenant, self.tenant)

    def test_owner_role_cannot_be_demoted(self):
        admin_user = User.objects.create_user(username='team_admin', password='password123', tenant=self.tenant)
        TenantMembership.objects.create(tenant=self.tenant, user=admin_user, role=TenantMembership.Role.ADMIN)

        self.client.force_login(admin_user)
        response = self.client.post(reverse('members'), {
            'username': 'team_owner',
            'role': TenantMembership.Role.VIEWER,
        })
        self.assertRedirects(response, reverse('members'))
        owner_membership = TenantMembership.objects.get(tenant=self.tenant, user=self.owner)
        self.assertEqual(owner_membership.role, TenantMembership.Role.OWNER)

    def test_viewer_cannot_access_members_page(self):
        viewer = User.objects.create_user(username='team_viewer', password='password123', tenant=self.tenant)
        TenantMembership.objects.create(tenant=self.tenant, user=viewer, role=TenantMembership.Role.VIEWER)

        self.client.force_login(viewer)
        response = self.client.get(reverse('members'))
        self.assertRedirects(response, reverse('dashboard'))


class MetricIngestionTests(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(name='MetricsCorp')
        self.owner = User.objects.create_user(username='metrics_owner', password='password123', tenant=self.tenant)
        TenantMembership.objects.create(tenant=self.tenant, user=self.owner, role=TenantMembership.Role.OWNER)

    def test_owner_can_add_metric_via_ui(self):
        self.client.force_login(self.owner)
        response = self.client.post(reverse('add_metric'), {
            'metric_name': 'monthly_active_users',
            'value': '1250',
        })
        self.assertRedirects(response, reverse('dashboard'))
        metric = AnalyticsMetric.unscoped_objects.get(tenant=self.tenant)
        self.assertEqual(metric.metric_name, 'monthly_active_users')
        self.assertEqual(metric.value, 1250.0)

    def test_viewer_cannot_add_metric_via_ui(self):
        viewer = User.objects.create_user(username='metric_viewer', password='password123', tenant=self.tenant)
        TenantMembership.objects.create(tenant=self.tenant, user=viewer, role=TenantMembership.Role.VIEWER)

        self.client.force_login(viewer)
        response = self.client.post(reverse('add_metric'), {
            'metric_name': 'hacked_metric',
            'value': '9999',
        })
        self.assertRedirects(response, reverse('dashboard'))
        self.assertFalse(AnalyticsMetric.unscoped_objects.filter(metric_name='hacked_metric').exists())


class BillingAndStripeWebhookTests(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(name='BillingCorp', stripe_customer_id='cus_test_123')
        self.owner = User.objects.create_user(username='billing_owner', password='password123', tenant=self.tenant)
        TenantMembership.objects.create(tenant=self.tenant, user=self.owner, role=TenantMembership.Role.OWNER)

    @override_settings(BILLING_DEMO_MODE=True)
    def test_create_checkout_session_in_demo_mode_upgrades_workspace(self):
        self.client.force_login(self.owner)
        response = self.client.post(reverse('create_checkout_session'))
        self.assertRedirects(response, reverse('billing'))
        self.tenant.refresh_from_db()
        self.assertEqual(self.tenant.plan_tier, 'paid')

    @override_settings(STRIPE_WEBHOOK_SECRET='whsec_test_secret')
    def test_stripe_webhook_rejects_missing_signature(self):
        response = self.client.post(
            reverse('stripe-webhook'),
            data=b'{"id": "evt_1"}',
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 400)

    @override_settings(STRIPE_WEBHOOK_SECRET='whsec_test_secret')
    @patch('stripe.Webhook.construct_event')
    def test_stripe_webhook_activates_subscription_and_is_idempotent(self, mock_construct):
        mock_construct.return_value = {
            'id': 'evt_sub_created_1',
            'type': 'customer.subscription.created',
            'data': {
                'object': {
                    'id': 'sub_test_abc',
                    'customer': 'cus_test_123',
                    'status': 'active',
                }
            }
        }

        # First delivery
        response = self.client.post(
            reverse('stripe-webhook'),
            data=b'{}',
            content_type='application/json',
            HTTP_STRIPE_SIGNATURE='valid_signature'
        )
        self.assertEqual(response.status_code, 200)
        self.tenant.refresh_from_db()
        self.assertEqual(self.tenant.plan_tier, 'paid')
        self.assertEqual(self.tenant.stripe_subscription_id, 'sub_test_abc')
        self.assertEqual(self.tenant.subscription_status, 'active')
        self.assertTrue(StripeEvent.objects.filter(stripe_event_id='evt_sub_created_1').exists())

        # Duplicate delivery retry (idempotent handling)
        retry_response = self.client.post(
            reverse('stripe-webhook'),
            data=b'{}',
            content_type='application/json',
            HTTP_STRIPE_SIGNATURE='valid_signature'
        )
        self.assertEqual(retry_response.status_code, 200)

    @override_settings(STRIPE_WEBHOOK_SECRET='whsec_test_secret')
    @patch('stripe.Webhook.construct_event')
    def test_stripe_webhook_cancels_subscription(self, mock_construct):
        self.tenant.plan_tier = 'paid'
        self.tenant.save()

        mock_construct.return_value = {
            'id': 'evt_sub_deleted_1',
            'type': 'customer.subscription.deleted',
            'data': {
                'object': {
                    'customer': 'cus_test_123',
                }
            }
        }

        response = self.client.post(
            reverse('stripe-webhook'),
            data=b'{}',
            content_type='application/json',
            HTTP_STRIPE_SIGNATURE='valid_signature'
        )
        self.assertEqual(response.status_code, 200)
        self.tenant.refresh_from_db()
        self.assertEqual(self.tenant.plan_tier, 'trial')
        self.assertEqual(self.tenant.subscription_status, 'canceled')


class HealthzAndApiKeyTests(TestCase):
    def test_healthz_endpoint_returns_ok(self):
        response = self.client.get(reverse('healthz'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {'status': 'ok'})

    def test_api_key_issuance_creates_prefix_and_sha256_hash(self):
        tenant = Tenant.objects.create(name='ApiKeyCorp')
        raw_key, api_key_obj = ApiKey.issue(tenant=tenant, name='Production Service')

        self.assertTrue(raw_key.startswith('nxr_'))
        self.assertEqual(api_key_obj.prefix, raw_key[:12])
        self.assertEqual(api_key_obj.key_hash, hashlib.sha256(raw_key.encode()).hexdigest())
        self.assertEqual(api_key_obj.tenant, tenant)
        self.assertIn('Production Service', str(api_key_obj))
