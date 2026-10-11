import clsx from 'clsx'
import { Activity, ChevronLeft, FileStack, X } from 'lucide-react'
import { useMemo, useState } from 'react'

import { ArtifactPreview } from '@/components/chat/ArtifactPreview'
import { IconButton, Spinner } from '@/components/ui'
import { useChatStore } from '@/stores/chatStore'
import type { FileRecord, TraceData, TraceSpan } from '@/types'

/**
 * 「链路与产物」这一列的宽度（px）。
 *
 * ## ⚠️ 这个常量是**两个地方的唯一来源**
 *
 * - 本组件用它当自己的宽度（`style={{ width: DRAWER_WIDTH }}`）；
 * - `ChatView` 打开抽屉时按 **`DRAWER_WIDTH + DRAWER_GAP`** 把**窗口整体加宽**。
 *
 * 之所以必须共用同一个常量：这一列不是从对话栏身上抠出来的，而是**窗口向外
 * 长出来的一块**。窗口只加宽 480、而列实际占 550（旧版是 `min(560px,46vw)`），
 * 差的那 70 多像素就必然从对话栏里挤 —— 用户看到的"还是往左压缩了一点"就是它，
 * 而且**窗口越宽差得越多**（vw 随窗口变，加宽量是定值）。
 *
 * 所以这里刻意用**固定像素**而不是 vw / 百分比：只有定值才能和加宽量恒等。
 *
 * 宽度取 280 是指定的（"它自己过宽，要窄些，现在的一半即可"）——
 * 原先的 `min(560px,46vw)` 在宽屏上接近 560，占掉了大半个对话区。
 */
export const DRAWER_WIDTH = 280

/**
 * 抽屉列与对话列之间的间距（px）。
 *
 * ⚠️ 必须与 `ChatView` 根元素上的 `gap-2` 保持一致（Tailwind 的 `gap-2` = 8px）。
 * 加宽量要把它一起算进去，否则窗口会少加 8px、对话栏被压 8px —— 单看只有一条
 * 细缝，但它是"差一点没对齐"的来源，而且越攒越多。
 */
export const DRAWER_GAP = 3

const SPAN_LABELS: Record<string, string> = {
  step: '模型推理',
  skill: '工具执行',
}

function describeSpan(name: string): { title: string; hint?: string } {
  const [prefix, rest] = name.split(':')
  const label = SPAN_LABELS[prefix]
  if (label && rest) return { title: `${label} · ${rest}`, hint: name }
  return { title: name }
}

function formatDuration(ms: number): string {
  if (ms >= 1000) return `${(ms / 1000).toFixed(2)}s`
  return `${Math.round(ms)}ms`
}

/** 按 parent_id 算嵌套深度，用来做缩进 */
function depthOf(span: TraceSpan, byId: Map<string, TraceSpan>): number {
  let depth = 0
  let current = span.parent_id
  // 防御性上限：脏数据可能形成环，不能让它把界面卡死
  while (current && depth < 8) {
    const parent = byId.get(current)
    if (!parent) break
    depth += 1
    current = parent.parent_id
  }
  return depth
}

function TimelineRow({
  span,
  depth,
  totalMs,
}: {
  span: TraceSpan
  depth: number
  totalMs: number
}) {
  const { title, hint } = describeSpan(span.name)
  const scale = totalMs > 0 ? totalMs : 1
  // 起止偏移由后端给出；缺失时退化成"从 0 开始"，仍然能看时长
  const start = span.start_ms ?? 0
  const left = Math.min((start / scale) * 100, 100)
  const width = Math.max((span.duration_ms / scale) * 100, 0.8)

  return (
    <div className="px-3 py-1.5" style={{ paddingLeft: 12 + depth * 12 }}>
      <div className="flex items-baseline gap-2">
        <span
          className={clsx(
            'h-[6px] w-[6px] shrink-0 rounded-full',
            span.status === 'error'
              ? 'bg-danger'
              : span.status === 'running'
                ? 'bg-brand'
                : 'bg-success',
          )}
        />
        <span className="min-w-0 flex-1 truncate text-[12px] text-ink" title={hint}>
          {title}
        </span>
        <span className="shrink-0 text-[11px] tabular-nums text-ink-faint">
          {formatDuration(span.duration_ms)}
        </span>
      </div>

      {/* 条形按真实起止位置摆放，能看出并发与嵌套；只给 duration 是排不出先后的 */}
      <div className="relative mt-1 ml-[14px] h-[4px] rounded-full bg-line-soft">
        <div
          className={clsx(
            'absolute h-full rounded-full',
            span.status === 'error'
              ? 'bg-danger/70'
              : span.status === 'running'
                ? 'bg-brand/70'
                : 'bg-success/60',
          )}
          style={{ left: `${left}%`, width: `${Math.min(width, 100 - left)}%` }}
        />
      </div>

      {span.error ? (
        <div className="mt-1 ml-[14px] text-[11px] leading-relaxed whitespace-pre-wrap text-danger">
          {span.error}
        </div>
      ) : null}
    </div>
  )
}

function TracePanel({ trace, streaming }: { trace: TraceData; streaming: boolean }) {
  const rows = useMemo(() => {
    const map = new Map(trace.spans.map((span) => [span.span_id, span]))
    return trace.spans.map((span) => ({ span, depth: depthOf(span, map) }))
  }, [trace])

  return (
    <>
      <div className="grid shrink-0 grid-cols-3 gap-2 border-b border-line px-3 py-2.5">
        <div>
          <div className="text-[10.5px] text-ink-faint">总耗时</div>
          <div className="text-[13px] font-medium tabular-nums text-ink">
            {formatDuration(trace.total_duration_ms)}
          </div>
        </div>
        <div>
          <div className="text-[10.5px] text-ink-faint">Tokens</div>
          <div className="text-[13px] font-medium tabular-nums text-ink">
            {trace.total_tokens}
          </div>
        </div>
        <div>
          <div className="text-[10.5px] text-ink-faint">输入 / 输出</div>
          <div className="text-[13px] font-medium tabular-nums text-ink">
            {trace.prompt_tokens}/{trace.completion_tokens}
          </div>
        </div>
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto py-1">
        {trace.spans.length === 0 ? (
          <div className="px-3 py-6 text-center text-[12px] text-ink-faint">
            {streaming ? '正在执行…' : '暂无链路数据'}
          </div>
        ) : (
          rows.map(({ span, depth }) => (
            <TimelineRow
              key={span.span_id || span.name}
              span={span}
              depth={depth}
              // total_duration_ms 是墙钟时间，所有 span 的条形共用同一把尺子
              totalMs={trace.total_duration_ms}
            />
          ))
        )}
      </div>
    </>
  )
}

function ArtifactList({
  files,
  selectedId,
  onSelect,
  currentSessionId,
  onDelete,
}: {
  files: FileRecord[]
  selectedId: string | null
  onSelect: (file: FileRecord) => void
  currentSessionId: string | null
  onDelete: (file: FileRecord) => void
}) {
  const { own, others } = useMemo(() => {
    if (!currentSessionId) return { own: files, others: [] as FileRecord[] }
    return {
      own: files.filter((item) => item.session_id === currentSessionId),
      others: files.filter((item) => item.session_id !== currentSessionId),
    }
  }, [files, currentSessionId])

  if (files.length === 0) {
    return (
      <div className="px-4 py-8 text-center text-[12px] leading-relaxed text-ink-faint">
        还没有产物。
        <br />
        让助手生成图表或报告后，文件会出现在这里。
      </div>
    )
  }

  const renderGroup = (label: string | null, items: FileRecord[]) =>
    items.length > 0 ? (
      <div>
        {label ? (
          <div className="px-3 pt-2 pb-1 text-[11px] font-medium text-ink-faint">{label}</div>
        ) : null}
        {items.map((file) => (
          <div
            key={file.id}
            className={clsx(
              'group flex items-center gap-2 px-3 py-1.5',
              selectedId === file.id ? 'bg-brand-soft' : 'hover:bg-hover',
            )}
          >
            <button
              type="button"
              onClick={() => onSelect(file)}
              className="no-drag min-w-0 flex-1 text-left"
            >
              <div
                className={clsx(
                  'truncate text-[12px]',
                  selectedId === file.id ? 'text-brand' : 'text-ink',
                )}
                title={file.original_name}
              >
                {file.original_name}
              </div>
              {file.note ? (
                <div className="truncate text-[11px] text-ink-faint">{file.note}</div>
              ) : null}
            </button>
            <button
              type="button"
              onClick={() => onDelete(file)}
              title="删除产物"
              aria-label="删除产物"
              className="no-drag shrink-0 text-[11px] text-ink-faint opacity-0 transition-opacity group-hover:opacity-100 hover:text-danger"
            >
              删除
            </button>
          </div>
        ))}
      </div>
    ) : null

  return (
    <>
      {renderGroup(currentSessionId && others.length > 0 ? '本次会话' : null, own)}
      {renderGroup('其他产物', others)}
    </>
  )
}

/**
 * 右侧抽屉：执行链路 + 产物。
 *
 * 对应客户端计划的「右侧抽屉：本次任务完整 Trace 时间线 + 产物列表」。
 * 出问题时这里能直接回答"模型看到了什么、调用了什么、花了多少 token、
 * 产出了哪些文件"。
 */
export function DetailDrawer({ streaming }: { streaming: boolean }) {
  const trace = useChatStore((state) => state.trace)
  const artifacts = useChatStore((state) => state.artifacts)
  const activeSessionId = useChatStore((state) => state.activeSessionId)
  const setDrawerOpen = useChatStore((state) => state.setDrawerOpen)
  const deleteArtifact = useChatStore((state) => state.deleteArtifact)
  const openTrace = useChatStore((state) => state.drawerTab)

  const [selected, setSelected] = useState<FileRecord | null>(null)

  const artifactCount = artifacts.length
  // 有产物、没链路时默认落到产物页，省得用户再点一下
  const defaultTab = artifactCount > 0 && !trace ? 'artifacts' : 'trace'
  const tab = openTrace ?? defaultTab

  const previewing = selected ?? null

  return (
    /*
      ⚠️ 它是一个**独立卡片容器**（产品要求："以一个单独容器呈现，
      和最开始的页面还是相同的，也就是和搭子列表等那样类似的一个新页面容器"）。

      所以根上要有和左侧那几栏**一模一样的**规格：`rounded-[12px]` + `border-line`
      + `bg-panel` + `overflow-hidden`。原来只有一条 `border-l`，读起来像"对话卡片
      被劈开了右半"，而不是"多出来一个新面板"。

      ⚠️ 宽度走 `DRAWER_WIDTH` 常量、**不用 vw**：这一列是"窗口向外长出来的一块"，
      打开时窗口会按同一个常量加宽。用 `46vw` 这类相对单位的话，实际宽度随窗口变
      而加宽量是定值，两者必然对不上 —— 差多少就从对话栏里抠多少
      实测反馈"还是往左压缩了一点"正是这么来的）。
    */
    <aside
      className="flex shrink-0 flex-col overflow-hidden rounded-[12px] border border-line bg-panel"
      style={{ width: DRAWER_WIDTH }}
    >
      <header className="flex h-11 shrink-0 items-center gap-1 border-b border-line px-3">
        {previewing ? (
          <IconButton label="返回产物列表" onClick={() => setSelected(null)}>
            <ChevronLeft size={16} />
          </IconButton>
        ) : null}
        <span className="text-[12.5px] font-medium text-ink">
          {previewing ? '产物预览' : '任务详情'}
        </span>
        {streaming && !previewing ? <Spinner className="h-3 w-3 text-brand" /> : null}
        <div className="flex-1" />

        {!previewing ? (
          <div className="flex items-center gap-0.5 rounded-[8px] bg-canvas p-0.5">
            <button
              type="button"
              onClick={() => useChatStore.getState().setDrawerTab('trace')}
              className={clsx(
                'no-drag flex h-6 items-center gap-1 rounded-[6px] px-2 text-[11.5px] transition-colors',
                tab === 'trace' ? 'bg-panel text-ink shadow-[0_1px_2px_rgba(0,0,0,0.06)]' : 'text-ink-soft hover:text-ink',
              )}
            >
              <Activity size={12} />
              链路
            </button>
            <button
              type="button"
              onClick={() => useChatStore.getState().setDrawerTab('artifacts')}
              className={clsx(
                'no-drag flex h-6 items-center gap-1 rounded-[6px] px-2 text-[11.5px] transition-colors',
                tab === 'artifacts' ? 'bg-panel text-ink shadow-[0_1px_2px_rgba(0,0,0,0.06)]' : 'text-ink-soft hover:text-ink',
              )}
            >
              <FileStack size={12} />
              产物
              {artifactCount > 0 ? (
                <span className="rounded-full bg-brand-soft px-1 text-[10px] text-brand">
                  {artifactCount}
                </span>
              ) : null}
            </button>
          </div>
        ) : null}

        <IconButton label="收起" onClick={() => setDrawerOpen(false)}>
          <X size={15} />
        </IconButton>
      </header>

      {previewing ? (
        <div className="min-h-0 flex-1">
          <ArtifactPreview file={previewing} />
        </div>
      ) : tab === 'artifacts' ? (
        <div className="min-h-0 flex-1 overflow-y-auto py-1">
          <ArtifactList
            files={artifacts}
            selectedId={selected?.id ?? null}
            onSelect={setSelected}
            currentSessionId={activeSessionId}
            onDelete={(file) => {
              void deleteArtifact(file.id)
              if (selected?.id === file.id) setSelected(null)
            }}
          />
        </div>
      ) : trace ? (
        <TracePanel trace={trace} streaming={streaming} />
      ) : (
        <div className="flex min-h-0 flex-1 items-center justify-center px-6 text-center text-[12px] leading-relaxed text-ink-faint">
          发送一条消息后，这里会显示本次任务的完整执行链路。
        </div>
      )}
    </aside>
  )
}
