import os, json
from pathlib import Path
from flask import Blueprint, request, jsonify, current_app
from werkzeug.utils import secure_filename
from app.database import get_db
from app.questions.service import parse_file, import_bank, serialize_question
from app.utils.security import admin_or_teacher_required, admin_required
from app.utils.audit import audit
from app.utils.helpers import now_iso

bp=Blueprint("questions",__name__,url_prefix="/api/question-banks")
ALLOWED={"pdf","xml","html","htm","docx","xlsx","xlsm","csv"}

def row_bank(row): return dict(row) if row else None

@bp.get("")
@admin_or_teacher_required
def banks(actor):
    rows=get_db().execute("SELECT qb.*,COUNT(q.id) question_count FROM question_banks qb LEFT JOIN questions q ON q.bank_id=qb.id GROUP BY qb.id ORDER BY qb.created_at DESC").fetchall()
    if actor["role"]=="teacher": rows=[r for r in rows if r["creator_id"]==actor["id"] or r["creator_role"]=="admin"]
    return jsonify(question_banks=[dict(r) for r in rows])

@bp.post("/import")
@admin_or_teacher_required
def import_bank_route(actor):
    f=request.files.get("file"); name=(request.form.get("name") or "").strip()
    if not f or not name: return jsonify(error="name and file are required"),400
    ext=Path(f.filename or "").suffix.lower().lstrip(".")
    if ext not in ALLOWED: return jsonify(error="Unsupported file type"),422
    max_bytes=current_app.config["MAX_UPLOAD_BYTES"]
    data=f.read(max_bytes+1)
    if len(data)>max_bytes: return jsonify(error="Uploaded file exceeds size limit"),413
    fname=secure_filename(f.filename) or f"upload.{ext}"
    server=f"{os.urandom(16).hex()}_{fname}"; path=Path(current_app.config["UPLOAD_DIR"])/server; path.write_bytes(data)
    try:
        questions=parse_file(path,ext)
        if not questions: return jsonify(error="No questions could be parsed safely"),422
        bid=import_bank(name,request.form.get("description","") ,server,ext,actor,questions)
    except Exception as e:
        path.unlink(missing_ok=True)
        return jsonify(error=f"Could not parse file: {e}"),422
    review=sum(1 for q in questions if q.get("needs_review"))
    audit(actor,"question_bank_imported","question_banks",bid,{"questions":len(questions),"needs_review":review})
    return jsonify(id=bid,imported=len(questions),needs_review=review),201

@bp.get("/<bid>")
@admin_or_teacher_required
def bank_detail(bid,actor):
    db=get_db(); bank=db.execute("SELECT * FROM question_banks WHERE id=?",(bid,)).fetchone()
    if not bank: return jsonify(error="Question bank not found"),404
    rows=db.execute("SELECT * FROM questions WHERE bank_id=? ORDER BY question_order",(bid,)).fetchall()
    return jsonify(question_bank={**dict(bank),"questions":[serialize_question(r) for r in rows]})

@bp.put("/<bid>")
@admin_or_teacher_required
def update_bank(bid,actor):
    data=request.get_json(silent=True) or {}; db=get_db()
    row=db.execute("SELECT * FROM question_banks WHERE id=?",(bid,)).fetchone()
    if not row: return jsonify(error="Question bank not found"),404
    if actor["role"]!="admin" and row["creator_id"]!=actor["id"]: return jsonify(error="Not authorized"),403
    db.execute("UPDATE question_banks SET name=?,description=?,updated_at=? WHERE id=?",(data.get("name",row["name"]),data.get("description",row["description"]),now_iso(),bid)); db.commit()
    return jsonify(message="Question bank updated")

@bp.delete("/<bid>")
@admin_or_teacher_required
def delete_bank(bid,actor):
    db=get_db(); row=db.execute("SELECT * FROM question_banks WHERE id=?",(bid,)).fetchone()
    if not row: return jsonify(error="Question bank not found"),404
    if actor["role"]!="admin" and row["creator_id"]!=actor["id"]: return jsonify(error="Not authorized"),403
    if db.execute("SELECT 1 FROM exam_questions eq JOIN questions q ON q.id=eq.question_id WHERE q.bank_id=? LIMIT 1",(bid,)).fetchone(): return jsonify(error="Question bank has questions used by an exam"),409
    db.execute("DELETE FROM question_banks WHERE id=?",(bid,)); db.commit(); audit(actor,"question_bank_deleted","question_banks",bid)
    return jsonify(message="Question bank deleted")

@bp.put("/../questions/<qid>")
def _unused(): return jsonify(error="Not found"),404


