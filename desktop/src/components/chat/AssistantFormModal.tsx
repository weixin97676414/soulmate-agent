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

/**
 * 人格文件的名字。
 *
 * ⚠️ 必须与后端 ``assistants/persona.py`` 的 ``ALLOWED_FILES`` 一致。
 * 飘了的后果不是报错，而是"界面上能编辑、保存时后端说不认识这个文件"。
 */
const PERSONA_FILE_NAMES = ['IDENTITY.md', 'SOUL.md', 'RULES.md', 'MEMORY.md', 'USER.md'] as const

const PERSONA_LABELS: Record<string, string> = {
  'IDENTITY.md': '搭子身份（IDENTITY）',
  'SOUL.md': '人格（SOUL）',
  'RULES.md': '工作逻辑与规则（RULES）',
  'MEMORY.md': '记忆（MEMORY）',
  'USER.md': '用户档案（USER）',
}

/** 标签与文件路径之间的**一行说明**（产品要求）：告诉用户这个文档是做什么的 */
const PERSONA_DESCRIPTIONS: Record<string, string> = {
  'IDENTITY.md': '它是谁：名字、角色定位、自我介绍。',
  'SOUL.md': '它的性格：怎么说话、在意什么、待人接物的风格。',
  'RULES.md': '它的工作方式与规矩：先做什么后做什么、什么必须先确认。',
  'MEMORY.md': '它记得的事：你的偏好、约定。AI 也可以自己补充（会先确认）。',
  'USER.md': '关于你的档案：怎么称呼你、你的偏好。AI 也可以自己补充（会先确认）。',
}

const PERSONA_PLACEHOLDERS: Record<string, string> = {
  'IDENTITY.md': '我是……',
  'SOUL.md': '它怎么看自己、怎么说话、在意什么。',
  'RULES.md': '它的工作方式与规矩。AI 也可以按你的要求修改（每次修改都会先让你确认）。',
  'MEMORY.md': '它记得的关于你的事：偏好、习惯、约定。它也可以自己往这里补充。',
  'USER.md': '关于你本人的档案：怎么称呼、职业、长期偏好（对齐 openclaw 的 user.md）。',
}

// ---- 头像历史（产品要求：上传过的头像永久保留、随时换回）---------------- //
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
    // 存不进去只影响"历史可换回"，不影响当前头像
  }
}

/** 一份空白助手，作为"新建"的起点 */
export function blankProfile(): AssistantProfile {
  return {
    id: '',
    name: '',
    nickname: '',
    emoji: '🤖',
    avatar: '',
    description: '',
    system_prompt: '',
    // 语音设置给一份出厂默认：`wake_words` 留空是有意的 —— 后端会在读写搭子时
    // 按名字自动补成「你好+名字」（见核心 `default_wake_words`）。这里若自己拼一个，
    // 反而会在用户改过名字之后留下一份对不上的旧词。
    voice: {
      wake_words: [],
      send_word: '发送',
      cancel_word: '取消',
      // 其余命令词不在这里写默认值：它们由命令表（services/voiceCommands.ts）
      // 提供，用户改过的才落进 `command_words`。见 types.ts 里那段说明。
      command_words: {},
      disabled_commands: [],
      // 新搭子的语音设置只是"起点"，启动状态属于**全局**（在语音设置面板里改），
      // 这里保持默认值即可，不必自造一个
      startup_mode: 'off',
      enable_word: '开启语音',
      disable_word: '关闭语音',
    },
    model_id: '',
    temperature: 0.7,
    max_iterations: null,
    max_tool_calls_per_turn: null,
    // 新建搭子默认**跟随全局**：它只在用户主动选过档位时才会真的发出去
    reasoning_effort: null,
    chat_background: '',
    enabled_skills: [],
    confirm_mode: null,
    // 新建的助手默认**不上锁**；锁是在表单里显式设置的
    persona_locked: false,
    builtin: false,
    sort_order: 100,
    restricts_skills: false,
    unavailable_skills: [],
  }
}

/** 由名称生成安全 id：助手 id 会进 URL 与文件名，只能留下安全字符 */
export function toId(name: string): string {
  const ascii = name
    .toLowerCase()
    .replace(/[^a-z0-9_-]+/g, '-')
    .replace(/^-+|-+$/g, '')
  return ascii || `assistant-${Date.now().toString(36)}`
}

// 这里曾有 ``duplicateProfile()``：以某个搭子为模板复制出一份新建用的草稿
// （自动改 id、加" 副本"后缀、不继承人格锁）。「复制搭子」按产品要求整体剔除，
// 它随之删除 —— 现在新建搭子只有 ``blankProfile()`` 一条路（一张空表单）。

/**
 * 助手头像：**一律是图片**，点一下能看大图。
 *
 * ## 取图顺序
 *
 * 1. 搭子自己的 `avatar`（用户上传的 data URL，或 AI 从头像包里挑的）；
 * 2. 随包的内置头像（四个出厂搭子，按 **id** 找，见 `services/avatarPack`）。
 *
 * ## ⚠️ 为什么不再用 emoji / 图标兜底
 *
 * 产品要求"不再使用表情、图标作为头像"。原先这里有三条分支：
 * emoji、`BrandMark`（搭子总管专用的产品 logo）、上传图。结果是同一个列表里
 * 混着照片、emoji 和 logo 三种形态 —— 看起来像三个不同来源的东西拼起来的。
 * 现在内置搭子也有真实头像了，那两条分支就没有存在理由。
 *
 * 兜底仍留一个占位（图片加载不出来时），但它是一个**中性的图框图标**，
 * 不再是"某个搭子专属的表情"。
 *
 * 抽出来是因为**十几个地方**都要渲染它（搭子栏、会话列表、气泡、群聊、设置…），
 * 各写一遍的话，"取图顺序"这个规则迟早会在某处漏掉。
 */
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
  // 圆角与品牌标识一致（见 BrandMark：22px 配 6px，约 27%）
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
    /*
      ⚠️ 用 `<span role="button">` 而**不是** `<button>`（改）。

      原来用 `<button>` 的三条理由都成立（键盘焦点、Enter/Space 触发、cursor-zoom-in
      的"这里能点开"语义），但它有个硬伤：这个头像大量嵌在**本身就是 button 的容器**里
      （搭子栏的列表项、群聊的列表项），于是浏览器报
      `<button> cannot be a descendant of <button>`，React 还会警告 hydration 不一致。

      换成 span 之后，那三点必须**自己补回来**，否则就是拿可用性换掉了警告：
      - `role="button"` + `tabIndex={0}` 让它进 Tab 序列；
      - `onKeyDown` 处理 Enter / Space（原生 button 是自动的）；
      - `cursor-zoom-in` 本来就在类名里，保留即可。
      - **可见焦点**：原生 button 有浏览器默认的 focus ring，span **没有**，
        而 Tailwind 的 reset 又把 outline 清掉了 —— 不显式补 `focus-visible:ring-*`，
        键盘用户就完全看不到焦点在哪（这比按钮嵌套更严重，直接不可用）。

      ⚠️ `stopPropagation` 是必需的 —— 不拦住的话，点头像会顺带把搭子切走、把消息选中。
      ⚠️ `inline-block` 也是必需的：span 默认是 inline，宽高会被忽略、头像会塌成一条线。
    */
    <span
      role="button"
      tabIndex={0}
      title="查看大图"
      aria-label={`查看 ${profile.name} 的头像大图`}
      onClick={(event) => {
        event.stopPropagation()
        event.preventDefault()
        // 一并带上 id：大图里的「配置搭子」要靠它找到是哪个搭子
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

/**
 * 「添加能力」弹窗（产品要求：把"可用工具"长列表换成一个按钮 + 两级选择）。
 *
 * 第一级选类型：Skill（技能）/ MCP（连接器），第二级按**分类**分组勾选；
 * 另外内置 ClawHub / SkillHub 两个查找入口（跳外部网站找技能包，回来上传）。
 */
/** 上层分类的中文名（与 core 的 `skill/groups.py::BUCKET_LABELS` 对齐）。 */
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

  // MCP 工具名形如 server__tool，按 server 分组；技能按**上层分类**分组。
  //
  // ⚠️ 四分类后，这里**只列「通用技能」与「我的技能」**：
  // 内置技能是每个搭子自带、专属技能按归属自动生效 —— 它们出现在"可勾选"的清单里
  // 只会让人以为"勾了才有/勾了就能有"（前者本来就有，后者勾了也拿不到）。
  // 判定以 core 下发的 `bucket` 为准（见 skill/groups.py）。
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
            {/* SkillHub 正确链接（用户指正），另加热门市场魔搭 */}
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

/**
 * 新建 / 编辑助手的表单弹窗。
 *
 * **为什么抽成独立组件**：它有两个入口 —— 设置页的助手列表，和左侧助手栏的
 * 右键菜单。两份实现迟早会长歪（改了一边忘了另一边，而"复制助手"这类逻辑
 * 一旦不一致就特别难解释），所以只留这一份。
 */
export function AssistantFormModal({
  open,
  initial,
  isNew,
  onClose,
  onSaved,
}: {
  open: boolean
  /** 新建时传 `blankProfile()`；编辑时传被编辑的助手 */
  initial: AssistantProfile | null
  isNew: boolean
  onClose: () => void
  /** 保存成功后的回调，调用方通常用它刷新列表 */
  onSaved?: () => void
}) {
  const models = useAppStore((state) => state.models)
  const paths = useAppStore((state) => state.paths)
  const reloadSkills = useAppStore((state) => state.reloadSkills)
  // 「可用能力」那一行要算"这个搭子一共具备多少技能"，得知道全部技能的分类
  const skills = useAppStore((state) => state.skills)
  const activeId = useAssistantStore((state) => state.activeId)
  const setActive = useAssistantStore((state) => state.setActive)
  const save = useAssistantStore((state) => state.save)

  const api = useAppStore((state) => state.api)

  const [form, setForm] = useState<AssistantProfile | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  /** 正在用大编辑窗查看/编辑的人格文件名；null = 关闭 */
  const [editingPersona, setEditingPersona] = useState<string | null>(null)
  /** 该助手上传过的头像历史（最新在前） */
  const [avatarHistory, setAvatarHistory] = useState<string[]>([])
  /**
   * 「语音唤醒词」那一行的输入文本。
   *
   * 它是**独立的一份状态**而不是直接绑 `form.voice.wake_words`：后者是数组，
   * 而输入框是单值 —— 直接来回转换的话，用户打到一半的「你好，」会被解析成
   * `["你好"]` 再渲染回「你好」，逗号被吃掉，第二个词永远打不进去。
   * 分隔约定与语音面板那个唤醒词输入框**完全一致**（见 VoicePanel）。
   */
  const [wakeWordsText, setWakeWordsText] = useState('')
  /** 「添加能力」弹窗：type = 选类型；skill / mcp = 二级分类勾选 */
  const [abilityOpen, setAbilityOpen] = useState(false)
  const [abilityView, setAbilityView] = useState<'type' | 'skill' | 'mcp'>('type')

  // ---- 人格文件与人格锁 -------------------------------------------------- //
  const [personaFiles, setPersonaFiles] = useState<PersonaFile[]>([])
  const [personaLoading, setPersonaLoading] = useState(false)
  const [personaError, setPersonaError] = useState('')
  /** 本次会话里是否已经输对过密码（关掉弹窗就失效） */
  const [unlocked, setUnlocked] = useState(false)
  const [passwordInput, setPasswordInput] = useState('')
  const [newPassword, setNewPassword] = useState('')
  /** 重置锁时要手打的确认语（故意留一点摩擦，见后端 UNLOCK_CONFIRM_TEXT） */
  const [resetConfirm, setResetConfirm] = useState('')
  const avatarInputRef = useRef<HTMLInputElement>(null)
  const backgroundInputRef = useRef<HTMLInputElement>(null)

  // 每次打开都从 initial 重新播种。不能沿用上一次的残留 —— 换个助手编辑却看到
  // 上一个的内容，用户会以为保存错了对象，而且这种错觉很难自证。
  useEffect(() => {
    if (!open) return
    // nickname 等是新字段，旧配置里没有 —— 缺了就补默认值，否则输入框 value 为 undefined
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
    // 唤醒词与表单同一次播种：打开哪个搭子就显示哪个搭子的词
    setWakeWordsText((initial?.voice?.wake_words ?? []).join('，'))
  }, [open, initial])

  // 人格文件是**独立的文件**，不在 AssistantProfile 里，所以要单独读写。
  // 每次打开重新拉：用户在别处（或助手自己）改过的话，界面必须看到最新内容。
  useEffect(() => {
    if (!open || !api) return
    const id = initial?.id
    setUnlocked(false)
    setPasswordInput('')
    setPersonaError('')

    if (!id) {
      // 新建：给两个空条目，让用户一上来就能写人格
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

  /** 人格是否被锁住（锁住时提示词与 SOUL 不可编辑） */
  const personaLocked = Boolean(form?.persona_locked) && !unlocked

  /**
   * 是否为**写死**的内置搭子（服务端下发，见 types.AssistantProfile.locked）。
   *
   * 与 ``personaLocked`` 是两回事：人格锁是用户自己设的密码锁，可以输密码解开；
   * 这个是产品层面"名称 / 简介 / 可用能力 / 人格规则固定"，**没有任何解锁入口**。
   * 只有这四个内置搭子的对应字段要置灰；昵称、头像、温度、模型仍照常可改。
   */
  const lockedBuiltin = Boolean(form?.locked)
  const lockedFields = new Set(form?.locked_fields ?? [])
  // 人格文件里**只有 RULES.md 写死**（修正：SOUL / IDENTITY
  // 是"它是谁"，对齐一次后必须能改）；MEMORY / USER 本来就可写。
  const lockedPersonaFiles = lockedBuiltin
    ? new Set(['RULES.md'])
    : new Set<string>()

  /**
   * 「可用能力」那一行要显示的两个数（产品要求）：
   * **这个搭子一共具备多少技能**、**其中多少当前加载不出来**。
   *
   * 为什么要有这两个数：以前那一行只写"已选 N 项" ——
   * 看不出总量（内置那几十个技能根本不在这行里显示），
   * 也看不出"勾了却没生效"的那些（MCP 没连、技能被停用或删掉了）。
   * 用户勾完一堆技能后，界面不给任何反馈。
   */
  const abilitySummary = useMemo(() => {
    if (!form) return null
    // ⚠️ `skills` 还没加载完时**不要**显示这两个数（独立核查发现的）：
    // 它初值是空数组，这时算出来是"具备 0 个技能"甚至只剩勾选数 —— 那是**假的**
    // （内置技能明明有几十个），用户会以为技能丢了。与其给一个错的数，不如先不给。
    if (skills.length === 0) return null
    const builtin = skills.filter((item) => item.bucket === 'builtin').length
    // 专属技能按**归属**算：只有自己那一批才算它的能力（别人的专属它根本拿不到）
    const own = skills.filter(
      (item) => item.bucket === 'exclusive' && (item.owners ?? []).includes(form.id),
    ).length
    // 内置搭子忽略 `enabled_skills`（服务端锁死那行），所以额外勾选数记 0
    const extra = form.builtin ? 0 : (form.enabled_skills ?? []).length
    const total = builtin + own + extra
    // **未配备**（产品约定）：全局开着开关的技能数 − 这个搭子已具备的。
    // 它回答的是"还有多少技能可以加给它"，是个"还能升级到什么程度"的提示。
    //
    // ⚠️ 与 `unusable` 是**两件事**，别合并：那个是"你勾了、但它当前加载不出来"
    // （MCP 没连、技能被停用/删掉），是**出问题了**，要染警示色；
    // 这个是"它还没有的"，完全正常。口径混了以后，用户会分不清"我勾的东西丢了"
    // 和"还有一些我没勾"。
    const enabledTotal = skills.filter((item) => item.enabled).length
    return {
      total,
      spare: Math.max(0, enabledTotal - total),
      unusable: form.unavailable_skills?.length ?? 0,
    }
  }, [skills, form])

  /**
   * 人格文件在磁盘上的完整路径（显示用）。
   *
   * 依据后端 ``assistants/persona.py`` 的目录规则：``<data>/assistants/<id>/``。
   * 新建中的助手还没有 id，如实写"保存后创建"——编一个路径反而会让人去找。
   */
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
        // 上传过的头像**永久保留**（产品要求）：按助手 id 存在本机，
        // 配置页"我的头像"里随时可以换回来
        const list = [dataUrl, ...loadAvatarHistory(prev.id).filter((item) => item !== dataUrl)]
        saveAvatarHistory(prev.id, list)
        setAvatarHistory(list.slice(0, 8))
      }
      return prev ? { ...prev, avatar: dataUrl } : prev
    })
  }

  const pickBackground = async (file: File) => {
    // 背景图按壁纸同款规格压缩（宽 1600），它与助手一起存进 assistants.json，
    // 太大会拖慢每次保存
    const dataUrl = await readImageAsDataUrl(file, 1600)
    setForm((prev) => (prev ? { ...prev, chat_background: dataUrl } : prev))
  }

  const submit = async () => {
    if (!form) return
    const payload: AssistantProfile = {
      ...form,
      id: isNew ? toId(form.name || form.id) : form.id,
      name: form.name.trim(),
      // 唤醒词那一行是单值输入框，提交时按与语音面板同一套约定拆回数组。
      // 全空 → 空数组，交给后端按名字补默认词（前端不自己造一个 —— 否则用户
      // 改了名字之后会留下一份对不上的旧词）。
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

      // 人格文件**不在** AssistantProfile 里（是磁盘上的独立文件），必须单独写。
      // 只写有内容的：两个都空的话没必要在磁盘上留两个空文件。
      if (api) {
        for (const file of personaFiles) {
          // ⚠️ 跳过硬锁人格文件（内置搭子的 RULES.md）。
          //
          // 实测反馈"点保存关不掉弹窗、但配置其实已经生效"就出在这里：
          //   1. 上面 `save(payload)` **已经成功落盘** —— 所以配置真的生效了；
          //   2. 这里接着把**整份**人格文件重发一遍，包括用户根本没动过的 RULES.md
          //      （打开弹窗时 getPersonaFiles 把全文拉回来了，见上面的 load effect）；
          //   3. 后端对 RULES.md 是**无条件 409**（只看文件名、不比对内容），于是抛错；
          //   4. catch 只 setError 不 onClose → 红字留着、弹窗关不掉。
          //
          // 界面早就把这个文件那行按钮置灰成「固定」了（见 lockedPersonaFiles），
          // 提交时漏的正是同一个判断。**产品固定的文件不该由客户端提交** ——
          // 比"比较内容有没有变"更清楚，也不用为此多存一份原始副本。
          if (lockedPersonaFiles.has(file.name)) continue
          if (file.content.trim()) {
            await api.writePersonaFile(payload.id, file.name, file.content)
          }
        }
        // 新建助手时设的密码，要等拿到 id 之后才提交得出去
        if (isNew && newPassword.trim()) {
          await api.personaLock(payload.id, { action: 'set', password: newPassword.trim() })
        }
      }

      // 助手的技能白名单会影响可用工具集，保存后要让技能列表跟着刷新
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
                '这是内置搭子：名称、简介、可用能力与人格规则（RULES.md）由产品固定，不能修改或删除；昵称、头像与人格（SOUL / IDENTITY）仍可自由设置。'}
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

            {/* 保存时才撞上「唤醒词不能为空，否则这个搭子喊不醒」
                的校验，而表单里**根本没有填的地方** —— 把入口补在这一行。
                分隔约定与语音面板那个唤醒词输入框一致（逗号隔开多个）。 */}
            <Field label="语音唤醒词" hint="说了它就切到这个搭子；多个用逗号隔开，留空则按名字自动生成">
              <Input
                value={wakeWordsText}
                onChange={(event) => setWakeWordsText(event.target.value)}
                onBlur={() =>
                  // 失焦时归一化显示（与语音面板同一套处理）：各种分隔符统一成「，」
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
              {/* 「图标」改成「头像」—— 不再让用户从一堆 emoji 里挑，
                  直接展示这个搭子当前的头像；新建搭子还没有头像，就干脆不显示，
                  不给一个假的占位。
                  ⚠️ `emoji` 字段仍然保留：它早已不参与头像显示（见 AssistantAvatar
                  的取图顺序），但老配置与搭子包导入还要读它。 */}
              <div className="flex flex-wrap items-center gap-2">
                <Button variant="secondary" onClick={() => avatarInputRef.current?.click()}>
                  {form.avatar ? '换张头像' : '上传图片'}
                </Button>
                {form.avatar ? (
                  <Button variant="secondary" onClick={() => setForm({ ...form, avatar: '' })}>
                    移除头像
                  </Button>
                ) : null}
                {/* 上传后立刻给预览：没有它，用户只能保存后再去列表里确认图长什么样 */}
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
                    // 清掉 value，否则连续选同一张图不会再触发 change
                    event.target.value = ''
                  }}
                />
              </div>

              {/* 我的头像：上传过的所有头像永久保留（产品要求），点一下即可换回 */}
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

            {/* 聊天背景（产品要求）：与全局壁纸独立，只作用于这个助手的对话区 */}
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

          {/* ---- 人格 / 规则 / 记忆 / 用户档案 --------------------------------- */}
          {/* 系统提示词已**文件化**为 RULES.md（产品要求，改名"工作逻辑与规则"）：
              与人格/记忆同形式 —— 显示路径、点开编辑、AI 可改。 */}
          <div className="mt-3">
            <div className="text-[12.5px] text-ink-soft">人格与记忆</div>
            <p className="mt-0.5 text-[11px] leading-relaxed text-ink-faint">
              这几个文件是这个搭子的“自我”与“规矩”，会一起进入每次对话。你随时可以改，
              搭子也可以按你的要求往里补充（每次补充都会先让你确认，且立即生效）。
            </p>

            {personaLocked ? (
              /* 上锁时**只拦人格类**（SOUL/RULES），模型、工具照常可改 ——
                  这是用户明确要的粒度。解锁入口从原"系统提示词"框挪到这里。 */
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

            {/* **文件入口而不是文本框**（产品明确要求）：内容多了文本框会把整个
                表单撑得很长，而且"每次都要滚下来找"很难受。这里只显示文件路径
                与状态，点「打开」进专门的大编辑窗。 */}
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
                    {/* 说明行（产品要求）：标签与路径之间，一句话讲清这个文档管什么 */}
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
                {/* 要能一眼看出"这个搭子一共有多少能力、其中多少当前用不了"。
                    以前只写"已选 N 项" —— 看不出总量（内置那几十个不在这行显示），
                    也看不出"勾了却没加载出来"的那些（MCP 没连、技能被停用或删掉）。 */}
                {abilitySummary ? `具备 ${abilitySummary.total} 个技能` : ''}
                {/* 的原话：「具备 xx 个技能，xx 个技能未配备」——
                    两个数**一直**都要写出来（为 0 也照写）。这个数是中性的，不染警示色。 */}
                {abilitySummary ? `，${abilitySummary.spare} 个技能未配备` : ''}
                {/* 「当前不可用」是**另一码事**（勾了却加载不出来），确实出问题了才提，
                    而且要染警示色 —— 与上面那个中性数分开说，用户才不会混淆。 */}
                {abilitySummary && abilitySummary.unusable > 0 ? (
                  <span className="text-warning">
                    {`；其中 ${abilitySummary.unusable} 个当前不可用`}
                  </span>
                ) : null}
                {!form.builtin && (form.enabled_skills ?? []).length > 0
                  ? `（额外勾选 ${(form.enabled_skills ?? []).length} 项）`
                  : null}
                {!form.builtin && (form.enabled_skills ?? []).length === 0
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
              {/* **按钮而不是开关**：以前是个 Switch，"关掉"却做不到（它表达的是
                  "谁是当前助手"这个全局状态，不是这个助手自己的属性）——
                  用户理解成"打开之后无法关闭"。按钮语义清楚：是当前时禁用。 */}
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

    {/* 「添加能力」两级选择弹窗 */}
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

    {/* 人格文件的大编辑窗。放在外层 Modal 的**同级**而不是嵌在里面：
        外层有滚动容器与进场动画，嵌套 fixed 弹层的位置会被动画的
        transform 影响，且滚动会被外层截走。 */}
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
          </p>
          <textarea
            value={
              personaFiles.find((file) => file.name === editingPersona)?.content ?? ''
            }
            // SOUL/RULES 属于"人格"，跟着锁一起；MEMORY/USER 是事实记录，不拦
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
