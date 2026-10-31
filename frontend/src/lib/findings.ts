import type { Finding, Kind } from '@/lib/events'

const PRIORITY: Record<Kind, number> = { violation: 4, advisory: 3, needs_review: 2, good_practice: 1 }

/** Best finding that covers a word (violation beats advisory beats needs_review beats good practice). */
export function findingAt(findings: Finding[], turnIdx: number, i: number): Finding | null {
  let best: Finding | null = null
  for (const f of findings) {
    if (f.turn_idx !== turnIdx || i < f.token_range[0] || i >= f.token_range[1]) continue
    if (!best || PRIORITY[f.kind] > PRIORITY[best.kind]) best = f
  }
  return best
}

export function confidenceLabel(f: Finding): 'High' | 'Medium' | 'Needs review' {
  if (f.kind === 'needs_review' || f.confidence < 0.5) return 'Needs review'
  return f.confidence >= 0.8 ? 'High' : 'Medium'
}

export const SOURCE_LABEL: Record<Finding['source'], string> = {
  prefilter: 'Rules',
  llm: 'AI',
  both: 'Rules + AI',
}

export const KIND_COLOR: Record<Kind, string> = {
  violation: 'var(--mc-violation)',
  advisory: 'var(--mc-advisory)',
  needs_review: 'var(--mc-needs-review)',
  good_practice: 'var(--mc-good-practice)',
}

export const tokId = (turnIdx: number, i: number) => `tok-${turnIdx}-${i}`
