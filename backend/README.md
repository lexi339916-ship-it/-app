# FastAPI 后端

## 运行

1. Python 3.10+，建议使用虚拟环境：
   ```bash
   python -m venv .venv
   .venv\Scripts\activate
   pip install -r requirements.txt
   ```
2. 开发模式直接启动（默认 SQLite，自动建表并写入系统预置分类）：
   ```bash
   uvicorn app.main:app --reload --port 8000
   ```
3. 打开 `http://127.0.0.1:8000/docs` 查看接口文档。

## 配置

复制 `.env.example` 为 `.env`：

- `DATABASE_URL`：默认 SQLite；正式部署改为 `mysql+pymysql://...` 并先导入 `database/schema.sql`
- `JWT_SECRET`：生产环境必须替换为长随机串
- `AI_BASE_URL / AI_API_KEY / AI_MODEL`：OpenAI 兼容接口；未配置时 AI 接口 503，规则/确定性功能不受影响
- `AI_DAILY_LIMIT`：每用户每日调用上限
- `ASR_BASE_URL / ASR_API_KEY`：可选语音转写

## 模块结构

```text
app/
├── main.py           # 入口、路由注册、统一错误、启动建表/迁移/种子分类
├── version.py        # 品牌、版本 2.1.0、服务名、介绍
├── config.py         # 环境变量
├── database.py       # SQLAlchemy 2 引擎/会话
├── models.py         # 用户、账单、预算、目标、订阅、Agent、通知等表
├── schemas.py        # Pydantic 契约
├── security.py       # PBKDF2 + JWT
├── deps.py           # get_db / get_current_user
├── routers/          # auth/agent/ai/bills/budget-center/goals/subscriptions/health/simulator/imports/notifications...
└── services/
    ├── agent/        # orchestrator/tools/policy/trace
    ├── ai_service.py # 模型调用、提示词、JSON 校验、限流、日志、脱敏
    ├── health_service.py
    ├── decision_simulator.py
    ├── csv_import.py
    └── notification_service.py
```

## 设计要点

- **认证与隔离**：JWT Bearer；所有业务接口按 `user_id` 过滤，跨用户 404。
- **Agent 写操作**：`propose → approve → execute → verify → audit → undo`；
  审批幂等，执行后回查数据库，支持撤销。
- **会话**：`agent_runs.session_id/parent_run_id/turn_index` 保存多轮；历史会话支持标题/预览、继续与软删除（`agent_session_archives`），审计轨迹不物理删除。
- **数字口径**：金额用 Decimal；预算/目标/订阅/健康/模拟全部由 SQL/规则计算，模型只负责解析和表达。
- **统一通知**：保留 `budget_alerts` 与 `agent_notifications` 两张源表，
  新增 `/api/notifications/*` 聚合读模型；支持 `group=budget_over/budget_near/subscription/goal/purchase/other` 分组筛选；旧接口不变。
- **Agent 健康诊断**：`/api/agent/run` 的 `health` 意图复用 `health_service.build_report`，只读返回真实指标/覆盖率/建议，不审批、不编造。
- **简单对话**：`chat` 意图处理你好/你是谁/谢谢/怎么用等，确定性话术，不调用模型、不编造业务数字；带业务词的问候仍走原意图。
- **预算**：`category_budgets` 是唯一写入源；`/api/budgets` 在存在分类预算时返回只读投影。
- **头像**：`users.avatar` 存 256×256 JPEG data URL，不保存原图。
- **个人资产**：`asset_accounts/asset_liabilities/asset_transactions` 独立账本；支持现金/银行/微信/支付宝/储蓄、房产/车辆/理财/贵重物品；转账只写两条流水、不生成账单；账单显式关联 `account_id` 才影响余额，关联 `liability_id` 时自动增加信用卡/分期负债。
- **CSV**：`/api/imports/*` 支持 UTF-8/GBK、常见微信/支付宝/通用表头、预览去重。
- **统一错误**：`{"code": HTTP状态码, "message": 提示}`；参数校验 422 并注明字段。

## 测试

```bash
python tests/smoke_test.py
python tests/agent_smoke.py
python tests/avatar_test.py
python tests/notifications_test.py
python tests/budget_consistency_test.py
python tests/assets_test.py
python tests/agent_assets_test.py
python tests/version_test.py
python tests/agent_eval/run_flow_eval.py
```
