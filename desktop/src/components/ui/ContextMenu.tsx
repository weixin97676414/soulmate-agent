import clsx from 'clsx'
import type { ReactNode } from 'react'
import { useEffect, useLayoutEffect, useRef, useState } from 'react'

/**
 * 共用的右键 / 「⋯」菜单容器。
 *
 * ## 为什么要抽出来
 *
 * 单聊的对话列表、群聊的列表、搭子栏都要"在鼠标位置弹一张卡片式菜单"。
 * 这三处的定位与关闭逻辑（贴边回收、点空白关、Esc 关、拦住 mousedown 免得
 * 自己的点击先把自己关掉）**一个字都不该有差别** —— 各写一份的结果是
 * "在某个列表里菜单会跑出屏幕外"这种只在特定位置复现的怪毛病。
 * 项目里已经有同类教训（两套渲染逻辑迟早长歪），所以这里只留一份实现。
 *
 * ## 为什么不用系统菜单
 *
 * Electron 的 `Menu.popup` 是系统原生样式，与应用的三套皮肤（浅色 / 深色 / 暖阳）
 * 对不上，还会短暂夺走焦点。应用内自绘的这张卡片跟按钮、卡片是同一套令牌。
 */
export function ContextMenu({
  x,
  y,
  onClose,
  children,
  width = 184,
}: {
  /** 鼠标坐标（用 `fixed` 定位，所以直接用 clientX / clientY） */
  x: number
  y: number
  /** 点空白处或按 Esc 时调用 */
  onClose: () => void
  children: ReactNode
  width?: number
}) {
  const panelRef = useRef<HTMLDivElement>(null)
  const [position, setPosition] = useState({ left: x, top: y })

  // 贴边回收：鼠标在屏幕右下角右键时，菜单要往左上弹，而不是有一半在屏幕外。
  // 必须用 useLayoutEffect —— 在浏览器绘制前算好位置，否则会先闪一下错位。
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
      // 拦住 mousedown：否则"点别处关闭"的监听会在点击菜单项**之前**先关掉它，
      // 表现为"菜单项点了没反应"
      onMouseDown={(event) => event.stopPropagation()}
      className="fixed z-50 overflow-hidden rounded-[8px] border border-line bg-canvas py-1 shadow-[0_8px_24px_rgba(0,0,0,0.16)]"
    >
      {children}
    </div>
  )
}

/** 菜单顶部的标题（一般是"这条叫什么"），让用户确认自己点对了对象 */
export function ContextMenuLabel({ children }: { children: ReactNode }) {
  return (
    <div className="truncate px-3 pt-1 pb-1.5 text-[11px] text-ink-faint">{children}</div>
  )
}

/** 菜单项。`danger` 给删除这类不可逆操作用（红色文字 + 红色悬停底） */
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

/** 分组分隔线 */
export function ContextMenuDivider() {
  return <div className="my-1 border-t border-line-soft" />
}
