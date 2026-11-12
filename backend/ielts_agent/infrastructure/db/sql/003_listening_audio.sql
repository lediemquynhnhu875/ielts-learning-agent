-- Additive per-exercise Listening WAV, timing manifest and private review state.
-- Access layers must require status=verified AND matching source/config/audio
-- hashes before delivery. Reports may contain answer evidence and stay private.

CREATE TABLE IF NOT EXISTS listening_audio (
    audio_id uuid PRIMARY KEY,
    item_id uuid NOT NULL UNIQUE REFERENCES content_item(item_id) ON DELETE CASCADE,
    status text NOT NULL CHECK (status IN ('blocked', 'verified')),
    source_hash text NOT NULL CHECK (source_hash ~ '^[0-9a-f]{64}$'),
    config_hash text NOT NULL CHECK (config_hash ~ '^[0-9a-f]{64}$'),
    audio_sha256 text NOT NULL CHECK (audio_sha256 ~ '^[0-9a-f]{64}$'),
    audio bytea NOT NULL CHECK (octet_length(audio) BETWEEN 1 AND 29000000),
    manifest jsonb NOT NULL CHECK (jsonb_typeof(manifest) = 'object'),
    verification jsonb NOT NULL CHECK (jsonb_typeof(verification) = 'object'),
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP
);
