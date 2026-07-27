<script setup>
import { ref } from 'vue'
import { onLoad, onPullDownRefresh } from '@dcloudio/uni-app'
import { fetchMatches, fetchEngines } from '../../common/api.js'
import MatchCard from '../../components/MatchCard.vue'
import EngineBar from '../../components/EngineBar.vue'

// —— 预测引擎 ——
const engines = ref([{ id: 'dc', name: 'Dixon-Coles 泊松', available: true }])
const engine = ref('dc')

async function loadEngines() {
  try {
    const res = await fetchEngines()
    if (res.engines && res.engines.length) {
      engines.value = res.engines
      const def = res.engines.find((e) => e.default && e.available)
      engine.value = (def || res.engines.find((e) => e.available) || res.engines[0]).id
    }
  } catch (e) {
    // 拉取失败保留默认 dc
  }
}

function switchEngine(id) {
  if (engine.value === id) return
  engine.value = id
  load()
}

// —— 赛前赛程 + 预测 ——
const matches = ref([])
const loading = ref(false)
const errorMsg = ref('')
const limit = ref(10)

// 展示场次选项（小程序用 picker）
const limitOptions = [5, 10, 15, 20]
const limitIndex = ref(1)
function onLimitChange(e) {
  limitIndex.value = Number(e.detail.value)
  limit.value = limitOptions[limitIndex.value]
  load()
}

async function load() {
  loading.value = true
  errorMsg.value = ''
  try {
    const res = await fetchMatches(limit.value, engine.value)
    matches.value = res.matches || []
  } catch (e) {
    errorMsg.value = e.message
  } finally {
    loading.value = false
    uni.stopPullDownRefresh()
  }
}

onLoad(async () => {
  await loadEngines()
  load()
})
onPullDownRefresh(() => load())
</script>

<template>
  <view class="page">
    <view class="app-header">
      <text class="title">⚽ 中超赛事数据分析</text>
      <text class="subtitle">基于 Dixon-Coles 时变泊松模型的赛事概率科普与数据展示</text>
    </view>

    <EngineBar :engines="engines" :engine="engine" @switch="switchEngine" />

    <view class="toolbar">
      <text class="tb-label">展示场次</text>
      <picker :range="limitOptions" :value="limitIndex" @change="onLimitChange">
        <view class="picker">最近 {{ limit }} 场 ▾</view>
      </picker>
      <view class="tb-btn" @click="load">{{ loading ? '加载中…' : '↻ 刷新' }}</view>
    </view>

    <view v-if="loading" class="status-line">正在加载赛程与预测…</view>
    <view v-else-if="errorMsg" class="status-line error">加载失败：{{ errorMsg }}</view>
    <view v-else-if="!matches.length" class="status-line">暂无即将开赛的中超赛程。</view>

    <view v-else>
      <MatchCard v-for="m in matches" :key="m.match_id" :match="m" :engine="engine" />
    </view>

    <view class="app-footer">
      数据来源：中国足协官方 API · 模型：时变泊松 + Dixon-Coles{{ '\n' }}
      ⚠️ 本小程序仅提供赛事数据与概率科普，不构成任何投注建议，与博彩无关。
    </view>
  </view>
</template>

<style scoped>
.page { padding: 24rpx 24rpx 80rpx; }
.app-header { text-align: center; margin-bottom: 20rpx; }
.app-header .title { display: block; font-size: 44rpx; font-weight: 700; }
.app-header .subtitle { display: block; color: #8b96ab; font-size: 24rpx; margin-top: 8rpx; }
.toolbar {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 20rpx;
  margin: 24rpx 0 32rpx;
  flex-wrap: wrap;
}
.tb-label { color: #8b96ab; font-size: 26rpx; }
.picker, .tb-btn {
  background: #212a3d;
  color: #e6ebf5;
  border: 1rpx solid #2c374d;
  border-radius: 12rpx;
  padding: 12rpx 26rpx;
  font-size: 26rpx;
}
.app-footer {
  text-align: center;
  color: #8b96ab;
  font-size: 22rpx;
  margin-top: 60rpx;
  line-height: 1.8;
  white-space: pre-line;
}
</style>
