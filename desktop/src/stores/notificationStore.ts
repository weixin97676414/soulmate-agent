import { create } from 'zustand'

import type { NoticeEvent, ReminderEvent } from '@/services/api'
import { useAppStore } from '@/stores/appStore'
import { useAssistantStore } from '@/stores/assistantStore'
import { useChatStore } from '@/stores/chatStore'
import { useGroupStore } from '@/stores/groupStore'
import { useModelHubStore } from '@/stores/modelHubStore'

export type ToastLevel = 'info' | 'success' | 'warning' | 'error'

/** 通知上的一个动作按钮（例如定时任务的「查看结果」）。 */
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
  /** 毫秒；0 表示不自动消失 */
  autoDismissMs: number
  /**
   * 可选动作按钮。
   *
   * 有它的通知本该由用户**手动关掉**：按钮一闪而过就等于没有这个按钮，
   * 而"结果在新会话里"这种话不给出入口，用户只能自己去列表里翻。
   */
  action?: ToastAction
}

/**
 * 提示默认多久自动消失。
 *
 * ⚠️ 从 6 秒改成 **10 秒**（产品要求："所有提示弹窗，倒计时 10 秒后
 * 就自动消失"）。改这个默认值而不是逐个调用点传参：那要动二十多个文件，
 * 而且下一个新提示必然又忘。想要"常驻"的提示仍然显式传 `autoDismissMs: 0`。
 */
const DEFAULT_DISMISS_MS = 10000
const RECONNECT_DELAY_MS = 3000

interface NotificationState {
  toasts: Toast[]
  /** 事件流是否处于连接状态（顶部指示器用） */
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

/** 用系统通知再提醒一次：用户可能已经切到别的窗口了。 */
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
    // 通知不可用不影响应用内提示
  }
}

// 事件流的运行时句柄：不放进 store，避免订阅对象被当作状态比较
let controller: AbortController | null = null
let running = false

/**
 * 「刷新工具计数」的防抖句柄（见下面 `skills_changed` / `mcp_status` 的处理）。
 *
 * 放模块级而不是 store：它是个纯粹的调度细节，进 store 会让每次重启订阅
 * 都多一次无意义的状态更新。
 */
let healthRefreshTimer: number | null = null

/**
 * 「长期记忆重建完成」提示的聚合句柄（见下面 `memory_rebuilt` 的处理）。
 *
 * 每个搭子的记忆是**独立的库**，换一次嵌入方式会让它们各自重建、各发一条事件 ——
 * 不聚合的话，用户会连着看到四五条一模一样的提示，反而像是出了故障。
 */
let rebuildNoticeTimer: number | null = null
let rebuildNoticeCount = 0

/**
 * 应用级事件订阅。
 *
 * 全局只维持**一条**到 `/v1/events` 的长连接，需要感知服务端状态的组件
 * （例如 MCP 页签）通过这个函数挂载回调，而不是各自再开一条连接。
 */
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
      // ⚠️ **带按钮的通知常驻，其余一律按 10 秒**（产品拍板）。
      //
      // 来龙去脉：说过"所有右下角可能出现的提醒弹窗，比如群聊完成、
      // 自动化任务完成等等，都倒计时十秒消失"—— 那条**依然有效**，纯提醒仍然 10 秒。
      // 但它是在还没有"带按钮的通知"之前说的：像「查看结果」这种按钮，10 秒后
      // 连通知一起消失，用户根本来不及点，等于那个按钮不存在。
      // ⇒ 所以规则收敛成一条：**有 `action` 就常驻到手动关，没有就 10 秒**。
      // 这样将来再加带按钮的通知也不必记得传 `autoDismissMs: 0`（漏传就会变成
      // "按钮点不到"，而且没有任何报错）。
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
      // 纯提醒、没有按钮 ⇒ 按产品约定 10 秒后自动消失（只有带按钮的才常驻）
      autoDismissMs: 0,
    })
    systemNotify('提醒时间到', event.content)
  }

  /**
   * 打开定时任务产出的那条会话。
   *
   * 顺序不能反：`selectSession` 要先去 `sessions` 里查这条会话，才能把搭子与
   * 思考强度切回去 —— 而通知到达的这一刻，列表里可能还没有这条新会话
   * （它是刚刚在后台建出来的）。所以**先刷新、再选中**。
   */
  const openScheduledResult = async (sessionId: string): Promise<void> => {
    const chat = useChatStore.getState()
    // 这里原先有一段"正在生成就先拦住"的判断：那时 `selectSession` 在流式期间
    // 会直接早退（全局只有一个消息列表，切走会把正在写的内容丢进别的会话）。
    //
    // 起消息与运行态都按会话分桶，切换不再有任何代价，
    // `selectSession` 的早退也取消了 —— 于是这段拦截连同它的提示一起删掉：
    // 留着它只会让"查看结果"在后台有任务时被莫名挡住。
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
                // 本地模型（语音 / 嵌入）的下载进度（，模型改为按需下载）。
                //
                // ⚠️ 它**不弹 toast**：进度本来就该显示在"点了下载的那个卡片"里
                // （首启引导页 / 语音设置 / 长期记忆设置），弹通知反而会在下载的
                // 几分钟里刷屏。这里只把数据交给 `modelHubStore`，由卡片去渲染；
                // 断流时那边还有轮询兜底。
                useModelHubStore.getState().applyDownloadEvent(data ?? {})
              }
              if (event === 'model_fallback') {
                // 降级到备用模型。
                // 用户必须知道：输出风格、能力甚至**计费方**都变了，
                // 而界面上原本看不出任何区别。
                // 它是纯提醒（没有按钮）⇒ 按产品约定 10 秒后消失；真要回看
                // 还能在对话里看到那条模型切换的痕迹。
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
                // 落盘失败。后果是「重启后这一轮对话没了」，而界面上什么都看不出来 ——
                // 必须当场告诉用户。
                // ⚠️ 它是纯提醒（没有按钮）⇒ 按的"所有提醒都 10 秒"
                // 口径会自动消失。这是**已知的取舍**：真的要留住它，得给它配一个
                // 「重试保存」之类的按钮（那时它会自动变成常驻）。
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
                // 群聊里的确认请求走这条常驻通道（单聊走它自己那条 SSE 流，
                // 见 chatStore 的 onPermissionRequest）。两条来源落到**同一个**
                // `permission` 字段上，于是弹窗与回传只有一份实现。
                //
                // 为什么群聊不用自己那条流：一场讨论可能跑几分钟，用户会切页面，
                // 而确认必须在他切走之后依然弹得出来。
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
              if (event === 'scheduled_task_done' || event === 'scheduled_task_failed') {
                // 定时任务跑完 / 失败。
                //
                // 它必须被看见：后台任务没有界面，用户唯一能知道"今天那份早报出来了"
                // 的地方就是这条通知。
                const failed = event === 'scheduled_task_failed'
                const name = (data?.name as string) ?? '自动化任务'
                const sessionId = typeof data?.session_id === 'string' ? data.session_id : ''
                const title = failed ? `「${name}」执行失败` : `「${name}」已完成`
                // 主动刷新会话列表：定时任务是后台跑的，没有"这一轮流结束"那一下
                // 可以挂（单聊是靠流结束时刷新）。不刷新的话，那条新会话要等用户
                // 下一次操作甚至重启才出现 —— 而通知已经说了"结果在新会话里"。
                void useChatStore.getState().loadSessions()
                // 同一条任务反复跑（例如每 5 分钟一次）时不能把通知堆成一片：
                // 先收掉上一条同名的，界面上永远只有"最新一次"的入口，
                // 而它带的「查看结果」指向的也正是最新那条会话。
                // 这些通知都不自动消失（见下面的 autoDismissMs: 0），
                // 不去重的话几分钟就能铺满整个屏幕。
                for (const stale of get().toasts) {
                  if (stale.title === title) get().dismiss(stale.id)
                }
                push({
                  level: failed ? 'error' : 'success',
                  title,
                  message:
                    (data?.message as string) ??
                    (failed ? '这一轮没有跑成，可在「自动」页查看。' : '结果已保存到新会话里。'),
                  // 两条都不自动消失：失败的原因（地址失效、文件被删）需要用户
                  // 看着去改；完成那条带着「查看结果」，得留着让他随时点。
                  autoDismissMs: 0,
                  action:
                    !failed && sessionId
                      ? { label: '查看结果', run: () => openScheduledResult(sessionId) }
                      : undefined,
                })
                if (failed) systemNotify(`自动化任务「${name}」执行失败`, (data?.message as string) ?? '')
              }
              if (event === 'assistants_changed' || event === 'groups_changed') {
                // AI 自己建了搭子 / 建了群之后，把清单重拉一遍。
                //
                // 用户的原话："我发现了不是没有放在这两处，而是没有自动刷新" ——
                // 数据其实已经在配置里了，只是**这个窗口不知道**。所以后端改完就广播，
                // 这里收到就重拉：左侧搭子栏、设置 → 搭子、群聊列表立刻跟上。
                // 不弹通知：用户正在做的事没被打断，只是列表里多了一条。
                void useAssistantStore.getState().load()
                if (event === 'groups_changed') void useGroupStore.getState().loadGroups()
              }
              if (event === 'skills_changed' || event === 'mcp_status') {
                /*
                  工具清单变了 → 刷新标题栏右上角那个「N 个工具」。

                  ## ⚠️ 它原先只在启动与重启时更新

                  那个数字读的是 `/v1/health` 的 `skills` 字段，而它只在**握手**时
                  被拉取一次。于是用户上传一个技能包、装一个 MCP 服务之后，数字
                  纹丝不动 —— 他会以为没装上，然后反复重传实测反馈
                  就是这个）。数字是假的比没有数字更糟：它会被当成"权威答案"。

                  ## 为什么两件事共用一个处理

                  `skills_changed` 是自定义技能增删（后端在 `reload_custom_skills`
                  里发），`mcp_status` 是 MCP 服务的上下线 —— **MCP 工具也会随连接
                  状态增删**，两种都会改变那个数字。分两处写迟早漏一处。

                  ## 为什么要防抖

                  一个 MCP 服务从 starting → ready（或反复重连）会连发好几条
                  `mcp_status`。`/v1/health` 本身很轻，但每条都打一次纯属浪费 ——
                  与 `McpSettings` 里刷新技能清单用的是同一套 400ms 防抖。
                */
                if (healthRefreshTimer !== null) window.clearTimeout(healthRefreshTimer)
                healthRefreshTimer = window.setTimeout(() => {
                  healthRefreshTimer = null
                  void useAppStore.getState().reloadHealth()
                }, 400)
              }
              if (event === 'memory_rebuilt') {
                /*
                  长期记忆换嵌入模型后**重建完成**（核心见 memory/long_term.py）。

                  ⚠️ 这条提示不是"顺手加个 toast"，它是那次改动的组成部分：
                  重建要跑几十秒到几分钟，这期间检索是**跳过**的 —— 界面上一声不吭
                  的话，用户看到的就是"我问它以前的事，它说没有相关记忆"，然后合理
                  推断出"换个模型把我以前的记忆弄丢了"。这件事必须由应用亲口澄清。

                  多个库（每个搭子一个）会各发一条，所以这里做 1.2 秒聚合：
                  否则用户会连着看到四五条一模一样的提示，反而像是出了问题。
                */
                rebuildNoticeCount += Number(data?.count ?? 0) || 0
                if (rebuildNoticeTimer !== null) window.clearTimeout(rebuildNoticeTimer)
                rebuildNoticeTimer = window.setTimeout(() => {
                  rebuildNoticeTimer = null
                  const total = rebuildNoticeCount
                  rebuildNoticeCount = 0
                  push({
                    level: 'success',
                    title: '长期记忆已整理好',
                    // 重点在"没丢"，不在"重建了几条向量"——后者是内部概念
                    message: `换过嵌入方式，已用当前模型把 ${total} 条记忆重新整理了一遍；原文一条都没少，现在可以照常问我以前的事了。`,
                  })
                }, 1200)
              }
              if (event === 'group_threads_changed') {
                /*
                  某个群的**对话列表**变了（AI 建/改名/清空/删除了一条对话）。

                  ⚠️ 这条事件不能并进上面的 `groups_changed`：那条在界面上的动作是
                  `loadGroups()`（重拉**群**清单），而对话列表是"选中某个群之后"
                  才去拉的 —— 不单独发这一条，AI 改完对话之后用户正开着的那个列表
                  不会刷新，他会以为 AI 什么都没做。
                */
                const groupId = typeof data?.group_id === 'string' ? data.group_id : ''
                if (groupId) void useGroupStore.getState().reloadThreads(groupId)
              }
              if (event === 'group_event') {
                // 后台群聊的**实时事件**。
                //
                // 后台讨论没有 HTTP 订阅者（见 core 的 agent/orchestrator.py），所以它把
                // 每条事件经这条常驻通道广播出来 —— 只读观察窗就是靠它实时看到讨论的。
                // 落气泡时与 `/discuss` 的流式事件共用同一个 `applyGroupEvent`：
                // 两套渲染逻辑迟早会长歪（一边显示系统提示、另一边不显示）。
                const groupId = typeof data?.group_id === 'string' ? data.group_id : ''
                const inner = typeof data?.event === 'string' ? data.event : ''
                // ⚠️ `thread_id` 是**必需**的（一个群可以有多条对话）。
                // 后端每场讨论都归在某条对话下，前端靠它判断这批发言该画到哪条上；
                // 少了它就只能按群匹配，用户切到另一条对话时会看到不属于它的字冒出来。
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
                // AI 在**后台**开始了一场讨论：给用户开一个只读观察窗。
                //
                // 观察窗**不抢焦点**（见 electron/main.ts 的 showInactive）—— 它是在用户
                // 没要求的时候自己弹出来的，抢焦点等于顶掉他正在打的字。不想要它的人
                // 可以在「设置 → 安全与通用」里关掉这个开关。
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
                // 后台讨论结束了：结论已经由**后端**写进发起它的那条会话。
                //
                // 这里是"把这件事变成看得见"的唯一机会 —— 后台跑完不吭声是这类功能
                // 最招人恨的地方（用户以为它还在跑）。
                const sessionId = typeof data?.session_id === 'string' ? data.session_id : ''
                const groupId = typeof data?.group_id === 'string' ? data.group_id : ''
                const name = (data?.group_name as string) ?? '群聊'
                const ok = String(data?.outcome ?? 'done') === 'done'
                const chat = useChatStore.getState()
                if (sessionId && chat.activeSessionId === sessionId) {
                  // 用户正看着那条会话：重读一次，界面就与库里一致
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
                        // 复用定时任务那套「刷新列表 → 选中会话」（它做的就是这件事）
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
                  // 单个订阅者的异常不能影响其他订阅者
                }
              }
            },
          },
          controller.signal,
        )
      } catch {
        // 连接断开/被中止：下面统一处理重连
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
