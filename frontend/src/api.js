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

// 获取可用的预测引擎列表（dc / nn 及其可用状态）
export function fetchEngines() {
  return request('/api/engines')
}

// 获取接下来 N 场比赛 + 赛前预测概率（engine: 'dc' | 'nn'）
export function fetchMatches(limit = 10, engine = 'dc') {
  return request(`/api/matches?limit=${limit}&engine=${engine}`)
}

// 获取当前「进行中」比赛的实时状态 + 实时预测（engine: 'dc' | 'nn'）
export function fetchLive(engine = 'dc') {
  return request(`/api/live?engine=${engine}`)
}

// 提交某场比赛的赔率，获取投注建议（odds 为空则仅返回概率）
// payload 可含 engine 字段
export function predict(payload) {
  return request('/api/predict', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
}
