"""
URL configuration for B2B_SaaS_Platform project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from core.views import (
    AnalyticsViewSet, StripeWebhookView,
    login_view, register_view, logout_view, 
    dashboard, add_metric, billing, create_checkout_session, create_billing_portal_session, healthz, members
)

router = DefaultRouter()
router.register(r'analytics', AnalyticsViewSet, basename='analytics')

urlpatterns = [
    path('healthz/', healthz, name='healthz'),
    path('admin/', admin.site.urls),
    path('api/v1/', include(router.urls)), # Make sure api/v1/ is written exactly like this
    path('api/v1/webhooks/stripe/', StripeWebhookView.as_view(), name='stripe-webhook'),

    path('', login_view, name='login_view'),
    path('workspace/register/', register_view, name='register_view'),
    path('workspace/logout/', logout_view, name='logout_view'),
    path('workspace/dashboard/', dashboard, name='dashboard'),
    path('workspace/dashboard/add/', add_metric, name='add_metric'),
    path('workspace/billing/', billing, name='billing'),
    path('workspace/billing/upgrade/', create_checkout_session, name='create_checkout_session'),
    path('workspace/billing/portal/', create_billing_portal_session, name='create_billing_portal_session'),
    path('workspace/members/', members, name='members'),
]
