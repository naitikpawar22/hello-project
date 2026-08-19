import json
from flask import Blueprint,request,jsonify
from app.database import get_db
from app.exams.service import create_exam, update_exam, get_exam
from app.utils.security import admin_or_teacher_required
from app.utils.audit import audit
from app.utils.helpers import now_iso

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
    return jsonify(exams=[dict(r) for r in rows])

@bp.post("")
@admin_or_teacher_required
def add_exam(actor):
    try:
        data = request.get_json(silent=True) or {}

        eid = create_exam(
            data,
            actor,
        )

    except ValueError as e:
        return jsonify(
            error=str(e)
        ), 422

    exam = get_exam_public_data(eid)

    if not exam:
        return jsonify(
            error="Exam was created but could not be loaded"
        ), 500

    audit(
        actor,
        "exam_created",
        "exams",
        eid,
        {
            "exam_code": exam["exam_code"],
            "access_mode": exam["access_mode"],
        },
    )

    return jsonify(
        id=eid,
        title=exam["title"],
        exam_code=exam["exam_code"],
        public_token=exam["public_token"],
        access_mode=exam["access_mode"],
    ), 201

@bp.get("/<eid>")
@admin_or_teacher_required
def exam_detail(eid,actor):
    e=get_exam(eid)
    if not e: return jsonify(error="Exam not found"),404
    if actor["role"]!="admin" and e["creator_id"]!=actor["id"]: return jsonify(error="Not authorized"),403
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
    data=request.get_json(silent=True) or {}
    questions=data.get("questions") or []
    if not questions: return jsonify(error="At least one question is required"),422
    normalized=[]
    for q in questions:
        opts=[str(x).strip() for x in (q.get("options") or []) if str(x).strip()]
        try: correct=[int(x.strip()) for x in str(q.get("correct","")).split(",") if x.strip()!='']
        except ValueError: return jsonify(error="Correct indexes must be numeric"),422
        typ=(q.get("type") or "MCQ").upper()
        if typ not in {"MCQ","MSQ"} or not 2<=len(opts)<=4: return jsonify(error="Each question needs type MCQ/MSQ and 2-4 options"),422
        if any(i<0 or i>=len(opts) for i in correct) or not correct or (typ=="MCQ" and len(correct)!=1): return jsonify(error="Invalid correct answer configuration"),422
        normalized.append({"text":q.get("text","").strip(),"type":typ,"options":opts,"correct":correct,"marks":float(q.get("marks",1) or 1),"negative_marks":float(q.get("negative",0) or 0),"topic":q.get("topic","") or "","explanation":q.get("explanation","") or "","needs_review":0})
    if any(not q["text"] or q["marks"]<0 or q["negative_marks"]<0 for q in normalized): return jsonify(error="Question text and non-negative marks are required"),422
    bid=import_bank(f"{data.get('title','Blank Exam')} Question Bank",data.get("description","") or "","manual","manual",actor,normalized)
    # import_bank returns a bank; create an exam from all its questions.
    qids=[r["id"] for r in get_db().execute("SELECT id FROM questions WHERE bank_id=? ORDER BY question_order",(bid,)).fetchall()]
    payload={**data,"question_ids":qids}
    try: eid=create_exam(payload,actor)
    except Exception as e: return jsonify(error=str(e)),422
    audit(actor,"blank_exam_created","exams",eid,{"bank_id":bid})
    return jsonify(id=eid,question_bank_id=bid),201

@bp.delete("/<eid>")
@admin_or_teacher_required
def delete_exam(eid,actor):
    db=get_db(); e=db.execute("SELECT * FROM exams WHERE id=?",(eid,)).fetchone()
    if not e: return jsonify(error="Exam not found"),404
    if actor["role"]!="admin" and e["creator_id"]!=actor["id"]: return jsonify(error="Not authorized"),403
    if db.execute("SELECT 1 FROM attempts WHERE exam_id=? LIMIT 1",(eid,)).fetchone(): return jsonify(error="Exam has attempts and cannot be deleted"),409
    db.execute("DELETE FROM exams WHERE id=?",(eid,)); db.commit(); return jsonify(message="Exam deleted")
