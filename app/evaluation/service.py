from app.database import get_db

def evaluate_attempt(attempt_id):
    db=get_db()
    attempt=db.execute("SELECT * FROM attempts WHERE id=?",(attempt_id,)).fetchone()
    if not attempt: raise LookupError("Attempt not found")
    if attempt["status"] not in {"SUBMITTED","AUTO_SUBMITTED"}: raise ValueError("Attempt is not finalized")
    rows=db.execute("SELECT eq.question_id,eq.exam_marks,eq.exam_negative_marks,q.text,q.type,q.topic,q.explanation,aa.selected_json FROM exam_questions eq JOIN questions q ON q.id=eq.question_id LEFT JOIN attempt_answers aa ON aa.question_id=q.id AND aa.attempt_id=? WHERE eq.exam_id=? ORDER BY eq.question_order",(attempt_id,attempt["exam_id"])).fetchall()
    score=max_score=0; correct=wrong=skipped=0; details=[]; topics={}
    import json
    for r in rows:
        opts=db.execute("SELECT option_index,option_text,is_correct FROM question_options WHERE question_id=? ORDER BY option_index",(r["question_id"],)).fetchall()
        selected=json.loads(r["selected_json"] or "[]") if r["selected_json"] else []
        correct_set={o["option_index"] for o in opts if o["is_correct"]}; selected_set={int(x) for x in selected}
        marks=float(r["exam_marks"] if r["exam_marks"] is not None else 1); neg=float(r["exam_negative_marks"] if r["exam_negative_marks"] is not None else 0); max_score+=marks
        if not selected_set: status="SKIPPED"; awarded=0; skipped+=1
        elif selected_set==correct_set: status="CORRECT"; awarded=marks; correct+=1
        else: status="WRONG"; awarded=-neg; wrong+=1
        score+=awarded; topic=r["topic"] or "Uncategorized"; t=topics.setdefault(topic,{"correct":0,"wrong":0,"skipped":0,"max_marks":0,"score":0}); t[status.lower()]+=1; t["max_marks"]+=marks; t["score"]+=awarded
        details.append({"question_id":r["question_id"],"question":r["text"],"selected":sorted(selected_set),"correct":sorted(correct_set),"status":status,"marks_awarded":awarded,"marks":marks,"negative_marks":neg,"explanation":r["explanation"] or "","options":[dict(o) for o in opts]})
    pct=(score/max_score*100) if max_score else 0; passed=pct>=db.execute("SELECT pass_percentage FROM exams WHERE id=?",(attempt["exam_id"],)).fetchone()["pass_percentage"]
    result_id=__import__("uuid").uuid4().hex
    db.execute("INSERT INTO results(id,attempt_id,exam_id,student_id,score,max_marks,percentage,passed,correct_count,wrong_count,skipped_count,time_taken_seconds,security_event_count,topic_json,details_json,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,datetime('now'))",
      (result_id,attempt_id,attempt["exam_id"],attempt["student_id"],max(0,score),max_score,max(0,pct),1 if passed else 0,correct,wrong,skipped,attempt["time_taken_seconds"] or 0,attempt["security_event_count"],json.dumps(topics),json.dumps(details)))
    db.commit(); return result_id
