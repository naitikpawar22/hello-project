import json
import secrets
import string

from app.database import get_db
from app.utils.helpers import new_id, now_iso


EXAM_CODE_ALPHABET = string.ascii_uppercase + string.digits


def generate_exam_code():
    """
    Generate a human-readable unique ExamForge code.

    Example:
    EXF-7K29PQ
    """

    db = get_db()

    while True:
        suffix = "".join(
            secrets.choice(EXAM_CODE_ALPHABET)
            for _ in range(6)
        )

        code = f"EXF-{suffix}"

        exists = db.execute(
            """
            SELECT 1
            FROM exams
            WHERE exam_code=?
            LIMIT 1
            """,
            (code,),
        ).fetchone()

        if not exists:
            return code


def generate_public_token():
    """
    Cryptographically secure token for public exam URLs.
    """

    return secrets.token_urlsafe(32)


def create_exam(data, actor):
    title = (
        data.get("title")
        or ""
    ).strip()

    duration = int(
        data.get(
            "duration_minutes",
            0,
        )
    )

    pass_pct = float(
        data.get(
            "pass_percentage",
            40,
        )
    )

    qids = data.get(
        "question_ids"
    ) or []

    access_mode = (
        data.get(
            "access_mode",
            "PRIVATE",
        )
        or "PRIVATE"
    ).upper()

    if access_mode not in {
        "PRIVATE",
        "PUBLIC",
    }:
        raise ValueError(
            "access_mode must be PRIVATE or PUBLIC"
        )

    if not title:
        raise ValueError(
            "title is required"
        )

    if duration <= 0:
        raise ValueError(
            "duration_minutes must be greater than 0"
        )

    if not 0 <= pass_pct <= 100:
        raise ValueError(
            "pass_percentage must be between 0 and 100"
        )

    if not qids:
        raise ValueError(
            "Exam must contain at least one question"
        )

    # Remove duplicate question IDs while preserving order.
    qids = list(
        dict.fromkeys(
            str(qid)
            for qid in qids
            if qid
        )
    )

    db = get_db()

    placeholders = ",".join(
        "?" for _ in qids
    )

    rows = db.execute(
        f"""
        SELECT id
        FROM questions
        WHERE id IN ({placeholders})
          AND active=1
        """,
        qids,
    ).fetchall()

    valid = [
        row["id"]
        for row in rows
    ]

    if len(valid) != len(qids):
        raise ValueError(
            "One or more selected questions do not exist or are inactive"
        )

    eid = new_id()
    exam_code = generate_exam_code()
    public_token = generate_public_token()
    timestamp = now_iso()

    security = (
        data.get("security_settings")
        or {}
    )

    if isinstance(
        security,
        str,
    ):
        security = json.loads(
            security
        )

    db.execute("BEGIN")

    try:
        db.execute(
            """
            INSERT INTO exams (
                id,
                title,
                description,
                duration_minutes,
                pass_percentage,
                randomize_questions,
                randomize_options,
                security_settings,
                status,
                visibility_auto_submit,
                creator_id,
                creator_role,
                created_at,
                updated_at,
                exam_code,
                public_token,
                access_mode
            )
            VALUES (
                ?, ?, ?, ?, ?, ?, ?, ?, ?,
                ?, ?, ?, ?, ?, ?, ?, ?
            )
            """,
            (
                eid,
                title,
                data.get(
                    "description",
                    "",
                ) or "",
                duration,
                pass_pct,
                int(
                    bool(
                        data.get(
                            "randomize_questions"
                        )
                    )
                ),
                int(
                    bool(
                        data.get(
                            "randomize_options"
                        )
                    )
                ),
                json.dumps(
                    security
                ),
                "DRAFT",
                int(
                    bool(
                        data.get(
                            "visibility_auto_submit"
                        )
                    )
                ),
                actor["id"],
                actor["role"],
                timestamp,
                timestamp,
                exam_code,
                public_token,
                access_mode,
            ),
        )

        marks = (
            data.get(
                "question_marks"
            )
            or {}
        )

        negative_marks = (
            data.get(
                "question_negative_marks"
            )
            or {}
        )

        for index, qid in enumerate(qids):
            question = db.execute(
                """
                SELECT
                    marks,
                    negative_marks
                FROM questions
                WHERE id=?
                """,
                (qid,),
            ).fetchone()

            db.execute(
                """
                INSERT INTO exam_questions (
                    id,
                    exam_id,
                    question_id,
                    question_order,
                    exam_marks,
                    exam_negative_marks
                )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    new_id(),
                    eid,
                    qid,
                    index,
                    float(
                        marks.get(
                            qid,
                            question["marks"],
                        )
                    ),
                    float(
                        negative_marks.get(
                            qid,
                            question["negative_marks"],
                        )
                    ),
                ),
            )

        db.commit()

    except Exception:
        db.rollback()
        raise

    return eid


def update_exam(eid, data, actor):
    db = get_db()

    row = db.execute(
        """
        SELECT *
        FROM exams
        WHERE id=?
        """,
        (eid,),
    ).fetchone()

    if not row:
        raise LookupError(
            "Exam not found"
        )

    if (
        actor["role"] != "admin"
        and row["creator_id"] != actor["id"]
    ):
        raise PermissionError(
            "Not authorized"
        )

    title = data.get(
        "title",
        row["title"],
    )

    duration = int(
        data.get(
            "duration_minutes",
            row["duration_minutes"],
        )
    )

    pass_pct = float(
        data.get(
            "pass_percentage",
            row["pass_percentage"],
        )
    )

    access_mode = (
        data.get(
            "access_mode",
            row["access_mode"] or "PRIVATE",
        )
        or "PRIVATE"
    ).upper()

    if duration <= 0:
        raise ValueError(
            "Invalid duration"
        )

    if not 0 <= pass_pct <= 100:
        raise ValueError(
            "Invalid pass percentage"
        )

    if access_mode not in {
        "PRIVATE",
        "PUBLIC",
    }:
        raise ValueError(
            "access_mode must be PRIVATE or PUBLIC"
        )

    db.execute(
        """
        UPDATE exams
        SET
            title=?,
            description=?,
            duration_minutes=?,
            pass_percentage=?,
            randomize_questions=?,
            randomize_options=?,
            access_mode=?,
            updated_at=?
        WHERE id=?
        """,
        (
            title,
            data.get(
                "description",
                row["description"],
            ),
            duration,
            pass_pct,
            int(
                bool(
                    data.get(
                        "randomize_questions",
                        row["randomize_questions"],
                    )
                )
            ),
            int(
                bool(
                    data.get(
                        "randomize_options",
                        row["randomize_options"],
                    )
                )
            ),
            access_mode,
            now_iso(),
            eid,
        ),
    )

    db.commit()


def get_exam(eid):
    db = get_db()

    exam = db.execute(
        """
        SELECT *
        FROM exams
        WHERE id=?
        """,
        (eid,),
    ).fetchone()

    if not exam:
        return None

    questions = db.execute(
        """
        SELECT
            q.*,
            eq.id exam_question_id,
            eq.question_order,
            eq.exam_marks,
            eq.exam_negative_marks
        FROM exam_questions eq
        JOIN questions q
            ON q.id=eq.question_id
        WHERE eq.exam_id=?
        ORDER BY eq.question_order
        """,
        (eid,),
    ).fetchall()

    result = {
        **dict(exam),
        "security_settings": json.loads(
            exam["security_settings"]
            or "{}"
        ),
        "questions": [
            dict(question)
            for question in questions
        ],
    }

    return result


def get_exam_public_data(eid):
    """
    Return only the information needed by admin after creation.
    Never expose the internal database ID as the public exam token.
    """

    db = get_db()

    exam = db.execute(
        """
        SELECT
            id,
            title,
            exam_code,
            public_token,
            access_mode
        FROM exams
        WHERE id=?
        """,
        (eid,),
    ).fetchone()

    if not exam:
        return None

    return dict(exam)