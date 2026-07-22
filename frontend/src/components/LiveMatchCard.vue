<script setup>
import { computed } from 'vue'

const props = defineProps({
  match: { type: Object, required: true },
})

const pct = (v) => (v == null ? '-' : (v * 100).toFixed(1) + '%')

const prediction = computed(() => props.match.prediction || null)
const outcome = computed(() => prediction.value?.outcome || {})
const ou = computed(() => prediction.value?.over_under || {})
const btts = computed(() => prediction.value?.btts || {})
const topScores = computed(() => prediction.value?.top_scores || [])
const stats = computed(() => props.match.stats || {})

const minuteLabel = computed(() => {
  if (props.match.finished) return '完场'
  return `${props.match.minute}'`
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
</script>

<template>
  <div class="match-card live-card">
    <div class="match-meta">
      <span class="live-badge" :class="{ finished: match.finished }">
        <span v-if="!match.finished" class="live-dot"></span>
        {{ match.finished ? '完场' : '进行中' }}
      </span>
      <span class="live-minute">{{ minuteLabel }}</span>
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
.live-minute {
  font-variant-numeric: tabular-nums;
  font-weight: 700;
  color: #111827;
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
  background: #f9fafb;
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
  color: #111827;
}
.stat-row .sv:first-child { text-align: right; }
.stat-row .sv:last-child { text-align: left; }
.stat-row .sl {
  padding: 0 14px;
  color: #6b7280;
  white-space: nowrap;
}
.live-pred-title {
  font-size: 13px;
  font-weight: 700;
  color: #374151;
  margin-bottom: 8px;
}
</style>
