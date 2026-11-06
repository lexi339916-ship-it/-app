# Agent 评测

用于比赛材料中的“可验证智能体”证据。

## 运行

```bash
# 先启动后端（judge_demo 演示数据可用 tools/seed_demo.py 生成）
python tools/seed_demo.py
python tests/agent_eval/run_eval.py --username judge_demo --password judge2026
```

快速试跑前 10 条：

```bash
python tests/agent_eval/run_eval.py --limit 10
```

## 输出

- `report.md`：分类通过率、失败用例、延迟。
- `report.json`：逐条结果，便于二次分析。

## 说明

- 默认不批准写操作，只验证 Agent 状态、工具选择、审批生成与回答内容；
  如需验证执行/撤销，请用 `tests/agent_smoke.py`。
- 评测会写入 `agent_runs/steps/approvals` 轨迹，可用 `python tools/seed_demo.py` 重置演示账号。
- 官方未公开评分权重；本报告只作为团队自测证据，不宣称官方标准。
