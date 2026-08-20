import csv, re
from .common import make_question

def parse(path):
    with open(path, "r", encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    result = []
    for row in rows:
        r = {re.sub(r'[\s\.\-]+', '_', str(k or "").strip().lower()): str(v or "").strip() for k, v in row.items() if k is not None}
        
        q = r.get("question") or r.get("question_text")
        if not q: continue
        
        opts = []
        for opt_key in ("option_a", "option_b", "option_c", "option_d", "option_1", "option_2", "option_3", "option_4", "a", "b", "c", "d"):
            val = r.get(opt_key)
            if val: opts.append(val)
            
        answer = r.get("correct_answer") or r.get("correct") or r.get("answer")
        topic = r.get("category") or r.get("topic") or ""
        typ = r.get("type") or r.get("question_type") or "MCQ"
        marks = r.get("marks", 1)
        neg = r.get("negative_marks", 0)
        expl = r.get("explanation") or r.get("solution") or ""
        
        result.append(make_question(q, opts, answer, type=typ, marks=marks, negative_marks=neg, topic=topic, explanation=expl))
    return result
