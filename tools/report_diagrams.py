# -*- coding: utf-8 -*-
"""生成课程设计报告所需黑白学术风图示（PNG, 300dpi）。"""
import os
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import (
    FancyBboxPatch, Rectangle, Ellipse, Polygon, FancyArrowPatch, Circle,
)
from matplotlib.lines import Line2D
from matplotlib import font_manager

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(BASE, "diagrams", "report")
os.makedirs(OUT, exist_ok=True)

FONT_PATH = "C:/Windows/Fonts/simhei.ttf"
FONT = font_manager.FontProperties(fname=FONT_PATH)
INK = "#111111"
GRAY = "#555555"
LIGHT = "#F4F4F4"

plt.rcParams["axes.unicode_minus"] = False
plt.rcParams["font.family"] = FONT.get_name()


def canvas(w=8.5, h=7.0, xlim=(0, 100), ylim=(0, 100)):
    fig, ax = plt.subplots(figsize=(w, h))
    ax.set_xlim(*xlim)
    ax.set_ylim(*ylim)
    ax.axis("off")
    fig.patch.set_facecolor("white")
    fig.subplots_adjust(0, 0, 1, 1)
    return fig, ax


def save(fig, name):
    path = os.path.join(OUT, name)
    fig.savefig(path, dpi=300, facecolor="white", bbox_inches="tight", pad_inches=0.08)
    plt.close(fig)
    print("saved", path)


def box(ax, x, y, w, h, text, fs=11, fill="white", lw=1.1, rounded=False,
        bold=False, align="center"):
    if rounded:
        patch = FancyBboxPatch(
            (x - w / 2, y - h / 2), w, h,
            boxstyle="round,pad=0,rounding_size=1.6",
            facecolor=fill, edgecolor=INK, linewidth=lw, zorder=2)
    else:
        patch = Rectangle((x - w / 2, y - h / 2), w, h, facecolor=fill,
                          edgecolor=INK, linewidth=lw, zorder=2)
    ax.add_patch(patch)
    ax.text(x, y, text, ha="center", va="center", fontsize=fs,
            fontproperties=FONT, color=INK, zorder=3,
            fontweight="bold" if bold else "normal", linespacing=1.35)
    return patch


def arrow(ax, p1, p2, label="", fs=9.5, style="-|>", lw=1.0, dashed=False,
          connectionstyle="arc3,rad=0", label_pos=0.5, label_offset=(0, 1.0),
          color=INK, zorder=1):
    patch = FancyArrowPatch(
        p1, p2, arrowstyle=style, mutation_scale=10, linewidth=lw,
        color=color, linestyle="--" if dashed else "-",
        connectionstyle=connectionstyle, shrinkA=0, shrinkB=0, zorder=zorder)
    ax.add_patch(patch)
    if label:
        lx = p1[0] + (p2[0] - p1[0]) * label_pos + label_offset[0]
        ly = p1[1] + (p2[1] - p1[1]) * label_pos + label_offset[1]
        ax.text(lx, ly, label, ha="center", va="center", fontsize=fs,
                fontproperties=FONT, color=INK, zorder=4,
                bbox=dict(facecolor="white", edgecolor="none", pad=0.6))


def poly_arrow(ax, points, label="", fs=9.5, dashed=False):
    """折线箭头：最后一段带箭头。"""
    for i in range(len(points) - 2):
        ax.plot([points[i][0], points[i + 1][0]],
                [points[i][1], points[i + 1][1]], color=INK, lw=1.0,
                linestyle="--" if dashed else "-", zorder=1)
    arrow(ax, points[-2], points[-1], label=label, fs=fs, dashed=dashed)


def diamond(ax, cx, cy, w, h, text, fs=10):
    pts = [(cx, cy + h / 2), (cx + w / 2, cy), (cx, cy - h / 2), (cx - w / 2, cy)]
    ax.add_patch(Polygon(pts, closed=True, facecolor="white", edgecolor=INK,
                         linewidth=1.1, zorder=2))
    ax.text(cx, cy, text, ha="center", va="center", fontsize=fs,
            fontproperties=FONT, color=INK, zorder=3, linespacing=1.2)


def ellipse(ax, cx, cy, w, h, text, fs=10):
    ax.add_patch(Ellipse((cx, cy), w, h, facecolor="white", edgecolor=INK,
                         linewidth=1.05, zorder=2))
    ax.text(cx, cy, text, ha="center", va="center", fontsize=fs,
            fontproperties=FONT, color=INK, zorder=3, linespacing=1.2)


def actor(ax, cx, cy, label, fs=11):
    r = 1.7
    ax.add_patch(Circle((cx, cy + 5.2), r, facecolor="white", edgecolor=INK,
                        linewidth=1.1, zorder=3))
    ax.plot([cx, cx], [cy + 3.5, cy - 1.0], color=INK, lw=1.1, zorder=3)
    ax.plot([cx - 3.0, cx + 3.0], [cy + 2.0, cy + 2.0], color=INK, lw=1.1, zorder=3)
    ax.plot([cx, cx - 2.4], [cy - 1.0, cy - 4.4], color=INK, lw=1.1, zorder=3)
    ax.plot([cx, cx + 2.4], [cy - 1.0, cy - 4.4], color=INK, lw=1.1, zorder=3)
    ax.text(cx, cy - 7.2, label, ha="center", va="top", fontsize=fs,
            fontproperties=FONT, color=INK)


def title(ax, text, y=99, fs=14):
    ax.text(50, y, text, ha="center", va="top", fontsize=fs,
            fontproperties=FONT, color=INK, fontweight="bold")


# ---------------------------------------------------------------- 图3.1 用例图
def draw_usecase():
    fig, ax = canvas(8.6, 10.4)
    title(ax, "智能记账与生活便签一体化管理系统", 99.2, 13.5)
    ax.add_patch(Rectangle((25, 3), 50, 91, fill=False, edgecolor=INK,
                           linewidth=1.2, linestyle=(0, (6, 3)), zorder=0))
    ax.text(50, 91.5, "系统边界", ha="center", va="bottom", fontsize=9.5,
            fontproperties=FONT, color=GRAY)

    cases = [
        ("注册账号", False), ("登录系统", False), ("自动登录与令牌刷新", False),
        ("管理个人资料", False), ("配置服务器地址", False), ("查看首页总览", False),
        ("管理账单", False), ("查看账单日历", False), ("管理账单分类", False),
        ("管理便签", False), ("管理待办", False), ("切换任务视图", False),
        ("AI 智能记账", True), ("截图识别记账", True), ("AI 任务提取", True),
        ("问账本", True), ("查看消费总结", True), ("查看统计与目标", False),
    ]
    ys = [88 - i * 4.55 for i in range(len(cases))]
    for (name, ai), y in zip(cases, ys):
        ellipse(ax, 50, y, 40, 3.7, name, 9.2)
        arrow(ax, (10.3, 50.5), (30.0, y), "", lw=0.65)
        if ai:
            arrow(ax, (70.0, y), (89.7, 50.5), "", lw=0.65, dashed=True)

    actor(ax, 8, 50, "普通用户", 11)
    actor(ax, 92, 50, "大模型服务", 11)
    ax.text(92, 39.0, "（外部系统）", ha="center", va="top", fontsize=8.5,
            fontproperties=FONT, color=GRAY)
    ax.text(50, 0.6, "注：虚线表示系统调用外部大模型服务，用户不直接访问模型。",
            ha="center", va="bottom", fontsize=8.5, fontproperties=FONT, color=GRAY)
    save(fig, "图3.1_系统用例图.png")


# ------------------------------------------------------- 图4.1 系统功能结构图
def draw_function_tree():
    fig, ax = canvas(10.2, 8.6)
    box(ax, 50, 94, 38, 6.2, "智能记账与生活便签一体化管理系统", 10.5,
        fill=LIGHT, bold=True)
    modules = [
        ("用户认证", ["用户注册", "用户登录", "自动登录/刷新", "个人中心/密码", "服务器地址"]),
        ("首页总览", ["收支结余", "近 7 日趋势", "AI 消费洞察", "预算进度", "快捷入口"]),
        ("账单管理", ["列表/日历", "账单筛选", "新增/编辑", "删除账单", "分类与渠道"]),
        ("便签待办", ["待办月历", "任务清单", "竖向看板", "生活便签", "六色/优先级"]),
        ("AI 智能助手", ["智能记账", "截图识别", "任务提取", "问账本", "总结/洞察"]),
        ("统计与目标", ["收支统计", "分类/渠道", "预算管理", "储蓄目标", "生活挑战"]),
    ]
    xs = [9.5, 25.6, 41.7, 57.8, 73.9, 90.0]
    ax.plot([xs[0], xs[-1]], [87.5, 87.5], color=INK, lw=1.0)
    ax.plot([50, 50], [90.9, 87.5], color=INK, lw=1.0)
    for x, (name, children) in zip(xs, modules):
        ax.plot([x, x], [87.5, 83.2], color=INK, lw=1.0)
        box(ax, x, 80.2, 14.6, 5.6, name, 9.8, fill=LIGHT, bold=True)
        start_y = 69.5
        step = 8.0
        for i, child in enumerate(children):
            cy = start_y - i * step
            ax.plot([x, x], [77.4, cy + 2.65], color=INK, lw=0.8)
            box(ax, x, cy, 13.8, 5.3, child, 8.3)
    save(fig, "图4.2_系统功能结构图.png")


# ------------------------------------------------------- 图4.2 系统总体架构图
def draw_architecture():
    fig, ax = canvas(9.2, 9.6)
    layers = [
        (90, "用户层", "移动端用户（Android / H5）"),
        (77, "展示层", "uni-app + Vue 3 页面与组件\n路由 / 状态管理 / 请求封装 / 统一交互反馈"),
        (63, "接口层", "FastAPI RESTful API\nJWT 鉴权 · Pydantic 校验 · 统一错误码"),
        (47, "业务服务层", "认证服务 | 账单服务 | 便签服务\n统计服务 | 目标挑战服务 | AI 服务"),
        (31, "数据访问层", "SQLAlchemy ORM 模型与事务\n用户数据隔离 · 聚合查询"),
        (17, "数据层", "MySQL 8.0（生产） / SQLite（开发）\n用户·分类·账单·便签·预算·目标·挑战·AI日志"),
    ]
    for y, name, detail in layers:
        box(ax, 48, y, 62, 10.2, detail, 9.2, fill="white")
        box(ax, 9, y, 14, 10.2, name, 9.5, fill=LIGHT, bold=True)
    for i in range(len(layers) - 1):
        arrow(ax, (48, layers[i][0] - 5.1), (48, layers[i + 1][0] + 5.1), "", lw=1.0)
    box(ax, 90, 47, 17, 15, "外部大模型服务\nOpenAI 兼容 API\n文本模型 / 视觉模型", 8.6,
        fill=LIGHT)
    arrow(ax, (79.2, 47), (80.2, 47), "", lw=1.0, style="<|-|>")
    ax.text(50, 3.0, "图注：箭头表示调用与数据流向；模型密钥仅保存在后端环境变量中。",
            ha="center", va="bottom", fontsize=8.6, fontproperties=FONT, color=GRAY)
    save(fig, "图4.1_系统总体架构图.png")



# ------------------------------------------------------------------ 图4.3 E-R图
def entity_box(ax, cx, cy, w, h, name, attrs, fs=8.6):
    box(ax, cx, cy, w, h, "", 1, fill="white")
    ax.add_patch(Rectangle((cx - w / 2, cy + h / 2 - 4.0), w, 4.0,
                           facecolor=LIGHT, edgecolor=INK, linewidth=1.0, zorder=3))
    ax.text(cx, cy + h / 2 - 2.0, name, ha="center", va="center", fontsize=9.6,
            fontproperties=FONT, color=INK, fontweight="bold", zorder=4)
    ty = cy + h / 2 - 5.2
    for a in attrs:
        ax.text(cx - w / 2 + 1.0, ty, a, ha="left", va="center", fontsize=fs,
                fontproperties=FONT, color=INK, zorder=4)
        ty -= 1.75


def rel(ax, cx, cy, text, w=8.0, h=6.0, fs=8.4):
    diamond(ax, cx, cy, w, h, text, fs)


def draw_er():
    fig, ax = canvas(10.4, 9.2, ylim=(-2, 100))
    title(ax, "系统 E-R 图", 99.5, 14)
    entity_box(ax, 50, 52, 17, 15, "用户",
               ["id (PK)", "username", "password_hash", "nickname", "created_at"])
    entity_box(ax, 20, 82, 16, 13, "账单分类",
               ["id (PK)", "user_id (FK)", "name", "type"])
    entity_box(ax, 80, 82, 18, 15, "账单",
               ["id (PK)", "user_id (FK)", "category_id (FK)", "type / amount",
                "bill_date / source"])
    entity_box(ax, 10, 50, 17, 15, "便签",
               ["id (PK)", "user_id (FK)", "title", "note_type / status",
                "due_at / priority"])
    entity_box(ax, 28, 17, 15, 11, "预算",
               ["id (PK)", "user_id (FK)", "month", "amount"])
    entity_box(ax, 48, 15, 16, 11, "储蓄目标",
               ["id (PK)", "user_id (FK)", "target_amount", "saved_amount"])
    entity_box(ax, 68, 17, 17, 12, "生活挑战",
               ["id (PK)", "user_id (FK)", "category_id (FK)", "period_days", "target_amount"])
    entity_box(ax, 89, 50, 17, 14, "AI 调用日志",
               ["id (PK)", "user_id (FK)", "feature / model", "status / latency",
                "created_at"])

    # 关系菱形与连线
    rel(ax, 35, 67, "创建")
    ax.plot([50, 35], [59.5, 67], color=INK, lw=1.0)
    ax.plot([35, 23], [67, 75.5], color=INK, lw=1.0)
    ax.text(46, 61.5, "1", fontsize=8.5, fontproperties=FONT)
    ax.text(27, 72.5, "N", fontsize=8.5, fontproperties=FONT)

    rel(ax, 65, 67, "记录")
    ax.plot([58.5, 65], [59.5, 67], color=INK, lw=1.0)
    ax.plot([65, 77], [67, 74.5], color=INK, lw=1.0)
    ax.text(60.5, 61.5, "1", fontsize=8.5, fontproperties=FONT)
    ax.text(73, 72.0, "N", fontsize=8.5, fontproperties=FONT)

    rel(ax, 50, 82, "归类", 8, 6)
    ax.plot([28, 46], [82, 82], color=INK, lw=1.0)
    ax.plot([54, 71], [82, 82], color=INK, lw=1.0)
    ax.text(30, 83.3, "1", fontsize=8.5, fontproperties=FONT)
    ax.text(68, 83.3, "N", fontsize=8.5, fontproperties=FONT)

    rel(ax, 31, 51, "编写")
    ax.plot([41.5, 35], [50, 51], color=INK, lw=1.0)
    ax.plot([27, 18.5], [51, 50], color=INK, lw=1.0)
    ax.text(39, 52.2, "1", fontsize=8.5, fontproperties=FONT)
    ax.text(20, 52.2, "N", fontsize=8.5, fontproperties=FONT)

    rel(ax, 38.5, 34, "设置")
    ax.plot([44, 38.5], [44.5, 34], color=INK, lw=1.0)
    ax.plot([38.5, 30], [34, 22.5], color=INK, lw=1.0)
    ax.text(42, 40.5, "1", fontsize=8.5, fontproperties=FONT)
    ax.text(32, 27.0, "N", fontsize=8.5, fontproperties=FONT)

    rel(ax, 49, 33, "设立")
    ax.plot([50, 49], [44.5, 33], color=INK, lw=1.0)
    ax.plot([49, 48], [33, 20.5], color=INK, lw=1.0)
    ax.text(51.3, 40.0, "1", fontsize=8.5, fontproperties=FONT)
    ax.text(50.0, 26.0, "N", fontsize=8.5, fontproperties=FONT)

    rel(ax, 59.5, 34, "发起")
    ax.plot([56, 59.5], [44.5, 34], color=INK, lw=1.0)
    ax.plot([59.5, 66], [34, 23], color=INK, lw=1.0)
    ax.text(56.5, 40.5, "1", fontsize=8.5, fontproperties=FONT)
    ax.text(64, 28.0, "N", fontsize=8.5, fontproperties=FONT)

    rel(ax, 70, 50, "产生")
    ax.plot([58.5, 66], [50, 50], color=INK, lw=1.0)
    ax.plot([74, 80.5], [50, 50], color=INK, lw=1.0)
    ax.text(60, 51.4, "1", fontsize=8.5, fontproperties=FONT)
    ax.text(77.5, 51.4, "N", fontsize=8.5, fontproperties=FONT)

    ax.text(50, -0.5,
            "注：实线为实体间联系，1 与 N 表示联系基数；各实体完整字段见 4.3.2 节数据表。",
            ha="center", va="bottom", fontsize=8.6, fontproperties=FONT, color=GRAY)
    save(fig, "图4.3_系统E-R图.png")


# ------------------------------------------------------------- 时序图公共函数
def lifelines(ax, items, y_top=94, y_bottom=4):
    for x, name in items:
        box(ax, x, y_top, 16.0, 5.0, name, 9.2, fill=LIGHT, bold=True)
        ax.plot([x, x], [y_top - 2.5, y_bottom], color=INK, lw=0.8,
                linestyle=(0, (4, 3)), zorder=0)


def msg(ax, x1, x2, y, text, fs=8.8, dashed=False, self_x=None):
    if self_x is not None:
        # 自调用：小矩形环
        x = self_x
        ax.plot([x, x + 5.5], [y + 1.6, y + 1.6], color=INK, lw=0.9)
        ax.plot([x + 5.5, x + 5.5], [y + 1.6, y - 0.8], color=INK, lw=0.9)
        ax.plot([x + 5.5, x], [y - 0.8, y - 0.8], color=INK, lw=0.9)
        ax.annotate("", xy=(x, y - 0.8), xytext=(x + 2.0, y - 0.8),
                    arrowprops=dict(arrowstyle="-|>", color=INK, lw=0.9,
                                    mutation_scale=8))
        ax.text(x + 6.5, y + 0.4, text, ha="left", va="center", fontsize=fs,
                fontproperties=FONT, color=INK)
        return
    arrow(ax, (x1, y), (x2, y), "", lw=0.9, dashed=dashed)
    ax.text((x1 + x2) / 2, y + 0.8, text, ha="center", va="bottom", fontsize=fs,
            fontproperties=FONT, color=INK,
            bbox=dict(facecolor="white", edgecolor="none", pad=0.4))


def seq_note(ax, x, y, w, h, text, fs=8.4):
    ax.add_patch(Rectangle((x - w / 2, y - h / 2), w, h, facecolor="white",
                           edgecolor=INK, linewidth=0.8, linestyle="--", zorder=3))
    ax.text(x, y, text, ha="center", va="center", fontsize=fs,
            fontproperties=FONT, color=INK, zorder=4, linespacing=1.3)


def draw_seq_login():
    fig, ax = canvas(9.6, 7.8)
    title(ax, "用户认证模块时序图", 99.5, 13.5)
    lifelines(ax, [(8, "用户"), (26, "uni-app 页面"), (45, "FastAPI 路由"),
                   (64, "认证服务"), (84, "数据库")])
    ys = [86, 80.5, 75, 69.5, 64, 58.5, 53, 47.5, 42, 36.5, 31]
    msg(ax, 8, 26, ys[0], "1. 输入用户名与密码")
    msg(ax, None, None, ys[1], "2. 非空与长度校验", self_x=26)
    msg(ax, 26, 45, ys[2], "3. POST /api/auth/login")
    msg(ax, 45, 64, ys[3], "4. 查询用户")
    msg(ax, 64, 84, ys[4], "5. SELECT users")
    msg(ax, 84, 64, ys[5], "6. 返回用户记录")
    msg(ax, None, None, ys[6], "7. PBKDF2 校验密码", self_x=64)
    msg(ax, None, None, ys[7], "8. 签发 access / refresh", self_x=64)
    msg(ax, 64, 45, ys[8], "9. 返回 TokenOut")
    msg(ax, 45, 26, ys[9], "10. 返回用户与令牌")
    msg(ax, None, None, ys[10], "11. 保存令牌并跳转首页", self_x=26)

    ax.add_patch(Rectangle((22, 7), 74, 15, fill=False, edgecolor=INK,
                           linewidth=0.9, linestyle="--"))
    ax.text(23.5, 20.6, "alt  校验失败", fontsize=8.4, fontproperties=FONT,
            va="bottom")
    msg(ax, 64, 45, 16.5, "12. 返回 400 错误码与提示", fs=8.4)
    msg(ax, 45, 26, 12.0, "13. 展示“用户名或密码不正确”", fs=8.4)
    seq_note(ax, 82, 10.0, 15, 5.0, "停留在登录页\n允许重新输入", 8.0)
    save(fig, "图5.1_用户认证模块时序图.png")



def draw_seq_ai_bill():
    fig, ax = canvas(9.8, 8.0)
    title(ax, "AI 自然语言记账时序图", 99.5, 13.5)
    lifelines(ax, [(7, "用户"), (24, "AI 记账页"), (41, "AI 路由"),
                   (58, "AI 服务层"), (75, "大模型服务"), (92, "账单服务")])
    ys = [86, 80.5, 75, 69.5, 64, 58.5, 53, 47.5, 42, 36.5, 31, 25.5, 20, 14.5, 9]
    msg(ax, 7, 24, ys[0], "1. 输入自然语言文本")
    msg(ax, 24, 41, ys[1], "2. POST /api/ai/parse-bill")
    msg(ax, 41, 58, ys[2], "3. 鉴权与每日限流")
    msg(ax, 58, 58, ys[3], "4. 构造提示词（分类白名单）", self_x=58)
    msg(ax, 58, 75, ys[4], "5. POST /chat/completions")
    msg(ax, 75, 58, ys[5], "6. 返回 JSON 文本")
    msg(ax, 58, 58, ys[6], "7. 提取 JSON 并校验字段", self_x=58)
    msg(ax, 58, 41, ys[7], "8. 返回账单草稿")
    msg(ax, 41, 24, ys[8], "9. 返回 ParseBillOut")
    msg(ax, 24, 24, ys[9], "10. 展示可编辑草稿", self_x=24)
    msg(ax, 7, 24, ys[10], "11. 核对并修改金额/分类")
    msg(ax, 24, 92, ys[11], "12. POST /api/bills 确认保存")
    msg(ax, 92, 92, ys[12], "13. 校验并 INSERT bills", self_x=92)
    msg(ax, 92, 24, ys[13], "14. 返回正式账单")
    msg(ax, 24, 24, ys[14], "15. 刷新账单与统计", self_x=24)

    ax.add_patch(Rectangle((40, 2.0), 57, 11.5, fill=False, edgecolor=INK,
                           linewidth=0.9, linestyle="--"))
    ax.text(41.2, 13.0, "alt  超时 / 格式错误", fontsize=8.2, fontproperties=FONT,
            va="bottom")
    ax.text(68.5, 7.6,
            "重试 1 次仍失败 → 提示换说法或手动记账；\n"
            "草稿不直接写入数据库，未确认不产生正式账单。",
            ha="center", va="center", fontsize=7.8, fontproperties=FONT)
    save(fig, "图5.12_AI自然语言记账时序图.png")


def draw_seq_bills():
    fig, ax = canvas(9.4, 7.4)
    title(ax, "账单管理模块时序图", 99.5, 13.5)
    lifelines(ax, [(8, "用户"), (28, "账单页面"), (48, "账单路由"),
                   (68, "业务服务"), (88, "数据库")])
    ys = [86, 80, 74, 68, 62, 56, 50, 44, 38, 32, 26, 20, 14]
    msg(ax, 8, 28, ys[0], "1. 进入账单页并选择月份")
    msg(ax, 28, 48, ys[1], "2. GET /api/bills?month&type&q")
    msg(ax, 48, 68, ys[2], "3. JWT 鉴权")
    msg(ax, 68, 88, ys[3], "4. 按 user_id 查询与分页")
    msg(ax, 88, 68, ys[4], "5. 返回账单与分类")
    msg(ax, 68, 48, ys[5], "6. 组装 BillPageOut")
    msg(ax, 48, 28, ys[6], "7. 返回分页数据")
    msg(ax, 28, 28, ys[7], "8. 渲染列表与汇总", self_x=28)
    msg(ax, 8, 28, ys[8], "9. 新增 / 编辑 / 删除")
    msg(ax, 28, 48, ys[9], "10. POST / PUT / DELETE")
    msg(ax, 48, 68, ys[10], "11. 校验金额、分类与归属")
    msg(ax, 68, 88, ys[11], "12. 写入并提交事务")
    msg(ax, 88, 28, ys[12], "13. 返回结果并刷新列表")

    ax.add_patch(Rectangle((44, 2.0), 54, 9.0, fill=False, edgecolor=INK,
                           linewidth=0.9, linestyle="--"))
    ax.text(45.2, 10.2, "alt  校验失败", fontsize=8.2, fontproperties=FONT, va="bottom")
    ax.text(71, 6.2, "金额越界、分类不存在或跨用户访问 → 400/404，页面提示并保留输入",
            ha="center", va="center", fontsize=7.8, fontproperties=FONT)
    save(fig, "图5.6_账单管理模块时序图.png")


def draw_seq_notes():
    fig, ax = canvas(9.4, 7.4)
    title(ax, "便签与待办模块时序图", 99.5, 13.5)
    lifelines(ax, [(8, "用户"), (28, "便签页面"), (48, "便签路由"),
                   (68, "业务服务"), (88, "数据库")])
    ys = [86, 80, 74, 68, 62, 56, 50, 44, 38, 32, 26, 20, 14]
    msg(ax, 8, 28, ys[0], "1. 新建便签 / 待办")
    msg(ax, 28, 48, ys[1], "2. POST /api/notes")
    msg(ax, 48, 68, ys[2], "3. 参数与归属校验")
    msg(ax, 68, 88, ys[3], "4. INSERT notes")
    msg(ax, 88, 28, ys[4], "5. 返回记录并刷新")
    msg(ax, 28, 48, ys[5], "6. GET /api/notes?view=today")
    msg(ax, 48, 68, ys[6], "7. 组合筛选条件")
    msg(ax, 68, 88, ys[7], "8. 查询并按优先级排序")
    msg(ax, 88, 28, ys[8], "9. 返回分页结果")
    msg(ax, 8, 28, ys[9], "10. 标记完成 / 编辑")
    msg(ax, 28, 48, ys[10], "11. PUT /api/notes/{id}")
    msg(ax, 48, 68, ys[11], "12. 更新状态与截止时间")
    msg(ax, 68, 88, ys[12], "13. UPDATE 并返回最新记录")
    save(fig, "图5.9_便签与待办模块时序图.png")


def draw_seq_ask():
    fig, ax = canvas(9.8, 8.0)
    title(ax, "问账本工具调用时序图", 99.5, 13.5)
    lifelines(ax, [(7, "用户"), (24, "问答页面"), (41, "AI 路由"),
                   (58, "AI 服务层"), (75, "大模型服务"), (92, "数据库")])
    ys = [86, 80, 74, 68, 62, 56, 50, 44, 38, 32, 26, 20]
    msg(ax, 7, 24, ys[0], "1. 输入“本月餐饮花了多少”")
    msg(ax, 24, 41, ys[1], "2. POST /api/ai/ask")
    msg(ax, 41, 58, ys[2], "3. 鉴权与限流")
    msg(ax, 58, 75, ys[3], "4. 提示词一：选择查询工具")
    msg(ax, 75, 58, ys[4], "5. 返回 {tool, params}")
    msg(ax, 58, 58, ys[5], "6. 工具白名单校验", self_x=58)
    msg(ax, 58, 92, ys[6], "7. 执行参数化聚合查询")
    msg(ax, 92, 58, ys[7], "8. 返回统计结果（无明细）")
    msg(ax, 58, 75, ys[8], "9. 提示词二：组织自然语言回答")
    msg(ax, 75, 58, ys[9], "10. 返回 {answer}")
    msg(ax, 58, 41, ys[10], "11. 返回 answer / tool / steps")
    msg(ax, 41, 24, ys[11], "12. 展示回答与数据依据")

    ax.add_patch(Rectangle((38, 2.0), 58, 9.0, fill=False, edgecolor=INK,
                           linewidth=0.9, linestyle="--"))
    ax.text(39.2, 10.2, "alt  不支持 / 超时", fontsize=8.2, fontproperties=FONT,
            va="bottom")
    ax.text(67, 6.2, "返回固定引导话术或 504 提示，不执行越界查询、不返回其他用户数据",
            ha="center", va="center", fontsize=7.8, fontproperties=FONT)
    save(fig, "图5.16_问账本工具调用时序图.png")


# ------------------------------------------------------------- 流程图公共函数
def fc_start(ax, x, y, text, w=24, h=6.2):
    box(ax, x, y, w, h, text, 10.2, rounded=True, fill="white")


def fc_process(ax, x, y, text, w=28, h=7.0, fs=9.8):
    box(ax, x, y, w, h, text, fs, fill="white")


def fc_io(ax, x, y, text, w=28, h=7.0, fs=9.6):
    pts = [(x - w / 2 + 2.2, y + h / 2), (x + w / 2, y + h / 2),
           (x + w / 2 - 2.2, y - h / 2), (x - w / 2, y - h / 2)]
    ax.add_patch(Polygon(pts, closed=True, facecolor="white", edgecolor=INK,
                         linewidth=1.05, zorder=2))
    ax.text(x, y, text, ha="center", va="center", fontsize=fs,
            fontproperties=FONT, color=INK, zorder=3, linespacing=1.3)


def fc_decision(ax, x, y, text, w=24, h=10.0, fs=9.4):
    diamond(ax, x, y, w, h, text, fs)


def fc_end(ax, x, y, text="结束", w=20, h=6.0):
    box(ax, x, y, w, h, text, 10.2, rounded=True, fill=LIGHT)


def branch_label(ax, x, y, text):
    ax.text(x, y, text, ha="center", va="center", fontsize=8.6,
            fontproperties=FONT, color=INK,
            bbox=dict(facecolor="white", edgecolor="none", pad=0.4))


# --------------------------------------------------- 图5.2 登录与注册流程图
def draw_flow_login():
    fig, ax = canvas(8.8, 11.2)
    title(ax, "用户登录与注册流程图", 99.5, 13.5)
    fc_start(ax, 50, 95, "打开应用", 22, 6.0)
    fc_decision(ax, 50, 86, "本地令牌有效？", 22, 9.0)
    fc_process(ax, 80, 86, "进入首页", 18, 6.0)
    fc_end(ax, 80, 76.5, "结束", 16, 5.5)
    fc_process(ax, 50, 76.5, "进入登录页", 24, 6.0, 9.8)
    fc_decision(ax, 50, 67, "是否已有账号？", 23, 9.0)
    fc_process(ax, 24, 57, "填写注册信息\n用户名/昵称/密码", 25, 8.0, 9.2)
    fc_process(ax, 76, 57, "输入用户名与密码", 24, 7.5, 9.2)
    fc_decision(ax, 24, 45, "格式正确且\n两次密码一致？", 25, 10.5, 9.0)
    fc_decision(ax, 76, 45, "非空且长度\n符合要求？", 23, 10.0, 9.0)
    fc_process(ax, 24, 33.5, "POST /api/auth/register", 27, 6.8, 8.8)
    fc_process(ax, 76, 33.5, "POST /api/auth/login", 27, 6.8, 8.8)
    fc_decision(ax, 24, 22, "用户名\n已存在？", 20, 9.0, 9.0)
    fc_decision(ax, 76, 22, "账号存在且\n密码正确？", 24, 10.0, 9.0)
    fc_process(ax, 24, 11, "PBKDF2 哈希\n写入 users 表", 24, 8.0, 8.8)
    fc_process(ax, 76, 11, "签发并保存令牌\n跳转首页", 24, 8.0, 8.8)
    fc_end(ax, 24, 2.0, "提示注册成功\n返回登录页", 24, 6.5)
    fc_end(ax, 76, 2.0, "进入系统", 18, 5.5)

    arrow(ax, (50, 92.0), (50, 90.5))
    arrow(ax, (61.0, 86), (71.0, 86), "是", 8.4)
    arrow(ax, (80, 83.0), (80, 79.3))
    arrow(ax, (50, 81.5), (50, 79.5), "否", 8.4)
    arrow(ax, (50, 73.5), (50, 71.5))
    arrow(ax, (38.5, 67), (36.5, 67), "否", 8.4)
    poly_arrow(ax, [(36.5, 67), (24, 67), (24, 61.0)])
    arrow(ax, (61.5, 67), (64.0, 67), "是", 8.4)
    poly_arrow(ax, [(64.0, 67), (76, 67), (76, 60.8)])

    arrow(ax, (24, 53.0), (24, 50.3))
    arrow(ax, (76, 53.3), (76, 50.0))
    arrow(ax, (24, 39.8), (24, 36.9), "是", 8.4)
    arrow(ax, (76, 40.0), (76, 36.9), "是", 8.4)
    poly_arrow(ax, [(11.5, 45), (6, 45), (6, 57), (11.5, 57)])
    branch_label(ax, 8.5, 46.6, "否")
    poly_arrow(ax, [(88.0, 45), (94, 45), (94, 57), (88.0, 57)])
    branch_label(ax, 91.5, 46.6, "否")

    arrow(ax, (24, 30.1), (24, 26.5))
    arrow(ax, (76, 30.1), (76, 27.0))
    arrow(ax, (24, 17.5), (24, 15.0), "否", 8.4)
    arrow(ax, (76, 17.0), (76, 15.0), "是", 8.4)
    poly_arrow(ax, [(14.0, 22), (6, 22), (6, 33.5), (10.5, 33.5)])
    branch_label(ax, 8.5, 23.5, "是")
    poly_arrow(ax, [(88.0, 22), (94, 22), (94, 33.5), (89.5, 33.5)])
    branch_label(ax, 91.5, 23.5, "否")

    arrow(ax, (24, 7.0), (24, 5.3))
    arrow(ax, (76, 7.0), (76, 4.8))
    save(fig, "图5.2_用户登录与注册流程图.png")


# ------------------------------------------------------- 图5.3 首页总览流程图
def draw_flow_home():
    fig, ax = canvas(10.0, 7.8)
    title(ax, "首页总览流程图", 99.5, 13.5)
    fc_start(ax, 8, 88, "进入首页", 18, 6.0)
    fc_process(ax, 24, 88, "检查登录态", 18, 6.0)
    fc_decision(ax, 42, 88, "令牌有效？", 17, 8.5)
    fc_process(ax, 58, 88, "并行请求统计/预算\n账单/待办/AI洞察", 22, 8.0, 9.2)
    fc_process(ax, 80, 88, "渲染结余/趋势/预算\n快捷入口与提醒", 24, 8.0, 9.2)
    fc_process(ax, 80, 76, "请求 AI 消费洞察", 22, 7.0, 9.2)
    fc_decision(ax, 80, 64, "当日有缓存？", 18, 8.5)
    fc_process(ax, 58, 64, "使用缓存文案", 18, 6.5, 9.0)
    fc_decision(ax, 80, 51, "有数据且\nAI 可用？", 19, 9.0)
    fc_process(ax, 58, 51, "规则降级文案", 18, 6.5, 9.0)
    fc_process(ax, 80, 39, "调用模型生成\n一句话洞察", 20, 8.0, 9.2)
    fc_decision(ax, 80, 27, "调用成功？", 17, 8.5)
    fc_process(ax, 80, 17, "写入当日缓存\n展示洞察卡片", 22, 8.0, 9.0)
    fc_process(ax, 50, 8, "下拉刷新 / 切换月份\n重新请求", 24, 8.0, 9.0)
    fc_end(ax, 20, 8, "结束", 16, 5.5)

    arrow(ax, (17, 88), (15, 88))
    arrow(ax, (33, 88), (33.5, 88))
    arrow(ax, (50.5, 88), (47, 88), "是", 8.4)
    arrow(ax, (58.5, 88), (68, 88))
    arrow(ax, (80, 84), (80, 79.5))
    arrow(ax, (80, 72.5), (80, 68.2))
    arrow(ax, (71, 64), (67, 64), "是", 8.4)
    arrow(ax, (80, 59.8), (80, 55.5))
    arrow(ax, (70.5, 51), (67, 51), "否", 8.4)
    arrow(ax, (80, 46.5), (80, 43))
    arrow(ax, (80, 35), (80, 31.2))
    arrow(ax, (88.5, 27), (92, 27), "否", 8.4)
    poly_arrow(ax, [(92, 27), (94, 27), (94, 51), (89.5, 51)])
    arrow(ax, (80, 22.8), (80, 21))
    arrow(ax, (69, 17), (64, 12), "", 8.4)
    arrow(ax, (58, 64), (50, 64))
    poly_arrow(ax, [(42, 88), (42, 96), (2, 96), (2, 88), (0, 88)])
    branch_label(ax, 44, 94.0, "否")
    ax.text(4, 90.5, "跳转登录页", ha="left", va="bottom", fontsize=8.4,
            fontproperties=FONT)
    arrow(ax, (38, 96), (48, 96))
    ax.text(50, 96.8, "返回登录页", ha="center", va="bottom", fontsize=8.2,
            fontproperties=FONT)
    save(fig, "图5.4_首页总览流程图.png")


# ------------------------------------------------------- 图5.5 账单管理流程图
def draw_flow_bills():
    fig, ax = canvas(10.2, 8.2)
    title(ax, "账单管理流程图", 99.5, 13.5)
    fc_start(ax, 8, 90, "进入账单页", 18, 6.0)
    fc_process(ax, 24, 90, "切换列表/日历\n选择月份/类型", 22, 8.0, 9.2)
    fc_process(ax, 42, 90, "GET /api/bills\n分页查询", 22, 8.0, 9.0)
    fc_process(ax, 60, 90, "JWT 鉴权\n按 user_id 查询", 22, 8.0, 9.0)
    fc_process(ax, 79, 90, "展示列表/日历\n与月度汇总", 22, 8.0, 9.0)
    fc_decision(ax, 50, 78, "选择操作", 19, 8.0)
    fc_process(ax, 17, 66, "填写账单表单\n类型/金额/分类", 20, 8.0, 9.0)
    fc_process(ax, 50, 66, "选择已有账单\n修改字段", 20, 7.0, 9.0)
    fc_process(ax, 83, 66, "选择账单\n二次确认", 20, 7.0, 9.0)
    fc_decision(ax, 17, 54, "校验通过？", 17, 8.0)
    fc_decision(ax, 50, 54, "归属正确？", 17, 8.0)
    fc_decision(ax, 83, 54, "确认删除？", 17, 8.0)
    fc_process(ax, 17, 42, "POST /api/bills\n新增账单", 20, 7.5, 9.0)
    fc_process(ax, 50, 42, "PUT /api/bills/{id}\n更新账单", 21, 7.5, 9.0)
    fc_process(ax, 83, 42, "DELETE /api/bills/{id}\n删除账单", 21, 7.5, 9.0)
    fc_process(ax, 17, 30, "INSERT 并提交", 19, 6.5, 9.0)
    fc_process(ax, 50, 30, "UPDATE 并提交", 19, 6.5, 9.0)
    fc_process(ax, 83, 30, "DELETE 并提交", 19, 6.5, 9.0)
    fc_process(ax, 50, 18, "刷新列表与汇总", 22, 6.5, 9.2)
    fc_end(ax, 50, 7, "结束", 16, 5.5)
    fc_process(ax, 5, 54, "提示\n保留输入", 9, 6.0, 8.6)
    fc_process(ax, 38, 54, "提示\n无权访问", 9, 6.0, 8.6)
    fc_process(ax, 96, 54, "取消", 8, 5.5, 8.8)

    arrow(ax, (17, 90), (13, 90))
    arrow(ax, (35, 90), (31, 90))
    arrow(ax, (53, 90), (49, 90))
    arrow(ax, (71, 90), (68, 90))
    poly_arrow(ax, [(79, 86), (79, 84), (61, 84), (58.5, 80)])
    arrow(ax, (42, 78), (27, 78))
    poly_arrow(ax, [(42, 78), (17, 78), (17, 70)])
    arrow(ax, (50, 74), (50, 69.5))
    arrow(ax, (58.5, 78), (83, 78))
    poly_arrow(ax, [(58.5, 78), (83, 78), (83, 69.5)])
    arrow(ax, (17, 62), (17, 58))
    arrow(ax, (50, 62.5), (50, 58))
    arrow(ax, (83, 62.5), (83, 58))
    arrow(ax, (17, 50), (17, 45.8), "是", 8.4)
    arrow(ax, (50, 50), (50, 45.8), "是", 8.4)
    arrow(ax, (83, 50), (83, 45.8), "是", 8.4)
    arrow(ax, (8.5, 54), (5.5, 54), "否", 8.2)
    arrow(ax, (41.5, 54), (42.5, 54), "否", 8.2)
    arrow(ax, (91.5, 54), (92, 54), "否", 8.2)
    arrow(ax, (17, 38.2), (17, 33.2))
    arrow(ax, (50, 38.2), (50, 33.2))
    arrow(ax, (83, 38.2), (83, 33.2))
    arrow(ax, (17, 26.8), (17, 21.2))
    arrow(ax, (50, 26.8), (50, 21.2))
    arrow(ax, (83, 26.8), (83, 21.2))
    arrow(ax, (50, 14.8), (50, 9.8))
    save(fig, "图5.7_账单管理流程图.png")


# --------------------------------------------------- 图5.7 便签与待办流程图
def draw_flow_notes():
    fig, ax = canvas(10.2, 8.2)
    title(ax, "便签与待办流程图", 99.5, 13.5)
    fc_start(ax, 8, 90, "进入便签页", 18, 6.0)
    fc_process(ax, 24, 90, "切换待办/便签\n月历/清单/看板", 22, 8.0, 9.0)
    fc_process(ax, 42, 90, "GET /api/notes\n组合筛选", 22, 8.0, 9.0)
    fc_process(ax, 60, 90, "按置顶/截止时间\n优先级排序", 22, 8.0, 9.0)
    fc_process(ax, 79, 90, "展示便签与\n待办列表", 21, 8.0, 9.2)
    fc_decision(ax, 50, 78, "选择操作", 19, 8.0)
    fc_process(ax, 17, 66, "新建便签/待办\n标题/类型/截止", 21, 8.0, 9.0)
    fc_process(ax, 50, 66, "编辑内容或\n标记完成", 20, 7.0, 9.0)
    fc_process(ax, 83, 66, "选择记录\n二次确认", 20, 7.0, 9.0)
    fc_decision(ax, 17, 54, "参数合法？", 17, 8.0)
    fc_decision(ax, 50, 54, "归属正确？", 17, 8.0)
    fc_decision(ax, 83, 54, "确认删除？", 17, 8.0)
    fc_process(ax, 17, 42, "POST /api/notes\n新建记录", 20, 7.5, 9.0)
    fc_process(ax, 50, 42, "PUT /api/notes/{id}\n更新状态/字段", 22, 7.5, 9.0)
    fc_process(ax, 83, 42, "DELETE /api/notes/{id}\n删除记录", 21, 7.5, 9.0)
    fc_process(ax, 17, 30, "INSERT 并提交", 19, 6.5, 9.0)
    fc_process(ax, 50, 30, "UPDATE 并提交", 19, 6.5, 9.0)
    fc_process(ax, 83, 30, "DELETE 并提交", 19, 6.5, 9.0)
    fc_process(ax, 50, 18, "刷新列表与\n未完成计数", 21, 7.0, 9.0)
    fc_end(ax, 50, 7, "结束", 16, 5.5)
    fc_process(ax, 5, 54, "提示\n补充信息", 9, 6.0, 8.6)
    fc_process(ax, 38, 54, "提示\n无权访问", 9, 6.0, 8.6)
    fc_process(ax, 96, 54, "取消", 8, 5.5, 8.8)

    arrow(ax, (17, 90), (13, 90))
    arrow(ax, (35, 90), (31, 90))
    arrow(ax, (53, 90), (49, 90))
    arrow(ax, (71, 90), (68.5, 90))
    poly_arrow(ax, [(79, 86), (79, 84), (61, 84), (58.5, 80)])
    arrow(ax, (42, 78), (27, 78))
    poly_arrow(ax, [(42, 78), (17, 78), (17, 70)])
    arrow(ax, (50, 74), (50, 69.5))
    arrow(ax, (58.5, 78), (83, 78))
    poly_arrow(ax, [(58.5, 78), (83, 78), (83, 69.5)])
    arrow(ax, (17, 62), (17, 58))
    arrow(ax, (50, 62.5), (50, 58))
    arrow(ax, (83, 62.5), (83, 58))
    arrow(ax, (17, 50), (17, 45.8), "是", 8.4)
    arrow(ax, (50, 50), (50, 45.8), "是", 8.4)
    arrow(ax, (83, 50), (83, 45.8), "是", 8.4)
    arrow(ax, (8.5, 54), (5.5, 54), "否", 8.2)
    arrow(ax, (41.5, 54), (42.5, 54), "否", 8.2)
    arrow(ax, (91.5, 54), (92, 54), "否", 8.2)
    arrow(ax, (17, 38.2), (17, 33.2))
    arrow(ax, (50, 38.2), (50, 33.2))
    arrow(ax, (83, 38.2), (83, 33.2))
    arrow(ax, (17, 26.8), (17, 21.2))
    arrow(ax, (50, 26.8), (50, 21.2))
    arrow(ax, (83, 26.8), (83, 21.2))
    arrow(ax, (50, 14.5), (50, 9.8))
    save(fig, "图5.10_便签与待办流程图.png")


# ----------------------------------------------- 图5.9 AI 自然语言记账流程图
def draw_flow_ai():
    fig, ax = canvas(8.8, 12.0, ylim=(-4, 100))
    title(ax, "AI 自然语言记账流程图", 99.5, 13.5)
    fc_start(ax, 55, 96, "用户输入文本或上传截图")
    fc_process(ax, 55, 89, "前端非空与格式校验", 28, 6.2)
    fc_decision(ax, 55, 80, "输入有效？", 19, 8.5)
    fc_process(ax, 55, 70, "JWT 鉴权 + 每日限流", 28, 6.2)
    fc_decision(ax, 55, 61, "通过？", 16, 8.0)
    fc_process(ax, 55, 51, "构造文本/视觉提示词\n注入分类白名单", 28, 8.0)
    fc_process(ax, 55, 42, "调用大模型（30s 超时）", 30, 6.2)
    fc_decision(ax, 55, 33, "调用成功？", 19, 8.5)
    fc_process(ax, 55, 23, "提取 JSON\nPydantic 字段校验", 28, 8.0)
    fc_decision(ax, 55, 14, "输出合法？", 19, 8.5)
    fc_process(ax, 55, 5, "生成可编辑草稿\n用户核对确认", 28, 8.0)
    fc_decision(ax, 55, -3.5, "确认保存？", 19, 7.5)

    fc_process(ax, 20, 80, "提示\n重新输入", 14, 6.0, 8.6)
    fc_process(ax, 82, 61, "返回 429/503\n提示稍后重试", 18, 7.5, 8.2)
    fc_process(ax, 82, 51, "切换手动记账", 18, 6.2, 8.6)
    fc_process(ax, 22, 33, "重试 1 次", 15, 6.0, 8.8)
    fc_decision(ax, 22, 23, "仍失败？", 16, 8.0)
    fc_process(ax, 8, 23, "降级提示\n改用手动记账", 12, 7.5, 7.6)
    fc_process(ax, 82, 14, "提示未识别\n换一种说法", 18, 7.5, 8.2)
    fc_process(ax, 82, -3.5, "取消本次草稿", 18, 6.5, 8.6)

    arrow(ax, (55, 92.9), (55, 92.1))
    arrow(ax, (55, 85.9), (55, 84.3))
    arrow(ax, (55, 75.8), (55, 73.1), "是", 8.4)
    arrow(ax, (45.5, 80), (34.5, 80), "否", 8.2)
    poly_arrow(ax, [(20, 77), (20, 74), (40, 74), (40, 89), (41, 89)])
    arrow(ax, (55, 67.9), (55, 65.0))
    arrow(ax, (63, 61), (73, 61), "否", 8.2)
    arrow(ax, (82, 57.2), (82, 54.2))
    arrow(ax, (82, 47.9), (82, 45), "", 8.2)
    poly_arrow(ax, [(82, 45), (82, 39), (97, 39), (97, 30), (95, 30)])
    arrow(ax, (55, 57.9), (55, 55.0), "是", 8.4)
    arrow(ax, (55, 47.9), (55, 45.1))
    arrow(ax, (55, 38.9), (55, 37.2))
    arrow(ax, (55, 29.3), (55, 27.0), "是", 8.4)
    arrow(ax, (45.5, 33), (34, 33), "否", 8.2)
    arrow(ax, (22, 30), (22, 27.0))
    arrow(ax, (30, 23), (14.6, 23), "是", 8.2)
    poly_arrow(ax, [(14, 23), (14, 42), (40, 42)])
    arrow(ax, (22, 19), (22, 12), "否", 8.2)
    poly_arrow(ax, [(22, 12), (22, 9), (40, 9)])
    arrow(ax, (55, 18.8), (55, 17.2))
    arrow(ax, (55, 9.8), (55, 9.0), "是", 8.4)
    arrow(ax, (64.5, 14), (73, 14), "否", 8.2)
    arrow(ax, (82, 10.2), (82, 0.8), "", 8.2)
    arrow(ax, (55, 0.8), (55, -1.8), "是", 8.4)
    arrow(ax, (64.5, -3.5), (73, -3.5), "否", 8.2)
    poly_arrow(ax, [(82, -3.5), (97, -3.5), (97, -8), (55, -8)])
    ax.text(55, -7.2, "保存成功 → 刷新账单与统计", ha="center", va="bottom",
            fontsize=8.2, fontproperties=FONT)
    save(fig, "图5.13_AI自然语言记账流程图.png")


# ------------------------------------------------------- 图5.11 统计分析流程图
def draw_flow_stats():
    fig, ax = canvas(8.6, 10.4)
    title(ax, "统计分析流程图", 99.5, 13.5)
    fc_start(ax, 50, 95, "进入统计页")
    fc_process(ax, 50, 87, "选择统计月份", 24, 6.2)
    fc_process(ax, 50, 78, "并行请求月度/分类/渠道\nGET /api/statistics/*", 30, 8.0, 9.2)
    fc_process(ax, 50, 68, "后端 SQL 分组聚合", 26, 6.2)
    fc_decision(ax, 50, 58, "有数据？", 18, 8.5)
    fc_process(ax, 78, 58, "空状态提示\n引导先记账", 18, 7.5, 8.4)
    fc_process(ax, 50, 46, "绘制每日柱状图\n分类/渠道环形图", 28, 8.0, 9.0)
    fc_process(ax, 50, 36, "设置月度预算\nPUT /api/budgets", 26, 7.5, 9.0)
    fc_process(ax, 50, 27, "计算预算使用率\n与剩余额度", 24, 7.5, 9.0)
    fc_process(ax, 50, 18, "计算储蓄目标进度\n与生活挑战完成度", 28, 8.0, 9.0)
    fc_process(ax, 50, 9, "更新图表与提示", 22, 6.2)
    fc_end(ax, 50, 1, "结束", 16, 5.5)
    fc_end(ax, 78, 46, "结束", 14, 5.5)

    arrow(ax, (50, 91.8), (50, 90.1))
    arrow(ax, (50, 83.9), (50, 82.0))
    arrow(ax, (50, 74.0), (50, 71.1))
    arrow(ax, (50, 64.9), (50, 62.3))
    arrow(ax, (50, 53.8), (50, 50.0), "是", 8.4)
    arrow(ax, (59, 58), (69, 58), "否", 8.2)
    arrow(ax, (78, 54.2), (78, 48.8))
    arrow(ax, (50, 42.0), (50, 39.8))
    arrow(ax, (50, 32.2), (50, 30.8))
    arrow(ax, (50, 23.2), (50, 22.0))
    arrow(ax, (50, 14.0), (50, 12.1))
    arrow(ax, (50, 5.9), (50, 3.8))
    save(fig, "图5.17_统计分析流程图.png")


if __name__ == "__main__":
    draw_usecase()
    draw_function_tree()
    draw_architecture()
    draw_er()
    draw_seq_login()
    draw_seq_ai_bill()
    draw_seq_bills()
    draw_seq_notes()
    draw_seq_ask()
    draw_flow_login()
    draw_flow_home()
    draw_flow_bills()
    draw_flow_notes()
    draw_flow_ai()
    draw_flow_stats()
