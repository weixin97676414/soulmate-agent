import type { ModelInfo } from '@/types'

/**
 * 设置页里"一条模型"的编辑草稿。
 *
 * 比 `ModelInfo` 多出来的字段**全是前端专用的**（测试结果、Key 的输入/掩码/脏标记），
 * 它们**绝不能**出现在提交给后端的 payload 里 —— 后端是"整份覆盖"语义，
 * 多出来的字段不会报错，只会悄悄变成配置里的垃圾。
 */
export interface Draft extends ModelInfo {
  /** 测试结果，仅前端展示 */
  testState?: { status: 'idle' | 'testing' | 'ok' | 'fail'; message?: string }
  /** 通过「保存并测试」从端点拉回来的真实模型名列表 */
  availableModels?: string[]
  /**
   * 输入框里**当前显示**的 Key 明文（挂载时从加密存储读回，之后跟随用户输入）。
   *
   * 它**永远不是脱敏预览** —— 掩码住在 `apiKeyMask` 里，只用于 placeholder。
   *
   * ⚠️ 这个字段绝不能被"服务端列表刷新"清空：用户看到的现象就是
   * "我去点了下别处，Key 自己没了"。
   */
  apiKeyInput: string
  /** 脱敏预览，**只用于输入框的 placeholder** */
  apiKeyMask: string
  /** 用户是否动过这个输入框（保存时决定要不要把它写进加密存储） */
  apiKeyDirty: boolean
  /** 用户是否**显式点了「清除密钥」**。只有它为真才允许把 Key 删掉。 */
  apiKeyCleared: boolean
  /** 是否正在显示明文（点了小眼睛并确认过） */
  apiKeyRevealed: boolean
}

/** `PUT /v1/models` 的请求体 */
export interface ModelsPayload {
  default_model: string
  models: Array<Record<string, unknown>>
}

/**
 * 把编辑草稿组装成 `PUT /v1/models` 的请求体 —— **这是唯一的字段清单来源**。
 *
 * ## 为什么必须只有一处
 *
 * 这个接口是"整份覆盖"语义：缺席的字段会被后端按默认值重置，而且**不会报错**。
 * 于是"加了字段但忘了加到这里"的表现是"界面上改完一保存就丢"。
 * 这个坑在历史上**翻过三次车**：`supports_vision`、价格三字段 + `tier` +
 * `fallback_models`、以及之后的新增字段。
 *
 * 所以：**给模型加字段时，只改这一个函数**，设置页与首启向导同时生效。
 */
export function modelPayload(list: Draft[], defaultModel: string): ModelsPayload {
  return {
    default_model: defaultModel,
    models: list.map((model) => ({
      id: model.id,
      name: model.name,
      provider: model.provider,
      adapter: model.adapter,
      base_url: model.base_url,
      // Key 的三个字段必须**配对**看（不能因为自动保存写进空内容把已配好的模型打坏）：
      // - 显式点了「清除密钥」→ 提交空 + clear_api_key=true（**唯一**能删掉密钥的路径）；
      // - 输入框有值（常驻明文）→ 直接提交它（后端存的还是同一个值）；
      // - 输入框为空、也没点清除 → unchanged=true，沿用旧 Key。
      //
      // ⚠️ **"输入框为空"本身永远不等于"删除"**。
      //
      // ⚠️ `api_key_unchanged` 刻意**不再依赖 `has_api_key`**。
      // 以前写的是 `... && model.has_api_key`：只要这个布尔因为任何原因
      // （密钥库条目缺失、注入时机、列表正在刷新）是 false，用户啥也没干、
      // 一次自动保存就会把 Key 提交成空串 —— 而后端当时把"空值且未声明 unchanged"
      // 解释成"用户要清除"，于是密钥真的没了。这就是"不知道操作了什么，
      // 密钥就被清空"的来源。现在两个方向都堵死了：**空值永远表示"没改"**。
      api_key: model.apiKeyCleared ? '' : model.apiKeyInput,
      api_key_unchanged: !model.apiKeyCleared && !model.apiKeyInput,
      clear_api_key: model.apiKeyCleared,
      // 「同步」新增的条目用它从锚点继承 Key；普通编辑恒为空
      inherit_key_from: model.inherit_key_from ?? '',
      model_name: model.model_name,
      token_limit: model.token_limit,
      supports_tools: model.supports_tools,
      supports_stream: model.supports_stream,
      supports_vision: model.supports_vision,
      supports_reasoning: model.supports_reasoning,
      use_system_proxy: model.use_system_proxy ?? false,
      timeout: model.timeout,
      temperature: model.temperature,
      max_tokens: model.max_tokens,
      enabled: model.enabled,
      is_default: model.is_default,
      tier: model.tier,
      fallback_models: model.fallback_models,
      price_input_per_1m: model.price_input_per_1m,
      price_cached_input_per_1m: model.price_cached_input_per_1m,
      price_output_per_1m: model.price_output_per_1m,
      price_input_per_1m_peak: model.price_input_per_1m_peak ?? null,
      price_output_per_1m_peak: model.price_output_per_1m_peak ?? null,
      price_cached_input_per_1m_peak: model.price_cached_input_per_1m_peak ?? null,
      peak_windows: model.peak_windows ?? [],
    })),
  }
}

/**
 * 造一份**完整**的编辑草稿（缺省值 + 你给的覆盖）。
 *
 * ⚠️ **它必须住在这个文件里**：模型字段的全部知识（提交清单 + 缺省值）归一处，
 * 别处再造第二份"我想到的那几个字段"就是这次要修的毛病本身 ——
 * 首启向导以前自己手写了一份字段表，于是**重跑一次向导**会把设置页里配过的
 * `use_system_proxy` / 高峰分时价 / `peak_windows` 静默清零。
 *
 * 缺省值的口径与后端一致（见 `ModelInfo` 上各字段的说明）：
 * 图片默认**不支持**（误判成支持的代价是整条请求被拒），思考默认**支持**
 * （只有用户主动选档位时才发字段），不降级、不预设厂商档位。
 */
export function emptyDraft(overrides: Partial<Draft> = {}): Draft {
  return {
    id: '',
    name: '',
    display_name: '',
    provider: '',
    adapter: 'openai_compat',
    base_url: '',
    api_key: '',
    has_api_key: false,
    model_name: '',
    token_limit: 131072,
    supports_tools: true,
    supports_stream: true,
    supports_vision: false,
    supports_reasoning: true,
    use_system_proxy: false,
    timeout: 120,
    temperature: 0.7,
    max_tokens: null,
    tier: 'standard',
    fallback_models: [],
    enabled: true,
    is_default: false,
    price_input_per_1m: null,
    price_cached_input_per_1m: null,
    price_output_per_1m: null,
    price_input_per_1m_peak: null,
    price_output_per_1m_peak: null,
    price_cached_input_per_1m_peak: null,
    peak_windows: [],
    // 前端专用字段（**绝不会进 payload**，见 `Draft` 的说明）
    apiKeyInput: '',
    apiKeyMask: '',
    apiKeyDirty: false,
    apiKeyCleared: false,
    apiKeyRevealed: false,
    ...overrides,
  }
}
