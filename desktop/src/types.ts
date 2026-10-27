import type { AgentBridge } from '@shared/bridge'

declare global {
  interface Window {
    agentBridge: AgentBridge
  }
}




export interface SessionSummary {
  id: string
  title: string
  model_id: string | null
  
  assistant_id: string | null
  




  reasoning_effort: string | null
  created_at: number
  updated_at: number
  message_count: number
}

export interface HistoryMessage {
  role: 'user' | 'assistant'
  content: string
  






  created_at?: number | null
  





  plan?: Plan | null
  






  reasoning?: string
  







  tool_calls?: Array<{ id: string; name: string; arguments?: Record<string, unknown> }>
}










export interface RunRecord {
  id: string
  
  kind: 'task' | 'group' | 'chat' | string
  
  ref_id: string
  
  session_id: string
  
  status: 'failed' | 'cancelled' | 'incomplete' | string
  step: number
  last_action: string
  error: string
  created_at: number
  updated_at: number
  
  summary: string
}




export type ToolStatus = 'running' | 'ok' | 'error' | 'denied'

export interface ToolCallState {
  id: string
  name: string
  displayName: string
  description: string
  params: Record<string, unknown>
  permissionLevel: string
  status: ToolStatus
  result?: string
  durationMs?: number
  
  startedAt?: number
}

export type MessageStatus = 'streaming' | 'done' | 'error' | 'cancelled'

export interface TokenUsage {
  prompt_tokens: number
  completion_tokens: number
  total_tokens: number
  
  cached_tokens?: number
  cache_write_tokens?: number
  reasoning_tokens?: number
  
  cache_hit_rate?: number
}

export interface ChatMessage {
  id: string
  role: 'user' | 'assistant'
  content: string
  reasoning: string
  toolCalls: ToolCallState[]
  status: MessageStatus
  error?: string
  iterations?: number
  usage?: TokenUsage
  createdAt: number
  





  plan?: Plan | null
  










  assistantId?: string
}













export type PlanStepStatus = 'pending' | 'doing' | 'done' | 'failed'










export type PlanState = 'awaiting' | 'executing' | 'done' | 'cancelled' | 'aborted'

export interface PlanStep {
  
  id: string
  text: string
  status: PlanStepStatus
  
  note?: string
}

export interface Plan {
  
  id: string
  
  goal: string
  steps: PlanStep[]
  state: PlanState
}





export interface InteractionChoice {
  label: string
  description: string
}


export interface InteractionSecretField {
  
  name: string
  
  label: string
  hint: string
  multiline: boolean
}








export interface InteractionEvent {
  requestId: string
  skillName: string
  displayName: string
  kind: 'choice' | 'secret'
  
  question: string
  options: InteractionChoice[]
  allowCustom: boolean
  
  reason: string
  fields: InteractionSecretField[]
  
  groupId?: string
  groupName?: string
  assistantId?: string
  assistantName?: string
  
  sessionKey?: string
  
  sessionTitle?: string
}


export interface InteractionAnswer {
  
  cancelled?: boolean
  
  value?: string
  
  custom?: string
  
  names?: string[]
}




export interface PermissionRequest {
  requestId: string
  skillName: string
  displayName: string
  description: string
  permissionLevel: string
  params: Record<string, unknown>
  prompt: string
  





  source?: string
  





  sessionId?: string
  
  sessionTitle?: string
}




export interface TraceSpan {
  span_id: string
  parent_id?: string
  name: string
  status: 'running' | 'ok' | 'error'
  duration_ms: number
  
  start_ms?: number
  end_ms?: number
  meta: Record<string, unknown>
  events: Array<Record<string, unknown>>
  error?: string
}

export interface TraceData {
  trace_id: string
  started_at: number
  total_duration_ms: number
  total_tokens: number
  prompt_tokens: number
  completion_tokens: number
  spans: TraceSpan[]
}




export interface ModelInfo {
  id: string
  name: string
  display_name: string
  provider: string
  adapter: string
  base_url: string
  api_key: string
  has_api_key: boolean
  



  inherit_key_from?: string
  model_name: string
  token_limit: number
  supports_tools: boolean
  supports_stream: boolean
  






  supports_vision: boolean
  






  supports_reasoning: boolean
  
  use_system_proxy?: boolean
  timeout: number
  
  price_input_per_1m_peak?: number | null
  price_output_per_1m_peak?: number | null
  
  price_cached_input_per_1m_peak?: number | null
  peak_windows?: Array<{ days: number[]; start: string; end: string }>
  temperature: number
  max_tokens: number | null
  





  tier: 'cheap' | 'standard' | 'strong'
  





  fallback_models: string[]
  enabled: boolean
  is_default: boolean
  





  price_input_per_1m: number | null
  price_cached_input_per_1m: number | null
  price_output_per_1m: number | null
}










export type ModelHubState = 'idle' | 'running' | 'done' | 'failed' | 'cancelled' | 'unknown'


export interface ModelHubEntry {
  
  key: string
  title: string
  summary: string
  
  requirement: string
  state: ModelHubState
  
  installed: boolean
  total_bytes: number
  done_bytes: number
  
  current_file: string
  
  speed: number
  error: string
  





  fallback_used: boolean
  
  line: string | null
  files: Array<{ path: string; size: number; done?: number }>
}


export interface ModelHubStatus {
  ok: boolean
  line: string
  line_title: string
  models: ModelHubEntry[]
}


export interface ModelHubAction {
  ok: boolean
  reason: string
  key: string
}


export interface ModelVerifyResult {
  ok: boolean
  reason: string
  detail?: string
}


export interface GroupProfile {
  id: string
  name: string
  member_assistant_ids: string[]
  
  speaking_order: string[]
  







  group_type: 'work' | 'discussion'
  




  reasoning_effort: 'low' | 'medium' | 'high' | null
  





  confirm_mode: 'interactive' | 'deny' | 'auto_approve' | null
  






  avatar: string
  










  wake_words: string[]
}







export interface GroupThread {
  id: string
  group_id: string
  title: string
  created_at: string
  updated_at: string
}


export interface GroupUpdate {
  name?: string
  





  member_assistant_ids?: string[]
  speaking_order?: string[]
  
  avatar?: string
  reasoning_effort?: GroupProfile['reasoning_effort'] | ''
  confirm_mode?: GroupProfile['confirm_mode'] | ''
  





  wake_words?: string[]
}





export interface ProviderPreset {
  provider: string
  name: string
  base_url: string
  models: string[]
  
  docs: string
  







  apply_url?: string
  






  token_limit?: number
  






  adapter?: string
  
  use_system_proxy?: boolean
}

export interface ModelsPayload {
  default_model: string
  effective_default: string
  models: ModelInfo[]
  presets?: ProviderPreset[]
}

export interface SkillInfo {
  name: string
  display_name: string
  description: string
  parameters: Record<string, unknown>
  category: string
  permission_level: 'safe' | 'confirm' | 'admin'
  timeout: number
  enabled: boolean
  tags: string[]
  source: string
  








  locked?: boolean
  



  instruction_only?: boolean
  







  domain?: string
  
  owner_label?: string
  
  locked_reason?: string
  











  bucket?: 'mine' | 'common' | 'builtin' | 'exclusive'
  
  owners?: string[]
}


export interface CalendarConfig {
  



  mode: 'auto' | 'local' | 'caldav'
  caldav_url: string
  caldav_username: string
  
  caldav_password: string
  
  default_duration_minutes: number
  calendar_name: string
}


export interface CalendarTestResult {
  ok: boolean
  upcoming: number
  sample: Array<{ uid: string; summary: string; start: string; text: string }>
  message: string
}

export interface AppSettings {
  app_name: string
  log_level: string
  trace_enabled: boolean
  






  theme:
    | 'light'
    | 'dark'
    | 'system'
    | 'warm'
    | 'forest'
    | 'ocean'
    | 'sakura'
    | 'mint'
    | 'sky'
    | 'apricot'
    | 'plum'
    | 'pine'
    | 'charcoal'
    | 'deepday'
    | 'deepnight'
  language: string
  
  
  agent: {
    max_iterations: number
    max_tool_calls_per_turn: number
    temperature: number
    



    top_p: number | null
    frequency_penalty: number | null
    presence_penalty: number | null
    system_prompt: string
    confirm_mode: ConfirmMode
    
    max_context_tokens: number
    






    utility_model_id: string
    same_tool_failure_tolerance: number
    





    auto_open_group_window: boolean
  }
  security: {
    allowed_dirs: string[]
    confirm_mode: ConfirmMode
    confirm_timeout_seconds: number
    redact_enabled: boolean
    audit_retention_days: number
  }
  





  voice: {
    
    wake_words: string[]
    send_word: string
    cancel_word: string
    










    









    startup_mode: 'off' | 'global' | 'all'
    



    enable_word: string
    disable_word: string
    






    command_words: Record<string, string>
    
    disabled_commands: string[]
  }
  usage: {
    currency: 'CNY' | 'USD'
    
    daily_budget: number | null
    retention_days: number
  }
  calendar: CalendarConfig
  memory: {
    
    long_term_enabled: boolean
    vector_top_k: number
    
    embedding_backend: 'builtin' | 'api' | 'ollama'
    
    embedding_base_url: string
    embedding_model: string
    
    embedding_key_model_id: string
    
    embedding_api_key: string
    
    embedding_ollama_url: string
    embedding_ollama_model: string
    
    use_api_embedding: boolean
    embedding_model_id: string
  }
}

export interface PathsInfo {
  root: string
  config: string
  data: string
  logs: string
  workspace: string
  artifacts: string
}

export interface BackendHealth {
  status: string
  version: string
  default_model: string
  models: string[]
  skills: number
  sessions: number
  running_tasks: number
  data_dir: string
  persistent: boolean
}




export interface FileRecord {
  id: string
  original_name: string
  kind: 'upload' | 'artifact'
  size: number
  mime: string | null
  session_id: string | null
  note: string | null
  created_at: number
}





export interface CustomSkillParam {
  name: string
  description: string
  required: boolean
  default: string | null
  type: 'string' | 'number' | 'boolean'
}







export interface CustomSkillDef {
  id: string
  name: string
  description: string
  params: CustomSkillParam[]
  



  kind: 'http' | 'command' | 'instruction'
  url: string
  method: 'GET' | 'POST' | 'PUT' | 'DELETE'
  headers: Record<string, string>
  body_template: string
  command_template: string
  
  instructions?: string
  timeout: number
  permission_level: 'safe' | 'confirm' | 'admin'
  enabled: boolean
  




  source_format?: string
  
  package_root?: string
  
  scripts?: string[]
  
  allowed_tools?: string[]
  
  note?: string
  







  domain?: string
}


export interface SkillImportEntry {
  name: string
  id?: string
  ok: boolean
  kind?: string
  source_format?: string
  
  note?: string
  message?: string
  
  skipped?: boolean
  
  updated?: boolean
  
  files?: number
  
  pack?: string
}


export interface SkillImportOutcome {
  ok: boolean
  installed: CustomSkillDef[]
  results: SkillImportEntry[]
  
  unpacked: Record<string, number>
  
  unrecognized: string[]
  
  skipped: string[]
  total: number
  message: string
  
  mcp?: Array<{ name: string; ok: boolean; message: string }>
  
  source_path?: string
  
  scanned?: number
}


export interface SkillFolderInfo {
  skills_dir: string
  inbox: string
  exists: boolean
}


export interface SkillFileEntry {
  path: string
  size: number
}


export interface McpImportResult {
  ok: boolean
  added: string[]
  errors: Array<{ name: string; message: string }>
  total: number
}


export interface PersonaFile {
  name: string
  exists: boolean
  size: number
  content: string
  
  hint: string
}

export interface PersonaFilesPayload {
  files: PersonaFile[]
}


export interface PersonaLockRequest {
  action: 'set' | 'clear' | 'verify'
  password?: string
  current?: string
  confirm?: string
}

export interface PersonaLockResult {
  ok: boolean
  locked: boolean
}

export interface AssistantProfile {
  id: string
  name: string
  
  nickname: string
  emoji: string
  
  avatar: string
  
  chat_background: string
  





  voice: AppSettings['voice']
  description: string
  





  persona_locked: boolean
  system_prompt: string
  model_id: string
  temperature: number | null
  max_iterations: number | null
  max_tool_calls_per_turn: number | null
  






  reasoning_effort: string | null
  enabled_skills: string[]
  confirm_mode: ConfirmMode | null
  builtin: boolean
  sort_order: number
  
  restricts_skills: boolean
  
  unavailable_skills: string[]
  






  locked?: boolean
  
  locked_fields?: string[]
  
  locked_reason?: string
}

export interface AssistantsPayload {
  assistants: AssistantProfile[]
  default_assistant: string
  





  legacy_ids?: Record<string, string>
}




export interface TableSheet {
  name: string
  columns: string[]
  rows: Array<Array<string | number | boolean | null>>
  total_rows: number
  truncated: boolean
}

export type ArtifactPreview = {
  name: string
  suffix: string
  size: number
  mime: string | null
  download_url: string | null
} & (
  | { kind: 'svg'; content: string; truncated: boolean }
  | { kind: 'markdown'; content: string; truncated: boolean; note?: string }
  | { kind: 'text'; content: string; truncated: boolean; note?: string }
  | { kind: 'json'; content: string }
  | { kind: 'table'; sheets: TableSheet[]; note?: string }
  | { kind: 'image'; url: string | null }
  | { kind: 'unsupported'; reason: string }
)

export interface WorkspaceStats {
  total: number
  uploads: number
  artifacts: number
  total_bytes: number
  workspace_dir: string
  artifacts_dir: string
}







export interface SessionContext {
  used_tokens: number
  limit_tokens: number
  remaining_tokens: number
  
  ratio: number
  
  compress_threshold: number
  
  summary_chars: number
}





export type TaskTrigger = 'interval' | 'daily' | 'weekly'


export type TaskCondition = 'none' | 'url_changed' | 'file_changed'









export type TaskOrigin = 'user' | 'agent' | 'builtin'


export interface ScheduledTask {
  id: string
  name: string
  prompt: string
  
  assistant_id: string
  enabled: boolean
  trigger: TaskTrigger
  
  interval_minutes: number
  
  at_time: string
  
  weekday: number
  





  start_at: string
  condition: TaskCondition
  
  condition_target: string
  
  origin: TaskOrigin
  
  silent: boolean
}








export type ScheduledTaskDraft = Omit<ScheduledTask, 'id' | 'origin' | 'silent'>












export interface ScheduledTaskState extends ScheduledTask {
  






  locked: boolean
  
  last_run_at: number | null
  running: boolean
  
  next_run_in_seconds: number | null
  





  condition_ready: boolean
}

export interface TasksPayload {
  total: number
  enabled: number
  scheduler_running: boolean
  items: ScheduledTaskState[]
}


export interface PendingAttachment {
  id: string
  name: string
  size: number
  status: 'uploading' | 'ready' | 'error'
  error?: string
  








  kind: 'file' | 'image'
}




export type AuditStatus = 'ok' | 'error' | 'denied' | 'timeout'








export type AuditKind = 'skill' | 'assistant' | 'group' | 'session' | 'task' | 'permission'

export interface AuditLogEntry {
  id: number
  ts: number
  session_id: string | null
  skill_name: string
  permission_level: string
  params: Record<string, unknown> | null
  status: AuditStatus
  duration_ms: number | null
  detail: string | null
  
  kind?: string
  
  actor_id?: string
  
  action?: string
  
  target?: string
}

export interface AuditStats {
  available: boolean
  total: number
  by_status: Record<string, number>
  
  by_kind?: Record<string, number>
  top_skills: Array<{ skill_name: string; count: number }>
}












export type ConfirmMode = 'interactive' | 'deny' | 'auto_approve'

export interface ConfirmModeState {
  
  mode: ConfirmMode
  
  assistant_override: ConfirmMode | null
  
  effective: ConfirmMode
}




export interface UsageTotals {
  prompt_tokens: number
  completion_tokens: number
  cached_tokens: number
  cache_write_tokens: number
  reasoning_tokens: number
  total_tokens: number
  calls: number
  
  cache_hit_rate: number | null
  





  cost: number | null
}

export interface UsageDay extends UsageTotals {
  
  day: string
}

export interface UsageByModel extends UsageTotals {
  model_id: string
}

export interface UsageSummary {
  available: boolean
  
  message?: string
  currency: string
  daily_budget: number | null
  
  prices_configured: boolean
  window_days: number
  today: UsageTotals | null
  total: UsageTotals | null
  window: UsageTotals | null
  by_model: UsageByModel[]
  by_day: UsageDay[]
}




export type McpServerState =
  | 'disabled'
  | 'stopped'
  | 'starting'
  | 'ready'
  | 'restarting'
  | 'error'

export interface McpToolInfo {
  name: string
  title: string
  description: string
  input_schema: Record<string, unknown>
  read_only: boolean | null
  destructive: boolean | null
}

export interface McpServerConfig {
  name: string
  






  transport: string
  
  url: string
  
  headers: Record<string, string>
  command: string
  args: string[]
  env: Record<string, string>
  cwd: string | null
  enabled: boolean
  auto_start: boolean
  description: string
  timeout: number
  permission_overrides: Record<string, string>
}






export interface McpServerStatus extends McpServerConfig {
  state: McpServerState
  message: string
  tools: McpToolInfo[]
  tool_count: number
  restarts: number
  last_error: string | null
  
  sdk_missing: boolean
}

export interface McpPreset {
  key: string
  title: string
  description: string
  
  requires: string
  server: McpServerConfig
}











export interface ImportResultRow {
  
  name: string
  ok: boolean
  
  message?: string
  kind?: string
  id?: string
  
  pack?: string
  
  skipped?: boolean
}


export interface ImportOutcome {
  ok: boolean
  action?: 'create' | 'update'
  assistant?: { id: string; name: string }
  group?: { id: string; name: string }
  
  skills?: string[]
  
  skills_missing?: string[]
  results: ImportResultRow[]
}
