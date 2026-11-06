<script setup>
/**
 * 订阅设置：新增 / 编辑周期固定支出
 *
 * 订阅记录完全由用户手动录入，系统不联网查询第三方平台的真实续费状态；
 * 到达每月扣费日后，由后端在账单页同步时自动生成一笔支出账单。
 */
import { ref, computed } from 'vue'
import { onLoad } from '@dcloudio/uni-app'
import {
  apiSubscriptions, apiAddSubscription, apiUpdateSubscription, apiDeleteSubscription,
  apiCategories,
} from '../../api/index.js'

const subId = ref(null)
const name = ref('')
const dayOfMonth = ref(1)
const amount = ref('')
const categoryId = ref(null)
const categories = ref([])
const remark = ref('')
const remindEnabled = ref(true)
const saving = ref(false)

const dayRange = Array.from({ length: 31 }, (_, i) => `每月 ${i + 1} 日`)
const dayIndex = computed(() => dayOfMonth.value - 1)

const categoryIndex = computed(() =>
  Math.max(0, categories.value.findIndex(c => c.id === categoryId.value)))
const categoryName = computed(() =>
  (categories.value.find(c => c.id === categoryId.value) || {}).name || '其他')

function changeDay(e) {
  dayOfMonth.value = Number(e.detail.value) + 1
}

function changeCategory(e) {
  const c = categories.value[Number(e.detail.value)]
  if (c) categoryId.value = c.id
}

async function loadCategories() {
  try {
    const res = await apiCategories('expense')
    categories.value = res.items
    if (!categoryId.value) {
      const def = res.items.find(c => c.name === '其他') || res.items[0]
      if (def) categoryId.value = def.id
    }
  } catch (e) { /* 忽略 */ }
}

async function loadSub(id) {
  const list = await apiSubscriptions()
  const row = list.find(s => s.id === id)
  if (!row) {
    uni.showToast({ title: '订阅不存在', icon: 'none' })
    setTimeout(() => uni.navigateBack(), 800)
    return
  }
  name.value = row.name
  dayOfMonth.value = row.day_of_month
  amount.value = String(Number(row.amount))
  if (row.category_id) categoryId.value = row.category_id
  remark.value = row.remark || ''
  remindEnabled.value = !!row.remind_enabled
}

async function save() {
  if (!name.value.trim()) {
    uni.showToast({ title: '请填写订阅名称', icon: 'none' }); return
  }
  if (!(Number(amount.value) > 0)) {
    uni.showToast({ title: '请输入正确的扣费金额', icon: 'none' }); return
  }
  const payload = {
    name: name.value.trim(),
    day_of_month: dayOfMonth.value,
    amount: Number(amount.value).toFixed(2),
    category_id: categoryId.value,
    remark: remark.value,
    remind_enabled: remindEnabled.value,
  }
  saving.value = true
  try {
    if (subId.value) {
      await apiUpdateSubscription(subId.value, payload)
      uni.showToast({ title: '已保存修改', icon: 'success' })
    } else {
      await apiAddSubscription(payload)
      uni.showToast({ title: '订阅已添加', icon: 'success' })
    }
    setTimeout(() => uni.navigateBack(), 700)
  } catch (e) { /* 统一提示 */ } finally { saving.value = false }
}

function removeSub() {
  uni.showModal({
    title: '删除订阅',
    content: '删除后不再自动记账，已生成的历史账单会保留。确定删除吗？',
    confirmText: '删除',
    confirmColor: '#E45858',
    success: async (res) => {
      if (!res.confirm) return
      try {
        await apiDeleteSubscription(subId.value)
        uni.showToast({ title: '已删除', icon: 'success' })
        setTimeout(() => uni.navigateBack(), 700)
      } catch (e) { /* 统一提示 */ }
    },
  })
}

onLoad(async (options) => {
  await loadCategories()
  if (options && options.id) {
    subId.value = Number(options.id)
    uni.setNavigationBarTitle({ title: '编辑订阅' })
    await loadSub(subId.value)
  }
})
</script>

<template>
  <view class="page">
    <view class="card">
      <!-- 名称 -->
      <text class="field-label">订阅名称</text>
      <input class="input" v-model="name" maxlength="60"
        placeholder="例如：QQ音乐会员、网易云会员、房租" placeholder-class="ph" />

      <!-- 每月扣费日期 -->
      <text class="field-label">每月扣费日期</text>
      <picker mode="selector" :range="dayRange" :value="dayIndex" @change="changeDay">
        <view class="picker-value">
          <text>每月 {{ dayOfMonth }} 日</text>
          <text class="picker-arrow">▾</text>
        </view>
      </picker>
      <text class="field-tip">遇到不足该天数的月份，自动按当月最后一天扣费</text>

      <!-- 金额 -->
      <text class="field-label">扣费金额</text>
      <view class="amount-box">
        <text class="yen">¥</text>
        <input class="amount-input" type="digit" v-model="amount" placeholder="0.00"
          placeholder-class="ph" />
      </view>

      <!-- 账单分类 -->
      <text class="field-label">账单分类</text>
      <picker mode="selector" :range="categories" range-key="name"
        :value="categoryIndex" @change="changeCategory">
        <view class="picker-value">
          <text>{{ categoryName }}</text>
          <text class="picker-arrow">▾</text>
        </view>
      </picker>
      <text class="field-tip">到达扣费日后，自动生成的账单会计入该分类</text>

      <!-- 备注 -->
      <text class="field-label">备注（选填）</text>
      <input class="input" v-model="remark" maxlength="200"
        placeholder="例如：家庭共享账号 / 出租屋" placeholder-class="ph" />

      <!-- 提醒开关 -->
      <view class="switch-row">
        <view class="switch-text">
          <text class="switch-title">扣费前 1 天提醒</text>
          <text class="switch-sub">打开小程序时弹窗提示即将扣费</text>
        </view>
        <switch :checked="remindEnabled" color="#6C7BF5"
          @change="e => remindEnabled = e.detail.value" />
      </view>
    </view>

    <!-- 规则说明 -->
    <view class="card rule-card">
      <text class="rule-title">自动记账规则</text>
      <text class="rule-line">· 到达每月扣费日，进入账单页时自动生成一笔支出账单</text>
      <text class="rule-line">· 自动生成的账单计入你选择的账单分类（默认「其他」）</text>
      <text class="rule-line">· 自动生成的账单计入收支统计，可在账单页查看与修改</text>
      <text class="rule-line">· 订阅状态由你手动维护，系统不联网获取平台真实续费状态</text>
    </view>

    <view class="actions">
      <button class="btn btn-primary" :class="{ 'btn-disabled': saving }"
        :disabled="saving" @click="save">
        {{ saving ? '保存中…' : (subId ? '保存修改' : '保存订阅') }}
      </button>
      <button class="btn btn-danger" v-if="subId" @click="removeSub">删除订阅</button>
    </view>
  </view>
</template>

<style scoped>
.page { padding-bottom: 60rpx; }
.field-label { display: block; font-size: 28rpx; color: #5A5F78; margin: 30rpx 0 16rpx; }
.field-label:first-child { margin-top: 4rpx; }
.ph { color: #DCE0EC; }
.picker-value { height: 92rpx; background: #FAF9FF; border: 1rpx solid #E9E6F4;
  border-radius: 22rpx; display: flex; align-items: center; justify-content: space-between;
  padding: 0 26rpx; font-size: 30rpx; box-sizing: border-box; }
.picker-arrow { color: #A6AAC2; font-size: 26rpx; }
.field-tip { display: block; font-size: 23rpx; color: #B4B8CC; margin-top: 10rpx; }

.amount-box { display: flex; align-items: center; border-bottom: 2rpx solid #EEF0F5;
  padding-bottom: 16rpx; }
.yen { font-size: 48rpx; font-weight: 800; color: #3A3F58; margin-right: 14rpx; }
.amount-input { flex: 1; font-size: 60rpx; font-weight: 800; }

.switch-row { display: flex; align-items: center; justify-content: space-between;
  margin-top: 34rpx; padding-top: 26rpx; border-top: 1rpx dashed #EFECF7; }
.switch-text { flex: 1; min-width: 0; }
.switch-title { display: block; font-size: 29rpx; font-weight: 600; color: #3A3F58; }
.switch-sub { display: block; font-size: 23rpx; color: #A6AAC2; margin-top: 6rpx; }

.rule-card { background: #FBFAFF; }
.rule-title { display: block; font-size: 27rpx; font-weight: 700; color: #5A54B8;
  margin-bottom: 12rpx; }
.rule-line { display: block; font-size: 24rpx; color: #8A90A8; line-height: 1.7; }

.actions { margin: 30rpx 24rpx; display: flex; flex-direction: column; gap: 20rpx; }
</style>
