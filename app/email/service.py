import os
import smtplib
from email.message import EmailMessage
from pathlib import Path

from app.database import get_db
from app.utils.helpers import new_id, now_iso


def email_enabled():
    """
    Master switch for email sending.

    Local development:
        EXAMFORGE_EMAIL_ENABLED=0

    Production:
        EXAMFORGE_EMAIL_ENABLED=1
    """

    return (
        os.getenv(
            "EXAMFORGE_EMAIL_ENABLED",
            "0",
        )
        == "1"
    )


def smtp_configured():
    """
    Check minimum SMTP configuration required
    to attempt an actual email send.
    """

    return bool(
        os.getenv("SMTP_HOST")
        and os.getenv("SMTP_FROM")
    )


def enqueue_email(
    kind,
    recipient,
    subject,
    body,
    attachment_path=None,
):
    """
    Create a database-backed email job.

    This function DOES NOT send email.
    """

    recipient = (
        recipient
        or ""
    ).strip()

    if not recipient:
        raise ValueError(
            "Email recipient is required"
        )

    db = get_db()

    job_id = new_id()

    db.execute(
        """
        INSERT INTO email_jobs (
            id,
            kind,
            recipient,
            subject,
            body,
            attachment_path,
            status,
            created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            job_id,
            kind,
            recipient,
            subject,
            body,
            attachment_path,
            "PENDING",
            now_iso(),
        ),
    )

    db.commit()

    return job_id


def _mark_invitation_sent(db, email_job):
    """
    When an invitation email is actually sent,
    update its invitation record to SENT.

    We identify the invitation by recipient email
    and exam-related email job timing. Since the
    current email_jobs table does not contain an
    explicit invitation_id, update the most recent
    matching PENDING/DISABLED invitation.
    """

    if email_job["kind"] != "INVITATION":
        return

    db.execute(
        """
        UPDATE exam_invitations
        SET
            status='SENT',
            sent_at=?
        WHERE id = (
            SELECT ei.id
            FROM exam_invitations ei
            WHERE lower(ei.email)=lower(?)
              AND ei.status IN ('PENDING', 'DISABLED')
            ORDER BY ei.created_at DESC
            LIMIT 1
        )
        """,
        (
            now_iso(),
            email_job["recipient"],
        ),
    )


def _mark_invitation_failed(db, email_job, error_message):
    """
    Keep invitation non-SENT if the SMTP attempt failed.
    """

    if email_job["kind"] != "INVITATION":
        return

    db.execute(
        """
        UPDATE exam_invitations
        SET
            status='PENDING'
        WHERE id = (
            SELECT ei.id
            FROM exam_invitations ei
            WHERE lower(ei.email)=lower(?)
              AND ei.status IN ('PENDING', 'DISABLED')
            ORDER BY ei.created_at DESC
            LIMIT 1
        )
        """,
        (
            email_job["recipient"],
        ),
    )


def process_pending(limit=50):
    """
    Process database-backed email jobs.

    Possible states:

        EXAMFORGE_EMAIL_ENABLED=0
            -> DISABLED

        SMTP not configured
            -> DISABLED

        SMTP send succeeds
            -> SENT

        SMTP send fails
            -> RETRY
    """

    db = get_db()

    rows = db.execute(
        """
        SELECT *
        FROM email_jobs
        WHERE status IN ('PENDING', 'RETRY')
        ORDER BY created_at
        LIMIT ?
        """,
        (limit,),
    ).fetchall()

    results = []

    # -----------------------------------------------------
    # Local development / email disabled
    # -----------------------------------------------------

    if not email_enabled():

        for row in rows:

            db.execute(
                """
                UPDATE email_jobs
                SET
                    status='DISABLED',
                    last_error=?,
                    attempts=attempts+1
                WHERE id=?
                """,
                (
                    "Email sending is disabled in this environment",
                    row["id"],
                ),
            )

        db.commit()

        return [
            {
                "id": row["id"],
                "status": "DISABLED",
            }
            for row in rows
        ]

    # -----------------------------------------------------
    # Email enabled but SMTP missing
    # -----------------------------------------------------

    if not smtp_configured():

        for row in rows:

            db.execute(
                """
                UPDATE email_jobs
                SET
                    status='DISABLED',
                    last_error=?,
                    attempts=attempts+1
                WHERE id=?
                """,
                (
                    "SMTP is not configured",
                    row["id"],
                ),
            )

        db.commit()

        return [
            {
                "id": row["id"],
                "status": "DISABLED",
            }
            for row in rows
        ]

    # -----------------------------------------------------
    # Process actual SMTP jobs
    # -----------------------------------------------------

    for row in rows:

        server = None

        try:

            message = EmailMessage()

            message["Subject"] = row["subject"]
            message["From"] = os.getenv("SMTP_FROM")
            message["To"] = row["recipient"]

            message.set_content(
                row["body"]
            )

            # -------------------------------------------------
            # Optional PDF attachment
            # -------------------------------------------------

            if row["attachment_path"]:

                attachment = Path(
                    row["attachment_path"]
                )

                if attachment.exists():

                    with attachment.open(
                        "rb"
                    ) as file:

                        message.add_attachment(
                            file.read(),
                            maintype="application",
                            subtype="pdf",
                            filename=attachment.name,
                        )

            # -------------------------------------------------
            # SMTP configuration
            # -------------------------------------------------

            host = os.getenv(
                "SMTP_HOST"
            )

            port = int(
                os.getenv(
                    "SMTP_PORT",
                    "587",
                )
            )

            use_tls = (
                os.getenv(
                    "SMTP_USE_TLS",
                    "1",
                )
                == "1"
            )

            username = os.getenv(
                "SMTP_USERNAME"
            )

            password = os.getenv(
                "SMTP_PASSWORD",
                "",
            )

            # -------------------------------------------------
            # Connect
            # -------------------------------------------------

            server = smtplib.SMTP(
                host,
                port,
                timeout=20,
            )

            server.ehlo()

            if use_tls:
                server.starttls()
                server.ehlo()

            if username:
                server.login(
                    username,
                    password,
                )

            # -------------------------------------------------
            # Actual send
            # -------------------------------------------------

            server.send_message(
                message
            )

            server.quit()
            server = None

            # -------------------------------------------------
            # Mark email SENT
            # -------------------------------------------------

            sent_time = now_iso()

            db.execute(
                """
                UPDATE email_jobs
                SET
                    status='SENT',
                    sent_at=?,
                    last_error=NULL,
                    attempts=attempts+1
                WHERE id=?
                """,
                (
                    sent_time,
                    row["id"],
                ),
            )

            # -------------------------------------------------
            # Invitation synchronization
            # -------------------------------------------------

            if row["kind"] == "INVITATION":
                db.execute(
                    """
                    UPDATE exam_invitations
                    SET
                        status='SENT',
                        sent_at=?
                    WHERE id = (
                        SELECT ei.id
                        FROM exam_invitations ei
                        WHERE lower(ei.email)=lower(?)
                          AND ei.status IN ('PENDING', 'DISABLED')
                        ORDER BY ei.created_at DESC
                        LIMIT 1
                    )
                    """,
                    (
                        sent_time,
                        row["recipient"],
                    ),
                )

            results.append(
                {
                    "id": row["id"],
                    "status": "SENT",
                }
            )

        except Exception as error:

            error_text = str(error)[:1000]

            if server is not None:

                try:
                    server.quit()
                except Exception:
                    pass

            db.execute(
                """
                UPDATE email_jobs
                SET
                    status='RETRY',
                    last_error=?,
                    attempts=attempts+1
                WHERE id=?
                """,
                (
                    error_text,
                    row["id"],
                ),
            )

            # Keep invitation non-SENT.
            if row["kind"] == "INVITATION":

                db.execute(
                    """
                    UPDATE exam_invitations
                    SET status='PENDING'
                    WHERE id = (
                        SELECT ei.id
                        FROM exam_invitations ei
                        WHERE lower(ei.email)=lower(?)
                          AND ei.status IN ('PENDING', 'DISABLED')
                        ORDER BY ei.created_at DESC
                        LIMIT 1
                    )
                    """,
                    (
                        row["recipient"],
                    ),
                )

            results.append(
                {
                    "id": row["id"],
                    "status": "RETRY",
                    "error": error_text,
                }
            )

    db.commit()

    return results