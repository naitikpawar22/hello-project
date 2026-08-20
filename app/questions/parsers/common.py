import re, json

def normalize_type(value):
    v=(value or "MCQ").strip().upper()
    return "MSQ" if v in {"MSQ","MULTIPLE","MULTIPLE SELECT","MULTI"} else "MCQ"

def normalize_answer(value, option_count, options=None):
    if value is None: return []
    if isinstance(value,(list,tuple)): parts=list(value)
    else:
        s=str(value).strip()
        if s.startswith("["):
            try:
                parsed=json.loads(s); parts=parsed if isinstance(parsed,list) else [parsed]
            except Exception: parts=re.split(r"\s*,\s*",s.strip("[]"))
        else: parts=re.split(r"\s*[,;|/]\s*|\s+",s)
    result=[]
    for part in parts:
        p=str(part).strip().upper()
        if not p: continue
        idx = -1
        if len(p)==1 and "A"<=p<="Z": idx=ord(p)-65
        elif p.isdigit():
            n=int(p); idx=n if 0 <= n < option_count else n-1
        
        if (idx < 0 or idx >= option_count) and options:
            for opt_i, opt_val in enumerate(options):
                if str(opt_val).strip().lower() == str(part).strip().lower():
                    idx = opt_i
                    break
                    
        if 0 <= idx < option_count and idx not in result: result.append(idx)
    return sorted(result)

def make_question(text, options, answer, **kwargs):
    opts=[str(x).strip() for x in options if str(x).strip()]
    correct=normalize_answer(answer,len(opts),options=opts)
    typ=normalize_type(kwargs.get("type"))
    review=0
    if len(opts)<2 or len(opts)>4 or not correct or (typ=="MCQ" and len(correct)!=1): review=1
    return {"text":str(text).strip(),"type":typ,"options":opts,"correct":correct,
            "marks":float(kwargs.get("marks",1) or 1),"negative_marks":float(kwargs.get("negative_marks",0) or 0),
            "topic":str(kwargs.get("topic","") or "").strip(),"explanation":str(kwargs.get("explanation","") or "").strip(),"needs_review":review}

def parse_question_blocks(text):
    lines=[re.sub(r"\s+"," ",x.strip()) for x in text.replace("\r","\n").split("\n") if x.strip()]
    questions=[]; current=None
    q_re=re.compile(r"^(?:Q(?:uestion)?\s*\d+[:.)-]?|\d+[.)])\s*(.+)$",re.I)
    opt_re=re.compile(r"^([A-D])\s*[.)\-:]+\s*(.+)$",re.I)
    ans_re=re.compile(r"^(?:Answer|Correct Answer|Correct)\s*[:=-]\s*(.+)$",re.I)
    for line in lines:
        m=q_re.match(line)
        if m:
            if current: questions.append(current)
            current={"text":m.group(1),"options":[],"answer":None}
        elif current and (m:=opt_re.match(line)): current["options"].append(m.group(2))
        elif current and (m:=ans_re.match(line)): current["answer"]=m.group(1)
    if current: questions.append(current)
    return [make_question(x["text"],x["options"],x["answer"]) for x in questions]
