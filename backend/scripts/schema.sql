CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE IF NOT EXISTS documents (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    filename text NOT NULL,
    content_type text,
    storage_path text NOT NULL,
    status text NOT NULL DEFAULT 'processing',
    uploaded_at timestamptz NOT NULL DEFAULT now(),

    page_count integer,
    table_count integer NOT NULL DEFAULT 0,
    confidence real,

    text text,
    result_json jsonb,
    error text
);

ALTER TABLE documents
    ADD COLUMN IF NOT EXISTS table_count integer
    NOT NULL DEFAULT 0;

ALTER TABLE documents
    ADD COLUMN IF NOT EXISTS result_json jsonb;

CREATE INDEX IF NOT EXISTS documents_uploaded_at_idx
    ON documents (uploaded_at DESC);

CREATE INDEX IF NOT EXISTS documents_text_search_idx
    ON documents USING gin (
        to_tsvector('english', coalesce(text, ''))
    );
