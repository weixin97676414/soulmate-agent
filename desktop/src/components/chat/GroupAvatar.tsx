import { Users } from 'lucide-react'

import { resolveGroupAvatar } from '@/services/avatarPack'
import { useAvatarPreviewStore } from '@/stores/avatarPreviewStore'
import type { GroupProfile } from '@/types'




















export function GroupAvatar({
  group,
  size = 24,
  className = '',
}: {
  group: Pick<GroupProfile, 'id' | 'name' | 'avatar'>
  
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
    











    <span
      role="button"
      tabIndex={0}
      title="查看大图"
      aria-label={`查看「${group.name}」的群头像`}
      onClick={(event) => {
        event.stopPropagation()
        event.preventDefault()
        
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
