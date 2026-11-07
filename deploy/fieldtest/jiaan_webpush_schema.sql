-- Controlled migration. Run only on explicitly selected database after backup.
CREATE TABLE IF NOT EXISTS jiaan_webpush_subscriptions (
 id uuid PRIMARY KEY, user_id uuid NOT NULL REFERENCES users(id),
 org_id uuid NOT NULL REFERENCES organizations(id),
 endpoint text NOT NULL,
 endpoint_hash text NOT NULL UNIQUE,
 p256dh text NOT NULL, auth text NOT NULL,
 is_active boolean NOT NULL DEFAULT true,
 created_at timestamptz NOT NULL DEFAULT now(),
 updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_jiaan_webpush_subs_org ON jiaan_webpush_subscriptions(org_id,is_active);
CREATE TABLE IF NOT EXISTS jiaan_webpush_deliveries (
 id uuid PRIMARY KEY, emergency_id uuid NOT NULL REFERENCES jiaan1030_emergencies(id),
 subscription_id uuid NOT NULL REFERENCES jiaan_webpush_subscriptions(id),
 stage text NOT NULL CHECK (stage IN ('new','unacknowledged_60s','unacknowledged_180s')),
 status text NOT NULL DEFAULT 'queued', attempts int NOT NULL DEFAULT 0,
 created_at timestamptz NOT NULL DEFAULT now(), attempted_at timestamptz,
 UNIQUE (emergency_id,subscription_id,stage)
);
CREATE INDEX IF NOT EXISTS ix_jiaan_webpush_delivery_q ON jiaan_webpush_deliveries(status,created_at);
