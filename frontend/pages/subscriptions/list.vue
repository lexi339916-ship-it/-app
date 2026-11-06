<script setup>
/**
 * 订阅管理：周期固定支出列表
 *
 * 数据全部来自远程后端数据库，由用户手动录入；
 * 系统不联网查询 QQ 音乐 / 网易云等平台的真实续费状态，
 * 只在到达「每月扣费日」时由后端自动生成一笔支出账单。
 */
import { ref, computed } from 'vue'
import { onShow } from '@dcloudio/uni-app'
import {
  apiSubscriptions, apiToggleSubscription, apiDeleteSubscription,
} from '../../api/index.js'

const items = ref([])
const loading = ref(false)

const activeCount = computed(() => items.value.filter(s => s.status === 'active').length)
const pausedCount = computed(() => items.value.filter(s => s.status !== 'active').length)
const monthlyTotal = computed(() => items.value
  .filter(s => s.status === 'active')
  .reduce((sum, s) => sum + Number(s.amount), 0))

function daysLabel(s) {
  if (s.status !== 'active') return '暂停中，不自动记账'
  if (s.days_left === 0) return '今天扣费'
  return `${s.days_left} 天后扣费（${s.next_charge_date.slice(5)}）`
}

async function load() {
  if (loading.value) return
  loading.value = true
  try {
    items.value = await apiSubscriptions()
  } catch (e) { /* 统一提示 */ } finally { loading.value = false }
}

function goEdit(id) {
  uni.navigateTo({ url: '/pages/subscriptions/edit' + (id ? '?id=' + id : '') })
}

/** 暂停 / 恢复：暂停后不再自动生成月度账单，也不弹扣费提醒 */
function toggle(s) {
  const pausing = s.status === 'active'
  uni.showModal({
    title: pausing ? '暂停订阅' : '恢复订阅',
    content: pausing
      ? `暂停后「${s.name}」不再自动生成月度账单和扣费提醒，可随时恢复。`
      : `恢复后「${s.name}」将在每月 ${s.day_of_month} 日自动记账。`,
    confirmText: pausing ? '暂停' : '恢复',
    confirmColor: '#6C7BF5',
    success: async (res) => {
      if (!res.confirm) return
      try {
        const updated = await apiToggleSubscription(s.id)
        Object.assign(s, updated)
        uni.showToast({ title: pausing ? '已暂停' : '已恢复', icon: 'none' })
      } catch (e) { /* 统一提示 */ }
    },
  })
}

/** 删除订阅项：已自动生成的历史账单保留（属于真实支出记录） */
function remove(s) {
  uni.showModal({
    title: '删除订阅',
    content: `确定删除「${s.name}」吗？已自动生成的历史账单会保留。`,
    confirmText: '删除',
    confirmColor: '#E45858',
    success: async (res) => {
      if (!res.confirm) return
      try {
        await apiDeleteSubscription(s.id)
        items.value = items.value.filter(x => x.id !== s.id)
        uni.showToast({ title: '已删除', icon: 'success' })
      } catch (e) { /* 统一提示 */ }
    },
  })
}

onShow(load)
</script>

<template>
  <view class="page">
    <!-- 概览 + 新增入口 -->
    <view class="card summary">
      <view class="sum-main">
        <text class="sum-label">每月固定支出</text>
        <text class="sum-amount">¥{{ monthlyTotal.toFixed(2) }}</text>
        <text class="sum-sub">
          {{ activeCount }} 项进行中<text v-if="pausedCount"> · {{ pausedCount }} 项已暂停</text>
        </text>
      </view>
      <view class="add-btn" @click="goEdit()">＋ 新增订阅</view>
    </view>

    <!-- 订阅列表 -->
    <view v-if="items.length" class="list">
      <view v-for="s in items" :key="s.id" :class="['sub-card', s.status !== 'active' && 'sub-paused']">
        <view class="sub-head">
          <view class="sub-icon">
            <image class="sub-img" src="/static/icons/act_wallet.png" mode="widthFix" />
          </view>
          <view class="sub-mid">
            <view class="sub-title-row">
              <text class="sub-name">{{ s.name }}</text>
              <text :class="['sub-state', s.status === 'active' ? 'st-on' : 'st-off']">
                {{ s.status === 'active' ? '进行中' : '已暂停' }}
              </text>
            </view>
            <text class="sub-cycle">每月 {{ s.day_of_month }} 日 · {{ daysLabel(s) }}</text>
            <text v-if="s.remark" class="sub-remark">{{ s.remark }}</text>
          </view>
          <text class="sub-amount">-¥{{ Number(s.amount).toFixed(2) }}</text>
        </view>
        <view class="sub-ops">
          <text class="op" @click="goEdit(s.id)">编辑</text>
          <text class="op" @click="toggle(s)">{{ s.status === 'active' ? '暂停' : '恢复' }}</text>
          <text class="op op-danger" @click="remove(s)">删除</text>
        </view>
      </view>
    </view>

    <!-- 空状态 -->
    <view v-else-if="!loading" class="empty">
      <image class="empty-doodle" src="/static/doodles/cloud.png" mode="widthFix" />
      <text class="empty-line">还没有订阅</text>
      <text class="empty-tip">添加会员、房租等固定支出，到扣费日自动记一笔</text>
    </view>

    <text class="foot-hint">订阅由你手动录入，系统不联网获取平台真实续费状态</text>
  </view>
</template>

<style scoped>
.page { padding-bottom: 60rpx; }

/* 概览卡 */
.summary { display: flex; align-items: center; justify-content: space-between;
  background: linear-gradient(135deg, #FFFDF8 0%, #F7F5FF 100%); }
.sum-main { flex: 1; min-width: 0; }
.sum-label { display: block; font-size: 26rpx; color: #8A90A8; }
.sum-amount { display: block; font-size: 56rpx; font-weight: 800; color: #E45858;
  letter-spacing: 1rpx; margin: 6rpx 0 4rpx; }
.sum-sub { display: block; font-size: 25rpx; color: #A6AAC2; }
.add-btn { flex-shrink: 0; padding: 18rpx 28rpx; border-radius: 999rpx; font-size: 27rpx;
  font-weight: 700; color: #fff; background: linear-gradient(135deg, #7C8BFF, #A78BFA);
  box-shadow: 0 10rpx 24rpx rgba(124, 139, 255, .28); }
.add-btn:active { opacity: .88; }

/* 订阅卡片 */
.list { margin-top: 6rpx; }
.sub-card { background: #FFFDF8; margin: 14rpx 24rpx; border-radius: 26rpx;
  padding: 24rpx; box-shadow: 0 6rpx 24rpx rgba(124, 139, 255, .10); }
.sub-paused { opacity: .72; }
.sub-head { display: flex; align-items: flex-start; }
.sub-icon { width: 80rpx; height: 80rpx; border-radius: 26rpx; background: #EFF1FF;
  display: flex; align-items: center; justify-content: center; margin-right: 20rpx; flex-shrink: 0; }
.sub-img { width: 54rpx; height: 54rpx; }
.sub-mid { flex: 1; min-width: 0; }
.sub-title-row { display: flex; align-items: center; gap: 12rpx; }
.sub-name { font-size: 30rpx; font-weight: 700; max-width: 320rpx; overflow: hidden;
  text-overflow: ellipsis; white-space: nowrap; }
.sub-state { font-size: 22rpx; padding: 2rpx 12rpx; border-radius: 8rpx; font-weight: 600; }
.st-on { background: #E8F8F1; color: #1FA97F; }
.st-off { background: #F1F1F5; color: #A6AAC2; }
.sub-cycle { display: block; font-size: 24rpx; color: #8A90A8; margin-top: 8rpx; }
.sub-remark { display: block; font-size: 23rpx; color: #B4B8CC; margin-top: 4rpx;
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.sub-amount { flex-shrink: 0; margin-left: 14rpx; font-size: 32rpx; font-weight: 800;
  color: #E45858; }

.sub-ops { display: flex; justify-content: flex-end; gap: 16rpx; margin-top: 18rpx;
  padding-top: 16rpx; border-top: 1rpx dashed #EFECF7; }
.op { font-size: 25rpx; color: #6C7BF5; background: #EFF1FF; border-radius: 999rpx;
  padding: 8rpx 26rpx; }
.op-danger { color: #E45858; background: #FEF0F0; }
.op:active { opacity: .8; }

/* 空状态 */
.empty-doodle { width: 160rpx; display: block; margin: 0 auto 14rpx; opacity: .9; }
.empty-line { display: block; font-size: 29rpx; color: #8A90A8; }
.empty-tip { display: block; font-size: 24rpx; color: #B4B8CC; margin-top: 8rpx; }
.foot-hint { display: block; text-align: center; font-size: 23rpx; color: #B4B8CC;
  margin: 26rpx 40rpx 0; line-height: 1.6; }
</style>
