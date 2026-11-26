/** 纯前端数据层的公共类型：与全栈版后端返回的结构保持一致，换回后端时页面不用改。 */

export type EntryRow = {
  id: number
  status: string
  pending: boolean
  abnormal: boolean
  [field: string]: string | number | boolean
}

export type ModuleMeta = {
  key: string
  name: string
  entity: string
  desc: string
  fields: string[]
  statuses: string[]
  actions: string[]
  actionTargets: Record<string, string>
  metrics: string[]
  /** 送审能力：选中行可提交到粒度声明的复核待办 */
  review?: {
    submitAction: string
    confirmAction: string
  }
  /** 复核待办能力：页面展示复核回执签收台 */
  reviewTodo?: boolean
}

export type PageResult = {
  items: EntryRow[]
  total: number
  page: number
  size: number
}

export type ActionResult = {
  ok: boolean
  message: string
}

export type ReviewAssociation = {
  声明编号: string
  维度组合: string
  声明版本: string
}

export type ReviewTicket = {
  受理号: string
  汇总id: number
  汇总编号: string
  来源事实表: string
  粒度关联: ReviewAssociation
  待确认关联: ReviewAssociation | null
  status: string
  复核组: string | null
  历史: { 事件: string; 说明: string }[]
}

export type ReviewTodoResult = {
  items: ReviewTicket[]
  total: number
}

export type OverviewResult = {
  cards: { label: string; value: number }[]
  modules: { name: string; created: number; pending: number; abnormal: number }[]
}
