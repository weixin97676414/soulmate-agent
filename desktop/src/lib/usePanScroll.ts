import { useEffect, useRef } from 'react'

/**
 * 「按住左键拖动即可平移页面」。
 *
 * ## 为什么提到这里
 *
 * 它原先长在 `SettingsView` 的内容容器上。产品要求把设置页里的八个
 * 分栏**提升成左栏的顶级页面**（设置页本身取消），于是那段外壳要跟着走 ——
 * 与其在九个页面各写一遍，不如提到一处、由 `App.tsx` 统一包一层容器。
 * 这样"哪个页面能拖动平移"这件事只有一个答案，不会出现某页能拖某页不能。
 *
 * ## 为什么只在这类区域启用
 *
 * 只在**以浏览为主**的页面启用：对话输入区绝不能启用，否则没法用鼠标选字。
 * 交互元素（按钮 / 输入框 / 链接 / 可选中文字）一律跳过 —— 拖动不能劫持它们的点击。
 */
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
      // 这些地方按下左键各有自己的含义（点击、选字、拉滚动条），不能抢
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
