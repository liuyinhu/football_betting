<script setup>
import { ref } from 'vue'
import { onShow, onHide, onUnload } from '@dcloudio/uni-app'
import { fetchLive, fetchEngines } from '../../common/api.js'
import LiveMatchCard from '../../components/LiveMatchCard.vue'
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
  } catch (e) {}
}

function switchEngine(id) {
  if (engine.value === id) return
  engine.value = id
  startPolling()
}

// —— 实时数据 + 轮询 ——
const LIVE_INTERVAL = 30000
const liveMatches = ref([])
const liveLoading = ref(false)
const liveError = ref('')
const liveNote = ref('')
const liveEnabled = ref(true)
const lastUpdated = ref('')
let liveTimer = null
let enginesLoaded = false

async function loadLive(showSpinner = true) {
  if (showSpinner) liveLoading.value = true
  liveError.value = ''
  try {
    const res = await fetchLive(engine.value)
    liveEnabled.value = res.live_enabled !== false
    liveMatches.value = res.matches || []
    liveNote.value = res.note || ''
    lastUpdated.value = formatTime(new Date())
    if (!liveEnabled.value) stopPolling()
  } catch (e) {
    liveError.value = e.message
  } finally {
    liveLoading.value = false
  }
}

function formatTime(d) {
  const p = (n) => String(n).padStart(2, '0')
  return `${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())}`
}

function startPolling() {
  stopPolling()
  loadLive(true).then(() => {
    if (liveEnabled.value && !liveTimer) {
      liveTimer = setInterval(() => loadLive(false), LIVE_INTERVAL)
    }
  })
}

function stopPolling() {
  if (liveTimer) {
    clearInterval(liveTimer)
    liveTimer = null
  }
}

// 小程序生命周期：进入页面开始轮询，离开/隐藏时停止（省电、避免后台请求）
onShow(async () => {
  if (!enginesLoaded) {
    await loadEngines()
    enginesLoaded = true
  }
  startPolling()
})
onHide(stopPolling)
onUnload(stopPolling)
</script>

<template>
  <view class="page">
    <view class="app-header">
      <text class="title"><text class="tab-live-dot"></text> 实时赛事数据</text>
      <text class="subtitle">比赛进行中每 30 秒自动刷新数据与概率</text>
    </view>

    <EngineBar :engines="engines" :engine="engine" @switch="switchEngine" />

    <!-- 实时功能未启用 -->
    <view v-if="!liveEnabled" class="live-disabled">
      <text class="live-disabled-icon">🔌</text>
      <text class="live-disabled-title">实时更新未启用</text>
      <text class="live-disabled-p">{{ liveNote || '服务器未配置 API_FOOTBALL_KEY 环境变量，无法获取实时比赛数据。' }}</text>
      <view class="tb-btn" @click="loadLive(true)">{{ liveLoading ? '检查中…' : '↻ 重新检查' }}</view>
    </view>

    <template v-else>
      <view class="toolbar">
        <text class="live-status">
          <text class="tab-live-dot"></text>
          每 30 秒自动刷新<text v-if="lastUpdated"> · 最近 {{ lastUpdated }}</text>
        </text>
        <view class="tb-btn" @click="loadLive(true)">{{ liveLoading ? '刷新中…' : '↻ 立即刷新' }}</view>
      </view>
      <view v-if="liveNote" class="live-demo-note">{{ liveNote }}</view>

      <view v-if="liveLoading && !liveMatches.length" class="status-line">正在加载实时比赛…</view>
      <view v-else-if="liveError" class="status-line error">加载失败：{{ liveError }}</view>
      <view v-else-if="!liveMatches.length" class="status-line">当前没有进行中的中超比赛。</view>

      <view v-else>
        <LiveMatchCard v-for="m in liveMatches" :key="m.match_id" :match="m" :engine="engine" />
      </view>
    </template>

    <view class="app-footer">
      ⚠️ 本小程序仅提供赛事数据与概率科普，不构成任何投注建议，与博彩无关。
    </view>
  </view>
</template>

<style scoped>
.page { padding: 24rpx 24rpx 80rpx; }
.app-header { text-align: center; margin-bottom: 20rpx; }
.app-header .title { display: inline-flex; align-items: center; gap: 12rpx; font-size: 44rpx; font-weight: 700; }
.app-header .subtitle { display: block; color: #8b96ab; font-size: 24rpx; margin-top: 8rpx; }
.tab-live-dot {
  width: 16rpx;
  height: 16rpx;
  border-radius: 50%;
  background: #e11d48;
  animation: tab-live-pulse 1.2s ease-in-out infinite;
}
@keyframes tab-live-pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.3; }
}
.toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 20rpx;
  margin: 24rpx 0 24rpx;
  flex-wrap: wrap;
}
.live-status { display: inline-flex; align-items: center; gap: 12rpx; color: #6b7280; font-size: 24rpx; }
.tb-btn {
  background: #212a3d;
  color: #e6ebf5;
  border: 1rpx solid #2c374d;
  border-radius: 12rpx;
  padding: 12rpx 26rpx;
  font-size: 26rpx;
}
.live-demo-note {
  margin: 0 0 24rpx;
  padding: 16rpx 24rpx;
  background: #fef3c7;
  border-radius: 12rpx;
  color: #92400e;
  font-size: 24rpx;
}
.live-disabled { text-align: center; padding: 80rpx 40rpx; }
.live-disabled-icon { display: block; font-size: 80rpx; margin-bottom: 16rpx; }
.live-disabled-title { display: block; color: #f9fafb; font-size: 34rpx; font-weight: 600; margin-bottom: 16rpx; }
.live-disabled-p { display: block; color: #9ca3af; font-size: 26rpx; margin-bottom: 24rpx; }
.live-disabled .tb-btn { display: inline-block; }
.app-footer { text-align: center; color: #8b96ab; font-size: 22rpx; margin-top: 60rpx; line-height: 1.8; }
</style>
