from datetime import datetime, timedelta, timezone

from app.database import get_db
from app.email.service import enqueue_email
from app.utils.helpers import (
    new_id,
    now_iso,
    secure_token,
    token_hash,
)


def is_email_enabled():
    """
    Email sending is disabled by default.

    Local development:
        EXAMFORGE_EMAIL_ENABLED=0

    Production:
        EXAMFORGE_EMAIL_ENABLED=1
    """

    import os

    return (
        os.getenv(
            "EXAMFORGE_EMAIL_ENABLED",
            "0",
        )
        == "1"
    )


def create_invitation(
    eid,
    email,
    student_id=None,
    expires_at=None,
):
    db = get_db()

    email = (
        email or ""
    ).strip().lower()

    if not email or "@" not in email:
        return None, "Valid email is required"

    exam = db.execute(
        """
        SELECT
            id,
            title,
            access_mode,
            status
        FROM exams
        WHERE id=?
        """,
        (eid,),
    ).fetchone()

    if not exam:
        return None, "Exam not found"

    # Public exams do not need invitations.
    if exam["access_mode"] == "PUBLIC":
        return None, (
            "Public exams do not require student invitations"
        )

    existing = db.execute(
        """
        SELECT
            id,
            status
        FROM exam_invitations
        WHERE exam_id=?
          AND lower(email)=lower(?)
          AND status NOT IN (
              'CANCELLED',
              'EXPIRED'
          )
        """,
        (
            eid,
            email,
        ),
    ).fetchone()

    if existing:
        return None, "Invitation already exists"

    # ---------------------------------------------------------
    # Generate secure token
    # ---------------------------------------------------------

    token = secure_token()

    invitation_id = new_id()

    timestamp = now_iso()

    if expires_at:
        expiry = expires_at
    else:
        expiry = (
            datetime.now(timezone.utc)
            + timedelta(days=30)
        ).isoformat()

    # ---------------------------------------------------------
    # Create invitation
    #
    # Only the HASH is stored for authentication.
    # The raw token is returned to the caller so that
    # the secure URL can be created.
    # ---------------------------------------------------------

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
            expires_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            invitation_id,
            eid,
            student_id,
            email,
            token_hash(token),
            "PENDING",
            timestamp,
            expiry,
        ),
    )

    db.commit()

    return (
        (
            invitation_id,
            token,
        ),
        None,
    )


def build_invitation_link(
    base_url,
    token,
):
    return (
        f"{base_url.rstrip('/')}"
        f"/student/exam/{token}"
    )


def queue_invitations(
    eid,
    items,
    base_url,
):
    db = get_db()

    created = []

    exam = db.execute(
        """
        SELECT
            id,
            title,
            access_mode
        FROM exams
        WHERE id=?
        """,
        (eid,),
    ).fetchone()

    if not exam:
        raise ValueError(
            "Exam not found"
        )

    if exam["access_mode"] == "PUBLIC":
        raise ValueError(
            "Public exams do not require invitations"
        )

    email_enabled = is_email_enabled()

    for item in items:

        result, error = create_invitation(
            eid,
            item.get("email"),
            item.get("student_id"),
        )

        if error:
            continue

        invitation_id, token = result

        # -----------------------------------------------------
        # Build the student's unique secure exam URL
        # -----------------------------------------------------

        link = build_invitation_link(
            base_url,
            token,
        )

        # -----------------------------------------------------
        # Save the URL for the future EXAM_STARTED email.
        #
        # We cannot recreate the raw token later because
        # only its hash is stored for authentication.
        # -----------------------------------------------------

        db.execute(
            """
            UPDATE exam_invitations
            SET start_email_link=?
            WHERE id=?
            """,
            (
                link,
                invitation_id,
            ),
        )

        exam_title = (
            item.get("exam_title")
            or exam["title"]
            or "Your exam"
        )

        subject = (
            f"ExamForge invitation: "
            f"{exam_title}"
        )

        body = (
            "You are invited to take the exam.\n\n"
            f"Exam: {exam_title}\n\n"
            "Open your secure exam link:\n"
            f"{link}\n\n"
            "This invitation link is unique to you."
        )

        status = "PENDING"
        sent_at = None
        email_job_id = None

        if email_enabled:

            email_job_id = enqueue_email(
                "INVITATION",
                item["email"],
                subject,
                body,
                None,
            )

            # Queued != successfully sent.
            # The email worker is responsible for actual sending.
            status = "PENDING"

        else:

            # Local development:
            # do not send and do not mark SENT.
            status = "DISABLED"

        db.execute(
            """
            UPDATE exam_invitations
            SET
                status=?,
                sent_at=?
            WHERE id=?
            """,
            (
                status,
                sent_at,
                invitation_id,
            ),
        )

        db.commit()

        created.append(
            {
                "id": invitation_id,
                "email": item["email"],
                "link": link,
                "status": status,
                "email_enabled": email_enabled,
                "email_job_id": email_job_id,
            }
        )

    return created


def cancel_invitation(
    invitation_id,
):
    """
    Cancel an invitation.

    The invitation record is retained so audit/history
    remains available and its token cannot be used.
    """

    db = get_db()

    invitation = db.execute(
        """
        SELECT
            id,
            exam_id,
            status
        FROM exam_invitations
        WHERE id=?
        """,
        (invitation_id,),
    ).fetchone()

    if not invitation:
        raise LookupError(
            "Invitation not found"
        )

    if invitation["status"] == "CANCELLED":
        return False

    if invitation["status"] == "COMPLETED":
        raise ValueError(
            "Completed invitations cannot be cancelled"
        )

    if invitation["status"] == "EXPIRED":
        return False

    db.execute(
        """
        UPDATE exam_invitations
        SET status='CANCELLED'
        WHERE id=?
        """,
        (invitation_id,),
    )

    db.commit()

    return True


def get_invitation(
    invitation_id,
):
    db = get_db()

    row = db.execute(
        """
        SELECT *
        FROM exam_invitations
        WHERE id=?
        """,
        (invitation_id,),
    ).fetchone()

    return dict(row) if row else None