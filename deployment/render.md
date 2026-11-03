# Render deployment

1. Create a PostgreSQL database and Redis instance in Render.
2. Create a Web Service from this repository using Docker, or use `render.yaml` as a Blueprint.
3. Set the start command to `gunicorn B2B_SaaS_Platform.wsgi:application --bind 0.0.0.0:$PORT --workers 3`.
4. Provision a Render Key Value (Redis-compatible) service, then set `REDIS_URL`; set `DJANGO_ALLOWED_HOSTS`, `SITE_URL`, and Stripe variables in the environment dashboard.
5. Run `python manage.py migrate`, then apply `deployment/postgres-rls.sql` using a database owner. Use a restricted database user for the web service.
6. Set Render's health-check path to `/healthz/`, configure the Stripe production webhook endpoint, and keep `BILLING_DEMO_MODE=false`.
