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

/*
  ⚠️ 这里原本还定义着 `SOURCE_FORMAT_LABELS` / `PACKAGE_ACCEPT` / `OPTION_BUTTON_CLASS` /
  `sourceLabel`。第 57 批把「添加技能」弹层提成了顶层组件
  （`components/AddSkillDialog.tsx`，为的是"任何页面都能用语音唤起它"），它也要用这几样 ——
  于是搬进了中立的小模块 `components/skillImport.ts`，两边共用。
  留着两份的下场很具体：以后加一种新格式，只改到一处，另一处显示成原始英文 key。
*/

function formatBytes(size: number): string {
  if (size < 1024) return `${size}B`
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)}KB`
  return `${(size / 1024 / 1024).toFixed(1)}MB`
}

/**
 * 分类的显示名与图标。
 *
 * ⚠️ **必须与后端实际在用的 `category` 取值保持一一对应**。
 * 这里只登记了一部分时，渲染处会回退到 `general`，于是 `memory`/`knowledge`/
 * `thinking`/`persona` 四类**全部显示成「通用」** —— 用户看到的就是
 * "设置里冒出好几个都叫通用栏目"（报的缺陷）。
 * 后端取值来源：`core/src/my_agent/skill/builtin/*.py` 的 `@skill(category=...)`。
 */
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

/**
 * 分栏的显示顺序。
 *
 * 用显式清单而不是 `localeCompare` 按分类名排序：分类键是英文、显示名是中文，
 * 按英文键排会得到 office/knowledge/life/... 这种**用户看不出道理**的顺序，
 * 而顺序一乱，用户上次记住的位置就变了。
 *
 * 未登记的分类排在最后（见 `grouped`），保证将来新增分类时只影响末尾，不搅乱前面。
 */
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

/**
 * 技能页的四个子页（产品约定）。
 *
 * ⚠️ 数组顺序就是界面上按钮的顺序；**默认停在「我的技能」**
 * （产品明确要求："用户上传技能在 我的技能 里，且进入技能页默认就在我的技能子页面"）。
 *
 * ⚠️ 分类判定以 core 下发的 `SkillInfo.bucket` 为准（见 core 的 `skill/groups.py`）——
 * 前端**不重算**：两边各有一套归类规则的话，改一处必然对不上。
 */
type SkillBucket = 'mine' | 'common' | 'builtin' | 'exclusive'

const BUCKETS: ReadonlyArray<{ key: SkillBucket; label: string; note: string }> = [
  { key: 'mine', label: '我的技能', note: '你上传的、AI 创建的、AI 下载安装的技能' },
  { key: 'common', label: '通用技能', note: '按需挑选：预设能力与 MCP 外部工具' },
  { key: 'builtin', label: '内置技能', note: '每个搭子创建时即自带，不可关闭' },
  { key: 'exclusive', label: '专属技能', note: '只有归属的那个搭子能用，不可关闭' },
]

/**
 * 「通用技能」栏那排**小分类**按钮的顺序（产品要求）。
 *
 * ⚠️ 必须与核心的 `skill/groups.py::DOMAIN_ORDER` **逐字一致**：那边是判定与下发的
 * 唯一真相来源，这边只管顺序与按钮文案。前端拿到的 domain 是中文串，直接当按钮名用 ——
 * 所以这里不需要"键 → 显示名"的映射表（与上面 `CATEGORY_META` 那种英文键不同）。
 *
 * 前 13 个来自用户导入的第三方素材库的分类文件夹名；「系统」是给客户端自带的
 * 音量 / 亮度 / 锁屏那几项补的（它们没有对应行业，但产品要求自带技能也要分类）。
 *
 * ⚠️ 「玄学」整分类删除（产品约定："删除玄学分类以及其中的 16 个技能"）——
 * 这一项删掉的同时，核心那份 `DOMAIN_ORDER`、出厂技能资源目录、同步脚本都要跟着删，
 * 缺一处就会出现"按钮还在、点进去是空的"或者"资源里还有、下次同步又冒出来"。
 */
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

/**
 * 一个技能在「通用技能」栏里归到哪个分类（**显示用的名字**）。
 *
 * ⚠️ 这个函数是分类显示名的**唯一**来源：筛选按钮（`domainOptions`）、
 * 实际筛选（`scoped`）、分组标题（`grouped` 的 key）三处都必须用它。
 * 任何一处改回 `skill.domain`，就会冒出"按钮上叫「办公」、点进去却筛不出东西"
 * 或者"分组标题全叫「通用」"这类对不上的毛病。
 *
 * 为什么要分两级：`domain` 是**中文小分类**（电商 / 金融 / 办公 / 系统…），
 * 它来自两处 —— 第三方技能包导入时随包带进来的，以及后端 `groups.BUILTIN_DOMAINS`
 * 给自带技能补的那张表（在 `SkillMeta.to_dict` 里合成后下发）。
 * 但**总有漏网的**（既没随包带、也不在那张表里，例如自带的知识类技能），
 * 它们的 `domain` 是空串 —— 这时退回 `category`（英文键）翻成中文，
 * 至少让它们落进「知识」这样的一个组里，而不是全挤在一堆没有名字的地方。
 *
 * 最坏情况（两级都拿不到）原样返回 `category`：让用户看出是个陌生的键，
 * 也好过悄悄归进「通用」让人以为分类丢了。
 */
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

/**
 * 用户自定义技能。
 *
 * **声明式，不让用户写代码**：打包后的核心是 PyInstaller 产物，运行时既没有
 * 编译环境也装不了新依赖；而且"让用户写 Python"等于把任意代码执行交出去。
 * 这里只提供两种动作 —— 发一个 HTTP 请求、跑一条本机命令。
 */
function CustomSkillsSection({ onChanged }: { onChanged: () => void }) {
  const api = useAppStore((state) => state.api)
  const [list, setList] = useState<CustomSkillDef[]>([])
  const [loaded, setLoaded] = useState(false)
  const [draft, setDraft] = useState<CustomSkillDef | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  /**
   * 技能文件夹（投放区）的位置。
   *
   * ⚠️ 界面上**不再有**"打开技能文件夹 / 重新扫描"两个按钮了（产品要求
   * 按钮太多、合并成一个）。但这个路径仍然要显示出来：投放区机制还在用（丢了技能
   * 文件夹进去，下次启动会自动接入），**不显示路径用户就没法用** —— 那等于把能力删了
   * 却不说。所以这里只取路径做文字展示，不做"打开"动作。
   */
  const [folder, setFolder] = useState<SkillFolderInfo | null>(null)
  /**
   * 导入技能包的整套东西（上传 / 导入文件夹 / 结果弹窗）都搬去了**顶层**
   * `components/AddSkillDialog.tsx`（语音要能从任何页面唤起它）。
   * 这里只订阅它的"版本号"来刷新列表 —— 否则在别的页面导入完切回来，看到的还是
   * 那份旧列表，用户会以为"我明明添加了，怎么没有"。
   */
  const revision = useSkillRevision()

  // 导入完成（revision 变化）后重新拉列表。
  // ⚠️ 依赖里**只放 revision** 是有意的：`load` 每次渲染都是新函数，放进去会让它
  // 每一帧都重拉一次列表；而 revision 变化恰恰就是"该重拉了"的唯一信号。
  useEffect(() => {
    if (revision > 0) void load()
  }, [revision])
  /** 「查看详情」正在展示的自定义技能；指导型可在详情里**直接编辑指导内容** */
  const [detail, setDetail] = useState<CustomSkillDef | null>(null)
  const [detailSaving, setDetailSaving] = useState(false)
  /** 详情弹窗里的"包内文件"（打开详情时才拉，不在列表接口里带） */
  const [detailFiles, setDetailFiles] = useState<SkillFileEntry[]>([])

  /*
    ⚠️ 这里原本是 `finishImport` / `uploadPackage` / `importFolder` 三个函数。
    它们随弹层一起搬去了 `AddSkillDialog`（那边自己管忙态、失败 toast 与结果弹窗）。
    技能页不再需要知道"导入是怎么进行的"，只需要在**成功之后**刷新列表 ——
    见上面的 `revision` 订阅。
  */

  /** 打开详情：顺带把"包内文件"拉出来（列表接口不带，避免每次列技能都读盘）。 */
  const openDetail = async (item: CustomSkillDef) => {
    setDetail(item)
    setDetailFiles([])
    if (!api) return
    try {
      const result = await api.getSkillFiles(item.id)
      setDetailFiles(result.files ?? [])
    } catch {
      // 没落盘过的技能（手动创建的）查不到文件，这不是错误，安静留空即可
      setDetailFiles([])
    }
  }

  const load = async () => {
    if (!api) return
    try {
      const result = await api.getCustomSkills()
      // ⚠️ 只保留**没有小分类**的那些（报"我的技能里还显示着几百个"）。
      // 带 `domain` 的是批量导入的第三方技能，它们归「通用技能」栏（见 core 的
      // `bucket_of`）—— 两栏都列同一批，用户会以为装了两份，也分不清哪份能删。
      // 判据用 `domain` 而不是别处下发的 `bucket`：这个接口返回的是**原始定义**，
      // 它本来就没有 bucket 字段（bucket 是下发时按分类算出来的）。
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
  // 技能文件夹位置：只读、幂等，渲染期取一次即可（与上面 load 的写法一致）
  if (!folder && api) {
    void api
      .getSkillFolder()
      .then(setFolder)
      .catch(() => {
        // 拿不到路径就不显示那一行，不影响别的功能
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

  /** 行上直接改开关 / 权限（上传导入的技能也要能改这两样，用户明确指出） */
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
        {/* 一个入口就够：具体走哪条路由「添加技能」里的两个选项决定。
            以前这里并排四个按钮（上传 / 文件夹 / 打开文件夹 / 重新扫描），
            宽窄不一、还让人以为是四件不同的事（产品要求合并）。 */}
        <div className="flex shrink-0 items-center gap-2">
          {/*
            ⚠️ 弹层现在挂在**应用顶层**（`AddSkillDialog`），这里只是把它叫起来 ——
            「导入中…」那个忙态也跟着搬过去了：导入可能跑好几秒，而这颗按钮所在的
            页面随时可能被切走（语音从**任何页面**都能唤起那个弹层）。
          */}
          <Button variant="primary" icon={<Plus size={13} />} onClick={openAddSkill}>
            添加技能
          </Button>
        </div>
      </div>

      {/* 两条路各写各的：用户最容易误解的是"随便丢哪儿都行"，
          所以按"点哪里 → 发生什么"的顺序写，不出现内部概念。
          ⚠️ 投放区这段必须留着：界面上已经没有"打开技能文件夹 / 重新扫描"按钮了，
          路径再不写出来，用户就彻底没办法把技能放进去了（能力还在，只是不再有按钮）。 */}
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
                {/* 导入时的提示（解释器没找到、字段被截断…）**必须露出来**：
                    静默降级是这个项目最不能接受的失败方式 */}
                {item.note ? (
                  <p className="mt-1 rounded-[6px] border border-warning/30 px-2 py-1 text-[11px] leading-relaxed text-warning">
                    {item.note}
                  </p>
                ) : null}
                {/* 权限与开关**直接在行上改**（用户指出上传导入的技能没有这两样）。
                    走 saveCustomSkill 整条 upsert，与编辑表单同一落库路径 */}
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
                  {/* 指导型没有 url/命令可编辑，表单是给"可执行技能"用的，别让用户点进去一脸懵 */}
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

      {/*
        ⚠️ 这里原本是「添加技能」的二选弹层（上传技能包 / 导入文件夹）。
        第 57 批整块搬到了 `components/AddSkillDialog.tsx` 并挂在应用顶层 ——
        因为它现在要能被**语音从任何页面**唤起，而 `useVoiceCommand` 的实现
        只存在于"当前渲染出来的组件"里：弹层留在技能页，人在群聊页说「添加技能」
        就是石沉大海。
      */}

      {/*
        ⚠️ 这里原本是「技能包导入结果」弹窗，一并搬去了 `AddSkillDialog`。
        它必须跟着走：导入是异步的（可能好几秒），用户往往先把选项弹层关掉 ——
        结果得**自己冒出来**，而不是塞进一个已经关掉的窗里。
      */}

      {/* 自定义技能详情 */}
      <Modal
        open={detail !== null}
        onClose={() => setDetail(null)}
        width="max-w-lg"
        title={`详情：${detail?.name ?? ''}`}
        footer={
          <>
            <Button onClick={() => setDetail(null)}>关闭</Button>
            {/* 指导型支持在详情里直接改 SKILL.md 内容并保存（产品要求） */}
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
            {/* 导入时的提示要在这里出现（解释器没找到、字段被截断…） */}
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
            {/* 包内文件：技能包里常常带着模板、示例、脚本 —— 用户要能看到它们
                真的被保留下来了，而不是只看到一句"已安装" */}
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
  /** 「查看详情」正在展示的技能（内置 / MCP） */
  const [detailSkill, setDetailSkill] = useState<SkillInfo | null>(null)
  /**
   * 当前停在哪个子页。**默认「我的技能」**（产品要求：
   * "用户上传技能在 我的技能 里，且进入技能页默认就在我的技能子页面"）。
   */
  const [bucket, setBucket] = useState<SkillBucket>('mine')

  /** 「通用技能」栏的小分类筛选：`'all'` = 全部。 */
  const [domain, setDomain] = useState<string>('all')

  /** 按上层分类分桶（判定以 core 下发的 `bucket` 为准，见 core 的 skill/groups.py）。 */
  const byBucket = useMemo(() => {
    const map: Record<SkillBucket, SkillInfo[]> = { mine: [], common: [], builtin: [], exclusive: [] }
    for (const skill of skills) {
      // 老核心没有 `bucket` 字段时按 source 兜底，免得整页空掉
      const key = (skill.bucket ?? (skill.source === 'custom' ? 'mine' : 'common')) as SkillBucket
      ;(map[key] ?? map.common).push(skill)
    }
    return map
  }, [skills])

  /** 当前子页里**实际出现**的小分类（按核心那份顺序排；未登记的排末尾）。 */
  const domainOptions = useMemo(() => {
    const found = new Set<string>()
    for (const skill of byBucket[bucket]) {
      // ⚠️ 用 `domainLabel` 而不是 `skill.domain`：客户端自带的通用技能（音量 / 文档 /
      // Excel…）**没有** domain，但它们同样要能被筛出来（
      // "每部分的标题要和分类同步"）。只收 domain 的话，按钮里永远没有「办公 / 系统 /
      // 生活」，而「全部」下却实实在在摆着这几组 —— 两边对不上。
      found.add(domainLabel(skill))
    }
    const ordered = DOMAIN_ORDER.filter((item) => found.has(item))
    const rest = [...found].filter((item) => !DOMAIN_ORDER.includes(item)).sort()
    return [...ordered, ...rest]
  }, [byBucket, bucket])

  /**
   * 按小分类筛选后的技能。
   *
   * ⚠️ 只在「通用技能」栏生效：那是导入的第三方技能（电商 / 金融 / 医疗…）所在的地方。
   * 其它三栏不加这一层 —— 给它们也摆一排按钮只会让界面更吵。
   *
   * ⚠️ 筛的时候必须用**同一个** `domainLabel`：按钮上的名字是它算的，
   * 这里要是改回 `skill.domain`，点「办公」就会把所有自带办公技能筛掉。
   */
  const scoped = useMemo(() => {
    if (bucket !== 'common' || domain === 'all') return byBucket[bucket]
    return byBucket[bucket].filter((skill) => domainLabel(skill) === domain)
  }, [byBucket, bucket, domain])

  /** 当前子页里再按细类分栏；「专属技能」按**归属搭子**分栏（用户要看到"仅谁可用"）。 */
  const grouped = useMemo(() => {
    const map = new Map<string, SkillInfo[]>()
    for (const skill of scoped) {
      // 「专属技能」按归属搭子分栏；「通用技能」按**显示用的小分类名**分栏
      // （导入的第三方技能要在通用栏里按电商 / 金融 / 医疗… 分组看，
      //   自带的那批按办公 / 系统 / 生活 —— 两组名字都走 `domainLabel`，于是"办公"
      //   只会出现一组，而不是"office"和"办公"各一组）；其余一律按 category。
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
    // 英文键按 CATEGORY_ORDER，中文小分类按 DOMAIN_ORDER，都未登记的一律排到最后
    // （而不是回退成 0 跑到最前面 —— 那样新分类一出现就会插到用户眼前第一个位置）。
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

  /** 「我的技能」子页不列内置/MCP 那批；其余子页按当前分类渲染。 */
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
      // **不能静默。** 后端对"永久开启"的技改会明确拒绝（409 + 人话），
      // 而那正是这个界面既没有开关也可能改不动的地方 —— 吞掉它的话，
      // 用户点了一下、界面毫无变化，只会以为设置页坏了。
      useNotificationStore.getState().push({
        level: 'warning',
        title: '这个技能改不了',
        message: exc instanceof Error ? exc.message : String(exc),
      })
      // 重新拉一次，把界面拉回后端的真实状态（避免显示成"已改"）
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
          {/* 原来那句是中性的功能说明，换成**警示**。
              理由很实在：技能越多，模型每轮要读的工具定义与说明就越多，token 消耗与
              跑偏概率一起涨。这句话是给用户的决策依据，不是装饰 —— 所以用警示色 + 加粗，
              而不是跟正文一样的灰色小字（那等于没说）。 */}
          <p className="mt-1 text-[12.5px] font-semibold leading-relaxed text-warning">
            重要提示：搭子的技能不是越多越好，那样只会让它产生大量的不必要消耗，
            我们建议每个搭子仅搭配它职能所必须的技能。
          </p>
          {/* 在这一行下面再补一句**澄清**。
              它答的是用户最容易搞混的那件事 —— 技能页这里的开关是**总闸**
              （这个技能允不允许被配置），而"某个搭子到底用不用它"要去搭子的配置页勾。
              少了这句，用户会以为在本页打开开关就等于给所有搭子都装上了，
              然后去搭子那儿发现没生效，还以为技能坏了。 */}
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

      {/* 四个子页的切换按钮（四个分类按钮放在页面顶部） */}
      <div className="mt-4 flex flex-wrap gap-2">
        {BUCKETS.map((item) => (
          <button
            key={item.key}
            type="button"
            title={item.note}
            aria-current={bucket === item.key ? 'page' : undefined}
            onClick={() => {
              setBucket(item.key)
              // 切子页时把小分类筛选归零：否则从「电商」切到「内置技能」会带着一个
              // 那边根本不存在的筛选条件，界面看起来像空的（用户会以为技能丢了）
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

      {/*
        「通用技能」栏的**小分类**按钮（"要根据分类在通用技能里增加
        小分类按钮，全部按钮 + 多个分类按钮"）。

        ⚠️ 只在这一栏显示：那是导入的第三方技能（电商 / 金融 / 医疗…）所在的地方。
        其它三栏不加这一层 —— 摆一排点进去多半是空的按钮只会让界面更吵。

        ⚠️ 选项从**当前实际存在的** domain 生成，而不是写死清单里那 14 个：只装了电商那批时，
        就不该出现一个点进去必然空白的按钮。
      */}
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
                {/* ⚠️ 计数必须与按钮名**同源**（`domainLabel`）。原先这里直接比 `skill.domain`，
                    而 MCP 工具的 domain 是空串（它靠 category='mcp' 才映射成「MCP 外部工具」）
                    ⇒ 恒不相等 ⇒ 那个按钮上永远写着 0；客户端自带的办公/系统/生活几组
                    也各少算了几个（实测反馈正是这个 0）。 */}
                {byBucket.common.filter((skill) => domainLabel(skill) === item).length}
              </span>
            </button>
          ))}
        </div>
      ) : null}

      <div className="mt-4 flex flex-col gap-5">
        {bucket === 'mine' ? (
          // 「我的技能」= 用户上传 / AI 创建 / AI 下载安装的那一批 = 原来的自定义技能区
          //（含「添加技能」入口）。产品要求：用户上传的技能就落在这一页。
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
                // 「专属技能」子页是按**归属搭子**分栏的（这里的 category 变量装的是搭子名），
                // 所以不走细类图标那套，直接写成「仅 XX 可用」——
                // 这一栏要回答的正是"这是谁的专属"。
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
                // ⚠️ 分组键有**两种**：通用技能里带 domain 的用中文小分类名（"电商"），
                // 其余用 `category`（英文键）。原先这里只查英文表、查不到就回退 `general`，
                // 于是「全部」下每一组的标题都写成「通用 xx 个」—— 分组其实分对了，
                // 标题却全一样，用户会以为分类根本没生效（报的）。
                const meta = CATEGORY_META[category]
                if (!meta) {
                  // 不在英文表里 = 中文小分类（导入技能带的 domain）→ 直接拿它当标题
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
                // 收费口径：这两个心鉴学技能**当前免费** ——
                // 服务端侧的口径也一并改成"当前不产生任何费用"（见核心
                // `resources/xjx/` 里两份正文的 billing 说明）。
                // 以前这里分两档（一个标"要花钱"、一个标"换绑才花钱"），现在统一成
                // 一个绿徽标，只与"其余全部永久免费"在文案上区分。
                // 按 display_name 精确匹配，别按 name 或来源猜 —— 心鉴学的名字
                // 是产品口径，改动必须在这里显式体现。
                const xjxFree =
                  skill.display_name === '人际关系运营' || skill.display_name === 'Soulmate专用'

                // **完全免费**标签（"只有你完整检查完一个技能，才能确认
                // 是否能为它打上完全免费标签"）。
                //
                // ⚠️ `domain` 有值 = 本次导入的第三方技能：它们是**逐个通读全文**核过
                // "要不要 API Key / 注册 / 留联系方式 / 付费"之后才装进来的，导入时把源目录的
                // 分类写进了 domain。其余没走过这套检查的东西**不该**挂这个标签。
                //
                // ⚠️ MCP 工具是产品要求加上来的（"通用技能中，两个 MCP 外部
                // 工具也要加上完全免费标签"）：它是我们自带的那一个只读 SQLite 服务，
                // 不需要任何外部账号、不产生费用。**别按旧注释把它删掉。**
                //
                // ⚠️ `&& bucket === 'common'` 是 补的**互斥条件**：这两个标签
                // 表达的是两种不同的"免费"，同一个技能**不该同时挂**（用户在改分类那批里
                // 说的原话是"将完全免费标签**更换为**永久免费"）。少了它，那 10 个从通用栏
                // 转出去的技能会同时亮两个绿标 —— 判据本身没错（它们的 domain 还在），
                // 错在"转类之后就不该再按通用栏那套标了"。实测确认过这个重叠。
                const verifiedFree =
                  (Boolean(skill.domain) || skill.source === 'mcp') && skill.bucket === 'common'

                // **永久免费**标签：内置技能全部 + 专属技能全部。
                //
                // 与上面「完全免费」的分界是**判据来源**，不是免费程度：
                // - 「完全免费」= 逐个通读过全文、确认没有外部依赖的第三方 / MCP 技能；
                // - 「永久免费」= 客户端出厂就带着的那两批（内置 = 每个搭子都有且关不掉；
                //   专属 = 只有归属的那个搭子能用）—— 都是我们自己做的，不存在收费的可能。
                //
                // ⚠️ 专属这一栏按 `bucket` **整栏**判，**不要**去筛 `owners`：用户说的是
                // "buddy manager 可用的 33 个技能要全部加上永久免费标签"，而那一栏里正好
                // 33 个 —— 31 个归 Buddy Manager，另 2 个是心鉴学的。按 owners 筛会漏掉心鉴学
                // 那两个，用户看到的就是"说好 33 个、只亮了 31 个"。
                // （心鉴学那两个**另外**还会带上「免费」徽标，那是上次的产品约定，语义不冲突：
                //   一个说"这是出厂自带、永久不收费"，一个说"当前使用不产生费用"。）
                //
                // ⚠️ 心鉴学那两条要**排除**：它们现在标「免费」，
                // 而且**以后是要收费的** —— 打上「永久免费」就等于我们自己再也改不回去。
                // 两者的分界在这里是**产品事实**，不是措辞偏好。
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
                      {/* 永久开启的技能**不画开关与权限下拉框**：
                          后端会拒绝关闭与降级（见 core 的 skill/locked.py），
                          画一个点了必报错的控件比不画更糟。这里只如实说明状态。 */}
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

                      {/* 「详情」固定在最右：专属技能的红字说明
                          在它左边，其余技能在开关左边 —— 阅读顺序都是"状态 → 操作" */}
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

      {/* 技能详情（内置 / MCP） */}
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
