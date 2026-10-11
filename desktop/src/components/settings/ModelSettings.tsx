import clsx from 'clsx'
import {
  Check,
  Coins,
  Copy,
  ExternalLink,
  Loader2,
  Plus,
  RefreshCw,
  Trash2,
  X,
  Zap,
} from 'lucide-react'
import { useEffect, useRef, useState } from 'react'

import { filterDiscoveredModels } from '@/components/settings/ModelPickerField'
import { ModelWizard } from '@/components/settings/ModelWizard'
import { type Draft, modelPayload } from '@/components/settings/modelPayload'
import { Badge, Button, Field, Input, Modal, Select, Switch } from '@/components/ui'
import type { ModelTestOutcome } from '@/services/api'
import { useAppStore } from '@/stores/appStore'
import { useNotificationStore } from '@/stores/notificationStore'
import type { ModelInfo, ProviderPreset } from '@/types'

function newModelFromPreset(preset: ProviderPreset, existing: Draft[]): Draft {
  const modelName = preset.models[0] ?? ''
  let index = 1
  let id = `${preset.provider}-${index}`
  while (existing.some((model) => model.id === id)) {
    index += 1
    id = `${preset.provider}-${index}`
  }
  return {
    id,
    name: preset.name,
    display_name: preset.name,
    provider: preset.provider,
    // 预设可以指定原生协议（目前只有 Anthropic）；缺省走 OpenAI 兼容
    adapter: preset.adapter ?? 'openai_compat',
    base_url: preset.base_url,
    api_key: '',
    has_api_key: false,
    apiKeyInput: '',
    apiKeyMask: '',
    apiKeyDirty: false,
    apiKeyCleared: false,
    apiKeyRevealed: false,
    model_name: modelName,
    // 逐家取预设值；预设没给就用一个偏大的兜底。
    //
    // 兜底值刻意**不是** 32768：设小了是"过早把老对话压成摘要"——一种安静的能力
    // 损失，用户只会觉得模型变笨，联想不到配置；设大了最坏是撞厂商报错，
    // 而那条路有"压缩后重试"兜底。可自愈的失败好过静默的损失。
    token_limit: preset.token_limit ?? 131072,
    supports_tools: true,
    supports_stream: true,
    // 视觉默认关闭：预设表里无法可靠判断某个模型名是不是多模态
    // （同一家既有文本模型也有视觉模型，靠名字猜会误判）
    supports_vision: false,
    // 思考强度默认**打开**（与其他能力开关相反）：它只在用户主动选过档位时
    // 才会真的发出去，所以默认打开不会让任何人付出代价；关掉则会让支持它的
    // 用户连那个控件都看不到。
    supports_reasoning: true,
    // 系统代理默认**关**：实测有代理的机器上国内厂商全被拖成超时，直连很快；
    // 需要代理访问 OpenAI 等的用户按模型打开。
    use_system_proxy: false,
    timeout: 120,
    temperature: 0.7,
    max_tokens: null,
    // 档位默认 standard：不预设任何厂商的"便宜/强"，那随厂商与时间变化
    tier: 'standard',
    // 备用模型默认空 = 不降级。请求会不会发到另一家、花另一家的钱，
    // 只能由用户显式决定（见后端 llm/fallback.py）
    fallback_models: [],
    enabled: true,
    is_default: false,
    // 价格默认留空：厂商调价频繁，内置一份"参考价"会让界面显示一个
    // 看起来很精确、实则过时的金额，而用户看到金额就会当真。
    price_input_per_1m: null,
    price_cached_input_per_1m: null,
    price_output_per_1m: null,
    price_input_per_1m_peak: null,
    price_cached_input_per_1m_peak: null,
    price_output_per_1m_peak: null,
    peak_windows: [],
    testState: { status: 'idle' },
  }
}

/**
 * 解析价格输入。
 *
 * **空字符串 → null（未配置），而不是 0（免费）。** 这两者含义完全不同：
 * 显示成 0 会让用户以为这个模型不花钱，从而放心地大量调用。
 */
function parsePrice(value: string): number | null {
  const trimmed = value.trim()
  if (!trimmed) return null
  const parsed = Number(trimmed)
  if (!Number.isFinite(parsed) || parsed < 0) return null
  return parsed
}

/**
 * 草稿的内容签名 —— 自动保存靠它判断"到底改没改"。
 *
 * ⚠️ **纯前端簿记字段必须排除**（`testState` / `availableModels` /
 * `apiKeyDirty` / `apiKeyCleared` / `apiKeyMask` / `apiKeyRevealed`）：
 * 它们会被我们自己改写（保存成功后复位脏标记），若参与签名就会自激出
 * "保存 → 复位 → 签名又变 → 再保存"的死循环。
 *
 * 真正决定"要不要落盘"的只有 `apiKeyInput`（用户**打进去的 Key**）与
 * 其余业务字段。
 */
function draftSignature(list: Draft[]): string {
  return JSON.stringify(
    list.map((model) => {
      const {
        testState: _t,
        availableModels: _a,
        apiKeyDirty: _d,
        apiKeyCleared: _c,
        apiKeyMask: _m,
        apiKeyRevealed: _r,
        ...rest
      } = model
      return rest
    }),
  )
}

// ---- 高峰时段（分时定价）的周几展开/收拢 -------------------------------- //
function expandDays(startDay: number, endDay: number): number[] {
  if (!startDay || !endDay) return []
  const days: number[] = []
  let cursor = startDay
  for (let guard = 0; guard < 7; guard += 1) {
    days.push(cursor)
    if (cursor === endDay) break
    cursor = cursor === 7 ? 1 : cursor + 1
  }
  return days
}

function collapseDays(days: number[]): { startDay: number; endDay: number } {
  if (!days.length) return { startDay: 1, endDay: 7 }
  const set = new Set(days)
  const start = days[0]
  let end = start
  let cursor = start
  for (let guard = 0; guard < 7; guard += 1) {
    const next = cursor === 7 ? 1 : cursor + 1
    if (set.has(next) && next !== start) {
      cursor = next
      end = next
    } else break
  }
  return { startDay: start, endDay: end }
}

/** 时间下拉选项（每 30 分钟一档，00:00 ~ 23:30） */
const TIME_OPTIONS = Array.from({ length: 48 }, (_, i) => {
  const h = String(Math.floor(i / 2)).padStart(2, '0')
  const m = i % 2 === 0 ? '00' : '30'
  return `${h}:${m}`
})

const WEEKDAY_LABELS = ['周一', '周二', '周三', '周四', '周五', '周六', '周日']
/** 三个固定高峰槽位：早高峰 / 晚高峰 / 自定义高峰（约定 3~4 行的下拉结构） */
const PEAK_SLOTS = ['早高峰', '晚高峰', '自定义高峰']

/** 更新第 index 个高峰时段；四项全空时从列表里移除该窗口 */
function updatePeakWindow(
  model: Draft,
  onChange: (patch: Partial<Draft>) => void,
  index: number,
  patch: Partial<{ days: number[]; start: string; end: string }>,
): void {
  const list = [...(model.peak_windows ?? [])]
  while (list.length <= index) list.push({ days: [], start: '', end: '' })
  list[index] = { ...list[index], ...patch }
  const cleaned = list.filter(
    (item) => item.days.length > 0 || item.start || item.end,
  )
  onChange({ peak_windows: cleaned })
}

/** 把「周几范围」应用到全部高峰槽位（周几是三个时段共享的） */
function setPeakDays(
  model: Draft,
  onChange: (patch: Partial<Draft>) => void,
  startDay: number,
  endDay: number,
): void {
  const days = expandDays(startDay, endDay)
  const list = [...(model.peak_windows ?? [])]
  while (list.length < PEAK_SLOTS.length) list.push({ days: [], start: '', end: '' })
  onChange({ peak_windows: list.map((item) => ({ ...item, days })) })
}

function ModelCard({
  model,
  presets,
  onChange,
  onRemove,
  onTest,
}: {
  model: Draft
  presets: ProviderPreset[]
  onChange: (patch: Partial<Draft>) => void
  onRemove: () => void
  onTest: () => void
}) {
  const [copied, setCopied] = useState(false)
  // 「清除密钥」的二次确认状态。见下面按钮处的说明。
  const [confirmClear, setConfirmClear] = useState(false)
  // 「获取模型」的进行态与结果提示
  const [fetching, setFetching] = useState(false)
  const [fetchNote, setFetchNote] = useState<{ tone: 'ok' | 'error'; text: string } | null>(null)
  const testing = model.testState?.status === 'testing'
  // 已连接的模型清单：备用模型从这里下拉选（产品要求，不再让用户手填 id）
  const allModels = useAppStore((state) => state.models)
  const api = useAppStore((state) => state.api)

  // Key **持久展示**（产品要求）：把已保存的明文读出来填进输入框。
  // 这样自动保存提交的始终是完整 Key，不会写进空值把已配好的模型打坏。
  //
  // ⚠️ 两个防坑点：
  // 1. 读取是异步的，用户完全可能在读取返回前就手动粘贴了新 Key ——
  //    所以用 ref 读**最新**的输入值，只有"框里仍然是空的"才回填；
  // 2. 依赖只放 `id` 与 `has_api_key`，不随每次编辑重跑（重跑会打断输入）。
  const latestInputRef = useRef(model.apiKeyInput)
  latestInputRef.current = model.apiKeyInput

  useEffect(() => {
    if (!model.has_api_key) return
    if (latestInputRef.current) return
    const bridge = window.agentBridge
    if (!bridge) return
    let cancelled = false
    void (async () => {
      try {
        const value = await bridge.revealSecret({ modelId: model.id })
        if (cancelled || !value) return
        // 用户在这期间已经自己填了 → 绝不覆盖他刚输入的内容
        if (latestInputRef.current) return
        onChange({ apiKeyInput: value, apiKeyDirty: false, apiKeyCleared: false })
      } catch {
        // 读不到就保持空白（用户仍可手填），不打断界面
      }
    })()
    return () => {
      cancelled = true
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [model.id, model.has_api_key])

  const copyKey = async () => {
    if (!model.apiKeyInput) return
    try {
      await navigator.clipboard.writeText(model.apiKeyInput)
      setCopied(true)
      setTimeout(() => setCopied(false), 1500)
    } catch {
      useNotificationStore.getState().push({
        level: 'warning',
        title: '复制失败',
        message: '请手动选中输入框内容复制。',
      })
    }
  }

  const preset = presets.find((item) => item.provider === model.provider)
  /*
    ⚠️ 一旦**发现过真实清单，预设候选就必须退场**（产品要求）。

    原先这里是 `preset.models + availableModels` 的无条件并集。问题在于
    `preset.models` 是**出厂快照**（按写代码时的官方文档抄的，很多名字早已下架），
    而 `availableModels` 是**这家账号此刻真实可用的**。两者混在一起，用户会看到
    一串"看着能选、选了 404"的名字 —— 而且分不出哪个是真的，因为界面上它们
    长得一模一样。

    与 `ModelPickerField` 的口径对齐：真实清单优先，快照只在**一次都没拉到过**
    的时候兜底（那时它就是唯一的信息来源）。
  */
  const modelOptions =
    (model.availableModels?.length ?? 0) > 0
      ? Array.from(new Set(model.availableModels))
      : Array.from(new Set(preset?.models ?? []))

  /**
   * 「获取模型」：用**当前草稿的地址与 Key** 直接拉该服务商真实提供的模型清单。
   *
   * ⚠️ 这里刻意不走 `/v1/models/sync`：那个接口要传**已保存**的 model_id，去已落盘的
   * 配置里查；而这个页面是"边填边自动保存"的，刚加/刚改地址的服务商还没落盘，用它
   * 必然 404（用户看到的就是"点了没反应/报错"）。`discover` 自带地址与 Key，没有这个
   * 时序问题，而且与「添加服务商」向导走的是同一条路，两处行为才一致。
   */
  const fetchModels = async () => {
    if (!api) {
      setFetchNote({ tone: 'error', text: '后端还没连接上，稍后重试。' })
      return
    }
    if (!model.base_url.trim()) {
      setFetchNote({ tone: 'error', text: '请先填写接口地址。' })
      return
    }
    setFetching(true)
    setFetchNote(null)
    try {
      const result = await api.discoverModels({
        base_url: model.base_url.trim(),
        api_key: model.apiKeyInput.trim(),
      })
      // 与 ModelPickerField 走**同一个**过滤（硅基流动只留 deepseek）：
      // 两个入口必须一致，否则用户会觉得"引导页能看到的模型，设置里看不到"。
      const list = filterDiscoveredModels(model.base_url.trim(), result.models ?? [])
      if (list.length === 0) {
        // 能连通但没返回列表：如实说，并指回手填这条路
        setFetchNote({ tone: 'error', text: '该地址没有返回模型列表，可在输入框手动填写。' })
        return
      }
      const patch: Partial<Draft> = { availableModels: list }
      // 原先填的（预设默认值）不在返回列表里时，直接替用户选第一个 ——
      // 对零基础用户来说，多一步选择就是多一道坎
      if (!model.model_name || !list.includes(model.model_name)) patch.model_name = list[0]
      onChange(patch)
      setFetchNote({ tone: 'ok', text: `获取到 ${list.length} 个模型，点下方候选即可选中。` })
    } catch (error) {
      setFetchNote({
        tone: 'error',
        text: error instanceof Error ? error.message : String(error),
      })
    } finally {
      setFetching(false)
    }
  }

  // 高峰时段的「周几范围」是三个槽位共享的，取第一个窗口的 days 作为展示值
  const peakDays = collapseDays(model.peak_windows?.[0]?.days ?? [])

  return (
    <div
      className={clsx(
        'rounded-[10px] border bg-canvas p-4',
        model.enabled ? 'border-line' : 'border-line opacity-70',
      )}
    >
      <div className="flex items-center gap-2">
        <span className="text-[13.5px] font-medium text-ink">
          {model.display_name || model.model_name || model.id}
        </span>
        {model.is_default ? <Badge tone="brand">默认</Badge> : null}
        {model.apiKeyCleared ? (
          <Badge tone="danger">待保存：将清除密钥</Badge>
        ) : model.apiKeyDirty && model.apiKeyInput ? (
          <Badge tone="success">待保存：密钥将更新</Badge>
        ) : model.apiKeyDirty && !model.apiKeyInput && model.has_api_key ? (
          // 用户把输入框清空了但没点「清除密钥」→ 已保存的 Key 依然有效。
          // 必须说出来：否则用户以为"删掉了"，下次连接失败时完全摸不着头脑。
          <Badge tone="warning">输入框已空：已保存的密钥仍然有效</Badge>
        ) : null}

        {/* ⚠️ 这里原先还有一份「申请 API」+「复制申请链接」。指着
            截图说"同一个页面上有了两个入口，把下面那个剔除" —— 上面那个服务商
            标题后面的才是唯一的入口（没配过也看得见）。**别再加回来**：
            闸里有一条"整页只许出现一处申请页链接"钉着。 */}
        <div className="flex-1" />
        <Switch
          checked={model.enabled}
          onChange={(enabled) => onChange({ enabled })}
          label="启用"
        />
        <button
          type="button"
          onClick={onRemove}
          className="no-drag flex h-7 w-7 items-center justify-center rounded-[7px] text-ink-faint hover:bg-danger-soft hover:text-danger"
          aria-label="删除"
        >
          <Trash2 size={14} />
        </button>
      </div>

      <div className="mt-3 grid grid-cols-2 gap-3">
        <Field label="展示名称">
          <Input
            value={model.name}
            onChange={(event) => onChange({ name: event.target.value })}
            placeholder="例如 DeepSeek Chat"
          />
        </Field>

        <Field
          label="模型名（厂商真实名称）"
          hint={
            model.availableModels?.length
              ? `已从端点发现 ${model.availableModels.length} 个可用模型，点下方候选即可选`
              : undefined
          }
        >
          <div className="flex gap-2">
            <Input
              value={model.model_name}
              onChange={(event) => onChange({ model_name: event.target.value })}
              placeholder="例如 deepseek-chat"
              list={modelOptions.length ? `models-${model.id}` : undefined}
            />
            <Button
              size="sm"
              className="shrink-0"
              icon={fetching ? <Loader2 size={13} className="animate-spin" /> : <RefreshCw size={13} />}
              disabled={fetching}
              onClick={() => void fetchModels()}
            >
              {fetching ? '获取中…' : '获取模型'}
            </Button>
          </div>
          {modelOptions.length ? (
            <datalist id={`models-${model.id}`}>
              {modelOptions.map((name) => (
                <option key={name} value={name} />
              ))}
            </datalist>
          ) : null}
          {/* 光靠 datalist 不够：它要点过输入框才展开、而且会按输入框当前值过滤，
              等于把"有哪些可选"藏起来了（用户看到的正是"提示说能下拉、下拉里却没有"）。
              这里把候选直接摊开，点一下就选中 —— 与 ModelPickerField 的做法一致。 */}
          {modelOptions.length ? (
            <div className="mt-1.5 flex max-h-[150px] flex-wrap gap-1 overflow-y-auto">
              {modelOptions.map((name) => (
                <button
                  key={name}
                  type="button"
                  onClick={() => onChange({ model_name: name })}
                  className={clsx(
                    'no-drag rounded-[6px] border px-2 py-0.5 text-[11.5px] whitespace-nowrap transition-colors',
                    model.model_name === name
                      ? 'border-brand/40 bg-brand-soft text-brand'
                      : 'border-line text-ink-soft hover:border-brand/40 hover:text-ink',
                  )}
                >
                  {name}
                </button>
              ))}
            </div>
          ) : null}
          {fetchNote ? (
            <p
              className={clsx(
                'mt-1.5 text-[11.5px] leading-relaxed',
                fetchNote.tone === 'ok' ? 'text-success' : 'text-danger',
              )}
            >
              {fetchNote.text}
            </p>
          ) : null}
        </Field>

        <Field label="接口地址 Base URL" className="col-span-2">
          <Input
            value={model.base_url}
            onChange={(event) => onChange({ base_url: event.target.value })}
            placeholder="https://api.deepseek.com/v1"
          />
        </Field>

        <Field
          label="API Key"
          className="col-span-2"
          hint="密钥保存在本机（Windows 上用 DPAPI 加密，只有本机当前用户能解密）。右侧可一键复制；要删除密钥请点最右侧的 ✕ —— 把输入框清空不会删掉已保存的密钥。"
        >
          <div className="flex gap-2">
            {/* 明文常显（产品要求）：不做"点小眼睛才看得到"，省得自动保存
                把空值当新值写进去，把已配好的模型打坏。 */}
            <Input
              type="text"
              value={model.apiKeyInput}
              onChange={(event) =>
                onChange({
                  apiKeyInput: event.target.value,
                  apiKeyDirty: true,
                  // 重新打字就是"我要重新填"，撤销掉之前的清除意图
                  apiKeyCleared: false,
                })
              }
              placeholder={
                model.has_api_key
                  ? '已保存（留空 = 不修改；要删除请点右侧 ✕）'
                  : 'sk-...'
              }
              autoComplete="off"
              spellCheck={false}
            />
            <button
              type="button"
              onClick={() => void copyKey()}
              className="no-drag flex h-9 w-9 shrink-0 items-center justify-center rounded-[8px] border border-line text-ink-faint hover:text-ink"
              aria-label="复制密钥"
              title="复制密钥"
            >
              {copied ? <Check size={14} className="text-success" /> : <Copy size={14} />}
            </button>
            {/* 删除密钥必须是**显式动作 + 二次确认**（实测反馈：几轮以来 Key 总是被清空，
                而且"不知道操作了什么"）。

                三道防线叠在一起：
                1. 这个按钮是全应用**唯一**能删掉密钥的入口（提交时带 clear_api_key）；
                2. 就算误点一次也不会删 —— 第一次点击只是"预备"，4 秒内再点一次才真的清；
                3. 它和「复制」紧挨着、形状也一样，所以预备态会**变宽变色**并显示"确认清除"，
                   避免用户以为"我点了复制"。

                之所以要这么小心：密钥是用户花钱买的，删掉之后他只知道"模型不能用了"，
                几乎不可能联想到是这里点错了。 */}
            {model.has_api_key || model.apiKeyInput ? (
              <button
                type="button"
                onClick={() => {
                  if (!confirmClear) {
                    setConfirmClear(true)
                    setTimeout(() => setConfirmClear(false), 4000)
                    return
                  }
                  setConfirmClear(false)
                  onChange({ apiKeyInput: '', apiKeyDirty: false, apiKeyCleared: true })
                }}
                className={clsx(
                  'no-drag flex h-9 shrink-0 items-center justify-center rounded-[8px] border',
                  confirmClear
                    ? 'w-auto gap-1 border-danger/50 bg-danger-soft px-2 text-[11px] text-danger'
                    : 'w-9 border-line text-ink-faint hover:border-danger/40 hover:bg-danger-soft hover:text-danger',
                )}
                aria-label={confirmClear ? '确认清除密钥' : '清除密钥'}
                title={
                  confirmClear
                    ? '再点一次即清除，不可撤销'
                    : '清除已保存的密钥（需要再点一次确认）'
                }
              >
                <X size={14} />
                {confirmClear ? '确认清除' : null}
              </button>
            ) : null}
          </div>
        </Field>

        {/* 保存并测试连通性**紧跟 API Key**（产品要求）：填完 Key 顺手一测，
            不用滚到卡片底部找按钮 */}
        <div className="col-span-2 -mt-1 flex flex-wrap items-center gap-2">
          <Button
            size="sm"
            variant="secondary"
            icon={testing ? <Loader2 size={13} className="animate-spin" /> : <Zap size={13} />}
            onClick={onTest}
            disabled={testing}
          >
            保存并测试连通性
          </Button>
          {model.testState?.status === 'ok' ? (
            <span className="flex items-center gap-1 text-[12px] text-success">
              <Check size={12} />
              连接正常{model.testState.message ? ` · ${model.testState.message}` : ''}
            </span>
          ) : null}
          {model.testState?.status === 'fail' ? (
            <span className="min-w-0 flex-1 truncate text-[12px] text-danger" title={model.testState.message}>
              {model.testState.message}
            </span>
          ) : null}
        </div>

        <Field label="上下文窗口（tokens）">
          <Input
            type="number"
            value={model.token_limit}
            onChange={(event) => onChange({ token_limit: Number(event.target.value) || 32768 })}
          />
        </Field>

        <Field label="超时时间（秒）">
          <Input
            type="number"
            value={model.timeout}
            onChange={(event) => onChange({ timeout: Number(event.target.value) || 120 })}
          />
        </Field>

        <div className="col-span-2 flex flex-wrap items-center gap-4">
          <label className="flex items-center gap-2 text-[12.5px] text-ink-soft">
            <Switch
              checked={model.supports_tools}
              onChange={(supports_tools) => onChange({ supports_tools })}
              label="支持工具调用"
            />
            支持工具调用
          </label>
          <label className="flex items-center gap-2 text-[12.5px] text-ink-soft">
            <Switch
              checked={model.supports_vision}
              onChange={(supports_vision) => onChange({ supports_vision })}
              label="支持图片输入"
            />
            支持图片输入
          </label>
          <label
            className="flex items-center gap-2 text-[12.5px] text-ink-soft"
            title="打开后，输入框下方会出现「思考强度」选择；只在你主动选过档位时才会把该参数发给模型"
          >
            <Switch
              checked={model.supports_reasoning}
              onChange={(supports_reasoning) => onChange({ supports_reasoning })}
              label="支持思考强度"
            />
            支持思考强度
          </label>
          <label
            className="flex items-center gap-2 text-[12.5px] text-ink-soft"
            title="默认关闭。只有需要代理才能访问的厂商（如 OpenAI、Anthropic）才打开；国内厂商走代理反而会超时"
          >
            <Switch
              checked={model.use_system_proxy ?? false}
              onChange={(use_system_proxy) => onChange({ use_system_proxy })}
              label="使用系统代理"
            />
            使用系统代理
          </label>
          <label className="flex items-center gap-2 text-[12.5px] text-ink-soft">
            <Switch
              checked={model.is_default}
              onChange={(is_default) => onChange({ is_default })}
              label="设为默认"
            />
            设为默认模型
          </label>
        </div>

        {/*
          下面两项原先在界面上完全没有入口 —— 后端早就实现了模型路由与故障降级，
          但用户在客户端里根本配不了，等于功能不存在。
        */}
        <div className="mt-3 grid grid-cols-2 gap-3">
          <Field label="能力档位" hint="模型路由按任务复杂度挑模型时使用">
            <Select
              value={model.tier}
              onChange={(event) => onChange({ tier: event.target.value as ModelInfo['tier'] })}
            >
              <option value="cheap">便宜快速</option>
              <option value="standard">标准</option>
              <option value="strong">最强</option>
            </Select>
          </Field>

          <Field
            label="备用模型"
            hint="主模型失败时按顺序降级；从已连接的模型里下拉选择（可多选）。留空 = 不降级"
          >
            <div className="space-y-2">
              {model.fallback_models.length ? (
                <div className="flex flex-wrap gap-1.5">
                  {model.fallback_models.map((id, index) => {
                    const target = allModels.find((item) => item.id === id)
                    return (
                      <span
                        key={id}
                        className="flex items-center gap-1 rounded-[6px] border border-line bg-panel px-2 py-0.5 text-[12px] text-ink"
                      >
                        <span className="text-ink-faint">{index + 1}.</span>
                        {target ? target.display_name || target.model_name : id}
                        <button
                          type="button"
                          aria-label="移除"
                          title="移除"
                          onClick={() =>
                            onChange({
                              fallback_models: model.fallback_models.filter((item) => item !== id),
                            })
                          }
                          className="text-ink-faint hover:text-danger"
                        >
                          <X size={11} />
                        </button>
                      </span>
                    )
                  })}
                </div>
              ) : null}
              <Select
                value=""
                onChange={(event) => {
                  const id = event.target.value
                  if (id) onChange({ fallback_models: [...model.fallback_models, id] })
                }}
              >
                <option value="">+ 添加备用模型…</option>
                {allModels
                  .filter((item) => item.id !== model.id && !model.fallback_models.includes(item.id))
                  .map((item) => (
                    <option key={item.id} value={item.id}>
                      {item.display_name || item.model_name}
                    </option>
                  ))}
              </Select>
            </div>
          </Field>
        </div>
      </div>

      {/* 价格设置放**卡片最底部**（产品要求），含高峰时段定价 */}
      <div className="mt-3 rounded-[10px] border border-line-soft bg-canvas px-3 py-2.5">
        <div className="mb-2 flex flex-wrap items-center gap-1.5 text-[12px] text-ink-soft">
          <Coins size={13} className="text-ink-faint" />
          <span className="font-medium text-ink">价格设置（每百万 token）</span>
          <span className="text-[11px] text-ink-faint">
            可选，填了才能在「用量与费用」里看到金额。命中缓存的输入会用更低的单价。
          </span>
        </div>
        <div className="grid grid-cols-3 gap-2">
          <Field label="输入">
            <Input
              type="number"
              step="0.01"
              min="0"
              placeholder="留空"
              value={model.price_input_per_1m ?? ''}
              onChange={(event) =>
                onChange({ price_input_per_1m: parsePrice(event.target.value) })
              }
            />
          </Field>
          <Field label="输入·缓存命中" hint="留空按未命中价算（偏保守）">
            <Input
              type="number"
              step="0.01"
              min="0"
              placeholder="留空"
              value={model.price_cached_input_per_1m ?? ''}
              onChange={(event) =>
                onChange({ price_cached_input_per_1m: parsePrice(event.target.value) })
              }
            />
          </Field>
          <Field label="输出">
            <Input
              type="number"
              step="0.01"
              min="0"
              placeholder="留空"
              value={model.price_output_per_1m ?? ''}
              onChange={(event) =>
                onChange({ price_output_per_1m: parsePrice(event.target.value) })
              }
            />
          </Field>
        </div>

        {/* 高峰时段价格（如 DeepSeek 的分时定价）：命中时段时计费用峰值价 */}
        <div className="mt-3 text-[11.5px] font-medium text-ink-soft">
          高峰时段价格（可选；与普通价一样含输入 / 缓存命中 / 输出三档）
        </div>
        <div className="mt-1 grid grid-cols-3 gap-2">
          <Field label="高峰·输入">
            <Input
              type="number"
              step="0.01"
              min="0"
              placeholder="留空按普通价"
              value={model.price_input_per_1m_peak ?? ''}
              onChange={(event) =>
                onChange({ price_input_per_1m_peak: parsePrice(event.target.value) })
              }
            />
          </Field>
          <Field label="高峰·缓存命中">
            <Input
              type="number"
              step="0.01"
              min="0"
              placeholder="留空按普通价"
              value={model.price_cached_input_per_1m_peak ?? ''}
              onChange={(event) =>
                onChange({ price_cached_input_per_1m_peak: parsePrice(event.target.value) })
              }
            />
          </Field>
          <Field label="高峰·输出">
            <Input
              type="number"
              step="0.01"
              min="0"
              placeholder="留空按普通价"
              value={model.price_output_per_1m_peak ?? ''}
              onChange={(event) =>
                onChange({ price_output_per_1m_peak: parsePrice(event.target.value) })
              }
            />
          </Field>
        </div>

        <div className="mt-3 text-[11.5px] font-medium text-ink-soft">
          高峰时段（下拉选择；命中时段内才按高峰价计费）
        </div>

        {/* 第 1 行：周几范围（三个时段共享，产品要求 的结构） */}
        <div className="mt-1.5 flex items-center gap-1.5 text-[12px] text-ink-soft">
          <span className="w-[56px] shrink-0">周几</span>
          {/*
            ⚠️ 这几个下拉的可见文字（"周几"/"早高峰"…）是**旁边的 span**，
            与控件本身没有任何程序化关联（没有 `htmlFor`/`id`）——
            读屏念到它时只会说"组合框"，用户不知道在选什么（第 90 批，M-34）。
            补 `aria-label` 是视觉零改动的做法。
          */}
          <select
            value={peakDays.startDay}
            onChange={(event) =>
              setPeakDays(model, onChange, Number(event.target.value), peakDays.endDay)
            }
            aria-label="高峰时段起始周几"
            className="h-7 rounded-[6px] border border-line bg-canvas px-1.5 text-[12px] text-ink focus:border-brand focus:outline-none focus-visible:ring-2 focus-visible:ring-brand/40"
          >
            {WEEKDAY_LABELS.map((label, i) => (
              <option key={label} value={i + 1}>
                {label}
              </option>
            ))}
          </select>
          <span>到</span>
          <select
            value={peakDays.endDay}
            onChange={(event) =>
              setPeakDays(model, onChange, peakDays.startDay, Number(event.target.value))
            }
            aria-label="高峰时段结束周几"
            className="h-7 rounded-[6px] border border-line bg-canvas px-1.5 text-[12px] text-ink focus:border-brand focus:outline-none focus-visible:ring-2 focus-visible:ring-brand/40"
          >
            {WEEKDAY_LABELS.map((label, i) => (
              <option key={label} value={i + 1}>
                {label}
              </option>
            ))}
          </select>
          <span className="text-[11px] text-ink-faint">（三个时段共用这组周几）</span>
        </div>

        {/* 第 2~4 行：早高峰 / 晚高峰 / 自定义高峰，时间用下拉选择 */}
        {PEAK_SLOTS.map((label, index) => {
          const win = model.peak_windows?.[index]
          const days = expandDays(peakDays.startDay, peakDays.endDay)
          return (
            <div key={label} className="mt-1.5 flex items-center gap-1.5 text-[12px] text-ink-soft">
              <span className="w-[56px] shrink-0">{label}</span>
              <select
                value={win?.start ?? ''}
                onChange={(event) =>
                  updatePeakWindow(model, onChange, index, {
                    start: event.target.value,
                    days,
                  })
                }
                aria-label={`${label}开始时间`}
                className="h-7 rounded-[6px] border border-line bg-canvas px-1.5 text-[12px] text-ink focus:border-brand focus:outline-none focus-visible:ring-2 focus-visible:ring-brand/40"
              >
                <option value="">不设</option>
                {TIME_OPTIONS.map((t) => (
                  <option key={t} value={t}>
                    {t}
                  </option>
                ))}
              </select>
              <span>至</span>
              <select
                value={win?.end ?? ''}
                onChange={(event) =>
                  updatePeakWindow(model, onChange, index, {
                    end: event.target.value,
                    days,
                  })
                }
                aria-label={`${label}结束时间`}
                className="h-7 rounded-[6px] border border-line bg-canvas px-1.5 text-[12px] text-ink focus:border-brand focus:outline-none focus-visible:ring-2 focus-visible:ring-brand/40"
              >
                <option value="">不设</option>
                {TIME_OPTIONS.map((t) => (
                  <option key={t} value={t}>
                    {t}
                  </option>
                ))}
              </select>
              {index === PEAK_SLOTS.length - 1 ? (
                <span className="text-[11px] text-ink-faint">（跨午夜如 22:00 至 06:00 也支持）</span>
              ) : null}
            </div>
          )
        })}
      </div>

    </div>
  )
}

export function ModelSettings() {
  const models = useAppStore((state) => state.models)
  const presets = useAppStore((state) => state.presets)
  const defaultModel = useAppStore((state) => state.modelDefaults.defaultModel)
  const api = useAppStore((state) => state.api)
  const reloadModels = useAppStore((state) => state.reloadModels)

  const [draft, setDraft] = useState<Draft[]>([])
  /** 草稿是否已经完成过一次"服务端播种"。没播种前绝不触发自动保存。 */
  const hydratedRef = useRef(false)
  /** 最近一次**成功落盘**的内容签名（自动保存用它判断有没有真改动）。 */
  const lastSavedRef = useRef('')
  /** 保存防抖定时器 */
  const saveTimerRef = useRef<number | null>(null)
  /** 最新的草稿（供保存成功后在"异步回调"里取到当前值，避免闭包过期） */
  const latestDraftRef = useRef<Draft[]>([])
  latestDraftRef.current = draft
  /** 自动保存是否正在进行（用于串行化，避免并发的整份提交互相覆盖） */
  const autoSaveBusyRef = useRef(false)
  /** 保存进行中又发生了改动：结束后立刻再存一次最新的草稿（合并，不排队） */
  const autoSavePendingRef = useRef(false)
  const [wizardOpen, setWizardOpen] = useState(false)
  const [message, setMessage] = useState<{
    // warning = "现在还不能保存，但不是你做错了"（例如新服务商还没填完）。
    // 用红色报错去表达这种情况会让用户以为出了故障。
    tone: 'ok' | 'warning' | 'error'
    text: string
  } | null>(null)
  // Cherry 式布局：左侧列表选中了哪家。null 表示"还没选"，此时落到第一项
  // **服务商中心**：左列九家预设每家一行（含未配置的），点进去右侧配置；
  // 模型用**下拉**选，不再"每个模型一行"。
  const [selectedKey, setSelectedKey] = useState<string | null>(null)
  // 这里曾有 `filter`（服务商搜索框的输入）。搜索框按产品要求剔除后它没有使用者了，
  // 一并删掉 —— 留一个永远为空的 state 只会让下一个读代码的人以为筛选还在生效。
  // 「同步服务商模型」按钮的状态。应用动作在 applySync 里完成，这里只管状态与提示。
  //
  // `key` 记录"这份结果属于哪家服务商"：切到别家时**不显示**上一家的残留结果，
  // 而不是把一个刚写好的结果清掉 —— 直接清掉会让"同步完成"的提示一闪就没。
  const [sync, setSync] = useState<{
    key: string | null
    status: 'idle' | 'busy' | 'done' | 'error'
    message?: string
  }>({ key: null, status: 'idle' })

  /** 删除模型前先问：删单个还是删整个服务商（本轮反馈：同步后底部模型太多，只能一个个删） */
  const [deletePrompt, setDeletePrompt] = useState<{ model: Draft } | null>(null)

  interface ProviderGroup {
    key: string
    name: string
    provider: string
    baseUrl: string
    models: Draft[]
    anyEnabled: boolean
    hasDefault: boolean
  }
  const providerGroups: ProviderGroup[] = (() => {
    const map = new Map<string, Draft[]>()
    for (const model of draft) {
      const key = `${model.provider}|${model.base_url}`
      const list = map.get(key)
      if (list) list.push(model)
      else map.set(key, [model])
    }
    return [...map.entries()].map(([key, groupModels]) => {
      const first = groupModels[0]
      const preset = presets.find(
        (item) => item.provider === first.provider && item.base_url === first.base_url,
      )
      return {
        key,
        name: preset?.name ?? first.display_name.split(' · ')[0] ?? first.provider,
        provider: first.provider,
        baseUrl: first.base_url,
        models: groupModels,
        anyEnabled: groupModels.some((model) => model.enabled),
        hasDefault: groupModels.some((model) => model.is_default),
      }
    })
  })()

  // 左列条目 = 预设厂商（无论配没配）+ 自建端点（不在预设里的已配置组）
  // "真正配置好"= 组内任一条目**有 Key**（自建的本机端点免 Key 除外）。
  // 以前只判断"存在条目就亮绿点"——点了「添加」还没填 Key 也显示绿色，
  // 用户会误以为已经配置完成（本轮反馈 #3）。
  const isGroupUsable = (group: { models: Draft[] }): boolean =>
    group.models.some(
      (model) =>
        model.enabled &&
        (model.has_api_key || /^https?:\/\/(127\.0\.0\.1|localhost)/i.test(model.base_url)),
    )
  const presetKey = (provider: string) => `p:${provider}`
  const groupKeyOf = (preset: ProviderPreset) => `${preset.provider}|${preset.base_url}`
  /** 一条模型所属分组的键（与 groupKeyOf 同构，只是数据来源是草稿里的模型） */
  const providerGroupKey = (model: Draft) => `${model.provider}|${model.base_url}`
  /**
   * 自建分组的选中键。取该组**代表条目**（默认条目，没有就第一条）的 id ——
   * id 不随用户编辑接口地址而变，所以右侧配置区不会在打字途中断开。
   */
  const customGroupSelectKey = (group: ProviderGroup) =>
    `g:${(group.models.find((item) => item.is_default) ?? group.models[0])?.id ?? ''}`
  const customGroups = providerGroups.filter(
    (group) => !presets.some((p) => groupKeyOf(p) === group.key),
  )
  // ⚠️ 搜索服务商的输入框按产品要求**剔除**，所以这里不再按
  // `keyword` 过滤 —— 这两个名字保留（而不是让调用点直接用 presets/customGroups），
  // 是为了将来想加回筛选时只改这一处。
  const visiblePresets = presets
  const visibleCustomGroups = customGroups

  // 当前选中：优先用户点过的；否则第一家**已配置**的，再否则第一家预设
  //
  // ⚠️ 自建端点的选中键是 **`g:<模型 id>`**，不是 `g:<provider>|<base_url>`。
  //
  // 用 provider|base_url 当身份时，"点「+添加服务商」→ 往接口地址里打字"这个
  // 再正常不过的动作会让身份**当场改变**：选中键对不上任何分组 → 右侧配置区
  // 判定为"没选中" → 直接消失。用户看到的就是"我还没填完，页面就自己退出了"
  // （反馈 #2）。模型 id 在整个生命周期里不变，所以它是唯一合适的锚点。
  const activeGroup: ProviderGroup | null = (() => {
    if (selectedKey?.startsWith('g:')) {
      const modelId = selectedKey.slice('g:'.length)
      const owner = draft.find((item) => item.id === modelId)
      if (!owner) return null
      return providerGroups.find((group) => group.key === providerGroupKey(owner)) ?? null
    }
    if (selectedKey?.startsWith('p:')) {
      const preset = presets.find((item) => presetKey(item.provider) === selectedKey)
      return preset ? providerGroups.find((group) => group.key === groupKeyOf(preset)) ?? null : null
    }
    return providerGroups[0] ?? null
  })()
  const activePreset: ProviderPreset | null = (() => {
    if (selectedKey?.startsWith('p:')) {
      return presets.find((item) => presetKey(item.provider) === selectedKey) ?? null
    }
    if (selectedKey?.startsWith('g:')) return null
    const firstConfigured = providerGroups[0]
    if (firstConfigured) {
      return (
        presets.find((item) => groupKeyOf(item) === firstConfigured.key) ?? null
      )
    }
    return presets[0] ?? null
  })()
  /**
   * 该服务商**申请 API Key 的直达页**（显示在右侧"服务商独立页面"的标题后面）。
   *
   * ⚠️ 画红框定的位置就是这个标题后面。之前它只在 `ModelCard` 里，
   * 而那张卡要**先点「添加」**才出现 —— 没配过的服务商整屏**看不到申请入口**，
   * 于是"想拿 Key 得先点添加"，本末倒置。`docs` 只作兜底（自定义端点两个都没有
   * ⇒ 不渲染按钮，不画空壳）。
   */
  const activeApplyUrl: string = activePreset ? activePreset.apply_url || activePreset.docs || '' : ''
  /**
   * 复制申请链接。
   *
   * 为什么要单独给一个"复制"：这段链接在界面上是看不到、也选不中的，
   * 而用户常常要把它发到手机上打开（或在浏览器里粘贴）—— 只能靠按钮给。
   * 复制成功后 1.5 秒对勾反馈，与同一张卡上「复制密钥」的反馈一致
   * （同一个动作在两处给不同反馈，会让人怀疑其中一个没生效）。
   *
   * ⚠️ 它就挨着标题后面那个「申请 API」。原先这对按钮在**下面的模型卡**里，
   * 指着截图说"同一个页面上有了两个入口，把下面那个剔除" ⇒
   * 整页只留这一处（闸里有一条钉着）。
   */
  const [applyCopied, setApplyCopied] = useState(false)
  const copyApplyUrl = async () => {
    try {
      await navigator.clipboard.writeText(activeApplyUrl)
      setApplyCopied(true)
      setTimeout(() => setApplyCopied(false), 1500)
    } catch {
      useNotificationStore.getState().push({
        level: 'warning',
        title: '复制失败',
        message: `请手动复制这个地址：${activeApplyUrl}`,
      })
    }
  }
  // 右侧编辑的**代表条目**（一个服务商一张配置卡；多出来的条目列在下面可删）
  const activeEntry: Draft | null = activeGroup
    ? activeGroup.models.find((model) => model.is_default) ?? activeGroup.models[0]
    : null

  /** 删除选择：只删这一个模型 */
  const removeSingleModel = () => {
    if (!deletePrompt) return
    setDraft((list) => list.filter((item) => item !== deletePrompt.model))
    setDeletePrompt(null)
  }
  /** 删除选择：删整个服务商（同 provider|base_url 的所有模型，含当前代表条目） */
  const removeWholeProvider = () => {
    if (!deletePrompt) return
    const key = providerGroupKey(deletePrompt.model)
    setDraft((list) => list.filter((item) => providerGroupKey(item) !== key))
    setDeletePrompt(null)
  }

  /**
   * 当前服务商**已发现**的模型清单（组内所有条目 `availableModels` 的并集）。
   *
   * 这是"两个下拉"的统一数据源 —— 不管是点「获取模型」、「同步模型」还是
   * 「保存并测试连通性」，写进去的都是同一份，所以不会再出现"一个下拉有模型、
   * 另一个没有"。
   */
  const discoveredModels = activeGroup
    ? Array.from(new Set(activeGroup.models.flatMap((model) => model.availableModels ?? [])))
    : []
  /** 同步按钮的结果：只认**当前这家**的，免得上一家的"同步完成"挂在下一家头上 */
  const activeSync = activeGroup && sync.key === activeGroup.key ? sync : null

  // ---- 草稿播种（服务端列表 → 本地草稿） ---------------------------------- //
  //
  // ⚠️ 这里是"Key 总被清空"这个反复出现的问题的**主现场**，改之前先读完这段。
  //
  // 以前这个 effect 每次都把草稿**整份重建**，并把 `apiKeyInput` 写死成空串。
  // 而它依赖 `[models]`，`models` 又会在每次保存后（reloadModels）被替换 ——
  // 于是时间线是：
  //   用户粘好 Key → 自动保存成功 → reloadModels → 本 effect 重建草稿
  //   → 输入框被清成空白（用户看到的就是"Key 没了"）
  //   → 而填充明文的那段 effect 依赖只有 [id, has_api_key]，值没变不会重跑
  //   → 输入框**永久**停在空白，之后任何一次自动保存提交的都是空值。
  //
  // 现在改成"**合并**"而不是"重建"：服务端字段照常刷新，但**用户手里的
  // Key 字段原样保留**（按 id 对齐）。这样输入框在任何一次刷新后都不会变空。
  useEffect(() => {
    let cancelled = false
    // 真实 Key 在加密存储里（由主进程用 DPAPI 保管），两边下发的都是**脱敏预览**。
    // 预览必须带 `*`（见 electron/secret-envelope.ts 的 maskSecret），只用于 placeholder。
    void (async () => {
      let keys: Record<string, string> = {}
      try {
        keys = (await window.agentBridge?.getSecretsMasked())?.models ?? {}
      } catch {
        // 拿不到就退回后端下发的值（同样是脱敏的），不阻断设置页
      }
      if (cancelled) return
      // 用 ref 取"最新一帧的草稿"来做合并基准 —— 刻意**不**把这段逻辑塞进
      // setDraft 的更新函数里：更新函数必须是纯函数（React 在 StrictMode 下
      // 会重复调用它来暴露副作用），而下面要写两个 ref。
      const previousById = new Map(latestDraftRef.current.map((item) => [item.id, item]))
      const next: Draft[] = models.map((model) => {
        const before = previousById.get(model.id)
        return {
          ...model,
          // 掩码只进 `apiKeyMask`（placeholder 用），**永不进输入框的值**
          apiKeyMask: keys[model.id] ?? model.api_key,
          // ⬇︎ 用户手里的 Key：原样带过来，**绝不被服务端数据覆盖**
          //
          // ⚠️ 首帧的兜底值从 `''` 改成 `model.api_key`：后端现在**直接下发明文**，
          // 所以输入框第一帧就有真字符，不再依赖那个异步的 `revealSecret` 回填。
          //
          // 这修掉的是一个真实的竞态：回填还没返回、自动保存已经带着空值跑掉了。
          // 现在"框里有真 Key"和"保存时提交真 Key"之间没有任何时间窗。
          apiKeyInput: before?.apiKeyInput ?? model.api_key ?? '',
          apiKeyDirty: before?.apiKeyDirty ?? false,
          // 「清除」意图要跨刷新存活；但服务端已经确认没有 Key 了（说明清除
          // 已经落盘），就把这个意图复位，免得徽标一直挂着"将清除密钥"
          apiKeyCleared: (before?.apiKeyCleared ?? false) && model.has_api_key,
          apiKeyRevealed: before?.apiKeyRevealed ?? false,
          // 测试结果同理：用户没改配置时不该把"连接正常"抹掉
          testState: before?.testState ?? { status: 'idle' as const },
          availableModels: before?.availableModels,
        }
      })
      // 播种完成 + 记录签名：这样"打开设置页"本身不会触发一次无意义保存，
      // 也保证保存成功后回到稳定状态（签名与已保存内容一致 → 不再自动保存）。
      hydratedRef.current = true
      lastSavedRef.current = draftSignature(next)
      setDraft(next)
    })()
    return () => {
      cancelled = true
    }
  }, [models])

  const patch = (index: number, changes: Partial<Draft>) => {
    setDraft((list) =>
      list.map((model, i) => {
        if (i !== index) {
          // 默认模型唯一：设置某一个为默认时，取消其他
          return changes.is_default ? { ...model, is_default: false } : model
        }
        return { ...model, ...changes, testState: { status: 'idle' as const } }
      }),
    )
  }

  const addModel = (preset: ProviderPreset) => {
    setDraft((list) => [...list, newModelFromPreset(preset, list)])
  }

  // 「+ 添加服务商」（产品要求）：建一个**全空**的服务商，让用户自己填
  // base_url / 模型名 / Key，接入任何 OpenAI 兼容端点（包括被剔除的那几家）。
  const addCustomProvider = () => {
    const blankPreset: ProviderPreset = {
      provider: 'custom',
      name: '自定义服务商',
      base_url: '',
      models: [],
      docs: '',
      token_limit: 131072,
    }
    let index = 1
    let id = 'custom-1'
    while (draft.some((item) => item.id === id)) {
      index += 1
      id = `custom-${index}`
    }
    const model: Draft = {
      ...newModelFromPreset(blankPreset, draft),
      id,
      provider: 'custom',
      name: '自定义服务商',
      display_name: '自定义服务商',
      base_url: '',
      model_name: '',
    }
    setDraft((list) => [...list, model])
    // 用**模型 id** 选中（不是 provider|base_url）—— 后者会随接口地址一起变，
    // 用户一开始打字右侧配置区就"找不到自己"了。
    setSelectedKey(`g:${model.id}`)
  }

  /**
   * 保存。
   *
   * `list` 默认就是当前 draft；之所以允许传参，是给「接入向导」用的 ——
   * 向导新增的模型要跟着一起提交，而**组装与提交只能有一处实现**
   * （下面那段"整份提交的字段清单"已经因为漏字段翻过三次车）。
   */
  const save = async (list: Draft[] = draft): Promise<boolean> => {
    if (!api) return false
    setMessage(null)

    // 「+添加服务商」刚建出来时是个**空表单**（接口地址与模型名都还没填）。
    // 自动保存的 300ms 防抖会立刻把这个半成品提交上去，而后端必然校验失败、
    // 回一个 400 —— 用户正在打字，却突然看到一句完全看不懂的红色报错。
    // 这就是"还没设置完就自动保存"的另一半现象（反馈 #2）。
    //
    // 所以：**没填完的条目不落盘**，并如实告诉用户"填完会自动保存"。
    // 已保存的条目一定同时有 base_url 与 model_name，所以这条不会误伤它们。
    const unfinished = list.filter(
      (model) => !model.base_url.trim() || !model.model_name.trim(),
    )
    if (unfinished.length > 0) {
      setMessage({
        tone: 'warning',
        text: '还有服务商没填完（接口地址与模型名都不能为空），填完之后会自动保存。',
      })
      return false
    }

    try {
      const chosenDefault = list.find((model) => model.is_default)?.id ?? defaultModel
      // 字段清单在 modelPayload.ts —— **唯一来源**，向导与设置页共用。
      // 历史上"加了字段忘了加到这里"翻过三次车（supports_vision、价格三字段、
      // tier/fallback_models），表现都是"界面上改完一保存就丢"。
      const payload = modelPayload(list, chosenDefault)
      await api.saveModels(payload)

      // 把密钥交给主进程加密保存。只提交**用户真正改过**的条目，
      // 其余由 saveSecrets 的合并语义原样保留。
      //
      // ⚠️ 这里曾经只有 `apiKeyDirty` 一个条件，于是"脏标记还在 + 输入框恰好
      // 是空的"会提交 `{id: ''}`，而 Electron 侧 `merge()` 把空串解释成
      // **删除** —— 已配好的 Key 就这样没了。现在有三重保障：
      //   1. 空值根本不写进 `models`（只写非空）；
      //   2. 删除走**独立的** `removeModelIds` 通道，只有用户显式点
      //      「清除密钥」才会进来；
      //   3. Electron 的 `merge()` 本身也不再"见空就删"（最后一道防线）。
      const keyed: Record<string, string> = {}
      const removeIds: string[] = []
      for (const model of list) {
        if (model.apiKeyCleared) {
          // 删除走独立通道（写空串已经不再被解释成删除）
          removeIds.push(model.id)
          continue
        }
        if (model.apiKeyDirty && model.apiKeyInput) {
          keyed[model.id] = model.apiKeyInput
          continue
        }
        // 「同步模型」新增的条目：后端会用 `inherit_key_from` 把锚点的 Key 复制到
        // 配置里，但**加密存储里并没有它的条目** —— 不在这里补一份的话，下次启动
        // apply_secrets 注入不到 Key，它就变成一个连不上的空壳。
        // 锚点的明文此刻就在前端手里（输入框里那个），直接复制一份过去。
        if (model.inherit_key_from) {
          const source = list.find((item) => item.id === model.inherit_key_from)
          if (source?.apiKeyInput) keyed[model.id] = source.apiKeyInput
        }
      }
      // 密钥写入加密存储 与 刷新内存注册表 **互相不依赖**，并行做。
      //
      // 串起来做只是白等一个往返：前者是 IPC 到主进程写文件，后者是 GET /v1/models。
      // 自动保存是每次改字段都会走的路，省掉一个往返就是实打实的体感差别。
      let secretsError: unknown = null
      await Promise.all([
        (async () => {
          try {
            await window.agentBridge?.saveSecrets({ models: keyed, removeModelIds: removeIds })
          } catch (error) {
            secretsError = error
          }
        })(),
        reloadModels(),
      ])

      // 复位脏标记。**不影响内容签名**（见 draftSignature 的排除列表），
      // 所以不会自激出"保存→复位→再保存"的循环。
      // 只复位"这次提交的值到现在仍然没变"的条目 —— 保存期间用户接着打字
      // 的那部分不能被误判成已保存。
      setDraft((current) =>
        current.map((item) => {
          const submitted = list.find((entry) => entry.id === item.id)
          if (!submitted) return item
          if (item.apiKeyInput !== submitted.apiKeyInput) return item
          if (!item.apiKeyDirty && !item.apiKeyCleared) return item
          return { ...item, apiKeyDirty: false, apiKeyCleared: false }
        }),
      )

      if (secretsError) {
        // 密钥保存失败不该让整个保存动作失败，但必须让用户知道
        console.error('[settings] 密钥加密保存失败', secretsError)
        setMessage({
          tone: 'error',
          text: '模型配置已保存，但密钥写入加密存储失败，重启后可能需要重新填写。',
        })
        return false
      }

      // 服务端已确认的内容签名：自动保存据此判断还有没有未落盘的改动。
      lastSavedRef.current = draftSignature(list)
      setMessage({ tone: 'ok', text: '已保存' })
      return true
    } catch (error) {
      setMessage({
        tone: 'error',
        text: error instanceof Error ? error.message : String(error),
      })
      return false
    } finally {
      // 自动保存模式：状态由 autoSaveState 呈现，这里无需额外复位
    }
  }

  /**
   * 「保存并测试连通性」。
   *
   * ⚠️ 以前是**先保存、再测试**（`await save()` 之后才 `testModel`）。后果是
   * 用户看到的"测个连接要十几秒"里，绝大部分其实是**保存**的耗时
   * （后端每次保存都要重建全部模型客户端，实测 3 个模型 1.5 秒且阻塞事件循环）。
   * 而界面显示的"延迟 100ms"只统计了测试请求本身 —— 两件事根本不可比，
   * 于是留下"明明 100ms 为什么要等十几秒"这个说不通的观感。
   *
   * 现在两件事**并行**：测试直接用输入框里的 Key 构造 spec 发给后端
   * （``POST /v1/models/test`` 本来就支持直接收 spec），不必等保存完成，
   * 网络一有结果立刻显示。
   */
  const saveAndTest = async (index: number) => {
    const target = draft[index]
    if (!api) return
    setDraft((list) =>
      list.map((model, i) => (i === index ? { ...model, testState: { status: 'testing' } } : model)),
    )

    // 输入框里没有明文、但这条已经配过 Key 时，**不能**拿空 Key 去测
    // （那样必然鉴权失败，而用户并没有做错什么）。退回"让后端用已保存的 Key 测"。
    const useTypedSpec = Boolean(target.apiKeyInput) || !target.has_api_key
    const testPromise: Promise<ModelTestOutcome> = useTypedSpec
      ? api.testModel({ spec: modelPayload([target], target.id).models[0] })
      : api.testModel({ model_id: target.id })

    const [, result] = await Promise.all([
      // 保存失败不影响测试结论（两件事已经解耦），保存自己的报错走 message 显示
      save(),
      testPromise.catch(
        (error): ModelTestOutcome => ({
          ok: false,
          error: error instanceof Error ? error.message : String(error),
        }),
      ),
    ])

    setDraft((list) =>
      list.map((model, i) =>
        i === index
          ? {
              ...model,
              // ⚠️ 这里也要走过滤（点「保存并测试连通性」会
              // 把硅基流动的全部模型刷出来）。它和「获取模型」「同步整组模型」
              // 是**第三条**写 `availableModels` 的路径 —— 前两条都过滤了，
              // 漏掉这条就等于过滤形同虚设（用户看到的清单取决于他点了哪个按钮）。
              availableModels: result.ok
                ? filterDiscoveredModels(model.base_url.trim(), result.models ?? [])
                : model.availableModels,
              testState: result.ok
                ? {
                    status: 'ok',
                    message:
                      result.warning ??
                      (result.latency_ms !== undefined ? `${result.latency_ms} ms` : undefined),
                  }
                : { status: 'fail', message: result.error ?? '连接失败' },
            }
          : model,
      ),
    )
  }

  /**
   * 把「服务商真实提供的模型清单」应用到本地草稿。
   *
   * 设计要点（这是整个同步里最关键的一段）：
   * - **锚点 = 该服务商组里的默认条目（没有默认就取第一条），id 不变**。
   *   真实 Key 只在后端（前端只有脱敏预览），锚点 id 不变，它的 Key 就走
   *   `api_key_unchanged` 原样保留。若锚点的模型名已不再提供，让它顶上
   *   真实清单的第一个 —— 依旧不动 id。
   * - 其余真实清单里的模型：同名条目保留（不动 id），缺的克隆锚点新增，
   *   用 `inherit_key_from` 让**后端**把锚点的 Key 复制过来（前端拿不到明文，
   *   想带也带不了 —— 这就是为什么要做一个后端字段而不是在前端传 Key）。
   * - 真实清单里没有的条目**直接删除**（产品明确要求的语义），
   *   Key 已经由锚点持有，不会被带走。
   */
  const applySync = async (live: string[]): Promise<void> => {
    if (!activeGroup) {
      setSync({ key: null, status: 'error', message: '当前没有选中的服务商，无法应用同步结果。' })
      return
    }
    const liveNames = Array.from(new Set(live.map((name) => name.trim()).filter(Boolean)))
    // 记住"这份结果属于哪家"：下面 setSelectedKey 会改选中态，但分组的 key
    // （provider|base_url）不变，所以这个值在同步完成后依然对得上。
    const groupKey = activeGroup.key
    const group = activeGroup.models
    const others = draft.filter((model) => !group.includes(model))
    // baseName 用预设名（服务商名），克隆出来的条目才能都叫 "DeepSeek · xxx"
    const baseName = activeGroup.name

    const anchorSource = group.find((model) => model.is_default) ?? group[0]
    let anchor = { ...anchorSource }
    let removedCount = 0
    if (liveNames.length === 0) {
      setSync({
        key: groupKey,
        status: 'error',
        message: '该服务商当前没有返回任何模型，未做改动。',
      })
      return
    }
    if (!liveNames.includes(anchor.model_name)) {
      anchor = {
        ...anchor,
        model_name: liveNames[0],
        name: `${baseName} · ${liveNames[0]}`,
        display_name: `${baseName} · ${liveNames[0]}`,
      }
    }
    // 默认模型条目被同步删掉时，把默认挪到锚点上，避免 default 指向空气
    if (!liveNames.includes(anchorSource.model_name) && group.some((model) => model.is_default)) {
      anchor = { ...anchor, is_default: true }
    }

    const covered = new Set([anchor.model_name])
    const kept: Draft[] = []
    const added: Draft[] = []
    for (const name of liveNames) {
      if (covered.has(name)) continue
      const existing = group.find((model) => model.model_name === name && model.id !== anchor.id)
      if (existing) {
        covered.add(name)
        kept.push(existing)
        continue
      }
      let index = 1
      let id = `${anchor.provider}-${index}`
      while (draft.some((model) => model.id === id) || added.some((model) => model.id === id)) {
        index += 1
        id = `${anchor.provider}-${index}`
      }
      added.push({
        ...anchor,
        id,
        model_name: name,
        name: `${baseName} · ${name}`,
        display_name: `${baseName} · ${name}`,
        inherit_key_from: anchor.id,
        is_default: false,
        // Key 状态不跟着克隆：它是**新条目**，还没有自己的密钥。
        // 密钥由 save() 按 inherit_key_from 从锚点复制过去（前端不传明文）。
        apiKeyInput: '',
        apiKeyDirty: false,
        apiKeyCleared: false,
        // ⚠️ 同步新增的条目**必须显式启用**（实测反馈 #12）：以前靠 `...anchor`
        // 继承，锚点若没启用，新增的一整批都处于停用态，对话下拉里根本看不到
        // （ModelSelector 只列 `enabled` 的模型）。
        enabled: true,
        // 备用链与默认状态都是"那一条模型自己的配置"，不该跟着克隆
        fallback_models: [],
        price_input_per_1m: null,
        price_cached_input_per_1m: null,
        price_output_per_1m: null,
      })
    }
    removedCount = group.filter(
      (model) =>
        model.id !== anchorSource.id &&
        model.model_name !== anchor.model_name &&
        !liveNames.includes(model.model_name),
    ).length

    // 同步到的清单要记在**组内每一个条目**上：服务商头的「模型」下拉与编辑卡的
    // 候选列表都从这份数据派生，两处才会同时有值（用户要的"两个下拉都正确"）。
    const tagged = (model: Draft): Draft => ({ ...model, availableModels: liveNames })
    const next = [...others, tagged(anchor), ...kept.map(tagged), ...added.map(tagged)]
    setDraft(next)
    // 选中状态跟着服务商走：预设服务商用 p: 键，自建端点用「锚点模型 id」
    setSelectedKey(activePreset ? presetKey(activePreset.provider) : `g:${anchor.id}`)
    setSync({
      key: groupKey,
      status: 'done',
      // 落盘交给统一的自动保存（draft 变化即触发）
      message: `同步完成：新增 ${added.length} 个、移除 ${removedCount} 个。`,
    })
  }

  /**
   * 「同步模型」：拉该服务商真实提供的模型清单，并据此重排这一组条目（applySync）。
   *
   * 与编辑卡的「获取模型」用**同一个接口**（`/v1/models/discover`），只是它多一步
   * "把清单应用回草稿"。之所以不用 `/v1/models/sync`：那个接口要传**已保存**的
   * model_id，去已落盘的配置里查，而这个页面是边填边自动保存的 —— 草稿还没落盘时
   * 它必然 404（用户看到的就是"点了没反应"）。
   */
  const runSync = async (): Promise<void> => {
    if (!activeGroup) {
      setSync({ key: null, status: 'error', message: '当前没有选中的服务商。' })
      return
    }
    if (!api) {
      setSync({ key: activeGroup.key, status: 'error', message: '后端还没连接上，稍后重试。' })
      return
    }
    const anchor = activeGroup.models.find((model) => model.is_default) ?? activeGroup.models[0]
    if (!anchor) {
      setSync({ key: activeGroup.key, status: 'error', message: '这家服务商还没有可用的模型条目。' })
      return
    }
    if (!anchor.base_url.trim()) {
      setSync({ key: activeGroup.key, status: 'error', message: '请先填写接口地址再同步。' })
      return
    }
    setSync({ key: activeGroup.key, status: 'busy' })
    try {
      const result = await api.discoverModels({
        base_url: anchor.base_url.trim(),
        api_key: anchor.apiKeyInput.trim(),
      })
      // ⚠️ 必须与「获取模型」走**同一个**过滤。
      //
      // 这里原来直接把原始清单交给 `applySync`，于是硅基流动点「同步整组模型」
      // 会把这家广场上的 Qwen / GLM / Kimi 全都拉进草稿 —— 而用户要的是
      // "这家只留 deepseek"。同一个过滤规则在两个入口表现不一致，是最难被
      // 用户理解的一类 bug（"我在那边看到的是对的，这边又变了"）。
      //
      // 过滤函数**内部**先判断 base_url 是不是硅基流动（不是就原样返回），
      // 所以对其它服务商没有任何副作用。
      await applySync(filterDiscoveredModels(anchor.base_url.trim(), result.models ?? []))
    } catch (error) {
      // ⚠️ 无论成功失败都必须写终态：留在 busy 会让按钮**永久禁用**，
      // 这正是"同步模型按钮点了没反应"的一半原因。
      setSync({
        key: activeGroup.key,
        status: 'error',
        message: error instanceof Error ? error.message : String(error),
      })
    }
  }

  // ---- 自动保存（产品要求：整个应用不再手动点保存）------------------------
  // draft 变化 → 300ms 防抖 → 整份提交。**必须防循环**：save 成功后会
  // reloadModels → 重新播种 draft → 又触发本 effect。判据是**内容签名**
  // （见 draftSignature：纯前端簿记字段不参与，否则点一次"测试"、
  // 或保存成功后复位脏标记，都会引发一轮无意义保存）。
  const [autoSaveState, setAutoSaveState] = useState<'idle' | 'saving' | 'saved'>('idle')

  /**
   * **串行化 + 合并**的自动保存。
   *
   * **为什么必须串行**：`save()` 提交的是整份模型列表。两个并发的 save 会互相
   * 覆盖（后发的那份可能基于更旧的快照），而且各自都会 `reloadModels()` 一次，
   * 把草稿来回重建两遍 —— 表现就是"保存中"迟迟不结束。
   *
   * **为什么要合并**：保存进行中又来了新改动时，不排队等第二次，而是记一个标记，
   * 当前这次结束后立刻再存一次**最新**的草稿。连续打字因此只会产生一次尾随保存，
   * 而不是攒出 N 次。
   */
  const runAutoSave = async () => {
    if (autoSaveBusyRef.current) {
      autoSavePendingRef.current = true
      return
    }
    autoSaveBusyRef.current = true
    let lastOk = true
    try {
      do {
        autoSavePendingRef.current = false
        setAutoSaveState('saving')
        // 签名由 save() 自己在成功时写入（用的是**真正提交的那份**内容），
        // 不在调用处用闭包里的 draft 去算 —— 那样会把"保存期间用户新打的字"
        // 误标成已保存。
        lastOk = await save()
      } while (autoSavePendingRef.current)
      setAutoSaveState(lastOk ? 'saved' : 'idle')
    } finally {
      autoSaveBusyRef.current = false
    }
  }

  useEffect(() => {
    // 还没从服务端播种完 → 手上这份草稿是空的/不全的，**绝不能**拿去覆盖服务端
    if (!hydratedRef.current) return
    const signature = draftSignature(draft)
    if (signature === lastSavedRef.current) return
    if (saveTimerRef.current !== null) window.clearTimeout(saveTimerRef.current)
    saveTimerRef.current = window.setTimeout(() => void runAutoSave(), 300)
    return () => {
      if (saveTimerRef.current !== null) window.clearTimeout(saveTimerRef.current)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [draft])

  return (
    <div className="max-w-[880px]">
      <div className="flex items-start gap-4">
        <div className="flex-1">
          <h2 className="text-[15px] font-semibold text-ink">模型服务商</h2>
          <p className="mt-1 text-[12.5px] leading-relaxed text-ink-soft">
            所有 OpenAI 兼容端点（DeepSeek、通义、Kimi、智谱等）
            都可以用同一套配置接入。
          </p>
        </div>
        {/* 状态小字**固定最小宽度**：三个状态字数不同，宽度一变会牵动标题段落
            换行（用户实测"页面跳动"）。固定后只有颜色变化、没有布局变化。 */}
        <span
          className={clsx(
            'shrink-0 pt-1 text-right text-[11.5px] whitespace-nowrap',
            autoSaveState === 'saved' ? 'text-success' : 'text-ink-faint',
          )}
          style={{ minWidth: 76 }}
        >
          {autoSaveState === 'saving' ? '保存中…' : autoSaveState === 'saved' ? '已自动保存' : ''}
        </span>
      </div>

      {message && message.tone !== 'ok' ? (
        <div
          className={clsx(
            'mt-3 rounded-[8px] border px-3 py-2 text-[12.5px]',
            message.tone === 'error'
              ? 'border-danger/30 bg-danger-soft text-danger'
              : 'border-warning/30 bg-warning-soft text-warning',
          )}
        >
          {message.text}
        </div>
      ) : null}

      <ModelWizard
        open={wizardOpen}
        presets={presets}
        onClose={() => setWizardOpen(false)}
        onSubmit={async (result) => {
          // 用与「快速添加」同一个构造函数，保证字段不落后
          const created = newModelFromPreset(result.preset, draft)
          const model: Draft = {
            ...created,
            name: `${result.preset.name} · ${result.modelName}`,
            model_name: result.modelName,
            base_url: result.baseUrl || created.base_url,
            // 向导里是新输入的 Key，所以它一定是"改过的" —— 明确标记，
            // 否则后端会按"未修改"处理，用户刚填的 Key 就不会写进去
            api_key: result.apiKey,
            apiKeyInput: result.apiKey,
            apiKeyDirty: Boolean(result.apiKey),
            apiKeyMask: '',
            has_api_key: Boolean(result.apiKey),
            // 第一个模型自动设为默认：否则用户配完了还得再找一次"设为默认"
            is_default: draft.length === 0,
          }
          // 落盘交给自动保存；选中跳到新服务商，让用户接着调
          setDraft([...draft, model])
          setSelectedKey(presetKey(result.preset.provider))
        }}
      />

      {/* ---- 服务商中心两栏：左列九家预设（含未配置），右侧选中那家的配置 ---- */}
      <div className="mt-5 flex items-start gap-4">
        <div className="flex w-[224px] shrink-0 flex-col rounded-[10px] border border-line bg-panel p-1.5">
          {/*
            ⚠️ 这里原先是「搜索服务商」输入框，按产品要求**剔除**。
            内置服务商只有个位数，一屏就看完 —— 搜索框在这种量级下不是功能，
            是一块占位。加回时记得同时恢复 `filter`/`keyword` 与 visible* 的过滤。
          */}

          <div className="max-h-[520px] min-h-0 space-y-0.5 overflow-y-auto">
            {visiblePresets.map((preset) => {
              const group = providerGroups.find((item) => item.key === groupKeyOf(preset))
              const key = presetKey(preset.provider)
              const active =
                selectedKey === key ||
                (selectedKey === null && activeGroup?.key === group?.key && group != null)
              return (
                // ⚠️ 列表行**故意只放名字**（看过一版"每行都带申请链接"的，
                // 明确指了红框说位置不对：申请页链接要放**右侧这个服务商独立页面的标题后面**，
                // 不是列表行）。列表本来就只有 224px，塞了链接会把名字挤断
                // （"硅基流动（领16…"、"Anthropic（Cla…"）——列表要的是扫得快。
                <button
                  key={preset.provider}
                  type="button"
                  onClick={() => setSelectedKey(key)}
                  className={clsx(
                    'flex w-full items-center gap-2 rounded-[7px] px-2 py-1.5 text-left transition-colors',
                    active ? 'bg-brand-soft text-brand' : 'text-ink-soft hover:bg-hover hover:text-ink',
                  )}
                >
                  <span
                    className={clsx(
                      'h-1.5 w-1.5 shrink-0 rounded-full',
                      group && isGroupUsable(group) ? 'bg-success' : 'bg-ink-faint',
                    )}
                    title={
                      group && isGroupUsable(group)
                        ? '已配置并可用'
                        : '尚未配置完成（点了「添加」但还没填 Key / 测试通过）'
                    }
                  />
                  <span className="min-w-0 flex-1 truncate text-[12px]" title={preset.name}>
                    {preset.name}
                  </span>
                  {group?.hasDefault ? (
                    <span className="shrink-0 text-[10px] text-brand">默认</span>
                  ) : null}
                </button>
              )
            })}

            {visibleCustomGroups.length > 0 ? (
              <>
                <div className="px-2 pt-2 pb-1 text-[10.5px] font-medium text-ink-faint">
                  自定义端点
                </div>
                {visibleCustomGroups.map((group) => {
                  const active = customGroupSelectKey(group) === selectedKey
                  return (
                    <button
                      key={group.key}
                      type="button"
                      onClick={() => setSelectedKey(customGroupSelectKey(group))}
                      className={clsx(
                        'flex w-full items-center gap-2 rounded-[7px] px-2 py-1.5 text-left transition-colors',
                        active
                          ? 'bg-brand-soft text-brand'
                          : 'text-ink-soft hover:bg-hover hover:text-ink',
                      )}
                    >
                      <span
                        className={clsx(
                          'h-1.5 w-1.5 shrink-0 rounded-full',
                          group.anyEnabled ? 'bg-success' : 'bg-ink-faint',
                        )}
                      />
                      <span className="min-w-0 flex-1 truncate text-[12px]">{group.name}</span>
                    </button>
                  )
                })}
              </>
            ) : null}

            {visiblePresets.length === 0 && visibleCustomGroups.length === 0 ? (
              <p className="px-2 py-3 text-[11.5px] leading-relaxed text-ink-faint">
                没有匹配的服务商。
              </p>
            ) : null}
          </div>
          {/* 「+ 添加服务商」放在列表**底部**（产品要求）：它是"往这个列表里加一个"，
              放页面底部离列表太远，用户找不着 */}
          <div className="mt-1.5 border-t border-line-soft pt-1.5">
            <Button
              size="sm"
              icon={<Plus size={12} />}
              className="w-full"
              onClick={() => addCustomProvider()}
            >
              添加服务商
            </Button>
          </div>
        </div>

        <div className="min-w-0 flex-1">
          {activePreset || activeGroup ? (
            <>
              {/* 服务商头：名称 + 地址 + 同步按钮 */}
              <div className="rounded-[10px] border border-line bg-panel px-3.5 py-3">
                <div className="flex items-center justify-between gap-3">
                  <div className="min-w-0">
                    {/* 「申请 API」就摆在**这个服务商标题后面**（画红框
                        指定的位置）：进这一页就能看见，不必先点「添加」。
                        样式与首启引导页那颗一致（产品要求的高亮 + 边框，
                        同一个动作在两个页面长得一样）。 */}
                    <div className="flex items-center gap-2">
                      <span className="whitespace-nowrap text-[13px] font-semibold text-ink">
                        {activePreset?.name ?? activeGroup?.name}
                      </span>
                      {activeApplyUrl ? (
                        <>
                          <button
                            type="button"
                            onClick={() => void window.agentBridge?.openExternal(activeApplyUrl)}
                            title={`用默认浏览器打开申请页：${activeApplyUrl}`}
                            className="flex shrink-0 items-center gap-1 rounded-[6px] border border-brand/40 bg-brand-soft px-2 py-0.5 text-[11.5px] font-medium text-brand transition-colors hover:border-brand hover:opacity-90 focus-visible:ring-2 focus-visible:ring-brand/60 focus-visible:outline-none"
                          >
                            申请 API
                            <ExternalLink size={11} />
                          </button>
                          {/* 复制链接（原先在模型卡里，已挪上来 —— 整页只留这一处入口） */}
                          <button
                            type="button"
                            onClick={() => void copyApplyUrl()}
                            className="flex h-6 w-6 shrink-0 items-center justify-center rounded-[6px] text-ink-faint transition-colors hover:bg-hover hover:text-ink focus-visible:ring-2 focus-visible:ring-brand/60 focus-visible:outline-none"
                            aria-label="复制申请链接"
                            title="复制申请链接"
                          >
                            {applyCopied ? <Check size={12} className="text-success" /> : <Copy size={12} />}
                          </button>
                        </>
                      ) : null}
                    </div>
                    <p
                      className="mt-0.5 w-full truncate text-[11px] text-ink-faint"
                      title={activePreset?.base_url ?? activeGroup?.baseUrl}
                    >
                      {activePreset?.base_url ?? activeGroup?.baseUrl}
                    </p>
                  </div>
                  {activeGroup ? (
                    /*
                      ⚠️ 文案从「同步模型」改成「同步整组模型」。

                      问"同步模型和获取模型两个按钮是否冲突，冲突就只留
                      获取模型"。查下来**不冲突**：两者调同一个接口，但这个是把**整组**
                      与真实清单对齐（多出来的条目会**新增**、清单里没有的会**删除**、
                      Key 跨条目继承），而卡片里那个「获取模型」只填当前这一条的候选、
                      不动任何条目。删掉它等于丢掉"一键把服务商下所有模型补齐"的能力。

                      既然留着，就必须让区别一眼可见 —— 原名和「获取模型」太像，
                      看起来像同一件事的两个入口。
                    */
                    <Button
                      size="sm"
                      variant="secondary"
                      className="shrink-0"
                      title="用这家服务商当前可用的模型清单，把整组条目对齐（新增缺失、删除下架）"
                      icon={
                        activeSync?.status === 'busy' ? (
                          <Loader2 size={13} className="animate-spin" />
                        ) : (
                          <RefreshCw size={13} />
                        )
                      }
                      onClick={() => void runSync()}
                      disabled={activeSync?.status === 'busy'}
                    >
                      同步整组模型
                    </Button>
                  ) : null}
                </div>

                {/* **模型下拉**（产品要求）：一个服务商一张配置卡，模型用下拉选 */}
                <div className="mt-3">
                  <div className="mb-1 text-[12px] text-ink-soft">模型</div>
                  <Select
                    value={activeEntry?.model_name ?? ''}
                    onChange={(event) => {
                      if (!activeEntry) return
                      const index = draft.indexOf(activeEntry)
                      const modelName = event.target.value
                      patch(index, {
                        model_name: modelName,
                        name: `${activePreset?.name ?? activeGroup?.name ?? ''} · ${modelName}`.trim(),
                        display_name: `${activePreset?.name ?? activeGroup?.name ?? ''} · ${modelName}`.trim(),
                      })
                    }}
                    className="min-w-0 flex-1"
                  >
                    {(() => {
                      // 选项优先级：已发现的真实清单 > 预设清单 > 当前值。
                      // `discoveredModels` 是组内并集，三处取模型动作写进去的都是它，
                      // 所以这里与编辑卡下方那份候选列表**永远一致**。
                      const options =
                        discoveredModels.length > 0
                          ? discoveredModels
                          : activePreset && activePreset.models.length > 0
                            ? activePreset.models
                            : activeEntry
                              ? [activeEntry.model_name]
                              : []
                      const all = activeEntry?.model_name
                        ? [activeEntry.model_name, ...options]
                        : options
                      return [...new Set(all.filter(Boolean))].map((name) => (
                        <option key={name} value={name}>
                          {name}
                        </option>
                      ))
                    })()}
                  </Select>
                  <p className="mt-1 text-[11px] leading-relaxed text-ink-faint">
                    {activeGroup
                      ? '点「同步模型」（或编辑卡里的「获取模型」）拉取该服务商真实提供的模型。'
                      : '先在下方添加并填好 Key，再点「同步模型」获取实时清单。'}
                  </p>
                  {activeSync?.message ? (
                    <p
                      className={clsx(
                        'mt-1 text-[11.5px] leading-relaxed',
                        activeSync.status === 'error' ? 'text-danger' : 'text-ink-soft',
                      )}
                    >
                      {activeSync.message}
                    </p>
                  ) : null}
                </div>
              </div>

              {activeEntry ? (
                <>
                  {/* 该服务商的配置卡（Key / 高级参数 / 测试） */}
                  <ModelCard
                    key={activeEntry.id}
                    model={activeEntry}
                    presets={presets}
                    onChange={(changes) => patch(draft.indexOf(activeEntry), changes)}
                    onRemove={() => setDeletePrompt({ model: activeEntry })}
                    onTest={() => void saveAndTest(draft.indexOf(activeEntry))}
                  />

                  {/* 历史遗留的同服务商多模型条目：列出来可删，不再各占一行 */}
                  {activeGroup && activeGroup.models.length > 1 ? (
                    <div className="mt-3 rounded-[10px] border border-line-soft px-3.5 py-2.5">
                      <div className="text-[11.5px] text-ink-faint">
                        该服务商下的其他模型条目（不再单独展示，可删除多余的）
                      </div>
                      <div className="mt-1.5 flex flex-col gap-1">
                        {activeGroup.models
                          .filter((model) => model !== activeEntry)
                          .map((model) => (
                            <div key={model.id} className="flex items-center gap-2">
                              <span className="min-w-0 flex-1 truncate text-[12px] text-ink-soft">
                                {model.model_name || model.id}
                              </span>
                              <Button
                                size="sm"
                                variant="secondary"
                                onClick={() => setDeletePrompt({ model })}
                              >
                                删除
                              </Button>
                            </div>
                          ))}
                      </div>
                    </div>
                  ) : null}
                </>
              ) : activePreset ? (
                /* 该服务商还没配置：一个明确的启用入口 */
                <div className="mt-3 rounded-[10px] border border-dashed border-line px-4 py-8 text-center">
                  <p className="text-[12.5px] text-ink-soft">
                    这个服务商还没有配置。点下面添加，然后填入 API Key 即可使用。
                  </p>
                  <Button
                    variant="primary"
                    className="mt-3"
                    icon={<Plus size={13} />}
                    onClick={() => addModel(activePreset)}
                  >
                    添加 {activePreset.name}
                  </Button>
                </div>
              ) : null}
            </>
          ) : (
            <div className="rounded-[10px] border border-dashed border-line px-4 py-10 text-center text-[12.5px] text-ink-faint">
              从左侧选择一个服务商开始配置。
            </div>
          )}
        </div>
      </div>

      <div className="mt-4 flex items-center gap-2">
        <Button
          size="sm"
          icon={<Zap size={12} />}
          onClick={() => setWizardOpen(true)}
        >
          用向导添加服务商
        </Button>
        <span className="text-[11.5px] text-ink-faint">
          不确定怎么填？向导会一步一步带你：选服务商 → 粘 Key → 选模型 → 测试。
        </span>
      </div>

      <div className="mt-4 rounded-[8px] border border-line bg-panel px-3.5 py-2.5 text-[12px] leading-relaxed text-ink-soft">
        若你的网络需要代理才能访问某家厂商，可在该模型的高级设置里打开
        「使用系统代理」。
      </div>

      {/* 删除模型前先问：删单个还是删整个服务商（避免"只能一个个删"） */}
      <Modal
        open={deletePrompt !== null}
        onClose={() => setDeletePrompt(null)}
        width="max-w-sm"
        title="删除模型"
        description="只删这一个，还是把整个服务商一起删掉？"
        footer={
          <>
            <Button onClick={() => setDeletePrompt(null)}>取消</Button>
            <Button variant="secondary" onClick={removeSingleModel}>
              删除单个
            </Button>
            <Button variant="primary" onClick={removeWholeProvider}>
              删除整个服务商
            </Button>
          </>
        }
      >
        <p className="text-[12.5px] leading-relaxed text-ink-soft">
          当前条目：{deletePrompt?.model.model_name || deletePrompt?.model.id}
          <br />
          「删除整个服务商」会移除该服务商下的**所有**模型，且不可撤销。
        </p>
      </Modal>
    </div>
  )
}
