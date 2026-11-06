const pptxgen = require("pptxgenjs");

const W = 13.33, H = 7.5, M = 0.6;
const BG = "FBF8F3", DARK = "23223A", PRIMARY = "5A54B8", PRIMARY2 = "7C8BFF";
const ACCENT = "E45858", GOLD = "D98A32", TEXT = "2F3047", MUTED = "7A7F99";
const LIGHT = "EFECF8", WHITE = "FFFFFF", GREEN = "1FA97F";
const FONT = "微软雅黑";

const pres = new pptxgen();
pres.layout = "LAYOUT_WIDE";
pres.author = "知账团队";
pres.title = "知账 · 家庭消费健康 Agent";
pres.subject = "第二届全国人工智能应用创新大赛 · 通用赛道 · 消费领域";

const shadow = () => ({ type: "outer", color: "5A54B8", blur: 10, offset: 2, angle: 45, opacity: 0.10 });
const tx = (slide, text, x, y, w, h, size = 18, color = TEXT, bold = false, align = "left", opts = {}) =>
  slide.addText(text, { x, y, w, h, fontSize: size, color, bold, align, valign: "mid",
    fontFace: FONT, margin: 0, ...opts });
const lines = (slide, arr, x, y, w, h, size = 18, color = TEXT, opts = {}) =>
  slide.addText(arr.map((t, i) => ({ text: t, options: { breakLine: i < arr.length - 1 } })),
    { x, y, w, h, fontSize: size, color, fontFace: FONT, margin: 0, valign: "top", ...opts });
const card = (slide, x, y, w, h, fill = WHITE, line = LIGHT) => {
  slide.addShape(pres.shapes.ROUNDED_RECTANGLE, { x, y, w, h, rectRadius: 0.10,
    fill: { color: fill }, line: { color: line, width: 0.8 }, shadow: shadow() });
};
const pill = (slide, text, x, y, w, fill = LIGHT, color = PRIMARY) => {
  slide.addShape(pres.shapes.ROUNDED_RECTANGLE, { x, y, w, h: 0.34, rectRadius: 0.17,
    fill: { color: fill }, line: { color: fill, width: 0.5 } });
  tx(slide, text, x, y - 0.005, w, 0.34, 12, color, true, "center");
};
const header = (slide, kicker, title, dark = false) => {
  tx(slide, kicker, M, 0.42, 10, 0.28, 12, dark ? "B9B6D6" : MUTED, true);
  tx(slide, title, M, 0.72, 12, 0.72, 32, dark ? WHITE : TEXT, true);
};
const footer = (slide, n, source = "") => {
  if (source) tx(slide, source, M, H - 0.42, 10.8, 0.24, 10, MUTED);
  tx(slide, String(n), W - 0.75, H - 0.42, 0.3, 0.24, 10, MUTED, false, "right");
};
const bg = (slide) => { slide.background = { color: BG }; };

const S = [];

// 1 Cover
{
  const s = pres.addSlide(); s.background = { color: DARK }; S.push(s);
  tx(s, "通用赛道 · 消费领域 / 参赛团队", M, 0.55, 7, 0.3, 13, "B9B6D6", true);
  tx(s, "知账", M, 1.35, 5.6, 0.95, 60, WHITE, true);
  tx(s, "家庭消费健康 Agent", M, 2.35, 6.5, 0.55, 30, WHITE, true);
  tx(s, "从记一笔，到做对下一步。", M, 3.15, 6.6, 0.45, 22, PRIMARY2, true);
  tx(s, "不是又一个记账 App，而是能理解、规划、审批、执行、验证的消费健康智能体。",
    M, 3.85, 6.2, 0.9, 16, "C9C6E2", false);
  // ledger card
  card(s, 7.55, 1.45, 5.1, 3.5, "2E2C4A", "4A4770");
  tx(s, "演示数据 · 合成", 7.85, 1.72, 3.5, 0.3, 12, "B9B6D6", true);
  tx(s, "本月结余", 7.85, 2.2, 2, 0.3, 15, "C9C6E2");
  tx(s, "¥3,691", 7.85, 2.55, 4.2, 0.7, 40, WHITE, true);
  tx(s, "收入 ¥9,000    支出 ¥5,309", 7.85, 3.45, 4.3, 0.3, 14, "C9C6E2");
  tx(s, "健康分 73 / 良好", 7.85, 3.95, 4.0, 0.4, 20, PRIMARY2, true);
  tx(s, "可复现证据：100 条评测 · 94 项流程断言 · 53 项多轮 · 62 项模拟 · 47 项 CSV",
    M, 6.35, 12, 0.35, 12, "9C98C3");
}

// 2 Pain
{
  const s = pres.addSlide(); bg(s); S.push(s);
  header(s, "01 / 真实痛点", "记了 3 年账，为什么还是存不下钱？");
  const rows = [
    ["账单分散", "微信、支付宝、银行卡、截图、待办，各记各的。"],
    ["预算不执行", "设了额度，月底才发现超支；不知道从哪调。"],
    ["订阅暗扣", "涨价、低频、重复扣费，发现时已经扣了几个月。"],
    ["目标不可执行", "只写“存 3000”，没有月度拆解，也没有复盘。"],
  ];
  rows.forEach(([lead, desc], i) => {
    const y = 1.72 + i * 0.95;
    tx(s, lead, M, y, 2.5, 0.34, 20, TEXT, true);
    tx(s, desc, M + 2.65, y, 7.0, 0.34, 15, MUTED);
    s.addShape(pres.shapes.LINE, { x: M, y: y + 0.55, w: 9.55, h: 0, line: { color: "E4E0D8", width: 0.6 } });
  });
  card(s, 10.35, 1.7, 2.35, 3.35, "FFF1EC", "F3D3C8");
  tx(s, "3 年", 10.55, 2.0, 1.95, 0.8, 46, ACCENT, true);
  tx(s, "记录 ≠ 改变", 10.55, 2.95, 1.95, 0.4, 16, TEXT, true);
  tx(s, "真正缺的不是账本，而是从“看见”到“改掉”的那一步。", 10.55, 3.5, 1.95, 1.2, 13, MUTED);
  footer(s, 2, "来源：团队对目标用户访谈与产品调研（定性，非统计样本）");
}

// 3 Users
{
  const s = pres.addSlide(); bg(s); S.push(s);
  header(s, "02 / 用户与场景", "三个具体的人，三种“知道却做不到”");
  const users = [
    ["小林 · 初入职场", "每天一杯咖啡，月底餐饮超支。", "想要：记账后就知道下一步怎么调。"],
    ["小周 · 大学生", "视频会员涨价 20%，忘了取消。", "想要：主动发现涨价和低频订阅。"],
    ["两人小家庭", "想 3 个月存 3000 去旅行。", "想要：把目标拆成预算和每周任务。"],
  ];
  users.forEach(([name, pain, want], i) => {
    const x = M + i * 4.05;
    card(s, x, 1.75, 3.7, 3.55, i === 1 ? "F4F0FF" : WHITE);
    tx(s, name, x + 0.28, 2.0, 3.1, 0.35, 19, PRIMARY, true);
    tx(s, pain, x + 0.28, 2.55, 3.1, 0.8, 17, TEXT, true);
    tx(s, want, x + 0.28, 3.55, 3.1, 1.1, 14, MUTED);
  });
  tx(s, "共同需求：不是更多报表，而是“下一步做什么、做完有没有效”。", M, 5.8, 12, 0.42, 18, TEXT, true);
  footer(s, 3, "目标用户：大学生、初入职场青年、两人小家庭；演示数据为合成数据");
}

// 4 Solution
{
  const s = pres.addSlide(); bg(s); S.push(s);
  header(s, "03 / 方案概览", "不是又一个记账 App，而是消费健康 Agent");
  tx(s, "把消费数据、AI 分析、任务规划、业务工具、审批机制和结果验证串成一条闭环。",
    M, 1.55, 6.0, 0.8, 17, MUTED);
  const steps = ["感知", "记忆", "规划", "行动", "反思", "主动"];
  steps.forEach((t, i) => {
    const x = M + (i % 3) * 1.95, y = 2.55 + Math.floor(i / 3) * 1.05;
    pill(s, t, x, y, 1.55, i === 3 ? "E9F8F2" : "EFF1FF", i === 3 ? GREEN : PRIMARY);
    if (i % 3 < 2) tx(s, "→", x + 1.58, y - 0.02, 0.35, 0.34, 18, MUTED);
  });
  tx(s, "单 Agent + 状态机", M, 4.9, 3.0, 0.32, 14, PRIMARY, true);
  tx(s, "读写工具分离 · 写操作必须审批 · 执行后回查数据库", M, 5.3, 6.2, 0.4, 14, MUTED);
  card(s, 7.0, 1.65, 5.7, 4.15, "23223A", "3A3758");
  tx(s, "三条差异", 7.3, 1.9, 2.5, 0.35, 14, "B9B6D6", true);
  [["多步行动闭环", "不是只给建议，而是生成可执行方案。"],
   ["审批 + 审计", "每个写操作有 diff、幂等、撤销、回查。"],
   ["可解释轨迹", "数字来自 SQL/工具，带来源、公式、as_of。"]].forEach(([a, b], i) => {
    tx(s, a, 7.3, 2.45 + i * 1.05, 4.6, 0.35, 19, WHITE, true);
    tx(s, b, 7.3, 2.83 + i * 1.05, 4.8, 0.35, 13, "C9C6E2");
  });
  footer(s, 4);
}

// 5 Capabilities
{
  const s = pres.addSlide(); bg(s); S.push(s);
  header(s, "04 / Agent 能力", "六种能力，落在同一条业务闭环");
  const caps = [
    ["感知", "文本、截图、语音、CSV、订阅、待办"],
    ["记忆", "目标、偏好、商户→分类纠正、历史决策"],
    ["规划", "拆目标、查数据、信息不足先澄清"],
    ["行动", "生成 diff，用户批准后才写库"],
    ["反思", "执行后回查，偏离时重规划"],
    ["主动", "预算漂移、订阅涨价、目标延期"],
  ];
  caps.forEach(([t, d], i) => {
    const x = M + (i % 2) * 3.35, y = 1.75 + Math.floor(i / 2) * 1.25;
    tx(s, String(i + 1).padStart(2, "0"), x, y + 0.02, 0.45, 0.3, 13, PRIMARY2, true);
    tx(s, t, x + 0.5, y, 1.2, 0.32, 19, TEXT, true);
    tx(s, d, x + 1.65, y + 0.02, 1.6, 0.55, 12, MUTED);
  });
  card(s, 7.55, 1.65, 5.15, 4.55, "F4F0FF", "DCD5F2");
  tx(s, "业务闭环", 7.85, 1.9, 2.5, 0.35, 14, PRIMARY, true);
  const loop = ["用户提出目标", "读取真实数据", "识别问题", "制定计划", "用户审批", "执行并验证", "复盘调整"];
  loop.forEach((t, i) => {
    const y = 2.35 + i * 0.5;
    tx(s, `${i + 1}. ${t}`, 7.9, y, 3.8, 0.3, 14, i === 4 ? ACCENT : TEXT, i === 4);
  });
  tx(s, "所有数字来自工具/SQL；模型只负责理解与表达。", 7.9, 5.75, 4.4, 0.35, 12, MUTED);
  footer(s, 5);
}

// 6 Architecture
{
  const s = pres.addSlide(); bg(s); S.push(s);
  header(s, "05 / 技术架构", "单 Agent + 状态机，拒绝过度设计");
  const box = (x, y, w, h, t, sub, fill = WHITE, color = TEXT) => {
    card(s, x, y, w, h, fill);
    tx(s, t, x + 0.15, y + 0.12, w - 0.3, 0.32, 15, color, true, "center");
    if (sub) tx(s, sub, x + 0.12, y + 0.48, w - 0.24, h - 0.55, 11, MUTED, false, "center");
  };
  box(M, 1.8, 2.3, 1.05, "uni-app H5 / App", "首页 · Agent · 健康报告 · 模拟器 · CSV");
  box(3.35, 1.8, 2.4, 1.05, "FastAPI", "REST · JWT · 统一错误 · 用户隔离");
  box(6.2, 1.8, 2.7, 1.05, "Agent Runtime", "orchestrator / tools / policy / trace", "F4F0FF", PRIMARY);
  box(9.35, 1.8, 3.3, 1.05, "SQLite / MySQL", "账单 · 预算 · 目标 · 审批 · 审计");
  tx(s, "→", 2.4, 2.1, 0.5, 0.45, 18, MUTED, true, "center");
  tx(s, "→", 5.85, 2.1, 0.5, 0.45, 18, MUTED, true, "center");
  tx(s, "→", 9.0, 2.1, 0.45, 0.45, 18, MUTED, true, "center");
  box(3.35, 3.55, 2.4, 1.0, "OpenAI 兼容模型", "仅解析/表达；不参与算术", "FFF6E7", GOLD);
  box(6.2, 3.55, 2.7, 1.0, "规则 / SQL", "预算、目标、订阅、健康指标", "E9F8F2", GREEN);
  tx(s, "模型可替换 · 未配置/超时自动降级为规则", 3.55, 4.85, 5.8, 0.3, 12, MUTED, false, "center");
  tx(s, "不做：多 Agent / 向量数据库 / Kafka / K8s", M, 5.65, 8, 0.35, 15, ACCENT, true);
  tx(s, "理由：比赛场景需要可解释、可验证、可维护；单 Agent 状态机足够讲清楚。", M, 6.05, 11.5, 0.35, 13, MUTED);
  footer(s, 6, "技术栈：Python 3.10+ / FastAPI / SQLAlchemy 2 / Pydantic 2 / uni-app Vue 3");
}

// 7 Scenario 1
{
  const s = pres.addSlide(); bg(s); S.push(s);
  header(s, "06 / 英雄场景 1", "一句话记账，先预判预算冲击");
  tx(s, "用户说：“午饭花了 32 元，微信付的。”", M, 1.55, 6.0, 0.4, 18, TEXT, true);
  const flow = ["解析账单", "查本月预算", "发现将超支", "生成方案", "用户审批"];
  flow.forEach((t, i) => {
    const x = M + i * 2.25;
    pill(s, t, x, 2.2, 1.95, i === 4 ? "FFF1EC" : "EFF1FF", i === 4 ? ACCENT : PRIMARY);
    if (i < 4) tx(s, "→", x + 1.98, 2.18, 0.25, 0.34, 16, MUTED);
  });
  lines(s, ["餐饮预算 ¥1,200，已花 ¥1,180", "记账后 ¥1,212，超出 ¥12",
    "方案：从交通调配 ¥50 到餐饮", "并创建“本周控制餐饮支出”任务"], M, 2.9, 6.2, 1.4, 16, TEXT);
  card(s, 7.1, 1.55, 5.55, 3.95, "FFFCF7", "F0E3CE");
  tx(s, "等待你确认", 7.35, 1.8, 3, 0.32, 14, GOLD, true);
  tx(s, "写入账单", 7.35, 2.25, 1.5, 0.28, 12, PRIMARY, true);
  tx(s, "支出 ¥32.00 · 餐饮 · 当天", 7.35, 2.55, 4.8, 0.28, 13, TEXT);
  tx(s, "调整预算", 7.35, 2.95, 1.5, 0.28, 12, PRIMARY, true);
  tx(s, "交通 ¥350.00；餐饮 ¥1,250.00", 7.35, 3.25, 4.8, 0.28, 13, TEXT);
  tx(s, "创建任务", 7.35, 3.65, 1.5, 0.28, 12, PRIMARY, true);
  tx(s, "本周控制「餐饮」支出", 7.35, 3.95, 4.8, 0.28, 13, TEXT);
  pill(s, "批准执行", 7.35, 4.55, 1.7, PRIMARY, WHITE);
  pill(s, "先不要", 9.2, 4.55, 1.4, LIGHT, PRIMARY);
  tx(s, "真实页面结构示意 · 金额来自演示数据", 7.35, 5.05, 4.8, 0.25, 10, MUTED);
  tx(s, "批准后才会写入；执行后回查数据库，并支持撤销。", M, 5.55, 11.5, 0.35, 15, TEXT, true);
  footer(s, 7, "场景验证：tests/agent_smoke.py、tests/agent_eval/flow_report.md");
}

// 8 Scenario 2
{
  const s = pres.addSlide(); bg(s); S.push(s);
  header(s, "07 / 英雄场景 2", "订阅体检：拒绝之后，不是重复原方案");
  card(s, M, 1.65, 5.55, 3.55, WHITE);
  tx(s, "视频会员", M + 0.3, 1.9, 2.2, 0.35, 19, TEXT, true);
  tx(s, "¥25 → ¥30   近 90 天 1 次", M + 0.3, 2.35, 4.8, 0.3, 14, ACCENT, true);
  tx(s, "健身会员", M + 0.3, 2.85, 2.2, 0.35, 19, TEXT, true);
  tx(s, "¥199   近 90 天 0 次", M + 0.3, 3.3, 4.8, 0.3, 14, ACCENT, true);
  tx(s, "年化影响约 ¥2,748", M + 0.3, 3.95, 4.8, 0.35, 17, PRIMARY, true);
  const flow2 = ["扫描订阅", "发现涨价/低频", "暂停方案", "用户拒绝", "替代：只建复盘任务"];
  flow2.forEach((t, i) => {
    const y = 1.75 + i * 0.7;
    tx(s, `${i + 1}`, 6.75, y, 0.35, 0.3, 14, i === 3 ? ACCENT : PRIMARY2, true);
    tx(s, t, 7.15, y - 0.02, 4.9, 0.32, 15, i === 3 ? ACCENT : TEXT, i === 3);
    if (i < 4) s.addShape(pres.shapes.LINE, { x: 6.92, y: y + 0.28, w: 0, h: 0.38,
      line: { color: "D9D4EC", width: 1 } });
  });
  pill(s, "旧审批 superseded", 7.15, 5.35, 2.35, "FFF1EC", ACCENT);
  tx(s, "用户拒绝不会丢上下文；旧审批被替代，新方案重新走审批。", M, 5.55, 11.5, 0.35, 15, TEXT, true);
  footer(s, 8, "场景验证：tests/agent_smoke.py、tests/multi_turn_test.py");
}

// 9 Scenario 3
{
  const s = pres.addSlide(); bg(s); S.push(s);
  header(s, "08 / 英雄场景 3", "3 个月存 3000，拆成预算和每周任务");
  tx(s, "目标", M, 1.65, 1.2, 0.3, 13, MUTED, true);
  tx(s, "¥3,000", M, 1.95, 2.2, 0.65, 34, PRIMARY, true);
  tx(s, "3 个月 · 每月 ¥1,000", M, 2.65, 2.4, 0.3, 14, MUTED);
  tx(s, "近 3 个月平均结余", 3.1, 1.65, 2.2, 0.3, 13, MUTED, true);
  tx(s, "¥3,820", 3.1, 1.95, 2.2, 0.65, 34, GREEN, true);
  pill(s, "可行", 3.1, 2.65, 1.0, "E9F8F2", GREEN);
  const parts = [
    ["创建目标", "旅行基金 · 3 个月 · ¥3,000"],
    ["调整预算", "压缩可自由支配分类约 ¥540"],
    ["创建任务", "每周日复盘目标进度"],
  ];
  parts.forEach(([a, b], i) => {
    const y = 3.55 + i * 0.75;
    tx(s, a, M, y, 1.2, 0.3, 15, PRIMARY, true);
    tx(s, b, M + 1.35, y, 5.0, 0.3, 14, TEXT);
    s.addShape(pres.shapes.LINE, { x: M, y: y + 0.45, w: 6.0, h: 0, line: { color: "E4E0D8", width: 0.6 } });
  });
  card(s, 7.2, 1.65, 5.45, 3.95, "F4F0FF", "DCD5F2");
  tx(s, "每周复盘", 7.5, 1.9, 2.5, 0.35, 15, PRIMARY, true);
  tx(s, "实际支出 vs 计划", 7.5, 2.4, 4.6, 0.35, 19, TEXT, true);
  tx(s, "偏离时重规划，而不是月底才发现。", 7.5, 2.9, 4.6, 0.5, 14, MUTED);
  tx(s, "目标不是一次性写入，而是持续校准。", 7.5, 3.8, 4.6, 0.5, 17, PRIMARY, true);
  footer(s, 9, "场景验证：tests/agent_smoke.py、tests/health_report_test.py");
}

// 10 Trusted design
{
  const s = pres.addSlide(); bg(s); S.push(s);
  header(s, "09 / 可信执行", "模型只能提议，不能直接写库");
  const chain = ["propose", "approve", "execute", "verify", "audit", "undo"];
  chain.forEach((t, i) => {
    const x = M + i * 2.02;
    pill(s, t, x, 1.85, 1.75, i === 1 ? "FFF1EC" : "EFF1FF", i === 1 ? ACCENT : PRIMARY);
    if (i < 5) tx(s, "→", x + 1.78, 1.83, 0.22, 0.34, 15, MUTED);
  });
  const gs = [
    ["幂等审批", "唯一 idempotency_key；重复批准不重复写。"],
    ["执行后回查", "金额、分类、日期、来源逐项校验。"],
    ["可撤销", "执行记录保留 undo；撤销后恢复原状。"],
    ["审计留痕", "工具、证据、diff、审批、结果全可追溯。"],
  ];
  gs.forEach(([a, b], i) => {
    const x = M + (i % 2) * 6.05, y = 2.85 + Math.floor(i / 2) * 1.0;
    tx(s, a, x, y, 2.0, 0.32, 17, TEXT, true);
    tx(s, b, x + 2.1, y + 0.02, 3.7, 0.55, 12, MUTED);
  });
  card(s, 7.0, 4.55, 5.65, 1.25, "23223A", "3A3758");
  tx(s, "0", 7.3, 4.75, 0.8, 0.55, 34, PRIMARY2, true);
  tx(s, "未审批写入（团队自测）", 8.05, 4.85, 4.2, 0.3, 15, WHITE, true);
  tx(s, "所有写操作必须经过用户批准 + 执行后校验。", 8.05, 5.2, 4.2, 0.3, 11, "C9C6E2");
  footer(s, 10, "证据：tests/agent_eval/flow_report.md（94 项数据库断言）");
}

// 11 Security
{
  const s = pres.addSlide(); bg(s); S.push(s);
  header(s, "10 / 安全与合规", "边界清楚，才敢让 Agent 碰钱");
  const rows = [
    ["只用合成数据", "演示账号 judge_demo；不接真实银行/支付宝/微信账号。"],
    ["不做资金动作", "不做自动转账、投资建议、代客理财。"],
    ["最小化处理", "敏感文本脱敏；语音转写后删除；日志不含密钥。"],
    ["用户可控", "写操作审批、可撤销、可删除记忆与数据。"],
  ];
  rows.forEach(([a, b], i) => {
    const y = 1.7 + i * 0.78;
    tx(s, a, M, y, 2.5, 0.32, 18, TEXT, true);
    tx(s, b, M + 2.65, y + 0.02, 6.4, 0.34, 13, MUTED);
    s.addShape(pres.shapes.LINE, { x: M, y: y + 0.52, w: 9.3, h: 0, line: { color: "E4E0D8", width: 0.6 } });
  });
  card(s, 9.9, 1.65, 2.85, 3.9, "E9F8F2", "C8E9DC");
  tx(s, "数据流", 10.15, 1.9, 2.3, 0.3, 14, GREEN, true);
  ["用户输入", "脱敏/最小化", "模型或规则", "用户审批", "本地库"].forEach((t, i) => {
    tx(s, t, 10.15, 2.35 + i * 0.55, 2.3, 0.28, 13, TEXT, i === 3);
  });
  tx(s, "定位：消费健康/预算管理，不进入金融监管敏感区。", M, 5.55, 11.5, 0.35, 15, PRIMARY, true);
  footer(s, 11, "安全实现：登录限流、脱敏、审批幂等、跨用户隔离、交付检查脚本");
}

// 12 Eval
{
  const s = pres.addSlide(); bg(s); S.push(s);
  header(s, "11 / 评测结果", "100 条任务，100% 通过（团队自测）");
  const stats = [["100/100", "任务通过", PRIMARY], ["100%", "工具选择", GREEN],
    ["100%", "参数准确", PRIMARY2], ["0", "未审批写入", ACCENT]];
  stats.forEach(([n, l, c], i) => {
    tx(s, n, M + i * 3.0, 1.55, 2.8, 0.55, 28, c, true);
    tx(s, l, M + i * 3.0, 2.1, 2.8, 0.25, 11, MUTED);
  });
  const labels = ["query", "bill", "subscription", "goal", "budget", "safety", "clarify", "multi"];
  const values = [18, 22, 12, 14, 8, 12, 8, 6];
  s.addChart(pres.charts.BAR, [{ name: "通过", labels, values }], {
    x: M, y: 2.55, w: 8.0, h: 3.3, barDir: "col",
    chartColors: [PRIMARY], showValue: true, dataLabelPosition: "outEnd",
    dataLabelColor: TEXT, dataLabelFontFace: FONT, dataLabelFontSize: 10,
    catAxisLabelColor: MUTED, valAxisLabelColor: MUTED,
    catAxisLabelFontFace: FONT, valAxisLabelFontFace: FONT,
    valGridLine: { color: "E8E4F0", size: 0.5 }, catGridLine: { style: "none" },
    showLegend: false, valAxisMaxVal: 26, chartArea: { fill: { color: BG } },
  });
  card(s, 8.85, 2.55, 3.85, 3.0, "FFF6E7", "F0DDB8");
  tx(s, "评测口径", 9.1, 2.75, 2.5, 0.3, 14, GOLD, true);
  lines(s, ["dev/test 各 50 条", "工具 80 组、参数 51 组", "金额一致性 27/27",
    "审批一致性 66/66", "P95 4.9s；模型 21 / 规则 8"], 9.1, 3.15, 3.3, 1.7, 12, TEXT);
  tx(s, "不是第三方认证；dev/test 为预设划分。", M, 6.1, 11.8, 0.3, 11, MUTED);
  footer(s, 12, "证据：tests/agent_eval/report.md、report_test.md");
}

// 13 Flow eval
{
  const s = pres.addSlide(); bg(s); S.push(s);
  header(s, "12 / 审批与异常", "94 项数据库级断言，覆盖真实失败路径");
  tx(s, "94/94", M, 1.55, 2.6, 0.7, 42, GREEN, true);
  tx(s, "审批、拒绝、撤销、并发、回滚、跨用户、注入、空库", M, 2.25, 6.0, 0.35, 14, MUTED);
  const items = [
    "审批 → 执行 → 回查 → 撤销", "拒绝 → 替代方案 → 批准",
    "改金额 → 重算 → 执行", "过期审批 / 重复批准",
    "并发批准只写一次", "执行校验失败回滚",
    "模型超时/非法 JSON 降级", "跨用户读写 404",
    "提示词注入不产生越权动作", "空数据库不崩",
  ];
  items.forEach((t, i) => {
    const x = M + (i % 2) * 6.05, y = 2.95 + Math.floor(i / 2) * 0.55;
    tx(s, "·", x, y, 0.2, 0.3, 18, PRIMARY2, true);
    tx(s, t, x + 0.25, y + 0.02, 5.4, 0.3, 14, TEXT);
  });
  pill(s, "未审批写入 0", 7.0, 5.65, 2.1, "FFF1EC", ACCENT);
  pill(s, "并发只写 1 次", 9.3, 5.65, 2.3, "E9F8F2", GREEN);
  footer(s, 13, "证据：tests/agent_eval/flow_report.md");
}

// 14 Multi-turn
{
  const s = pres.addSlide(); bg(s); S.push(s);
  header(s, "13 / 多轮对话", "同一会话内改条件，旧审批自动替代");
  const turns = [
    ["第 1 轮", "午饭32元", "从「交通」调配 ¥50"],
    ["第 2 轮", "不想动交通预算", "改从「学习」调配 ¥50"],
    ["第 3 轮", "只调整100元", "「学习」→「餐饮」¥100"],
  ];
  turns.forEach(([n, q, a], i) => {
    const y = 1.65 + i * 1.15;
    pill(s, n, M, y, 1.2, i === 2 ? "E9F8F2" : "EFF1FF", i === 2 ? GREEN : PRIMARY);
    tx(s, q, M + 1.45, y - 0.02, 3.6, 0.3, 15, TEXT, true);
    tx(s, a, M + 5.2, y - 0.02, 3.8, 0.3, 13, MUTED);
    if (i < 2) s.addShape(pres.shapes.LINE, { x: M + 0.6, y: y + 0.36, w: 0, h: 0.55,
      line: { color: "D9D4EC", width: 1 } });
  });
  pill(s, "superseded", 9.4, 1.7, 1.7, "FFF1EC", ACCENT);
  tx(s, "旧审批不可再执行", 9.4, 2.15, 2.4, 0.3, 12, ACCENT, true);
  card(s, 8.6, 3.05, 4.0, 2.35, "F4F0FF", "DCD5F2");
  tx(s, "链路字段", 8.85, 3.25, 2.0, 0.3, 14, PRIMARY, true);
  lines(s, ["session_id", "parent_run_id", "turn_index"], 8.85, 3.65, 3.4, 1.1, 14, TEXT);
  tx(s, "旧审批不会被新对话污染；每轮新方案重新审批、可撤销。", M, 5.75, 11.5, 0.35, 15, TEXT, true);
  footer(s, 14, "证据：tests/multi_turn_test.py（53 项）、tests/agent_eval/multi_turn_report.md");
}

// 15 Simulator
{
  const s = pres.addSlide(); bg(s); S.push(s);
  header(s, "14 / 决策模拟", "买之前先算：5000 元手机会影响旅行计划吗？");
  const nums = [["¥5,000", "购买金额", PRIMARY], ["-¥4,980", "预算剩余", ACCENT],
    ["+39 天", "完成时间变晚", GOLD], ["0 天", "截止日延期", GREEN]];
  nums.forEach(([n, l, c], i) => {
    tx(s, n, M + i * 3.0, 1.55, 2.8, 0.5, 28, c, true);
    tx(s, l, M + i * 3.0, 2.08, 2.8, 0.25, 11, MUTED);
  });
  const sc = [
    ["现在购买", "预算超支 ¥4,980；目标完成晚约 39 天", "压力较大"],
    ["下个月购买", "本月预算不变；目标总延期不变", "可缓解现金流"],
    ["分 3 个月压缩支出", "每月需省 ¥1,666.67；当前额度不足", "需调整"],
  ];
  sc.forEach(([t, d, tag], i) => {
    const y = 2.75 + i * 0.95;
    tx(s, t, M, y, 2.8, 0.3, 16, TEXT, true);
    tx(s, d, M + 3.0, y + 0.02, 4.9, 0.3, 12, MUTED);
    pill(s, tag, 8.1, y - 0.02, 1.5, i === 0 ? "FFF1EC" : "EFF1FF", i === 0 ? ACCENT : PRIMARY);
  });
  tx(s, "按近 3 个月平均结余 ¥3,923 测算；不代表账户真实余额。", M, 5.9, 11.5, 0.3, 11, MUTED);
  footer(s, 15, "证据：tests/decision_simulator_test.py（62 项）");
}

// 16 CSV
{
  const s = pres.addSlide(); bg(s); S.push(s);
  header(s, "15 / 数据接入", "把散落的账单拉回账本：CSV 导入");
  const flow = ["微信/支付宝/通用 CSV", "编码与表头识别", "预览去重", "逐行勾选", "写入 source=csv"];
  flow.forEach((t, i) => {
    const x = M + (i % 3) * 3.7, y = 1.65 + Math.floor(i / 3) * 0.95;
    pill(s, t, x, y, 2.9, i === 2 ? "E9F8F2" : "EFF1FF", i === 2 ? GREEN : PRIMARY);
    if (i % 3 < 2) tx(s, "→", x + 2.92, y - 0.02, 0.3, 0.34, 15, MUTED);
  });
  const stats = [["47", "测试断言"], ["UTF-8/GBK", "编码"], ["5MB/5000行", "上限"], ["双重去重", "已有+文件内"]];
  stats.forEach(([n, l], i) => {
    tx(s, n, M + i * 2.35, 4.15, 2.1, 0.45, 24, PRIMARY, true);
    tx(s, l, M + i * 2.35, 4.65, 2.1, 0.25, 11, MUTED);
  });
  tx(s, "识别：日期、金额、收支、分类、渠道、扣款账户；关闭/失败交易跳过。", M, 5.4, 11.5, 0.35, 14, TEXT);
  tx(s, "无法识别的行进入错误列表，不猜、不静默导入。", M, 5.85, 11.5, 0.35, 14, ACCENT, true);
  footer(s, 16, "证据：tests/csv_import_test.py（47 项）");
}

// 17 Health
{
  const s = pres.addSlide(); bg(s); S.push(s);
  header(s, "16 / 消费健康", "五个指标，全部可解释");
  tx(s, "73", M, 1.55, 1.4, 0.8, 42, PRIMARY, true);
  tx(s, "综合健康分", M, 2.3, 1.8, 0.3, 13, MUTED);
  tx(s, "良好 · 指标覆盖 60%", M, 2.65, 3.2, 0.3, 14, GREEN, true);
  const ind = [
    ["预算执行", "30%", "68", GOLD],
    ["储蓄目标", "25%", "数据不足", MUTED],
    ["订阅健康", "15%", "65", GOLD],
    ["结构稳定", "15%", "91", GREEN],
    ["计划执行", "15%", "数据不足", MUTED],
  ];
  ind.forEach(([name, w, score, c], i) => {
    const y = 1.65 + i * 0.62;
    tx(s, name, 4.0, y, 2.2, 0.3, 15, TEXT, true);
    tx(s, w, 6.2, y + 0.02, 0.7, 0.3, 12, MUTED);
    tx(s, score, 7.0, y, 1.5, 0.3, 17, c, true);
    if (score !== "数据不足") {
      s.addShape(pres.shapes.RECTANGLE, { x: 8.5, y: y + 0.08, w: 2.5 * Number(score) / 100, h: 0.14,
        fill: { color: c }, line: { color: c, width: 0 } });
    }
  });
  card(s, 4.0, 4.95, 7.8, 1.1, "FFF6E7", "F0DDB8");
  tx(s, "每项返回 formula / inputs / source / period / as_of；覆盖率 <50% 不给总分。", 4.25, 5.15, 7.3, 0.3, 12, TEXT);
  tx(s, "不是信用评分、金融风险评级或投资建议。", 4.25, 5.5, 7.3, 0.3, 11, MUTED);
  footer(s, 17, "证据：tests/health_report_test.py（52 项）");
}

// 18 Competition
{
  const s = pres.addSlide(); bg(s); S.push(s);
  header(s, "17 / 竞争位置", "竞品很多，但这个位置还空着");
  const ox = 1.1, oy = 1.65, sw = 7.2, sh = 4.6;
  s.addShape(pres.shapes.LINE, { x: ox, y: oy + sh, w: sw, h: 0, line: { color: TEXT, width: 1 } });
  s.addShape(pres.shapes.LINE, { x: ox, y: oy, w: 0, h: sh, line: { color: TEXT, width: 1 } });
  tx(s, "记录", ox, oy + sh + 0.08, 1.2, 0.25, 11, MUTED);
  tx(s, "行动", ox + sw - 0.8, oy + sh + 0.08, 1.2, 0.25, 11, MUTED);
  tx(s, "单点", ox - 0.55, oy + sh - 0.25, 0.6, 0.25, 11, MUTED);
  tx(s, "家庭", ox - 0.55, oy + 0.05, 0.6, 0.25, 11, MUTED);
  const dots = [
    ["随手记/鲨鱼", 1.8, 4.9, MUTED], ["支付宝/微信", 2.6, 5.4, MUTED],
    ["Copilot/Rocket", 6.2, 2.9, PRIMARY2], ["Monarch", 6.6, 1.95, PRIMARY2],
    ["知账", 7.25, 1.55, ACCENT],
  ];
  dots.forEach(([t, x, y, c]) => {
    s.addShape(pres.shapes.OVAL, { x, y, w: 0.18, h: 0.18, fill: { color: c }, line: { color: c, width: 0 } });
    tx(s, t, x + 0.25, y - 0.08, 1.9, 0.3, 12, c, t === "知账");
  });
  card(s, 8.55, 1.65, 4.1, 3.95, "F4F0FF", "DCD5F2");
  tx(s, "我们的空位", 8.85, 1.9, 2.4, 0.3, 14, PRIMARY, true);
  lines(s, ["中文跨平台账单", "多步行动 + 审批/审计", "可解释轨迹 + 可撤销", "隐私优先、合成数据演示"],
    8.85, 2.35, 3.5, 2.2, 15, TEXT);
  tx(s, "不拼“功能最多”，拼“从洞察到行动的可信闭环”。", 8.85, 4.75, 3.5, 0.6, 13, MUTED);
  footer(s, 18, "对标：Copilot Money / Rocket Money / Monarch / 随手记 / 支付宝/微信");
}

// 19 Roadmap
{
  const s = pres.addSlide(); bg(s); S.push(s);
  header(s, "18 / 落地路线", "从可演示，到可落地");
  const phases = [
    ["现在", "3 场景 + 健康诊断 + 决策模拟 + CSV + 100 条评测", PRIMARY],
    ["校赛 / 区域赛", "真实语音、成本面板、家庭共享账本、10–30 用户", PRIMARY2],
    ["全国赛", "多角色审批、长期行为分析、产业试点", GOLD],
  ];
  phases.forEach(([t, d, c], i) => {
    const x = M + i * 4.05;
    tx(s, `0${i + 1}`, x, 1.65, 0.7, 0.4, 18, c, true);
    tx(s, t, x, 2.1, 3.6, 0.35, 20, TEXT, true);
    tx(s, d, x, 2.55, 3.5, 1.0, 13, MUTED);
    s.addShape(pres.shapes.LINE, { x: x, y: 3.65, w: 3.5, h: 0, line: { color: c, width: 2 } });
  });
  tx(s, "部署：Docker + HTTPS + MySQL 8；演示环境 SQLite + 同源代理。", M, 4.45, 11.5, 0.35, 14, TEXT);
  tx(s, "商业模式：B2C 学生免费/家庭订阅；B2B2C 校园、社区、银行合作。", M, 4.9, 11.5, 0.35, 14, TEXT);
  pill(s, "证据可复现", M, 5.65, 1.6, "E9F8F2", GREEN);
  pill(s, "数据可重置", M + 1.8, 5.65, 1.6, "EFF1FF", PRIMARY);
  pill(s, "边界可解释", M + 3.6, 5.65, 1.6, "FFF6E7", GOLD);
  footer(s, 19);
}

// 20 Closing
{
  const s = pres.addSlide(); s.background = { color: DARK }; S.push(s);
  tx(s, "知账", M, 1.4, 3.0, 0.7, 44, WHITE, true);
  tx(s, "让每一笔消费，都指向更好的下一步。", M, 2.25, 11.0, 0.7, 32, WHITE, true);
  tx(s, "从记一笔，到做对下一步。", M, 3.2, 8.0, 0.45, 20, PRIMARY2, true);
  tx(s, "演示账号：judge_demo / judge2026", M, 4.35, 6.0, 0.35, 16, "C9C6E2");
  tx(s, "证据：tests/agent_eval/ · docs/competition/audit_2026-11-05.md", M, 4.85, 9.0, 0.35, 13, "9C98C3");
  tx(s, "团队自测，不是第三方认证；所有数字可复现。", M, 5.3, 9.0, 0.35, 12, "9C98C3");
  tx(s, "谢谢", W - 2.0, 6.2, 1.4, 0.5, 28, WHITE, true, "right");
}

pres.writeFile({ fileName: "docs/competition/知账_比赛PPT.pptx" }).then(() => {
  console.log("PPT generated:", "docs/competition/知账_比赛PPT.pptx", "slides:", S.length);
});
