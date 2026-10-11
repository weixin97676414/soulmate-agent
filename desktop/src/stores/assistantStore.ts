import { create } from 'zustand'

import { BUILTIN_AVATARS, CUSTOM_AVATARS, pickAvatar } from '@/services/avatarPack'
import { useAppStore } from '@/stores/appStore'
import type { AssistantProfile } from '@/types'

interface AssistantState {
  assistants: AssistantProfile[]
  defaultAssistantId: string
  /**
   * 旧内置搭子 id → 新 id（``office`` → ``RelationBuddy``）。
   *
   * 只给**历史记录**用：审计日志里存的仍是旧 id（我们刻意不改写历史），
   * 界面靠它把旧 id 显示成搭子名。
   */
  legacyIds: Record<string, string>
  /** 当前生效的助手；null 表示不绑定（使用全局默认配置） */
  activeId: string | null
  /**
   * 用户是否**主动点选过**搭子。
   *
   * 为什么单独记这一个布尔：首启时 `activeId` 会被自动落到后端写死的默认搭子
   * （0.1.36 起是「搭子总管」BuddyManager，更早是 Relation Buddy / `office`），
   * 那是"系统选的"而不是"用户选的"。左上角要一直显示产品名 Soulmate Agent，直到
   * 用户自己点过某个搭子 —— 一进来就顶着一个用户没听说过的搭子名，会让人以为
   * 这应用默认属于别人。
   *
   * 只活在会话里、不做持久化：每次启动都从产品名开始。
   */
  picked: boolean
  loading: boolean

  /**
   * 一次"请打开某个搭子的编辑弹窗"的请求（空串 = 没有请求）。
   *
   * ⚠️ 为什么这个也要进 store：能打开编辑弹窗的入口有**三个**（搭子栏右键菜单、
   * 搭子栏的编辑按钮、头像大图里的「配置搭子」）。弹窗本体渲染在搭子栏里，
   * 另外两个入口够不着它的本地 state —— 各写一份就会出现"从这边打开的弹窗，
   * 从那边关不掉"，或者压根打不开。
   *
   * 用法是**一次性信号**：`AssistantRail` 读到非空就打开弹窗并立刻清掉，
   * 否则下次它重渲染时会莫名其妙又弹一次。
   */
  editRequestId: string
  openEditor: (id: string) => void
  clearEditRequest: () => void

  /**
   * 一次"请打开**新建**搭子流程"的请求（与 `editRequestId` 同一套机制）。
   *
   * ⚠️ 为什么另开一个字段，而不是复用 `editRequestId` 的空串：那个字段的约定是
   * "空串 = 没有请求"，用空串兼职"新建"会让两种意图分不开。而且两者的落点本来
   * 就不一样 —— 编辑直接开配置表单，新建要先问"手动 / 导入搭子包 / 导入搭子群"。
   *
   * ⚠️ 它是在**设置页取消之后**才需要的：原先输入栏那个「新建助手」按钮是
   * `setView('settings')`（指望设置页里的搭子栏来开新建），而设置页 
   * 已经不存在了。同样是一次性信号，`AssistantRail` 读到就开弹窗并立刻清掉。
   */
  newRequest: boolean
  openNewBuddy: () => void
  clearNewRequest: () => void

  load: () => Promise<void>
  setActive: (id: string | null) => void
  preview: (id: string, changes: Partial<AssistantProfile>) => void
  save: (profile: AssistantProfile) => Promise<void>
  remove: (id: string) => Promise<void>
}

function pickInitialAssistant(
  assistants: AssistantProfile[],
  defaultId: string,
): string | null {
  if (assistants.some((item) => item.id === defaultId)) return defaultId
  return assistants[0]?.id ?? null
}

/**
 * 给"没有头像、也不在内置头像包里"的搭子补一张，并写回后端。
 *
 * ## 为什么放在 `load` 里，而不是创建搭子时
 *
 * 「AI 创建搭子」走后端技能（`team_create_assistant`），**那条路完全不经过前端** ——
 * 前端没有机会在创建的那一刻塞头像进去。而"列表重新加载"是**所有**搭子都会过的
 * 唯一入口，不管它是用户手动建的、AI 建的、还是从搭子包导入的。
 *
 * ## 规则（产品要求）
 *
 * - **内置四个搭子不参与**：它们的头像由 `BUILTIN_AVATARS` 按 id 兜底，
 *   兜底不需要写盘，而且它们**不该占用自定义池** —— 那 24 张是留给用户自己的搭子的。
 * - 其余搭子：从自定义池挑一张**当前没被别人用过**的；全被占满了才允许重复
 *   （见 `pickAvatar`）。
 *
 * ## 为什么写回后端
 *
 * 不写回的话每次启动都会重新分配一遍，而 `used` 每次都从头算 —— 结果可能每次
 * 都是同一张（因为判断顺序一样），但一旦用户删掉某个搭子，剩下的就会集体换头像。
 * 写回去之后再也不会变。
 */
async function assignMissingAvatars(assistants: AssistantProfile[]): Promise<void> {
  const api = useAppStore.getState().api
  if (!api || CUSTOM_AVATARS.length === 0) return

  const used = new Set(assistants.map((item) => item.avatar).filter(Boolean))
  const pending = assistants.filter((item) => !item.avatar && !BUILTIN_AVATARS[item.id])
  if (pending.length === 0) return

  for (const profile of pending) {
    const avatar = pickAvatar(used, profile.id)
    if (!avatar) return
    used.add(avatar)
    try {
      await api.updateAssistant(profile.id, { ...profile, avatar })
      // 同步内存：不然这一帧它还是占位图，用户会看到"新搭子没头像"然后它自己变了
      useAssistantStore.setState((state) => ({
        assistants: state.assistants.map((item) =>
          item.id === profile.id ? { ...item, avatar } : item,
        ),
      }))
    } catch {
      // 补头像失败不该影响搭子能不能用；下次 load 会再试一次
    }
  }
}

export const useAssistantStore = create<AssistantState>((set, get) => ({
  assistants: [],
  defaultAssistantId: '',
  // 旧内置搭子 id → 新 id：只给**历史记录**（审计日志里存的是旧 id）解析名字用
  legacyIds: {},
  activeId: null,
  picked: false,
  loading: false,
  editRequestId: '',
  newRequest: false,

  openEditor: (id) => set({ editRequestId: id }),
  clearEditRequest: () => set({ editRequestId: '' }),
  openNewBuddy: () => set({ newRequest: true }),
  clearNewRequest: () => set({ newRequest: false }),

  load: async () => {
    const api = useAppStore.getState().api
    if (!api) return
    set({ loading: true })
    try {
      const payload = await api.getAssistants()
      set((state) => ({
        assistants: payload.assistants,
        defaultAssistantId: payload.default_assistant,
        legacyIds: payload.legacy_ids ?? {},
        // 首次加载（或当前助手被删掉）时落到默认助手，避免出现"没有助手"的空态
        activeId:
          state.activeId && payload.assistants.some((item) => item.id === state.activeId)
            ? state.activeId
            : pickInitialAssistant(payload.assistants, payload.default_assistant),
      }))
      // ⚠️ 给"还没有头像的搭子"补一张（见 assignMissingAvatars）。
      // **不 await**：补头像是一次额外的写盘，不该让整个搭子列表等它 ——
      // 它失败也不影响任何功能，只是那一张头像暂时是占位图。
      void assignMissingAvatars(payload.assistants)
    } finally {
      set({ loading: false })
    }
  },

  // 走到这里就说明是"用户主动选的"（点搭子栏 / 点某个会话 / 点「使用」「设为当前搭子」），
  // 所以顺手把 picked 置位；`load()` 里的自动落位**不经过这里**，不会误置。
  setActive: (id) => set({ activeId: id, picked: true }),

  /**
   * 只改**内存里**这一份搭子配置，不落盘。
   *
   * 给"快捷设置"卡片的实时预览用（头像与昵称要"实时替换"）：
   * 选完头像、打字改昵称的那一刻，侧栏那张卡片与对话区里的称呼就得跟着变，
   * 不能等点了保存才动。
   *
   * 与 `save()` 的分工必须说清楚：**`preview` 决定"这一帧看到什么"，`save` 才决定
   * "文件里写什么"**。所以预览过又没保存就离开的，调用方要负责把它撤回原样
   * （见 `QuickSetupCard` 的卸载清理）—— 否则会出现"界面显示新昵称、文件里是旧的"，
   * 下次启动又变回去，正是用户最不能接受的"改了没生效"。
   */
  preview: (id, changes) =>
    set((state) => ({
      assistants: state.assistants.map((item) => (item.id === id ? { ...item, ...changes } : item)),
    })),

  save: async (profile) => {
    const api = useAppStore.getState().api
    if (!api) return
    const exists = get().assistants.some((item) => item.id === profile.id)
    if (exists) {
      await api.updateAssistant(profile.id, profile)
    } else {
      await api.createAssistant(profile)
    }
    await get().load()
  },

  remove: async (id) => {
    const api = useAppStore.getState().api
    if (!api) return
    await api.deleteAssistant(id)
    if (get().activeId === id) set({ activeId: null })
    await get().load()
  },

}))

/** 取当前助手对象；未绑定或已被删除时返回 null（调用方回落到全局配置）。 */
export function useActiveAssistant(): AssistantProfile | null {
  return useAssistantStore((state) => {
    if (!state.activeId) return null
    return state.assistants.find((item) => item.id === state.activeId) ?? null
  })
}
