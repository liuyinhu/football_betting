<script setup>
import { ref, computed, watch } from 'vue'

const props = defineProps({
  match: { type: Object, required: true },
  engine: { type: String, default: 'dc' },
})

// 概率数据来自列表接口；引擎切换时同步更新
const prediction = ref(props.match.prediction)
watch(() => props.match.prediction, (p) => {
  prediction.value = p
})

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
    <view class="lambda-line" v-if="prediction">
      模型预期进球 λ：主 {{ prediction.lambda_home }} · 客 {{ prediction.lambda_away }}
    </view>

    <template v-if="prediction">
      <!-- 胜平负概率条 -->
      <view class="prob-bar">
        <view class="seg home" :style="{ width: barSegs.home + '%' }">{{ pct(outcome.home) }}</view>
        <view class="seg draw" :style="{ width: barSegs.draw + '%' }">{{ pct(outcome.draw) }}</view>
        <view class="seg away" :style="{ width: barSegs.away + '%' }">{{ pct(outcome.away) }}</view>
      </view>
      <view class="prob-legend">
        <text>主胜</text><text>平局</text><text>客胜</text>
      </view>

      <!-- 大小球 / 双方进球 概率 -->
      <view class="sub-grid">
        <view class="kv"><text>大 2.5</text><text class="v">{{ pct(ou['over_2.5']) }}</text></view>
        <view class="kv"><text>小 2.5</text><text class="v">{{ pct(ou['under_2.5']) }}</text></view>
        <view class="kv"><text>大 1.5</text><text class="v">{{ pct(ou['over_1.5']) }}</text></view>
        <view class="kv"><text>大 3.5</text><text class="v">{{ pct(ou['over_3.5']) }}</text></view>
        <view class="kv"><text>双方进球 是</text><text class="v">{{ pct(btts.yes) }}</text></view>
        <view class="kv"><text>双方进球 否</text><text class="v">{{ pct(btts.no) }}</text></view>
      </view>

      <!-- 最可能比分 TOP -->
      <view class="section-label">最可能比分</view>
      <view class="scores">
        <text class="chip" v-for="s in topScores" :key="s.score">
          {{ s.score }} <text class="chip-b">{{ pct(s.prob) }}</text>
        </text>
      </view>

      <!-- 半全场 (HT/FT) 概率 -->
      <view class="hf-panel" v-if="halfFull.length">
        <view class="section-label">半全场概率</view>
        <view class="hf-row hf-head">
          <text class="hf-cell hf-th">半场＼全场</text>
          <text class="hf-cell hf-th">全主</text>
          <text class="hf-cell hf-th">全平</text>
          <text class="hf-cell hf-th">全客</text>
        </view>
        <view class="hf-row" v-for="ht in signs" :key="ht">
          <text class="hf-cell hf-th">半{{ SIGN_ZH[ht] }}</text>
          <text class="hf-cell" v-for="ft in signs" :key="ft"
                :class="{ hi: hfBest && hfBest.ht === ht && hfBest.ft === ft }">
            {{ pct(hfGrid[ht + '/' + ft]) }}
          </text>
        </view>
        <view class="hf-note">行=半场结果，列=全场结果；高亮为模型判断最可能的组合。</view>
      </view>
    </template>
    <view v-else class="rec-empty">该场暂无预测数据。</view>
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
  margin-bottom: 8rpx;
}
.match-teams .vs { color: var(--muted); font-size: 26rpx; font-weight: 400; }
.lambda-line {
  text-align: center;
  color: var(--muted);
  font-size: 24rpx;
  margin-bottom: 28rpx;
}

/* 胜平负概率条 */
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

.sub-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 16rpx 36rpx;
  font-size: 26rpx;
  margin-bottom: 24rpx;
}
.sub-grid .kv { display: flex; justify-content: space-between; }
.sub-grid .kv .v { color: var(--home); font-weight: 600; }

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
  margin-bottom: 20rpx;
}
.scores .chip {
  background: var(--card2);
  border: 1rpx solid var(--line);
  border-radius: 40rpx;
  padding: 6rpx 20rpx;
  font-size: 24rpx;
}
.scores .chip-b { color: var(--gold); font-weight: 600; }

/* 半全场 HT/FT 网格 */
.hf-panel { margin-top: 8rpx; }
.hf-row { display: flex; }
.hf-cell {
  flex: 1;
  border: 1rpx solid var(--line);
  padding: 10rpx 6rpx;
  font-size: 24rpx;
  text-align: center;
  color: var(--text);
}
.hf-th { color: var(--muted); font-weight: 500; }
.hf-cell.hi {
  background: rgba(245, 196, 81, 0.18);
  color: var(--gold);
  font-weight: 700;
}
.hf-note { color: var(--muted); font-size: 22rpx; margin-top: 12rpx; }
.rec-empty { color: var(--muted); font-size: 26rpx; padding: 16rpx 0; }
</style>
