<script setup>
import { computed, reactive, ref } from 'vue'
import { predictLive } from '../api.js'

const props = defineProps({
  match: { type: Object, required: true },
  engine: { type: String, default: 'dc' },
})

const pct = (v) => (v == null ? '-' : (v * 100).toFixed(1) + '%')

const prediction = computed(() => props.match.prediction || null)
const outcome = computed(() => prediction.value?.outcome || {})
const ou = computed(() => prediction.value?.over_under || {})
const btts = computed(() => prediction.value?.btts || {})
const topScores = computed(() => prediction.value?.top_scores || [])
const stats = computed(() => props.match.stats || {})

// 半全场（HT/FT）：整理成 3x3 网格；下半场已定时部分组合不可能
const SIGN_ZH = { home: '主', draw: '平', away: '客' }
const signs = ['home', 'draw', 'away']
const halfFull = computed(() => prediction.value?.half_full || [])
const hfGrid = computed(() => {
  const map = {}
  halfFull.value.forEach((c) => { map[`${c.ht}/${c.ft}`] = c.prob })
  return map
})
const hfImpossible = computed(() => new Set(prediction.value?.hf_impossible || []))
const htDecided = computed(() => !!prediction.value?.ht_decided)
const htActual = computed(() => prediction.value?.ht_actual || null)
// 高亮概率最大的「可能」组合
const hfBest = computed(() => {
  if (!halfFull.value.length) return null
  const cand = halfFull.value.filter((c) => !hfImpossible.value.has(`${c.ht}/${c.ft}`))
  if (!cand.length) return null
  return cand.reduce((a, b) => (b.prob > a.prob ? b : a))
})
const isImpossible = (ht, ft) => hfImpossible.value.has(`${ht}/${ft}`)

// 比赛阶段（上半场/中场/下半场/完场）：优先用后端 status（API-Football 提供），
// 否则按分钟推断（模拟数据源无 status）。
const phaseLabel = computed(() => {
  if (props.match.finished) return '完场'
  const st = (props.match.status || '').toLowerCase()
  if (st) {
    if (st.includes('halftime') || st === 'ht') return '中场休息'
    if (st.includes('extra')) return '加时赛'
    if (st.includes('penalty')) return '点球大战'
    if (st.includes('first')) return '上半场'
    if (st.includes('second')) return '下半场'
  }
  const m = props.match.minute || 0
  if (m <= 0) return '未开始'
  if (m <= 45) return '上半场'
  return '下半场'
})

// 比赛时钟：进行中且已开赛时显示分钟数，如 18'
const minuteLabel = computed(() => {
  if (props.match.finished) return ''
  const m = props.match.minute || 0
  return m > 0 ? `${m}'` : ''
})

const barSegs = computed(() => {
  const o = outcome.value
  const total = (o.home || 0) + (o.draw || 0) + (o.away || 0) || 1
  return {
    home: ((o.home || 0) / total * 100).toFixed(1),
    draw: ((o.draw || 0) / total * 100).toFixed(1),
    away: ((o.away || 0) / total * 100).toFixed(1),
  }
})

// ---- 实时赔率输入 → 投注建议 ----
const odds = reactive({
  home: '', draw: '', away: '',
  over25: '', under25: '', over15: '', over35: '',
})
// 半全场赔率（9 格）；下半场已不可能的组合会被禁用
const htftOdds = reactive({
  'home/home': '', 'home/draw': '', 'home/away': '',
  'draw/home': '', 'draw/draw': '', 'draw/away': '',
  'away/home': '', 'away/draw': '', 'away/away': '',
})
const showOuOdds = ref(false)
const showHtftOdds = ref(false)
const loading = ref(false)
const errorMsg = ref('')
const recommendations = ref(null)   // null=未提交, []=提交但无建议

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
    // 已不可能的组合（下半场已定）直接跳过
    if (isImpossible(...k.split('/'))) continue
    const o = num(htftOdds[k])
    if (o) htft[k] = o
  }
  if (Object.keys(htft).length) payload.htft = htft
  return payload
}

async function submitOdds() {
  loading.value = true
  errorMsg.value = ''
  try {
    const res = await predictLive({
      match_id: props.match.match_id,
      engine: props.engine,
      odds: buildOddsPayload(),
    })
    recommendations.value = res.recommendations
  } catch (e) {
    errorMsg.value = e.message
  } finally {
    loading.value = false
  }
}

function clearOdds() {
  Object.keys(odds).forEach((k) => (odds[k] = ''))
  Object.keys(htftOdds).forEach((k) => (htftOdds[k] = ''))
  recommendations.value = null
  errorMsg.value = ''
}
</script>

<template>
  <div class="match-card live-card">
    <div class="match-meta">
      <span class="live-badge" :class="{ finished: match.finished }">
        <span v-if="!match.finished" class="live-dot"></span>
        {{ match.finished ? '完场' : '进行中' }}
      </span>
      <span class="live-phase">
        <span class="phase-tag">{{ phaseLabel }}</span>
        <span v-if="minuteLabel" class="live-minute">{{ minuteLabel }}</span>
      </span>
    </div>

    <!-- 比分板 -->
    <div class="live-scoreboard">
      <span class="team home">{{ match.home_zh }}</span>
      <span class="score">{{ match.score.home }} - {{ match.score.away }}</span>
      <span class="team away">{{ match.away_zh }}</span>
    </div>

    <!-- 场面统计 -->
    <div class="live-stats">
      <div class="stat-row">
        <span class="sv">{{ stats.shots?.home ?? 0 }}</span>
        <span class="sl">射门</span>
        <span class="sv">{{ stats.shots?.away ?? 0 }}</span>
      </div>
      <div class="stat-row">
        <span class="sv">{{ stats.sot?.home ?? 0 }}</span>
        <span class="sl">射正</span>
        <span class="sv">{{ stats.sot?.away ?? 0 }}</span>
      </div>
      <div class="stat-row">
        <span class="sv">{{ stats.corners?.home ?? 0 }}</span>
        <span class="sl">角球</span>
        <span class="sv">{{ stats.corners?.away ?? 0 }}</span>
      </div>
      <div class="stat-row" v-if="(stats.red?.home || stats.red?.away)">
        <span class="sv">{{ stats.red?.home ?? 0 }}</span>
        <span class="sl">红牌</span>
        <span class="sv">{{ stats.red?.away ?? 0 }}</span>
      </div>
      <div class="stat-row">
        <span class="sv">{{ stats.possession_home ?? 50 }}%</span>
        <span class="sl">控球</span>
        <span class="sv">{{ (100 - (stats.possession_home ?? 50)).toFixed(1) }}%</span>
      </div>
    </div>

    <template v-if="prediction">
      <div class="live-pred-title">实时预测（随比赛进程更新）</div>
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

      <!-- 比分 TOP（在当前比分基础上的最终比分预测） -->
      <div class="scores">
        <span class="chip" v-for="s in topScores" :key="s.score">
          {{ s.score }} <b>{{ pct(s.prob) }}</b>
        </span>
      </div>

      <!-- 半全场 (HT/FT) 实时预测 -->
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
              <th :class="{ 'hf-row-dim': htDecided && htActual !== ht }">半{{ SIGN_ZH[ht] }}</th>
              <td v-for="ft in signs" :key="ft"
                  :class="{
                    hi: hfBest && hfBest.ht === ht && hfBest.ft === ft,
                    'hf-x': isImpossible(ht, ft),
                  }">
                <template v-if="isImpossible(ht, ft)">—</template>
                <template v-else>{{ pct(hfGrid[ht + '/' + ft]) }}</template>
              </td>
            </tr>
          </tbody>
        </table>
        <p class="hf-note">
          行=半场结果，列=全场结果；高亮为最可能组合。
          <template v-if="htDecided">半场已定（半{{ SIGN_ZH[htActual] }}），灰色“—”为已不可能的组合。</template>
        </p>
      </div>

      <!-- 实时赔率输入 → 投注建议 -->
      <div class="odds-panel" v-if="!match.finished">
        <div class="odds-hint">输入当前盘口赔率，获取基于实时状态的 EV 投注建议</div>
        <div class="odds-row">
          <div class="field">
            <label>主胜</label>
            <input v-model="odds.home" type="number" step="0.01" placeholder="2.10" />
          </div>
          <div class="field">
            <label>平局</label>
            <input v-model="odds.draw" type="number" step="0.01" placeholder="3.20" />
          </div>
          <div class="field">
            <label>客胜</label>
            <input v-model="odds.away" type="number" step="0.01" placeholder="3.60" />
          </div>
        </div>

        <!-- 大小球赔率（可选） -->
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
            <input v-model="odds.over25" type="number" step="0.01" placeholder="-" />
          </div>
          <div class="field">
            <label>小 2.5</label>
            <input v-model="odds.under25" type="number" step="0.01" placeholder="-" />
          </div>
          <div class="field">
            <label>大 3.5</label>
            <input v-model="odds.over35" type="number" step="0.01" placeholder="-" />
          </div>
        </div>

        <!-- 半全场赔率（可选，9 格；不可能组合禁用） -->
        <button class="htft-odds-toggle" @click="showHtftOdds = !showHtftOdds">
          {{ showHtftOdds ? '▲ 收起半全场赔率' : '＋ 半全场赔率（可选）' }}
        </button>
        <div class="htft-odds-grid" v-show="showHtftOdds">
          <div class="htft-odds-cell" v-for="ht in signs" :key="ht">
            <div class="htft-odds-col">
              <div class="field" v-for="ft in signs" :key="ft">
                <label>{{ SIGN_ZH[ht] }}/{{ SIGN_ZH[ft] }}</label>
                <input
                  v-model="htftOdds[ht + '/' + ft]"
                  type="number" step="0.01"
                  :placeholder="isImpossible(ht, ft) ? '—' : '-'"
                  :disabled="isImpossible(ht, ft)" />
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
    </template>
    <p v-else class="rec-empty">该场暂无预测数据。</p>
  </div>
</template>

<style scoped>
.live-card {
  border-top: 3px solid #e11d48;
}
.live-badge {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  color: #e11d48;
  font-weight: 700;
}
.live-badge.finished {
  color: #6b7280;
}
.live-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #e11d48;
  animation: live-pulse 1.2s ease-in-out infinite;
}
@keyframes live-pulse {
  0%, 100% { opacity: 1; transform: scale(1); }
  50% { opacity: 0.35; transform: scale(0.7); }
}
.live-phase {
  display: inline-flex;
  align-items: center;
  gap: 8px;
}
.phase-tag {
  font-size: 12px;
  font-weight: 700;
  color: #a5f3fc;
  background: rgba(34, 211, 238, 0.12);
  border: 1px solid rgba(34, 211, 238, 0.35);
  border-radius: 999px;
  padding: 2px 10px;
}
.live-minute {
  font-variant-numeric: tabular-nums;
  font-weight: 700;
  color: #e5e7eb;
}
.live-scoreboard {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  margin: 12px 0 14px;
}
.live-scoreboard .team {
  flex: 1;
  font-size: 15px;
  font-weight: 600;
}
.live-scoreboard .team.home { text-align: right; }
.live-scoreboard .team.away { text-align: left; }
.live-scoreboard .score {
  font-size: 26px;
  font-weight: 800;
  font-variant-numeric: tabular-nums;
  padding: 2px 14px;
  background: #111827;
  color: #fff;
  border-radius: 8px;
}
.live-stats {
  display: flex;
  flex-direction: column;
  gap: 4px;
  margin-bottom: 12px;
  padding: 8px 10px;
  background: rgba(255, 255, 255, 0.05);
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 8px;
}
.stat-row {
  display: grid;
  grid-template-columns: 1fr auto 1fr;
  align-items: center;
  font-size: 13px;
}
.stat-row .sv {
  font-variant-numeric: tabular-nums;
  font-weight: 600;
  color: #e5e7eb;
}
.stat-row .sv:first-child { text-align: right; }
.stat-row .sv:last-child { text-align: left; }
.stat-row .sl {
  padding: 0 14px;
  color: #9ca3af;
  white-space: nowrap;
}
.live-pred-title {
  font-size: 13px;
  font-weight: 700;
  color: #374151;
  margin-bottom: 8px;
}
/* 半全场：不可能组合 + 已定半场行置灰 */
.hf-table td.hf-x {
  color: #4b5563;
  background: rgba(255, 255, 255, 0.02);
}
.hf-table th.hf-row-dim {
  color: #4b5563;
}
/* 实时赔率输入区提示 */
.odds-hint {
  font-size: 12px;
  color: #9ca3af;
  margin-bottom: 8px;
}
/* 禁用的半全场赔率输入（下半场已不可能的组合） */
.htft-odds-col .field input:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

</style>
