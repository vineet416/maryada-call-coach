/** Toggle switch (role="switch") drawn as in the design: 36 x 22 px, indigo when on. */
export function Switch({ checked, onChange, label, small = false }: { checked: boolean; onChange: (v: boolean) => void; label: string; small?: boolean }) {
  const w = small ? 34 : 36
  const h = small ? 20 : 22
  const d = small ? 16 : 18
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      aria-label={label}
      onClick={() => onChange(!checked)}
      className="relative inline-block flex-none rounded-full transition-colors"
      style={{ width: w, height: h, background: checked ? 'var(--mc-accent)' : '#98a2b3' }}
    >
      <span
        className="absolute top-0.5 rounded-full bg-white transition-all"
        style={{ width: d, height: d, left: checked ? w - d - 2 : 2 }}
      />
    </button>
  )
}
