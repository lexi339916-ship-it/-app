<script setup>
import { computed, ref } from 'vue'
import { onLoad } from '@dcloudio/uni-app'
import { loadSimulatorBase, apiSimulateDecision } from '../../api/simulator.js'

const amount = ref('5000')
const categoryIndex = ref(0)
const categories = ref([])
const goals = ref([])
const goalIndex = ref(0)
const horizon = ref('3')
const loading = ref(false)
const initLoading = ref(true)
const error = ref(null)
const result = ref(null)

function money(value) {
  if (value === null || value === undefined || value === '') return '—'
  return Number(value).toFixed(2)
}

function days(value) {
  if (value === null || value === undefined) return '—'
  return `${value} 天`
}

const categoryName = computed(() => categories.value[categoryIndex.value]?.name || '购物')
const goal = computed(() => goals.value[goalIndex.value] || null)
const canRun = computed(() =>
  Number(amount.value) > 0 && categories.value.length > 0 && goals.value.length > 0 && !loading.value)

const missingLabels = {
  goal: '储蓄目标',
  cashflow: '近 3 个月账单',
  budget: '分类预算',
}

async function loadBase() {
  initLoading.value = true
  error.value = null
  try {
    const [cats, gs] = await loadSimulatorBase()
    categories.value = (cats.items || []).filter(c => c.name !== '其他')
    goals.value = gs || []
    const index = categories.value.findIndex(c => c.name === '购物')
    categoryIndex.value = index >= 0 ? index : 0
  } catch (e) {
    error.value = e
  } finally {
    initLoading.value = false
  }
}

function onCategoryChange(e) {
  categoryIndex.value = Number(e.detail.value)
}

function onGoalChange(e) {
  goalIndex.value = Number(e.detail.value)
}

async function simulate() {
  if (!goals.value.length) {
    uni.showToast({ title: '先创建一个储蓄目标', icon: 'none' })
    return
  }
  const value = Number(amount.value)
  if (!value || value <= 0) {
    uni.showToast({ title: '请输入大于 0 的金额', icon: 'none' })
    return
  }
  loading.value = true
  error.value = null
  result.value = null
  try {
    result.value = await apiSimulateDecision({
      amount: String(value),
      category: categoryName.value,
      goal_id: goal.value?.id || null,
      horizon_months: Math.max(1, Number(horizon.value) || 3),
    })
  } catch (e) {
    error.value = e
  } finally {
    loading.value = false
  }
}

function goGoals() {
  uni.navigateTo({ url: '/pages/goals/goals' })
}

function goAddBill() {
  uni.navigateTo({ url: '/pages/bills/edit' })
}

function goBudget() {
  uni.navigateTo({ url: '/pages/budget/center' })
}

onLoad(() => {
  loadBase()
})
</script>

<template>
  <view class="page">
    <view class="hero">
      <text class="hero-title">消费决策模拟</text>
      <text class="hero-sub">买之前先算一算：预算会不会超、目标会不会延期</text>
    </view>

    <view v-if="initLoading" class="card">
      <view class="skeleton skeleton-lg" />
      <view class="skeleton" />
      <text class="muted">正在读取预算和目标…</text>
    </view>

    <view v-else-if="error && !result" class="card state-error">
      <text class="state-title">加载失败</text>
      <text class="state-text">{{ error.message || '网络异常，请稍后重试' }}</text>
      <button class="btn primary small" @click="loadBase">重新加载</button>
    </view>

    <template v-else>
      <view class="card">
        <text class="card-title">这次想买什么？</text>
        <view class="form-row">
          <text class="form-label">金额</text>
          <input class="form-input" type="digit" v-model="amount" placeholder="例如 5000" />
          <text class="form-unit">元</text>
        </view>
        <view class="form-row">
          <text class="form-label">分类</text>
          <picker class="form-picker" :range="categories" range-key="name"
            :value="categoryIndex" @change="onCategoryChange">
            <view class="picker-box">{{ categoryName }} <text class="picker-arrow">⌄</text></view>
          </picker>
        </view>
        <view class="form-row">
          <text class="form-label">关联目标</text>
          <picker class="form-picker" :range="goals" range-key="name"
            :value="goalIndex" @change="onGoalChange">
            <view class="picker-box">
              {{ goal ? `${goal.name}（还差 ¥${money(goal.remaining)}）` : '暂无目标' }}
              <text class="picker-arrow">⌄</text>
            </view>
          </picker>
        </view>
        <view class="form-row">
          <text class="form-label">观察周期</text>
          <input class="form-input" type="number" v-model="horizon" placeholder="3" />
          <text class="form-unit">个月</text>
        </view>

        <view class="goal-empty" v-if="!goals.length">
          <text>还没有储蓄目标，无法判断购买对目标的影响。</text>
          <text class="link" @click="goGoals">去创建目标 ›</text>
        </view>

        <button class="btn primary" :class="{ 'btn-off': !canRun }" :disabled="!canRun" @click="simulate">
          {{ loading ? '正在测算…' : '开始测算' }}
        </button>
      </view>

      <view v-if="loading" class="card">
        <view class="skeleton skeleton-lg" />
        <view class="skeleton" />
        <text class="muted">正在按真实账单、预算和目标计算…</text>
      </view>

      <view v-else-if="error && result === null" class="card state-error">
        <text class="state-title">测算失败</text>
        <text class="state-text">{{ error.message || '请稍后重试' }}</text>
        <button class="btn ghost small" @click="simulate">重试</button>
      </view>

      <template v-if="result">
        <view class="card summary-card" :class="result.available ? '' : 'summary-warn'">
          <view class="row-between">
            <text class="card-title no-margin">测算结论</text>
            <text :class="['level-badge', result.available ? 'tone-good' : 'tone-watch']">
              {{ result.available ? '可以测算' : '数据不足' }}
            </text>
          </view>
          <text class="summary-text">{{ result.message }}</text>
          <view class="missing-row" v-if="result.missing.length">
            <text class="missing-label">还需要补充：</text>
            <text class="missing-tag" v-for="m in result.missing" :key="m">{{ missingLabels[m] || m }}</text>
          </view>
          <view class="quick-actions" v-if="result.missing.length">
            <text class="link" v-if="result.missing.includes('goal')" @click="goGoals">创建目标 ›</text>
            <text class="link" v-if="result.missing.includes('cashflow')" @click="goAddBill">去记一笔 ›</text>
            <text class="link" v-if="result.missing.includes('budget')" @click="goBudget">设置预算 ›</text>
          </view>
          <text class="as-of">截至 {{ result.as_of }}</text>
        </view>

        <!-- 预算冲击 -->
        <view class="card">
          <text class="card-title">预算冲击</text>
          <view class="metric-grid">
            <view class="metric">
              <text class="metric-label">购买金额</text>
              <text class="metric-value">¥{{ money(result.amount) }}</text>
            </view>
            <view class="metric">
              <text class="metric-label">购买前剩余</text>
              <text class="metric-value">{{ result.purchase.available ? '¥' + money(result.purchase.budget_remaining_before) : '未设预算' }}</text>
            </view>
            <view class="metric">
              <text class="metric-label">购买后剩余</text>
              <text class="metric-value" :class="result.purchase.over_budget ? 'expense' : 'income'">
                {{ result.purchase.available ? '¥' + money(result.purchase.budget_remaining_after) : '—' }}
              </text>
            </view>
            <view class="metric">
              <text class="metric-label">本月结余（测算）</text>
              <text class="metric-value" :class="Number(result.purchase.monthly_net_after) < 0 ? 'expense' : 'income'">
                ¥{{ money(result.purchase.monthly_net_after) }}
              </text>
            </view>
          </view>
          <view class="hint-box" v-if="result.purchase.over_budget">
            购买后「{{ result.purchase.category }}」将超出预算 ¥{{ money(result.purchase.over_amount) }}。
          </view>
          <view class="hint-box neutral" v-else-if="result.purchase.available">
            购买后「{{ result.purchase.category }}」预算还剩 ¥{{ money(result.purchase.budget_remaining_after) }}。
          </view>
        </view>

        <!-- 目标影响 -->
        <view class="card" v-if="result.goal">
          <view class="row-between">
            <text class="card-title no-margin">目标影响：{{ result.goal.name }}</text>
            <text :class="['level-badge', (result.goal.delay_days > 0 || result.goal.extra_days) ? 'tone-watch' : 'tone-good']">
              {{ result.goal.delay_days > 0 ? '可能延期' : (result.goal.extra_days ? '完成时间变晚' : '基本不影响') }}
            </text>
          </view>
          <view class="bar-track">
            <view class="bar-fill goal-fill"
              :style="{ width: Math.min(Number(result.goal.progress_ratio) * 100, 100) + '%' }" />
          </view>
          <view class="metric-grid">
            <view class="metric">
              <text class="metric-label">目标差额</text>
              <text class="metric-value">¥{{ money(result.goal.remaining) }}</text>
            </view>
            <view class="metric">
              <text class="metric-label">购买后目标差额</text>
              <text class="metric-value" :class="Number(result.goal.gap_after) > Number(result.goal.gap_before) ? 'expense' : 'income'">
                ¥{{ money(result.goal.gap_after) }}
              </text>
            </view>
            <view class="metric">
              <text class="metric-label">目标截止日影响</text>
              <text class="metric-value">{{ result.goal.delay_days > 0 ? '延期 ' + days(result.goal.delay_days) : '不延期' }}</text>
            </view>
            <view class="metric">
              <text class="metric-label">预计完成</text>
              <text class="metric-value small-text">{{ result.goal.projected_finish_after || '—' }}</text>
            </view>
          </view>
          <text class="goal-note">
            按近 3 个月平均结余 ¥{{ money(result.cashflow.monthly_net) }} 测算；
            购买前预计 {{ result.goal.projected_finish_before || '—' }} 完成。
          </text>
          <text class="goal-note warn" v-if="!result.goal.delay_days && result.goal.extra_days">
            完成时间比不买晚约 {{ result.goal.extra_days }} 天，但仍在观察周期内。
          </text>
        </view>

        <!-- 方案对比 -->
        <view class="card" v-if="result.scenarios.length">
          <text class="card-title">方案对比</text>
          <view class="scenario" v-for="s in result.scenarios" :key="s.key">
            <view class="row-between">
              <text class="scenario-title">{{ s.title }}</text>
              <text :class="['level-badge', 'small', s.feasible ? 'tone-good' : 'tone-watch']">
                {{ s.feasible ? '可行' : '压力较大' }}
              </text>
            </view>
            <text class="scenario-desc">{{ s.description }}</text>
            <view class="scenario-meta">
              <text v-if="s.budget_impact !== null">本月预算影响 ¥{{ money(s.budget_impact) }}</text>
              <text v-if="s.goal_delay_days !== null">
                目标影响 {{ s.goal_delay_days > 0 ? '延期 ' + s.goal_delay_days + ' 天' : '不延期' }}
              </text>
              <text v-else>目标影响 需进一步调整</text>
              <text v-if="Number(s.monthly_cut) > 0">每月需省 ¥{{ money(s.monthly_cut) }}</text>
            </view>
          </view>
        </view>

        <!-- 建议 -->
        <view class="card" v-if="result.recommendations.length">
          <text class="card-title">调整建议</text>
          <view class="advice" v-for="(rec, i) in result.recommendations" :key="i">
            <view class="row-between">
              <text class="advice-title">{{ rec.title }}</text>
              <text :class="['level-badge', 'small', rec.priority === 'high' ? 'tone-bad' : (rec.priority === 'medium' ? 'tone-watch' : 'tone-muted')]">
                {{ rec.priority === 'high' ? '优先处理' : (rec.priority === 'medium' ? '建议关注' : '提示') }}
              </text>
            </view>
            <text class="advice-detail">{{ rec.detail }}</text>
            <text class="advice-impact" v-if="rec.impact_amount !== null">涉及金额 ¥{{ money(rec.impact_amount) }}</text>
            <text class="advice-hint">{{ rec.action_hint }}</text>
          </view>
        </view>

        <view class="footer-note">
          <text>{{ result.disclaimer }}</text>
          <text class="footer-assumption" v-for="(a, i) in result.assumptions" :key="i">· {{ a }}</text>
        </view>
      </template>
    </template>
  </view>
</template>

<style scoped>
.page { padding: 18rpx 24rpx 80rpx; }
.hero { padding: 18rpx 8rpx 20rpx; }
.hero-title { display: block; font-size: 40rpx; font-weight: 800; color: #5A54B8; letter-spacing: 1rpx; }
.hero-sub { display: block; font-size: 23rpx; color: #8A90A8; margin-top: 6rpx; line-height: 1.6; }

.card { background: #FFFDF8; border-radius: 28rpx; padding: 26rpx; margin-bottom: 22rpx;
  box-shadow: 0 10rpx 26rpx rgba(124, 139, 255, .08); border: 1rpx solid #F0EDF8; }
.card-title { display: block; font-size: 30rpx; font-weight: 800; color: #3A3F58; margin-bottom: 16rpx; }
.no-margin { margin-bottom: 0; }
.row-between { display: flex; align-items: center; justify-content: space-between; gap: 12rpx; }
.muted { font-size: 22rpx; color: #A6AAC2; }
.link { font-size: 23rpx; color: #6C7BF5; }
.skeleton { height: 24rpx; background: #F2F0FA; border-radius: 12rpx; margin: 14rpx 0; }
.skeleton-lg { height: 90rpx; }
.state-error { border-color: #FFD7D7; background: #FFF8F8; }
.state-title { display: block; font-size: 30rpx; font-weight: 800; color: #C94F4F; }
.state-text { display: block; font-size: 25rpx; color: #8A90A8; margin: 10rpx 0 18rpx; line-height: 1.6; }

.form-row { display: flex; align-items: center; gap: 14rpx; padding: 14rpx 0;
  border-bottom: 1rpx dashed #F0EDF8; }
.form-row:last-of-type { border-bottom: none; }
.form-label { width: 130rpx; flex-shrink: 0; font-size: 25rpx; color: #5A5F78; }
.form-input { flex: 1; height: 68rpx; background: #FAF9FF; border: 1rpx solid #E9E6F4;
  border-radius: 14rpx; padding: 0 18rpx; font-size: 28rpx; color: #3A3F58; }
.form-unit { font-size: 23rpx; color: #8A90A8; }
.form-picker { flex: 1; }
.picker-box { height: 68rpx; line-height: 68rpx; background: #FAF9FF; border: 1rpx solid #E9E6F4;
  border-radius: 14rpx; padding: 0 18rpx; font-size: 26rpx; color: #3A3F58; }
.picker-arrow { float: right; color: #A6AAC2; }
.goal-empty { margin-top: 14rpx; background: #FFF6E7; border-radius: 14rpx; padding: 14rpx 16rpx;
  font-size: 23rpx; color: #A56A1F; line-height: 1.6; display: flex; justify-content: space-between; gap: 12rpx; }
.btn { margin: 20rpx 0 0; height: 84rpx; line-height: 84rpx; border-radius: 22rpx;
  font-size: 29rpx; font-weight: 700; color: #fff;
  background: linear-gradient(135deg, #7C8BFF 0%, #A78BFA 100%); }
.btn-off { opacity: .55; }
.btn.small { height: 68rpx; line-height: 68rpx; font-size: 26rpx; padding: 0 28rpx; }
.btn.ghost { color: #6C7BF5; background: #F2F1FF; }

.summary-card { border: 2rpx solid #E4E7FB; }
.summary-warn { border-color: #F5D9A8; background: #FFFCF5; }
.summary-text { display: block; font-size: 27rpx; color: #4A4F6B; line-height: 1.75; margin-top: 14rpx; }
.missing-row { display: flex; flex-wrap: wrap; align-items: center; gap: 10rpx; margin-top: 14rpx; }
.missing-label { font-size: 22rpx; color: #8A90A8; }
.missing-tag { font-size: 21rpx; color: #D98A32; background: #FFF6E7; border-radius: 999rpx; padding: 4rpx 14rpx; }
.quick-actions { display: flex; gap: 20rpx; margin-top: 12rpx; }
.as-of { display: block; font-size: 20rpx; color: #A6AAC2; margin-top: 12rpx; }

.metric-grid { display: flex; flex-wrap: wrap; gap: 14rpx; margin-top: 14rpx; }
.metric { width: calc(50% - 7rpx); background: #FAF9FF; border-radius: 18rpx; padding: 16rpx 18rpx;
  box-sizing: border-box; }
.metric-label { display: block; font-size: 22rpx; color: #8A90A8; }
.metric-value { display: block; font-size: 30rpx; font-weight: 800; color: #3A3F58; margin-top: 6rpx; }
.small-text { font-size: 23rpx; }
.income { color: #1FA97F; }
.expense { color: #E45858; }
.hint-box { margin-top: 14rpx; background: #FFEDEE; border-radius: 14rpx; padding: 14rpx 16rpx;
  font-size: 23rpx; color: #C94F4F; line-height: 1.6; }
.hint-box.neutral { background: #F4F2FA; color: #5A5F78; }

.bar-track { height: 14rpx; background: #EFEDF7; border-radius: 8rpx; margin: 14rpx 0; overflow: hidden; }
.bar-fill { height: 100%; border-radius: 8rpx; background: linear-gradient(90deg, #7C8BFF, #A78BFA); }
.goal-fill { background: linear-gradient(90deg, #6FD3B5, #1FA97F); }
.goal-note { display: block; font-size: 21rpx; color: #8A90A8; line-height: 1.6; margin-top: 8rpx; }
.goal-note.warn { color: #D98A32; }

.scenario { padding: 16rpx 0; border-bottom: 1rpx dashed #F0EDF8; }
.scenario:last-child { border-bottom: none; }
.scenario-title { font-size: 27rpx; font-weight: 700; color: #3A3F58; }
.scenario-desc { display: block; font-size: 23rpx; color: #6B7089; line-height: 1.65; margin-top: 6rpx; }
.scenario-meta { display: flex; flex-wrap: wrap; gap: 14rpx; font-size: 21rpx; color: #8A90A8; margin-top: 8rpx; }

.advice { padding: 14rpx 0; border-bottom: 1rpx dashed #F0EDF8; }
.advice:last-child { border-bottom: none; }
.advice-title { font-size: 26rpx; font-weight: 700; color: #3A3F58; flex: 1; }
.advice-detail { display: block; font-size: 23rpx; color: #6B7089; line-height: 1.6; margin-top: 6rpx; }
.advice-impact { display: block; font-size: 22rpx; color: #6C7BF5; margin-top: 4rpx; }
.advice-hint { display: block; font-size: 22rpx; color: #A56A1F; line-height: 1.6; margin-top: 4rpx; }

.level-badge { font-size: 22rpx; font-weight: 700; border-radius: 999rpx; padding: 5rpx 16rpx; }
.level-badge.small { font-size: 20rpx; padding: 3rpx 12rpx; flex-shrink: 0; }
.tone-good { background: #E9F8F2; color: #1FA97F; }
.tone-watch { background: #FFF6E7; color: #D98A32; }
.tone-bad { background: #FFEDEE; color: #E45858; }
.tone-muted { background: #F4F2FA; color: #8A90A8; }

.footer-note { padding: 8rpx 12rpx; font-size: 21rpx; color: #A6AAC2; line-height: 1.7; text-align: center; }
.footer-assumption { display: block; margin-top: 4rpx; font-size: 20rpx; }
</style>
