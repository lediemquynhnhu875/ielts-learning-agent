-- Temporary UC-04 standalone-practice schema, authorized for this new project.
-- Canonical entity/field names follow DATABASE_CONTEXT.md. EXAM, EXAM_ITEM,
-- answer_sets and the undocumented exam_item_id relationship are out of scope.
-- JSONB answer_key owns both the canonical answer and its generated explanation.
-- UC04_TRACE is an explicit extension for complete retry/failure audit records.

CREATE TABLE IF NOT EXISTS uc04_trace (
    trace_id text PRIMARY KEY,
    details jsonb NOT NULL,
    updated_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS content_item (
    item_id uuid PRIMARY KEY,
    skill text NOT NULL CHECK (skill IN ('Reading', 'Listening', 'Writing', 'Speaking')),
    topic text NOT NULL,
    target_band double precision NOT NULL CHECK (target_band BETWEEN 1 AND 9),
    source text NOT NULL CHECK (source IN ('self_written', 'llm_generated_verified', 'open_license')),
    model text NOT NULL,
    prompt_version text NOT NULL,
    status text NOT NULL CHECK (status IN ('verified', 'rejected', 'spare')),
    body jsonb NOT NULL CHECK (
        body ? 'title' AND body ? 'text' AND body ? 'metadata'
        AND NOT body ? 'questions' AND NOT body ? 'question_groups'
    ),
    question_type text CHECK (skill IN ('Writing', 'Speaking') OR question_type IS NULL),
    position integer NOT NULL CHECK (position >= 1),
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS question_group (
    group_id uuid PRIMARY KEY,
    item_id uuid NOT NULL REFERENCES content_item(item_id) ON DELETE CASCADE,
    position integer NOT NULL CHECK (position >= 1),
    question_type text NOT NULL CHECK (question_type IN (
        'true_false_not_given', 'multiple_choice', 'sentence_completion', 'matching_headings'
    )),
    instructions text NOT NULL,
    prompt text,
    response_mode text NOT NULL CHECK (response_mode IN ('text', 'options', 'classification')),
    options jsonb NOT NULL DEFAULT '{}',
    response_limits jsonb NOT NULL DEFAULT '{}',
    layout jsonb NOT NULL DEFAULT '{}',
    allow_reuse boolean NOT NULL DEFAULT false CHECK (NOT allow_reuse),
    UNIQUE (item_id, position),
    UNIQUE (group_id, item_id)
);

CREATE TABLE IF NOT EXISTS question (
    id uuid PRIMARY KEY,
    item_id uuid NOT NULL REFERENCES content_item(item_id) ON DELETE CASCADE,
    group_id uuid NOT NULL,
    position integer NOT NULL CHECK (position >= 1),
    number integer NOT NULL CHECK (number BETWEEN 1 AND 40),
    prompt text NOT NULL,
    options jsonb NOT NULL DEFAULT '{}',
    target jsonb NOT NULL DEFAULT '{}',
    question_type text CHECK (question_type IS NULL),
    answer_key jsonb NOT NULL CHECK (answer_key ? 'answer' AND answer_key ? 'explanation'),
    evidence_span text,
    excluded boolean NOT NULL DEFAULT false,
    FOREIGN KEY (group_id, item_id) REFERENCES question_group(group_id, item_id) ON DELETE CASCADE,
    UNIQUE (group_id, position),
    UNIQUE (item_id, number),
    UNIQUE (id, item_id)
);

CREATE TABLE IF NOT EXISTS validation_result (
    id uuid PRIMARY KEY,
    item_id uuid NOT NULL REFERENCES content_item(item_id) ON DELETE CASCADE,
    question_id uuid,
    layer text NOT NULL CHECK (layer IN ('rules', 'solver', 'dedup')),
    passed boolean NOT NULL,
    details jsonb NOT NULL,
    FOREIGN KEY (question_id, item_id) REFERENCES question(id, item_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS question_group_item_idx ON question_group(item_id);
CREATE INDEX IF NOT EXISTS question_item_idx ON question(item_id);
CREATE INDEX IF NOT EXISTS validation_result_item_idx ON validation_result(item_id);
