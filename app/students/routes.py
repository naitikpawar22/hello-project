import csv, io
from flask import Blueprint, request, jsonify
from app.database import get_db
from app.students.service import create_student, update_student
from app.utils.security import admin_required, admin_or_teacher_required
from app.utils.audit import audit

bp=Blueprint("students",__name__,url_prefix="/api/students")

@bp.get("")
@admin_or_teacher_required
def list_students(actor):
    q=(request.args.get("q") or "").strip(); active=request.args.get("active")
    sql="SELECT id,name,email,student_code,active,created_at,updated_at FROM students WHERE 1=1"; p=[]
    if q: sql+=" AND (name LIKE ? OR email LIKE ? OR student_code LIKE ?)"; p += [f"%{q}%"]*3
    if active in ("0","1"): sql+=" AND active=?"; p.append(int(active))
    rows=get_db().execute(sql+" ORDER BY created_at DESC",p).fetchall()
    return jsonify(students=[dict(r) for r in rows])

@bp.post("")
@admin_required
def add_student(actor):
    try: sid=create_student(request.get_json(silent=True) or {})
    except ValueError as e: return jsonify(error=str(e)),422
    except Exception as e:
        if "UNIQUE" in str(e): return jsonify(error="Email or student code already exists"),409
        raise
    audit(actor,"student_created","students",sid)
    return jsonify(id=sid),201

@bp.get("/<sid>")
@admin_or_teacher_required
def get_student(sid,actor):
    row=get_db().execute("SELECT id,name,email,student_code,active,created_at,updated_at FROM students WHERE id=?",(sid,)).fetchone()
    return (jsonify(student=dict(row)),200) if row else (jsonify(error="Student not found"),404)

@bp.put("/<sid>")
@admin_required
def edit_student(sid,actor):
    try: update_student(sid,request.get_json(silent=True) or {})
    except LookupError as e: return jsonify(error=str(e)),404
    except ValueError as e: return jsonify(error=str(e)),422
    except Exception as e:
        if "UNIQUE" in str(e): return jsonify(error="Email or student code already exists"),409
        raise
    audit(actor,"student_updated","students",sid)
    return jsonify(message="Student updated")

@bp.delete("/<sid>")
@admin_required
def delete_student(sid,actor):
    db=get_db(); row=db.execute("SELECT id FROM students WHERE id=?",(sid,)).fetchone()
    if not row: return jsonify(error="Student not found"),404
    db.execute("DELETE FROM students WHERE id=?",(sid,)); db.commit(); audit(actor,"student_deleted","students",sid)
    return jsonify(message="Student deleted")

@bp.post("/<sid>/status")
@admin_required
def status(sid,actor):
    active=bool((request.get_json(silent=True) or {}).get("active",True)); db=get_db()
    if not db.execute("SELECT 1 FROM students WHERE id=?",(sid,)).fetchone(): return jsonify(error="Student not found"),404
    db.execute("UPDATE students SET active=?,updated_at=datetime('now') WHERE id=?",(1 if active else 0,sid)); db.commit()
    audit(actor,"student_activated" if active else "student_deactivated","students",sid); return jsonify(message="Status updated")

@bp.post("/import")
@admin_required
def import_csv(actor):
    if "file" not in request.files: return jsonify(error="CSV file is required"),400
    try: text=request.files["file"].read().decode("utf-8-sig")
    except UnicodeDecodeError: return jsonify(error="CSV must be UTF-8 encoded"),422
    reader=csv.DictReader(io.StringIO(text)); headers={h.strip().lower() for h in (reader.fieldnames or [])}
    required={"name","email","student_code"}
    if not required.issubset(headers): return jsonify(error="CSV requires name,email,student_code columns"),422
    imported=0; skipped=[]
    for line_no,row in enumerate(reader,start=2):
        data={str(k).strip().lower(): (v or "").strip() for k,v in row.items()}
        try:
            create_student(data); imported+=1
        except Exception as e: skipped.append({"row":line_no,"reason": "Duplicate email/code" if "UNIQUE" in str(e) else str(e)})
    audit(actor,"students_csv_import","students",None,{"imported":imported,"skipped":len(skipped)})
    return jsonify(imported=imported,skipped=skipped),201
