import { CartesianGrid, ComposedChart, Line, ReferenceArea, ReferenceLine, ResponsiveContainer, Scatter, XAxis, YAxis } from 'recharts'
import type { CallReport } from '@/lib/api'
import type { Kind } from '@/lib/events'
import { KIND_LABEL } from '@/lib/events'
import { KIND_COLOR } from '@/lib/findings'
import { clock } from '@/lib/format'

const INK = '#5b6577'
const MARK = 9

/** The shape tells the kind as well as the colour: diamond = violation, square = advisory, ring = needs review. */
function Marker({ cx = 0, cy = 0, kind }: { cx?: number; cy?: number; kind: Kind }) {
  const color = KIND_COLOR[kind]
  if (kind === 'violation') return <path d={`M${cx} ${cy - MARK}L${cx + MARK} ${cy}L${cx} ${cy + MARK}L${cx - MARK} ${cy}Z`} fill={color} stroke="#fff" strokeWidth={1.5} />
  if (kind === 'advisory') return <rect x={cx - MARK + 2} y={cy - MARK + 2} width={(MARK - 2) * 2} height={(MARK - 2) * 2} fill={color} stroke="#fff" strokeWidth={1.5} />
  return <circle cx={cx} cy={cy} r={MARK - 2} fill="#fff" stroke={color} strokeWidth={2.5} />
}

const scoreAt = (risk: CallReport['risk'], t: number) => risk.reduce((s, r) => (r.t_ms <= t ? r.score : s), 0)

/** Risk after each agent turn as a step line, with the moment each flag appeared. The same numbers are listed below the chart. */
export function RiskChart({ report }: { report: CallReport }) {
  const { risk, flags, bands, kpis, scenario } = report
  const end = Math.max(scenario.duration_ms ?? 0, ...risk.map((r) => r.t_ms), ...flags.map((f) => f.t_ms))
  const line = [{ t: 0, score: 0 }, ...risk.map((r) => ({ t: r.t_ms, score: r.score }))]
  const dots = flags.map((f) => ({ t: f.t_ms, y: scoreAt(risk, f.t_ms), kind: f.kind }))
  const top = Math.max(kpis.peak_risk, bands.high_from)
  const floor = -Math.ceil(top * 0.1) // headroom below zero so a marker on the baseline is drawn whole
  const kinds = [...new Set(flags.map((f) => f.kind))]
  const label = `Risk over time. ${risk.length ? `${risk.length} readings, peak ${kpis.peak_risk}.` : 'No readings.'} ${flags.length} flag${flags.length === 1 ? '' : 's'}.`

  return (
    <div>
      <div role="img" aria-label={label} className="h-[230px] w-full sm:h-[260px]">
        <ResponsiveContainer width="100%" height="100%">
          <ComposedChart margin={{ top: 12, right: 14, bottom: 4, left: 0 }} accessibilityLayer={false}>
            <CartesianGrid stroke="#eaecf0" vertical={false} />
            <ReferenceArea y1={bands.high_from} y2={top} fill="var(--mc-violation-tint)" fillOpacity={0.7} ifOverflow="visible" />
            <ReferenceLine y={bands.medium_from} stroke="#98a2b3" strokeDasharray="4 4" label={{ value: 'Medium', position: 'insideTopLeft', fill: INK, fontSize: 11 }} />
            <ReferenceLine y={bands.high_from} stroke="#98a2b3" strokeDasharray="4 4" label={{ value: 'High', position: 'insideTopLeft', fill: INK, fontSize: 11 }} />
            <XAxis type="number" dataKey="t" domain={[0, end]} padding={{ left: MARK, right: 0 }} tickFormatter={clock} tick={{ fill: INK, fontSize: 12 }} tickLine={false} axisLine={{ stroke: '#d0d5dd' }} />
            <YAxis type="number" domain={[floor, top]} ticks={[0, bands.medium_from, bands.high_from]} tick={{ fill: INK, fontSize: 12 }} tickLine={false} axisLine={false} width={32} allowDataOverflow />
            <Line data={line} dataKey="score" type="stepAfter" stroke="var(--mc-accent)" strokeWidth={2.5} dot={false} isAnimationActive={false} />
            <Scatter data={dots} dataKey="y" isAnimationActive={false} shape={(p: { cx?: number; cy?: number; payload?: { kind: Kind } }) => <Marker cx={p.cx} cy={p.cy} kind={p.payload?.kind ?? 'violation'} />} />
          </ComposedChart>
        </ResponsiveContainer>
      </div>

      {kinds.length > 0 && (
        <ul className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-xs text-[var(--mc-text-2)]" aria-label="Marker key">
          {kinds.map((k) => (
            <li key={k} className="flex items-center gap-1.5">
              <svg width="16" height="16" viewBox="-10 -10 20 20" aria-hidden>
                <Marker kind={k} />
              </svg>
              {KIND_LABEL[k]}
            </li>
          ))}
        </ul>
      )}

      {/* The chart is a picture; this table carries the same readings for screen readers */}
      <table className="sr-only">
        <caption>Risk readings and flags over time</caption>
        <thead>
          <tr><th>Time</th><th>Risk</th><th>Band</th></tr>
        </thead>
        <tbody>
          {risk.map((r) => (
            <tr key={r.t_ms}><td>{clock(r.t_ms)}</td><td>{r.score}</td><td>{r.band}</td></tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
