import { Fragment, type CSSProperties } from 'react'
import type { Finding } from '@/lib/events'
import { KIND_LABEL } from '@/lib/events'
import { tokId } from '@/lib/findings'
import type { TokenView } from '@/store/sessionStore'

interface Common {
  turnIdx: number
  reveal: boolean
  step: number
}

const langOf = (t: TokenView) => (t.lang === 'mixed' ? 'hi' : t.lang)
const styleOf = (t: TokenView, step: number) => ({ '--d': t.d, '--step': `${step}ms` }) as CSSProperties

/** One unflagged word. */
export function Word({ turnIdx, token, reveal, step }: Common & { token: TokenView }) {
  return (
    <span id={tokId(turnIdx, token.i)} lang={langOf(token)} className={`tok ${reveal ? 'reveal' : ''}`} style={styleOf(token, step)}>
      {token.w}{' '}
    </span>
  )
}

/**
 * One flagged phrase: a single keyboard-operable marker with one continuous underline, however many words it covers.
 * The rule id sits after the last word. Words keep their own ids so a finding can scroll to its first word.
 */
export function Phrase({
  turnIdx,
  tokens,
  finding,
  reveal,
  step,
  onOpen,
}: Common & { tokens: TokenView[]; finding: Finding; onOpen: (f: Finding) => void }) {
  const showRule = finding.kind !== 'good_practice'
  const open = () => onOpen(finding)
  return (
    <>
      <span
        id={tokId(turnIdx, tokens[0].i)}
        role="button"
        tabIndex={0}
        className={`tok tok-${finding.kind} cursor-pointer`}
        aria-label={`${tokens.map((t) => t.w).join(' ')}${showRule ? ` ${finding.rule_id}` : ''}: ${KIND_LABEL[finding.kind]}, press Enter for details`}
        onClick={open}
        onKeyDown={(e) => {
          if (e.key === 'Enter' || e.key === ' ') {
            e.preventDefault()
            open()
          }
        }}
      >
        {/* The spaces sit outside the word spans, so the one underline runs through them without a gap */}
        {tokens.map((t, k) => (
          <Fragment key={t.i}>
            {k > 0 && ' '}
            <span id={k === 0 ? undefined : tokId(turnIdx, t.i)} lang={langOf(t)} className={reveal ? 'reveal' : ''} style={styleOf(t, step)}>
              {t.w}
            </span>
          </Fragment>
        ))}
        {showRule && <sup className="rt">{finding.rule_id}</sup>}
      </span>{' '}
    </>
  )
}
