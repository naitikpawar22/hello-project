from bs4 import BeautifulSoup
from .common import parse_question_blocks

def parse(path):
    with open(path,"r",encoding="utf-8",errors="replace") as f: soup=BeautifulSoup(f.read(),"html.parser")
    return parse_question_blocks(soup.get_text("\n"))
