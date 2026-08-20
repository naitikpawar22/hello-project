import json
from flask import Blueprint,request,jsonify
from app.database import get_db
from app.exams.service import create_exam, update_exam, get_exam
from app.utils.security import admin_or_teacher_required
from app.utils.audit import audit
from app.utils.helpers import now_iso, get_shareable_url

bp=Blueprint("exams",__name__,url_prefix="/api/exams")

from app.exams.service import (
    create_exam,
    update_exam,
    get_exam,
    get_exam_public_data,
)

@bp.get("")
@admin_or_teacher_required
def list_exams(actor):
    db=get_db(); rows=db.execute("SELECT e.*,COUNT(eq.id) question_count FROM exams e LEFT JOIN exam_questions eq ON eq.exam_id=e.id GROUP BY e.id ORDER BY e.created_at DESC").fetchall()
    if actor["role"]!="admin": rows=[r for r in rows if r["creator_id"]==actor["id"]]
    exams = []
    for r in rows:
        d = dict(r)
        d["exam_link"] = get_shareable_url(request, f"exam/{d['exam_code']}") if d.get("exam_code") else ""
        exams.append(d)
    return jsonify(exams=exams)

@bp.post("")
@admin_or_teacher_required
def add_exam(actor):
    try:
        data = request.get_json(silent=True) or {}
        eid = create_exam(data, actor)
        db = get_db()
        db.execute("UPDATE exams SET status='PUBLISHED' WHERE id=?", (eid,))
        db.commit()
    except ValueError as e:
        return jsonify(error=str(e)), 422

    exam = get_exam_public_data(eid)
    if not exam:
        return jsonify(error="Exam was created but could not be loaded"), 500

    audit(actor, "exam_created", "exams", eid, {"exam_code": exam["exam_code"], "access_mode": exam["access_mode"]})
    exam_link = get_shareable_url(request, f"exam/{exam['exam_code']}")
    return jsonify(
        id=eid,
        title=exam["title"],
        exam_code=exam["exam_code"],
        public_token=exam["public_token"],
        access_mode=exam["access_mode"],
        exam_link=exam_link,
    ), 201

@bp.get("/<eid>")
@admin_or_teacher_required
def exam_detail(eid,actor):
    e=get_exam(eid)
    if not e: return jsonify(error="Exam not found"),404
    if actor["role"]!="admin" and e["creator_id"]!=actor["id"]: return jsonify(error="Not authorized"),403
    e["exam_link"] = get_shareable_url(request, f"exam/{e['exam_code']}") if e.get("exam_code") else ""
    return jsonify(exam=e)


@bp.put("/<eid>")
@admin_or_teacher_required
def edit_exam(eid,actor):
    try: update_exam(eid,request.get_json(silent=True) or {},actor)
    except LookupError as e: return jsonify(error=str(e)),404
    except PermissionError as e: return jsonify(error=str(e)),403
    except ValueError as e: return jsonify(error=str(e)),422
    audit(actor,"exam_updated","exams",eid); return jsonify(message="Exam updated")

@bp.post("/<eid>/publish")
@admin_or_teacher_required
def publish(eid,actor):
    db=get_db(); e=db.execute("SELECT * FROM exams WHERE id=?",(eid,)).fetchone()
    if not e: return jsonify(error="Exam not found"),404
    if actor["role"]!="admin" and e["creator_id"]!=actor["id"]: return jsonify(error="Not authorized"),403
    if db.execute("SELECT 1 FROM exam_questions WHERE exam_id=? LIMIT 1",(eid,)).fetchone() is None: return jsonify(error="Exam must contain at least one question"),422
    status="PUBLISHED"; sched=db.execute("SELECT start_at,end_at FROM exam_schedules WHERE exam_id=?",(eid,)).fetchone()
    if sched: status="SCHEDULED"
    db.execute("UPDATE exams SET status=?,updated_at=? WHERE id=?",(status,now_iso(),eid)); db.commit(); audit(actor,"exam_published","exams",eid); return jsonify(status=status)

@bp.post("/blank")
@admin_or_teacher_required
def blank_exam(actor):
    from app.questions.service import import_bank
    from app.questions.parsers.common import normalize_answer, normalize_type
    data=request.get_json(silent=True) or {}
    questions=data.get("questions") or []
    if not questions: return jsonify(error="At least one question is required"),422
    normalized=[]
    for q in questions:
        opts=[str(x).strip() for x in (q.get("options") or []) if str(x).strip()]
        correct=normalize_answer(q.get("correct"), len(opts))
        typ=normalize_type(q.get("type"))
        if not 2<=len(opts)<=4: return jsonify(error="Each question needs 2-4 options"),422
        if not correct or (typ=="MCQ" and len(correct)!=1): return jsonify(error=f"Invalid correct answer for question: '{q.get('text','')}'"),422
        normalized.append({"text":q.get("text","").strip(),"type":typ,"options":opts,"correct":correct,"marks":float(q.get("marks",1) or 1),"negative_marks":float(q.get("negative",0) or 0),"topic":q.get("topic","") or "","explanation":q.get("explanation","") or "","needs_review":0})
    if any(not q["text"] or q["marks"]<0 or q["negative_marks"]<0 for q in normalized): return jsonify(error="Question text and non-negative marks are required"),422
    bid=import_bank(f"{data.get('title','Blank Exam')} Question Bank",data.get("description","") or "","manual","manual",actor,normalized)
    qids=[r["id"] for r in get_db().execute("SELECT id FROM questions WHERE bank_id=? ORDER BY question_order",(bid,)).fetchall()]
    payload={**data,"question_ids":qids,"access_mode":data.get("access_mode","PUBLIC")}
    try:
        eid=create_exam(payload,actor)
        db=get_db()
        db.execute("UPDATE exams SET status='PUBLISHED' WHERE id=?",(eid,))
        db.commit()
        exam_data = get_exam_public_data(eid)
    except Exception as e: return jsonify(error=str(e)),422
    audit(actor,"blank_exam_created","exams",eid,{"bank_id":bid})
    exam_link = f"{request.host_url}exam/{exam_data['exam_code']}"
    return jsonify(id=eid,question_bank_id=bid,exam_code=exam_data["exam_code"],exam_link=exam_link,title=data.get("title")),201

@bp.post("/<eid>/toggle-status")
@admin_or_teacher_required
def toggle_status(eid, actor):
    db = get_db()
    e = db.execute("SELECT * FROM exams WHERE id=?", (eid,)).fetchone()
    if not e: return jsonify(error="Exam not found"), 404
    if actor["role"] != "admin" and e["creator_id"] != actor["id"]: return jsonify(error="Not authorized"), 403
    curr = (e["status"] or "").upper()
    new_status = "DRAFT" if curr in {"PUBLISHED", "LIVE", "SCHEDULED"} else "PUBLISHED"
    db.execute("UPDATE exams SET status=?, updated_at=? WHERE id=?", (new_status, now_iso(), eid))
    db.commit()
    audit(actor, "exam_status_toggled", "exams", eid, {"new_status": new_status})
    return jsonify(status=new_status, active=(new_status == "PUBLISHED"))

@bp.delete("/<eid>")
@admin_or_teacher_required
def delete_exam(eid, actor):
    db = get_db()
    e = db.execute("SELECT * FROM exams WHERE id=?", (eid,)).fetchone()
    if not e:
        return jsonify(error="Exam not found"), 404
    if actor["role"] != "admin" and e["creator_id"] != actor["id"]:
        return jsonify(error="Not authorized"), 403

    attempt_ids = [r["id"] for r in db.execute("SELECT id FROM attempts WHERE exam_id=?", (eid,)).fetchall()]
    if attempt_ids:
        placeholders = ",".join("?" for _ in attempt_ids)
        db.execute(f"DELETE FROM attempt_answers WHERE attempt_id IN ({placeholders})", attempt_ids)
        db.execute(f"DELETE FROM security_events WHERE attempt_id IN ({placeholders})", attempt_ids)
        db.execute(f"DELETE FROM results WHERE attempt_id IN ({placeholders})", attempt_ids)
        db.execute("DELETE FROM attempts WHERE exam_id=?", (eid,))

    db.execute("DELETE FROM exam_questions WHERE exam_id=?", (eid,))
    db.execute("DELETE FROM exam_schedules WHERE exam_id=?", (eid,))
    db.execute("DELETE FROM exam_invitations WHERE exam_id=?", (eid,))
    db.execute("DELETE FROM exams WHERE id=?", (eid,))
    db.commit()

    audit(actor, "exam_deleted", "exams", eid, {"title": e["title"]})
    return jsonify(message=f"Exam '{e['title']}' deleted successfully.")
