import clsx from 'clsx'
import { AlertTriangle, Check, ExternalLink, Loader2, Plug, Zap } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'

import { ModelDownloadCard } from '@/components/ModelDownloadCard'
import { emptyDraft, modelPayload, type Draft } from '@/components/settings/modelPayload'
import { ModelPickerField } from '@/components/settings/ModelPickerField'
import { VoicePanel } from '@/components/chat/VoicePanel'
import { Button, Field, Input } from '@/components/ui'
import { useAppStore } from '@/stores/appStore'
import { useModelHubStore } from '@/stores/modelHubStore'
import type { ProviderPreset } from '@/types'





























const CUSTOM_PRESET: ProviderPreset = {
  provider: 'custom',
  name: '自定义服务商',
  base_url: '',
  models: [],
  docs: '',
  token_limit: 131072,
}












function isLocalEndpoint(provider: string, baseUrl: string): boolean {
  if (provider === 'ollama') return true
  try {
    const host = new URL(baseUrl).hostname.toLowerCase()
    return (
      host === 'localhost' ||
      host === '127.0.0.1' ||
      host === '::1' ||
      host === '[::1]' ||
      host.endsWith('.localhost')
    )
  } catch {
    
    return false
  }
}

export function Onboarding() {
  const api = useAppStore((state) => state.api)
  const presets = useAppStore((state) => state.presets)
  const models = useAppStore((state) => state.models)
  const reloadModels = useAppStore((state) => state.reloadModels)
  const dismissOnboarding = useAppStore((state) => state.dismissOnboarding)

  const choices = useMemo(() => presets, [presets])

  const [selected, setSelected] = useState<ProviderPreset | null>(null)
  const [apiKey, setApiKey] = useState('')
  const [baseUrl, setBaseUrl] = useState('')
  const [modelName, setModelName] = useState('')
  const [testing, setTesting] = useState(false)
  const [saving, setSaving] = useState(false)
  const [result, setResult] = useState<{ ok: boolean; text: string; models?: string[] } | null>(null)

  
  const [providerSaved, setProviderSaved] = useState(false)
  const [skippedVoice, setSkippedVoice] = useState(false)
  const [skippedMemory, setSkippedMemory] = useState(false)
  const [voiceConfigOpen, setVoiceConfigOpen] = useState(false)

  const voiceEntry = useModelHubStore((state) => state.models.voice)
  const memoryEntry = useModelHubStore((state) => state.models.embedding)

  






  const existingKeyFor = (name: string): string =>
    models.find((model) => model.id === name || model.model_name === name)?.api_key ?? ''

  const pick = (preset: ProviderPreset) => {
    setSelected(preset)
    setBaseUrl(preset.base_url)
    const name = preset.models[0] ?? ''
    setModelName(name)
    
    
    
    
    
    
    setApiKey(existingKeyFor(name))
    setResult(null)
    
    setProviderSaved(false)
  }

  
  
  useEffect(() => {
    if (apiKey.trim()) return
    const saved = existingKeyFor(modelName.trim() || (selected?.models[0] ?? ''))
    if (saved) setApiKey(saved)
    
  }, [modelName, selected])

  









  const buildDraft = (): Draft | null => {
    if (!selected) return null
    const name = modelName.trim() || selected.models[0] || 'model'
    
    const existing = models.find((model) => model.id === name)
    return emptyDraft({
      ...(existing ?? {}),
      id: existing?.id ?? name,
      name: `${selected.name} · ${name}`,
      provider: selected.provider,
      adapter: 'openai_compat',
      base_url: baseUrl.trim(),
      model_name: name,
      
      token_limit: existing?.token_limit ?? selected.token_limit ?? 131072,
      enabled: true,
      is_default: true,
      
      
      apiKeyInput: apiKey.trim(),
    })
  }

  





  const buildSpec = () => {
    const draft = buildDraft()
    return draft ? modelPayload([draft], draft.id).models[0] : null
  }

  const runTest = async (): Promise<boolean> => {
    const spec = buildSpec()
    if (!api || !spec) return false
    setTesting(true)
    setResult(null)
    try {
      const response = await api.testModel({ spec })
      if (response.ok) {
        setResult({
          ok: true,
          text: `连接成功${response.latency_ms ? `，延迟 ${Math.round(response.latency_ms)}ms` : ''}${
            response.warning ? `。${response.warning}` : ''
          }`,
          models: response.models,
        })
        return true
      }
      setResult({ ok: false, text: response.error ?? '连接失败，请检查 Key 与网络。' })
      return false
    } catch (error) {
      setResult({
        ok: false,
        text: error instanceof Error ? error.message : String(error),
      })
      return false
    } finally {
      setTesting(false)
    }
  }

  





  const saveProvider = async () => {
    const draft = buildDraft()
    if (!api || !draft || !selected) return
    
    
    if (!isLocalEndpoint(selected.provider, baseUrl) && !apiKey.trim()) {
      setResult({
        ok: false,
        text: '这家服务商需要 API Key：点上面的「申请 API」申请一个，粘贴进来再保存。',
      })
      
      return
    }
    setSaving(true)
    setResult(null)
    try {
      
      
      
      
      
      
      const others = models
        .filter((model) => model.id !== draft.id)
        .map((model) => emptyDraft({ ...model, is_default: false }))

      await api.saveModels(modelPayload([...others, draft], draft.id))

      
      if (draft.apiKeyInput) {
        await window.agentBridge?.saveSecrets({ models: { [draft.id]: draft.apiKeyInput } })
      }

      await reloadModels()
      setProviderSaved(true)
      setResult({ ok: true, text: '服务商配置已保存。' })
    } catch (error) {
      
      setResult({
        ok: false,
        text: error instanceof Error ? error.message : String(error),
      })
    } finally {
      setSaving(false)
    }
  }

  




  const voiceReady = Boolean(voiceEntry?.installed) || skippedVoice
  const memoryReady = Boolean(memoryEntry?.installed) || skippedMemory
  const canFinish = voiceReady && memoryReady && providerSaved
  const missing: string[] = []
  if (!voiceReady) missing.push('语音设置（下载或跳过）')
  if (!memoryReady) missing.push('长期记忆（下载或跳过）')
  if (!providerSaved) missing.push('服务商配置（填好并点「保存」）')

  const canSubmit = Boolean(selected && baseUrl.trim() && modelName.trim())
  
  const configuredProviders = useMemo(
    () => new Set(models.filter((model) => model.has_api_key).map((model) => model.provider)),
    [models],
  )

  return (
    <div className="flex h-full flex-col overflow-hidden bg-canvas">
      <div className="mx-auto flex w-full max-w-[980px] min-h-0 flex-1 flex-col px-10">
        {




}
        <div className="shrink-0 pt-8">
          <h1 className="text-[22px] font-semibold text-ink">欢迎使用 Soulmate Agent</h1>
          <p className="mt-1 text-[14px] text-ink-soft">
            下面三部分从上到下做完就能开始用了；语音与长期记忆可以跳过，之后随时能补装。
          </p>
          {
}
          <p className="mt-2 text-[14px] font-semibold leading-relaxed text-ink">
            推荐模型：DeepSeek-flash，DeepSeek-v4-flash，Qwen3.5以上全量模型，Gpt5.6以上全量模型。
          </p>
        </div>

        {}
        <div className="mt-6 min-h-0 flex-1 overflow-y-auto pb-4">
          <div className="flex flex-col gap-5">
            {}
            <section>
              <div className="flex flex-wrap items-baseline gap-2">
                <span className="flex h-[18px] w-[18px] items-center justify-center rounded-full bg-brand/15 text-[11px] font-semibold text-brand">
                  1
                </span>
                <h3 className="text-[14px] font-semibold text-ink">语音设置</h3>
                <span className="text-[11.5px] text-ink-faint">我们大多数指令都支持语音</span>
              </div>
              <ModelDownloadCard
                modelKey="voice"
                className="mt-2"
                showVerify={false}
                skipLabel="跳过配置"
                skipped={skippedVoice}
                onSkip={() => setSkippedVoice(true)}
                extra={
                  voiceEntry?.installed ? (
                    <Button
                      size="sm"
                      onClick={() => setVoiceConfigOpen((prev) => !prev)}
                    >
                      {voiceConfigOpen ? '收起语音设置' : '开始配置'}
                    </Button>
                  ) : null
                }
              />
              {
}
              {voiceConfigOpen && voiceEntry?.installed ? (
                <div className="mt-2 rounded-[10px] border border-line bg-canvas px-3 py-2.5">
                  <p className="text-[11.5px] leading-relaxed text-ink-faint">
                    这里只配全局项（启动档位、开关词、命令词）。每个搭子的**唤醒词**要在各搭子
                    输入栏的「语音设置」里单独配 —— 它管的是"喊谁醒谁"，天然跟着搭子走。
                  </p>
                  <VoicePanel globalOnly onClose={() => setVoiceConfigOpen(false)} />
                </div>
              ) : null}
            </section>

            {}
            <section>
              <div className="flex flex-wrap items-baseline gap-2">
                <span className="flex h-[18px] w-[18px] items-center justify-center rounded-full bg-brand/15 text-[11px] font-semibold text-brand">
                  2
                </span>
                <h3 className="text-[14px] font-semibold text-ink">长期记忆</h3>
                <span className="text-[11.5px] text-ink-faint">
                  不会占用对话上下文，仅在需要时被读取
                </span>
              </div>
              <ModelDownloadCard
                modelKey="embedding"
                className="mt-2"
                skipLabel="跳过配置"
                skipped={skippedMemory}
                onSkip={() => setSkippedMemory(true)}
              />
            </section>

            {}
            <section>
              <div className="flex flex-wrap items-baseline gap-2">
                <span className="flex h-[18px] w-[18px] items-center justify-center rounded-full bg-brand/15 text-[11px] font-semibold text-brand">
                  3
                </span>
                <h3 className="text-[14px] font-semibold text-ink">服务厂商</h3>
                <span className="text-[11.5px] text-ink-faint">
                  填好并点「保存」，这一步是必须的
                </span>
              </div>

              {}
              <div className="mt-2 flex min-h-[320px] items-start gap-4">
                {}
                <div className="flex max-h-[380px] w-[248px] shrink-0 flex-col overflow-hidden rounded-[10px] border border-line bg-panel p-1.5">
                  <div className="min-h-0 flex-1 space-y-0.5 overflow-y-auto">
                    {choices.length === 0 ? (
                      <p className="px-2.5 py-3 text-[11.5px] leading-relaxed text-ink-faint">
                        暂时没取到内置服务商清单。直接用下面的「添加服务商」自己填一个也能开始。
                      </p>
                    ) : null}
                    {choices.map((preset) => {
                      const active = selected?.provider === preset.provider
                      const configured = configuredProviders.has(preset.provider)
                      return (
                        <button
                          key={preset.provider}
                          type="button"
                          onClick={() => pick(preset)}
                          className={clsx(
                            'no-drag flex w-full items-center gap-2 rounded-[7px] px-2.5 py-2 text-left transition-colors',
                            active
                              ? 'bg-brand-soft text-brand'
                              : 'text-ink-soft hover:bg-hover hover:text-ink',
                          )}
                        >
                          <span
                            className={clsx(
                              'h-1.5 w-1.5 shrink-0 rounded-full',
                              configured ? 'bg-success' : 'bg-ink-faint',
                            )}
                            title={configured ? '已配置密钥' : '尚未配置'}
                          />
                          <span className="min-w-0 flex-1 truncate text-[12.5px]" title={preset.name}>
                            {preset.name}
                          </span>
                          {active ? <Check size={13} className="shrink-0 text-brand" /> : null}
                        </button>
                      )
                    })}
                  </div>

                  {
}
                  <div className="mt-1.5 shrink-0 border-t border-line-soft pt-1.5">
                    <button
                      type="button"
                      onClick={() => pick(CUSTOM_PRESET)}
                      className={clsx(
                        'no-drag flex w-full items-center gap-2 rounded-[7px] px-2.5 py-2 text-left transition-colors',
                        selected?.provider === 'custom'
                          ? 'bg-brand-soft text-brand'
                          : 'text-ink-soft hover:bg-hover hover:text-ink',
                      )}
                    >
                      <Plug size={13} className="shrink-0" />
                      <span className="text-[12.5px]">添加服务商</span>
                    </button>
                  </div>
                </div>

                {}
                <div className="min-w-0 flex-1">
                  {selected ? (
                    <div className="rounded-[10px] border border-line bg-canvas p-4">
                      <div className="mb-3 flex items-center gap-2">
                        <span className="text-[13.5px] font-medium text-ink">{selected.name}</span>
                        {









}
                        {selected.apply_url || selected.docs ? (
                          <button
                            type="button"
                            onClick={() =>
                              void window.agentBridge?.openExternal(
                                selected.apply_url || selected.docs,
                              )
                            }
                            className="no-drag flex items-center gap-1 rounded-[6px] border border-brand/40 bg-brand-soft px-2 py-0.5 text-[11.5px] font-medium text-brand transition-colors hover:border-brand hover:opacity-90"
                          >
                            申请 API
                            <ExternalLink size={11} />
                          </button>
                        ) : null}
                      </div>

                      <div className="grid grid-cols-2 gap-3">
                        <Field
                          label="API Key"
                          hint="密钥加密保存在本机，不会上传到任何服务器。这里**明文显示**，方便你核对有没有粘错。"
                        >
                          {
}
                          <Input
                            type="text"
                            value={apiKey}
                            autoComplete="off"
                            spellCheck={false}
                            onChange={(event) => {
                              setApiKey(event.target.value)
                              setProviderSaved(false)
                              setResult(null)
                            }}
                            placeholder="sk-..."
                          />
                        </Field>

                        <Field
                          label="模型名"
                          hint="点输入框右侧的按钮自动列出这个账号可用的模型，也可以直接填写。"
                        >
                          {
}
                          <ModelPickerField
                            id="onboarding-model"
                            baseUrl={baseUrl}
                            apiKey={apiKey}
                            value={modelName}
                            onChange={(name) => {
                              setModelName(name)
                              setProviderSaved(false)
                              setResult(null)
                            }}
                            suggested={result?.models ?? selected.models}
                          />
                        </Field>

                        <Field
                          label="接口地址"
                          className="col-span-2"
                          hint={selected.provider === 'custom' ? '必填，填服务商文档里的 API 地址' : '一般不用改'}
                        >
                          <Input
                            value={baseUrl}
                            onChange={(event) => {
                              setBaseUrl(event.target.value)
                              setProviderSaved(false)
                              setResult(null)
                            }}
                            placeholder="https://api.example.com/v1"
                          />
                        </Field>
                      </div>

                      {result ? (
                        <div
                          className={clsx(
                            'mt-3 flex items-start gap-2 rounded-[8px] px-3 py-2 text-[12px] leading-relaxed',
                            result.ok ? 'bg-success-soft text-ink-soft' : 'bg-danger-soft text-danger',
                          )}
                        >
                          {result.ok ? (
                            <Check size={13} className="mt-[3px] shrink-0 text-success" />
                          ) : (
                            <AlertTriangle size={13} className="mt-[3px] shrink-0" />
                          )}
                          <span className="selectable break-words">{result.text}</span>
                        </div>
                      ) : null}

                      {











}
                      <div className="mt-4 flex flex-wrap items-center gap-2">
                        <Button
                          size="md"
                          icon={testing ? <Loader2 size={13} className="animate-spin" /> : <Zap size={13} />}
                          onClick={() => void runTest()}
                          disabled={!canSubmit || testing || saving}
                        >
                          测试连接
                        </Button>
                        {





}
                        {!providerSaved ? (
                          <Button
                            
                            size="md"
                            variant="primary"
                            icon={saving ? <Loader2 size={13} className="animate-spin" /> : <Check size={13} />}
                            onClick={() => void saveProvider()}
                            disabled={!canSubmit || testing || saving}
                          >
                            保存
                          </Button>
                        ) : null}
                        {providerSaved ? (
                          <span className="text-[11.5px] text-success">服务商配置已保存</span>
                        ) : null}
                        {!canSubmit ? (
                          <span className="text-[11.5px] text-ink-faint">
                            接口地址与模型名都填好之后就可以保存了。
                          </span>
                        ) : null}
                        {}
                        {!providerSaved &&
                        canSubmit &&
                        !isLocalEndpoint(selected.provider, baseUrl) &&
                        !apiKey.trim() ? (
                          <span className="text-[11.5px] text-warning">这家服务商需要 API Key。</span>
                        ) : null}
                      </div>
                    </div>
                  ) : (
                    <div className="rounded-[10px] border border-dashed border-line px-5 py-10 text-center">
                      <p className="text-[13px] text-ink-soft">从左边选一个服务商开始配置</p>
                      <p className="mt-1 text-[11.5px] leading-relaxed text-ink-faint">
                        列表里没有你要用的？点左下方的「添加服务商」，自己填接口地址与模型名。
                      </p>
                    </div>
                  )}
                </div>
              </div>
            </section>

            {

}
            <p className="text-[12.5px] leading-relaxed text-ink-faint">
              配置会自动保存在本机、随时可在设置里修改；应用会采集设备标识信息来创建并保护你的账号与权益。
            </p>
          </div>
        </div>

        {


}
        <div className="flex shrink-0 flex-wrap items-center justify-between gap-3 border-t border-line-soft py-4">
          <p className="text-[12.5px] leading-relaxed text-ink-faint">
            {canFinish ? '三项都已完成，可以开始使用了。' : `还差：${missing.join('、')}`}
          </p>
          <Button
            variant="primary"
            icon={<Check size={13} />}
            disabled={!canFinish}
            onClick={() => dismissOnboarding()}
          >
            开始
          </Button>
        </div>
      </div>
    </div>
  )
}
