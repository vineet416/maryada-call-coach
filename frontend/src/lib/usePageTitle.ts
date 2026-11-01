import { useEffect } from 'react'

/** Sets the browser tab title for the page, e.g. "Evaluation · Maryada". */
export function usePageTitle(title: string) {
  useEffect(() => {
    document.title = title
  }, [title])
}
