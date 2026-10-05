<template>
  <section class="page" data-module="contractor">
    <header class="page-head">
      <div>
        <h2>外委队伍准入台账</h2>
        <p class="page-desc">按统一社会信用代码建档，资质证书与安全协议任一过期即退出准入名单；提交、撤回、审核仅限队伍归属单位的安全员。</p>
      </div>
      <div class="page-actions">
        <button class="btn primary" type="button" @click="openCreate">补录建档</button>
        <button class="btn" type="button" @click="openFilings">备案管理</button>
        <button class="btn" type="button" @click="exportRows">导出台账</button>
      </div>
    </header>

    <div class="identity-bar">
      <span>当前操作人：<strong>{{ store.operator }}</strong></span>
      <span>归属单位：<strong>{{ identityUnit || '未备案' }}</strong></span>
      <span class="muted">同一人挂多家单位时以最近一次备案为准；跨单位仅可查看，提交与撤回会被当场拒绝。</span>
    </div>

    <div class="stat-row">
      <article v-for="item in statCards" :key="item.label" class="stat-card">
        <span class="stat-label">{{ item.label }}</span>
        <strong class="stat-value">{{ item.value }}</strong>
      </article>
    </div>

    <form class="filter-bar" @submit.prevent="reload">
      <label class="filter-item">
        <span>信用代码 / 队伍名称</span>
        <input v-model="filters.keyword" placeholder="输入关键词检索" />
      </label>
      <label class="filter-item">
        <span>准入状态</span>
        <select v-model="filters.status">
          <option value="">全部状态</option>
          <option v-for="s in statuses" :key="s" :value="s">{{ s }}</option>
        </select>
      </label>
      <label class="filter-item">
        <span>归属单位</span>
        <select v-model="filters.unit">
          <option value="">全部单位</option>
          <option v-for="u in units" :key="u" :value="u">{{ u }}</option>
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
          <td>{{ row['统一社会信用代码'] }}</td>
          <td>{{ row['队伍名称'] }}</td>
          <td>{{ row['归属单位'] }}</td>
          <td>{{ row['资质有效期至'] }}</td>
          <td>{{ row['协议有效期至'] }}</td>
          <td>{{ row['进场时间'] }}</td>
          <td>
            <span class="badge" :class="badgeClass(String(row.status))">{{ row.status }}</span>
            <div v-if="row['临期提示']" class="hint-text">{{ row['临期提示'] }}</div>
          </td>
          <td class="row-actions">
            <button v-if="row.status !== '待审核'" class="link" type="button" @click="openSubmit(row)">提交审核</button>
            <button v-if="row.status === '待审核'" class="link" type="button" @click="runAction('撤回', row)">撤回</button>
            <button v-if="row.status === '待审核'" class="link" type="button" @click="runAction('审核通过', row)">审核通过</button>
            <button v-if="row.status === '待审核'" class="link" type="button" @click="runAction('审核退回', row)">审核退回</button>
            <button class="link" type="button" @click="openReviews(row)">留痕</button>
          </td>
        </tr>
        <tr v-if="!rows.length">
          <td :colspan="columns.length + 1" class="empty-state">暂无外委队伍数据，可先补录建档</td>
        </tr>
      </tbody>
    </table>

    <footer class="page-foot">
      <span>共 {{ total }} 支队伍（按进场时间排序）</span>
      <span v-if="errorMessage" class="error-text">{{ errorMessage }}</span>
      <span v-else-if="successMessage" class="success-text">{{ successMessage }}</span>
    </footer>

    <!-- 提交审核：可带续期后的材料 -->
    <div v-if="submitTarget" class="modal-mask" @click.self="submitTarget = null">
      <div class="modal">
        <h3>提交准入审核 · {{ submitTarget['队伍名称'] }}</h3>
        <p class="hint-text">材料以本次报送为准并快照留痕；资质续期后请在此填写新的有效期，重新走一遍准入。</p>
        <div class="form-grid">
          <label>资质证书编号<input v-model="submitForm['资质证书编号']" /></label>
          <label>资质有效期至<input v-model="submitForm['资质有效期至']" type="date" /></label>
          <label>安全协议编号<input v-model="submitForm['安全协议编号']" /></label>
          <label>协议有效期至<input v-model="submitForm['协议有效期至']" type="date" /></label>
          <label class="span-2">备注<input v-model="submitForm['备注']" placeholder="如：协议已续签，重新报审" /></label>
        </div>
        <div class="modal-foot">
          <button class="btn ghost" type="button" @click="submitTarget = null">取消</button>
          <button class="btn primary" type="button" @click="confirmSubmit">提交审核</button>
        </div>
      </div>
    </div>

    <!-- 补录建档 -->
    <div v-if="createOpen" class="modal-mask" @click.self="createOpen = false">
      <div class="modal">
        <h3>补录建档（存量队伍按进场时间补录）</h3>
        <div class="form-grid">
          <label>队伍名称<input v-model="createForm['队伍名称']" /></label>
          <label>统一社会信用代码<input v-model="createForm['统一社会信用代码']" placeholder="18 位，全库唯一" /></label>
          <label>资质证书编号<input v-model="createForm['资质证书编号']" /></label>
          <label>资质有效期至<input v-model="createForm['资质有效期至']" type="date" /></label>
          <label>安全协议编号<input v-model="createForm['安全协议编号']" /></label>
          <label>协议有效期至<input v-model="createForm['协议有效期至']" type="date" /></label>
          <label>进场时间<input v-model="createForm['进场时间']" type="date" /></label>
          <label>联系人<input v-model="createForm['联系人']" /></label>
        </div>
        <p class="hint-text">归属单位自动取当前操作人的备案单位（{{ identityUnit || '未备案' }}）；材料有效直接纳入准入名单，已过期则需续期后重新报审。</p>
        <div class="modal-foot">
          <button class="btn ghost" type="button" @click="createOpen = false">取消</button>
          <button class="btn primary" type="button" @click="confirmCreate">确认建档</button>
        </div>
      </div>
    </div>

    <!-- 审核留痕 -->
    <div v-if="reviewTarget" class="modal-mask" @click.self="reviewTarget = null">
      <div class="modal">
        <h3>审核留痕 · {{ reviewTarget['队伍名称'] }}</h3>
        <div class="review-list">
          <article v-for="item in reviews" :key="item.id" class="review-item">
            <div class="review-head">
              <strong>第{{ item['轮次'] }}轮 · {{ item['动作'] }}（{{ item['结论'] }}）</strong>
              <span class="muted">{{ item['时间'] }}</span>
            </div>
            <div>操作人：{{ item['操作人'] }}（{{ item['操作人单位'] }}）</div>
            <div class="review-materials">
              当时材料：资质 {{ item['资质证书编号'] }} 至 {{ item['资质有效期至'] }}；协议 {{ item['安全协议编号'] }} 至 {{ item['协议有效期至'] }}
            </div>
            <div>备注：{{ item['备注'] }}</div>
          </article>
          <p v-if="!reviews.length" class="empty-state">暂无留痕记录</p>
        </div>
        <div class="modal-foot">
          <button class="btn ghost" type="button" @click="reviewTarget = null">关闭</button>
        </div>
      </div>
    </div>

    <!-- 备案管理 -->
    <div v-if="filingsOpen" class="modal-mask" @click.self="filingsOpen = false">
      <div class="modal">
        <h3>安全员单位备案</h3>
        <table class="data-table">
          <thead>
            <tr><th>安全员</th><th>归属单位</th><th>备案时间</th><th>备注</th></tr>
          </thead>
          <tbody>
            <tr v-for="item in filings" :key="item.id">
              <td>{{ item['安全员姓名'] }}</td>
              <td>{{ item['归属单位'] }}</td>
              <td>{{ item['备案时间'] }}</td>
              <td>{{ item['备注'] }}</td>
            </tr>
          </tbody>
        </table>
        <p class="hint-text">当前归属按最近一次备案解析：{{ currentFilingText }}</p>
        <div class="form-grid">
          <label>安全员姓名<input v-model="filingForm['安全员姓名']" /></label>
          <label>归属单位
            <select v-model="filingForm['归属单位']">
              <option v-for="u in units" :key="u" :value="u">{{ u }}</option>
            </select>
          </label>
          <label class="span-2">备注<input v-model="filingForm['备注']" placeholder="如：岗位调整" /></label>
        </div>
        <div class="modal-foot">
          <button class="btn ghost" type="button" @click="filingsOpen = false">关闭</button>
          <button class="btn primary" type="button" @click="confirmFiling">新增备案</button>
        </div>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue'

import { request } from '@/api/client'
import { useSessionStore } from '@/stores/session'

type Row = Record<string, any>

const ENDPOINT = '/api/contractor'
const columns = ['统一社会信用代码', '队伍名称', '归属单位', '资质有效期至', '协议有效期至', '进场时间', '准入状态']
const statuses = ['待审核', '准入有效', '已退回', '已撤回', '已退出（证件过期）']
const units = ['安全管理一部', '安全管理二部', '安全管理三部']

const store = useSessionStore()

const rows = ref<Row[]>([])
const total = ref(0)
const stats = ref<Record<string, number>>({})
const errorMessage = ref('')
const successMessage = ref('')
const filters = reactive({ keyword: '', status: '', unit: '' })

const identityUnit = ref('')
const submitTarget = ref<Row | null>(null)
const submitForm = reactive<Record<string, string>>({})
const createOpen = ref(false)
const createForm = reactive<Record<string, string>>({})
const reviewTarget = ref<Row | null>(null)
const reviews = ref<Row[]>([])
const filingsOpen = ref(false)
const filings = ref<Row[]>([])
const currentFilings = ref<Record<string, string>>({})
const filingForm = reactive<Record<string, string>>({ 安全员姓名: '', 归属单位: units[0], 备注: '' })

const statCards = computed(() => [
  { label: '准入有效', value: stats.value['准入有效'] ?? 0 },
  { label: '待审核', value: stats.value['待审核'] ?? 0 },
  { label: '已退出（证件过期）', value: stats.value['已退出'] ?? 0 },
  { label: '临期预警（30日内）', value: stats.value['临期预警'] ?? 0 },
])

const currentFilingText = computed(() =>
  Object.entries(currentFilings.value).map(([name, unit]) => `${name}→${unit}`).join('；') || '暂无备案',
)

function badgeClass(status: string): string {
  if (status === '准入有效') return 'ok'
  if (status === '待审核') return 'warn'
  if (status === '已退出（证件过期）' || status === '已退回') return 'bad'
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
  if (filters.unit) query.set('unit', filters.unit)
  try {
    const [listResp, statsResp] = await Promise.all([
      request(`${ENDPOINT}?${query}`),
      request(`${ENDPOINT}/stats`),
    ])
    const listPayload = await listResp.json()
    rows.value = listPayload.items ?? []
    total.value = listPayload.total ?? rows.value.length
    stats.value = await statsResp.json()
  } catch (error) {
    showError(error)
  }
}

async function reloadIdentity() {
  try {
    const response = await request(`${ENDPOINT}/identity?name=${encodeURIComponent(store.operator)}`)
    const payload = await response.json()
    identityUnit.value = payload['当前单位'] ?? ''
  } catch {
    identityUnit.value = ''
  }
}

function resetFilters() {
  filters.keyword = ''
  filters.status = ''
  filters.unit = ''
  void reload()
}

function exportRows() {
  window.open(`${ENDPOINT}/export`, '_blank')
}

function openSubmit(row: Row) {
  submitForm['资质证书编号'] = row['资质证书编号'] ?? ''
  submitForm['资质有效期至'] = row['资质有效期至'] ?? ''
  submitForm['安全协议编号'] = row['安全协议编号'] ?? ''
  submitForm['协议有效期至'] = row['协议有效期至'] ?? ''
  submitForm['备注'] = ''
  submitTarget.value = row
}

async function confirmSubmit() {
  if (!submitTarget.value) return
  try {
    const result = await callApi(`${ENDPOINT}/${submitTarget.value.id}/actions`, {
      method: 'POST',
      body: JSON.stringify({ values: { action: '提交审核', ...submitForm } }),
    })
    submitTarget.value = null
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

async function openReviews(row: Row) {
  reviewTarget.value = row
  reviews.value = []
  try {
    const response = await request(`${ENDPOINT}/${row.id}/reviews`)
    const payload = await response.json()
    reviews.value = payload.items ?? []
  } catch (error) {
    showError(error)
  }
}

async function openFilings() {
  filingsOpen.value = true
  filingForm['安全员姓名'] = store.operator
  try {
    const response = await request(`${ENDPOINT}/filings`)
    const payload = await response.json()
    filings.value = payload.items ?? []
    currentFilings.value = payload['当前归属'] ?? {}
  } catch (error) {
    showError(error)
  }
}

async function confirmFiling() {
  try {
    const result = await callApi(`${ENDPOINT}/filings`, {
      method: 'POST',
      body: JSON.stringify({ values: { ...filingForm } }),
    })
    showResult(result.message)
    await openFilings()
    await reloadIdentity()
  } catch (error) {
    showError(error)
  }
}

watch(() => store.operator, () => {
  void reloadIdentity()
})

onMounted(() => {
  void reload()
  void reloadIdentity()
})
</script>
