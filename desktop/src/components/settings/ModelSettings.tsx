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

import { filterDiscoveredModels } from '@/components/settings/modelFilter'
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
    
    
    
    
    
    token_limit: preset.token_limit ?? 131072,
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
    price_cached_input_per_1m_peak: null,
    price_output_per_1m_peak: null,
    peak_windows: [],
    testState: { status: 'idle' },
  }
}







function parsePrice(value: string): number | null {
  const trimmed = value.trim()
  if (!trimmed) return null
  const parsed = Number(trimmed)
  if (!Number.isFinite(parsed) || parsed < 0) return null
  return parsed
}












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


const TIME_OPTIONS = Array.from({ length: 48 }, (_, i) => {
  const h = String(Math.floor(i / 2)).padStart(2, '0')
  const m = i % 2 === 0 ? '00' : '30'
  return `${h}:${m}`
})

const WEEKDAY_LABELS = ['周一', '周二', '周三', '周四', '周五', '周六', '周日']

const PEAK_SLOTS = ['早高峰', '晚高峰', '自定义高峰']


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
  
  const [confirmClear, setConfirmClear] = useState(false)
  
  const [fetching, setFetching] = useState(false)
  const [fetchNote, setFetchNote] = useState<{ tone: 'ok' | 'error'; text: string } | null>(null)
  const testing = model.testState?.status === 'testing'
  
  const allModels = useAppStore((state) => state.models)
  const api = useAppStore((state) => state.api)

  
  
  
  
  
  
  
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
        
        if (latestInputRef.current) return
        onChange({ apiKeyInput: value, apiKeyDirty: false, apiKeyCleared: false })
      } catch {
        
      }
    })()
    return () => {
      cancelled = true
    }
    
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
  











  const modelOptions =
    (model.availableModels?.length ?? 0) > 0
      ? Array.from(new Set(model.availableModels))
      : Array.from(new Set(preset?.models ?? []))

  







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
      
      
      
      const list = filterDiscoveredModels(model.base_url.trim(), result.models ?? [])
      if (list.length === 0) {
        
        setFetchNote({ tone: 'error', text: '该地址没有返回模型列表，可在输入框手动填写。' })
        return
      }
      const patch: Partial<Draft> = { availableModels: list }
      
      
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
          
          
          <Badge tone="warning">输入框已空：已保存的密钥仍然有效</Badge>
        ) : null}

        {


}
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
          {

}
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
            {
}
            <Input
              type="text"
              value={model.apiKeyInput}
              onChange={(event) =>
                onChange({
                  apiKeyInput: event.target.value,
                  apiKeyDirty: true,
                  
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
            {









}
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

        {
}
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

        {


}
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

      {}
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

        {}
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

        {}
        <div className="mt-1.5 flex items-center gap-1.5 text-[12px] text-ink-soft">
          <span className="w-[56px] shrink-0">周几</span>
          {




}
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

        {}
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
  
  const hydratedRef = useRef(false)
  
  const lastSavedRef = useRef('')
  
  const saveTimerRef = useRef<number | null>(null)
  
  const latestDraftRef = useRef<Draft[]>([])
  latestDraftRef.current = draft
  
  const autoSaveBusyRef = useRef(false)
  
  const autoSavePendingRef = useRef(false)
  const [wizardOpen, setWizardOpen] = useState(false)
  const [message, setMessage] = useState<{
    
    
    tone: 'ok' | 'warning' | 'error'
    text: string
  } | null>(null)
  
  
  
  const [selectedKey, setSelectedKey] = useState<string | null>(null)
  
  
  
  
  
  
  const [sync, setSync] = useState<{
    key: string | null
    status: 'idle' | 'busy' | 'done' | 'error'
    message?: string
  }>({ key: null, status: 'idle' })

  
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

  
  
  
  
  const isGroupUsable = (group: { models: Draft[] }): boolean =>
    group.models.some(
      (model) =>
        model.enabled &&
        (model.has_api_key || /^https?:\/\/(127\.0\.0\.1|localhost)/i.test(model.base_url)),
    )
  const presetKey = (provider: string) => `p:${provider}`
  const groupKeyOf = (preset: ProviderPreset) => `${preset.provider}|${preset.base_url}`
  
  const providerGroupKey = (model: Draft) => `${model.provider}|${model.base_url}`
  



  const customGroupSelectKey = (group: ProviderGroup) =>
    `g:${(group.models.find((item) => item.is_default) ?? group.models[0])?.id ?? ''}`
  const customGroups = providerGroups.filter(
    (group) => !presets.some((p) => groupKeyOf(p) === group.key),
  )
  
  
  
  const visiblePresets = presets
  const visibleCustomGroups = customGroups

  
  
  
  
  
  
  
  
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
  







  const activeApplyUrl: string = activePreset ? activePreset.apply_url || activePreset.docs || '' : ''
  











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
  
  const activeEntry: Draft | null = activeGroup
    ? activeGroup.models.find((model) => model.is_default) ?? activeGroup.models[0]
    : null

  
  const removeSingleModel = () => {
    if (!deletePrompt) return
    setDraft((list) => list.filter((item) => item !== deletePrompt.model))
    setDeletePrompt(null)
  }
  
  const removeWholeProvider = () => {
    if (!deletePrompt) return
    const key = providerGroupKey(deletePrompt.model)
    setDraft((list) => list.filter((item) => providerGroupKey(item) !== key))
    setDeletePrompt(null)
  }

  






  const discoveredModels = activeGroup
    ? Array.from(new Set(activeGroup.models.flatMap((model) => model.availableModels ?? [])))
    : []
  
  const activeSync = activeGroup && sync.key === activeGroup.key ? sync : null

  
  
  
  
  
  
  
  
  
  
  
  
  
  
  useEffect(() => {
    let cancelled = false
    
    
    void (async () => {
      let keys: Record<string, string> = {}
      try {
        keys = (await window.agentBridge?.getSecretsMasked())?.models ?? {}
      } catch {
        
      }
      if (cancelled) return
      
      
      
      const previousById = new Map(latestDraftRef.current.map((item) => [item.id, item]))
      const next: Draft[] = models.map((model) => {
        const before = previousById.get(model.id)
        return {
          ...model,
          
          apiKeyMask: keys[model.id] ?? model.api_key,
          
          
          
          
          
          
          
          apiKeyInput: before?.apiKeyInput ?? model.api_key ?? '',
          apiKeyDirty: before?.apiKeyDirty ?? false,
          
          
          apiKeyCleared: (before?.apiKeyCleared ?? false) && model.has_api_key,
          apiKeyRevealed: before?.apiKeyRevealed ?? false,
          
          testState: before?.testState ?? { status: 'idle' as const },
          availableModels: before?.availableModels,
        }
      })
      
      
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
          
          return changes.is_default ? { ...model, is_default: false } : model
        }
        return { ...model, ...changes, testState: { status: 'idle' as const } }
      }),
    )
  }

  const addModel = (preset: ProviderPreset) => {
    setDraft((list) => [...list, newModelFromPreset(preset, list)])
  }

  
  
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
    
    
    setSelectedKey(`g:${model.id}`)
  }

  






  const save = async (list: Draft[] = draft): Promise<boolean> => {
    if (!api) return false
    setMessage(null)

    
    
    
    
    
    
    
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
      
      
      
      const payload = modelPayload(list, chosenDefault)
      await api.saveModels(payload)

      
      
      
      
      
      
      
      
      
      
      const keyed: Record<string, string> = {}
      const removeIds: string[] = []
      for (const model of list) {
        if (model.apiKeyCleared) {
          
          removeIds.push(model.id)
          continue
        }
        if (model.apiKeyDirty && model.apiKeyInput) {
          keyed[model.id] = model.apiKeyInput
          continue
        }
        
        
        
        
        if (model.inherit_key_from) {
          const source = list.find((item) => item.id === model.inherit_key_from)
          if (source?.apiKeyInput) keyed[model.id] = source.apiKeyInput
        }
      }
      
      
      
      
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
        
        console.error('[settings] 密钥加密保存失败', secretsError)
        setMessage({
          tone: 'error',
          text: '模型配置已保存，但密钥写入加密存储失败，重启后可能需要重新填写。',
        })
        return false
      }

      
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
      
    }
  }

  












  const saveAndTest = async (index: number) => {
    const target = draft[index]
    if (!api) return
    setDraft((list) =>
      list.map((model, i) => (i === index ? { ...model, testState: { status: 'testing' } } : model)),
    )

    
    
    const useTypedSpec = Boolean(target.apiKeyInput) || !target.has_api_key
    const testPromise: Promise<ModelTestOutcome> = useTypedSpec
      ? api.testModel({ spec: modelPayload([target], target.id).models[0] })
      : api.testModel({ model_id: target.id })

    const [, result] = await Promise.all([
      
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

  













  const applySync = async (live: string[]): Promise<void> => {
    if (!activeGroup) {
      setSync({ key: null, status: 'error', message: '当前没有选中的服务商，无法应用同步结果。' })
      return
    }
    const liveNames = Array.from(new Set(live.map((name) => name.trim()).filter(Boolean)))
    
    
    const groupKey = activeGroup.key
    const group = activeGroup.models
    const others = draft.filter((model) => !group.includes(model))
    
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
        
        
        apiKeyInput: '',
        apiKeyDirty: false,
        apiKeyCleared: false,
        
        
        
        enabled: true,
        
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

    
    
    const tagged = (model: Draft): Draft => ({ ...model, availableModels: liveNames })
    const next = [...others, tagged(anchor), ...kept.map(tagged), ...added.map(tagged)]
    setDraft(next)
    
    setSelectedKey(activePreset ? presetKey(activePreset.provider) : `g:${anchor.id}`)
    setSync({
      key: groupKey,
      status: 'done',
      
      message: `同步完成：新增 ${added.length} 个、移除 ${removedCount} 个。`,
    })
  }

  







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
      
      
      
      
      
      
      
      
      
      await applySync(filterDiscoveredModels(anchor.base_url.trim(), result.models ?? []))
    } catch (error) {
      
      
      setSync({
        key: activeGroup.key,
        status: 'error',
        message: error instanceof Error ? error.message : String(error),
      })
    }
  }

  
  
  
  
  
  const [autoSaveState, setAutoSaveState] = useState<'idle' | 'saving' | 'saved'>('idle')

  










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
        
        
        
        lastOk = await save()
      } while (autoSavePendingRef.current)
      setAutoSaveState(lastOk ? 'saved' : 'idle')
    } finally {
      autoSaveBusyRef.current = false
    }
  }

  useEffect(() => {
    
    if (!hydratedRef.current) return
    const signature = draftSignature(draft)
    if (signature === lastSavedRef.current) return
    if (saveTimerRef.current !== null) window.clearTimeout(saveTimerRef.current)
    saveTimerRef.current = window.setTimeout(() => void runAutoSave(), 300)
    return () => {
      if (saveTimerRef.current !== null) window.clearTimeout(saveTimerRef.current)
    }
    
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
        {
}
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
          
          const created = newModelFromPreset(result.preset, draft)
          const model: Draft = {
            ...created,
            name: `${result.preset.name} · ${result.modelName}`,
            model_name: result.modelName,
            base_url: result.baseUrl || created.base_url,
            
            
            api_key: result.apiKey,
            apiKeyInput: result.apiKey,
            apiKeyDirty: Boolean(result.apiKey),
            apiKeyMask: '',
            has_api_key: Boolean(result.apiKey),
            
            is_default: draft.length === 0,
          }
          
          setDraft([...draft, model])
          setSelectedKey(presetKey(result.preset.provider))
        }}
      />

      {}
      <div className="mt-5 flex items-start gap-4">
        <div className="flex w-[224px] shrink-0 flex-col rounded-[10px] border border-line bg-panel p-1.5">
          {



}

          <div className="max-h-[520px] min-h-0 space-y-0.5 overflow-y-auto">
            {visiblePresets.map((preset) => {
              const group = providerGroups.find((item) => item.key === groupKeyOf(preset))
              const key = presetKey(preset.provider)
              const active =
                selectedKey === key ||
                (selectedKey === null && activeGroup?.key === group?.key && group != null)
              return (
                
                
                
                
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
          {
}
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
              {}
              <div className="rounded-[10px] border border-line bg-panel px-3.5 py-3">
                <div className="flex items-center justify-between gap-3">
                  <div className="min-w-0">
                    {


}
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
                          {}
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

                {}
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
                  {}
                  <ModelCard
                    key={activeEntry.id}
                    model={activeEntry}
                    presets={presets}
                    onChange={(changes) => patch(draft.indexOf(activeEntry), changes)}
                    onRemove={() => setDeletePrompt({ model: activeEntry })}
                    onTest={() => void saveAndTest(draft.indexOf(activeEntry))}
                  />

                  {}
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

      {}
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
