<script setup>
import { ref, onMounted } from 'vue'
import { fetchMatches } from './api.js'
import MatchCard from './components/MatchCard.vue'

const matches = ref([])
const loading = ref(false)
const errorMsg = ref('')
const limit = ref(10)

async function load() {
  loading.value = true
  errorMsg.value = ''
  try {
    const res = await fetchMatches(limit.value)
    matches.value = res.matches
  } catch (e) {
    errorMsg.value = e.message
  } finally {
    loading.value = false
  }
}

onMounted(load)
</script>

<template>
  <div class="container">
    <header class="app-header">
      <h1>⚽ 中超赛前预测与投注建议</h1>
      <p>接下来的中超赛程，基于 Dixon-Coles 强度模型给出预测概率；输入赔率即可获得正期望值投注建议。</p>
    </header>

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
      <MatchCard v-for="m in matches" :key="m.match_id" :match="m" />
    </div>

    <footer class="app-footer">
      数据来源：中国足协官方 API · 模型：时变泊松 + Dixon-Coles<br />
      ⚠️ 本项目仅供学习研究，模型不保证盈利，请勿用于真实赌博。
    </footer>
  </div>
</template>
