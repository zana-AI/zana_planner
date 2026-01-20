#!/bin/bash
# Refresh staging database from production database
# This script dumps production DB and restores to staging

set -e  # Exit on error

# Check if required environment variables are set
if [ -z "$DATABASE_URL_PROD" ]; then
    echo "Error: DATABASE_URL_PROD environment variable is not set"
    exit 1
fi

if [ -z "$DATABASE_URL_STAGING" ]; then
    echo "Error: DATABASE_URL_STAGING environment variable is not set"
    exit 1
fi

echo "Starting staging database refresh from production..."
echo "Production: $DATABASE_URL_PROD"
echo "Staging: $DATABASE_URL_STAGING"

# Dump production database
echo "Dumping production database..."
pg_dump "$DATABASE_URL_PROD" > /tmp/prod_dump.sql

# Restore to staging
echo "Restoring to staging database..."
psql "$DATABASE_URL_STAGING" < /tmp/prod_dump.sql

# CRITICAL: Sync sequences after restore
# pg_dump includes explicit IDs, but sequences don't auto-update
# This prevents duplicate key errors on the next insert
echo "Syncing PostgreSQL sequences after restore..."
psql "$DATABASE_URL_STAGING" -c "
DO \$\$
DECLARE
    r RECORD;
    seq_name TEXT;
    max_val BIGINT;
BEGIN
    FOR r IN (
        SELECT 
            t.table_name,
            c.column_name
        FROM information_schema.tables t
        JOIN information_schema.columns c 
            ON t.table_name = c.table_name 
            AND t.table_schema = c.table_schema
        WHERE t.table_schema = 'public'
            AND t.table_type = 'BASE TABLE'
            AND c.column_default LIKE 'nextval%'
    )
    LOOP
        seq_name := pg_get_serial_sequence('public.' || r.table_name, r.column_name);
        IF seq_name IS NOT NULL THEN
            EXECUTE format('SELECT COALESCE(MAX(%I), 0) FROM %I', r.column_name, r.table_name) INTO max_val;
            EXECUTE format('SELECT setval(%L, GREATEST(%s, 1))', seq_name, max_val);
            RAISE NOTICE 'Synced sequence % to %', seq_name, max_val;
        END IF;
    END LOOP;
END \$\$;
"

# Clean up
rm -f /tmp/prod_dump.sql

echo "Staging database refresh completed successfully!"
