<script setup>
import { ref, computed } from 'vue'
import { onShow } from '@dcloudio/uni-app'
import { apiUpdateMe, apiProfileStats, apiUploadAvatar, apiDeleteAvatar, apiMe } from '../../api/index.js'
import store, { clearLogin, setUser } from '../../store/user.js'
import { BASE_URL } from '../../common/config.js'
import { APP_FULL_NAME, APP_VERSION, APP_FEATURES, RELEASE_NOTES } from '../../common/app-info.js'
import { clearNotificationBadge } from '../../store/notifications.js'

const stats = ref({ total_bills: 0, total_days: 0, total_notes: 0, pending_todos: 0 })
const avatarUploading = ref(false)
const nickname = ref('')
const editingName = ref(false)
const pwdOpen = ref(false)
const oldPwd = ref('')
const newPwd = ref('')
const confirmPwd = ref('')
const pwdSaving = ref(false)
const apiOpen = ref(false)
const apiBase = ref(uni.getStorageSync('api_base') || BASE_URL)
const aboutOpen = ref(false)
const apiBaseLabel = computed(() => String(apiBase.value).replace(/^https?:\/\//, ''))

const avatar = computed(() => store.user?.avatar || '')
const initial = computed(() => (nickname.value || store.user?.username || 'U').slice(0, 1))

function saveApiBase() {
  const value = String(apiBase.value || '').trim().replace(/\/+$/, '')
  if (!/^https?:\/\/.+/.test(value)) {
    uni.showToast({ title: '请输入 http:// 开头的地址', icon: 'none' })
    return
  }
  uni.setStorageSync('api_base', value)
  apiBase.value = value
  apiOpen.value = false
  uni.showToast({ title: '服务器地址已保存', icon: 'success' })
}

async function loadAll() {
  try {
    const [s, me] = await Promise.all([apiProfileStats(), apiMe()])
    stats.value = s
    setUser(me)
    nickname.value = me.nickname || me.username || ''
  } catch (e) { /* 统一提示 */ }
}

async function saveNickname() {
  if (!nickname.value.trim()) { editingName.value = false; return }
  try {
    const user = await apiUpdateMe({ nickname: nickname.value.trim() })
    setUser(user)
    uni.showToast({ title: '昵称已更新', icon: 'success' })
  } catch (e) { /* 统一提示 */ } finally { editingName.value = false }
}

async function savePassword() {
  if (!oldPwd.value || !newPwd.value) {
    uni.showToast({ title: '请填写原密码和新密码', icon: 'none' }); return
  }
  if (newPwd.value.length < 6) {
    uni.showToast({ title: '新密码至少 6 位', icon: 'none' }); return
  }
  if (newPwd.value !== confirmPwd.value) {
    uni.showToast({ title: '两次输入的新密码不一致', icon: 'none' }); return
  }
  pwdSaving.value = true
  try {
    await apiUpdateMe({ old_password: oldPwd.value, new_password: newPwd.value })
    uni.showToast({ title: '密码修改成功', icon: 'success' })
    pwdOpen.value = false
    oldPwd.value = newPwd.value = confirmPwd.value = ''
  } catch (e) { /* 统一提示 */ } finally { pwdSaving.value = false }
}

function uploadAvatar(path) {
  if (!path) return
  avatarUploading.value = true
  apiUploadAvatar(path)
    .then((user) => {
      setUser(user)
      uni.showToast({ title: '头像已更新', icon: 'none' })
    })
    .catch(() => {})
    .finally(() => { avatarUploading.value = false })
}

function chooseAvatar() {
  if (avatarUploading.value) return
  uni.showActionSheet({
    itemList: ['从相册选择', '拍照'],
    success: (res) => {
      const sourceType = res.tapIndex === 1 ? ['camera'] : ['album']
      uni.chooseImage({
        count: 1,
        sizeType: ['compressed'],
        sourceType,
        success: (img) => uploadAvatar(img.tempFilePaths && img.tempFilePaths[0]),
      })
    },
  })
}

function removeAvatar() {
  uni.showModal({
    title: '恢复默认头像',
    content: '确定移除当前头像吗？',
    success: async (res) => {
      if (!res.confirm) return
      try {
        const user = await apiDeleteAvatar()
        setUser(user)
        uni.showToast({ title: '已恢复默认头像', icon: 'none' })
      } catch (e) { /* 统一提示 */ }
    },
  })
}

function goBudget() { uni.navigateTo({ url: '/pages/budget/center' }) }
function goGoals() { uni.navigateTo({ url: '/pages/goals/goals' }) }
function goSubscriptions() { uni.navigateTo({ url: '/pages/subscriptions/list' }) }

function logout() {
  uni.showModal({
    title: '退出登录',
    content: '确定退出当前账号吗？',
    success: (res) => {
      if (res.confirm) {
        clearLogin()
        clearNotificationBadge()
        uni.reLaunch({ url: '/pages/login/login' })
      }
    },
  })
}

onShow(() => {
  nickname.value = store.user?.nickname || store.user?.username || ''
  loadAll()
})
</script>

<template>
  <view class="page">
    <view class="title-row">
      <text class="page-title">我的</text>
      <image class="profile-sun" src="/static/doodles/sun.png" mode="widthFix" />
    </view>

    <!-- 用户卡 -->
    <view class="user-card">
      <view class="avatar-wrap" @click="chooseAvatar" @longpress="removeAvatar">
        <image v-if="avatar" class="avatar-img" :src="avatar" mode="aspectFill" />
        <view v-else class="avatar">{{ initial }}</view>
        <text class="avatar-edit">{{ avatarUploading ? '上传中…' : '换头像' }}</text>
      </view>
      <view class="user-info">
        <view v-if="!editingName" class="name-row" @click="editingName = true">
          <text class="name">{{ nickname }}</text>
          <text class="edit-hint">修改</text>
        </view>
        <view v-else class="name-edit">
          <input class="name-input" v-model="nickname" maxlength="30" />
          <text class="save-btn" @click="saveNickname">保存</text>
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

    <!-- 账号与安全 -->
    <text class="group-title">账号与安全</text>
    <view class="group-card">
      <view class="menu-item" @click="pwdOpen = !pwdOpen">
        <view class="menu-icon" style="background: #EFF1FF"><image class="menu-img" src="/static/icons/act_lock.png" mode="widthFix" /></view>
        <view class="menu-main">
          <text class="menu-title">账号与安全</text>
          <text class="menu-sub">@{{ store.user?.username }} · 修改登录密码</text>
        </view>
        <text class="menu-arrow">{{ pwdOpen ? '⌄' : '›' }}</text>
      </view>
      <view v-if="pwdOpen" class="expand-form">
        <input class="input form-input" v-model="oldPwd" password placeholder="原密码" placeholder-class="ph" />
        <input class="input form-input" v-model="newPwd" password placeholder="新密码（至少 6 位）" placeholder-class="ph" />
        <input class="input form-input" v-model="confirmPwd" password placeholder="确认新密码" placeholder-class="ph" />
        <button class="btn btn-primary form-btn" :class="{ 'btn-disabled': pwdSaving }"
          :disabled="pwdSaving" @click="savePassword">
          {{ pwdSaving ? '保存中…' : '保存新密码' }}
        </button>
      </view>
    </view>

    <!-- 常用功能 -->
    <text class="group-title">常用功能</text>
    <view class="group-card">
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
      <view class="menu-item" @click="apiOpen = !apiOpen">
        <view class="menu-icon" style="background: #F6F4FB"><image class="menu-img" src="/static/icons/act_info.png" mode="widthFix" /></view>
        <view class="menu-main">
          <text class="menu-title">服务器地址</text>
          <text class="menu-sub">{{ apiBaseLabel }}（真机调试用）</text>
        </view>
        <text class="menu-arrow">{{ apiOpen ? '⌄' : '›' }}</text>
      </view>
      <view v-if="apiOpen" class="expand-form">
        <input class="input form-input" v-model="apiBase"
          placeholder="http://192.168.1.100:8000" placeholder-class="ph" />
        <button class="btn btn-primary form-btn" @click="saveApiBase">保存地址</button>
      </view>
    </view>

    <!-- 关于 -->
    <text class="group-title">关于</text>
    <view class="group-card">
      <view class="menu-item" @click="aboutOpen = !aboutOpen">
        <view class="menu-icon" style="background: #F6F4FB"><image class="menu-img" src="/static/icons/act_info.png" mode="widthFix" /></view>
        <view class="menu-main">
          <text class="menu-title">关于系统</text>
          <text class="menu-sub">{{ APP_FULL_NAME }} v{{ APP_VERSION }}</text>
        </view>
        <text class="menu-arrow">{{ aboutOpen ? '⌄' : '›' }}</text>
      </view>
      <view v-if="aboutOpen" class="expand-form">
        <text class="about-text">
          {{ APP_FULL_NAME }} v{{ APP_VERSION }}。把记账、预算、订阅、目标、消费健康诊断、决策模拟和 Agent 行动连成一条闭环。
        </text>
        <text class="about-sub">当前能力</text>
        <text class="about-item" v-for="f in APP_FEATURES" :key="f">· {{ f }}</text>
        <text class="about-sub">版本更新</text>
        <text class="about-item" v-for="n in RELEASE_NOTES" :key="n.version">v{{ n.version }}（{{ n.date }}）：{{ n.text }}</text>
      </view>
    </view>

    <view class="logout-wrap">
      <button class="btn btn-danger" @click="logout">退出登录</button>
    </view>
  </view>
</template>

<style scoped>
.page { padding: 24rpx 24rpx 60rpx; }
.title-row { display: flex; justify-content: space-between; align-items: center; padding-right: 16rpx; }
.title-actions { display: flex; align-items: center; gap: 14rpx; }
.title-row .page-title { margin-bottom: 14rpx; }
.profile-sun { width: 88rpx; height: 88rpx; opacity: .9; transform: rotate(8deg); margin-top: -4rpx; }
.page-title { display: block; font-size: 48rpx; font-weight: 800; margin: 10rpx 8rpx 26rpx; }

/* 用户卡 */
.user-card { display: flex; align-items: center; background: #FFFDF8; border-radius: 32rpx;
  padding: 34rpx 30rpx; box-shadow: 0 6rpx 24rpx rgba(124, 139, 255, .10); }
.avatar-wrap { position: relative; width: 118rpx; height: 118rpx; flex-shrink: 0; }
.avatar { width: 118rpx; height: 118rpx; border-radius: 36rpx;
  background: linear-gradient(135deg, #6C7BF5, #A8B2FF); color: #fff;
  display: flex; align-items: center; justify-content: center; font-size: 52rpx; font-weight: 800; }
.avatar-img { width: 118rpx; height: 118rpx; border-radius: 36rpx; display: block; }
.avatar-edit { position: absolute; left: 0; right: 0; bottom: -22rpx; text-align: center;
  font-size: 19rpx; color: #6C7BF5; background: #FFFDF8; border-radius: 999rpx;
  padding: 2rpx 0; border: 1rpx solid #E9E6F4; }
.user-info { margin-left: 26rpx; flex: 1; min-width: 0; }
.name-row { display: flex; align-items: center; gap: 16rpx; }
.name { font-size: 38rpx; font-weight: 700; }
.edit-hint { font-size: 25rpx; color: #6C7BF5; background: #EFF1FF; border-radius: 20rpx; padding: 4rpx 16rpx; }
.name-edit { display: flex; align-items: center; gap: 16rpx; }
.name-input { height: 64rpx; background: #F6F4FB; border-radius: 12rpx; padding: 0 20rpx;
  font-size: 32rpx; width: 300rpx; }
.save-btn { font-size: 28rpx; font-weight: 600; color: #6C7BF5; }
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
/* 未读角标（预算预警入口） */
.menu-badge {
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

/* 展开表单 */
.expand-form { padding: 8rpx 26rpx 30rpx; background: #FBFAFE; border-bottom: 1rpx solid #F4F2FA; }
.form-input { margin-bottom: 18rpx; background: #FFFDF8; }
.ph { color: #C3C7DA; }
.form-btn { height: 80rpx; font-size: 30rpx; }
.about-text { display: block; font-size: 26rpx; color: #5A5F78; line-height: 1.9; }
.about-sub { display: block; font-size: 24rpx; font-weight: 700; color: #6C7BF5; margin-top: 16rpx; }
.about-item { display: block; font-size: 23rpx; color: #8A90A8; line-height: 1.8; margin-top: 4rpx; }

.logout-wrap { margin-top: 40rpx; }
</style>
