<script setup>
import { ref, computed } from 'vue'
import { onShow } from '@dcloudio/uni-app'
import { apiProfileStats, apiMe } from '../../api/index.js'
import store, { setUser } from '../../store/user.js'

const stats = ref({ total_bills: 0, total_days: 0, total_notes: 0, pending_todos: 0 })
const avatar = computed(() => store.user?.avatar || '')
const displayName = computed(() =>
  store.user?.nickname || store.user?.username || '用户')
const initial = computed(() => displayName.value.slice(0, 1))

async function loadAll() {
  try {
    const [s, me] = await Promise.all([apiProfileStats(), apiMe()])
    stats.value = s
    setUser(me)
  } catch (e) { /* 统一提示 */ }
}

function goSettings() { uni.navigateTo({ url: '/pages/settings/settings' }) }
function goBudget() { uni.navigateTo({ url: '/pages/budget/center' }) }
function goGoals() { uni.navigateTo({ url: '/pages/goals/goals' }) }
function goSubscriptions() { uni.navigateTo({ url: '/pages/subscriptions/list' }) }
function goAssets() { uni.navigateTo({ url: '/pages/assets/assets' }) }

onShow(loadAll)
</script>

<template>
  <view class="page">
    <view class="title-row">
      <text class="page-title">我的</text>
      <view class="title-actions">
        <image class="profile-sun" src="/static/doodles/sun.png" mode="widthFix" />
        <view class="settings-btn" @click="goSettings">
          <text class="gear">⚙</text>
          <text>设置</text>
        </view>
      </view>
    </view>

    <!-- 用户概览：点击进入设置 -->
    <view class="user-card" @click="goSettings">
      <view class="avatar-wrap">
        <image v-if="avatar" class="avatar-img" :src="avatar" mode="aspectFill" />
        <view v-else class="avatar">{{ initial }}</view>
      </view>
      <view class="user-info">
        <view class="name-row">
          <text class="name">{{ displayName }}</text>
          <text class="edit-hint">资料与设置 ›</text>
        </view>
        <text class="username">@{{ store.user?.username }}</text>
        <view class="status-chip">
          <view class="status-dot" />
          <text>已记账 {{ stats.total_days }} 天 · 陪你记好每一笔</text>
        </view>
      </view>
    </view>

    <!-- 统计三卡 -->
    <view class="stats-row">
      <view class="stat-card">
        <text class="stat-num">{{ stats.total_bills }}</text>
        <text class="stat-label">记账条目</text>
      </view>
      <view class="stat-card">
        <text class="stat-num">{{ stats.total_days }}</text>
        <text class="stat-label">记账天数</text>
      </view>
      <view class="stat-card">
        <text class="stat-num">{{ stats.pending_todos }}</text>
        <text class="stat-label">待办事项</text>
      </view>
    </view>

    <!-- 常用功能 -->
    <text class="group-title">常用功能</text>
    <view class="group-card">
      <view class="menu-item" @click="goAssets">
        <view class="menu-icon" style="background: #EFF1FF"><image class="menu-img" src="/static/icons/act_wallet.png" mode="widthFix" /></view>
        <view class="menu-main">
          <text class="menu-title">个人资产管理</text>
          <text class="menu-sub">资产总览 · 账户管理 · 负债管理</text>
        </view>
        <text class="menu-arrow">›</text>
      </view>
      <view class="menu-item" @click="goBudget">
        <view class="menu-icon" style="background: #FFEFF2"><image class="menu-img" src="/static/icons/act_wallet.png" mode="widthFix" /></view>
        <view class="menu-main">
          <text class="menu-title">预算中心</text>
          <text class="menu-sub">分类预算 · AI 方案 · 弹性调度</text>
        </view>
        <text class="menu-arrow">›</text>
      </view>
      <view class="menu-item" @click="goGoals">
        <view class="menu-icon" style="background: #FFEDEE"><image class="menu-img" src="/static/icons/act_target.png" mode="widthFix" /></view>
        <view class="menu-main">
          <text class="menu-title">储蓄目标与挑战</text>
          <text class="menu-sub">攒钱目标 · 生活挑战 · 进度追踪</text>
        </view>
        <text class="menu-arrow">›</text>
      </view>
      <view class="menu-item" @click="goSubscriptions">
        <view class="menu-icon" style="background: #E9F8F2"><image class="menu-img" src="/static/icons/act_note.png" mode="widthFix" /></view>
        <view class="menu-main">
          <text class="menu-title">订阅管理</text>
          <text class="menu-sub">固定支出 · 涨价/低频体检</text>
        </view>
        <text class="menu-arrow">›</text>
      </view>
    </view>

    <!-- 设置入口 -->
    <text class="group-title">更多</text>
    <view class="group-card">
      <view class="menu-item" @click="goSettings">
        <view class="menu-icon" style="background: #F6F4FB"><image class="menu-img" src="/static/icons/act_info.png" mode="widthFix" /></view>
        <view class="menu-main">
          <text class="menu-title">设置</text>
          <text class="menu-sub">头像 · 用户名 · 账号安全 · 关于系统</text>
        </view>
        <text class="menu-arrow">›</text>
      </view>
    </view>
  </view>
</template>

<style scoped>
.page { padding: 24rpx 24rpx 60rpx; }
.title-row { display: flex; justify-content: space-between; align-items: center; padding-right: 8rpx; }
.title-actions { display: flex; align-items: center; gap: 14rpx; }
.title-row .page-title { margin-bottom: 14rpx; }
.profile-sun { width: 82rpx; height: 82rpx; opacity: .9; transform: rotate(8deg); margin-top: -4rpx; }
.page-title { display: block; font-size: 48rpx; font-weight: 800; margin: 10rpx 8rpx 26rpx; }
.settings-btn {
  display: flex;
  align-items: center;
  gap: 6rpx;
  height: 62rpx;
  padding: 0 20rpx;
  border-radius: 999rpx;
  background: #FFFDF8;
  border: 1rpx solid #E9E5F4;
  color: #6C7BF5;
  font-size: 25rpx;
  font-weight: 700;
  box-shadow: 0 6rpx 18rpx rgba(124, 139, 255, .10);
}
.gear { font-size: 28rpx; line-height: 1; }

/* 用户卡 */
.user-card {
  display: flex;
  align-items: center;
  background: #FFFDF8;
  border-radius: 32rpx;
  padding: 34rpx 30rpx;
  box-shadow: 0 6rpx 24rpx rgba(124, 139, 255, .10);
}
.user-card:active { opacity: .9; }
.avatar-wrap { width: 118rpx; height: 118rpx; flex-shrink: 0; }
.avatar { width: 118rpx; height: 118rpx; border-radius: 36rpx;
  background: linear-gradient(135deg, #6C7BF5, #A8B2FF); color: #fff;
  display: flex; align-items: center; justify-content: center; font-size: 52rpx; font-weight: 800; }
.avatar-img { width: 118rpx; height: 118rpx; border-radius: 36rpx; display: block; }
.user-info { margin-left: 26rpx; flex: 1; min-width: 0; }
.name-row { display: flex; align-items: center; gap: 14rpx; flex-wrap: wrap; }
.name { font-size: 38rpx; font-weight: 700; }
.edit-hint { font-size: 22rpx; color: #6C7BF5; background: #EFF1FF; border-radius: 20rpx; padding: 4rpx 14rpx; }
.username { display: block; font-size: 26rpx; color: #A6AAC2; margin-top: 8rpx; }
.status-chip { display: inline-flex; align-items: center; gap: 10rpx; margin-top: 16rpx;
  background: #E9F8F2; color: #33B98E; border-radius: 28rpx; padding: 8rpx 20rpx; font-size: 25rpx; }
.status-dot { width: 12rpx; height: 12rpx; border-radius: 6rpx; background: #45C39A; }

/* 统计三卡 */
.stats-row { display: flex; gap: 18rpx; margin-top: 20rpx; }
.stat-card { flex: 1; background: #FFFDF8; border-radius: 26rpx; padding: 26rpx 0;
  text-align: center; box-shadow: 0 6rpx 24rpx rgba(124, 139, 255, .10); }
.stat-num { display: block; font-size: 42rpx; font-weight: 800; color: #6C7BF5; }
.stat-label { display: block; font-size: 25rpx; color: #A6AAC2; margin-top: 8rpx; }

/* 分组菜单 */
.group-title { display: block; font-size: 28rpx; color: #8A90A8; font-weight: 600;
  margin: 34rpx 8rpx 14rpx; }
.group-card { background: #FFFDF8; border-radius: 28rpx; overflow: hidden;
  box-shadow: 0 6rpx 24rpx rgba(124, 139, 255, .10); }
.menu-item { display: flex; align-items: center; padding: 28rpx 26rpx;
  border-bottom: 1rpx solid #F4F2FA; }
.menu-item:last-child { border-bottom: none; }
.menu-item:active { background: #FBFAFE; }
.menu-icon { width: 76rpx; height: 76rpx; border-radius: 26rpx; flex-shrink: 0;
  display: flex; align-items: center; justify-content: center; margin-right: 22rpx; }
.menu-img { width: 56rpx; height: 56rpx; }
.menu-main { flex: 1; min-width: 0; }
.menu-title { display: block; font-size: 31rpx; font-weight: 600; }
.menu-sub { display: block; font-size: 25rpx; color: #A6AAC2; margin-top: 8rpx; }
.menu-arrow { font-size: 36rpx; color: #D3D7E7; padding-left: 12rpx; }
</style>
