import { create } from 'zustand'

import { addFilesTo, readyFileIds } from '@/services/attachments'
import { pickGroupAvatar } from '@/services/avatarPack'
import { useAppStore } from '@/stores/appStore'
import { useNotificationStore } from '@/stores/notificationStore'
import type { GroupProfile, GroupThread, GroupUpdate, PendingAttachment } from '@/types'

const newId = (): string =>
  typeof crypto !== 'undefined' && 'randomUUID' in crypto
    ? crypto.randomUUID()
    : `b-${Date.now()}-${Math.random().toString(16).slice(2)}`

export type BubbleKind = 'user' | 'assistant' | 'summary' | 'system'

export interface Bubble {
  id: string
  kind: BubbleKind
  /** 发言人搭子 id（用于按 id 显示头像/昵称） */
  assistantId?: string
  name: string
  content: string
  streaming?: boolean
  badge?: string
}

// --------------------------------------------------------------------------- //
// 运行时对象：不放进 store，避免触发无谓渲染
// --------------------------------------------------------------------------- //
let abortController: AbortController | null = null
/** 当前正在流式接收的那条气泡（`delta` 事件只带文本、不带 id，靠它定位） */
let activeBubbleId = ''

/**
 * 还没选定群时收到的**广播事件**先存这里，选定后补放。
 *
 * 为什么需要它：只读观察窗是"先订阅事件流、再去 selectGroup"的。窗口刚打开的那一瞬
 * `selectedId` 还是 null，而此时后台讨论的 `speaker` / `delta` / `message` 已经在推 ——
 * 原先这些事件被直接丢掉，于是**第一个发言者的内容永远显示不出来**
 * （实测反馈就是这个：观察窗里第一条不显示，群聊页正常）。
 * 群聊页不会撞上：它本来就是发起方，事件与选中几乎同时发生。
 *
 * 上限是为了"窗口开着但用户从没选群"这种极端情况：不设上限会一直攒下去。
 */
let pendingRemote: Array<{
  groupId: string
  threadId: string
  event: string
  data: Record<string, unknown>
}> = []
const MAX_PENDING_REMOTE = 500

/**
 * 把一条事件作用到气泡列表上。
 *
 * **实时接收与历史回放共用这一个函数** —— 这样"从数据库恢复出来的记录"和
 * "刚讨论完的记录"长得完全一样，不会出现两套渲染逻辑慢慢长歪的问题
 * （群聊记录现在会落库并从库里重放，见后端 `storage/group_events.py`）。
 */
/**
 * 定位一条 delta / message / summary 该写到哪个气泡。
 *
 * 优先按 `assistant_id` 从后往前找「该搭子最近一个非用户 / 非系统气泡」：
 * 这样补放缓冲里的 delta 不再依赖模块级游标，也不会因为 speaker 重复建气泡
 * 而写错搭子（观察窗首条丢失的根因之一）。找不到再回退到 `activeBubbleId`
 * （前台实时流的正常路径仍靠它）。
 */
function findTargetBubble(bubbles: Bubble[], assistantId: string): string {
  if (assistantId) {
    for (let i = bubbles.length - 1; i >= 0; i--) {
      const item = bubbles[i]
      if (item.assistantId === assistantId && item.kind !== 'user' && item.kind !== 'system') {
        return item.id
      }
    }
  }
  return activeBubbleId
}

export function applyGroupEvent(bubbles: Bubble[], event: string, data: Record<string, unknown>): Bubble[] {
  const push = (bubble: Bubble) => [...bubbles, bubble]
  switch (event) {
    case 'topic':
      return push({ id: newId(), kind: 'user', name: '我', content: String(data.content ?? '') })
    case 'speaker': {
      activeBubbleId = newId()
      return push({
        id: activeBubbleId,
        kind: data.summary ? 'summary' : 'assistant',
        assistantId: String(data.assistant_id ?? ''),
        name: String(data.name ?? ''),
        content: '',
        streaming: true,
        badge: data.summary ? '最终总结' : undefined,
      })
    }
    case 'delta': {
      const target = findTargetBubble(bubbles, String(data.assistant_id ?? ''))
      return bubbles.map((item) =>
        item.id === target
          ? { ...item, content: item.content + String(data.text ?? '') }
          : item,
      )
    }
    case 'message':
    case 'summary': {
      const target = findTargetBubble(bubbles, String(data.assistant_id ?? ''))
      return bubbles.map((item) =>
        item.id === target
          ? { ...item, content: String(data.content ?? item.content), streaming: false }
          : item,
      )
    }
    case 'vote_request':
      return push({
        id: newId(),
        kind: 'system',
        name: '',
        content: `${data.name} 发起了结束投票${data.reason ? `：${data.reason}` : ''}`,
      })
    case 'vote':
      return push({
        id: newId(),
        kind: 'system',
        name: '',
        content: `${data.name} ${data.agree ? '同意结束' : '不同意结束'}`,
      })
    case 'vote_result':
      return push({
        id: newId(),
        kind: 'system',
        name: '',
        content: data.passed ? '投票通过，由发起者总结。' : '投票未通过，继续讨论。',
      })
    case 'error':
      return push({
        id: newId(),
        kind: 'system',
        name: '',
        content: `出错了：${String(data.message ?? '')}`,
      })
    case 'out_of_scope': {
      // 越权：谁用了不属于自己职责的工具（产品要求"把越权晾出来"）
      const owners = Array.isArray(data.owners) ? (data.owners as string[]) : []
      return push({
        id: newId(),
        kind: 'system',
        name: '',
        content:
          `⚠️ ${String(data.name ?? '')} 调用了 ${String(data.skill ?? '')}（不在它的职责范围内）` +
          (owners.length ? `。这活本来是：${owners.join('、')}。` : '。'),
      })
    }
    case 'review': {
      const passed = data.passed === true
      return push({
        id: newId(),
        kind: 'system',
        name: '',
        content: passed
          ? `✅ ${String(data.name ?? '')} 验收通过。`
          : `↩️ ${String(data.name ?? '')} 打回给总管重新安排${
              data.reason ? `：${String(data.reason)}` : ''
            }`,
      })
    }
    case 'vote_denied':
      return push({
        id: newId(),
        kind: 'system',
        name: '',
        content: `${String(data.name ?? '')} 发起的结束投票无效：${String(data.reason ?? '')}`,
      })
    default:
      // done 之类的事件不改气泡内容
      return bubbles
  }
}

interface GroupState {
  groups: GroupProfile[]
  loading: boolean
  selectedId: string | null
  /**
   * 当前群的「对话」列表（一个群可以有多条，最近有动静的排前面）。
   *
   * 与单聊的 `sessions` 同构：单聊那边是"一个搭子多条会话"，这边是"一个群多条对话"。
   */
  threads: GroupThread[]
  /**
   * 正在看的那条对话。
   *
   * `null` 只在"还没选群 / 列表还没拉回来"的极短窗口里出现 —— 所有读操作
   * （发话题、清空、接收广播）都以它为准，所以拿不到时宁可什么都不做，
   * 也不要落到"最近一条"上：那会在用户还没看清界面时就把内容写进某条对话。
   */
  activeThreadId: string | null
  bubbles: Bubble[]
  busy: boolean
  /** 后端是否真的在持久化（内存模式时为 false，界面要如实说明） */
  persistent: boolean
  /** 正在讨论的群 id；切到别的页面再回来时据此恢复"进行中"的观感 */
  runningGroupId: string | null
  /**
   * 群聊的草稿与附件。
   *
   * 放在 store 而不是页面里（与 bubbles 同理）：用户写到一半切去别的页面，
   * 回来发现输入框被清空 —— 那是很可能丢内容的体验（写了一大段话就没了）。
   */
  draft: string
  attachments: PendingAttachment[]

  loadGroups: () => Promise<void>
  selectGroup: (id: string) => Promise<void>
  createGroup: (payload: {
    name: string
    member_assistant_ids: string[]
    speaking_order?: string[]
    /** 群头像（用户自己上传的 data URL）；留空由前端按规则自动配一张 */
    avatar?: string
  }) => Promise<GroupProfile | null>
  deleteGroup: (id: string) => Promise<void>
  /** 局部更新群设置；返回更新后的群（失败返回 null，并已弹提示） */
  updateGroup: (id: string, patch: GroupUpdate) => Promise<GroupProfile | null>
  clearMessages: (id?: string, threadId?: string) => Promise<void>
  /** 切到另一条对话（重新拉它的记录并重放） */
  selectThread: (threadId: string) => Promise<void>
  /**
   * 开一条**新对话**并切过去（输入栏左下角那个按钮）。
   *
   * 只是新建 + 切换，**不发送任何内容**：真正的会话由后端在首次抛出话题时
   * 落到这条对话上（与单聊 `startNewSession` 的思路一致 —— 用户点一下不该
   * 在库里留下一堆空记录）。
   */
  startNewThread: () => Promise<void>
  deleteThread: (threadId: string) => Promise<void>
  renameThread: (threadId: string, title: string) => Promise<void>
  /**
   * 重拉某个群的对话列表。
   *
   * 由 `group_threads_changed` 事件触发 —— **AI 也能建/改名/清空/删除群对话**
   * ，它改完之后用户正开着的那个列表必须跟着变，
   * 否则他会以为 AI 什么都没做。
   */
  reloadThreads: (groupId: string) => Promise<void>
  /**
   * 「请求打开某个群的群设置弹窗」。
   *
   * ⚠️ 为什么要绕 store：那个 Modal 在 `GroupChatPage` 里（它是页面的局部 state），
   * 而发起请求的是 App 顶层的头像大图弹窗 —— 两者之间没有可用的调用路径。
   * 页面订阅这个字段，看到非空就打开自己的弹窗并清掉它。
   *
   * 与「配置搭子」按钮走 `assistantStore.openEditor` 是同一个套路。
   */
  settingsRequestId: string | null
  requestGroupSettings: (groupId: string) => void
  clearGroupSettingsRequest: () => void
  /**
   * 把一条**后台讨论**的事件作用到气泡上。
   *
   * 后台讨论没有界面订阅它的那条 SSE 流（见 core 的 `agent/orchestrator.py`），
   * 事件改从常驻的 `/v1/events` 广播过来。走的是与 `/discuss` **同一个**
   * `applyGroupEvent`：这样"看直播"和"自己发起讨论"渲染出来完全一样。
   */
  applyRemoteEvent: (
    groupId: string,
    threadId: string,
    event: string,
    data: Record<string, unknown>,
  ) => void
  setDraft: (value: string) => void
  addFiles: (files: File[]) => Promise<void>
  removeAttachment: (id: string) => void
  discuss: (topic?: string) => Promise<void>
  stop: () => void
}

/**
 * 群聊状态。
 *
 * ⚠️ 这些状态**必须放在 store 而不是页面组件里**（反馈 #6）：
 * 原来 `groups/bubbles/busy` 都是 `GroupChatPage` 的局部 state，
 * 用户切到别的页面（组件卸载）再回来，讨论记录就被清空了 ——
 * 而正在进行的讨论甚至会被静默丢弃。
 */
/**
 * 给**还没有头像**的群补一张（产品要求群也有头像）。
 *
 * 与搭子那套（`assistantStore.assignMissingAvatars`）是同一个做法，也同一个理由：
 * 群头像库是**前端随包的 24 张图**（`services/avatarPack.ts`），后端根本不知道
 * 有哪几张可选。所以"选哪张"只能在这一侧做 —— 后端收到的是一个已经定好的
 * data URL 或空串，它不参与挑选。
 *
 * 规则是产品定的："优先选择与现有群不重复的，如果现有群用了所有的头像，
 * 则随机选一张即可"（见 `pickGroupAvatar`）。
 *
 * ⚠️ 写回后端**失败不弹提示**：用户没做错任何事（他可能只是离线了一下），
 * 这次显示也没受影响，下次启动会再补一次。弹一个他无法处理的错误只会让他困惑。
 */
async function assignMissingGroupAvatars(
  set: (partial: Partial<GroupState>) => void,
  get: () => GroupState,
  groups: GroupProfile[],
): Promise<void> {
  const api = useAppStore.getState().api
  if (!api) return

  // 已经有头像的那些先**占住位置** —— "优先不与现有群重复"就是靠这份 used。
  // 必须包含**本次拉回来的全部**群（不只是没头像的），否则会挑出一张
  // 别的群正在用的。
  const used = new Set(groups.map((item) => item.avatar).filter(Boolean))
  const patched: GroupProfile[] = []
  for (const group of groups) {
    if (group.avatar) continue
    const picked = pickGroupAvatar(used, group.id)
    if (!picked) continue
    used.add(picked)
    patched.push({ ...group, avatar: picked })
  }
  if (patched.length === 0) return

  // 先就地更新界面（用户马上能看到头像），再逐个写回后端
  const byId = new Map(patched.map((item) => [item.id, item]))
  set({ groups: get().groups.map((item) => byId.get(item.id) ?? item) })

  for (const group of patched) {
    try {
      await api.updateGroup(group.id, { avatar: group.avatar })
    } catch {
      /* 写回失败不影响本次显示，下次启动会再补一次 */
    }
  }
}

export const useGroupStore = create<GroupState>((set, get) => ({
  groups: [],
  loading: false,
  selectedId: null,
  threads: [],
  activeThreadId: null,
  bubbles: [],
  busy: false,
  persistent: true,
  runningGroupId: null,
  draft: '',
  attachments: [],
  settingsRequestId: null,

  loadGroups: async () => {
    const api = useAppStore.getState().api
    if (!api) return
    set({ loading: true })
    try {
      const payload = await api.getGroups()
      set((state) => ({
        groups: payload.groups,
        // 当前选中的群被删掉时清空选择，避免右侧停在一个不存在的群上
        selectedId: payload.groups.some((item) => item.id === state.selectedId)
          ? state.selectedId
          : (payload.groups[0]?.id ?? null),
      }))
      // 补头像要在选群**之前**：用户第一眼看到的就是左边那一列，
      // 等他点进去之后再补，列表会当着面跳一下
      await assignMissingGroupAvatars(set, get, payload.groups)
      const selected = get().selectedId
      if (selected && get().bubbles.length === 0) await get().selectGroup(selected)
    } catch (error) {
      useNotificationStore.getState().push({
        level: 'error',
        title: '群聊列表加载失败',
        message: error instanceof Error ? error.message : String(error),
      })
    } finally {
      set({ loading: false })
    }
  },

  selectGroup: async (id) => {
    const api = useAppStore.getState().api
    if (!api) return
    // 换群时清掉草稿与附件：带着上一个群的附件发言，多半不是用户的本意
    set({
      selectedId: id,
      threads: [],
      activeThreadId: null,
      bubbles: [],
      draft: '',
      attachments: [],
    })
    try {
      // 先拉对话列表，再进**最近有动静**的那条 —— 也就是用户上次离开时看着的那条。
      // 后端在一条都没有时会先建一条，所以这里拿到的一定非空。
      const listed = await api.getGroupThreads(id)
      // 期间用户可能又切了别的群：只在仍是当前选中时才写
      if (get().selectedId !== id) return
      const first = listed.threads[0]
      if (!first) return
      set({ threads: listed.threads })
      await get().selectThread(first.id)
    } catch (error) {
      useNotificationStore.getState().push({
        level: 'error',
        title: '群对话列表加载失败',
        message: error instanceof Error ? error.message : String(error),
      })
    }
  },

  selectThread: async (threadId) => {
    const api = useAppStore.getState().api
    const groupId = get().selectedId
    if (!api || !groupId) return
    // 切对话时同样清草稿与附件：它们是**这条对话**的上下文，带到另一条上是错位的
    set({ activeThreadId: threadId, bubbles: [], draft: '', attachments: [] })
    try {
      const payload = await api.getGroupMessages(groupId, threadId)
      // 重放：与实时接收走同一个 applyGroupEvent，所以两边的观感完全一致。
      //
      // ⚠️ `applyGroupEvent` 靠模块级的 `activeBubbleId` 定位"正在写的这条"。
      // 重放期间必须把游标**存下来再还回去** —— 否则用户在"A 群正在讨论时"
      // 切到 B 群看历史，重放会把游标指到 B 群的气泡上，
      // A 群后续的 delta 就会写进 B 群的消息里。
      const savedCursor = activeBubbleId
      let bubbles: Bubble[] = []
      for (const item of payload.events) {
        bubbles = applyGroupEvent(bubbles, item.event, item.data)
      }
      // 重放出来的气泡不该带着"正在输入"的光标
      bubbles = bubbles.map((item) => ({ ...item, streaming: false }))
      // 期间用户可能又切了别的群 / 别的对话 —— 只在仍是当前选中时才写入
      if (get().selectedId !== groupId || get().activeThreadId !== threadId) {
        activeBubbleId = savedCursor
        return
      }
      // 重放完成后再把"还没选群时攒下的广播事件"补放上去 —— 顺序很关键：
      // 重放给出的是**已经落库**的部分，缓冲里是那之后（或重放期间）到达的增量。
      //
      // ⚠️ 游标 `activeBubbleId` **要等补放完之后再恢复**：观察窗是"先订阅广播、再
      // selectGroup"的，讨论刚开始时库里只落库了 `speaker`（空气泡）、`message` 还没落库。
      // 重放 speaker 会把游标指到那个空气泡；若像以前那样在补放**之前**就 `finally` 恢复
      // 成 savedCursor，缓冲里的 `delta`/`message` 会拿旧游标去匹配、匹配不到 → 第一个
      // 发言者的气泡永远是空的（群聊页正常，因为它点进去时 message 已落库）。
      let merged = bubbles
      // ⚠️ 按 **(群, 对话)** 取缓冲：只按群取的话，用户在另一条对话里打开时
      // 会把这条对话的增量补到那条上 —— 表现为"我没聊过的话突然出现在这里"。
      const buffered = pendingRemote.filter(
        (item) => item.groupId === groupId && item.threadId === threadId,
      )
      pendingRemote = pendingRemote.filter(
        (item) => !(item.groupId === groupId && item.threadId === threadId),
      )
      // 补放**只补 delta**：speaker / message / summary / vote 等事件在"先落库再广播"
      // 的时序下已经包含在库重放结果里了，再补一次会重复建气泡（观察窗首条丢失的
      // 另一半根因）。delta 不落库、且带 assistant_id，按搭子定位补进去即可。
      for (const item of buffered) {
        if (item.event !== 'delta') continue
        merged = applyGroupEvent(merged, item.event, item.data)
      }
      // 游标只在"确实有别的群在流式"时才需要恢复（群聊页切群看历史的场景）；
      // 观察窗 / 独立窗口是新窗口、savedCursor 是空串，恢复成空串会让后续实时
      // delta / message 匹配不到气泡，所以这里**保持不恢复**，让游标停在最后那个
      // speaker 气泡上。
      if (savedCursor) {
        activeBubbleId = savedCursor
      }
      set({ bubbles: merged, persistent: payload.persistent })
    } catch (error) {
      useNotificationStore.getState().push({
        level: 'error',
        title: '群聊记录加载失败',
        message: error instanceof Error ? error.message : String(error),
      })
    }
  },

  createGroup: async (payload) => {
    const api = useAppStore.getState().api
    if (!api) return null
    const group = await api.createGroup(payload)
    await get().loadGroups()
    // ⚠️ 新群的对话列表还没拉过，这里**不能**只清 bubbles —— 否则 `activeThreadId`
    // 还是上一个群留下的值，用户在新群里发的第一句话会被判成"不属于这条对话"
    // 而静默丢掉。交给 `selectGroup` 走完整流程（拉列表 → 进第一条）。
    await get().selectGroup(group.id)
    return group
  },

  deleteGroup: async (id) => {
    const api = useAppStore.getState().api
    if (!api) return
    await api.deleteGroup(id)
    if (get().selectedId === id) {
      set({ selectedId: null, threads: [], activeThreadId: null, bubbles: [] })
    }
    await get().loadGroups()
  },

  updateGroup: async (id, patch) => {
    const api = useAppStore.getState().api
    if (!api) return null
    try {
      const group = await api.updateGroup(id, patch)
      // 就地替换那一条，而不是 `loadGroups()` 全量重拉：
      // 用户正在看这个群，全量刷新会让列表重建、滚动位置跳一下。
      set((state) => ({
        groups: state.groups.map((item) => (item.id === group.id ? group : item)),
      }))
      return group
    } catch (error) {
      // **必须报出来**：这是"设置没保存成功"，而界面上的开关会自己弹回去，
      // 不提示的话用户只会觉得"这个开关坏了"
      useNotificationStore.getState().push({
        level: 'error',
        title: '群设置保存失败',
        message: error instanceof Error ? error.message : String(error),
      })
      return null
    }
  },

  clearMessages: async (id, threadId) => {
    const api = useAppStore.getState().api
    const target = id ?? get().selectedId
    const thread = threadId ?? get().activeThreadId ?? ''
    if (!api || !target) return
    // ⚠️ 清的是**这条对话**，不是整个群（一个群可以有多条对话）。
    // 传空串时后端会落到"最近一条"，所以老调用点也不会误伤别的对话。
    await api.clearGroupMessages(target, thread)
    if (get().selectedId === target && get().activeThreadId === (thread || get().activeThreadId)) {
      set({ bubbles: [] })
    }
  },

  startNewThread: async () => {
    const api = useAppStore.getState().api
    const groupId = get().selectedId
    if (!api || !groupId) return
    try {
      const created = await api.createGroupThread(groupId)
      if (get().selectedId !== groupId) return
      // 新对话排最前：列表顺序是 `updated_at` 降序，而它的时间就是刚刚
      set((state) => ({ threads: [created, ...state.threads] }))
      // ⚠️ 走 `selectThread` 而不是"就地清空 bubbles"：它会把 `activeThreadId`
      // 一起改过去。只清气泡的话，用户在新对话里说的第一句话仍然挂在**旧对话**上
      // —— 界面上看起来正常，但他回头去旧对话里找那句话是找不到的。
      await get().selectThread(created.id)
    } catch (error) {
      useNotificationStore.getState().push({
        level: 'error',
        title: '新建对话失败',
        message: error instanceof Error ? error.message : String(error),
      })
    }
  },

  deleteThread: async (threadId) => {
    const api = useAppStore.getState().api
    const groupId = get().selectedId
    if (!api || !groupId) return
    try {
      await api.deleteGroupThread(groupId, threadId)
    } catch (error) {
      useNotificationStore.getState().push({
        level: 'error',
        title: '删除对话失败',
        message: error instanceof Error ? error.message : String(error),
      })
      return
    }
    const remaining = get().threads.filter((item) => item.id !== threadId)
    set({ threads: remaining })
    if (get().activeThreadId !== threadId) return
    // 删掉的正是当前这条 → 落到剩下的第一条；一条都不剩就让后端再建一条
    // （与列表接口的行为一致：群里永远至少有一条对话等着用户）
    if (remaining[0]) {
      await get().selectThread(remaining[0].id)
      return
    }
    await get().startNewThread()
  },

  requestGroupSettings: (groupId) =>
    set({ selectedId: get().selectedId ?? groupId, settingsRequestId: groupId }),

  clearGroupSettingsRequest: () => set({ settingsRequestId: null }),

  reloadThreads: async (groupId) => {
    const api = useAppStore.getState().api
    if (!api) return
    // 只刷**当前正看着的那个群**：别的群等用户切过去时会自然拉到最新的，
    // 这里跟着刷只是白打一次请求
    if (get().selectedId !== groupId) return
    try {
      const listed = await api.getGroupThreads(groupId)
      if (get().selectedId !== groupId) return
      set({ threads: listed.threads })
      // ⚠️ 当前正看的那条被 AI 删了 → 落到第一条。
      // 不处理的话界面会停在一个**已经不存在的对话**上：用户在里面说一句话，
      // 后端按 `thread_id` 找不到那条对话，那句话就"发出去但什么都没发生"。
      const active = get().activeThreadId
      if (active && !listed.threads.some((item) => item.id === active)) {
        const fallback = listed.threads[0]
        if (fallback) await get().selectThread(fallback.id)
      }
    } catch {
      // 列表没刷上不影响使用（用户切一下群就会重拉），不值得弹提示打断他
    }
  },

  renameThread: async (threadId, title) => {
    const api = useAppStore.getState().api
    const groupId = get().selectedId
    if (!api || !groupId) return
    const clean = title.trim()
    if (!clean) return
    try {
      const updated = await api.renameGroupThread(groupId, threadId, clean)
      set((state) => ({
        threads: state.threads.map((item) => (item.id === updated.id ? updated : item)),
      }))
    } catch (error) {
      useNotificationStore.getState().push({
        level: 'error',
        title: '重命名失败',
        message: error instanceof Error ? error.message : String(error),
      })
    }
  },

  applyRemoteEvent: (groupId, threadId, event, data) => {
    const { selectedId, activeThreadId } = get()
    if (selectedId === null) {
      // 还没选群（观察窗刚打开那一下）→ **先存着**，别把第一个发言者的内容丢掉
      if (pendingRemote.length >= MAX_PENDING_REMOTE) pendingRemote.shift()
      pendingRemote.push({ groupId, threadId, event, data })
      return
    }
    // 事件属于某个群**的某条对话**：两样都要匹配上。
    //
    // ⚠️ 少了 thread 那一半，用户在另一条对话里打字时会看到后台那场讨论的字
    // 一句一句冒出来 —— 而且那些内容根本不属于他正在看的这条（
    // 一个群可以有多条对话）。判据与 `/discuss` 流式那条完全一样。
    if (selectedId !== groupId || activeThreadId !== threadId) return
    set((state) => {
      const next = applyGroupEvent(state.bubbles, event, data)
      // `done` 不改气泡内容，但它意味着讨论结束了：必须把最后那条的"正在输入"
      // 光标收掉，否则观察窗里会永远留一个还在闪的光标
      const bubbles =
        event === 'done' ? next.map((item) => ({ ...item, streaming: false })) : next
      return { bubbles }
    })
  },

  setDraft: (value) => set({ draft: value }),

  addFiles: async (files) => {
    const api = useAppStore.getState().api
    if (!api || files.length === 0) return
    // 与单聊共用同一份上传实现（services/attachments.ts）：占位 → 上传 → 回填/标红
    await addFilesTo(get().attachments, files, {
      api,
      onChange: (next) => set({ attachments: next }),
    })
  },

  removeAttachment: (id) =>
    set((state) => ({ attachments: state.attachments.filter((item) => item.id !== id) })),

  discuss: async (topic) => {
    const api = useAppStore.getState().api
    const groupId = get().selectedId
    // ⚠️ 没有 `activeThreadId` 就**什么都不做**：那说明对话列表还没拉回来
    // （进群的那一瞬间）。此刻若回退成"最近一条"，用户刚发的第一句话会被写进
    // 一条他还没看到的对话里 —— 后端有同样的兜底，但这里不发请求更诚实。
    const threadId = get().activeThreadId
    if (!api || !groupId || !threadId || get().busy) return

    const text = (topic ?? get().draft).trim()
    // 附件与图片分开传（与单聊同一套语义）：附件只把文件信息写进上下文，
    // 图片则把本体发给模型。上传中/失败的都不发 —— 发给后端只会 404。
    const attachments = get().attachments
    const attachmentIds = readyFileIds(attachments, 'file')
    const imageIds = readyFileIds(attachments, 'image')
    if (!text && attachmentIds.length === 0 && imageIds.length === 0) return

    abortController = new AbortController()
    activeBubbleId = ''
    set({ busy: true, runningGroupId: groupId, draft: '', attachments: [] })

    try {
      await api.discussGroup(
        groupId,
        { topic: text, attachments: attachmentIds, images: imageIds, threadId },
        (event, data) => {
          // 流式期间用户可能切到了别的群 / 别的对话：那些事件属于 (groupId, threadId)，
          // 不能把它们画到当前正在看的另一条上。
          if (get().selectedId !== groupId || get().activeThreadId !== threadId) return
          set((state) => ({ bubbles: applyGroupEvent(state.bubbles, event, data) }))
        },
        abortController.signal,
      )
    } catch (error) {
      const aborted = error instanceof DOMException && error.name === 'AbortError'
      if (!aborted) {
        set((state) => ({
          bubbles: [
            ...state.bubbles,
            { id: newId(), kind: 'system', name: '', content: `讨论中断：${String(error)}` },
          ],
        }))
      }
    } finally {
      abortController = null
      // 收尾：把最后一条气泡的"正在输入"光标去掉
      set((state) => ({
        busy: false,
        runningGroupId: null,
        bubbles: state.bubbles.map((item) => ({ ...item, streaming: false })),
      }))
    }
  },

  stop: () => {
    abortController?.abort()
    abortController = null
    set((state) => ({
      busy: false,
      runningGroupId: null,
      bubbles: state.bubbles.map((item) => ({ ...item, streaming: false })),
    }))
  },
}))
