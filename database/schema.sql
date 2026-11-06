-- 智能记账与生活便签一体化管理系统 —— MySQL 8.x 初始化脚本
-- 用法：mysql -u root -p < database/schema.sql
-- 说明：与 backend/app/models.py 保持一致；开发时后端也可用 SQLite 自动建表。

CREATE DATABASE IF NOT EXISTS smart_life CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE smart_life;

-- 用户表：密码只存 PBKDF2 哈希，不存明文
CREATE TABLE IF NOT EXISTS users (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  username VARCHAR(50) NOT NULL UNIQUE,
  password_hash VARCHAR(255) NOT NULL,
  nickname VARCHAR(50) NOT NULL DEFAULT '',
  avatar MEDIUMTEXT NOT NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB;

-- 收支分类表：user_id 为 NULL 表示系统预置分类；非空表示用户自定义
CREATE TABLE IF NOT EXISTS bill_categories (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  user_id BIGINT NULL,
  name VARCHAR(40) NOT NULL,
  type ENUM('income','expense') NOT NULL,
  UNIQUE KEY uq_category_user_name_type (user_id, name, type),
  CONSTRAINT fk_category_user FOREIGN KEY (user_id) REFERENCES users(id)
) ENGINE=InnoDB;

-- 账单表：source 标记数据来源（manual 手动 / ai 智能解析确认后保存），满足可追溯要求
CREATE TABLE IF NOT EXISTS bills (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  user_id BIGINT NOT NULL,
  category_id BIGINT NULL,
  -- 可选：关联用户维护的资产账户；为空表示不计入资产账本（兼容旧账单）
  account_id BIGINT NULL,
  type ENUM('income','expense') NOT NULL,
  amount DECIMAL(12,2) NOT NULL,
  bill_date DATE NOT NULL,
  remark VARCHAR(200) NOT NULL DEFAULT '',
  source VARCHAR(12) NOT NULL DEFAULT 'manual',
  pay_channel VARCHAR(20) NOT NULL DEFAULT '',
  funding_account VARCHAR(40) NOT NULL DEFAULT '',
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  INDEX idx_bill_user_date (user_id, bill_date),
  INDEX idx_bill_account (account_id),
  CONSTRAINT fk_bill_user FOREIGN KEY (user_id) REFERENCES users(id),
  CONSTRAINT fk_bill_category FOREIGN KEY (category_id) REFERENCES bill_categories(id)
) ENGINE=InnoDB;

-- 便签与任务表：note_type 区分便签/待办；priority 优先级；pinned 置顶；due_at 截止时间
CREATE TABLE IF NOT EXISTS notes (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  user_id BIGINT NOT NULL,
  title VARCHAR(100) NOT NULL,
  content TEXT,
  note_type ENUM('note','todo') NOT NULL DEFAULT 'note',
  status ENUM('open','done') NOT NULL DEFAULT 'open',
  due_at DATETIME NULL,
  priority VARCHAR(10) NOT NULL DEFAULT 'medium',
  pinned TINYINT NOT NULL DEFAULT 0,
  color VARCHAR(20) NOT NULL DEFAULT 'lilac',
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  INDEX idx_note_user_status (user_id, status),
  CONSTRAINT fk_note_user FOREIGN KEY (user_id) REFERENCES users(id)
) ENGINE=InnoDB;

-- 月度预算表：每用户每月一条
CREATE TABLE IF NOT EXISTS budgets (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  user_id BIGINT NOT NULL,
  month CHAR(7) NOT NULL,
  amount DECIMAL(12,2) NOT NULL,
  UNIQUE KEY uq_budget_user_month (user_id, month),
  CONSTRAINT fk_budget_user FOREIGN KEY (user_id) REFERENCES users(id)
) ENGINE=InnoDB;

-- AI 调用日志表：记录功能、提示词版本、模型、耗时与结果，满足可复现与审计要求
CREATE TABLE IF NOT EXISTS ai_call_logs (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  user_id BIGINT NOT NULL,
  feature VARCHAR(30) NOT NULL,
  prompt_version VARCHAR(10) NOT NULL,
  model VARCHAR(60) NOT NULL,
  status VARCHAR(20) NOT NULL,
  latency_ms INT NOT NULL DEFAULT 0,
  error_msg VARCHAR(255) NOT NULL DEFAULT '',
  input_chars INT NOT NULL DEFAULT 0,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  INDEX idx_ai_log_user_date (user_id, created_at),
  CONSTRAINT fk_ai_log_user FOREIGN KEY (user_id) REFERENCES users(id)
) ENGINE=InnoDB;

-- 储蓄目标表：目标金额与已存入金额；预计完成时间由后端按月均结余计算
CREATE TABLE IF NOT EXISTS savings_goals (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  user_id BIGINT NOT NULL,
  name VARCHAR(50) NOT NULL,
  target_amount DECIMAL(12,2) NOT NULL,
  saved_amount DECIMAL(12,2) NOT NULL DEFAULT 0,
  target_months INT NULL,
  target_date DATE NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  CONSTRAINT fk_goal_user FOREIGN KEY (user_id) REFERENCES users(id)
) ENGINE=InnoDB;

-- 储蓄目标存入记录表：每笔存入留痕，支持事后修改/删除某一笔（saved_amount 由后端联动）
CREATE TABLE IF NOT EXISTS goal_deposits (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  goal_id BIGINT NOT NULL,
  user_id BIGINT NOT NULL,
  amount DECIMAL(12,2) NOT NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT fk_deposit_goal FOREIGN KEY (goal_id) REFERENCES savings_goals(id),
  INDEX idx_goal_deposit_goal (goal_id)
) ENGINE=InnoDB;

-- 生活挑战表：周期内某分类支出不超过上限；进度与上期对比由后端统计
CREATE TABLE IF NOT EXISTS challenges (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  user_id BIGINT NOT NULL,
  name VARCHAR(60) NOT NULL,
  category_id BIGINT NULL,
  period_days INT NOT NULL DEFAULT 7,
  target_amount DECIMAL(12,2) NOT NULL,
  start_date DATE NOT NULL,
  end_date DATE NOT NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT fk_challenge_user FOREIGN KEY (user_id) REFERENCES users(id),
  CONSTRAINT fk_challenge_category FOREIGN KEY (category_id) REFERENCES bill_categories(id)
) ENGINE=InnoDB;

-- ========== 自动订阅扣费 ==========

-- 周期性固定支出订阅：由用户手动录入，不抓取任何第三方平台续费状态
CREATE TABLE IF NOT EXISTS subscriptions (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  user_id BIGINT NOT NULL,
  name VARCHAR(60) NOT NULL,
  day_of_month INT NOT NULL DEFAULT 1,
  amount DECIMAL(12,2) NOT NULL,
  category_id BIGINT NULL,
  previous_amount DECIMAL(12,2) NULL,                -- 上次价格，用于订阅体检发现涨价
  usage_90d INT NOT NULL DEFAULT 0,                  -- 近 90 天使用次数，用于发现低频订阅
  remark VARCHAR(200) NOT NULL DEFAULT '',
  remind_enabled TINYINT NOT NULL DEFAULT 1,
  status VARCHAR(10) NOT NULL DEFAULT 'active',
  last_billed_month CHAR(7) NOT NULL DEFAULT '',
  remind_month CHAR(7) NOT NULL DEFAULT '',
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  INDEX idx_sub_user_status (user_id, status),
  CONSTRAINT fk_sub_user FOREIGN KEY (user_id) REFERENCES users(id),
  CONSTRAINT fk_sub_category FOREIGN KEY (category_id) REFERENCES bill_categories(id)
) ENGINE=InnoDB;

-- ========== 订阅计费记录（幂等 + 跨月补单） ==========

CREATE TABLE IF NOT EXISTS subscription_billings (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  user_id BIGINT NOT NULL,
  subscription_id BIGINT NOT NULL,
  month CHAR(7) NOT NULL,
  bill_id BIGINT NOT NULL,
  amount DECIMAL(12,2) NOT NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE KEY uq_sub_billing_sub_month (subscription_id, month),
  INDEX idx_sub_billing_user (user_id, month),
  CONSTRAINT fk_sub_billing_user FOREIGN KEY (user_id) REFERENCES users(id),
  CONSTRAINT fk_sub_billing_sub FOREIGN KEY (subscription_id) REFERENCES subscriptions(id)
) ENGINE=InnoDB;

-- ========== Agent 运行时 ==========

CREATE TABLE IF NOT EXISTS agent_runs (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  user_id BIGINT NOT NULL,
  session_id VARCHAR(64) NOT NULL DEFAULT '',              -- 多轮对话会话标识
  parent_run_id BIGINT NULL,                               -- 上一轮 run，形成可追溯链路
  turn_index INT NOT NULL DEFAULT 0,                       -- 会话内轮次，从 0 开始
  goal VARCHAR(500) NOT NULL,
  mode VARCHAR(20) NOT NULL DEFAULT 'auto',
  status VARCHAR(20) NOT NULL DEFAULT 'running',
  plan_json TEXT NOT NULL,
  answer TEXT NOT NULL,
  evidence_json TEXT NOT NULL,
  cost DECIMAL(10,4) NOT NULL DEFAULT 0,
  latency_ms INT NOT NULL DEFAULT 0,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  finished_at DATETIME NULL,
  INDEX idx_agent_run_user (user_id, created_at),
  INDEX idx_agent_run_session (user_id, session_id, turn_index),
  CONSTRAINT fk_agent_run_user FOREIGN KEY (user_id) REFERENCES users(id)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS agent_steps (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  run_id BIGINT NOT NULL,
  seq INT NOT NULL,
  step_type VARCHAR(20) NOT NULL,
  tool_name VARCHAR(40) NOT NULL DEFAULT '',
  args_json TEXT NOT NULL,
  result_json TEXT NOT NULL,
  status VARCHAR(20) NOT NULL DEFAULT 'ok',
  error VARCHAR(255) NOT NULL DEFAULT '',
  started_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  finished_at DATETIME NULL,
  UNIQUE KEY uq_agent_step_run_seq (run_id, seq),
  INDEX idx_agent_step_run (run_id, seq),
  CONSTRAINT fk_agent_step_run FOREIGN KEY (run_id) REFERENCES agent_runs(id)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS agent_approvals (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  run_id BIGINT NOT NULL,
  step_id BIGINT NULL,
  action_type VARCHAR(30) NOT NULL DEFAULT 'multi',
  diff_json TEXT NOT NULL,
  status VARCHAR(20) NOT NULL DEFAULT 'pending',
  idempotency_key VARCHAR(100) NOT NULL UNIQUE,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  expires_at DATETIME NULL,
  decided_at DATETIME NULL,
  INDEX idx_agent_approval_run (run_id, status),
  CONSTRAINT fk_agent_approval_run FOREIGN KEY (run_id) REFERENCES agent_runs(id)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS agent_memories (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  user_id BIGINT NOT NULL,
  kind VARCHAR(20) NOT NULL DEFAULT 'profile',
  mem_key VARCHAR(80) NOT NULL,
  value_json TEXT NOT NULL,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  UNIQUE KEY uq_agent_memory_user_kind_key (user_id, kind, mem_key),
  INDEX idx_agent_memory_user (user_id, kind),
  CONSTRAINT fk_agent_memory_user FOREIGN KEY (user_id) REFERENCES users(id)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS agent_notifications (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  user_id BIGINT NOT NULL,
  alert_type VARCHAR(30) NOT NULL,
  level VARCHAR(10) NOT NULL DEFAULT 'info',
  title VARCHAR(80) NOT NULL,
  message VARCHAR(300) NOT NULL,
  suggestion VARCHAR(300) NOT NULL DEFAULT '',
  category VARCHAR(40) NOT NULL DEFAULT '',
  amount DECIMAL(12,2) NULL,
  payload_json TEXT NOT NULL,
  status VARCHAR(10) NOT NULL DEFAULT 'unread',
  dedupe_key VARCHAR(120) NOT NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  read_at DATETIME NULL,
  UNIQUE KEY uq_agent_notif_user_key (user_id, dedupe_key),
  INDEX idx_agent_notif_user (user_id, status, created_at),
  CONSTRAINT fk_agent_notif_user FOREIGN KEY (user_id) REFERENCES users(id)
) ENGINE=InnoDB;

-- ========== AI 消费预警 & 预算模块（新增，不影响已有表） ==========

-- 分类月度预算表：每用户每分类每月一条（参考支付宝按分类设预算）
CREATE TABLE IF NOT EXISTS category_budgets (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  user_id BIGINT NOT NULL,
  category_id BIGINT NOT NULL,
  month CHAR(7) NOT NULL,                                  -- 格式：2026-10
  amount DECIMAL(12,2) NOT NULL,                           -- 该分类本月预算额度
  source VARCHAR(10) NOT NULL DEFAULT 'manual',            -- manual 手动 / ai AI推荐
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  UNIQUE KEY uq_cb_user_cat_month (user_id, category_id, month),
  CONSTRAINT fk_cb_user FOREIGN KEY (user_id) REFERENCES users(id),
  CONSTRAINT fk_cb_category FOREIGN KEY (category_id) REFERENCES bill_categories(id)
) ENGINE=InnoDB;

-- 预警消息表：所有预警统一入消息中心（80%提醒/100%超支/异常大额/弹性调度/计划采购）
CREATE TABLE IF NOT EXISTS budget_alerts (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  user_id BIGINT NOT NULL,
  alert_type VARCHAR(20) NOT NULL,                         -- budget_80 / budget_100 / anomaly / rebalance / planned_purchase
  level VARCHAR(10) NOT NULL DEFAULT 'info',               -- info 提醒 / warn 警示 / critical 强提醒
  category_id BIGINT NULL,
  month CHAR(7) NOT NULL,
  title VARCHAR(60) NOT NULL,                              -- 弹窗标题
  message VARCHAR(300) NOT NULL,                           -- 柔和预警文案（AI生成或模板降级）
  suggestion VARCHAR(300) NOT NULL DEFAULT '',             -- 附带的小建议
  payload TEXT,                                            -- JSON 扩展数据：已花/剩余/历史均值/调配方案等
  related_bill_id BIGINT NULL,                             -- 触发的账单（异常大额用）
  status VARCHAR(10) NOT NULL DEFAULT 'unread',            -- unread / read / accepted / dismissed
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  read_at DATETIME NULL,
  INDEX idx_alert_user_month (user_id, month, status),
  -- 同一分类同一月同一类型只推一次，防止重复打扰（anomaly 靠 related_bill_id 区分，不受此约束）
  UNIQUE KEY uq_alert_once (user_id, category_id, month, alert_type),
  CONSTRAINT fk_alert_user FOREIGN KEY (user_id) REFERENCES users(id)
) ENGINE=InnoDB;

-- AI 预算方案表：自然语言存钱目标 → AI 分配结果留痕，可一键采纳
CREATE TABLE IF NOT EXISTS budget_plans (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  user_id BIGINT NOT NULL,
  month CHAR(7) NOT NULL,
  goal_text VARCHAR(200) NOT NULL DEFAULT '',              -- 用户原话，如"这个月想存2000"
  income_estimate DECIMAL(12,2) NOT NULL DEFAULT 0,        -- AI 估计的月收入基准
  total_budget DECIMAL(12,2) NOT NULL DEFAULT 0,           -- 分配后的总预算
  plan_json TEXT NOT NULL,                                 -- 各分类分配明细 JSON
  applied TINYINT NOT NULL DEFAULT 0,                      -- 0 未采纳 / 1 已写入 category_budgets
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT fk_plan_user FOREIGN KEY (user_id) REFERENCES users(id)
) ENGINE=InnoDB;

-- ========== 个人资产管理（独立账本，不改变账单统计口径） ==========

-- 资产账户：余额由 asset_transactions 变动；只保存尾号提示，不保存完整卡号
CREATE TABLE IF NOT EXISTS asset_accounts (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  user_id BIGINT NOT NULL,
  name VARCHAR(50) NOT NULL,
  type VARCHAR(20) NOT NULL DEFAULT 'other',               -- cash/bank/wechat/alipay/savings/other
  institution VARCHAR(50) NOT NULL DEFAULT '',
  account_hint VARCHAR(8) NOT NULL DEFAULT '',             -- 仅尾号等提示
  balance DECIMAL(14,2) NOT NULL DEFAULT 0,
  note VARCHAR(200) NOT NULL DEFAULT '',
  is_active TINYINT NOT NULL DEFAULT 1,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  INDEX idx_asset_account_user (user_id, is_active),
  CONSTRAINT fk_asset_account_user FOREIGN KEY (user_id) REFERENCES users(id)
) ENGINE=InnoDB;

-- 负债：信用卡、分期、个人借款等；outstanding 为当前欠款
CREATE TABLE IF NOT EXISTS asset_liabilities (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  user_id BIGINT NOT NULL,
  name VARCHAR(50) NOT NULL,
  type VARCHAR(20) NOT NULL DEFAULT 'other',               -- credit_card/installment/personal_loan/other
  outstanding DECIMAL(14,2) NOT NULL DEFAULT 0,
  due_date DATE NULL,
  remark VARCHAR(200) NOT NULL DEFAULT '',
  status VARCHAR(10) NOT NULL DEFAULT 'active',            -- active/repaid
  is_active TINYINT NOT NULL DEFAULT 1,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  INDEX idx_asset_liability_user (user_id, is_active),
  CONSTRAINT fk_asset_liability_user FOREIGN KEY (user_id) REFERENCES users(id)
) ENGINE=InnoDB;

-- 资产/负债变动流水：只追加；冲正用 bill_reversal，不覆盖历史
CREATE TABLE IF NOT EXISTS asset_transactions (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  user_id BIGINT NOT NULL,
  account_id BIGINT NULL,
  liability_id BIGINT NULL,
  type VARCHAR(30) NOT NULL DEFAULT 'adjustment',
  direction VARCHAR(4) NOT NULL DEFAULT 'in',              -- in=余额/欠款增加，out=减少
  amount DECIMAL(14,2) NOT NULL DEFAULT 0,
  before_amount DECIMAL(14,2) NOT NULL DEFAULT 0,
  after_amount DECIMAL(14,2) NOT NULL DEFAULT 0,
  note VARCHAR(200) NOT NULL DEFAULT '',
  source VARCHAR(20) NOT NULL DEFAULT 'manual',
  related_bill_id BIGINT NULL,
  transfer_group_id VARCHAR(40) NOT NULL DEFAULT '',
  status VARCHAR(10) NOT NULL DEFAULT 'posted',            -- posted/reversed
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  INDEX idx_asset_tx_user_time (user_id, created_at),
  INDEX idx_asset_tx_account_time (account_id, created_at),
  INDEX idx_asset_tx_liability_time (liability_id, created_at),
  INDEX idx_asset_tx_bill (related_bill_id),
  CONSTRAINT fk_asset_tx_user FOREIGN KEY (user_id) REFERENCES users(id)
) ENGINE=InnoDB;

-- 系统预置分类（与后端 app/main.py 的 DEFAULT_CATEGORIES 一致）
INSERT INTO bill_categories(user_id, name, type) VALUES
  (NULL, '餐饮', 'expense'), (NULL, '交通', 'expense'), (NULL, '购物', 'expense'),
  (NULL, '住房', 'expense'), (NULL, '学习', 'expense'), (NULL, '娱乐', 'expense'),
  (NULL, '医疗', 'expense'), (NULL, '通讯', 'expense'), (NULL, '其他', 'expense'),
  (NULL, '工资', 'income'), (NULL, '兼职', 'income'), (NULL, '理财', 'income'),
  (NULL, '红包', 'income'), (NULL, '退款', 'income'), (NULL, '其他收入', 'income');
