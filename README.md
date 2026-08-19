# ExamForge

ExamForge is a Flask + SQLite online examination management platform with admin/teacher workflows, student invitations, secure token access, question-bank importing, server-side evaluation, result cards, audit logs, and database-backed email jobs.

## Features

- Admin bootstrap, session authentication, Werkzeug password hashing.
- Teacher role with creator-scoped access.
- Real-time dashboard metrics from SQLite.
- Student CRUD, activation/deactivation, CSV bulk import.
- Question-bank imports from PDF, XML, HTML, DOCX, XLSX/XLSM, and CSV.
- MCQ/MSQ with exact-set evaluation and negative marking.
- Normal and blank exam builders.
- Exam scheduling with timezone-aware Asia/Kolkata default.
- Secure invitation tokens with expiry/status tracking.
- Distraction-free student exam UI, server-time timer enforcement, fullscreen and browser event logging.
- Automatic evaluation, topic performance, result review, PDF result cards.
- SMTP email queue with graceful disabled fallback when SMTP is not configured.
- Audit logging and API validation/error handling.

## Requirements

Python 3.11+.

## Installation

```bash
cd ExamForge
python -m venv .venv
# Windows
.venv\\Scripts\\activate
# macOS/Linux
source .venv/bin/activate
pip install -r requirements.txt
copy .env.example .env   # Windows
# or: cp .env.example .env
```

Set a strong `EXAMFORGE_SECRET_KEY` in `.env`. `EXAMFORGE_SECURE_COOKIE=1` should only be used behind HTTPS.

## Database initialization

The SQLite database and all tables are created automatically when the application starts. The file is `instance/examforge.db`.

You can also force initialization with:

```bash
python -c "from run import app; from app.database import init_db; ctx=app.app_context(); ctx.push(); init_db(); print('Database initialized')"
```

## First admin

Preferred CLI bootstrap:

```bash
flask --app run.py create-admin
```

There is also a one-time JSON bootstrap endpoint:

```http
POST /api/auth/bootstrap
Content-Type: application/json

{"name":"Admin","email":"admin@example.com","password":"change-me-123"}
```

Once any admin exists, the bootstrap endpoint refuses to create more admins.

## Running

```bash
python run.py
```

Default URL: `http://127.0.0.1:5000/`

Admin/teacher login URL: `http://127.0.0.1:5000/`

Student invitation URL format:
`http://127.0.0.1:5000/student/exam/<secure-token>`

## Teacher

Create a teacher from the CLI:

```bash
flask --app run.py create-teacher
```

Teachers can log in through the same login screen and can manage the exams/question banks they created.

## SMTP setup

Configure the following in `.env`:

```text
SMTP_HOST=smtp.example.com
SMTP_PORT=587
SMTP_USERNAME=user@example.com
SMTP_PASSWORD=secret
SMTP_FROM=ExamForge <user@example.com>
SMTP_USE_TLS=1
```

Email creation is database-backed. When SMTP is not configured, jobs are marked `DISABLED` instead of pretending to send messages.

Process jobs with:

```bash
flask --app run.py process-email-jobs
```

Run this command from cron/Task Scheduler in production.

## CSV formats

### Students

```csv
name,email,student_code,password
Aarav Sharma,aarav@example.com,EX1001,
Diya Patil,diya@example.com,EX1002,
```

### Questions

```csv
question,option_a,option_b,option_c,option_d,answer,type,marks,negative_marks,topic,explanation
What is 2+2?,3,4,5,6,B,MCQ,2,0.5,Math,Two plus two equals four.
```

Common question headers supported include `question`, `question_text`, `option_a` through `option_d`, `answer`, `correct_answer`, `type`, `question_type`, `marks`, `negative_marks`, `topic`, `category`, `explanation`, and `solution`.

Answers can use option letters such as `A` or `A,C`, or one-based/zero-based indexes where they map to valid options. Imported records with unsafe answer/type/option structure are marked for review rather than given a silently invented answer.

## Exam workflow

1. Create an admin.
2. Register/import students.
3. Import a question bank or create a blank exam.
4. Review imported questions.
5. Build and configure an exam.
6. Publish and schedule it.
7. Generate single or bulk invitations.
8. Students open secure token links.
9. The server records the attempt start time and enforces the duration.
10. Answers are stored server-side.
11. Submission is evaluated with MCQ/MSQ exact matching, marks, and negative marks.
12. A result is created, with topic performance and question review.
13. The result card can be downloaded as PDF.
14. A result email job is queued and can be processed by the SMTP worker command.

## Testing

```bash
pytest -q
```

The test suite covers authentication, protected endpoints, student CSV import, MCQ/MSQ evaluation, and scoring.

## Production notes

- Use HTTPS and `EXAMFORGE_SECURE_COOKIE=1`.
- Replace the development secret key with a long random value.
- Put the app behind a production WSGI server and reverse proxy.
- Back up `instance/examforge.db` and uploaded source documents.
- Run the email job processor from a scheduler/worker.
- Browser security controls are only a deterrent. Server-side authorization, timing, attempt state, and evaluation are authoritative.
- For high-stakes examinations, consider network controls, managed devices, or third-party proctoring in addition to the browser controls implemented here.
