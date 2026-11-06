/** 资产/负债类型与流水文案：全站统一，避免各页面各写一套。 */
export const ASSET_TYPES = {
  cash: { label: '现金', icon: '💵', color: '#D98A32', bg: '#FFF6E7' },
  bank: { label: '银行账户', icon: '🏦', color: '#4C7FE8', bg: '#EAF2FF' },
  wechat: { label: '微信余额', icon: '💚', color: '#07A85B', bg: '#E9F8F2' },
  alipay: { label: '支付宝余额', icon: '🔵', color: '#1677FF', bg: '#EAF2FF' },
  savings: { label: '储蓄存款', icon: '🏧', color: '#7C6BD8', bg: '#F4F0FF' },
  other: { label: '其他资产', icon: '📦', color: '#8A90A8', bg: '#F6F4FB' },
}

export const LIABILITY_TYPES = {
  credit_card: { label: '信用卡待还', icon: '💳', color: '#E45858', bg: '#FFEDEE' },
  installment: { label: '分期欠款', icon: '🧾', color: '#D98A32', bg: '#FFF6E7' },
  personal_loan: { label: '个人借款', icon: '🤝', color: '#6C7BF5', bg: '#EFF1FF' },
  other: { label: '其他负债', icon: '📌', color: '#8A90A8', bg: '#F6F4FB' },
}

export function assetMeta(type) {
  return ASSET_TYPES[type] || ASSET_TYPES.other
}

export function liabilityMeta(type) {
  return LIABILITY_TYPES[type] || LIABILITY_TYPES.other
}

export const TX_LABELS = {
  opening: '初始余额',
  manual_in: '手动增加',
  manual_out: '手动减少',
  adjustment: '余额调整',
  transfer_in: '转账转入',
  transfer_out: '转账转出',
  bill_expense: '账单支出',
  bill_income: '账单收入',
  bill_reversal: '账单冲正',
  liability_increase: '负债增加',
  liability_repay: '负债偿还',
  liability_adjustment: '欠款调整',
}

export function txLabel(type) {
  return TX_LABELS[type] || type || '资产变动'
}

export function fmtMoney(value) {
  const n = Number(value || 0)
  return n.toLocaleString('zh-CN', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })
}
