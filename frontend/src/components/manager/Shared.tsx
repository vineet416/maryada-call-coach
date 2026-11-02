import { Line, LineChart, ResponsiveContainer, YAxis } from 'recharts'
import type { ManagerStatus } from '@/lib/api'
import { STATUS_CLASS, STATUS_COLOR, STATUS_LABEL } from '@/lib/manager'

export function StatusChip({ status, rule }: { status: ManagerStatus; rule: string }) {
  return (
    <span className={`chip ${STATUS_CLASS[status]} font-semibold`} title={rule}>
      {STATUS_LABEL[status]}
    </span>
  )
}

/** Risk of each call, oldest first. The numbers are in the label; the picture adds nothing a reader would miss. */
export function Spark({ values, status, name }: { values: number[]; status: ManagerStatus; name: string }) {
  const label = values.length ? `${name}: risk per call, oldest first: ${values.join(', ')}` : `${name}: no calls`
  return (
    <div role="img" aria-label={label} className="h-[26px] w-[84px]">
      {values.length > 0 && (
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={values.map((v, i) => ({ i, v }))} margin={{ top: 3, right: 3, bottom: 3, left: 3 }} accessibilityLayer={false}>
            <YAxis hide domain={[0, 100]} />
            <Line type="monotone" dataKey="v" stroke={STATUS_COLOR[status]} strokeWidth={2} dot={values.length === 1} isAnimationActive={false} />
          </LineChart>
        </ResponsiveContainer>
      )}
    </div>
  )
}

export function Initials({ name, status }: { name: string; status: ManagerStatus }) {
  const tone: Record<ManagerStatus, string> = {
    needs_training: 'bg-[var(--mc-violation-tint)] text-[var(--mc-violation-ink)]',
    watch: 'bg-[var(--mc-advisory-tint)] text-[var(--mc-advisory-ink)]',
    excellent: 'bg-[var(--mc-good-practice-tint)] text-[var(--mc-good-practice-ink)]',
    too_few_calls: 'bg-[var(--mc-line-soft)] text-[var(--mc-muted)]',
    no_calls: 'bg-[var(--mc-line-soft)] text-[var(--mc-muted)]',
  }
  const letters = name.split(' ').map((w) => w[0]).slice(0, 2).join('')
  return (
    <span aria-hidden className={`flex h-[34px] w-[34px] flex-none items-center justify-center rounded-full text-xs font-bold ${tone[status]}`}>
      {letters}
    </span>
  )
}

export function RecordedChip({ note, savedOn }: { note: string; savedOn: string | null }) {
  return (
    <span className="chip chip-warn" title={note}>
      Recorded run{savedOn ? ` · saved ${new Date(savedOn).toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' })}` : ''}
    </span>
  )
}
