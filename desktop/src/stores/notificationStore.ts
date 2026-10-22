import { create } from 'zustand'

import type { NoticeEvent, ReminderEvent } from '@/services/api'
import { useAppStore } from '@/stores/appStore'
import { useAssistantStore } from '@/stores/assistantStore'
import { useChatStore } from '@/stores/chatStore'
import { useGroupStore } from '@/stores/groupStore'
import { useModelHubStore } from '@/stores/modelHubStore'

export type ToastLevel = 'info' | 'success' | 'warning' | 'error'


export interface ToastAction {
  label: string
  run: () => void | Promise<void>
}

export interface Toast {
  id: string
  level: ToastLevel
  title: string
  message?: string
  createdAt: number
  
  autoDismissMs: number
  





  action?: ToastAction
}








const DEFAULT_DISMISS_MS = 10000
const RECONNECT_DELAY_MS = 3000

interface NotificationState {
  toasts: Toast[]
  
  eventsConnected: boolean
  push: (toast: Omit<Toast, 'id' | 'createdAt' | 'autoDismissMs'> & Partial<Toast>) => string
  dismiss: (id: string) => void
  clearAll: () => void
  startEventStream: () => void
  stopEventStream: () => void
}

const newId = (): string =>
  typeof crypto !== 'undefined' && 'randomUUID' in crypto
    ? crypto.randomUUID()
    : `t-${Date.now()}-${Math.random().toString(16).slice(2)}`


function systemNotify(title: string, body: string): void {
  try {
    if (typeof Notification === 'undefined') return
    if (Notification.permission === 'granted') {
      new Notification(title, { body })
    } else if (Notification.permission !== 'denied') {
      void Notification.requestPermission().then((permission) => {
        if (permission === 'granted') new Notification(title, { body })
      })
    }
  } catch {
    
  }
}


let controller: AbortController | null = null
let running = false







let healthRefreshTimer: number | null = null







let rebuildNoticeTimer: number | null = null
let rebuildNoticeCount = 0







export type AppEventListener = (event: string, data: Record<string, any>) => void

const listeners = new Set<AppEventListener>()

export function subscribeAppEvents(listener: AppEventListener): () => void {
  listeners.add(listener)
  return () => {
    listeners.delete(listener)
  }
}

export const useNotificationStore = create<NotificationState>((set, get) => {
  const push = (
    toast: Omit<Toast, 'id' | 'createdAt' | 'autoDismissMs'> & Partial<Toast>,
  ): string => {
    const item: Toast = {
      id: newId(),
      level: toast.level,
      title: toast.title,
      message: toast.message,
      createdAt: Date.now(),
      
      
      
      
      
      
      
      
      
      autoDismissMs: toast.action
        ? 0
        : toast.autoDismissMs && toast.autoDismissMs > 0
          ? toast.autoDismissMs
          : DEFAULT_DISMISS_MS,
      action: toast.action,
    }
    set((state) => ({ toasts: [...state.toasts, item] }))

    if (item.autoDismissMs > 0) {
      window.setTimeout(() => get().dismiss(item.id), item.autoDismissMs)
    }
    return item.id
  }

  const onReminder = (event: ReminderEvent): void => {
    push({
      level: 'info',
      title: '提醒',
      message: event.content,
      
      autoDismissMs: 0,
    })
    systemNotify('提醒时间到', event.content)
  }

  






  const openScheduledResult = async (sessionId: string): Promise<void> => {
    const chat = useChatStore.getState()
    
    
    
    
    
    
    useAppStore.getState().setView('chat')
    await chat.loadSessions()
    await useChatStore.getState().selectSession(sessionId)
  }

  const onNotice = (event: NoticeEvent): void => {
    push({
      level: event.level ?? 'info',
      title: event.title ?? '通知',
      message: event.message,
    })
  }

  const loop = async (): Promise<void> => {
    while (running) {
      const api = useAppStore.getState().api
      if (!api) {
        await new Promise((resolve) => setTimeout(resolve, 1000))
        continue
      }

      controller = new AbortController()
      try {
        set({ eventsConnected: true })
        await api.streamEvents(
          {
            onReminder,
            onNotice,
            onAny: (event, data) => {
              if (event === 'model_download') {
                
                
                
                
                
                
                useModelHubStore.getState().applyDownloadEvent(data ?? {})
              }
              if (event === 'model_fallback') {
                
                
                
                
                
                push({
                  level: 'warning',
                  title: '已切换到备用模型',
                  message:
                    (data?.message as string) ??
                    '主模型调用失败，本次回复由备用模型生成。',
                  autoDismissMs: 0,
                })
              }
              if (event === 'session_save_failed') {
                
                
                
                
                
                push({
                  level: 'error',
                  title: '对话未能保存',
                  message:
                    (data?.message as string) ??
                    '这一轮对话没有写入本机数据库，重启后可能丢失。',
                  autoDismissMs: 0,
                })
              }
              if (event === 'permission_request' && data?.request_id) {
                
                
                
                
                
                
                const groupName = typeof data.group_name === 'string' ? data.group_name : ''
                useChatStore.getState().setPermission({
                  requestId: String(data.request_id),
                  skillName: String(data.skill_name ?? ''),
                  displayName: String(data.display_name || data.skill_name || '工具'),
                  description: String(data.description ?? ''),
                  permissionLevel: String(data.permission_level ?? 'confirm'),
                  params: (data.params as Record<string, unknown>) ?? {},
                  prompt: String(data.prompt ?? ''),
                  source: groupName ? `群聊「${groupName}」` : undefined,
                })
                if (groupName) systemNotify(`群聊「${groupName}」有一个操作等待确认`, '打开应用点「允许」或「拒绝」。')
              }
              if (event === 'interaction_request' && data?.request_id) {
                
                
                
                
                const groupName = typeof data.group_name === 'string' ? data.group_name : ''
                useChatStore.getState().setInteraction(data)
                if (groupName) systemNotify(`群聊「${groupName}」有一个提问等待回答`, '打开应用作答。')
              }
              if (event === 'scheduled_task_done' || event === 'scheduled_task_failed') {
                
                
                
                
                const failed = event === 'scheduled_task_failed'
                const name = (data?.name as string) ?? '自动化任务'
                const sessionId = typeof data?.session_id === 'string' ? data.session_id : ''
                const title = failed ? `「${name}」执行失败` : `「${name}」已完成`
                
                
                
                void useChatStore.getState().loadSessions()
                
                
                
                
                
                for (const stale of get().toasts) {
                  if (stale.title === title) get().dismiss(stale.id)
                }
                push({
                  level: failed ? 'error' : 'success',
                  title,
                  message:
                    (data?.message as string) ??
                    (failed ? '这一轮没有跑成，可在「自动」页查看。' : '结果已保存到新会话里。'),
                  
                  
                  autoDismissMs: 0,
                  action:
                    !failed && sessionId
                      ? { label: '查看结果', run: () => openScheduledResult(sessionId) }
                      : undefined,
                })
                if (failed) systemNotify(`自动化任务「${name}」执行失败`, (data?.message as string) ?? '')
              }
              if (event === 'assistants_changed' || event === 'groups_changed') {
                
                
                
                
                
                
                void useAssistantStore.getState().load()
                if (event === 'groups_changed') void useGroupStore.getState().loadGroups()
              }
              if (event === 'skills_changed' || event === 'mcp_status') {
                





















                if (healthRefreshTimer !== null) window.clearTimeout(healthRefreshTimer)
                healthRefreshTimer = window.setTimeout(() => {
                  healthRefreshTimer = null
                  void useAppStore.getState().reloadHealth()
                }, 400)
              }
              if (event === 'memory_rebuilt') {
                










                rebuildNoticeCount += Number(data?.count ?? 0) || 0
                if (rebuildNoticeTimer !== null) window.clearTimeout(rebuildNoticeTimer)
                rebuildNoticeTimer = window.setTimeout(() => {
                  rebuildNoticeTimer = null
                  const total = rebuildNoticeCount
                  rebuildNoticeCount = 0
                  push({
                    level: 'success',
                    title: '长期记忆已整理好',
                    
                    message: `换过嵌入方式，已用当前模型把 ${total} 条记忆重新整理了一遍；原文一条都没少，现在可以照常问我以前的事了。`,
                  })
                }, 1200)
              }
              if (event === 'group_threads_changed') {
                







                const groupId = typeof data?.group_id === 'string' ? data.group_id : ''
                if (groupId) void useGroupStore.getState().reloadThreads(groupId)
              }
              if (event === 'group_event') {
                
                
                
                
                
                
                const groupId = typeof data?.group_id === 'string' ? data.group_id : ''
                const inner = typeof data?.event === 'string' ? data.event : ''
                
                
                
                const threadId = typeof data?.thread_id === 'string' ? data.thread_id : ''
                if (groupId && inner) {
                  useGroupStore.getState().applyRemoteEvent(
                    groupId,
                    threadId,
                    inner,
                    (data?.data as Record<string, unknown>) ?? {},
                  )
                }
              }
              if (event === 'group_task_started') {
                
                
                
                
                
                const groupId = typeof data?.group_id === 'string' ? data.group_id : ''
                const name = (data?.group_name as string) ?? '群聊'
                const autoOpen =
                  useAppStore.getState().settings?.agent?.auto_open_group_window ?? true
                if (groupId && autoOpen) window.agentBridge?.openGroupWindow?.(groupId, true)
                push({
                  level: 'info',
                  title: '已在后台开始讨论',
                  message: `「${name}」的搭子们正在讨论，结束后结论会发回你刚才那条对话。`,
                  autoDismissMs: 0,
                  action: groupId
                    ? {
                        label: '看它们讨论',
                        run: () => window.agentBridge?.openGroupWindow?.(groupId, true),
                      }
                    : undefined,
                })
              }
              if (event === 'group_task_done') {
                
                
                
                
                const sessionId = typeof data?.session_id === 'string' ? data.session_id : ''
                const groupId = typeof data?.group_id === 'string' ? data.group_id : ''
                const name = (data?.group_name as string) ?? '群聊'
                const ok = String(data?.outcome ?? 'done') === 'done'
                const chat = useChatStore.getState()
                if (sessionId && chat.activeSessionId === sessionId) {
                  
                  void chat.reloadMessages()
                }
                push({
                  level: ok ? 'success' : 'warning',
                  title: ok ? `「${name}」讨论有结论了` : `「${name}」讨论没能完成`,
                  message: ok
                    ? '结论已写在发起它的那条对话里，可以接着聊。'
                    : '它停下来了（原因写在对话里）。想看过程就点下面的按钮。',
                  autoDismissMs: 0,
                  action: sessionId
                    ? {
                        
                        label: '查看结论',
                        run: () => openScheduledResult(sessionId),
                      }
                    : groupId
                      ? {
                          label: '看讨论过程',
                          run: () => window.agentBridge?.openGroupWindow?.(groupId, false),
                        }
                      : undefined,
                })
              }
              for (const listener of listeners) {
                try {
                  listener(event, data)
                } catch {
                  
                }
              }
            },
          },
          controller.signal,
        )
      } catch {
        
      } finally {
        set({ eventsConnected: false })
        controller = null
      }

      if (!running) break
      await new Promise((resolve) => setTimeout(resolve, RECONNECT_DELAY_MS))
    }
  }

  return {
    toasts: [],
    eventsConnected: false,
    push,
    dismiss: (id) => set((state) => ({ toasts: state.toasts.filter((t) => t.id !== id) })),
    clearAll: () => set({ toasts: [] }),

    startEventStream: () => {
      if (running) return
      running = true
      void loop()
    },

    stopEventStream: () => {
      running = false
      controller?.abort()
      controller = null
      set({ eventsConnected: false })
    },
  }
})
