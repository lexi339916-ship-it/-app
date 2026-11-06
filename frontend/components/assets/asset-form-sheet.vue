<script setup>
import { computed, ref, watch } from 'vue'
import { ASSET_TYPES, LIABILITY_TYPES } from '../../common/asset-meta.js'

const props = defineProps({
  visible: { type: Boolean, default: false },
  kind: { type: String, default: 'account' }, // account/editAccount/balance/liability/editLiability/repay/adjust/transfer
  item: { type: Object, default: null },
  accounts: { type: Array, default: () => [] },
  saving: { type: Boolean, default: false },
})
const emit = defineEmits(['close', 'submit'])

const name = ref('')
const type = ref('other')
const institution = ref('')
const hint = ref('')
const note = ref('')
const balance = ref('')
const outstanding = ref('')
const dueDate = ref('')
const target = ref('')
const amount = ref('')
const accountIndex = ref(0)
const fromIndex = ref(0)
const toIndex = ref(1)

const isAccount = computed(() => props.kind === 'account' || props.kind === 'editAccount')
const isLiability = computed(() => props.kind === 'liability' || props.kind === 'editLiability')
const title = computed(() => ({
  account: '新增资产账户',
  editAccount: '编辑资产账户',
  balance: '调整账户余额',
  liability: '新增负债',
  editLiability: '编辑负债',
  repay: '偿还负债',
  adjust: '调整欠款',
  transfer: '账户间转账',
}[props.kind] || '资产操作'))
const submitLabel = computed(() => ({
  account: '创建账户', editAccount: '保存修改', balance: '保存余额',
  liability: '创建负债', editLiability: '保存修改', repay: '确认还款',
  adjust: '保存欠款', transfer: '确认转账',
}[props.kind] || '保存'))
const selectedAccount = computed(() => props.accounts[accountIndex.value] || null)
const fromAccount = computed(() => props.accounts[fromIndex.value] || null)
const toAccount = computed(() => props.accounts[toIndex.value] || null)

function init() {
  const row = props.item || {}
  name.value = row.name || ''
  type.value = row.type || (isLiability.value ? 'credit_card' : 'other')
  institution.value = row.institution || ''
  hint.value = row.account_hint || ''
  note.value = row.note || row.remark || ''
  balance.value = props.kind === 'account' ? '' : String(Number(row.balance || 0))
  outstanding.value = String(Number(row.outstanding || 0))
  dueDate.value = row.due_date || ''
  target.value = props.kind === 'balance'
    ? String(Number(row.balance || 0))
    : String(Number(row.outstanding || 0))
  amount.value = ''
  accountIndex.value = 0
  fromIndex.value = 0
  toIndex.value = props.accounts.length > 1 ? 1 : 0
}

watch(() => props.visible, (v) => { if (v) init() })
watch(() => props.item, () => { if (props.visible) init() })

function money(value) {
  const n = Number(value)
  if (!Number.isFinite(n) || n < 0) return null
  return n.toFixed(2)
}

function submit() {
  if (props.saving) return
  if (isAccount.value) {
    if (!name.value.trim()) { toast('请填写账户名称'); return }
    const payload = {
      name: name.value.trim(),
      type: type.value,
      institution: institution.value.trim(),
      account_hint: hint.value.trim(),
      note: note.value.trim(),
    }
    if (props.kind === 'account') {
      const v = money(balance.value || 0)
      if (v === null) { toast('初始余额不能为负数'); return }
      payload.balance = v
    }
    emit('submit', payload)
    return
  }
  if (props.kind === 'balance') {
    const v = money(target.value)
    if (v === null) { toast('请输入正确的目标余额'); return }
    emit('submit', { kind: 'adjust', target_balance: v, note: note.value.trim() })
    return
  }
  if (isLiability.value) {
    if (!name.value.trim()) { toast('请填写负债名称'); return }
    const payload = {
      name: name.value.trim(),
      type: type.value,
      due_date: dueDate.value || null,
      remark: note.value.trim(),
    }
    if (props.kind === 'liability') {
      const v = money(outstanding.value)
      if (!v || Number(v) <= 0) { toast('欠款金额必须大于 0'); return }
      payload.outstanding = v
    }
    emit('submit', payload)
    return
  }
  if (props.kind === 'adjust') {
    const v = money(target.value)
    if (v === null) { toast('请输入正确的欠款金额'); return }
    emit('submit', { target_outstanding: v, note: note.value.trim() })
    return
  }
  if (props.kind === 'repay') {
    const v = money(amount.value)
    if (!v || Number(v) <= 0) { toast('请输入还款金额'); return }
    if (!selectedAccount.value) { toast('请选择还款账户'); return }
    emit('submit', { amount: v, account_id: selectedAccount.value.id, note: note.value.trim() })
    return
  }
  if (props.kind === 'transfer') {
    const v = money(amount.value)
    if (!v || Number(v) <= 0) { toast('请输入转账金额'); return }
    if (!fromAccount.value || !toAccount.value) { toast('请选择转出和转入账户'); return }
    if (fromAccount.value.id === toAccount.value.id) { toast('转出和转入账户不能相同'); return }
    emit('submit', {
      from_account_id: fromAccount.value.id,
      to_account_id: toAccount.value.id,
      amount: v,
      note: note.value.trim(),
    })
  }
}

function toast(title) {
  uni.showToast({ title, icon: 'none' })
}

function close() { emit('close') }
</script>

<template>
  <view v-if="visible" class="mask" @click.self="close">
    <view class="sheet">
      <view class="sheet-head">
        <text class="sheet-title">{{ title }}</text>
        <text class="sheet-close" @click="close">×</text>
      </view>

      <view v-if="isAccount">
        <text class="field-label">账户名称</text>
        <input class="input" v-model="name" maxlength="50" placeholder="如：招商银行储蓄卡" placeholder-class="ph" />

        <text class="field-label">资产类型</text>
        <view class="chips">
          <view v-for="(meta, key) in ASSET_TYPES" :key="key"
            :class="['chip', type === key && 'chip-on']" @click="type = key">
            <text class="chip-emoji">{{ meta.icon }}</text>
            <text>{{ meta.label }}</text>
          </view>
        </view>

        <view v-if="kind === 'account'">
          <text class="field-label">初始余额</text>
          <input class="input" type="digit" v-model="balance" placeholder="0.00" placeholder-class="ph" />
          <text class="hint">保存后会生成一笔“初始余额”流水，之后请用调整/转账/账单变动。</text>
        </view>

        <text class="field-label">开户机构 / 平台（选填）</text>
        <input class="input" v-model="institution" maxlength="50" placeholder="如：招商银行 / 微信" placeholder-class="ph" />

        <text class="field-label">卡号尾号（选填，只保留后 4 位）</text>
        <input class="input" v-model="hint" maxlength="32" placeholder="如：6789" placeholder-class="ph" />

        <text class="field-label">备注（选填）</text>
        <input class="input" v-model="note" maxlength="200" placeholder="用途说明" placeholder-class="ph" />
      </view>

      <view v-if="kind === 'balance'">
        <text class="field-label">当前余额</text>
        <view class="readonly">¥{{ Number(item?.balance || 0).toFixed(2) }}</view>
        <text class="field-label">调整到目标余额</text>
        <input class="input" type="digit" v-model="target" placeholder="0.00" placeholder-class="ph" />
        <text class="field-label">备注（选填）</text>
        <input class="input" v-model="note" maxlength="200" placeholder="如：与银行 App 对账" placeholder-class="ph" />
        <text class="hint">保存后会记录变动前/后余额，不会删除历史流水。</text>
      </view>

      <view v-if="isLiability">
        <text class="field-label">负债名称</text>
        <input class="input" v-model="name" maxlength="50" placeholder="如：招行信用卡" placeholder-class="ph" />
        <text class="field-label">负债类型</text>
        <view class="chips">
          <view v-for="(meta, key) in LIABILITY_TYPES" :key="key"
            :class="['chip', type === key && 'chip-on']" @click="type = key">
            <text class="chip-emoji">{{ meta.icon }}</text>
            <text>{{ meta.label }}</text>
          </view>
        </view>
        <view v-if="kind === 'liability'">
          <text class="field-label">当前欠款</text>
          <input class="input" type="digit" v-model="outstanding" placeholder="0.00" placeholder-class="ph" />
        </view>
        <text class="field-label">还款日（选填）</text>
        <view class="row">
          <picker mode="date" :value="dueDate" @change="dueDate = $event.detail.value">
            <view class="picker-box">{{ dueDate || '选择日期' }} ▾</view>
          </picker>
          <text v-if="dueDate" class="clear-link" @click="dueDate = ''">清除</text>
        </view>
        <text class="field-label">备注（选填）</text>
        <input class="input" v-model="note" maxlength="200" placeholder="如：本月账单" placeholder-class="ph" />
      </view>

      <view v-if="kind === 'adjust'">
        <text class="field-label">当前欠款</text>
        <view class="readonly">¥{{ Number(item?.outstanding || 0).toFixed(2) }}</view>
        <text class="field-label">调整到目标欠款</text>
        <input class="input" type="digit" v-model="target" placeholder="0.00" placeholder-class="ph" />
        <text class="field-label">备注（选填）</text>
        <input class="input" v-model="note" maxlength="200" placeholder="如：账单分期调整" placeholder-class="ph" />
      </view>

      <view v-if="kind === 'repay'">
        <text class="field-label">当前欠款</text>
        <view class="readonly">¥{{ Number(item?.outstanding || 0).toFixed(2) }}</view>
        <text class="field-label">还款金额</text>
        <input class="input" type="digit" v-model="amount" placeholder="0.00" placeholder-class="ph" />
        <text class="field-label">还款账户</text>
        <picker v-if="accounts.length" mode="selector" :range="accounts" range-key="name"
          :value="accountIndex" @change="accountIndex = Number($event.detail.value)">
          <view class="picker-box">{{ selectedAccount?.name || '选择账户' }} ▾</view>
        </picker>
        <view v-else class="warn-box">还没有资产账户，请先新增账户再还款。</view>
        <text class="hint">还款会同时减少账户余额和负债，净资产不变。</text>
        <text class="field-label">备注（选填）</text>
        <input class="input" v-model="note" maxlength="200" placeholder="如：部分还款" placeholder-class="ph" />
      </view>

      <view v-if="kind === 'transfer'">
        <text class="field-label">从账户</text>
        <picker v-if="accounts.length" mode="selector" :range="accounts" range-key="name"
          :value="fromIndex" @change="fromIndex = Number($event.detail.value)">
          <view class="picker-box">{{ fromAccount?.name || '选择转出账户' }} ▾</view>
        </picker>
        <text class="field-label">到账户</text>
        <picker v-if="accounts.length" mode="selector" :range="accounts" range-key="name"
          :value="toIndex" @change="toIndex = Number($event.detail.value)">
          <view class="picker-box">{{ toAccount?.name || '选择转入账户' }} ▾</view>
        </picker>
        <text class="field-label">转账金额</text>
        <input class="input" type="digit" v-model="amount" placeholder="0.00" placeholder-class="ph" />
        <text class="hint">账户间转账只是资金转移，不生成消费账单，不会增加本月支出。</text>
        <text class="field-label">备注（选填）</text>
        <input class="input" v-model="note" maxlength="200" placeholder="如：银行卡转到支付宝" placeholder-class="ph" />
      </view>

      <button class="btn btn-primary sheet-submit" :class="{ 'btn-disabled': saving }"
        :disabled="saving" @click="submit">
        {{ saving ? '保存中…' : submitLabel }}
      </button>
    </view>
  </view>
</template>

<style scoped>
.mask { position: fixed; left: 0; right: 0; top: 0; bottom: 0; z-index: 999;
  background: rgba(35, 34, 58, .45); display: flex; align-items: flex-end; }
.sheet { width: 100%; max-height: 84vh; overflow-y: auto; background: #FFFDF8;
  border-radius: 34rpx 34rpx 0 0; padding: 26rpx 28rpx 40rpx; box-sizing: border-box; }
.sheet-head { display: flex; align-items: center; justify-content: space-between; margin-bottom: 8rpx; }
.sheet-title { font-size: 32rpx; font-weight: 800; color: #3A3F58; }
.sheet-close { font-size: 42rpx; color: #A6AAC2; padding: 0 8rpx; line-height: 1; }
.field-label { display: block; font-size: 25rpx; color: #5A5F78; margin: 20rpx 0 10rpx; }
.input { width: 100%; height: 78rpx; box-sizing: border-box; }
.ph { color: #C3C7DA; }
.chips { display: flex; flex-wrap: wrap; gap: 12rpx; }
.chip { display: flex; align-items: center; gap: 6rpx; padding: 12rpx 20rpx;
  border-radius: 18rpx; background: #F6F4FB; color: #5A5F78; font-size: 24rpx;
  border: 2rpx solid transparent; }
.chip-on { background: #EFF1FF; color: #5A54B8; border-color: #A9B0F0; font-weight: 700; }
.chip-emoji { font-size: 24rpx; }
.hint { display: block; font-size: 21rpx; color: #A6AAC2; line-height: 1.6; margin-top: 10rpx; }
.readonly { height: 70rpx; line-height: 70rpx; padding: 0 20rpx; background: #F6F4FB;
  border-radius: 16rpx; font-size: 30rpx; font-weight: 700; color: #5A54B8; }
.row { display: flex; align-items: center; gap: 16rpx; }
.picker-box { min-width: 260rpx; height: 78rpx; line-height: 78rpx; background: #F6F4FB;
  border-radius: 18rpx; padding: 0 22rpx; font-size: 27rpx; color: #3A3F58; }
.clear-link { font-size: 24rpx; color: #8A90A8; }
.warn-box { background: #FFFAF0; border: 1rpx dashed #F5D9A8; color: #A56A1F;
  border-radius: 14rpx; padding: 14rpx 16rpx; font-size: 23rpx; line-height: 1.6; }
.sheet-submit { margin-top: 30rpx; height: 86rpx; font-size: 29rpx; }
.btn-disabled { opacity: .55; }
</style>
