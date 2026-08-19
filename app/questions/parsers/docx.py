from docx import Document
from .common import parse_question_blocks

def parse(path):
    doc=Document(path); text="\n".join(p.text for p in doc.paragraphs)
    return parse_question_blocks(text)
