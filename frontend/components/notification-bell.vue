<script setup>
import { onMounted } from 'vue'
import { notificationState, refreshNotifications, goNotifications } from '../store/notifications.js'

defineProps({ dark: { type: Boolean, default: false } })

onMounted(() => { refreshNotifications() })
</script>

<template>
  <view :class="['msg-btn', dark ? 'msg-dark' : '']" @click="goNotifications">
    <text class="msg-icon">✉</text>
    <text class="msg-text">消息</text>
    <text v-if="notificationState.unique > 0" class="msg-badge">
      {{ notificationState.unique > 99 ? '99+' : notificationState.unique }}
    </text>
  </view>
</template>

<style scoped>
.msg-btn { position: relative; display: flex; align-items: center; gap: 6rpx;
  padding: 8rpx 16rpx; background: #FFFDF8; border: 1rpx solid #E9E6F4;
  border-radius: 999rpx; box-shadow: 0 6rpx 16rpx rgba(124, 139, 255, .08); }
.msg-icon { font-size: 24rpx; color: #6C7BF5; }
.msg-text { font-size: 22rpx; color: #5A5F78; }
.msg-dark { background: rgba(255,255,255,.12); border-color: rgba(255,255,255,.2); }
.msg-dark .msg-icon, .msg-dark .msg-text { color: #FFF; }
.msg-badge { position: absolute; top: -8rpx; right: -8rpx; min-width: 28rpx; height: 28rpx;
  line-height: 28rpx; padding: 0 8rpx; border-radius: 999rpx; background: #E45858;
  color: #FFF; font-size: 18rpx; text-align: center; font-weight: 700; box-sizing: border-box; }
</style>
