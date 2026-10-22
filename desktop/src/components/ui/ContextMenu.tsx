import clsx from 'clsx'
import type { ReactNode } from 'react'
import { useEffect, useLayoutEffect, useRef, useState } from 'react'

















export function ContextMenu({
  x,
  y,
  onClose,
  children,
  width = 184,
}: {
  
  x: number
  y: number
  
  onClose: () => void
  children: ReactNode
  width?: number
}) {
  const panelRef = useRef<HTMLDivElement>(null)
  const [position, setPosition] = useState({ left: x, top: y })

  
  
  useLayoutEffect(() => {
    const element = panelRef.current
    if (!element) return
    const rect = element.getBoundingClientRect()
    const margin = 8
    setPosition({
      left: Math.max(margin, Math.min(x, window.innerWidth - rect.width - margin)),
      top: Math.max(margin, Math.min(y, window.innerHeight - rect.height - margin)),
    })
  }, [x, y])

  useEffect(() => {
    const close = () => onClose()
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose()
    }
    window.addEventListener('mousedown', close)
    window.addEventListener('keydown', onKey)
    return () => {
      window.removeEventListener('mousedown', close)
      window.removeEventListener('keydown', onKey)
    }
  }, [onClose])

  return (
    <div
      ref={panelRef}
      style={{ left: position.left, top: position.top, width }}
      
      
      onMouseDown={(event) => event.stopPropagation()}
      className="fixed z-50 overflow-hidden rounded-[8px] border border-line bg-canvas py-1 shadow-[0_8px_24px_rgba(0,0,0,0.16)]"
    >
      {children}
    </div>
  )
}


export function ContextMenuLabel({ children }: { children: ReactNode }) {
  return (
    <div className="truncate px-3 pt-1 pb-1.5 text-[11px] text-ink-faint">{children}</div>
  )
}


export function ContextMenuItem({
  icon,
  children,
  onSelect,
  danger = false,
}: {
  icon?: ReactNode
  children: ReactNode
  onSelect: () => void
  danger?: boolean
}) {
  return (
    <button
      type="button"
      onClick={onSelect}
      className={clsx(
        'flex w-full items-center gap-2 px-3 py-1.5 text-left text-[12.5px]',
        danger ? 'text-danger hover:bg-danger-soft' : 'text-ink-soft hover:bg-hover hover:text-ink',
      )}
    >
      {icon ? <span className="shrink-0">{icon}</span> : null}
      {children}
    </button>
  )
}


export function ContextMenuDivider() {
  return <div className="my-1 border-t border-line-soft" />
}
