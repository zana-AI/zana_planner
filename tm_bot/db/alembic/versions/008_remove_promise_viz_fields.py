"""Remove angle_deg and radius columns from promises table

Revision ID: 008_remove_promise_viz_fields
Revises: 007_add_action_notes
Create Date: 2026-01-29

This migration removes the angle_deg and radius visualization fields from the promises table.
These fields are no longer used in the application.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '008_remove_promise_viz_fields'
down_revision: Union[str, None] = '007_add_action_notes'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Drop columns from promises table
    # Check if columns exist first (for idempotency)
    conn = op.get_bind()
    
    # Check for angle_deg column
    result = conn.execute(sa.text("""
        SELECT column_name 
        FROM information_schema.columns 
        WHERE table_name = 'promises' AND column_name = 'angle_deg'
    """))
    if result.fetchone():
        op.drop_column('promises', 'angle_deg')
    
    # Check for radius column
    result = conn.execute(sa.text("""
        SELECT column_name 
        FROM information_schema.columns 
        WHERE table_name = 'promises' AND column_name = 'radius'
    """))
    if result.fetchone():
        op.drop_column('promises', 'radius')
    
    # Recreate the view without these columns
    op.execute("DROP VIEW IF EXISTS promises_with_type;")
    op.execute("""
        CREATE VIEW promises_with_type AS
        SELECT 
            promise_uuid,
            user_id,
            current_id,
            text,
            hours_per_week,
            recurring,
            start_date,
            end_date,
            is_deleted,
            visibility,
            description,
            created_at_utc,
            updated_at_utc,
            CASE WHEN hours_per_week <= 0 THEN 1 ELSE 0 END AS is_check_based,
            CASE WHEN hours_per_week > 0 THEN 1 ELSE 0 END AS is_time_based,
            CASE WHEN hours_per_week <= 0 THEN 'check_based' ELSE 'time_based' END AS promise_type
        FROM promises;
    """)


def downgrade() -> None:
    # Re-add columns (with default values for existing rows)
    op.add_column('promises', sa.Column('angle_deg', sa.Integer(), nullable=False, server_default='0'))
    op.add_column('promises', sa.Column('radius', sa.Integer(), nullable=False, server_default='0'))
    
    # Recreate the view with these columns
    op.execute("DROP VIEW IF EXISTS promises_with_type;")
    op.execute("""
        CREATE VIEW promises_with_type AS
        SELECT 
            promise_uuid,
            user_id,
            current_id,
            text,
            hours_per_week,
            recurring,
            start_date,
            end_date,
            angle_deg,
            radius,
            is_deleted,
            visibility,
            description,
            created_at_utc,
            updated_at_utc,
            CASE WHEN hours_per_week <= 0 THEN 1 ELSE 0 END AS is_check_based,
            CASE WHEN hours_per_week > 0 THEN 1 ELSE 0 END AS is_time_based,
            CASE WHEN hours_per_week <= 0 THEN 'check_based' ELSE 'time_based' END AS promise_type
        FROM promises;
    """)
