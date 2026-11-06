/**
 * 自动订阅扣费：进入页面时的同步与提醒
 *
 * 进入账单页 / 打开小程序时调用：
 * - 后端按服务器日期判断，到达扣费日自动补生成支出账单（并计入收支统计）；
 * - 明天就是扣费日的订阅，弹窗提醒（同一扣费月只弹一次）。
 *
 * 防重复：同一时刻只发一次请求（首页与账单页连续 onShow 复用同一个 Promise）；
 * 下次触发会重新同步，保证刚新增的订阅能立刻补生成账单。
 */
import { apiSubscriptionSync } from '../api/index.js'

let pending = null

export function syncSubscriptions() {
  if (pending) return pending
  pending = apiSubscriptionSync()
    .then((res) => {
      if (res && res.created_count > 0) {
        uni.showToast({
          title: `已自动记录 ${res.created_count} 笔订阅扣费`,
          icon: 'none',
          duration: 2500,
        })
      }
      if (res && res.reminders && res.reminders.length) showSubReminders(res.reminders)
      return res
    })
    .catch(() => null)
    .finally(() => { pending = null })
  return pending
}

/** 扣费前 1 天提醒：多条合并成一个弹窗，「去查看」进订阅管理页 */
export function showSubReminders(list) {
  const lines = list.map(r => `明天将自动扣费：${r.name} ¥${Number(r.amount).toFixed(2)}`)
  uni.showModal({
    title: '订阅扣费提醒',
    content: lines.join('\n'),
    confirmText: '去查看',
    cancelText: '知道了',
    confirmColor: '#6C7BF5',
    success: (res) => {
      if (res.confirm) uni.navigateTo({ url: '/pages/subscriptions/list' })
    },
  })
}
