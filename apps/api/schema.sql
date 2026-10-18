-- Turbo sniper tables (also auto-created on API startup via SQLAlchemy)
CREATE TABLE IF NOT EXISTS sniper_jobs (
    id           VARCHAR(36) PRIMARY KEY,
    user_id      INTEGER NOT NULL REFERENCES users(id),
    user_token   VARCHAR NOT NULL,
    platform     VARCHAR(32) NOT NULL DEFAULT 'discord',
    targets      JSONB NOT NULL,
    proxy        TEXT NOT NULL,
    webhook_url  TEXT,
    workers      INTEGER NOT NULL DEFAULT 160,
    status       VARCHAR(32) NOT NULL DEFAULT 'idle',
    stats        JSONB,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS sniper_hits (
    id         SERIAL PRIMARY KEY,
    job_id     VARCHAR(36) NOT NULL REFERENCES sniper_jobs(id),
    user_id    INTEGER NOT NULL REFERENCES users(id),
    platform   VARCHAR(32) NOT NULL,
    target     VARCHAR(256) NOT NULL,
    status     VARCHAR(32) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_sniper_jobs_user_token ON sniper_jobs(user_token);
CREATE INDEX IF NOT EXISTS ix_sniper_hits_job_id ON sniper_hits(job_id);
