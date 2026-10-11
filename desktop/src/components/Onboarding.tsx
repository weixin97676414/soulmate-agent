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

/**
 * 首启动引导。
 *
 * 目标只有一个：**让用户在两分钟内完成第一次成功对话**。
 *
 * ## 三部分 + 一个总闸（产品定下的结构）
 *
 * 从上到下：**语音设置 → 长期记忆 → 服务厂商**，底部一个「开始」。
 *
 * 为什么把语音与长期记忆提到服务商**前面**：这两个是"点一下就自动下完"的事，
 * 而服务商要用户去别处申请 Key —— 把它放最后，用户可以先让几百 MB 在后台下着，
 * 再去填 Key，两件事不互相阻塞（放第一个的话，他会盯着一个不动的进度条发愁）。
 *
 * ## 服务商与那两项是**两步保存**
 *
 * 服务商有它自己的「保存」（产品约定："必须先保存成功，底部才可点"）。
 * ⚠️ 它**绝不能顺手调 `dismissOnboarding()`**（也不能让向导因为"有可用模型了"
 * 而消失）—— 否则服务商一保存、向导当场没了，后面的模型下载就没地方做了。
 * 见 `appStore.onboardingActive` 与 `App.tsx` 里那段说明。
 *
 * ## 模型为什么不随包了
 *
 * 语音与嵌入模型 起从安装包里移出（省约 800MB），改由这里按需下载：
 * 按当前线路自动选国内（ModelScope）/ 国外（HuggingFace）源，失败自动换另一条。
 * 详见 `core/src/my_agent/model_hub/`。
 */

/** 自定义服务商的空白预设（与设置页的「+添加服务商」同一形态） */
const CUSTOM_PRESET: ProviderPreset = {
  provider: 'custom',
  name: '自定义服务商',
  base_url: '',
  models: [],
  docs: '',
  token_limit: 131072,
}

/**
 * 这家服务商是不是**本机**的（Ollama / 本地地址）。
 *
 * 起，「保存」对**线上**服务商要求 Key 非空：允许空 Key
 * 保存的后果很实在 —— 用户以为配好了、点了「开始」进主界面，下次启动又因为
 * "没有可用服务商"被弹回向导，而界面上那两条服务商看着都像配好了
 * （这正是实测反馈"明明装好了又被拦一次"的成因之一）。
 *
 * 本机服务天然不需要 Key，不能拦：`provider === 'ollama'`，或者地址的主机名是
 * `localhost` / `127.0.0.1` / `::1`。
 */
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
    // 地址还拼不成 URL（用户正在输入）⇒ 当成"不是本机"，让下面的 Key 校验正常拦
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

  /** 服务商是否**已经保存成功**（底部总闸的第三个条件；改任何一格就作废，见下） */
  const [providerSaved, setProviderSaved] = useState(false)
  const [skippedVoice, setSkippedVoice] = useState(false)
  const [skippedMemory, setSkippedMemory] = useState(false)
  const [voiceConfigOpen, setVoiceConfigOpen] = useState(false)

  const voiceEntry = useModelHubStore((state) => state.models.voice)
  const memoryEntry = useModelHubStore((state) => state.models.embedding)

  /**
   * 取"这个模型名对应的、已保存的**明文** Key"。
   *
   * 后端现在直接下发明文（见 `server/routes/models.py` 的 `_mask`），
   * 所以这里不需要任何 IPC、也没有异步回填 —— 列表里就带着真字符。
   * 顺带就消灭了"回填还没到、自动保存已经带着空值跑掉"那个竞态。
   */
  const existingKeyFor = (name: string): string =>
    models.find((model) => model.id === name || model.model_name === name)?.api_key ?? ''

  const pick = (preset: ProviderPreset) => {
    setSelected(preset)
    setBaseUrl(preset.base_url)
    const name = preset.models[0] ?? ''
    setModelName(name)
    // 这家已经配过 Key 的话，**把明文填回来**（产品要求：无论在设置页还是引导页
    // 配的密钥，都要在这一栏常显真字符）。
    //
    // 为什么不能一律清空：重新跑一遍引导（只想换个模型名）会让输入框变空，
    // 而"空值提交"在历史上正是密钥被清掉的那条路 —— 现在后端已经不再把空值
    // 当删除，但界面也不该让用户看着一个空框去猜"我的 Key 还在不在"。
    setApiKey(existingKeyFor(name))
    setResult(null)
    // 换了服务商 = 之前那次保存不再代表当前表单
    setProviderSaved(false)
  }

  // 用户手动改模型名时，把对应的已保存明文同步过来。
  // **只在当前输入框为空时填** —— 绝不覆盖他正在打的字（这条原则在设置页也踩过坑）。
  useEffect(() => {
    if (apiKey.trim()) return
    const saved = existingKeyFor(modelName.trim() || (selected?.models[0] ?? ''))
    if (saved) setApiKey(saved)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [modelName, selected])

  /**
   * 把"这一页填的东西 + 已存在的那条"合成一份**完整草稿**。
   *
   * ⚠️ **字段清单的唯一来源是 `settings/modelPayload.ts`**：那个接口是"整份覆盖"
   * 语义 —— 缺席的字段会被后端按默认值重置，而且**不报错**。
   * 向导以前**自己手写了一份字段表**，于是"设置页里配过、向导里没有的字段"
   * （`use_system_proxy`、高峰分时价、`peak_windows`）会在**重跑一次向导**
   * （比如只想改个模型名）时被静默清零 —— 用户只会觉得"我配的分时定价自己没了"。
   * 现在以已存在的那条为底、只覆盖这一页真正填了的字段，其余原样继承。
   */
  const buildDraft = (): Draft | null => {
    if (!selected) return null
    const name = modelName.trim() || selected.models[0] || 'model'
    // 直接复用同名条目的 id，避免留下两条同名模型让用户困惑
    const existing = models.find((model) => model.id === name)
    return emptyDraft({
      ...(existing ?? {}),
      id: existing?.id ?? name,
      name: `${selected.name} · ${name}`,
      provider: selected.provider,
      adapter: 'openai_compat',
      base_url: baseUrl.trim(),
      model_name: name,
      // 沿用已存在条目的窗口（用户可能改过）；没有才用这家预设的
      token_limit: existing?.token_limit ?? selected.token_limit ?? 131072,
      enabled: true,
      is_default: true,
      // 这一页填的 Key。**空 = 没填**，交给 `modelPayload` 声明"没改过"
      // （绝不会被当成"产品要求删除"）。
      apiKeyInput: apiKey.trim(),
    })
  }

  /**
   * 这一页当前**会提交**的那条模型 —— 与保存路径逐字段相同。
   *
   * 「验证一下」用它，是为了让"测的"和"存的"是同一份东西：
   * 各写一份的话，"测通了却存不上"这类差异迟早会出现。
   */
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

  /**
   * **保存服务商**（第一步；不再进主界面）。
   *
   * ⚠️ 与旧版的唯一区别就是这里**不调 `dismissOnboarding()`**：向导里还有
   * 两项模型要装，保存完就退出等于把后面两步藏起来。真正的出口是底部的总闸。
   */
  const saveProvider = async () => {
    const draft = buildDraft()
    if (!api || !draft || !selected) return
    // ⚠️ **线上服务商必须填 Key 才算保存成功**（产品要求）。
    // 判据是"不是本机地址" —— 本机 Ollama / 本地推理服务本来就不要 Key。
    if (!isLocalEndpoint(selected.provider, baseUrl) && !apiKey.trim()) {
      setResult({
        ok: false,
        text: '这家服务商需要 API Key：点上面的「申请 API」申请一个，粘贴进来再保存。',
      })
      // 刻意**不置 providerSaved**：保存不算成功，底部那个「开始」也不会放行。
      return
    }
    setSaving(true)
    setResult(null)
    try {
      // 保留用户已有的其他模型，只把当前这条替换/加入。
      //
      // ⚠️ 它们也走**同一份** `modelPayload`：这样"整份覆盖"语义下谁都不会漏字段。
      // 这些条目的 api_key 在后端下发时是**脱敏预览**，所以这里的 `apiKeyInput` 留空 ⇒
      // `modelPayload` 会声明 `api_key_unchanged`，后端沿用原 Key
      //（绝不会把脱敏预览当成新值收下）。
      const others = models
        .filter((model) => model.id !== draft.id)
        .map((model) => emptyDraft({ ...model, is_default: false }))

      await api.saveModels(modelPayload([...others, draft], draft.id))

      // 密钥交给主进程加密保存；后端落盘时会把 api_key 字段剥成空串
      if (draft.apiKeyInput) {
        await window.agentBridge?.saveSecrets({ models: { [draft.id]: draft.apiKeyInput } })
      }

      await reloadModels()
      setProviderSaved(true)
      setResult({ ok: true, text: '服务商配置已保存。' })
    } catch (error) {
      // 保存失败**不关窗、也不把 providerSaved 置真**：那会让底部总闸骗人
      setResult({
        ok: false,
        text: error instanceof Error ? error.message : String(error),
      })
    } finally {
      setSaving(false)
    }
  }

  /**
   * 底部总闸：三项条件全过才可点（产品明确要求"不允许直接点它进入主页面"）。
   *
   * 「完成或跳过」对两个模型都算通过 —— 用户有权不用语音 / 不用长期记忆。
   */
  const voiceReady = Boolean(voiceEntry?.installed) || skippedVoice
  const memoryReady = Boolean(memoryEntry?.installed) || skippedMemory
  const canFinish = voiceReady && memoryReady && providerSaved
  const missing: string[] = []
  if (!voiceReady) missing.push('语音设置（下载或跳过）')
  if (!memoryReady) missing.push('长期记忆（下载或跳过）')
  if (!providerSaved) missing.push('服务商配置（填好并点「保存」）')

  const canSubmit = Boolean(selected && baseUrl.trim() && modelName.trim())
  // 已经配过 Key 的服务商在左列标一个绿点：让用户一眼看出"这家我已经配好了"
  const configuredProviders = useMemo(
    () => new Set(models.filter((model) => model.has_api_key).map((model) => model.provider)),
    [models],
  )

  return (
    <div className="flex h-full flex-col overflow-hidden bg-canvas">
      <div className="mx-auto flex w-full max-w-[980px] min-h-0 flex-1 flex-col px-10">
        {/*
          ⚠️ 这里的 logo（`BrandMark`）按产品要求**剔除**了：
          首启页要腾出空间给真正要读的文字，而一个图标不承载任何信息。
          说明文字同时**放大**了（正文 12.5 → 14，标题 18 → 22）—— 这一段是
          "该选哪个模型"的唯一依据，是要真读的，不该用脚注字号。
        */}
        <div className="shrink-0 pt-8">
          <h1 className="text-[22px] font-semibold text-ink">欢迎使用 Soulmate Agent</h1>
          <p className="mt-1 text-[14px] text-ink-soft">
            下面三部分从上到下做完就能开始用了；语音与长期记忆可以跳过，之后随时能补装。
          </p>
          {/* 产品要求：这段加粗。**必须在选之前说** —— 用户随便挑一家弱模型之后
              只会觉得"这软件不好用"，等事后再解释就晚了。 */}
          <p className="mt-2 text-[14px] font-semibold leading-relaxed text-ink">
            推荐模型：DeepSeek-flash，DeepSeek-v4-flash，Qwen3.5以上全量模型，Gpt5.6以上全量模型。
          </p>
        </div>

        {/* 三部分：语音设置 / 长期记忆 / 服务厂商。窄窗口下整体滚动，底部总闸固定。 */}
        <div className="mt-6 min-h-0 flex-1 overflow-y-auto pb-4">
          <div className="flex flex-col gap-5">
            {/* ---- ① 语音设置 ---- */}
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
              {/* 产品要求：语音装好后给「开始配置」，点开**只有全局设置**那一区，
                  并明说"每个搭子的唤醒词要去各自的语音设置里配"。 */}
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

            {/* ---- ② 长期记忆 ---- */}
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

            {/* ---- ③ 服务厂商 ---- */}
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

              {/* 左右两栏：与「设置 → 模型服务商」同一套布局 */}
              <div className="mt-2 flex min-h-[320px] items-start gap-4">
                {/* 左列：服务商列表 + 添加入口 */}
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

                  {/* 产品要求：一开始就能自定义服务商。原来这里只是一句
                      "服务商列表暂时没有取到…稍后再添加"的被动提示，已剔除。 */}
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

                {/* 右列：配置表单 */}
                <div className="min-w-0 flex-1">
                  {selected ? (
                    <div className="rounded-[10px] border border-line bg-canvas p-4">
                      <div className="mb-3 flex items-center gap-2">
                        <span className="text-[13.5px] font-medium text-ink">{selected.name}</span>
                        {/*
                          「申请 API」按产品要求**高亮 + 加边框**。
                          原先它是一行灰字（`text-ink-faint`，无边框），看起来像说明文字，
                          用户根本不知道那是个链接 —— 而它是这条路径上**第一步**必须点的东西
                          （没有 Key 什么都配不了）。

                          ⚠️ 起跳的是 **`apply_url`（申请页）**，
                          不再是 `docs`（文档首页）：用户卡住的地方是"去哪儿弄一把 Key"，
                          把他丢到文档首页还得自己找一圈。`docs` 只在预设没给申请页时兜底
                          （自定义服务商两个都没有 ⇒ 不渲染按钮，不画空壳）。
                        */}
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
                          {/* 明文常显（产品要求）：与设置页一致 —— 不做"点小眼睛才看得到"。
                              字段里始终是真字符，"自动保存/覆盖"就不可能把空值写进去。 */}
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
                          {/* 与「添加服务商」向导共用同一个组件：两个入口的行为必须一致，
                              否则用户会觉得"有时候能自动获取有时候不能" */}
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

                      <div className="mt-4 flex flex-wrap items-center gap-2">
                        <Button
                          icon={testing ? <Loader2 size={13} className="animate-spin" /> : <Zap size={13} />}
                          onClick={() => void runTest()}
                          disabled={!canSubmit || testing || saving}
                        >
                          测试连接
                        </Button>
                        {/* ⚠️ **保存成功后这个按钮就消失**（产品要求）。
                            `providerSaved` 已经把"改了就作废"包在里面：`pick()` 与三个
                            输入框的 onChange 都会把它置回 false ⇒ 用户改完 Key 或换个
                            服务商，按钮**自己就回来**了（否则他再也保存不了）。
                            保存成功后的反馈（下面那行绿字 + 结果块）保留，不然按钮一没
                            用户就看不出到底成没成。
                            进主界面只由底部总闸负责，这里**不调** dismissOnboarding。 */}
                        {!providerSaved ? (
                          <Button
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
                        {/* 提前说一声"这家要 Key"，别让用户在点了保存之后才被拦回来 */}
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

            {/* ⚠️ 产品要求**收成一行**（原先是两行：配置保存 + 设备标识采集）。
                两件都是"告知"，但都不影响用户下一步要做什么 —— 占两行会把视线从
                "还要做完哪几项"上引开。合成一句后信息一条没少，只是不再抢版面。 */}
            <p className="text-[12.5px] leading-relaxed text-ink-faint">
              配置会自动保存在本机、随时可在设置里修改；应用会采集设备标识信息来创建并保护你的账号与权益。
            </p>
          </div>
        </div>

        {/*
          底部总闸。**固定**在底部（不进滚动区）：用户要随时看得到"还差什么"。
          三项齐了才可点 —— 产品明确要求"不允许直接点它进入主页面"。
        */}
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
