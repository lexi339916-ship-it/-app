<script setup>
import { ref, computed } from 'vue'
import { onLoad } from '@dcloudio/uni-app'
import { apiBill, apiAddBill, apiUpdateBill, apiDeleteBill, apiCategories, apiBillCheck, apiAlertAction } from '../../api/index.js'
import { categoryMeta } from '../../common/category-icons.js'
import BudgetAlertPopup from '../../components/budget-alert-popup.vue'

const editId = ref(null)
const type = ref('expense')
const amount = ref('')
const category = ref('')
const billDate = ref('')
const remark = ref('')
const payChannel = ref('')
const fundingAccount = ref('')
const categories = ref([])
const saving = ref(false)
// OCR 截图识别进入：保存时 source 标记为 receipt（截图草稿统一进 Agent 工具抽屉）
const fromReceipt = ref(false)
const originalSource = ref('manual')
// 预算预警：记账成功后触发的预警队列（非空时弹窗逐条展示）
const pendingAlerts = ref([])
const CHANNELS = ['微信支付', '支付宝', '银行卡', '云闪付', '现金', '其他']
// 取本地日期（toISOString 会按 UTC 计算，凌晨时段会差一天）
const today = new Date(Date.now() - new Date().getTimezoneOffset() * 60000)
  .toISOString().slice(0, 10)

const typeCategories = computed(() => categories.value.filter(c => c.type === type.value))

async function loadCategories() {
  const res = await apiCategories()
  categories.value = res.items
}

function switchType(t) {
  type.value = t
  // 切换收支类型后，若当前分类不属于该类型则清空
  if (!typeCategories.value.some(c => c.name === category.value)) {
    category.value = ''
  }
}

function pickCategory(name) { category.value = name }

async function loadBill(id) {
  const b = await apiBill(id)
  type.value = b.type
  amount.value = String(Number(b.amount))
  category.value = b.category
  billDate.value = b.bill_date
  remark.value = b.remark
  payChannel.value = b.pay_channel || ''
  fundingAccount.value = b.funding_account || ''
  originalSource.value = b.source || 'manual'
}

async function save() {
  if (!amount.value || Number(amount.value) <= 0) {
    uni.showToast({ title: '请输入正确的金额', icon: 'none' }); return
  }
  if (!category.value) {
    uni.showToast({ title: '请选择分类', icon: 'none' }); return
  }
  if (!billDate.value) {
    uni.showToast({ title: '请选择日期', icon: 'none' }); return
  }
  const payload = {
    type: type.value,
    amount: Number(amount.value).toFixed(2),
    category: category.value,
    bill_date: billDate.value,
    remark: remark.value,
    source: fromReceipt.value ? 'receipt' : (editId.value ? originalSource.value : 'manual'),
    pay_channel: payChannel.value,
    funding_account: fundingAccount.value,
  }
  saving.value = true
  try {
    let billId
    if (editId.value) {
      await apiUpdateBill(editId.value, payload)
      billId = editId.value
      uni.showToast({ title: '修改成功', icon: 'success' })
    } else {
      const newBill = await apiAddBill(payload)
      billId = newBill.id
      uni.showToast({ title: '记账成功', icon: 'success' })
    }
    // 预算预警（新增模块，仅追加）：无论新增还是编辑，保存成功后都检查
    // 80%/100%/异常大额预警，命中则弹窗展示，用户看完再返回；检查失败静默
    try {
      const chk = await apiBillCheck(billId)
      if (chk && chk.alerts && chk.alerts.length) {
        pendingAlerts.value = chk.alerts
        return
      }
    } catch (e) { /* 预警检查失败静默，绝不影响记账流程 */ }
    setTimeout(() => uni.navigateBack(), 700)
  } catch (e) { /* 统一提示 */ } finally { saving.value = false }
}

function removeBill() {
  uni.showModal({
    title: '确认删除',
    content: '删除后无法恢复，确定删除该账单吗？',
    success: async (res) => {
      if (res.confirm) {
        await apiDeleteBill(editId.value)
        uni.showToast({ title: '已删除', icon: 'success' })
        setTimeout(() => uni.navigateBack(), 700)
      }
    },
  })
}

/** 预警弹窗全部看完：清空队列并返回账单列表 */
function onAlertsClosed() {
  // 弹窗里看过的预警标记已读，避免之后进首页时再弹一次同一条
  pendingAlerts.value.forEach(a => apiAlertAction(a.id, 'read').catch(() => {}))
  pendingAlerts.value = []
  uni.navigateBack()
}

onLoad(async (options) => {
  billDate.value = today
  // 支持从日历"为这天记一笔"进入：?date=YYYY-MM-DD 预填日期
  if (options && options.date && /^\d{4}-\d{2}-\d{2}$/.test(options.date)) {
    billDate.value = options.date
  }
  await loadCategories()
  if (options && options.id) {
    editId.value = Number(options.id)
    uni.setNavigationBarTitle({ title: '编辑账单' })
    await loadBill(editId.value)
  } else if (options && options.from === 'receipt') {
    // 首页"拍张截图自动记账"：OCR 草稿预填，用户确认后再保存
    fromReceipt.value = true
    if (options.type === 'income' || options.type === 'expense') type.value = options.type
    if (options.amount && Number(options.amount) > 0) amount.value = String(Number(options.amount))
    if (options.bill_date && /^\d{4}-\d{2}-\d{2}$/.test(options.bill_date)) billDate.value = options.bill_date
    if (options.category
        && categories.value.some(c => c.name === options.category && c.type === type.value)) {
      category.value = options.category
    }
    if (options.remark) remark.value = options.remark
    if (options.pay_channel && CHANNELS.includes(options.pay_channel)) payChannel.value = options.pay_channel
    if (options.funding_account) fundingAccount.value = options.funding_account
  }
})
</script>

<template>
  <view class="page">
    <view class="card">
      <!-- 收支类型 -->
      <view class="type-switch">
        <text :class="['type-btn', type === 'expense' && 'type-expense']" @click="switchType('expense')">支出</text>
        <text :class="['type-btn', type === 'income' && 'type-income']" @click="switchType('income')">收入</text>
      </view>

      <!-- 金额 -->
      <view class="amount-box">
        <text class="yen">¥</text>
        <input class="amount-input" type="digit" v-model="amount" placeholder="0.00"
          placeholder-class="ph" />
      </view>

      <!-- 分类 -->
      <text class="field-label">分类</text>
      <view class="cat-grid">
        <view v-for="c in typeCategories" :key="c.id"
          :class="['cat-item', category === c.name && 'cat-selected']"
          @click="pickCategory(c.name)">
          <image class="cat-emoji-img" :src="categoryMeta(c.name).img" mode="widthFix" />
          <text>{{ c.name }}</text>
        </view>
      </view>

      <!-- 日期 -->
      <text class="field-label">日期</text>
      <picker mode="date" :value="billDate" @change="e => billDate = e.detail.value">
        <view class="picker-value">{{ billDate }} ▾</view>
      </picker>

      <!-- 备注 -->
      <text class="field-label">备注</text>
      <input class="input" v-model="remark" placeholder="选填，如：午饭" placeholder-class="ph" />

      <!-- 支付渠道 -->
      <text class="field-label">支付渠道（选填）</text>
      <view class="cat-grid">
        <view :class="['cat-item', payChannel === '' && 'cat-selected']" @click="payChannel = ''">
          <text>未记录</text>
        </view>
        <view v-for="c in CHANNELS" :key="c"
          :class="['cat-item', payChannel === c && 'cat-selected']"
          @click="payChannel = c">
          <text>{{ c }}</text>
        </view>
      </view>
      <input v-if="payChannel" class="input channel-account" v-model="fundingAccount"
        placeholder="扣款账户（选填），如：零钱 / 工商银行储蓄卡" placeholder-class="ph" />
    </view>

    <view class="actions">
      <button class="btn btn-primary" :class="{ 'btn-disabled': saving }" :disabled="saving" @click="save">
        {{ saving ? '保存中…' : (editId ? '保存修改' : '保存账单') }}
      </button>
      <button class="btn btn-danger" v-if="editId" @click="removeBill">删除账单</button>
    </view>

    <!-- 预算预警弹窗（新增模块）：记账触发预警时逐条展示，看完后返回上一页 -->
    <budget-alert-popup :alerts="pendingAlerts" @close="onAlertsClosed" />
  </view>
</template>

<style scoped>
.page { padding-bottom: 60rpx; }
.type-switch { display: flex; background: #F6F4FB; border-radius: 20rpx; padding: 8rpx; }
.type-btn { flex: 1; text-align: center; padding: 16rpx 0; border-radius: 12rpx;
  font-size: 30rpx; color: #8A90A8; }
.type-expense { background: #6C7BF5; color: #fff; font-weight: 700; }
.type-income { background: #45C39A; color: #fff; font-weight: 700; }

.amount-box { display: flex; align-items: center; margin: 36rpx 0 10rpx; border-bottom: 2rpx solid #eef0f5; padding-bottom: 16rpx; }
.yen { font-size: 52rpx; font-weight: 800; color: #3A3F58; margin-right: 16rpx; }
.amount-input { flex: 1; font-size: 68rpx; font-weight: 800; }
.ph { color: #DCE0EC; }

.field-label { display: block; font-size: 28rpx; color: #5A5F78; margin: 30rpx 0 16rpx; }
.cat-grid { display: flex; flex-wrap: wrap; gap: 16rpx; }
.cat-item { display: flex; align-items: center; gap: 8rpx; padding: 14rpx 26rpx;
  background: #F6F4FB; border-radius: 22rpx; font-size: 28rpx; color: #5A5F78; }
.cat-emoji-img { width: 48rpx; height: 48rpx; }
.cat-selected { background: #6C7BF5; color: #fff; font-weight: 700; }
.channel-account { margin-top: 16rpx; }
.picker-value { height: 88rpx; background: #F6F4FB; border-radius: 20rpx;
  display: flex; align-items: center; padding: 0 24rpx; font-size: 30rpx; }

.actions { margin: 30rpx 24rpx; display: flex; flex-direction: column; gap: 20rpx; }
</style>
