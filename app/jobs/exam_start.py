from datetime import datetime, timezone

from app.database import get_db
from app.email.service import enqueue_email
from app.utils.helpers import now_iso


def process_exam_start_emails():

    db = get_db()

    now = datetime.now(timezone.utc).isoformat()

    exams = db.execute(
        """
        SELECT
            e.id,
            e.title,
            e.access_mode,
            s.start_at,
            s.end_at
        FROM exams e
        JOIN exam_schedules s
            ON s.exam_id = e.id
        WHERE s.start_at <= ?
          AND s.end_at >= ?
          AND e.status = 'SCHEDULED'
        """,
        (now, now),
    ).fetchall()

    queued = 0

    for exam in exams:

        invitations = db.execute(
            """
            SELECT
                id,
                email
            FROM exam_invitations
            WHERE exam_id = ?
              AND status NOT IN ('CANCELLED', 'EXPIRED')
              AND start_email_sent_at IS NULL
            """,
            (exam["id"],),
        ).fetchall()

        for invitation in invitations:

            subject = f"Exam Started - {exam['title']}"

            body = (
                "Your exam has started.\n\n"
                f"Exam: {exam['title']}\n\n"
                "Please open your ExamForge invitation link "
                "to start the exam.\n\n"
                "Good luck!\n\n"
                "ExamForge"
            )

            try:

                enqueue_email(
                    "EXAM_STARTED",
                    invitation["email"],
                    subject,
                    body,
                    None,
                )

                db.execute(
                    """
                    UPDATE exam_invitations
                    SET start_email_sent_at = ?
                    WHERE id = ?
                      AND start_email_sent_at IS NULL
                    """,
                    (
                        now_iso(),
                        invitation["id"],
                    ),
                )

                queued += 1

                print(
                    f"Exam start email queued: "
                    f"{invitation['email']}"
                )

            except Exception as e:

                print(
                    f"Exam start email failed "
                    f"for {invitation['email']}: {e}"
                )

    db.commit()

    return queued