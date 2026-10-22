import { Check, Pencil, Trash2 } from 'lucide-react'
import { useEffect, useLayoutEffect, useRef, useState } from 'react'

import { AssistantAvatar } from '@/components/chat/AssistantFormModal'
import type { AssistantProfile } from '@/types'











export function AssistantContextMenu({
  profile,
  x,
  y,
  isActive,
  onEdit,
  onSetActive,
  onDelete,
  onClose,
}: {
  profile: AssistantProfile
  x: number
  y: number
  isActive: boolean
  onEdit: () => void
  onSetActive: () => void
  onDelete: () => void
  onClose: () => void
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

  const item = 'flex w-full items-center gap-2 px-3 py-1.5 text-left text-[12px]'

  return (
    <div
      ref={panelRef}
      style={{ left: position.left, top: position.top }}
      
      onMouseDown={(event) => event.stopPropagation()}
      className="fixed z-50 w-[184px] overflow-hidden rounded-[8px] border border-line bg-canvas py-1 shadow-[0_8px_24px_rgba(0,0,0,0.16)]"
    >
      <div className="truncate px-3 pt-1 pb-1.5 text-[11px] text-ink-faint">
        <span className="mr-1 inline-flex align-middle">
          <AssistantAvatar profile={profile} size={14} />
        </span>
        {profile.name}
      </div>

      <button type="button" className={`${item} text-ink hover:bg-hover`} onClick={onEdit}>
        <Pencil size={13} className="shrink-0 text-ink-faint" />
        编辑配置
      </button>

      {isActive ? null : (
        <button type="button" className={`${item} text-ink hover:bg-hover`} onClick={onSetActive}>
          <Check size={13} className="shrink-0 text-ink-faint" />
          切换到这个助手
        </button>
      )}

      <div className="my-1 border-t border-line-soft" />

      {
}
      {profile.locked ? null : (
        <button
          type="button"
          className={`${item} text-danger hover:bg-danger-soft`}
          onClick={onDelete}
        >
          <Trash2 size={13} className="shrink-0" />
          删除助手
        </button>
      )}
    </div>
  )
}
