from datetime import datetime, timezone, timedelta

from app.database import get_db
<<<<<<< HEAD
from app.utils.helpers import new_id, now_iso, parse_iso
=======
from app.utils.helpers import new_id, now_iso
>>>>>>> 00cdc5ce5c2c164af42ff31e6595073d105d2b0b


# ExamForge default timezone: India (IST)
IST = timezone(timedelta(hours=5, minutes=30))


def parse_schedule(date_str, time_str):
    if not date_str:
        raise ValueError("Date is required")

    if not time_str:
        raise ValueError("Time is required")

    try:
        local_time = datetime.fromisoformat(
            f"{date_str}T{time_str}"
        )
    except ValueError:
        raise ValueError("Invalid date or time")

    # Treat entered time as IST
    local_time = local_time.replace(tzinfo=IST)

    # Store as UTC
    return local_time.astimezone(timezone.utc)


def schedule_exam(eid, data, actor):
    db = get_db()

    # --------------------------------------------------
    # Get exam
    # --------------------------------------------------
    exam = db.execute(
        "SELECT * FROM exams WHERE id=?",
        (eid,)
    ).fetchone()

    if not exam:
        raise LookupError("Exam not found")

    # --------------------------------------------------
    # Permission
    # --------------------------------------------------
    if actor["role"] != "admin":
        if exam["creator_id"] != actor["id"]:
            raise PermissionError("Not authorized")

    # --------------------------------------------------
    # Date + Time
    # --------------------------------------------------
    start = parse_schedule(
        data.get("date"),
        data.get("time")
    )

    # --------------------------------------------------
    # Duration
    # --------------------------------------------------
    duration = data.get("duration_minutes")

    if duration:
        try:
            duration = int(duration)
        except (TypeError, ValueError):
            raise ValueError("Invalid duration")
    else:
        duration = exam["duration_minutes"]

    if not duration or duration <= 0:
        raise ValueError("Exam duration must be greater than 0")

    # --------------------------------------------------
    # Calculate end time
    # --------------------------------------------------
    end = start + timedelta(minutes=duration)

    if end <= start:
        raise ValueError("Schedule end must be after start")

    # --------------------------------------------------
    # Current timestamp
    # --------------------------------------------------
    ts = now_iso()

    # --------------------------------------------------
    # Check existing schedule
    # --------------------------------------------------
    existing = db.execute(
        "SELECT id FROM exam_schedules WHERE exam_id=?",
        (eid,)
    ).fetchone()

    teacher_email = data.get("teacher_email") or None

    # --------------------------------------------------
    # Update existing schedule
    # --------------------------------------------------
    if existing:
        db.execute(
            """
            UPDATE exam_schedules
            SET
                start_at=?,
                end_at=?,
                timezone=?,
                teacher_email=?,
                updated_at=?
            WHERE exam_id=?
            """,
            (
                start.isoformat(),
                end.isoformat(),
                "IST",
                teacher_email,
                ts,
                eid
            )
        )

    # --------------------------------------------------
    # Create new schedule
    # --------------------------------------------------
    else:
        db.execute(
            """
            INSERT INTO exam_schedules
            (
                id,
                exam_id,
                start_at,
                end_at,
                timezone,
                teacher_email,
                created_at,
                updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                new_id(),
                eid,
                start.isoformat(),
                end.isoformat(),
                "IST",
                teacher_email,
                ts,
                ts
            )
        )

    # --------------------------------------------------
    # Update exam status
    # --------------------------------------------------
    db.execute(
        """
        UPDATE exams
        SET status='SCHEDULED',
            updated_at=?
        WHERE id=?
        """,
        (ts, eid)
    )

    db.commit()


def exam_window(eid):
    db = get_db()

    row = db.execute(
        """
        SELECT *
        FROM exam_schedules
        WHERE exam_id=?
        """,
        (eid,)
    ).fetchone()

    if not row:
        return None

    try:
<<<<<<< HEAD
        start = parse_iso(row["start_at"])
        end = parse_iso(row["end_at"])
=======
        start = datetime.fromisoformat(row["start_at"])
        end = datetime.fromisoformat(row["end_at"])
>>>>>>> 00cdc5ce5c2c164af42ff31e6595073d105d2b0b
    except (ValueError, TypeError):
        return None

    now = datetime.now(timezone.utc)

    if now < start:
        state = "upcoming"
    elif now <= end:
        state = "live"
    else:
        state = "closed"

    result = dict(row)

    result["start_at"] = start
    result["end_at"] = end
    result["state"] = state

    return result