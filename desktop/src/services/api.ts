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
    
  }
  return new ApiError(response.status, code, message, detail)
}




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
  





  onPlan?: (data: Plan) => void
  
  onPlanUpdate?: (data: Plan) => void
  onUsage?: (data: {
    prompt_tokens: number
    completion_tokens: number
    total_tokens: number
  }) => void
  onTrace?: (data: TraceData) => void
  onDone?: (data: DoneEvent) => void
  onErrorEvent?: (data: StreamError) => void
  






  onWarning?: (data: { message: string }) => void
  








  onContextCompressed?: (data: { summary_chars: number }) => void
  






  onInjectionSuspected?: (data: {
    name: string
    display_name?: string
    labels: string[]
  }) => void
  






  onInteractionRequest?: (data: InteractionEvent) => void
}




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

  
  
  
  
  

  












  async fetchLocalImage(path: string): Promise<Blob> {
    const response = await fetch(
      `${this.baseUrl}/v1/media/local-image?path=${encodeURIComponent(path)}`,
      { headers: { 'X-Local-Token': this.token } },
    )
    if (!response.ok) throw await toApiError(response)
    return response.blob()
  }

  










  private static readonly DEFAULT_TIMEOUT_MS = 60_000

  async request<T>(
    path: string,
    init: RequestInit = {},
    timeoutMs: number = AgentApi.DEFAULT_TIMEOUT_MS,
  ): Promise<T> {
    
    
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

  
  health = () => this.get<BackendHealth>('/v1/health')
  getSettings = () => this.get<AppSettings>('/v1/settings')
  






  saveSettings = (payload: AppSettings, options?: { clearCalendarPassword?: boolean }) =>
    this.send<AppSettings>(
      `/v1/settings${options?.clearCalendarPassword ? '?clear_calendar_password=true' : ''}`,
      'PUT',
      payload,
    )
  
  testCalendar = (payload: {
    caldav_url?: string
    caldav_username?: string
    caldav_password?: string
  }) => this.send<CalendarTestResult>('/v1/calendar/test', 'POST', payload)
  getPaths = () => this.get<PathsInfo>('/v1/paths')

  
  






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

  





  voiceStatus = () =>
    this.get<{
      asr: { available: boolean; loaded: boolean }
      wake: { available: boolean; loaded: boolean }
      tts: { available: boolean; loaded: boolean; speakers: number }
    }>('/v1/voice/status')

  






  matchVoiceCommand = (text: string, candidates: Array<{ id: string; word: string }>) =>
    this.voicePost<{ id: string | null }>('/v1/voice/match', { text, candidates }, 10_000)

  
  voiceAsr = (pcmBase64: string, sampleRate: number) =>
    this.voicePost<{
      text: string
      emotion: string
      event: string
      language: string
      duration_ms: number
      took_ms: number
    }>('/v1/voice/asr', { pcm: pcmBase64, sample_rate: sampleRate }, 30_000)

  











  voiceWake = (pcmBase64: string, sampleRate: number, words: string[]) =>
    this.voicePost<{ hit: string | null; source: 'asr'; text: string }>(
      '/v1/voice/wake',
      { pcm: pcmBase64, sample_rate: sampleRate, words },
      15_000,
    )



  
  






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
  





  runTask = (id: string) =>
    this.send<{ ok: boolean; task_id: string }>(
      `/v1/tasks/${encodeURIComponent(id)}/run`,
      'POST',
    )

  
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

  
  





  modelStatus = () => this.get<ModelHubStatus>('/v1/models/status')
  
  downloadModel = (key: string) =>
    this.send<ModelHubAction>('/v1/models/download', 'POST', { key })
  
  cancelModelDownload = (key: string) =>
    this.send<ModelHubAction>('/v1/models/cancel', 'POST', { key })
  
  verifyModel = (key: string) =>
    this.send<ModelVerifyResult>('/v1/models/verify', 'POST', { key })

  









  async uploadSkillPackage(file: File): Promise<SkillImportOutcome> {
    const form = new FormData()
    form.append('package', file)
    
    
    
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

  






  importBuddyPackage = (file: File) => this.postPackage<ImportOutcome>('/v1/assistants/import', file)

  
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

  






  setLine = (line: string) =>
    this.send<{ ok: boolean; line: string }>('/v1/client/line', 'PUT', { line })

  
  getSkills = (enabledOnly = false) =>
    this.get<{ total: number; enabled: number; skills: SkillInfo[]; categories: string[] }>(
      `/v1/skills${enabledOnly ? '?enabled_only=true' : ''}`,
    )
  patchSkill = (name: string, payload: { enabled?: boolean; permission_level?: string }) =>
    this.send<SkillInfo>(`/v1/skills/${encodeURIComponent(name)}`, 'PATCH', payload)

  
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
  
  getSessionContext = (id: string) =>
    this.get<SessionContext>(`/v1/sessions/${encodeURIComponent(id)}/context`)
  getMessages = (id: string) =>
    this.get<{ session_id: string; messages: HistoryMessage[] }>(`/v1/sessions/${id}/messages`)
  clearMessages = (id: string) =>
    this.send<{ ok: boolean }>(`/v1/sessions/${id}/messages`, 'DELETE')

  
  getFiles = (kind?: 'upload' | 'artifact') =>
    this.get<{ files: FileRecord[]; stats: WorkspaceStats }>(
      `/v1/files${kind ? `?kind=${kind}` : ''}`,
    )

  getFileStats = () => this.get<WorkspaceStats>('/v1/files/stats')

  
  previewFile = (id: string, kind: 'upload' | 'artifact' = 'artifact') =>
    this.get<ArtifactPreview>(
      `/v1/files/${encodeURIComponent(id)}/preview?kind=${kind}`,
    )

  deleteFile = (id: string, kind: 'upload' | 'artifact' = 'upload') =>
    this.send<{ ok: boolean }>(`/v1/files/${encodeURIComponent(id)}?kind=${kind}`, 'DELETE')

  clearFiles = (kind?: 'upload' | 'artifact') =>
    this.send<{ ok: boolean; removed: number }>('/v1/files/clear', 'POST', { kind })

  





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

  
  







  getAudit = (
    params: {
      limit?: number
      session_id?: string
      status?: string
      
      kind?: string
      
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

  
  
  getRuns = () => this.get<{ total: number; runs: RunRecord[] }>('/v1/runs')

  





  resumeRun = (id: string) =>
    this.send<{
      ok: boolean
      kind: string
      session_id?: string
      group_id?: string
      topic?: string
      message?: string
    }>(`/v1/runs/${encodeURIComponent(id)}/resume`, 'POST')

  
  dismissRun = (id: string) =>
    this.send<{ ok: boolean }>(`/v1/runs/${encodeURIComponent(id)}`, 'DELETE')

  getAuditStats = () => this.get<AuditStats>('/v1/audit/stats')

  clearAudit = () => this.send<{ ok: boolean; removed: number }>('/v1/audit', 'DELETE')

  
  stop = (payload: { task_id?: string; session_id?: string }) =>
    this.send<{ ok: boolean; cancelled: number }>('/v1/stop', 'POST', payload)
  confirm = (requestId: string, approved: boolean) =>
    this.send<{ ok: boolean }>('/v1/confirm', 'POST', {
      request_id: requestId,
      approved,
    })

  







  planDecision = (planId: string, approved: boolean, feedback = '') =>
    this.send<{ ok: boolean; action?: 'approved' | 'revise' | 'aborted'; message?: string }>(
      '/v1/plan/decision',
      'POST',
      { plan_id: planId, approved, feedback },
    )

  









  interactionDecision = (requestId: string, answer: InteractionAnswer) =>
    this.send<{ ok: boolean; message?: string }>('/v1/interaction/decision', 'POST', {
      request_id: requestId,
      answer,
    })

  
  





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

  
  getUsageSummary = (days = 30) => this.get<UsageSummary>(`/v1/usage/summary?days=${days}`)

  getSessionUsage = (sessionId: string) =>
    this.get<UsageTotals & { available: boolean }>(
      `/v1/usage/session/${encodeURIComponent(sessionId)}`,
    )

  
  clearUsage = () => this.send<{ ok: boolean; removed: number }>('/v1/usage', 'DELETE')

  
  getConfirmMode = (assistantId?: string | null) =>
    this.get<ConfirmModeState>(
      `/v1/security/confirm-mode${
        assistantId ? `?assistant_id=${encodeURIComponent(assistantId)}` : ''
      }`,
    )

  






  setConfirmMode = (mode: ConfirmMode) =>
    this.send<{ mode: ConfirmMode }>('/v1/security/confirm-mode', 'PUT', { mode })

  
  getSecurityOverrides = () =>
    this.get<{ overrides: Record<string, string> }>('/v1/security/overrides')

  addSecurityOverride = (skill: string) =>
    this.send<{ overrides: Record<string, string> }>('/v1/security/overrides', 'POST', {
      skill,
      remember: true,
    })

  
  clearSecurityOverrides = () =>
    this.send<{ overrides: Record<string, string> }>('/v1/security/overrides', 'DELETE')

  
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

  




  importMcpJson = (payload: string, overwrite = false) =>
    this.send<McpImportResult>('/v1/mcp/import-json', 'POST', { payload, overwrite })

  
  getCustomSkills = () => this.get<{ skills: CustomSkillDef[] }>('/v1/skills/custom')

  
  saveCustomSkill = (skill: CustomSkillDef) =>
    this.send<{ ok: boolean; skill: CustomSkillDef; total: number }>('/v1/skills/custom', 'POST', {
      skill,
    })

  deleteCustomSkill = (id: string) =>
    this.send<{ ok: boolean; total: number }>(`/v1/skills/custom/${encodeURIComponent(id)}`, 'DELETE')

  





  importSkillFolder = (path: string, name = '') =>
    this.send<SkillImportOutcome>('/v1/skills/custom/import-path', 'POST', { path, name })

  
  getSkillFolder = () => this.get<SkillFolderInfo>('/v1/skills/custom/folder')

  
  scanSkillFolder = (only = '') =>
    this.send<SkillImportOutcome>('/v1/skills/custom/scan', 'POST', { only })

  
  getSkillFiles = (skillId: string) =>
    this.get<{ skill_id: string; dir: string; files: SkillFileEntry[] }>(
      `/v1/skills/custom/${encodeURIComponent(skillId)}/files`,
    )

  
  setMcpToolPermission = (name: string, tool: string, level: string) =>
    this.send<{ ok: boolean; overrides: Record<string, string> }>(
      `/v1/mcp/servers/${encodeURIComponent(name)}/permission`,
      'PATCH',
      { tool, permission_level: level },
    )

  
  getAssistants = () => this.get<AssistantsPayload>('/v1/assistants')

  createAssistant = (profile: AssistantProfile) =>
    this.send<AssistantProfile>('/v1/assistants', 'POST', profile)

  updateAssistant = (id: string, profile: AssistantProfile) =>
    this.send<AssistantProfile>(`/v1/assistants/${encodeURIComponent(id)}`, 'PUT', profile)

  deleteAssistant = (id: string) =>
    this.send<{ ok: boolean }>(`/v1/assistants/${encodeURIComponent(id)}`, 'DELETE')

  
  getGroups = () => this.get<{ groups: GroupProfile[] }>('/v1/groups')

  createGroup = (payload: {
    name: string
    member_assistant_ids: string[]
    
    speaking_order?: string[]
    





    avatar?: string
  }) => this.send<GroupProfile>('/v1/groups', 'POST', payload)

  deleteGroup = (id: string) =>
    this.send<{ ok: boolean }>(`/v1/groups/${encodeURIComponent(id)}`, 'DELETE')

  






  updateGroup = (id: string, payload: GroupUpdate) =>
    this.send<GroupProfile>(`/v1/groups/${encodeURIComponent(id)}`, 'PATCH', payload)

  groupChat = (id: string, message: string) =>
    this.send<{
      replies: Array<{ assistant_id: string; name: string; content: string; error?: string }>
    }>(`/v1/groups/${encodeURIComponent(id)}/chat`, 'POST', { message })

  
  





  getGroupThreads = (id: string) =>
    this.get<{ threads: GroupThread[]; persistent: boolean }>(
      `/v1/groups/${encodeURIComponent(id)}/threads`,
    )

  
  createGroupThread = (id: string, title = '') =>
    this.send<GroupThread>(`/v1/groups/${encodeURIComponent(id)}/threads`, 'POST', { title })

  renameGroupThread = (id: string, threadId: string, title: string) =>
    this.send<GroupThread>(
      `/v1/groups/${encodeURIComponent(id)}/threads/${encodeURIComponent(threadId)}`,
      'PATCH',
      { title },
    )

  
  deleteGroupThread = (id: string, threadId: string) =>
    this.send<{ ok: boolean }>(
      `/v1/groups/${encodeURIComponent(id)}/threads/${encodeURIComponent(threadId)}`,
      'DELETE',
    )

  








  getGroupMessages = (id: string, threadId = '') =>
    this.get<{ events: GroupReplayEvent[]; persistent: boolean; thread_id: string }>(
      `/v1/groups/${encodeURIComponent(id)}/messages${threadId ? `?thread_id=${encodeURIComponent(threadId)}` : ''}`,
    )

  
  clearGroupMessages = (id: string, threadId = '') =>
    this.send<{ ok: boolean; removed: number; thread_id: string }>(
      `/v1/groups/${encodeURIComponent(id)}/messages${threadId ? `?thread_id=${encodeURIComponent(threadId)}` : ''}`,
      'DELETE',
    )

  
  stopGroupDiscussion = (id: string) =>
    this.send<{ group_id: string; stopped: boolean }>(
      `/v1/groups/${encodeURIComponent(id)}/stop`,
      'POST',
    )

  








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
          
          thread_id: payload.threadId ?? '',
        }),
        signal,
      },
    )
    if (!response.ok) throw await toApiError(response)
    if (!response.body) throw new ApiError(500, 'no_body', '服务端未返回响应流')
    await consumeSSE(response, onEvent)
  }

  
  getPersonaFiles = (id: string) =>
    this.get<PersonaFilesPayload>(`/v1/assistants/${encodeURIComponent(id)}/persona-files`)

  writePersonaFile = (id: string, name: string, content: string) =>
    this.send<PersonaFilesPayload>(
      `/v1/assistants/${encodeURIComponent(id)}/persona-files/${encodeURIComponent(name)}`,
      'PUT',
      { content },
    )

  




  personaLock = (id: string, payload: PersonaLockRequest) =>
    this.send<PersonaLockResult>(
      `/v1/assistants/${encodeURIComponent(id)}/persona-lock`,
      'POST',
      payload,
    )

  
  
  
  

  
  async streamChat(
    payload: {
      message: string
      session_id?: string
      model_id?: string
      assistant_id?: string
      attachments?: string[]
      
      images?: string[]
      




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


async function consumeSSE(
  response: Response,
  
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
    
    void reader.cancel().catch(() => undefined)
  }
}

function parseBlock(block: string): { event: string; data: Record<string, any> } | null {
  let event = 'message'
  const dataLines: string[] = []

  for (const rawLine of block.split('\n')) {
    const line = rawLine.trimEnd()
    if (!line || line.startsWith(':')) continue 
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
