import logging
import os
from pathlib import Path

from dotenv import load_dotenv
from flask import Flask, jsonify, render_template

from app.cli import register_cli
from app.database import close_db, init_db


def create_app(test_config=None):
    load_dotenv()

    # ---------------------------------------------------------
    # Project paths
    # ---------------------------------------------------------
    # __file__ = ExamForge/app/__init__.py
    # parent      = ExamForge/app
    # parent.parent = ExamForge
    BASE_DIR = Path(__file__).resolve().parent.parent

    TEMPLATE_DIR = BASE_DIR / "templates"
    STATIC_DIR = BASE_DIR / "static"
    UPLOAD_DIR = BASE_DIR / "uploads"

    # ---------------------------------------------------------
    # Flask application
    # ---------------------------------------------------------
    app = Flask(
        __name__,
        instance_relative_config=True,
        template_folder=str(TEMPLATE_DIR),
        static_folder=str(STATIC_DIR),
    )

    # ---------------------------------------------------------
    # Configuration
    # ---------------------------------------------------------
    app.config.from_mapping(
        SECRET_KEY=os.getenv(
            "EXAMFORGE_SECRET_KEY",
            "dev-only-change-me",
        ),
        MAX_UPLOAD_BYTES=(
            int(
                os.getenv(
                    "EXAMFORGE_MAX_UPLOAD_MB",
                    "25",
                )
            )
            * 1024
            * 1024
        ),
        UPLOAD_DIR=str(UPLOAD_DIR),

        # Session security
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=(
            os.getenv(
                "EXAMFORGE_SECURE_COOKIE",
                "0",
            )
            == "1"
        ),

        # Application settings
        TIMEZONE=os.getenv(
            "EXAMFORGE_TIMEZONE",
            "Asia/Kolkata",
        ),
        JSON_SORT_KEYS=False,
    )

    # ---------------------------------------------------------
    # Test configuration override
    # ---------------------------------------------------------
    if test_config is not None:
        app.config.update(test_config)

    # ---------------------------------------------------------
    # Required directories
    # ---------------------------------------------------------
    Path(app.instance_path).mkdir(
        parents=True,
        exist_ok=True,
    )

    TEMPLATE_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    STATIC_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    UPLOAD_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    # ---------------------------------------------------------
    # Database lifecycle
    # ---------------------------------------------------------
    app.teardown_appcontext(close_db)

    with app.app_context():
        init_db()

    # ---------------------------------------------------------
    # Register Flask CLI commands
    # IMPORTANT:
    # app must already exist before calling register_cli(app)
    # ---------------------------------------------------------
    register_cli(app)

    # ---------------------------------------------------------
    # Import blueprints
    # ---------------------------------------------------------
    from app.auth.routes import bp as auth_bp
    from app.students.routes import bp as students_bp
    from app.questions.routes import bp as question_banks_bp
    from app.questions.question_routes import bp as questions_bp
    from app.exams.routes import bp as exams_bp
    from app.scheduling.routes import bp as scheduling_bp
    from app.invitations.routes import bp as invitations_bp
    from app.attempts.routes import bp as attempts_bp
    from app.results.routes import bp as results_bp
    from app.dashboard import bp as dashboard_bp

    # ---------------------------------------------------------
    # Register blueprints
    # ---------------------------------------------------------
    app.register_blueprint(auth_bp)
    app.register_blueprint(students_bp)
    app.register_blueprint(question_banks_bp)
    app.register_blueprint(questions_bp)
    app.register_blueprint(exams_bp)
    app.register_blueprint(scheduling_bp)
    app.register_blueprint(invitations_bp)
    app.register_blueprint(attempts_bp)
    app.register_blueprint(results_bp)
    app.register_blueprint(dashboard_bp)

    # ---------------------------------------------------------
    # Health endpoint
    # ---------------------------------------------------------
    @app.get("/api/health")
    def health():
        return jsonify(
            status="ok",
            service="ExamForge",
        )

    # ---------------------------------------------------------
    # Frontend
    # ---------------------------------------------------------
    @app.get("/")
    def home():
        return render_template("login.html")

    @app.get("/admin/<page>")
    def admin_page(page):
        allowed_pages = {
            "dashboard",
            "students",
            "question-banks",
            "question-bank-detail",
            "exam-builder",
            "blank-exam-builder",
            "scheduling",
            "invitations",
            "results",
        }

        if page not in allowed_pages:
            return jsonify(
                error="Page not found",
            ), 404

        return render_template(
            f"{page}.html",
        )

    @app.get("/student/exam/<token>")
    def student_exam_page(token):
        return render_template(
            "student-exam.html",
            token=token,
        )

    @app.get("/student/result/<rid>")
    def student_result_page(rid):
        return render_template(
            "student-result.html",
            result_id=rid,
        )

    @app.get("/admin/results/<rid>")
    def admin_result_page(rid):
        return render_template(
            "student-result.html",
            result_id=rid,
        )

    # ---------------------------------------------------------
    # API error handlers
    # ---------------------------------------------------------
    @app.errorhandler(400)
    def bad_request(_error):
        return jsonify(
            error="Bad request",
        ), 400

    @app.errorhandler(401)
    def unauthorized(_error):
        return jsonify(
            error="Authentication required",
        ), 401

    @app.errorhandler(403)
    def forbidden(_error):
        return jsonify(
            error="Forbidden",
        ), 403

    @app.errorhandler(404)
    def not_found(_error):
        return jsonify(
            error="Not found",
        ), 404

    @app.errorhandler(409)
    def conflict(_error):
        return jsonify(
            error="Conflict",
        ), 409

    @app.errorhandler(422)
    def unprocessable(_error):
        return jsonify(
            error="Validation error",
        ), 422

    @app.errorhandler(500)
    def internal_server_error(_error):
        logging.exception(
            "Internal ExamForge server error"
        )

        return jsonify(
            error="Internal server error",
        ), 500

    # Catch unexpected exceptions without exposing
    # Python stack traces to normal users.
    @app.errorhandler(Exception)
    def internal_exception(error):
        logging.exception(
            "Unhandled ExamForge error",
            exc_info=error,
        )

        return jsonify(
            error="Internal server error",
        ), 500

    return app