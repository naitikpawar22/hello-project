from pathlib import Path
import json
from flask import Blueprint, request, jsonify, send_file, current_app
from app.database import get_db
from app.results.service import result_detail
from app.results.pdf import generate_result_pdf
from app.utils.security import admin_or_teacher_required
from app.utils.helpers import new_id, now_iso

bp = Blueprint("results", __name__, url_prefix="/api/results")

@bp.get("")
@admin_or_teacher_required
def list_results(actor):
    db = get_db()
    sql = """
        SELECT r.id, r.score, r.max_marks, r.percentage, r.passed,
               r.correct_count, r.wrong_count, r.skipped_count, r.created_at,
               a.candidate_name, a.candidate_email, a.candidate_phone,
               a.candidate_department, a.candidate_division,
               a.status AS attempt_status, a.security_event_count,
               e.title AS exam_title
        FROM results r
        JOIN attempts a ON a.id = r.attempt_id
        JOIN exams e ON e.id = r.exam_id
        WHERE 1=1
    """
    p = []
    if actor["role"] != "admin":
        sql += " AND e.creator_id=?"
        p.append(actor["id"])
    rows = db.execute(sql + " ORDER BY r.created_at DESC", p).fetchall()
    return jsonify(results=[dict(r) for r in rows])

@bp.get("/<rid>")
@admin_or_teacher_required
def get_result(rid, actor):
    r = result_detail(rid)
    if not r:
        return jsonify(error="Result not found"), 404
    if actor["role"] != "admin" and get_db().execute("SELECT creator_id FROM exams WHERE id=?", (r["exam_id"],)).fetchone()["creator_id"] != actor["id"]:
        return jsonify(error="Not authorized"), 403
    return jsonify(result=r)

@bp.get("/<rid>/pdf")
@admin_or_teacher_required
def pdf(rid, actor):
    r = result_detail(rid)
    if not r:
        return jsonify(error="Result not found"), 404
    if actor["role"] != "admin" and get_db().execute("SELECT creator_id FROM exams WHERE id=?", (r["exam_id"],)).fetchone()["creator_id"] != actor["id"]:
        return jsonify(error="Not authorized"), 403
    path = Path(current_app.config["UPLOAD_DIR"]) / f"result_{rid}.pdf"
    generate_result_pdf(r, path)
    return send_file(path, as_attachment=True, download_name=f"ExamForge_Result_{rid}.pdf", mimetype="application/pdf")

@bp.get("/public/<rid>")
def public_result(rid):
    r = result_detail(rid)
    if not r:
        return jsonify(error="Result not found"), 404
    d = {k: v for k, v in r.items() if k not in {"details", "topic_performance", "attempt_id"}}
    return jsonify(result=d)

@bp.get("/public/<rid>/details")
def public_result_details(rid):
    r = result_detail(rid)
    if not r:
        return jsonify(error="Result not found"), 404
    return jsonify(result=r)

@bp.get("/public/<rid>/pdf")
def public_pdf(rid):
    r = result_detail(rid)
    if not r:
        return jsonify(error="Result not found"), 404
    path = Path(current_app.config["UPLOAD_DIR"]) / f"result_{rid}.pdf"
    generate_result_pdf(r, path)
    return send_file(path, as_attachment=True, download_name=f"ExamForge_Result_{rid}.pdf", mimetype="application/pdf")
