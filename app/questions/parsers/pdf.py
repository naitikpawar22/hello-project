from pypdf import PdfReader
from .common import parse_question_blocks

def parse(path):
    text="\n".join((p.extract_text() or "") for p in PdfReader(path).pages)
    return parse_question_blocks(text)
