import { useEffect, useRef } from 'react'
















export function usePanScroll() {
  const ref = useRef<HTMLDivElement>(null)
  useEffect(() => {
    const el = ref.current
    if (!el) return
    let panning = false
    let startX = 0
    let startY = 0
    let left = 0
    let top = 0

    const onDown = (event: MouseEvent) => {
      if (event.button !== 0) return
      const target = event.target as HTMLElement | null
      if (!target) return
      
      if (target.closest('button, input, textarea, select, a, label, code, .no-pan, .selectable')) {
        return
      }
      panning = true
      startX = event.clientX
      startY = event.clientY
      left = el.scrollLeft
      top = el.scrollTop
      el.style.cursor = 'grabbing'
    }
    const onMove = (event: MouseEvent) => {
      if (!panning) return
      el.scrollLeft = left - (event.clientX - startX)
      el.scrollTop = top - (event.clientY - startY)
    }
    const onUp = () => {
      if (!panning) return
      panning = false
      el.style.cursor = ''
    }

    el.addEventListener('mousedown', onDown)
    window.addEventListener('mousemove', onMove)
    window.addEventListener('mouseup', onUp)
    return () => {
      el.removeEventListener('mousedown', onDown)
      window.removeEventListener('mousemove', onMove)
      window.removeEventListener('mouseup', onUp)
    }
  }, [])
  return ref
}
