-- Shodh-a-Code relational schema
-- Postgres is the source of truth for identity, contest structure, and verdicts.
-- Graph (Neo4j) and vector (Chroma) stores are derived/enriched views over this data.

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS pg_trgm; -- for fuzzy name matching (entity resolution)

CREATE TABLE organizations (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TYPE user_role AS ENUM ('learner', 'instructor', 'admin');

CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    org_id UUID NOT NULL REFERENCES organizations(id),
    username TEXT NOT NULL,
    display_name TEXT NOT NULL, -- free-text as entered; may be inconsistent across sessions
    email TEXT,
    password_hash TEXT NOT NULL,
    role user_role NOT NULL DEFAULT 'learner',
    -- canonical_person_id groups records the AI layer's entity-resolution step believes
    -- refer to the same human, even if display_name/username differ. NULL until resolved.
    canonical_person_id UUID,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (org_id, username)
);
CREATE INDEX idx_users_display_name_trgm ON users USING gin (display_name gin_trgm_ops);

CREATE TABLE contests (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    org_id UUID NOT NULL REFERENCES organizations(id),
    title TEXT NOT NULL,
    starts_at TIMESTAMPTZ NOT NULL,
    ends_at TIMESTAMPTZ NOT NULL,
    hint_policy TEXT NOT NULL DEFAULT 'no_hints_during_contest',
    -- 'no_hints_during_contest' | 'conceptual_hints_only' | 'open'
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE problems (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    contest_id UUID NOT NULL REFERENCES contests(id),
    slug TEXT NOT NULL,
    title TEXT NOT NULL,
    statement_md TEXT NOT NULL,
    time_limit_ms INTEGER NOT NULL DEFAULT 2000,
    memory_limit_mb INTEGER NOT NULL DEFAULT 256,
    points INTEGER NOT NULL DEFAULT 100,
    -- version lets us tell "outdated problem" apart from current one (Stage 3 requirement)
    version INTEGER NOT NULL DEFAULT 1,
    is_hidden_from_learners_until TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (contest_id, slug)
);

CREATE TABLE test_cases (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    problem_id UUID NOT NULL REFERENCES problems(id),
    input TEXT NOT NULL,
    expected_output TEXT NOT NULL,
    is_sample BOOLEAN NOT NULL DEFAULT false, -- sample cases are visible to learners; others are hidden
    weight INTEGER NOT NULL DEFAULT 1
);

CREATE TYPE submission_status AS ENUM ('queued', 'running', 'completed', 'infra_error');
CREATE TYPE verdict_type AS ENUM (
    'pending', 'accepted', 'wrong_answer', 'time_limit_exceeded',
    'memory_limit_exceeded', 'runtime_error', 'compile_error'
);

CREATE TABLE submissions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    problem_id UUID NOT NULL REFERENCES problems(id),
    user_id UUID NOT NULL REFERENCES users(id),
    contest_id UUID NOT NULL REFERENCES contests(id),
    language TEXT NOT NULL,
    source_code TEXT NOT NULL,
    -- idempotency: client-generated key prevents duplicate processing on retry
    client_submission_key TEXT NOT NULL,
    status submission_status NOT NULL DEFAULT 'queued',
    verdict verdict_type NOT NULL DEFAULT 'pending',
    score INTEGER NOT NULL DEFAULT 0,
    runtime_ms INTEGER,
    memory_kb INTEGER,
    judge_image_version TEXT, -- which judge/runtime image executed this — ties to "did a judge change affect outcomes"
    error_detail TEXT,
    submitted_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    judged_at TIMESTAMPTZ,
    UNIQUE (user_id, problem_id, client_submission_key)
);
CREATE INDEX idx_submissions_contest ON submissions(contest_id, submitted_at);
CREATE INDEX idx_submissions_user_problem ON submissions(user_id, problem_id);

CREATE TABLE test_case_results (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    submission_id UUID NOT NULL REFERENCES submissions(id),
    test_case_id UUID NOT NULL REFERENCES test_cases(id),
    passed BOOLEAN NOT NULL,
    actual_output TEXT,
    runtime_ms INTEGER
);

-- Tracks judge/runtime environment changes so the AI layer can distinguish
-- "learner error" from "infra/judge incident" (Stage 3 requirement).
CREATE TABLE judge_incidents (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    occurred_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    judge_image_version TEXT NOT NULL,
    description TEXT NOT NULL,
    affected_language TEXT,
    resolved_at TIMESTAMPTZ
);

-- Learning material referenced by the AI layer's vector index; content also lives in Chroma,
-- this table is the versioned/timestamped system of record so staleness can be judged.
CREATE TABLE learning_materials (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    topic TEXT NOT NULL,
    title TEXT NOT NULL,
    body_md TEXT NOT NULL,
    version INTEGER NOT NULL DEFAULT 1,
    is_current BOOLEAN NOT NULL DEFAULT true,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE audit_log (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    at TIMESTAMPTZ NOT NULL DEFAULT now(),
    actor_user_id UUID,
    action TEXT NOT NULL,
    resource TEXT NOT NULL,
    allowed BOOLEAN NOT NULL,
    detail JSONB
);
