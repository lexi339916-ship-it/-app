<script setup>
import { computed, ref } from 'vue'

const props = defineProps({
  visible: { type: Boolean, default: false },
  sessions: { type: Array, default: () => [] },
  memories: { type: Array, default: () => [] },
  loading: { type: Boolean, default: false },
  currentSessionId: { type: String, default: '' },
})
const emit = defineEmits(['close', 'select', 'delete', 'new', 'delete-memory'])

const tab = ref('sessions')
const hasSessions = computed(() => props.sessions.length > 0)
const hasMemories = computed(() => props.memories.length > 0)

function formatTime(value) {
  if (!value) return ''
  const text = String(value).replace('T', ' ')
  return text.slice(5, 16)
}

function statusLabel(status) {
  return {
    completed: '已完成', awaiting_approval: '待确认', needs_input: '需补充',
    failed: '未完成', rejected: '已取消', undone: '已撤销',
  }[status] || status || ''
}

function memoryLabel(memory) {
  if (memory.kind === 'merchant_category') {
    return `商户「${memory.key}」→ ${memory.value?.category || '未知分类'}`
  }
  if (memory.kind === 'goal') {
    return `目标「${memory.value?.name || ''}」¥${memory.value?.target_amount || ''}`
  }
  if (memory.kind === 'preference') return `偏好：${memory.key}`
  return `${memory.kind}：${memory.key}`
}

function close() { emit('close') }
</script>

<template>
  <view v-if="visible" class="mask" @click.self="close">
    <view class="sheet">
      <view class="sheet-head">
        <view>
          <text class="sheet-title">对话历史</text>
          <text class="sheet-sub">继续之前的会话，或管理 Agent 记忆</text>
        </view>
        <text class="sheet-close" @click="close">×</text>
      </view>

      <view class="tabs">
        <text :class="['tab', tab === 'sessions' && 'tab-on']" @click="tab = 'sessions'">
          会话 {{ sessions.length }}
        </text>
        <text :class="['tab', tab === 'memories' && 'tab-on']" @click="tab = 'memories'">
          记忆 {{ memories.length }}
        </text>
      </view>

      <view v-if="tab === 'sessions'" class="tab-body">
        <view class="new-session-btn" @click="emit('new')">＋ 新建会话</view>
        <view v-if="loading" class="empty">正在读取历史…</view>
        <view v-else-if="!hasSessions" class="empty">
          <text>还没有历史会话</text>
          <text class="empty-sub">发送第一条消息后，这里会保存每一轮对话。</text>
        </view>
        <view v-else class="session-list">
          <view v-for="s in sessions" :key="s.session_id"
            :class="['session-item', s.session_id === currentSessionId && 'session-active']"
            @click="emit('select', s)">
            <view class="session-main">
              <view class="session-top">
                <text class="session-title">{{ s.title || s.last_goal || '未命名会话' }}</text>
                <text class="session-time">{{ formatTime(s.last_at) }}</text>
              </view>
              <text class="session-preview">{{ s.preview || s.last_goal || '暂无摘要' }}</text>
              <view class="session-meta">
                <text>{{ s.turn_count }} 轮</text>
                <text v-if="s.last_status">{{ statusLabel(s.last_status) }}</text>
                <text v-if="s.session_id === currentSessionId" class="current-tag">当前</text>
              </view>
            </view>
            <text class="session-del" @click.stop="emit('delete', s)">×</text>
          </view>
        </view>
      </view>

      <view v-else class="tab-body">
        <view v-if="!hasMemories" class="empty">
          <text>还没有 Agent 记忆</text>
          <text class="empty-sub">商户分类纠正、储蓄目标等信息会记录在这里。</text>
        </view>
        <view v-else class="memory-list">
          <view class="memory-row" v-for="m in memories" :key="m.id">
            <text class="memory-text">{{ memoryLabel(m) }}</text>
            <text class="memory-del" @click="emit('delete-memory', m)">×</text>
          </view>
        </view>
      </view>
    </view>
  </view>
</template>

<style scoped>
.mask { position: fixed; left: 0; right: 0; top: 0; bottom: 0; z-index: 1000;
  background: rgba(35, 34, 58, .45); display: flex; align-items: flex-end; }
.sheet { width: 100%; max-height: 82vh; background: #FFFDF8; border-radius: 34rpx 34rpx 0 0;
  padding: 26rpx 28rpx 30rpx; box-sizing: border-box; display: flex; flex-direction: column; }
.sheet-head { display: flex; align-items: flex-start; justify-content: space-between; gap: 12rpx; }
.sheet-title { display: block; font-size: 32rpx; font-weight: 800; color: #3A3F58; }
.sheet-sub { display: block; font-size: 21rpx; color: #A6AAC2; margin-top: 4rpx; }
.sheet-close { font-size: 42rpx; color: #A6AAC2; padding: 0 8rpx; line-height: 1; }
.tabs { display: flex; gap: 10rpx; margin: 20rpx 0 12rpx; }
.tab { flex: 1; text-align: center; font-size: 24rpx; color: #8A90A8; background: #F6F4FB;
  border-radius: 999rpx; padding: 12rpx 0; }
.tab-on { background: #6C7BF5; color: #fff; font-weight: 700; }
.tab-body { flex: 1; min-height: 0; overflow-y: auto; }
.new-session-btn { text-align: center; font-size: 25rpx; font-weight: 700; color: #6C7BF5;
  background: #EFF1FF; border-radius: 18rpx; padding: 16rpx 0; margin-bottom: 12rpx; }
.empty { text-align: center; color: #A6AAC2; font-size: 24rpx; padding: 50rpx 0; line-height: 1.7; }
.empty-sub { display: block; font-size: 21rpx; margin-top: 6rpx; }
.session-item { display: flex; align-items: flex-start; gap: 12rpx; padding: 18rpx 16rpx;
  border-radius: 18rpx; background: #FAF9FF; margin-bottom: 10rpx; border: 1rpx solid #F0EDF8; }
.session-item:active { background: #F4F0FF; }
.session-active { border-color: #B9C0FF; background: #F4F0FF; }
.session-main { flex: 1; min-width: 0; }
.session-top { display: flex; align-items: center; justify-content: space-between; gap: 10rpx; }
.session-title { flex: 1; min-width: 0; font-size: 25rpx; font-weight: 700; color: #3A3F58;
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.session-time { font-size: 18rpx; color: #B0B4C8; flex-shrink: 0; }
.session-preview { display: block; font-size: 21rpx; color: #8A90A8; line-height: 1.5;
  margin-top: 5rpx; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.session-meta { display: flex; align-items: center; gap: 12rpx; margin-top: 8rpx;
  font-size: 18rpx; color: #A6AAC2; }
.current-tag { color: #6C7BF5; background: #EFF1FF; border-radius: 999rpx; padding: 2rpx 10rpx; }
.session-del { font-size: 30rpx; color: #C3C7DA; padding: 0 4rpx; flex-shrink: 0; }
.memory-row { display: flex; align-items: center; gap: 12rpx; padding: 16rpx 4rpx;
  border-bottom: 1rpx dashed #F0EDF8; }
.memory-row:last-child { border-bottom: none; }
.memory-text { flex: 1; font-size: 23rpx; color: #4A4F6B; line-height: 1.6; word-break: break-word; }
.memory-del { font-size: 30rpx; color: #C3C7DA; padding: 0 8rpx; }
</style>
