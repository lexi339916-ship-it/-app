<script setup>
import { computed, ref } from 'vue'
import { onShow } from '@dcloudio/uni-app'
import {
  apiUnifiedNotifications, apiUnifiedNotificationAction,
  apiMarkAllNotificationsRead,
} from '../../api/index.js'
import { notificationState, refreshNotifications } from '../../store/notifications.js'

const items = ref([])
const loading = ref(true)
const error = ref(null)
const activeGroup = ref('all')
const acting = ref('')
let clearedOnce = false

const GROUPS = [
  { key: 'all', label: '全部' },
  { key: 'unread', label: '未读' },
  { key: 'budget_over', label: '预算超支' },
  { key: 'budget_near', label: '预算不足' },
  { key: 'subscription', label: '订阅风险' },
  { key: 'goal', label: '目标风险' },
  { key: 'purchase', label: '采购提醒' },
  { key: 'other', label: '异常/其他' },
]

const filteredCount = computed(() => items.value.length)

function levelText(level) {
  return { critical: '重要', warn: '关注', info: '提示' }[level] || level
}

function statusText(status) {
  return { unread: '未读', read: '已读', dismissed: '已忽略', accepted: '已采纳' }[status] || status
}

function dateText(value) {
  return String(value || '').replace('T', ' ').slice(5, 16)
}

function setGroup(key) {
  activeGroup.value = key
  load()
}

async function load() {
  loading.value = true
  error.value = null
  try {
    const params = { limit: 50 }
    if (activeGroup.value === 'unread') params.status = 'unread'
    else if (activeGroup.value !== 'all') params.group = activeGroup.value
    items.value = await apiUnifiedNotifications(params)
    await refreshNotifications()
  } catch (e) {
    error.value = e
  } finally {
    loading.value = false
  }
}

async function act(item, action) {
  if (acting.value) return
  acting.value = `${item.source}-${item.id}`
  try {
    await apiUnifiedNotificationAction(item.source, item.id, action)
    uni.showToast({
      title: action === 'dismissed' ? '已忽略' : (action === 'accepted' ? '已采纳' : '已读'),
      icon: 'none',
    })
    await load()
  } catch (e) {
    error.value = e
  } finally {
    acting.value = ''
  }
}

function canAccept(item) {
  return item.source === 'budget' && item.alert_type === 'rebalance' && item.status !== 'accepted'
}

function openTarget(item) {
  if (!item.target_route) return
  const tabs = ['/pages/index/index', '/pages/bills/list', '/pages/agent/agent',
    '/pages/notes/list', '/pages/profile/profile']
  if (tabs.includes(item.target_route)) uni.switchTab({ url: item.target_route })
  else uni.navigateTo({ url: item.target_route })
}

function agentPrompt(item) {
  const category = item.category ? `「${item.category}」` : ''
  if (['budget_100', 'budget_80', 'budget'].includes(item.alert_type)) {
    return `帮我看看${category}预算，给我一个调整方案`
  }
  if (item.alert_type === 'subscription') {
    return '帮我检查订阅，看看有没有涨价或低频的'
  }
  if (item.alert_type === 'goal') {
    return '帮我重新规划储蓄目标'
  }
  if (item.alert_type === 'planned_purchase') {
    return '帮我评估待办里的计划采购'
  }
  if (item.alert_type === 'anomaly') {
    return '帮我分析这笔异常大额支出'
  }
  if (item.alert_type === 'spending_change') {
    return '帮我分析本月消费变化'
  }
  return `帮我处理这条提醒：${item.title}`
}

function sendToAgent(item) {
  uni.setStorageSync('agent_pending_prompt', agentPrompt(item))
  uni.switchTab({ url: '/pages/agent/agent' })
}

onShow(async () => {
  if (!clearedOnce) {
    clearedOnce = true
    try { await apiMarkAllNotificationsRead() } catch (e) { /* 已读失败不阻塞列表 */ }
  }
  load()
})
</script>

<template>
  <view class="page">
    <view class="hero">
      <view>
        <text class="hero-title">提醒中心</text>
        <text class="hero-sub">
          {{ items.length }} 条提醒 · 未读 {{ notificationState.unique }} · 预算 {{ notificationState.budget }} · Agent {{ notificationState.agent }}
        </text>
      </view>
      <text class="refresh" @click="load">刷新</text>
    </view>

    <scroll-view class="group-scroll" scroll-x>
      <view class="group-row">
        <text v-for="g in GROUPS" :key="g.key"
          :class="['group-chip', activeGroup === g.key && 'group-on']"
          @click="setGroup(g.key)">{{ g.label }}</text>
      </view>
    </scroll-view>

    <view v-if="loading" class="card">
      <view class="skeleton" />
      <view class="skeleton" />
      <text class="muted">正在加载提醒…</text>
    </view>

    <view v-else-if="error" class="card state-error">
      <text class="state-title">提醒加载失败</text>
      <text class="state-text">{{ error.message || '请稍后重试' }}</text>
      <button class="btn primary small" @click="load">重新加载</button>
    </view>

    <view v-else-if="!items.length" class="card empty">
      <text class="empty-title">暂时没有提醒</text>
      <text class="empty-text">预算、订阅、目标或消费变化出现风险时，会在这里提醒你。</text>
    </view>

    <template v-else>
      <view class="card msg-card" v-for="item in items" :key="item.source + '-' + item.id">
        <view class="msg-head" @click="openTarget(item)">
          <view class="msg-head-left">
            <text :class="['level', 'level-' + item.level]">{{ levelText(item.level) }}</text>
            <text class="msg-title">{{ item.title }}</text>
          </view>
          <text :class="['status', 'status-' + item.status]">{{ statusText(item.status) }}</text>
        </view>
        <text class="msg-body" @click="openTarget(item)">{{ item.message }}</text>
        <view class="msg-meta">
          <text v-if="item.category">{{ item.category }}</text>
          <text v-if="item.amount !== null">影响 ¥{{ Number(item.amount).toFixed(2) }}</text>
          <text>{{ dateText(item.created_at) }}</text>
          <text v-if="item.related_count > 1">关联 {{ item.related_count }} 条</text>
        </view>
        <text v-if="item.suggestion" class="msg-suggestion">{{ item.suggestion }}</text>
        <view class="msg-actions">
          <text v-if="item.status === 'unread'" class="act" @click="act(item, 'read')">标为已读</text>
          <text v-if="canAccept(item)" class="act accept" @click="act(item, 'accepted')">采纳调配</text>
          <text v-if="item.status !== 'dismissed'" class="act" @click="act(item, 'dismissed')">忽略</text>
          <text v-if="item.target_route" class="act go" @click="openTarget(item)">查看详情 ›</text>
          <text class="act agent" @click="sendToAgent(item)">交给 Agent</text>
        </view>
      </view>
      <text class="footer-note">共 {{ filteredCount }} 条 · 同一条风险会自动合并展示</text>
    </template>
  </view>
</template>

<style scoped>
.page { padding: 18rpx 24rpx 80rpx; }
.hero { display: flex; align-items: flex-start; justify-content: space-between; gap: 16rpx;
  padding: 16rpx 8rpx 16rpx; }
.hero-title { display: block; font-size: 40rpx; font-weight: 800; color: #5A54B8; }
.hero-sub { display: block; font-size: 23rpx; color: #8A90A8; margin-top: 6rpx; }
.refresh { font-size: 23rpx; color: #6C7BF5; flex-shrink: 0; padding-top: 10rpx; }
.group-scroll { white-space: nowrap; margin-bottom: 18rpx; }
.group-row { display: inline-flex; gap: 10rpx; padding: 2rpx 2rpx 6rpx; }
.group-chip { display: inline-block; font-size: 22rpx; color: #8A90A8; background: #F6F4FB;
  border-radius: 999rpx; padding: 10rpx 20rpx; }
.group-on { color: #FFF; background: #6C7BF5; font-weight: 700; }
.card { background: #FFFDF8; border-radius: 28rpx; padding: 24rpx; margin-bottom: 20rpx;
  box-shadow: 0 10rpx 26rpx rgba(124, 139, 255, .08); border: 1rpx solid #F0EDF8; }
.skeleton { height: 24rpx; background: #F2F0FA; border-radius: 12rpx; margin: 14rpx 0; }
.muted { font-size: 22rpx; color: #A6AAC2; }
.state-error { border-color: #FFD7D7; background: #FFF8F8; }
.state-title { display: block; font-size: 29rpx; font-weight: 800; color: #C94F4F; }
.state-text { display: block; font-size: 24rpx; color: #8A90A8; margin: 8rpx 0 16rpx; line-height: 1.6; }
.btn { margin: 0; border-radius: 20rpx; font-size: 26rpx; font-weight: 700; }
.btn.primary { color: #FFF; background: linear-gradient(135deg, #7C8BFF, #A78BFA); }
.btn.small { height: 64rpx; line-height: 64rpx; padding: 0 24rpx; }
.empty { text-align: center; padding: 44rpx 24rpx; }
.empty-title { display: block; font-size: 30rpx; font-weight: 800; color: #3A3F58; }
.empty-text { display: block; font-size: 24rpx; color: #8A90A8; margin-top: 10rpx; line-height: 1.6; }
.msg-card { padding: 22rpx; }
.msg-head { display: flex; align-items: flex-start; justify-content: space-between; gap: 12rpx; }
.msg-head-left { flex: 1; min-width: 0; display: flex; align-items: center; gap: 10rpx; }
.level { flex-shrink: 0; font-size: 19rpx; font-weight: 700; border-radius: 999rpx;
  padding: 4rpx 12rpx; background: #EFF1FF; color: #6C7BF5; }
.level-critical { background: #FFEDEE; color: #E45858; }
.level-warn { background: #FFF6E7; color: #D98A32; }
.msg-title { font-size: 27rpx; font-weight: 800; color: #3A3F58; word-break: break-word; }
.status { flex-shrink: 0; font-size: 19rpx; color: #A6AAC2; }
.status-unread { color: #E45858; font-weight: 700; }
.status-accepted { color: #1FA97F; }
.msg-body { display: block; font-size: 24rpx; color: #5A5F78; line-height: 1.7;
  margin-top: 10rpx; word-break: break-word; }
.msg-meta { display: flex; flex-wrap: wrap; gap: 14rpx; font-size: 20rpx;
  color: #A6AAC2; margin-top: 10rpx; }
.msg-suggestion { display: block; font-size: 22rpx; color: #A56A1F; background: #FFFAF0;
  border-radius: 12rpx; padding: 10rpx 12rpx; margin-top: 10rpx; line-height: 1.6; }
.msg-actions { display: flex; flex-wrap: wrap; align-items: center; gap: 16rpx; margin-top: 12rpx; }
.act { font-size: 22rpx; color: #6C7BF5; }
.act.accept { color: #1FA97F; font-weight: 700; }
.act.go { margin-left: auto; }
.act.agent { color: #5A54B8; font-weight: 700; }
.footer-note { display: block; text-align: center; font-size: 20rpx; color: #A6AAC2; margin-top: 8rpx; }
</style>
