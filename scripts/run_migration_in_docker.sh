#!/bin/bash
# Run database migration inside Docker container
# Usage: ./scripts/run_migration_in_docker.sh [staging|prod]

ENVIRONMENT=${1:-staging}
CONTAINER_NAME="zana-webapp"

if [ "$ENVIRONMENT" = "prod" ]; then
    CONTAINER_NAME="zana-webapp"
    echo "Running migration for PRODUCTION database..."
else
    echo "Running migration for STAGING database..."
fi

echo "Executing SQL to add 'notes' column to actions table..."
docker compose exec $CONTAINER_NAME python -c "
import os
from sqlalchemy import create_engine, text

# Get database URL from environment
env = os.getenv('ENVIRONMENT', 'staging').lower()
if env in ('production', 'prod'):
    db_url = os.getenv('DATABASE_URL_PROD')
elif env in ('staging', 'stage') or not env:
    db_url = os.getenv('DATABASE_URL_STAGING')
else:
    db_url = os.getenv('DATABASE_URL')

if not db_url:
    print('ERROR: Database URL not found in environment')
    exit(1)

# Connect and run migration
engine = create_engine(db_url)
with engine.connect() as conn:
    try:
        # Check if column already exists
        result = conn.execute(text(\"\"\"
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name = 'actions' AND column_name = 'notes'
        \"\"\"))
        if result.fetchone():
            print('Column notes already exists. Skipping migration.')
        else:
            # Add the column
            conn.execute(text('ALTER TABLE actions ADD COLUMN notes TEXT;'))
            conn.commit()
            print('✓ Successfully added notes column to actions table')
    except Exception as e:
        print(f'ERROR: {e}')
        exit(1)
"
