import clsx from 'clsx'
import { Loader2, RefreshCw, Trash2 } from 'lucide-react'
import { useCallback, useEffect, useState } from 'react'

import { Badge, Button, EmptyState, Input, Modal, Select } from '@/components/ui'
import { formatDateTime } from '@/lib/format'
import { useAppStore } from '@/stores/appStore'
import { useAssistantStore } from '@/stores/assistantStore'
import type { AuditKind, AuditLogEntry, AuditStats, AuditStatus } from '@/types'

const STATUS_META: Record<
  AuditStatus,
  { label: string; tone: 'success' | 'danger' | 'warning' | 'neutral' }
> = {
  ok: { label: '成功', tone: 'success' },
  error: { label: '失败', tone: 'danger' },
  denied: { label: '被拒绝', tone: 'warning' },
  timeout: { label: '超时', tone: 'warning' },
}

const FILTERS: Array<{ key: AuditStatus | 'all'; label: string }> = [
  { key: 'all', label: '全部' },
  { key: 'ok', label: '成功' },
  { key: 'error', label: '失败' },
  { key: 'denied', label: '被拒绝' },
]

/**
 * 留痕类型。
 *
 * 取值与 core 的 `security/audit.py` 一一对应；`skill` 是技能调用，其余是实体操作。
 * 「权限确认」这个类型目前还没有写入点（确认结果记在对应技能那条的 status 上），
 * 留着是为了与后端口径一致 —— 不是漏了筛选项。
 */
const KIND_LABEL: Record<string, string> = {
  skill: '技能调用',
  assistant: '搭子',
  group: '群聊',
  session: '会话',
  task: '自动化任务',
  permission: '权限确认',
}

const KIND_FILTERS: Array<{ key: AuditKind | 'all'; label: string }> = [
  { key: 'all', label: '全部类型' },
  { key: 'skill', label: '技能调用' },
  { key: 'assistant', label: '搭子' },
  { key: 'group', label: '群聊' },
  { key: 'session', label: '会话' },
  { key: 'task', label: '自动化任务' },
  { key: 'permission', label: '权限确认' },
]

/**
 * 实体操作的动作用词。
 *
 * 这些词来自 core 的 `record_op(action=...)` 调用点，**改核心时要一起改这里**，
 * 否则界面上会直接露出英文原文（兜底就是这么写的：宁可露出原文，也不编一个
 * 看起来像人话、其实对不上的词）。
 */
const ACTION_LABEL: Record<string, string> = {
  create: '新建',
  update: '修改',
  delete: '删除',
  clear: '清空',
  run: '执行',
  run_now: '立即执行',
  resume: '续跑',
  interrupt: '被中断',
  fail: '失败',
  discuss_done: '讨论完成',
  discuss_interrupted: '讨论中断',
}

type RangeKey = 'all' | 'today' | '7d' | '30d' | 'custom'

const RANGES: Array<{ key: RangeKey; label: string }> = [
  { key: 'all', label: '全部时间' },
  { key: 'today', label: '今天' },
  { key: '7d', label: '近 7 天' },
  { key: '30d', label: '近 30 天' },
  { key: 'custom', label: '自定义' },
]

function dayString(date: Date): string {
  const pad = (value: number) => String(value).padStart(2, '0')
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`
}

/**
 * 把快捷范围换算成后端要的起止日期。
 *
 * 传 **YYYY-MM-DD** 而不是 epoch：后端 `day_range` 负责把结束日算到当天 23:59:59
 * —— 在前端自己算 epoch，"结束日少一天"是最常见的错，而且很难看出来。
 */
function rangeDates(
  range: RangeKey,
  from: string,
  to: string,
): { date_from?: string; date_to?: string } {
  if (range === 'all') return {}
  if (range === 'custom') {
    return { date_from: from || undefined, date_to: to || undefined }
  }
  const now = new Date()
  const start = new Date(now.getFullYear(), now.getMonth(), now.getDate())
  if (range === '7d') start.setDate(start.getDate() - 6)
  if (range === '30d') start.setDate(start.getDate() - 29)
  return { date_from: dayString(start), date_to: dayString(now) }
}

/**
 * 审计表里的时刻：**不带年、带秒**（表格一行一条记录，带年会把那一列撑得很宽）。
 * 格式实现统一在 `lib/format`（第 92 批，M-36 改用 `Intl`）——
 * 原先它与工作区那份是**两份一模一样的手写实现**。
 */
const formatTime = (seconds: number): string =>
  formatDateTime(seconds, { withSeconds: true, withYear: false })

/** 实体操作（建群 / 改搭子 / 跑任务…）的标题 —— 它们的 `skill_name` 是空串。 */
function entityTitle(entry: AuditLogEntry): string {
  const kind = KIND_LABEL[entry.kind ?? ''] ?? '操作'
  const action = entry.action ?? ''
  return `${kind}·${ACTION_LABEL[action] ?? (action || '操作')}`
}

function EntryRow({ entry, actorName }: { entry: AuditLogEntry; actorName?: string }) {
  const [open, setOpen] = useState(false)
  const meta = STATUS_META[entry.status] ?? STATUS_META.ok
  const hasDetail = Boolean(entry.params || entry.detail)

  return (
    <div className="px-3.5 py-2.5">
      <div className="flex items-center gap-2">
        <button
          type="button"
          disabled={!hasDetail}
          onClick={() => setOpen((value) => !value)}
          className="no-drag min-w-0 flex-1 text-left"
        >
          <div className="flex items-center gap-2">
            <span className="truncate text-[13px] font-medium text-ink">
              {entry.skill_name || entityTitle(entry)}
            </span>
            <Badge tone={meta.tone}>{meta.label}</Badge>
            {/* 实体操作不显类型的话，这一行就只剩一个状态徽章 —— 用户看不出刚才
                到底是"建了个群"还是"跑了一次自动化任务" */}
            {entry.kind && entry.kind !== 'skill' ? (
              <Badge tone="neutral">{KIND_LABEL[entry.kind] ?? entry.kind}</Badge>
            ) : null}
            {entry.permission_level !== 'safe' ? (
              <Badge tone="neutral">{entry.permission_level}</Badge>
            ) : null}
          </div>
          <div className="mt-0.5 text-[11px] text-ink-faint">
            {actorName ? `${actorName} · ` : ''}
            {formatTime(entry.ts)}
            {entry.duration_ms !== null ? ` · ${Math.round(entry.duration_ms)} ms` : ''}
            {entry.session_id ? ` · 会话 ${entry.session_id}` : ''}
          </div>
        </button>
      </div>

      {entry.detail && !open ? (
        <div className="mt-1 truncate text-[11.5px] text-ink-soft" title={entry.detail}>
          {entry.detail}
        </div>
      ) : null}

      {open ? (
        <div className="mt-2 space-y-2">
          {entry.params ? (
            <pre className="selectable max-h-[160px] overflow-auto rounded-[8px] border border-line bg-panel p-2 text-[11.5px] leading-relaxed whitespace-pre-wrap text-ink-soft">
              {JSON.stringify(entry.params, null, 2)}
            </pre>
          ) : null}
          {entry.detail ? (
            <div className="rounded-[8px] border border-line bg-panel p-2 text-[11.5px] whitespace-pre-wrap text-ink-soft">
              {entry.detail}
            </div>
          ) : null}
        </div>
      ) : null}
    </div>
  )
}

/**
 * 审计日志。
 *
 * 对应开发文档 10.5 节：用户必须能查清「谁在什么时候调用了什么工具、
 * 参数是什么、是否被批准」。参数在写入数据库时已脱敏，这里直接展示。
 */
export function AuditSettings() {
  const api = useAppStore((state) => state.api)
  // 搭子列表给「按搭子筛」用：条目里存的只有 actor_id，直接显示 id 等于没说
  const assistants = useAssistantStore((state) => state.assistants)

  const [entries, setEntries] = useState<AuditLogEntry[]>([])
  const [stats, setStats] = useState<AuditStats | null>(null)
  const [filter, setFilter] = useState<AuditStatus | 'all'>('all')
  const [kind, setKind] = useState<AuditKind | 'all'>('all')
  const [actor, setActor] = useState('all')
  const [range, setRange] = useState<RangeKey>('all')
  const [from, setFrom] = useState('')
  const [to, setTo] = useState('')
  const [loading, setLoading] = useState(false)
  const [available, setAvailable] = useState(true)
  const [reason, setReason] = useState<string | null>(null)
  const [confirmClear, setConfirmClear] = useState(false)

  const legacyIds = useAssistantStore((state) => state.legacyIds)
  const assistantNames = new Map(assistants.map((item) => [item.id, item.name]))
  /**
   * 把审计记录里的搭子 id 翻成名字。
   *
   * ⚠️ 必须先试**旧 id → 新 id**：内置搭子在 改过 id（office →
   * RelationBuddy），而审计日志是历史事实、我们刻意不改写它 —— 少了这一步，
   * 升级用户翻历史时会看到一串「office」，既不知道那是什么，也不知道那就是
   * 现在的 Relation Buddy。
   */
  const nameOf = (id: string): string => {
    const direct = assistantNames.get(id)
    if (direct) return direct
    const migrated = legacyIds[id]
    return (migrated && assistantNames.get(migrated)) || id
  }
  const filtering = filter !== 'all' || kind !== 'all' || actor !== 'all' || range !== 'all'

  /**
   * 当前筛了什么。
   *
   * 空结果时必须把它显示出来 —— 否则用户只会看到一片空白，然后以为"记录都没了"
   * （他刚刚才点了一堆筛选条件，但屏幕上没有任何东西提示这件事）。
   */
  const activeLabels = [
    filter === 'all' ? null : `结果：${STATUS_META[filter].label}`,
    kind === 'all' ? null : `类型：${KIND_LABEL[kind] ?? kind}`,
    actor === 'all' ? null : `搭子：${nameOf(actor)}`,
    range === 'all' ? null : `时间：${RANGES.find((item) => item.key === range)?.label}`,
  ].filter((item): item is string => Boolean(item))

  const chipClass = (active: boolean): string =>
    clsx(
      'no-drag rounded-[7px] border px-2.5 py-1 text-[12px] transition-colors',
      active
        ? 'border-brand/40 bg-brand-soft text-brand'
        : 'border-line text-ink-soft hover:text-ink',
    )

  const load = useCallback(async () => {
    if (!api) return
    setLoading(true)
    try {
      const [list, summary] = await Promise.all([
        api.getAudit({
          limit: 200,
          ...(filter === 'all' ? {} : { status: filter }),
          ...(kind === 'all' ? {} : { kind }),
          ...(actor === 'all' ? {} : { actor_id: actor }),
          ...rangeDates(range, from, to),
        }),
        api.getAuditStats(),
      ])
      setEntries(list.entries)
      setAvailable(list.available)
      setReason(list.reason ?? null)
      setStats(summary)
    } finally {
      setLoading(false)
    }
  }, [api, filter, kind, actor, range, from, to])

  const resetFilters = () => {
    setFilter('all')
    setKind('all')
    setActor('all')
    setRange('all')
    setFrom('')
    setTo('')
  }

  useEffect(() => {
    void load()
  }, [load])

  return (
    <div className="max-w-[880px]">
      <div className="flex items-start gap-4">
        <div className="flex-1">
          <h2 className="text-[15px] font-semibold text-ink">审计日志</h2>
          <p className="mt-1 text-[12.5px] leading-relaxed text-ink-soft">
            记录每一次工具调用：调用方、参数、结果与耗时。参数中的手机号、身份证号与
            API Key 在写入时已脱敏。
          </p>
        </div>
        <div className="flex gap-2">
          <Button
            icon={loading ? <Loader2 size={13} className="animate-spin" /> : <RefreshCw size={13} />}
            onClick={() => void load()}
            disabled={loading}
          >
            刷新
          </Button>
          {entries.length > 0 ? (
            <Button
              variant="ghost"
              icon={<Trash2 size={13} />}
              onClick={() => setConfirmClear(true)}
            >
              清空
            </Button>
          ) : null}
        </div>
      </div>

      {!available ? (
        <div className="mt-4 rounded-[8px] border border-warning/30 bg-warning-soft px-3 py-2 text-[12.5px] text-warning">
          {reason ?? '当前未启用审计持久化，历史记录不会保留。'}
        </div>
      ) : null}

      {stats?.available ? (
        <div className="mt-4 grid grid-cols-4 gap-2.5">
          <div className="rounded-[10px] border border-line bg-canvas px-3.5 py-3">
            <div className="text-[11.5px] text-ink-faint">总记录</div>
            <div className="mt-0.5 text-[17px] font-semibold tabular-nums text-ink">
              {stats.total}
            </div>
          </div>
          {(['ok', 'error', 'denied'] as const).map((key) => (
            <div key={key} className="rounded-[10px] border border-line bg-canvas px-3.5 py-3">
              <div className="text-[11.5px] text-ink-faint">{STATUS_META[key].label}</div>
              <div className="mt-0.5 text-[17px] font-semibold tabular-nums text-ink">
                {stats.by_status[key] ?? 0}
              </div>
            </div>
          ))}
        </div>
      ) : null}

      {/* 筛选区：结果 / 类型 / 搭子 / 时间范围。
          用户的原话是"九点半那会儿出了什么事" —— 只能从头翻列表的话，
          一次失败就得翻到尾。四类条件**可叠加**，右上角一键清空。 */}
      <div className="mt-4 rounded-[10px] border border-line bg-canvas px-3.5 py-3">
        <div className="flex flex-wrap items-center gap-x-2.5 gap-y-2">
          <span className="w-[28px] text-[11.5px] text-ink-faint">结果</span>
          {FILTERS.map((item) => (
            <button
              key={item.key}
              type="button"
              onClick={() => setFilter(item.key)}
              className={chipClass(filter === item.key)}
            >
              {item.label}
            </button>
          ))}

          <span className="ml-1.5 text-[11.5px] text-ink-faint">类型</span>
          <Select
            value={kind}
            onChange={(event) => setKind(event.target.value as AuditKind | 'all')}
            className="h-7 w-[124px] text-[12px]"
          >
            {KIND_FILTERS.map((item) => (
              <option key={item.key} value={item.key}>
                {item.label}
              </option>
            ))}
          </Select>

          <span className="ml-1.5 text-[11.5px] text-ink-faint">搭子</span>
          <Select
            value={actor}
            onChange={(event) => setActor(event.target.value)}
            className="h-7 w-[140px] text-[12px]"
          >
            <option value="all">全部搭子</option>
            {assistants.map((item) => (
              <option key={item.id} value={item.id}>
                {item.name}
              </option>
            ))}
          </Select>
        </div>

        <div className="mt-2 flex flex-wrap items-center gap-x-2.5 gap-y-2">
          <span className="w-[28px] text-[11.5px] text-ink-faint">时间</span>
          {RANGES.map((item) => (
            <button
              key={item.key}
              type="button"
              onClick={() => setRange(item.key)}
              className={chipClass(range === item.key)}
            >
              {item.label}
            </button>
          ))}
          {range === 'custom' ? (
            <>
              <Input
                type="date"
                value={from}
                onChange={(event) => setFrom(event.target.value)}
                className="h-7 w-[136px] text-[12px]"
              />
              <span className="text-[11.5px] text-ink-faint">至</span>
              <Input
                type="date"
                value={to}
                onChange={(event) => setTo(event.target.value)}
                className="h-7 w-[136px] text-[12px]"
              />
            </>
          ) : null}
          {filtering ? (
            <button
              type="button"
              onClick={resetFilters}
              className="no-drag ml-auto text-[11.5px] text-brand hover:underline"
            >
              清空筛选
            </button>
          ) : null}
        </div>
      </div>

      <div className="mt-3 divide-y divide-line-soft overflow-hidden rounded-[10px] border border-line">
        {entries.map((entry) => (
          <EntryRow
            key={entry.id}
            entry={entry}
            actorName={entry.actor_id ? nameOf(entry.actor_id) : undefined}
          />
        ))}
        {entries.length === 0 ? (
          <div className="py-10">
            {filtering ? (
              <EmptyState
                title="没有符合条件的记录"
                description={`当前筛的是 ${activeLabels.join('、')}。换个条件，或点右上角「清空筛选」看全部。`}
              />
            ) : (
              <EmptyState
                title="暂无审计记录"
                description="智能体调用工具后，这里会出现对应的记录。"
              />
            )}
          </div>
        ) : null}
      </div>

      {entries.length >= 200 ? (
        <div className="mt-2 text-[11.5px] text-ink-faint">仅展示最近 200 条记录。</div>
      ) : null}

      <Modal
        open={confirmClear}
        onClose={() => setConfirmClear(false)}
        width="max-w-md"
        title="清空审计日志"
        description="清空后将无法追溯历史操作记录。"
        footer={
          <>
            <Button onClick={() => setConfirmClear(false)}>取消</Button>
            <Button
              variant="danger"
              onClick={async () => {
                setConfirmClear(false)
                if (!api) return
                await api.clearAudit()
                await load()
              }}
            >
              清空
            </Button>
          </>
        }
      >
        <p className="text-[13px] text-ink">
          确定清空全部 {stats?.total ?? entries.length} 条审计记录吗？此操作不可撤销。
        </p>
      </Modal>
    </div>
  )
}
