<script setup>
import { computed } from 'vue'

const props = defineProps({
  match: { type: Object, required: true },
  engine: { type: String, default: 'dc' },
})

const pct = (v) => (v == null ? '-' : (v * 100).toFixed(1) + '%')

const prediction = computed(() => props.match.prediction || null)
const outcome = computed(() => prediction.value?.outcome || {})
const topScores = computed(() => prediction.value?.top_scores || [])
const stats = computed(() => props.match.stats || {})

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
</script>

<template>
  <view class="match-card live-card">
    <view class="match-meta">
      <text class="live-badge" :class="{ finished: match.finished }">
        <text v-if="!match.finished" class="live-dot"></text>
        {{ match.finished ? '完场' : '进行中' }}
      </text>
      <view class="live-phase">
        <text class="phase-tag">{{ phaseLabel }}</text>
        <text v-if="minuteLabel" class="live-minute">{{ minuteLabel }}</text>
      </view>
    </view>

    <!-- 比分板 -->
    <view class="live-scoreboard">
      <text class="team home">{{ match.home_zh }}</text>
      <text class="score">{{ match.score.home }} - {{ match.score.away }}</text>
      <text class="team away">{{ match.away_zh }}</text>
    </view>

    <!-- 场面统计 -->
    <view class="live-stats">
      <view class="stat-row">
        <text class="sv">{{ stats.shots?.home ?? 0 }}</text>
        <text class="sl">射门</text>
        <text class="sv">{{ stats.shots?.away ?? 0 }}</text>
      </view>
      <view class="stat-row">
        <text class="sv">{{ stats.sot?.home ?? 0 }}</text>
        <text class="sl">射正</text>
        <text class="sv">{{ stats.sot?.away ?? 0 }}</text>
      </view>
      <view class="stat-row">
        <text class="sv">{{ stats.corners?.home ?? 0 }}</text>
        <text class="sl">角球</text>
        <text class="sv">{{ stats.corners?.away ?? 0 }}</text>
      </view>
      <view class="stat-row" v-if="(stats.red?.home || stats.red?.away)">
        <text class="sv">{{ stats.red?.home ?? 0 }}</text>
        <text class="sl">红牌</text>
        <text class="sv">{{ stats.red?.away ?? 0 }}</text>
      </view>
      <view class="stat-row">
        <text class="sv">{{ stats.possession_home ?? 50 }}%</text>
        <text class="sl">控球</text>
        <text class="sv">{{ (100 - (stats.possession_home ?? 50)).toFixed(1) }}%</text>
      </view>
    </view>

    <template v-if="prediction">
      <view class="live-pred-title">实时胜率分析（随比赛进程更新）</view>
      <!-- 胜平负分析条 -->
      <view class="prob-bar">
        <view class="seg home" :style="{ width: barSegs.home + '%' }">{{ pct(outcome.home) }}</view>
        <view class="seg draw" :style="{ width: barSegs.draw + '%' }">{{ pct(outcome.draw) }}</view>
        <view class="seg away" :style="{ width: barSegs.away + '%' }">{{ pct(outcome.away) }}</view>
      </view>
      <view class="prob-legend">
        <text>主胜</text><text>平局</text><text>客胜</text>
      </view>

      <!-- 最终比分分析 TOP -->
      <view class="section-label">最终比分分析</view>
      <view class="scores">
        <text class="chip" v-for="s in topScores" :key="s.score">
          {{ s.score }} <text class="chip-b">{{ pct(s.prob) }}</text>
        </text>
      </view>
    </template>
    <view v-else class="rec-empty">该场暂无分析数据。</view>
  </view>
</template>

<style scoped>
.match-card {
  background: var(--card);
  border: 1rpx solid var(--line);
  border-radius: 28rpx;
  padding: 32rpx 36rpx;
  margin-bottom: 32rpx;
}
.live-card { border-top: 6rpx solid #e11d48; }
.match-meta {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-size: 24rpx;
  margin-bottom: 16rpx;
}
.live-badge {
  display: inline-flex;
  align-items: center;
  gap: 10rpx;
  color: #e11d48;
  font-weight: 700;
}
.live-badge.finished { color: #6b7280; }
.live-dot {
  width: 16rpx;
  height: 16rpx;
  border-radius: 50%;
  background: #e11d48;
  animation: live-pulse 1.2s ease-in-out infinite;
}
@keyframes live-pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.35; }
}
.live-phase { display: inline-flex; align-items: center; gap: 16rpx; }
.phase-tag {
  font-size: 22rpx;
  font-weight: 700;
  color: #a5f3fc;
  background: rgba(34, 211, 238, 0.12);
  border: 1rpx solid rgba(34, 211, 238, 0.35);
  border-radius: 999rpx;
  padding: 4rpx 20rpx;
}
.live-minute { font-weight: 700; color: #e5e7eb; }
.live-scoreboard {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 20rpx;
  margin: 24rpx 0 28rpx;
}
.live-scoreboard .team { flex: 1; font-size: 30rpx; font-weight: 600; }
.live-scoreboard .team.home { text-align: right; }
.live-scoreboard .team.away { text-align: left; }
.live-scoreboard .score {
  font-size: 52rpx;
  font-weight: 800;
  padding: 4rpx 28rpx;
  background: #111827;
  color: #fff;
  border-radius: 16rpx;
}
.live-stats {
  display: flex;
  flex-direction: column;
  gap: 8rpx;
  margin-bottom: 24rpx;
  padding: 16rpx 20rpx;
  background: rgba(255, 255, 255, 0.05);
  border: 1rpx solid rgba(255, 255, 255, 0.08);
  border-radius: 16rpx;
}
.stat-row {
  display: grid;
  grid-template-columns: 1fr auto 1fr;
  align-items: center;
  font-size: 26rpx;
}
.stat-row .sv { font-weight: 600; color: #e5e7eb; }
.stat-row .sv:first-child { text-align: right; }
.stat-row .sv:last-child { text-align: left; }
.stat-row .sl { padding: 0 28rpx; color: #9ca3af; white-space: nowrap; }
.live-pred-title { font-size: 26rpx; font-weight: 700; color: #9ca3af; margin-bottom: 16rpx; }

/* 胜平负分析条 */
.prob-bar {
  display: flex;
  height: 60rpx;
  border-radius: 12rpx;
  overflow: hidden;
  margin-bottom: 12rpx;
  font-size: 24rpx;
}
.prob-bar .seg {
  display: flex;
  align-items: center;
  justify-content: center;
  color: #0b0e16;
  font-weight: 600;
  min-width: 52rpx;
}
.seg.home { background: var(--home); }
.seg.draw { background: var(--draw); }
.seg.away { background: var(--away); }
.prob-legend {
  display: flex;
  justify-content: space-between;
  font-size: 24rpx;
  color: var(--muted);
  margin-bottom: 24rpx;
}
.section-label { font-size: 24rpx; color: var(--muted); font-weight: 600; margin: 8rpx 0 12rpx; }
.scores { display: flex; flex-wrap: wrap; gap: 12rpx; }
.scores .chip {
  background: var(--card2);
  border: 1rpx solid var(--line);
  border-radius: 40rpx;
  padding: 6rpx 20rpx;
  font-size: 24rpx;
}
.scores .chip-b { color: var(--gold); font-weight: 600; }

.rec-empty { color: var(--muted); font-size: 26rpx; padding: 16rpx 0; }
</style>
