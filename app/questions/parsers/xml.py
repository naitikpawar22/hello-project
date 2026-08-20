import xml.etree.ElementTree as ET
from .common import make_question

def parse(path):
    root=ET.parse(path).getroot(); result=[]
    for q in root.iter():
        if q.tag.lower().split("}")[-1] not in {"question","item"}: continue
        def txt(names):
            for child in q.iter():
                tag=child.tag.lower().split("}")[-1]
                if tag in names and child is not q and (child.text or "").strip(): return child.text.strip()
            return ""
        question=txt({"text","question","questiontext"})
        opts=[(c.text or "").strip() for c in list(q) if c.tag.lower().split("}")[-1] in {"option","choice"} and (c.text or "").strip()]
        answer=txt({"answer","correct","correctanswer"})
        if question and opts: result.append(make_question(question,opts,answer,type=txt({"type","questiontype"}) or "MCQ",marks=txt({"marks"}) or 1,negative_marks=txt({"negativemarks","negative"}) or 0,topic=txt({"topic","category"}),explanation=txt({"explanation","solution"})))
    return result
