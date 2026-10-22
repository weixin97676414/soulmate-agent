import { create } from 'zustand'

import { addFilesTo, readyFileIds } from '@/services/attachments'
import { pickGroupAvatar } from '@/services/avatarPack'
import { useAppStore } from '@/stores/appStore'
import { useNotificationStore } from '@/stores/notificationStore'
import type {
  GroupProfile,
  GroupThread,
  GroupUpdate,
  PendingAttachment,
  ToolCallState,
} from '@/types'

const newId = (): string =>
  typeof crypto !== 'undefined' && 'randomUUID' in crypto
    ? crypto.randomUUID()
    : `b-${Date.now()}-${Math.random().toString(16).slice(2)}`

export type BubbleKind = 'user' | 'assistant' | 'summary' | 'system'

export interface Bubble {
  id: string
  kind: BubbleKind
  
  assistantId?: string
  name: string
  content: string
  streaming?: boolean
  badge?: string
  









  reasoning?: string
  





  toolCalls?: ToolCallState[]
}




let abortController: AbortController | null = null

let activeBubbleId = ''












let pendingRemote: Array<{
  groupId: string
  threadId: string
  event: string
  data: Record<string, unknown>
}> = []
const MAX_PENDING_REMOTE = 500
















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











function summarizerName(data: Record<string, unknown>): string | null {
  const who = data.summary_by as { name?: unknown } | null | undefined
  const name = typeof who?.name === 'string' ? who.name.trim() : ''
  return name || null
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
    
    
    
    
    
    case 'reasoning': {
      const target = findTargetBubble(bubbles, String(data.assistant_id ?? ''))
      return bubbles.map((item) =>
        item.id === target
          ? { ...item, reasoning: (item.reasoning ?? '') + String(data.text ?? '') }
          : item,
      )
    }
    case 'tool_call': {
      const target = findTargetBubble(bubbles, String(data.assistant_id ?? ''))
      const raw = (data.tool ?? {}) as Record<string, unknown>
      const tool: ToolCallState = {
        id: String(raw.id ?? newId()),
        name: String(raw.name ?? ''),
        displayName: String(raw.display_name ?? raw.name ?? ''),
        description: String(raw.description ?? ''),
        params: {},
        
        permissionLevel: String(raw.permission_level ?? ''),
        status: 'running',
      }
      return bubbles.map((item) =>
        item.id === target ? { ...item, toolCalls: [...(item.toolCalls ?? []), tool] } : item,
      )
    }
    case 'tool_result': {
      const target = findTargetBubble(bubbles, String(data.assistant_id ?? ''))
      const raw = (data.tool ?? {}) as Record<string, unknown>
      const id = String(raw.id ?? '')
      return bubbles.map((item) =>
        item.id === target && item.toolCalls
          ? {
              ...item,
              toolCalls: item.toolCalls.map((tool) =>
                tool.id === id
                  ? {
                      ...tool,
                      status: (raw.status as ToolCallState['status']) ?? 'ok',
                      result: String(raw.result ?? ''),
                      durationMs:
                        typeof raw.duration_ms === 'number' ? raw.duration_ms : undefined,
                    }
                  : tool,
              ),
            }
          : item,
      )
    }
    case 'message': {
      const target = findTargetBubble(bubbles, String(data.assistant_id ?? ''))
      return bubbles.map((item) =>
        item.id === target
          ? { ...item, content: String(data.content ?? item.content), streaming: false }
          : item,
      )
    }
    case 'summary': {
      












      const target = findTargetBubble(bubbles, String(data.assistant_id ?? ''))
      return bubbles.map((item) =>
        item.id === target
          ? {
              ...item,
              kind: 'summary',
              badge: '最终总结',
              content: String(data.content ?? item.content),
              streaming: false,
            }
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
    case 'vote_result': {
      
      
      const by = summarizerName(data)
      return push({
        id: newId(),
        kind: 'system',
        name: '',
        content: data.passed
          ? `投票通过，由 ${by ?? '会话发起人'} 做最终总结。`
          : '投票未通过，继续讨论。',
      })
    }
    case 'error':
      return push({
        id: newId(),
        kind: 'system',
        name: '',
        content: `出错了：${String(data.message ?? '')}`,
      })
    case 'out_of_scope': {
      
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
      
      
      
      const by = summarizerName(data)
      return push({
        id: newId(),
        kind: 'system',
        name: '',
        content: passed
          ? `✅ ${String(data.name ?? '')} 验收通过，讨论结束${
              by ? `，由 ${by} 做最终总结` : ''
            }。`
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
      
      return bubbles
  }
}

interface GroupState {
  groups: GroupProfile[]
  loading: boolean
  selectedId: string | null
  




  threads: GroupThread[]
  






  activeThreadId: string | null
  bubbles: Bubble[]
  busy: boolean
  
  persistent: boolean
  
  runningGroupId: string | null
  





  draft: string
  attachments: PendingAttachment[]

  loadGroups: () => Promise<void>
  selectGroup: (id: string) => Promise<void>
  createGroup: (payload: {
    name: string
    member_assistant_ids: string[]
    speaking_order?: string[]
    
    avatar?: string
  }) => Promise<GroupProfile | null>
  deleteGroup: (id: string) => Promise<void>
  
  updateGroup: (id: string, patch: GroupUpdate) => Promise<GroupProfile | null>
  clearMessages: (id?: string, threadId?: string) => Promise<void>
  
  selectThread: (threadId: string) => Promise<void>
  






  startNewThread: () => Promise<void>
  deleteThread: (threadId: string) => Promise<void>
  renameThread: (threadId: string, title: string) => Promise<void>
  






  reloadThreads: (groupId: string) => Promise<void>
  








  settingsRequestId: string | null
  requestGroupSettings: (groupId: string) => void
  clearGroupSettingsRequest: () => void
  






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























async function assignMissingGroupAvatars(
  set: (partial: Partial<GroupState>) => void,
  get: () => GroupState,
  groups: GroupProfile[],
): Promise<void> {
  const api = useAppStore.getState().api
  if (!api) return

  
  
  
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

  
  const byId = new Map(patched.map((item) => [item.id, item]))
  set({ groups: get().groups.map((item) => byId.get(item.id) ?? item) })

  for (const group of patched) {
    try {
      await api.updateGroup(group.id, { avatar: group.avatar })
    } catch {
      
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
        
        selectedId: payload.groups.some((item) => item.id === state.selectedId)
          ? state.selectedId
          : (payload.groups[0]?.id ?? null),
      }))
      
      
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
    
    set({
      selectedId: id,
      threads: [],
      activeThreadId: null,
      bubbles: [],
      draft: '',
      attachments: [],
    })
    try {
      
      
      const listed = await api.getGroupThreads(id)
      
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
    
    set({ activeThreadId: threadId, bubbles: [], draft: '', attachments: [] })
    try {
      const payload = await api.getGroupMessages(groupId, threadId)
      
      
      
      
      
      
      const savedCursor = activeBubbleId
      let bubbles: Bubble[] = []
      for (const item of payload.events) {
        bubbles = applyGroupEvent(bubbles, item.event, item.data)
      }
      
      bubbles = bubbles.map((item) => ({ ...item, streaming: false }))
      
      if (get().selectedId !== groupId || get().activeThreadId !== threadId) {
        activeBubbleId = savedCursor
        return
      }
      
      
      
      
      
      
      
      
      let merged = bubbles
      
      
      const buffered = pendingRemote.filter(
        (item) => item.groupId === groupId && item.threadId === threadId,
      )
      pendingRemote = pendingRemote.filter(
        (item) => !(item.groupId === groupId && item.threadId === threadId),
      )
      
      
      
      for (const item of buffered) {
        if (item.event !== 'delta') continue
        merged = applyGroupEvent(merged, item.event, item.data)
      }
      
      
      
      
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
      
      
      set((state) => ({
        groups: state.groups.map((item) => (item.id === group.id ? group : item)),
      }))
      return group
    } catch (error) {
      
      
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
      
      set((state) => ({ threads: [created, ...state.threads] }))
      
      
      
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
    
    
    if (get().selectedId !== groupId) return
    try {
      const listed = await api.getGroupThreads(groupId)
      if (get().selectedId !== groupId) return
      set({ threads: listed.threads })
      
      
      
      const active = get().activeThreadId
      if (active && !listed.threads.some((item) => item.id === active)) {
        const fallback = listed.threads[0]
        if (fallback) await get().selectThread(fallback.id)
      }
    } catch {
      
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
      
      if (pendingRemote.length >= MAX_PENDING_REMOTE) pendingRemote.shift()
      pendingRemote.push({ groupId, threadId, event, data })
      return
    }
    
    
    
    
    
    if (selectedId !== groupId || activeThreadId !== threadId) return
    set((state) => {
      const next = applyGroupEvent(state.bubbles, event, data)
      
      
      const bubbles =
        event === 'done' ? next.map((item) => ({ ...item, streaming: false })) : next
      return { bubbles }
    })
  },

  setDraft: (value) => set({ draft: value }),

  addFiles: async (files) => {
    const api = useAppStore.getState().api
    if (!api || files.length === 0) return
    
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
    
    
    
    const threadId = get().activeThreadId
    if (!api || !groupId || !threadId || get().busy) return

    const text = (topic ?? get().draft).trim()
    
    
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
