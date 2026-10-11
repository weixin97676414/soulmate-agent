import clsx from 'clsx'
import { ArrowLeft, ChevronDown, ExternalLink, Loader2, Zap } from 'lucide-react'
import { useEffect, useState } from 'react'

import { ModelPickerField } from '@/components/settings/ModelPickerField'
import { Button, Field, Input, Modal } from '@/components/ui'
import { useAppStore } from '@/stores/appStore'
import type { ProviderPreset } from '@/types'

/** 向导收集到的东西。**真正落库由调用方做**，见组件说明。 */
export interface ModelWizardResult {
  preset: ProviderPreset
  baseUrl: string
  modelName: string
  apiKey: string
}

const STEPS = ['选择服务商', '填密钥、选模型', '测试并保存'] as const

/**
 * 添加服务商的三步向导。
 *
 * ## 为什么只"问"不"存"
 *
 * 落库（模型配置 + 密码）由调用方完成。因为"整份提交要带哪些字段"是**一处**
 * 实现（`ModelSettings` 的 save），向导再写一遍必然会长歪 —— 本项目已经因为
 * 漏字段吃过三次亏（supports_vision、价格三字段、MCP 的 transport）。
 *
 * ## 为什么保留手动输入与高级设置
 *
 * 自动拉取模型列表是"让默认路径最省事"，不是"唯一路径"。部分网关不提供
 * `/models`，或需要额外权限 —— 没有手填兜底的话，用户正好卡在这一步，
 * 而这恰恰是零基础用户最没有能力自救的地方。
 */
export function ModelWizard({
  open,
  presets,
  onClose,
  onSubmit,
}: {
  open: boolean
  presets: ProviderPreset[]
  onClose: () => void
  onSubmit: (result: ModelWizardResult) => Promise<void>
}) {
  const api = useAppStore((state) => state.api)

  const [step, setStep] = useState(0)
  const [preset, setPreset] = useState<ProviderPreset | null>(null)
  const [baseUrl, setBaseUrl] = useState('')
  const [apiKey, setApiKey] = useState('')
  const [modelName, setModelName] = useState('')
  const [advancedOpen, setAdvancedOpen] = useState(false)
  const [busy, setBusy] = useState(false)
  const [test, setTest] = useState<{ ok: boolean; text: string } | null>(null)
  const [error, setError] = useState<string | null>(null)

  // 每次打开都重置：上一次填了一半的密钥留在界面上，既让人困惑也不安全
  useEffect(() => {
    if (!open) return
    setStep(0)
    setPreset(null)
    setBaseUrl('')
    setApiKey('')
    setModelName('')
    setAdvancedOpen(false)
    setBusy(false)
    setTest(null)
    setError(null)
  }, [open])

  const pickPreset = (item: ProviderPreset) => {
    setPreset(item)
    setBaseUrl(item.base_url)
    setModelName(item.models[0] ?? '')
    setApiKey('')
    setTest(null)
    setError(null)
    setStep(1)
  }

  const runTest = async () => {
    if (!api || !preset) return
    setBusy(true)
    setTest(null)
    setError(null)
    try {
      const result = await api.testModel({
        // 用草稿 spec 测试：**不需要先保存**才能验连接。
        // 先存再测会让"填错了"这件事在数据库里留下一条坏配置。
        spec: {
          id: 'wizard-preview',
          name: `${preset.name} · ${modelName}`.trim(),
          provider: preset.provider,
          adapter: preset.adapter ?? 'openai_compat',
          base_url: baseUrl.trim(),
          api_key: apiKey.trim(),
          model_name: modelName.trim(),
          token_limit: preset.token_limit ?? 131072,
        },
      })
      setTest({
        ok: result.ok,
        text: result.ok
          ? `连接成功${result.latency_ms ? `，延迟 ${Math.round(result.latency_ms)} ms` : ''}${
              result.warning ? `。${result.warning}` : ''
            }`
          : (result.error ?? '连接失败，请检查 API Key 与接口地址。'),
      })
    } catch (err) {
      setTest({ ok: false, text: err instanceof Error ? err.message : String(err) })
    } finally {
      setBusy(false)
    }
  }

  const finish = async () => {
    if (!preset) return
    if (!modelName.trim()) {
      setError('请先填写或选择模型名。')
      return
    }
    setBusy(true)
    setError(null)
    try {
      await onSubmit({
        preset,
        baseUrl: baseUrl.trim(),
        modelName: modelName.trim(),
        apiKey: apiKey.trim(),
      })
      onClose()
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setBusy(false)
    }
  }

  return (
    <Modal
      open={open}
      onClose={onClose}
      width="max-w-2xl"
      title="添加模型服务商"
      description="选服务商 → 粘贴 API Key → 自动获取可用模型 → 测试连接 → 保存。"
      footer={
        <div className="flex w-full items-center justify-between gap-2">
          <div>
            {step > 0 ? (
              <Button
                icon={<ArrowLeft size={13} />}
                disabled={busy}
                onClick={() => setStep(step - 1)}
              >
                上一步
              </Button>
            ) : null}
          </div>
          <div className="flex gap-2">
            <Button disabled={busy} onClick={onClose}>
              取消
            </Button>
            {step === 0 ? null : step === 1 ? (
              <Button
                variant="primary"
                disabled={busy || !modelName.trim() || !baseUrl.trim()}
                icon={busy ? <Loader2 size={13} className="animate-spin" /> : <Zap size={13} />}
                onClick={() => {
                  setStep(2)
                  void runTest()
                }}
              >
                测试连接
              </Button>
            ) : (
              <Button variant="primary" disabled={busy} onClick={() => void finish()}>
                {busy ? '保存中…' : '保存并开始使用'}
              </Button>
            )}
          </div>
        </div>
      }
    >
      {/* 步骤指示：让用户知道"还差几步"，而不是面对一个不知道有多长的表单 */}
      <div className="mb-4 flex items-center gap-2">
        {STEPS.map((label, index) => (
          <div key={label} className="flex items-center gap-2">
            <div
              className={clsx(
                'flex items-center gap-1.5 rounded-[7px] px-2 py-1 text-[11.5px]',
                index === step
                  ? 'bg-brand-soft font-medium text-brand'
                  : index < step
                    ? 'text-ink-soft'
                    : 'text-ink-faint',
              )}
            >
              <span
                className={clsx(
                  'flex h-4 w-4 items-center justify-center rounded-full text-[10px]',
                  index === step ? 'bg-brand text-white' : 'bg-line text-ink-soft',
                )}
              >
                {index + 1}
              </span>
              {label}
            </div>
            {index < STEPS.length - 1 ? <div className="h-px w-4 bg-line" /> : null}
          </div>
        ))}
      </div>

      {error ? (
        <div className="mb-3 rounded-[8px] border border-danger/30 bg-danger-soft px-3 py-2 text-[12px] text-danger">
          {error}
        </div>
      ) : null}

      {step === 0 ? (
        <div className="grid grid-cols-2 gap-2">
          {presets.map((item) => (
            <button
              key={item.provider}
              type="button"
              onClick={() => pickPreset(item)}
              className="no-drag flex flex-col items-start gap-1 rounded-[10px] border border-line bg-canvas px-3 py-2.5 text-left transition-colors hover:border-brand/40 hover:bg-brand-soft/30"
            >
              <span className="w-full truncate text-[13px] font-medium whitespace-nowrap text-ink">
                {item.name}
              </span>
              <span className="w-full truncate text-[11.5px] text-ink-faint">{item.base_url}</span>
              {/* 跳的是 **`apply_url`（申请页）**，不是 `docs`（文档首页）：
                  用户卡住的地方是"去哪儿弄一把 Key"（统一口径，
                  与导航页、模型设置页三处一致）。没有申请页的（自定义服务商）
                  退回文档首页；两个都没有就**不渲染** —— 不画一个点了没反应的壳。 */}
              {item.apply_url || item.docs ? (
                <span
                  className="flex items-center gap-1 text-[11px] text-brand hover:underline"
                  onClick={(event) => {
                    // 卡片本身是"选中服务商"，点链接不该顺带选中它
                    event.stopPropagation()
                    void window.agentBridge?.openExternal(item.apply_url || item.docs)
                  }}
                >
                  申请 API
                  <ExternalLink size={10} />
                </span>
              ) : null}
            </button>
          ))}
        </div>
      ) : null}

      {step === 1 ? (
        <div className="flex flex-col gap-3">
          <Field
            label="API Key"
            hint="会加密保存在本机（Windows 上由 DPAPI 保护，仅本机当前用户能解密），不会上传到任何服务器。"
          >
            <Input
              type="password"
              value={apiKey}
              onChange={(event) => setApiKey(event.target.value)}
              placeholder="粘贴服务商后台复制来的 Key"
              autoComplete="off"
              spellCheck={false}
            />
          </Field>

          <Field label="模型名" hint="点「获取模型」自动列出该账号可用的模型；也可以直接填写。">
            <ModelPickerField
              id="wizard-model"
              baseUrl={baseUrl}
              apiKey={apiKey}
              value={modelName}
              onChange={setModelName}
              suggested={preset?.models ?? []}
            />
          </Field>

          <div className="rounded-[10px] border border-line">
            <button
              type="button"
              onClick={() => setAdvancedOpen(!advancedOpen)}
              className="no-drag flex w-full items-center gap-1.5 px-3 py-2 text-left text-[12px] text-ink-soft hover:text-ink"
            >
              <ChevronDown
                size={13}
                className={clsx('transition-transform', advancedOpen ? '' : '-rotate-90')}
              />
              高级设置
            </button>
            {advancedOpen ? (
              <div className="border-t border-line px-3 py-3">
                <Field
                  label="接口地址 Base URL"
                  hint="自建网关或代理时才需要改；一般保持默认即可。"
                >
                  <Input
                    value={baseUrl}
                    onChange={(event) => setBaseUrl(event.target.value)}
                    placeholder="https://api.example.com/v1"
                    spellCheck={false}
                  />
                </Field>
                <p className="mt-2 text-[11.5px] leading-relaxed text-ink-faint">
                  上下文窗口、超时、价格、能力开关等参数保存后可在「模型服务商」列表里逐项调整。
                </p>
              </div>
            ) : null}
          </div>
        </div>
      ) : null}

      {step === 2 ? (
        <div className="flex flex-col gap-3">
          <div className="rounded-[10px] border border-line bg-panel px-3 py-2.5 text-[12.5px]">
            <div className="flex justify-between gap-3 py-0.5">
              <span className="text-ink-faint">服务商</span>
              <span className="text-ink">{preset?.name}</span>
            </div>
            <div className="flex justify-between gap-3 py-0.5">
              <span className="text-ink-faint">模型</span>
              <span className="text-ink">{modelName}</span>
            </div>
            <div className="flex justify-between gap-3 py-0.5">
              <span className="text-ink-faint">接口地址</span>
              <span className="max-w-[320px] truncate text-ink">{baseUrl}</span>
            </div>
            <div className="flex justify-between gap-3 py-0.5">
              <span className="text-ink-faint">API Key</span>
              {/* 只回显末四位：界面不需要为了"确认填了没"而把明文再铺一遍 */}
              <span className="text-ink">{apiKey ? `••••${apiKey.slice(-4)}` : '（未填写）'}</span>
            </div>
          </div>

          {busy ? (
            <div className="flex items-center gap-2 px-1 text-[12.5px] text-ink-soft">
              <Loader2 size={14} className="animate-spin text-brand" />
              正在测试连接…
            </div>
          ) : test ? (
            <div
              className={clsx(
                'rounded-[8px] border px-3 py-2 text-[12.5px] leading-relaxed',
                test.ok
                  ? 'border-success/30 bg-success-soft text-success'
                  : 'border-danger/30 bg-danger-soft text-danger',
              )}
            >
              {test.text}
            </div>
          ) : null}

          {test && !test.ok ? (
            <p className="px-1 text-[11.5px] leading-relaxed text-ink-faint">
              测试没通过也可以先保存（例如网络暂时不通），之后在设置里再测。
            </p>
          ) : null}
        </div>
      ) : null}
    </Modal>
  )
}
