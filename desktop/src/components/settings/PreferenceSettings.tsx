import type { CloseAction } from '@shared/bridge'
import clsx from 'clsx'
import { FolderPlus, Trash2 } from 'lucide-react'
import { useEffect, useRef, useState, type ReactNode } from 'react'

import { ModelDownloadCard } from '@/components/ModelDownloadCard'
import { SkillSecretsCard } from '@/components/settings/SkillSecretsCard'
import { Button, Field, Input, Select, Switch } from '@/components/ui'
import { useAppStore } from '@/stores/appStore'
import type { AppSettings } from '@/types'

/**
 * 「点关闭按钮时」的三个选项。
 *
 * 顺序有讲究：`ask` 放第一个，它也是默认值 —— 对零基础用户来说，
 * "先问一次再决定"永远比"替我做主"更安全。
 *
 * 皮肤、壁纸与"我的资料"已移至独立的「外观」页签（见 AppearanceSettings）。
 */
const CLOSE_ACTION_OPTIONS: Array<{ value: CloseAction; label: string }> = [
  { value: 'ask', label: '每次询问' },
  { value: 'tray', label: '最小化到托盘' },
  { value: 'quit', label: '直接退出' },
]

/**
 * 嵌入（把文字变成可检索的向量）用哪条路。
 *
 * `builtin` 放第一个且是默认值：普通用户装完就该有能用的中文记忆，
 * 不该先去申请一个 API Key 才配得上"有记忆"这个功能。
 */
const EMBEDDING_BACKENDS: Array<{
  value: 'builtin' | 'api' | 'ollama'
  label: string
  hint: string
}> = [
  {
    value: 'builtin',
    label: '内置中文模型',
    // ⚠️ 起这个模型**不再随安装包分发**（改按需下载）：旧文案写的
    // "随安装包一起装好、开箱即用"已经不成立了，留着就是让用户以为装完就有。
    hint: '需要先在「长期记忆」那里下载一次（约 600 MB），之后不用联网、不花钱。输出 1024 维向量。',
  },
  {
    value: 'api',
    label: '自定义接口',
    hint: '填一个自己的 /embeddings 接口。要联网、消耗你的配额，但模型更强 —— 维度由你选的模型决定。',
  },
  {
    value: 'ollama',
    label: '本机 Ollama',
    hint: '你电脑上已经跑着 Ollama 的话，直接复用它本地的模型。维度由你选的模型决定。',
  },
]

function Section({
  title,
  description,
  children,
}: {
  title: string
  description?: string
  children: ReactNode
}) {
  return (
    <section className="mb-6">
      <h3 className="text-[13.5px] font-semibold text-ink">{title}</h3>
      {description ? (
        <p className="mt-0.5 mb-3 text-[12px] leading-relaxed text-ink-soft">{description}</p>
      ) : (
        <div className="mb-3" />
      )}
      {children}
    </section>
  )
}

export function PreferenceSettings() {
  const settings = useAppStore((state) => state.settings)
  const api = useAppStore((state) => state.api)
  const reloadSettings = useAppStore((state) => state.reloadSettings)
  const closeAction = useAppStore((state) => state.closeAction)
  const setCloseAction = useAppStore((state) => state.setCloseAction)

  // 皮肤、壁纸与"我的资料"已移至独立的「外观」页签（产品要求单独成栏 DIY 界面）。

  // Ollama 的模型列表是**读出来**的（本机有哪些模型，取决于用户装了什么），
  // 所以放在这里按需拉取，不随设置一起存。
  const [ollamaModels, setOllamaModels] = useState<string[]>([])
  const [ollamaLoading, setOllamaLoading] = useState(false)
  const [ollamaError, setOllamaError] = useState('')

  const loadOllamaModels = async () => {
    if (!api || !draft) return
    setOllamaLoading(true)
    setOllamaError('')
    try {
      const result = await api.discoverModels({
        base_url: draft.memory.embedding_ollama_url,
        api_key: '',
      })
      const names = result.models ?? []
      setOllamaModels(names)
      // 读到了 0 条不是"成功"：多半是 Ollama 没启动，不说清楚用户会以为列表本来就是空的
      if (names.length === 0) {
        setOllamaError('没读到模型。请确认 Ollama 已经启动，并且地址填写正确。')
      }
    } catch (error) {
      setOllamaError(error instanceof Error ? error.message : String(error))
    } finally {
      setOllamaLoading(false)
    }
  }
  // 嵌入模型的下拉要列出已配置的模型（复用模型配置是为了让 Key 走既有的密钥托管）
  const models = useAppStore((state) => state.models)

  const [draft, setDraft] = useState<AppSettings | null>(settings)
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)

  useEffect(() => {
    setDraft(settings)
  }, [settings])

  if (!draft) {
    return <div className="text-[12.5px] text-ink-faint">正在加载设置…</div>
  }

  const patch = (changes: Partial<AppSettings>) => {
    setDraft({ ...draft, ...changes })
    setSaved(false)
  }
  const patchAgent = (changes: Partial<AppSettings['agent']>) =>
    patch({ agent: { ...draft.agent, ...changes } })
  const patchSecurity = (changes: Partial<AppSettings['security']>) =>
    patch({ security: { ...draft.security, ...changes } })
  const patchUsage = (changes: Partial<AppSettings['usage']>) =>
    patch({ usage: { ...draft.usage, ...changes } })
  const patchMemory = (changes: Partial<AppSettings['memory']>) =>
    patch({ memory: { ...draft.memory, ...changes } })

  /**
   * 当前生效的嵌入后端，**要兼容旧配置**。
   *
   * 旧版本只有一个 `use_api_embedding` 开关。不认它的话，用户升级后会发现自己
   * 选过的"走接口"悄悄变回内置 —— 两边都能跑、只是结果不同，属于最难被察觉
   * 的那类"改了没生效"。
   */
  const embeddingBackend: 'builtin' | 'api' | 'ollama' = (() => {
    if (!draft) return 'builtin'
    const raw = draft.memory.embedding_backend
    if (raw === 'api' || raw === 'ollama') return raw
    // 旧配置：只有开关，没有新字段
    if (draft.memory.use_api_embedding) return 'api'
    return 'builtin'
  })()

  const save = async () => {
    if (!api || !draft) return
    setSaving(true)
    try {
      await api.saveSettings(draft)
      await reloadSettings()
      setSaved(true)
      window.setTimeout(() => setSaved(false), 2000)
    } finally {
      setSaving(false)
    }
  }

  // ---- 自动保存（产品要求：整个应用不再手动点保存）---------------------- //
  // draft 变化后 800ms 落盘。跳过首装载入：用 ref 标记"已经用服务器返回值
  // 播种过"，否则挂载时会空跑一次 save。
  const seededRef = useRef(false)
  const saveTimerRef = useRef<number | null>(null)
  useEffect(() => {
    if (!draft) return
    if (!seededRef.current) {
      seededRef.current = true
      return
    }
    if (saveTimerRef.current !== null) window.clearTimeout(saveTimerRef.current)
    saveTimerRef.current = window.setTimeout(() => {
      void save()
    }, 800)
    return () => {
      if (saveTimerRef.current !== null) window.clearTimeout(saveTimerRef.current)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [draft])

  const addDirectory = async () => {
    const picked = await window.agentBridge.pickDirectory()
    if (!picked) return
    if (draft.security.allowed_dirs.includes(picked)) return
    patchSecurity({ allowed_dirs: [...draft.security.allowed_dirs, picked] })
  }

  return (
    <div className="max-w-[760px]">
      <div className="flex items-start gap-4">
        <div className="flex-1">
          <h2 className="text-[15px] font-semibold text-ink">安全与通用</h2>
          <p className="mt-1 text-[12.5px] leading-relaxed text-ink-soft">
            控制高危操作的处理方式、文件可访问范围，以及客户端的通用行为。
            改动会自动保存，无需手动点保存。
          </p>
        </div>
        {/* 自动保存的状态指示（替代原来的「保存」按钮） */}
        <span
          className={clsx(
            'shrink-0 pt-1 text-[11.5px] whitespace-nowrap',
            saving ? 'text-ink-faint' : saved ? 'text-success' : 'text-ink-faint',
          )}
        >
          {saving ? '保存中…' : saved ? '已自动保存' : '改动后自动保存'}
        </span>
      </div>

      <div className="mt-5">
        <Section
          title="权限确认"
          description="有副作用的技能（写入、删除、发送等）在执行前如何处理。"
        >
          {/* 措辞必须对得上真实行为：「每次确认」才是出厂默认（后端
              ``SecuritySettings.confirm_mode = "interactive"``，见 config/schemas.py，
              另有测试 test_security.py::test_新装默认是每次确认 钉着）。
              以前给「自动批准」标的是"（出厂默认）"，与真实默认**正好相反** ——
              用户会据此以为"它默认就会自动执行"，那是完全另一套风险假设。 */}
          <Field label="确认模式">
            <Select
              value={draft.security.confirm_mode}
              onChange={(event) =>
                patchSecurity({
                  confirm_mode: event.target.value as AppSettings['security']['confirm_mode'],
                })
              }
            >
              <option value="interactive">每次确认（出厂默认）</option>
              <option value="deny">一律拒绝（最安全）</option>
              <option value="auto_approve">自动批准（兼顾方便与安全）</option>
            </Select>
          </Field>

          {/*
            ⚠️ 这块位置前后放过两样东西，都按产品要求**剔除**了：
            1. 「确认超时（秒）」—— 移除：确认弹窗现在**永不超时**，
               一直等到用户点「允许 / 拒绝」，或被停止 / 关会话 / 重启而作废；
            2. 「确认弹窗」那段行为说明 —— 移除（产品要求）。

            为什么不留着标成"已失效"：一个改了没效果的输入框比没有它更糟 ——
            用户会以为"我设成 5 秒了，它怎么还在等"，然后开始怀疑整个设置页。
            判断标准是"它有没有在替用户做判断"：这两块都只是复述行为；
            而下面那条自动批准的警告说的是"高危操作仍会被拒绝"，会直接影响
            用户的安全决策，所以**留着**。
          */}

          {draft.security.confirm_mode === 'auto_approve' ? (
            <div className="mt-2 rounded-[8px] border border-warning/30 bg-warning-soft px-3 py-2 text-[12px] text-warning">
              自动批准：需要确认的操作不再询问、直接执行。高危（admin）级操作仍会被拒绝（定时任务除外，见「自动化任务」页）。
            </div>
          ) : null}
        </Section>

        <Section
          title="文件访问白名单"
          description="技能只能读写以下目录内的文件。留空表示不加限制（不建议）。"
        >
          <div className="flex flex-col gap-2">
            {draft.security.allowed_dirs.map((dir) => (
              <div
                key={dir}
                className="flex items-center gap-2 rounded-[8px] border border-line bg-canvas px-2.5 py-1.5"
              >
                <span className="selectable min-w-0 flex-1 truncate text-[12.5px] text-ink" title={dir}>
                  {dir}
                </span>
                <button
                  type="button"
                  onClick={() =>
                    patchSecurity({
                      allowed_dirs: draft.security.allowed_dirs.filter((item) => item !== dir),
                    })
                  }
                  className="no-drag flex h-6 w-6 items-center justify-center rounded-[6px] text-ink-faint hover:bg-danger-soft hover:text-danger"
                  aria-label="移除"
                >
                  <Trash2 size={13} />
                </button>
              </div>
            ))}
            <Button
              size="sm"
              className="self-start"
              icon={<FolderPlus size={13} />}
              onClick={() => void addDirectory()}
            >
              添加目录
            </Button>
          </div>
        </Section>

        {/* 「给技能的密钥」：搭子请求用户提供、只存本机的凭据。
            ⚠️ 与上面那个"文件访问白名单"是**两件事**，别搞混：
            白名单管的是"技能能读写哪些目录"，这个管的是"用户交出去的凭据怎么保管"。
            放在这一页是因为它同属"安全"这一组，而且用户找不到它时会以为没地方删。 */}
        <SkillSecretsCard />

        <Section
          title="用量与预算"
          description="费用统计的展示方式。各模型的单价在「模型服务商」页签里逐个填写。"
        >
          <div className="grid grid-cols-3 gap-3">
            <Field label="货币单位">
              <Select
                value={draft.usage.currency}
                onChange={(event) =>
                  patchUsage({ currency: event.target.value as AppSettings['usage']['currency'] })
                }
              >
                <option value="CNY">人民币（¥）</option>
                <option value="USD">美元（$）</option>
              </Select>
            </Field>

            <Field label="每日预算" hint="超过后仅提示，不阻止发送">
              <Input
                type="number"
                min={0}
                step="0.01"
                placeholder="留空表示不提示"
                value={draft.usage.daily_budget ?? ''}
                onChange={(event) => {
                  const raw = event.target.value.trim()
                  // 空字符串 -> null（不提示），而不是 0（"预算为零"）。
                  // 后者会让每一次发送都触发超支提示，用户只能被迫关掉功能。
                  patchUsage({ daily_budget: raw === '' ? null : Number(raw) || 0 })
                }}
              />
            </Field>

            <Field label="流水保留天数" hint="做月度对比，建议比审计日志长">
              <Input
                type="number"
                min={1}
                value={draft.usage.retention_days}
                onChange={(event) =>
                  patchUsage({ retention_days: Number(event.target.value) || 365 })
                }
              />
            </Field>
          </div>
        </Section>

        <Section
          title="长期记忆"
          description="把资料存进本地向量库，之后 Agent 可以按语义检索出来。数据只存在本机。"
        >
          <label className="flex items-center gap-3 text-[12.5px] text-ink-soft">
            <Switch
              checked={draft.memory.long_term_enabled}
              onChange={(long_term_enabled) => patchMemory({ long_term_enabled })}
              label="启用长期记忆"
            />
            启用长期记忆（kb_add / kb_search 技能）
          </label>

          {/*
            本地嵌入模型（**不再随安装包分发**，改按需下载）。
            放在这里是为了承接产品约定 —— "跳过的用户在记忆设置这儿补装"，
            并且顺手给一个「验证一下」：那个按钮**只做一次自检**（真加载模型跑一遍），
            不是"打开某个设置页"（产品要求这么定）。
          */}
          <ModelDownloadCard modelKey="embedding" className="mt-3" />

          {draft.memory.long_term_enabled ? (
            <div className="mt-3 grid grid-cols-2 gap-3">
              <Field
                label="默认检索条数"
                hint="每次按语义检索记忆时取回几条。取回的越多信息越全，但也越占对话上下文。"
              >
                <Input
                  type="number"
                  min={1}
                  max={20}
                  value={draft.memory.vector_top_k}
                  onChange={(event) =>
                    patchMemory({ vector_top_k: Number(event.target.value) || 5 })
                  }
                />
              </Field>
              <div className="col-span-2">
                <div className="text-[12.5px] text-ink-soft">嵌入方式</div>
                <div className="mt-2 flex flex-wrap gap-1.5">
                  {EMBEDDING_BACKENDS.map((option) => (
                    <button
                      key={option.value}
                      type="button"
                      onClick={() => patchMemory({ embedding_backend: option.value })}
                      className={clsx(
                        'rounded-[7px] border px-2.5 py-1 text-[12px] transition-colors',
                        embeddingBackend === option.value
                          ? 'border-brand/40 bg-brand-soft text-brand'
                          : 'border-line text-ink-soft hover:text-ink',
                      )}
                    >
                      {option.label}
                    </button>
                  ))}
                </div>
                <p className="mt-1.5 text-[11px] leading-relaxed text-ink-faint">
                  {EMBEDDING_BACKENDS.find((item) => item.value === embeddingBackend)?.hint}
                </p>
              </div>

              {embeddingBackend === 'api' ? (
                <>
                  <Field
                    label="接口地址"
                    hint="形如 https://xxx/v1；留空则复用下面那个已配置模型的地址"
                  >
                    <Input
                      value={draft.memory.embedding_base_url}
                      placeholder="https://api.example.com/v1"
                      onChange={(event) =>
                        patchMemory({ embedding_base_url: event.target.value })
                      }
                    />
                  </Field>
                  <Field label="嵌入模型名">
                    <Input
                      value={draft.memory.embedding_model}
                      placeholder="text-embedding-v3"
                      onChange={(event) => patchMemory({ embedding_model: event.target.value })}
                    />
                  </Field>
                  <Field
                    label="密钥来源（推荐）"
                    hint="复用已配置模型的密钥：它走系统加密托管，不会明文写进配置文件"
                  >
                    <Select
                      value={draft.memory.embedding_key_model_id}
                      onChange={(event) =>
                        patchMemory({ embedding_key_model_id: event.target.value })
                      }
                    >
                      <option value="">不复用（改用下面填的密钥）</option>
                      {models.map((item) => (
                        <option key={item.id} value={item.id}>
                          {item.display_name}
                        </option>
                      ))}
                    </Select>
                  </Field>
                  <Field label="密钥" hint="留空就用上面复用的那条；填了会明文存在本机配置文件里">
                    <Input
                      type="password"
                      value={draft.memory.embedding_api_key}
                      onChange={(event) => patchMemory({ embedding_api_key: event.target.value })}
                    />
                  </Field>
                </>
              ) : null}

              {embeddingBackend === 'ollama' ? (
                <>
                  <Field label="Ollama 地址">
                    <Input
                      value={draft.memory.embedding_ollama_url}
                      onChange={(event) =>
                        patchMemory({ embedding_ollama_url: event.target.value })
                      }
                    />
                  </Field>
                  <Field
                    label="用哪个模型"
                    hint={ollamaError || '点「读取本机模型」列出你已经装好的模型'}
                  >
                    <div className="flex items-center gap-2">
                      <Select
                        className="min-w-0 flex-1"
                        value={draft.memory.embedding_ollama_model}
                        onChange={(event) =>
                          patchMemory({ embedding_ollama_model: event.target.value })
                        }
                      >
                        <option value="">请选择…</option>
                        {ollamaModels.map((name) => (
                          <option key={name} value={name}>
                            {name}
                          </option>
                        ))}
                      </Select>
                      <Button
                        variant="secondary"
                        onClick={() => void loadOllamaModels()}
                        disabled={ollamaLoading}
                      >
                        {ollamaLoading ? '读取中…' : '读取本机模型'}
                      </Button>
                    </div>
                  </Field>
                </>
              ) : null}
            </div>
          ) : null}

          <div className="mt-3 rounded-[8px] border border-line bg-canvas px-3 py-2 text-[11.5px] leading-relaxed text-ink-faint">
            默认用<b className="text-ink-soft">内置中文模型</b>
            （Qwen3-Embedding-0.6B，约 585 MB）。
            ⚠️ 它<b className="text-ink-soft">不在安装包里</b>
            ：第一次要用时在上面那张卡片点一次「下载」，之后不用联网、不花钱。
            向量库依赖 <code className="text-ink-soft">chromadb</code>，这一部分随客户端分发。
            向量数据与模型都只在本机，不会上传。
            <br />
            <b className="text-ink-soft">向量维度由嵌入方式决定</b>：内置模型是{' '}
            <b className="text-ink-soft">1024 维</b>
            —— 那是这个模型本身的输出维度，不是本地向量库的限制；换成「自定义接口」或
            「本机 Ollama」后，维度完全由你选的模型决定（768 维、1536 维都能用）。
            <br />
            ⚠️ 换嵌入方式之后，库里的旧向量会跟新模型<b className="text-ink-soft">对不上</b>
            （维度不同，算不了相似度）。这时客户端会自动用
            <b className="text-ink-soft">当前模型把原文重新嵌入一遍</b>
            —— <b className="text-ink-soft">记忆本身不会丢</b>
            ：向量只是原文的一份索引，原文一直存在库里；重建期间那一小会儿检索会暂时跳过。
          </div>
        </Section>

        <Section title="隐私" description="日志、追踪与审计中的敏感信息处理。">
          <label className="flex items-center gap-3 text-[12.5px] text-ink-soft">
            <Switch
              checked={draft.security.redact_enabled}
              onChange={(redact_enabled) => patchSecurity({ redact_enabled })}
              label="敏感信息脱敏"
            />
            日志与追踪中自动脱敏手机号、身份证号与 API Key
          </label>

          <label className="mt-3 flex items-center gap-3 text-[12.5px] text-ink-soft">
            <Switch
              checked={draft.trace_enabled}
              onChange={(trace_enabled) => patch({ trace_enabled })}
              label="记录执行链路"
            />
            记录每次任务的完整执行链路（右侧「执行链路」面板的数据来源）
          </label>
        </Section>

        {/*
          ⚠️ 这里原先是一个「语音」分区（从语音输入区收窄成的一段说明）。
          产品要求**整块剔除**：语音设置本来就全在输入栏上那个
          「语音设置」面板里（分「全局」/「当前主体」两区，后者在群聊页对应当前群），
          在设置页再复述一遍只会让人以为"这里也能改"。
          面板本身没动 —— 唤醒词、命令词照旧在那里改。
        */}

        <Section
          title="搭子团队"
          description="AI 自己组队、在后台跑群聊讨论时的表现。"
        >
          <label className="flex items-center gap-3 text-[12.5px] text-ink-soft">
            <Switch
              checked={draft.agent.auto_open_group_window}
              onChange={(auto_open_group_window) => patchAgent({ auto_open_group_window })}
              label="自动弹出讨论观察窗"
            />
            AI 在后台发起群聊时，自动弹一个只读的观察窗让我看得见它在干什么
          </label>
          <p className="mt-1.5 text-[11.5px] leading-relaxed text-ink-faint">
            观察窗不会抢走你的输入焦点；关掉它也不会中断那场讨论。关掉这个开关后，
            讨论照跑、结论照回发到对话里，只是不再自动开窗（通知里仍然留着入口）。
          </p>
        </Section>

        <Section title="智能体行为" description="影响模型的推理循环与上下文管理。">
          <div className="grid grid-cols-2 gap-3">
            {/* 这个输入框原先写着"最大循环轮数 / 推荐 10～15 / max=50" ——
                它是"没执行几个就提示已达到最大执行轮数"的另一半原因：
                后端的默认值早就改成 500 了，**界面上限却还卡在 50**，
                用户想调大都调不了。用户的原话是"我们一直都是不设对话轮数上限"。 */}
            <Field
              label="单次任务最大执行步数"
              hint="模型↔工具的往返次数上限。默认 500（对正常任务等于不限制）；留一个极端兜底，避免真死循环时把 token 无限烧下去"
            >
              <Input
                type="number"
                min={1}
                max={100000}
                value={draft.agent.max_iterations}
                onChange={(event) =>
                  patchAgent({ max_iterations: Number(event.target.value) || 500 })
                }
              />
            </Field>

            <Field label="单轮最多工具调用" hint="一次模型回复中最多并行执行几个工具">
              <Input
                type="number"
                min={1}
                max={20}
                value={draft.agent.max_tool_calls_per_turn}
                onChange={(event) =>
                  patchAgent({ max_tool_calls_per_turn: Number(event.target.value) || 5 })
                }
              />
            </Field>

            <Field
              label="上下文预算上限（tokens）"
              hint="0 = 跟随所选模型的上下文窗口（推荐）。填正数当作硬上限，用于控成本"
            >
              <Input
                type="number"
                min={0}
                value={draft.agent.max_context_tokens}
                onChange={(event) =>
                  // **0 是合法值**（表示不设上限），不能被 `|| 32000` 吞掉变成默认值 ——
                  // 那会让用户永远没法把它改回"跟随模型"
                  patchAgent({ max_context_tokens: Number(event.target.value) || 0 })
                }
              />
            </Field>

            <Field
              label="压缩 / 规划 / 自检用哪个模型"
              hint="这三件事各要额外调一次模型。留空 = 跟随当前对话的模型（默认）；想省钱可以指定一个便宜的小模型"
            >
              <Select
                value={draft.agent.utility_model_id ?? ''}
                onChange={(event) => patchAgent({ utility_model_id: event.target.value })}
              >
                <option value="">跟随当前对话的模型（默认）</option>
                {models.map((item) => (
                  <option key={item.id} value={item.id}>
                    {item.display_name}
                  </option>
                ))}
              </Select>
            </Field>

            <Field label="温度" hint="0 最稳定，越大越有创意">
              <Input
                type="number"
                step={0.1}
                min={0}
                max={2}
                value={draft.agent.temperature}
                onChange={(event) =>
                  patchAgent({ temperature: Number(event.target.value) || 0.7 })
                }
              />
            </Field>

            {/*
              下面三个默认留空 = **不发送这个字段**。留空是有意义的默认值，
              所以 placeholder 写"不发送"而不是给一个数字 —— 给了数字用户就会
              以为那是当前生效的值。
            */}
            <Field
              label="top_p（核采样）"
              hint="留空不发送。与温度二选一，两个同时调会互相干扰"
            >
              <Input
                type="number"
                step={0.05}
                min={0}
                max={1}
                value={draft.agent.top_p ?? ''}
                placeholder="不发送"
                onChange={(event) =>
                  patchAgent({
                    top_p: event.target.value === '' ? null : Number(event.target.value),
                  })
                }
              />
            </Field>

            <Field
              label="频率惩罚"
              hint="留空不发送。正数压低重复用词，治“车轱辘话”；通义 / 智谱等不支持"
            >
              <Input
                type="number"
                step={0.1}
                min={-2}
                max={2}
                value={draft.agent.frequency_penalty ?? ''}
                placeholder="不发送"
                onChange={(event) =>
                  patchAgent({
                    frequency_penalty:
                      event.target.value === '' ? null : Number(event.target.value),
                  })
                }
              />
            </Field>

            <Field
              label="存在惩罚"
              hint="留空不发送。正数促它换角度、扩大覆盖面；与频率惩罚同调容易互相抵消"
            >
              <Input
                type="number"
                step={0.1}
                min={-2}
                max={2}
                value={draft.agent.presence_penalty ?? ''}
                placeholder="不发送"
                onChange={(event) =>
                  patchAgent({
                    presence_penalty:
                      event.target.value === '' ? null : Number(event.target.value),
                  })
                }
              />
            </Field>
          </div>

          {/* 这里曾有「自定义系统提示词」输入框。提示词现在只由搭子自己的五个人格
              文档组装（设置 → 搭子 → 编辑 → 人格与记忆），这个字段已不再被任何地方
              读取 —— 留在界面上只会骗人，所以整块删掉。字段本身
              （AgentSettings.system_prompt / 会话 / 搭子三处）保留，零迁移风险。 */}
          {/* 窄窗口下这行会挤：标签、三颗按钮、一句长提示抢一条线。
              标签必须**先**保住自己（shrink-0 + nowrap），让该换行的换到下一行 ——
              不这么做的话被压扁的是标签，症状是"点关闭按钮 / 时"折成两行
              实测反馈现象）。行上加 flex-wrap 是给长提示句留的出口。 */}
          <div className="mt-4 flex flex-wrap items-center gap-2">
            <span className="shrink-0 whitespace-nowrap text-[12.5px] text-ink-soft">
              点关闭按钮时
            </span>
            <div className="flex gap-1.5">
              {CLOSE_ACTION_OPTIONS.map((option) => (
                <button
                  key={option.value}
                  type="button"
                  onClick={() => setCloseAction(option.value)}
                  className={clsx(
                    'no-drag rounded-[7px] border px-2.5 py-1 text-[12px] whitespace-nowrap transition-colors',
                    closeAction === option.value
                      ? 'border-brand/40 bg-brand-soft text-brand'
                      : 'border-line text-ink-soft hover:text-ink',
                  )}
                >
                  {option.label}
                </button>
              ))}
            </div>
            <span className="ml-2 text-[11.5px] text-ink-faint">
              第一次点关闭时会问一次，可以勾选「记住我的选择」；选错了随时能在这里改回来。
            </span>
          </div>
        </Section>
      </div>
    </div>
  )
}
