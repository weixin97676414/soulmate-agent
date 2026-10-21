import { create } from 'zustand'

import type { PermissionEvent, ToolResultEvent } from '@/services/api'
import { ApiError } from '@/services/api'
import { addFilesTo } from '@/services/attachments'
import { useAppStore } from '@/stores/appStore'
import { useAssistantStore } from '@/stores/assistantStore'
import { useNotificationStore } from '@/stores/notificationStore'
import { budgetStatus, useUsageStore } from '@/stores/usageStore'
import type {
  ChatMessage,
  FileRecord,
  InteractionAnswer,
  InteractionChoice,
  InteractionEvent,
  InteractionSecretField,
  PendingAttachment,
  PermissionRequest,
  Plan,
  SessionSummary,
  ToolCallState,
  TokenUsage,
  TraceData,
} from '@/types'

const ATTACHMENT_OPEN = '[附件]'
const ATTACHMENT_CLOSE = '[/附件]'


let budgetWarnedOn = ''








function warnIfOverBudget(): void {
  const status = budgetStatus(useUsageStore.getState().summary)
  if (!status?.exceeded) return
  const today = new Date().toISOString().slice(0, 10)
  if (budgetWarnedOn === today) return
  budgetWarnedOn = today
  useNotificationStore.getState().push({
    level: 'warning',
    title: '今日已超出预算',
    message: `今日已花费约 ${status.spent.toFixed(2)}，达到设定的每日预算 ${status.budget.toFixed(2)}。这里只提示，不会阻止发送。`,
    autoDismissMs: 10000,
  })
}







export function stripAttachmentBlock(content: string): string {
  if (!content.startsWith(ATTACHMENT_OPEN)) return content
  const end = content.indexOf(ATTACHMENT_CLOSE)
  if (end < 0) return content
  return content.slice(end + ATTACHMENT_CLOSE.length).replace(/^\s+/, '')
}

export type DrawerTab = 'trace' | 'artifacts'













const keyOf = (state: { activeSessionId: string | null; pendingSessionKey: string }): string =>
  state.activeSessionId ?? state.pendingSessionKey











interface RunState {
  runId: string
  
  sessionId: string
  
  assistantId: string | null
  
  assistantMessageId: string
  taskId: string | null
  abort: AbortController
  startedAt: number
}

interface ChatState {
  sessions: SessionSummary[]
  activeSessionId: string | null
  





  pendingSessionKey: string
  






  messagesBySession: Record<string, ChatMessage[]>
  






  messages: ChatMessage[]
  
  runs: Record<string, RunState>
  
  modelId: string | null
  





  reasoningEffort: string | null
  





  streaming: boolean
  





  permissions: PermissionRequest[]
  
  permission: PermissionRequest | null
  






  interactions: InteractionEvent[]
  
  interaction: InteractionEvent | null
  
  trace: TraceData | null
  tracesBySession: Record<string, TraceData>
  
  drawerOpen: boolean
  drawerTab: DrawerTab | null
  
  artifacts: FileRecord[]
  draft: string
  attachments: PendingAttachment[]
  persistent: boolean
  sessionsLoading: boolean
  












  runningAssistantId: string | null
  runningSessionId: string | null
  runningStartedAt: number | null

  loadSessions: () => Promise<void>
  selectSession: (id: string) => Promise<void>
  







  reloadMessages: () => Promise<void>
  startNewSession: () => void
  renameSession: (id: string, title: string) => Promise<void>
  deleteSession: (id: string) => Promise<void>
  clearHistory: () => Promise<void>
  setModelId: (id: string) => void
  setReasoningEffort: (effort: string | null) => void
  setDraft: (value: string) => void
  addFiles: (files: File[]) => Promise<void>
  removeAttachment: (id: string) => void
  







  send: (text?: string, displayText?: string) => Promise<void>
  stop: () => Promise<void>
  respondPermission: (approved: boolean) => Promise<void>
  










  respondPlan: (planId: string, approved: boolean, feedback?: string) => Promise<void>
  






  setPermission: (request: PermissionRequest | null) => void
  





  respondInteraction: (answer: InteractionAnswer) => Promise<void>
  setDrawerOpen: (open: boolean) => void
  setDrawerTab: (tab: DrawerTab) => void
  loadArtifacts: () => Promise<void>
  deleteArtifact: (id: string) => Promise<void>
}















interface RunBuffer {
  delta: string
  reasoning: string
  flush: number | null
}
const runBuffers = new Map<string, RunBuffer>()

const newId = (): string =>
  typeof crypto !== 'undefined' && 'randomUUID' in crypto
    ? crypto.randomUUID()
    : `id-${Date.now()}-${Math.random().toString(16).slice(2)}`


const EMPTY_MESSAGES: ChatMessage[] = []


function visibleMessages(
  key: string,
  bySession: Record<string, ChatMessage[]>,
): ChatMessage[] {
  return bySession[key] ?? EMPTY_MESSAGES
}







function visibleStreaming(key: string, runs: Record<string, RunState>): boolean {
  return Object.values(runs).some((run) => run.sessionId === key)
}







function runningSummary(runs: Record<string, RunState>): {
  runningAssistantId: string | null
  runningSessionId: string | null
  runningStartedAt: number | null
} {
  const list = Object.values(runs)
  if (list.length === 0) {
    return { runningAssistantId: null, runningSessionId: null, runningStartedAt: null }
  }
  const latest = list.reduce((a, b) => (b.startedAt > a.startedAt ? b : a))
  return {
    runningAssistantId: latest.assistantId,
    runningSessionId: latest.sessionId || null,
    runningStartedAt: latest.startedAt,
  }
}








function toChatMessages(
  
  items: Array<{
    role: string
    content: string
    created_at?: number | null
    plan?: Plan | null
    reasoning?: string
    tool_calls?: Array<{ id: string; name: string; arguments?: Record<string, unknown> }>
  }>,
): ChatMessage[] {
  return items.map((message) => ({
    id: newId(),
    role: message.role as ChatMessage['role'],
    content:
      message.role === 'user' ? stripAttachmentBlock(message.content) : message.content,
    
    
    
    
    reasoning: message.reasoning ?? '',
    toolCalls: (message.tool_calls ?? []).map((call) => ({
      id: call.id || newId(),
      name: call.name,
      displayName: call.name,
      description: '',
      params: call.arguments ?? {},
      permissionLevel: '',
      






      status: 'ok' as const,
    })),
    status: 'done' as const,
    
    
    createdAt: message.created_at ? message.created_at * 1000 : 0,
    
    plan: message.plan ?? undefined,
  }))
}



















interface RawInteractionEvent {
  request_id?: string
  skill_name?: string
  display_name?: string
  kind?: string
  payload?: {
    question?: string
    options?: InteractionChoice[]
    allow_custom?: boolean
    reason?: string
    fields?: InteractionSecretField[]
  }
  prompt?: string
}

function flattenInteraction(
  raw: RawInteractionEvent,
  sessionKey: string,
  sessionTitle?: string,
): InteractionEvent {
  const payload = raw.payload ?? {}
  return {
    requestId: raw.request_id ?? '',
    skillName: raw.skill_name ?? '',
    displayName: raw.display_name || raw.skill_name || '',
    kind: raw.kind === 'secret' ? 'secret' : 'choice',
    
    
    question: payload.question || raw.prompt || '',
    options: Array.isArray(payload.options) ? payload.options : [],
    
    
    allowCustom: payload.allow_custom !== false,
    reason: payload.reason || raw.prompt || '',
    fields: Array.isArray(payload.fields) ? payload.fields : [],
    sessionKey,
    ...(sessionTitle ? { sessionTitle } : {}),
  }
}

export const useChatStore = create<ChatState>((set, get) => {
  






  const patchInRun = (runId: string, patch: (message: ChatMessage) => ChatMessage): void => {
    set((state) => {
      const run = state.runs[runId]
      if (!run) return {}
      const bucket = state.messagesBySession[run.sessionId]
      if (!bucket) return {}
      const index = bucket.findIndex((message) => message.id === run.assistantMessageId)
      if (index < 0) return {}
      const messages = [...bucket]
      messages[index] = patch(messages[index])
      const messagesBySession = { ...state.messagesBySession, [run.sessionId]: messages }
      
      
      return keyOf(state) === run.sessionId
        ? { messagesBySession, messages }
        : { messagesBySession }
    })
  }

  
  const bufferOf = (runId: string): RunBuffer => {
    let buffer = runBuffers.get(runId)
    if (!buffer) {
      buffer = { delta: '', reasoning: '', flush: null }
      runBuffers.set(runId, buffer)
    }
    return buffer
  }

  
  const commitBuffer = (runId: string): void => {
    const buffer = runBuffers.get(runId)
    if (!buffer) return
    const chunk = buffer.delta
    const reasoning = buffer.reasoning
    buffer.delta = ''
    buffer.reasoning = ''
    if (!chunk && !reasoning) return
    patchInRun(runId, (m) => ({
      ...m,
      content: chunk ? m.content + chunk : m.content,
      reasoning: reasoning ? m.reasoning + reasoning : m.reasoning,
    }))
  }

  const flushRun = (runId: string): void => {
    const buffer = runBuffers.get(runId)
    if (!buffer) return
    if (buffer.flush !== null) {
      cancelAnimationFrame(buffer.flush)
      buffer.flush = null
    }
    commitBuffer(runId)
  }

  const scheduleFlush = (runId: string): void => {
    const buffer = bufferOf(runId)
    if (buffer.flush !== null) return
    buffer.flush = requestAnimationFrame(() => {
      const current = runBuffers.get(runId)
      if (current) current.flush = null
      commitBuffer(runId)
    })
  }

  const queueDelta = (runId: string, text: string): void => {
    if (!text) return
    bufferOf(runId).delta += text
    scheduleFlush(runId)
  }

  const queueReasoning = (runId: string, text: string): void => {
    if (!text) return
    bufferOf(runId).reasoning += text
    scheduleFlush(runId)
  }

  const patchToolCall = (
    runId: string,
    toolCallId: string,
    patch: (tool: ToolCallState) => ToolCallState,
  ): void => {
    patchInRun(runId, (m) => ({
      ...m,
      toolCalls: m.toolCalls.map((tool) => (tool.id === toolCallId ? patch(tool) : tool)),
    }))
  }

  





  const pushPermission = (request: PermissionRequest): void => {
    set((state) => {
      const permissions = [...state.permissions, request]
      return { permissions, permission: permissions[0] ?? null }
    })
  }

  
  const dropPermission = (requestId: string): void => {
    set((state) => {
      const permissions = state.permissions.filter((item) => item.requestId !== requestId)
      return { permissions, permission: permissions[0] ?? null }
    })
  }

  
  const dropPermissionsOf = (sessionKey: string): void => {
    set((state) => {
      const permissions = state.permissions.filter((item) => item.sessionId !== sessionKey)
      if (permissions.length === state.permissions.length) return {}
      return { permissions, permission: permissions[0] ?? null }
    })
  }

  
  
  
  
  

  
  const pushInteraction = (request: InteractionEvent): void => {
    set((state) => {
      const interactions = [...state.interactions, request]
      return { interactions, interaction: interactions[0] ?? null }
    })
  }

  
  const dropInteraction = (requestId: string): void => {
    set((state) => {
      const interactions = state.interactions.filter((item) => item.requestId !== requestId)
      return { interactions, interaction: interactions[0] ?? null }
    })
  }

  
  const dropInteractionsOf = (sessionKey: string): void => {
    set((state) => {
      const interactions = state.interactions.filter((item) => item.sessionKey !== sessionKey)
      if (interactions.length === state.interactions.length) return {}
      return { interactions, interaction: interactions[0] ?? null }
    })
  }

  return {
    sessions: [],
    activeSessionId: null,
    pendingSessionKey: newId(),
    messagesBySession: {},
    messages: [],
    runs: {},
    modelId: null,
    reasoningEffort: null,
    streaming: false,
    permissions: [],
    permission: null,
    interactions: [],
    interaction: null,
    trace: null,
    tracesBySession: {},
    drawerOpen: false,
    drawerTab: null,
    artifacts: [],
    draft: '',
    attachments: [],
    persistent: false,
    sessionsLoading: false,
    runningAssistantId: null,
    runningSessionId: null,
    runningStartedAt: null,

    
    
    
    loadSessions: async () => {
      const api = useAppStore.getState().api
      if (!api) return
      set({ sessionsLoading: true })
      try {
        const payload = await api.getSessions()
        set({ sessions: payload.sessions, persistent: payload.persistent })
      } catch (error) {
        
        
        
        useNotificationStore.getState().push({
          level: 'error',
          title: '会话列表加载失败',
          message: error instanceof Error ? error.message : String(error),
        })
      } finally {
        set({ sessionsLoading: false })
      }
    },

    selectSession: async (id) => {
      
      
      
      
      
      
      set((state) => ({
        activeSessionId: id,
        messages: visibleMessages(id, state.messagesBySession),
        
        trace: state.tracesBySession[id] ?? null,
        streaming: visibleStreaming(id, state.runs),
        attachments: [],
        
        
      }))

      
      
      const session = get().sessions.find((item) => item.id === id)
      if (session) {
        useAssistantStore.getState().setActive(session.assistant_id)
        
        
        set({ reasoningEffort: session.reasoning_effort })
      }

      try {
        const api = useAppStore.getState().api
        if (!api) return
        const payload = await api.getMessages(id)
        



















        if (!visibleStreaming(id, get().runs)) {
          
          
          set((state) => {
            const messagesBySession = {
              ...state.messagesBySession,
              [id]: toChatMessages(payload.messages),
            }
            return {
              messagesBySession,
              messages: visibleMessages(keyOf(state), messagesBySession),
            }
          })
        }
      } catch (error) {
        
        
        
        
        
        
        
        if (!visibleStreaming(id, get().runs)) {
          set((state) => {
            const messagesBySession = { ...state.messagesBySession, [id]: [] }
            return {
              messagesBySession,
              messages: visibleMessages(keyOf(state), messagesBySession),
            }
          })
        }
        useNotificationStore.getState().push({
          level: 'error',
          title: '历史消息加载失败',
          message: `${error instanceof Error ? error.message : String(error)}（会话内容仍在本地数据库中，重新点击该会话即可重试）`,
          autoDismissMs: 0,
        })
      }
      void get().loadArtifacts()
    },

    reloadMessages: async () => {
      const sessionId = get().activeSessionId
      const api = useAppStore.getState().api
      if (!sessionId || !api) return
      try {
        const payload = await api.getMessages(sessionId)
        
        
        
        
        
        
        
        
        if (get().activeSessionId !== sessionId) return
        if (visibleStreaming(sessionId, get().runs)) return
        set((state) => {
          const messagesBySession = {
            ...state.messagesBySession,
            [sessionId]: toChatMessages(payload.messages),
          }
          return {
            messagesBySession,
            messages: visibleMessages(keyOf(state), messagesBySession),
          }
        })
      } catch {
        
      }
    },

    startNewSession: () => {
      
      
      
      const pending = newId()
      set((state) => ({
        activeSessionId: null,
        pendingSessionKey: pending,
        messages: visibleMessages(pending, state.messagesBySession),
        trace: state.tracesBySession[pending] ?? null,
        streaming: visibleStreaming(pending, state.runs),
        modelId: null,
        attachments: [],
        artifacts: [],
        drawerTab: null,
      }))
      
      
    },

    renameSession: async (id, title) => {
      const api = useAppStore.getState().api
      if (!api) return
      await api.updateSession(id, { title })
      await get().loadSessions()
    },

    deleteSession: async (id) => {
      const api = useAppStore.getState().api
      if (!api) return
      
      
      
      
      
      
      if (visibleStreaming(id, get().runs)) {
        useNotificationStore.getState().push({
          level: 'warning',
          title: '正在生成，无法删除',
          message: '请先点「停止」，再删除这个会话。',
        })
        return
      }
      await api.deleteSession(id)
      
      set((state) => {
        const messagesBySession = { ...state.messagesBySession }
        delete messagesBySession[id]
        const tracesBySession = { ...state.tracesBySession }
        delete tracesBySession[id]
        return { messagesBySession, tracesBySession }
      })
      
      if (get().activeSessionId === id) get().startNewSession()
      await get().loadSessions()
    },

    clearHistory: async () => {
      const key = keyOf(get())
      
      
      
      
      if (visibleStreaming(key, get().runs)) {
        useNotificationStore.getState().push({
          level: 'warning',
          title: '正在生成，无法清空',
          message: '请先点「停止」，再清空当前会话。',
        })
        return
      }

      const sessionId = get().activeSessionId
      
      if (!sessionId) {
        set((state) => {
          const messagesBySession = { ...state.messagesBySession, [key]: [] }
          return { messagesBySession, messages: [] }
        })
        return
      }
      const api = useAppStore.getState().api
      if (!api) return
      await api.clearMessages(sessionId)
      set((state) => {
        const messagesBySession = { ...state.messagesBySession, [sessionId]: [] }
        
        const tracesBySession = { ...state.tracesBySession }
        delete tracesBySession[sessionId]
        return {
          messagesBySession,
          messages: visibleMessages(keyOf(state), messagesBySession),
          tracesBySession,
          trace: null,
        }
      })
      await get().loadSessions()
    },

    
    
    
    setModelId: (id) => set({ modelId: id }),
    setReasoningEffort: (effort) => set({ reasoningEffort: effort }),
    setDraft: (value) => set({ draft: value }),

    
    
    
    addFiles: async (files) => {
      const api = useAppStore.getState().api
      if (!api || files.length === 0) return
      
      
      await addFilesTo(get().attachments, files, {
        api,
        sessionId: get().activeSessionId ?? undefined,
        onChange: (next) => set({ attachments: next }),
      })
    },

    removeAttachment: (id) =>
      set((state) => ({ attachments: state.attachments.filter((item) => item.id !== id) })),

    
    
    
    send: async (text, displayText) => {
      const message = (text ?? get().draft).trim()
      const ready = get().attachments.filter((item) => item.status === 'ready')
      
      
      if (!message && ready.length === 0) return

      
      
      
      
      
      const runKey = keyOf(get())
      if (visibleStreaming(runKey, get().runs)) return

      
      
      
      const api = useAppStore.getState().api
      if (!api) {
        useNotificationStore.getState().push({
          level: 'error',
          title: '智能体核心尚未就绪',
          message: '请等待启动完成，或在左侧「关于」页里重启后端。',
        })
        return
      }

      warnIfOverBudget()

      const attachmentIds = ready.map((item) => item.id)
      
      
      const imageIds = ready.filter((item) => item.kind === 'image').map((item) => item.id)

      const now = Date.now()
      const userMessage: ChatMessage = {
        id: newId(),
        role: 'user',
        
        
        
        
        content:
          displayText?.trim() ||
          message ||
          `已发送附件：${ready.map((item) => item.name).join('、')}`,
        reasoning: '',
        toolCalls: [],
        status: 'done',
        createdAt: now,
      }
      
      
      
      
      const modelId =
        get().modelId ?? useAppStore.getState().modelDefaults.effectiveDefault ?? undefined
      const assistantId = useAssistantStore.getState().activeId ?? undefined

      const assistantMessage: ChatMessage = {
        id: newId(),
        role: 'assistant',
        content: '',
        reasoning: '',
        toolCalls: [],
        status: 'streaming',
        createdAt: now + 1,
        
        
        
        assistantId: assistantId || undefined,
      }

      
      
      const runId = newId()
      runBuffers.set(runId, { delta: '', reasoning: '', flush: null })
      const abort = new AbortController()

      set((state) => {
        const bucket = state.messagesBySession[runKey] ?? []
        const messagesBySession = {
          ...state.messagesBySession,
          [runKey]: [...bucket, userMessage, assistantMessage],
        }
        const runs = {
          ...state.runs,
          [runId]: {
            runId,
            sessionId: runKey,
            assistantId: assistantId ?? null,
            assistantMessageId: assistantMessage.id,
            taskId: null,
            abort,
            startedAt: Date.now(),
          },
        }
        
        const tracesBySession = { ...state.tracesBySession }
        delete tracesBySession[runKey]
        const visible = keyOf(state) === runKey
        return {
          messagesBySession,
          messages: visible ? visibleMessages(runKey, messagesBySession) : state.messages,
          runs,
          streaming: visibleStreaming(keyOf(state), runs),
          tracesBySession,
          trace: visible ? null : state.trace,
          draft: '',
          attachments: [],
          
          ...runningSummary(runs),
        }
      })

      try {
        await api.streamChat(
          {
            message,
            session_id: get().activeSessionId ?? undefined,
            model_id: modelId,
            assistant_id: assistantId,
            attachments: attachmentIds.length ? attachmentIds : undefined,
            images: imageIds.length ? imageIds : undefined,
            
            
            reasoning_effort: get().reasoningEffort,
          },
          {
            onMeta: (meta) => {
              
              
              
              
              
              
              set((state) => {
                const run = state.runs[runId]
                if (!run) return {}
                const messagesBySession = { ...state.messagesBySession }
                if (run.sessionId !== meta.session_id) {
                  const bucket = messagesBySession[run.sessionId] ?? []
                  delete messagesBySession[run.sessionId]
                  messagesBySession[meta.session_id] = bucket
                }
                const runs = {
                  ...state.runs,
                  [runId]: { ...run, sessionId: meta.session_id, taskId: meta.task_id },
                }
                const stillVisible = keyOf(state) === run.sessionId
                
                const pendingSessionKey =
                  state.pendingSessionKey === run.sessionId ? newId() : state.pendingSessionKey
                const activeSessionId =
                  state.activeSessionId ?? (stillVisible ? meta.session_id : null)
                const key = activeSessionId ?? pendingSessionKey
                return {
                  activeSessionId,
                  pendingSessionKey,
                  messagesBySession,
                  runs,
                  messages: visibleMessages(key, messagesBySession),
                  streaming: visibleStreaming(key, runs),
                  ...runningSummary(runs),
                }
              })

              













              void get().loadSessions()
            },
            onWarning: (data) => {
              
              
              
              useNotificationStore.getState().push({
                level: 'warning',
                title: '提示',
                message: data.message,
                autoDismissMs: 0,
              })
            },
            onContextCompressed: () => {
              
              
              
              
              
              
              
              useNotificationStore.getState().push({
                level: 'info',
                title: '早前的对话已折叠为摘要',
                message:
                  '为了让对话继续下去，更早的内容被压缩成了摘要（不是删除）。' +
                  '你的聊天记录仍然是完整的，随时可以翻看；如果发现它记不清某个细节，' +
                  '直接把它指出来即可。',
                autoDismissMs: 9000,
              })
            },
            onInjectionSuspected: (data) => {
              
              
              
              useNotificationStore.getState().push({
                level: 'warning',
                title: '检测到疑似指令注入',
                message:
                  `工具「${data.display_name || data.name}」的返回内容里包含可疑指令` +
                  `（${data.labels.join('、')}）。已按数据处理，未执行其中的指令。` +
                  `如果你不认识这个来源，建议核实这次结果。`,
                autoDismissMs: 0,
              })
            },
            onDelta: (text) => queueDelta(runId, text),
            
            
            
            
            
            onReasoning: (text) => queueReasoning(runId, text),
            onToolCall: (data) => {
              
              const tool: ToolCallState = {
                id: data.id,
                name: data.name,
                displayName: data.display_name || data.name,
                description: data.description,
                params: data.params ?? {},
                permissionLevel: data.permission_level ?? 'safe',
                status: 'running',
                
                
                
                startedAt: data.started_at ? data.started_at * 1000 : undefined,
              }
              patchInRun(runId, (m) => ({ ...m, toolCalls: [...m.toolCalls, tool] }))

              














            },
            onToolResult: (data: ToolResultEvent) => {
              patchToolCall(runId, data.id, (tool) => ({
                ...tool,
                status: data.status,
                result: data.result,
                durationMs: data.duration_ms,
              }))
            },
            onPermissionRequest: (data: PermissionEvent) => {
              
              
              
              const sessionId = get().runs[runId]?.sessionId ?? ''
              const title = get().sessions.find((item) => item.id === sessionId)?.title
              pushPermission({
                requestId: data.request_id,
                skillName: data.skill_name,
                displayName: data.display_name || data.skill_name,
                description: data.description,
                permissionLevel: data.permission_level,
                params: data.params ?? {},
                prompt: data.prompt,
                sessionId,
                sessionTitle: title,
              })
            },
            onInteractionRequest: (data) => {
              
              
              const sessionKey = get().runs[runId]?.sessionId ?? ''
              const title = get().sessions.find((item) => item.id === sessionKey)?.title
              pushInteraction(flattenInteraction(data, sessionKey, title))
            },
            
            
            
            
            
            
            onPlan: (plan) => patchInRun(runId, (m) => ({ ...m, plan })),
            onPlanUpdate: (plan) => patchInRun(runId, (m) => ({ ...m, plan })),
            onUsage: (usage: TokenUsage) => patchInRun(runId, (m) => ({ ...m, usage })),
            onTrace: (trace) =>
              set((state) => {
                const run = state.runs[runId]
                if (!run) return { trace }
                const tracesBySession = { ...state.tracesBySession, [run.sessionId]: trace }
                
                
                return {
                  tracesBySession,
                  trace: keyOf(state) === run.sessionId ? trace : state.trace,
                }
              }),
            onDone: (done) => {
              flushRun(runId)
              patchInRun(runId, (m) => ({
                ...m,
                status: done.cancelled ? 'cancelled' : 'done',
                iterations: done.iterations,
              }))
            },
            onErrorEvent: (error) => {
              flushRun(runId)
              patchInRun(runId, (m) => ({ ...m, status: 'error', error: error.message }))
            },
          },
          abort.signal,
        )
      } catch (error) {
        flushRun(runId)
        const aborted = error instanceof DOMException && error.name === 'AbortError'
        const text =
          error instanceof ApiError
            ? error.message
            : aborted
              ? '已中断'
              : error instanceof Error
                ? error.message
                : String(error)
        patchInRun(runId, (m) => ({
          ...m,
          status: aborted ? 'cancelled' : 'error',
          error: aborted ? undefined : text,
        }))
      } finally {
        flushRun(runId)
        
        
        
        
        patchInRun(runId, (m) => (m.status === 'streaming' ? { ...m, status: 'done' } : m))
        const finishedSession = get().runs[runId]?.sessionId ?? runKey
        set((state) => {
          
          
          
          const runs = { ...state.runs }
          delete runs[runId]
          return {
            runs,
            streaming: visibleStreaming(keyOf(state), runs),
            ...runningSummary(runs),
          }
        })
        
        
        dropPermissionsOf(finishedSession)
        
        runBuffers.delete(runId)
        void get().loadSessions()
        
        
        
        
        
        
        
        
        void useAssistantStore.getState().load()
        
        
        void useUsageStore.getState().load()

        
        
        
        
        
        
        
        
        
        
        
        
        
        await get().loadArtifacts()
      }
    },

    stop: async () => {
      const api = useAppStore.getState().api
      
      const key = keyOf(get())
      const run = Object.values(get().runs).find((item) => item.sessionId === key)
      if (!run) return
      run.abort.abort()
      if (api) {
        try {
          await api.stop({
            task_id: run.taskId ?? undefined,
            session_id: get().activeSessionId ?? undefined,
          })
        } catch {
          
        }
      }
      set((state) => {
        const runs = { ...state.runs }
        delete runs[run.runId]
        return {
          runs,
          streaming: visibleStreaming(keyOf(state), runs),
          ...runningSummary(runs),
        }
      })
      dropPermissionsOf(key)
      
      
      dropInteractionsOf(key)
    },

    respondPermission: async (approved) => {
      
      const request = get().permission
      if (!request) return
      dropPermission(request.requestId)
      try {
        const api = useAppStore.getState().api
        await api?.confirm(request.requestId, approved)
      } catch {
        
      }
    },

    










    respondInteraction: async (answer) => {
      const request = get().interaction
      if (!request) return
      dropInteraction(request.requestId)
      try {
        const api = useAppStore.getState().api
        const result = await api?.interactionDecision(request.requestId, answer)
        
        
        
        if (result && result.ok === false) {
          useNotificationStore.getState().push({
            level: 'warning',
            title: '这次询问已经结束了',
            message: result.message || '任务可能已被停止，或你已经作答过了。',
          })
        }
      } catch (error) {
        useNotificationStore.getState().push({
          level: 'error',
          title: '提交失败',
          message: error instanceof Error ? error.message : String(error),
        })
      }
    },

    respondPlan: async (planId, approved, feedback = '') => {
      
      
      
      
      
      
      if (!planId) return

      const api = useAppStore.getState().api
      if (!api) return
      try {
        const result = await api.planDecision(planId, approved, feedback)
        if (!result.ok) {
          
          
          useNotificationStore.getState().push({
            level: 'warning',
            title: '这个计划已经不在等待中了',
            message: result.message || '它可能已经开始执行，或者被取消了。',
          })
        }
      } catch (error) {
        useNotificationStore.getState().push({
          level: 'error',
          title: '计划操作没有送达',
          message: error instanceof Error ? error.message : String(error),
        })
      }
    },

    
    
    setPermission: (request) => {
      if (!request) {
        
        const head = get().permission
        if (head) dropPermission(head.requestId)
        return
      }
      pushPermission(request)
    },

    
    
    
    
    
    setDrawerOpen: (open) => set({ drawerOpen: open }),
    setDrawerTab: (tab) => set({ drawerTab: tab }),

    loadArtifacts: async () => {
      const api = useAppStore.getState().api
      if (!api) return
      try {
        const payload = await api.getFiles('artifact')
        set({ artifacts: payload.files })
      } catch {
        
      }
    },

    deleteArtifact: async (id) => {
      const api = useAppStore.getState().api
      if (!api) return
      try {
        await api.deleteFile(id, 'artifact')
      } finally {
        await get().loadArtifacts()
      }
    },
  }
})
