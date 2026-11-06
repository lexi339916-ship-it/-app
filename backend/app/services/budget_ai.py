"""预算预警模块的 AI 能力：提示词构建、结构化输出校验、文案生成与降级。

设计原则：
- 复用 ai_service 的 chat_json / log_call / 限流，模型配置只在 config；
- 所有 AI 输出都经 JSON 校验；AI 不可用时由路由层降级为模板文案，
  保证预警功能不依赖大模型可用性；
- 刚性支出（住房/医疗/通讯/学习）与弹性支出（餐饮/娱乐/购物等）区分文案。
"""
import json
import time
from decimal import Decimal

from sqlalchemy.orm import Session

from app.services import ai_service
from app.services.ai_service import AIServiceError

PROMPT_VERSION = "budget-v1.0"

# 刚性必要支出分类（提示语更温和、不建议压缩）；其余视为弹性/冲动消费空间更大
RIGID_CATEGORIES = {"住房", "医疗", "通讯", "学习"}


def is_rigid(category: str) -> bool:
    """判断分类是否属于刚性必要支出。"""
    return category in RIGID_CATEGORIES


# ---------------- 模板文案（AI 不可用时的降级方案，语气保持柔和） ----------------

def tpl_budget_80(category: str, spent: Decimal, remaining: Decimal) -> tuple[str, str, str]:
    """80% 提醒模板：展示已花与剩余额度。"""
    title = f"「{category}」预算用了八成啦"
    message = f"这个月{category}已花 ¥{spent:.2f}，还剩 ¥{remaining:.2f} 额度。"
    suggestion = "后面稍微留意一下这一类开销，就能稳稳守住预算～"
    return title, message, suggestion


def tpl_budget_100(category: str, spent: Decimal, over: Decimal) -> tuple[str, str, str]:
    """100% 超支强提醒模板。"""
    title = f"「{category}」预算超支了"
    message = f"这个月{category}已花 ¥{spent:.2f}，超出预算 ¥{over:.2f}。"
    suggestion = ("这类是必要支出，超了也没关系，下月可以把预算调高一点。"
                  if is_rigid(category) else
                  "接下来几天这类开销可以先缓一缓，月底再看会轻松些。")
    return title, message, suggestion


def tpl_anomaly(category: str, amount: Decimal, avg: Decimal) -> tuple[str, str, str]:
    """异常大额模板：对比该分类历史单笔均值。"""
    title = f"这笔{category}开销有点大哦"
    message = (f"刚刚这笔 ¥{amount:.2f}，比你以往{category}单笔平均 "
               f"¥{avg:.2f} 高不少，属于异常大额支出。")
    suggestion = ("如果是必要的东西就不用纠结，记得心里有数就好。"
                  if is_rigid(category) else
                  "如果是一时心动，不妨想想它是不是真的需要～")
    return title, message, suggestion


# ---------------- AI 文案生成（失败抛 AIServiceError，由路由层降级） ----------------

async def gen_alert_copy(db: Session, *, user_id: int, feature: str,
                         context: dict) -> dict:
    """让 AI 把预警数据组织成柔和文案。

    context 含 type/category/amount/spent/remaining/avg 等字段。
    返回 {"title":..., "message":..., "suggestion":...}。
    """
    started = time.perf_counter()
    messages = [
        {"role": "system", "content": """你是记账应用的温柔提醒助手。根据给出的预警数据，生成一段柔和的提醒文案。
只输出一个 JSON 对象：{"title": "不超过14字", "message": "不超过60字，必须包含给出的真实数字", "suggestion": "不超过40字的一条小建议"}
要求：
1. 语气像朋友轻声提醒，不说教、不指责、不制造焦虑；不用感叹号连用。
2. 只能使用给出的数字，不得编造。
3. 若分类属于住房/医疗/通讯/学习等必要支出，建议方向是"理解、下月调整预算"；其余分类建议方向是"缓一缓、想一想是否需要"。"""},
        {"role": "user", "content": f"预警数据：{json.dumps(context, ensure_ascii=False)}"},
    ]
    result = await ai_service.chat_json(messages)
    ai_service.log_call(db, user_id=user_id, feature=feature, status="success",
                        latency_ms=int((time.perf_counter() - started) * 1000),
                        input_chars=len(json.dumps(context, ensure_ascii=False)))
    # 校验字段完整性，缺字段视为失败走模板
    if not all(isinstance(result.get(k), str) and result[k] for k in ("title", "message")):
        raise AIServiceError(502, "AI 文案字段不完整")
    return {
        "title": str(result["title"])[:60],
        "message": str(result["message"])[:300],
        "suggestion": str(result.get("suggestion", ""))[:300],
    }


# ---------------- AI 预算推荐 / 目标分配 ----------------

def _history_text(history: list[dict]) -> str:
    """把分类历史月均支出格式化为提示词文本。"""
    if not history:
        return "（该用户暂无历史账单，是新手）"
    return "、".join(
        f"{h['category']} 月均{h['avg_monthly']}元（{h['months']}个月）" for h in history)


async def recommend_budget(db: Session, *, user_id: int, month: str,
                           history: list[dict], avg_income: Decimal,
                           categories: list[dict]) -> dict:
    """根据历史消费推荐初始预算方案。

    history: [{"category":.., "avg_monthly":.., "months":..}]
    返回 {"items":[{"category":..,"amount":..,"reason":..}], "comment":..}
    """
    started = time.perf_counter()
    cat_names = "、".join(c["name"] for c in categories)
    messages = [
        {"role": "system", "content": f"""你是记账应用的预算规划师。根据用户历史消费数据，为 {month} 推荐一套分类月预算。
历史数据：{_history_text(history)}
近3个月平均月收入：{avg_income} 元。
可分配的分类白名单：{cat_names}

只输出一个 JSON 对象：
{{"items": [{{"category": "分类名", "amount": 数字, "reason": "不超过20字的分配理由"}}], "comment": "不超过50字的方案总说明"}}
规则：
1. 分类必须来自白名单；amount 为正数，取整到十位数。
2. 有历史的分类参考历史均值上浮 10%~20% 作为预算；没历史的常见分类给保守默认值。
3. 总额不要超过平均月收入的 90%，要给人留存钱空间。
4. 只使用给出的数据，不编造收入或开销。"""},
        {"role": "user", "content": f"请为 {month} 推荐一套预算方案。"},
    ]
    result = await ai_service.chat_json(messages)
    ai_service.log_call(db, user_id=user_id, feature="budget_recommend", status="success",
                        latency_ms=int((time.perf_counter() - started) * 1000),
                        input_chars=len(_history_text(history)))
    if not isinstance(result.get("items"), list) or not result["items"]:
        raise AIServiceError(502, "AI 预算方案格式不完整")
    return result


async def allocate_by_goal(db: Session, *, user_id: int, month: str,
                           goal_text: str, history: list[dict],
                           avg_income: Decimal, categories: list[dict]) -> dict:
    """自然语言存钱目标 → AI 分配各分类预算。

    返回 {"income_estimate":.., "save_target":.., "items":[...], "comment":..}
    """
    started = time.perf_counter()
    cat_names = "、".join(c["name"] for c in categories)
    messages = [
        {"role": "system", "content": f"""你是记账应用的预算规划师。用户说了一句话描述存钱目标，请结合历史消费，为 {month} 分配各分类预算。
用户原话：「{goal_text}」
历史数据：{_history_text(history)}
近3个月平均月收入：{avg_income} 元。
可分配的分类白名单：{cat_names}

只输出一个 JSON 对象：
{{"income_estimate": 数字, "save_target": 数字, "items": [{{"category": "分类名", "amount": 数字, "reason": "不超过20字"}}], "comment": "不超过50字，说明方案如何实现目标"}}
规则：
1. 从原话中理解想存多少钱/什么目标；save_target 为每月想存的金额，原话没明说就按收入的 20% 估。
2. income_estimate 优先用给出的平均收入；各分类预算合计 = income_estimate - save_target。
3. 分类必须来自白名单；amount 为正数，取整到十位数。
4. 压缩预算时优先压缩餐饮/娱乐/购物等弹性支出；住房/医疗/通讯/学习等必要支出参考历史均值保留。
5. 只使用给出的数据，不编造。"""},
        {"role": "user", "content": f"请根据我的目标分配 {month} 的预算。"},
    ]
    result = await ai_service.chat_json(messages)
    ai_service.log_call(db, user_id=user_id, feature="budget_goal", status="success",
                        latency_ms=int((time.perf_counter() - started) * 1000),
                        input_chars=len(goal_text) + len(_history_text(history)))
    if not isinstance(result.get("items"), list) or not result["items"]:
        raise AIServiceError(502, "AI 预算分配格式不完整")
    return result


# ---------------- 弹性调度建议文案 ----------------

async def gen_rebalance_copy(db: Session, *, user_id: int, context: dict) -> str:
    """为结余→紧缺调配生成一句柔和建议（区分刚性/冲动消费）。失败时调用方用模板。"""
    started = time.perf_counter()
    messages = [
        {"role": "system", "content": """你是记账应用的预算调度助手。用户某分类预算快超支，另一分类有结余。
只输出 JSON：{"message": "不超过60字的建议"}
硬性要求：
1. 方向绝对不能写反：是从 from_category（有结余的分类）调 amount 元额度到 to_category（快超支的分类）。
2. 不得鼓励在快超支的 to_category 上继续多花钱。
3. 语气像朋友商量，用"要不要""可以呀"这类商量口吻；
   若超支分类是住房/医疗/通讯/学习等必要支出，口吻偏向理解与支持；
   若是餐饮/娱乐/购物等弹性支出，顺带轻轻提醒一句这类开销可以留意。"""},
        {"role": "user", "content": f"调度数据：{json.dumps(context, ensure_ascii=False)}"},
    ]
    result = await ai_service.chat_json(messages)
    ai_service.log_call(db, user_id=user_id, feature="budget_rebalance", status="success",
                        latency_ms=int((time.perf_counter() - started) * 1000),
                        input_chars=len(json.dumps(context, ensure_ascii=False)))
    if not isinstance(result.get("message"), str) or not result["message"]:
        raise AIServiceError(502, "AI 调度文案不完整")
    return result["message"][:300]


# ---------------- 计划采购识别与资金压力预判 ----------------

async def parse_planned_purchases(db: Session, *, user_id: int,
                                  todos: list[dict], categories: list[str]) -> list[dict]:
    """从未完成待办中识别计划大额采购，并估算金额与分类。

    todos: [{"id":..,"title":..,"content":..,"due_at":..}]
    返回 [{"note_id":..,"estimated_amount":数字或null,"category":"分类名"}]
    """
    started = time.perf_counter()
    brief = [{"id": t["id"], "title": t["title"], "content": t["content"][:100]}
             for t in todos]
    messages = [
        {"role": "system", "content": f"""你是记账应用的计划采购识别器。下面是用户的未完成待办清单。
请找出其中"计划购买/采购类"的待办（含买、入手、换、购置等意图），并估算金额。
待办清单：{json.dumps(brief, ensure_ascii=False)}
分类白名单：{'、'.join(categories)}

只输出一个 JSON 对象：
{{"purchases": [{{"note_id": 数字, "estimated_amount": 数字或null, "category": "分类名"}}]}}
规则：
1. 只有明确购买意图的待办才入选；纯事项（如"开会""交作业"）不选。
2. 待办里写了金额就用写的；没写就按常识估一个市场参考价，估不出用 null。
3. category 必须从白名单选，都不合适用"购物"。
4. 没有采购类待办时返回 {{"purchases": []}}。"""},
        {"role": "user", "content": "请识别其中的计划采购。"},
    ]
    result = await ai_service.chat_json(messages)
    ai_service.log_call(db, user_id=user_id, feature="planned_purchase", status="success",
                        latency_ms=int((time.perf_counter() - started) * 1000),
                        input_chars=len(json.dumps(brief, ensure_ascii=False)))
    purchases = result.get("purchases")
    return purchases if isinstance(purchases, list) else []


async def gen_pressure_copy(db: Session, *, user_id: int, context: dict) -> str:
    """计划采购资金压力预判文案。失败时调用方用模板。"""
    started = time.perf_counter()
    messages = [
        {"role": "system", "content": """你是记账应用的贴心助手。用户待办里有计划采购，结合本月预算剩余情况给出一句预判提示。
只输出 JSON：{"message": "不超过70字"}
要求：语气温和，说明这笔计划开销大概占本月剩余预算的比例、会不会造成压力；不阻止消费，只提醒提前规划。"""},
        {"role": "user", "content": f"数据：{json.dumps(context, ensure_ascii=False)}"},
    ]
    result = await ai_service.chat_json(messages)
    ai_service.log_call(db, user_id=user_id, feature="purchase_pressure", status="success",
                        latency_ms=int((time.perf_counter() - started) * 1000),
                        input_chars=len(json.dumps(context, ensure_ascii=False)))
    if not isinstance(result.get("message"), str) or not result["message"]:
        raise AIServiceError(502, "AI 预判文案不完整")
    return result["message"][:300]
