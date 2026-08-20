import csv
import io

from flask import Blueprint, request, jsonify

from app.database import get_db
from app.invitations.service import (
    create_invitation,
    queue_invitations,
    cancel_invitation,
)
from app.email.service import enqueue_email
from app.utils.security import admin_or_teacher_required
from app.utils.audit import audit
from app.utils.helpers import now_iso, get_shareable_url


bp = Blueprint(
    "invitations",
    __name__,
    url_prefix="/api/exams",
)


# =========================================================
# Create single invitation
# =========================================================

@bp.post("/<eid>/invitations")
@admin_or_teacher_required
def one(eid, actor):

    data = request.get_json(silent=True) or {}

    email = (
        data.get("email") or ""
    ).strip().lower()

    student_id = data.get("student_id")

    if not email or "@" not in email:
        return jsonify(
            error="Valid email is required"
        ), 422

    db = get_db()

    # -----------------------------------------------------
    # Check exam
    # -----------------------------------------------------

    exam = db.execute(
        """
        SELECT
            id,
            title,
            access_mode,
            creator_id
        FROM exams
        WHERE id=?
        """,
        (eid,),
    ).fetchone()

    if not exam:
        return jsonify(
            error="Exam not found"
        ), 404

    # -----------------------------------------------------
    # Teacher authorization
    # -----------------------------------------------------

    if (
        actor["role"] != "admin"
        and exam["creator_id"] != actor["id"]
    ):
        return jsonify(
            error="Not authorized"
        ), 403

    # -----------------------------------------------------
    # Public exams do not require invitations
    # -----------------------------------------------------

    if exam["access_mode"] == "PUBLIC":
        return jsonify(
            error="Public exams do not require invitations"
        ), 422

    # -----------------------------------------------------
    # Create invitation
    # -----------------------------------------------------

    result, error = create_invitation(
        eid,
        email,
        student_id,
    )

    if error:
        return jsonify(
            error=error
        ), 409

    from app.utils.helpers import get_shareable_url

    invitation_id, token = result

    link = get_shareable_url(request, f"student/exam/{token}")


    # -----------------------------------------------------
    # Email
    #
    # The invitation service is responsible for deciding
    # whether local email sending is enabled.
    # -----------------------------------------------------

    from app.invitations.service import is_email_enabled

    email_enabled = is_email_enabled()

    email_job_id = None
    invitation_status = "DISABLED"

    if email_enabled:

        subject = (
            f"ExamForge invitation: "
            f"{exam['title']}"
        )

        body = (
            "You are invited to take the exam.\n\n"
            f"Exam: {exam['title']}\n\n"
            "Open your secure exam link:\n"
            f"{link}\n\n"
            "This invitation link is unique to you."
        )

        email_job_id = enqueue_email(
            "INVITATION",
            email,
            subject,
            body,
            None,
        )

        # Do NOT mark SENT here.
        #
        # The email worker must change the invitation
        # to SENT only after actual SMTP delivery.

        invitation_status = "PENDING"

    # -----------------------------------------------------
    # Update invitation state
    # -----------------------------------------------------

    db.execute(
        """
        UPDATE exam_invitations
        SET
            status=?,
            sent_at=NULL
        WHERE id=?
        """,
        (
            invitation_status,
            invitation_id,
        ),
    )

    db.commit()

    audit(
        actor,
        "invitation_created",
        "exam_invitations",
        invitation_id,
        {
            "email": email,
            "email_enabled": email_enabled,
        },
    )

    return jsonify(
        id=invitation_id,
        token=token,
        link=link,
        email=email,
        email_enabled=email_enabled,
        email_queued=bool(email_job_id),
        status=invitation_status,
        email_job_id=email_job_id,
    ), 201


# =========================================================
# Bulk invitations
# =========================================================

@bp.post("/<eid>/invitations/bulk")
@admin_or_teacher_required
def bulk(eid, actor):

    db = get_db()

    # -----------------------------------------------------
    # Check exam
    # -----------------------------------------------------

    exam = db.execute(
        """
        SELECT
            id,
            title,
            access_mode,
            creator_id
        FROM exams
        WHERE id=?
        """,
        (eid,),
    ).fetchone()

    if not exam:
        return jsonify(
            error="Exam not found"
        ), 404

    # -----------------------------------------------------
    # Teacher authorization
    # -----------------------------------------------------

    if (
        actor["role"] != "admin"
        and exam["creator_id"] != actor["id"]
    ):
        return jsonify(
            error="Not authorized"
        ), 403

    # -----------------------------------------------------
    # Public exams don't need invitations
    # -----------------------------------------------------

    if exam["access_mode"] == "PUBLIC":
        return jsonify(
            error="Public exams do not require invitations"
        ), 422

    emails = []

    # -----------------------------------------------------
    # JSON input
    # -----------------------------------------------------

    data = request.get_json(silent=True)

    if data:

        raw_emails = data.get(
            "emails",
            [],
        )

        if not isinstance(
            raw_emails,
            list,
        ):
            return jsonify(
                error="emails must be an array"
            ), 422

        for value in raw_emails:

            email = (
                str(value)
                .strip()
                .lower()
            )

            if "@" in email:
                emails.append(
                    {
                        "email": email,
                    }
                )

    # -----------------------------------------------------
    # CSV upload
    # -----------------------------------------------------

    elif "file" in request.files:

        uploaded_file = request.files["file"]

        if not uploaded_file.filename:
            return jsonify(
                error="CSV file is required"
            ), 400

        try:

            content = uploaded_file.read().decode(
                "utf-8-sig"
            )

            rows = csv.DictReader(
                io.StringIO(content)
            )

            for row in rows:

                email = (
                    row.get("email")
                    or ""
                ).strip().lower()

                if "@" in email:
                    emails.append(
                        {
                            "email": email,
                            "student_id": (
                                row.get("student_id")
                                or None
                            ),
                        }
                    )

        except UnicodeDecodeError:

            return jsonify(
                error="CSV file must be UTF-8 encoded"
            ), 422

    # -----------------------------------------------------
    # Pasted email list
    # -----------------------------------------------------

    else:

        raw = (
            request.form.get(
                "emails",
                "",
            )
            .replace(";", ",")
        )

        for value in raw.split(","):

            email = (
                value
                .strip()
                .lower()
            )

            if "@" in email:
                emails.append(
                    {
                        "email": email,
                    }
                )

    # -----------------------------------------------------
    # Validate list
    # -----------------------------------------------------

    if not emails:
        return jsonify(
            error="No valid email addresses were provided"
        ), 422

    # Remove duplicates while preserving order.

    unique = []
    seen = set()

    for item in emails:

        email = item["email"]

        if email in seen:
            continue

        seen.add(email)
        unique.append(item)

    emails = unique

    # -----------------------------------------------------
    # Create invitations
    # -----------------------------------------------------

    try:

        created = queue_invitations(
            eid,
            [
                {
                    **item,
                    "exam_title": exam["title"],
                }
                for item in emails
            ],
            get_shareable_url(request, "").rstrip("/"),
        )


    except ValueError as e:

        return jsonify(
            error=str(e)
        ), 422

    audit(
        actor,
        "invitations_created",
        "exams",
        eid,
        {
            "count": len(created),
            "requested_count": len(emails),
        },
    )

    return jsonify(
        created=created,
        created_count=len(created),
        requested_count=len(emails),
    ), 201


# =========================================================
# List invitations
# =========================================================

@bp.get("/<eid>/invitations")
@admin_or_teacher_required
def list_invites(eid, actor):

    db = get_db()

    exam = db.execute(
        """
        SELECT
            id,
            creator_id
        FROM exams
        WHERE id=?
        """,
        (eid,),
    ).fetchone()

    if not exam:
        return jsonify(
            error="Exam not found"
        ), 404

    # -----------------------------------------------------
    # Teacher authorization
    # -----------------------------------------------------

    if (
        actor["role"] != "admin"
        and exam["creator_id"] != actor["id"]
    ):
        return jsonify(
            error="Not authorized"
        ), 403

    rows = db.execute(
        """
        SELECT
            id,
            email,
            status,
            created_at,
            sent_at,
            opened_at,
            started_at,
            completed_at,
            expires_at,
            student_id
        FROM exam_invitations
        WHERE exam_id=?
        ORDER BY created_at DESC
        """,
        (eid,),
    ).fetchall()

    return jsonify(
        invitations=[
            dict(row)
            for row in rows
        ]
    )


# =========================================================
# Cancel / Delete invitation
# =========================================================

@bp.delete("/<eid>/invitations/<iid>")
@admin_or_teacher_required
def delete_invitation(eid, iid, actor):

    db = get_db()

    # -----------------------------------------------------
    # Check invitation belongs to this exam
    # -----------------------------------------------------

    invitation = db.execute(
        """
        SELECT
            id,
            exam_id,
            email,
            status
        FROM exam_invitations
        WHERE id=?
          AND exam_id=?
        """,
        (
            iid,
            eid,
        ),
    ).fetchone()

    if not invitation:
        return jsonify(
            error="Invitation not found"
        ), 404

    # -----------------------------------------------------
    # Check exam ownership
    # -----------------------------------------------------

    exam = db.execute(
        """
        SELECT
            id,
            creator_id
        FROM exams
        WHERE id=?
        """,
        (eid,),
    ).fetchone()

    if not exam:
        return jsonify(
            error="Exam not found"
        ), 404

    if (
        actor["role"] != "admin"
        and exam["creator_id"] != actor["id"]
    ):
        return jsonify(
            error="Not authorized"
        ), 403

    # -----------------------------------------------------
    # Cancel invitation
    # -----------------------------------------------------

    try:

        changed = cancel_invitation(iid)

    except LookupError as e:

        return jsonify(
            error=str(e)
        ), 404

    except ValueError as e:

        return jsonify(
            error=str(e)
        ), 409

    if not changed:
        return jsonify(
            message="Invitation is already inactive"
        ), 200

    audit(
        actor,
        "invitation_cancelled",
        "exam_invitations",
        iid,
        {
            "email": invitation["email"],
            "previous_status": invitation["status"],
        },
    )

    return jsonify(
        message="Invitation cancelled successfully"
    ), 200