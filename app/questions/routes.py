import os, json
from pathlib import Path
from flask import Blueprint, request, jsonify, current_app
from werkzeug.utils import secure_filename
from app.database import get_db
from app.questions.service import parse_file, import_bank, serialize_question
from app.utils.security import admin_or_teacher_required, admin_required
from app.utils.audit import audit
from app.utils.helpers import now_iso, get_shareable_url

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

@bp.post("/<bid>/create-exam")
@admin_or_teacher_required
def create_exam_from_bank(bid, actor):
    from app.exams.service import create_exam, get_exam_public_data
    db = get_db()
    bank = db.execute("SELECT * FROM question_banks WHERE id=?", (bid,)).fetchone()
    if not bank: return jsonify(error="Question bank not found"), 404
    
    q_rows = db.execute("SELECT id FROM questions WHERE bank_id=? ORDER BY question_order", (bid,)).fetchall()
    if not q_rows: return jsonify(error="Question bank contains no questions"), 422
    
    qids = [r["id"] for r in q_rows]
    data = request.get_json(silent=True) or {}
    
    title = (data.get("title") or f"{bank['name']} Exam").strip()
    duration = int(data.get("duration_minutes", 60) or 60)
    pass_pct = int(data.get("pass_percentage", 40) or 40)
    access_mode = data.get("access_mode", "PUBLIC")
    
    payload = {
        "title": title,
        "description": data.get("description") or bank["description"] or "",
        "duration_minutes": duration,
        "pass_percentage": pass_pct,
        "access_mode": access_mode,
        "question_ids": qids,
        "randomize_questions": bool(data.get("randomize_questions", False)),
        "randomize_options": bool(data.get("randomize_options", False)),
    }
    
    try:
        eid = create_exam(payload, actor)
        db.execute("UPDATE exams SET status='PUBLISHED' WHERE id=?", (eid,))
        db.commit()
        exam_data = get_exam_public_data(eid)
    except Exception as e:
        return jsonify(error=str(e)), 422
        
    audit(actor, "exam_created_from_bank", "exams", eid, {"bank_id": bid})
    exam_link = get_shareable_url(request, f"exam/{exam_data['exam_code']}")
    return jsonify(
        id=eid,
        title=exam_data["title"],
        exam_code=exam_data["exam_code"],
        exam_link=exam_link,
        message=f"Exam '{exam_data['title']}' created successfully from Question Bank!"
    ), 201

@bp.post("/<bid>/questions")
@admin_or_teacher_required
def add_question_to_bank(bid, actor):
    from app.questions.question_routes import validate_question
    from app.questions.parsers.common import normalize_answer, normalize_type
    from app.utils.helpers import new_id
    data = request.get_json(silent=True) or {}
    err = validate_question(data)
    if err: return jsonify(error=err), 422
    db = get_db()
    bank = db.execute("SELECT * FROM question_banks WHERE id=?", (bid,)).fetchone()
    if not bank: return jsonify(error="Question bank not found"), 404
    if actor["role"] != "admin" and bank["creator_id"] != actor["id"]: return jsonify(error="Not authorized"), 403
    
    qid = new_id()
    opts = [str(x).strip() for x in (data.get("options") or []) if str(x).strip()]
    typ = normalize_type(data.get("type"))
    correct = normalize_answer(data.get("correct"), len(opts))
    ts = now_iso()
    
    count = db.execute("SELECT COUNT(*) FROM questions WHERE bank_id=?", (bid,)).fetchone()[0]
    db.execute("INSERT INTO questions (id, bank_id, text, type, marks, negative_marks, topic, explanation, question_order, needs_review, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?,0,?,?)",
               (qid, bid, data["text"].strip(), typ, float(data.get("marks", 1)), float(data.get("negative_marks", 0)), data.get("topic", "") or "", data.get("explanation", "") or "", count + 1, ts, ts))
    for i, opt in enumerate(opts):
        db.execute("INSERT INTO question_options (id, question_id, option_index, option_text, is_correct) VALUES (?,?,?,?,?)",
                   (new_id(), qid, i, opt, 1 if i in correct else 0))
    db.commit()
    audit(actor, "question_added", "questions", qid, {"bank_id": bid})
    return jsonify(message="Question added successfully", id=qid), 201

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


