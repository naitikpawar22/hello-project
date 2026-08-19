from flask import Blueprint,request,jsonify
from app.scheduling.service import schedule_exam,exam_window
from app.utils.security import admin_or_teacher_required
from app.utils.audit import audit
bp=Blueprint("scheduling",__name__,url_prefix="/api/exams")
@bp.post("/<eid>/schedule")
@admin_or_teacher_required
def schedule(eid,actor):
    try: schedule_exam(eid,request.get_json(silent=True) or {},actor)
    except LookupError as e: return jsonify(error=str(e)),404
    except PermissionError as e: return jsonify(error=str(e)),403
    except ValueError as e: return jsonify(error=str(e)),422
    audit(actor,"exam_scheduled","exams",eid); return jsonify(message="Exam scheduled",schedule=exam_window(eid))
@bp.put("/<eid>/schedule")
@admin_or_teacher_required
def reschedule(eid,actor): return schedule(eid,actor)
@bp.get("/<eid>/schedule")
@admin_or_teacher_required
def schedule_status(eid,actor):
    s=exam_window(eid); return (jsonify(schedule=s),200) if s else (jsonify(schedule=None),404)
