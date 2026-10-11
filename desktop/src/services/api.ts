import type { BackendInfo } from '@shared/bridge'

import type {
  AppSettings,
  PersonaFilesPayload,
  PersonaLockRequest,
  PersonaLockResult,
  ArtifactPreview,
  AssistantProfile,
  AssistantsPayload,
  AuditLogEntry,
  AuditStats,
  BackendHealth,
  CalendarTestResult,
  ConfirmMode,
  ConfirmModeState,
  CustomSkillDef,
  FileRecord,
  GroupProfile,
  GroupThread,
  GroupUpdate,
  HistoryMessage,
  ImportOutcome,
  McpImportResult,
  McpPreset,
  McpServerConfig,
  McpServerStatus,
  McpToolInfo,
  ModelHubAction,
  ModelHubStatus,
  ModelVerifyResult,
  ModelsPayload,
  PathsInfo,
  Plan,
  RunRecord,
  SessionContext,
  SessionSummary,
  ScheduledTask,
  ScheduledTaskDraft,
  SkillFileEntry,
  SkillFolderInfo,
  SkillImportOutcome,
  InteractionAnswer,
  InteractionEvent,
  SkillInfo,
  TasksPayload,
  TraceData,
  UsageSummary,
  UsageTotals,
  WorkspaceStats,
} from '@/types'

/**
 * `POST /v1/models/test` 的返回形状。
 *
 * 单独导出而不是内联：设置页要在"测试失败"时自己合成一条同样形状的结果
 * （见 `saveAndTest` 里对 catch 的处理），两边共用同一个类型才不会漂移。
 */
/** 群聊历史里的一条事件（与实时推送的事件同构，可直接重放） */
export interface GroupReplayEvent {
  seq: number
  event: string
  data: Record<string, unknown>
  created_at: string
}

export interface ModelTestOutcome {
  ok: boolean
  latency_ms?: number
  models?: string[]
  warning?: string
  error?: string
}

export class ApiError extends Error {
  constructor(
    public status: number,
    public code: string,
    message: string,
    public detail?: unknown,
  ) {
    super(message)
    this.name = 'ApiError'
  }
}

async function toApiError(response: Response): Promise<ApiError> {
  let code = `http_${response.status}`
  let message = `请求失败（HTTP ${response.status}）`
  let detail: unknown

  try {
    const body = (await response.json()) as Record<string, unknown>
    // 后端统一返回 { code, message, detail }；FastAPI 校验错误则是 { detail: [...] }
    if (typeof body.code === 'string') code = body.code
    if (typeof body.message === 'string') message = body.message
    else if (typeof body.detail === 'string') message = body.detail
    else if (Array.isArray(body.detail)) {
      message = body.detail
        .map((item) => {
          const issue = item as { loc?: unknown[]; msg?: string }
          const field = Array.isArray(issue.loc) ? issue.loc.slice(1).join('.') : ''
          return field ? `${field}: ${issue.msg ?? ''}` : (issue.msg ?? '参数错误')
        })
        .join('；')
    }
    detail = body.detail
  } catch {
    // 响应不是 JSON，保留默认文案
  }
  return new ApiError(response.status, code, message, detail)
}

// --------------------------------------------------------------------------- //
// SSE 事件负载
// --------------------------------------------------------------------------- //
export interface ChatMeta {
  session_id: string
  task_id: string
  trace_id: string
  model_id: string
}

export interface ToolCallEvent {
  id: string
  name: string
  display_name: string
  description: string
  params: Record<string, unknown>
  permission_level: string
  /** 该次调用的开始时刻（epoch 秒）：工具卡片上显示时间用*/
  started_at?: number
}

export interface ToolResultEvent {
  id: string
  name: string
  display_name: string
  status: 'ok' | 'error' | 'denied'
  result: string
  duration_ms: number
}

export interface PermissionEvent {
  request_id: string
  skill_name: string
  display_name: string
  description: string
  permission_level: string
  params: Record<string, unknown>
  prompt: string
}

export interface DoneEvent {
  trace_id: string
  iterations: number
  cancelled?: boolean
  partial?: boolean
  usage: { prompt_tokens: number; completion_tokens: number; total_tokens: number }
}

export interface StreamError {
  code: string
  message: string
}

export interface ReminderRecord {
  id: number
  content: string
  remind_at: number
  remind_at_text: string
  base_at: number
  base_at_text: string
  advance_min: number
  status: string
  fired_at: number | null
}

export interface ExpenseRecord {
  id: number
  amount: number
  category: string
  note: string
  spent_on: string
  created_at: number
}

export interface ExpenseSummary {
  period: string
  category?: string | null
  range: { start: string; end: string } | null
  total: number
  count: number
  average: number
  by_category: Array<{ category: string; total: number; count: number; ratio: number }>
  by_day: Array<{ date: string; total: number }>
}

export interface ReminderEvent {
  id: number
  content: string
  remind_at_text: string
  advance_min: number
  ts: number
}

export interface NoticeEvent {
  level: 'info' | 'success' | 'warning' | 'error'
  title: string
  message: string
  ts: number
}

export interface EventHandlers {
  onReady?: (data: { subscribers: number }) => void
  onReminder?: (data: ReminderEvent) => void
  onNotice?: (data: NoticeEvent) => void
  /**
   * 所有事件的旁路回调。
   *
   * 界面里有些局部状态需要「服务端一变就刷新」（例如 MCP 服务的连接灯），
   * 但它们不值得各开一条长连接，所以统一从这里分发。
   */
  onAny?: (event: string, data: Record<string, any>) => void
}

export interface ChatHandlers {
  onMeta?: (data: ChatMeta) => void
  onMessageStart?: (data: { iteration: number }) => void
  onDelta?: (text: string) => void
  onReasoning?: (text: string) => void
  onMessageEnd?: (data: {
    iteration: number
    content: string
    tool_calls: Array<{ id: string; name: string; arguments: Record<string, unknown> }>
  }) => void
  onToolCall?: (data: ToolCallEvent) => void
  onToolResult?: (data: ToolResultEvent) => void
  onPermissionRequest?: (data: PermissionEvent) => void
  /**
   * 计划生成 / 状态变化（单聊多步任务）。
   *
   * 与 `plan_update` 收的是**同一个形状**（整份计划的最新快照），所以前端
   * 直接整体替换即可 —— 不需要自己去合并增量，也就不会出现"某一步漏更新"。
   */
  onPlan?: (data: Plan) => void
  /** 某一步的进度变化（同样带整份计划快照，前端逐项打勾的依据） */
  onPlanUpdate?: (data: Plan) => void
  onUsage?: (data: {
    prompt_tokens: number
    completion_tokens: number
    total_tokens: number
  }) => void
  onTrace?: (data: TraceData) => void
  onDone?: (data: DoneEvent) => void
  onErrorEvent?: (data: StreamError) => void
  /**
   * 服务端的**非致命提醒**。
   *
   * 和 `onErrorEvent` 的区别是它不影响这一轮继续跑：例如"附带的图片没有发出去，
   * 因为当前模型未开启图片支持"。既不是错误、也不能当成无事发生 ——
   * 静默吞掉的话用户会以为模型看不到图是能力问题。
   */
  onWarning?: (data: { message: string }) => void
  /**
   * 服务端把**早期对话压成了摘要**（上下文快满了）。
   *
   * 为什么必须让用户看到：这件事会让模型"忘掉"更早的细节，而用户的第一反应是
   * "它怎么突然不记得了"。后端已经在发给模型的摘要里写明"更早的完整记录仍在，
   * 需要细节就直接问"，但**人也该知道** —— 否则他只会觉得模型变笨了。
   *
   * 这不是错误：对话能继续跑，内容一条都没删（用户翻历史仍然是完整的）。
   */
  onContextCompressed?: (data: { summary_chars: number }) => void
  /**
   * 某个工具的返回内容里检测到**疑似指令注入**。
   *
   * 这是注入防护的第三层，也是唯一不会失效的一层：边界标记和就地警示都可能被
   * 模型绕过，但"某个工具返回了可疑内容"这件事必须让**人**看到 ——
   * 否则回答看起来一切正常，实际可能是被一段文件内容指挥出来的。
   */
  onInjectionSuspected?: (data: {
    name: string
    display_name?: string
    labels: string[]
  }) => void
  /**
   * 技能要**问用户一个问题**（`ask_choice` / `request_secret`）。
   *
   * 与 `onPermissionRequest` 的区别：那个问"允不允许执行"，答案是布尔；
   * 这个问"你指的是哪个 / 把东西给我"，答案是任意结构，而且**不设超时**。
   * 两者的语义与收尾方式都不同，所以后端也是两套挂起表。
   */
  onInteractionRequest?: (data: InteractionEvent) => void
}

// --------------------------------------------------------------------------- //
// 客户端
// --------------------------------------------------------------------------- //
export class AgentApi {
  constructor(
    private readonly baseUrl: string,
    private readonly token: string,
  ) {}

  static from(info: BackendInfo): AgentApi {
    return new AgentApi(info.baseUrl, info.token)
  }

  private get headers(): Record<string, string> {
    return {
      'X-Local-Token': this.token,
      'Content-Type': 'application/json',
    }
  }

  /**
   * 取文件的原始字节（图片 / SVG 预览用）。
   *
   * 必须先用带鉴权头的 fetch 拿成 Blob，再转成 object URL 交给 `<img>`——
   * `<img src>` 不会带自定义请求头，而后端要求 `X-Local-Token`。
   * 顺带还有个安全好处：浏览器不会执行 `<img>` 加载的 SVG 里的脚本，
   * 直接内联 SVG 文本则等于把上传文件当 HTML 渲染。
   */
  async fetchFileBlob(id: string, kind: 'upload' | 'artifact' = 'artifact'): Promise<Blob> {
    const response = await fetch(
      `${this.baseUrl}/v1/files/${encodeURIComponent(id)}?kind=${kind}`,
      { headers: { 'X-Local-Token': this.token } },
    )
    if (!response.ok) {
      throw new Error(`读取文件失败（HTTP ${response.status}）`)
    }
    return response.blob()
  }

  // 「另存为」**不在这里**：它要弹系统保存对话框并落盘，渲染层做不到
  // （沙箱下没有写盘能力，本项目也不允许渲染层碰本地路径）。
  // 走主进程的 `window.agentBridge.saveArtifactAs`，见 shared/bridge.ts。
  // 原先这里有一个 `downloadFile`（Blob + `<a download>`），只能落到浏览器
  // 默认下载目录、用户无法选位置 —— 已由那条通道取代。

  /**
   * 取**本机图片**的字节（对话里模型写的 `D:\图片\a.png` 这类路径）。
   *
   * ## 为什么要绕核心
   *
   * `D:\图片\a.png` 不是合法 URL（`d:` 会被当成协议名），`file:///D:/...` 在开发态
   * （页面在 http://localhost）拿不到、生产态的 CSP 也不放行 `file:` —— 于是"贴了本地图
   * 却必然破图"。所以由核心读文件回字节，这里取成 Blob 再交给 `<img>`。
   *
   * 与 `fetchFileBlob` 的差别在**错误处理**：这里把后端给的原因原样抛出去。
   * "图片不存在 / 不是支持的格式 / 超出文件访问白名单 / 是网络共享路径"都要显示给用户，
   * 而一句"读取文件失败（HTTP 404）"等于没说。
   */
  async fetchLocalImage(path: string): Promise<Blob> {
    const response = await fetch(
      `${this.baseUrl}/v1/media/local-image?path=${encodeURIComponent(path)}`,
      { headers: { 'X-Local-Token': this.token } },
    )
    if (!response.ok) throw await toApiError(response)
    return response.blob()
  }

  /**
   * 默认请求超时。
   *
   * 原先是**完全没有超时**的。后端一旦卡住（例如某个技能进了死循环、
   * 数据库被外部进程锁住），这个 Promise 就永远不落地，界面上表现为
   * "一直转圈"—— 用户既拿不到结果、也看不到错误，只能强杀应用。
   * 有个上限之后，至少会变成一条可读的错误。
   *
   * 取 60s：比任何正常的设置类接口都宽裕得多，又明显短于
   * "用户开始怀疑程序挂了"的时间。
   */
  private static readonly DEFAULT_TIMEOUT_MS = 60_000

  async request<T>(
    path: string,
    init: RequestInit = {},
    timeoutMs: number = AgentApi.DEFAULT_TIMEOUT_MS,
  ): Promise<T> {
    // 调用方自带 signal 时就尊重它、**不叠加**：两个 AbortController 抢同一个
    // 请求时，谁先 abort 决定最终错误信息，叠加只会让原因变得难以判断
    const controller = init.signal ? null : new AbortController()
    const timer = controller
      ? setTimeout(() => controller.abort(), timeoutMs)
      : null

    try {
      const response = await fetch(`${this.baseUrl}${path}`, {
        ...init,
        signal: init.signal ?? controller!.signal,
        headers: { ...this.headers, ...(init.headers ?? {}) },
      })
      if (!response.ok) throw await toApiError(response)
      if (response.status === 204) return undefined as T
      return (await response.json()) as T
    } catch (error) {
      // fetch 在 abort 时抛的是 DOMException，和网络错误长得一样。
      // 不区分的话用户会看到 "The operation was aborted" 这种无从下手的提示。
      if (controller?.signal.aborted) {
        throw new ApiError(
          408,
          'timeout',
          `请求超时（超过 ${Math.round(timeoutMs / 1000)} 秒），后端可能没有响应。`,
        )
      }
      throw error
    } finally {
      if (timer) clearTimeout(timer)
    }
  }

  private get<T>(path: string) {
    return this.request<T>(path, { method: 'GET' })
  }

  private send<T>(path: string, method: string, body?: unknown) {
    return this.request<T>(path, {
      method,
      body: body === undefined ? undefined : JSON.stringify(body),
    })
  }

  // ---- 系统 ---------------------------------------------------------- //
  health = () => this.get<BackendHealth>('/v1/health')
  getSettings = () => this.get<AppSettings>('/v1/settings')
  /**
   * 提交整份设置。
   *
   * `clearCalendarPassword` 是唯一一个"显式清空"的通道：日历密码在请求体里留空
   * 表示"用户没动它"（保留内存里那份），真要清空必须显式说出来 —— 与模型 Key
   * 的 `removeModelIds` 同一个道理。
   */
  saveSettings = (payload: AppSettings, options?: { clearCalendarPassword?: boolean }) =>
    this.send<AppSettings>(
      `/v1/settings${options?.clearCalendarPassword ? '?clear_calendar_password=true' : ''}`,
      'PUT',
      payload,
    )
  /** 试一次 CalDAV 只读请求（可以先用界面上的值试，不必先保存） */
  testCalendar = (payload: {
    caldav_url?: string
    caldav_username?: string
    caldav_password?: string
  }) => this.send<CalendarTestResult>('/v1/calendar/test', 'POST', payload)
  getPaths = () => this.get<PathsInfo>('/v1/paths')

  // ---- 语音 ---------------------------------------------------------- //
  /**
   * 语音请求单独走一条带超时的通道，不复用 `send`。
   *
   * 识别是**本地 CPU 推理**（实测 8 秒音频约 300ms），但它和别的事共用核心进程：
   * 核心正在加载嵌入模型或解析大文件时会被占住。这时如实报"超时、请重试"
   * 远好过看着转圈等下去 —— 语音场景下用户就站在那儿等着说话。
   */
  private async voicePost<T>(path: string, payload: unknown, timeoutMs: number): Promise<T> {
    const response = await fetch(`${this.baseUrl}${path}`, {
      method: 'POST',
      headers: this.headers,
      body: JSON.stringify(payload),
      signal: AbortSignal.timeout(timeoutMs),
    }).catch((error: unknown) => {
      if (error instanceof DOMException && error.name === 'TimeoutError') {
        throw new ApiError(408, 'timeout', '语音请求超时：核心可能正忙于其他任务，请再说一次。')
      }
      throw error
    })
    if (!response.ok) throw await toApiError(response)
    return (await response.json()) as T
  }

  /**
   * 语音能力就位情况。
   *
   * 分成 `available`（模型在不在）与 `loaded`（是否已载入内存）：设置页据此
   * 告诉用户"能用 / 正在加载 / 缺文件"，而不是等他按下麦克风才失败。
   */
  voiceStatus = () =>
    this.get<{
      asr: { available: boolean; loaded: boolean }
      wake: { available: boolean; loaded: boolean }
      tts: { available: boolean; loaded: boolean; speakers: number }
    }>('/v1/voice/status')

  /**
   * 识别文本 → 命中的**命令 id**（核心按拼音判，且要求整句相等）。
   *
   * 前端会先做一次字面比较，不中才来这里 —— 所以这条请求只在"识别写了同音字"
   * 时才发生，日常路径没有额外往返。整句相等是刻意的：命令词很短，
   * 用"包含"会让「帮我确认一下这个文件」变成批准一个高危操作。
   */
  matchVoiceCommand = (text: string, candidates: Array<{ id: string; word: string }>) =>
    this.voicePost<{ id: string | null }>('/v1/voice/match', { text, candidates }, 10_000)

  /** 整段音频 → 文本（含情感与事件标签）。 */
  voiceAsr = (pcmBase64: string, sampleRate: number) =>
    this.voicePost<{
      text: string
      emotion: string
      event: string
      language: string
      duration_ms: number
      took_ms: number
    }>('/v1/voice/asr', { pcm: pcmBase64, sample_rate: sampleRate }, 30_000)

  /**
   * 一小段音频 → 有没有说出唤醒词；命中返回**用户填的那个词**。
   *
   * 判定完全由识别模型完成（专门的 KWS 小模型已弃用），后端**按拼音**匹配 ——
   * 所以「你好搭子」被听成「你好，大子」也能唤醒。
   *
   * `text` 是这一段**实际被听成的话** —— 喊不醒时，用户靠它就能分辨
   * "它没听懂我说的"还是"听懂了但词不对"，否则只能一遍遍重复喊。
   *
   * 传进来的音频通常是前端窗口累积的**最近几秒**（不是被 VAD 断出的单段），
   * 所以这里一次要识别约 3 秒音频，超时给 15 秒留够余量。
   */
  voiceWake = (pcmBase64: string, sampleRate: number, words: string[]) =>
    this.voicePost<{ hit: string | null; source: 'asr'; text: string }>(
      '/v1/voice/wake',
      { pcm: pcmBase64, sample_rate: sampleRate, words },
      15_000,
    )



  // ---- 定时任务 -------------------------------------------------------- //
  /**
   * 定时任务为什么不复用 `saveSettings`。
   *
   * 任务确实是配置（也在 settings.json 里），但整份提交 settings 会顺手覆盖
   * **别的**字段 —— 用户正在设置页编辑的、还没点保存的改动会一起被写掉。
   * 所以增删改各有接口，每次只动一个任务。
   */
  getTasks = () => this.get<TasksPayload>('/v1/tasks')
  createTask = (payload: ScheduledTaskDraft) =>
    this.send<{ ok: boolean; task: ScheduledTask }>('/v1/tasks', 'POST', payload)
  updateTask = (id: string, payload: ScheduledTaskDraft) =>
    this.send<{ ok: boolean; task: ScheduledTask }>(
      `/v1/tasks/${encodeURIComponent(id)}`,
      'PUT',
      payload,
    )
  deleteTask = (id: string) =>
    this.send<{ ok: boolean; deleted: string }>(`/v1/tasks/${encodeURIComponent(id)}`, 'DELETE')
  /**
   * 立刻执行一次。
   *
   * 正在执行中时后端返回 409 —— 这是刻意的：排队成"跑完再来一遍"不是用户
   * 点这个按钮的意思，而且定时任务会真的花钱。
   */
  runTask = (id: string) =>
    this.send<{ ok: boolean; task_id: string }>(
      `/v1/tasks/${encodeURIComponent(id)}/run`,
      'POST',
    )

  // ---- 模型 ---------------------------------------------------------- //
  getModels = () => this.get<ModelsPayload>('/v1/models')
  saveModels = (payload: { default_model: string; models: unknown[] }) =>
    this.send<ModelsPayload>('/v1/models', 'PUT', payload)
  compressSession = (sessionId: string) =>
    this.send<{
      ok: boolean
      compressed: boolean
      summary_chars?: number
      message: string
    }>(`/v1/sessions/${encodeURIComponent(sessionId)}/compress`, 'POST', {})
  testModel = (payload: { model_id?: string; spec?: unknown }) =>
    this.send<ModelTestOutcome>('/v1/models/test', 'POST', payload)
  discoverModels = (payload: { base_url: string; api_key: string }) =>
    this.send<{ models: string[]; latency_ms?: number }>('/v1/models/discover', 'POST', payload)
  syncModels = (payload: { model_id: string }) =>
    this.send<{ models: string[]; backend?: string }>('/v1/models/sync', 'POST', payload)

  // ---- 本地模型下载（语音 / 嵌入，起改为按需下载） ---------- //
  /**
   * 两个本地模型的当前状态。
   *
   * 线路**不由前端指定**：主进程已经通过 `PUT /v1/client/line` 把线路同步给了核心，
   * 下载端点自己按它选国内 / 国外源（所以这里连 `line` 参数都不用传）。
   */
  modelStatus = () => this.get<ModelHubStatus>('/v1/models/status')
  /** 开始下载（已在跑就原样返回，不会重起任务） */
  downloadModel = (key: string) =>
    this.send<ModelHubAction>('/v1/models/download', 'POST', { key })
  /** 取消下载（幂等：没在跑返回 not-running，不算错误） */
  cancelModelDownload = (key: string) =>
    this.send<ModelHubAction>('/v1/models/cancel', 'POST', { key })
  /** 真加载一次模型做自检（下载完的"自动检测"与设置页的「验证一下」共用） */
  verifyModel = (key: string) =>
    this.send<ModelVerifyResult>('/v1/models/verify', 'POST', { key })

  /**
   * 上传技能包并导入。
   *
   * 支持 `.zip` / `.tar.gz` / 单个技能文件（`.md` / `.json` / `.yaml` / `.mdc`）——
   * **容器类型由后端按内容识别**，前端只负责把文件原样传过去：用户常把包改名，
   * 或者从浏览器拖来一个没有后缀的文件，只按后缀判断会白白拒收。
   *
   * 与 uploadFile 同理：**必须让浏览器自己生成 multipart 头**，
   * 手动设 Content-Type 会缺 boundary，服务端解析不出表单。
   */
  async uploadSkillPackage(file: File): Promise<SkillImportOutcome> {
    const form = new FormData()
    form.append('package', file)
    // **必须有超时**：裸 fetch 会无限挂起（"导入中"永远转圈的那种体验）。
    // 核心偶尔会被重活（嵌入模型加载、大文件解析）短暂占住，60s 后如实报错，
    // 让用户重试，而不是看着他猜。
    const response = await fetch(`${this.baseUrl}/v1/skills/custom/import`, {
      method: 'POST',
      headers: { 'X-Local-Token': this.token },
      body: form,
      signal: AbortSignal.timeout(60_000),
    }).catch((error: unknown) => {
      if (error instanceof DOMException && error.name === 'TimeoutError') {
        throw new ApiError(
          408,
          'timeout',
          '导入超时（60 秒）：核心可能正忙于其他任务，请稍候重试。',
        )
      }
      throw error
    })
    if (!response.ok) throw await toApiError(response)
    return (await response.json()) as SkillImportOutcome
  }

  /**
   * 导入一个搭子包（zip：搭子 json + 该搭子的技能包），也接受单独的 .json。
   *
   * 上传形态与 `uploadSkillPackage` 完全一致（**必须让浏览器自己生成
   * multipart 头**，手动设 Content-Type 会缺 boundary）。超时给到 180 秒：
   * 一个包里可能有好几个技能包要解析、校验、落盘，60 秒不够稳。
   */
  importBuddyPackage = (file: File) => this.postPackage<ImportOutcome>('/v1/assistants/import', file)

  /** 导入一个搭子群包（zip：group.json + 多个搭子包）。 */
  importBuddyGroup = (file: File) =>
    this.postPackage<ImportOutcome>('/v1/assistants/import-group', file)

  private async postPackage<T>(path: string, file: File): Promise<T> {
    const form = new FormData()
    form.append('package', file)
    const response = await fetch(`${this.baseUrl}${path}`, {
      method: 'POST',
      headers: { 'X-Local-Token': this.token },
      body: form,
      signal: AbortSignal.timeout(180_000),
    }).catch((error: unknown) => {
      if (error instanceof DOMException && error.name === 'TimeoutError') {
        throw new ApiError(408, 'timeout', '导入超时（180 秒）：核心可能正忙于其他任务，请稍候重试。')
      }
      throw error
    })
    if (!response.ok) throw await toApiError(response)
    return (await response.json()) as T
  }

  /**
   * 把**当前线路**告诉核心（大陆 / 首尔）。
   *
   * 核心自己算不出线路，而"官网搭子库地址"与"兑换码接口域名"都跟着线路走
   * （见 core 的 `config/lines.py`）。调用点只有一个：`App.tsx` 里那个
   * 盯 `snapshot.line.preferred` 的 effect。
   */
  setLine = (line: string) =>
    this.send<{ ok: boolean; line: string }>('/v1/client/line', 'PUT', { line })

  // ---- 技能 ---------------------------------------------------------- //
  getSkills = (enabledOnly = false) =>
    this.get<{ total: number; enabled: number; skills: SkillInfo[]; categories: string[] }>(
      `/v1/skills${enabledOnly ? '?enabled_only=true' : ''}`,
    )
  patchSkill = (name: string, payload: { enabled?: boolean; permission_level?: string }) =>
    this.send<SkillInfo>(`/v1/skills/${encodeURIComponent(name)}`, 'PATCH', payload)

  // ---- 会话 ---------------------------------------------------------- //
  getSessions = () =>
    this.get<{ sessions: SessionSummary[]; persistent: boolean }>('/v1/sessions')
  createSession = (payload: { title?: string; model_id?: string } = {}) =>
    this.send<SessionSummary>('/v1/sessions', 'POST', payload)
  updateSession = (
    id: string,
    payload: {
      title?: string
      model_id?: string
      system_prompt?: string
      enabled_skills?: string[]
    },
  ) => this.send<SessionSummary>(`/v1/sessions/${id}`, 'PATCH', payload)
  deleteSession = (id: string) => this.send<{ ok: boolean }>(`/v1/sessions/${id}`, 'DELETE')
  /** 会话当前的上下文占用（已用 / 上限 / 何时会自动压缩），见后端同名接口 */
  getSessionContext = (id: string) =>
    this.get<SessionContext>(`/v1/sessions/${encodeURIComponent(id)}/context`)
  getMessages = (id: string) =>
    this.get<{ session_id: string; messages: HistoryMessage[] }>(`/v1/sessions/${id}/messages`)
  clearMessages = (id: string) =>
    this.send<{ ok: boolean }>(`/v1/sessions/${id}/messages`, 'DELETE')

  // ---- 工作区文件 ---------------------------------------------------- //
  getFiles = (kind?: 'upload' | 'artifact') =>
    this.get<{ files: FileRecord[]; stats: WorkspaceStats }>(
      `/v1/files${kind ? `?kind=${kind}` : ''}`,
    )

  getFileStats = () => this.get<WorkspaceStats>('/v1/files/stats')

  /** 产物预览：后端把各种格式归一化成前端可直接渲染的结构 */
  previewFile = (id: string, kind: 'upload' | 'artifact' = 'artifact') =>
    this.get<ArtifactPreview>(
      `/v1/files/${encodeURIComponent(id)}/preview?kind=${kind}`,
    )

  deleteFile = (id: string, kind: 'upload' | 'artifact' = 'upload') =>
    this.send<{ ok: boolean }>(`/v1/files/${encodeURIComponent(id)}?kind=${kind}`, 'DELETE')

  clearFiles = (kind?: 'upload' | 'artifact') =>
    this.send<{ ok: boolean; removed: number }>('/v1/files/clear', 'POST', { kind })

  /**
   * 上传附件。
   *
   * 这里**不能**带 `Content-Type: application/json`——必须让浏览器
   * 自己生成带 boundary 的 multipart 头，否则服务端解析不出表单。
   */
  async uploadFile(file: File, sessionId?: string): Promise<FileRecord> {
    const form = new FormData()
    form.append('file', file)
    const query = sessionId ? `?session_id=${encodeURIComponent(sessionId)}` : ''
    const response = await fetch(`${this.baseUrl}/v1/files/upload${query}`, {
      method: 'POST',
      headers: { 'X-Local-Token': this.token },
      body: form,
    })
    if (!response.ok) throw await toApiError(response)
    return (await response.json()) as FileRecord
  }

  // ---- 审计 ---------------------------------------------------------- //
  /**
   * 查留痕。
   *
   * 支持按**类型 / 搭子 / 日期范围**筛：用户问的是"九点半那会儿出了什么事"，
   * 只能从头翻列表的话，一次失败就得翻到尾。
   * 日期用 `YYYY-MM-DD`（后端负责把结束日算到当天最后一刻 —— 那种"少一天"的错
   * 交给人手算最容易犯）。
   */
  getAudit = (
    params: {
      limit?: number
      session_id?: string
      status?: string
      /** skill / assistant / group / session / task / permission */
      kind?: string
      /** 按搭子筛：它做过什么 */
      actor_id?: string
      date_from?: string
      date_to?: string
    } = {},
  ) => {
    const query = new URLSearchParams()
    if (params.limit) query.set('limit', String(params.limit))
    if (params.session_id) query.set('session_id', params.session_id)
    if (params.status) query.set('status', params.status)
    if (params.kind) query.set('kind', params.kind)
    if (params.actor_id) query.set('actor_id', params.actor_id)
    if (params.date_from) query.set('date_from', params.date_from)
    if (params.date_to) query.set('date_to', params.date_to)
    const suffix = query.toString()
    return this.get<{ entries: AuditLogEntry[]; available: boolean; reason?: string }>(
      `/v1/audit${suffix ? `?${suffix}` : ''}`,
    )
  }

  // ---- 断点续跑（未完成的运行） --------------------------------------- //
  /** 列出**没跑完**的运行（失败/被叫停的）；跑完的不会在这里。 */
  getRuns = () => this.get<{ total: number; runs: RunRecord[] }>('/v1/runs')

  /**
   * 接着上次中断的地方继续。
   *
   * 群讨论是**流式**的：后端只回"接着讨论要用的话题与群 id"，由界面去调既有的
   * 讨论接口重新订阅那条流 —— 复用同一条渲染路径，不另造一套"从断点恢复"的流。
   */
  resumeRun = (id: string) =>
    this.send<{
      ok: boolean
      kind: string
      session_id?: string
      group_id?: string
      topic?: string
      message?: string
    }>(`/v1/runs/${encodeURIComponent(id)}/resume`, 'POST')

  /** 不再续跑这条（用户自己放弃）。 */
  dismissRun = (id: string) =>
    this.send<{ ok: boolean }>(`/v1/runs/${encodeURIComponent(id)}`, 'DELETE')

  getAuditStats = () => this.get<AuditStats>('/v1/audit/stats')

  clearAudit = () => this.send<{ ok: boolean; removed: number }>('/v1/audit', 'DELETE')

  // ---- 任务控制 ------------------------------------------------------ //
  stop = (payload: { task_id?: string; session_id?: string }) =>
    this.send<{ ok: boolean; cancelled: number }>('/v1/stop', 'POST', payload)
  confirm = (requestId: string, approved: boolean) =>
    this.send<{ ok: boolean }>('/v1/confirm', 'POST', {
      request_id: requestId,
      approved,
    })

  /**
   * 回传用户对执行计划的决定（单聊计划模式）。
   *
   * 三种决定共用一个接口，靠 `approved` 与 `feedback` 的组合区分（见后端
   * `/v1/plan/decision`）：`approved=true` 是「开始执行」；`approved=false`
   * 且 `feedback` 非空是「改一下」（带上用户的意见重拟）；两者都不满足是
   * 「不用了」。后端用 `ok=false` 表示这份计划已经不在等待中了（例如重复点击）。
   */
  planDecision = (planId: string, approved: boolean, feedback = '') =>
    this.send<{ ok: boolean; action?: 'approved' | 'revise' | 'aborted'; message?: string }>(
      '/v1/plan/decision',
      'POST',
      { plan_id: planId, approved, feedback },
    )

  /**
   * 回传用户对交互弹窗的作答（选择 / 敏感输入）。
   *
   * ⚠️ `answer.names` 里**只有引用名，没有值** —— 敏感内容由弹窗直接写进本地
   * 加密文件（`window.agentBridge.saveSkillSecrets`），根本不经过这条请求。
   * 这条接口会被写进服务端日志与审计，所以**绝不能**让它带上明文。
   *
   * `ok=false` 表示这次交互已经不在等待中了（重复点击、或任务已被停止），
   * 调用方应据此提示用户，而不是静默吞掉。
   */
  interactionDecision = (requestId: string, answer: InteractionAnswer) =>
    this.send<{ ok: boolean; message?: string }>('/v1/interaction/decision', 'POST', {
      request_id: requestId,
      answer,
    })

  // ---- 全局事件流（SSE） --------------------------------------------- //
  /**
   * 订阅服务端主动推送（提醒到点等）。
   *
   * 这是一条**长连接**：正常情况下会一直挂着直到主动 abort 或服务端关闭。
   * 调用方负责断线重连。
   */
  async streamEvents(
    handlers: EventHandlers,
    signal?: AbortSignal,
  ): Promise<void> {
    const response = await fetch(`${this.baseUrl}/v1/events`, {
      method: 'GET',
      headers: { 'X-Local-Token': this.token, Accept: 'text/event-stream' },
      signal,
    })
    if (!response.ok) throw await toApiError(response)
    if (!response.body) throw new ApiError(500, 'no_body', '服务端未返回事件流')

    await consumeSSE(response, (event, data) => {
      handlers.onAny?.(event, data)
      switch (event) {
        case 'ready':
          handlers.onReady?.(data as { subscribers: number })
          break
        case 'reminder':
          handlers.onReminder?.(data as ReminderEvent)
          break
        case 'notice':
          handlers.onNotice?.(data as NoticeEvent)
          break
        default:
          break
      }
    })
  }

  // ---- 生活数据 ------------------------------------------------------ //
  getReminders = (status?: string) =>
    this.get<{ reminders: ReminderRecord[]; pending: number }>(
      `/v1/reminders${status ? `?status=${status}` : ''}`,
    )
  deleteReminder = (id: number) =>
    this.send<{ ok: boolean }>(`/v1/reminders/${id}`, 'DELETE')

  getExpenses = (period = 'month', limit = 50) =>
    this.get<{ summary: ExpenseSummary; expenses: ExpenseRecord[]; categories: string[] }>(
      `/v1/expenses?period=${encodeURIComponent(period)}&limit=${limit}`,
    )
  deleteExpense = (id: number) => this.send<{ ok: boolean }>(`/v1/expenses/${id}`, 'DELETE')

  // ---- 用量与费用 ----------------------------------------------------- //
  getUsageSummary = (days = 30) => this.get<UsageSummary>(`/v1/usage/summary?days=${days}`)

  getSessionUsage = (sessionId: string) =>
    this.get<UsageTotals & { available: boolean }>(
      `/v1/usage/session/${encodeURIComponent(sessionId)}`,
    )

  /** 清空用量流水。只删统计，不动会话与消息。 */
  clearUsage = () => this.send<{ ok: boolean; removed: number }>('/v1/usage', 'DELETE')

  // ---- 权限确认模式 --------------------------------------------------- //
  getConfirmMode = (assistantId?: string | null) =>
    this.get<ConfirmModeState>(
      `/v1/security/confirm-mode${
        assistantId ? `?assistant_id=${encodeURIComponent(assistantId)}` : ''
      }`,
    )

  /**
   * 只改确认模式这一个字段。
   *
   * 刻意不复用 saveSettings：那个接口要求提交**整个** AppSettings，
   * 而输入栏旁边的快捷开关只改一个字段，全量提交会把用户正在设置页里
   * 编辑、还没保存的其他改动一起覆盖掉。
   */
  setConfirmMode = (mode: ConfirmMode) =>
    this.send<{ mode: ConfirmMode }>('/v1/security/confirm-mode', 'PUT', { mode })

  // ---- MCP ----------------------------------------------------------- //
  getMcpServers = () =>
    this.get<{
      servers: McpServerStatus[]
      sdk_available: boolean
      tool_total: number
      presets: McpPreset[]
    }>('/v1/mcp/servers')

  createMcpServer = (config: McpServerConfig) =>
    this.send<McpServerStatus>('/v1/mcp/servers', 'POST', config)

  updateMcpServer = (name: string, config: McpServerConfig) =>
    this.send<McpServerStatus>(
      `/v1/mcp/servers/${encodeURIComponent(name)}`,
      'PUT',
      config,
    )

  deleteMcpServer = (name: string) =>
    this.send<{ ok: boolean }>(`/v1/mcp/servers/${encodeURIComponent(name)}`, 'DELETE')

  restartMcpServer = (name: string) =>
    this.send<McpServerStatus>(
      `/v1/mcp/servers/${encodeURIComponent(name)}/restart`,
      'POST',
    )

  stopMcpServer = (name: string) =>
    this.send<McpServerStatus>(`/v1/mcp/servers/${encodeURIComponent(name)}/stop`, 'POST')

  getMcpTools = (name: string) =>
    this.get<{ name: string; state: string; message: string; tools: McpToolInfo[] }>(
      `/v1/mcp/servers/${encodeURIComponent(name)}/tools`,
    )

  /**
   * 批量导入：直接粘贴一段 MCP 配置 JSON。
   *
   * 逐条处理、逐条报错 —— 一条不合法不该让整批失败。
   */
  importMcpJson = (payload: string, overwrite = false) =>
    this.send<McpImportResult>('/v1/mcp/import-json', 'POST', { payload, overwrite })

  // ---- 用户自定义技能 ------------------------------------------------- //
  getCustomSkills = () => this.get<{ skills: CustomSkillDef[] }>('/v1/skills/custom')

  /** 新建或更新。后端会立即重新注册，无需重启 */
  saveCustomSkill = (skill: CustomSkillDef) =>
    this.send<{ ok: boolean; skill: CustomSkillDef; total: number }>('/v1/skills/custom', 'POST', {
      skill,
    })

  deleteCustomSkill = (id: string) =>
    this.send<{ ok: boolean; total: number }>(`/v1/skills/custom/${encodeURIComponent(id)}`, 'DELETE')

  /**
   * 导入本机文件夹（多层嵌套原样导入，不用先压缩）。
   *
   * 路径来自主进程的目录选择框（`window.agentBridge.pickDirectory()`）。
   * **遍历在核心侧做**：没有 50MB 与浏览器文件数限制，多层嵌套也完整保留。
   */
  importSkillFolder = (path: string, name = '') =>
    this.send<SkillImportOutcome>('/v1/skills/custom/import-path', 'POST', { path, name })

  /** 技能文件夹（投放区）的位置 —— 界面显示路径并用资源管理器打开它。 */
  getSkillFolder = () => this.get<SkillFolderInfo>('/v1/skills/custom/folder')

  /** 重新扫描技能文件夹并接入（幂等；顺带把包里的 MCP 配置接进来）。 */
  scanSkillFolder = (only = '') =>
    this.send<SkillImportOutcome>('/v1/skills/custom/scan', 'POST', { only })

  /** 某个技能包落盘后的文件清单（详情弹窗的"包内文件"）。 */
  getSkillFiles = (skillId: string) =>
    this.get<{ skill_id: string; dir: string; files: SkillFileEntry[] }>(
      `/v1/skills/custom/${encodeURIComponent(skillId)}/files`,
    )

  /** 覆盖单个工具的权限；传空字符串表示恢复自动推断。 */
  setMcpToolPermission = (name: string, tool: string, level: string) =>
    this.send<{ ok: boolean; overrides: Record<string, string> }>(
      `/v1/mcp/servers/${encodeURIComponent(name)}/permission`,
      'PATCH',
      { tool, permission_level: level },
    )

  // ---- 助手（Agent 预设） -------------------------------------------- //
  getAssistants = () => this.get<AssistantsPayload>('/v1/assistants')

  createAssistant = (profile: AssistantProfile) =>
    this.send<AssistantProfile>('/v1/assistants', 'POST', profile)

  updateAssistant = (id: string, profile: AssistantProfile) =>
    this.send<AssistantProfile>(`/v1/assistants/${encodeURIComponent(id)}`, 'PUT', profile)

  deleteAssistant = (id: string) =>
    this.send<{ ok: boolean }>(`/v1/assistants/${encodeURIComponent(id)}`, 'DELETE')

  // ---- AI 群 ---------------------------------------------------------- //
  getGroups = () => this.get<{ groups: GroupProfile[] }>('/v1/groups')

  createGroup = (payload: {
    name: string
    member_assistant_ids: string[]
    /** 发言顺序（用户可设置）；留空用成员原顺序 */
    speaking_order?: string[]
    /**
     * 群头像（data URL，用户自己上传的）。
     *
     * 留空是**推荐**路径：后端不认识群头像库（那 24 张随包图在前端），所以
     * 留空时由前端按"优先不与现有群重复"的规则补一张 —— 与 AI 建群同一条规则。
     */
    avatar?: string
  }) => this.send<GroupProfile>('/v1/groups', 'POST', payload)

  deleteGroup = (id: string) =>
    this.send<{ ok: boolean }>(`/v1/groups/${encodeURIComponent(id)}`, 'DELETE')

  /**
   * 局部更新群设置（思考强度 / 权限策略 / 名字 / 发言顺序）。
   *
   * 只为传进来的字段生效 —— 界面上一处改思考强度、一处改权限策略时，
   * 提交全量配置会把对方的改动顺手覆盖掉。
   * 把某个字段传成空串表示**清回"跟随成员各自的设置"**。
   */
  updateGroup = (id: string, payload: GroupUpdate) =>
    this.send<GroupProfile>(`/v1/groups/${encodeURIComponent(id)}`, 'PATCH', payload)

  groupChat = (id: string, message: string) =>
    this.send<{
      replies: Array<{ assistant_id: string; name: string; content: string; error?: string }>
    }>(`/v1/groups/${encodeURIComponent(id)}/chat`, 'POST', { message })

  // ---- 群「对话」：一个群可以有多条----------------- //
  /**
   * 列出某个群的对话，最近有动静的排前面。
   *
   * 后端在**一条都没有时也会建一条**再返回，所以这里的列表不会为空 ——
   * 界面不需要处理"群里一条对话都没有"这个空态（那看起来像功能坏了）。
   */
  getGroupThreads = (id: string) =>
    this.get<{ threads: GroupThread[]; persistent: boolean }>(
      `/v1/groups/${encodeURIComponent(id)}/threads`,
    )

  /** 新建一条空对话（输入栏左下角「开启新对话」按钮） */
  createGroupThread = (id: string, title = '') =>
    this.send<GroupThread>(`/v1/groups/${encodeURIComponent(id)}/threads`, 'POST', { title })

  renameGroupThread = (id: string, threadId: string, title: string) =>
    this.send<GroupThread>(
      `/v1/groups/${encodeURIComponent(id)}/threads/${encodeURIComponent(threadId)}`,
      'PATCH',
      { title },
    )

  /** 删一条对话（连带它的事件）。群本身与其它对话不受影响。 */
  deleteGroupThread = (id: string, threadId: string) =>
    this.send<{ ok: boolean }>(
      `/v1/groups/${encodeURIComponent(id)}/threads/${encodeURIComponent(threadId)}`,
      'DELETE',
    )

  /**
   * 取某条对话的讨论记录。
   *
   * 返回的是**事件流**（与 `discussGroup` 推的是同一套事件），恢复时重放即可 ——
   * 不需要为"读历史"再写一套渲染逻辑。
   *
   * `threadId` 留空表示"最近有动静的那条"；返回值里带回**实际用的** id
   * （`thread_id`），界面据此知道自己读的是哪条，不必猜。
   */
  getGroupMessages = (id: string, threadId = '') =>
    this.get<{ events: GroupReplayEvent[]; persistent: boolean; thread_id: string }>(
      `/v1/groups/${encodeURIComponent(id)}/messages${threadId ? `?thread_id=${encodeURIComponent(threadId)}` : ''}`,
    )

  /** 清空**某条对话**的记录（保留群、成员与其它对话） */
  clearGroupMessages = (id: string, threadId = '') =>
    this.send<{ ok: boolean; removed: number; thread_id: string }>(
      `/v1/groups/${encodeURIComponent(id)}/messages${threadId ? `?thread_id=${encodeURIComponent(threadId)}` : ''}`,
      'DELETE',
    )

  /** 停止某个群正在跑的后台讨论（观察窗「暂停任务」按钮） */
  stopGroupDiscussion = (id: string) =>
    this.send<{ group_id: string; stopped: boolean }>(
      `/v1/groups/${encodeURIComponent(id)}/stop`,
      'POST',
    )

  /**
   * AI 群自主讨论（SSE 流式）。事件：topic / speaker / delta / message /
   * vote_request / vote / vote_result / summary / done。
   *
   * 逐条回调，界面据此"说完一句就出现一句"。传 signal 可随时叫停。
   *
   * `attachments` / `images` 与单聊同一套语义（见后端 `GroupDiscussRequest`）：
   * 附件只把文件信息写进讨论上下文，图片才把本体发给每个成员。
   */
  async discussGroup(
    groupId: string,
    payload: { topic: string; attachments?: string[]; images?: string[]; threadId?: string },
    onEvent: (event: string, data: Record<string, unknown>) => void,
    signal?: AbortSignal,
  ): Promise<void> {
    const response = await fetch(
      `${this.baseUrl}/v1/groups/${encodeURIComponent(groupId)}/discuss`,
      {
        method: 'POST',
        headers: { ...this.headers, Accept: 'text/event-stream' },
        body: JSON.stringify({
          topic: payload.topic,
          attachments: payload.attachments ?? [],
          images: payload.images ?? [],
          // 话题抛给哪条对话。留空时后端会兜底到"最近一条"，所以老路径也不会坏。
          thread_id: payload.threadId ?? '',
        }),
        signal,
      },
    )
    if (!response.ok) throw await toApiError(response)
    if (!response.body) throw new ApiError(500, 'no_body', '服务端未返回响应流')
    await consumeSSE(response, onEvent)
  }

  // ---- 助手：人格与记忆文件（SOUL.md / MEMORY.md）---------------------- //
  getPersonaFiles = (id: string) =>
    this.get<PersonaFilesPayload>(`/v1/assistants/${encodeURIComponent(id)}/persona-files`)

  writePersonaFile = (id: string, name: string, content: string) =>
    this.send<PersonaFilesPayload>(
      `/v1/assistants/${encodeURIComponent(id)}/persona-files/${encodeURIComponent(name)}`,
      'PUT',
      { content },
    )

  /**
   * 人格锁：设置 / 校验 / 清除。
   *
   * 校验**必须**走服务端 —— 服务端不会把哈希下发给界面，界面也不可能自己比对。
   */
  personaLock = (id: string, payload: PersonaLockRequest) =>
    this.send<PersonaLockResult>(
      `/v1/assistants/${encodeURIComponent(id)}/persona-lock`,
      'POST',
      payload,
    )

  // 这里曾有 exportAssistants / importAssistants / getAssistantMarket /
  // installFromMarket / setAssistantMarketSource 五个方法，对应"导出搭子、
  // 从文件导入、搭子集市、从集市安装、保存集市地址"。产品要求把这四项功能整体
  // 剔除，前端入口与后端路由都已连根删除。

  // ---- 对话（SSE） --------------------------------------------------- //
  async streamChat(
    payload: {
      message: string
      session_id?: string
      model_id?: string
      assistant_id?: string
      attachments?: string[]
      /** 作为图片附到本轮消息的工作区文件 id（需要模型支持图片输入） */
      images?: string[]
      /**
       * 思考强度：`low` / `medium` / `high`；`null` 表示**不发送这个参数**。
       *
       * 每轮都会带上它，后端据此更新会话记录（`null` 就是"关掉"）。
       */
      reasoning_effort?: string | null
    },
    handlers: ChatHandlers,
    signal?: AbortSignal,
  ): Promise<void> {
    const response = await fetch(`${this.baseUrl}/v1/chat`, {
      method: 'POST',
      headers: { ...this.headers, Accept: 'text/event-stream' },
      body: JSON.stringify(payload),
      signal,
    })

    if (!response.ok) throw await toApiError(response)
    if (!response.body) throw new ApiError(500, 'no_body', '服务端未返回响应流')

    await consumeSSE(response, (event, data) => handleChatEvent(event, data, handlers))
  }
}

/** 逐块解析 SSE 响应体，把 ``(event, data)`` 交给回调。 */
async function consumeSSE(
  response: Response,
  // 同 handleChatEvent 的理由：网络负载无法编译期校验，用 any 让各分支自行收窄
  onEvent: (event: string, data: Record<string, any>) => void,
): Promise<void> {
  const reader = response.body!.getReader()
  const decoder = new TextDecoder('utf-8')
  let buffer = ''

  try {
    for (;;) {
      const { done, value } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true })

      let boundary = buffer.indexOf('\n\n')
      while (boundary >= 0) {
        const block = buffer.slice(0, boundary)
        buffer = buffer.slice(boundary + 2)
        const parsed = parseBlock(block)
        if (parsed) onEvent(parsed.event, parsed.data)
        boundary = buffer.indexOf('\n\n')
      }
    }
    if (buffer.trim()) {
      const parsed = parseBlock(buffer)
      if (parsed) onEvent(parsed.event, parsed.data)
    }
  } finally {
    // 主动取消时释放底层连接，避免连接池泄漏
    void reader.cancel().catch(() => undefined)
  }
}

function parseBlock(block: string): { event: string; data: Record<string, any> } | null {
  let event = 'message'
  const dataLines: string[] = []

  for (const rawLine of block.split('\n')) {
    const line = rawLine.trimEnd()
    if (!line || line.startsWith(':')) continue // 心跳注释帧
    if (line.startsWith('event:')) event = line.slice(6).trim()
    else if (line.startsWith('data:')) dataLines.push(line.slice(5).trim())
  }
  if (dataLines.length === 0) return null

  try {
    const data = JSON.parse(dataLines.join('\n')) as unknown
    if (typeof data !== 'object' || data === null) return null
    return { event, data: data as Record<string, any> }
  } catch {
    return null
  }
}

/**
 * 事件分发。
 *
 * 参数用 ``Record<string, any>`` 而非 ``unknown``：负载来自网络，本来就无法在
 * 编译期校验，各个 case 里的断言（``data as ChatMeta``）是必要的类型收窄。
 * 用 ``unknown`` 会导致 9 处都要先 ``as unknown as X``，噪音大于收益。
 * 类型安全由下面的 `ChatHandlers` 契约保证调用方拿到的字段名是对的。
 */
function handleChatEvent(
  event: string,
  data: Record<string, any>,
  handlers: ChatHandlers,
): void {
  switch (event) {
    case 'meta':
      handlers.onMeta?.(data as ChatMeta)
      break
    case 'message_start':
      handlers.onMessageStart?.(data as { iteration: number })
      break
    case 'delta':
      handlers.onDelta?.((data as { text: string }).text ?? '')
      break
    case 'reasoning':
      handlers.onReasoning?.((data as { text: string }).text ?? '')
      break
    case 'message_end':
      handlers.onMessageEnd?.(
        data as {
          iteration: number
          content: string
          tool_calls: Array<{ id: string; name: string; arguments: Record<string, unknown> }>
        },
      )
      break
    case 'tool_call':
      handlers.onToolCall?.(data as ToolCallEvent)
      break
    case 'tool_result':
      handlers.onToolResult?.(data as ToolResultEvent)
      break
    case 'plan':
      handlers.onPlan?.(data as Plan)
      break
    case 'plan_update':
      handlers.onPlanUpdate?.(data as Plan)
      break
    case 'permission_request':
      handlers.onPermissionRequest?.(data as PermissionEvent)
      break
    // 技能要问用户一个问题（选择 / 敏感输入）。形状与 `permission_request` 不同
    // （那个是扁平的权限信息，这个是 `payload` 里带内容的交互请求），
    // 所以这里原样透传，由 `chatStore.onInteractionRequest` 负责拍平 ——
    // 放在 store 里转换而不是这里，是因为那里才知道会话上下文（sessionKey）。
    case 'interaction_request':
      handlers.onInteractionRequest?.(data as InteractionEvent)
      break
    case 'usage':
      handlers.onUsage?.(
        data as { prompt_tokens: number; completion_tokens: number; total_tokens: number },
      )
      break
    case 'trace':
      handlers.onTrace?.(data as TraceData)
      break
    case 'done':
      handlers.onDone?.(data as DoneEvent)
      break
    case 'error':
      handlers.onErrorEvent?.(data as StreamError)
      break
    case 'warning':
      handlers.onWarning?.(data as { message: string })
      break
    case 'context_compressed':
      handlers.onContextCompressed?.(data as { summary_chars: number })
      break
    case 'injection_suspected':
      handlers.onInjectionSuspected?.(
        data as { name: string; display_name?: string; labels: string[] },
      )
      break
    default:
      break
  }
}
