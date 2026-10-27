import clsx from 'clsx'
import { Blocks, ImageIcon, Sparkles } from 'lucide-react'
import { useEffect, useMemo, useRef, useState } from 'react'

import { Button, Field, Input, Modal, Select, Textarea } from '@/components/ui'
import { AVATAR_MAX_SIZE, readImageAsDataUrl } from '@/lib/image'
import { resolveAvatar } from '@/services/avatarPack'
import { useAppStore } from '@/stores/appStore'
import { useAssistantStore } from '@/stores/assistantStore'
import { useAvatarPreviewStore } from '@/stores/avatarPreviewStore'
import type { AssistantProfile, PersonaFile } from '@/types'







const PERSONA_FILE_NAMES = [
  'IDENTITY.md',
  'SOUL.md',
  'RULES.md',
  'MEMORY.md',
  'USER.md',
  '进化日志.md',
  '待确认.md',
] as const

const PERSONA_LABELS: Record<string, string> = {
  'IDENTITY.md': '搭子身份（IDENTITY）',
  'SOUL.md': '人格（SOUL）',
  'RULES.md': '工作逻辑与规则（RULES）',
  'MEMORY.md': '记忆（MEMORY）',
  'USER.md': '用户档案（USER）',
  '进化日志.md': '进化日志（全员进化）',
  '待确认.md': '待确认清单',
}


const PERSONA_DESCRIPTIONS: Record<string, string> = {
  'IDENTITY.md': '它是谁：名字、角色定位、自我介绍。',
  'SOUL.md': '它的性格：怎么说话、在意什么、待人接物的风格。',
  'RULES.md': '它的工作方式与规矩：先做什么后做什么、什么必须先确认。',
  'MEMORY.md': '它记得的事：你的偏好、约定。AI 也可以自己补充（会先确认）。',
  'USER.md': '关于你的档案：怎么称呼你、你的偏好。AI 也可以自己补充（会先确认）。',
  '进化日志.md':
    '它每周「全员进化」那一轮的记录：改了什么、为什么、下轮要验证什么。由搭子自己写，你可以看也可以改。',
  '待确认.md':
    '搭子看不到你的屏幕，所以把「需要你亲眼核对的事」写成条目放在这里；你可以逐条标注通过 / 不通过。',
}

const PERSONA_PLACEHOLDERS: Record<string, string> = {
  'IDENTITY.md': '我是……',
  'SOUL.md': '它怎么看自己、怎么说话、在意什么。',
  'RULES.md': '它的工作方式与规矩。AI 也可以按你的要求修改（每次修改都会先让你确认）。',
  'MEMORY.md': '它记得的关于你的事：偏好、习惯、约定。它也可以自己往这里补充。',
  'USER.md': '关于你本人的档案：怎么称呼、职业、长期偏好（对齐 openclaw 的 user.md）。',
  '进化日志.md':
    '这一轮改了什么、为什么、下轮要验证什么。由搭子自己每周写，你不需要在这里手动记。',
  '待确认.md':
    '由搭子写「核对项 / 期望 / 判据」，你逐条标注通过或不通过。格式：## 1 / - 核对项： / - 期望： / - 判据： / - 结论：待定',
}


interface ConfirmationRow {
  index: string
  check: string
  expect: string
  passIf: string
  verdict: string
}








function parseConfirmations(text: string): ConfirmationRow[] {
  const rows: ConfirmationRow[] = []
  for (const block of text.split(/^## /m).slice(1)) {
    const [head, ...rest] = block.split('\n')
    const body = rest.join('\n')
    const pick = (label: string): string => {
      const matched = body.match(new RegExp(`- ${label}：(.*)`))
      return matched ? matched[1].trim() : ''
    }
    rows.push({
      index: head.trim(),
      check: pick('核对项'),
      expect: pick('期望'),
      passIf: pick('判据'),
      verdict: pick('结论') || '待定',
    })
  }
  return rows
}


function setConfirmationVerdict(text: string, index: string, verdict: string): string {
  const safe = index.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
  return text.replace(
    new RegExp(`(## ${safe}\\n(?:.*\\n)*?- 结论：)(.*)`),
    (_match, prefix: string) => `${prefix}${verdict}`,
  )
}


const avatarHistoryKey = (id: string) => `agent-desktop:assistant-avatars:${id}`

function loadAvatarHistory(id: string): string[] {
  try {
    const raw = localStorage.getItem(avatarHistoryKey(id))
    return raw ? (JSON.parse(raw) as string[]) : []
  } catch {
    return []
  }
}

function saveAvatarHistory(id: string, list: string[]): void {
  try {
    localStorage.setItem(avatarHistoryKey(id), JSON.stringify(list.slice(0, 8)))
  } catch {
    
  }
}


export function blankProfile(): AssistantProfile {
  return {
    id: '',
    name: '',
    nickname: '',
    emoji: '🤖',
    avatar: '',
    description: '',
    system_prompt: '',
    
    
    
    voice: {
      wake_words: [],
      send_word: '发送',
      cancel_word: '清空',
      
      
      command_words: {},
      disabled_commands: [],
      
      
      startup_mode: 'off',
      enable_word: '打开语音',
      disable_word: '关闭语音',
    },
    model_id: '',
    temperature: 0.7,
    max_iterations: null,
    max_tool_calls_per_turn: null,
    
    reasoning_effort: null,
    chat_background: '',
    enabled_skills: [],
    confirm_mode: null,
    
    persona_locked: false,
    builtin: false,
    sort_order: 100,
    restricts_skills: false,
    unavailable_skills: [],
  }
}


export function toId(name: string): string {
  const ascii = name
    .toLowerCase()
    .replace(/[^a-z0-9_-]+/g, '-')
    .replace(/^-+|-+$/g, '')
  return ascii || `assistant-${Date.now().toString(36)}`
}


























export function AssistantAvatar({
  profile,
  size = 20,
  className = '',
}: {
  profile: Pick<AssistantProfile, 'avatar' | 'emoji' | 'name'> & { id?: string }
  size?: number
  className?: string
}) {
  const openPreview = useAvatarPreviewStore((state) => state.open)
  const src = resolveAvatar(profile)
  
  const radius = Math.round(size * (6 / 22))

  if (!src) {
    return (
      <span
        className={`flex shrink-0 select-none items-center justify-center overflow-hidden bg-brand-soft text-brand ${className}`}
        style={{ width: size, height: size, borderRadius: radius }}
      >
        <ImageIcon size={Math.max(10, Math.round(size * 0.55))} />
      </span>
    )
  }

  return (
    


















    <span
      role="button"
      tabIndex={0}
      title="查看大图"
      aria-label={`查看 ${profile.name} 的头像大图`}
      onClick={(event) => {
        event.stopPropagation()
        event.preventDefault()
        
        openPreview(src, profile.name, profile.id ?? '')
      }}
      onKeyDown={(event) => {
        if (event.key !== 'Enter' && event.key !== ' ') return
        event.preventDefault()
        event.stopPropagation()
        openPreview(src, profile.name, profile.id ?? '')
      }}
      className={`group relative inline-block shrink-0 cursor-zoom-in overflow-hidden focus-visible:ring-2 focus-visible:ring-brand/60 focus-visible:outline-none ${className}`}
      style={{ width: size, height: size, borderRadius: radius }}
    >
      <img
        src={src}
        alt={profile.name}
        width={size}
        height={size}
        draggable={false}
        className="h-full w-full object-cover select-none"
      />
    </span>
  )
}








const BUCKET_LABELS: Record<string, string> = {
  mine: '我的技能',
  common: '通用技能',
}


function AbilityPicker({
  view,
  onView,
  selected,
  onChange,
  onClose,
}: {
  view: 'type' | 'skill' | 'mcp'
  onView: (view: 'type' | 'skill' | 'mcp') => void
  selected: string[]
  onChange: (next: string[]) => void
  onClose: () => void
}) {
  const skills = useAppStore((state) => state.skills)
  const [keyword, setKeyword] = useState('')

  const toggle = (name: string) =>
    onChange(
      selected.includes(name) ? selected.filter((item) => item !== name) : [...selected, name],
    )

  
  
  
  
  
  
  const groups = useMemo(() => {
    const map = new Map<string, typeof skills>()
    for (const skill of skills) {
      if (view === 'mcp' && skill.source !== 'mcp') continue
      if (view === 'skill' && skill.source === 'mcp') continue
      const bucket = skill.bucket ?? (skill.source === 'custom' ? 'mine' : 'common')
      if (view === 'skill' && bucket !== 'common' && bucket !== 'mine') continue
      if (keyword && !`${skill.name} ${skill.display_name} ${skill.description}`.includes(keyword)) {
        continue
      }
      const key =
        view === 'mcp'
          ? (skill.name.split('__')[0] ?? 'mcp')
          : (skill.bucket ?? (skill.source === 'custom' ? 'mine' : 'common'))
      const list = map.get(key) ?? []
      list.push(skill)
      map.set(key, list)
    }
    return [...map.entries()].sort(([a], [b]) => a.localeCompare(b))
  }, [skills, keyword, view])

  if (view === 'type') {
    return (
      <div className="space-y-2">
        <button
          type="button"
          className="no-drag w-full rounded-[10px] border border-line bg-canvas px-4 py-3 text-left transition-colors hover:border-brand/40 hover:bg-brand-soft/30"
          onClick={() => onView('skill')}
        >
          <div className="text-[13px] font-medium text-ink">Skill（技能）</div>
          <p className="mt-0.5 text-[11.5px] text-ink-faint">
            内置技能与你上传的技能包，按分类挑选。
          </p>
        </button>
        <button
          type="button"
          className="no-drag w-full rounded-[10px] border border-line bg-canvas px-4 py-3 text-left transition-colors hover:border-brand/40 hover:bg-brand-soft/30"
          onClick={() => onView('mcp')}
        >
          <div className="text-[13px] font-medium text-ink">MCP（连接器）</div>
          <p className="mt-0.5 text-[11.5px] text-ink-faint">
            已连接的 MCP 服务提供的工具，按服务分组挑选。
          </p>
        </button>
        <div className="rounded-[10px] border border-dashed border-line px-4 py-3">
          <div className="text-[12px] text-ink-soft">没找到想要的？去技能市场逛逛</div>
          <div className="mt-1.5 flex flex-wrap gap-2">
            <Button
              size="sm"
              onClick={() => void window.agentBridge?.openExternal('https://clawhub.com')}
            >
              ClawHub
            </Button>
            {}
            <Button
              size="sm"
              onClick={() =>
                void window.agentBridge?.openExternal('https://skillhub.cn/skills?sortBy=score')
              }
            >
              SkillHub
            </Button>
            <Button
              size="sm"
              onClick={() => void window.agentBridge?.openExternal('https://modelscope.cn')}
            >
              魔搭社区
            </Button>
            <span className="self-center text-[11px] text-ink-faint">
              找到技能包后，到「技能」页上传即可
            </span>
          </div>
        </div>
      </div>
    )
  }

  return (
    <div className="flex flex-col gap-2">
      <div className="flex items-center gap-2">
        <Button size="sm" onClick={() => onView('type')}>
          返回
        </Button>
        <span className="text-[12.5px] text-ink-soft">
          已选 {selected.length === 0 ? '仅内置技能' : `${selected.length} 项`}
        </span>
        {selected.length > 0 ? (
          <Button size="sm" variant="secondary" onClick={() => onChange([])}>
            清空
          </Button>
        ) : null}
        <div className="flex-1" />
        <Input
          value={keyword}
          onChange={(event) => setKeyword(event.target.value)}
          placeholder="搜索"
          className="h-7 w-[140px] text-[12px]"
        />
      </div>

      <div className="max-h-[300px] overflow-y-auto rounded-[10px] border border-line">
        {selected.length === 0 ? (
          <div className="border-b border-line-soft bg-brand-soft/40 px-3 py-2 text-[11.5px] leading-relaxed text-ink-soft">
            没有勾选任何项 = 这个助手只使用**内置技能**；勾上「通用技能 / 我的技能」里的项才会加上去。
          </div>
        ) : null}

        {groups.map(([group, list]) => (
          <div key={group}>
            <div className="bg-panel px-3 py-1 text-[11px] font-medium text-ink-faint">
              {view === 'mcp' ? group : (BUCKET_LABELS[group] ?? group)}
            </div>
            {list.map((skill) => {
              const checked = selected.includes(skill.name)
              return (
                <label
                  key={skill.name}
                  className="flex cursor-pointer items-start gap-2.5 px-3 py-1.5 hover:bg-hover"
                >
                  <input
                    type="checkbox"
                    checked={checked}
                    onChange={() => toggle(skill.name)}
                    className="mt-[3px] h-3.5 w-3.5 accent-[var(--app-brand)]"
                  />
                  <span className="min-w-0 flex-1">
                    <span className="text-[12.5px] text-ink">{skill.display_name}</span>
                    <span className="mt-0.5 block truncate text-[11px] text-ink-faint">
                      {skill.description}
                    </span>
                  </span>
                </label>
              )
            })}
          </div>
        ))}

        {groups.length === 0 ? (
          <p className="px-3 py-3 text-[11.5px] text-ink-faint">
            {view === 'mcp'
              ? '还没有已连接的 MCP 服务。到「MCP 服务」页添加一个。'
              : '没有匹配的技能。'}
          </p>
        ) : null}
      </div>

      <div className="flex justify-end">
        <Button variant="primary" onClick={onClose}>
          完成
        </Button>
      </div>
    </div>
  )
}








export function AssistantFormModal({
  open,
  initial,
  isNew,
  onClose,
  onSaved,
}: {
  open: boolean
  
  initial: AssistantProfile | null
  isNew: boolean
  onClose: () => void
  
  onSaved?: () => void
}) {
  const models = useAppStore((state) => state.models)
  const paths = useAppStore((state) => state.paths)
  const reloadSkills = useAppStore((state) => state.reloadSkills)
  
  const skills = useAppStore((state) => state.skills)
  const activeId = useAssistantStore((state) => state.activeId)
  const setActive = useAssistantStore((state) => state.setActive)
  const save = useAssistantStore((state) => state.save)

  const api = useAppStore((state) => state.api)

  const [form, setForm] = useState<AssistantProfile | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  
  const [editingPersona, setEditingPersona] = useState<string | null>(null)
  
  const [avatarHistory, setAvatarHistory] = useState<string[]>([])
  







  const [wakeWordsText, setWakeWordsText] = useState('')
  
  const [abilityOpen, setAbilityOpen] = useState(false)
  const [abilityView, setAbilityView] = useState<'type' | 'skill' | 'mcp'>('type')

  
  const [personaFiles, setPersonaFiles] = useState<PersonaFile[]>([])
  const [personaLoading, setPersonaLoading] = useState(false)
  const [personaError, setPersonaError] = useState('')
  
  const [unlocked, setUnlocked] = useState(false)
  const [passwordInput, setPasswordInput] = useState('')
  const [newPassword, setNewPassword] = useState('')
  
  const [resetConfirm, setResetConfirm] = useState('')
  const avatarInputRef = useRef<HTMLInputElement>(null)
  const backgroundInputRef = useRef<HTMLInputElement>(null)

  
  
  useEffect(() => {
    if (!open) return
    
    setForm(
      initial
        ? {
            ...initial,
            nickname: initial.nickname ?? '',
            max_tool_calls_per_turn: initial.max_tool_calls_per_turn ?? null,
            chat_background: initial.chat_background ?? '',
          }
        : blankProfile(),
    )
    setError(null)
    setBusy(false)
    setAvatarHistory(initial?.id ? loadAvatarHistory(initial.id) : [])
    
    setWakeWordsText((initial?.voice?.wake_words ?? []).join('，'))
  }, [open, initial])

  
  
  useEffect(() => {
    if (!open || !api) return
    const id = initial?.id
    setUnlocked(false)
    setPasswordInput('')
    setPersonaError('')

    if (!id) {
      
      setPersonaFiles(
        PERSONA_FILE_NAMES.map((name) => ({
          name,
          exists: false,
          size: 0,
          content: '',
          hint: '',
        })),
      )
      return
    }

    let cancelled = false
    setPersonaLoading(true)
    api
      .getPersonaFiles(id)
      .then((result) => {
        if (!cancelled) setPersonaFiles(result.files ?? [])
      })
      .catch((exc: unknown) => {
        if (!cancelled) {
          setPersonaError(exc instanceof Error ? exc.message : String(exc))
          setPersonaFiles([])
        }
      })
      .finally(() => {
        if (!cancelled) setPersonaLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [open, initial?.id, api])

  
  const personaLocked = Boolean(form?.persona_locked) && !unlocked

  








  const lockedBuiltin = Boolean(form?.locked)
  const lockedFields = new Set(form?.locked_fields ?? [])
  
  
  const lockedPersonaFiles = new Set<string>()

  








  const abilitySummary = useMemo(() => {
    if (!form) return null
    
    
    
    if (skills.length === 0) return null
    const builtin = skills.filter((item) => item.bucket === 'builtin').length
    
    const own = skills.filter(
      (item) => item.bucket === 'exclusive' && (item.owners ?? []).includes(form.id),
    ).length
    
    
    
    const extra = (form.enabled_skills ?? []).length
    const total = builtin + own + extra
    
    
    
    
    
    
    
    const enabledTotal = skills.filter((item) => item.enabled).length
    return {
      total,
      spare: Math.max(0, enabledTotal - total),
      unusable: form.unavailable_skills?.length ?? 0,
    }
  }, [skills, form])

  





  const personaFilePath = (name: string): string => {
    if (!form?.id) return '（保存助手后才会创建这个文件）'
    const dataDir = paths?.data ?? '<数据目录>'
    return `${dataDir}\\assistants\\${form.id}\\${name}`
  }

  const unlock = async () => {
    if (!form?.id || !api) return
    setPersonaError('')
    try {
      const result = await api.personaLock(form.id, {
        action: 'verify',
        password: passwordInput,
      })
      if (result.ok) {
        setUnlocked(true)
      } else {
        setPersonaError('密码不对。忘了的话可以在下面「重置」。')
      }
    } catch (exc) {
      setPersonaError(exc instanceof Error ? exc.message : String(exc))
    }
  }

  const resetLock = async () => {
    if (!form?.id || !api) return
    setPersonaError('')
    try {
      await api.personaLock(form.id, {
        action: 'clear',
        confirm: '解除人格锁',
      })
      setUnlocked(true)
      setForm((prev) => (prev ? { ...prev, persona_locked: false } : prev))
    } catch (exc) {
      setPersonaError(exc instanceof Error ? exc.message : String(exc))
    }
  }

  const pickAvatar = async (file: File) => {
    const dataUrl = await readImageAsDataUrl(file, AVATAR_MAX_SIZE)
    setForm((prev) => {
      if (prev?.id) {
        
        
        const list = [dataUrl, ...loadAvatarHistory(prev.id).filter((item) => item !== dataUrl)]
        saveAvatarHistory(prev.id, list)
        setAvatarHistory(list.slice(0, 8))
      }
      return prev ? { ...prev, avatar: dataUrl } : prev
    })
  }

  const pickBackground = async (file: File) => {
    
    
    const dataUrl = await readImageAsDataUrl(file, 1600)
    setForm((prev) => (prev ? { ...prev, chat_background: dataUrl } : prev))
  }

  const submit = async () => {
    if (!form) return
    const payload: AssistantProfile = {
      ...form,
      id: isNew ? toId(form.name || form.id) : form.id,
      name: form.name.trim(),
      
      
      
      voice: {
        ...form.voice,
        wake_words: wakeWordsText
          .split(/[，,、\s]+/)
          .map((word) => word.trim())
          .filter(Boolean),
      },
    }
    if (!payload.name) {
      setError('搭子名称不能为空。')
      return
    }
    setBusy(true)
    setError(null)
    try {
      await save(payload)

      
      
      if (api) {
        for (const file of personaFiles) {
          
          
          
          
          
          
          
          
          
          
          
          
          if (lockedPersonaFiles.has(file.name)) continue
          if (file.content.trim()) {
            await api.writePersonaFile(payload.id, file.name, file.content)
          }
        }
        
        if (isNew && newPassword.trim()) {
          await api.personaLock(payload.id, { action: 'set', password: newPassword.trim() })
        }
      }

      
      await reloadSkills()
      onSaved?.()
      onClose()
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : String(exc))
    } finally {
      setBusy(false)
    }
  }

  return (
    <>
    <Modal
      open={open}
      onClose={onClose}
      width="max-w-3xl"
      title={isNew ? 'New Buddy' : `编辑：${form?.name ?? ''}`}
      description="留空的模型、温度等参数会沿用「安全与通用」页签里的全局设置。"
      footer={
        <>
          <Button onClick={onClose}>取消</Button>
          <Button variant="primary" disabled={busy} onClick={() => void submit()}>
            {busy ? '保存中…' : '保存'}
          </Button>
        </>
      }
    >
      {form ? (
        <div className="flex flex-col gap-3">
          {error ? (
            <div className="rounded-[8px] border border-danger/30 bg-danger-soft px-3 py-2 text-[12px] text-danger">
              {error}
            </div>
          ) : null}

          {lockedBuiltin ? (
            <div className="rounded-[8px] border border-line bg-panel px-3 py-2 text-[12px] leading-relaxed text-ink-soft">
              {form?.locked_reason ||
                '这是内置搭子：名称、简介与人格规则（RULES.md）由产品固定，不能修改或删除；可用能力可以像普通搭子一样勾选技能，昵称、头像与人格（SOUL / IDENTITY）仍可自由设置。'}
            </div>
          ) : null}

          <div className="grid grid-cols-3 gap-3">
            <Field label="名称" hint={lockedFields.has('name') ? '内置搭子的名称固定，不可修改' : undefined}>
              <Input
                value={form.name}
                disabled={lockedFields.has('name')}
                onChange={(event) => setForm({ ...form, name: event.target.value })}
                placeholder="例如 周报搭子"
              />
            </Field>

            <Field label="昵称" hint="对话里显示的称呼；留空则用名称">
              <Input
                value={form.nickname}
                onChange={(event) => setForm({ ...form, nickname: event.target.value })}
                placeholder="例如 小伴"
              />
            </Field>

            {

}
            <Field label="语音唤醒词" hint="说了它就切到这个搭子；多个用逗号隔开，留空则按名字自动生成">
              <Input
                value={wakeWordsText}
                onChange={(event) => setWakeWordsText(event.target.value)}
                onBlur={() =>
                  
                  setWakeWordsText(
                    wakeWordsText
                      .split(/[，,、\s]+/)
                      .map((word) => word.trim())
                      .filter(Boolean)
                      .join('，'),
                  )
                }
                placeholder="例如 你好小伴"
              />
            </Field>

            <Field label="头像">
              {



}
              <div className="flex flex-wrap items-center gap-2">
                <Button variant="secondary" onClick={() => avatarInputRef.current?.click()}>
                  {form.avatar ? '换张头像' : '上传图片'}
                </Button>
                {form.avatar ? (
                  <Button variant="secondary" onClick={() => setForm({ ...form, avatar: '' })}>
                    移除头像
                  </Button>
                ) : null}
                {}
                {form.avatar ? (
                  <AssistantAvatar profile={form} size={32} />
                ) : null}
                <span className="text-[11px] text-ink-faint">
                  会自动压缩到 {AVATAR_MAX_SIZE}px 后存在本机
                </span>
                <input
                  ref={avatarInputRef}
                  type="file"
                  accept="image/*"
                  className="hidden"
                  onChange={(event) => {
                    const file = event.target.files?.[0]
                    if (file) void pickAvatar(file)
                    
                    event.target.value = ''
                  }}
                />
              </div>

              {}
              {avatarHistory.length > 0 ? (
                <div className="mt-2">
                  <div className="text-[11px] text-ink-faint">我的头像</div>
                  <div className="mt-1 flex flex-wrap gap-1.5">
                    {avatarHistory.map((src) => (
                      <button
                        key={src.slice(-24) + String(src.length)}
                        type="button"
                        onClick={() => setForm({ ...form, avatar: src })}
                        className={clsx(
                          'no-drag overflow-hidden rounded-[8px] ring-1 transition-opacity',
                          form.avatar === src ? 'ring-brand' : 'ring-transparent opacity-70 hover:opacity-100',
                        )}
                        title="点击使用这张头像"
                      >
                        <img
                          src={src}
                          alt="历史头像"
                          width={36}
                          height={36}
                          draggable={false}
                          className="h-9 w-9 object-cover"
                        />
                      </button>
                    ))}
                  </div>
                </div>
              ) : null}
            </Field>

            <Field
              label="说明"
              className="col-span-2"
              hint="展示在搭子列表与会话栏上。支持 Markdown（**加粗**、- 列表、[链接](https://…)），敲回车换行也会保留。"
            >
              <Textarea
                value={form.description}
                rows={3}
                disabled={lockedFields.has('description')}
                onChange={(event) => setForm({ ...form, description: event.target.value })}
                placeholder={'一句话说明这个搭子适合做什么；\n换行与 Markdown 都会保留'}
              />
            </Field>

            {}
            <Field label="聊天背景（可选）" className="col-span-2">
              <div className="flex flex-wrap items-center gap-2">
                <Button
                  variant="secondary"
                  onClick={() => backgroundInputRef.current?.click()}
                >
                  {form.chat_background ? '换一张' : '上传图片'}
                </Button>
                {form.chat_background ? (
                  <>
                    <img
                      src={form.chat_background}
                      alt="聊天背景预览"
                      className="h-12 w-20 rounded-[6px] border border-line object-cover"
                    />
                    <Button
                      variant="secondary"
                      onClick={() => setForm({ ...form, chat_background: '' })}
                    >
                      移除
                    </Button>
                  </>
                ) : null}
                <span className="text-[11px] text-ink-faint">
                  只在这个助手的对话区显示；不会裁剪，按窗口长宽缩放。
                </span>
                <input
                  ref={backgroundInputRef}
                  type="file"
                  accept="image/*"
                  className="hidden"
                  onChange={async (event) => {
                    const file = event.target.files?.[0]
                    if (file) await pickBackground(file)
                    event.target.value = ''
                  }}
                />
              </div>
            </Field>
          </div>

          {}
          {
}
          <div className="mt-3">
            <div className="text-[12.5px] text-ink-soft">人格与记忆</div>
            <p className="mt-0.5 text-[11px] leading-relaxed text-ink-faint">
              这几个文件是这个搭子的“自我”与“规矩”，会一起进入每次对话。你随时可以改，
              搭子也可以按你的要求往里补充（每次补充都会先让你确认，且立即生效）。
            </p>

            {personaLocked ? (
              

              <div className="mt-2 rounded-[8px] border border-line bg-panel px-3 py-3">
                <div className="text-[12.5px] text-ink-soft">人格已上锁 —— 要改 SOUL / RULES，先输密码</div>
                <div className="mt-2 flex items-center gap-2">
                  <Input
                    type="password"
                    value={passwordInput}
                    onChange={(event) => setPasswordInput(event.target.value)}
                    placeholder="人格密码"
                  />
                  <Button variant="secondary" onClick={() => void unlock()}>
                    解锁
                  </Button>
                </div>
                {personaError ? (
                  <p className="mt-2 text-[11.5px] text-danger">{personaError}</p>
                ) : null}

                <div className="mt-3 border-t border-line pt-2">
                  <div className="text-[11.5px] text-ink-faint">
                    忘了密码也能救回来：在下面输入「解除人格锁」即可清除。
                  </div>
                  <div className="mt-1.5 flex items-center gap-2">
                    <Input
                      value={resetConfirm}
                      onChange={(event) => setResetConfirm(event.target.value)}
                      placeholder="解除人格锁"
                    />
                    <Button
                      variant="secondary"
                      disabled={resetConfirm.trim() !== '解除人格锁'}
                      onClick={() => void resetLock()}
                    >
                      重置密码
                    </Button>
                  </div>
                </div>
              </div>
            ) : null}

            {personaLoading ? (
              <p className="mt-2 text-[11.5px] text-ink-faint">读取中…</p>
            ) : null}

            {

}
            <div className="mt-2 overflow-hidden rounded-[8px] border border-line">
              {personaFiles.map((file, index) => (
                <div
                  key={file.name}
                  className={clsx(
                    'flex items-center gap-3 px-3 py-2',
                    index > 0 ? 'border-t border-line-soft' : '',
                  )}
                >
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2">
                      <span className="text-[12.5px] whitespace-nowrap text-ink">
                        {PERSONA_LABELS[file.name] ?? file.name}
                      </span>
                      <span className="text-[11px] whitespace-nowrap text-ink-faint">
                        {file.exists ? `${Math.max(1, Math.round(file.size / 1024))} KB` : '还没写过'}
                      </span>
                    </div>
                    {}
                    <div className="mt-0.5 text-[11px] leading-relaxed text-ink-faint">
                      {PERSONA_DESCRIPTIONS[file.name] ?? ''}
                    </div>
                    <div className="mt-0.5 w-full truncate text-[11px] text-ink-faint" title={personaFilePath(file.name)}>
                      {personaFilePath(file.name)}
                    </div>
                  </div>
                  <Button
                    size="sm"
                    variant="secondary"
                    className="shrink-0"
                    disabled={lockedPersonaFiles.has(file.name)}
                    onClick={() => setEditingPersona(file.name)}
                  >
                    {lockedPersonaFiles.has(file.name)
                      ? '固定'
                      : file.content.trim()
                        ? '查看 / 编辑'
                        : '写一点'}
                  </Button>
                </div>
              ))}
            </div>
          </div>

          {isNew ? (
            <Field
              label="人格密码（可选）"
              hint="设了之后，以后改这个助手的提示词与人格要先输密码；忘了可以在编辑页里重置"
              className="mt-3"
            >
              <Input
                type="password"
                value={newPassword}
                onChange={(event) => setNewPassword(event.target.value)}
                placeholder="留空表示不设密码"
              />
            </Field>
          ) : null}

          <div className="grid grid-cols-2 gap-3">
            <Field label="默认模型">
              <Select
                value={form.model_id}
                onChange={(event) => setForm({ ...form, model_id: event.target.value })}
              >
                <option value="">跟随全局默认</option>
                {models
                  .filter((model) => model.enabled)
                  .map((model) => (
                    <option key={model.id} value={model.id}>
                      {model.model_name || model.display_name}
                    </option>
                  ))}
              </Select>
            </Field>

            <Field label="温度" hint="数值越低回答越稳定">
              <Input
                type="number"
                step="0.1"
                min={0}
                max={2}
                value={form.temperature ?? ''}
                placeholder="跟随全局"
                onChange={(event) =>
                  setForm({
                    ...form,
                    temperature: event.target.value === '' ? null : Number(event.target.value),
                  })
                }
              />
            </Field>

            <Field label="最大轮数" hint="不设上限；留空表示跟随全局">
              <Input
                type="number"
                min={1}
                value={form.max_iterations ?? ''}
                placeholder="跟随全局"
                onChange={(event) =>
                  setForm({
                    ...form,
                    max_iterations: event.target.value === '' ? null : Number(event.target.value),
                  })
                }
              />
            </Field>

            <Field
              label="思考强度"
              hint={
                '群里这个搭子按这里的值走（除非在群页面单独设过，群设置优先）；' +
                '单人对话则由输入栏旁边的「思考强度」按对话设置。' +
                '留空 = 不发送这个参数，由服务商用自己的默认行为。'
              }
            >
              <Select
                value={form.reasoning_effort ?? ''}
                onChange={(event) =>
                  setForm({ ...form, reasoning_effort: event.target.value || null })
                }
              >
                <option value="">不发送（服务商默认）</option>
                <option value="low">低</option>
                <option value="medium">中</option>
                <option value="high">高</option>
              </Select>
            </Field>

            <Field label="单轮工具调用上限" hint="留空表示跟随全局">
              <Input
                type="number"
                min={1}
                value={form.max_tool_calls_per_turn ?? ''}
                placeholder="跟随全局"
                onChange={(event) =>
                  setForm({
                    ...form,
                    max_tool_calls_per_turn:
                      event.target.value === '' ? null : Number(event.target.value),
                  })
                }
              />
            </Field>
          </div>

          <Field label="权限策略" hint="覆盖全局的确认模式；留空表示沿用全局设置">
            <Select
              value={form.confirm_mode ?? ''}
              onChange={(event) =>
                setForm({
                  ...form,
                  confirm_mode: (event.target.value || null) as AssistantProfile['confirm_mode'],
                })
              }
            >
              <option value="">跟随全局设置</option>
              <option value="interactive">每次询问</option>
              <option value="deny">一律拒绝高危操作</option>
              <option value="auto_approve">自动批准</option>
            </Select>
          </Field>

          <Field
            label="可用能力"
            hint={
              lockedFields.has('enabled_skills')
                ? '内置搭子的可用能力固定，不可增删'
                : '不选 = 只用内置技能；勾上通用 / 我的技能才会加上去'
            }
          >
            <div className="flex flex-wrap items-center gap-2">
              <span className="text-[12px] text-ink-soft">
                {

}
                {abilitySummary ? `具备 ${abilitySummary.total} 个技能` : ''}
                {
}
                {abilitySummary ? `，${abilitySummary.spare} 个技能未配备` : ''}
                {
}
                {abilitySummary && abilitySummary.unusable > 0 ? (
                  <span className="text-warning">
                    {`；其中 ${abilitySummary.unusable} 个当前不可用`}
                  </span>
                ) : null}
                {(form.enabled_skills ?? []).length > 0
                  ? `（额外勾选 ${(form.enabled_skills ?? []).length} 项）`
                  : null}
                {(form.enabled_skills ?? []).length === 0
                  ? '（未额外勾选，只带内置技能）'
                  : null}
              </span>
              <Button
                variant="secondary"
                icon={<Blocks size={13} />}
                disabled={lockedFields.has('enabled_skills')}
                onClick={() => {
                  setAbilityView('type')
                  setAbilityOpen(true)
                }}
              >
                添加能力
              </Button>
              {form.enabled_skills.length > 0 ? (
                <Button
                  variant="secondary"
                  disabled={lockedFields.has('enabled_skills')}
                  onClick={() => setForm({ ...form, enabled_skills: [] })}
                >
                  清空选择
                </Button>
              ) : null}
            </div>
          </Field>

          {isNew ? null : (
            <div className="flex items-center gap-2 border-t border-line-soft pt-3 text-[12px] text-ink-soft">
              <Sparkles size={13} className="shrink-0 text-ink-faint" />
              <span className="min-w-0 flex-1 truncate">
                搭子 id：<code className="rounded bg-panel px-1">{form.id}</code>
                <span
                  className="ml-1 text-[11px] text-ink-faint"
                  title="会话归属与人格文件的存放目录都按这个 id；自动生成，一般不用管"
                >
                  （内部标识，自动生成，一般不用管）
                </span>
              </span>
              {

}
              {form.id === activeId ? (
                <span className="shrink-0 text-[11.5px] text-brand">当前使用中</span>
              ) : (
                <Button
                  size="sm"
                  variant="secondary"
                  className="shrink-0"
                  onClick={() => setActive(form.id)}
                >
                  设为当前搭子
                </Button>
              )}
            </div>
          )}
        </div>
      ) : null}
    </Modal>

    {}
    <Modal
      open={abilityOpen}
      onClose={() => setAbilityOpen(false)}
      width="max-w-lg"
      title={abilityView === 'type' ? '添加能力' : abilityView === 'mcp' ? '选择 MCP 工具' : '选择技能'}
      description={
        abilityView === 'type'
          ? '选一类能力进入详细选择；也可以去技能市场找找。'
          : undefined
      }
      footer={abilityView === 'type' ? <Button onClick={() => setAbilityOpen(false)}>取消</Button> : undefined}
    >
      <AbilityPicker
        view={abilityView}
        onView={setAbilityView}
        selected={form?.enabled_skills ?? []}
        onChange={(next) => setForm((prev) => (prev ? { ...prev, enabled_skills: next } : prev))}
        onClose={() => setAbilityOpen(false)}
      />
    </Modal>

    {

}
    <Modal
      open={editingPersona !== null}
      onClose={() => setEditingPersona(null)}
      width="max-w-3xl"
      title={`编辑 ${PERSONA_LABELS[editingPersona ?? ''] ?? editingPersona ?? ''}`}
      description={personaFilePath(editingPersona ?? '')}
      footer={
        <>
          <Button onClick={() => setEditingPersona(null)}>完成</Button>
        </>
      }
    >
      {editingPersona ? (
        <div className="flex flex-col gap-2">
          <p className="text-[11.5px] leading-relaxed text-ink-faint">
            {PERSONA_PLACEHOLDERS[editingPersona] ?? ''}
            {editingPersona === 'MEMORY.md' ? '（内容会作为独立的记忆提示进入对话）' : ''}
            {editingPersona === '进化日志.md' ? '（每周「全员进化」那轮会先读它，再按周追加）' : ''}
          </p>
          {}
          {editingPersona === '待确认.md'
            ? (() => {
                const current =
                  personaFiles.find((file) => file.name === editingPersona)?.content ?? ''
                const rows = parseConfirmations(current)
                if (rows.length === 0) {
                  return (
                    <p className="text-[11px] text-ink-faint">
                      还没有待确认项。搭子判断不了画面时，会往这里写。
                    </p>
                  )
                }
                return (
                  <div className="flex flex-col gap-1.5">
                    {rows.map((row) => (
                      <div
                        key={row.index}
                        className="rounded-[6px] border border-line-soft px-2.5 py-2"
                      >
                        <div className="text-[12px] font-medium text-ink">
                          {row.index}. {row.check}
                        </div>
                        {row.expect ? (
                          <div className="mt-0.5 text-[11px] text-ink-faint">
                            期望：{row.expect}
                          </div>
                        ) : null}
                        {row.passIf ? (
                          <div className="text-[11px] text-ink-faint">判据：{row.passIf}</div>
                        ) : null}
                        <div className="mt-1 flex gap-1.5">
                          {(['通过', '不通过', '待定'] as const).map((verdict) => (
                            <button
                              key={verdict}
                              type="button"
                              onClick={() =>
                                setPersonaFiles((prev) =>
                                  prev.map((item) =>
                                    item.name === editingPersona
                                      ? {
                                          ...item,
                                          content: setConfirmationVerdict(
                                            current,
                                            row.index,
                                            verdict,
                                          ),
                                        }
                                      : item,
                                  ),
                                )
                              }
                              className={clsx(
                                'rounded-[6px] px-2 py-0.5 text-[11px]',
                                row.verdict === verdict
                                  ? 'bg-brand/15 text-brand'
                                  : 'text-ink-faint hover:bg-hover',
                              )}
                            >
                              {verdict}
                            </button>
                          ))}
                        </div>
                      </div>
                    ))}
                  </div>
                )
              })()
            : null}
          <textarea
            value={
              personaFiles.find((file) => file.name === editingPersona)?.content ?? ''
            }
            
            disabled={
              personaLocked && (editingPersona === 'SOUL.md' || editingPersona === 'RULES.md')
            }
            onChange={(event) =>
              setPersonaFiles((prev) =>
                prev.map((item) =>
                  item.name === editingPersona
                    ? { ...item, content: event.target.value }
                    : item,
                ),
              )
            }
            rows={18}
            className="w-full resize-y rounded-[8px] border border-line bg-canvas px-2.5 py-2 text-[12.5px] leading-relaxed text-ink placeholder:text-ink-faint focus:border-brand focus:outline-none disabled:opacity-60"
          />
          <p className="text-[11px] text-ink-faint">
            点「完成」只是收起编辑窗；要点外层的「保存」才会写入文件。
          </p>
        </div>
      ) : null}
    </Modal>
    </>
  )
}
