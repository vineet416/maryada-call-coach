import { Check } from 'lucide-react'

/** What the visitor may choose; the values are the ones the server knows (set_answered_by). */
export const ANSWERED_BY = [
  { value: 'borrower', label: 'Borrower' },
  { value: 'spouse', label: 'Spouse / family' },
  { value: 'neighbour', label: 'Other third party' },
] as const

/** "Who are you speaking with?": three radio options, operable with the arrow keys. The server's value is what shows. */
export function AnsweredBySelector({ value, onChoose, disabled = false }: { value: string; onChoose: (v: string) => void; disabled?: boolean }) {
  return (
    <fieldset disabled={disabled} className="card flex flex-col gap-2.5 p-3 sm:flex-row sm:items-center sm:gap-4 sm:px-5 sm:py-3">
      <legend className="sr-only">Who are you speaking with?</legend>
      <p className="text-[13.5px] font-semibold" aria-hidden>Who are you speaking with?</p>
      <div className="flex flex-1 flex-col gap-2 sm:flex-row">
        {ANSWERED_BY.map((o) => {
          const on = value === o.value
          return (
            <label
              key={o.value}
              className={`flex min-h-11 flex-1 cursor-pointer items-center gap-2.5 rounded-[10px] border px-3.5 py-2 text-[13.5px] font-medium has-[:focus-visible]:outline has-[:focus-visible]:outline-2 has-[:focus-visible]:outline-offset-2 has-[:focus-visible]:outline-[var(--mc-accent)] ${
                on ? 'border-[var(--mc-accent)] bg-[var(--mc-accent-tint)] text-[var(--mc-accent-dark)]' : 'border-[var(--mc-field)] bg-white text-[var(--mc-text-2)] hover:bg-[#f9fafb]'
              }`}
            >
              <input type="radio" name="answered-by" value={o.value} checked={on} onChange={() => onChoose(o.value)} className="sr-only" />
              <span aria-hidden className={`flex h-[18px] w-[18px] flex-none items-center justify-center rounded-full border ${on ? 'border-[var(--mc-accent)] bg-[var(--mc-accent)] text-white' : 'border-[var(--mc-field)] bg-white'}`}>
                {on && <Check className="h-3 w-3" strokeWidth={3} />}
              </span>
              {o.label}
            </label>
          )
        })}
      </div>
    </fieldset>
  )
}
