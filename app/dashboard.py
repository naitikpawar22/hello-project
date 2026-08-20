from flask import Blueprint,jsonify
from app.database import get_db
from app.utils.security import admin_or_teacher_required
bp=Blueprint("dashboard",__name__,url_prefix="/api/dashboard")
@bp.get("")
@admin_or_teacher_required
def dashboard(actor):
    db=get_db();
    def count(sql,p=()): return db.execute(sql,p).fetchone()["c"]
    total_students=count("SELECT COUNT(*) c FROM students"); active_students=count("SELECT COUNT(*) c FROM students WHERE active=1")
    banks=count("SELECT COUNT(*) c FROM question_banks"); questions=count("SELECT COUNT(*) c FROM questions")
    exams=count("SELECT COUNT(*) c FROM exams"); published=count("SELECT COUNT(*) c FROM exams WHERE status IN ('PUBLISHED','SCHEDULED','LIVE')")
    attempts=count("SELECT COUNT(*) c FROM attempts"); avg=db.execute("SELECT COALESCE(AVG(percentage),0) x FROM results").fetchone()["x"]; rate=db.execute("SELECT COALESCE(AVG(passed)*100,0) x FROM results").fetchone()["x"]
    recent=db.execute("SELECT r.id,r.created_at,r.percentage,r.passed,a.candidate_name,e.title FROM results r JOIN attempts a ON a.id=r.attempt_id JOIN exams e ON e.id=r.exam_id ORDER BY r.created_at DESC LIMIT 8").fetchall()
    ex=db.execute("SELECT e.id,e.title,e.status,e.creator_id,e.created_at,s.start_at,s.end_at FROM exams e LEFT JOIN exam_schedules s ON s.exam_id=e.id ORDER BY e.created_at DESC LIMIT 8").fetchall()
    upcoming=db.execute("SELECT e.id,e.title,s.start_at,s.end_at,s.timezone FROM exam_schedules s JOIN exams e ON e.id=s.exam_id WHERE datetime(s.start_at)>datetime('now') ORDER BY s.start_at LIMIT 8").fetchall()
    if actor["role"]!="admin":
        ex=[dict(x) for x in ex if x["creator_id"]==actor["id"]] if ex else []
    return jsonify(stats={"total_students":total_students,"active_students":active_students,"question_banks":banks,"questions":questions,"exams":exams,"published_exams":published,"attempts":attempts,"average_percentage":round(avg,2),"pass_rate":round(rate,2)},recent_attempts=[dict(x) for x in recent],recent_exams=[dict(x) for x in ex],upcoming_exams=[dict(x) for x in upcoming])
