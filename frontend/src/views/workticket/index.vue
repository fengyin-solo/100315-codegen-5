<template>
  <section class="page" data-module="workticket">
    <header class="page-head">
      <div>
        <h2>作业票管理</h2>
        <p class="page-desc">作业票只能引用准入名单内的外委队伍；准入审核结论会同步到待办清单，处置后办结。</p>
      </div>
      <div class="page-actions">
        <button class="btn primary" type="button" @click="showCreate = !showCreate">开具作业票</button>
        <button class="btn" type="button" @click="exportRows">导出作业票清单</button>
      </div>
    </header>

    <div class="stat-row">
      <article v-for="item in stats" :key="item.label" class="stat-card">
        <span class="stat-label">{{ item.label }}</span>
        <strong class="stat-value">{{ item.value }}</strong>
      </article>
    </div>

    <div class="panel">
      <h3 class="panel-title">准入结论待办清单</h3>
      <table class="data-table">
        <thead>
          <tr><th>时间</th><th>队伍名称</th><th>结论</th><th>内容</th><th>操作</th></tr>
        </thead>
        <tbody>
          <tr v-for="todo in todos" :key="String(todo.id)">
            <td>{{ todo['时间'] }}</td>
            <td>{{ todo['队伍名称'] }}</td>
            <td>
              <span class="status-pill" :class="todo['结论'] === '通过' ? 'ok' : 'bad'">{{ todo['结论'] }}</span>
            </td>
            <td>{{ todo['内容'] }}</td>
            <td><button class="link" type="button" @click="closeTodo(todo)">办结</button></td>
          </tr>
          <tr v-if="!todos.length">
            <td colspan="5" class="empty-state">暂无待办，准入结论出现后会自动同步到这里</td>
          </tr>
        </tbody>
      </table>
    </div>

    <form v-if="showCreate" class="panel" @submit.prevent="submitCreate">
      <h3 class="panel-title">开具作业票</h3>
      <div class="form-grid">
        <label class="filter-item">
          <span>作业票编号</span>
          <input v-model="createForm['作业票编号']" placeholder="如 ZYP-2026-0046" />
        </label>
        <label class="filter-item">
          <span>施工队伍（统一社会信用代码）</span>
          <select v-model="createForm['统一社会信用代码']">
            <option value="">请选择</option>
            <option v-for="team in teams" :key="team['统一社会信用代码']" :value="team['统一社会信用代码']">
              {{ team['队伍名称'] }}（{{ team['统一社会信用代码'] }}）
            </option>
          </select>
        </label>
        <label class="filter-item">
          <span>作业地点</span>
          <input v-model="createForm['作业地点']" placeholder="作业地点" />
        </label>
        <label class="filter-item">
          <span>作业内容</span>
          <input v-model="createForm['作业内容']" placeholder="作业内容" />
        </label>
        <label class="filter-item">
          <span>计划日期</span>
          <input v-model="createForm['计划日期']" type="date" />
        </label>
      </div>
      <p class="panel-hint">下拉只列出已建档队伍；提交时仍会复核准入状态，名单外或已退出的队伍会被当场拒绝。</p>
      <div class="panel-actions">
        <button class="btn primary" type="submit">提交开票</button>
        <button class="btn ghost" type="button" @click="showCreate = false">取消</button>
      </div>
    </form>

    <form class="filter-bar" @submit.prevent="reload">
      <label class="filter-item">
        <span>作业票编号</span>
        <input v-model="filters.keyword" placeholder="按作业票编号检索" />
      </label>
      <label class="filter-item">
        <span>作业票状态</span>
        <select v-model="filters.status">
          <option value="">全部</option>
          <option v-for="item in statuses" :key="item" :value="item">{{ item }}</option>
        </select>
      </label>
      <button class="btn" type="submit">查询</button>
      <button class="btn ghost" type="button" @click="resetFilters">重置条件</button>
    </form>

    <table class="data-table">
      <thead>
        <tr>
          <th v-for="column in columns" :key="column">{{ column }}</th>
          <th>可执行动作</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="row in rows" :key="String(row.id)">
          <td v-for="column in columns" :key="column">
            <span v-if="column === '状态'" class="status-pill" :class="statusClass(row)">{{ row.status }}</span>
            <template v-else>{{ row[column] ?? '—' }}</template>
          </td>
          <td class="row-actions">
            <button class="link" type="button" @click="runAction('开工', row)">开工</button>
            <button class="link" type="button" @click="runAction('完工', row)">完工</button>
          </td>
        </tr>
        <tr v-if="!rows.length">
          <td :colspan="columns.length + 1" class="empty-state">暂无作业票数据，可先开具作业票</td>
        </tr>
      </tbody>
    </table>

    <footer class="page-foot">
      <span>共 {{ total }} 条作业票记录</span>
      <span v-if="noticeMessage" class="ok-text">{{ noticeMessage }}</span>
      <span v-if="errorMessage" class="error-text">{{ errorMessage }}</span>
    </footer>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'

import { request } from '@/api/client'

type Row = Record<string, any>

const ENDPOINT = '/api/workticket'
const columns = ['作业票编号', '队伍名称', '作业地点', '作业内容', '计划日期', '状态']
const statuses = ['待开工', '已开工', '已完工']

const rows = ref<Row[]>([])
const todos = ref<Row[]>([])
const teams = ref<Row[]>([])
const total = ref(0)
const errorMessage = ref('')
const noticeMessage = ref('')
const filters = ref<Record<string, string>>({ keyword: '', status: '' })
const showCreate = ref(false)
const createForm = ref<Record<string, string>>({ 作业票编号: '', 统一社会信用代码: '', 作业地点: '', 作业内容: '', 计划日期: '' })

const stats = computed(() => [
  { label: '作业票', value: total.value },
  { label: '待办结论', value: todos.value.length },
  { label: '待开工', value: rows.value.filter((row) => row.status === '待开工').length },
])

function statusClass(row: Row) {
  if (row.status === '已完工') return 'ok'
  if (row.status === '已开工') return 'warn'
  return 'pending'
}

function resetFilters() {
  filters.value = { keyword: '', status: '' }
  void reload()
}

function exportRows() {
  window.open(`${ENDPOINT}/export`, '_blank')
}

async function runAction(action: string, row: Row) {
  errorMessage.value = ''
  noticeMessage.value = ''
  try {
    const response = await request(`${ENDPOINT}/${row.id}/actions`, {
      method: 'POST',
      body: JSON.stringify({ values: { action } }),
    })
    const payload = await response.json()
    if (!payload.ok) {
      errorMessage.value = payload.message
      return
    }
    noticeMessage.value = payload.message
    await reload()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '作业票操作失败'
  }
}

async function closeTodo(todo: Row) {
  errorMessage.value = ''
  noticeMessage.value = ''
  try {
    const response = await request(`${ENDPOINT}/todos/${todo.id}/actions`, { method: 'POST' })
    const payload = await response.json()
    if (!payload.ok) {
      errorMessage.value = payload.message
      return
    }
    noticeMessage.value = payload.message
    await loadTodos()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '待办办结失败'
  }
}

async function submitCreate() {
  errorMessage.value = ''
  noticeMessage.value = ''
  try {
    const response = await request(ENDPOINT, {
      method: 'POST',
      body: JSON.stringify({ values: createForm.value }),
    })
    const payload = await response.json()
    if (!payload.ok) {
      errorMessage.value = payload.message
      return
    }
    noticeMessage.value = payload.message
    createForm.value = { 作业票编号: '', 统一社会信用代码: '', 作业地点: '', 作业内容: '', 计划日期: '' }
    showCreate.value = false
    await reload()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '开票失败'
  }
}

async function loadTodos() {
  try {
    const response = await request(`${ENDPOINT}/todos`)
    const payload = await response.json()
    todos.value = payload.items ?? []
  } catch {
    todos.value = []
  }
}

async function loadTeams() {
  try {
    const response = await request('/api/contractor?size=200')
    const payload = await response.json()
    teams.value = payload.items ?? []
  } catch {
    teams.value = []
  }
}

async function reload() {
  errorMessage.value = ''
  const query = new URLSearchParams()
  if (filters.value.keyword) query.set('keyword', filters.value.keyword)
  if (filters.value.status) query.set('status', filters.value.status)
  try {
    const response = await request(`${ENDPOINT}?${query.toString()}`)
    if (!response.ok) {
      throw new Error('作业票列表读取失败')
    }
    const payload = await response.json()
    rows.value = payload.items ?? []
    total.value = payload.total ?? rows.value.length
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '作业票列表读取失败'
  }
}

onMounted(async () => {
  await Promise.all([reload(), loadTodos(), loadTeams()])
})
</script>

<style scoped>
.panel {
  background: #fff;
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 12px;
  margin-bottom: 12px;
}
.panel-title { margin: 0 0 10px; font-size: 14px; }
.panel-hint { font-size: 12px; color: var(--muted); }
.panel-actions { display: flex; gap: 8px; margin-top: 8px; }
.form-grid { display: flex; flex-wrap: wrap; gap: 10px; }
.form-grid .filter-item { min-width: 220px; }
.status-pill { padding: 2px 8px; border-radius: 10px; font-size: 12px; }
.status-pill.ok { background: #e7f6ec; color: #157347; }
.status-pill.warn { background: #fff4e0; color: #b25e09; }
.status-pill.bad { background: #fdecea; color: #b42318; }
.status-pill.pending { background: #eef2ff; color: #1f6feb; }
.ok-text { color: #157347; }
</style>
