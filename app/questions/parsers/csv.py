<<<<<<< HEAD
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
=======
import csv
from .common import make_question

def parse(path):
    with open(path,"r",encoding="utf-8-sig",newline="") as f: rows=list(csv.DictReader(f))
    result=[]
    aliases={"question":"question","question_text":"question","answer":"answer","correct_answer":"answer","type":"type","question_type":"type","marks":"marks","negative_marks":"negative_marks","topic":"topic","category":"topic","explanation":"explanation","solution":"explanation"}
    for row in rows:
        r={str(k).strip().lower():v for k,v in row.items()}
        q=next((r[k] for k,v in aliases.items() if v=="question" and r.get(k)),None)
        options=[r[k] for k in ("option_a","option_b","option_c","option_d") if r.get(k)]
        if not q: continue
        answer=next((r[k] for k,v in aliases.items() if v=="answer" and r.get(k)),None)
        result.append(make_question(q,options,answer,type=next((r[k] for k,v in aliases.items() if v=="type" and r.get(k)),"MCQ"),marks=r.get("marks",1),negative_marks=r.get("negative_marks",0),topic=next((r[k] for k,v in aliases.items() if v=="topic" and r.get(k)),""),explanation=next((r[k] for k,v in aliases.items() if v=="explanation" and r.get(k)),"")))
>>>>>>> 00cdc5ce5c2c164af42ff31e6595073d105d2b0b
    return result
