<script setup>
import { ref, computed } from 'vue'
import { onShow } from '@dcloudio/uni-app'
import { apiUpdateMe, apiUploadAvatar, apiDeleteAvatar, apiMe } from '../../api/index.js'
import store, { clearLogin, setUser } from '../../store/user.js'
import { BASE_URL } from '../../common/config.js'
import { APP_FULL_NAME, APP_VERSION, APP_FEATURES, RELEASE_NOTES } from '../../common/app-info.js'
import { clearNotificationBadge } from '../../store/notifications.js'

const nickname = ref('')
const nameDraft = ref('')
const editingName = ref(false)
const avatarUploading = ref(false)
const pwdOpen = ref(false)
const oldPwd = ref('')
const newPwd = ref('')
const confirmPwd = ref('')
const pwdSaving = ref(false)
const apiOpen = ref(false)
const apiBase = ref(uni.getStorageSync('api_base') || BASE_URL)
const aboutOpen = ref(false)

const avatar = computed(() => store.user?.avatar || '')
const displayName = computed(() => nickname.value || store.user?.nickname || store.user?.username || '用户')
const initial = computed(() => displayName.value.slice(0, 1))
const apiBaseLabel = computed(() => String(apiBase.value).replace(/^https?:\/\//, ''))

async function loadMe() {
  try {
    const me = await apiMe()
    setUser(me)
    nickname.value = me.nickname || me.username || ''
    nameDraft.value = nickname.value
  } catch (e) { /* 统一提示 */ }
}

function startNameEdit() {
  nameDraft.value = displayName.value
  editingName.value = true
}

async function saveName() {
  const value = nameDraft.value.trim()
  if (!value) {
    uni.showToast({ title: '用户名不能为空', icon: 'none' })
    return
  }
  try {
    const user = await apiUpdateMe({ nickname: value })
    setUser(user)
    nickname.value = user.nickname || user.username || value
    editingName.value = false
    uni.showToast({ title: '用户名已更新', icon: 'success' })
  } catch (e) { /* 统一提示 */ }
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
  if (!avatar.value) return
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

onShow(loadMe)
</script>

<template>
  <view class="page">
    <!-- 账号头部：头像、展示名、登录账号 -->
    <view class="hero">
      <view class="avatar-wrap" @click="chooseAvatar" @longpress="removeAvatar">
        <image v-if="avatar" class="avatar-img" :src="avatar" mode="aspectFill" />
        <view v-else class="avatar">{{ initial }}</view>
        <text class="avatar-tip">{{ avatarUploading ? '上传中…' : '点击更换' }}</text>
      </view>
      <view class="hero-main">
        <text class="hero-name">{{ displayName }}</text>
        <text class="hero-sub">@{{ store.user?.username }}</text>
        <text class="hero-note">长按头像可恢复默认</text>
      </view>
    </view>

    <text class="group-title">账号</text>
    <view class="group-card">
      <view class="row" @click="startNameEdit">
        <view class="row-main">
          <text class="row-title">用户名</text>
          <text class="row-sub">用于展示，可随时修改</text>
        </view>
        <view class="row-value">
          <text>{{ displayName }}</text>
          <text class="row-arrow">›</text>
        </view>
      </view>
      <view v-if="editingName" class="edit-panel">
        <input class="input form-input" v-model="nameDraft" maxlength="30"
          placeholder="输入新的用户名" placeholder-class="ph" />
        <view class="form-actions">
          <button class="btn btn-outline form-btn" @click="editingName = false">取消</button>
          <button class="btn btn-primary form-btn" @click="saveName">保存</button>
        </view>
      </view>

      <view class="row">
        <view class="row-main">
          <text class="row-title">登录账号</text>
          <text class="row-sub">账号 ID 已固定，暂不支持修改</text>
        </view>
        <text class="row-text">@{{ store.user?.username }}</text>
      </view>

      <view class="row" @click="pwdOpen = !pwdOpen">
        <view class="row-main">
          <text class="row-title">账号与安全</text>
          <text class="row-sub">修改登录密码</text>
        </view>
        <text class="row-arrow">{{ pwdOpen ? '⌄' : '›' }}</text>
      </view>
      <view v-if="pwdOpen" class="edit-panel">
        <input class="input form-input" v-model="oldPwd" password placeholder="原密码" placeholder-class="ph" />
        <input class="input form-input" v-model="newPwd" password placeholder="新密码（至少 6 位）" placeholder-class="ph" />
        <input class="input form-input" v-model="confirmPwd" password placeholder="确认新密码" placeholder-class="ph" />
        <button class="btn btn-primary form-btn" :class="{ 'btn-disabled': pwdSaving }"
          :disabled="pwdSaving" @click="savePassword">
          {{ pwdSaving ? '保存中…' : '保存新密码' }}
        </button>
      </view>
    </view>

    <text class="group-title">通用</text>
    <view class="group-card">
      <view class="row" @click="apiOpen = !apiOpen">
        <view class="row-main">
          <text class="row-title">服务器地址</text>
          <text class="row-sub">{{ apiBaseLabel }}（真机调试用）</text>
        </view>
        <text class="row-arrow">{{ apiOpen ? '⌄' : '›' }}</text>
      </view>
      <view v-if="apiOpen" class="edit-panel">
        <input class="input form-input" v-model="apiBase"
          placeholder="http://192.168.1.100:8000" placeholder-class="ph" />
        <button class="btn btn-primary form-btn" @click="saveApiBase">保存地址</button>
      </view>
    </view>

    <text class="group-title">关于</text>
    <view class="group-card">
      <view class="row" @click="aboutOpen = !aboutOpen">
        <view class="row-main">
          <text class="row-title">关于系统</text>
          <text class="row-sub">{{ APP_FULL_NAME }}</text>
        </view>
        <view class="version-row">
          <text class="version-badge">v{{ APP_VERSION }}</text>
          <text class="row-arrow">{{ aboutOpen ? '⌄' : '›' }}</text>
        </view>
      </view>
      <view v-if="aboutOpen" class="about-panel">
        <text class="about-lead">{{ APP_FULL_NAME }} v{{ APP_VERSION }}</text>
        <text class="about-text">
          知账把记录、记账、预算、资产、订阅、目标和 Agent 行动连成一条闭环，重点做可解释、可审批、可撤销的家庭消费健康管理。
        </text>
        <text class="about-sub">当前能力</text>
        <text class="about-item" v-for="f in APP_FEATURES" :key="f">· {{ f }}</text>
        <text class="about-sub">版本更新</text>
        <text class="about-item" v-for="n in RELEASE_NOTES" :key="n.version">
          v{{ n.version }}（{{ n.date }}）：{{ n.text }}
        </text>
        <text class="about-sub">数据与隐私</text>
        <text class="about-item">· 记录照片上传后自动压缩、去除位置信息，不保存原图。</text>
        <text class="about-item">· 演示数据均为合成数据；日志不记录密钥、完整账号或银行卡。</text>
      </view>
    </view>

    <view class="logout-wrap">
      <button class="btn btn-danger" @click="logout">退出登录</button>
    </view>
    <text class="footer-version">知账 · 家庭消费健康 Agent v{{ APP_VERSION }}</text>
  </view>
</template>

<style scoped>
.page { padding: 24rpx 24rpx 60rpx; }

.hero {
  display: flex;
  align-items: center;
  background: #FFFDF8;
  border-radius: 32rpx;
  padding: 32rpx 30rpx;
  box-shadow: 0 6rpx 24rpx rgba(124, 139, 255, .10);
}
.avatar-wrap { position: relative; width: 122rpx; height: 122rpx; flex-shrink: 0; }
.avatar,
.avatar-img { width: 122rpx; height: 122rpx; border-radius: 36rpx; display: block; }
.avatar {
  background: linear-gradient(135deg, #6C7BF5, #A8B2FF);
  color: #fff;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 52rpx;
  font-weight: 800;
}
.avatar-tip {
  position: absolute;
  left: 0;
  right: 0;
  bottom: -22rpx;
  text-align: center;
  font-size: 19rpx;
  color: #6C7BF5;
  background: #FFFDF8;
  border-radius: 999rpx;
  padding: 2rpx 0;
  border: 1rpx solid #E9E6F4;
}
.hero-main { margin-left: 28rpx; flex: 1; min-width: 0; }
.hero-name { display: block; font-size: 38rpx; font-weight: 800; color: #3A3F58; }
.hero-sub { display: block; margin-top: 6rpx; font-size: 26rpx; color: #A6AAC2; }
.hero-note { display: block; margin-top: 14rpx; font-size: 22rpx; color: #6C7BF5; }

.group-title {
  display: block;
  font-size: 28rpx;
  color: #8A90A8;
  font-weight: 600;
  margin: 34rpx 8rpx 14rpx;
}
.group-card {
  background: #FFFDF8;
  border-radius: 28rpx;
  overflow: hidden;
  box-shadow: 0 6rpx 24rpx rgba(124, 139, 255, .10);
}
.row {
  display: flex;
  align-items: center;
  gap: 18rpx;
  padding: 28rpx 26rpx;
  border-bottom: 1rpx solid #F4F2FA;
}
.row:last-child { border-bottom: none; }
.row:active { background: #FBFAFE; }
.row-main { flex: 1; min-width: 0; }
.row-title { display: block; font-size: 30rpx; font-weight: 600; color: #3A3F58; }
.row-sub { display: block; margin-top: 6rpx; font-size: 23rpx; color: #A6AAC2; }
.row-value { display: flex; align-items: center; gap: 8rpx; font-size: 26rpx; color: #6C7BF5; font-weight: 600; max-width: 330rpx; }
.row-value text:first-child { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.row-text { font-size: 26rpx; color: #8A90A8; }
.row-arrow { font-size: 34rpx; color: #D3D7E7; }
.version-row { display: flex; align-items: center; gap: 10rpx; }
.version-badge {
  font-size: 22rpx;
  color: #6C7BF5;
  background: #EFF1FF;
  border-radius: 999rpx;
  padding: 6rpx 14rpx;
}

.edit-panel {
  padding: 8rpx 26rpx 28rpx;
  background: #FBFAFE;
  border-bottom: 1rpx solid #F4F2FA;
}
.form-input { margin-bottom: 18rpx; background: #FFFDF8; }
.ph { color: #C3C7DA; }
.form-btn { height: 76rpx; font-size: 28rpx; }
.form-actions { display: flex; gap: 18rpx; }
.form-actions .form-btn { flex: 1; }

.about-panel { padding: 8rpx 26rpx 30rpx; background: #FBFAFE; }
.about-lead { display: block; font-size: 30rpx; font-weight: 800; color: #3A3F58; }
.about-text { display: block; margin-top: 12rpx; font-size: 25rpx; line-height: 1.9; color: #5A5F78; }
.about-sub { display: block; margin-top: 20rpx; font-size: 24rpx; font-weight: 700; color: #6C7BF5; }
.about-item { display: block; margin-top: 5rpx; font-size: 23rpx; line-height: 1.8; color: #8A90A8; }

.logout-wrap { margin-top: 42rpx; }
.footer-version { display: block; margin-top: 24rpx; text-align: center; font-size: 21rpx; color: #C3C7DA; }
</style>
