from openpyxl import load_workbook
from .common import make_question

def parse(path):
    wb=load_workbook(path,read_only=True,data_only=True)
    ws=wb.active; rows=ws.iter_rows(values_only=True)
    headers=[str(x or "").strip().lower() for x in next(rows,())]
    records=[]
    for vals in rows:
        row={headers[i]:vals[i] for i in range(min(len(headers),len(vals)))}
        q=row.get("question") or row.get("question_text")
        if not q: continue
        options=[row.get(k) for k in ("option_a","option_b","option_c","option_d") if row.get(k) not in (None,"")]
        records.append(make_question(q,options,row.get("answer") or row.get("correct_answer"),type=row.get("type") or row.get("question_type") or "MCQ",marks=row.get("marks",1),negative_marks=row.get("negative_marks",0),topic=row.get("topic") or row.get("category") or "",explanation=row.get("explanation") or row.get("solution") or ""))
    return records
