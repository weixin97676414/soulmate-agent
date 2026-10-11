import { Check, Pencil, Trash2 } from 'lucide-react'
import { useEffect, useLayoutEffect, useRef, useState } from 'react'

import { AssistantAvatar } from '@/components/chat/AssistantFormModal'
import type { AssistantProfile } from '@/types'

/**
 * 助手的右键菜单。
 *
 * 用应用内自绘面板而不是系统菜单：本项目全仓没有一处用系统原生菜单，
 * 而系统菜单的字体、圆角、深浅色都跟着 Windows 走，在深色主题下尤其突兀。
 *
 * 定位方式与 `SessionList` 的「更多」菜单同源，区别只是这个要贴着鼠标位置弹，
 * 所以用 `fixed` + 坐标，并**在贴边时往回收**（右键点在屏幕最底下的那个助手上时，
 * 菜单不能跑到视口外面去）。
 */
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
    // 先按鼠标位置放，再在贴边时往回收 —— 用 layout effect 是为了不出现
    // "先闪到屏幕外再跳回来"的一帧
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
    // 点任何地方都关掉。打开这个菜单的那次右键（mousedown 已先发生）不会误触发。
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
      // 拦住 mousedown，否则上面那个"点别处关闭"的监听会在点击菜单项之前先关掉它
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

      {/* 内置搭子**不画删除项**（内置 buddy 不允许用户删除）。
          后端 409 兜底仍在，但界面摆一个"点了必报错"的删除项，比不画更糟。 */}
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
