<template>
  <section class="page" data-module="contractor">
    <header class="page-head">
      <div>
        <h2>外委队伍准入台账</h2>
        <p class="page-desc">一支队伍按统一社会信用代码建档；资质证书或安全协议任一过期即退出准入名单，名单外队伍不允许被作业票引用。</p>
      </div>
      <div class="page-actions">
        <button class="btn primary" type="button" @click="showCreate = !showCreate">登记 / 补录队伍</button>
        <button class="btn" type="button" @click="showFilings = !showFilings">安全员备案</button>
        <button class="btn" type="button" @click="exportRows">导出准入台账</button>
      </div>
    </header>

    <div class="operator-bar">
      <label class="filter-item">
        <span>当前安全员（决定可操作的队伍范围）</span>
        <select v-model="operator">
          <option value="">未选择</option>
          <option v-for="item in operatorOptions" :key="item.name" :value="item.name">
            {{ item.name }}（{{ item.unit || '未备案' }}）
          </option>
        </select>
      </label>
      <span class="operator-hint">只有队伍归属单位的安全员能提交审核、续期与撤回；跨单位仅可查看。一人挂多家单位时以最近一次备案为准。</span>
    </div>

    <div class="stat-row">
      <article v-for="item in stats" :key="item.label" class="stat-card">
        <span class="stat-label">{{ item.label }}</span>
        <strong class="stat-value">{{ item.value }}</strong>
      </article>
    </div>

    <form v-if="showCreate" class="panel" @submit.prevent="submitCreate">
      <h3 class="panel-title">登记 / 补录外委队伍</h3>
      <div class="form-grid">
        <label v-for="field in createFields" :key="field.key" class="filter-item">
          <span>{{ field.label }}</span>
          <input v-model="createForm[field.key]" :type="field.type ?? 'text'" :placeholder="field.label" />
        </label>
        <label class="filter-item checkbox-item">
          <span>存量补录</span>
          <input v-model="createForm['补录']" type="checkbox" />
        </label>
      </div>
      <p class="panel-hint">勾选「存量补录」时按所填进场时间建档；不勾选按新队伍登记。建档后状态为待审核，需归属单位安全员提交准入审核。</p>
      <div class="panel-actions">
        <button class="btn primary" type="submit">提交建档</button>
        <button class="btn ghost" type="button" @click="showCreate = false">取消</button>
      </div>
    </form>

    <form v-if="showFilings" class="panel" @submit.prevent="submitFiling">
      <h3 class="panel-title">安全员备案（留痕，最近一次备案为准）</h3>
      <table class="data-table">
        <thead>
          <tr><th>安全员</th><th>备案单位</th><th>备案时间</th></tr>
        </thead>
        <tbody>
          <tr v-for="row in filings" :key="String(row.id)">
            <td>{{ row['安全员'] }}</td>
            <td>{{ row['单位'] }}</td>
            <td>{{ row['备案时间'] }}</td>
          </tr>
        </tbody>
      </table>
      <div class="form-grid">
        <label class="filter-item">
          <span>安全员</span>
          <input v-model="filingForm['安全员']" placeholder="安全员姓名" />
        </label>
        <label class="filter-item">
          <span>备案单位</span>
          <input v-model="filingForm['单位']" placeholder="如：通风安全科" />
        </label>
        <label class="filter-item">
          <span>备案时间</span>
          <input v-model="filingForm['备案时间']" type="date" />
        </label>
      </div>
      <div class="panel-actions">
        <button class="btn primary" type="submit">新增备案</button>
        <button class="btn ghost" type="button" @click="showFilings = false">收起</button>
      </div>
    </form>

    <form class="filter-bar" @submit.prevent="reload">
      <label class="filter-item">
        <span>队伍名称 / 信用代码</span>
        <input v-model="filters.keyword" placeholder="按队伍名称或统一社会信用代码检索" />
      </label>
      <label class="filter-item">
        <span>准入状态</span>
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
            <button class="link" type="button" @click="runAction('提交审核', row)">提交审核</button>
            <button class="link" type="button" @click="openRenew(row)">资质续期</button>
            <button class="link" type="button" @click="runAction('撤回', row)">撤回</button>
            <button class="link" type="button" @click="toggleReviews(row)">审核记录</button>
          </td>
        </tr>
        <tr v-if="!rows.length">
          <td :colspan="columns.length + 1" class="empty-state">暂无外委队伍数据，可先登记或补录队伍</td>
        </tr>
      </tbody>
    </table>

    <form v-if="renewTarget" class="panel" @submit.prevent="submitRenew">
      <h3 class="panel-title">资质续期：{{ renewTarget['队伍名称'] }}</h3>
      <div class="form-grid">
        <label class="filter-item">
          <span>资质证书新有效期（当前 {{ renewTarget['资质到期日'] }}）</span>
          <input v-model="renewForm['资质到期日']" type="date" />
        </label>
        <label class="filter-item">
          <span>安全协议新有效期（当前 {{ renewTarget['协议到期日'] }}）</span>
          <input v-model="renewForm['协议到期日']" type="date" />
        </label>
      </div>
      <p class="panel-hint">至少填一项新有效期；续期登记后队伍回到待审核状态，需重新走一遍准入审核，历史审核结论按当时材料保留。</p>
      <div class="panel-actions">
        <button class="btn primary" type="submit">登记续期</button>
        <button class="btn ghost" type="button" @click="renewTarget = null">取消</button>
      </div>
    </form>

    <div v-if="reviewTarget" class="panel">
      <h3 class="panel-title">审核记录：{{ reviewTarget['队伍名称'] }}（历史结论按当时材料封存）</h3>
      <table class="data-table">
        <thead>
          <tr><th>审核时间</th><th>操作人</th><th>操作人单位</th><th>结论</th><th>资质到期日(当时)</th><th>协议到期日(当时)</th><th>备注</th></tr>
        </thead>
        <tbody>
          <tr v-for="item in reviews" :key="String(item.id)">
            <td>{{ item['审核时间'] }}</td>
            <td>{{ item['操作人'] }}</td>
            <td>{{ item['操作人单位'] }}</td>
            <td>{{ item['结论'] }}</td>
            <td>{{ item['材料快照']?.['资质到期日'] ?? '—' }}</td>
            <td>{{ item['材料快照']?.['协议到期日'] ?? '—' }}</td>
            <td>{{ item['备注'] }}</td>
          </tr>
          <tr v-if="!reviews.length"><td colspan="7" class="empty-state">暂无审核记录</td></tr>
        </tbody>
      </table>
    </div>

    <footer class="page-foot">
      <span>共 {{ total }} 条外委队伍记录</span>
      <span v-if="noticeMessage" class="ok-text">{{ noticeMessage }}</span>
      <span v-if="errorMessage" class="error-text">{{ errorMessage }}</span>
    </footer>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'

import { request } from '@/api/client'

type Row = Record<string, any>

const ENDPOINT = '/api/contractor'
const columns = ['统一社会信用代码', '队伍名称', '归属单位', '资质到期日', '协议到期日', '进场时间', '来源', '状态']
const statuses = ['待审核', '准入有效', '已退出']
const createFields = [
  { key: '统一社会信用代码', label: '统一社会信用代码' },
  { key: '队伍名称', label: '队伍名称' },
  { key: '归属单位', label: '归属安全管理单位' },
  { key: '资质证书编号', label: '资质证书编号' },
  { key: '资质到期日', label: '资质到期日', type: 'date' },
  { key: '安全协议编号', label: '安全协议编号' },
  { key: '协议到期日', label: '协议到期日', type: 'date' },
  { key: '进场时间', label: '进场时间', type: 'date' },
]

const rows = ref<Row[]>([])
const total = ref(0)
const errorMessage = ref('')
const noticeMessage = ref('')
const filters = ref<Record<string, string>>({ keyword: '', status: '' })
const operator = ref('')
const filings = ref<Row[]>([])
const showCreate = ref(false)
const showFilings = ref(false)
const createForm = ref<Record<string, any>>({ 补录: false })
const filingForm = ref<Record<string, string>>({ 安全员: '', 单位: '', 备案时间: '' })
const renewTarget = ref<Row | null>(null)
const renewForm = ref<Record<string, string>>({ 资质到期日: '', 协议到期日: '' })
const reviewTarget = ref<Row | null>(null)
const reviews = ref<Row[]>([])

const stats = computed(() => [
  { label: '在册队伍', value: total.value },
  { label: '准入有效', value: rows.value.filter((row) => row.status === '准入有效').length },
  { label: '临期预警', value: rows.value.filter((row) => row['临期']).length },
  { label: '已退出', value: rows.value.filter((row) => row.status === '已退出').length },
])

const operatorOptions = computed(() => {
  const latest = new Map<string, string>()
  for (const filing of [...filings.value].reverse()) {
    const name = String(filing['安全员'] ?? '')
    if (name && !latest.has(name)) {
      latest.set(name, String(filing['单位'] ?? ''))
    }
  }
  return [...latest.entries()].map(([name, unit]) => ({ name, unit }))
})

function statusClass(row: Row) {
  if (row.status === '准入有效') return row['临期'] ? 'warn' : 'ok'
  if (row.status === '已退出') return 'bad'
  return 'pending'
}

function resetFilters() {
  filters.value = { keyword: '', status: '' }
  void reload()
}

function exportRows() {
  window.open(`${ENDPOINT}/export`, '_blank')
}

async function callAction(id: number | string, values: Record<string, any>) {
  errorMessage.value = ''
  noticeMessage.value = ''
  try {
    const response = await request(`${ENDPOINT}/${id}/actions`, {
      method: 'POST',
      body: JSON.stringify({ values }),
    })
    const payload = await response.json()
    if (!payload.ok) {
      errorMessage.value = payload.message
      return false
    }
    noticeMessage.value = payload.message
    return true
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '外委队伍操作失败'
    return false
  }
}

async function runAction(action: string, row: Row) {
  const ok = await callAction(row.id, { action, 操作人: operator.value })
  if (ok) {
    await reload()
  }
}

function openRenew(row: Row) {
  renewTarget.value = row
  renewForm.value = { 资质到期日: '', 协议到期日: '' }
}

async function submitRenew() {
  if (!renewTarget.value) return
  const ok = await callAction(renewTarget.value.id, {
    action: '资质续期',
    操作人: operator.value,
    ...renewForm.value,
  })
  if (ok) {
    renewTarget.value = null
    await reload()
  }
}

async function toggleReviews(row: Row) {
  if (reviewTarget.value?.id === row.id) {
    reviewTarget.value = null
    return
  }
  reviewTarget.value = row
  const response = await request(`${ENDPOINT}/${row.id}/reviews`)
  const payload = await response.json()
  reviews.value = payload.items ?? []
}

async function submitCreate() {
  errorMessage.value = ''
  noticeMessage.value = ''
  try {
    const response = await request(ENDPOINT, {
      method: 'POST',
      body: JSON.stringify({ values: { ...createForm.value, 操作人: operator.value } }),
    })
    const payload = await response.json()
    if (!payload.ok) {
      errorMessage.value = payload.message
      return
    }
    noticeMessage.value = payload.message
    createForm.value = { 补录: false }
    showCreate.value = false
    await reload()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '建档失败'
  }
}

async function submitFiling() {
  errorMessage.value = ''
  noticeMessage.value = ''
  try {
    const response = await request(`${ENDPOINT}/filings`, {
      method: 'POST',
      body: JSON.stringify({ values: filingForm.value }),
    })
    const payload = await response.json()
    if (!payload.ok) {
      errorMessage.value = payload.message
      return
    }
    noticeMessage.value = payload.message
    filingForm.value = { 安全员: '', 单位: '', 备案时间: '' }
    await loadFilings()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '备案失败'
  }
}

async function loadFilings() {
  try {
    const response = await request(`${ENDPOINT}/filings`)
    const payload = await response.json()
    filings.value = payload.items ?? []
  } catch {
    filings.value = []
  }
}

async function reload() {
  errorMessage.value = ''
  const query = new URLSearchParams()
  if (filters.value.keyword) query.set('keyword', filters.value.keyword)
  if (filters.value.status) query.set('status', filters.value.status)
  query.set('size', '200')
  try {
    const response = await request(`${ENDPOINT}?${query.toString()}`)
    if (!response.ok) {
      throw new Error('外委队伍列表读取失败')
    }
    const payload = await response.json()
    rows.value = payload.items ?? []
    total.value = payload.total ?? rows.value.length
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '外委队伍列表读取失败'
  }
}

onMounted(async () => {
  await loadFilings()
  operator.value = operatorOptions.value[0]?.name ?? ''
  await reload()
})
</script>

<style scoped>
.operator-bar {
  display: flex;
  gap: 12px;
  align-items: flex-end;
  background: #fff;
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 10px 12px;
  margin-bottom: 12px;
}
.operator-hint { font-size: 12px; color: var(--muted); }
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
.checkbox-item input { width: auto; }
.status-pill { padding: 2px 8px; border-radius: 10px; font-size: 12px; }
.status-pill.ok { background: #e7f6ec; color: #157347; }
.status-pill.warn { background: #fff4e0; color: #b25e09; }
.status-pill.bad { background: #fdecea; color: #b42318; }
.status-pill.pending { background: #eef2ff; color: #1f6feb; }
.ok-text { color: #157347; }
</style>
