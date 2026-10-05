<template>
  <section class="page" data-module="workticket">
    <header class="page-head">
      <div>
        <h2>作业票管理</h2>
        <p class="page-desc">开具作业票必须引用准入名单内的外委队伍；准入结论（通过、退回、到期退出）自动同步到待办清单。</p>
      </div>
      <div class="page-actions">
        <button class="btn primary" type="button" @click="openCreate">开具作业票</button>
        <button class="btn" type="button" @click="exportRows">导出作业票清单</button>
      </div>
    </header>

    <div class="stat-row">
      <article v-for="item in statCards" :key="item.label" class="stat-card">
        <span class="stat-label">{{ item.label }}</span>
        <strong class="stat-value">{{ item.value }}</strong>
      </article>
    </div>

    <form class="filter-bar" @submit.prevent="reload">
      <label class="filter-item">
        <span>编号 / 队伍 / 信用代码</span>
        <input v-model="filters.keyword" placeholder="输入关键词检索" />
      </label>
      <label class="filter-item">
        <span>状态</span>
        <select v-model="filters.status">
          <option value="">全部状态</option>
          <option v-for="s in statuses" :key="s" :value="s">{{ s }}</option>
        </select>
      </label>
      <button class="btn" type="submit">查询</button>
      <button class="btn ghost" type="button" @click="resetFilters">重置条件</button>
    </form>

    <table class="data-table">
      <thead>
        <tr>
          <th v-for="column in columns" :key="column">{{ column }}</th>
          <th>待办清单</th>
          <th>可执行动作</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="row in rows" :key="String(row.id)">
          <td>{{ row['作业票编号'] }}</td>
          <td>{{ row['外委队伍名称'] }}</td>
          <td>{{ row['作业内容'] }}</td>
          <td>{{ row['作业区域'] }}</td>
          <td>{{ row['计划日期'] }}</td>
          <td><span class="badge" :class="badgeClass(String(row.status))">{{ row.status }}</span></td>
          <td>
            <ul class="todo-list">
              <li v-for="(todo, index) in row['待办清单']" :key="index">
                <span class="badge" :class="todo['状态'] === '待办' ? 'warn' : 'ok'">{{ todo['状态'] }}</span>
                <span>
                  {{ todo['内容'] }}
                  <span class="todo-time">{{ todo['来源'] }} · {{ todo['时间'] }}</span>
                </span>
                <button v-if="todo['状态'] === '待办'" class="link" type="button" @click="closeTodo(row, index)">办结</button>
              </li>
            </ul>
          </td>
          <td class="row-actions">
            <button v-if="row.status === '待开工'" class="link" type="button" @click="runAction('开工', row)">开工</button>
            <button v-if="row.status === '作业中'" class="link" type="button" @click="runAction('叫停', row)">叫停</button>
            <button v-if="row.status !== '已完工'" class="link" type="button" @click="runAction('完工', row)">完工</button>
          </td>
        </tr>
        <tr v-if="!rows.length">
          <td :colspan="columns.length + 2" class="empty-state">暂无作业票数据，可先开具作业票</td>
        </tr>
      </tbody>
    </table>

    <footer class="page-foot">
      <span>共 {{ total }} 张作业票</span>
      <span v-if="errorMessage" class="error-text">{{ errorMessage }}</span>
      <span v-else-if="successMessage" class="success-text">{{ successMessage }}</span>
    </footer>

    <!-- 开具作业票 -->
    <div v-if="createOpen" class="modal-mask" @click.self="createOpen = false">
      <div class="modal">
        <h3>开具作业票</h3>
        <div class="form-grid">
          <label class="span-2">外委队伍信用代码
            <input v-model="createForm['外委队伍信用代码']" placeholder="18 位统一社会信用代码，仅准入名单内可引用" />
          </label>
          <label class="span-2">作业内容<input v-model="createForm['作业内容']" /></label>
          <label>作业区域<input v-model="createForm['作业区域']" /></label>
          <label>计划日期<input v-model="createForm['计划日期']" type="date" /></label>
        </div>
        <p class="hint-text">名单外的队伍（未建档、待审核、已退回、已撤回、已退出）不允许被作业票引用。</p>
        <div class="modal-foot">
          <button class="btn ghost" type="button" @click="createOpen = false">取消</button>
          <button class="btn primary" type="button" @click="confirmCreate">确认开票</button>
        </div>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'

import { request } from '@/api/client'

type Row = Record<string, any>

const ENDPOINT = '/api/workticket'
const columns = ['作业票编号', '外委队伍名称', '作业内容', '作业区域', '计划日期', '状态']
const statuses = ['待开工', '作业中', '已叫停', '已完工']

const rows = ref<Row[]>([])
const total = ref(0)
const errorMessage = ref('')
const successMessage = ref('')
const filters = reactive({ keyword: '', status: '' })
const createOpen = ref(false)
const createForm = reactive<Record<string, string>>({})

const statCards = computed(() => [
  { label: '作业票总数', value: total.value },
  { label: '待开工', value: rows.value.filter((row) => row.status === '待开工').length },
  { label: '作业中', value: rows.value.filter((row) => row.status === '作业中').length },
  { label: '未办结待办', value: rows.value.reduce((sum, row) => sum + (row['待办清单'] ?? []).filter((t: Row) => t['状态'] === '待办').length, 0) },
])

function badgeClass(status: string): string {
  if (status === '作业中') return 'ok'
  if (status === '待开工') return 'warn'
  if (status === '已叫停') return 'bad'
  return 'idle'
}

async function callApi(path: string, init?: RequestInit): Promise<{ ok: boolean; message: string }> {
  const response = await request(path, init)
  const payload = (await response.json()) as { ok: boolean; message: string }
  if (!payload.ok) {
    throw new Error(payload.message || '操作未生效')
  }
  return payload
}

function showResult(message: string) {
  errorMessage.value = ''
  successMessage.value = message
}

function showError(error: unknown) {
  successMessage.value = ''
  errorMessage.value = error instanceof Error ? error.message : '操作失败'
}

async function reload() {
  errorMessage.value = ''
  successMessage.value = ''
  const query = new URLSearchParams()
  if (filters.keyword) query.set('keyword', filters.keyword)
  if (filters.status) query.set('status', filters.status)
  try {
    const response = await request(`${ENDPOINT}?${query}`)
    const payload = await response.json()
    rows.value = payload.items ?? []
    total.value = payload.total ?? rows.value.length
  } catch (error) {
    showError(error)
  }
}

function resetFilters() {
  filters.keyword = ''
  filters.status = ''
  void reload()
}

function exportRows() {
  window.open(`${ENDPOINT}/export`, '_blank')
}

function openCreate() {
  Object.keys(createForm).forEach((key) => delete createForm[key])
  createOpen.value = true
}

async function confirmCreate() {
  try {
    const result = await callApi(ENDPOINT, {
      method: 'POST',
      body: JSON.stringify({ values: { ...createForm } }),
    })
    createOpen.value = false
    showResult(result.message)
    await reload()
  } catch (error) {
    showError(error)
  }
}

async function runAction(action: string, row: Row) {
  try {
    const result = await callApi(`${ENDPOINT}/${row.id}/actions`, {
      method: 'POST',
      body: JSON.stringify({ values: { action } }),
    })
    showResult(result.message)
    await reload()
  } catch (error) {
    showError(error)
  }
}

async function closeTodo(row: Row, index: number) {
  try {
    const result = await callApi(`${ENDPOINT}/${row.id}/actions`, {
      method: 'POST',
      body: JSON.stringify({ values: { action: '办结待办', 待办序号: index } }),
    })
    showResult(result.message)
    await reload()
  } catch (error) {
    showError(error)
  }
}

onMounted(reload)
</script>
