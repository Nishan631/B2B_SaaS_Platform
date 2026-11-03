-- Apply after `python manage.py migrate`, using the database owner.
-- It is safe to re-run. The Django application role must not own these tables
-- and must not have BYPASSRLS in a real deployment.
DO $$
DECLARE
    table_name text;
BEGIN
    FOREACH table_name IN ARRAY ARRAY['core_analyticsmetric', 'core_apikey', 'core_tenantmembership']
    LOOP
        EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY', table_name);
        EXECUTE format('ALTER TABLE %I FORCE ROW LEVEL SECURITY', table_name);
        EXECUTE format('DROP POLICY IF EXISTS tenant_access ON %I', table_name);
        EXECUTE format(
            'CREATE POLICY tenant_access ON %I USING (tenant_id = NULLIF(current_setting(''app.tenant_id'', true), '''')::bigint) WITH CHECK (tenant_id = NULLIF(current_setting(''app.tenant_id'', true), '''')::bigint)',
            table_name
        );
    END LOOP;
END $$;
