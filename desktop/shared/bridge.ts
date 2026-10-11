/**
 * 主进程与渲染层共享的类型与常量。
 *
 * 放在 desktop/shared 下，被 electron 与 src 两套 tsconfig 同时引用，
 * 避免 IPC 契约在两侧各写一份而逐渐漂移。
 */

export interface BackendInfo {
  port: number
  token: string
  baseUrl: string
  pid: number
  mode: 'development' | 'packaged'
}

export type BackendState = 'starting' | 'ready' | 'restarting' | 'stopped' | 'failed'

export interface BackendStatus {
  state: BackendState
  message: string
  restarts?: number
}

export interface AppInfo {
  version: string
  electronVersion: string
  chromeVersion: string
  /** 平台标识，如 win32 / darwin / linux。用 string 而非 NodeJS.Platform，
   *  避免渲染层为了一个字段引入 @types/node。 */
  platform: string
  isDev: boolean
  dataDir: string
}

/**
 * 密钥集合。
 *
 * **只存在于主进程与渲染层之间**：Python 核心既不加密也不落盘，
 * 只通过一次性临时文件接收（见 electron/secrets.ts 的说明）。
 *
 * 注意跨 IPC 到渲染层时，里面的值一律是**脱敏预览**（形如 `sk-****3f9a`），
 * 不是明文 —— 见 AgentBridge.getSecretsMasked。
 */
export interface SecretsPayload {
  /** 模型 id -> API Key（或脱敏预览） */
  models: Record<string, string>
  /** MCP 服务名 -> 该服务的密钥类环境变量（或脱敏预览） */
  mcp: Record<string, Record<string, string>>
  /**
   * 外部集成的凭据：能力名 -> 字段（目前只有 `calendar` 的 CalDAV 密码）。
   *
   * 单独一段而不是塞进 mcp：mcp 的那些键会被注入到第三方 MCP 进程的环境变量里，
   * 把日历密码放进去等于**顺手泄漏给第三方**。这一段只交给核心进程自己用。
   */
  integrations: Record<string, Record<string, string>>
}

/**
 * 增量提交的密钥。
 *
 * **合并语义**：只提交本次改动的条目。不做全量替换，是因为渲染层只掌握
 * "用户刚编辑过"的那些值——全量提交会把用户没碰过的 Key 全部抹掉。
 *
 * ## 空值语义：**忽略，不删除**（重要）
 *
 * 早先这里是"值为空字符串 = 删除"，结果是任何一次"空值被当成新值提交"
 * 都会把已配好的 Key 抹掉（自动保存时输入框恰好为空、页面刷新把输入框
 * 重建为空……都能触发），而且症状是**重启后才连不上**，极难定位。
 *
 * 现在删除必须**显式声明**：走 `removeModelIds` / `removeMcpVars`。
 * 空值一律忽略，这条路在结构上被堵死了。
 */
export interface SecretsPatch {
  /** 模型 id -> 新的明文 Key。**空字符串会被忽略**，不表示删除。 */
  models?: Record<string, string>
  /** 明确要**删除**密钥的模型 id 列表（用户点了「清除密钥」）。 */
  removeModelIds?: string[]
  /** MCP 服务名 -> 该服务的密钥类环境变量。空值同样被忽略。 */
  mcp?: Record<string, Record<string, string>>
  /** 明确要删除的 MCP 密钥条目：`{ "服务名": ["环境变量名", ...] }`。 */
  removeMcpVars?: Record<string, string[]>
  /** 外部集成凭据：`{ "calendar": { "password": "..." } }`。空值同样被忽略。 */
  integrations?: Record<string, Record<string, string>>
}

export interface SecretsStatus {
  /** 系统是否提供可用的加密能力（Windows 上为 DPAPI） */
  available: boolean
  /** 实际使用的保护方式；plaintext 时界面要给出明确警告 */
  protection: 'encrypted' | 'plaintext'
  /** 密钥文件的落盘位置，供用户排查 */
  path: string
  /** 已保存的密钥条目数 */
  count: number
}

/**
 * **用户给技能的密钥**（私钥 / API Secret…）—— 与上面的 `SecretsPayload` 无关。
 *
 * ⚠️ 两者是**两条独立链路**（不同的文件、不同的注入变量、不同的键空间）。
 * 产品要求不要动现有密钥存储逻辑；而且技术上也不该合：
 * `secrets.bin` 的结构只保留固定的三个顶层键，往里塞东西会被静默丢弃。
 *
 * 这里存的是**扁平** `名字 -> 值`，名字的字符集与核心的
 * `security/secret_ref.py::SECRET_NAME_PATTERN` **同一套**（它会出现在
 * `{{secret:名字}}` 占位符里，两边不一致会出现"存了却引用不到"）。
 */
export interface SkillSecretsPatch {
  /** 名字 -> 新值。**空值会被忽略**（不表示删除，同 `SecretsPatch` 的口径）。 */
  keys?: Record<string, string>
  /** 明确要删除的名字；**传空数组表示清空全部**（管理面板的「全部清空」）。 */
  remove?: string[]
}

/**
 * 给界面看的密钥视图。**永远不下发明文** —— 只有名字与脱敏预览。
 *
 * 这是刻意的：应用里**没有任何界面**能显示出用户给技能的密钥内容。
 * 要换一把就重新提供（覆盖同名即可）——"能看"和"能被偷看"是同一件事。
 */
export interface SkillSecretsView {
  /** 已保存的名字（排序后） */
  names: string[]
  /** 名字 -> 脱敏预览（形如 `0xDE****EEF1`） */
  masked: Record<string, string>
  /** 系统是否提供加密能力（Windows 上为 DPAPI） */
  available: boolean
  /** 实际保护方式；plaintext 时界面必须显眼警示 */
  protection: 'encrypted' | 'plaintext'
  /** 落盘位置，供用户排查 */
  path: string
}

/**
 * 皮肤 id。
 *
 * 前三个是"深浅"轴（system 表示跟随系统），后面是**成品皮肤** ——
 * 每个都是完整的一套配色，且**浅色系与深色系在设置页分组展示**
 * （产品明确要求"浅色背景和深色背景分两行"）。
 *
 * 刻意把两件事收在同一个枚举里：分成"皮肤"和"深浅"两个开关的话，
 * 用户选了深色皮肤又把深浅拨到浅色，结果就是谁也说不清该听谁的。
 */
export type ThemeId =
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

/** 旧名字，保留以免主进程与 appStore 的引用一次性改不完 */
export type WindowTheme = ThemeId

/** 这套皮肤是不是深色系（决定窗口底色与标题栏配色） */
export function isDarkTheme(theme: ThemeId): boolean {
  return (
    theme === 'dark' ||
    theme === 'forest' ||
    theme === 'ocean' ||
    theme === 'plum' ||
    theme === 'pine' ||
    theme === 'charcoal' ||
    theme === 'deepnight'
  )
}

/** 所有可选择的皮肤（供设置页渲染，避免两处各写一份） */
export const THEME_IDS: readonly ThemeId[] = [
  'light',
  'warm',
  'sakura',
  'mint',
  'sky',
  'apricot',
  'deepday',
  'dark',
  'forest',
  'ocean',
  'plum',
  'pine',
  'charcoal',
  'deepnight',
]

/** 点窗口关闭按钮时做什么 */
export type CloseAction = 'ask' | 'tray' | 'quit'

/**
 * 主进程侧的桌面偏好。
 *
 * **为什么不放后端配置**：这两项都必须在后端不可用时仍然读得到 ——
 * 关闭窗口那一刻后端可能正在退出，甚至已经挂了，而"关窗"是必须永远可用的操作。
 *
 * **为什么主题在主进程也存一份**：主题真正的来源是渲染层的 localStorage，
 * 而主进程读不到 localStorage；可窗口创建必须在那之前就知道该用什么配色，
 * 否则首帧只能是白的。主进程这份是**镜像**，渲染层每次启动都会重发，所以会自愈。
 */
export interface DesktopPrefs {
  theme: WindowTheme
  /**
   * 点关闭按钮的行为。默认 `ask`（每次询问）—— **不替用户拿主意**：
   * 点了 × 应用直接消失，零基础用户容易以为是自己弄坏了；
   * 但直接改成最小化到托盘，又会让另一部分用户找不到退出的地方。
   */
  closeAction: CloseAction
  /**
   * 选定的录音设备 id（`enumerateDevices()` 给的 `deviceId`）；空串 = 用系统默认。
   *
   * ⚠️ 为什么放主进程偏好文件、而不是后端设置（第 103 批）：麦克风是**这台机器**
   * 的属性 —— 换个后端配置或换台机器都不该跟着走；而且"上次选了哪个麦"必须在
   * **打开麦克风之前**就读得到（那一刻核心可能还没起来）。
   *
   * ⚠️ 存下来的 id 可能在下次启动时已经不存在了（蓝牙耳机拔了/换接口了）。
   * 渲染层必须**回落系统默认并说明**，绝不能拿着死 id 去 `getUserMedia` ——
   * 那会直接打不开麦克风，而用户完全看不出是"上次选的那个设备没了"。
   */
  micDeviceId?: string
}

/**
 * 关闭询问的三种结果。
 *
 * `cancel` 是必需的：用户按 Esc 或点了空白处时，期望的是"把弹窗收回去、
 * 窗口照旧开着"，而不是顺手把窗口关掉 —— 那是模态框最容易被误解的行为。
 */
export type ClosePromptResult = 'cancel' | 'tray' | 'quit'

/** 用户在应用内关闭弹窗里的选择 */
export interface ClosePromptAnswer {
  action: ClosePromptResult
  /** 是否勾选了"记住我的选择" */
  remember: boolean
}

/**
 * 要看哪一条密钥的明文。
 *
 * 只按"单条"取，不做整批下发 —— 保留"明文默认不出主进程"的约束，
 * 把可能的暴露面收窄到用户明确要看的那一条。
 */
/** 当前窗口的角色参数（由主进程通过 additionalArguments 注入，preload 解析） */
export interface WindowArgs {
  /**
   * 'main' = 主窗口；'chat' = 独立对话窗口（只显示某个搭子的对话区）；
   * 'group' = 群聊独立窗口（AI 在后台跑讨论时的观察窗，或用户手动打开的群窗口）
   */
  mode: 'main' | 'chat' | 'group'
  /** 独立窗口绑定的是哪个搭子 */
  assistantId: string
  /**
   * 群聊独立窗口绑定的是哪条**对话**（一个群可以有多条对话）。
   *
   * 空串 = 没指定，窗口进去后落到该群"最近有动静"的那条 —— 观察窗就是这样
   * （AI 在后台跑的那场讨论固定写在最近一条上，没有"选定哪条"这一说）。
   * 手动从某条对话的右键菜单打开时才会带上具体 id。
   */
  threadId: string
  /**
   * 独立窗口要**直接打开的那条会话**。
   *
   * 没有它时窗口只能自己猜（取该搭子最近一条），用户看到的就是"另开了一个新对话"，
   * 而不是"把我在看的这段对话单独拎出来"。空串 = 没有指定，沿用旧的兜底行为
   * （新建会话时后端才会真正建会话）。
   */
  sessionId: string
  /** 群聊窗口绑定的是哪个群（mode='group' 时有效） */
  groupId: string
  /**
   * 群聊窗口是否**只读**。
   *
   * 只读窗是"观察窗"：AI 在后台跑讨论时自动弹出，让用户能看着它在干什么，
   * 但不能在里面发言、也不能改群设置（那场讨论由后台运行器在跑）。
   * 手动打开的群窗口是 false（与群聊页能力完全一致）。
   */
  readonly: boolean
}

/**
 * 请求把某个产物「另存为」到用户自己选的位置。
 *
 * 渲染层只说清"要保存哪一个"（文件 id + 类型 + 建议文件名），
 * **既不给目标路径、也不碰磁盘**：
 *
 * - 系统「另存为」对话框只能在主进程弹（渲染层开着沙箱）；
 * - 落盘的字节由**主进程**自己去核心取（它本来就持有核心地址与本地令牌），
 *   这样几十 MB 的产物不必走 IPC 传一遍，也不多占一份内存；
 * - 渲染层是本项目明确的不可信边界（它要渲染模型输出与上传文件），
 *   把"写到任意路径"的能力开在它身上等于绕过这个边界。
 */
export interface SaveArtifactRequest {
  /** 产物在核心里的文件 id（可能就是带中文的文件名，见 core/storage/files.py） */
  fileId: string
  kind: 'upload' | 'artifact'
  /** 预填进对话框的文件名，通常就是原始文件名 */
  suggestedName: string
  /** 由核心给的 MIME；主进程按它推导对话框的文件类型筛选 */
  mime?: string
}

/**
 * 「另存为」的结果。
 *
 * `cancelled` 与 `ok: false` 是**两件事**：用户点取消什么错都没有，界面必须静默；
 * 只有真的写失败才该报错 —— 把取消当失败报一遍，是最惹人烦的那种提示。
 */
export interface SaveArtifactResult {
  ok: boolean
  cancelled?: boolean
  /** 成功时写到的完整路径（用于提示"已保存到 …"） */
  path?: string
  /** 失败原因（人话，直接展示） */
  error?: string
}

export interface RevealTarget {
  /** 模型 id */
  modelId?: string
  /** 或者：MCP 服务名 + 其中某个环境变量名 */
  mcpServer?: string
  mcpVar?: string
  /** 或者：外部集成名（如 `calendar`）+ 字段名（如 `password`） */
  integration?: string
  integrationField?: string
}

// --------------------------------------------------------------------------- //
// 账号 / 充值
//
// 全部逻辑在主进程（见 desktop/electron/account/**），渲染层只拿**不含凭据**的快照。
// device_secret / session_token 永不过 IPC：渲染层在本项目里是明确的不可信边界
// （见 electron/secrets.ts 的说明），而这两个值一旦泄漏就等于账号被完全接管。
// --------------------------------------------------------------------------- //

/** 线路：两条线行为完全一致，只有入口不同（文档 §2） */
export type AccountLine = 'cn' | 'seoul'

/**
 * 本设备绑定过的一个账号。
 *
 * 字段直接对应后端下发（文档 §5.3 / §5.6），**不做重命名**：这类跨端契约一旦
 * 两边各起一套名字，排查时就得在脑子里做一次翻译，而账目/余额恰恰是最不敢猜的地方。
 *
 * 带 `?` 的是只有一个接口才给的字段，别拿它当"这个值一定是空"来用。
 */
export interface AccountUser {
  id: number
  account: string
  /** 已设过密码。false 时本机（自动创建的那个）可以空密码进入 */
  has_password: boolean
  /** 我的邀请码（可复制给别人） */
  my_invite_code: string
  /** 是否已经补填过邀请码（只可补一次） */
  invite_bound: boolean
  /** 6 位小数字符串，如 "0.000000"。**界面不要用浮点直接算** */
  token_balance: string
  /** TRC20 充值地址；为空表示后端暂时取不到，不是错误（走补偿流程） */
  tron_address: string
  created_at: string
  /** 仅 /account/lookup 会给 */
  is_primary?: boolean
  last_used_at?: string
  /** 仅 /account 会给；null = 没绑过邀请码 */
  inviter_masked?: string | null
}

/** 线路探测结论（文档 §6.3） */
export interface AccountLineState {
  preferred: AccountLine
  /** 线路 -> 最近一次测得的中位延迟（毫秒）；null = 那一侧不通 */
  measurements: Record<string, number | null>
  /** 结论产出的时间（毫秒）。超过 24 小时要重测（文档 §6.4） */
  updatedAt: number
  /**
   * 是不是用户手动选的。
   *
   * 手动选过之后**只有它彻底连不上**才会自动切走（切走时会写明原因）——
   * 否则"我明明选了首尔，它自己又跑回大陆了"会让人觉得开关是坏的。
   */
  manual: boolean
}

/**
 * 首启状态机（文档 §6.1）对外的那一面。
 *
 * `offline` 与 `deviceUsable` 是**两个独立的开关**：前者随时会恢复，后者不会
 * （设备都认不出来，再重试一万次也一样，所以界面要直接说"账号功能暂不可用"）。
 */
export type AccountPhase =
  | 'idle'
  | 'checking-network'
  | 'probing-line'
  | 'lookup'
  | 'register'
  | 'ready'
  | 'offline'
  | 'device-unusable'
  | 'error'

/** 给界面渲染权益页的全部信息（不含任何凭据，也不需要凭据） */
export interface AccountSnapshot {
  phase: AccountPhase
  /** 状态行文案：进度说明或失败原因（后端 error 原文，不二次改写） */
  message: string
  /** false = 这台机器认不出设备，账号功能不可用，**且不再重试** */
  deviceUsable: boolean
  /** true = 未联网，需要联网的按钮要置灰（但页面仍可进入，看得到原因） */
  offline: boolean
  /** 是否需要弹「部分功能需要联网才能使用」（渲染层弹完回 answerOffline） */
  offlinePrompt: boolean
  /** 本设备绑定过的全部账号 */
  accounts: AccountUser[]
  /** 当前账号 id；没有账号时为 null */
  currentId: number | null
  /** 是否持有 device_secret（**只给布尔，不给值**）——改密/改名要靠它签名 */
  hasDeviceSecret: boolean
  /** 是否持有会话 token */
  loggedIn: boolean
  /** 1 USDT = N Token；取后端 /rate，不写死 */
  rate: number | null
  line: AccountLineState | null
  /** 是否正在盯充值（盯单期间每 pollSeconds 拉一次余额） */
  watching: boolean
  /** 本次盯单窗口还剩多少秒 */
  watchSecondsLeft: number
  /**
   * 最近一次**检测到余额变大**的时间（毫秒）。
   *
   * 给界面做"到账闪一下"用：轮询是主进程在做的，渲染层只订阅快照，
   * 没有这个时间戳就只能靠 diff 猜"是哪一次更新导致余额变了"。
   */
  balanceIncreasedAt: number | null
  /** 佣金（可提现）+ 提现记录。按线路只展示对应那一类（cn → rmb / seoul → usdt） */
  commission: AccountCommission | null
  /**
   * 上次拉佣金**失败的原因**（空串 = 最近一次是成功的）。
   *
   * 佣金取不到时界面必须有话说：原先引擎把异常吞掉，界面只剩一张空卡片，
   * 用户反复点刷新也看不出是什么问题（"返佣刷新不生效"这条缺陷的本质）。
   */
  commissionError: string
  /** 当前微信订单（大陆）；没有未完成订单时为 null */
  wxOrder: WxOrderState | null
  /**
   * PayPal 渠道配置（首尔线路）。**数值全部来自服务端**（单价 / 上下限 / currency），
   * 界面只负责按它渲染与试算 —— 写死就意味着后端调价后界面还在按旧价收钱。
   */
  paypalConfig: PayPalConfig | null
  /** 当前 PayPal 订单（首尔）；没有进行中的结账时为 null */
  paypalOrder: PayPalOrderState | null
  /**
   * PayPal 最近一次的提示（按文档 §3 的错误码对照由主进程裁决，界面只画颜色）。
   *
   * 与动作返回值分开放快照里，是因为**轮询结果也必须有回音**：结账在独立窗口完成，
   * 用户看不到主界面在做什么，只有"已到账 / 已过期 / 请重新发起"这类提示能告诉他进展。
   */
  paypalNotice: PayPalNotice | null
}

// --------------------------------------------------------------------------- //
// 支付 / 返佣 / 提现（《微信支付接入文档》v1.0）
// --------------------------------------------------------------------------- //

/** 微信订单状态（文档 §3.2） */
export type WxOrderStatus = 'CREATING' | 'NOTPAY' | 'SUCCESS' | 'CLOSED' | 'FAIL'

/** 一条提现记录（文档 §6.1）。amount 是实发净额，gross_amount 是原额。 */
export interface WithdrawalRecord {
  id: number
  amount: string
  gross_amount?: string
  fee?: string
  method?: string
  status: 'pending' | 'done' | 'rejected'
  admin_note: string | null
  created_at: string
  reviewed_at?: string | null
}

/** 人民币佣金（大陆线路） */
export interface RmbCommission {
  withdrawable: string
  total: string
  withdrawn: string
  /** 手续费率（如 0.03 = 3%） */
  fee_rate: number
  /** 返佣比例（如 0.2 = 20%） */
  commission_rate: number
  /** 各收款方式是否已填过（首次提现时后端要求带上） */
  payee_ready: Record<string, boolean>
  withdrawals: WithdrawalRecord[]
}

/** USDT 佣金（国际线路） */
export interface UsdtCommission {
  withdrawable: string
  total: string
  withdrawn: string
  /** 固定手续费（USDT/次） */
  fee_fixed: number
  commission_rate: number
  withdrawals: WithdrawalRecord[]
}

/** 佣金全量（文档 §6.1：两类都返回，客户端按线路只展示对应那一类） */
export interface AccountCommission {
  region: AccountLine
  rmb: RmbCommission
  usdt: UsdtCommission
}

/**
 * 当前微信订单（大陆线路）。
 *
 * 它是**运行态**，不进 account.json：客户端重启后"上一单"就丢了，由后端
 * 按 order_no 兜底（查单 404 时当作过期、重新下单）。
 */
export interface WxOrderState {
  order_no: string
  amount_yuan: number
  token_amount: string
  status: WxOrderStatus
  /** 二维码内容（微信 code_url 原文，本地生成二维码用） */
  code_url: string
  /** 离过期还剩多少秒 */
  countdown_seconds: number
}

/**
 * 动作类调用的返回。
 *
 * 为什么错误不放进快照：每个弹窗（改密 / 改名 / 补邀请码…）要把**自己这一条**
 * 错误显示在自己旁边，而快照是全局共享的 —— 放进快照会让"改密失败"的提示
 * 跑到别的卡片上去，也会在弹窗关掉之后残留。
 */
export interface AccountActionResult {
  ok: boolean
  /** 失败原因（后端 error 原文，直接展示） */
  error?: string
  /** 忘记密码自动重置被拒时的**人工重置**指引（文档 §5.11） */
  manualReset?: { email: string; require: string }
  snapshot: AccountSnapshot
}

/**
 * 兑换码的结果。
 *
 * 与 `AccountActionResult` 分开，是因为它要带一句**成功文案**
 * ——后端返回的"充值成功，获得 60 Token"必须原样显示给用户
 * （只回一个 `ok:true` 的话，界面只能自己编一句，而它不知道充了多少）。
 */
export interface RedeemOutcome {
  ok: boolean
  /** 成功时的后端文案；失败时为空串 */
  message: string
  /** 失败原因（后端 error 原文，直接展示，不要改写） */
  error: string
  snapshot: AccountSnapshot
}

// --------------------------------------------------------------------------- //
// PayPal 充值（首尔线路专有，见 desktop/electron/account/api.ts 的说明）
// --------------------------------------------------------------------------- //

/** PayPal 渠道配置。数值一律服务端下发（不写死）。 */
export interface PayPalConfig {
  /** 每份到账 Token 数（服务端字段 unit_tokens 映射而来，见 api.ts） */
  unit_price: number
  /**
   * 每份美元单价（服务端字段 unit_usd）。
   *
   * 为什么单独要它：「数量」的单位是**份**，应付美元 = 份数 × unit_usd ——
   * 以前把数量直接当美元金额，是靠"1 份恰好 = 1 USD"的巧合成立的；
   * 服务端字段一分开（unit_tokens / unit_usd），这个巧合就不再成立，
   * 必须各自用各自的字段算，否则会出现"到账对、应付错"的账目偏差。
   */
  unit_usd: number
  /** 单次可购数量下限（服务端缺失时主进程补 1） */
  min: number
  /** 单次可购数量上限（服务端缺失时主进程补 100） */
  max: number
  /** PayPal 前端 SDK 的 client_id */
  client_id: string
  /** 运行模式，如 sandbox / live */
  mode: string
  currency: string
}

/** PayPal 订单状态（由后端 status 字符串归一化而来）。 */
export type PayPalOrderStatus = 'PENDING' | 'PAID' | 'EXPIRED' | 'CANCELLED' | 'FAILED'

/**
 * 当前 PayPal 结账（运行态，不进 account.json）。
 *
 * ⚠️ 标识是 `ct`（服务端签发的一次性结账令牌），**不是** `order_id`：方案 B 里
 * 客户端只调 `/paypal/session` 拿 ct，订单号由结账页内部创建，客户端根本看不到。
 * ct 只留在主进程，这里带上它只是为了"同一份快照能自洽"，界面不展示、不外传。
 */
export interface PayPalOrderState {
  ct: string
  /** 购买份数 */
  quantity: number
  status: PayPalOrderStatus
  /** 离结账窗口失效还剩多少秒 */
  countdown_seconds: number
  /** 结账窗口总时长（秒）。由服务端 `expires_in` 下发，界面用来说明"窗口多久内有效" */
  expires_seconds: number
}

/** 提示配色。由主进程按文档 §3 的错误码对照裁决，界面不自己猜。 */
export type PayPalNoticeTone = 'warning' | 'danger' | 'success'

export interface PayPalNotice {
  tone: PayPalNoticeTone
  /** 人话文案，直接展示 */
  message: string
}

export interface PayPalResult {
  ok: boolean
  /** 失败原因（后端原文，直接展示） */
  error?: string
  /** 按文档 §3 对照出的提示（取配置 / 下单失败时给出） */
  notice?: PayPalNotice
  snapshot: AccountSnapshot
}

export interface AgentBridge {
  getBackendInfo: () => Promise<BackendInfo>
  getBackendStatus: () => Promise<BackendStatus>
  restartBackend: () => Promise<BackendInfo>
  getBackendLogs: () => Promise<string[]>
  getAppInfo: () => Promise<AppInfo>
  setTitleBarTheme: (theme: WindowTheme) => void
  /** 自绘标题栏的窗口控制按钮（壁纸铺满标题栏后，系统 overlay 按钮被移除） */
  minimizeWindow: () => void
  toggleMaximizeWindow: () => void
  /**
   * 把窗口**恢复成默认大小**（产品要求）。
   *
   * ⚠️ 这与 `toggleMaximizeWindow` 里那个"还原"**不是一回事**，别合并：
   * - `toggleMaximizeWindow` 的"还原"= 最大化 ↔ 上一档普通尺寸（Windows 惯例）；
   * - 这个 = **不管现在多大/是不是最大化，一律回到出厂默认 1366×768**。
   *
   * 用户的原话是"点击后界面长宽恢复默认"，所以这里是"复位"而不是"反向操作"。
   * 主进程会先 `unmaximize()` 再设尺寸（否则在最大化状态下设尺寸不生效），
   * 并在屏幕装不下时按工作区夹小。
   */
  resetWindowSize: () => void
  closeWindow: () => void
  /**
   * 按增量改窗口宽度（正数变宽、负数变窄）。
   *
   * 侧栏收起/展开时调它 —— 收起侧栏要**整体收窄窗口**，而不是把腾出的宽度
   * 让给对话栏（产品要求）。最大化的窗口会被主进程忽略。
   */
  resizeWindowBy: (deltaWidth: number) => void
  /**
   * `resizeWindowBy` 的**同步**版：等主进程真的改完窗口宽度才返回。
   *
   * ## 为什么非要有同步版（而不是都用异步的）
   *
   * 「链路与产物」抽屉是**窗口向外长出来的一块**，所以打开时要"窗口先变宽、
   * 抽屉再出现"。用异步版做不到这个顺序 —— `useEffect` 里发 `send` 之后
   * 抽屉 DOM 已经渲染了，而窗口还没变宽，中间隔着一到三次 IPC 往返
   * （实测 1~3 帧）。这几帧里对话栏被硬挤 288px、内容整体重排，然后窗口才变宽
   * 把宽度还回去 —— 用户看到的就是**打开/收回时整个客户端闪一下**
   * （反馈）。
   *
   * 同步版把"窗口变宽"提前到**浏览器绘制之前**（配合渲染层的 `useLayoutEffect`），
   * 于是窗口宽度与抽屉 DOM 落在同一帧里，中间态根本不会被画出来。
   *
   * 代价是**阻塞渲染进程**：主进程处理这个 IPC 期间界面不动。所以它只给
   * 这一处用（`setBounds` 是原生调用，耗时在亚毫秒级），**侧栏收起/展开仍走异步版**
   * —— 那边没有"必须先变宽再渲染"的顺序要求，不该白担这个风险。
   *
   * 返回是否真的改了窗口（最大化/全屏、或已顶到屏幕右边界时为 `false`）。
   */
  resizeWindowBySync: (deltaWidth: number) => boolean
  /** 当前窗口的角色参数（主窗口 / 独立对话窗口 + 绑定搭子） */
  getWindowArgs: () => WindowArgs
  /** 打开（或聚焦）某个搭子的独立对话窗口；给了 sessionId 就直接开那一条会话 */
  openChatWindow: (assistantId: string, sessionId?: string) => void
  /**
   * 打开（或聚焦）某个群的独立窗口。
   *
   * `observing = true` 是**只读观察窗**（AI 在后台跑讨论时自动弹出的那个）：
   * 只能看，不能发言。手动从群聊列表打开时传 false —— 与群聊页能力一致。
   */
  openGroupWindow: (groupId: string, observing?: boolean, threadId?: string) => void
  pickDirectory: () => Promise<string | null>
  /**
   * 弹系统「选择文件」对话框，返回选中文件的**绝对路径**（用户取消返回 null）。
   *
   * 与 `pickDirectory` 同一族（dialog → 主进程 → 绝对路径），新增（43 → 44）。
   * 为什么非有它不可：自动化任务的「文件有更新才执行」要求填**完整路径**，而普通用户
   * 不会自己去文件属性里复制路径 —— 文档里写"例如 D:\报告\月度.xlsx"也帮不上忙。
   * 手动输入**照旧保留**：愿意粘贴路径的用户不该被强制走对话框。
   */
  pickFile: () => Promise<string | null>
  /**
   * 弹系统「另存为」对话框并把产物写到用户选的位置。
   *
   * 这是**唯一**一条与"产物"相关的 IPC 通道（新增，42 → 43）。
   * 在此之前渲染层只能把 Blob 塞进 `<a download>`，落到浏览器默认下载目录 ——
   * 用户没法自己选保存到哪里（而"另存为"这个名字承诺的正是这件事）。
   */
  saveArtifactAs: (payload: SaveArtifactRequest) => Promise<SaveArtifactResult>
  openPath: (target: string) => Promise<boolean>
  openExternal: (url: string) => Promise<boolean>
  onBackendStatus: (callback: (status: BackendStatus) => void) => () => void

  // ---- 关闭询问（主进程 <-> 界面往返）---- //
  /**
   * 订阅「主进程要求界面弹出关闭询问」。
   *
   * 与 `onBackendStatus` 一样返回退订函数 —— React 严格模式会让 effect 跑两次，
   * 不退订就会叠出两个弹窗。
   */
  onClosePrompt: (callback: () => void) => () => void
  /** 回传用户在应用内关闭弹窗里的选择 */
  answerClosePrompt: (answer: ClosePromptAnswer) => void

  // ---- 桌面偏好（主进程侧）---- //
  getDesktopPrefs: () => Promise<DesktopPrefs>
  setDesktopPrefs: (patch: Partial<DesktopPrefs>) => Promise<DesktopPrefs>

  // ---- 密钥（safeStorage / DPAPI）---- //
  /**
   * 取密钥的**脱敏预览**（形如 `sk-****3f9a`）。**永不下发明文。**
   *
   * 设置页并不需要明文就能工作：编辑走 `saveSecrets` 的增量合并语义，
   * 用户没碰过的条目原样保留。所以没有理由把全部 Key 一次性交给渲染层 ——
   * 渲染层是要渲染模型输出、Markdown 和上传文件的不可信边界。
   */
  getSecretsMasked: () => Promise<SecretsPayload>
  saveSecrets: (patch: SecretsPatch) => Promise<SecretsStatus>
  getSecretsStatus: () => Promise<SecretsStatus>
  /**
   * 取**某一条**密钥的明文，供用户点"小眼睛"时查看。
   *
   * 这是刻意开的一个窄口子：上一版连这个入口都没有（明文永不出主进程）。
   * 但用户确实会需要——换了 Key 之后想核对一下自己粘进去的是不是完整、
   * 有没有多带空格。**看之前界面会先弹一次确认**，并且每次取用都记一条日志。
   *
   * 取不到（没配过、或 id 不存在）返回空串，不抛异常：这只是个展示功能。
   */
  revealSecret: (target: RevealTarget) => Promise<string>

  // ---- 用户给技能的密钥（独立于上面的密钥库）---- //
  /**
   * 取**名字 + 脱敏预览**。⚠️ 这里**没有** reveal：私钥不像 API Key 那样
   * "用户会想核对粘全了没有" —— 它通常是从别处一键复制来的，
   * 而没有查看入口本身就是一层保护。
   */
  getSkillSecrets: () => Promise<SkillSecretsView>
  /**
   * 保存用户提供的密钥（合并语义，空值忽略；删除走 `remove`）。
   *
   * ⚠️ 这条路径是**唯一**能写入这类密钥的入口，而且它**不经过聊天链路** ——
   * 这正是"AI 看不到明文"的实现方式（见 `electron/skill-secrets.ts`）。
   * 主进程写盘成功后会顺带把新内容推给核心（热更新），所以用户粘贴完
   * 立刻就能被 `{{secret:名字}}` 引用到，不需要重启。
   */
  saveSkillSecrets: (patch: SkillSecretsPatch) => Promise<SkillSecretsView>
  /** 删除（`names` 传空数组 = 清空全部）。这是**唯一**会让条目消失的入口。 */
  removeSkillSecrets: (names: string[]) => Promise<SkillSecretsView>
  /** 状态查询（供管理面板显示加密状态）。与 `getSkillSecrets` 同源，单独一条是为了语义清楚。 */
  getSkillSecretsStatus: () => Promise<SkillSecretsView>

  // ---- 账号 / 充值（主进程持有凭据，渲染层只看快照）---- //
  /** 取当前快照（进权益页时拉一次即可，平时靠 onAccountChanged 推） */
  getAccountSnapshot: () => Promise<AccountSnapshot>
  /** 完整性补偿（文档 §6.4）：缺地址 / 缺费率 / 线路过期 / 有待重试动作时补齐它 */
  refreshAccount: () => Promise<AccountSnapshot>
  /** 手动切换线路（写进本地结论，之后只有它彻底连不上才会自动切走） */
  setAccountLine: (line: AccountLine) => Promise<AccountSnapshot>
  /** 重新测速：无视 24 小时有效期，强制重跑一次完整探测 */
  reprobeAccountLine: () => Promise<AccountSnapshot>
  /** 登录**其他**账号（不在本机列表里的那个）：账号 + 密码，不支持空密码 */
  loginAccount: (account: string, password: string) => Promise<AccountActionResult>
  /**
   * 切到本机列表里的某个账号。
   *
   * 只有「本机自动创建、且没设过密码」的那个可以空密码进入（文档 §5.5），
   * 其余必须给密码 —— 这条规则在后端，界面照它的报错提示即可，不在这里猜。
   */
  switchAccount: (id: number, password: string) => Promise<AccountActionResult>
  /** 改账号名（3–32 位字母数字下划线；已设密码时后端要密码） */
  renameAccount: (name: string, password: string) => Promise<AccountActionResult>
  /** 设 / 改密码（**设备签名**路径；首次设置不需要旧密码） */
  setAccountPassword: (next: string, old: string) => Promise<AccountActionResult>
  /** 忘记密码：设备指纹匹配则重置，不匹配返回人工重置指引（文档 §5.11） */
  recoverAccount: (account: string, next: string) => Promise<AccountActionResult>
  /** 补填邀请码（只成功一次；填官方码 XJX 得 20，其他有效码得 30） */
  submitInviteCode: (code: string) => Promise<AccountActionResult>
  /** 开始盯充值（文档 §8）：之后主进程按后端给的节奏轮询余额 */
  watchRecharge: () => Promise<AccountActionResult>
  /** 离开充值区时停掉盯单循环，别让它在用户看不见的地方一直打接口 */
  stopRechargeWatch: () => Promise<AccountSnapshot>

  // ---- 支付 / 返佣 / 提现（《微信支付接入文档》v1.0）---- //
  /** 拉一次佣金余额与提现记录（`/commission/me`），结果推进快照 */
  getAccountCommission: () => Promise<AccountActionResult>
  /**
   * 兑换码充值 Token（一次性核销，**失败不自动重试**）。
   *
   * 成功后余额由主进程直接写进快照（后端把新余额一并返回了），界面不用再拉一次。
   */
  redeemCode: (code: string) => Promise<RedeemOutcome>
  /** 微信下单（大陆）：`amount_yuan` 是整数元。成功后主进程开始轮询查单 */
  createWxRecharge: (amountYuan: number) => Promise<AccountActionResult>
  /** 取消当前微信订单的轮询（用户点「重新生成」或离开时） */
  cancelWxRecharge: () => Promise<AccountSnapshot>
  /**
   * 取 PayPal 渠道配置（单价 / 数量上下限 / client_id / mode）。
   *
   * 只在首尔线路可用；大陆线路直接返回 `forbidden`（线路闸在主进程，界面无法绕过）。
   */
  getPaypalConfig: () => Promise<PayPalResult>
  /**
   * 发起 PayPal 结账：主进程下单、开一个独立的结账窗口、并开始每 3 秒查单。
   *
   * `quantity` 是**购买份数**，主进程会按服务端下发的 min–max 夹紧后再发给后端。
   */
  createPaypalCheckout: (quantity: number) => Promise<PayPalResult>
  /** 取消当前 PayPal 结账（关窗 + 停轮询），语义与 cancelWxRecharge 一致。 */
  cancelPaypalCheckout: () => Promise<AccountSnapshot>
  /**
   * 清掉当前 PayPal 提示（改数量 / 重新下单之前）。
   *
   * 提示是"上一次动作的结论"，与当前输入无关：不清掉的话，用户把数量改到合法区间后
   * 上一条红字还挂着，看起来像"改完还是错的"。界面在数量变更与下单入口各调一次。
   */
  dismissPaypalNotice: () => Promise<AccountSnapshot>
  /**
   * 人民币提现（大陆）：3% 手续费。
   *
   * 收款口径（清单 §5.2）：**支付宝号 或 银行卡号，填一个即可**。渲染层只交两个字符串，
   * 由主进程按「支付宝优先、否则银行卡」推导后端 `method`；两个都没填且账号里也没存过，
   * 才报「请先填写支付宝账号或银行卡号（有一个即可）」。
   */
  withdrawRmb: (payload: {
    amount: number
    zhifubao: string
    bank: string
  }) => Promise<AccountActionResult>
  /** USDT 提现（国际）：固定 1 USDT/次，`trc20_address` 需 T 开头 34 位 */
  withdrawUsdt: (payload: { amount: number; trc20_address: string }) => Promise<AccountActionResult>
  /**
   * 回传用户对「部分功能需要联网才能使用」弹窗的选择。
   *
   * `continue` = 继续用离线界面，并保持每 60 秒静默重试；
   * `skip` = 本次运行不再检测（否则每 60 秒弹一次，用户会疯）。
   */
  answerOfflinePrompt: (mode: 'continue' | 'skip') => Promise<void>
  /**
   * 订阅账号快照变化。与 onBackendStatus 一样返回退订函数。
   *
   * 只推**完整快照**，不推增量：渲染层靠自己拼状态时，任何一次丢事件都会
   * 留下一个永远歪掉的界面，而这种 bug 只在用户机器上偶发。
   */
  onAccountChanged: (callback: (snapshot: AccountSnapshot) => void) => () => void
}

/**
 * IPC 通道名集中管理，防止两端字符串写错却无法被类型系统发现。
 *
 * ⚠️ 这份常量只能被**主进程**（electron/main.ts）与渲染层的类型引用。
 * preload.ts **不能**从这里做值导入 —— 渲染进程开着沙箱，而沙箱化 preload
 * 无法 require 相对路径的文件，产物里一旦出现那条 require，preload 就会在
 * 注入 contextBridge 之前抛错，`window.agentBridge` 整个不存在，界面全废。
 *
 * preload 侧因此内联了一份同名常量；两份由 verify-packaged-app.mjs 比对。
 */
export const IPC = {
  backendInfo: 'backend:info',
  backendStatus: 'backend:status',
  backendStatusEvent: 'backend:status-event',
  backendRestart: 'backend:restart',
  backendLogs: 'backend:logs',
  appInfo: 'app:info',
  titleBarTheme: 'window:titlebar-theme',
  closePrompt: 'window:close-prompt',
  closeAnswer: 'window:close-answer',
  windowMinimize: 'window:minimize',
  windowToggleMaximize: 'window:toggle-maximize',
  /** 恢复出厂默认大小（见 `AgentBridge.resetWindowSize`） */
  windowResetSize: 'window:reset-size',
  windowClose: 'window:close',
  /** 按增量改窗口宽度（侧栏收起/展开时用） */
  windowResizeBy: 'window:resize-by',
  /** 同步版（见 AgentBridge.resizeWindowBySync：「链路与产物」抽屉用） */
  windowResizeBySync: 'window:resize-by-sync',
  openChatWindow: 'window:open-chat',
  openGroupWindow: 'window:open-group',
  pickDirectory: 'dialog:pick-directory',
  /** 系统「选择文件」对话框（见 AgentBridge.pickFile） */
  pickFile: 'dialog:pick-file',
  /** 系统「另存为」对话框 + 落盘（见 AgentBridge.saveArtifactAs） */
  saveFile: 'dialog:save-file',
  openPath: 'shell:open-path',
  openExternal: 'shell:open-external',
  desktopPrefsGet: 'desktop:prefs-get',
  desktopPrefsSet: 'desktop:prefs-set',
  secretsMasked: 'secrets:masked',
  secretsSave: 'secrets:save',
  secretsStatus: 'secrets:status',
  secretsReveal: 'secrets:reveal',
  /**
   * 用户给技能的密钥（独立的一份文件与键空间）。
   * ⚠️ 这四条**必须**与 `electron/preload.ts` 里那份逐项一致 ——
   * 打包闸会比对两侧通道名，漏一边直接红。
   *
   * ⚠️ 前缀写 `skillsecrets` 而**不是** `skill-secrets`：闸的通道名正则是
   * `[a-z0-9]+:[a-z0-9-]+`，冒号**前**不允许连字符 —— 写成带连字符的版本会
   * 被静默漏掉，于是这四条**没有被任何断言守着**（实测踩到：加了 4 条，
   * 闸报的通道数还是 52）。宁可名字丑一点，也要让闸看得见。
   */
  skillSecretsGet: 'skillsecrets:get',
  skillSecretsSave: 'skillsecrets:save',
  skillSecretsRemove: 'skillsecrets:remove',
  skillSecretsStatus: 'skillsecrets:status',
  accountSnapshot: 'account:snapshot',
  accountRefresh: 'account:refresh',
  accountLineSet: 'account:line-set',
  accountLineReprobe: 'account:line-reprobe',
  accountLogin: 'account:login',
  accountSwitch: 'account:switch',
  accountRename: 'account:rename',
  accountSetPassword: 'account:set-password',
  accountRecover: 'account:recover',
  accountInvite: 'account:invite',
  accountWatch: 'account:watch',
  accountWatchStop: 'account:watch-stop',
  accountOfflineAnswer: 'account:offline-answer',
  accountCommission: 'account:commission',
  accountRedeem: 'account:redeem',
  accountWxCreate: 'account:wx-create',
  accountWxCancel: 'account:wx-cancel',
  accountPaypalConfig: 'account:paypal-config',
  accountPaypalCreate: 'account:paypal-create',
  accountPaypalCancel: 'account:paypal-cancel',
  accountPaypalDismiss: 'account:paypal-dismiss',
  accountWithdrawRmb: 'account:withdraw-rmb',
  accountWithdrawUsdt: 'account:withdraw-usdt',
  accountChangedEvent: 'account:changed',
} as const
