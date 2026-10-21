import { useLayoutEffect, useRef, useState } from 'react'



























































const STICK_THRESHOLD = 80
const SHOW_JUMP_THRESHOLD = 200







const TOP_EPSILON = 1

export function useStickToBottom(signature: unknown, resetKey?: unknown) {
  const ref = useRef<HTMLDivElement>(null)
  const stick = useRef(true)
  






  const lastTop = useRef(0)
  const [showJump, setShowJump] = useState(false)

  
  
  useLayoutEffect(() => {
    if (resetKey === undefined) return
    stick.current = true
    setShowJump(false)
  }, [resetKey])

  



  useLayoutEffect(() => {
    if (!stick.current) return
    const element = ref.current
    if (!element) return
    element.scrollTop = element.scrollHeight
    
    
    lastTop.current = element.scrollTop
  }, [signature])

  















  useLayoutEffect(() => {
    const element = ref.current
    if (!element) return
    if (typeof ResizeObserver === 'undefined') return
    const target = element.firstElementChild ?? element
    const observer = new ResizeObserver(() => {
      if (!stick.current) return
      element.scrollTop = element.scrollHeight
      lastTop.current = element.scrollTop
    })
    observer.observe(target)
    return () => observer.disconnect()
  }, [])

  const onScroll = () => {
    const element = ref.current
    if (!element) return

    



    if (Math.abs(element.scrollTop - lastTop.current) < TOP_EPSILON) return
    lastTop.current = element.scrollTop

    const distance = element.scrollHeight - element.scrollTop - element.clientHeight
    stick.current = distance < STICK_THRESHOLD
    setShowJump(distance >= SHOW_JUMP_THRESHOLD)
  }

  const jumpToBottom = () => {
    const element = ref.current
    if (!element) return
    element.scrollTop = element.scrollHeight
    
    lastTop.current = element.scrollTop
    stick.current = true
    setShowJump(false)
  }

  return { ref, showJump, onScroll, jumpToBottom }
}
