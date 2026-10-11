/**
 * 「我的资料」弹窗的开关。
 *
 * 与 `avatarPreviewStore` 同一个理由：能打开它的入口有两个（单聊气泡里点自己的
 * 头像/昵称、群聊里点自己的头像/昵称），而弹窗本体只在 `ChatView` 挂一次 ——
 * 各写一份本地 state 就会出现"从这边打开的弹窗，那边关不掉"。
 */

import { create } from 'zustand'

interface UserProfileDialogState {
  open: boolean
  show: () => void
  hide: () => void
}

export const useUserProfileDialogStore = create<UserProfileDialogState>((set) => ({
  open: false,
  show: () => set({ open: true }),
  hide: () => set({ open: false }),
}))
