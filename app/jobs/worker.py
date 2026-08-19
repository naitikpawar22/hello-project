import time
import logging

from app import create_app
from app.jobs.exam_start import process_exam_start_emails
from app.email.service import process_pending


logging.basicConfig(
    level=logging.INFO,
)


def run_worker():
    app = create_app()

    logging.info("ExamForge background worker started")

    while True:
        try:
            with app.app_context():

                # 1. Find exams that have started
                queued = process_exam_start_emails()

                if queued:
                    logging.info(
                        "Queued %s exam-start emails",
                        len(queued),
                    )

                # 2. Actually send pending emails through SMTP
                results = process_pending()

                if results:
                    logging.info(
                        "Processed %s email jobs",
                        len(results),
                    )

        except Exception:
            logging.exception(
                "Background worker error"
            )

        # Check every 60 seconds
        time.sleep(60)


if __name__ == "__main__":
    run_worker()