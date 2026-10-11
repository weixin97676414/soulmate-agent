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

/** 每天只提示一次预算超支，避免每条消息都弹一次把用户烦到关掉提示 */
let budgetWarnedOn = ''

/**
 * 发送前的预算提示。
 *
 * 按用户设定：**只警告、不阻止**。之所以不直接拦截，是因为用户可能正在
 * 一个关键任务中间，拦下来只会让人绕道去用别的工具；提示的价值在于
 * "让你知道你正在超支"，而不是替你做决定。
 */
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

/**
 * 把后端注入的附件上下文从用户消息里剥掉，只留用户真正打的字。
 *
 * 后端需要把文件绝对路径送进模型上下文，因此会拼在用户消息前面；
 * 但那一段属于"机器写给模型看的"，不该出现在聊天气泡里。
 */
export function stripAttachmentBlock(content: string): string {
  if (!content.startsWith(ATTACHMENT_OPEN)) return content
  const end = content.indexOf(ATTACHMENT_CLOSE)
  if (end < 0) return content
  return content.slice(end + ATTACHMENT_CLOSE.length).replace(/^\s+/, '')
}

export type DrawerTab = 'trace' | 'artifacts'

/**
 * 桶键：会话没有 id 时用"临时键"。
 *
 * 一条新对话在**后端首次回 meta 之前**还没有 id（会话是发送时才创建的），
 * 但消息已经要显示出来了。所以给它一个**每次新建都不同**的临时键，
 * 等 meta 带着真 id 回来时再把整个桶搬过去。
 *
 * ⚠️ 为什么不用一个固定的空串当临时键：那样"在前一条新对话还在跑的时候又建一条"
 * 会让两条对话共用同一个桶 —— 用户会看到新对话里冒出上一个对话的内容，
 * 而且那条还在跑的 run 结束后会把消息迁到一个不属于它的会话 id 上。
 * 每次新建换一个键，这类串味就不存在了。
 */
const keyOf = (state: { activeSessionId: string | null; pendingSessionKey: string }): string =>
  state.activeSessionId ?? state.pendingSessionKey

/**
 * 一轮正在进行的任务。
 *
 * ## 为什么按 `runId` 而不是按 sessionId 存
 *
 * 新会话在 `meta` 到达前只有临时桶键（`''`），那一刻如果按 sessionId 索引，
 * 流回调闭包里捕获的键在 meta 之后就**过期了** —— 分片会写进一个已经不存在的桶。
 * 用稳定的 `runId` 作键、把"当前桶键"放在 `sessionId` 字段里随时更新，
 * 就绕开了这类错位。
 */
interface RunState {
  runId: string
  /** 当前桶键（新会话一度是 `''`，meta 到达后换成真 id） */
  sessionId: string
  /** 这一轮服务的是哪个搭子（标题栏的「XX 正在工作」用） */
  assistantId: string | null
  /** 本轮的助手消息 id：所有补丁**只打这一条**，不再"找最后一条 assistant" */
  assistantMessageId: string
  taskId: string | null
  abort: AbortController
  startedAt: number
}

interface ChatState {
  sessions: SessionSummary[]
  activeSessionId: string | null
  /**
   * 新对话的临时桶键（每次「新建对话」都换一个，见 `keyOf` 的说明）。
   *
   * 会话是**后端在首次发送时才创建**的，所以"还没发过消息的新对话"没有 id；
   * 消息与运行态先挂在这个临时键下，meta 一回来就整体迁到真 id 上。
   */
  pendingSessionKey: string
  /**
   * **按会话分桶**的消息。切走、切回来看到的就是各会话自己的那一份。
   *
   * 这是"切换不打断"的根基：后台那一轮把分片写进**它自己那条会话**的桶，
   * 与"用户当前看到哪一条"彻底解耦。改造前只有一个全局 `messages`，
   * 所以流式期间必须禁止切换（否则分片会写进别的会话）。
   */
  messagesBySession: Record<string, ChatMessage[]>
  /**
   * **当前可见会话**的那一份消息。
   *
   * 保留这个字段（而不是让所有消费方改成 `messagesBySession[activeSessionId]`）
   * 是为了让 `ChatView` / `MessageItem` / `ContextUsagePill` 等零改动 ——
   * 它们读到的语义与改造前完全一致。
   */
  messages: ChatMessage[]
  /** 正在跑的每一轮，键是 `runId`（见 RunState 的说明）。可以同时有多轮。 */
  runs: Record<string, RunState>
  /** 本会话使用的模型；为空表示跟随后端默认模型 */
  modelId: string | null
  /**
   * 本会话的思考强度：`'low' | 'medium' | 'high'`，`null` = 不发送该参数。
   *
   * 每轮发送时都会带上它（含 null），后端据此覆盖会话记录 —— 这样"用户选了档位
   * 但还没发消息就关掉应用"之外的情况都能落库。
   */
  reasoningEffort: string | null
  /**
   * **当前可见会话**是否在跑。
   *
   * 语义从"全局有没有任务在跑"改成了"我现在看的这条在不在跑"：多个会话可以
   * 同时各跑一轮，而输入框该显示「发送」还是「停止」只取决于**眼前这条**。
   */
  streaming: boolean
  /**
   * 待用户答复的工具确认，**队列**。
   *
   * 从单值改成队列的原因：多个会话同时跑时，后台那一轮的确认请求会被后到的
   * 顶掉，而它还在等 —— 结果就是那一轮永远醒不过来。队列保证每条都轮得到。
   */
  permissions: PermissionRequest[]
  /** 队首（= 此刻该展示的那一条）。派生字段，改 `permissions` 时一起更新。 */
  permission: PermissionRequest | null
  /**
   * 待用户作答的**技能交互**（选择 / 敏感输入），同样是**队列**。
   *
   * ⚠️ 用队列的理由与 `permissions` 完全一样：多个会话同时跑时，
   * 后台那一轮的请求会被后到的顶掉，而它还在等 —— 那一轮会永远醒不过来
   * （界面上就是"卡住不动"，而且没有任何报错）。
   */
  interactions: InteractionEvent[]
  /** 队首（= 此刻该展示的那一条）。派生字段。 */
  interaction: InteractionEvent | null
  /** 当前可见会话的链路数据（同样按会话分，避免抽屉里串味） */
  trace: TraceData | null
  tracesBySession: Record<string, TraceData>
  /** 右侧抽屉：是否展开、当前页签 */
  drawerOpen: boolean
  drawerTab: DrawerTab | null
  /** 本次会话的产物清单（供右侧抽屉预览） */
  artifacts: FileRecord[]
  draft: string
  attachments: PendingAttachment[]
  persistent: boolean
  sessionsLoading: boolean
  /**
   * 正在为**哪个搭子**、哪个会话干活（有任务在跑期间有值）。
   *
   * 产品要求：「给 buddy 安排工作后切到别的页面，它得能在后台继续」。
   * 任务本身早就跑在 store 里（不随页面卸载而中断），但**界面上看不见**，
   * 用户完全无从判断它到底还在不在干活 —— 于是只能靠"切回去看内容有没有变"。
   * 这三个字段就是为了让"它在后台工作"变成**看得见**的事实：标题栏据此显示运行指示。
   *
   * 允许多轮同时跑之后，它们指向**最近启动的那一轮**（代表性地告诉用户"在忙"），
   * 数量由 `runs` 自己数得出来（见 TitleBar 的「N 个搭子正在工作」）。
   * ⚠️ 改造前搭子栏还用 `streaming` 来"禁止切搭子"，那条约束已经取消 ——
   * 现在的口径是"随便切，不打断"。
   */
  runningAssistantId: string | null
  runningSessionId: string | null
  runningStartedAt: number | null

  loadSessions: () => Promise<void>
  selectSession: (id: string) => Promise<void>
  /**
   * 重新拉一次**当前会话**的消息。
   *
   * 后台群聊跑完时，结论由**后端**写进发起它的那条会话（见 core 的
   * agent/orchestrator.py）：这里重读一次，界面就与库里一致。
   * 刻意**不**在前端自己拼一条消息塞进去 —— 那样重启后就只剩库里那一份，
   * 而两份的措辞可能早就不同了（那正是"同一件事两种说法"的来源）。
   */
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
  /**
   * 发一条消息。
   *
   * ``displayText`` 只影响**气泡里显示什么**：发给模型的仍然是 ``text``。
   * 目前唯一的用法是「继续」——后端给的那段续跑提示（``[续跑] 上一轮…``）是
   * 协议的一部分，绝不能当成用户自己说过的话显示出来（用户看到一长串内部措辞
   * 会以为界面坏了），所以气泡里只显示「继续」两个字。
   */
  send: (text?: string, displayText?: string) => Promise<void>
  stop: () => Promise<void>
  respondPermission: (approved: boolean) => Promise<void>
  /**
   * 回传对**执行计划**的决定（单聊计划模式）。
   *
   * `approved` 为 true 是「开始执行」；false 时若 `feedback` 非空是「改一下」，
   * 空则视为「不用了」。
   *
   * ⚠️ `planId` 由**卡片自己**传进来（就是它渲染的那一版计划的 id）。
   * 改造前这里是"去消息列表里反查哪一份在等待确认"—— 消息按会话分桶之后，
   * 那个反查会扫到**错误的会话**（用户在 A 卡片上点，却可能作用到 B 会话
   * 正在等待的那一版计划）。让调用方把 id 说清楚，这条路就被堵死了。
   */
  respondPlan: (planId: string, approved: boolean, feedback?: string) => Promise<void>
  /**
   * 把"有操作等确认"这件事置位（由**全局事件流**调用）。
   *
   * 单聊的确认请求来自它自己那条 SSE 流，而**群聊**的确认走的是常驻
   * `/v1/events` 通道（群讨论的流里没法插入确认，见后端 groups.py 的说明）。
   * 两条来源最终落到同一个 `permission` 字段上，于是弹窗与回传链路只有一份实现。
   */
  setPermission: (request: PermissionRequest | null) => void
  /**
   * 回传用户对交互弹窗的作答（选择 / 敏感输入）。
   *
   * ⚠️ `answer.names` 只带引用名、**不带值** —— 敏感内容由弹窗直接写本地加密
   * 文件（见 `electron/skill-secrets.ts`）。这条请求会进服务端日志与审计。
   */
  respondInteraction: (answer: InteractionAnswer) => Promise<void>
  setDrawerOpen: (open: boolean) => void
  setDrawerTab: (tab: DrawerTab) => void
  loadArtifacts: () => Promise<void>
  deleteArtifact: (id: string) => Promise<void>
}

// --------------------------------------------------------------------------- //
// 运行时对象：不放进 store，避免触发无谓的渲染
// --------------------------------------------------------------------------- //
/**
 * 每一轮的流式缓冲与合帧句柄，**按键是 runId**。
 *
 * 改造前这里是四个模块级单例（`deltaBuffer` / `reasoningBuffer` / `flushHandle` /
 * `abortController`）。多会话同时跑时它们会被互相覆盖：B 会话开跑会把 A 会话
 * 攒了一半的分片清掉、把 A 的合帧句柄 `cancelAnimationFrame` 掉、
 * 把 A 的 abort controller 顶掉（于是"停止"停不下来）。
 *
 * 放进 Map 而不是放进 store：这些值**每帧都在变**，进 store 等于每个 token
 * 都触发一次全量订阅者重算 —— 与"按帧批量提交"的初衷正好相反。
 */
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

/** 空数组常量：保持引用稳定，避免"桶里没内容"时每帧生成新数组导致的重渲染 */
const EMPTY_MESSAGES: ChatMessage[] = []

/** 某个桶键下的那一份消息 */
function visibleMessages(
  key: string,
  bySession: Record<string, ChatMessage[]>,
): ChatMessage[] {
  return bySession[key] ?? EMPTY_MESSAGES
}

/**
 * 某个桶键在不在跑。
 *
 * 只认"桶键相同"的那一轮：后台会话跑得再欢，也不该把眼前这条的输入框
 * 变成「停止」。
 */
function visibleStreaming(key: string, runs: Record<string, RunState>): boolean {
  return Object.values(runs).some((run) => run.sessionId === key)
}

/**
 * 由 `runs` 推出标题栏要用的「正在工作」摘要（最近启动的那一轮）。
 *
 * 多轮并发时"最近启动"是一个诚实的代表：它至少保证有任务在跑时指示**一定**亮着，
 * 而具体有几个由 `runs` 的元素个数给出（标题栏显示「N 个搭子正在工作」）。
 */
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

/**
 * 把后端给的历史消息转成界面用的结构。
 *
 * 抽出来是因为有**两个**入口要用：切会话（`selectSession`）与"后台群聊跑完了、
 * 把结果读回来"（`reloadMessages`）。两处各写一份转换，迟早会出现"从某一处进来的
 * 消息没有时间戳"这类只在一半路径上出现的怪现象。
 */
function toChatMessages(
  // created_at 可能是 null / 缺省（更早版本落盘的老消息）→ 按"不知道时间"处理
  items: Array<{
    role: string
    content: string
    created_at?: number | null
    plan?: Plan | null
  }>,
): ChatMessage[] {
  return items.map((message) => ({
    id: newId(),
    role: message.role as ChatMessage['role'],
    content:
      message.role === 'user' ? stripAttachmentBlock(message.content) : message.content,
    reasoning: '',
    toolCalls: [],
    status: 'done' as const,
    // 用**后端给的时刻**（它才是这条消息真正发生的时间）。
    // 0 = 不知道（更早版本落盘的老消息时间戳不可信）→ 界面上不显示时间。
    createdAt: message.created_at ? message.created_at * 1000 : 0,
    // 计划随消息回读：老消息没有这个字段 → undefined，界面不画卡片、不报错
    plan: message.plan ?? undefined,
  }))
}

/**
 * 「链路与产物」抽屉的自动展开记账（按会话）。
 *
 * ⚠️ 为什么不放进 store 的 state：这两个集合**变化时界面不需要重渲染**
 * （它们只在"要不要自动开抽屉"这一个判断里被读）。放进 state 会让每次工具调用
 * 都触发一轮订阅通知，而工具调用可能一秒好几次。
 *
 * 两者是互补的：
 * - `drawerAutoOpened`：已经为这个会话自动开过了，别反复开（用户手动关了又开、
 *   开了又关时不会来回弹）；
 * - `drawerAutoSuppressed`：用户**手动关过**。他关掉就是在说"我知道有这个，
 *   现在不想看" —— 再自动弹出来是最招人烦的一类交互。
 */
const drawerAutoOpened = new Set<string>()
const drawerAutoSuppressed = new Set<string>()

/**
 * 把后端下发的交互事件**拍平**成前端用的形状，并补上来源会话。
 *
 * ⚠️ 后端下发的形状是**嵌套**的：`{request_id, kind, payload: {...}, prompt}` ——
 * 因为 `choice` 与 `secret` 两种请求的内容字段完全不同（一个要 `options`、
 * 一个要 `fields`），后端用一个 `payload` 袋子装，免得让两个技能共用一个
 * 布满可选字段的扁平结构。前端这边则相反：弹窗是一份组件，扁平更好写。
 * 两边形状不同没关系，**但转换只能有这一处** —— 散在组件里迟早对不上。
 *
 * ⚠️ `kind === 'secret'` 时，`fields` 里**只有名字与提示**：用户粘贴的内容
 * 由弹窗直接写进本地加密文件，**从来不会出现在这个事件里**。
 * 所以这个函数不需要、也绝不应该处理"值"。
 */
/** 后端 `InteractionRequest.to_dict()` 下发的**原始**形状（下划线命名）。 */
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
    // 选择题的标题后端放在 `payload.question`，同时也有一份 `prompt`；
    // 字段缺失时回落到 prompt，再没有就空串（弹窗会显示一句兜底文案）
    question: payload.question || raw.prompt || '',
    options: Array.isArray(payload.options) ? payload.options : [],
    // 默认**允许**自定义输入（产品约定是"要能自己填一个"）；
    // 只有后端明确说 false 才关掉
    allowCustom: payload.allow_custom !== false,
    reason: payload.reason || raw.prompt || '',
    fields: Array.isArray(payload.fields) ? payload.fields : [],
    sessionKey,
    ...(sessionTitle ? { sessionTitle } : {}),
  }
}

export const useChatStore = create<ChatState>((set, get) => {
  /**
   * 给**某一轮**的助手消息打补丁。
   *
   * 定位方式从"找消息列表里最后一条 assistant"改成了"按 runId 找到那一轮，
   * 再按它记下的 `assistantMessageId` 精确定位"。这是"切走不写错会话"的关键：
   * 老写法在用户切了会话之后**必然**打错桶（分片会补到别的对话上）。
   */
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
      // 只有改的是**当前可见**会话时才动 `messages`；后台会话的补丁不该
      // 让用户眼前的列表产生任何变化（连"重建一次数组"都不必要）
      return keyOf(state) === run.sessionId
        ? { messagesBySession, messages }
        : { messagesBySession }
    })
  }

  /** 取该轮的缓冲（没有就建一个） */
  const bufferOf = (runId: string): RunBuffer => {
    let buffer = runBuffers.get(runId)
    if (!buffer) {
      buffer = { delta: '', reasoning: '', flush: null }
      runBuffers.set(runId, buffer)
    }
    return buffer
  }

  /** 把该轮攒下的正文与思维链合并成**一次** patch（分开调用会连续重建两次数组） */
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

  /**
   * 加入一条工具确认请求。
   *
   * 用**队列**而不是单值：多个会话同时跑时，后台那一轮的确认请求会被后到的
   * 顶掉，而它还在等 —— 结果是那一轮永远醒不过来（界面上表现为"卡住不动"）。
   */
  const pushPermission = (request: PermissionRequest): void => {
    set((state) => {
      const permissions = [...state.permissions, request]
      return { permissions, permission: permissions[0] ?? null }
    })
  }

  /** 把某条确认从队列里摘掉（用户答完了，或那一轮已经结束） */
  const dropPermission = (requestId: string): void => {
    set((state) => {
      const permissions = state.permissions.filter((item) => item.requestId !== requestId)
      return { permissions, permission: permissions[0] ?? null }
    })
  }

  /** 丢掉某个会话残留的确认请求（那一轮已经结束，后端也不会再等了） */
  const dropPermissionsOf = (sessionKey: string): void => {
    set((state) => {
      const permissions = state.permissions.filter((item) => item.sessionId !== sessionKey)
      if (permissions.length === state.permissions.length) return {}
      return { permissions, permission: permissions[0] ?? null }
    })
  }

  // ---- 技能交互（选择 / 敏感输入）------------------------------------ //
  // ⚠️ 与上面那三个是**并行的另一套**，不是复用：权限确认的答复是布尔、
  // 走 /v1/confirm；交互的答复是任意结构、走 /v1/interaction/decision。
  // 混用会让"答了哪一条"对不上（两套队列共用 id 空间是不可能的，
  // 而且权限那条的收尾逻辑带 interrupted 语义，掺进来会互相干扰）。

  /** 加入一条交互请求（队尾），并刷新队首。 */
  const pushInteraction = (request: InteractionEvent): void => {
    set((state) => {
      const interactions = [...state.interactions, request]
      return { interactions, interaction: interactions[0] ?? null }
    })
  }

  /** 把某条交互从队列里摘掉（用户答完了，或那一轮已经结束）。 */
  const dropInteraction = (requestId: string): void => {
    set((state) => {
      const interactions = state.interactions.filter((item) => item.requestId !== requestId)
      return { interactions, interaction: interactions[0] ?? null }
    })
  }

  /** 丢掉某个会话残留的交互请求（那一轮已经结束，后端也不会再等了）。 */
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

    // ---------------------------------------------------------------- //
    // 会话
    // ---------------------------------------------------------------- //
    loadSessions: async () => {
      const api = useAppStore.getState().api
      if (!api) return
      set({ sessionsLoading: true })
      try {
        const payload = await api.getSessions()
        set({ sessions: payload.sessions, persistent: payload.persistent })
      } catch (error) {
        // 原先只有 try/finally：出错时异常直接冒到 `void loadSessions()`，
        // 变成一个没人处理的 rejection。界面上会话列表就是空的，
        // 用户分不清"还没有会话"和"读取失败了"—— 前者正常，后者要重试。
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
      // ⚠️ 这里**不再**因为"正在回答"而早退（「切换对话，切换搭子，
      // 切换到任何页面都不打断」）。
      //
      // 改造前必须早退，是因为全局只有一个 messages 列表：切走之后，流式分片会
      // 补到**别人**的对话上。现在每一轮写的是"它自己那条会话的桶"（见 patchInRun），
      // 切走完全安全 —— 那一轮继续跑，切回来就能看到完整结果。
      set((state) => ({
        activeSessionId: id,
        messages: visibleMessages(id, state.messagesBySession),
        // 这两个是"跟随可见会话"的派生值，一起换
        trace: state.tracesBySession[id] ?? null,
        streaming: visibleStreaming(id, state.runs),
        attachments: [],
        // ⚠️ 刻意**不**清空 permissions：那个队列里可能正躺着**别的**会话
        // 发来的确认请求，清掉就等于让那一轮永远醒不过来
      }))

      // 会话自己记着用的哪个助手，切换会话要跟着切回去，
      // 否则用户会看到"同一个会话，人设却变了"
      const session = get().sessions.find((item) => item.id === id)
      if (session) {
        useAssistantStore.getState().setActive(session.assistant_id)
        // 思考强度同样是"会话自己的偏好"，不跟着走会让控件显示成"未设置"，
        // 而用户明明在这个对话里调过
        set({ reasoningEffort: session.reasoning_effort })
      }

      try {
        const api = useAppStore.getState().api
        if (!api) return
        const payload = await api.getMessages(id)
        // 只往**这条会话自己的桶**里写；`messages` 是否跟着变由 visibleMessages
        // 判断（用户在读取期间又切走了的话，就不该动他眼前的列表）
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
      } catch (error) {
        // **不能静默清空。** 原实现只有 `set({ messages: [] })`：用户看到的是
        // 一个空白会话，自然会认为"我的历史记录丢了"，而实际上只是这次读取失败。
        // 两者的处置完全不同（一个要重试，一个只能接受），必须让他分得清。
        set((state) => {
          const messagesBySession = { ...state.messagesBySession, [id]: [] }
          return {
            messagesBySession,
            messages: visibleMessages(keyOf(state), messagesBySession),
          }
        })
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
        // 读取期间用户可能已经切走、或者又发了一轮：只在"还是同一条会话"
        // 时才覆盖 —— 否则会把他眼前的内容换掉。
        //
        // ⚠️ 判据里**去掉了 `get().streaming`**：改造前"正在跑就不覆盖"是为了
        // 避免丢掉还没 flush 的分片；现在分片写在该会话自己的桶里，
        // 覆盖等于把"库里已落盘的完整回复"换上来，反而是件好事。
        // 但**正在跑的那一条仍要跳过**：库里还没有这一轮的消息，
        // 覆盖会让用户眼前的回复瞬间消失。
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
        // 静默：结果已经落在库里，用户切一下会话就能看到，不值得打断他
      }
    },

    startNewSession: () => {
      // ⚠️ 同样不再早退：切走一个正在跑的会话是允许的，它会在后台跑完。
      // 新对话换一个**全新**的临时键：这样"上一条新对话还在跑、又建一条"时，
      // 两者不会共用同一个桶（否则新对话里会冒出上一个对话的内容）。
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
      // 刻意**不重置助手**：沿用当前选择。用户刚切到"生活管家"，
      // 开新对话多半还是想继续用它；每次都弹回默认助手反而更烦。
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
      // 删掉正在生成的那个会话，流式回调之后会往一个已经删掉的会话里写，
      // 界面上表现为"删除之后消息又冒出来了"，而后端也会因为会话不存在而报错。
      // 直接拒绝比"先悄悄停掉再删"好：用户可能是手滑点错了。
      //
      // ⚠️ 判据从全局 `streaming` 收窄成"**这条会话**在不在跑"：
      // 后台别的会话在跑不该妨碍我删掉一条已经说完的对话。
      if (visibleStreaming(id, get().runs)) {
        useNotificationStore.getState().push({
          level: 'warning',
          title: '正在生成，无法删除',
          message: '请先点「停止」，再删除这个会话。',
        })
        return
      }
      await api.deleteSession(id)
      // 把它的桶也扔掉：留着只会白占内存，而且万一以后 id 被复用会看到幽灵消息
      set((state) => {
        const messagesBySession = { ...state.messagesBySession }
        delete messagesBySession[id]
        const tracesBySession = { ...state.tracesBySession }
        delete tracesBySession[id]
        return { messagesBySession, tracesBySession }
      })
      // 删掉的正是当前会话时才换到新对话（否则用户会被莫名切走）
      if (get().activeSessionId === id) get().startNewSession()
      await get().loadSessions()
    },

    clearHistory: async () => {
      const key = keyOf(get())
      // 生成过程中清空，之后每个分片都会补回到被清空的消息列表上 ——
      // 用户看到的是"清空了，但内容又自己长回来了"。这比报个错更让人害怕。
      //
      // 判据同样是"**这一条会话**在不在跑"（后台别的会话不受影响）。
      if (visibleStreaming(key, get().runs)) {
        useNotificationStore.getState().push({
          level: 'warning',
          title: '正在生成，无法清空',
          message: '请先点「停止」，再清空当前会话。',
        })
        return
      }

      const sessionId = get().activeSessionId
      // 还没落库的新对话（没有 id）：清空就是把这个临时桶置空
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
        // 链路数据也一起清：留着上一轮的 trace 会让抽屉显示"刚才那次的耗时"
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

    // ---------------------------------------------------------------- //
    // 输入
    // ---------------------------------------------------------------- //
    setModelId: (id) => set({ modelId: id }),
    setReasoningEffort: (effort) => set({ reasoningEffort: effort }),
    setDraft: (value) => set({ draft: value }),

    // ---------------------------------------------------------------- //
    // 附件
    // ---------------------------------------------------------------- //
    addFiles: async (files) => {
      const api = useAppStore.getState().api
      if (!api || files.length === 0) return
      // 上传流程与群聊**共用一份实现**（services/attachments.ts）：
      // 占位 → 上传 → 回填/标红，两边各写一遍必然会在某一步上长歪
      await addFilesTo(get().attachments, files, {
        api,
        sessionId: get().activeSessionId ?? undefined,
        onChange: (next) => set({ attachments: next }),
      })
    },

    removeAttachment: (id) =>
      set((state) => ({ attachments: state.attachments.filter((item) => item.id !== id) })),

    // ---------------------------------------------------------------- //
    // 发送
    // ---------------------------------------------------------------- //
    send: async (text, displayText) => {
      const message = (text ?? get().draft).trim()
      const ready = get().attachments.filter((item) => item.status === 'ready')
      // 允许**只发附件**（产品要求）：任务常常整份都在附件里，
      // 逼用户再打一句废话是不合理的。只有"既没文字也没附件"才拦住。
      if (!message && ready.length === 0) return

      // ⚠️ 拦截从"全局有任务在跑"收窄成"**这一条会话**已经在跑"。
      //
      // 改造前是 `get().streaming`：别的会话在跑时，这一条连发都发不出去。
      // 现在允许多条同时跑，只拦"同一条会话里发第二次"（两条回答会抢同一个
      // 气泡，本来就不该允许），其余会话照发不误。
      const runKey = keyOf(get())
      if (visibleStreaming(runKey, get().runs)) return

      // 直接取 api 而不是抛错，避免在 async 函数开头抛错变成未捕获的 rejection。
      // 但**必须给出反馈**：用户按了发送却什么都不发生，比报错更让人困惑 ——
      // 尤其是后端崩溃重启之后（那时界面看起来还是"已就绪"）。
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
      // 图片单独成组：后端会把它作为图片内容块发给模型，
      // 而不是像普通附件那样只把文件名与路径拼进文字
      const imageIds = ready.filter((item) => item.kind === 'image').map((item) => item.id)

      const now = Date.now()
      const userMessage: ChatMessage = {
        id: newId(),
        role: 'user',
        // 气泡里显示 displayText（有的话）：它是"用户会说的话"，
        // 而 message 可能是协议文本（见接口上的说明）。
        // 两者都空（只发了附件）时，用一句可读的说明顶上 —— 空气泡会让用户
        // 以为"没发出去"，而实际上任务已经在跑了。
        content:
          displayText?.trim() ||
          message ||
          `已发送附件：${ready.map((item) => item.name).join('、')}`,
        reasoning: '',
        toolCalls: [],
        status: 'done',
        createdAt: now,
      }
      const assistantMessage: ChatMessage = {
        id: newId(),
        role: 'assistant',
        content: '',
        reasoning: '',
        toolCalls: [],
        status: 'streaming',
        createdAt: now + 1,
      }

      // 这一轮的运行时对象**按 runId 独立**：多会话同时跑时互不覆盖
      // （改造前是四个模块级单例，B 会话一开跑就会冲掉 A 的缓冲与控制器）
      const runId = newId()
      runBuffers.set(runId, { delta: '', reasoning: '', flush: null })
      const abort = new AbortController()

      // 模型与搭子在**入队前**取好：它们要一起进下面那次 set，
      // 而且之后用户可能立刻去切搭子，那时再读就不是"这一轮"的了。
      const modelId =
        get().modelId ?? useAppStore.getState().modelDefaults.effectiveDefault ?? undefined
      const assistantId = useAssistantStore.getState().activeId ?? undefined

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
        // 这一轮产生的链路数据从零开始（上一轮的 trace 不该挂在新一轮上）
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
          // 登记"正在为谁干活"：标题栏据此显示运行指示（要求 #8）
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
            // 每轮都带上当前的档位（含 null）—— 后端把 null 当作"就是不发送"。
            // 带上而不是"改过才带"，是为了让"切会话后不匹配"这类问题没有藏身处。
            reasoning_effort: get().reasoningEffort,
          },
          {
            onMeta: (meta) => {
              // 新会话**在这里**才拿到真 id（会话是发送时后端才创建的）。
              // 把这一轮的桶整体搬到真 id 下，并让"当前可见会话"跟着走。
              //
              // `stillVisible` 这道判断防的是：用户在这几百毫秒里已经按了
              // Ctrl+N 或切去了别处 —— 那时**不能**把他拽到这条新会话上
              // （他眼睛里是另一条，突然被换掉比"没反应"更让人困惑）。
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
                // 临时键用完就作废（下次「新建对话」会再取一个全新的）
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
            },
            onWarning: (data) => {
              // 非致命提醒（例如"图片没发出去，因为模型没开图片支持"）。
              // 不用 error 级别：这一轮会正常出结果，用红色错误框会让用户
              // 以为整条消息失败了。
              useNotificationStore.getState().push({
                level: 'warning',
                title: '提示',
                message: data.message,
                autoDismissMs: 0,
              })
            },
            onContextCompressed: () => {
              // 上下文被压成摘要了。**这不是错误**，但必须让用户知道：
              // 模型接下来可能对更早的细节记不清，而用户的第一反应是
              // "它怎么突然不记得了" —— 没有任何提示的话，他只会觉得模型变笨。
              //
              // 用 info 级别、可自动消失：它是"发生了什么"的说明，
              // 不是需要用户处理的问题。文案里强调**记录没丢**，
              // 因为这才是用户真正会担心的那件事。
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
              // 注入告警**必须留在屏幕上**（autoDismissMs: 0）。
              // 一闪而过等于没说 —— 用户不会为了一条自动消失的提示回头翻记录，
              // 而这条恰恰是"这次回答可能不可信"的唯一信号。
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
            // 思维链同样按帧批处理。
            //
            // 它原先是一条一分片直接 patch：每次 patch 都会重建整个 messages
            // 数组和消息对象。推理模型的思维链动辄几千字，观感和性能问题
            // 都和正文一样，没理由只优化正文那一半。
            onReasoning: (text) => queueReasoning(runId, text),
            onToolCall: (data) => {
              // 工具调用卡片在流式过程中插入，状态先置为「运行中」
              const tool: ToolCallState = {
                id: data.id,
                name: data.name,
                displayName: data.display_name || data.name,
                description: data.description,
                params: data.params ?? {},
                permissionLevel: data.permission_level ?? 'safe',
                status: 'running',
                // 时间跟工具卡走：正文里不再有模型写的时间戳，
                // 每次调用发生在几点，就显示在它自己的卡片上。
                // core 给的是 epoch 秒，本应用的显示口径是毫秒（见 lib/time.ts）
                startedAt: data.started_at ? data.started_at * 1000 : undefined,
              }
              patchInRun(runId, (m) => ({ ...m, toolCalls: [...m.toolCalls, tool] }))

              // ---- 本次对话首次调工具 → 自动展开「链路与产物」----
              //
              // 产品要求。配合的另一半是"对话栏不再展示工具调用记录"：
              // 过程信息挪进了抽屉，所以第一次需要它的时候必须自己把门推开 ——
              // 否则用户会以为"工具调用记录被我弄没了"。
              //
              // ⚠️ 每个会话**只自动开一次**，而且**用户手动关过之后本会话不再开**：
              // 他关掉的动作就是在说"我知道有这个东西，现在不想看"。再自动弹出来
              // 是最招人烦的一类交互（自己做的事被系统反复撤销）。
              const key = keyOf(get())
              if (!drawerAutoOpened.has(key) && !drawerAutoSuppressed.has(key)) {
                drawerAutoOpened.add(key)
                set({ drawerOpen: true, drawerTab: 'trace' })
              }
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
              // 进**队列**而不是覆盖单值：多会话同时跑时，后台那一轮的确认
              // 会被后到的顶掉，而它还在等 —— 结果是那一轮永远醒不过来。
              // 带上来源会话：用户可能在 A 会话看到 B 会话的确认框。
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
              // 技能要问用户（选择 / 敏感输入）。同 `onPermissionRequest`：
              // **进队列**，并带上来源会话，免得用户在 A 会话看到 B 的弹窗。
              const sessionKey = get().runs[runId]?.sessionId ?? ''
              const title = get().sessions.find((item) => item.id === sessionKey)?.title
              pushInteraction(flattenInteraction(data, sessionKey, title))
            },
            // 计划出现 / 状态变化：整份快照直接盖上。
            //
            // `plan` 与 `plan_update` 收的是**同一种形状**，所以合并逻辑只有一份
            // （这也是后端刻意让两个事件同构的原因）。计划阶段发生在正文之前，
            // 但这一轮的助手消息在 `send` 里就已经占好位了（`assistantMessageId`），
            // 所以补丁照样能精确落到它身上。
            onPlan: (plan) => patchInRun(runId, (m) => ({ ...m, plan })),
            onPlanUpdate: (plan) => patchInRun(runId, (m) => ({ ...m, plan })),
            onUsage: (usage: TokenUsage) => patchInRun(runId, (m) => ({ ...m, usage })),
            onTrace: (trace) =>
              set((state) => {
                const run = state.runs[runId]
                if (!run) return { trace }
                const tracesBySession = { ...state.tracesBySession, [run.sessionId]: trace }
                // 只有这一轮就是用户眼前那条时才更新可见的 trace ——
                // 否则抽屉里会显示另一个会话的耗时
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
        // 流被异常掐断（没收到 done / error）时，消息会永远停在「生成中」，
        // 这里兜底收敛一次状态，避免 UI 出现无法结束的转圈。
        // ⚠️ 必须排在下面对 run 的清理**之前**：`patchInRun` 靠 runs 里的
        // 这一轮来定位，run 一删它就找不到目标、补丁会被静默丢掉。
        patchInRun(runId, (m) => (m.status === 'streaming' ? { ...m, status: 'done' } : m))
        const finishedSession = get().runs[runId]?.sessionId ?? runKey
        set((state) => {
          // 只清掉**这一轮**：别的会话还在跑的轮次必须留着 ——
          // 改造前这里无条件把全局 streaming 置 false，等于"后台跑完
          // 就把用户眼前那条刚开跑的任务标记成已结束"。
          const runs = { ...state.runs }
          delete runs[runId]
          return {
            runs,
            streaming: visibleStreaming(keyOf(state), runs),
            ...runningSummary(runs),
          }
        })
        // 这一轮结束后，它还在排队等确认的请求也不会有答复了：
        // 留着它只会让用户点一个"点了没反应"的按钮
        dropPermissionsOf(finishedSession)
        // 这一轮的缓冲与句柄用完就扔，别攒在 Map 里
        runBuffers.delete(runId)
        void get().loadSessions()
        // 刷新搭子列表：一轮对话里 AI 可能改过**自己的昵称/头像**
        // （内置技能 `update_assistant_profile`）。不刷新的话，用户在搜索结果下
        // 那张简介卡上看到的还是旧名字，得重开应用才更新 —— 
        // 报的就是这个"改了没生效"。
        //
        // 放在这里而不是给简介卡单独加逻辑：简介卡读的就是本 store 的当前搭子，
        // 源头刷新一次，所有读它的地方（搭子栏、简介卡、欢迎页头像）一起对齐。
        // `load()` 内部会保留仍然存在的 activeId，所以不会把用户切走。
        void useAssistantStore.getState().load()
        // 刷新用量统计：今日花费/缓存命中率会随每轮对话变化，
        // 不刷新的话设置页里的数字会一直停在打开时的快照上
        void useUsageStore.getState().load()

        // 本轮产生了新产物就自动把抽屉切到产物页。
        // 不这么做的话，用户根本不知道有文件生成——产物是这批功能里最容易被忽略的。
        //
        // ⚠️ 但**只有这一轮就是用户眼前那条**时才自动开抽屉：后台会话跑完
        // 突然弹出一个抽屉，会打断用户正在看的另一条对话（
        // 选的口径是"静默完成，不额外打扰"）。
        const before = get().artifacts.length
        await get().loadArtifacts()
        const stillVisible = keyOf(get()) === finishedSession
        if (stillVisible && get().artifacts.length > before) {
          set({ drawerOpen: true, drawerTab: 'artifacts' })
        }
      }
    },

    stop: async () => {
      const api = useAppStore.getState().api
      // 只停**当前可见会话**的那一轮：后台会话的任务不该被这个按钮连坐
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
          // 中断请求失败不影响前端状态收敛
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
      // 交互请求也要一起收掉：这一轮已经停了，后端 `reject_pending` 会把挂起的
      // 那个交互作废（技能拿到"没答"并降级），前端再留着弹窗只会让人点了没反应。
      dropInteractionsOf(key)
    },

    respondPermission: async (approved) => {
      // 取**队首**（也就是弹窗正在显示的那一条）
      const request = get().permission
      if (!request) return
      dropPermission(request.requestId)
      try {
        const api = useAppStore.getState().api
        await api?.confirm(request.requestId, approved)
      } catch {
        // 超时或已处理，忽略即可
      }
    },

    /**
     * 回传用户对交互弹窗的作答（选择 / 敏感输入）。
     *
     * ⚠️ `answer.names` 里**只有名字，没有值**：敏感内容由弹窗直接写进本地
     * 加密文件（`window.agentBridge.saveSkillSecrets`），**不经过这里**。
     * 这条请求会进服务端日志与审计，带上明文就等于把密钥发到模型厂商那边
     * 的同一份记录里 —— 那正是这套机制要防的事。
     *
     * ⚠️ 先把队首摘掉再发请求：用户点了两次时，第二次会因为队列已空而直接返回，
     * 不会白跑一趟（后端也会用 `ok=false` 兜底，但这里更早拦住）。
     */
    respondInteraction: async (answer) => {
      const request = get().interaction
      if (!request) return
      dropInteraction(request.requestId)
      try {
        const api = useAppStore.getState().api
        const result = await api?.interactionDecision(request.requestId, answer)
        // `ok=false` = 这次交互已经不在等待中了（任务被停止 / 会话被关 /
        // 重复提交）。**要说出来**，否则用户点了「保存并使用」什么都没发生，
        // 只能反复点 —— 那是最让人困惑的一类沉默。
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
      // 计划 id 由**卡片自己**给（就是它渲染的那一版）。
      //
      // 改造前这里是"扫描消息列表找 `state === 'awaiting'` 的那一份"——
      // 消息按会话分桶之后那个扫描会看到**错误的会话**：用户在 A 的卡片上
      // 点「开始执行」，却可能唤醒 B 会话正在等待的那一版计划（两版 id 不同，
      // 后端的 resolve_plan 会找不到 A 的那一份，于是点了没反应）。
      if (!planId) return

      const api = useAppStore.getState().api
      if (!api) return
      try {
        const result = await api.planDecision(planId, approved, feedback)
        if (!result.ok) {
          // **不静默。** 后端说"这份计划已经不在等待中了"时，界面必须说出来 ——
          // 否则用户点了按钮却什么都没发生，只会以为界面坏了。
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

    // 群聊那条链路（常驻 /v1/events）也走这里入队，与单聊共用同一个队列，
    // 于是"弹窗 + 回传"只有一份实现。
    setPermission: (request) => {
      if (!request) {
        // `null` 是历史语义（"清空"）：从队列头摘掉当前那条
        const head = get().permission
        if (head) dropPermission(head.requestId)
        return
      }
      pushPermission(request)
    },

    // ---------------------------------------------------------------- //
    // 右侧抽屉与产物
    // ---------------------------------------------------------------- //
    setDrawerOpen: (open) => {
      // ⚠️ 用户**手动关**抽屉 = 明确表示"这次对话的过程我不想看"。
      // 记下来，本会话不再自动展开（见 `drawerAutoSuppressed` 的说明）。
      // 只在"关"的时候记：手动开说明他愿意看，不该影响后续的自动行为。
      if (!open) drawerAutoSuppressed.add(keyOf(get()))
      set({ drawerOpen: open })
    },
    setDrawerTab: (tab) => set({ drawerTab: tab }),

    loadArtifacts: async () => {
      const api = useAppStore.getState().api
      if (!api) return
      try {
        const payload = await api.getFiles('artifact')
        set({ artifacts: payload.files })
      } catch {
        // 产物列表拉不到不该影响对话本身
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
