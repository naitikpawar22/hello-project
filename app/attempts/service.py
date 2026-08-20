import json
import random
from datetime import datetime, timezone
import secrets
from app.database import get_db
from app.utils.helpers import (
    new_id,
    now_iso,
    parse_iso,
    token_hash,
)
from app.evaluation.service import evaluate_attempt
from app.email.service import enqueue_email


# =========================================================
# PRIVATE EXAM
# =========================================================

def load_invitation(token):
    db = get_db()

    invitation = db.execute(
        """
        SELECT *
        FROM exam_invitations
        WHERE token_hash=?
        """,
        (
            token_hash(token),
        ),
    ).fetchone()

    if not invitation:
        raise LookupError(
            "Invalid invitation"
        )

    if invitation["status"] in {
        "EXPIRED",
        "CANCELLED",
    }:
        raise PermissionError(
            "Invitation is no longer valid"
        )

    if invitation["expires_at"]:

        expiry = parse_iso(
            invitation["expires_at"]
        )

        if expiry < datetime.now(timezone.utc):

            db.execute(
                """
                UPDATE exam_invitations
                SET status='EXPIRED'
                WHERE id=?
                """,
                (
                    invitation["id"],
                ),
            )

            db.commit()

            raise PermissionError(
                "Invitation has expired"
            )

    return invitation


def _load_exam_schedule(exam_id):
    db = get_db()

    return db.execute(
        """
        SELECT *
        FROM exam_schedules
        WHERE exam_id=?
        """,
        (
            exam_id,
        ),
    ).fetchone()


def _validate_schedule(exam_id):
    """
    Check whether an exam is currently available.

    Scheduling timestamps are stored as ISO timestamps.
    """

    schedule = _load_exam_schedule(
        exam_id
    )

    if not schedule:
        return

    now = datetime.now(timezone.utc)

    start = parse_iso(
        schedule["start_at"]
    )

    end = parse_iso(
        schedule["end_at"]
    )

    if now < start:
        raise PermissionError(
            "Exam has not started yet"
        )

    if now > end:
        raise PermissionError(
            "Exam has already closed"
        )


def _load_exam_questions(exam_id):
    db = get_db()

    rows = db.execute(
        """
        SELECT
            eq.question_id,
            eq.question_order,
            q.text,
            q.type
        FROM exam_questions eq
        JOIN questions q
            ON q.id=eq.question_id
        WHERE eq.exam_id=?
          AND q.active=1
        ORDER BY eq.question_order
        """,
        (
            exam_id,
        ),
    ).fetchall()

    items = []

    for row in rows:

        options = db.execute(
            """
            SELECT
                option_index,
                option_text
            FROM question_options
            WHERE question_id=?
            ORDER BY option_index
            """,
            (
                row["question_id"],
            ),
        ).fetchall()

        items.append(
            {
                "question_id": row["question_id"],
                "question_order": row["question_order"],
                "text": row["text"],
                "type": row["type"],
                "options": [
                    dict(option)
                    for option in options
                ],
            }
        )

    return items


def _randomize_exam_questions(
    exam,
    questions,
    seed_value,
):
    """
    Keep randomization deterministic for the same access
    session/token so a refresh does not unexpectedly
    produce a different question order.
    """

    items = list(
        questions
    )

    seed_bytes = (
        str(seed_value)
        .encode()
    )

    seed = int.from_bytes(
        seed_bytes[:8].ljust(
            8,
            b"0",
        ),
        "little",
        signed=False,
    )

    rng = random.Random(
        seed
    )

    if exam["randomize_questions"]:
        rng.shuffle(items)

    if exam["randomize_options"]:

        for item in items:
            rng.shuffle(
                item["options"]
            )

    return items


def public_exam(token):
    """
    Existing PRIVATE invitation-based exam access.
    """

    invitation = load_invitation(
        token
    )

    db = get_db()

    exam = db.execute(
        """
        SELECT *
        FROM exams
        WHERE id=?
        """,
        (
            invitation["exam_id"],
        ),
    ).fetchone()

    if not exam:
        raise LookupError(
            "Exam not found"
        )

    # A PRIVATE exam must be accessed using an invitation.
    if (
        exam["access_mode"]
        and exam["access_mode"] != "PRIVATE"
    ):
        raise PermissionError(
            "This exam is not configured for private invitation access"
        )

    _validate_schedule(
        exam["id"]
    )

    now = now_iso()

    if invitation["status"] == "SENT":

        db.execute(
            """
            UPDATE exam_invitations
            SET
                status='OPENED',
                opened_at=?
            WHERE id=?
            """,
            (
                now,
                invitation["id"],
            ),
        )

        db.commit()

        invitation = db.execute(
            """
            SELECT *
            FROM exam_invitations
            WHERE id=?
            """,
            (
                invitation["id"],
            ),
        ).fetchone()

    questions = _load_exam_questions(
        exam["id"]
    )

    questions = _randomize_exam_questions(
        exam,
        questions,
        token,
    )

    return {
        "invitation": dict(
            invitation
        ),
        "exam": dict(
            exam
        ),
        "questions": questions,
        "access_mode": "PRIVATE",
    }


# =========================================================
# PUBLIC EXAM
# =========================================================

def load_public_exam(exam_code):
    """
    Find a PUBLIC exam using its shareable exam code.

    Exam code identifies the exam only.
    It is NOT treated as a secret attempt token.
    """

    exam_code = (
        exam_code
        or ""
    ).strip().upper()

    if not exam_code:
        raise LookupError(
            "Exam code is required"
        )

    db = get_db()

    exam = db.execute(
        """
        SELECT *
        FROM exams
        WHERE exam_code=?
        """,
        (
            exam_code,
        ),
    ).fetchone()

    if not exam:
        raise LookupError(
            "Exam not found"
        )

    if (
        exam["access_mode"] != "PUBLIC"
    ):
        raise PermissionError(
            "This exam is private"
        )

    if exam["status"] not in {
        "PUBLISHED",
        "SCHEDULED",
        "LIVE",
    }:
        raise PermissionError(
            "This exam is not available"
        )

    _validate_schedule(
        exam["id"]
    )

    questions = _load_exam_questions(
        exam["id"]
    )

    questions = _randomize_exam_questions(
        exam,
        questions,
        exam["exam_code"],
    )

    # Do NOT expose:
    # - public_token
    # - correct answers
    # - internal creator information

    public_exam_data = {
        "id": exam["id"],
        "title": exam["title"],
        "description": exam["description"],
        "duration_minutes": exam["duration_minutes"],
        "pass_percentage": exam["pass_percentage"],
        "randomize_questions": exam["randomize_questions"],
        "randomize_options": exam["randomize_options"],
        "security_settings": exam["security_settings"],
        "visibility_auto_submit": exam["visibility_auto_submit"],
        "exam_code": exam["exam_code"],
        "access_mode": "PUBLIC",
    }

    return {
        "exam": public_exam_data,
        "questions": questions,
        "access_mode": "PUBLIC",
    }


# =========================================================
# START PRIVATE ATTEMPT
# =========================================================

def _get_existing_attempt(
    invitation_id,
):
    db = get_db()

    return db.execute(
        """
        SELECT *
        FROM attempts
        WHERE invitation_id=?
          AND status IN (
              'IN_PROGRESS',
              'SUBMITTED',
              'AUTO_SUBMITTED'
          )
        ORDER BY start_time DESC
        """,
        (
            invitation_id,
        ),
    ).fetchone()


def start_attempt(
    token,
    candidate,
):
    invitation = load_invitation(
        token
    )

    db = get_db()

    existing = _get_existing_attempt(
        invitation["id"]
    )

    if existing:

        if (
            existing["status"]
            == "IN_PROGRESS"
        ):
            return existing["id"]

        raise PermissionError(
            "This invitation has already been completed"
        )

    exam = db.execute(
        """
        SELECT *
        FROM exams
        WHERE id=?
        """,
        (
            invitation["exam_id"],
        ),
    ).fetchone()

    if not exam:
        raise LookupError(
            "Exam not found"
        )

    if (
        exam["access_mode"]
        and exam["access_mode"] != "PRIVATE"
    ):
        raise PermissionError(
            "This exam must be accessed through its public exam code"
        )

    _validate_schedule(
        exam["id"]
    )

    now = datetime.now(
        timezone.utc
    )

    candidate_name = (
        candidate.get("name")
        or invitation["email"]
    ).strip()

    candidate_email = (
        candidate.get("email")
        or invitation["email"]
    ).strip()

    candidate_phone = (
        candidate.get("phone") or candidate.get("mobile") or ""
    ).strip()

    candidate_department = (
        candidate.get("department") or candidate.get("dept") or ""
    ).strip()

    candidate_division = (
        candidate.get("division") or candidate.get("div") or ""
    ).strip()

    attempt_id = new_id()

    db.execute(
        """
        INSERT INTO attempts (
            id,
            exam_id,
            student_id,
            invitation_id,
            start_time,
            status,
            candidate_name,
            candidate_email,
            candidate_phone,
            candidate_department,
            candidate_division
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            attempt_id,
            exam["id"],
            invitation["student_id"],
            invitation["id"],
            now_iso(),
            "IN_PROGRESS",
            candidate_name,
            candidate_email,
            candidate_phone,
            candidate_department,
            candidate_division,
        ),
    )

    db.execute(
        """
        UPDATE exam_invitations
        SET
            status='STARTED',
            started_at=?
        WHERE id=?
        """,
        (
            now_iso(),
            invitation["id"],
        ),
    )

    db.commit()

    return attempt_id


# =========================================================
# START PUBLIC ATTEMPT
# =========================================================

def start_public_attempt(
    exam_code,
    candidate,
):
    """
    Start an attempt for a PUBLIC exam.

    No invitation is required.

    A synthetic internal invitation record is created
    because the attempts table currently requires
    invitation_id.

    This keeps the existing evaluation/attempt schema
    intact without duplicating the attempt engine.
    """

    exam_code = (
        exam_code
        or ""
    ).strip().upper()

    if not exam_code:
        raise LookupError(
            "Exam code is required"
        )

    db = get_db()

    exam = db.execute(
        """
        SELECT *
        FROM exams
        WHERE exam_code=?
        """,
        (
            exam_code,
        ),
    ).fetchone()

    if not exam:
        raise LookupError(
            "Exam not found"
        )

    if exam["access_mode"] != "PUBLIC":
        raise PermissionError(
            "This exam is private"
        )

    if exam["status"] not in {
        "PUBLISHED",
        "SCHEDULED",
        "LIVE",
    }:
        raise PermissionError(
            "This exam is not available"
        )

    _validate_schedule(
        exam["id"]
    )

    candidate_name = (
        candidate.get("name")
        or ""
    ).strip()

    candidate_email = (
        candidate.get("email")
        or ""
    ).strip().lower()

    candidate_phone = (
        candidate.get("phone") or candidate.get("mobile") or ""
    ).strip()

    candidate_department = (
        candidate.get("department") or candidate.get("dept") or ""
    ).strip()

    candidate_division = (
        candidate.get("division") or candidate.get("div") or ""
    ).strip()

    if not candidate_name:
        raise ValueError(
            "Candidate name is required"
        )

    if not candidate_email:
        raise ValueError(
            "Candidate email is required"
        )

    if not candidate_phone:
        raise ValueError(
            "Mobile number is required"
        )

    if not candidate_department:
        raise ValueError(
            "Department is required"
        )

    if not candidate_division:
        raise ValueError(
            "Division / Section is required"
        )

    # -----------------------------------------------------
    # Find an active student by email when possible.
    # -----------------------------------------------------

    student = db.execute(
        """
        SELECT id
        FROM students
        WHERE lower(email)=lower(?)
        LIMIT 1
        """,
        (
            candidate_email,
        ),
    ).fetchone()

    student_id = (
        student["id"]
        if student
        else None
    )

    # -----------------------------------------------------
    # Prevent duplicate active public attempt.
    #
    # Public candidates do not have invitation IDs,
    # so use exam + candidate identity.
    # -----------------------------------------------------

    existing = db.execute(
        """
        SELECT *
        FROM attempts
        WHERE exam_id=?
          AND lower(candidate_email)=lower(?)
          AND status IN (
              'IN_PROGRESS',
              'SUBMITTED',
              'AUTO_SUBMITTED'
          )
        ORDER BY start_time DESC
        LIMIT 1
        """,
        (
            exam["id"],
            candidate_email,
        ),
    ).fetchone()

    if existing:

        if (
            existing["status"]
            == "IN_PROGRESS"
        ):
            return existing["id"]

        raise PermissionError(
            "You have already completed this exam"
        )

    # -----------------------------------------------------
    # Existing attempts table requires invitation_id.
    #
    # Create an internal invitation record for PUBLIC
    # attempts. It is not sent by email and its token is
    # not exposed to the candidate.
    # -----------------------------------------------------

    internal_invitation_id = new_id()

    internal_token = secrets.token_urlsafe(32)

    now = now_iso()

    db.execute(
        """
        INSERT INTO exam_invitations (
            id,
            exam_id,
            student_id,
            email,
            token_hash,
            status,
            created_at,
            started_at
        )
        VALUES (
            ?, ?, ?, ?, ?, ?, ?, ?
        )
        """,
        (
            internal_invitation_id,
            exam["id"],
            student_id,
            candidate_email,
            token_hash(
                internal_token
            ),
            "STARTED",
            now,
            now,
        ),
    )

    attempt_id = new_id()

    db.execute(
        """
        INSERT INTO attempts (
            id,
            exam_id,
            student_id,
            invitation_id,
            start_time,
            status,
            candidate_name,
            candidate_email,
            candidate_phone,
            candidate_department,
            candidate_division
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            attempt_id,
            exam["id"],
            student_id,
            internal_invitation_id,
            now,
            "IN_PROGRESS",
            candidate_name,
            candidate_email,
            candidate_phone,
            candidate_department,
            candidate_division,
        ),
    )
    db.commit()

    return attempt_id


# =========================================================
# Attempt state
# =========================================================

def get_attempt(aid):
    return get_db().execute(
        """
        SELECT *
        FROM attempts
        WHERE id=?
        """,
        (
            aid,
        ),
    ).fetchone()


def ensure_attempt_active(aid):
    db = get_db()

    attempt = db.execute(
        """
        SELECT *
        FROM attempts
        WHERE id=?
        """,
        (
            aid,
        ),
    ).fetchone()

    if not attempt:
        raise LookupError(
            "Attempt not found"
        )

    if (
        attempt["status"]
        != "IN_PROGRESS"
    ):
        return attempt

    exam = db.execute(
        """
        SELECT duration_minutes
        FROM exams
        WHERE id=?
        """,
        (
            attempt["exam_id"],
        ),
    ).fetchone()

    if exam:

        elapsed = (
            datetime.now(timezone.utc)
            - parse_iso(
                attempt["start_time"]
            )
        ).total_seconds()

        if (
            elapsed
            >= int(
                exam["duration_minutes"]
            ) * 60
        ):

            submit_attempt(
                aid,
                True,
            )

            return db.execute(
                """
                SELECT *
                FROM attempts
                WHERE id=?
                """,
                (
                    aid,
                ),
            ).fetchone()

    return attempt


# =========================================================
# Save answers
# =========================================================

def save_answers(
    aid,
    answers,
):
    db = get_db()

    attempt = ensure_attempt_active(
        aid
    )

    if not attempt:
        raise LookupError(
            "Attempt not found"
        )

    if (
        attempt["status"]
        != "IN_PROGRESS"
    ):
        raise ValueError(
            "Attempt is already finalized"
        )

    valid = {
        row["id"]
        for row in db.execute(
            """
            SELECT q.id
            FROM questions q
            JOIN exam_questions eq
                ON eq.question_id=q.id
            WHERE eq.exam_id=?
            """,
            (
                attempt["exam_id"],
            ),
        ).fetchall()
    }

    for question_id, selected in (
        answers or {}
    ).items():

        if question_id not in valid:
            continue

        if not isinstance(
            selected,
            list,
        ):
            selected = [
                selected
            ]

        normalized = []

        for value in selected:

            try:
                normalized.append(
                    int(value)
                )
            except (
                TypeError,
                ValueError,
            ):
                continue

        normalized = sorted(
            set(
                normalized
            )
        )

        existing = db.execute(
            """
            SELECT id
            FROM attempt_answers
            WHERE attempt_id=?
              AND question_id=?
            """,
            (
                aid,
                question_id,
            ),
        ).fetchone()

        if existing:

            db.execute(
                """
                UPDATE attempt_answers
                SET
                    selected_json=?,
                    updated_at=?
                WHERE id=?
                """,
                (
                    json.dumps(
                        normalized
                    ),
                    now_iso(),
                    existing["id"],
                ),
            )

        else:

            db.execute(
                """
                INSERT INTO attempt_answers (
                    id,
                    attempt_id,
                    question_id,
                    selected_json,
                    updated_at
                )
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    new_id(),
                    aid,
                    question_id,
                    json.dumps(
                        normalized
                    ),
                    now_iso(),
                ),
            )

    db.commit()


# =========================================================
# Security events
# =========================================================

def add_security_event(
    aid,
    event_type,
    metadata,
):
    db = get_db()

    attempt = db.execute(
        """
        SELECT status
        FROM attempts
        WHERE id=?
        """,
        (
            aid,
        ),
    ).fetchone()

    if not attempt:
        raise LookupError(
            "Attempt not found"
        )

    if (
        attempt["status"]
        != "IN_PROGRESS"
    ):
        raise ValueError(
            "Attempt is already finalized"
        )

    db.execute(
        """
        INSERT INTO security_events (
            id,
            attempt_id,
            event_type,
            metadata_json,
            created_at
        )
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            new_id(),
            aid,
            event_type,
            json.dumps(
                metadata or {}
            ),
            now_iso(),
        ),
    )

    db.execute(
        """
        UPDATE attempts
        SET
            security_event_count =
                security_event_count + 1
        WHERE id=?
        """,
        (
            aid,
        ),
    )

    db.commit()


# =========================================================
# Submit attempt
# =========================================================

def submit_attempt(
    aid,
    auto=False,
):
    db = get_db()

    attempt = db.execute(
        """
        SELECT *
        FROM attempts
        WHERE id=?
        """,
        (
            aid,
        ),
    ).fetchone()

    if not attempt:
        raise LookupError(
            "Attempt not found"
        )

    if (
        attempt["status"]
        != "IN_PROGRESS"
    ):

        result = db.execute(
            """
            SELECT id
            FROM results
            WHERE attempt_id=?
            """,
            (
                aid,
            ),
        ).fetchone()

        return (
            result["id"]
            if result
            else None
        )

    now = datetime.now(
        timezone.utc
    )

    start = parse_iso(
        attempt["start_time"]
    )

    elapsed_seconds = max(
        0,
        int(
            (
                now - start
            ).total_seconds()
        ),
    )

    status = (
        "AUTO_SUBMITTED"
        if auto
        else "SUBMITTED"
    )

    db.execute(
        """
        UPDATE attempts
        SET
            status=?,
            submit_time=?,
            time_taken_seconds=?
        WHERE id=?
        """,
        (
            status,
            now_iso(),
            elapsed_seconds,
            aid,
        ),
    )

    db.execute(
        """
        UPDATE exam_invitations
        SET
            status='COMPLETED',
            completed_at=?
        WHERE id=?
        """,
        (
            now_iso(),
            attempt["invitation_id"],
        ),
    )

    db.commit()

    result_id = evaluate_attempt(
        aid
    )

    result = db.execute(
        """
        SELECT
            r.*,
            e.title
        FROM results r
        JOIN exams e
            ON e.id=r.exam_id
        WHERE r.id=?
        """,
        (
            result_id,
        ),
    ).fetchone()

    if result:

        enqueue_email(
            "RESULT",
            attempt["candidate_email"],
            f"ExamForge result: {result['title']}",
            (
                "Your result is ready.\n\n"
                f"Score: {result['score']}/"
                f"{result['max_marks']}\n"
                f"Percentage: "
                f"{result['percentage']:.2f}%\n"
                f"Status: "
                f"{'PASS' if result['passed'] else 'FAIL'}."
            ),
            None,
        )

    return result_id