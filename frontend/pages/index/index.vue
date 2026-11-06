<script setup>
import { ref, computed } from 'vue'
import { onShow, onPullDownRefresh } from '@dcloudio/uni-app'
import { apiMonthlyStats, apiBills, apiNotes, apiInsight, apiParseReceipt, apiHealthReport } from '../../api/index.js'
import { categoryMeta } from '../../common/category-icons.js'
import { syncSubscriptions } from '../../common/subscription-notify.js'
import store from '../../store/user.js'

const month = ref('')
const stats = ref({ income: '0', expense: '0', net: '0', count: 0, days: [] })
const recentBills = ref([])
const todos = ref([])
const pendingCount = ref(0)
const todayDueCount = ref(0)
const health = ref(null)

// AI 洞察卡状态
const insightText = ref('')
const insightLoading = ref(false)
const insightNotice = ref('')

const nickname = computed(() =>
  store.user?.nickname || store.user?.username || '朋友')

const todayText = computed(() => {
  const d = new Date()
  const names = '日一二三四五六'
  return `${d.getMonth() + 1}月${d.getDate()}日 周${names[d.getDay()]}`
})

const greeting = computed(() => {
  const h = new Date().getHours()
  if (h < 6) return '夜深了，记完这笔早点休息'
  if (h < 11) return '早上好，今天也要好好记账呀'
  if (h < 14) return '中午好，别忘了记下这顿饭'
  if (h < 18) return '下午好，来看看今天的开销吧'
  return '晚上好，今天记账了吗'
})

const netColor = computed(() =>
  (Number(stats.value.net) >= 0 ? '#1F9D74' : '#DE4F4F'))

const healthScore = computed(() => {
  const value = health.value?.overall_score
  return value === null || value === undefined ? '—' : Number(value).toFixed(1)
})
const healthTop = computed(() => (health.value?.recommendations || [])[0] || null)

function pct(value) {
  if (value === null || value === undefined) return '—'
  return Math.round(Number(value) * 100)
}

function currentMonth() {
  const d = new Date()
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`
}

function shiftMonth(m, delta) {
  const [y, mo] = m.split('-').map(Number)
  const d = new Date(y, mo - 1 + delta, 1)
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`
}

// 近 7 日支出迷你趋势（取自月度按日明细）
const weekBars = computed(() => {
  if (!stats.value.days || !stats.value.days.length) return []
  const days = stats.value.days
  const isCurrent = month.value === currentMonth()
  const cutoff = isCurrent ? new Date().getDate() : days.length
  const slice = days.slice(Math.max(0, cutoff - 7), cutoff)
  const max = Math.max(...slice.map(d => Number(d.expense)), 1)
  return slice.map(d => {
    const amount = Number(d.expense)
    return {
      label: String(d.date).slice(8, 10),
      pct: amount > 0 ? Math.max(14, Math.round(amount / max * 100)) : 6,
      has: amount > 0,
    }
  })
})

async function loadInsight(refresh = false) {
  insightLoading.value = true
  try {
    const res = await apiInsight(refresh)
    insightText.value = res.text
    insightNotice.value = res.notice || ''
  } catch (e) {
    insightText.value = ''
  } finally {
    insightLoading.value = false
  }
}

async function loadAll() {
  if (!store.token) return
  try {
    const [s, bills, notes, todayNotes, h] = await Promise.all([
      apiMonthlyStats(month.value),
      apiBills({ month: month.value, page: 1, page_size: 5 }),
      apiNotes({ note_type: 'todo', status: 'open', page: 1, page_size: 3 }),
      apiNotes({ view: 'today', page: 1, page_size: 1 }),
      apiHealthReport(month.value).catch(() => null),
    ])
    stats.value = s
    health.value = h
    recentBills.value = bills.items
    todos.value = notes.items
    pendingCount.value = notes.total
    todayDueCount.value = todayNotes.total
  } catch (e) { /* 统一提示已处理 */ }
}


function goHealth() {
  uni.navigateTo({ url: '/pages/health/report?month=' + month.value })
}

function prevMonth() { month.value = shiftMonth(month.value, -1); loadAll() }
function nextMonth() { month.value = shiftMonth(month.value, 1); loadAll() }

// ---------- 截图记账：选图 → OCR 识别 → 预填记账表单 ----------
const shooting = ref(false)

function shootReceipt() {
  if (shooting.value) return
  shooting.value = true
  uni.chooseImage({
    count: 1,
    sizeType: ['compressed'],
    sourceType: ['album', 'camera'], // 相机拍摄或相册选择小票/支付截图
    success: async (res) => {
      const path = res.tempFilePaths && res.tempFilePaths[0]
      if (!path) { shooting.value = false; return }
      uni.showLoading({ title: '识别中…', mask: true })
      try {
        const data = await apiParseReceipt(path)
        if (!data.found || !data.drafts || !data.drafts.length) {
          uni.showToast({ title: data.notice || '未识别到支付信息', icon: 'none', duration: 2500 })
          return
        }
        // 截图草稿统一进 Agent 工具抽屉确认，不再跳到独立 AI 助手页
        uni.setStorageSync('agent_pending_receipt', JSON.stringify(data.drafts))
        uni.showToast({ title: `识别到 ${data.drafts.length} 笔，请在 Agent 确认`, icon: 'none', duration: 2200 })
        setTimeout(() => uni.switchTab({ url: '/pages/agent/agent' }), 500)
      } catch (e) { /* 识别失败由请求层统一提示 */ }
      finally {
        uni.hideLoading()
        shooting.value = false
      }
    },
    fail: () => { shooting.value = false },
  })
}

onShow(() => {
  if (!store.token) {
    uni.reLaunch({ url: '/pages/login/login' })
    return
  }
  if (!month.value) month.value = currentMonth()
  loadAll()
  loadInsight(false)
  // 订阅扣费：到达扣费日自动生成账单；扣费前 1 天弹窗提醒
  syncSubscriptions().then((res) => {
    // 自动生成了新账单，刷新首页统计
    if (res && res.created_count > 0) {
      loadAll()
      loadInsight(false)
    }
  })
})

onPullDownRefresh(() => {
  Promise.all([loadAll(), loadInsight(false)])
    .finally(() => uni.stopPullDownRefresh())
})
</script>

<template>
  <view class="page">
    <!-- 手账页眉 -->
    <view class="header">
      <view class="header-top">
        <view class="header-left">
          <text class="date-text">{{ todayText }}</text>
          <text class="header-deco">✧ ✦</text>
        </view>
        <image class="header-cat" src="/static/doodles/cat.png" mode="widthFix" />
      </view>
      <text class="page-title">你好，{{ nickname }}</text>
      <image class="title-underline" src="/static/doodles/underline.png" mode="widthFix" />
      <text class="greeting">{{ greeting }}</text>
    </view>

    <!-- 月度结余手账卡 -->
    <view class="hero">
      <view class="washi" />
      <image class="hero-stars" src="/static/doodles/stars.png" mode="widthFix" />
      <view class="month-nav">
        <text class="arrow" @click="prevMonth">‹</text>
        <text class="month">{{ month.slice(0, 4) }}年{{ Number(month.slice(5)) }}月</text>
        <text class="arrow" @click="nextMonth">›</text>
      </view>
      <text class="net-label">本月结余</text>
      <text class="net-num" :style="{ color: netColor }">
        {{ Number(stats.net) >= 0 ? '' : '-' }}¥{{ Math.abs(Number(stats.net)).toFixed(2) }}
      </text>
      <view class="io-row">
        <text class="io-chip">收入 ¥{{ Number(stats.income).toFixed(2) }}</text>
        <text class="io-chip">支出 ¥{{ Number(stats.expense).toFixed(2) }}</text>
      </view>
      <!-- 近 7 日支出趋势 -->
      <view class="trend" v-if="weekBars.length">
        <view class="trend-col" v-for="(b, i) in weekBars" :key="i">
          <view class="trend-bar" :class="{ 'trend-has': b.has }" :style="{ height: b.pct + '%' }" />
          <text class="trend-label">{{ b.label }}</text>
        </view>
      </view>
    </view>

    <!-- 截图记账入口（突出）：唤起相机/相册 → OCR 识别 → 预填记账表单 -->
    <view class="shoot-card" @click="shootReceipt">
      <view class="shoot-icon">
        <image class="shoot-img" src="/static/icons/act_camera.png" mode="widthFix" />
      </view>
      <view class="shoot-main">
        <text class="shoot-title">拍张截图，自动记账</text>
        <text class="shoot-sub">上传支付截图 / 小票 · AI 识别金额、商户与渠道</text>
      </view>
      <text class="shoot-arrow">›</text>
    </view>

    <!-- AI 洞察卡 -->
    <view class="insight-card card-sketch">
      <image class="insight-tape" src="/static/doodles/tape_lilac.png" mode="widthFix" />
      <image class="insight-coffee" src="/static/doodles/coffee.png" mode="widthFix" />
      <view class="insight-head">
        <view class="insight-badge">✦ AI 小助手</view>
        <text class="insight-refresh" @click="loadInsight(true)">刷新</text>
      </view>
      <view v-if="insightLoading" class="insight-loading">
        <text class="dot" /><text class="dot" /><text class="dot" />
      </view>
      <text v-else class="insight-text">{{ insightText || '继续记账，AI 会给出越来越多有用的提示' }}</text>
      <text v-if="insightNotice" class="insight-notice">{{ insightNotice }}</text>
    </view>

    <!-- 消费健康概览（点击进入完整诊断） -->
    <view class="card health-card" v-if="health" @click="goHealth">
      <view class="row-between">
        <view class="health-head-left">
          <text class="budget-title">消费健康</text>
          <text class="health-level">{{ health.overall_level }}</text>
        </view>
        <text class="agent-unread">完整诊断 ›</text>
      </view>
      <view class="health-body">
        <view class="health-score-box">
          <text class="health-score">{{ healthScore }}</text>
          <text class="health-score-label">健康分</text>
        </view>
        <view class="health-main">
          <text class="health-summary">{{ health.summary }}</text>
          <view class="health-tags">
            <text class="health-tag" v-if="health.budget.available">
              预算 {{ pct(health.budget.usage_ratio) }}%
            </text>
            <text class="health-tag">指标覆盖 {{ pct(health.coverage) }}%</text>
          </view>
        </view>
      </view>
      <view class="health-tip" v-if="healthTop">
        <text>优先建议：{{ healthTop.title }}</text>
      </view>
    </view>

    <!-- 旧整月预算卡已下线：预算统一在预算中心按分类管理 -->

    <!-- 快捷入口 -->
    <view class="quick">
      <view class="quick-item" @click="uni.navigateTo({ url: '/pages/bills/edit' })">
        <view class="quick-icon q-blue">
          <image class="quick-img" src="/static/icons/act_pencil.png" mode="widthFix" />
        </view>
        <text>记一笔</text>
      </view>
      <view class="quick-item" @click="uni.switchTab({ url: '/pages/agent/agent' })">
        <view class="quick-icon q-green">
          <image class="quick-img" src="/static/icons/act_sparkle.png" mode="widthFix" />
        </view>
        <text>Agent</text>
      </view>
      <view class="quick-item" @click="uni.navigateTo({ url: '/pages/notes/edit' })">
        <view class="quick-icon q-orange">
          <image class="quick-img" src="/static/icons/act_note.png" mode="widthFix" />
        </view>
        <text>写便签</text>
      </view>
      <view class="quick-item" @click="uni.navigateTo({ url: '/pages/statistics/statistics' })">
        <view class="quick-icon q-purple">
          <image class="quick-img" src="/static/icons/act_chart.png" mode="widthFix" />
        </view>
        <text>看统计</text>
      </view>
    </view>

    <!-- 最近账单 -->
    <view class="card">
      <view class="section-title">
        <view class="title-line">
          <image class="title-doodle" src="/static/doodles/flower.png" mode="widthFix" />
          <text>最近账单</text>
        </view>
        <text class="section-more" @click="uni.switchTab({ url: '/pages/bills/list' })">全部 ›</text>
      </view>
      <view v-if="recentBills.length === 0" class="empty">本月还没有账单，记一笔吧</view>
      <view class="bill-row" v-for="b in recentBills" :key="b.id"
        @click="uni.navigateTo({ url: '/pages/bills/edit?id=' + b.id })">
        <view class="cat-icon" :style="{ background: categoryMeta(b.category).color + '22' }">
          <image class="cat-img" :src="categoryMeta(b.category).img" mode="widthFix" />
        </view>
        <view class="bill-left">
          <text class="bill-cat">{{ b.category }}</text>
          <text class="bill-remark">{{ b.remark || (b.type === 'income' ? '收入' : '支出') }}</text>
        </view>
        <text class="bill-amount" :class="b.type === 'income' ? 'amount-in' : 'amount-out'">
          {{ b.type === 'income' ? '+' : '-' }}{{ Number(b.amount).toFixed(2) }}
        </text>
      </view>
    </view>

    <!-- 待办摘要 -->
    <view class="card">
      <view class="section-title">
        <view class="title-line">
          <image class="title-doodle" src="/static/doodles/heart.png" mode="widthFix" />
          <text>待办事项（{{ pendingCount }}）</text>
        </view>
        <text class="section-more" @click="uni.switchTab({ url: '/pages/notes/list' })">全部 ›</text>
      </view>
      <view v-if="todayDueCount > 0" class="overdue-tip" @click="uni.switchTab({ url: '/pages/notes/list' })">
        ⏰ 今天/已逾期 <text class="overdue-num">{{ todayDueCount }}</text> 项，记得处理
      </view>
      <view v-if="todos.length === 0" class="empty">暂无待办，安排得井井有条</view>
      <view class="todo-row" v-for="n in todos" :key="n.id">
        <view class="todo-dot" />
        <text class="todo-title">{{ n.title }}</text>
        <text class="todo-due" v-if="n.due_at">截止 {{ String(n.due_at).slice(5, 10) }}</text>
      </view>
    </view>
  </view>
</template>

<style scoped>
.page { padding-bottom: 40rpx; }

/* 页眉 */
.header { position: relative; padding: 28rpx 32rpx 6rpx; }
.header-top { display: flex; justify-content: space-between; align-items: flex-start; }
.header-left { display: flex; flex-direction: column; gap: 6rpx; padding-top: 12rpx; }
.date-text { font-size: 26rpx; color: #8A90A8; letter-spacing: 1rpx; }
.header-deco { font-size: 26rpx; color: #C7B7F7; letter-spacing: 8rpx; }
.header-actions { display: flex; align-items: center; gap: 14rpx; }
.header-cat { width: 136rpx; height: 110rpx; margin-top: -12rpx; }
.header .page-title { margin: 10rpx 0 2rpx; }
.title-underline { display: block; width: 224rpx; height: 26rpx; margin: 0 0 8rpx 4rpx; opacity: .75; }
.greeting { display: block; font-size: 27rpx; color: #8A90A8; letter-spacing: 1rpx; }

/* 结余手账卡（水彩质感 + 手绘边框） */
.hero { position: relative; margin: 22rpx 24rpx 0; padding: 34rpx 30rpx 26rpx;
  border-radius: 260rpx 26rpx 240rpx 22rpx / 22rpx 240rpx 26rpx 260rpx;
  overflow: hidden; color: #5A5F78;
  border: 3rpx solid #4E5170;
  background:
    radial-gradient(circle at 18% 12%, rgba(206, 217, 255, .95) 0%, rgba(206, 217, 255, 0) 55%),
    radial-gradient(circle at 85% 22%, rgba(236, 223, 255, .95) 0%, rgba(236, 223, 255, 0) 60%),
    linear-gradient(160deg, #F5F2FF 0%, #E9E5F8 100%);
  box-shadow: 8rpx 10rpx 0 rgba(120, 110, 180, .12); }
.hero-stars { position: absolute; right: 18rpx; top: 8rpx; width: 116rpx; opacity: .92;
  transform: rotate(4deg); }
.month-nav { display: flex; align-items: center; justify-content: center; gap: 30rpx; }
.arrow { font-size: 42rpx; color: #6B7089; padding: 0 18rpx; }
.month { font-size: 29rpx; font-weight: 700; color: #5A5F78; letter-spacing: 1rpx; }
.net-label { display: block; text-align: center; font-size: 26rpx; color: #8A90A8; margin-top: 24rpx; }
.net-num { display: block; text-align: center; font-size: 76rpx; font-weight: 800;
  letter-spacing: 1rpx; margin: 8rpx 0 14rpx; }
.io-row { display: flex; justify-content: center; gap: 18rpx; }
.io-chip { font-size: 26rpx; color: #5A5F78; background: rgba(255, 255, 255, .55);
  border: 1rpx solid rgba(255, 255, 255, .9); border-radius: 999rpx; padding: 8rpx 22rpx; }
.trend { display: flex; align-items: flex-end; gap: 10rpx; height: 104rpx;
  margin-top: 26rpx; padding-top: 6rpx; border-top: 1rpx dashed #D8D3EC; }
.trend-col { flex: 1; height: 100%; display: flex; flex-direction: column;
  align-items: center; justify-content: flex-end; }
.trend-bar { width: 62%; border-radius: 8rpx 8rpx 3rpx 3rpx; background: #D7DBF2; }
.trend-has { background: #A9B4F5; }
.trend-label { font-size: 20rpx; color: #8A90A8; margin-top: 8rpx; }

/* 截图记账入口 */
.shoot-card { display: flex; align-items: center; margin: 20rpx 24rpx 0; padding: 26rpx 26rpx;
  background: #FFFDF8; border: 3rpx dashed #8B7FE8;
  border-radius: 255rpx 22rpx 235rpx 18rpx / 18rpx 235rpx 20rpx 255rpx;
  box-shadow: 6rpx 8rpx 0 rgba(120, 110, 180, .10); }
.shoot-card:active { opacity: .88; }
.shoot-icon { width: 92rpx; height: 92rpx; border-radius: 28rpx; flex-shrink: 0;
  background: #F4F0FF; display: flex; align-items: center; justify-content: center; }
.shoot-img { width: 60rpx; height: 60rpx; }
.shoot-main { flex: 1; margin-left: 22rpx; min-width: 0; }
.shoot-title { display: block; font-size: 31rpx; font-weight: 800; color: #4A4F6B; letter-spacing: 1rpx; }
.shoot-sub { display: block; font-size: 25rpx; color: #A6AAC2; margin-top: 8rpx; }
.shoot-arrow { font-size: 38rpx; color: #C3C7DA; padding-left: 10rpx; }

/* AI 洞察 */
.insight-card { position: relative; background: linear-gradient(180deg, #FBFAFF 0%, #FFFDF8 70%); }
.insight-tape { position: absolute; top: -20rpx; left: 34rpx; width: 132rpx; transform: rotate(-5deg); }
.insight-coffee { position: absolute; right: 16rpx; bottom: 6rpx; width: 82rpx; opacity: .85;
  transform: rotate(3deg); }
.insight-head { display: flex; justify-content: space-between; align-items: center; }
.insight-badge { font-size: 26rpx; font-weight: 800; color: #7C6FE0; letter-spacing: 1rpx; }
.insight-refresh { font-size: 25rpx; color: #A6AAC2; padding: 4rpx 12rpx; }
.insight-text { display: block; font-size: 28rpx; line-height: 1.75; color: #4A4F6B;
  margin-top: 14rpx; padding-right: 88rpx; }
.insight-notice { display: block; font-size: 23rpx; color: #A6AAC2; margin-top: 8rpx; }
.insight-loading { display: flex; gap: 10rpx; padding: 18rpx 0 6rpx; }
.dot { width: 14rpx; height: 14rpx; border-radius: 7rpx; background: #BFB4F2;
  animation: blink 1.2s infinite ease-in-out; }
.dot:nth-child(2) { animation-delay: .2s; }
.dot:nth-child(3) { animation-delay: .4s; }
@keyframes blink { 0%, 80%, 100% { opacity: .25; } 40% { opacity: 1; } }

/* 预算 */
.row-between { display: flex; justify-content: space-between; align-items: center; }
.budget-title { font-size: 30rpx; font-weight: 700; }
.budget-nums { font-size: 26rpx; color: #5A5F78; }
.bar-track { height: 16rpx; background: #EFEDF7; border-radius: 8rpx; margin: 20rpx 0 12rpx; overflow: hidden; }
.bar-fill { height: 100%; border-radius: 8rpx; transition: width .3s; }
.budget-hint { font-size: 25rpx; color: #8A90A8; }
.health-card { border: 2rpx solid #E4E7FB; }
.health-head-left { display: flex; align-items: center; gap: 12rpx; }
.health-level { font-size: 21rpx; font-weight: 700; color: #6C7BF5; background: #EFF1FF;
  border-radius: 999rpx; padding: 4rpx 14rpx; }
.health-body { display: flex; align-items: center; gap: 20rpx; margin-top: 18rpx; }
.health-score-box { width: 132rpx; height: 132rpx; border-radius: 50%; flex-shrink: 0;
  background: linear-gradient(160deg, #F0EDFF 0%, #E4E0FA 100%);
  display: flex; flex-direction: column; align-items: center; justify-content: center;
  border: 2rpx solid #D9D3F5; }
.health-score { font-size: 42rpx; font-weight: 800; color: #5A54B8; line-height: 1.1; }
.health-score-label { font-size: 19rpx; color: #8A90A8; margin-top: 2rpx; }
.health-main { flex: 1; min-width: 0; }
.health-summary { display: block; font-size: 24rpx; color: #4A4F6B; line-height: 1.65; }
.health-tags { display: flex; flex-wrap: wrap; gap: 10rpx; margin-top: 10rpx; }
.health-tag { font-size: 20rpx; color: #6C7BF5; background: #F2F1FF;
  border-radius: 999rpx; padding: 4rpx 12rpx; }
.health-tip { margin-top: 14rpx; background: #FFFAF0; border-radius: 14rpx;
  padding: 12rpx 16rpx; font-size: 22rpx; color: #A56A1F; line-height: 1.6; }
.agent-tip-card { border: 2rpx solid #E4E7FB; }
.agent-unread { font-size: 23rpx; color: #6C7BF5; }
.agent-tip { display: flex; align-items: flex-start; gap: 12rpx; margin-top: 14rpx; }
.agent-dot { width: 12rpx; height: 12rpx; border-radius: 50%; background: #6C7BF5;
  margin-top: 10rpx; flex-shrink: 0; }
.agent-critical { background: #E45858; }
.agent-warn { background: #F2A93B; }
.agent-tip-text { flex: 1; font-size: 24rpx; color: #5A5F78; line-height: 1.6;
  word-break: break-word; }

/* 快捷入口 */
.quick { display: flex; gap: 14rpx; margin: 20rpx 24rpx 0; }
.quick-item { flex: 1; background: #FFFDF8; border-radius: 28rpx; padding: 24rpx 0;
  display: flex; flex-direction: column; align-items: center; gap: 10rpx;
  font-size: 26rpx; color: #5A5F78; box-shadow: 0 10rpx 26rpx rgba(124, 139, 255, .10); }
.quick-item:active { opacity: .8; }
.quick-icon { width: 78rpx; height: 78rpx; border-radius: 26rpx;
  display: flex; align-items: center; justify-content: center; }
.quick-img { width: 60rpx; height: 60rpx; }
.q-blue { background: #EEF1FF; } .q-green { background: #E9F8F2; }
.q-orange { background: #FFF6E7; } .q-purple { background: #F4F0FF; }

/* 账单行 */
.bill-row { display: flex; align-items: center; padding: 20rpx 0; border-bottom: 1rpx dashed #EFEDF7; }
.bill-row:last-child { border-bottom: none; }
.cat-icon { width: 76rpx; height: 76rpx; border-radius: 24rpx;
  display: flex; align-items: center; justify-content: center; margin-right: 22rpx; }
.cat-img { width: 62rpx; height: 62rpx; }
.bill-left { flex: 1; display: flex; flex-direction: column; gap: 6rpx; }
.bill-cat { font-size: 30rpx; font-weight: 600; }
.bill-remark { font-size: 25rpx; color: #A6AAC2; max-width: 380rpx; overflow: hidden;
  text-overflow: ellipsis; white-space: nowrap; }
.bill-amount { font-size: 34rpx; font-weight: 800; }
.amount-in { color: #1FA97F; } .amount-out { color: #E45858; }

/* 待办 */
.overdue-tip { margin: 4rpx 0 14rpx; background: #FFEDEE; color: #D96363; border-radius: 18rpx;
  padding: 16rpx 22rpx; font-size: 26rpx; }
.overdue-num { font-weight: 800; }
.todo-row { display: flex; align-items: center; gap: 16rpx; padding: 20rpx 4rpx; border-bottom: 1rpx dashed #EFEDF7; }
.todo-row:last-child { border-bottom: none; }
.todo-dot { width: 16rpx; height: 16rpx; border-radius: 8rpx; background: #F2B45C; flex-shrink: 0; }
.todo-title { flex: 1; font-size: 28rpx; }
.todo-due { font-size: 25rpx; color: #A6AAC2; }

/* 手绘标题装饰 */
.title-line { display: flex; align-items: center; gap: 10rpx; }
.title-doodle { width: 30rpx; height: 32rpx; opacity: .9; }
</style>
