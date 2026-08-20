import re
from openpyxl import load_workbook
from .common import make_question

def parse(path):
    wb = load_workbook(path, read_only=True, data_only=True)
    ws = wb.active; rows = ws.iter_rows(values_only=True)
    raw_headers = next(rows, ())
    headers = [re.sub(r'[\s\.\-]+', '_', str(x or "").strip().lower()) for x in raw_headers]
    records = []
    for vals in rows:
        if not vals: continue
        row = {headers[i]: str(vals[i] if vals[i] is not None else "").strip() for i in range(min(len(headers), len(vals)))}
        
        q = row.get("question") or row.get("question_text")
        if not q: continue
        
        opts = []
        for opt_key in ("option_a", "option_b", "option_c", "option_d", "option_1", "option_2", "option_3", "option_4", "a", "b", "c", "d"):
            val = row.get(opt_key)
            if val: opts.append(val)
            
        answer = row.get("correct_answer") or row.get("correct") or row.get("answer")
        topic = row.get("category") or row.get("topic") or ""
        typ = row.get("type") or row.get("question_type") or "MCQ"
        marks = row.get("marks", 1)
        neg = row.get("negative_marks", 0)
        expl = row.get("explanation") or row.get("solution") or ""
        
        records.append(make_question(q, opts, answer, type=typ, marks=marks, negative_marks=neg, topic=topic, explanation=expl))
    return records
