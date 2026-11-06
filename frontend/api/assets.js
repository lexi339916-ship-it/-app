/** 个人资产管理 API。金额由后端 Decimal 计算，前端只负责展示。 */
import http from './request.js'

export const apiAssetOverview = () => http.get('/api/assets/overview')
export const apiAssetAccounts = () => http.get('/api/assets/accounts')
export const apiAddAssetAccount = (data) => http.post('/api/assets/accounts', data)
export const apiUpdateAssetAccount = (id, data) => http.put(`/api/assets/accounts/${id}`, data)
export const apiDeleteAssetAccount = (id) => http.delete(`/api/assets/accounts/${id}`)
export const apiAdjustAssetAccount = (id, data) => http.post(`/api/assets/accounts/${id}/adjust`, data)
export const apiAssetTransfer = (data) => http.post('/api/assets/transfers', data)
export const apiAssetTransactions = (params = {}) => http.get('/api/assets/transactions', params)
export const apiAssetLiabilities = () => http.get('/api/assets/liabilities')
export const apiAddAssetLiability = (data) => http.post('/api/assets/liabilities', data)
export const apiUpdateAssetLiability = (id, data) => http.put(`/api/assets/liabilities/${id}`, data)
export const apiDeleteAssetLiability = (id) => http.delete(`/api/assets/liabilities/${id}`)
export const apiRepayAssetLiability = (id, data) => http.post(`/api/assets/liabilities/${id}/repay`, data)
export const apiAdjustAssetLiability = (id, data) => http.post(`/api/assets/liabilities/${id}/adjust`, data)
export const apiAssetChangeAnalysis = (month) =>
  http.get('/api/assets/change-analysis', month ? { month } : {})
