import { useEffect, useRef, type RefObject } from 'react'

const FOCUSABLE = 'a[href],button:not([disabled]),input:not([disabled]),select:not([disabled]),textarea:not([disabled]),[tabindex]:not([tabindex="-1"])'

/**
 * While active: Tab and Shift+Tab cycle inside the container, and when it closes focus goes back to the element
 * that opened it (or to `fallback` when that element is gone).
 */
export function useFocusTrap(box: RefObject<HTMLElement | null>, active: boolean, fallback?: () => HTMLElement | null) {
  const fb = useRef(fallback)
  fb.current = fallback
  useEffect(() => {
    if (!active) return
    const opener = document.activeElement as HTMLElement | null
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== 'Tab' || !box.current) return
      const items = [...box.current.querySelectorAll<HTMLElement>(FOCUSABLE)].filter((el) => el.offsetParent !== null)
      if (items.length === 0) {
        e.preventDefault()
        box.current.focus()
        return
      }
      const first = items[0]
      const last = items[items.length - 1]
      const at = document.activeElement
      if (e.shiftKey && (at === first || at === box.current)) {
        e.preventDefault()
        last.focus()
      } else if (!e.shiftKey && at === last) {
        e.preventDefault()
        first.focus()
      } else if (!box.current.contains(at)) {
        e.preventDefault()
        first.focus()
      }
    }
    document.addEventListener('keydown', onKey)
    return () => {
      document.removeEventListener('keydown', onKey)
      const back = opener && document.contains(opener) ? opener : (fb.current?.() ?? null)
      back?.focus?.()
    }
  }, [active, box])
}
