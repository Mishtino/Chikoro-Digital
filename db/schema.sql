-- Chikoro Digital - initial schema (PostgreSQL)
CREATE TABLE IF NOT EXISTS schools (
    id SERIAL PRIMARY KEY,
    code VARCHAR(20) UNIQUE NOT NULL,
    name VARCHAR(200) NOT NULL,
    province VARCHAR(100),
    status VARCHAR(20) NOT NULL DEFAULT 'onboarding',
    plan VARCHAR(50) DEFAULT 'pilot',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    email VARCHAR(255) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    full_name VARCHAR(200) NOT NULL,
    role VARCHAR(50) NOT NULL DEFAULT 'staff',
    school_id INTEGER REFERENCES schools(id),
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    is_admin BOOLEAN NOT NULL DEFAULT FALSE,
    mfa_enabled BOOLEAN NOT NULL DEFAULT FALSE,
    mfa_secret VARCHAR(255),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_users_school_id ON users(school_id);

CREATE TABLE IF NOT EXISTS audit_logs (
    id SERIAL PRIMARY KEY,
    school_id INTEGER REFERENCES schools(id),
    actor_user_id INTEGER REFERENCES users(id),
    action VARCHAR(100) NOT NULL,
    entity_type VARCHAR(100),
    entity_id VARCHAR(100),
    details JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_audit_logs_school_id ON audit_logs(school_id);

CREATE TABLE IF NOT EXISTS students (
    id SERIAL PRIMARY KEY,
    school_id INTEGER NOT NULL REFERENCES schools(id),
    student_number VARCHAR(40) NOT NULL,
    first_name VARCHAR(100) NOT NULL,
    last_name VARCHAR(100) NOT NULL,
    form VARCHAR(40),
    status VARCHAR(20) NOT NULL DEFAULT 'active',
    activation_pin_hash VARCHAR(255),
    activation_expires_at TIMESTAMPTZ,
    activated_at TIMESTAMPTZ,
    portal_user_id INTEGER REFERENCES users(id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (school_id, student_number)
);

CREATE TABLE IF NOT EXISTS contacts (
    id SERIAL PRIMARY KEY,
    school_id INTEGER NOT NULL REFERENCES schools(id),
    student_id INTEGER NOT NULL REFERENCES students(id),
    name VARCHAR(200) NOT NULL,
    relationship VARCHAR(50),
    phone VARCHAR(40),
    email VARCHAR(255),
    is_primary BOOLEAN NOT NULL DEFAULT FALSE,
    verified_phone BOOLEAN NOT NULL DEFAULT FALSE,
    verified_email BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS terms (
    id SERIAL PRIMARY KEY,
    school_id INTEGER NOT NULL REFERENCES schools(id),
    name VARCHAR(100) NOT NULL,
    academic_year VARCHAR(20) NOT NULL,
    start_date DATE,
    end_date DATE,
    is_current BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS fee_items (
    id SERIAL PRIMARY KEY,
    school_id INTEGER NOT NULL REFERENCES schools(id),
    name VARCHAR(120) NOT NULL,
    amount NUMERIC(12,2) NOT NULL,
    currency VARCHAR(3) NOT NULL DEFAULT 'USD',
    applies_to_form VARCHAR(40),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS fee_structures (
    id SERIAL PRIMARY KEY,
    school_id INTEGER NOT NULL REFERENCES schools(id),
    term_id INTEGER NOT NULL REFERENCES terms(id),
    form VARCHAR(40),
    name VARCHAR(120) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS fee_structure_items (
    id SERIAL PRIMARY KEY,
    school_id INTEGER NOT NULL REFERENCES schools(id),
    fee_structure_id INTEGER NOT NULL REFERENCES fee_structures(id),
    fee_item_id INTEGER REFERENCES fee_items(id),
    description VARCHAR(200),
    amount NUMERIC(12,2) NOT NULL,
    currency VARCHAR(3) NOT NULL DEFAULT 'USD'
);

CREATE TABLE IF NOT EXISTS invoices (
    id SERIAL PRIMARY KEY,
    school_id INTEGER NOT NULL REFERENCES schools(id),
    student_id INTEGER NOT NULL REFERENCES students(id),
    term_id INTEGER REFERENCES terms(id),
    invoice_number VARCHAR(40) NOT NULL,
    currency VARCHAR(3) NOT NULL DEFAULT 'USD',
    total NUMERIC(12,2) NOT NULL DEFAULT 0,
    status VARCHAR(20) NOT NULL DEFAULT 'issued',
    due_date DATE,
    issued_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    voided_at TIMESTAMPTZ,
    void_reason VARCHAR(255),
    UNIQUE (school_id, invoice_number)
);

CREATE TABLE IF NOT EXISTS invoice_lines (
    id SERIAL PRIMARY KEY,
    school_id INTEGER NOT NULL REFERENCES schools(id),
    invoice_id INTEGER NOT NULL REFERENCES invoices(id),
    description VARCHAR(255) NOT NULL,
    amount NUMERIC(12,2) NOT NULL
);

CREATE TABLE IF NOT EXISTS payments (
    id SERIAL PRIMARY KEY,
    school_id INTEGER NOT NULL REFERENCES schools(id),
    student_id INTEGER NOT NULL REFERENCES students(id),
    amount NUMERIC(12,2) NOT NULL,
    currency VARCHAR(3) NOT NULL DEFAULT 'USD',
    method VARCHAR(40) NOT NULL DEFAULT 'manual',
    reference VARCHAR(120),
    received_by_user_id INTEGER REFERENCES users(id),
    received_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    voided BOOLEAN NOT NULL DEFAULT FALSE,
    voided_at TIMESTAMPTZ,
    void_reason VARCHAR(255)
);

CREATE TABLE IF NOT EXISTS payment_allocations (
    id SERIAL PRIMARY KEY,
    school_id INTEGER NOT NULL REFERENCES schools(id),
    payment_id INTEGER NOT NULL REFERENCES payments(id),
    invoice_id INTEGER NOT NULL REFERENCES invoices(id),
    amount NUMERIC(12,2) NOT NULL
);

CREATE TABLE IF NOT EXISTS receipts (
    id SERIAL PRIMARY KEY,
    school_id INTEGER NOT NULL REFERENCES schools(id),
    payment_id INTEGER NOT NULL REFERENCES payments(id),
    receipt_number VARCHAR(40) NOT NULL,
    issued_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (school_id, receipt_number)
);
