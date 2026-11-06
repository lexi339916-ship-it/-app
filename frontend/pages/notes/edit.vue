<script setup>
import { ref } from 'vue'
import { onLoad } from '@dcloudio/uni-app'
import { apiNote, apiAddNote, apiUpdateNote, apiDeleteNote } from '../../api/index.js'

const editId = ref(null)
const title = ref('')
const content = ref('')
const noteType = ref('note')
const priority = ref('medium')
const pinned = ref(false)
const color = ref('lilac')
const dueDate = ref('')
const dueTime = ref('09:00')
const saving = ref(false)
const TASK_COLORS = [
  { key: 'lilac', color: '#EFDFE9' },
  { key: 'sky', color: '#D2EFF1' },
  { key: 'mint', color: '#DEF6D6' },
  { key: 'peach', color: '#BDE4DD' },
  { key: 'sand', color: '#FFE8C9' },
  { key: 'rose', color: '#FED2DF' },
]
const today = new Date(Date.now() - new Date().getTimezoneOffset() * 60000)
  .toISOString().slice(0, 10)

const PRIORITIES = [
  { key: 'high', label: '高' },
  { key: 'medium', label: '中' },
  { key: 'low', label: '低' },
]

async function loadNote(id) {
  const n = await apiNote(id)
  title.value = n.title
  content.value = n.content
  noteType.value = n.note_type
  priority.value = n.priority || 'medium'
  pinned.value = !!n.pinned
  color.value = n.color || 'lilac'
  if (n.due_at) {
    dueDate.value = String(n.due_at).slice(0, 10)
    dueTime.value = String(n.due_at).slice(11, 16) || '09:00'
  }
}

function switchType(t) { noteType.value = t }

async function save() {
  if (!title.value.trim()) {
    uni.showToast({ title: '请输入标题', icon: 'none' }); return
  }
  const dueAt = noteType.value === 'todo' && dueDate.value
    ? `${dueDate.value} ${dueTime.value}:00`
    : null
  const payload = {
    title: title.value.trim(),
    content: content.value,
    note_type: noteType.value,
    status: 'open',
    due_at: dueAt,
    priority: priority.value,
    pinned: pinned.value,
    color: color.value,
  }
  saving.value = true
  try {
    if (editId.value) {
      const old = await apiNote(editId.value)
      payload.status = old.status
      await apiUpdateNote(editId.value, payload)
      uni.showToast({ title: '修改成功', icon: 'success' })
    } else {
      await apiAddNote(payload)
      uni.showToast({ title: '保存成功', icon: 'success' })
    }
    setTimeout(() => uni.navigateBack(), 700)
  } catch (e) { /* 统一提示 */ } finally { saving.value = false }
}

function removeIt() {
  uni.showModal({
    title: '确认删除',
    content: '删除后无法恢复，确定删除吗？',
    success: async (res) => {
      if (res.confirm) {
        await apiDeleteNote(editId.value)
        uni.showToast({ title: '已删除', icon: 'success' })
        setTimeout(() => uni.navigateBack(), 700)
      }
    },
  })
}

onLoad(async (options) => {
  if (options && options.id) {
    editId.value = Number(options.id)
    uni.setNavigationBarTitle({ title: '编辑' })
    await loadNote(editId.value)
  } else if (options && (options.type === 'todo' || options.type === 'note')) {
    noteType.value = options.type
    if (options.date && /^\d{4}-\d{2}-\d{2}$/.test(options.date)) {
      dueDate.value = options.date
    }
    uni.setNavigationBarTitle({ title: options.type === 'todo' ? '新建待办' : '新建便签' })
  }
})
</script>

<template>
  <view class="page">
    <view class="card">
      <view class="type-switch">
        <text :class="['type-btn', noteType === 'note' && 'type-note']" @click="switchType('note')">普通便签</text>
        <text :class="['type-btn', noteType === 'todo' && 'type-todo']" @click="switchType('todo')">待办任务</text>
      </view>

      <text class="field-label">标题</text>
      <input class="input" v-model="title" placeholder="例如：交季度报告" placeholder-class="ph" />

      <text class="field-label">内容</text>
      <textarea class="ta" v-model="content" placeholder="选填" placeholder-class="ph" />

      <block v-if="noteType === 'todo'">
        <text class="field-label">截止时间</text>
        <view class="due-row">
          <picker mode="date" :value="dueDate || today" @change="dueDate = $event.detail.value">
            <view class="picker-value">{{ dueDate || '选择日期' }} ▾</view>
          </picker>
          <picker mode="time" :value="dueTime" @change="dueTime = $event.detail.value">
            <view class="picker-value">{{ dueTime }} ▾</view>
          </picker>
        </view>

        <text class="field-label">优先级</text>
        <view class="pri-row">
          <text v-for="p in PRIORITIES" :key="p.key"
            :class="['pri-item', `pri-${p.key}`, priority === p.key && 'pri-active']"
            @click="priority = p.key">
            {{ p.label }}{{ priority === p.key ? ' ✓' : '' }}
          </text>
        </view>

        <text class="field-label">任务颜色</text>
        <view class="color-row">
          <view v-for="c in TASK_COLORS" :key="c.key"
            :class="['color-item', color === c.key && 'color-active']"
            :style="{ background: c.color }"
            @click="color = c.key">
            <text v-if="color === c.key" class="color-check">✓</text>
          </view>
        </view>
      </block>

      <view class="pin-row">
        <view class="pin-main">
          <text class="pin-title">置顶显示</text>
          <text class="pin-sub">置顶的任务会排在最前面</text>
        </view>
        <switch :checked="pinned" color="#6C7BF5" @change="e => pinned = e.detail.value" />
      </view>
    </view>

    <view class="actions">
      <button class="btn btn-primary" :class="{ 'btn-disabled': saving }" :disabled="saving" @click="save">
        {{ saving ? '保存中…' : (editId ? '保存修改' : '保存') }}
      </button>
      <button class="btn btn-danger" v-if="editId" @click="removeIt">删除</button>
    </view>
  </view>
</template>

<style scoped>
.page { padding-bottom: 60rpx; }
.type-switch { display: flex; background: #F6F4FB; border-radius: 20rpx; padding: 8rpx; }
.type-btn { flex: 1; text-align: center; padding: 16rpx 0; border-radius: 12rpx;
  font-size: 30rpx; color: #8A90A8; }
.type-note { background: #6C7BF5; color: #fff; font-weight: 700; }
.type-todo { background: #F2B45C; color: #fff; font-weight: 700; }

.field-label { display: block; font-size: 28rpx; color: #5A5F78; margin: 30rpx 0 16rpx; }
.ph { color: #C3C7DA; }
.ta { width: 100%; min-height: 180rpx; background: #F6F4FB; border-radius: 20rpx;
  padding: 24rpx; font-size: 30rpx; box-sizing: border-box; }
.due-row { display: flex; gap: 20rpx; }
.picker-value { height: 88rpx; background: #F6F4FB; border-radius: 20rpx;
  display: flex; align-items: center; justify-content: center; padding: 0 30rpx; font-size: 30rpx; }

.pri-row { display: flex; gap: 18rpx; }
.pri-item { flex: 1; text-align: center; padding: 18rpx 0; border-radius: 20rpx;
  font-size: 30rpx; background: #F6F4FB; color: #8A90A8; font-weight: 600; }
.pri-high.pri-active { background: #FFEDEE; color: #F27E7E; }
.pri-medium.pri-active { background: #FFF6E7; color: #F2B45C; }
.pri-low.pri-active { background: #F4F2FA; color: #6B7089; }

/* 任务颜色 */
.color-row { display: flex; gap: 22rpx; padding: 4rpx 0; }
.color-item { width: 60rpx; height: 60rpx; border-radius: 30rpx; display: flex;
  align-items: center; justify-content: center; box-shadow: 0 4rpx 10rpx rgba(124, 139, 255, .16); }
.color-active { border: 4rpx solid #4E5170; }
.color-check { color: #fff; font-size: 28rpx; font-weight: 800; }

.pin-row { display: flex; justify-content: space-between; align-items: center; margin-top: 34rpx; }
.pin-title { display: block; font-size: 30rpx; font-weight: 600; }
.pin-sub { display: block; font-size: 25rpx; color: #A6AAC2; margin-top: 6rpx; }

.actions { margin: 30rpx 24rpx; display: flex; flex-direction: column; gap: 20rpx; }
</style>
