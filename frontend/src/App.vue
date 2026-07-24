<script setup>
import { ref, onMounted, onUnmounted } from 'vue'
import { fetchMatches, fetchLive, fetchEngines } from './api.js'
import MatchCard from './components/MatchCard.vue'
import LiveMatchCard from './components/LiveMatchCard.vue'

const tab = ref('prematch')   // 'prematch' | 'live'

// —— 预测引擎（dc = Dixon-Coles 泊松, nn = 神经网络）——
const engines = ref([{ id: 'dc', name: 'Dixon-Coles 泊松', available: true }])
const engine = ref('dc')

async function loadEngines() {
  try {
    const res = await fetchEngines()
    if (res.engines && res.engines.length) {
      engines.value = res.engines
      // 默认选中后端标记的 default，且必须可用
      const def = res.engines.find((e) => e.default && e.available)
      engine.value = (def || res.engines.find((e) => e.available) || res.engines[0]).id
    }
  } catch (e) {
    // 拉取失败时保留默认 dc，不阻塞页面
  }
}

// 切换引擎：重新拉取当前标签页的数据
function switchEngine(id) {
  if (engine.value === id) return
  engine.value = id
  if (tab.value === 'prematch') {
    load()
  } else {
    startLivePolling()
  }
}

// —— 赛前 ——
const matches = ref([])
const loading = ref(false)
const errorMsg = ref('')
const limit = ref(10)

async function load() {
  loading.value = true
  errorMsg.value = ''
  try {
    const res = await fetchMatches(limit.value, engine.value)
    matches.value = res.matches
  } catch (e) {
    errorMsg.value = e.message
  } finally {
    loading.value = false
  }
}

// —— 实时 ——
const LIVE_INTERVAL = 30000   // 30 秒轮询
const liveMatches = ref([])
const liveLoading = ref(false)
const liveError = ref('')
const liveNote = ref('')
const liveEnabled = ref(true)   // 后端是否启用了实时功能（是否配置 API key）
const lastUpdated = ref('')
let liveTimer = null

async function loadLive(showSpinner = true) {
  if (showSpinner) liveLoading.value = true
  liveError.value = ''
  try {
    const res = await fetchLive(engine.value)
    liveEnabled.value = res.live_enabled !== false
    liveMatches.value = res.matches || []
    liveNote.value = res.note || ''
    lastUpdated.value = new Date().toLocaleTimeString()
    // 实时未启用时不再轮询
    if (!liveEnabled.value) stopLivePolling()
  } catch (e) {
    liveError.value = e.message
  } finally {
    liveLoading.value = false
  }
}

function startLivePolling() {
  stopLivePolling()
  loadLive(true).then(() => {
    // 仅在实时启用时开启定时轮询
    if (liveEnabled.value && !liveTimer) {
      liveTimer = setInterval(() => loadLive(false), LIVE_INTERVAL)
    }
  })
}

function stopLivePolling() {
  if (liveTimer) {
    clearInterval(liveTimer)
    liveTimer = null
  }
}

function switchTab(t) {
  tab.value = t
  if (t === 'live') {
    startLivePolling()
  } else {
    stopLivePolling()
    if (!matches.value.length) load()
  }
}

onMounted(async () => {
  await loadEngines()
  load()
})
onUnmounted(stopLivePolling)
</script>

<template>
  <div class="container">
    <header class="app-header">
      <h1>⚽ 中超预测与投注建议</h1>
      <p>基于 Dixon-Coles 时变泊松模型：赛前给出预测概率，比赛进行中每 30 秒刷新实时预测。</p>
    </header>

    <!-- 预测引擎切换 -->
    <div class="engine-bar">
      <span class="engine-label">预测引擎</span>
      <div class="engine-options">
        <button
          v-for="e in engines"
          :key="e.id"
          :class="{ active: engine === e.id }"
          :disabled="e.available === false"
          :title="e.available === false ? '该模型尚未训练：python3 -m data.train_nn --goals --save' : e.name"
          @click="switchEngine(e.id)"
        >
          {{ e.name }}
          <span v-if="e.available === false" class="engine-na">未训练</span>
        </button>
      </div>
    </div>

    <!-- 标签切换 -->
    <div class="tab-bar">
      <button :class="{ active: tab === 'prematch' }" @click="switchTab('prematch')">
        赛前预测
      </button>
      <button :class="{ active: tab === 'live' }" @click="switchTab('live')">
        <span class="tab-live-dot"></span> 实时预测
      </button>
    </div>

    <!-- 赛前预测 -->
    <template v-if="tab === 'prematch'">
      <div class="toolbar">
        <label>展示场次</label>
        <select v-model.number="limit" @change="load">
          <option :value="5">最近 5 场</option>
          <option :value="10">最近 10 场</option>
          <option :value="15">最近 15 场</option>
          <option :value="20">最近 20 场</option>
        </select>
        <button @click="load" :disabled="loading">
          {{ loading ? '加载中…' : '↻ 刷新' }}
        </button>
      </div>

      <p v-if="loading" class="status-line">正在加载赛程与预测…</p>
      <p v-else-if="errorMsg" class="status-line error">加载失败：{{ errorMsg }}</p>
      <p v-else-if="!matches.length" class="status-line">暂无即将开赛的中超赛程。</p>

      <div v-else class="match-grid">
        <MatchCard v-for="m in matches" :key="m.match_id" :match="m" :engine="engine" />
      </div>
    </template>

    <!-- 实时预测 -->
    <template v-else>
      <!-- 实时功能未启用（后端未配置 API key） -->
      <div v-if="!liveEnabled" class="live-disabled">
        <div class="live-disabled-icon">🔌</div>
        <h3>实时更新未启用</h3>
        <p>{{ liveNote || '服务器未配置 API_FOOTBALL_KEY 环境变量，无法获取实时比赛数据。' }}</p>
        <p class="live-disabled-hint">
          启动后端时提供 API key 即可开启实时预测：<br />
          <code>API_FOOTBALL_KEY=你的key python3 -m webapp.app</code>
        </p>
        <button @click="loadLive(true)" :disabled="liveLoading">
          {{ liveLoading ? '检查中…' : '↻ 重新检查' }}
        </button>
      </div>

      <template v-else>
        <div class="toolbar">
          <span class="live-status">
            <span class="tab-live-dot"></span>
            每 30 秒自动刷新<template v-if="lastUpdated"> · 最近更新 {{ lastUpdated }}</template>
          </span>
          <button @click="loadLive(true)" :disabled="liveLoading">
            {{ liveLoading ? '刷新中…' : '↻ 立即刷新' }}
          </button>
        </div>
        <p v-if="liveNote" class="live-demo-note">{{ liveNote }}</p>

        <p v-if="liveLoading && !liveMatches.length" class="status-line">正在加载实时比赛…</p>
        <p v-else-if="liveError" class="status-line error">加载失败：{{ liveError }}</p>
        <p v-else-if="!liveMatches.length" class="status-line">当前没有进行中的中超比赛。</p>

        <div v-else class="match-grid">
          <LiveMatchCard v-for="m in liveMatches" :key="m.match_id" :match="m" />
        </div>
      </template>
    </template>

    <footer class="app-footer">
      数据来源：中国足协官方 API · 模型：时变泊松 + Dixon-Coles<br />
      ⚠️ 本项目仅供学习研究，模型不保证盈利，请勿用于真实赌博。
    </footer>
  </div>
</template>

<style scoped>
.engine-bar {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 14px;
  flex-wrap: wrap;
}
.engine-label {
  font-size: 13px;
  color: #9ca3af;
  font-weight: 600;
}
.engine-options {
  display: inline-flex;
  gap: 6px;
  flex-wrap: wrap;
}
.engine-options button {
  padding: 6px 14px;
  border: 1px solid #374151;
  background: transparent;
  color: #d1d5db;
  border-radius: 999px;
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  display: inline-flex;
  align-items: center;
  gap: 6px;
  transition: all 0.15s ease;
}
.engine-options button.active {
  background: #22d3ee;
  border-color: #22d3ee;
  color: #0b1120;
}
.engine-options button:disabled {
  opacity: 0.45;
  cursor: not-allowed;
}
.engine-na {
  font-size: 11px;
  font-weight: 500;
  color: #f59e0b;
}
.tab-bar {
  display: flex;
  gap: 8px;
  margin-bottom: 16px;
}
.tab-bar button {
  flex: 1;
  padding: 10px 16px;
  border: 1px solid #111827;
  background: #111827;
  border-radius: 8px;
  font-size: 15px;
  font-weight: 600;
  color: #fff;
  cursor: pointer;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  transition: all 0.15s ease;
}
.tab-bar button.active {
  background: #fff;
  color: #111827;
  border-color: #111827;
}
.tab-live-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #e11d48;
  animation: tab-live-pulse 1.2s ease-in-out infinite;
}
@keyframes tab-live-pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.3; }
}
.live-status {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  color: #6b7280;
  font-size: 14px;
}
.live-demo-note {
  margin: -6px 0 14px;
  padding: 8px 12px;
  background: #fef3c7;
  border-radius: 8px;
  color: #92400e;
  font-size: 13px;
}
.live-disabled {
  text-align: center;
  padding: 40px 20px;
}
.live-disabled-icon {
  font-size: 44px;
  margin-bottom: 8px;
}
.live-disabled h3 {
  margin: 0 0 8px;
  color: #f9fafb;
}
.live-disabled p {
  color: #9ca3af;
  margin: 6px 0;
}
.live-disabled-hint {
  font-size: 13px;
  margin-top: 14px !important;
}
.live-disabled code {
  display: inline-block;
  margin-top: 6px;
  padding: 4px 10px;
  background: rgba(255, 255, 255, 0.08);
  border-radius: 6px;
  color: #d1d5db;
  font-size: 12px;
}
.live-disabled button {
  margin-top: 16px;
  padding: 8px 20px;
  border: 1px solid #4b5563;
  background: transparent;
  color: #e5e7eb;
  border-radius: 8px;
  cursor: pointer;
  font-weight: 600;
}
</style>
