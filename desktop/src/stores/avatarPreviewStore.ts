/**
 * 「点开头像看大图」的状态。
 *
 * ## 为什么是一个全局 store，而不是给每个头像传 `onClick`
 *
 * 头像出现在**十几个地方**（搭子栏、会话列表、气泡、群聊、设置、标题栏…）。
 * 逐处传回调意味着每加一个新的头像渲染点，都要记得把回调也接上 —— 漏掉的那处
 * 就是"这里的头像点不动"，而且没人会去逐个试。
 *
 * 改成头像组件自己去改这个 store：**所有** `<AssistantAvatar>` 自动都有大图，
 * 包括以后新加的。弹窗本身在 `App` 顶层渲染一个就够了。
 */

import { create } from 'zustand'

interface AvatarPreviewState {
  /** 正在看的那张大图（空串 = 没打开） */
  src: string
  /** 标题（搭子名 / 群名 / 用户自己的昵称） */
  name: string
  /**
   * 这张图属于哪个**搭子**（群头像与用户自己的都为空串）。
   *
   * 用来决定要不要显示「配置搭子」按钮 —— 点开大图的可能是一个搭子，
   * 也可能是用户自己（见 `lib/userProfile`）。对后者给一个"配置搭子"按钮
   * 只会让人点了不知道会打开谁。
   */
  assistantId: string
  /**
   * 这张图属于哪个**群**（搭子与用户自己的都为空串）。
   *
   * 与 `assistantId` 是**互斥**的两种身份：一个非空，另一个必为空。
   * 弹窗据此决定标题旁边挂哪个按钮 —— 搭子是「配置搭子」、群是「群设置」
   * （产品要求）。
   */
  groupId: string
  open: (src: string, name: string, assistantId?: string, groupId?: string) => void
  close: () => void
}

export const useAvatarPreviewStore = create<AvatarPreviewState>((set) => ({
  src: '',
  name: '',
  assistantId: '',
  groupId: '',
  open: (src, name, assistantId = '', groupId = '') => {
    if (src) set({ src, name, assistantId, groupId })
  },
  close: () => set({ src: '', name: '', assistantId: '', groupId: '' }),
}))
