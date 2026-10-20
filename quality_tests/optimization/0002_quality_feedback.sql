BEGIN;

-- Running upgrade 0001 -> 0002_quality_feedback

CREATE SCHEMA rag_quality;

CREATE TABLE rag_quality.feedback_entries (
    id UUID NOT NULL, 
    org_id UUID NOT NULL, 
    qa_id UUID NOT NULL, 
    submitted_by UUID NOT NULL, 
    qa_snapshot JSONB NOT NULL, 
    submission JSONB NOT NULL, 
    reviewed_correction JSONB, 
    status VARCHAR(20) DEFAULT 'pending_review' NOT NULL, 
    revision INTEGER DEFAULT '0' NOT NULL, 
    dataset_split VARCHAR(20), 
    reviewed_by UUID, 
    reviewed_at TIMESTAMP WITH TIME ZONE, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    PRIMARY KEY (id), 
    UNIQUE (qa_id, submitted_by), 
    CHECK (status IN ('pending_review','verified','rejected')), 
    CHECK (dataset_split IS NULL OR dataset_split IN ('training','validation','test')), 
    FOREIGN KEY(org_id) REFERENCES organizations (id) ON DELETE RESTRICT, 
    FOREIGN KEY(qa_id) REFERENCES qa_items (id) ON DELETE RESTRICT, 
    FOREIGN KEY(submitted_by) REFERENCES users (id) ON DELETE RESTRICT, 
    FOREIGN KEY(reviewed_by) REFERENCES users (id) ON DELETE RESTRICT
);

CREATE INDEX ix_feedback_entries_org_id ON rag_quality.feedback_entries (org_id);

CREATE INDEX ix_feedback_entries_qa_id ON rag_quality.feedback_entries (qa_id);

CREATE INDEX ix_feedback_entries_status ON rag_quality.feedback_entries (status);

CREATE TABLE rag_quality.feedback_reviews (
    id UUID NOT NULL, 
    feedback_id UUID NOT NULL, 
    org_id UUID NOT NULL, 
    reviewer_id UUID NOT NULL, 
    revision INTEGER NOT NULL, 
    decision VARCHAR(20) NOT NULL, 
    correction JSONB NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    PRIMARY KEY (id), 
    UNIQUE (feedback_id, revision), 
    FOREIGN KEY(feedback_id) REFERENCES rag_quality.feedback_entries (id) ON DELETE RESTRICT, 
    FOREIGN KEY(org_id) REFERENCES organizations (id) ON DELETE RESTRICT, 
    FOREIGN KEY(reviewer_id) REFERENCES users (id) ON DELETE RESTRICT
);

CREATE INDEX ix_feedback_reviews_org_id ON rag_quality.feedback_reviews (org_id);

CREATE INDEX ix_feedback_reviews_feedback_id ON rag_quality.feedback_reviews (feedback_id);

CREATE FUNCTION rag_quality.immutable_submission() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN
      IF NEW.qa_snapshot IS DISTINCT FROM OLD.qa_snapshot OR NEW.submission IS DISTINCT FROM OLD.submission
         OR NEW.qa_id IS DISTINCT FROM OLD.qa_id OR NEW.org_id IS DISTINCT FROM OLD.org_id
         OR NEW.submitted_by IS DISTINCT FROM OLD.submitted_by OR NEW.created_at IS DISTINCT FROM OLD.created_at
         OR NEW.id IS DISTINCT FROM OLD.id THEN
        RAISE EXCEPTION 'quality submission is immutable';
      END IF;
      RETURN NEW;
    END $$;

CREATE TRIGGER immutable_submission BEFORE UPDATE ON rag_quality.feedback_entries FOR EACH ROW EXECUTE FUNCTION rag_quality.immutable_submission();

CREATE FUNCTION rag_quality.append_only_review() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN RAISE EXCEPTION 'quality reviews are append-only'; END $$;

CREATE TRIGGER append_only_review BEFORE UPDATE OR DELETE ON rag_quality.feedback_reviews FOR EACH ROW EXECUTE FUNCTION rag_quality.append_only_review();

UPDATE alembic_version SET version_num='0002_quality_feedback' WHERE alembic_version.version_num = '0001';

COMMIT;

