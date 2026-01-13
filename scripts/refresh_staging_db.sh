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

# Clean up
rm -f /tmp/prod_dump.sql

echo "Staging database refresh completed successfully!"
