import { Eraser, Pencil, PictureInPicture2, Settings2, Trash2 } from 'lucide-react'

import {
  ContextMenu,
  ContextMenuDivider,
  ContextMenuItem,
  ContextMenuLabel,
} from '@/components/ContextMenu'















export function GroupContextMenu({
  name,
  x,
  y,
  onSettings,
  onDelete,
  onClose,
}: {
  name: string
  x: number
  y: number
  onSettings: () => void
  onDelete: () => void
  onClose: () => void
}) {
  return (
    <ContextMenu x={x} y={y} onClose={onClose}>
      <ContextMenuLabel>{name}</ContextMenuLabel>

      <ContextMenuItem icon={<Settings2 size={13} className="text-ink-faint" />} onSelect={onSettings}>
        群设置
      </ContextMenuItem>

      <ContextMenuDivider />

      <ContextMenuItem icon={<Trash2 size={13} />} onSelect={onDelete} danger>
        删除群
      </ContextMenuItem>
    </ContextMenu>
  )
}












export function GroupThreadContextMenu({
  title,
  x,
  y,
  onRename,
  onOpenWindow,
  onClear,
  onDelete,
  onClose,
}: {
  title: string
  x: number
  y: number
  onRename: () => void
  onOpenWindow: () => void
  onClear: () => void
  onDelete: () => void
  onClose: () => void
}) {
  return (
    <ContextMenu x={x} y={y} onClose={onClose}>
      <ContextMenuLabel>{title}</ContextMenuLabel>

      <ContextMenuItem icon={<Pencil size={13} className="text-ink-faint" />} onSelect={onRename}>
        重命名对话
      </ContextMenuItem>
      <ContextMenuItem
        icon={<PictureInPicture2 size={13} className="text-ink-faint" />}
        onSelect={onOpenWindow}
      >
        打开独立窗口
      </ContextMenuItem>

      <ContextMenuDivider />

      <ContextMenuItem icon={<Eraser size={13} className="text-ink-faint" />} onSelect={onClear}>
        清空这条对话
      </ContextMenuItem>
      <ContextMenuItem icon={<Trash2 size={13} />} onSelect={onDelete} danger>
        删除这条对话
      </ContextMenuItem>
    </ContextMenu>
  )
}
