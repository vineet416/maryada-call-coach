import type { ManagerAgent, ManagerCall, ManagerPayload, ManagerStatus } from '@/lib/api'

export const STATUS_LABEL: Record<ManagerStatus, string> = {
  needs_training: 'Needs training',
  watch: 'Watch',
  excellent: 'Excellent',
  no_calls: 'No calls',
}
export const STATUS_CLASS: Record<ManagerStatus, string> = {
  needs_training: 'chip-violation',
  watch: 'chip-advisory',
  excellent: 'chip-ok',
  no_calls: '',
}
export const STATUS_COLOR: Record<ManagerStatus, string> = {
  needs_training: 'var(--mc-violation)',
  watch: 'var(--mc-advisory)',
  excellent: 'var(--mc-good-practice)',
  no_calls: '#98a2b3',
}

export const pct = (n: number | null) => (n === null ? '–' : `${Math.round(n * 100)}%`)
export const num = (n: number | null) => (n === null ? '–' : String(Math.round(n)))
export const plural = (n: number, one: string, many = `${one}s`) => `${n} ${n === 1 ? one : many}`
export const shortDate = (iso: string) =>
  new Date(`${iso}T00:00:00`).toLocaleDateString('en-GB', { day: 'numeric', month: 'short' })

export const ruleIds = (p: ManagerPayload) => p.rules.map((r) => r.id)
export const ruleTitle = (p: ManagerPayload, id: string) => p.rules.find((r) => r.id === id)?.title ?? ''

export const violationsOf = (c: ManagerCall) =>
  c.findings.filter((f) => f.kind === 'violation' || f.kind === 'advisory')

/** The agent's call that best shows their top rule: highest peak risk among calls with that rule. */
export function exampleCall(p: ManagerPayload, a: ManagerAgent): ManagerCall | null {
  const mine = p.calls.filter((c) => c.agent_id === a.id)
  const withRule = mine.filter((c) => violationsOf(c).some((f) => f.rule_id === a.top_rule))
  const pool = withRule.length ? withRule : mine
  return [...pool].sort((x, y) => y.risk_peak - x.risk_peak || x.call_id.localeCompare(y.call_id))[0] ?? null
}

const csvCell = (v: string | number | null) => {
  let s = v === null ? '' : String(v)
  if (/^[=+\-@\t\r]/.test(s)) s = `'${s}` // never let a spreadsheet read a cell as a formula
  return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s
}

/** CSV text of the agent table, as shown (same numbers, same date range). */
export function agentsCsv(agents: ManagerAgent[], ids: string[]): string {
  const head = ['Agent', 'Team', 'Calls', 'Violations', 'Needs review', 'Average risk', 'Peak risk', 'Top rule', 'Status', ...ids]
  const rows = agents.map((a) => [
    a.name, a.team, a.calls, a.violations, a.needs_review, a.avg_risk, a.peak_risk, a.top_rule ?? '', STATUS_LABEL[a.status],
    ...ids.map((r) => a.by_rule[r] ?? 0),
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
