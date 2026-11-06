# -*- coding: utf-8 -*-
"""课程设计报告 Word 生成工具：版式、样式、图表、表格、代码块。"""
import os
from docx import Document
from docx.shared import Pt, Cm, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_LINE_SPACING
from docx.enum.section import WD_SECTION
from docx.enum.table import WD_TABLE_ALIGNMENT, WD_ALIGN_VERTICAL
from docx.enum.style import WD_STYLE_TYPE
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from PIL import Image

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIG_DIR = os.path.join(BASE, "diagrams", "report")
DOCS_DIR = os.path.join(BASE, "docs")
LATEST_DIR = os.path.join(DOCS_DIR, "最新截图")

# 逻辑截图名 -> 手账风设计图回退（用户把最新运行截图放入 docs/最新截图 后自动覆盖）
SHOT_FALLBACK = {
    "登录界面.png": "改造后_登录页.png",
    "个人中心界面.png": "手绘风_个人中心.png",
    "注册界面.png": "改造后_登录页.png",
    "首页界面.png": "改造后_首页.png",
    "账单列表界面.png": "手绘风_账单列表.png",
    "账单日历界面.png": "手账2.0_手绘日历.png",
    "便签界面.png": "手账2.0_任务看板.png",
    "待办界面.png": "手账2.0_待办清单.png",
    "AI智能记账界面.png": "改造后_AI记账页.png",
    "AI助手界面.png": "手账2.0_AI首页.png",
    "问账本界面.png": "手账2.0_问账本.png",
    "统计分析界面.png": "改造后_统计页.png",
    "统计图表界面.png": "手绘风_统计2.png",
    "目标与挑战界面.png": "手账2.0_任务看板.png",
}


def resolve_shot(filename):
    """优先使用 docs/最新截图 下的运行截图，否则回退到手账风设计图。"""
    latest = os.path.join(LATEST_DIR, filename)
    if os.path.exists(latest):
        return latest
    fallback = SHOT_FALLBACK.get(filename, filename)
    return os.path.join(DOCS_DIR, fallback)


def _set_run_font(run, name="宋体", size=12, bold=False, color=(0, 0, 0)):
    run.font.name = name
    run.font.size = Pt(size)
    run.bold = bold
    run.font.color.rgb = RGBColor(*color)
    rPr = run._element.get_or_add_rPr()
    rFonts = rPr.find(qn("w:rFonts"))
    if rFonts is None:
        rFonts = OxmlElement("w:rFonts")
        rPr.append(rFonts)
    rFonts.set(qn("w:ascii"), name)
    rFonts.set(qn("w:hAnsi"), name)
    rFonts.set(qn("w:eastAsia"), name)


def _set_mixed_font(run, ascii_name="Times New Roman", ea_name="宋体",
                    size=12, bold=False, color=(0, 0, 0)):
    run.font.name = ascii_name
    run.font.size = Pt(size)
    run.bold = bold
    run.font.color.rgb = RGBColor(*color)
    rPr = run._element.get_or_add_rPr()
    rFonts = rPr.find(qn("w:rFonts"))
    if rFonts is None:
        rFonts = OxmlElement("w:rFonts")
        rPr.append(rFonts)
    rFonts.set(qn("w:ascii"), ascii_name)
    rFonts.set(qn("w:hAnsi"), ascii_name)
    rFonts.set(qn("w:eastAsia"), ea_name)


def _shade(cell_or_par, fill):
    el = cell_or_par._tc if hasattr(cell_or_par, "_tc") else cell_or_par._p
    pr = el.get_or_add_tcPr() if hasattr(el, "get_or_add_tcPr") else el.get_or_add_pPr()
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:color"), "auto")
    shd.set(qn("w:fill"), fill)
    pr.append(shd)


def _cell_border(cell, edge="bottom", sz="8", color="000000"):
    tcPr = cell._tc.get_or_add_tcPr()
    borders = tcPr.find(qn("w:tcBorders"))
    if borders is None:
        borders = OxmlElement("w:tcBorders")
        tcPr.append(borders)
    el = OxmlElement(f"w:{edge}")
    el.set(qn("w:val"), "single")
    el.set(qn("w:sz"), sz)
    el.set(qn("w:space"), "0")
    el.set(qn("w:color"), color)
    borders.append(el)


def _no_table_borders(table):
    tblPr = table._tbl.tblPr
    borders = OxmlElement("w:tblBorders")
    for edge in ("top", "left", "bottom", "right", "insideH", "insideV"):
        el = OxmlElement(f"w:{edge}")
        el.set(qn("w:val"), "nil")
        borders.append(el)
    tblPr.append(borders)


def _field(paragraph, instr, placeholder=""):
    run = paragraph.add_run()
    fld_begin = OxmlElement("w:fldChar")
    fld_begin.set(qn("w:fldCharType"), "begin")
    instr_el = OxmlElement("w:instrText")
    instr_el.set(qn("xml:space"), "preserve")
    instr_el.text = instr
    fld_sep = OxmlElement("w:fldChar")
    fld_sep.set(qn("w:fldCharType"), "separate")
    text = OxmlElement("w:t")
    text.text = placeholder
    fld_end = OxmlElement("w:fldChar")
    fld_end.set(qn("w:fldCharType"), "end")
    run._r.append(fld_begin)
    run._r.append(instr_el)
    run._r.append(fld_sep)
    run._r.append(text)
    run._r.append(fld_end)


def _pg_num(section, fmt="decimal", start=1):
    sectPr = section._sectPr
    el = OxmlElement("w:pgNumType")
    el.set(qn("w:fmt"), fmt)
    el.set(qn("w:start"), str(start))
    sectPr.append(el)


class Report:
    def __init__(self):
        self.doc = Document()
        self._setup_page()
        self._setup_styles()
        self._first_section = True

    # ---------------- 页面与样式 ----------------
    def _setup_page(self):
        sec = self.doc.sections[0]
        sec.page_width = Cm(21.0)
        sec.page_height = Cm(29.7)
        sec.top_margin = Cm(3.0)
        sec.bottom_margin = Cm(2.5)
        sec.left_margin = Cm(2.8)
        sec.right_margin = Cm(2.5)
        sec.header_distance = Cm(2.0)
        sec.footer_distance = Cm(1.6)

    def _setup_styles(self):
        normal = self.doc.styles["Normal"]
        normal.font.name = "Times New Roman"
        normal.font.size = Pt(12)
        normal.element.rPr.rFonts.set(qn("w:eastAsia"), "宋体")
        pf = normal.paragraph_format
        pf.line_spacing = Pt(23)
        pf.line_spacing_rule = WD_LINE_SPACING.EXACTLY
        pf.first_line_indent = Pt(24)
        pf.space_before = Pt(0)
        pf.space_after = Pt(0)
        pf.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY

        specs = {
            "Heading 1": (18, False, WD_ALIGN_PARAGRAPH.LEFT, 7.8, 7.8),
            "Heading 2": (15, False, WD_ALIGN_PARAGRAPH.LEFT, 7.8, 7.8),
            "Heading 3": (14, False, WD_ALIGN_PARAGRAPH.LEFT, 7.8, 7.8),
        }
        for name, (size, bold, align, before, after) in specs.items():
            st = self.doc.styles[name]
            st.font.name = "黑体"
            st.font.size = Pt(size)
            st.font.bold = bold
            st.font.color.rgb = RGBColor(0, 0, 0)
            st.element.rPr.rFonts.set(qn("w:eastAsia"), "黑体")
            pf = st.paragraph_format
            pf.alignment = align
            pf.first_line_indent = Pt(0)
            pf.space_before = Pt(before)
            pf.space_after = Pt(after)
            pf.line_spacing = Pt(23)
            pf.line_spacing_rule = WD_LINE_SPACING.EXACTLY
            pf.keep_with_next = True

        cap = self.doc.styles["Caption"]
        cap.font.name = "黑体"
        cap.font.size = Pt(12)
        cap.font.bold = True
        cap.font.italic = False
        cap.font.color.rgb = RGBColor(0, 0, 0)
        cap.element.rPr.rFonts.set(qn("w:eastAsia"), "黑体")
        pf = cap.paragraph_format
        pf.alignment = WD_ALIGN_PARAGRAPH.CENTER
        pf.first_line_indent = Pt(0)
        pf.space_before = Pt(0)
        pf.space_after = Pt(0)
        pf.line_spacing = Pt(23)
        pf.line_spacing_rule = WD_LINE_SPACING.EXACTLY

        code = self.doc.styles.add_style("CodeBlock", WD_STYLE_TYPE.PARAGRAPH)
        code.base_style = self.doc.styles["Normal"]
        code.font.name = "Times New Roman"
        code.font.size = Pt(10.5)
        code.font.color.rgb = RGBColor(0x1A, 0x1A, 0x1A)
        code.element.rPr.rFonts.set(qn("w:eastAsia"), "宋体")
        pf = code.paragraph_format
        pf.alignment = WD_ALIGN_PARAGRAPH.LEFT
        pf.first_line_indent = Pt(0)
        pf.left_indent = Cm(0.5)
        pf.right_indent = Cm(0.4)
        pf.space_before = Pt(3)
        pf.space_after = Pt(5)
        pf.line_spacing = 1.0

        toc_head = self.doc.styles.add_style("TOCHead", WD_STYLE_TYPE.PARAGRAPH)
        toc_head.base_style = self.doc.styles["Normal"]
        toc_head.font.name = "黑体"
        toc_head.font.size = Pt(18)
        toc_head.font.bold = False
        toc_head.element.rPr.rFonts.set(qn("w:eastAsia"), "黑体")
        pf = toc_head.paragraph_format
        pf.alignment = WD_ALIGN_PARAGRAPH.CENTER
        pf.first_line_indent = Pt(0)
        pf.space_before = Pt(7.8)
        pf.space_after = Pt(7.8)
        pf.line_spacing = Pt(23)
        pf.line_spacing_rule = WD_LINE_SPACING.EXACTLY

        ref = self.doc.styles.add_style("Reference", WD_STYLE_TYPE.PARAGRAPH)
        ref.base_style = self.doc.styles["Normal"]
        ref.font.name = "Times New Roman"
        ref.font.size = Pt(10.5)
        ref.element.rPr.rFonts.set(qn("w:eastAsia"), "宋体")
        pf = ref.paragraph_format
        pf.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
        pf.left_indent = Pt(21)
        pf.first_line_indent = Pt(-21)
        pf.line_spacing = Pt(23)
        pf.line_spacing_rule = WD_LINE_SPACING.EXACTLY
        pf.space_before = Pt(0)
        pf.space_after = Pt(0)

        for name, ea, size in (("TOC 1", "黑体", 14), ("TOC 2", "宋体", 12), ("TOC 3", "宋体", 12)):
            try:
                st = self.doc.styles[name]
            except KeyError:
                st = self.doc.styles.add_style(name, WD_STYLE_TYPE.PARAGRAPH)
            st.font.name = "Times New Roman" if ea == "宋体" else "黑体"
            st.font.size = Pt(size)
            st.font.bold = False
            st.element.rPr.rFonts.set(qn("w:eastAsia"), ea)
            pf = st.paragraph_format
            pf.line_spacing = Pt(23)
            pf.line_spacing_rule = WD_LINE_SPACING.EXACTLY
            pf.space_before = Pt(0)
            pf.space_after = Pt(0)

    # ---------------- 分节、页眉页脚 ----------------
    def new_section(self, header_text=None, page_fmt="decimal", start=1):
        sec = self.doc.add_section(WD_SECTION.NEW_PAGE)
        sec.page_width = Cm(21.0)
        sec.page_height = Cm(29.7)
        sec.top_margin = Cm(3.0)
        sec.bottom_margin = Cm(2.5)
        sec.left_margin = Cm(2.8)
        sec.right_margin = Cm(2.5)
        sec.header_distance = Cm(2.0)
        sec.footer_distance = Cm(1.6)
        sec.header.is_linked_to_previous = False
        sec.footer.is_linked_to_previous = False
        hp = sec.header.paragraphs[0]
        hp.alignment = WD_ALIGN_PARAGRAPH.RIGHT
        hp.paragraph_format.first_line_indent = Pt(0)
        if header_text:
            run = hp.add_run(header_text)
            _set_run_font(run, "宋体", 10)
        fp = sec.footer.paragraphs[0]
        fp.alignment = WD_ALIGN_PARAGRAPH.CENTER
        fp.paragraph_format.first_line_indent = Pt(0)
        _field(fp, "PAGE", "1")
        _set_run_font(fp.runs[0] if fp.runs else fp.add_run(), "Times New Roman", 9)
        _pg_num(sec, page_fmt, start)
        self._first_section = False
        return sec

    # ---------------- 内容元素 ----------------
    def h1(self, text, page_break=False, center=False):
        if page_break:
            self.doc.add_page_break()
        p = self.doc.add_paragraph(text, style="Heading 1")
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER if center else WD_ALIGN_PARAGRAPH.LEFT
        return p

    def h2(self, text):
        return self.doc.add_paragraph(text, style="Heading 2")

    def h3(self, text):
        return self.doc.add_paragraph(text, style="Heading 3")

    def p(self, text, indent=True, bold_prefix=None):
        p = self.doc.add_paragraph()
        if not indent:
            p.paragraph_format.first_line_indent = Pt(0)
        if bold_prefix and text.startswith(bold_prefix):
            r1 = p.add_run(bold_prefix)
            _set_mixed_font(r1, "Times New Roman", "宋体", 12, bold=True)
            r2 = p.add_run(text[len(bold_prefix):])
            _set_mixed_font(r2, "Times New Roman", "宋体", 12)
        else:
            r = p.add_run(text)
            _set_mixed_font(r, "Times New Roman", "宋体", 12)
        return p

    def bullets(self, items, numbered=False):
        for i, item in enumerate(items, 1):
            p = self.doc.add_paragraph()
            p.paragraph_format.first_line_indent = Pt(0)
            p.paragraph_format.left_indent = Pt(24)
            p.paragraph_format.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
            prefix = f"（{i}）" if numbered else "· "
            r = p.add_run(prefix + item)
            _set_mixed_font(r, "Times New Roman", "宋体", 12)

    def code_caption(self, text):
        p = self.doc.add_paragraph(text, style="Caption")
        p.alignment = WD_ALIGN_PARAGRAPH.LEFT
        p.paragraph_format.first_line_indent = Pt(0)
        p.paragraph_format.left_indent = Cm(0.5)
        p.paragraph_format.space_before = Pt(1)
        p.paragraph_format.space_after = Pt(4)
        return p

    def code(self, text):
        p = self.doc.add_paragraph(style="CodeBlock")
        run = p.add_run(text.rstrip("\n"))
        _set_mixed_font(run, "Times New Roman", "宋体", 10.5)
        _shade(p, "F7F7F7")
        pPr = p._p.get_or_add_pPr()
        pBdr = OxmlElement("w:pBdr")
        for edge in ("top", "left", "bottom", "right"):
            el = OxmlElement(f"w:{edge}")
            el.set(qn("w:val"), "single")
            el.set(qn("w:sz"), "4")
            el.set(qn("w:space"), "2")
            el.set(qn("w:color"), "D9D9D9")
            pBdr.append(el)
        pPr.append(pBdr)

    def figure_caption(self, text):
        return self.doc.add_paragraph(text, style="Caption")

    def figure(self, filename, caption, max_w=14.3, max_h=18.8):
        path = os.path.join(FIG_DIR, filename)
        with Image.open(path) as im:
            w, h = im.size
        max_w = min(max_w, 14.3)
        max_h = min(max_h, 18.8)
        width = max_w
        if width * h / w > max_h:
            width = max_h * w / h
        p = self.doc.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p.paragraph_format.first_line_indent = Pt(0)
        p.paragraph_format.space_before = Pt(6)
        p.paragraph_format.space_after = Pt(2)
        p.paragraph_format.keep_with_next = True
        run = p.add_run()
        run.add_picture(path, width=Cm(width))
        cap = self.doc.add_paragraph(caption, style="Caption")
        return cap

    def figure_pair(self, filename1, caption1, filename2, caption2,
                    cell_w=7.2, img_w=6.2):
        table = self.doc.add_table(rows=2, cols=2)
        table.alignment = WD_TABLE_ALIGNMENT.CENTER
        table.autofit = False
        _no_table_borders(table)
        for i, (fn, cap) in enumerate(((filename1, caption1), (filename2, caption2))):
            cell = table.cell(0, i)
            cell.width = Cm(cell_w)
            cell.vertical_alignment = WD_ALIGN_VERTICAL.CENTER
            p = cell.paragraphs[0]
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            p.paragraph_format.first_line_indent = Pt(0)
            p.paragraph_format.space_before = Pt(4)
            p.paragraph_format.space_after = Pt(2)
            run = p.add_run()
            path = os.path.join(FIG_DIR, fn) if os.path.exists(os.path.join(FIG_DIR, fn)) else resolve_shot(fn)
            run.add_picture(path, width=Cm(img_w))
            ccell = table.cell(1, i)
            ccell.width = Cm(cell_w)
            cp = ccell.paragraphs[0]
            cp.alignment = WD_ALIGN_PARAGRAPH.CENTER
            cp.paragraph_format.first_line_indent = Pt(0)
            cp.paragraph_format.space_after = Pt(6)
            r = cp.add_run(cap)
            _set_run_font(r, "黑体", 12, bold=True)

    def screenshot(self, filename, caption, width=6.6):
        path = resolve_shot(filename)
        p = self.doc.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p.paragraph_format.first_line_indent = Pt(0)
        p.paragraph_format.space_before = Pt(6)
        p.paragraph_format.space_after = Pt(2)
        p.paragraph_format.keep_with_next = True
        run = p.add_run()
        run.add_picture(path, width=Cm(width))
        self.doc.add_paragraph(caption, style="Caption")

    def table(self, caption, headers, rows, widths=None, fs=10.5, align_center=False):
        fs = 10.5
        cap = self.doc.add_paragraph(caption, style="Caption")
        cap.paragraph_format.keep_with_next = True
        if widths:
            total = sum(widths)
            if total > 14.4:
                widths = [w * 14.4 / total for w in widths]
        ncols = len(headers)
        table = self.doc.add_table(rows=1, cols=ncols)
        table.style = "Table Grid"
        table.alignment = WD_TABLE_ALIGNMENT.CENTER
        table.autofit = False
        hdr = table.rows[0]
        trPr = hdr._tr.get_or_add_trPr()
        th = OxmlElement("w:tblHeader")
        th.set(qn("w:val"), "true")
        trPr.append(th)
        for i, text in enumerate(headers):
            cell = hdr.cells[i]
            cell.text = ""
            if widths:
                cell.width = Cm(widths[i])
            cell.vertical_alignment = WD_ALIGN_VERTICAL.CENTER
            p = cell.paragraphs[0]
            p.alignment = WD_ALIGN_PARAGRAPH.LEFT
            p.paragraph_format.first_line_indent = Pt(0)
            p.paragraph_format.line_spacing = 1.0
            r = p.add_run(str(text))
            _set_mixed_font(r, "Times New Roman", "宋体", fs, bold=False)
        for row in rows:
            cells = table.add_row().cells
            for i, val in enumerate(row):
                cell = cells[i]
                if widths:
                    cell.width = Cm(widths[i])
                cell.vertical_alignment = WD_ALIGN_VERTICAL.CENTER
                p = cell.paragraphs[0]
                p.alignment = WD_ALIGN_PARAGRAPH.CENTER if (align_center and i > 0) else WD_ALIGN_PARAGRAPH.LEFT
                p.paragraph_format.first_line_indent = Pt(0)
                p.paragraph_format.line_spacing = 1.0
                r = p.add_run(str(val))
                _set_mixed_font(r, "Times New Roman", "宋体", fs)
        if widths:
            for row in table.rows:
                for i, w in enumerate(widths):
                    row.cells[i].width = Cm(w)
        # 表后留白
        self.doc.add_paragraph().paragraph_format.space_after = Pt(2)
        return table

    def refs(self, items):
        for item in items:
            p = self.doc.add_paragraph(item, style="Reference")
            _set_mixed_font(p.runs[0], "Times New Roman", "宋体", 10.5)

    def save(self, path):
        settings = self.doc.settings.element
        update = OxmlElement("w:updateFields")
        update.set(qn("w:val"), "true")
        settings.append(update)
        self.doc.save(path)
