<script setup>
import { ref } from 'vue'
import { onLoad } from '@dcloudio/uni-app'
import {
  apiNote, apiAddNote, apiUpdateNote, apiDeleteNote, apiUploadNotePhoto,
} from '../../api/index.js'

const editId = ref(null)
const title = ref('')
const content = ref('')
const noteImages = ref([])
const MAX_PHOTOS = 6
const photoUploading = ref(false)
const location = ref('')
const recordType = ref('idea')       // todo / idea / mood
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

const TYPE_META = {
  todo: {
    label: '待办',
    icon: '✓',
    nav: '新建待办',
    titleLabel: '任务标题',
    titlePh: '例如：交季度报告',
    contentPh: '补充说明，选填',
  },
  idea: {
    label: '想法',
    icon: '✦',
    nav: '新建想法',
    titleLabel: '想法标题',
    titlePh: '例如：周五下午的灵光一现',
    contentPh: '展开写写这个想法…',
  },
  mood: {
    label: '心情',
    icon: '♥',
    nav: '记录心情',
    titleLabel: '此刻心情',
    titlePh: '例如：下班路上的晚霞',
    contentPh: '发生了什么？此刻感觉如何？',
  },
}

async function loadNote(id) {
  const n = await apiNote(id)
  title.value = n.title
  content.value = n.content
  const photos = (Array.isArray(n.images) && n.images.length)
    ? n.images
    : (n.image ? [n.image] : [])
  noteImages.value = photos.slice(0, MAX_PHOTOS)
  location.value = n.location || ''
  if (n.note_type === 'todo') recordType.value = 'todo'
  else recordType.value = n.entry_type === 'mood' ? 'mood' : 'idea'
  priority.value = n.priority || 'medium'
  pinned.value = !!n.pinned
  color.value = n.color || 'lilac'
  if (n.due_at) {
    dueDate.value = String(n.due_at).slice(0, 10)
    dueTime.value = String(n.due_at).slice(11, 16) || '09:00'
  }
}

function switchType(t) {
  recordType.value = t
  if (t === 'mood') color.value = 'rose'
  else if (t === 'idea') color.value = 'lilac'
  if (t === 'todo' && !dueDate.value) dueDate.value = today
}

function choosePhoto() {
  if (photoUploading.value) return
  const remaining = MAX_PHOTOS - noteImages.value.length
  if (remaining <= 0) {
    uni.showToast({ title: '最多上传 6 张照片', icon: 'none' })
    return
  }
  uni.chooseImage({
    count: remaining,
    sizeType: ['compressed'],
    sourceType: ['album', 'camera'],
    success: async (res) => {
      const paths = (res.tempFilePaths || []).slice(0, remaining)
      if (!paths.length) return
      photoUploading.value = true
      try {
        for (const path of paths) {
          const out = await apiUploadNotePhoto(path)
          if (out && out.image) noteImages.value.push(out.image)
        }
      } catch (e) { /* 统一提示 */ } finally {
        photoUploading.value = false
      }
    },
  })
}

function previewPhoto(index = 0) {
  if (!noteImages.value.length) return
  uni.previewImage({ urls: noteImages.value, current: noteImages.value[index] })
}

function removePhoto(index) {
  noteImages.value.splice(index, 1)
}

async function save() {
  if (!title.value.trim()) {
    uni.showToast({ title: '请输入标题', icon: 'none' }); return
  }
  if (photoUploading.value) {
    uni.showToast({ title: '照片还在上传，请稍候', icon: 'none' }); return
  }
  const isTodo = recordType.value === 'todo'
  const dueAt = isTodo && dueDate.value ? `${dueDate.value} ${dueTime.value}:00` : null
  const payload = {
    title: title.value.trim(),
    content: content.value,
    images: isTodo ? [] : noteImages.value,
    location: isTodo ? location.value.trim() : '',
    note_type: isTodo ? 'todo' : 'note',
    entry_type: isTodo ? 'note' : recordType.value,
    status: 'open',
    due_at: dueAt,
    priority: isTodo ? priority.value : 'medium',
    pinned: isTodo ? pinned.value : false,
    color: isTodo ? color.value : (recordType.value === 'mood' ? 'rose' : 'lilac'),
  }
  saving.value = true
  try {
    if (editId.value) {
      const old = await apiNote(editId.value)
      payload.status = old.note_type === 'todo' ? old.status : 'open'
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
    uni.setNavigationBarTitle({ title: '编辑记录' })
    await loadNote(editId.value)
  } else if (options && ['todo', 'note', 'idea', 'mood'].includes(options.type)) {
    recordType.value = options.type === 'note' ? 'idea' : options.type
    if (recordType.value === 'todo') {
      dueDate.value = options.date && /^\d{4}-\d{2}-\d{2}$/.test(options.date) ? options.date : today
    }
    uni.setNavigationBarTitle({ title: TYPE_META[recordType.value].nav })
  } else {
    uni.setNavigationBarTitle({ title: TYPE_META.idea.nav })
  }
})
</script>

<template>
  <view class="page" :class="'kind-' + recordType">
    <view class="card">
      <view class="type-switch">
        <text v-for="(m, key) in TYPE_META" :key="key"
          :class="['type-btn', 'type-' + key, recordType === key && 'type-active']"
          @click="switchType(key)">
          <text class="type-btn-icon">{{ m.icon }}</text>
          <text>{{ m.label }}</text>
        </text>
      </view>

      <text class="field-label">{{ TYPE_META[recordType].titleLabel }}</text>
      <input class="input" v-model="title" :placeholder="TYPE_META[recordType].titlePh" placeholder-class="ph" />

      <text class="field-label">内容</text>
      <textarea class="ta" v-model="content" :placeholder="TYPE_META[recordType].contentPh" placeholder-class="ph" />

      <block v-if="recordType !== 'todo'">
        <view class="photo-label-row">
          <text class="photo-title">这一刻的照片</text>
          <text class="photo-count">{{ noteImages.length }}/{{ MAX_PHOTOS }}</text>
        </view>
        <view class="photo-grid">
          <view v-for="(src, idx) in noteImages" :key="idx" class="photo-item">
            <image class="photo-img" :src="src" mode="aspectFill" @click="previewPhoto(idx)" />
            <view class="photo-remove" @click.stop="removePhoto(idx)">×</view>
          </view>
          <view v-if="noteImages.length < MAX_PHOTOS" class="photo-add" @click="choosePhoto">
            <text class="photo-plus">{{ photoUploading ? '…' : '＋' }}</text>
            <text class="photo-label">{{ photoUploading ? '上传中' : '添加照片' }}</text>
          </view>
        </view>
        <text class="photo-hint">最多 6 张 · 自动压缩、去除位置信息</text>
      </block>

      <block v-if="recordType === 'todo'">
        <text class="field-label">地点</text>
        <input class="input" v-model="location" placeholder="例如：理化国际大厦（选填）" placeholder-class="ph" />

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

        <view class="pin-row">
          <view class="pin-main">
            <text class="pin-title">置顶显示</text>
            <text class="pin-sub">置顶的任务会排在最前面</text>
          </view>
          <switch :checked="pinned" color="#6C7BF5" @change="e => pinned = e.detail.value" />
        </view>
      </block>

      <view v-else class="soft-tip">
        <text class="soft-tip-icon">{{ TYPE_META[recordType].icon }}</text>
        <text>{{ recordType === 'mood' ? '心情没有对错，记下此刻就好。' : '先记下来，之后再慢慢整理。' }}</text>
      </view>
    </view>

    <view class="actions">
      <button class="btn btn-primary" :class="{ 'btn-disabled': saving || photoUploading }"
        :disabled="saving || photoUploading" @click="save">
        {{ photoUploading ? '照片上传中…' : (saving ? '保存中…' : (editId ? '保存修改' : '保存')) }}
      </button>
      <button class="btn btn-danger" v-if="editId" @click="removeIt">删除</button>
    </view>
  </view>
</template>

<style scoped>
.page {
  min-height: 100vh;
  padding-bottom: 60rpx;
  --accent: #C9943C;
  --soft: #FFF4DC;
  --line: #F1DFC0;
}
.page.kind-idea { --accent: #7A5FD3; --soft: #F0E9FF; --line: #E3D8FB; }
.page.kind-mood { --accent: #D95D80; --soft: #FFE6ED; --line: #F7D3DF; }

.type-switch {
  display: flex;
  gap: 10rpx;
  padding: 8rpx;
  border-radius: 22rpx;
  background: #F6F4FB;
}
.type-btn {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 6rpx;
  padding: 16rpx 0;
  border-radius: 14rpx;
  font-size: 28rpx;
  color: #8A90A8;
  font-weight: 600;
}
.type-btn-icon { font-size: 24rpx; }
.type-todo.type-active { background: #F2B45C; color: #fff; }
.type-idea.type-active { background: #7A5FD3; color: #fff; }
.type-mood.type-active { background: #D95D80; color: #fff; }
.type-active { font-weight: 800; box-shadow: 0 6rpx 16rpx rgba(94, 70, 110, .16); }

.field-label { display: block; font-size: 28rpx; color: #5A5F78; margin: 30rpx 0 16rpx; }
.ph { color: #C3C7DA; }
.ta {
  width: 100%;
  min-height: 210rpx;
  background: #F6F4FB;
  border-radius: 20rpx;
  padding: 24rpx;
  font-size: 30rpx;
  box-sizing: border-box;
}
.photo-label-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin: 30rpx 0 16rpx;
}
.photo-title { font-size: 28rpx; color: #5A5F78; }
.photo-count { font-size: 22rpx; color: #A6AAC2; }
.photo-grid { display: flex; flex-wrap: wrap; gap: 12rpx; }
.photo-item {
  position: relative;
  width: 156rpx;
  height: 156rpx;
  flex-shrink: 0;
}
.photo-img { width: 156rpx; height: 156rpx; border-radius: 16rpx; background: var(--soft); }
.photo-remove {
  position: absolute;
  top: -10rpx;
  right: -10rpx;
  width: 38rpx;
  height: 38rpx;
  border-radius: 50%;
  background: rgba(58, 48, 68, .82);
  color: #fff;
  font-size: 26rpx;
  line-height: 34rpx;
  text-align: center;
}
.photo-add {
  width: 156rpx;
  height: 156rpx;
  flex-shrink: 0;
  border-radius: 16rpx;
  border: 2rpx dashed var(--line);
  background: var(--soft);
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 4rpx;
}
.photo-plus { color: var(--accent); font-size: 38rpx; line-height: 1; font-weight: 700; }
.photo-label { color: var(--accent); font-size: 21rpx; font-weight: 700; }
.photo-hint { display: block; margin-top: 12rpx; font-size: 22rpx; line-height: 1.7; color: #A6AAC2; }
.due-row { display: flex; gap: 20rpx; }
.picker-value {
  height: 88rpx;
  background: #F6F4FB;
  border-radius: 20rpx;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 0 30rpx;
  font-size: 30rpx;
}

.pri-row { display: flex; gap: 18rpx; }
.pri-item {
  flex: 1;
  text-align: center;
  padding: 18rpx 0;
  border-radius: 20rpx;
  font-size: 30rpx;
  background: #F6F4FB;
  color: #8A90A8;
  font-weight: 600;
}
.pri-high.pri-active { background: #FFEDEE; color: #F27E7E; }
.pri-medium.pri-active { background: #FFF6E7; color: #F2B45C; }
.pri-low.pri-active { background: #F4F2FA; color: #6B7089; }

.color-row { display: flex; gap: 22rpx; padding: 4rpx 0; }
.color-item {
  width: 60rpx;
  height: 60rpx;
  border-radius: 30rpx;
  display: flex;
  align-items: center;
  justify-content: center;
  box-shadow: 0 4rpx 10rpx rgba(124, 139, 255, .16);
}
.color-active { border: 4rpx solid #4E5170; }
.color-check { color: #fff; font-size: 28rpx; font-weight: 800; }

.pin-row { display: flex; justify-content: space-between; align-items: center; margin-top: 34rpx; }
.pin-title { display: block; font-size: 30rpx; font-weight: 600; }
.pin-sub { display: block; font-size: 25rpx; color: #A6AAC2; margin-top: 6rpx; }

.soft-tip {
  display: flex;
  align-items: center;
  gap: 12rpx;
  margin-top: 30rpx;
  padding: 20rpx 22rpx;
  border-radius: 20rpx;
  background: var(--soft);
  border: 1rpx dashed var(--line);
  color: #7B7186;
  font-size: 25rpx;
}
.soft-tip-icon { color: var(--accent); font-size: 28rpx; font-weight: 900; }

.kind-idea .btn-primary {
  background: linear-gradient(135deg, #8B6FE8, #6C52C9);
  box-shadow: 0 12rpx 26rpx rgba(108, 82, 201, .28);
}
.kind-mood .btn-primary {
  background: linear-gradient(135deg, #EA86A2, #D95D80);
  box-shadow: 0 12rpx 26rpx rgba(217, 93, 128, .26);
}

.actions { margin: 30rpx 24rpx; display: flex; flex-direction: column; gap: 20rpx; }
</style>
