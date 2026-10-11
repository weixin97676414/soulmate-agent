/**
 * 「我的资料」编辑弹窗 —— 点头像/昵称就能改。
 *
 * 产品要求修改入口有两个：
 * 1. 设置 → 外观 → 我的资料；
 * 2. **单聊 / 群聊里点自己的头像或昵称**（本组件）。
 *
 * 两个入口共用同一份数据（`lib/userProfile`），所以在这里改完，外观设置那一栏
 * 和消息气泡会立刻跟着变 —— 它是靠 `user-profile-changed` 事件广播的。
 */

import { useEffect, useRef, useState } from 'react'

import { AssistantAvatar } from '@/components/chat/AssistantFormModal'
import { Button, Field, Input, Modal } from '@/components/ui'
import { loadUserProfile, pickUserAvatar, saveUserProfile } from '@/lib/userProfile'
import { useAvatarPreviewStore } from '@/stores/avatarPreviewStore'

export function UserProfileDialog({ open, onClose }: { open: boolean; onClose: () => void }) {
  const [profile, setProfile] = useState(() => loadUserProfile())
  const fileRef = useRef<HTMLInputElement>(null)
  const openPreview = useAvatarPreviewStore((state) => state.open)

  // 每次打开都重新读一遍：另一个入口（外观设置）可能刚刚改过
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
          {/*
            头像点开看大图（与搭子头像同一个组件、同一套交互）。
            ⚠️ 传 `id: ''` 与空 assistantId：它不属于任何搭子，大图里因此
            **不会**显示「配置搭子」按钮 —— 那个按钮点开的是搭子的档案。
          */}
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
              // 清掉 value：不然后面选**同一个文件**不会再触发 change
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
