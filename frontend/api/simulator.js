/** 决策模拟页专用 API：直接复用统一请求封装，避免页面 chunk 的跨模块导出别名问题。 */
import http from './request.js'

export const loadSimulatorBase = () => Promise.all([
  http.get('/api/categories', { type: 'expense' }),
  http.get('/api/goals'),
])

export const apiSimulateDecision = (data) =>
  http.post('/api/decision-simulator/simulate', data)
