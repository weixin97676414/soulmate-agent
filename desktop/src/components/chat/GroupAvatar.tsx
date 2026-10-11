import { Users } from 'lucide-react'

import { resolveGroupAvatar } from '@/services/avatarPack'
import { useAvatarPreviewStore } from '@/stores/avatarPreviewStore'
import type { GroupProfile } from '@/types'

/**
 * 群头像：**一律是图片**，点一下能看大图。
 *
 * 与 `AssistantAvatar` 是同构的（取图 → 圆角按同比例算 → 点开大图 → 兜底占位），
 * 区别只在**没有"内置包"这一层**：四个出厂搭子是按 id 硬绑的图，而群没有出厂群，
 * 所以只有"自己设过的"和"没设过"两种（见 `resolveGroupAvatar`）。
 *
 * ## ⚠️ 为什么抽成组件而不是在页面里写
 *
 * 用到它的地方至少有两处 —— **群聊页的群列表 / 欢迎页**与**左上角标题栏**。
 * "圆角多大、能不能点开大图、没头像时显示什么"这几条必须处处一致：标题栏那个
 * 图标就挨在搭子头像旁边，两边的圆角只要差 1px，看起来就像"其中一个没对齐"。
 *
 * ## 没头像时不空着
 *
 * 群头像由 store 在载入后统一补（后端 `pickGroupAvatar` 保证有图），但补图是
 * 异步的 —— 打开应用的头几帧里 `avatar` 还是空串。这时显示品牌色方块 + `Users`，
 * 而不是留一格空白（那看起来像功能坏了）。
 */
export function GroupAvatar({
  group,
  size = 24,
  className = '',
}: {
  group: Pick<GroupProfile, 'id' | 'name' | 'avatar'>
  /** 边长（px）。圆角按 `BrandMark` 同一比例（6/22）算出来，与搭子头像对齐。 */
  size?: number
  className?: string
}) {
  const openPreview = useAvatarPreviewStore((state) => state.open)
  const src = resolveGroupAvatar(group)
  const radius = Math.round(size * (6 / 22))

  if (!src) {
    return (
      <span
        className={`flex shrink-0 items-center justify-center overflow-hidden bg-brand-soft text-brand select-none ${className}`}
        style={{ width: size, height: size, borderRadius: radius }}
      >
        <Users size={Math.max(10, Math.round(size * 0.5))} />
      </span>
    )
  }

  return (
    /*
      ⚠️ 用 `<span role="button">` 而**不是** `<button>`（改，与
      `AssistantAvatar` 同一处改动、同一套理由）：群头像也嵌在本身就是 button 的
      容器里（群聊页的群列表项），嵌套 button 会被浏览器与 React 同时挑出来。

      键盘那三件事要自己补：`role` + `tabIndex`、Enter/Space 的 `onKeyDown`、
      `focus-visible:ring-*`（原生 button 有默认焦点环，span 没有；Tailwind 的 reset
      又把 outline 清了，不补就看不见焦点）、以及 `inline-block`（span 默认 inline，宽高会失效）。

      ⚠️ `stopPropagation` 是必需的：不拦住的话，点头像会顺带把群切走 ——
      用户看完大图回来会以为自己选错了。
    */
    <span
      role="button"
      tabIndex={0}
      title="查看大图"
      aria-label={`查看「${group.name}」的群头像`}
      onClick={(event) => {
        event.stopPropagation()
        event.preventDefault()
        // 一并带上 groupId：大图里的「群设置」要靠它找到是哪个群
        openPreview(src, group.name, '', group.id)
      }}
      onKeyDown={(event) => {
        if (event.key !== 'Enter' && event.key !== ' ') return
        event.preventDefault()
        event.stopPropagation()
        openPreview(src, group.name, '', group.id)
      }}
      className={`inline-block shrink-0 cursor-zoom-in overflow-hidden focus-visible:ring-2 focus-visible:ring-brand/60 focus-visible:outline-none ${className}`}
      style={{ width: size, height: size, borderRadius: radius }}
    >
      <img
        src={src}
        alt={group.name}
        width={size}
        height={size}
        draggable={false}
        className="h-full w-full object-cover select-none"
      />
    </span>
  )
}
