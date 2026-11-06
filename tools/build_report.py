# -*- coding: utf-8 -*-
"""生成《应用软件开发专题实践》课程设计报告。"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from report_lib import Report
from report_text1 import cover, front_matter, chapter1, chapter2
from report_text2 import chapter3, chapter4
from report_text3 import chapter5
from report_text4 import (
    chapter6, conclusion, references, acknowledgement, appendix,
)

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(BASE, "课程设计报告_排版定稿.docx")
OUT = os.path.abspath(OUT)


def main():
    r = Report()
    cover(r)
    front_matter(r)
    chapter1(r)
    chapter2(r)
    chapter3(r)
    chapter4(r)
    chapter5(r)
    chapter6(r)
    conclusion(r)
    references(r)
    acknowledgement(r)
    appendix(r)
    r.save(OUT)
    print("saved:", OUT)


if __name__ == "__main__":
    main()
