<script setup>
import { ref, reactive, computed, watch } from 'vue'
import { predict } from '../api.js'

const props = defineProps({
  match: { type: Object, required: true },
  engine: { type: String, default: 'dc' },
})

// 概率初始值来自列表接口（无赔率），提交赔率后用返回值覆盖
const prediction = ref(props.match.prediction)
const loading = ref(false)
const errorMsg = ref('')
const recommendations = ref(null)   // null=未提交, []=提交但无建议
const hasOdds = ref(false)

// 切换引擎后 App 会重新拉取赛程，match.prediction 随之更新；
// 因组件实例被复用(key=match_id 不变)，需手动同步概率并清空旧的投注建议。
watch(() => props.match.prediction, (p) => {
  prediction.value = p
  recommendations.value = null
  hasOdds.value = false
})

// 赔率输入模型
const odds = reactive({
  home: '', draw: '', away: '',
  over25: '', under25: '',
  over15: '', over35: '',
})

// 半全场赔率输入（9 格），key = "半场/全场"
const htftOdds = reactive({
  'home/home': '', 'home/draw': '', 'home/away': '',
  'draw/home': '', 'draw/draw': '', 'draw/away': '',
  'away/home': '', 'away/draw': '', 'away/away': '',
})
const showHtftOdds = ref(false)

// 比分（正确比分）赔率输入，key = "主-客"，按主胜/平局/客胜分组
const CS_HOME = ['1-0', '2-0', '2-1', '3-0', '3-1', '3-2']
const CS_DRAW = ['0-0', '1-1', '2-2', '3-3']
const CS_AWAY = ['0-1', '0-2', '1-2', '0-3', '1-3', '2-3']
const CS_SCORES = [...CS_HOME, ...CS_DRAW, ...CS_AWAY]
const csOdds = reactive(Object.fromEntries(CS_SCORES.map((s) => [s, ''])))
const showCsOdds = ref(false)

// 大小球赔率默认隐藏，可选填
const showOuOdds = ref(false)

const pct = (v) => (v == null ? '-' : (v * 100).toFixed(1) + '%')

const outcome = computed(() => prediction.value?.outcome || {})
const ou = computed(() => prediction.value?.over_under || {})
const btts = computed(() => prediction.value?.btts || {})
const topScores = computed(() => prediction.value?.top_scores || [])

// 半全场：整理成 3x3 网格 + 找出概率最高的一格
const SIGN_ZH = { home: '主', draw: '平', away: '客' }
const halfFull = computed(() => prediction.value?.half_full || [])
const hfGrid = computed(() => {
  const map = {}
  halfFull.value.forEach((c) => { map[`${c.ht}/${c.ft}`] = c.prob })
  return map
})
const hfBest = computed(() => {
  if (!halfFull.value.length) return null
  return halfFull.value.reduce((a, b) => (b.prob > a.prob ? b : a))
})
const signs = ['home', 'draw', 'away']

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
  const htft = {}
  for (const k in htftOdds) {
    const o = num(htftOdds[k])
    if (o) htft[k] = o
  }
  if (Object.keys(htft).length) payload.htft = htft
  const exact = {}
  for (const s in csOdds) {
    const o = num(csOdds[s])
    if (o) exact[s] = o
  }
  if (Object.keys(exact).length) payload.exact = exact
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
      engine: props.engine,
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
  Object.keys(htftOdds).forEach((k) => (htftOdds[k] = ''))
  Object.keys(csOdds).forEach((k) => (csOdds[k] = ''))
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

      <!-- 半全场 (HT/FT) -->
      <div class="hf-panel" v-if="halfFull.length">
        <table class="hf-table">
          <thead>
            <tr>
              <th>半场＼全场</th>
              <th>全主</th><th>全平</th><th>全客</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="ht in signs" :key="ht">
              <th>半{{ SIGN_ZH[ht] }}</th>
              <td v-for="ft in signs" :key="ft"
                  :class="{ hi: hfBest && hfBest.ht === ht && hfBest.ft === ft }">
                {{ pct(hfGrid[ht + '/' + ft]) }}
              </td>
            </tr>
          </tbody>
        </table>
        <p class="hf-note">行=半场结果，列=全场结果；高亮为最可能组合。</p>
      </div>
    </template>

    <!-- 赔率输入 -->
    <div class="odds-panel">
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
      <!-- 大小球赔率（可选，默认隐藏） -->
      <button class="htft-odds-toggle" @click="showOuOdds = !showOuOdds">
        {{ showOuOdds ? '▲ 收起大小球赔率' : '＋ 大小球赔率（可选）' }}
      </button>
      <div class="odds-row" v-show="showOuOdds">
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

      <!-- 半全场赔率（可选，9 格） -->
      <button class="htft-odds-toggle" @click="showHtftOdds = !showHtftOdds">
        {{ showHtftOdds ? '▲ 收起半全场赔率' : '＋ 半全场赔率（可选）' }}
      </button>
      <div class="htft-odds-grid" v-show="showHtftOdds">
        <div class="htft-odds-cell" v-for="ht in signs" :key="ht">
          <div class="htft-odds-col">
            <div class="field" v-for="ft in signs" :key="ft">
              <label>{{ SIGN_ZH[ht] }}/{{ SIGN_ZH[ft] }}</label>
              <input v-model="htftOdds[ht + '/' + ft]" type="number" step="0.01" placeholder="-" />
            </div>
          </div>
        </div>
      </div>

      <!-- 比分（正确比分）赔率（可选） -->
      <button class="htft-odds-toggle" @click="showCsOdds = !showCsOdds">
        {{ showCsOdds ? '▲ 收起比分赔率' : '＋ 比分赔率（可选）' }}
      </button>
      <div class="cs-odds" v-show="showCsOdds">
        <div class="cs-group">
          <div class="cs-group-title">主胜比分</div>
          <div class="cs-grid">
            <div class="field" v-for="s in CS_HOME" :key="s">
              <label>{{ s }}</label>
              <input v-model="csOdds[s]" type="number" step="0.01" placeholder="-" />
            </div>
          </div>
        </div>
        <div class="cs-group">
          <div class="cs-group-title">平局比分</div>
          <div class="cs-grid">
            <div class="field" v-for="s in CS_DRAW" :key="s">
              <label>{{ s }}</label>
              <input v-model="csOdds[s]" type="number" step="0.01" placeholder="-" />
            </div>
          </div>
        </div>
        <div class="cs-group">
          <div class="cs-group-title">客胜比分</div>
          <div class="cs-grid">
            <div class="field" v-for="s in CS_AWAY" :key="s">
              <label>{{ s }}</label>
              <input v-model="csOdds[s]" type="number" step="0.01" placeholder="-" />
            </div>
          </div>
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
