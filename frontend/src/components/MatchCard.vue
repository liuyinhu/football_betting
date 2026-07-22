<script setup>
import { ref, reactive, computed } from 'vue'
import { predict } from '../api.js'

const props = defineProps({
  match: { type: Object, required: true },
})

// 概率初始值来自列表接口（无赔率），提交赔率后用返回值覆盖
const prediction = ref(props.match.prediction)
const showOdds = ref(false)
const loading = ref(false)
const errorMsg = ref('')
const recommendations = ref(null)   // null=未提交, []=提交但无建议
const hasOdds = ref(false)

// 赔率输入模型
const odds = reactive({
  home: '', draw: '', away: '',
  over25: '', under25: '',
  over15: '', over35: '',
})

const pct = (v) => (v == null ? '-' : (v * 100).toFixed(1) + '%')

const outcome = computed(() => prediction.value?.outcome || {})
const ou = computed(() => prediction.value?.over_under || {})
const btts = computed(() => prediction.value?.btts || {})
const topScores = computed(() => prediction.value?.top_scores || [])

// 胜平负条的三段宽度
const barSegs = computed(() => {
  const o = outcome.value
  const total = (o.home || 0) + (o.draw || 0) + (o.away || 0) || 1
  return {
    home: ((o.home || 0) / total * 100).toFixed(1),
    draw: ((o.draw || 0) / total * 100).toFixed(1),
    away: ((o.away || 0) / total * 100).toFixed(1),
  }
})

function buildOddsPayload() {
  const num = (v) => {
    const f = parseFloat(v)
    return isFinite(f) && f > 1 ? f : undefined
  }
  const payload = {}
  if (num(odds.home)) payload.home = num(odds.home)
  if (num(odds.draw)) payload.draw = num(odds.draw)
  if (num(odds.away)) payload.away = num(odds.away)
  const over = {}, under = {}
  if (num(odds.over15)) over['1.5'] = num(odds.over15)
  if (num(odds.over25)) over['2.5'] = num(odds.over25)
  if (num(odds.over35)) over['3.5'] = num(odds.over35)
  if (num(odds.under25)) under['2.5'] = num(odds.under25)
  if (Object.keys(over).length) payload.over = over
  if (Object.keys(under).length) payload.under = under
  return payload
}

async function submitOdds() {
  loading.value = true
  errorMsg.value = ''
  try {
    const oddsPayload = buildOddsPayload()
    const res = await predict({
      home_en: props.match.home_en,
      away_en: props.match.away_en,
      odds: oddsPayload,
    })
    prediction.value = res.prediction
    recommendations.value = res.recommendations
    hasOdds.value = res.has_odds
  } catch (e) {
    errorMsg.value = e.message
  } finally {
    loading.value = false
  }
}

function clearOdds() {
  Object.keys(odds).forEach((k) => (odds[k] = ''))
  recommendations.value = null
  hasOdds.value = false
}
</script>

<template>
  <div class="match-card">
    <div class="match-meta">
      <span>第 {{ match.week }} 轮</span>
      <span>{{ match.datetime || match.date }}</span>
    </div>

    <div class="match-teams">
      <span>{{ match.home_zh }}</span>
      <span class="vs">VS</span>
      <span>{{ match.away_zh }}</span>
    </div>
    <div class="lambda-line" v-if="prediction">
      预期进球 λ：主 {{ prediction.lambda_home }} · 客 {{ prediction.lambda_away }}
    </div>

    <template v-if="prediction">
      <!-- 胜平负概率条 -->
      <div class="prob-bar">
        <div class="seg home" :style="{ width: barSegs.home + '%' }">
          {{ pct(outcome.home) }}
        </div>
        <div class="seg draw" :style="{ width: barSegs.draw + '%' }">
          {{ pct(outcome.draw) }}
        </div>
        <div class="seg away" :style="{ width: barSegs.away + '%' }">
          {{ pct(outcome.away) }}
        </div>
      </div>
      <div class="prob-legend">
        <span>主胜</span><span>平局</span><span>客胜</span>
      </div>

      <!-- 大小球 / 双方进球 -->
      <div class="sub-grid">
        <div class="kv"><span>大 2.5</span><span>{{ pct(ou['over_2.5']) }}</span></div>
        <div class="kv"><span>小 2.5</span><span>{{ pct(ou['under_2.5']) }}</span></div>
        <div class="kv"><span>大 1.5</span><span>{{ pct(ou['over_1.5']) }}</span></div>
        <div class="kv"><span>大 3.5</span><span>{{ pct(ou['over_3.5']) }}</span></div>
        <div class="kv"><span>双方进球 是</span><span>{{ pct(btts.yes) }}</span></div>
        <div class="kv"><span>双方进球 否</span><span>{{ pct(btts.no) }}</span></div>
      </div>

      <!-- 比分 TOP -->
      <div class="scores">
        <span class="chip" v-for="s in topScores" :key="s.score">
          {{ s.score }} <b>{{ pct(s.prob) }}</b>
        </span>
      </div>
    </template>

    <!-- 赔率输入切换 -->
    <button class="odds-toggle" @click="showOdds = !showOdds">
      {{ showOdds ? '▲ 收起赔率' : '▼ 输入赔率获取投注建议' }}
    </button>

    <div class="odds-panel" v-show="showOdds">
      <div class="odds-row">
        <div class="field">
          <label>主胜</label>
          <input v-model="odds.home" type="number" step="0.01" placeholder="1.80" />
        </div>
        <div class="field">
          <label>平局</label>
          <input v-model="odds.draw" type="number" step="0.01" placeholder="3.50" />
        </div>
        <div class="field">
          <label>客胜</label>
          <input v-model="odds.away" type="number" step="0.01" placeholder="4.20" />
        </div>
      </div>
      <div class="odds-row">
        <div class="field">
          <label>大 1.5</label>
          <input v-model="odds.over15" type="number" step="0.01" placeholder="-" />
        </div>
        <div class="field">
          <label>大 2.5</label>
          <input v-model="odds.over25" type="number" step="0.01" placeholder="2.00" />
        </div>
        <div class="field">
          <label>小 2.5</label>
          <input v-model="odds.under25" type="number" step="0.01" placeholder="1.80" />
        </div>
        <div class="field">
          <label>大 3.5</label>
          <input v-model="odds.over35" type="number" step="0.01" placeholder="-" />
        </div>
      </div>
      <div>
        <button class="btn-primary" :disabled="loading" @click="submitOdds">
          {{ loading ? '计算中…' : '获取投注建议' }}
        </button>
        <button class="btn-clear" @click="clearOdds">清空</button>
      </div>
      <p v-if="errorMsg" class="status-line error" style="padding:10px 0">{{ errorMsg }}</p>
    </div>

    <!-- 投注建议 -->
    <div class="recs" v-if="recommendations !== null">
      <h4>投注建议（EV ≥ 3%）</h4>
      <template v-if="recommendations.length">
        <div class="rec-item" v-for="(r, i) in recommendations" :key="i">
          <span class="mkt">{{ r.market_zh }} @ {{ r.odds.toFixed(2) }}</span>
          <span>模型 {{ pct(r.model_prob) }}</span>
          <span class="tag">EV {{ (r.edge * 100).toFixed(1) }}%</span>
          <span>仓位 {{ (r.stake_fraction * 100).toFixed(2) }}%</span>
        </div>
      </template>
      <p v-else class="rec-empty">
        当前赔率下未发现正期望值（EV≥3%）的投注机会。
      </p>
    </div>
  </div>
</template>
