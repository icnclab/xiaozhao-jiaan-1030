"""New tables for GA09/SC09 service-client master data + explicit read grants; fully new, safe to downgrade.

service_clients 代表受照顧者（服務個案），獨立於 cases（督導問題回報工單）。
grants 是保守預設的明確授權機制：督導/主任/admin 須有未撤銷的授權紀錄才可唯讀特定個案。
"""
from alembic import op
import sqlalchemy as sa

revision = '0004_jiaan1030_clients'
down_revision = '0003_jiaan1030_catalog_schema'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'jiaan1030_service_clients',
        sa.Column('id', sa.UUID(), primary_key=True),
        sa.Column('org_id', sa.UUID(), sa.ForeignKey('organizations.id'), nullable=False),
        sa.Column('created_by', sa.UUID(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('display_label', sa.String(100), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    for col in ('org_id', 'created_by'):
        op.create_index(f'ix_jiaan1030_service_clients_{col}', 'jiaan1030_service_clients', [col])

    op.create_table(
        'jiaan1030_service_client_grants',
        sa.Column('id', sa.UUID(), primary_key=True),
        sa.Column('service_client_id', sa.UUID(), sa.ForeignKey('jiaan1030_service_clients.id'), nullable=False),
        sa.Column('grantee_id', sa.UUID(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('granted_by', sa.UUID(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('revoked_at', sa.DateTime(timezone=True)),
        sa.UniqueConstraint('service_client_id', 'grantee_id', name='uq_jiaan1030_client_grant'),
    )
    for col in ('service_client_id', 'grantee_id'):
        op.create_index(f'ix_jiaan1030_service_client_grants_{col}', 'jiaan1030_service_client_grants', [col])


def downgrade():
    op.drop_table('jiaan1030_service_client_grants')
    op.drop_table('jiaan1030_service_clients')
