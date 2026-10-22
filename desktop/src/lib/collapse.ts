import { useState } from 'react'


















const RAIL_WIDTH_DELTA = 264 - 44







function apply(next: boolean, key: string): void {
  try {
    localStorage.setItem(key, next ? '1' : '0')
  } catch {
    
  }
  
  
  try {
    window.agentBridge?.resizeWindowBy?.(next ? -RAIL_WIDTH_DELTA : RAIL_WIDTH_DELTA)
  } catch {
    
  }
}

export function useCollapsed(
  key: string,
): [boolean, () => void, (next: boolean) => void] {
  const [collapsed, setCollapsedState] = useState(() => {
    try {
      return localStorage.getItem(key) === '1'
    } catch {
      return false
    }
  })

  const toggle = () => {
    setCollapsedState((prev) => {
      const next = !prev
      apply(next, key)
      return next
    })
  }

  







  const setCollapsed = (next: boolean) => {
    setCollapsedState((prev) => {
      if (prev === next) return prev
      apply(next, key)
      return next
    })
  }

  return [collapsed, toggle, setCollapsed]
}
