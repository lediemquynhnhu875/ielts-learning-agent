-- Additive development-schema extension for one-content-item practice attempts.
-- This is not the complete SESSION/ATTEMPT/ANSWER product model. Accounts,
-- EXAM/EXAM_ITEM and multi-answer sets remain outside this prototype.

CREATE TABLE IF NOT EXISTS practice_attempt (
    attempt_id uuid PRIMARY KEY,
    item_id uuid NOT NULL REFERENCES content_item(item_id) ON DELETE RESTRICT,
    skill text NOT NULL CHECK (skill IN ('reading', 'listening')),
    status text NOT NULL CHECK (status IN ('in_progress', 'submitted')),
    token_hash text NOT NULL CHECK (length(token_hash) = 64),
    exercise_snapshot jsonb NOT NULL CHECK (jsonb_typeof(exercise_snapshot) = 'object'),
    answer_key_snapshot jsonb NOT NULL CHECK (jsonb_typeof(answer_key_snapshot) = 'object'),
    started_at timestamptz NOT NULL,
    submitted_at timestamptz,
    raw_score integer CHECK (raw_score >= 0),
    result jsonb,
    UNIQUE (attempt_id, item_id),
    CHECK (
        (status = 'in_progress' AND submitted_at IS NULL AND raw_score IS NULL AND result IS NULL)
        OR
        (status = 'submitted' AND submitted_at IS NOT NULL AND submitted_at >= started_at
            AND raw_score IS NOT NULL AND result IS NOT NULL AND jsonb_typeof(result) = 'object')
    )
);

CREATE TABLE IF NOT EXISTS practice_answer (
    attempt_id uuid NOT NULL,
    item_id uuid NOT NULL,
    -- Snapshot question IDs remain valid when a source question is revised or
    -- removed. Membership is validated against the attempt's frozen content.
    question_id uuid NOT NULL,
    response text NOT NULL CHECK (length(response) <= 2000),
    is_correct boolean,
    PRIMARY KEY (attempt_id, question_id),
    FOREIGN KEY (attempt_id, item_id)
        REFERENCES practice_attempt(attempt_id, item_id) ON DELETE RESTRICT
);

CREATE INDEX IF NOT EXISTS practice_attempt_item_idx ON practice_attempt(item_id);
