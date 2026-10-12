# Nexora

Nexora is a production-minded, multi-tenant B2B analytics and subscription SaaS. It demonstrates a defence-in-depth tenant boundary: application query scoping, role-based access control, and PostgreSQL Row-Level Security.

## Architecture

```text
Browser / REST client
        │
   Django + DRF ─── Redis (shared tiered throttling)
        │
 PostgreSQL + RLS ─── Stripe Checkout, Portal and signed webhooks
```

### Implemented features

- Tenant-isolated analytics API (`/api/v1/analytics/`) and dashboard.
- PostgreSQL RLS policy, tenant-aware ORM manager, and request-scoped PostgreSQL tenant variable.
- Workspace memberships: owner, admin, analyst, and viewer roles; viewers cannot write through either UI or API.
- Trial workspaces are throttled to 60 requests/minute; paid workspaces are unlimited. The shared Django cache uses Redis, so the limit works across application instances.
- Stripe Checkout, Customer Portal, signed idempotent webhook processing, and subscription status persistence.
- Docker Compose local stack: Django, PostgreSQL, Redis. `/healthz/` validates database and cache availability.
- Automated regression tests and GitHub Actions CI.

## Local setup

Docker Desktop must be running. From the project root:

```powershell
docker compose up -d --build
docker compose exec web python manage.py migrate --noinput
Get-Content deployment\postgres-rls.sql | docker compose exec -T db psql -U saas_app -d saas_platform
```

Open `http://localhost:8000`, create a workspace, then use `http://localhost:8000/admin/` after creating an administrator:

```powershell
docker compose exec web python manage.py createsuperuser
```

Run verification:

```powershell
docker compose exec web python manage.py test
docker compose exec web python manage.py check
```

## Roles

| Role | Read metrics | Create/update metrics | Manage members/billing |
| --- | --- | --- | --- |
| Owner | Yes | Yes | Yes |
| Admin | Yes | Yes | Yes |
| Analyst | Yes | Yes | No |
| Viewer | Yes | No | No |

## Stripe

For local Stripe testing set `BILLING_DEMO_MODE=false` plus `STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET`, and `STRIPE_PRICE_ID`. Then forward events with:

```powershell
stripe listen --forward-to localhost:8000/api/v1/webhooks/stripe/
```

Subscribe using test mode. Nexora stores each Stripe event ID, so Stripe retries do not apply subscription changes twice. The Customer Portal is available to owners and admins on the Billing page.

## Production deployment

The project includes [render.yaml](render.yaml) and detailed [Render deployment steps](deployment/render.md). Use a managed PostgreSQL database, managed Redis, HTTPS, and `DJANGO_DEBUG=false`. Set a long random `DJANGO_SECRET_KEY`, restrict `DJANGO_ALLOWED_HOSTS`, set `SITE_URL`, apply migrations, then apply `deployment/postgres-rls.sql` with the database owner.

For a strict production database boundary, use separate migration-owner and application database roles. The web application's role must not own tenant tables and must not have PostgreSQL's `BYPASSRLS` privilege.

## Resume summary

> Built and deployed Nexora, a multi-tenant B2B analytics SaaS using Django, DRF, PostgreSQL RLS, Stripe subscriptions, Redis-backed tiered rate limits, Docker, CI/CD, and role-based workspace access.

