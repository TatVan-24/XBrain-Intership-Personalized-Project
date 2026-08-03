BEGIN;

CREATE EXTENSION IF NOT EXISTS pgcrypto;
CREATE SCHEMA IF NOT EXISTS identity;
GRANT USAGE ON SCHEMA identity TO otelu;

CREATE TABLE IF NOT EXISTS identity.users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(), email TEXT NOT NULL, username VARCHAR(64) NOT NULL,
    password_hash TEXT NOT NULL, status VARCHAR(16) NOT NULL DEFAULT 'active',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(), updated_at TIMESTAMPTZ NOT NULL DEFAULT now(), deleted_at TIMESTAMPTZ
);
CREATE UNIQUE INDEX IF NOT EXISTS users_email_unique ON identity.users (lower(email)) WHERE deleted_at IS NULL;
CREATE UNIQUE INDEX IF NOT EXISTS users_username_unique ON identity.users (lower(username)) WHERE deleted_at IS NULL;

CREATE TABLE IF NOT EXISTS identity.sessions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(), user_id UUID NOT NULL REFERENCES identity.users(id) ON DELETE CASCADE,
    token_hash CHAR(64) NOT NULL UNIQUE, created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at TIMESTAMPTZ NOT NULL, revoked_at TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS sessions_user_id_index ON identity.sessions (user_id);
CREATE INDEX IF NOT EXISTS sessions_active_token_index ON identity.sessions (token_hash) WHERE revoked_at IS NULL;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA identity TO otelu;

ALTER TABLE reviews.productreviews ADD COLUMN IF NOT EXISTS user_id UUID REFERENCES identity.users(id) ON DELETE SET NULL;
ALTER TABLE reviews.productreviews ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ NOT NULL DEFAULT now();
ALTER TABLE reviews.productreviews ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT now();
ALTER TABLE reviews.productreviews ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMPTZ;
CREATE UNIQUE INDEX IF NOT EXISTS product_review_user_unique ON reviews.productreviews (product_id, user_id)
    WHERE user_id IS NOT NULL AND deleted_at IS NULL;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA reviews TO otelu;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA reviews TO otelu;

-- Fill each catalog product to 100 reviews. Text and score vary deterministically for repeatable tests.
WITH counts AS (
    SELECT p.id, count(r.id)::int AS current_count
    FROM catalog.products p LEFT JOIN reviews.productreviews r ON r.product_id = p.id AND r.deleted_at IS NULL
    GROUP BY p.id
)
INSERT INTO reviews.productreviews (product_id, username, description, score, created_at, updated_at)
SELECT c.id,
       'seed_user_' || c.id || '_' || n,
       (ARRAY[
         'Solid product and easy to use, but packaging could be better.',
         'Good value for the price. Setup was straightforward and performance was reliable.',
         'The product works as described; documentation needs more detail.',
         'Excellent quality and a noticeably better experience than my previous equipment.',
         'Mixed experience: useful features, although delivery and initial setup took longer than expected.',
         'After several uses it remains dependable and I would recommend it to beginners.',
         'Build quality is acceptable, but advanced users may want more control.',
         'Clear results, practical design, and responsive support when I had a question.'
       ])[1 + ((n - 1) % 8)],
       (1 + ((n * 7 + length(c.id)) % 5))::numeric(2,1),
       now() - make_interval(days => (n % 90)),
       now() - make_interval(days => (n % 90))
FROM counts c
CROSS JOIN LATERAL generate_series(1, greatest(0, 100 - c.current_count)) AS n;

COMMIT;
