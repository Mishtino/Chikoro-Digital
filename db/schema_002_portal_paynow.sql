-- Chikoro Digital - portal and Paynow extension
CREATE TABLE IF NOT EXISTS paynow_attempts (
    id SERIAL PRIMARY KEY,
    school_id INTEGER NOT NULL REFERENCES schools(id),
    student_id INTEGER,
    invoice_id INTEGER REFERENCES invoices(id),
    reference VARCHAR(120),
    amount NUMERIC(12,2) NOT NULL,
    currency VARCHAR(3) NOT NULL DEFAULT 'USD',
    status VARCHAR(20) NOT NULL DEFAULT 'created', -- created, sent, paid, failed, cancelled
    poll_url TEXT,
    paynow_reference VARCHAR(120),
    hash_verified BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_paynow_attempts_school_id ON paynow_attempts(school_id);
