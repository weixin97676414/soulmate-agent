import { AlertTriangle, CalendarClock, Pencil, Play, Plus, Trash2 } from 'lucide-react'
import { useCallback, useEffect, useState } from 'react'

import {
  Badge,
  Button,
  EmptyState,
  Field,
  IconButton,
  Input,
  Modal,
  Select,
  Spinner,
  Switch,
  Textarea,
} from '@/components/ui'
import { formatFull } from '@/lib/time'
import { useAppStore } from '@/stores/appStore'
import { useAssistantStore } from '@/stores/assistantStore'
import { useNotificationStore } from '@/stores/notificationStore'
import type {
  RunRecord,
  ScheduledTask,
  ScheduledTaskDraft,
  ScheduledTaskState,
} from '@/types'














const WEEKDAYS = ['周一', '周二', '周三', '周四', '周五', '周六', '周日']

const TRIGGER_OPTIONS: Array<{ value: ScheduledTask['trigger']; label: string }> = [
  { value: 'interval', label: '每隔一段时间' },
  { value: 'daily', label: '每天' },
  { value: 'weekly', label: '每周' },
]

const CONDITION_OPTIONS: Array<{ value: ScheduledTask['condition']; label: string }> = [
  { value: 'none', label: '到点就执行' },
  { value: 'url_changed', label: '网页内容有变化才执行' },
  { value: 'file_changed', label: '文件有更新才执行' },
]








function describeSchedule(task: ScheduledTaskDraft): string {
  if (task.trigger === 'daily') return `每天 ${task.at_time}`
  if (task.trigger === 'weekly') {
    return `每${WEEKDAYS[task.weekday] ?? '周一'} ${task.at_time}`
  }
  const minutes = task.interval_minutes
  const base = minutes >= 60 && minutes % 60 === 0 ? `每 ${minutes / 60} 小时` : `每 ${minutes} 分钟`
  
  
  const start = humanStartAt(task.start_at)
  return start ? `自 ${start} 起，${base}` : base
}


function humanStartAt(raw: string): string {
  const text = (raw ?? '').trim()
  if (!text) return ''
  const match = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})$/.exec(text)
  if (!match) return ''
  const [, year, month, day, hour, minute] = match
  return `${Number(year)}年${Number(month)}月${Number(day)}日 ${hour}:${minute}`
}







function toLocalStamp(date: Date): string {
  const pad = (value: number) => String(value).padStart(2, '0')
  return (
    `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}` +
    `T${pad(date.getHours())}:${pad(date.getMinutes())}`
  )
}

function describeCondition(task: ScheduledTask): string | null {
  if (task.condition === 'url_changed') return `仅当 ${task.condition_target} 有变化时`
  if (task.condition === 'file_changed') return `仅当 ${task.condition_target} 有更新时`
  return null
}

function describeCountdown(seconds: number | null): string {
  if (seconds === null) return '尚未排期'
  if (seconds <= 0) return '马上检查'
  const minutes = Math.round(seconds / 60)
  if (minutes < 60) return `约 ${Math.max(1, minutes)} 分钟后检查`
  const hours = Math.floor(minutes / 60)
  const rest = minutes % 60
  if (hours < 24) {
    return rest > 0 ? `约 ${hours} 小时 ${rest} 分钟后检查` : `约 ${hours} 小时后检查`
  }
  return `约 ${Math.round(hours / 24)} 天后检查`
}

function formatStamp(stamp: number | null): string {
  if (!stamp) return '还没有执行过'
  return new Date(stamp * 1000).toLocaleString()
}

function blankDraft(assistantId: string): ScheduledTaskDraft {
  return {
    name: '',
    prompt: '',
    assistant_id: assistantId,
    enabled: true,
    trigger: 'daily',
    interval_minutes: 60,
    at_time: '09:00',
    weekday: 0,
    
    
    start_at: toLocalStamp(new Date(Date.now() + 60 * 60 * 1000)),
    condition: 'none',
    condition_target: '',
  }
}

function toDraft(task: ScheduledTaskState): ScheduledTaskDraft {
  const { id: _id, ...rest } = task
  return {
    name: rest.name,
    prompt: rest.prompt,
    assistant_id: rest.assistant_id,
    enabled: rest.enabled,
    trigger: rest.trigger,
    interval_minutes: rest.interval_minutes,
    at_time: rest.at_time,
    weekday: rest.weekday,
    
    
    start_at: rest.start_at ?? '',
    condition: rest.condition,
    condition_target: rest.condition_target,
  }
}

export function TasksPage() {
  const api = useAppStore((state) => state.api)
  const assistants = useAssistantStore((state) => state.assistants)
  const activeAssistantId = useAssistantStore((state) => state.activeId)
  const push = useNotificationStore((state) => state.push)

  const [items, setItems] = useState<ScheduledTaskState[]>([])
  const [loading, setLoading] = useState(true)
  const [editing, setEditing] = useState<{ id: string | null; draft: ScheduledTaskDraft } | null>(
    null,
  )
  const [pendingDelete, setPendingDelete] = useState<ScheduledTaskState | null>(null)
  const [busyId, setBusyId] = useState<string | null>(null)
  const [formBusy, setFormBusy] = useState(false)

  const load = useCallback(async () => {
    if (!api) return
    try {
      const payload = await api.getTasks()
      setItems(payload.items)
    } catch (error) {
      push({
        level: 'error',
        title: '自动化任务加载失败',
        message: error instanceof Error ? error.message : String(error),
      })
    } finally {
      setLoading(false)
    }
  }, [api, push])

  useEffect(() => {
    void load()
  }, [load])

  
  
  useEffect(() => {
    const timer = window.setInterval(() => void load(), 30_000)
    return () => window.clearInterval(timer)
  }, [load])

  const submit = async (draft: ScheduledTaskDraft) => {
    if (!api) return
    setFormBusy(true)
    try {
      if (editing?.id) {
        await api.updateTask(editing.id, draft)
        push({ level: 'success', title: '任务已更新', message: `「${draft.name}」已按新设置生效。` })
      } else {
        await api.createTask(draft)
        push({
          level: 'success',
          title: '任务已创建',
          message: `「${draft.name}」已加入调度：${describeSchedule(draft)}。`,
        })
      }
      setEditing(null)
      await load()
    } catch (error) {
      push({
        level: 'error',
        title: '保存失败',
        message: error instanceof Error ? error.message : String(error),
        autoDismissMs: 0,
      })
    } finally {
      setFormBusy(false)
    }
  }

  const toggleEnabled = async (task: ScheduledTaskState, enabled: boolean) => {
    if (!api) return
    setBusyId(task.id)
    try {
      await api.updateTask(task.id, { ...toDraft(task), enabled })
      await load()
    } catch (error) {
      push({
        level: 'error',
        title: '切换失败',
        message: error instanceof Error ? error.message : String(error),
      })
    } finally {
      setBusyId(null)
    }
  }

  const runNow = async (task: ScheduledTaskState) => {
    if (!api) return
    setBusyId(task.id)
    try {
      await api.runTask(task.id)
      push({
        level: 'info',
        title: `「${task.name}」已开始执行`,
        message: '它会在一个新会话里跑完，完成后会弹通知；结果也能在对话里看到。',
        autoDismissMs: 0,
      })
      await load()
    } catch (error) {
      push({
        level: 'warning',
        title: '没能立刻执行',
        message:
          error instanceof Error && error.message.includes('409')
            ? '它正在执行中，等这一轮跑完再点。'
            : error instanceof Error
              ? error.message
              : String(error),
      })
    } finally {
      setBusyId(null)
    }
  }

  const confirmDelete = async () => {
    const target = pendingDelete
    setPendingDelete(null)
    if (!api || !target) return
    try {
      await api.deleteTask(target.id)
      push({ level: 'success', title: '任务已删除', message: `「${target.name}」不会再自动执行。` })
      await load()
    } catch (error) {
      push({
        level: 'error',
        title: '删除失败',
        message: error instanceof Error ? error.message : String(error),
      })
    }
  }

  





  const [resumable, setResumable] = useState<RunRecord[]>([])
  const loadRuns = useCallback(async () => {
    if (!api) return
    try {
      const payload = await api.getRuns()
      setResumable(payload.runs.filter((run) => run.kind === 'task'))
    } catch {
      
      setResumable([])
    }
  }, [api])

  useEffect(() => {
    void loadRuns()
  }, [loadRuns])

  const resume = async (run: RunRecord) => {
    if (!api) return
    try {
      await api.resumeRun(run.id)
      push({ level: 'success', title: '已接着上次继续跑', message: run.summary })
      await loadRuns()
      await load()
    } catch (error) {
      push({
        level: 'error',
        title: '续跑失败',
        message: error instanceof Error ? error.message : String(error),
        autoDismissMs: 0,
      })
    }
  }

  const dismissRun = async (run: RunRecord) => {
    if (!api) return
    try {
      await api.dismissRun(run.id)
      await loadRuns()
    } catch {
      
    }
  }

  const activeCount = items.filter((item) => item.enabled).length

  return (
    <div className="flex min-w-0 flex-1 flex-col overflow-y-auto px-10 py-6">
      <div className="max-w-[860px]">
        <div className="flex items-start gap-4">
          <div className="flex-1">
            <h2 className="text-[15px] font-semibold text-ink">自动化任务</h2>
            <p className="mt-1 text-[12.5px] leading-relaxed text-ink-soft">
              到点让搭子自己干活（每次执行都会真的调用模型）。也可以直接对搭子说
              「每天早上九点帮我做一份行业早报」，它会自己建。
            </p>
            <p className="mt-1.5 text-[11.5px] leading-relaxed text-ink-faint">
              后台任务无人值守，执行时一律自动批准 —— 包括删文件、跑命令这类高危操作，
              不会弹确认框（详见左侧「安全与通用」页里的「权限确认」）。
            </p>

            {}
            {resumable.length > 0 ? (
              <div className="mt-3 space-y-1.5">
                {resumable.map((run) => (
                  <div
                    key={run.id}
                    className="flex items-start gap-2 rounded-[10px] border border-warning/30 bg-warning-soft px-3 py-2"
                  >
                    <AlertTriangle size={13} className="mt-0.5 shrink-0 text-warning" />
                    <div className="min-w-0 flex-1">
                      <div className="text-[12px] text-ink">{run.summary}</div>
                      <div className="mt-0.5 text-[11px] text-ink-faint">
                        已完成 {run.step} 步 · {formatFull(run.updated_at * 1000)}
                      </div>
                    </div>
                    <Button size="sm" variant="primary" onClick={() => void resume(run)}>
                      继续
                    </Button>
                    <Button size="sm" variant="secondary" onClick={() => void dismissRun(run)}>
                      忽略
                    </Button>
                  </div>
                ))}
              </div>
            ) : null}
          </div>
          <Button
            icon={<Plus size={14} />}
            onClick={() => setEditing({ id: null, draft: blankDraft(activeAssistantId ?? '') })}
          >
            新建任务
          </Button>
        </div>

        {items.length > 0 ? (
          <div className="mt-4 text-[12px] text-ink-faint">
            共 {items.length} 个任务，其中 {activeCount} 个已启用
          </div>
        ) : null}

        <div className="mt-3 space-y-2.5">
          {loading ? (
            <div className="flex justify-center py-10">
              <Spinner />
            </div>
          ) : items.length === 0 ? (
            <div className="py-14">
              <EmptyState
                icon={<CalendarClock size={26} />}
                title="还没有自动化任务"
                description={
                  '适合放那些"每天都要做一遍"的事：整理昨天的记录、盯一个网页有没有更新、' +
                  '按周汇总数据。它会自己开一个新会话去跑，结果随时能翻。'
                }
                action={
                  <Button
                    variant="primary"
                    icon={<Plus size={14} />}
                    onClick={() =>
                      setEditing({ id: null, draft: blankDraft(activeAssistantId ?? '') })
                    }
                  >
                    新建第一个任务
                  </Button>
                }
              />
            </div>
          ) : (
            items.map((task) => {
              const condition = describeCondition(task)
              const busy = busyId === task.id
              return (
                <div
                  key={task.id}
                  className="rounded-[10px] border border-line bg-panel px-3.5 py-3"
                >
                  <div className="flex items-start gap-3">
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-2">
                        <span className="truncate text-[13px] font-medium text-ink">
                          {task.name}
                        </span>
                        <Badge tone={task.enabled ? 'success' : 'neutral'}>
                          {task.enabled ? '已启用' : '已停用'}
                        </Badge>
                        {
}
                        {task.locked ? <Badge tone="neutral">内置</Badge> : null}
                        {task.running ? <Badge tone="brand">正在执行</Badge> : null}
                      </div>
                      <div className="mt-1 text-[12px] text-ink-soft">
                        {describeSchedule(task)}
                        {task.enabled ? (
                          <span className="text-ink-faint">
                            {' · '}
                            {task.running ? '这一轮跑完再排下一次' : describeCountdown(task.next_run_in_seconds)}
                          </span>
                        ) : null}
                      </div>
                      {condition ? (
                        <div className="mt-0.5 text-[11.5px] text-ink-faint">
                          {condition}
                          {task.condition_ready
                            ? ''
                            : '（第一次检查只记录现状，之后有变化才会执行）'}
                        </div>
                      ) : null}
                      <div className="mt-0.5 text-[11.5px] text-ink-faint">
                        上次执行：{formatStamp(task.last_run_at)}
                      </div>
                      {

}
                      {task.locked ? (
                        <div className="mt-1 text-[11.5px] leading-relaxed text-ink-faint">
                          为了你更优质的体验，内置搭子的自动化任务不支持手动修改，你可以通过与搭子协商进行调整
                        </div>
                      ) : null}
                    </div>

                    <div className="flex shrink-0 items-center gap-1">
                      <Switch
                        checked={task.enabled}
                        onChange={(value) => void toggleEnabled(task, value)}
                        label={task.enabled ? '停用' : '启用'}
                        disabled={task.locked}
                      />
                      <IconButton
                        label="立刻执行一次"
                        onClick={() => void runNow(task)}
                        disabled={busy || task.running}
                      >
                        {busy ? <Spinner /> : <Play size={15} />}
                      </IconButton>
                      <IconButton
                        label="编辑"
                        onClick={() =>
                          setEditing({ id: task.id, draft: toDraft(task) })
                        }
                        disabled={busy || task.locked}
                      >
                        <Pencil size={15} />
                      </IconButton>
                      <IconButton
                        label="删除"
                        onClick={() => setPendingDelete(task)}
                        disabled={busy || task.locked}
                      >
                        <Trash2 size={15} />
                      </IconButton>
                    </div>
                  </div>
                </div>
              )
            })
          )}
        </div>
      </div>

      <TaskFormModal
        open={editing !== null}
        initial={editing?.draft ?? null}
        isNew={editing?.id === null}
        assistantOptions={assistants.map((item) => ({ id: item.id, name: item.name }))}
        busy={formBusy}
        onClose={() => setEditing(null)}
        onSubmit={submit}
      />

      <Modal
        open={pendingDelete !== null}
        onClose={() => setPendingDelete(null)}
        title="删除自动化任务"
        width="max-w-md"
        description="删除后它的触发时间与监控基线都会一并消失，已经跑出来的会话记录不受影响。"
        footer={
          <>
            <Button onClick={() => setPendingDelete(null)}>取消</Button>
            <Button variant="danger" onClick={() => void confirmDelete()}>
              删除
            </Button>
          </>
        }
      >
        <p className="text-[12.5px] leading-relaxed text-ink-soft">
          确定要删除「{pendingDelete?.name}」吗？
        </p>
      </Modal>
    </div>
  )
}

function TaskFormModal({
  open,
  initial,
  isNew,
  assistantOptions,
  busy,
  onClose,
  onSubmit,
}: {
  open: boolean
  initial: ScheduledTaskDraft | null
  isNew: boolean
  assistantOptions: Array<{ id: string; name: string }>
  busy: boolean
  onClose: () => void
  onSubmit: (draft: ScheduledTaskDraft) => Promise<void>
}) {
  const [draft, setDraft] = useState<ScheduledTaskDraft | null>(initial)

  
  
  useEffect(() => {
    if (open) setDraft(initial)
  }, [open, initial])

  if (!open || !draft) return null

  const patch = (changes: Partial<ScheduledTaskDraft>) => setDraft({ ...draft, ...changes })

  





  const browseFile = async () => {
    const picked = await window.agentBridge.pickFile()
    if (!picked) return
    patch({ condition_target: picked })
  }
  const needsTarget = draft.condition !== 'none'
  
  
  const needsStartAt = draft.trigger === 'interval'
  const valid =
    draft.name.trim().length > 0 &&
    draft.prompt.trim().length > 0 &&
    (!needsStartAt || draft.start_at.trim().length > 0) &&
    (!needsTarget || draft.condition_target.trim().length > 0)

  return (
    <Modal
      open={open}
      onClose={onClose}
      title={isNew ? '新建自动化任务' : '编辑自动化任务'}
      description="到点后搭子会在一个新会话里执行下面这条指令；执行会消耗 token。"
      footer={
        <>
          <Button onClick={onClose} disabled={busy}>
            取消
          </Button>
          <Button
            variant="primary"
            disabled={!valid || busy}
            onClick={() => void onSubmit({ ...draft, name: draft.name.trim(), prompt: draft.prompt.trim() })}
          >
            {busy ? '保存中…' : isNew ? '创建任务' : '保存'}
          </Button>
        </>
      }
    >
      <div className="space-y-3">
        <Field label="任务名" hint="只用来在列表里区分，例如「行业早报」">
          <Input
            value={draft.name}
            maxLength={48}
            placeholder="行业早报"
            onChange={(event) => patch({ name: event.target.value })}
          />
        </Field>

        <Field
          label="执行指令"
          hint="每次执行时原样交给搭子的指令。要写得能独立完成 —— 它开的是新会话，看不到你现在的对话。"
        >
          <Textarea
            rows={3}
            value={draft.prompt}
            placeholder="搜索今天 AI 行业的要闻，挑 5 条写成一页简报，附上来源链接。"
            onChange={(event) => patch({ prompt: event.target.value })}
          />
        </Field>

        <div className="grid grid-cols-2 gap-3">
          <Field label="什么时候执行">
            <Select
              value={draft.trigger}
              onChange={(event) =>
                patch({ trigger: event.target.value as ScheduledTaskDraft['trigger'] })
              }
            >
              {TRIGGER_OPTIONS.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </Select>
          </Field>

          {draft.trigger === 'interval' ? (
            <Field label="间隔（分钟）" hint="最少 1 分钟，建议 30 分钟以上；上限 30 天">
              <Input
                type="number"
                min={1}
                max={43200}
                value={draft.interval_minutes}
                onChange={(event) =>
                  patch({ interval_minutes: Number(event.target.value) || 1 })
                }
              />
            </Field>
          ) : (
            <Field label="时刻" hint="按本机时间（24 小时制）">
              <Input
                type="time"
                value={draft.at_time}
                onChange={(event) => patch({ at_time: event.target.value || '09:00' })}
              />
            </Field>
          )}
        </div>

        {draft.trigger === 'interval' ? (
          <Field
            label="起始时间"
            hint="从这一刻开始计时，之后每隔上面那个分钟数跑一次；到这一刻之前一次都不会跑（按本机时间）"
          >
            <Input
              type="datetime-local"
              value={draft.start_at}
              onChange={(event) => patch({ start_at: event.target.value })}
            />
          </Field>
        ) : null}

        {draft.trigger === 'weekly' ? (
          <Field label="星期几">
            <Select
              value={String(draft.weekday)}
              onChange={(event) => patch({ weekday: Number(event.target.value) })}
            >
              {WEEKDAYS.map((label, index) => (
                <option key={label} value={index}>
                  {label}
                </option>
              ))}
            </Select>
          </Field>
        ) : null}

        <Field
          label="执行条件"
          hint="选了条件后，到点只是「看一眼」：由核心每隔一段时间（默认每分钟）自动比一次，内容没变就不执行、也不花钱。第一次检查只记录现状；变化的内容不会发给搭子，它只是「放行」的开关。"
        >
          <Select
            value={draft.condition}
            onChange={(event) =>
              patch({ condition: event.target.value as ScheduledTaskDraft['condition'] })
            }
          >
            {CONDITION_OPTIONS.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </Select>
        </Field>

        {needsTarget ? (
          <Field
            label={draft.condition === 'url_changed' ? '要盯的网页地址' : '要盯的文件路径'}
            hint={
              draft.condition === 'url_changed'
                ? 'http/https 地址。核心会把整页内容比一遍，有任何变化（包含改版）都算一次变化'
                : '点「浏览…」挑一个文件，或者直接把完整路径粘进来（例如 D:\\报告\\月度.xlsx）'
            }
          >
            <div className="flex items-center gap-2">
              <div className="min-w-0 flex-1">
                <Input
                  value={draft.condition_target}
                  placeholder={
                    draft.condition === 'url_changed'
                      ? 'https://example.com/news'
                      : 'D:\\报告\\月度.xlsx'
                  }
                  onChange={(event) => patch({ condition_target: event.target.value })}
                />
              </div>
              {}
              {draft.condition === 'file_changed' ? (
                <Button variant="secondary" onClick={() => void browseFile()}>
                  浏览…
                </Button>
              ) : null}
            </div>
          </Field>
        ) : null}

        <Field label="用哪个搭子跑" hint="留空则用默认配置；群里的搭子也可以指定">
          <Select
            value={draft.assistant_id}
            onChange={(event) => patch({ assistant_id: event.target.value })}
          >
            <option value="">默认配置</option>
            {assistantOptions.map((item) => (
              <option key={item.id} value={item.id}>
                {item.name}
              </option>
            ))}
          </Select>
        </Field>

        <label className="flex items-center gap-3 text-[12.5px] text-ink-soft">
          <Switch
            checked={draft.enabled}
            onChange={(enabled) => patch({ enabled })}
            label="创建后立即启用"
          />
          创建后立即启用（关掉的话它会留在列表里但不跑）
        </label>
      </div>
    </Modal>
  )
}
