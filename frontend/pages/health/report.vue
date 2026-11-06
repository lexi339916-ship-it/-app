<script setup>
import { computed, ref } from 'vue'
import { onLoad } from '@dcloudio/uni-app'
import { apiHealthReport } from '../../api/index.js'
import { categoryMeta } from '../../common/category-icons.js'

const month = ref('')
const report = ref(null)
const loading = ref(true)
const error = ref(null)
const expanded = ref({})

function currentMonth() {
  const d = new Date()
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`
}

function shiftMonth(m, delta) {
  const [y, mo] = m.split('-').map(Number)
  const d = new Date(y, mo - 1 + delta, 1)
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`
}

function money(value) {
  if (value === null || value === undefined || value === '') return '—'
  return Number(value).toFixed(2)
}

function pct(value, digits = 0) {
  if (value === null || value === undefined) return '—'
  return (Number(value) * 100).toFixed(digits)
}

function scoreText(value) {
  return value === null || value === undefined ? '—' : Number(value).toFixed(1)
}

function tone(level) {
  return {
    '优秀': 'tone-good',
    '良好': 'tone-ok',
    '需关注': 'tone-watch',
    '需改善': 'tone-bad',
    '数据不足': 'tone-muted',
  }[level] || 'tone-muted'
}

function budgetStatusText(status) {
  return {
    over100: '已超支',
    near80: '接近上限',
    used_up: '已用完',
    ok: '正常',
    none: '未设预算',
  }[status] || status
}

function goalStatusText(status) {
  return {
    achieved: '已达成',
    on_track: '按计划',
    delayed: '预计延期',
    stalled: '进度停滞',
    no_deadline: '未设周期',
  }[status] || status
}

function priorityText(priority) {
  return { high: '优先处理', medium: '建议关注', low: '可以稍后', info: '提示' }[priority] || priority
}

const score = computed(() => report.value?.overall_score)
const isEmpty = computed(() => {
  const r = report.value
  if (!r) return false
  return r.overview.bill_count === 0
    && Number(r.overview.income) === 0
    && (r.goals || []).length === 0
    && !r.subscriptions?.available
})
const nonZeroCategories = computed(() =>
  (report.value?.categories || []).filter(c => Number(c.amount) > 0 || Number(c.budget) > 0).slice(0, 12))

// 分类饼图：直接使用后端分类金额，避免前端另算一套统计
const pieCategories = computed(() =>
  (report.value?.categories || []).filter(c => Number(c.amount) > 0))
const pieTotal = computed(() =>
  pieCategories.value.reduce((sum, c) => sum + Number(c.amount || 0), 0))
const pieStyle = computed(() => {
  const total = pieTotal.value
  if (!total) return {}
  let cursor = 0
  const stops = []
  for (const c of pieCategories.value) {
    const start = cursor
    cursor += (Number(c.amount || 0) / total) * 360
    stops.push(`${categoryMeta(c.category).color} ${start.toFixed(2)}deg ${cursor.toFixed(2)}deg`)
  }
  if (cursor < 359.99) stops.push(`#EFEDF7 ${cursor.toFixed(2)}deg 360deg`)
  return { background: `conic-gradient(${stops.join(',')})` }
})
const pieLegend = computed(() => pieCategories.value.map(c => ({
  ...c,
  color: categoryMeta(c.category).color,
  percent: pieTotal.value > 0 ? (Number(c.amount || 0) / pieTotal.value) * 100 : 0,
})))
const scoreStyle = computed(() => {
  const value = score.value
  if (value === null || value === undefined) return {}
  const deg = Math.max(0, Math.min(100, Number(value))) * 3.6
  return {
    background: `conic-gradient(#7C8BFF 0deg, #A78BFA ${deg}deg, #EEEAF9 ${deg}deg 360deg)`,
  }
})

async function load() {
  if (!month.value) month.value = currentMonth()
  loading.value = true
  error.value = null
  try {
    report.value = await apiHealthReport(month.value)
  } catch (e) {
    error.value = e
  } finally {
    loading.value = false
  }
}

function prevMonth() {
  month.value = shiftMonth(month.value, -1)
  load()
}

function nextMonth() {
  month.value = shiftMonth(month.value, 1)
  load()
}

function toggleFormula(key) {
  expanded.value = { ...expanded.value, [key]: !expanded.value[key] }
}

function goAddBill() {
  uni.navigateTo({ url: '/pages/bills/edit' })
}

function goBudget() {
  uni.navigateTo({ url: '/pages/budget/center?month=' + month.value })
}

function goAgent() {
  uni.switchTab({ url: '/pages/agent/agent' })
}

onLoad((options) => {
  month.value = (options && options.month) || currentMonth()
  load()
})
</script>

<template>
  <view class="page">
    <view class="hero">
      <view class="hero-top">
        <view>
          <text class="hero-title">消费健康诊断</text>
          <text class="hero-sub">业务公式计算 · 数据来源可追溯</text>
        </view>
        <view class="month-nav">
          <text class="month-arrow" @click="prevMonth">‹</text>
          <text class="month-text">{{ month }}</text>
          <text class="month-arrow" @click="nextMonth">›</text>
        </view>
      </view>
    </view>

    <!-- 加载态 -->
    <view v-if="loading" class="card">
      <view class="skeleton skeleton-lg" />
      <view class="skeleton" />
      <view class="skeleton" />
      <text class="muted">正在计算本月健康指标…</text>
    </view>

    <!-- 错误态 -->
    <view v-else-if="error" class="card state-error">
      <text class="state-title">报告加载失败</text>
      <text class="state-text">{{ error.message || '网络异常，请稍后重试' }}</text>
      <button class="btn primary small" @click="load">重新加载</button>
    </view>

    <!-- 空态 -->
    <view v-else-if="isEmpty" class="card empty-card">
      <text class="empty-emoji">✎</text>
      <text class="empty-title">这个月还没有足够的消费数据</text>
      <text class="empty-text">先记几笔账，或设置分类预算，健康报告会自动开始计算。</text>
      <view class="empty-actions">
        <button class="btn primary small" @click="goAddBill">去记一笔</button>
        <button class="btn ghost small" @click="goBudget">设置预算</button>
      </view>
    </view>

    <template v-else-if="report">
      <!-- 总分 -->
      <view class="card score-card">
        <view class="score-ring" :style="scoreStyle">
          <view class="score-inner">
            <text class="score-num">{{ scoreText(score) }}</text>
            <text class="score-label">消费健康分</text>
          </view>
        </view>
        <view class="score-main">
          <view class="score-head">
            <text :class="['level-badge', tone(report.overall_level)]">{{ report.overall_level }}</text>
            <text class="coverage">指标覆盖 {{ pct(report.coverage) }}%</text>
          </view>
          <text class="score-summary">{{ report.summary }}</text>
          <text class="score-time">截至 {{ String(report.generated_at).replace('T', ' ').slice(0, 16) }}</text>
        </view>
      </view>

      <!-- 收支概览 -->
      <view class="card">
        <view class="card-head">
          <text class="card-title">本月收支</text>
          <text class="muted">{{ report.period_start }} ~ {{ report.period_end }}</text>
        </view>
        <view class="metric-grid">
          <view class="metric">
            <text class="metric-label">收入</text>
            <text class="metric-value income">¥{{ money(report.overview.income) }}</text>
          </view>
          <view class="metric">
            <text class="metric-label">支出</text>
            <text class="metric-value expense">¥{{ money(report.overview.expense) }}</text>
          </view>
          <view class="metric">
            <text class="metric-label">结余</text>
            <text class="metric-value" :class="Number(report.overview.net) >= 0 ? 'income' : 'expense'">
              ¥{{ money(report.overview.net) }}
            </text>
          </view>
          <view class="metric">
            <text class="metric-label">结余率</text>
            <text class="metric-value">{{ pct(report.overview.savings_rate) }}%</text>
          </view>
        </view>
        <view class="hint-row" v-if="report.overview.projected_expense">
          <text class="hint">按当前日均支出推算，本月预计支出 ¥{{ money(report.overview.projected_expense) }}</text>
        </view>
        <view class="hint-row" v-if="report.overview.prev_expense">
          <text class="hint">
            上月支出 ¥{{ money(report.overview.prev_expense) }}，
            {{ Number(report.overview.expense_change_amount) >= 0 ? '增加' : '减少' }}
            ¥{{ money(Math.abs(Number(report.overview.expense_change_amount))) }}
            （{{ pct(Math.abs(Number(report.overview.expense_change_ratio || 0))) }}%）
          </text>
        </view>
      </view>

      <!-- 五项指标 -->
      <view class="card">
        <view class="card-head">
          <text class="card-title">健康指标</text>
          <text class="muted">点击查看公式</text>
        </view>
        <view class="indicator" v-for="item in report.indicators" :key="item.key">
          <view class="indicator-head" @click="toggleFormula(item.key)">
            <view class="indicator-left">
              <text class="indicator-name">{{ item.name }}</text>
              <text :class="['level-badge', 'small', tone(item.level)]">{{ item.level }}</text>
            </view>
            <text class="indicator-score">{{ scoreText(item.score) }}</text>
          </view>
          <view class="score-bar">
            <view class="score-bar-fill" :style="{ width: (item.score || 0) + '%' }" />
          </view>
          <text class="indicator-desc">{{ item.explanation }}</text>
          <view class="formula" v-if="expanded[item.key]">
            <text class="formula-title">计算依据</text>
            <text class="formula-text">{{ item.formula }}</text>
            <text class="formula-meta">来源：{{ item.source }} · 周期：{{ item.period }}</text>
            <text class="formula-meta">更新时间：{{ String(item.as_of).replace('T', ' ').slice(0, 16) }}</text>
          </view>
        </view>
      </view>

      <!-- 预算 -->
      <view class="card" v-if="report.budget.available">
        <view class="card-head">
          <text class="card-title">预算执行</text>
          <text class="link" @click="goBudget">管理预算 ›</text>
        </view>
        <view class="budget-line">
          <text class="budget-num">¥{{ money(report.budget.total_spent) }}</text>
          <text class="budget-total">/ ¥{{ money(report.budget.total_budget) }}</text>
          <text class="budget-usage">{{ pct(report.budget.usage_ratio) }}%</text>
        </view>
        <view class="bar-track">
          <view class="bar-fill" :class="{ 'bar-over': Number(report.budget.usage_ratio) > 1 }"
            :style="{ width: Math.min(Number(report.budget.usage_ratio) * 100, 100) + '%' }" />
        </view>
        <view class="tag-row">
          <text class="tag warn">超支 {{ report.budget.over_count }} 类</text>
          <text class="tag">接近上限 {{ report.budget.near_count }} 类</text>
          <text class="tag" v-if="Number(report.budget.unbudgeted_amount) > 0">
            未设预算支出 ¥{{ money(report.budget.unbudgeted_amount) }}
          </text>
        </view>
      </view>

      <!-- 分类结构 -->
      <view class="card" v-if="nonZeroCategories.length">
        <text class="card-title">分类消费结构</text>
        <view class="pie-wrap" v-if="pieTotal > 0">
          <view class="pie" :style="pieStyle">
            <view class="pie-hole">
              <text class="pie-label">总支出</text>
              <text class="pie-total">¥{{ money(pieTotal) }}</text>
            </view>
          </view>
          <view class="pie-legend">
            <view class="legend-item" v-for="c in pieLegend" :key="'legend-' + c.category">
              <text class="legend-dot" :style="{ background: c.color }" />
              <text class="legend-name">{{ c.category }}</text>
              <text class="legend-pct">{{ c.percent.toFixed(1) }}%</text>
            </view>
          </view>
        </view>
        <view class="category-row" v-for="c in nonZeroCategories" :key="c.category">
          <view class="category-main">
            <view class="category-line">
              <text class="category-name">{{ c.category }}</text>
              <text class="category-amount">¥{{ money(c.amount) }}</text>
            </view>
            <view class="bar-track slim">
              <view class="bar-fill" :style="{ width: Math.min(Number(c.ratio) * 100, 100) + '%' }" />
            </view>
            <view class="category-meta">
              <text>占比 {{ pct(c.ratio) }}%</text>
              <text v-if="Number(c.budget) > 0">
                预算 ¥{{ money(c.budget) }} · {{ budgetStatusText(c.budget_status) }}
              </text>
              <text v-if="c.change_ratio !== null" :class="Number(c.change_amount) > 0 ? 'expense' : 'income'">
                环比 {{ Number(c.change_amount) >= 0 ? '+' : '' }}{{ pct(c.change_ratio) }}%
              </text>
            </view>
          </view>
        </view>
      </view>

      <!-- 储蓄目标 -->
      <view class="card" v-if="report.goals.length">
        <text class="card-title">储蓄目标</text>
        <view class="goal-row" v-for="g in report.goals" :key="g.id">
          <view class="category-line">
            <text class="category-name">{{ g.name }}</text>
            <text :class="['level-badge', 'small', g.status === 'delayed' || g.status === 'stalled' ? 'tone-watch' : 'tone-good']">
              {{ goalStatusText(g.status) }}
            </text>
          </view>
          <view class="bar-track slim">
            <view class="bar-fill goal-fill" :style="{ width: Math.min(Number(g.progress_ratio) * 100, 100) + '%' }" />
          </view>
          <view class="category-meta">
            <text>已存 ¥{{ money(g.saved_amount) }} / ¥{{ money(g.target_amount) }}</text>
            <text v-if="g.target_date">目标日 {{ g.target_date }}</text>
          </view>
          <text class="goal-hint" v-if="g.status === 'delayed'">
            按近 3 个月结余估算，预计延期 {{ g.delay_days }} 天；每月需存 ¥{{ money(g.required_monthly) }}。
          </text>
          <text class="goal-hint" v-else-if="g.status === 'stalled'">
            近 3 个月平均结余 ¥{{ money(g.avg_monthly_net) }}，当前无法推进目标。
          </text>
        </view>
      </view>

      <!-- 订阅 -->
      <view class="card" v-if="report.subscriptions.available">
        <text class="card-title">订阅健康</text>
        <view class="metric-grid">
          <view class="metric">
            <text class="metric-label">进行中</text>
            <text class="metric-value">{{ report.subscriptions.active_count }} 个</text>
          </view>
          <view class="metric">
            <text class="metric-label">每月固定</text>
            <text class="metric-value">¥{{ money(report.subscriptions.monthly_amount) }}</text>
          </view>
          <view class="metric">
            <text class="metric-label">本月扣费</text>
            <text class="metric-value">¥{{ money(report.subscriptions.month_spent) }}</text>
          </view>
          <view class="metric">
            <text class="metric-label">支出占比</text>
            <text class="metric-value">{{ pct(report.subscriptions.share_of_expense) }}%</text>
          </view>
        </view>
        <view class="sub-issue" v-for="(issue, i) in report.subscriptions.issues" :key="i">
          <text class="sub-title">{{ issue.name }}</text>
          <text class="sub-desc">{{ issue.message }}</text>
          <text class="sub-impact">估算年化影响 ¥{{ money(issue.annual_impact) }}</text>
        </view>
        <text class="muted" v-if="!report.subscriptions.issues.length">没有发现涨价、低频或重复扣款。</text>
      </view>

      <!-- 变化与异常 -->
      <view class="card" v-if="report.changes.length || report.anomalies.length">
        <text class="card-title">变化与异常</text>
        <view class="change-row" v-for="(c, i) in report.changes" :key="'c' + i">
          <text class="change-title">{{ c.title }}</text>
          <text class="change-desc">{{ c.detail }}</text>
        </view>
        <view class="change-row" v-for="(a, i) in report.anomalies" :key="'a' + i">
          <text class="change-title">⚠ {{ a.title }}</text>
          <text class="change-desc">{{ a.detail }}</text>
        </view>
      </view>

      <!-- 建议 -->
      <view class="card" v-if="report.recommendations.length">
        <text class="card-title">改善建议</text>
        <view class="advice" v-for="(r, i) in report.recommendations" :key="i">
          <view class="advice-head">
            <text class="advice-title">{{ r.title }}</text>
            <text :class="['level-badge', 'small', r.priority === 'high' ? 'tone-bad' : (r.priority === 'medium' ? 'tone-watch' : 'tone-muted')]">
              {{ priorityText(r.priority) }}
            </text>
          </view>
          <text class="advice-detail">{{ r.detail }}</text>
          <text class="advice-impact" v-if="r.impact_amount !== null">
            涉及金额 ¥{{ money(r.impact_amount) }}
          </text>
          <text class="advice-hint">{{ r.action_hint }}</text>
        </view>
      </view>

      <view class="footer-note">
        <text>{{ report.disclaimer }}</text>
        <text class="footer-source">数据来源：{{ report.data_sources.join('、') }}；生成时间 {{ String(report.generated_at).replace('T', ' ').slice(0, 16) }}</text>
      </view>
    </template>
  </view>
</template>

<style scoped>
.page { padding: 18rpx 24rpx 80rpx; }
.hero { padding: 18rpx 8rpx 20rpx; }
.hero-top { display: flex; align-items: flex-start; justify-content: space-between; gap: 16rpx; }
.hero-title { display: block; font-size: 40rpx; font-weight: 800; color: #5A54B8; letter-spacing: 1rpx; }
.hero-sub { display: block; font-size: 23rpx; color: #8A90A8; margin-top: 6rpx; }
.month-nav { display: flex; align-items: center; gap: 10rpx; background: #F2F1FF;
  border-radius: 999rpx; padding: 6rpx 14rpx; flex-shrink: 0; }
.month-arrow { font-size: 34rpx; color: #6C7BF5; padding: 0 6rpx; }
.month-text { font-size: 23rpx; color: #5A5F78; font-weight: 700; }

.card { background: #FFFDF8; border-radius: 28rpx; padding: 26rpx; margin-bottom: 22rpx;
  box-shadow: 0 10rpx 26rpx rgba(124, 139, 255, .08); border: 1rpx solid #F0EDF8; }
.card-head { display: flex; align-items: center; justify-content: space-between; gap: 12rpx; }
.card-title { display: block; font-size: 30rpx; font-weight: 800; color: #3A3F58; margin-bottom: 16rpx; }
.muted { font-size: 22rpx; color: #A6AAC2; }
.link { font-size: 23rpx; color: #6C7BF5; flex-shrink: 0; }

.skeleton { height: 24rpx; background: #F2F0FA; border-radius: 12rpx; margin: 14rpx 0; }
.skeleton-lg { height: 90rpx; }
.state-error { border-color: #FFD7D7; background: #FFF8F8; }
.state-title { display: block; font-size: 30rpx; font-weight: 800; color: #C94F4F; }
.state-text { display: block; font-size: 25rpx; color: #8A90A8; margin: 10rpx 0 18rpx; line-height: 1.6; }
.empty-card { text-align: center; padding: 44rpx 30rpx; }
.empty-emoji { display: block; font-size: 66rpx; color: #B9B0EA; }
.empty-title { display: block; font-size: 31rpx; font-weight: 800; color: #3A3F58; margin-top: 10rpx; }
.empty-text { display: block; font-size: 25rpx; color: #8A90A8; line-height: 1.7; margin: 12rpx 0 22rpx; }
.empty-actions { display: flex; justify-content: center; gap: 16rpx; }

.score-card { display: flex; align-items: center; gap: 24rpx; }
.score-ring { width: 168rpx; height: 168rpx; border-radius: 50%; padding: 14rpx; flex-shrink: 0; }
.score-inner { width: 100%; height: 100%; border-radius: 50%; background: #FFFDF8;
  display: flex; flex-direction: column; align-items: center; justify-content: center; }
.score-num { font-size: 48rpx; font-weight: 800; color: #5A54B8; line-height: 1.1; }
.score-label { font-size: 20rpx; color: #8A90A8; margin-top: 4rpx; }
.score-main { flex: 1; min-width: 0; }
.score-head { display: flex; align-items: center; gap: 12rpx; }
.level-badge { font-size: 22rpx; font-weight: 700; border-radius: 999rpx; padding: 5rpx 16rpx;
  background: #EFF1FF; color: #6C7BF5; }
.level-badge.small { font-size: 20rpx; padding: 3rpx 12rpx; flex-shrink: 0; }
.tone-good { background: #E9F8F2; color: #1FA97F; }
.tone-ok { background: #EFF1FF; color: #6C7BF5; }
.tone-watch { background: #FFF6E7; color: #D98A32; }
.tone-bad { background: #FFEDEE; color: #E45858; }
.tone-muted { background: #F4F2FA; color: #8A90A8; }
.coverage { font-size: 21rpx; color: #A6AAC2; }
.score-summary { display: block; font-size: 26rpx; color: #4A4F6B; line-height: 1.7; margin-top: 12rpx; }
.score-time { display: block; font-size: 21rpx; color: #A6AAC2; margin-top: 8rpx; }

.metric-grid { display: flex; flex-wrap: wrap; gap: 14rpx; }
.metric { width: calc(50% - 7rpx); background: #FAF9FF; border-radius: 18rpx; padding: 16rpx 18rpx;
  box-sizing: border-box; }
.metric-label { display: block; font-size: 22rpx; color: #8A90A8; }
.metric-value { display: block; font-size: 32rpx; font-weight: 800; color: #3A3F58; margin-top: 6rpx; }
.income { color: #1FA97F; }
.expense { color: #E45858; }
.hint-row { margin-top: 12rpx; }
.hint { font-size: 23rpx; color: #8A90A8; line-height: 1.6; }

.indicator { padding: 18rpx 0; border-bottom: 1rpx dashed #F0EDF8; }
.indicator:last-child { border-bottom: none; }
.indicator-head { display: flex; align-items: center; justify-content: space-between; gap: 12rpx; }
.indicator-left { display: flex; align-items: center; gap: 12rpx; flex: 1; min-width: 0; }
.indicator-name { font-size: 27rpx; font-weight: 700; color: #3A3F58; }
.indicator-score { font-size: 34rpx; font-weight: 800; color: #5A54B8; }
.score-bar { height: 12rpx; background: #EFEDF7; border-radius: 8rpx; margin: 12rpx 0 10rpx; overflow: hidden; }
.score-bar-fill { height: 100%; border-radius: 8rpx; background: linear-gradient(90deg, #7C8BFF, #A78BFA); }
.indicator-desc { display: block; font-size: 23rpx; color: #6B7089; line-height: 1.65; }
.formula { margin-top: 12rpx; background: #FAF9FF; border-radius: 14rpx; padding: 14rpx 16rpx; }
.formula-title { display: block; font-size: 21rpx; font-weight: 700; color: #6C7BF5; }
.formula-text { display: block; font-size: 22rpx; color: #4A4F6B; line-height: 1.6; margin-top: 6rpx; }
.formula-meta { display: block; font-size: 20rpx; color: #A6AAC2; margin-top: 4rpx; }

.budget-line { display: flex; align-items: baseline; gap: 8rpx; }
.budget-num { font-size: 40rpx; font-weight: 800; color: #3A3F58; }
.budget-total { font-size: 24rpx; color: #8A90A8; }
.budget-usage { margin-left: auto; font-size: 24rpx; color: #6C7BF5; font-weight: 700; }
.bar-track { height: 16rpx; background: #EFEDF7; border-radius: 8rpx; margin: 14rpx 0; overflow: hidden; }
.bar-track.slim { height: 10rpx; margin: 8rpx 0; }
.bar-fill { height: 100%; border-radius: 8rpx; background: linear-gradient(90deg, #7C8BFF, #A78BFA); }
.bar-over { background: linear-gradient(90deg, #F27E7E, #E45858); }
.tag-row { display: flex; flex-wrap: wrap; gap: 10rpx; }
.tag { font-size: 21rpx; color: #6B7089; background: #F4F2FA; border-radius: 999rpx; padding: 5rpx 14rpx; }
.tag.warn { background: #FFF6E7; color: #D98A32; }

.pie-wrap { display: flex; align-items: center; gap: 24rpx; margin: 8rpx 0 22rpx; }
.pie { width: 230rpx; height: 230rpx; border-radius: 50%; flex-shrink: 0; position: relative; }
.pie-hole { position: absolute; inset: 34rpx; background: #FFFDF8; border-radius: 50%;
  display: flex; flex-direction: column; align-items: center; justify-content: center; }
.pie-label { font-size: 19rpx; color: #8A90A8; }
.pie-total { font-size: 24rpx; font-weight: 800; color: #3A3F58; margin-top: 4rpx; }
.pie-legend { flex: 1; min-width: 0; display: flex; flex-wrap: wrap; gap: 10rpx 14rpx; }
.legend-item { width: calc(50% - 7rpx); display: flex; align-items: center; gap: 8rpx; }
.legend-dot { width: 14rpx; height: 14rpx; border-radius: 50%; flex-shrink: 0; }
.legend-name { font-size: 20rpx; color: #5A5F78; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.legend-pct { font-size: 19rpx; color: #8A90A8; margin-left: auto; }
.category-row { padding: 14rpx 0; border-bottom: 1rpx dashed #F0EDF8; }
.category-row:last-child { border-bottom: none; }
.category-main { min-width: 0; }
.category-line { display: flex; align-items: center; justify-content: space-between; gap: 12rpx; }
.category-name { font-size: 27rpx; font-weight: 700; color: #3A3F58; }
.category-amount { font-size: 28rpx; font-weight: 800; color: #3A3F58; }
.category-meta { display: flex; flex-wrap: wrap; gap: 14rpx; font-size: 20rpx; color: #8A90A8; margin-top: 4rpx; }

.goal-row { padding: 14rpx 0; border-bottom: 1rpx dashed #F0EDF8; }
.goal-row:last-child { border-bottom: none; }
.goal-fill { background: linear-gradient(90deg, #6FD3B5, #1FA97F); }
.goal-hint { display: block; font-size: 21rpx; color: #D98A32; line-height: 1.6; margin-top: 6rpx; }

.sub-issue { margin-top: 14rpx; background: #FFFAF0; border: 1rpx solid #F5D9A8; border-radius: 16rpx;
  padding: 14rpx 16rpx; }
.sub-title { display: block; font-size: 25rpx; font-weight: 700; color: #A56A1F; }
.sub-desc { display: block; font-size: 23rpx; color: #6B7089; line-height: 1.6; margin-top: 4rpx; }
.sub-impact { display: block; font-size: 22rpx; color: #D98A32; margin-top: 4rpx; }

.change-row { padding: 12rpx 0; border-bottom: 1rpx dashed #F0EDF8; }
.change-row:last-child { border-bottom: none; }
.change-title { display: block; font-size: 25rpx; font-weight: 700; color: #3A3F58; }
.change-desc { display: block; font-size: 22rpx; color: #8A90A8; line-height: 1.6; margin-top: 4rpx; }

.advice { padding: 16rpx 0; border-bottom: 1rpx dashed #F0EDF8; }
.advice:last-child { border-bottom: none; }
.advice-head { display: flex; align-items: center; justify-content: space-between; gap: 12rpx; }
.advice-title { font-size: 26rpx; font-weight: 700; color: #3A3F58; flex: 1; }
.advice-detail { display: block; font-size: 23rpx; color: #6B7089; line-height: 1.6; margin-top: 6rpx; }
.advice-impact { display: block; font-size: 22rpx; color: #6C7BF5; margin-top: 4rpx; }
.advice-hint { display: block; font-size: 22rpx; color: #A56A1F; line-height: 1.6; margin-top: 4rpx; }

.footer-note { padding: 8rpx 12rpx; font-size: 21rpx; color: #A6AAC2; line-height: 1.7; text-align: center; }
.footer-source { display: block; margin-top: 6rpx; font-size: 20rpx; }

.btn { flex: 1; margin: 0; height: 82rpx; line-height: 82rpx; border-radius: 22rpx;
  font-size: 28rpx; font-weight: 700; }
.btn.primary { color: #fff; background: linear-gradient(135deg, #7C8BFF 0%, #A78BFA 100%); }
.btn.ghost { color: #6C7BF5; background: #F2F1FF; }
.btn.small { height: 68rpx; line-height: 68rpx; font-size: 26rpx; padding: 0 28rpx; flex: 0; }
</style>
