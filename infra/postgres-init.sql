-- ============================================================================
-- SwarmScout Postgres schema.
-- Hot storage lives in Redis Streams; cold, queryable storage lives here.
-- ============================================================================

CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- Full payload store keyed by msg_id (ULID string, 26 chars).
CREATE TABLE IF NOT EXISTS findings (
    msg_id          VARCHAR(26)  PRIMARY KEY,
    agent           VARCHAR(32)  NOT NULL,
    payload_hash    CHAR(64)     NOT NULL,             -- hex-encoded sha256
    upstream_ids    VARCHAR(26)[] NOT NULL DEFAULT '{}',
    payload         JSONB        NOT NULL,
    model_used      VARCHAR(128),
    created_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    on_chain_tx     VARCHAR(66),                       -- tx hash once anchored
    on_chain_block  BIGINT
);

CREATE INDEX IF NOT EXISTS idx_findings_agent_created  ON findings (agent, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_findings_upstream       ON findings USING GIN (upstream_ids);
CREATE INDEX IF NOT EXISTS idx_findings_hash           ON findings (payload_hash);

-- LLM call audit log for cost accountability (FR-143).
CREATE TABLE IF NOT EXISTS llm_calls (
    id              BIGSERIAL    PRIMARY KEY,
    call_id         UUID         NOT NULL DEFAULT gen_random_uuid(),
    agent           VARCHAR(32)  NOT NULL,
    provider        VARCHAR(32)  NOT NULL,
    model           VARCHAR(128) NOT NULL,
    prompt_hash     CHAR(64)     NOT NULL,
    response_hash   CHAR(64),
    input_tokens    INTEGER      NOT NULL DEFAULT 0,
    output_tokens   INTEGER      NOT NULL DEFAULT 0,
    cost_usd        NUMERIC(10, 6) NOT NULL DEFAULT 0,
    latency_ms      INTEGER      NOT NULL,
    success         BOOLEAN      NOT NULL,
    error_class     VARCHAR(64),
    created_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_llm_agent_time  ON llm_calls (agent, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_llm_provider    ON llm_calls (provider, model, created_at DESC);

-- Telegram subscriptions.
CREATE TABLE IF NOT EXISTS telegram_subscriptions (
    chat_id         BIGINT       PRIMARY KEY,
    threshold       VARCHAR(16)  NOT NULL DEFAULT 'moderate',
    subscribed_at   TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    active          BOOLEAN      NOT NULL DEFAULT TRUE,
    last_delivered  TIMESTAMPTZ
);

-- Agent heartbeat table (FR-008) — last row per agent is authoritative.
CREATE TABLE IF NOT EXISTS agent_heartbeats (
    agent            VARCHAR(32)  PRIMARY KEY,
    last_seen        TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    status           VARCHAR(16)  NOT NULL DEFAULT 'online',
    events_last_min  INTEGER      NOT NULL DEFAULT 0,
    current_model    VARCHAR(128),
    llm_error_rate   NUMERIC(4, 3) NOT NULL DEFAULT 0,
    extra            JSONB        NOT NULL DEFAULT '{}'::jsonb
);
