<template>
  <section class="page" :data-module="meta.key">
    <header class="page-head">
      <div>
        <h2>{{ meta.name }}</h2>
        <p class="page-desc">{{ meta.desc }}</p>
      </div>
      <div class="page-actions">
        <button class="btn primary" data-testid="open-create" type="button" @click="openCreate">
          登记{{ meta.entity }}
        </button>
        <button class="btn" data-testid="export" type="button" @click="exportRows">
          导出{{ meta.name }}清单
        </button>
      </div>
    </header>

    <div class="stat-row">
      <article v-for="item in stats" :key="item.label" class="stat-card">
        <span class="stat-label">{{ item.label }}</span>
        <strong class="stat-value">{{ item.value }}</strong>
      </article>
    </div>

    <p class="status-legend">
      <span v-for="item in statusSummary" :key="item.status" class="legend-item">
        {{ item.status }}：{{ item.count }}
      </span>
    </p>

    <form class="filter-bar" @submit.prevent="reload">
      <label v-for="field in filterFields" :key="field" class="filter-item">
        <span>{{ field }}</span>
        <input v-model="filters[field]" :data-testid="`filter-${field}`" :placeholder="`按${field}检索`" />
      </label>
      <button class="btn" data-testid="query" type="submit">查询</button>
      <button class="btn ghost" data-testid="reset" type="button" @click="resetFilters">重置条件</button>
    </form>

    <table class="data-table">
      <thead>
        <tr>
          <th v-if="meta.review" class="select-col">选择</th>
          <th v-for="column in meta.fields" :key="column">{{ column }}</th>
          <th>当前状态</th>
          <th v-if="meta.review">复核回执</th>
          <th>可执行动作</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="row in rows" :key="String(row.id)" :data-testid="`row-${row.id}`" :data-status="String(row.status)">
          <td v-if="meta.review" class="select-col">
            <input
              type="checkbox"
              :data-testid="`select-${row.id}`"
              :checked="isSelected(Number(row.id))"
              :disabled="row.review_eligible !== true && !isSelected(Number(row.id))"
              @change="toggleSelect(Number(row.id))"
            />
          </td>
          <td v-for="column in meta.fields" :key="column">{{ row[column] ?? '—' }}</td>
          <td>{{ row.status }}</td>
          <td v-if="meta.review" :data-testid="`receipt-${row.id}`">
            <span v-if="row.review_receipt">{{ row.review_receipt }}（{{ row.review_status }}）</span>
            <span v-else-if="row.review_eligible === true">可送审</span>
            <span v-else>—</span>
          </td>
          <td class="row-actions">
            <button
              v-for="action in meta.actions"
              :key="action"
              class="link"
              type="button"
              :data-testid="`action-${row.id}-${action}`"
              @click="runAction(action, row)"
            >
              {{ action }}
            </button>
          </td>
        </tr>
        <tr v-if="!rows.length">
          <td :colspan="tableColspan" class="empty-state">
            <span v-if="loading">正在读取{{ meta.name }}…</span>
            <span v-else-if="loadFailed">本次读取未完成，已保留最近一次确认结果，可重试最新一次</span>
            <span v-else-if="hasIssuedFilters">按当前条件查到 0 项{{ meta.name }}，可调整条件或重置后再查</span>
            <span v-else>暂无{{ meta.name }}数据，可先登记{{ meta.entity }}</span>
          </td>
        </tr>
      </tbody>
    </table>

    <section v-if="meta.review" class="review-panel" data-testid="review-panel">
      <div class="review-head">
        <h3>送审与复核回执</h3>
        <span class="review-summary">
          已选 {{ selectedIds.length }} 项，其中 {{ eligibleSelection.length }} 项仍有确认资格
          <template v-if="staleSelectionCount">
            ，{{ staleSelectionCount }} 项不在已确认范围或已失去资格
          </template>
        </span>
        <button
          class="btn primary"
          data-testid="submit-review"
          type="button"
          :disabled="!eligibleSelection.length || submittingReview"
          @click="submitReview"
        >
          {{ submittingReview ? '送审中…' : '提交送审' }}
        </button>
      </div>
      <p v-if="reviewMessage" class="review-message" data-testid="review-message">{{ reviewMessage }}</p>
      <table v-if="reviewTickets.length" class="data-table review-table">
        <thead>
          <tr>
            <th>受理号</th><th>汇总编号</th><th>粒度关联</th><th>回执状态</th><th>复核组</th><th>操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="ticket in reviewTickets" :key="ticket.受理号" :data-testid="`ticket-${ticket.受理号}`">
            <td>{{ ticket.受理号 }}</td>
            <td>{{ ticket.汇总编号 }}</td>
            <td>
              {{ ticket.粒度关联.声明编号 }}@{{ ticket.粒度关联.声明版本 }}
              <template v-if="ticket.待确认关联">
                → 待确认 {{ ticket.待确认关联.声明编号 }}@{{ ticket.待确认关联.声明版本 }}
              </template>
            </td>
            <td>{{ ticket.status }}</td>
            <td>{{ ticket.复核组 ?? '未分配' }}</td>
            <td>
              <button
                v-if="ticket.status === '已暂停'"
                class="link"
                type="button"
                :data-testid="`confirm-assoc-${ticket.受理号}`"
                @click="confirmAssociation(ticket)"
              >
                确认新关联
              </button>
              <span v-else>—</span>
            </td>
          </tr>
        </tbody>
      </table>
    </section>

    <section v-if="meta.reviewTodo" class="review-panel" data-testid="review-todo-panel">
      <div class="review-head">
        <h3>复核待办</h3>
        <span class="review-summary">汇总层送审的受理回执在这里签收，一个受理号只能交给一个复核组</span>
      </div>
      <p v-if="reviewMessage" class="review-message" data-testid="review-message">{{ reviewMessage }}</p>
      <table v-if="reviewTickets.length" class="data-table review-table">
        <thead>
          <tr>
            <th>受理号</th><th>汇总编号</th><th>来源事实表</th><th>粒度关联</th><th>回执状态</th><th>复核组</th><th>操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="ticket in reviewTickets" :key="ticket.受理号" :data-testid="`todo-${ticket.受理号}`">
            <td>{{ ticket.受理号 }}</td>
            <td>{{ ticket.汇总编号 }}</td>
            <td>{{ ticket.来源事实表 }}</td>
            <td>{{ ticket.粒度关联.声明编号 }}@{{ ticket.粒度关联.声明版本 }}</td>
            <td>
              {{ ticket.status }}
              <template v-if="ticket.status === '已暂停'">（待汇总员确认新关联）</template>
            </td>
            <td>{{ ticket.复核组 ?? '未分配' }}</td>
            <td>
              <button
                v-if="ticket.status !== '已办结'"
                class="link"
                type="button"
                :data-testid="`sign-${ticket.受理号}`"
                :disabled="signingReceipt === ticket.受理号"
                @click="signTicket(ticket)"
              >
                签收
              </button>
              <span v-else>已归档</span>
            </td>
          </tr>
        </tbody>
      </table>
      <p v-else class="review-message">暂无复核待办</p>
    </section>

    <div v-if="showCreate" class="modal-backdrop" data-testid="create-modal">
      <form class="modal" @submit.prevent="submitCreate">
        <h3>登记{{ meta.entity }}</h3>
        <label v-for="field in meta.fields" :key="field" class="create-field">
          <span>{{ field }}</span>
          <input v-model="createValues[field]" :data-testid="`create-${field}`" required />
        </label>
        <div class="page-actions">
          <button class="btn" type="button" @click="showCreate = false">取消</button>
          <button class="btn primary" data-testid="submit-create" type="submit" :disabled="creating">
            {{ creating ? '提交中…' : '确认登记' }}
          </button>
        </div>
      </form>
    </div>

    <footer class="page-foot">
      <span>共 {{ total }} 条{{ meta.name }}记录</span>
      <span v-if="errorMessage" class="error-text">
        {{ errorMessage }}
        <button v-if="loadFailed" class="link" data-testid="retry-list" type="button" @click="retryLast">
          重试最新一次
        </button>
      </span>
    </footer>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'

import {
  createEntry,
  downloadEntries,
  listEntries,
  listReviewTodos,
  moduleMeta,
  runAction as applyAction,
  signReviewTodo,
} from '@/api/backend-service'
import type { EntryRow, ReviewTicket } from '@/data/types'

const props = defineProps<{ moduleKey: string }>()
const meta = moduleMeta(props.moduleKey)
const rows = ref<EntryRow[]>([])
const total = ref(0)
const errorMessage = ref('')
const filters = ref<Record<string, string>>({})
const filterFields = meta.fields.slice(0, 3)
const showCreate = ref(false)
const creating = ref(false)
const createValues = ref<Record<string, string>>({})
const stats = computed(() => [
  { label: meta.metrics[0], value: total.value },
  { label: meta.metrics[1], value: rows.value.filter((row) => row.status === meta.statuses[1]).length },
  {
    label: meta.metrics[2],
    value: rows.value.filter((row) => row.status === meta.statuses[meta.statuses.length - 1]).length,
  },
])
const statusSummary = computed(() =>
  meta.statuses.map((status) => ({
    status,
    count: rows.value.filter((row) => String(row.status) === status).length,
  })),
)
const tableColspan = computed(() => meta.fields.length + 2 + (meta.review ? 2 : 0))

// 列表读取：查询、重置、动作后刷新都汇入同一条调用链，必须用请求序号 +
// 中断保证只有最新一次请求能落地——旧查询的慢响应（或它的错误）不得覆盖
// 重置后恢复出来的结果。
const loading = ref(false)
const loadFailed = ref(false)
const confirmedRows = ref<EntryRow[]>([])
const issuedFilters = ref<Record<string, string>>({})
let listSeq = 0
let listAbort: AbortController | null = null

async function runList(snapshot: Record<string, string>) {
  const seq = ++listSeq
  listAbort?.abort()
  const controller = new AbortController()
  listAbort = controller
  issuedFilters.value = { ...snapshot }
  loading.value = true
  loadFailed.value = false
  errorMessage.value = ''
  try {
    const payload = await listEntries(meta.key, snapshot, controller.signal)
    if (seq !== listSeq) return // 旧响应不得覆盖新结果
    rows.value = payload.items
    total.value = payload.total
    confirmedRows.value = payload.items
  } catch (error) {
    if (seq !== listSeq) return // 旧错误不得覆盖新状态
    loadFailed.value = true
    errorMessage.value = error instanceof Error ? error.message : '业务列表读取失败'
  } finally {
    if (seq === listSeq) loading.value = false
  }
}

function reload() {
  return runList({ ...filters.value })
}

function retryLast() {
  // 值班员重试最新一次读取：沿用最后一次实际发出的条件，而不是输入框里未提交的值
  return runList(issuedFilters.value)
}

function resetFilters() {
  filters.value = {}
  void reload()
}

const hasIssuedFilters = computed(() =>
  Object.values(issuedFilters.value).some((value) => String(value).trim() !== ''),
)

// 送审选择：资格只认最近一次确认成功的范围；查询失败不清空选择，
// 旧范围的空结果不会被当成当前结论。
const selectedIds = ref<number[]>([])
const confirmedById = computed(() => {
  const map = new Map<number, EntryRow>()
  for (const row of confirmedRows.value) map.set(Number(row.id), row)
  return map
})
const eligibleSelection = computed(() =>
  selectedIds.value.filter((id) => confirmedById.value.get(id)?.review_eligible === true),
)
const staleSelectionCount = computed(() => selectedIds.value.length - eligibleSelection.value.length)

function isSelected(id: number) {
  return selectedIds.value.includes(id)
}

function toggleSelect(id: number) {
  selectedIds.value = isSelected(id)
    ? selectedIds.value.filter((item) => item !== id)
    : [...selectedIds.value, id]
}

// 复核回执：汇总层送审面板与粒度声明签收台共用一份待办
const reviewTickets = ref<ReviewTicket[]>([])
const reviewMessage = ref('')
const submittingReview = ref(false)
const signingReceipt = ref('')

async function refreshReviewTodos() {
  if (!meta.review && !meta.reviewTodo) return
  try {
    const payload = await listReviewTodos('grain_declare')
    reviewTickets.value = payload.items
  } catch {
    // 待办读取失败不阻断列表，下一次动作后再刷
  }
}

async function submitReview() {
  if (!meta.review || submittingReview.value) return
  const ids = [...eligibleSelection.value]
  const dropped = staleSelectionCount.value
  if (!ids.length) {
    reviewMessage.value = '选中记录都不在已确认范围或已失去确认资格，未提交'
    return
  }
  submittingReview.value = true
  reviewMessage.value = ''
  const notes: string[] = []
  try {
    for (const id of ids) {
      const result = await applyAction(meta.key, id, meta.review.submitAction)
      notes.push(result.message)
    }
    if (dropped) notes.push(`${dropped} 项已失去确认资格，未提交`)
    reviewMessage.value = notes.join('；')
    selectedIds.value = selectedIds.value.filter((id) => !ids.includes(id))
    await Promise.all([reload(), refreshReviewTodos()])
  } catch (error) {
    reviewMessage.value = error instanceof Error ? error.message : '送审失败'
  } finally {
    submittingReview.value = false
  }
}

async function confirmAssociation(ticket: ReviewTicket) {
  if (!meta.review) return
  reviewMessage.value = ''
  try {
    const result = await applyAction(meta.key, ticket.汇总id, meta.review.confirmAction)
    if (!result.ok) throw new Error(result.message)
    reviewMessage.value = result.message
    await Promise.all([reload(), refreshReviewTodos()])
  } catch (error) {
    reviewMessage.value = error instanceof Error ? error.message : '确认新关联失败'
  }
}

async function signTicket(ticket: ReviewTicket) {
  signingReceipt.value = ticket.受理号
  reviewMessage.value = ''
  try {
    const result = await signReviewTodo('grain_declare', ticket.受理号)
    if (!result.ok) throw new Error(result.message)
    reviewMessage.value = result.message
    await refreshReviewTodos()
  } catch (error) {
    reviewMessage.value = error instanceof Error ? error.message : '签收失败'
  } finally {
    signingReceipt.value = ''
  }
}

async function exportRows() {
  errorMessage.value = ''
  try {
    await downloadEntries(meta.key, filters.value)
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '导出失败'
  }
}

function openCreate() {
  createValues.value = Object.fromEntries(meta.fields.map((field) => [field, '']))
  errorMessage.value = ''
  showCreate.value = true
}

async function submitCreate() {
  creating.value = true
  errorMessage.value = ''
  try {
    const result = await createEntry(meta.key, createValues.value)
    if (!result.ok) throw new Error(result.message)
    showCreate.value = false
    await reload()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '登记失败'
  } finally {
    creating.value = false
  }
}

async function runAction(action: string, row: EntryRow) {
  errorMessage.value = ''
  try {
    const result = await applyAction(meta.key, Number(row.id), action)
    if (!result.ok) throw new Error(result.message)
    await Promise.all([reload(), refreshReviewTodos()])
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '操作失败'
  }
}

onMounted(() => {
  void reload()
  void refreshReviewTodos()
})
</script>
