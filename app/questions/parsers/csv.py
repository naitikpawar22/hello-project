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
    return result
