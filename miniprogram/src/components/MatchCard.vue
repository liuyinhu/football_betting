<script setup>
import { ref, computed, watch } from 'vue'

const props = defineProps({
  match: { type: Object, required: true },
  engine: { type: String, default: 'dc' },
})

// 分析数据来自列表接口；引擎切换时同步更新
const prediction = ref(props.match.prediction)
watch(() => props.match.prediction, (p) => {
  prediction.value = p
})

const pct = (v) => (v == null ? '-' : (v * 100).toFixed(1) + '%')

const outcome = computed(() => prediction.value?.outcome || {})
const topScores = computed(() => prediction.value?.top_scores || [])

// 主客胜率条的三段宽度
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
  <view class="match-card">
    <view class="match-meta">
      <text>第 {{ match.week }} 轮</text>
      <text>{{ match.datetime || match.date }}</text>
    </view>

    <view class="match-teams">
      <text>{{ match.home_zh }}</text>
      <text class="vs">VS</text>
      <text>{{ match.away_zh }}</text>
    </view>

    <template v-if="prediction">
      <!-- 胜平负分析条 -->
      <view class="prob-bar">
        <view class="seg home" :style="{ width: barSegs.home + '%' }">{{ pct(outcome.home) }}</view>
        <view class="seg draw" :style="{ width: barSegs.draw + '%' }">{{ pct(outcome.draw) }}</view>
        <view class="seg away" :style="{ width: barSegs.away + '%' }">{{ pct(outcome.away) }}</view>
      </view>
      <view class="prob-legend">
        <text>主胜</text><text>平局</text><text>客胜</text>
      </view>

      <!-- 比分分析 TOP -->
      <view class="section-label">最可能比分</view>
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
.match-meta {
  display: flex;
  justify-content: space-between;
  color: var(--muted);
  font-size: 24rpx;
  margin-bottom: 20rpx;
}
.match-teams {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 24rpx;
  font-size: 36rpx;
  font-weight: 600;
  margin-bottom: 24rpx;
}
.match-teams .vs { color: var(--muted); font-size: 26rpx; font-weight: 400; }

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

.section-label {
  font-size: 24rpx;
  color: var(--muted);
  font-weight: 600;
  margin: 8rpx 0 12rpx;
}
.scores {
  display: flex;
  flex-wrap: wrap;
  gap: 12rpx;
}
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
