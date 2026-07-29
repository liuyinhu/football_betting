// 与后端交互的封装（赛事数据分析版：拉取赛事数据与胜率分析）。
import { request } from './request.js'

// 获取可用的分析引擎列表（dc / nn 及其可用状态）
export function fetchEngines() {
  return request('/api/engines')
}

// 获取接下来 N 场比赛 + 赛前胜率分析（engine: 'dc' | 'nn'）
export function fetchMatches(limit = 10, engine = 'dc') {
  return request(`/api/matches?limit=${limit}&engine=${engine}`)
}

// 获取当前「进行中」比赛的实时状态 + 实时胜率分析（engine: 'dc' | 'nn'）
export function fetchLive(engine = 'dc') {
  return request(`/api/live?engine=${engine}`)
}
