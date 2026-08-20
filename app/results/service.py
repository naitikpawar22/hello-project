import json
from app.database import get_db

def result_detail(rid):
<<<<<<< HEAD
    db=get_db(); r=db.execute("SELECT r.*,a.candidate_name,a.candidate_email,a.candidate_phone,a.candidate_department,a.candidate_division,a.status AS attempt_status,a.security_event_count,e.title exam_title,e.pass_percentage FROM results r JOIN attempts a ON a.id=r.attempt_id JOIN exams e ON e.id=r.exam_id WHERE r.id=?",(rid,)).fetchone()
    if not r: return None
    d=dict(r); d["topic_performance"]=json.loads(d.pop("topic_json") or "{}"); d["details"]=json.loads(d.pop("details_json") or "[]"); return d


=======
    db=get_db(); r=db.execute("SELECT r.*,a.candidate_name,a.candidate_email,e.title exam_title,e.pass_percentage FROM results r JOIN attempts a ON a.id=r.attempt_id JOIN exams e ON e.id=r.exam_id WHERE r.id=?",(rid,)).fetchone()
    if not r: return None
    d=dict(r); d["topic_performance"]=json.loads(d.pop("topic_json") or "{}"); d["details"]=json.loads(d.pop("details_json") or "[]"); return d
>>>>>>> 00cdc5ce5c2c164af42ff31e6595073d105d2b0b
