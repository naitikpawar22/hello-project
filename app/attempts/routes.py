from datetime import datetime, timezone

from flask import Blueprint, request, jsonify

from app.attempts.service import (
    public_exam,
    load_public_exam,
    start_attempt,
    start_public_attempt,
    save_answers,
    add_security_event,
    submit_attempt,
    get_attempt,
    ensure_attempt_active,
)


bp = Blueprint(
    "attempts",
    __name__,
    url_prefix="/api",
)


# =========================================================
# PRIVATE EXAM ACCESS
# =========================================================

@bp.get("/student/exams/<token>")
def student_exam(token):

    try:
        return jsonify(
            public_exam(token)
        )

    except LookupError as e:
        return jsonify(
            error=str(e)
        ), 404

    except PermissionError as e:
        return jsonify(
            error=str(e)
        ), 403


# =========================================================
# PUBLIC EXAM ACCESS
# =========================================================

@bp.get("/student/public-exams/<exam_code>")
def student_public_exam(exam_code):

    try:
        return jsonify(
            load_public_exam(
                exam_code
            )
        )

    except LookupError as e:
        return jsonify(
            error=str(e)
        ), 404

    except PermissionError as e:
        return jsonify(
            error=str(e)
        ), 403


# =========================================================
# START ATTEMPT
# =========================================================

@bp.post("/attempts")
def start():

    data = (
        request.get_json(
            silent=True
        )
        or {}
    )

    token = data.get(
        "token"
    )

    exam_code = data.get(
        "exam_code"
    )

    try:

        # -------------------------------------------------
        # PRIVATE
        # -------------------------------------------------

        if token:

            attempt_id = start_attempt(
                token,
                data,
            )

        # -------------------------------------------------
        # PUBLIC
        # -------------------------------------------------

        elif exam_code:

            attempt_id = start_public_attempt(
                exam_code,
                data,
            )

        else:

            return jsonify(
                error=(
                    "token or exam_code "
                    "is required"
                )
            ), 400

    except LookupError as e:

        return jsonify(
            error=str(e)
        ), 404

    except PermissionError as e:

        return jsonify(
            error=str(e)
        ), 403

    except ValueError as e:

        return jsonify(
            error=str(e)
        ), 422

    return jsonify(
        attempt_id=attempt_id
    ), 201


# =========================================================
# Attempt state
# =========================================================

@bp.get("/attempts/<aid>")
def state(aid):

    try:

        attempt = ensure_attempt_active(
            aid
        )

    except LookupError as e:

        return jsonify(
            error=str(e)
        ), 404

    if not attempt:

        return jsonify(
            error="Attempt not found"
        ), 404

    exam = get_attempt_exam(
        attempt["exam_id"]
    )

    if not exam:

        return jsonify(
            error="Exam not found"
        ), 404

    return jsonify(
        attempt=dict(
            attempt
        ),
        server_now=(
            datetime.now(
                timezone.utc
            ).isoformat()
        ),
        duration_minutes=exam[
            "duration_minutes"
        ],
    )


def get_attempt_exam(exam_id):
    from app.database import get_db

    return get_db().execute(
        """
        SELECT *
        FROM exams
        WHERE id=?
        """,
        (
            exam_id,
        ),
    ).fetchone()


# =========================================================
# Save answers
# =========================================================

@bp.put("/attempts/<aid>/answers")
def answers(aid):

    data = (
        request.get_json(
            silent=True
        )
        or {}
    )

    try:

        save_answers(
            aid,
            data.get(
                "answers",
                {},
            ),
        )

    except LookupError as e:

        return jsonify(
            error=str(e)
        ), 404

    except ValueError as e:

        return jsonify(
            error=str(e)
        ), 409

    return jsonify(
        message="Answers saved"
    )


# =========================================================
# Security events
# =========================================================

@bp.post("/attempts/<aid>/events")
def events(aid):

    data = (
        request.get_json(
            silent=True
        )
        or {}
    )

    attempt = get_attempt(
        aid
    )

    if not attempt:

        return jsonify(
            error="Attempt not found"
        ), 404

    if (
        attempt["status"]
        != "IN_PROGRESS"
    ):

        return jsonify(
            error="Attempt finalized"
        ), 409

    try:

        add_security_event(
            aid,
            str(
                data.get(
                    "event_type",
                    "unknown",
                )
            )[:64],
            data.get(
                "metadata"
            )
            or {},
        )

    except ValueError as e:

        return jsonify(
            error=str(e)
        ), 409

    return jsonify(
        message="Event recorded"
    )


# =========================================================
# Submit attempt
# =========================================================

@bp.post("/attempts/<aid>/submit")
def submit(aid):

    data = (
        request.get_json(
            silent=True
        )
        or {}
    )

    auto = bool(
        data.get(
            "auto",
            False,
        )
    )

    try:

        result_id = submit_attempt(
            aid,
            auto,
        )

    except LookupError as e:

        return jsonify(
            error=str(e)
        ), 404

    return jsonify(
        result_id=result_id
    ), 200