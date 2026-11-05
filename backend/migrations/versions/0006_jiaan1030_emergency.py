
from alembic import op
import sqlalchemy as sa

revision = "0006_jiaan1030_emergency"
down_revision = "0005_jiaan1030_drafts"
branch_labels = None
depends_on = None

def upgrade():
    op.execute('''
        CREATE TABLE IF NOT EXISTS jiaan1030_emergencies (
            id UUID PRIMARY KEY,
            org_id UUID NOT NULL,
            created_by UUID NOT NULL,
            client_request_id VARCHAR(100) NOT NULL,
            category VARCHAR(50) NOT NULL,
            status VARCHAR(30) NOT NULL DEFAULT 'open',
            acknowledged_at TIMESTAMPTZ,
            acknowledged_by UUID,
            resolved_at TIMESTAMPTZ,
            resolved_by UUID,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE (created_by, client_request_id)
        )
    ''')
    op.execute('''
        CREATE TABLE IF NOT EXISTS jiaan1030_emergency_events (
            id UUID PRIMARY KEY,
            emergency_id UUID NOT NULL,
            actor_id UUID NOT NULL,
            event_type VARCHAR(50) NOT NULL,
            from_status VARCHAR(30),
            to_status VARCHAR(30),
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    ''')

def downgrade():
    # Protect pre-existing manual tables and historical emergency records.
    raise RuntimeError(
        "Emergency migration downgrade requires manual schema review; "
        "automatic table deletion is prohibited."
    )


