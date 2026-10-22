










import { useEffect, useRef, useState } from 'react'

import { AssistantAvatar } from '@/components/chat/AssistantFormModal'
import { Button, Field, Input, Modal } from '@/components/ui'
import { loadUserProfile, pickUserAvatar, saveUserProfile } from '@/lib/userProfile'
import { useAvatarPreviewStore } from '@/stores/avatarPreviewStore'

export function UserProfileDialog({ open, onClose }: { open: boolean; onClose: () => void }) {
  const [profile, setProfile] = useState(() => loadUserProfile())
  const fileRef = useRef<HTMLInputElement>(null)
  const openPreview = useAvatarPreviewStore((state) => state.open)

  
  useEffect(() => {
    if (open) setProfile(loadUserProfile())
  }, [open])

  if (!open) return null

  const commit = (next: { nickname?: string; avatar?: string }) => {
    const merged = { ...profile, ...next }
    setProfile(merged)
    saveUserProfile(merged)
  }

  return (
    <Modal
      open
      onClose={onClose}
      title="我的资料"
      width="max-w-[440px]"
      footer={
        <div className="flex w-full justify-end">
          <Button variant="primary" onClick={onClose}>
            完成
          </Button>
        </div>
      }
    >
      <div className="flex flex-col gap-3">
        <div className="flex items-center gap-3">
          {



}
          <AssistantAvatar
            profile={{ avatar: profile.avatar, emoji: '', name: profile.nickname, id: '' }}
            size={56}
          />
          <div className="flex flex-wrap gap-2">
            <Button onClick={() => fileRef.current?.click()}>选择图片</Button>
            <Button
              onClick={() =>
                openPreview(profile.avatar, profile.nickname || '宿主', '')
              }
              disabled={!profile.avatar}
            >
              看大图
            </Button>
          </div>
          <input
            ref={fileRef}
            type="file"
            accept="image/*"
            className="hidden"
            onChange={(event) => {
              const file = event.target.files?.[0]
              
              event.target.value = ''
              if (file) void pickUserAvatar(file).then((avatar) => commit({ avatar }))
            }}
          />
        </div>

        <Field label="昵称" hint="单聊与群聊里别人看到的称呼">
          <Input
            value={profile.nickname}
            placeholder="宿主"
            onChange={(event) => commit({ nickname: event.target.value })}
          />
        </Field>
      </div>
    </Modal>
  )
}
