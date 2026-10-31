export type Speaker = 'agent' | 'borrower' | 'third_party'
export type Kind = 'violation' | 'advisory' | 'needs_review' | 'good_practice'
export type Band = 'low' | 'medium' | 'high'

export interface Token {
  i: number
  w: string
  lang: string
}

export interface Finding {
  id: string
  turn_idx: number
  rule_id: string
  kind: Kind
  confidence: number
  quote: string
  token_range: [number, number]
  reason: string
  rbi_ref: string
  rewrite: string
  source: 'prefilter' | 'llm' | 'both'
  latency?: { total_ms?: number }
}

export interface Envelope {
  seq: number
  type: string
  t_ms: number
  // The payload differs per event type; each handler reads only the fields it needs.
  data: Record<string, any>
}

export const KIND_LABEL: Record<Kind, string> = {
  violation: 'Violation',
  advisory: 'Advisory',
  needs_review: 'Needs review',
  good_practice: 'Good practice',
}
