-- 000001_init_schema.up.sql
-- URL Shortener initial database schema

-- 1. Links table
CREATE TABLE IF NOT EXISTS links (
    id              BIGSERIAL PRIMARY KEY,
    code            VARCHAR(32) NOT NULL,
    original_url    TEXT NOT NULL,
    is_custom       BOOLEAN NOT NULL DEFAULT FALSE,
    delete_token    VARCHAR(64) NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT (NOW() AT TIME ZONE 'UTC'),
    expires_at      TIMESTAMPTZ NULL,
    deleted_at      TIMESTAMPTZ NULL
);

-- Unique constraint on short code (strictly enforced at DB level)
CREATE UNIQUE INDEX IF NOT EXISTS uq_links_code ON links (code);

-- Partial index for active links lookup
CREATE INDEX IF NOT EXISTS idx_links_code_active 
    ON links (code) 
    WHERE deleted_at IS NULL;

-- Index for expiration cleanup worker
CREATE INDEX IF NOT EXISTS idx_links_expires_at 
    ON links (expires_at) 
    WHERE expires_at IS NOT NULL AND deleted_at IS NULL;

-- 2. Daily aggregate click statistics
CREATE TABLE IF NOT EXISTS link_clicks_daily (
    link_id         BIGINT NOT NULL REFERENCES links(id) ON DELETE CASCADE,
    click_date      DATE NOT NULL,
    click_count     BIGINT NOT NULL DEFAULT 0,
    PRIMARY KEY (link_id, click_date)
);

CREATE INDEX IF NOT EXISTS idx_clicks_daily_date ON link_clicks_daily (click_date);

-- 3. Click Referrer host rollup
CREATE TABLE IF NOT EXISTS link_referrer_stats (
    link_id         BIGINT NOT NULL REFERENCES links(id) ON DELETE CASCADE,
    referrer_host   VARCHAR(255) NOT NULL,
    click_count     BIGINT NOT NULL DEFAULT 0,
    PRIMARY KEY (link_id, referrer_host)
);

-- 4. Device family rollup
CREATE TABLE IF NOT EXISTS link_device_stats (
    link_id         BIGINT NOT NULL REFERENCES links(id) ON DELETE CASCADE,
    device_family   VARCHAR(64) NOT NULL,
    click_count     BIGINT NOT NULL DEFAULT 0,
    PRIMARY KEY (link_id, device_family)
);
