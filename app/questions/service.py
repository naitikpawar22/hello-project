from pathlib import Path
from app.database import get_db
from app.utils.helpers import new_id, now_iso
from app.questions.parsers import pdf, xml, html, docx, spreadsheet, csv
PARSERS={"pdf":pdf.parse,"xml":xml.parse,"html":html.parse,"htm":html.parse,"docx":docx.parse,"xlsx":spreadsheet.parse,"xlsm":spreadsheet.parse,"csv":csv.parse}

def import_bank(name,description,source_file,source_format,creator,questions):
    db=get_db(); ts=now_iso(); bid=new_id(); db.execute("BEGIN")
    try:
        db.execute("INSERT INTO question_banks(id,name,description,source_file,source_format,creator_id,creator_role,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?)",
                   (bid,name,description,source_file,source_format,creator["id"],creator["role"],ts,ts))
        for i,q in enumerate(questions):
            qid=new_id(); db.execute("INSERT INTO questions(id,bank_id,text,type,marks,negative_marks,topic,explanation,active,question_order,needs_review,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,1,?,?,?,?)",
                (qid,bid,q["text"],q["type"],q["marks"],q["negative_marks"],q["topic"],q["explanation"],i,q.get("needs_review",0),ts,ts))
            for idx,opt in enumerate(q["options"]):
                db.execute("INSERT INTO question_options(id,question_id,option_index,option_text,is_correct) VALUES(?,?,?,?,?)",(new_id(),qid,idx,opt,1 if idx in q["correct"] else 0))
        db.commit()
    except Exception:
        db.rollback(); raise
    return bid

def parse_file(path,fmt):
    if fmt not in PARSERS: raise ValueError("Unsupported question-bank format")
    return PARSERS[fmt](path)

def serialize_question(row):
    db=get_db(); opts=db.execute("SELECT option_index,option_text,is_correct FROM question_options WHERE question_id=? ORDER BY option_index",(row["id"],)).fetchall()
    return {**dict(row),"options":[{"index":o["option_index"],"text":o["option_text"],"is_correct":bool(o["is_correct"])} for o in opts]}
