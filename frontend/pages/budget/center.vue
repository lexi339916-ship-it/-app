<script setup>
/**
 * 预算中心（AI 消费预警 & 预算模块主页）
 *
 * 功能：分类月度预算设置（手动/AI）、两层预警状态总览、
 * AI 推荐预算 / 存钱目标分配、弹性调度建议、待办计划采购联动、预警消息入口。
 */
import { ref, computed } from 'vue'
import { onShow } from '@dcloudio/uni-app'
import {
  apiBudgetOverview, apiSetCategoryBudget, apiBudgetRecommend, apiAllocateGoal,
  apiRebalance, apiPlannedPurchase, apiUnifiedNotificationAction,
} from '../../api/index.js'
import { categoryMeta } from '../../common/category-icons.js'
import BudgetPlanSheet from '../../components/budget-plan-sheet.vue'
import { notificationState, refreshNotifications } from '../../store/notifications.js'

// 当前月份 YYYY-MM（用本地时区，避免 UTC 跨月偏差）
const _d = new Date()
const month = ref(`${_d.getFullYear()}-${String(_d.getMonth() + 1).padStart(2, '0')}`)

const overview = ref({ total_budget: 0, total_spent: 0, items: [] })
const rebalanceList = ref([])   // 弹性调度建议（需求 5）
const purchases = ref([])       // 待办计划采购（需求 6）
const plan = ref(null)
const planVisible = ref(false)
const goalText = ref('')        // 存钱目标自然语言输入
const aiLoading = ref(false)    // AI 调用中的防重复态

// 分类预算编辑弹层
const editOpen = ref(false)
const editItem = ref(null)
const editAmount = ref('')

// 状态视觉映射：none 未设预算 / ok 正常 / near80 接近上限 / used_up 刚好用完 / over100 已超支
const STATUS_META = {
  none: { text: '点我设预算', cls: 'st-none' },
  ok: { text: '进行中', cls: 'st-ok' },
  near80: { text: '超八成啦', cls: 'st-warn' },
  used_up: { text: '预算已用完', cls: 'st-warn' },
  over100: { text: '已超支', cls: 'st-over' },
}

// 总预算整体使用率（用于顶部进度条）
const totalRatio = computed(() => {
  const b = Number(overview.value.total_budget)
  if (!b) return 0
  return Number(overview.value.total_spent) / b
})

/** 月份前后切换 */
function shiftMonth(delta) {
  const [y, m] = month.value.split('-').map(Number)
  const d = new Date(y, m - 1 + delta, 1)
  month.value = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`
  loadAll()
}

/** 主数据：预算总览（失败时沿用旧数据，request.js 已统一提示） */
async function loadOverview() {
  overview.value = await apiBudgetOverview(month.value)
}

/**
 * 次要数据：调度建议 / 计划采购 / 未读数。
 * AI 未配置时后端返回 503（request.js 不弹 toast），这里静默降级即可。
 */
async function loadExtras() {
  try { rebalanceList.value = await apiRebalance(month.value) } catch (e) { rebalanceList.value = [] }
  try { purchases.value = await apiPlannedPurchase(month.value) } catch (e) { purchases.value = [] }
  refreshNotifications()
}

async function loadAll() {
  try { await loadOverview() } catch (e) { /* 统一提示 */ }
  loadExtras()
}

// ---------------- 分类预算手动设置 ----------------

function openEdit(item) {
  editItem.value = item
  editAmount.value = item.status === 'none' ? '' : String(Number(item.amount))
  editOpen.value = true
}

async function saveCategoryBudget() {
  const amount = Number(editAmount.value)
  if (!amount || amount <= 0) {
    uni.showToast({ title: '请输入正确的预算金额', icon: 'none' }); return
  }
  try {
    await apiSetCategoryBudget({
      category_id: editItem.value.category_id,
      month: month.value,
      amount: amount.toFixed(2),
    })
    uni.showToast({ title: '预算已保存', icon: 'success' })
    editOpen.value = false
    loadAll()
  } catch (e) { /* 统一提示 */ }
}

// ---------------- AI 预算方案（推荐 / 存钱目标） ----------------

/** 方案预览改为页内弹层，不再跨页传 storage */
function goPlan(nextPlan) {
  plan.value = nextPlan
  planVisible.value = true
}

/** AI 读取历史账单推荐一套初始预算 */
async function aiRecommend() {
  if (aiLoading.value) return
  aiLoading.value = true
  uni.showLoading({ title: 'AI 规划中…', mask: true })
  try {
    goPlan(await apiBudgetRecommend(month.value))
  } catch (e) { /* 统一提示（历史不足等 400 文案） */ } finally {
    uni.hideLoading()
    aiLoading.value = false
  }
}

/** 自然语言存钱目标 → AI 分配各分类预算 */
async function aiAllocate() {
  const text = goalText.value.trim()
  if (text.length < 2) {
    uni.showToast({ title: '先写一句存钱目标吧', icon: 'none' }); return
  }
  if (aiLoading.value) return
  aiLoading.value = true
  uni.showLoading({ title: 'AI 分配中…', mask: true })
  try {
    goPlan(await apiAllocateGoal({ goal_text: text, month: month.value }))
  } catch (e) { /* 统一提示 */ } finally {
    uni.hideLoading()
    aiLoading.value = false
  }
}

// ---------------- 弹性调度建议 ----------------

/** 采纳：后端自动完成预算调配（结余额度 → 紧缺分类） */
async function acceptRebalance(s) {
  if (!s.alert_id) return
  try {
    await apiUnifiedNotificationAction('budget', s.alert_id, 'accepted')
    uni.showToast({ title: '已帮你调配好啦', icon: 'success' })
    loadAll()
  } catch (e) { /* 统一提示 */ }
}

/** 忽略：本条建议不再展示 */
async function dismissRebalance(s) {
  if (!s.alert_id) return
  try {
    await apiUnifiedNotificationAction('budget', s.alert_id, 'dismissed')
    rebalanceList.value = rebalanceList.value.filter(x => x.alert_id !== s.alert_id)
  } catch (e) { /* 统一提示 */ }
}

// ---------------- 其他 ----------------

function goAlerts() { uni.navigateTo({ url: '/pages/notifications/notifications?source=budget' }) }

/** 进度条宽度（超支封顶 100%） */
function barWidth(item) {
  return Math.min(Number(item.usage_ratio) || 0, 1) * 100 + '%'
}

onShow(loadAll)
</script>

<template>
  <view class="page">
    <!-- 页眉：标题 + 预警消息入口（未读红点） -->
    <view class="title-row">
      <text class="page-title">预算中心</text>
      <view class="msg-btn" @click="goAlerts">
        <text>预警消息</text>
        <text v-if="notificationState.budget > 0" class="msg-badge">{{ notificationState.budget > 99 ? '99+' : notificationState.budget }}</text>
      </view>
    </view>

    <!-- 月份切换 -->
    <view class="month-bar">
      <text class="month-arrow" @click="shiftMonth(-1)">‹</text>
      <text class="month-text">{{ month.replace('-', ' 年 ') }} 月</text>
      <text class="month-arrow" @click="shiftMonth(1)">›</text>
    </view>

    <!-- 总预算汇总卡 -->
    <view class="card summary-card">
      <view class="summary-row">
        <view class="summary-item">
          <text class="summary-num">¥{{ Number(overview.total_budget).toFixed(0) }}</text>
          <text class="summary-label">分类预算合计</text>
        </view>
        <view class="summary-item">
          <text class="summary-num">¥{{ Number(overview.total_spent).toFixed(2) }}</text>
          <text class="summary-label">已花</text>
        </view>
        <view class="summary-item">
          <text :class="['summary-num', Number(overview.total_budget) - Number(overview.total_spent) < 0 && 'num-red']">
            ¥{{ (Number(overview.total_budget) - Number(overview.total_spent)).toFixed(2) }}
          </text>
          <text class="summary-label">剩余</text>
        </view>
      </view>
      <view class="progress-track">
        <view :class="['progress-fill', totalRatio >= 1 ? 'fill-over' : (totalRatio >= 0.8 ? 'fill-warn' : 'fill-ok')]"
          :style="{ width: Math.min(totalRatio, 1) * 100 + '%' }" />
      </view>
      <text class="summary-hint" v-if="Number(overview.total_budget) > 0">
        整体已用 {{ Math.round(totalRatio * 100) }}%
      </text>
      <text class="summary-hint" v-else>还没设置分类预算，可以先让 AI 帮你定一套～</text>
    </view>

    <!-- AI 预算助手 -->
    <view class="card">
      <view class="section-title">
        <text>AI 预算助手</text>
        <text class="ai-badge">AI</text>
      </view>
      <text class="ai-desc">读你的历史账单，自动生成一套贴合消费习惯的预算。</text>
      <button class="btn btn-primary" :class="{ 'btn-disabled': aiLoading }" @click="aiRecommend">
        按历史账单推荐预算
      </button>
      <view class="divider-dash" />
      <text class="ai-desc">也可以说一句存钱目标，AI 帮你把预算分到各分类。</text>
      <view class="goal-row">
        <input class="input goal-input" v-model="goalText" maxlength="200"
          placeholder="如：想每月存 2000 块" placeholder-class="ph" />
        <button class="btn btn-ghost goal-btn" :class="{ 'btn-disabled': aiLoading }" @click="aiAllocate">
          按目标分配
        </button>
      </view>
    </view>

    <!-- 弹性调度建议（有结余 ↔ 快超支时出现） -->
    <view v-if="rebalanceList.length" class="card">
      <view class="section-title"><text>预算小调度</text></view>
      <view v-for="s in rebalanceList" :key="s.alert_id || s.to_category_id" class="rebalance-item">
        <text class="rebalance-msg">{{ s.message }}</text>
        <view class="rebalance-ops" v-if="s.alert_id">
          <text class="op-ignore" @click="dismissRebalance(s)">忽略</text>
          <text class="op-accept" @click="acceptRebalance(s)">采纳调配 ¥{{ Number(s.amount).toFixed(0) }}</text>
        </view>
      </view>
    </view>

    <!-- 待办计划采购联动 -->
    <view v-if="purchases.length" class="card">
      <view class="section-title"><text>计划采购早知道</text></view>
      <view v-for="p in purchases" :key="p.note_id" class="purchase-item">
        <view class="purchase-head">
          <text class="purchase-title">{{ p.title }}</text>
          <text v-if="p.estimated_amount" class="purchase-amount">约 ¥{{ Number(p.estimated_amount).toFixed(0) }}</text>
        </view>
        <text class="purchase-msg">{{ p.pressure_message }}</text>
      </view>
    </view>

    <!-- 分类预算列表 -->
    <view class="card">
      <view class="section-title"><text>分类预算</text><text class="section-more">点分类可改额度</text></view>
      <view v-for="item in overview.items" :key="item.category_id" class="cat-row" @click="openEdit(item)">
        <image class="cat-icon" :src="categoryMeta(item.category).img" mode="widthFix" />
        <view class="cat-main">
          <view class="cat-head">
            <text class="cat-name">{{ item.category }}</text>
            <text :class="['cat-status', STATUS_META[item.status].cls]">{{ STATUS_META[item.status].text }}</text>
          </view>
          <template v-if="item.status !== 'none'">
            <view class="progress-track small">
              <view :class="['progress-fill',
                item.status === 'over100' ? 'fill-over' : (['near80', 'used_up'].includes(item.status) ? 'fill-warn' : 'fill-ok')]"
                :style="{ width: barWidth(item) }" />
            </view>
            <text class="cat-nums">
              已花 ¥{{ Number(item.spent).toFixed(2) }} / 预算 ¥{{ Number(item.amount).toFixed(0) }}
              <text v-if="Number(item.remaining) < 0" class="num-red">（超 ¥{{ (-Number(item.remaining)).toFixed(2) }}）</text>
            </text>
          </template>
          <text v-else class="cat-nums">本月已花 ¥{{ Number(item.spent).toFixed(2) }} · 未设预算</text>
        </view>
      </view>
      <view v-if="!overview.items.length" class="empty">还没有支出分类，先去记一笔吧</view>
    </view>

    <!-- 预算编辑弹层 -->
    <view v-if="editOpen" class="popup-mask" @click="editOpen = false">
      <view class="edit-card" @click.stop>
        <text class="edit-title">「{{ editItem?.category }}」{{ month }} 预算</text>
        <input class="input edit-input" type="digit" v-model="editAmount"
          placeholder="输入月度预算金额" placeholder-class="ph" focus />
        <view class="edit-ops">
          <button class="btn btn-outline half" @click="editOpen = false">取消</button>
          <button class="btn btn-primary half" @click="saveCategoryBudget">保存</button>
        </view>
      </view>
    </view>

    <BudgetPlanSheet :visible="planVisible" :plan="plan"
      @close="planVisible = false" @applied="loadAll" />
  </view>
</template>

<style scoped>
.page { padding: 24rpx 0 60rpx; }

/* 页眉 */
.title-row { display: flex; justify-content: space-between; align-items: center; padding: 0 24rpx; }
.msg-btn {
  position: relative;
  background: #FFFDF8;
  border-radius: 999rpx;
  padding: 14rpx 28rpx;
  font-size: 26rpx;
  color: #6C7BF5;
  font-weight: 700;
  box-shadow: 0 6rpx 20rpx rgba(124, 139, 255, 0.12);
}
.msg-badge {
  position: absolute;
  top: -10rpx;
  right: -10rpx;
  min-width: 36rpx;
  height: 36rpx;
  line-height: 36rpx;
  text-align: center;
  border-radius: 999rpx;
  background: #F27E7E;
  color: #fff;
  font-size: 22rpx;
  padding: 0 8rpx;
  box-sizing: border-box;
}

/* 月份切换 */
.month-bar {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 48rpx;
  margin: 6rpx 0 4rpx;
}
.month-arrow { font-size: 44rpx; color: #6C7BF5; padding: 10rpx 24rpx; }
.month-text { font-size: 32rpx; font-weight: 800; color: #3A3F58; letter-spacing: 2rpx; }

/* 汇总卡 */
.summary-card { text-align: center; }
.summary-row { display: flex; }
.summary-item { flex: 1; }
.summary-num { display: block; font-size: 38rpx; font-weight: 800; color: #3A3F58; }
.summary-label { display: block; font-size: 24rpx; color: #A6AAC2; margin-top: 8rpx; }
.num-red { color: #F27E7E; }
.summary-hint { display: block; margin-top: 18rpx; font-size: 25rpx; color: #8A90A8; }

/* 进度条（汇总用大号，分类用小号） */
.progress-track {
  height: 18rpx;
  background: #F0EEF9;
  border-radius: 999rpx;
  margin-top: 26rpx;
  overflow: hidden;
}
.progress-track.small { height: 14rpx; margin-top: 14rpx; }
.progress-fill { height: 100%; border-radius: 999rpx; transition: width .3s; }
.fill-ok { background: linear-gradient(90deg, #7C8BFF, #A78BFA); }
.fill-warn { background: #F5A623; }
.fill-over { background: #F27E7E; }

/* AI 预算助手卡 */
.ai-desc { display: block; font-size: 26rpx; color: #8A90A8; line-height: 1.7; margin: 10rpx 0 18rpx; }
.goal-row { display: flex; gap: 18rpx; }
.goal-input { flex: 1; }
.goal-btn { width: 200rpx; height: 92rpx; font-size: 28rpx; }
.ph { color: #C3C7DA; }

/* 弹性调度 */
.rebalance-item {
  background: #FAF9FF;
  border: 1rpx solid #E9E6F4;
  border-radius: 22rpx;
  padding: 22rpx 24rpx;
  margin-top: 16rpx;
}
.rebalance-msg { display: block; font-size: 27rpx; color: #5A5F78; line-height: 1.7; }
.rebalance-ops { display: flex; justify-content: flex-end; gap: 28rpx; margin-top: 14rpx; }
.op-ignore { font-size: 26rpx; color: #A6AAC2; padding: 6rpx 10rpx; }
.op-accept { font-size: 26rpx; color: #6C7BF5; font-weight: 700; padding: 6rpx 10rpx; }

/* 计划采购 */
.purchase-item { padding: 18rpx 4rpx; border-bottom: 1rpx dashed #E7E3F4; }
.purchase-item:last-child { border-bottom: none; }
.purchase-head { display: flex; justify-content: space-between; align-items: center; }
.purchase-title { font-size: 28rpx; font-weight: 700; color: #3A3F58; }
.purchase-amount { font-size: 26rpx; color: #F5A623; font-weight: 700; }
.purchase-msg { display: block; font-size: 25rpx; color: #8A90A8; line-height: 1.7; margin-top: 8rpx; }

/* 分类预算列表 */
.cat-row { display: flex; align-items: center; padding: 22rpx 0; border-bottom: 1rpx solid #F4F2FA; }
.cat-row:last-child { border-bottom: none; }
.cat-row:active { opacity: 0.75; }
.cat-icon { width: 64rpx; height: 64rpx; flex-shrink: 0; margin-right: 20rpx; }
.cat-main { flex: 1; min-width: 0; }
.cat-head { display: flex; justify-content: space-between; align-items: center; }
.cat-name { font-size: 29rpx; font-weight: 700; color: #3A3F58; }
.cat-status { font-size: 23rpx; padding: 4rpx 16rpx; border-radius: 999rpx; }
.st-none { background: #F6F4FB; color: #A6AAC2; }
.st-ok { background: #EFF1FF; color: #6C7BF5; }
.st-warn { background: #FFF3E0; color: #F5A623; }
.st-over { background: #FFEDEE; color: #F27E7E; }
.cat-nums { display: block; font-size: 24rpx; color: #A6AAC2; margin-top: 10rpx; }

/* 编辑弹层 */
.popup-mask {
  position: fixed;
  inset: 0;
  background: rgba(58, 63, 88, 0.38);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 999;
  padding: 48rpx;
  box-sizing: border-box;
}
.edit-card {
  width: 100%;
  background: #FFFDF8;
  border-radius: 34rpx;
  padding: 40rpx 36rpx 36rpx;
  box-sizing: border-box;
}
.edit-title { display: block; font-size: 32rpx; font-weight: 800; color: #3A3F58; }
.edit-input { margin-top: 28rpx; }
.edit-ops { display: flex; gap: 18rpx; margin-top: 28rpx; }
.half { flex: 1; height: 84rpx; font-size: 30rpx; }
</style>
