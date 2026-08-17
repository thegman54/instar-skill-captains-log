-- Captain's Log — dictated logs compiled from a conversation.
--
-- Two tables on purpose: a log is a CONTAINER (lifecycle, tags, one compiled document)
-- and the entries are its ordered contents. Recall's one-row-per-fact shape cannot model
-- that, which is why this is its own skill rather than another recall scope.
--
-- Lifecycle: open --(end)--> pending --(owner)--> approved | rejected
--                 \--(stale)--> abandoned                  \--(48h)--> expired
--
-- Idempotent.

CREATE TABLE IF NOT EXISTS captains_logs (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    stardate         TEXT NOT NULL,                    -- 20260813.8 — day + tenth of day
    title            TEXT NOT NULL,
    tags             TEXT[] NOT NULL DEFAULT '{}',     -- 'stardate' = daily journal, 'project' = project log, ...
    status           TEXT NOT NULL DEFAULT 'open',     -- open|pending|approved|rejected|abandoned|expired
    purpose          TEXT,                             -- why the log was opened (bot-supplied, shown at review)
    closing          TEXT,                             -- the bot's closing summary, written at end

    -- who / where (all server-resolved from the authenticated session, never bot-supplied)
    profile_slug     TEXT,
    speaker_id       TEXT,
    speaker_label    TEXT,
    source_interface TEXT,
    session_id       TEXT,

    parent_id        UUID REFERENCES captains_logs(id) ON DELETE SET NULL,  -- "continue that log"

    compiled         JSONB,                            -- the structured document (source of truth)
    compiled_md      TEXT,                             -- rendered markdown (what the owner reads)
    entry_count      INTEGER NOT NULL DEFAULT 0,

    started_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    ended_at         TIMESTAMPTZ,
    reviewed_at      TIMESTAMPTZ,
    expires_at       TIMESTAMPTZ                       -- set on end/abandon; approved logs are permanent
);

CREATE TABLE IF NOT EXISTS captains_log_entries (
    id          BIGSERIAL PRIMARY KEY,
    log_id      UUID NOT NULL REFERENCES captains_logs(id) ON DELETE CASCADE,
    seq         INTEGER NOT NULL,
    kind        TEXT NOT NULL,                         -- context|requirement|decision|open_question|risk|idea|todo|quote|next_step
    content     TEXT NOT NULL,                         -- the SUMMARY, not the transcript
    why         TEXT,                                  -- why this fragment is in the log
    tags        TEXT[] NOT NULL DEFAULT '{}',
    detail      JSONB NOT NULL DEFAULT '{}',
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (log_id, seq)
);

-- One open log per speaker. The invariant lives in the database, not in the model's
-- good intentions — otherwise a reconnect quietly forks the conversation into two logs.
CREATE UNIQUE INDEX IF NOT EXISTS idx_captains_logs_one_open
    ON captains_logs(speaker_id) WHERE status = 'open' AND speaker_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_captains_logs_status   ON captains_logs(status, started_at DESC);
CREATE INDEX IF NOT EXISTS idx_captains_logs_speaker  ON captains_logs(speaker_id, status);
CREATE INDEX IF NOT EXISTS idx_captains_logs_tags     ON captains_logs USING GIN(tags);
CREATE INDEX IF NOT EXISTS idx_captains_logs_stardate ON captains_logs(stardate);
CREATE INDEX IF NOT EXISTS idx_captains_log_entries   ON captains_log_entries(log_id, seq);
