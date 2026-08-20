import sqlite3
from pathlib import Path

from flask import current_app, g


SCHEMA = r'''
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS admins (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    email TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS teachers (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    email TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS students (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    email TEXT NOT NULL UNIQUE,
    student_code TEXT NOT NULL UNIQUE,
    password_hash TEXT,
    active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS question_banks (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT DEFAULT '',
    source_file TEXT,
    source_format TEXT,
    creator_id TEXT NOT NULL,
    creator_role TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS questions (
    id TEXT PRIMARY KEY,
    bank_id TEXT NOT NULL
        REFERENCES question_banks(id) ON DELETE CASCADE,
    text TEXT NOT NULL,
    type TEXT NOT NULL
        CHECK(type IN ('MCQ', 'MSQ')),
    marks REAL NOT NULL DEFAULT 1,
    negative_marks REAL NOT NULL DEFAULT 0,
    topic TEXT DEFAULT '',
    explanation TEXT DEFAULT '',
    active INTEGER NOT NULL DEFAULT 1,
    question_order INTEGER NOT NULL DEFAULT 0,
    needs_review INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS question_options (
    id TEXT PRIMARY KEY,
    question_id TEXT NOT NULL
        REFERENCES questions(id) ON DELETE CASCADE,
    option_index INTEGER NOT NULL,
    option_text TEXT NOT NULL,
    is_correct INTEGER NOT NULL DEFAULT 0,
    UNIQUE(question_id, option_index)
);

CREATE TABLE IF NOT EXISTS exams (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    description TEXT DEFAULT '',

    duration_minutes INTEGER NOT NULL,
    pass_percentage REAL NOT NULL DEFAULT 40,

    randomize_questions INTEGER NOT NULL DEFAULT 0,
    randomize_options INTEGER NOT NULL DEFAULT 0,

    security_settings TEXT NOT NULL DEFAULT '{}',

    status TEXT NOT NULL DEFAULT 'DRAFT',

    visibility_auto_submit INTEGER NOT NULL DEFAULT 0,

    creator_id TEXT NOT NULL,
    creator_role TEXT NOT NULL,

    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,

    exam_code TEXT,
    public_token TEXT,
    access_mode TEXT NOT NULL DEFAULT 'PRIVATE'
        CHECK(access_mode IN ('PRIVATE', 'PUBLIC'))
);

CREATE TABLE IF NOT EXISTS exam_questions (
    id TEXT PRIMARY KEY,
    exam_id TEXT NOT NULL
        REFERENCES exams(id) ON DELETE CASCADE,
    question_id TEXT NOT NULL
        REFERENCES questions(id) ON DELETE RESTRICT,
    question_order INTEGER NOT NULL,
    exam_marks REAL,
    exam_negative_marks REAL,
    UNIQUE(exam_id, question_id),
    UNIQUE(exam_id, question_order)
);

CREATE TABLE IF NOT EXISTS exam_schedules (
    id TEXT PRIMARY KEY,
    exam_id TEXT NOT NULL
        REFERENCES exams(id) ON DELETE CASCADE,
    start_at TEXT NOT NULL,
    end_at TEXT NOT NULL,
    timezone TEXT NOT NULL DEFAULT 'Asia/Kolkata',
    teacher_email TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(exam_id)
);

CREATE TABLE IF NOT EXISTS exam_invitations (
    id TEXT PRIMARY KEY,
    exam_id TEXT NOT NULL
        REFERENCES exams(id) ON DELETE CASCADE,
    student_id TEXT
        REFERENCES students(id) ON DELETE SET NULL,
    email TEXT NOT NULL,
    token_hash TEXT NOT NULL UNIQUE,
    status TEXT NOT NULL DEFAULT 'PENDING',
    created_at TEXT NOT NULL,
    sent_at TEXT,
    opened_at TEXT,
    started_at TEXT,
    completed_at TEXT,
    expires_at TEXT,

    start_email_sent_at TEXT,
    start_email_link TEXT
);

CREATE TABLE IF NOT EXISTS attempts (
    id TEXT PRIMARY KEY,
    exam_id TEXT NOT NULL
        REFERENCES exams(id) ON DELETE RESTRICT,
    student_id TEXT
        REFERENCES students(id) ON DELETE SET NULL,
    invitation_id TEXT NOT NULL
        REFERENCES exam_invitations(id) ON DELETE RESTRICT,
    start_time TEXT NOT NULL,
    submit_time TEXT,
    time_taken_seconds INTEGER,
    status TEXT NOT NULL DEFAULT 'IN_PROGRESS',
    security_event_count INTEGER NOT NULL DEFAULT 0,
    candidate_name TEXT NOT NULL,
    candidate_email TEXT NOT NULL,
    candidate_phone TEXT,
    candidate_department TEXT,
    candidate_division TEXT
);

CREATE TABLE IF NOT EXISTS attempt_answers (
    id TEXT PRIMARY KEY,
    attempt_id TEXT NOT NULL
        REFERENCES attempts(id) ON DELETE CASCADE,
    question_id TEXT NOT NULL
        REFERENCES questions(id) ON DELETE RESTRICT,
    selected_json TEXT NOT NULL DEFAULT '[]',
    updated_at TEXT NOT NULL,
    UNIQUE(attempt_id, question_id)
);

CREATE TABLE IF NOT EXISTS security_events (
    id TEXT PRIMARY KEY,
    attempt_id TEXT NOT NULL
        REFERENCES attempts(id) ON DELETE CASCADE,
    event_type TEXT NOT NULL,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS results (
    id TEXT PRIMARY KEY,
    attempt_id TEXT NOT NULL UNIQUE
        REFERENCES attempts(id) ON DELETE RESTRICT,
    exam_id TEXT NOT NULL
        REFERENCES exams(id) ON DELETE RESTRICT,
    student_id TEXT
        REFERENCES students(id) ON DELETE SET NULL,

    score REAL NOT NULL,
    max_marks REAL NOT NULL,
    percentage REAL NOT NULL,
    passed INTEGER NOT NULL,

    correct_count INTEGER NOT NULL,
    wrong_count INTEGER NOT NULL,
    skipped_count INTEGER NOT NULL,

    time_taken_seconds INTEGER NOT NULL,
    security_event_count INTEGER NOT NULL,

    topic_json TEXT NOT NULL DEFAULT '{}',
    details_json TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS email_jobs (
    id TEXT PRIMARY KEY,
    kind TEXT NOT NULL,
    recipient TEXT NOT NULL,
    subject TEXT NOT NULL,
    body TEXT NOT NULL,
    attachment_path TEXT,
    status TEXT NOT NULL DEFAULT 'PENDING',
    attempts INTEGER NOT NULL DEFAULT 0,
    last_error TEXT,
    created_at TEXT NOT NULL,
    sent_at TEXT
);

CREATE TABLE IF NOT EXISTS audit_logs (
    id TEXT PRIMARY KEY,
    actor_id TEXT,
    actor_role TEXT,
    action TEXT NOT NULL,
    entity TEXT,
    entity_id TEXT,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    timestamp TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_students_active
    ON students(active);

CREATE INDEX IF NOT EXISTS idx_questions_bank
    ON questions(bank_id);

CREATE INDEX IF NOT EXISTS idx_exam_questions_exam
    ON exam_questions(exam_id, question_order);

CREATE INDEX IF NOT EXISTS idx_invitations_exam
    ON exam_invitations(exam_id);

CREATE INDEX IF NOT EXISTS idx_attempts_exam
    ON attempts(exam_id);

CREATE INDEX IF NOT EXISTS idx_results_exam
    ON results(exam_id);

CREATE INDEX IF NOT EXISTS idx_email_jobs_status
    ON email_jobs(status, created_at);
'''


def get_db():
    if "db" not in g:
        db_path = Path(
            current_app.config.get("DATABASE")
            or (
                Path(current_app.instance_path)
                / "examforge.db"
            )
        )

        db_path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        conn = sqlite3.connect(
            db_path,
            timeout=30,
        )

        conn.row_factory = sqlite3.Row

        conn.execute(
            "PRAGMA foreign_keys = ON"
        )

        g.db = conn

    return g.db


def _existing_columns(db, table_name):
    rows = db.execute(
        f"PRAGMA table_info({table_name})"
    ).fetchall()

    return {
        row["name"]
        for row in rows
    }


def migrate_database():
    """
    Add columns introduced after the original
    database was created.

    SQLite CREATE TABLE IF NOT EXISTS does not
    modify an existing table, so new columns
    must be added explicitly.
    """

    db = get_db()

    # ---------------------------------------------------------
    # EXAMS TABLE
    # ---------------------------------------------------------

    columns = _existing_columns(
        db,
        "exams",
    )

    if "exam_code" not in columns:
        db.execute(
            """
            ALTER TABLE exams
            ADD COLUMN exam_code TEXT
            """
        )

    if "public_token" not in columns:
        db.execute(
            """
            ALTER TABLE exams
            ADD COLUMN public_token TEXT
            """
        )

    if "access_mode" not in columns:
        db.execute(
            """
            ALTER TABLE exams
            ADD COLUMN access_mode TEXT
            NOT NULL DEFAULT 'PRIVATE'
            """
        )

    # Normalize old / invalid values.
    db.execute(
        """
        UPDATE exams
        SET access_mode = 'PRIVATE'
        WHERE access_mode IS NULL
           OR access_mode NOT IN ('PRIVATE', 'PUBLIC')
        """
    )

    db.commit()

    # ---------------------------------------------------------
    # EXAM INVITATIONS TABLE
    # ---------------------------------------------------------

    invitation_columns = _existing_columns(
        db,
        "exam_invitations",
    )

    if "start_email_sent_at" not in invitation_columns:
        db.execute(
            """
            ALTER TABLE exam_invitations
            ADD COLUMN start_email_sent_at TEXT
            """
        )

    db.commit()

    # ---------------------------------------------------------
    # ATTEMPTS TABLE MIGRATIONS
    # ---------------------------------------------------------
    attempt_cols = _existing_columns(db, "attempts")
    if "candidate_phone" not in attempt_cols:
        db.execute("ALTER TABLE attempts ADD COLUMN candidate_phone TEXT")
    if "candidate_department" not in attempt_cols:
        db.execute("ALTER TABLE attempts ADD COLUMN candidate_department TEXT")
    if "candidate_division" not in attempt_cols:
        db.execute("ALTER TABLE attempts ADD COLUMN candidate_division TEXT")

    db.commit()


    # ---------------------------------------------------------
    # EXAM INDEXES
    # ---------------------------------------------------------
    # These are created only after the columns exist.

    db.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS
        idx_exams_exam_code
        ON exams(exam_code)
        WHERE exam_code IS NOT NULL
        """
    )

    db.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS
        idx_exams_public_token
        ON exams(public_token)
        WHERE public_token IS NOT NULL
        """
    )

    db.commit()


def init_db():
    db = get_db()

    # First create tables and common indexes.
    db.executescript(SCHEMA)

    db.commit()

    # Then handle migrations for existing databases.
    migrate_database()

    db.commit()


def close_db(_exc=None):
    db = g.pop(
        "db",
        None,
    )

    if db is not None:
        db.close()


def row_to_dict(row):
    return dict(row) if row else None