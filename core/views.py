import stripe
from django.conf import settings
from django.contrib import messages
from django.db import IntegrityError, transaction
from django.http import HttpResponse, HttpResponseBadRequest
from django.http import JsonResponse
from django.core.cache import cache
from django.db import connection
from rest_framework import viewsets
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated, AllowAny
from core.models import AnalyticsMetric, StripeEvent, Tenant, User
from core.serializers import AnalyticsMetricSerializer
from core.throttling import TieredRateThrottle
from django.db.models import QuerySet
from django.shortcuts import render, redirect
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from core.decorators import require_workspace_role
from core.models import TenantMembership
from core.permissions import HasTenantRole


class AnalyticsViewSet(viewsets.ModelViewSet):
    serializer_class = AnalyticsMetricSerializer
    permission_classes = [IsAuthenticated, HasTenantRole]
    throttle_classes = [TieredRateThrottle]
    allowed_roles = [
        TenantMembership.Role.OWNER,
        TenantMembership.Role.ADMIN,
        TenantMembership.Role.ANALYST,
        TenantMembership.Role.VIEWER,
    ]

    def get_permissions(self):
        if self.action in {'create', 'update', 'partial_update', 'destroy'}:
            self.allowed_roles = [
                TenantMembership.Role.OWNER,
                TenantMembership.Role.ADMIN,
                TenantMembership.Role.ANALYST,
            ]
        return super().get_permissions()

    # Explicitly telling Pylance this returns a standard QuerySet
    def get_queryset(self) -> QuerySet:
        # This explicit filter is intentional defence in depth for API authentication.
        return AnalyticsMetric.unscoped_objects.filter(tenant=self.request.user.tenant)

class StripeWebhookView(APIView):
    permission_classes = [AllowAny]

    def post(self, request, *args, **kwargs):
        payload = request.body
        sig_header = request.META.get('HTTP_STRIPE_SIGNATURE', '')
        
        if not settings.STRIPE_WEBHOOK_SECRET:
            return HttpResponseBadRequest('Stripe webhook secret is not configured.')
        try:
            event = stripe.Webhook.construct_event(payload, sig_header, settings.STRIPE_WEBHOOK_SECRET)
        except (ValueError, stripe.error.SignatureVerificationError):
            return HttpResponse(status=400)

        event_id = event['id']
        event_type = event['type']
        data_object = event['data']['object']
        customer_id = data_object.get('customer')

        try:
            with transaction.atomic():
                StripeEvent.objects.create(stripe_event_id=event_id, event_type=event_type)
                if customer_id:
                    tenant = Tenant.objects.filter(stripe_customer_id=customer_id).first()
                    if tenant:
                        if event_type in ['customer.subscription.created', 'customer.subscription.updated']:
                            tenant.plan_tier = 'paid' if data_object.get('status') in {'active', 'trialing'} else 'trial'
                            tenant.stripe_subscription_id = data_object.get('id', '')
                            tenant.subscription_status = data_object.get('status', '')
                        elif event_type == 'customer.subscription.deleted':
                            tenant.plan_tier = 'trial'
                            tenant.subscription_status = 'canceled'
                        tenant.save(update_fields=['plan_tier', 'stripe_subscription_id', 'subscription_status'])
        except IntegrityError:
            # Stripe retries are expected; a duplicate event has already been safely applied.
            pass

        return HttpResponse(status=200)

def login_view(request):
    if request.method == "POST":
        u = request.POST.get("username")
        p = request.POST.get("password")
        user = authenticate(request, username=u, password=p)
        if user is not None:
            login(request, user)
            return redirect("dashboard")
        return render(request, "login.html", {"error": "Invalid combination entry credentials."})
    return render(request, "login.html")

def register_view(request):
    if request.method == "POST":
        t_name = request.POST.get("tenant_name")
        u = request.POST.get("username")
        p = request.POST.get("password")
        
        if not all([t_name, u, p]):
            return render(request, 'register.html', {'error': 'Complete all fields to create a workspace.'})
        try:
            with transaction.atomic():
                new_tenant = Tenant.objects.create(name=t_name.strip(), plan_tier='trial')
                new_user = User.objects.create_user(username=u.strip(), password=p, tenant=new_tenant, is_staff=True)
                TenantMembership.objects.create(
                    tenant=new_tenant, user=new_user, role=TenantMembership.Role.OWNER
                )
        except IntegrityError:
            return render(request, 'register.html', {'error': 'That company name or username is already in use.'})
        
        login(request, new_user)
        return redirect("dashboard")
    return render(request, "register.html")

def logout_view(request):
    logout(request)
    return redirect("login_view")

@login_required(login_url="login_view")
def dashboard(request):
    # Use our standard tenant-aware objects manager layer to pull metrics safely
    metrics = AnalyticsMetric.objects.all().order_by('-timestamp')
    
    membership = TenantMembership.objects.filter(tenant=request.user.tenant, user=request.user).first()
    return render(request, "dashboard.html", {"metrics": metrics, "membership": membership})

@login_required(login_url="login_view")
@require_workspace_role(TenantMembership.Role.OWNER, TenantMembership.Role.ADMIN, TenantMembership.Role.ANALYST)
def add_metric(request):
    if request.method == "POST":
        name = request.POST.get("metric_name")
        val = request.POST.get("value")
        
        if name and val:
            try:
                AnalyticsMetric.objects.create(tenant=request.user.tenant, metric_name=name.strip(), value=float(val))
                messages.success(request, 'Metric recorded successfully.')
            except ValueError:
                messages.error(request, 'Enter a valid numeric value.')
    return redirect("dashboard")

@login_required(login_url="login_view")
def billing(request):
    return render(request, "billing.html")

# Mock Stripe Upgrade Session Controller Engine
@login_required(login_url="login_view")
@require_workspace_role(TenantMembership.Role.OWNER, TenantMembership.Role.ADMIN)
def create_checkout_session(request):
    if request.method == "POST":
        tenant = request.user.tenant
        if settings.BILLING_DEMO_MODE:
            tenant.plan_tier = 'paid'
            tenant.save(update_fields=['plan_tier'])
            messages.success(request, 'Demo workspace upgraded. Configure Stripe credentials for live billing.')
        elif not settings.STRIPE_SECRET_KEY or not settings.STRIPE_PRICE_ID:
            messages.error(request, 'Billing is not configured. Contact your workspace administrator.')
        else:
            stripe.api_key = settings.STRIPE_SECRET_KEY
            if not tenant.stripe_customer_id:
                customer = stripe.Customer.create(name=tenant.name, metadata={'tenant_id': tenant.id})
                tenant.stripe_customer_id = customer.id
                tenant.save(update_fields=['stripe_customer_id'])
            session = stripe.checkout.Session.create(
                customer=tenant.stripe_customer_id,
                mode='subscription', line_items=[{'price': settings.STRIPE_PRICE_ID, 'quantity': 1}],
                success_url=f'{settings.SITE_URL}/workspace/billing/?checkout=success',
                cancel_url=f'{settings.SITE_URL}/workspace/billing/?checkout=cancelled',
            )
            return redirect(session.url)
    return redirect("billing")


@login_required(login_url='login_view')
@require_workspace_role(TenantMembership.Role.OWNER, TenantMembership.Role.ADMIN)
def create_billing_portal_session(request):
    tenant = request.user.tenant
    if request.method != 'POST':
        return redirect('billing')
    if settings.BILLING_DEMO_MODE:
        messages.info(request, 'The Stripe customer portal is unavailable in demo mode.')
    elif not settings.STRIPE_SECRET_KEY or not tenant.stripe_customer_id:
        messages.error(request, 'No Stripe customer is configured for this workspace.')
    else:
        stripe.api_key = settings.STRIPE_SECRET_KEY
        try:
            session = stripe.billing_portal.Session.create(
                customer=tenant.stripe_customer_id,
                return_url=f'{settings.SITE_URL}/workspace/billing/',
            )
            return redirect(session.url)
        except stripe.StripeError:
            messages.error(request, 'Stripe could not open the customer portal. Please try again.')
    return redirect('billing')


@login_required(login_url='login_view')
@require_workspace_role(TenantMembership.Role.OWNER, TenantMembership.Role.ADMIN)
def members(request):
    tenant = request.user.tenant
    assignable_roles = [TenantMembership.Role.ADMIN, TenantMembership.Role.ANALYST, TenantMembership.Role.VIEWER]
    if request.method == 'POST':
        username = request.POST.get('username', '').strip()
        role = request.POST.get('role', TenantMembership.Role.VIEWER)
        target = User.objects.filter(username=username).first()
        if not target:
            messages.error(request, 'No user exists with that username. Ask them to register first.')
        elif role not in assignable_roles:
            messages.error(request, 'Only an existing owner can assign admin, analyst, or viewer roles.')
        else:
            TenantMembership.objects.update_or_create(tenant=tenant, user=target, defaults={'role': role})
            messages.success(request, f'{username} now has the {role} role.')
        return redirect('members')
    return render(request, 'members.html', {
        'memberships': tenant.memberships.select_related('user').order_by('role', 'user__username'),
        'roles': assignable_roles,
    })


def healthz(request):
    """Container/orchestrator health check for PostgreSQL and Redis."""
    try:
        with connection.cursor() as cursor:
            cursor.execute('SELECT 1')
        cache.set('healthcheck', 'ok', timeout=10)
        if cache.get('healthcheck') != 'ok':
            raise RuntimeError('Cache unavailable')
    except Exception:
        return JsonResponse({'status': 'unhealthy'}, status=503)
    return JsonResponse({'status': 'ok'})
