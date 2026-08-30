CREATE TABLE secureswipe_idempotency (
    key_digest char(64) PRIMARY KEY
        CHECK (key_digest ~ '^[0-9a-f]{64}$'),
    request_digest char(64) NOT NULL
        CHECK (request_digest ~ '^[0-9a-f]{64}$'),
    state text NOT NULL
        CHECK (state IN ('reserved', 'completed', 'failed')),
    created_at timestamptz NOT NULL,
    updated_at timestamptz NOT NULL,
    reservation_expires_at timestamptz NOT NULL,
    retention_until timestamptz NOT NULL,
    completed_at timestamptz,
    response_document jsonb,
    response_sha256 char(64)
        CHECK (response_sha256 IS NULL OR response_sha256 ~ '^[0-9a-f]{64}$'),
    audit_receipt_sha256 char(64)
        CHECK (audit_receipt_sha256 IS NULL OR audit_receipt_sha256 ~ '^[0-9a-f]{64}$'),
    CHECK (retention_until > created_at),
    CHECK (
        (state = 'completed'
            AND completed_at IS NOT NULL
            AND response_document IS NOT NULL
            AND jsonb_typeof(response_document) = 'object'
            AND response_sha256 IS NOT NULL)
        OR
        (state IN ('reserved', 'failed')
            AND completed_at IS NULL
            AND response_document IS NULL
            AND response_sha256 IS NULL
            AND audit_receipt_sha256 IS NULL)
    )
)
