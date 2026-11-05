"""New table for GA09/SC09 service-form drafts; fully new, safe to downgrade.

草稿關聯 jiaan1030_service_clients（服務個案主檔），不是 cases（督導問題回報工單）——
cases 代表照服員問題回報工單，語意上不適合用來代表「某受照顧者的某次服務紀錄」。
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = '0005_jiaan1030_drafts'
down_revision = '0004_jiaan1030_clients'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'jiaan1030_service_form_drafts',
        sa.Column('id', sa.UUID(), primary_key=True),
        sa.Column('org_id', sa.UUID(), sa.ForeignKey('organizations.id'), nullable=False),
        sa.Column('service_client_id', sa.UUID(), sa.ForeignKey('jiaan1030_service_clients.id'), nullable=False),
        sa.Column('form_code', sa.String(20), sa.ForeignKey('jiaan1030_service_forms.code'), nullable=False),
        sa.Column('client_request_id', sa.String(64), nullable=False),
        sa.Column('payload_json', JSONB(), nullable=False, server_default='{}'),
        sa.Column('status', sa.String(20), nullable=False, server_default='draft'),
        sa.Column('created_by', sa.UUID(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('updated_by', sa.UUID(), sa.ForeignKey('users.id')),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('submitted_at', sa.DateTime(timezone=True)),
        sa.CheckConstraint("status IN ('draft','submitted')", name='ck_jiaan1030_drafts_status'),
        sa.UniqueConstraint('created_by', 'client_request_id'),
    )
    for col in ('org_id', 'service_client_id', 'form_code', 'created_by', 'status'):
        op.create_index(f'ix_jiaan1030_service_form_drafts_{col}', 'jiaan1030_service_form_drafts', [col])


def downgrade():
    op.drop_table('jiaan1030_service_form_drafts')
