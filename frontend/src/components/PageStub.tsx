export function PageStub({ title, note }: { title: string; note: string }) {
  return (
    <section>
      <h1 className="mb-2 text-2xl font-semibold">{title}</h1>
      <p className="text-[var(--mc-muted)]">{note}</p>
    </section>
  )
}
