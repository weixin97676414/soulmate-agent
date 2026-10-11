import type { AgentBridge } from '@shared/bridge'

declare global {
  interface Window {
    agentBridge: AgentBridge
  }
}

// --------------------------------------------------------------------------- //
// 会话
// --------------------------------------------------------------------------- //
export interface SessionSummary {
  id: string
  title: string
  model_id: string | null
  /** 该会话使用的助手；为空表示未绑定（用全局默认配置） */
  assistant_id: string | null
  /**
   * 该会话的思考强度：`'low' | 'medium' | 'high'`，为空表示**不发送这个参数**。
   *
   * 放在会话上而不是全局设置里 —— 用户对"这轮值不值得多想一会儿"的判断是按对话来的。
   */
  reasoning_effort: string | null
  created_at: number
  updated_at: number
  message_count: number
}

export interface HistoryMessage {
  role: 'user' | 'assistant'
  content: string
  /**
   * 这条消息**产生**的时刻（epoch 秒）。
   *
   * `null` = 不知道：更早版本落盘的消息时间戳是坏的（每次保存都会被同一个
   * "保存时刻"刷成一致），后端读出来一律当不知道 —— 界面上**不显示时间**，
   * 而不是拿一个假时间糊上去（那会让人把几个月前的旧事当成刚说的）。
   */
  created_at?: number | null
  /**
   * 这条助手消息**当时**的计划（单聊计划模式）。
   *
   * 缺省表示没有计划 —— 老消息（这个功能之前落盘的）与普通问答都是这样，
   * 界面不画卡片、也不报错（与 `groups.json` 加 `reviewer_id` 同样的兼容口径）。
   */
  plan?: Plan | null
}

// --------------------------------------------------------------------------- //
// 未完成的运行（断点续跑）
// --------------------------------------------------------------------------- //
/**
 * 一次**没跑完**的执行。
 *
 * 只在失败 / 被叫停时存在（正常跑完后端会把记录删掉），所以列表里出现的每一条
 * 都意味着"这里还能接着干"。`step` 与 `last_action` 是给用户看的"做到哪了"。
 */
export interface RunRecord {
  id: string
  /** task = 自动化任务；group = 群讨论；chat = 单聊里的一轮对话 */
  kind: 'task' | 'group' | 'chat' | string
  /** 任务 id / 群 id（单聊这条留空） */
  ref_id: string
  /** 任务/群/单聊都带会话 id —— 单聊靠它定位到具体那一轮对话 */
  session_id: string
  /** incomplete = 没出错但没做完（例如执行步数用尽），**不等于** failed */
  status: 'failed' | 'cancelled' | 'incomplete' | string
  step: number
  last_action: string
  error: string
  created_at: number
  updated_at: number
  /** 后端拼好的那句人话（"自动化任务没跑完就被中断了（最后在做：xx）"） */
  summary: string
}

// --------------------------------------------------------------------------- //
// 消息
// --------------------------------------------------------------------------- //
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
  /** 该次调用的开始时刻（epoch 秒）。时间跟工具卡走：正文里不再出现模型写的时间戳 */
  startedAt?: number
}

export type MessageStatus = 'streaming' | 'done' | 'error' | 'cancelled'

export interface TokenUsage {
  prompt_tokens: number
  completion_tokens: number
  total_tokens: number
  /** 命中前缀缓存的输入 token —— 单价可能只有未命中的 1/10 */
  cached_tokens?: number
  cache_write_tokens?: number
  reasoning_tokens?: number
  /** 0~1。后端在没有输入 token 时不返回该字段（而不是给 0，避免显示"命中率 0%"误导） */
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
  /**
   * 这轮任务的**执行计划**（单聊多步任务才有）。
   *
   * 计划随消息走：出计划 → 等确认 → 执行中逐项打勾 → 完成/取消，全过程都
   * 更新在这一个字段上，重开对话也能回看当时的分步与完成情况。
   */
  plan?: Plan | null
}

// --------------------------------------------------------------------------- //
// 执行计划（单聊计划模式）
// --------------------------------------------------------------------------- //
/**
 * 单步状态。取值与后端 `planner.STEP_STATUSES` 一一对应，改这里要同步改
 * `core/src/my_agent/agent/planner.py`。
 *
 * - `pending` 还没开始（空心圈）
 * - `doing`   正在做（转圈）
 * - `done`    已完成（对勾）
 * - `failed`  失败了（叉号 + 原因）
 */
export type PlanStepStatus = 'pending' | 'doing' | 'done' | 'failed'

/**
 * 整份计划的状态。取值与后端 `planner.PLAN_STATES` 对应。
 *
 * - `awaiting`  已出计划，**停下等用户确认**（此时一个工具都没执行）
 * - `executing` 用户点了「开始执行」，正在逐步推进
 * - `done`      所有步骤都已完成/失败，收尾了
 * - `cancelled` 被叫停（用户点了停止或断开连接）
 * - `aborted`   用户点了「不用了」，这次任务不做了
 */
export type PlanState = 'awaiting' | 'executing' | 'done' | 'cancelled' | 'aborted'

export interface PlanStep {
  /** 稳定序号（"1"、"2"...）—— 进度回报靠它定位 */
  id: string
  text: string
  status: PlanStepStatus
  /** 失败/补充说明；空表示没有，界面不渲染那一行 */
  note?: string
}

export interface Plan {
  /** 计划 id：点「开始执行 / 改一下」时原样回传，后端靠它找到在等的那一份 */
  id: string
  /** 一句话目标 */
  goal: string
  steps: PlanStep[]
  state: PlanState
}

// --------------------------------------------------------------------------- //
// 用户交互（选择 / 敏感输入）
// --------------------------------------------------------------------------- //
/** 选择弹窗里的一项候选理解 */
export interface InteractionChoice {
  label: string
  description: string
}

/** 敏感输入弹窗里的一格 */
export interface InteractionSecretField {
  /** 引用名（会出现在 `{{secret:名字}}` 里）——**不是**给用户看的标题 */
  name: string
  /** 给用户看的字段名，如「钱包私钥」 */
  label: string
  hint: string
  multiline: boolean
}

/**
 * 后端发起的一次交互请求（技能 `ask_choice` / `request_secret` 发出）。
 *
 * ⚠️ `kind === 'secret'` 时 `fields` 里**只有名字与提示，从来没有值** ——
 * 用户粘贴的内容由弹窗直接写进本地加密文件，不会经过这条事件。
 * 这是"AI 看不到明文"的实现方式（见 `electron/skill-secrets.ts`）。
 */
export interface InteractionEvent {
  requestId: string
  skillName: string
  displayName: string
  kind: 'choice' | 'secret'
  /** `kind === 'choice'` 时有意义：问题、选项、是否允许自定义输入 */
  question: string
  options: InteractionChoice[]
  allowCustom: boolean
  /** `kind === 'secret'` 时有意义：为什么要、要哪几格 */
  reason: string
  fields: InteractionSecretField[]
  /** 来源（群聊时才有），弹窗上要显示"是谁、在哪个群问的" */
  groupId?: string
  groupName?: string
  assistantId?: string
  assistantName?: string
  /** 属于哪个会话 —— 会话被关掉时要能把它一起收掉 */
  sessionKey?: string
  /** 来源会话的标题（用户可能已经切到别的会话了，弹窗上要能看出是谁在问） */
  sessionTitle?: string
}

/** 用户对交互请求的答复（回传给 `/v1/interaction/decision`）。 */
export interface InteractionAnswer {
  /** 用户关掉了弹窗 / 任务被打断 */
  cancelled?: boolean
  /** 选择题：选中的选项文字 */
  value?: string
  /** 选择题：用户自己输入的内容 */
  custom?: string
  /** 敏感输入：用户确实提供了哪几个名字（**只有名字，没有值**） */
  names?: string[]
}

// --------------------------------------------------------------------------- //
// 权限确认
// --------------------------------------------------------------------------- //
export interface PermissionRequest {
  requestId: string
  skillName: string
  displayName: string
  description: string
  permissionLevel: string
  params: Record<string, unknown>
  prompt: string
  /**
   * 请求来自哪里（例如群聊的群名）。
   *
   * 弹窗必须说清来源：群聊里的确认是"某个搭子在讨论中要求的"，
   * 用户看到一个凭空出现的确认框时，第一反应是"我点的是群聊啊，这是什么"。
   */
  source?: string
  /**
   * 这条请求属于**哪个会话**（单聊用）。
   *
   * 允许多轮同时跑之后，用户完全可能在 A 会话看到一条属于 B 会话的确认框，
   * 不说清来源就会变成"我明明没在这个对话里让它干什么"。
   */
  sessionId?: string
  /** 该会话的标题（展示用；为空时弹窗只说明"另一个对话"） */
  sessionTitle?: string
}

// --------------------------------------------------------------------------- //
// Trace
// --------------------------------------------------------------------------- //
export interface TraceSpan {
  span_id: string
  parent_id?: string
  name: string
  status: 'running' | 'ok' | 'error'
  duration_ms: number
  /** 相对 trace 起点的偏移，用于画时间线（只有 duration 排不出先后与嵌套） */
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

// --------------------------------------------------------------------------- //
// 模型与技能
// --------------------------------------------------------------------------- //
export interface ModelInfo {
  id: string
  name: string
  display_name: string
  provider: string
  adapter: string
  base_url: string
  api_key: string
  has_api_key: boolean
  /**
   * 仅提交侧：「同步服务商模型」新增的条目声明"Key 从哪条旧配置继承"。
   * 真实 Key 只在后端，前端拿不到明文 —— 想保留只能让后端自己复制。
   */
  inherit_key_from?: string
  model_name: string
  token_limit: number
  supports_tools: boolean
  supports_stream: boolean
  /**
   * 该模型能否接收图片输入。
   *
   * 默认 `false` 是刻意的：发图片给不支持的模型会让**整条请求**被拒
   * （连文字也拿不到回复），而误判成"不支持"的代价只是图片不随消息发出、
   * 并且界面会明确提示 —— 两害相权。
   */
  supports_vision: boolean
  /**
   * 能否接受"思考强度"参数。
   *
   * 默认 `true`（与其他能力开关相反），因为**只有用户主动选过档位时才发送**：
   * 不选的人一个字段都不多，选的人碰上不认这家的网关时由自适应回退兜住。
   * 默认 `false` 反而会让支持它的用户连控件都看不到。
   */
  supports_reasoning: boolean
  /** 请求是否走系统代理（默认关；仅需要代理访问的厂商打开） */
  use_system_proxy?: boolean
  timeout: number
  /** 高峰时段价格（可选，分时定价） */
  price_input_per_1m_peak?: number | null
  price_output_per_1m_peak?: number | null
  /** 高峰时段的缓存命中输入价（产品要求） */
  price_cached_input_per_1m_peak?: number | null
  peak_windows?: Array<{ days: number[]; start: string; end: string }>
  temperature: number
  max_tokens: number | null
  /**
   * 能力档位，供 ModelRouter 按任务复杂度挑模型。
   *
   * 默认 `standard` —— 刻意不预设任何厂商的档位："哪个模型便宜、哪个强"
   * 随厂商与时间变化，写死必然过时，由用户标注才是准的。
   */
  tier: 'cheap' | 'standard' | 'strong'
  /**
   * 备用模型 id，按顺序降级（见后端 `llm/fallback.py`）。
   *
   * 留空表示不降级。**默认必须是不降级**：请求会不会被发到另一家、
   * 花另一家的钱，只能由用户显式决定。
   */
  fallback_models: string[]
  enabled: boolean
  is_default: boolean
  /**
   * 价格，单位「每百万 token」，用于费用估算。
   *
   * `null` 表示**未配置**，界面要显示成「未配置价格」而不是「¥0.00」——
   * 把"不知道"显示成"免费"会直接误导用户的成本判断。
   */
  price_input_per_1m: number | null
  price_cached_input_per_1m: number | null
  price_output_per_1m: number | null
}

/**
 * 本地模型（语音 / 嵌入）的**下载状态**。
 *
 * ⚠️ 与 `ModelInfo`（上面那个，指"服务商提供的对话模型"）**完全不是一回事**：
 * 那个是用户填 Key 接的云端模型，这个是本机要下载的几百 MB 文件。
 * 两者都叫 "model"，混着看必然读错，所以这里刻意用 `ModelHub*` 命名。
 */

/** 本地模型下载状态里 `state` 的取值（与核心 `model_hub/downloader.py` 逐字一致） */
export type ModelHubState = 'idle' | 'running' | 'done' | 'failed' | 'cancelled' | 'unknown'

/** 一个本地模型的清单项 + 当前进度 */
export interface ModelHubEntry {
  /** 'voice' | 'embedding'（不写死联合类型：核心将来加模型时前端不用改） */
  key: string
  title: string
  summary: string
  /** 需要什么电脑配置（界面要如实写出来，用户得先判断装不装得下） */
  requirement: string
  state: ModelHubState
  /** 文件齐、且长度对（**以磁盘为准**，不只看本次会话的下载记录） */
  installed: boolean
  total_bytes: number
  done_bytes: number
  /** 正在下的文件名（空串 = 没有） */
  current_file: string
  /** 字节/秒（最近 3 秒的滑窗，不是"总字节 ÷ 总耗时"） */
  speed: number
  error: string
  /**
   * 是否已经切到**备用线路**。
   *
   * ⚠️ 界面必须显示它：静默切换会让用户以为"我选的国内源其实能用"，
   * 下次换机照旧踩坑。
   */
  fallback_used: boolean
  /** 本次下载实际走的线路（还没开始时为 null） */
  line: string | null
  files: Array<{ path: string; size: number; done?: number }>
}

/** `GET /v1/models/status` 的返回 */
export interface ModelHubStatus {
  ok: boolean
  line: string
  line_title: string
  models: ModelHubEntry[]
}

/** `POST /v1/models/download` / `cancel` 的返回 */
export interface ModelHubAction {
  ok: boolean
  reason: string
  key: string
}

/** `POST /v1/models/verify` 的返回（"自动检测"与「验证一下」共用） */
export interface ModelVerifyResult {
  ok: boolean
  reason: string
  detail?: string
}

/** AI 群：多个搭子拉进一个群，自主讨论（可按 speaking_order 排发言顺序） */
export interface GroupProfile {
  id: string
  name: string
  member_assistant_ids: string[]
  /** 发言顺序（用户可设置）；留空用成员原顺序 */
  speaking_order: string[]
  /**
   * 群级思考强度；null = 跟随每个成员自己的设置。
   *
   * 优先级：群 > 成员 > 不发送该参数（用户的判断是"这个群值不值得多想"）。
   */
  reasoning_effort: 'low' | 'medium' | 'high' | null
  /**
   * 群级权限策略；null = 跟随每个成员自己的设置。
   *
   * 界面上是「群里一律批准」开关（打开写 `auto_approve`）。
   * ⚠️ 它只对 confirm 级生效，admin（高危）级始终要人工确认。
   */
  confirm_mode: 'interactive' | 'deny' | 'auto_approve' | null
  /**
   * 群头像（data URL）。
   *
   * ⚠️ **空串是正常状态**：群头像库在前端（`services/avatarPack.ts` 的 24 张随包图），
   * 后端看不到那些 URL，所以"从来没设过的群"一律是空串 —— 由 `groupStore` 在
   * 拉到清单后按"优先不与现有群重复"的规则补一张并写回（与搭子那套完全一样）。
   */
  avatar: string
  /**
   * 语音唤醒词：说了它就把界面切到这个群。
   *
   * 与搭子的 `voice.wake_words` 是**同一套机制**（同一个本地 KWS 模型、同样的
   * 拼音匹配），只是归属不同 —— 那边是"喊谁醒谁"，这边是"喊哪个群进哪个群"。
   * 由后端在建群/读配置时按群名补一个「你好{群名}」，所以多数群零配置就能喊。
   *
   * ⚠️ **空数组是合法且有意义的状态**：表示用户明确不要唤醒词（这个群不参与
   * 语音唤醒）。它**不会**被重新补默认值 —— 想改回按群名喊，得去改掉那个词，
   * 而不是删光。
   */
  wake_words: string[]
}

/**
 * 群里的一条「对话」—— 一个群可以有多条互不相干的消息流。
 *
 * 与单聊的 `SessionSummary` 是同一个角色：那条属于某个搭子，这条属于某个群。
 * 事件本体在 `group_events` 里按 `thread_id` 分组，这里只有列表要用的元信息。
 */
export interface GroupThread {
  id: string
  group_id: string
  title: string
  created_at: string
  updated_at: string
}

/** 群设置的局部更新体：只传要改的字段 */
export interface GroupUpdate {
  name?: string
  /**
   * 建好之后增删成员（产品要求：群聊要能随时调整成员）。
   *
   * 传了就按新名单**整体替换**（顺序即发言顺序的基准）；不传 = 不动。
   * 至少两个搭子，否则后端会拒。
   */
  member_assistant_ids?: string[]
  speaking_order?: string[]
  /** 群头像（data URL）。传空串 = 清掉，由前端按规则重新补一张。 */
  avatar?: string
  reasoning_effort?: GroupProfile['reasoning_effort'] | ''
  confirm_mode?: GroupProfile['confirm_mode'] | ''
  /**
   * 语音唤醒词。
   *
   * ⚠️ 语义与上面几个字段**不一样**：这里传 `[]` 不是"清回默认"，而是
   * **明确不要唤醒词**（后端只去空白/去重，不补默认值）。不传 = 不动。
   */
  wake_words?: string[]
}

// 这里曾有 MarketEntry / MarketPayload / InstallResult 三个类型：搭子集市
// 的条目、集市列表响应、以及导入/安装的结果。集市与导入导出四项功能已按用户
// 要求整体剔除，类型随之删除。

export interface ProviderPreset {
  provider: string
  name: string
  base_url: string
  models: string[]
  /** 官网文档首页（「添加服务商」向导里用） */
  docs: string
  /**
   * **申请 / 创建 API Key** 的直达页（与 `docs` 分开）。
   *
   * 两者刻意不是一个字段：`docs` 是文档首页，而用户真正卡住的地方是
   * "去哪儿弄一把 Key"——把他丢到文档首页还得自己找一圈（
   * 要的就是"点一下直接进申请页"）。自定义添加的服务商没有这个链接，
   * 前端**不渲染**它的按钮（不画空壳）。
   */
  apply_url?: string
  /**
   * 新建模型时的默认上下文窗口。
   *
   * 各家的窗口差别很大（Kimi 预设只有 32K、Claude 是 200K），所以由预设
   * 逐家给出，而不是前端硬编码一个统一数字——那样要么浪费、要么饿死。
   * 缺省时前端会退回一个偏大的值（**宁可偏大**，理由见后端 `PRESETS` 的注释）。
   */
  token_limit?: number
  /**
   * 适配器类型。缺省为 `openai_compat`。
   *
   * `anthropic` 表示走原生协议而非 OpenAI 兼容网关——差别不只是请求格式：
   * 兼容网关通常不转发 `cache_control`，Anthropic 的显式 prompt caching
   * 就完全用不上了。
   */
  adapter?: string
  /** 请求是否走系统代理（默认关；需要代理访问 OpenAI 等的模型才打开） */
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
  /**
   * **永久开启且免批准**（后端硬锁，见 core 的 `skill/locked.py`）。
   *
   * 这类技能界面上**不渲染开关与权限下拉框**，只显示「默认开启」徽标 ——
   * 因为后端会拒绝关闭与改权限，画一个点了会报错的开关比不画更糟。
   *
   * 缺省（老核心没有这个字段）按"未锁定"处理：宁可多显示一个能用的开关，
   * 也不要凭空把正常技能的控制项藏起来。
   */
  locked?: boolean
  /**
   * 只提供指导正文、没有可执行动作的内置专属技能（心鉴学四技能）。
   * 界面据此标注「按线路自动」并展示归属，而不是当成一个普通工具。
   */
  instruction_only?: boolean
  /**
   * 技能**小分类**（技能页「通用技能」栏那排分类按钮按它分组）：
   * 电商 / 金融 / 营销 / 教育 / 医疗 / 科技 / 学术 / 设计 / 法律 / 人力 /
   * 办公 / 生活 / 媒体 / 系统。
   *
   * ⚠️ 与 `category` 是两个维度：`category` 说"这技能干什么"，`domain` 说"属于哪个领域"。
   * 空 = 没归类（界面归到「其它」）。第三方技能包导入时由核心从源目录分类写进来。
   */
  domain?: string
  /** 归属搭子的显示名（如「Soulmate」「Buddy Manager」），专属技能才有 */
  owner_label?: string
  /** 给用户看的一句"为什么关不掉"（界面原样展示，不二次包装） */
  locked_reason?: string
  /**
   * **上层分类**（四分类）。判定的唯一真相来源是 core 的 `skill/groups.py`，
   * 前端**不重算** —— 两边各有一套归类规则的话，改一处必然对不上。
   *
   * - `mine` 我的技能（用户上传 / AI 创建 / AI 下载）
   * - `common` 通用技能（可自选：预设的按需能力 + MCP 外部工具）
   * - `builtin` 内置技能（每个搭子默认自带，关不掉）
   * - `exclusive` 专属技能（只有归属的那个搭子能用）
   *
   * ⚠️ 与 `category`（细类：办公 / 生活 / 系统…）是**两个维度**，别混用。
   * 缺省（老核心没有这个字段）时前端按 `source` 兜底推断，不至于整页空掉。
   */
  bucket?: 'mine' | 'common' | 'builtin' | 'exclusive'
  /** 专属技能的归属搭子 id 列表（非专属为空数组） */
  owners?: string[]
}

/** 日历配置（本地 .ics 与 CalDAV 双后端） */
export interface CalendarConfig {
  /**
   * `auto` = 配了 CalDAV 就用在线、没配就用本地文件（默认，零基础用户不用配）；
   * `local` / `caldav` = 手动固定住。
   */
  mode: 'auto' | 'local' | 'caldav'
  caldav_url: string
  caldav_username: string
  /** 密码：**只写不读**。后端下发时恒为空串，真相来自 Electron 的加密存储 */
  caldav_password: string
  /** 新建日程没给结束时间时默认持续多久 */
  default_duration_minutes: number
  calendar_name: string
}

/** `/v1/calendar/test` 的返回 */
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
  /**
   * 皮肤。前三个是深浅轴，后面是成品皮肤（浅色组与深色组在设置页分组展示）。
   *
   * ⚠️ 这份列表必须与 `@shared/bridge` 的 `ThemeId` **以及后端 `AppSettings.theme`
   * 的枚举**三处一致：设置是整份提交的，任何一处少一个 id，用户选中它时保存就会失败
   * （而且报错落在校验层，界面上只看到"保存失败"）。加新皮肤时三处一起加。
   */
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
  // 这里曾有 `assistant_market_source`（搭子集市的索引地址）。集市已按用户
  // 要求整体剔除，字段随之从后端与前端类型里删除。
  agent: {
    max_iterations: number
    max_tool_calls_per_turn: number
    temperature: number
    /**
     * 另外三个采样参数。`null` 表示**这个字段根本不发**，而不是"发默认值"——
     * 不支持的厂商收到默认值同样会 400，问题在字段本身而不在取值。
     */
    top_p: number | null
    frequency_penalty: number | null
    presence_penalty: number | null
    system_prompt: string
    confirm_mode: ConfirmMode
    /** 上下文硬上限；`0` = 跟随所选模型的上下文窗口 */
    max_context_tokens: number
    /**
     * 压缩 / 规划 / 自检这些**额外调用**走哪个模型（填模型 id）；空串 =
     * 跟随当前这个对话的模型。
     *
     * 这里**刻意没有** `tool_result_max_chars`：那个"把工具结果截断"的配置项
     * 已经连同截断逻辑一起删掉了（产品要求：不许省略任何给 AI 的内容）。
     */
    utility_model_id: string
    same_tool_failure_tolerance: number
    /**
     * AI 自己发起后台群聊时，是否**自动弹出只读观察窗**（默认开）。
     *
     * 关掉它的人通常是不想被打断：观察窗不会抢焦点，但毕竟会多出一个窗口。
     * 关掉之后讨论照跑、结论照回传，只是不再自动开窗（通知里仍留着入口）。
     */
    auto_open_group_window: boolean
  }
  security: {
    allowed_dirs: string[]
    confirm_mode: ConfirmMode
    confirm_timeout_seconds: number
    redact_enabled: boolean
    audit_retention_days: number
  }
  /**
   * 语音对话模式。**全在本机生效**：识别与唤醒都跑在本机模型上，音频不出这台机器。
   *
   * ⚠️ 必须与后端 `VoiceSettings` 一一对应 —— 设置是**整份提交**的，这边少一个
   * 字段，保存时就会把后端那份值重置掉。
   */
  voice: {
    /** 唤醒词（可多个）。说了它才开始录音；识别写成同音字（搭子→大子）也能唤醒 */
    wake_words: string[]
    send_word: string
    cancel_word: string
    /*
      ⚠️ 这里曾有 `confirm_word` / `reject_word` / `revise_word`，删除。

      它们从来**没有任何代码读过**（只有面板在显示它们）。"批准高危操作 / 拒绝 /
      改计划"三个动作的实现一律走命令表 —— 见下面 `command_words` 与
      `services/voiceCommands.ts`，词是「允许执行 / 拒绝执行 / 改一下」。

      留着它们最坏的地方不是多余，而是**骗人**：面板上那三个框看起来能配，
      用户在"确认词"里填「确认」、对着弹窗说"确认"毫无反应，而真正该喊的词
      在另一个区里。删掉之后语义只剩一套，没有第二处可以配错。
    */
    /**
     * 应用启动后的语音状态：
     * - `off` 不碰麦克风（应用不在后台等待）；
     * - `global`（**默认**）只开全局监听层 —— 等「开启语音」那个词；
     * - `all` 全局层 + 全体搭子一起待命，启动后直接能喊搭子。
     *
     * ⚠️ 默认值是 `global`（产品要求"首启默认为说出指令随时开启"）。
     * 它与后端 `VoiceSettings.startup_mode` 必须一致 —— 这里写错只是注释不对，
     * 但界面上的 `?? 'off'` 那种兜底一旦跟着错，用户会看到与实际不符的状态。
     */
    startup_mode: 'off' | 'global' | 'all'
    /**
     * 全局监听层的两个指令词。**这一层优先级最高**：不管正在跟哪个搭子说话，
     * 说「关闭语音」立刻把整个语音功能关掉（回到只等「开启语音」的状态）。
     */
    enable_word: string
    disable_word: string
    /**
     * 语音命令词覆盖：动作 id → 用户改过的词。
     *
     * ⚠️ **只存改过的**，其余走 `services/voiceCommands.ts` 里的出厂默认词 ——
     * 这样前端加新命令时不需要迁移任何已有配置（否则每加一条都得给所有老用户
     * 补一遍默认值，迟早会漏）。
     */
    command_words: Record<string, string>
    /** 被停用的命令 id：不参与识别，设置面板也不再显示 */
    disabled_commands: string[]
  }
  usage: {
    currency: 'CNY' | 'USD'
    /** 每日费用软上限；超过后仅提示，不阻止发送。null = 不提示 */
    daily_budget: number | null
    retention_days: number
  }
  calendar: CalendarConfig
  memory: {
    /** 长期记忆（向量检索）。默认开启，用的是**按需下载**的内置中文模型（起不再随包） */
    long_term_enabled: boolean
    vector_top_k: number
    /** builtin = 内置中文模型（默认、离线）；api = 自定义厂商接口；ollama = 本机 Ollama */
    embedding_backend: 'builtin' | 'api' | 'ollama'
    // ---- 自定义厂商接口 ---- //
    embedding_base_url: string
    embedding_model: string
    /** 复用哪个已配置模型的密钥（推荐：密钥走托管，不落明文） */
    embedding_key_model_id: string
    /** 直接填的密钥；留空表示用上面复用那条 */
    embedding_api_key: string
    // ---- Ollama ---- //
    embedding_ollama_url: string
    embedding_ollama_model: string
    /** 以下两个已废弃，仅为兼容旧配置而保留 */
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

// --------------------------------------------------------------------------- //
// 工作区文件
// --------------------------------------------------------------------------- //
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

// --------------------------------------------------------------------------- //
// 助手（Agent 预设）
// --------------------------------------------------------------------------- //
/** 用户自定义技能的一个参数 */
export interface CustomSkillParam {
  name: string
  description: string
  required: boolean
  default: string | null
  type: 'string' | 'number' | 'boolean'
}

/**
 * 用户自定义技能（声明式）。
 *
 * 用户**不写代码**：只填"什么时候用 + 发个什么请求/跑条什么命令"。
 * `kind` 决定走哪条路。
 */
export interface CustomSkillDef {
  id: string
  name: string
  description: string
  params: CustomSkillParam[]
  /**
   * `instruction` 是**纯指导型**：不做动作，`instructions` 的内容在对话时
   * 注入 system（上传技能包里只有 SKILL.md 时就是这种）。
   */
  kind: 'http' | 'command' | 'instruction'
  url: string
  method: 'GET' | 'POST' | 'PUT' | 'DELETE'
  headers: Record<string, string>
  body_template: string
  command_template: string
  /** 仅 instruction：指导内容原文（来自 SKILL.md） */
  instructions?: string
  timeout: number
  permission_level: 'safe' | 'confirm' | 'admin'
  enabled: boolean
  /**
   * 来源格式（导入时由后端判定）：claude-skill / skill-json / cursor-mdc /
   * clinerules / agents-md / plain-md / mcp-json / script / folder / manual。
   * 界面按它显示徽标 —— 用户拿到一个技能卡时，第一件事就是想知道"这是哪种"。
   */
  source_format?: string
  /** 该技能在技能包内的子目录（空 = 包根）。落盘范围靠它区分 */
  package_root?: string
  /** 随包提供的可执行脚本（包内相对路径） */
  scripts?: string[]
  /** SKILL.md frontmatter 的 allowed-tools（仅作展示） */
  allowed_tools?: string[]
  /** 导入时产生的提示（解释器未找到、字段被截断…）—— **必须如实展示** */
  note?: string
  /**
   * 技能**小分类**（技能页「通用技能」栏那排分类按钮按它分组）：
   * 电商 / 金融 / 营销 / 教育 / 医疗 / 科技 / 学术 / 设计 / 法律 / 人力 /
   * 办公 / 生活 / 媒体 / 系统。
   *
   * ⚠️ 空 = 没归类。**带它的技能归「通用技能」栏、不带它的留在「我的技能」栏** ——
   * 「我的技能」那一栏据此过滤（见 `SkillSettings.tsx` 的 `CustomSkillsSection`）。
   */
  domain?: string
}

/** 导入结果里的**一条**：哪个技能成功了、哪个失败了、为什么。 */
export interface SkillImportEntry {
  name: string
  id?: string
  ok: boolean
  kind?: string
  source_format?: string
  /** 导入时产生的提示（如"未找到 python 解释器，暂时跑不了"） */
  note?: string
  message?: string
  /** 本机已有、内容相同 → 跳过 */
  skipped?: boolean
  /** 内容有变化 → 更新（技能文件夹扫描才有） */
  updated?: boolean
  /** 落盘的文件数 */
  files?: number
  /** 搭子包导入时标记来自哪个内嵌包 */
  pack?: string
}

/** 技能包导入/扫描的结果（上传、从链接、文件夹、扫描四条路同形）。 */
export interface SkillImportOutcome {
  ok: boolean
  installed: CustomSkillDef[]
  results: SkillImportEntry[]
  /** 技能 id → 落盘文件数 */
  unpacked: Record<string, number>
  /** 没有参与识别、但已随包保留的文件 */
  unrecognized: string[]
  /** 因路径不安全被跳过的条目 */
  skipped: string[]
  total: number
  message: string
  /** 包里识别到的 MCP 服务接入结果 */
  mcp?: Array<{ name: string; ok: boolean; message: string }>
  /** 文件夹导入时的来源路径 */
  source_path?: string
  /** 扫描命中几个条目 */
  scanned?: number
}

/** 技能文件夹（投放区）的位置。 */
export interface SkillFolderInfo {
  skills_dir: string
  inbox: string
  exists: boolean
}

/** 技能包里的一个文件（详情弹窗的"包内文件"用）。 */
export interface SkillFileEntry {
  path: string
  size: number
}

/** MCP 批量导入的结果。逐条处理，所以成功与失败是分开的两份 */
export interface McpImportResult {
  ok: boolean
  added: string[]
  errors: Array<{ name: string; message: string }>
  total: number
}

/** 助手的人格 / 记忆文件（SOUL.md、MEMORY.md） */
export interface PersonaFile {
  name: string
  exists: boolean
  size: number
  content: string
  /** 文件为空时界面显示的说明 */
  hint: string
}

export interface PersonaFilesPayload {
  files: PersonaFile[]
}

/** 人格锁的操作。clear 不需要旧密码 —— 那条路就是给"忘了密码"准备的 */
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
  /** 对话里显示的昵称（区别于 id 与 name）；留空回退用 name */
  nickname: string
  emoji: string
  /** 用户上传的头像（data URL）；空表示用 emoji */
  avatar: string
  /** 该助手的聊天背景图（data URL）；空表示跟随全局壁纸 */
  chat_background: string
  /**
   * 这个搭子**自己的一套**语音设置（产品要求"每个搭子独立一套"）。
   *
   * 唤醒词天然就是"这个搭子叫什么"（「你好小助」）。后端在读写搭子时会按名字
   * 自动补齐唤醒词，所以多数用户零配置就能用；改过的那份不会被覆盖。
   */
  voice: AppSettings['voice']
  description: string
  /**
   * 人格是否已上锁（服务端派生字段）。
   *
   * **注意：服务端不会下发哈希或盐** —— 界面只能知道"有没有锁"，
   * 校验必须回服务端做。所以这个字段是**只读**的，改它没有任何意义。
   */
  persona_locked: boolean
  system_prompt: string
  model_id: string
  temperature: number | null
  max_iterations: number | null
  max_tool_calls_per_turn: number | null
  /**
   * 思考强度档位：`'low' | 'medium' | 'high'`，`null` = 跟随全局（等于不发送该参数）。
   *
   * 产品要求群聊里"跟随每个搭子自己的设置"，所以档位挂在**搭子**上：
   * 群里每个成员按自己的来（见 `server/routes/groups.py`）。
   * 单人对话仍以会话级档位优先 —— "这一轮值不值得多想"是随对话变的判断。
   */
  reasoning_effort: string | null
  enabled_skills: string[]
  confirm_mode: ConfirmMode | null
  builtin: boolean
  sort_order: number
  /** 服务端派生的只读字段 */
  restricts_skills: boolean
  /** 白名单里当前不可用的技能（例如 MCP 未连接），界面需要提示 */
  unavailable_skills: string[]
  /**
   * 是否为**写死**的内置搭子（服务端派生，四位内置搭子
   * 名称 / 简介 / 可用能力 / 人格规则不可改、不可删）。
   *
   * 界面据此把对应输入框置灰并写明原因 —— 只靠"保存时报 409"会让用户
   * 点半天没反应，以为客户端坏了。
   */
  locked?: boolean
  /** 被写死的字段名（``name`` / ``description`` / ``enabled_skills``） */
  locked_fields?: string[]
  /** 给用户看的一句话原因（界面原样展示，不二次包装） */
  locked_reason?: string
}

export interface AssistantsPayload {
  assistants: AssistantProfile[]
  default_assistant: string
  /**
   * 旧内置搭子 id → 新 id（``office`` → ``RelationBuddy`` 之类）。
   *
   * 只给**历史记录**用：审计日志里存的仍是旧 id（我们刻意不改写历史），
   * 界面拿这张表把它显示成搭子名，否则用户会看到一串看不懂的 ``office``。
   */
  legacy_ids?: Record<string, string>
}

// --------------------------------------------------------------------------- //
// 产物预览
// --------------------------------------------------------------------------- //
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

/**
 * 会话当前的上下文占用（后端 `GET /v1/sessions/{id}/context`）。
 *
 * 数值由后端算 —— "实际会发给模型的量"要算上系统提示词、已生成的摘要与图片
 * 占的 token，前端拿消息的 usage 相加会偏小。
 */
export interface SessionContext {
  used_tokens: number
  limit_tokens: number
  remaining_tokens: number
  /** 已用 / 上限，可能大于 1（超限时） */
  ratio: number
  /** 超过这个比例后端会自动压缩历史 */
  compress_threshold: number
  /** 已生成摘要的字数；为 0 说明还没压缩过 */
  summary_chars: number
}

// --------------------------------------------------------------------------- //
// 定时任务
// --------------------------------------------------------------------------- //
/** 什么时候检查（时间轴） */
export type TaskTrigger = 'interval' | 'daily' | 'weekly'

/** 到点之后"该不该真的跑" */
export type TaskCondition = 'none' | 'url_changed' | 'file_changed'

/**
 * 这条任务是**谁建的**（服务端强制写入，界面只读）。
 *
 * 它唯一的用途是**锁定判定**：内置搭子相关的任务里，`builtin`（我们预置的）
 * 与 `agent`（这四个搭子自己在对话里建的）用户不能改 / 关 / 删，只能再找搭子协商；
 * 用户手工建的一律是 `user`，不受限。判定在服务端（`task_store.locked_for_user`），
 * 界面拿到的只是结果 `locked`，不要自己按这个字段重算一遍 —— 两套判定迟早不一致。
 */
export type TaskOrigin = 'user' | 'agent' | 'builtin'

/** 定时任务的**配置**部分（落在 settings.json 里） */
export interface ScheduledTask {
  id: string
  name: string
  prompt: string
  /** 用哪个搭子跑；空串 = 默认配置 */
  assistant_id: string
  enabled: boolean
  trigger: TaskTrigger
  /** trigger=interval 时用 */
  interval_minutes: number
  /** trigger=daily/weekly 时用，HH:MM */
  at_time: string
  /** trigger=weekly 时用，0=周一 … 6=周日 */
  weekday: number
  /**
   * trigger=interval 时用：起始时间 `YYYY-MM-DDTHH:MM`（**本机时间**）。
   *
   * 从这一刻起每隔 `interval_minutes` 分钟跑一次，到点之前一次都不跑。
   * 空串 = 从现在起算（老配置里没有这个字段，一律按空串读）。
   */
  start_at: string
  condition: TaskCondition
  /** 条件的目标：网页地址或本地文件路径 */
  condition_target: string
  /** 谁建的（服务端写；老配置里没有这个字段，后端按 `user` 读） */
  origin: TaskOrigin
  /** 跑完**不弹通知**（只留痕）。四条「全员进化」预置任务用：每周自己跑一次，结果在会话里 */
  silent: boolean
}

/**
 * 新建 / 更新任务的提交体。
 *
 * ⚠️ 刻意**不含** `origin` 与 `silent`：这两个字段决定"能不能被改"和"跑完打不打扰"，
 * 只能由服务端写（`origin` 由创建接口写死成 `user`、搭子的技能写 `agent`；
 * 更新接口一律沿用现存值）。界面把它们回传上去等于给自己发钥匙。
 */
export type ScheduledTaskDraft = Omit<ScheduledTask, 'id' | 'origin' | 'silent'>

/**
 * 列表项 = 配置 + **运行期状态**。
 *
 * 状态字段只活在核心里，所以不要把它们塞进配置对象 ——
 * 界面上它们永远是只读的展示信息。
 *
 * 其中 ``last_run_at`` 核心是**落盘**的（``<data_dir>/scheduler_state.json``）：
 * "关闭客户端期间错过的那一次要不要补跑"必须跨重启说得清（见 scheduler.py 的
 * "重启后补跑一次"），所以重启后它不再一律显示成"刚刚"。其余字段（条件基线等）
 * 仍然是重启即丢。
 */
export interface ScheduledTaskState extends ScheduledTask {
  /**
   * 用户能不能在界面上改 / 关 / 删它（**服务端算好的结论**，界面照它置灰即可）。
   *
   * 为 true 的都是内置搭子相关的任务（我们预置的四条「全员进化中 X」，
   * 以及这四个搭子自己在对话里建的）。要改只能让搭子去改 —— 所以卡片上要写一句
   * "找搭子调整"，否则用户会以为是界面坏了。
   */
  locked: boolean
  /** 上次执行的时间戳（秒）；从未跑过是 null */
  last_run_at: number | null
  running: boolean
  /** 到下一个检查点还有多少秒；未排期是 null */
  next_run_in_seconds: number | null
  /**
   * 条件基线是否已建立。
   *
   * 为 false 说明"还在等第一次检查"—— 这不是故障，而是条件触发的正常第一步
   * （它要先记住网页/文件现在的样子）。界面上必须说清，否则用户会以为坏了。
   */
  condition_ready: boolean
}

export interface TasksPayload {
  total: number
  enabled: number
  scheduler_running: boolean
  items: ScheduledTaskState[]
}

/** 输入区里待发送的附件 */
export interface PendingAttachment {
  id: string
  name: string
  size: number
  status: 'uploading' | 'ready' | 'error'
  error?: string
  /**
   * 图片和普通文件在发送时走**两条不同的通道**：
   *
   * - `file`：只把文件名与路径写进文字里，模型看不到内容；
   * - `image`：把图片本身发给模型（需要模型支持图片输入）。
   *
   * 所以必须在**添加时**就分开，而不是发送时按扩展名现猜 ——
   * 上传接口返回的 mime 才是权威的（`.png` 里装的也可能是别的东西）。
   */
  kind: 'file' | 'image'
}

// --------------------------------------------------------------------------- //
// 审计日志
// --------------------------------------------------------------------------- //
export type AuditStatus = 'ok' | 'error' | 'denied' | 'timeout'

/**
 * 留痕的**类型**。
 *
 * `skill` 是一次技能/工具调用；其余都是**实体操作**（"谁在什么时候对什么做了什么"）。
 * 两类共用同一张表（见 core 的 security/audit.py），所以实体操作的 `skill_name`
 * 是**空串** —— 界面上得靠 `action` / `detail` 才看得出发生了什么。
 */
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
  /** 留痕类型（老记录可能没有这个字段） */
  kind?: string
  /** 发起操作的搭子 id；空串表示不是搭子发起的（例如用户自己在设置页改的） */
  actor_id?: string
  /** 实体操作的动作用词（技能调用类为空串） */
  action?: string
  /** 被操作对象的 id（群 / 任务 / 会话 / 搭子…） */
  target?: string
}

export interface AuditStats {
  available: boolean
  total: number
  by_status: Record<string, number>
  /** 按类型统计。查"那会儿出了什么事"时先看它最快 */
  by_kind?: Record<string, number>
  top_skills: Array<{ skill_name: string; count: number }>
}

// --------------------------------------------------------------------------- //
// 权限确认模式
// --------------------------------------------------------------------------- //
/**
 * 有副作用的技能（写入、删除、发送）在执行前如何处理。
 *
 * - `interactive`  弹确认框等你点允许，超时按拒绝
 * - `deny`         直接拒绝，连问都不问（最安全）
 * - `auto_approve` 不弹框直接执行（**首装默认**；只覆盖「需确认」级，
 *                  admin 高危级仍会被拒 —— 只有定时任务按次放开）
 */
export type ConfirmMode = 'interactive' | 'deny' | 'auto_approve'

export interface ConfirmModeState {
  /** 全局设置里的值 */
  mode: ConfirmMode
  /** 当前助手的专属策略；null 表示跟随全局 */
  assistant_override: ConfirmMode | null
  /** 实际生效的值（助手的优先） */
  effective: ConfirmMode
}

// --------------------------------------------------------------------------- //
// 用量与费用
// --------------------------------------------------------------------------- //
export interface UsageTotals {
  prompt_tokens: number
  completion_tokens: number
  cached_tokens: number
  cache_write_tokens: number
  reasoning_tokens: number
  total_tokens: number
  calls: number
  /** 0~1；没有输入 token 时为 null（而不是 0） */
  cache_hit_rate: number | null
  /**
   * 估算费用。
   *
   * **null 表示用户没配单价**，不是"花了 0 元"。界面必须区分这两者：
   * 把"不知道"显示成"免费"会直接误导用户的成本决策。
   */
  cost: number | null
}

export interface UsageDay extends UsageTotals {
  /** YYYY-MM-DD（本地时区） */
  day: string
}

export interface UsageByModel extends UsageTotals {
  model_id: string
}

export interface UsageSummary {
  available: boolean
  /** 数据库不可用时的说明文字 */
  message?: string
  currency: string
  daily_budget: number | null
  /** 是否有模型同时填了输入价与输出价 */
  prices_configured: boolean
  window_days: number
  today: UsageTotals | null
  total: UsageTotals | null
  window: UsageTotals | null
  by_model: UsageByModel[]
  by_day: UsageDay[]
}

// --------------------------------------------------------------------------- //
// MCP
// --------------------------------------------------------------------------- //
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
  /**
   * 传输方式：`stdio` / `sse` / `streamable_http`。
   *
   * **必须参与「读取 → 编辑 → 整体保存」的往返**：漏掉它的话，
   * 用户在界面上点一下开关，服务就会被静默从远程降级成 stdio
   * （或因为远程传输必填 `url` 而直接收到 422）。
   */
  transport: string
  /** 远程传输的端点地址；stdio 时为空 */
  url: string
  /** 远程传输的自定义请求头（例如 Authorization） */
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

/**
 * 服务状态 = 完整配置 + 运行时状态。
 *
 * 后端会连 env 一起回传，界面才能做「读取 → 编辑 → 整体保存」而不丢配置。
 */
export interface McpServerStatus extends McpServerConfig {
  state: McpServerState
  message: string
  tools: McpToolInfo[]
  tool_count: number
  restarts: number
  last_error: string | null
  /** 官方 mcp SDK 未安装时为 true，界面需要给出安装指引 */
  sdk_missing: boolean
}

export interface McpPreset {
  key: string
  title: string
  description: string
  /** 依赖说明，例如「Node.js（首次使用会自动下载该包）」 */
  requires: string
  server: McpServerConfig
}

// --------------------------------------------------------------------------- //
// 搭子 / 搭子群导入
// --------------------------------------------------------------------------- //
/**
 * 导入结果里的**一条**（一个技能包、一个搭子、一个群）。
 *
 * 逐条列出而不是只给一个总的成败：一个包里可能装了 5 个技能、其中 2 个失败，
 * 只说"导入失败"用户根本不知道要改哪一个。后端也是这么返回的（见
 * `core/src/my_agent/assistants/transfer.py`）。
 */
export interface ImportResultRow {
  /** 这一条的名字（技能名 / 搭子名 / 群名） */
  name: string
  ok: boolean
  /** 失败原因，或"已存在，未重复导入"这类说明；成功且无需解释时为空 */
  message?: string
  kind?: string
  id?: string
  /** 属于哪个技能包（一个搭子包可能带多个技能包） */
  pack?: string
  /** true = 本机已有、这次没有重复导入（不是失败） */
  skipped?: boolean
}

/** 导入一个搭子包 / 搭子群包的结果 */
export interface ImportOutcome {
  ok: boolean
  action?: 'create' | 'update'
  assistant?: { id: string; name: string }
  group?: { id: string; name: string }
  /** 这次配给搭子的技能（真实技能名） */
  skills?: string[]
  /** 包里写了、但本机没有的技能名 —— 要如实告诉用户，不能吞掉 */
  skills_missing?: string[]
  results: ImportResultRow[]
}
