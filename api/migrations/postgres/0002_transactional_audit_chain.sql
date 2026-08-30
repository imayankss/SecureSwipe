CREATE TABLE audit_chain_heads (
    chain_id text PRIMARY KEY,
    last_sequence bigint NOT NULL CHECK (last_sequence >= 0),
    last_hash char(64) NOT NULL CHECK (last_hash ~ '^[0-9a-f]{64}$'),
    updated_at timestamptz NOT NULL
);

INSERT INTO audit_chain_heads (chain_id, last_sequence, last_hash, updated_at)
VALUES ('primary', 0, repeat('0', 64), clock_timestamp());

CREATE TABLE audit_events (
    event_id uuid PRIMARY KEY,
    chain_id text NOT NULL
        REFERENCES audit_chain_heads (chain_id),
    sequence bigint NOT NULL CHECK (sequence > 0),
    previous_hash char(64) NOT NULL
        CHECK (previous_hash ~ '^[0-9a-f]{64}$'),
    event_hash char(64) NOT NULL UNIQUE
        CHECK (event_hash ~ '^[0-9a-f]{64}$'),
    key_digest char(64) NOT NULL UNIQUE
        CHECK (key_digest ~ '^[0-9a-f]{64}$'),
    request_digest char(64) NOT NULL
        CHECK (request_digest ~ '^[0-9a-f]{64}$'),
    decision text NOT NULL
        CHECK (decision IN ('human_review', 'below_review_threshold')),
    bounded_response jsonb NOT NULL
        CHECK (jsonb_typeof(bounded_response) = 'object'),
    response_sha256 char(64) NOT NULL
        CHECK (response_sha256 ~ '^[0-9a-f]{64}$'),
    occurred_at timestamptz NOT NULL,
    UNIQUE (chain_id, sequence),
    UNIQUE (key_digest, event_hash),
    FOREIGN KEY (key_digest)
        REFERENCES secureswipe_idempotency (key_digest)
);

ALTER TABLE secureswipe_idempotency
    ADD CONSTRAINT secureswipe_completed_requires_audit_receipt
        CHECK (state <> 'completed' OR audit_receipt_sha256 IS NOT NULL),
    ADD CONSTRAINT secureswipe_completion_event_fk
        FOREIGN KEY (key_digest, audit_receipt_sha256)
        REFERENCES audit_events (key_digest, event_hash);
