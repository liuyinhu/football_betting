<script setup>
// 分析引擎切换条（dc = Dixon-Coles, nn = 神经网络）
defineProps({
  engines: { type: Array, default: () => [] },
  engine: { type: String, default: 'dc' },
})
const emit = defineEmits(['switch'])
</script>

<template>
  <view class="engine-bar">
    <text class="engine-label">分析引擎</text>
    <view class="engine-options">
      <view
        v-for="e in engines"
        :key="e.id"
        class="engine-btn"
        :class="{ active: engine === e.id, disabled: e.available === false }"
        @click="e.available !== false && emit('switch', e.id)"
      >
        {{ e.name }}
        <text v-if="e.available === false" class="engine-na">未训练</text>
      </view>
    </view>
  </view>
</template>

<style scoped>
.engine-bar {
  display: flex;
  align-items: center;
  gap: 20rpx;
  margin-bottom: 24rpx;
  flex-wrap: wrap;
}
.engine-label { font-size: 24rpx; color: #9ca3af; font-weight: 600; }
.engine-options { display: flex; gap: 12rpx; flex-wrap: wrap; }
.engine-btn {
  padding: 10rpx 26rpx;
  border: 1rpx solid #374151;
  color: #d1d5db;
  border-radius: 999rpx;
  font-size: 24rpx;
  font-weight: 600;
  display: inline-flex;
  align-items: center;
  gap: 10rpx;
}
.engine-btn.active {
  background: #22d3ee;
  border-color: #22d3ee;
  color: #0b1120;
}
.engine-btn.disabled { opacity: 0.45; }
.engine-na { font-size: 20rpx; font-weight: 500; color: #f59e0b; }
</style>
