"""应用版本与品牌信息的唯一来源。

后端 FastAPI、健康检查、Agent health 都从这里读取版本，避免多处写死。
前端对应文件：frontend/common/app-info.js。
"""

APP_NAME = "知账 · 家庭消费健康 Agent"
APP_SHORT_NAME = "知账"
APP_VERSION = "2.0.0"
API_SERVICE_NAME = "zhizhang-api"
AGENT_SERVICE_NAME = "zhizhang-agent"
DESCRIPTION = (
    "知账是面向个人与两人小家庭的消费健康 Agent："
    "支持自然语言/截图/CSV 记账、预算与订阅体检、储蓄目标规划、"
    "消费健康诊断、决策模拟，以及带审批、审计、撤销的多步行动。"
)
