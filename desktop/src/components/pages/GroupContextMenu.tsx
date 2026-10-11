import { Eraser, Pencil, PictureInPicture2, Settings2, Trash2 } from 'lucide-react'

import {
  ContextMenu,
  ContextMenuDivider,
  ContextMenuItem,
  ContextMenuLabel,
} from '@/components/ContextMenu'

/**
 * 群聊列表的右键 / 「⋯」菜单。
 *
 * 定位与关闭逻辑全部来自共用容器（`components/ContextMenu`）——
 * 单聊的对话列表用的是**同一份**，所以两边的贴边行为、Esc、点空白关闭
 * 永远一致。这里只负责"群聊有哪几项"。
 *
 * ## ⚠️ 这一份只管**整个群**
 *
 * 明确划了边界："群右键的功能是管整个群，对话名右键的功能是管
 * 这一个对话。" 于是「打开独立窗口」与「清空对话」**从这里剔除** —— 两者说的
 * 都是"某一条对话"，放在群上会让人以为要清掉整个群的记录。
 * 它们现在在 `GroupThreadContextMenu` 里。
 */
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

/**
 * 某一条**对话**的右键菜单。
 *
 * 与群菜单的分工写在 `GroupContextMenu` 的说明里：那边管整个群，这边只管
 * 这一条对话。四项都是"对这条对话做什么"：
 * 改名、单独开一个窗口、清空它的记录、删掉它。
 *
 * ⚠️ 「删除对话」与「清空对话」的区别要在**文案**上说清：前者把这条对话连同
 * 它的记录一起抹掉，后者只把记录清空、对话本身还在（还能继续聊）。
 * 两者都是不可逆的，所以删除那条用 `danger` 色调。
 */
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
