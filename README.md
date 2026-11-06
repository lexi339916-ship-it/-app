# 知账 · 家庭消费健康 Agent

> 从记一笔，到做对下一步。

知账是一个面向个人与两人小家庭的消费健康智能体：把散落在微信、支付宝、银行卡、截图、CSV 和待办里的消费信息，变成可解释的预算计划、可审批的行动和可复盘的改进。

当前版本：**v2.0.0**

## 核心能力

- **感知**：自然语言、支付截图/小票、CSV、订阅、待办、语音输入（需配置 ASR）。
- **记忆**：消费偏好、目标、商户→分类纠正、历史决策。
- **规划**：把“3 个月存 3000”拆成月度预算、储蓄目标和每周复盘任务。
- **行动**：读写工具分离；写操作先出 diff，用户批准后才执行。
- **反思**：执行后回查数据库；偏离时重规划；支持撤销。
- **主动**：预算超支、订阅涨价/低频、目标延期、消费变化、异常大额、计划采购。
- **可解释**：数字来自 SQL/工具，带来源、公式、`as_of`；不展示模型原始思维链。

## 三个英雄场景

1. 一句话/截图记账 → 预算冲击 → 审批 → 执行 → 撤销。
2. 订阅体检 → 拒绝原方案 → 替代方案 → 审批。
3. 目标规划 → 预算/任务 → 执行 → 周复盘。

## 技术栈

- 后端：Python 3.10+、FastAPI、SQLAlchemy 2、Pydantic 2、SQLite（开发）/ MySQL 8（生产）。
- 前端：uni-app、Vue 3 `<script setup>`、H5/App。
- AI：OpenAI 兼容接口；账单解析优先模型，失败/未配置自动降级为规则；预算、目标、订阅、健康、模拟全部由后端计算。

## 快速开始

```bash
# 后端
cd backend
pip install -r requirements.txt
cp .env.example .env       # 填写 AI_BASE_URL / AI_API_KEY / AI_MODEL / JWT_SECRET
uvicorn app.main:app --host 127.0.0.1 --port 8000

# 前端 H5（同源代理，静态 + /api 反代）
cd ..
python deploy/proxy_server.py --port 8080 --backend http://127.0.0.1:8000
```

访问 `http://127.0.0.1:8080`，演示账号：

- 用户名：`judge_demo`
- 密码：`judge2026`

重置演示数据：

```bash
python tools/seed_demo.py
```

## 目录结构

```text
backend/            FastAPI 后端（Agent、账单、预算、目标、订阅、健康、模拟、CSV、通知）
frontend/           uni-app 前端（首页、Agent、消息、预算、健康、模拟、导入、我的）
database/schema.sql MySQL 8 初始化脚本
deploy/             Docker/Nginx/同源代理/公网验收脚本
tests/              冒烟、Agent、健康、通知、头像、CSV、评测
docs/competition/   评测报告、审查记录、比赛材料
tools/              演示数据、H5 构建、交付检查、PPT 构建
```

## 测试

```bash
python tests/smoke_test.py
python tests/agent_smoke.py
python tests/agent_eval/run_flow_eval.py
python tests/agent_eval/run_eval.py --split all
python tests/health_report_test.py
python tests/notifications_test.py
python tests/avatar_test.py
python tests/bills_filter_test.py
python tests/csv_import_test.py
```

评测报告：`tests/agent_eval/report.md`、`report_test.md`、`flow_report.md`、`multi_turn_report.md`、`decision_simulator_report.md`、`csv_import_report.md`。

## 安全边界

- 不使用真实银行/支付宝/微信账号，演示数据为合成数据。
- 不做自动转账、投资建议、代客理财。
- 写操作必须审批；审批幂等；执行后回查；支持撤销与审计。
- 敏感文本脱敏；语音/截图不在服务端长期保存。
- `.env`、数据库、`node_modules`、构建缓存不进入仓库。

## 已知限制

- 通知为两套源表（预算预警 + Agent 通知）的聚合读模型，物理单表迁移尚未做。
- 语音真实 ASR/麦克风链路需外部配置与真机验证。
- 消费决策模拟基于历史结余估算，不代表账户真实余额。
- CSV 覆盖常见微信/支付宝/通用表格，特殊银行格式未覆盖。
