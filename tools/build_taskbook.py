# -*- coding: utf-8 -*-
"""按模板生成《应用软件开发专题实践》课程设计任务书。"""
import os
from docx import Document
from docx.shared import Pt
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn

TEMPLATE = r"C:/Users/lexi3/Downloads/计科7班-2023109980-杜明烁-应用软件开发专题实践/计科7班-2023109980-杜明烁《应用软件开发专题实践》课程设计任务书.docx"
OUT = r"C:/Users/lexi3/Desktop/应用软件/计科7班-2023109980-杜明烁《应用软件开发专题实践》课程设计任务书_智能记账与生活便签.docx"

TITLE = "基于 uni-app 的智能记账与生活便签一体化管理系统设计与实现"

CONTENT = [
    ("1、目的和意义", True, False),
    ("通过本选题使学生综合运用所学基本理论知识、专业技能，培养分析与解决移动应用开发、前后端交互和大模型应用问题的能力。", False, False),
    ("学会本专业中英文文献资料的检索方法，掌握需求分析、系统设计、数据库设计、接口设计、测试与部署的基本流程，养成科学研究的基本素质。", False, False),
    ("2、主要内容", True, False),
    ("用户管理：实现账号密码注册登录、自动登录、JWT 令牌刷新、个人资料与密码修改、服务器地址配置，按用户隔离账单、便签、预算和目标数据。", False, False),
    ("首页总览：展示月度结余、收入、支出、近 7 日支出趋势、预算使用率、AI 消费洞察、最近账单和待办摘要，提供截图记账与快捷入口。", False, False),
    ("账单管理：实现列表/日历双视图、按月份和收支类型筛选、分页加载、账单新增/编辑/删除、分类图标、支付渠道与扣款账户记录、AI/截图来源标签、日历热力图与当日明细。", False, False),
    ("便签待办：实现待办月历、清单、竖向看板三种视图，支持六色标签、优先级、置顶、截止时间、逾期统计、一键完成；生活便签支持按周/日期查看、搜索与按日期分组。", False, False),
    ("AI 智能助手：实现自然语言记账、支付截图/小票识别、任务提取、问账本工具调用、消费总结与首页洞察；完成提示词设计、JSON 结构化输出、字段校验、超时重试、每日限流、调用日志、失败降级、敏感信息脱敏和提示词注入防护。", False, False),
    ("统计与目标：实现月度收支、每日支出柱状图、分类占比和支付渠道环形图、预算、储蓄目标、生活挑战和个人记账统计。", False, False),
    ("数据管理：使用 SQLAlchemy 完成 MySQL/SQLite 持久化，设计用户、分类、账单、便签、预算、储蓄目标、生活挑战和 AI 调用日志等数据表，保证用户数据隔离和事务一致性。", False, False),
    ("交互反馈与测试：提供加载、成功、失败、重试和降级提示；编写接口冒烟测试与不少于 20 条 AI 专项测试集，记录输入、期望、实际结果和问题分析。", False, False),
    ("真机适配：完成 Android 端服务器地址配置、明文 HTTP 适配、相机/存储权限申请和 APK 打包说明。", False, False),
    ("自行增加其他功能。", False, False),
    ("3、具体要求", True, False),
    ("综述国内外个人记账、生活便签、移动应用和大模型结构化抽取的现状与特点；", False, False),
    ("深入了解 uni-app、Vue 3、FastAPI、SQLAlchemy、MySQL 和大模型 API 等相关技术；", False, False),
    ("熟练掌握移动端界面开发、前后端分离、RESTful 接口设计和数据库设计方法；", False, False),
    ("设计并实现基于 uni-app 的智能记账与生活便签一体化管理系统；", False, False),
    ("深入分析 AI 草稿校验、用户确认落库、限流降级、隐私脱敏和提示词注入防护等关键技术；", False, False),
    ("训练检索文献资料、撰写技术文档、开展软件测试和部署演示的能力；", False, False),
    ("软件操作简单，界面统一，运行稳定，异常提示清晰。", False, False),
    ("4、报告主要内容至少包括：", True, False),
    ("引言；", False, False),
    ("可行性分析；", False, False),
    ("需求分析；", False, False),
    ("总体设计；", False, False),
    ("详细设计；", False, False),
    ("系统测试（包含测试方案、测试用例、测试结果）；", False, False),
    ("参考文献；", False, False),
    ("设计总结；", False, False),
    ("附录（主要用来放程序）；", False, False),
    ("AI 使用与责任说明。", False, False),
]

REFS = [
    ("5、参考资料及文献查询方向、范围：（由指导教师指定）", True, False),
    ("[1] 赵鑫, 李军毅, 周昆, 等. 大语言模型: 基础与前沿[M]. 北京: 高等教育出版社, 2024.", False, True),
    ("[2] 车万翔, 窦志成, 冯岩松, 等. 大模型时代的自然语言处理: 挑战、机遇与发展[J]. 中国科学: 信息科学, 2023, 53(9): 1645-1687.", False, True),
    ("[3] 董航. 基于记账管理APP系统需求分析与设计[J]. 辽宁高职学报, 2020, 22(10).", False, True),
    ("[4] 张安妮, 叶文青, 吕渝, 等. 基于Flutter跨平台记账软件的设计与实现[J]. 电脑知识与技术, 2023, 19(21).", False, True),
    ("[5] uni-app 官方文档[EB/OL]. https://uniapp.dcloud.net.cn/.", False, True),
    ("[6] FastAPI 官方文档[EB/OL]. https://fastapi.tiangolo.com/.", False, True),
    ("[7] SQLAlchemy 官方文档[EB/OL]. https://docs.sqlalchemy.org/.", False, True),
    ("[8] OpenAI API 官方文档[EB/OL]. https://platform.openai.com/docs/.", False, True),
    ("[9] Dagdelen J, Dunn A, Lee S, et al. Structured information extraction from scientific text with large language models[J]. Nature Communications, 2024, 15(1): 1418.", False, True),
    ("[10] Vaswani A, Shazeer N, Parmar N, et al. Attention Is All You Need[C]//Advances in Neural Information Processing Systems. 2017.", False, True),
]


def clear_cell(cell):
    for para in list(cell.paragraphs):
        para._element.getparent().remove(para._element)


def add_para(cell, text, heading=False, ref=False):
    p = cell.add_paragraph()
    pf = p.paragraph_format
    pf.first_line_indent = Pt(0) if heading else Pt(21)
    pf.left_indent = Pt(0)
    pf.space_before = Pt(0)
    pf.space_after = Pt(0)
    pf.line_spacing = 1.0
    p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    run = p.add_run(text)
    name = "宋体" if ref else "楷体"
    run.font.name = name
    run.font.size = Pt(10.5)
    run.bold = heading
    rPr = run._element.get_or_add_rPr()
    rFonts = rPr.rFonts
    if rFonts is None:
        from docx.oxml import OxmlElement
        rFonts = OxmlElement("w:rFonts")
        rPr.append(rFonts)
    rFonts.set(qn("w:ascii"), name)
    rFonts.set(qn("w:hAnsi"), name)
    rFonts.set(qn("w:eastAsia"), name)
    return p


def main():
    doc = Document(TEMPLATE)
    table = doc.tables[0]

    # 课程设计题目
    title_cell = table.cell(1, 1)
    p = title_cell.paragraphs[0]
    if p.runs:
        p.runs[0].text = TITLE
        for run in p.runs[1:]:
            run._element.getparent().remove(run._element)
    else:
        p.add_run(TITLE)

    # 主要内容（1-4）
    content_cell = table.cell(3, 0)
    clear_cell(content_cell)
    for text, heading, ref in CONTENT:
        add_para(content_cell, text, heading=heading, ref=ref)

    # 参考资料（5）
    ref_cell = table.cell(4, 0)
    clear_cell(ref_cell)
    for text, heading, ref in REFS:
        add_para(ref_cell, text, heading=heading, ref=ref)

    doc.save(OUT)
    print("saved:", OUT)


if __name__ == "__main__":
    main()
