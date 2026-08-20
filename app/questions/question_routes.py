from flask import Blueprint,request,jsonify
from app.database import get_db
from app.utils.security import admin_or_teacher_required
from app.utils.audit import audit
from app.utils.helpers import now_iso
from app.questions.service import serialize_question
bp=Blueprint("question_items",__name__,url_prefix="/api/questions")

<<<<<<< HEAD
from app.questions.parsers.common import normalize_answer, normalize_type

def validate_question(data):
    text=(data.get("text") or "").strip()
    typ=normalize_type(data.get("type"))
    opts=[str(x).strip() for x in (data.get("options") or []) if str(x).strip()]
    if not text: return "Question text is required"
    if not 2<=len(opts)<=4: return "Question must have 2-4 options"
    correct=normalize_answer(data.get("correct"), len(opts))
    if typ=="MCQ" and len(correct)!=1: return "MCQ requires exactly one correct option"
    if typ=="MSQ" and len(correct)<1: return "MSQ requires at least one correct option"
=======
def validate_question(data):
    text=(data.get("text") or "").strip(); typ=(data.get("type") or "MCQ").upper(); opts=data.get("options") or []
    if not text: return "Question text is required"
    if typ not in {"MCQ","MSQ"}: return "type must be MCQ or MSQ"
    if not 2<=len(opts)<=4: return "Question must have 2-4 options"
    correct=data.get("correct") or []
    if typ=="MCQ" and len(correct)!=1: return "MCQ requires exactly one correct option"
    if typ=="MSQ" and len(correct)<1: return "MSQ requires at least one correct option"
    if any(int(x)<0 or int(x)>=len(opts) for x in correct): return "Invalid correct option"
>>>>>>> 00cdc5ce5c2c164af42ff31e6595073d105d2b0b
    try:
        if float(data.get("marks",1))<0 or float(data.get("negative_marks",0))<0: return "Marks cannot be negative"
    except: return "Marks must be numeric"
    return None

@bp.put("/<qid>")
@admin_or_teacher_required
def update_question(qid,actor):
    data=request.get_json(silent=True) or {}; err=validate_question(data)
    if err: return jsonify(error=err),422
    db=get_db(); row=db.execute("SELECT * FROM questions WHERE id=?",(qid,)).fetchone()
    if not row: return jsonify(error="Question not found"),404
    bank=db.execute("SELECT * FROM question_banks WHERE id=?",(row["bank_id"],)).fetchone()
    if actor["role"]!="admin" and bank["creator_id"]!=actor["id"]: return jsonify(error="Not authorized"),403
<<<<<<< HEAD
    opts=[str(x).strip() for x in (data.get("options") or []) if str(x).strip()]
    typ=normalize_type(data.get("type"))
    correct=normalize_answer(data.get("correct"), len(opts))
    db.execute("UPDATE questions SET text=?,type=?,marks=?,negative_marks=?,topic=?,explanation=?,needs_review=0,updated_at=? WHERE id=?",
               (data["text"].strip(),typ,float(data.get("marks",1)),float(data.get("negative_marks",0)),data.get("topic","") or "",data.get("explanation","") or "",now_iso(),qid))
    db.execute("DELETE FROM question_options WHERE question_id=?",(qid,))
    for i,opt in enumerate(opts): db.execute("INSERT INTO question_options(id,question_id,option_index,option_text,is_correct) VALUES(?,?,?,?,?)",(str(i)+qid[:8],qid,i,opt,1 if i in correct else 0))
=======
    db.execute("UPDATE questions SET text=?,type=?,marks=?,negative_marks=?,topic=?,explanation=?,needs_review=0,updated_at=? WHERE id=?",
               (data["text"].strip(),data["type"].upper(),float(data.get("marks",1)),float(data.get("negative_marks",0)),data.get("topic","") or "",data.get("explanation","") or "",now_iso(),qid))
    db.execute("DELETE FROM question_options WHERE question_id=?",(qid,))
    for i,opt in enumerate(data["options"]): db.execute("INSERT INTO question_options(id,question_id,option_index,option_text,is_correct) VALUES(?,?,?,?,?)",(str(i)+qid[:8],qid,i,str(opt),1 if i in [int(x) for x in data["correct"]] else 0))
>>>>>>> 00cdc5ce5c2c164af42ff31e6595073d105d2b0b
    db.commit(); audit(actor,"question_updated","questions",qid); return jsonify(question=serialize_question(db.execute("SELECT * FROM questions WHERE id=?",(qid,)).fetchone()))

@bp.delete("/<qid>")
@admin_or_teacher_required
def delete_question(qid,actor):
    db=get_db(); row=db.execute("SELECT * FROM questions WHERE id=?",(qid,)).fetchone()
    if not row: return jsonify(error="Question not found"),404
    if actor["role"]!="admin" and not db.execute("SELECT 1 FROM question_banks WHERE id=? AND creator_id=?",(row["bank_id"],actor["id"])).fetchone(): return jsonify(error="Not authorized"),403
    if db.execute("SELECT 1 FROM exam_questions WHERE question_id=?",(qid,)).fetchone(): return jsonify(error="Question is used by an exam"),409
    db.execute("DELETE FROM questions WHERE id=?",(qid,)); db.commit(); audit(actor,"question_deleted","questions",qid); return jsonify(message="Question deleted")
