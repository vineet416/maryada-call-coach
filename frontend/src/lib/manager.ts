import type { ManagerAgent, ManagerCall, ManagerPayload, ManagerStatus } from '@/lib/api'

export const STATUS_LABEL: Record<ManagerStatus, string> = {
  needs_training: 'Needs training',
  watch: 'Watch',
  excellent: 'Excellent',
  too_few_calls: 'Too few calls',
  no_calls: 'No calls',
}
export const STATUS_CLASS: Record<ManagerStatus, string> = {
  needs_training: 'chip-violation',
  watch: 'chip-advisory',
  excellent: 'chip-ok',
  too_few_calls: '',
  no_calls: '',
}
export const STATUS_COLOR: Record<ManagerStatus, string> = {
  needs_training: 'var(--mc-violation)',
  watch: 'var(--mc-advisory)',
  excellent: 'var(--mc-good-practice)',
  too_few_calls: '#98a2b3',
  no_calls: '#98a2b3',
}

export const pct = (n: number | null) => (n === null ? '–' : `${Math.round(n * 100)}%`)
export const num = (n: number | null) => (n === null ? '–' : String(Math.round(n)))
export const plural = (n: number, one: string, many = `${one}s`) => `${n} ${n === 1 ? one : many}`
export const shortDate = (iso: string) =>
  new Date(`${iso}T00:00:00`).toLocaleDateString('en-GB', { day: 'numeric', month: 'short' })

export const ruleIds = (p: ManagerPayload) => p.rules.map((r) => r.id)
export const ruleTitle = (p: ManagerPayload, id: string) => p.rules.find((r) => r.id === id)?.title ?? ''

/** Rules whose findings are cases for a human to review, never violations (R6). The backend says which. */
export const isReviewOnly = (p: ManagerPayload, id: string) => p.rules.find((r) => r.id === id)?.review_only ?? false
/** What a per-rule count means: violations, or cases to review for a review-only rule. */
export const ruleCount = (p: ManagerPayload, a: ManagerAgent, id: string) =>
  isReviewOnly(p, id) ? (a.review_by_rule[id] ?? 0) : (a.by_rule[id] ?? 0)
export const reviewOnlyIds = (p: ManagerPayload) => p.rules.filter((r) => r.review_only).map((r) => r.id)
export const reviewNote = (p: ManagerPayload) => {
  const ids = reviewOnlyIds(p)
  return ids.length ? `${ids.join(', ')} ${ids.length > 1 ? 'are' : 'is'} advisory and needs-review only: its count is cases for a human to review, not violations.` : ''
}

export type SortKey = 'default' | 'name' | 'calls' | 'violations' | 'avg_risk' | 'top_rule' | 'status'
export const SORT_LABEL: Record<SortKey, string> = {
  default: 'Needs attention first', name: 'Agent', calls: 'Calls', violations: 'Violations', avg_risk: 'Average risk', top_rule: 'Top rule', status: 'Status',
}
const STATUS_RANK: Record<ManagerStatus, number> = { needs_training: 0, watch: 1, excellent: 2, too_few_calls: 3, no_calls: 4 }
/** Sorted copy of the rows. `default` keeps the server order. Ties keep the server order (stable sort). */
export function sortAgents<T extends ManagerAgent>(rows: T[], key: SortKey, desc: boolean, violations: (a: T) => number = (a) => a.violations): T[] {
  if (key === 'default') return rows
  const val = (a: T): string | number => {
    switch (key) {
      case 'name': return a.name
      case 'calls': return a.calls
      case 'violations': return violations(a)
      case 'avg_risk': return a.avg_risk ?? -1
      case 'top_rule': return a.top_rule ?? 'Z'
      case 'status': return STATUS_RANK[a.status]
      default: return 0
    }
  }
  const dir = desc ? -1 : 1
  return [...rows].sort((x, y) => {
    const a = val(x), b = val(y)
    return (typeof a === 'string' && typeof b === 'string' ? a.localeCompare(b) : (a as number) - (b as number)) * dir
  })
}

/** The agent's own call with the most violations of their top rule (chosen by the backend). */
export const exampleCall = (p: ManagerPayload, a: ManagerAgent): ManagerCall | null =>
  p.calls.find((c) => c.call_id === a.example_call_id) ?? null

const csvCell = (v: string | number | null) => {
  let s = v === null ? '' : String(v)
  if (/^[=+\-@\t\r]/.test(s)) s = `'${s}` // never let a spreadsheet read a cell as a formula
  return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s
}

/** CSV text of the agent table, as shown (same numbers, same date range). */
export function agentsCsv(p: ManagerPayload, agents: ManagerAgent[], ids: string[]): string {
  const head = ['Agent', 'Team', 'Calls', 'Violations', 'Needs review', 'Average risk', 'Peak risk', 'Top rule', 'Status', ...ids.map((r) => (isReviewOnly(p, r) ? `${r} (needs review)` : r))]
  const rows = agents.map((a) => [
    a.name, a.team, a.calls, a.violations, a.needs_review, a.avg_risk, a.peak_risk, a.top_rule ?? '', STATUS_LABEL[a.status],
    ...ids.map((r) => ruleCount(p, a, r)),
  ])
  return [head, ...rows].map((r) => r.map(csvCell).join(',')).join('\r\n') + '\r\n'
}

export function downloadCsv(name: string, text: string) {
  const url = URL.createObjectURL(new Blob([text], { type: 'text/csv;charset=utf-8' }))
  const a = document.createElement('a')
  a.href = url
  a.download = name
  document.body.appendChild(a)
  a.click()
  a.remove()
  URL.revokeObjectURL(url)
}
