// 与后端交互的封装。开发时通过 vite proxy 把 /api 转发到 Flask。
const BASE = import.meta.env.VITE_API_BASE || ''

async function request(path, options = {}) {
  const resp = await fetch(BASE + path, options)
  const data = await resp.json().catch(() => ({}))
  if (!resp.ok) {
    throw new Error(data.error || `请求失败 (${resp.status})`)
  }
  return data
}

// 获取接下来 N 场比赛 + 赛前预测概率
export function fetchMatches(limit = 10) {
  return request(`/api/matches?limit=${limit}`)
}

// 提交某场比赛的赔率，获取投注建议（odds 为空则仅返回概率）
export function predict(payload) {
  return request('/api/predict', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
}
