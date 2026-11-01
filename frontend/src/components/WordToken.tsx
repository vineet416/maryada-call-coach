import type { CSSProperties } from 'react'
import type { Finding } from '@/lib/events'
import { KIND_LABEL } from '@/lib/events'
import { tokId } from '@/lib/findings'
import type { TokenView } from '@/store/sessionStore'

interface Props {
  turnIdx: number
  token: TokenView
  finding: Finding | null
  reveal: boolean
  step: number
  onOpen: (f: Finding) => void
}

/** One word. Coloured and keyboard-operable when a finding covers it; the last word of a flagged phrase carries its rule id. */
export function WordToken({ turnIdx, token, finding, reveal, step, onOpen }: Props) {
  const lang = token.lang === 'mixed' ? 'hi' : token.lang
  const cls = `tok ${reveal ? 'reveal' : ''} ${finding ? `tok-${finding.kind}` : ''}`
  const style = { '--d': token.d, '--step': `${step}ms` } as CSSProperties
  if (!finding) {
    return (
      <span id={tokId(turnIdx, token.i)} lang={lang} className={cls} style={style}>
        {token.w}{' '}
      </span>
    )
  }
  const last = token.i === finding.token_range[1] - 1 && finding.kind !== 'good_practice'
  return (
    <span
      id={tokId(turnIdx, token.i)}
      role="button"
      tabIndex={0}
      lang={lang}
      className={`${cls} cursor-pointer`}
      style={style}
      aria-label={`${KIND_LABEL[finding.kind]}: ${finding.rule_id} ${token.w}, press Enter for details`}
      onClick={() => onOpen(finding)}
      onKeyDown={(e) => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault()
          onOpen(finding)
        }
      }}
    >
      {token.w}
      {last && <sup className="rt">{finding.rule_id}</sup>}{' '}
    </span>
  )
}
