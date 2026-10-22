import clsx from 'clsx'
import {
  Blocks,
  BookOpen,
  Brain,
  Briefcase,
  Coffee,
  Cpu,
  Lightbulb,
  Loader2,
  Plug,
  Plus,
  RefreshCw,
  ShieldCheck,
  Tag,
  UserRound,
  type LucideIcon,
} from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'

import { openAddSkill, useSkillRevision } from '@/components/AddSkillDialog'
import { sourceLabel } from '@/components/skillImport'
import { Badge, Button, Field, Input, Modal, Select, Switch } from '@/components/ui'
import { useAppStore } from '@/stores/appStore'
import { useNotificationStore } from '@/stores/notificationStore'
import type {
  CustomSkillDef,
  CustomSkillParam,
  SkillFileEntry,
  SkillFolderInfo,
  SkillInfo,
} from '@/types'









function formatBytes(size: number): string {
  if (size < 1024) return `${size}B`
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)}KB`
  return `${(size / 1024 / 1024).toFixed(1)}MB`
}










const CATEGORY_META: Record<string, { label: string; icon: LucideIcon }> = {
  office: { label: '办公', icon: Briefcase },
  life: { label: '生活', icon: Coffee },
  system: { label: '系统', icon: Cpu },
  memory: { label: '记忆', icon: Brain },
  knowledge: { label: '知识', icon: BookOpen },
  thinking: { label: '思考', icon: Lightbulb },
  persona: { label: '人格', icon: UserRound },
  general: { label: '通用', icon: Blocks },
  custom: { label: '我的技能', icon: Blocks },
  mcp: { label: 'MCP 外部工具', icon: Plug },
}










const CATEGORY_ORDER: readonly string[] = [
  'office',
  'life',
  'system',
  'memory',
  'knowledge',
  'thinking',
  'persona',
  'general',
  'custom',
  'mcp',
]










type SkillBucket = 'mine' | 'common' | 'builtin' | 'exclusive'

const BUCKETS: ReadonlyArray<{ key: SkillBucket; label: string; note: string }> = [
  { key: 'mine', label: '我的技能', note: '你上传的、AI 创建的、AI 下载安装的技能' },
  { key: 'common', label: '通用技能', note: '按需挑选：预设能力与 MCP 外部工具' },
  { key: 'builtin', label: '内置技能', note: '每个搭子创建时即自带，不可关闭' },
  { key: 'exclusive', label: '专属技能', note: '只有归属的那个搭子能用，不可关闭' },
]















const DOMAIN_ORDER: readonly string[] = [
  '系统',
  '办公',
  '生活',
  '学术',
  '媒体',
  '法律',
  '医疗',
  '电商',
  '金融',
  '营销',
  '教育',
  '科技',
  '设计',
  '人力',
]



















function domainLabel(skill: SkillInfo): string {
  if (skill.domain) return skill.domain
  return CATEGORY_META[skill.category]?.label ?? skill.category
}

const PERMISSION_OPTIONS: Array<{ value: SkillInfo['permission_level']; label: string }> = [
  { value: 'safe', label: '只读（直接执行）' },
  { value: 'confirm', label: '需确认' },
  { value: 'admin', label: '高危（需开启）' },
]

function permissionTone(level: string): 'success' | 'warning' | 'danger' {
  if (level === 'safe') return 'success'
  if (level === 'confirm') return 'warning'
  return 'danger'
}

function blankCustomSkill(): CustomSkillDef {
  return {
    id: '',
    name: '',
    description: '',
    params: [{ name: '', description: '', required: true, default: null, type: 'string' }],
    kind: 'http',
    url: '',
    method: 'GET',
    headers: {},
    body_template: '',
    command_template: '',
    timeout: 30,
    permission_level: 'confirm',
    enabled: true,
  }
}








function CustomSkillsSection({ onChanged }: { onChanged: () => void }) {
  const api = useAppStore((state) => state.api)
  const [list, setList] = useState<CustomSkillDef[]>([])
  const [loaded, setLoaded] = useState(false)
  const [draft, setDraft] = useState<CustomSkillDef | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  







  const [folder, setFolder] = useState<SkillFolderInfo | null>(null)
  





  const revision = useSkillRevision()

  
  
  
  useEffect(() => {
    if (revision > 0) void load()
  }, [revision])
  
  const [detail, setDetail] = useState<CustomSkillDef | null>(null)
  const [detailSaving, setDetailSaving] = useState(false)
  
  const [detailFiles, setDetailFiles] = useState<SkillFileEntry[]>([])

  






  
  const openDetail = async (item: CustomSkillDef) => {
    setDetail(item)
    setDetailFiles([])
    if (!api) return
    try {
      const result = await api.getSkillFiles(item.id)
      setDetailFiles(result.files ?? [])
    } catch {
      
      setDetailFiles([])
    }
  }

  const load = async () => {
    if (!api) return
    try {
      const result = await api.getCustomSkills()
      
      
      
      
      
      setList((result.skills ?? []).filter((item) => !item.domain))
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : String(exc))
    } finally {
      setLoaded(true)
    }
  }

  if (!loaded) {
    void load()
  }
  
  if (!folder && api) {
    void api
      .getSkillFolder()
      .then(setFolder)
      .catch(() => {
        
      })
  }

  const toId = (name: string) =>
    name
      .toLowerCase()
      .replace(/[^a-z0-9_-]+/g, '-')
      .replace(/^-+|-+$/g, '') || `skill-${Date.now().toString(36)}`

  const save = async () => {
    if (!api || !draft) return
    setBusy(true)
    setError('')
    try {
      await api.saveCustomSkill({ ...draft, id: draft.id || toId(draft.name) })
      setDraft(null)
      onChanged()
      await load()
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : String(exc))
    } finally {
      setBusy(false)
    }
  }

  const remove = async (id: string) => {
    if (!api) return
    setBusy(true)
    try {
      await api.deleteCustomSkill(id)
      onChanged()
      await load()
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : String(exc))
    } finally {
      setBusy(false)
    }
  }

  
  const updateDef = async (item: CustomSkillDef, changes: Partial<CustomSkillDef>) => {
    if (!api) return
    setBusy(true)
    setError('')
    try {
      await api.saveCustomSkill({ ...item, ...changes })
      onChanged()
      await load()
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : String(exc))
    } finally {
      setBusy(false)
    }
  }

  const setParam = (index: number, patch: Partial<CustomSkillParam>) => {
    setDraft((prev) =>
      prev
        ? {
            ...prev,
            params: prev.params.map((item, i) => (i === index ? { ...item, ...patch } : item)),
          }
        : prev,
    )
  }

  return (
    <div className="mb-5">
      <div className="mb-2 flex items-center justify-between">
        <div>
          <div className="text-[12.5px] font-medium text-ink-soft">我的技能</div>
          <p className="mt-0.5 text-[11px] leading-relaxed text-ink-faint">
            把现成的技能加进来就行 —— 压缩包、文件夹都能导入，不用写代码。
          </p>
        </div>
        {

}
        <div className="flex shrink-0 items-center gap-2">
          {



}
          <Button variant="primary" icon={<Plus size={13} />} onClick={openAddSkill}>
            添加技能
          </Button>
        </div>
      </div>

      {


}
      <p className="mb-2 text-[11px] leading-relaxed text-ink-faint">
        点「添加技能」，选一个文件（压缩包或单个技能文件）或一个文件夹 —— 是什么东西它自己认，
        成没成会弹窗告诉你。
        {folder ? (
          <>
            <br />
            也可以把技能文件夹或技能文件放进这个目录，
            <span className="text-ink-soft">下次启动时会自动加进来</span>：
            <br />
            <span className="selectable text-ink-soft">{folder.inbox}</span>
          </>
        ) : null}
      </p>

      {error ? (
        <div className="mb-2 rounded-[8px] border border-danger/30 bg-danger-soft px-3 py-2 text-[12px] text-danger">
          {error}
        </div>
      ) : null}

      {list.length ? (
        <div className="space-y-2">
          {list.map((item) => (
            <div
              key={item.id}
              className="flex items-start gap-3 rounded-[10px] border border-line bg-canvas px-3.5 py-2.5"
            >
              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="text-[12.5px] font-medium text-ink">{item.name}</span>
                  {item.source_format === 'script' ? (
                    <Badge tone="warning">脚本</Badge>
                  ) : item.kind === 'instruction' ? (
                    <Badge tone="brand">指导型</Badge>
                  ) : (
                    <span className="text-[10.5px] text-ink-faint">
                      {item.kind === 'http' ? 'HTTP' : '命令'}
                    </span>
                  )}
                  {sourceLabel(item.source_format) ? (
                    <span className="text-[10.5px] text-ink-faint">
                      {sourceLabel(item.source_format)}
                    </span>
                  ) : null}
                </div>
                <p className="mt-0.5 line-clamp-2 text-[11.5px] leading-relaxed text-ink-faint">
                  {item.description}
                </p>
                {
}
                {item.note ? (
                  <p className="mt-1 rounded-[6px] border border-warning/30 px-2 py-1 text-[11px] leading-relaxed text-warning">
                    {item.note}
                  </p>
                ) : null}
                {
}
                <div className="mt-1.5 flex flex-wrap items-center gap-3">
                  <label className="flex items-center gap-1.5 text-[11px] whitespace-nowrap text-ink-soft">
                    权限
                    <select
                      value={item.permission_level}
                      disabled={busy}
                      onChange={(event) =>
                        void updateDef(item, { permission_level: event.target.value as CustomSkillDef['permission_level'] })
                      }
                      className="h-6 rounded-[6px] border border-line bg-canvas px-1 text-[11px] text-ink focus:border-brand focus:outline-none disabled:opacity-60"
                    >
                      {PERMISSION_OPTIONS.map((option) => (
                        <option key={option.value} value={option.value}>
                          {option.label}
                        </option>
                      ))}
                    </select>
                  </label>
                  <span
                    className={clsx(
                      'text-[10.5px] whitespace-nowrap',
                      item.enabled ? 'text-success' : 'text-ink-faint',
                    )}
                  >
                    {item.enabled ? '已启用' : '已停用'}
                  </span>
                </div>
              </div>
              <div className="flex shrink-0 flex-col items-end gap-1.5">
                <Switch
                  checked={item.enabled}
                  disabled={busy}
                  onChange={(enabled) => void updateDef(item, { enabled })}
                  label={`启用 ${item.name}`}
                />
                <div className="flex gap-1.5">
                  <Button onClick={() => void openDetail(item)}>查看详情</Button>
                  {}
                  {item.kind !== 'instruction' ? (
                    <Button
                      onClick={() => {
                        setError('')
                        setDraft({ ...item, params: item.params.length ? item.params : blankCustomSkill().params })
                      }}
                    >
                      编辑
                    </Button>
                  ) : null}
                  <Button
                    variant="secondary"
                    disabled={busy}
                    onClick={() => void remove(item.id)}
                  >
                    删除
                  </Button>
                </div>
              </div>
            </div>
          ))}
        </div>
      ) : (
        <div className="rounded-[10px] border border-dashed border-line px-4 py-6 text-center text-[12px] leading-relaxed text-ink-faint">
          还没有技能。点「添加技能」导入一个技能包或文件夹试试。
        </div>
      )}

      {





}

      {



}

      {}
      <Modal
        open={detail !== null}
        onClose={() => setDetail(null)}
        width="max-w-lg"
        title={`详情：${detail?.name ?? ''}`}
        footer={
          <>
            <Button onClick={() => setDetail(null)}>关闭</Button>
            {}
            {detail?.kind === 'instruction' ? (
              <Button
                variant="primary"
                icon={detailSaving ? <Loader2 size={13} className="animate-spin" /> : undefined}
                disabled={detailSaving}
                onClick={async () => {
                  if (!detail || !api) return
                  setDetailSaving(true)
                  try {
                    await api.saveCustomSkill(detail)
                    onChanged()
                    await load()
                    setDetail(null)
                  } catch (exc) {
                    setError(exc instanceof Error ? exc.message : String(exc))
                  } finally {
                    setDetailSaving(false)
                  }
                }}
              >
                {detailSaving ? '保存中…' : '保存修改'}
              </Button>
            ) : null}
          </>
        }
      >
        {detail ? (
          <div className="space-y-3 text-[12.5px] leading-relaxed">
            <div className="flex flex-wrap items-center gap-2">
              <Badge tone={permissionTone(detail.permission_level)}>{detail.permission_level}</Badge>
              {detail.kind === 'instruction' ? (
                <Badge tone="brand">指导型</Badge>
              ) : (
                <Badge>{detail.kind === 'http' ? 'HTTP' : '命令'}</Badge>
              )}
              <Badge tone={detail.enabled ? 'success' : 'neutral'}>
                {detail.enabled ? '已启用' : '已停用'}
              </Badge>
              {sourceLabel(detail.source_format) ? (
                <span className="text-[11px] text-ink-faint">
                  来源：{sourceLabel(detail.source_format)}
                </span>
              ) : null}
            </div>
            {}
            {detail.note ? (
              <p className="rounded-[6px] border border-warning/30 px-2 py-1 text-[12px] leading-relaxed text-warning">
                {detail.note}
              </p>
            ) : null}
            <div>
              <div className="text-[11.5px] text-ink-faint">什么时候用（给模型看）</div>
              <p className="mt-0.5 selectable whitespace-pre-wrap text-ink">{detail.description}</p>
            </div>
            {detail.kind === 'instruction' ? (
              <div>
                <div className="text-[11.5px] text-ink-faint">
                  指导内容（进入对话）—— 可以直接在这里修改，点下方保存生效
                </div>
                <textarea
                  value={detail.instructions ?? ''}
                  onChange={(event) => setDetail({ ...detail, instructions: event.target.value })}
                  rows={10}
                  className="selectable mt-0.5 w-full resize-y rounded-[8px] border border-line bg-canvas px-2.5 py-2 text-[12px] leading-relaxed text-ink focus:border-brand focus:outline-none"
                />
              </div>
            ) : (
              <>
                {detail.kind === 'http' ? (
                  <div>
                    <div className="text-[11.5px] text-ink-faint">请求</div>
                    <code className="selectable mt-0.5 block break-all rounded-[6px] bg-panel px-2 py-1 text-[12px]">
                      {detail.method} {detail.url || '（未填地址）'}
                    </code>
                  </div>
                ) : (
                  <div>
                    <div className="text-[11.5px] text-ink-faint">命令</div>
                    <code className="selectable mt-0.5 block break-all rounded-[6px] bg-panel px-2 py-1 text-[12px]">
                      {detail.command_template || '（未填命令）'}
                    </code>
                  </div>
                )}
                <div>
                  <div className="text-[11.5px] text-ink-faint">参数</div>
                  {detail.params.length ? (
                    <ul className="mt-0.5 list-disc pl-5">
                      {detail.params.map((param) => (
                        <li key={param.name}>
                          <code className="text-[12px]">{param.name}</code>
                          {param.required ? '（必填）' : '（可选）'}
                          {param.description ? ` —— ${param.description}` : ''}
                        </li>
                      ))}
                    </ul>
                  ) : (
                    <p className="mt-0.5 text-ink-faint">无参数</p>
                  )}
                </div>
              </>
            )}
            {
}
            {detailFiles.length ? (
              <div>
                <div className="text-[11.5px] text-ink-faint">
                  这个技能带的东西（{detailFiles.length} 个文件）—— 搭子要用的时候会自己去看
                </div>
                <div className="mt-1 max-h-48 overflow-y-auto rounded-[8px] border border-line bg-canvas px-2.5 py-1.5">
                  {detailFiles.map((file) => (
                    <div
                      key={file.path}
                      className="flex items-baseline justify-between gap-3 text-[11.5px]"
                    >
                      <code className="selectable break-all text-ink">{file.path}</code>
                      <span className="shrink-0 text-ink-faint">{formatBytes(file.size)}</span>
                    </div>
                  ))}
                </div>
              </div>
            ) : null}
            <div className="text-[11px] text-ink-faint">
              id：{detail.id} · 超时 {detail.timeout}s
            </div>
          </div>
        ) : null}
      </Modal>

      <Modal
        open={draft !== null}
        onClose={() => setDraft(null)}
        width="max-w-2xl"
        title={list.some((item) => item.id === draft?.id) ? `编辑：${draft?.name}` : '新建技能'}
        description="说明会原样交给模型 —— 它靠这段话判断什么时候该用这个技能。"
        footer={
          <>
            <Button onClick={() => setDraft(null)}>取消</Button>
            <Button
              variant="primary"
              icon={busy ? <Loader2 size={13} className="animate-spin" /> : undefined}
              disabled={busy || !draft?.name.trim()}
              onClick={() => void save()}
            >
              {busy ? '保存中…' : '保存并启用'}
            </Button>
          </>
        }
      >
        {draft ? (
          <div className="space-y-3">
            <div className="grid grid-cols-2 gap-3">
              <Field label="技能名">
                <Input
                  value={draft.name}
                  onChange={(event) => setDraft({ ...draft, name: event.target.value })}
                  placeholder="例如 查快递"
                />
              </Field>
              <Field label="什么时候用（给模型看的说明）">
                <Input
                  value={draft.description}
                  onChange={(event) => setDraft({ ...draft, description: event.target.value })}
                  placeholder="当用户说「查快递」时调用"
                />
              </Field>
            </div>

            <div className="flex items-center gap-2">
              <span className="text-[12.5px] text-ink-soft">动作类型</span>
              {(
                [
                  { value: 'http', label: '发一个 HTTP 请求' },
                  { value: 'command', label: '跑一条本机命令' },
                ] as const
              ).map((option) => (
                <button
                  key={option.value}
                  type="button"
                  onClick={() => setDraft({ ...draft, kind: option.value })}
                  className={clsx(
                    'rounded-[7px] border px-2.5 py-1 text-[12px] transition-colors',
                    draft.kind === option.value
                      ? 'border-brand/40 bg-brand-soft text-brand'
                      : 'border-line text-ink-soft hover:text-ink',
                  )}
                >
                  {option.label}
                </button>
              ))}
            </div>

            {draft.kind === 'http' ? (
              <>
                <div className="grid grid-cols-[120px_1fr] gap-3">
                  <Field label="请求方式">
                    <Select
                      value={draft.method}
                      onChange={(event) =>
                        setDraft({ ...draft, method: event.target.value as CustomSkillDef['method'] })
                      }
                    >
                      {['GET', 'POST', 'PUT', 'DELETE'].map((method) => (
                        <option key={method} value={method}>
                          {method}
                        </option>
                      ))}
                    </Select>
                  </Field>
                  <Field label="地址" hint="可以用 {参数名} 占位">
                    <Input
                      value={draft.url}
                      onChange={(event) => setDraft({ ...draft, url: event.target.value })}
                      placeholder="https://api.example.com/query?q={city}"
                    />
                  </Field>
                </div>
                <Field label="请求体模板（GET 可留空）" hint="JSON 里直接写 {参数名} 即可">
                  <Input
                    value={draft.body_template}
                    onChange={(event) => setDraft({ ...draft, body_template: event.target.value })}
                    placeholder='{"q": "{city}"}'
                  />
                </Field>
              </>
            ) : (
              <Field label="要执行的命令" hint="可以用 {参数名} 占位；会以本机当前用户身份运行">
                <Input
                  value={draft.command_template}
                  onChange={(event) => setDraft({ ...draft, command_template: event.target.value })}
                  placeholder="ping {host}"
                />
              </Field>
            )}

            <div>
              <div className="mb-1.5 flex items-center justify-between">
                <span className="text-[12.5px] text-ink-soft">参数</span>
                <Button
                  onClick={() =>
                    setDraft({
                      ...draft,
                      params: [
                        ...draft.params,
                        { name: '', description: '', required: true, default: null, type: 'string' },
                      ],
                    })
                  }
                >
                  加一个参数
                </Button>
              </div>
              <div className="space-y-2">
                {draft.params.map((param, index) => (
                  <div key={index} className="grid grid-cols-[130px_1fr_auto_auto] items-center gap-2">
                    <Input
                      value={param.name}
                      onChange={(event) => setParam(index, { name: event.target.value.trim() })}
                      placeholder="参数名"
                    />
                    <Input
                      value={param.description}
                      onChange={(event) => setParam(index, { description: event.target.value })}
                      placeholder="这个参数是什么（给模型看）"
                    />
                    <label className="flex items-center gap-1.5 text-[11.5px] text-ink-soft">
                      <Switch
                        checked={param.required}
                        onChange={(required) => setParam(index, { required })}
                        label="必填"
                      />
                      必填
                    </label>
                    <Button
                      variant="secondary"
                      disabled={draft.params.length <= 1}
                      onClick={() =>
                        setDraft({
                          ...draft,
                          params: draft.params.filter((_, i) => i !== index),
                        })
                      }
                    >
                      删
                    </Button>
                  </div>
                ))}
              </div>
            </div>

            <div className="grid grid-cols-2 gap-3">
              <Field label="执行前是否要确认">
                <Select
                  value={draft.permission_level}
                  onChange={(event) =>
                    setDraft({
                      ...draft,
                      permission_level: event.target.value as CustomSkillDef['permission_level'],
                    })
                  }
                >
                  {PERMISSION_OPTIONS.map((option) => (
                    <option key={option.value} value={option.value}>
                      {option.label}
                    </option>
                  ))}
                </Select>
              </Field>
              <Field label="超时（秒）">
                <Input
                  type="number"
                  min={1}
                  max={120}
                  value={draft.timeout}
                  onChange={(event) =>
                    setDraft({ ...draft, timeout: Number(event.target.value) || 30 })
                  }
                />
              </Field>
            </div>
          </div>
        ) : null}
      </Modal>
    </div>
  )
}

export function SkillSettings() {
  const skills = useAppStore((state) => state.skills)
  const api = useAppStore((state) => state.api)
  const reloadSkills = useAppStore((state) => state.reloadSkills)
  const reloadHealth = useAppStore((state) => state.reloadHealth)

  const [busy, setBusy] = useState<string | null>(null)
  const [reloading, setReloading] = useState(false)
  
  const [detailSkill, setDetailSkill] = useState<SkillInfo | null>(null)
  



  const [bucket, setBucket] = useState<SkillBucket>('mine')

  
  const [domain, setDomain] = useState<string>('all')

  
  const byBucket = useMemo(() => {
    const map: Record<SkillBucket, SkillInfo[]> = { mine: [], common: [], builtin: [], exclusive: [] }
    for (const skill of skills) {
      
      const key = (skill.bucket ?? (skill.source === 'custom' ? 'mine' : 'common')) as SkillBucket
      ;(map[key] ?? map.common).push(skill)
    }
    return map
  }, [skills])

  
  const domainOptions = useMemo(() => {
    const found = new Set<string>()
    for (const skill of byBucket[bucket]) {
      
      
      
      
      found.add(domainLabel(skill))
    }
    const ordered = DOMAIN_ORDER.filter((item) => found.has(item))
    const rest = [...found].filter((item) => !DOMAIN_ORDER.includes(item)).sort()
    return [...ordered, ...rest]
  }, [byBucket, bucket])

  








  const scoped = useMemo(() => {
    if (bucket !== 'common' || domain === 'all') return byBucket[bucket]
    return byBucket[bucket].filter((skill) => domainLabel(skill) === domain)
  }, [byBucket, bucket, domain])

  
  const grouped = useMemo(() => {
    const map = new Map<string, SkillInfo[]>()
    for (const skill of scoped) {
      
      
      
      
      const key =
        bucket === 'exclusive'
          ? skill.owner_label || '专属'
          : bucket === 'common'
            ? domainLabel(skill)
            : skill.category
      const list = map.get(key) ?? []
      list.push(skill)
      map.set(key, list)
    }
    
    
    const rank = (category: string) => {
      const index = CATEGORY_ORDER.indexOf(category)
      if (index >= 0) return index
      const domainIndex = DOMAIN_ORDER.indexOf(category)
      return domainIndex < 0
        ? CATEGORY_ORDER.length + DOMAIN_ORDER.length
        : CATEGORY_ORDER.length + domainIndex
    }
    return [...map.entries()].sort(([a], [b]) => rank(a) - rank(b) || a.localeCompare(b))
  }, [scoped, bucket])

  
  const visibleGroups = bucket === 'mine' ? [] : grouped

  const update = async (
    skill: SkillInfo,
    payload: { enabled?: boolean; permission_level?: string },
  ) => {
    if (!api) return
    setBusy(skill.name)
    try {
      await api.patchSkill(skill.name, payload)
      await Promise.all([reloadSkills(), reloadHealth()])
    } catch (exc) {
      
      
      
      useNotificationStore.getState().push({
        level: 'warning',
        title: '这个技能改不了',
        message: exc instanceof Error ? exc.message : String(exc),
      })
      
      await Promise.all([reloadSkills(), reloadHealth()])
    } finally {
      setBusy(null)
    }
  }

  return (
    <div className="max-w-[880px]">
      <div className="flex items-start gap-4">
        <div className="flex-1">
          <h2 className="text-[15px] font-semibold text-ink">技能（工具）</h2>
          {


}
          <p className="mt-1 text-[12.5px] font-semibold leading-relaxed text-warning">
            重要提示：搭子的技能不是越多越好，那样只会让它产生大量的不必要消耗，
            我们建议每个搭子仅搭配它职能所必须的技能。
          </p>
          {



}
          <p className="mt-1 text-[12.5px] leading-relaxed text-warning">
            简要说明：技能开关只决定搭子是否能配置这个技能，而每个搭子的技能组合，要在该搭子的配置页面进行添加。
          </p>
        </div>
        <Button
          icon={reloading ? <Loader2 size={13} className="animate-spin" /> : <RefreshCw size={13} />}
          onClick={async () => {
            setReloading(true)
            try {
              await Promise.all([reloadSkills(), reloadHealth()])
            } finally {
              setReloading(false)
            }
          }}
        >
          刷新技能
        </Button>
      </div>

      {}
      <div className="mt-4 flex flex-wrap gap-2">
        {BUCKETS.map((item) => (
          <button
            key={item.key}
            type="button"
            title={item.note}
            aria-current={bucket === item.key ? 'page' : undefined}
            onClick={() => {
              setBucket(item.key)
              
              
              setDomain('all')
            }}
            className={`flex items-center gap-1.5 rounded-[10px] border px-3 py-1.5 text-[12.5px] transition-colors ${
              bucket === item.key
                ? 'border-brand/40 bg-brand-soft text-brand'
                : 'border-line bg-canvas text-ink-soft hover:border-brand/30 hover:text-ink'
            }`}
          >
            {item.label}
            <span className="text-[11px] text-ink-faint">{byBucket[item.key].length}</span>
          </button>
        ))}
      </div>

      {








}
      {bucket === 'common' && domainOptions.length > 0 ? (
        <div className="mt-2 flex flex-wrap gap-1.5">
          <button
            type="button"
            onClick={() => setDomain('all')}
            className={`rounded-[8px] border px-2.5 py-1 text-[12px] transition-colors ${
              domain === 'all'
                ? 'border-brand/40 bg-brand-soft text-brand'
                : 'border-line text-ink-soft hover:border-brand/30 hover:text-ink'
            }`}
          >
            全部
            <span className="ml-1 text-[11px] text-ink-faint">{byBucket.common.length}</span>
          </button>
          {domainOptions.map((item) => (
            <button
              key={item}
              type="button"
              onClick={() => setDomain(item)}
              className={`rounded-[8px] border px-2.5 py-1 text-[12px] transition-colors ${
                domain === item
                  ? 'border-brand/40 bg-brand-soft text-brand'
                  : 'border-line text-ink-soft hover:border-brand/30 hover:text-ink'
              }`}
            >
              {item}
              <span className="ml-1 text-[11px] text-ink-faint">
                {


}
                {byBucket.common.filter((skill) => domainLabel(skill) === item).length}
              </span>
            </button>
          ))}
        </div>
      ) : null}

      <div className="mt-4 flex flex-col gap-5">
        {bucket === 'mine' ? (
          
          
          <CustomSkillsSection
            onChanged={() => void Promise.all([reloadSkills(), reloadHealth()])}
          />
        ) : null}

        {bucket !== 'mine' && visibleGroups.length === 0 ? (
          <p className="text-[12.5px] text-ink-faint">这一类里暂时没有技能。</p>
        ) : null}

        {visibleGroups.map(([category, list]) => (
          <section key={category}>
            <div className="mb-2 flex items-center gap-2">
              {(() => {
                
                
                
                if (bucket === 'exclusive') {
                  return (
                    <>
                      <ShieldCheck size={14} className="text-ink-faint" />
                      <span className="text-[12.5px] font-medium text-ink-soft">
                        仅 {category} 可用
                      </span>
                    </>
                  )
                }
                
                
                
                
                const meta = CATEGORY_META[category]
                if (!meta) {
                  
                  return (
                    <>
                      <Tag size={14} className="text-ink-faint" />
                      <span className="text-[12.5px] font-medium text-ink-soft">{category}</span>
                    </>
                  )
                }
                const Icon = meta.icon
                return (
                  <>
                    <Icon size={14} className="text-ink-faint" />
                    <span className="text-[12.5px] font-medium text-ink-soft">{meta.label}</span>
                  </>
                )
              })()}
              <span className="text-[11.5px] text-ink-faint">{list.length} 个</span>
            </div>

            <div className="divide-y divide-line-soft overflow-hidden rounded-[10px] border border-line">
              {list.map((skill) => {
                const disabled = !skill.enabled
                
                
                
                
                
                
                
                
                
                
                
                const xjxFree =
                  skill.display_name === '人际关系运营' ||
                  skill.display_name === 'Soulmate专用' ||
                  skill.display_name === '西占' ||
                  skill.display_name === '八字' ||
                  skill.display_name === '梅花易数' ||
                  skill.display_name === '塔罗'

                
                
                
                
                
                
                
                
                
                
                
                
                
                
                
                
                const verifiedFree =
                  (Boolean(skill.domain) || skill.source === 'mcp') && skill.bucket === 'common'

                
                
                
                
                
                
                
                
                
                
                
                
                
                
                
                
                
                const foreverFree =
                  (skill.bucket === 'builtin' || skill.bucket === 'exclusive') && !xjxFree
                return (
                  <div
                    key={skill.name}
                    className={clsx('flex items-start gap-3 px-3.5 py-3', disabled && 'opacity-60')}
                  >
                    <div className="min-w-0 flex-1">
                      <div className="flex flex-wrap items-center gap-2">
                        <span className="text-[13px] font-medium text-ink">
                          {skill.display_name || skill.name}
                        </span>
                        <code className="rounded-[4px] bg-panel px-1 py-[1px] text-[11px] text-ink-faint">
                          {skill.name}
                        </code>
                        {xjxFree ? <Badge tone="success">免费</Badge> : null}
                        {verifiedFree ? <Badge tone="success">完全免费</Badge> : null}
                        {foreverFree ? <Badge tone="success">永久免费</Badge> : null}
                        <Badge tone={permissionTone(skill.permission_level)}>
                          {skill.permission_level}
                        </Badge>
                        {skill.source === 'mcp' ? <Badge tone="brand">MCP</Badge> : null}
                      </div>
                      <p className="mt-1 text-[12px] leading-relaxed text-ink-soft">
                        {skill.description}
                      </p>
                    </div>

                    <div className="flex shrink-0 items-center gap-3 pt-0.5">
                      {

}
                      {skill.locked ? (
                        <span
                          className="whitespace-nowrap"
                          title={
                            skill.locked_reason ??
                            '这是搭子长期记忆与基础能力的一部分，默认永久开启、免批准。' +
                              '不能关闭，也不能修改权限。'
                          }
                        >
                          {skill.instruction_only ? (
                            <Badge tone="brand">按线路自动 · 仅 {skill.owner_label ?? '归属搭子'}</Badge>
                          ) : (
                            <Badge tone="success">默认开启</Badge>
                          )}
                        </span>
                      ) : (
                        <>
                          <Select
                            value={skill.permission_level}
                            disabled={busy === skill.name}
                            onChange={(event) =>
                              void update(skill, { permission_level: event.target.value })
                            }
                            className="h-8 w-[132px] text-[12px]"
                          >
                            {PERMISSION_OPTIONS.map((option) => (
                              <option key={option.value} value={option.value}>
                                {option.label}
                              </option>
                            ))}
                          </Select>

                          <Switch
                            checked={skill.enabled}
                            disabled={busy === skill.name}
                            onChange={(enabled) => void update(skill, { enabled })}
                            label={`启用 ${skill.name}`}
                          />
                        </>
                      )}

                      {
}
                      <Button onClick={() => setDetailSkill(skill)}>详情</Button>
                    </div>
                  </div>
                )
              })}
            </div>
          </section>
        ))}

        {skills.length === 0 ? (
          <div className="rounded-[10px] border border-dashed border-line px-4 py-10 text-center text-[12.5px] text-ink-faint">
            暂无已注册的技能。
          </div>
        ) : null}
      </div>

      {}
      <Modal
        open={detailSkill !== null}
        onClose={() => setDetailSkill(null)}
        width="max-w-lg"
        title={`详情：${detailSkill?.display_name || (detailSkill?.name ?? '')}`}
        footer={<Button variant="primary" onClick={() => setDetailSkill(null)}>关闭</Button>}
      >
        {detailSkill ? (
          <div className="space-y-3 text-[12.5px] leading-relaxed">
            <div className="flex flex-wrap items-center gap-2">
              <Badge tone={permissionTone(detailSkill.permission_level)}>
                {detailSkill.permission_level}
              </Badge>
              <Badge tone={detailSkill.enabled ? 'success' : 'neutral'}>
                {detailSkill.enabled ? '已启用' : '已停用'}
              </Badge>
              {detailSkill.source === 'mcp' ? <Badge tone="brand">MCP</Badge> : null}
              {detailSkill.source === 'custom' ? <Badge tone="brand">自定义</Badge> : null}
            </div>
            <div>
              <div className="text-[11.5px] text-ink-faint">什么时候用（给模型看）</div>
              <p className="mt-0.5 selectable whitespace-pre-wrap text-ink">
                {detailSkill.description}
              </p>
            </div>
            <div>
              <div className="text-[11.5px] text-ink-faint">参数</div>
              {(() => {
                const entries = Object.entries(detailSkill.parameters ?? {})
                const properties = (entries.find(([key]) => key === 'properties')?.[1] ?? {}) as
                  | Record<string, Record<string, unknown>>
                  | undefined
                const required = (entries.find(([key]) => key === 'required')?.[1] ??
                  []) as string[]
                const names = properties ? Object.keys(properties) : []
                if (names.length === 0) return <p className="mt-0.5 text-ink-faint">无参数</p>
                return (
                  <ul className="mt-0.5 list-disc pl-5">
                    {names.map((name) => (
                      <li key={name}>
                        <code className="text-[12px]">{name}</code>
                        {required.includes(name) ? '（必填）' : '（可选）'}
                        {typeof properties?.[name]?.description === 'string'
                          ? ` —— ${properties[name].description as string}`
                          : ''}
                      </li>
                    ))}
                  </ul>
                )
              })()}
            </div>
            <div className="text-[11px] text-ink-faint">
              工具名：{detailSkill.name} · 分类 {detailSkill.category} · 超时 {detailSkill.timeout}s
            </div>
          </div>
        ) : null}
      </Modal>
    </div>
  )
}
