"""Isolated quality feedback storage; never alter existing business tables."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = '0002_quality_feedback'
down_revision = '0001'
branch_labels = None
depends_on = None


def upgrade():
    op.execute('CREATE SCHEMA rag_quality')
    op.create_table('feedback_entries',
        sa.Column('id', sa.UUID(), primary_key=True),
        sa.Column('org_id', sa.UUID(), sa.ForeignKey('organizations.id', ondelete='RESTRICT'), nullable=False),
        sa.Column('qa_id', sa.UUID(), sa.ForeignKey('qa_items.id', ondelete='RESTRICT'), nullable=False),
        sa.Column('submitted_by', sa.UUID(), sa.ForeignKey('users.id', ondelete='RESTRICT'), nullable=False),
        sa.Column('qa_snapshot', JSONB(), nullable=False),
        sa.Column('submission', JSONB(), nullable=False),
        sa.Column('reviewed_correction', JSONB(), nullable=True),
        sa.Column('status', sa.String(20), nullable=False, server_default='pending_review'),
        sa.Column('revision', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('dataset_split', sa.String(20)),
        sa.Column('reviewed_by', sa.UUID(), sa.ForeignKey('users.id', ondelete='RESTRICT')),
        sa.Column('reviewed_at', sa.DateTime(timezone=True)),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint('qa_id','submitted_by'),
        sa.CheckConstraint("status IN ('pending_review','verified','rejected')"),
        sa.CheckConstraint("dataset_split IS NULL OR dataset_split IN ('training','validation','test')"),
        schema='rag_quality')
    for col in ('org_id','qa_id','status'):
        op.create_index('ix_feedback_entries_'+col,'feedback_entries',[col],schema='rag_quality')
    op.create_table('feedback_reviews',
        sa.Column('id', sa.UUID(), primary_key=True),
        sa.Column('feedback_id', sa.UUID(), sa.ForeignKey('rag_quality.feedback_entries.id', ondelete='RESTRICT'), nullable=False),
        sa.Column('org_id', sa.UUID(), sa.ForeignKey('organizations.id', ondelete='RESTRICT'), nullable=False),
        sa.Column('reviewer_id', sa.UUID(), sa.ForeignKey('users.id', ondelete='RESTRICT'), nullable=False),
        sa.Column('revision', sa.Integer(), nullable=False),
        sa.Column('decision', sa.String(20), nullable=False),
        sa.Column('correction', JSONB(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint('feedback_id','revision'), schema='rag_quality')
    for col in ('org_id','feedback_id'):
        op.create_index('ix_feedback_reviews_'+col,'feedback_reviews',[col],schema='rag_quality')
    op.execute("""CREATE FUNCTION rag_quality.immutable_submission() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN
      IF NEW.qa_snapshot IS DISTINCT FROM OLD.qa_snapshot OR NEW.submission IS DISTINCT FROM OLD.submission
         OR NEW.qa_id IS DISTINCT FROM OLD.qa_id OR NEW.org_id IS DISTINCT FROM OLD.org_id
         OR NEW.submitted_by IS DISTINCT FROM OLD.submitted_by OR NEW.created_at IS DISTINCT FROM OLD.created_at
         OR NEW.id IS DISTINCT FROM OLD.id THEN
        RAISE EXCEPTION 'quality submission is immutable';
      END IF;
      RETURN NEW;
    END $$""")
    op.execute('CREATE TRIGGER immutable_submission BEFORE UPDATE ON rag_quality.feedback_entries FOR EACH ROW EXECUTE FUNCTION rag_quality.immutable_submission()')
    op.execute("""CREATE FUNCTION rag_quality.append_only_review() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN RAISE EXCEPTION 'quality reviews are append-only'; END $$""")
    op.execute('CREATE TRIGGER append_only_review BEFORE UPDATE OR DELETE ON rag_quality.feedback_reviews FOR EACH ROW EXECUTE FUNCTION rag_quality.append_only_review()')


def downgrade():
    op.drop_table('feedback_reviews', schema='rag_quality')
    op.drop_table('feedback_entries', schema='rag_quality')
    op.execute('DROP FUNCTION rag_quality.append_only_review()')
    op.execute('DROP FUNCTION rag_quality.immutable_submission()')
    op.execute('DROP SCHEMA rag_quality')
