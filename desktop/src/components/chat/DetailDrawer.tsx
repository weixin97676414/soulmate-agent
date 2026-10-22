import clsx from 'clsx'
import { Activity, ChevronLeft, FileStack, X } from 'lucide-react'
import { useMemo, useState } from 'react'

import { ArtifactPreview } from '@/components/chat/ArtifactPreview'
import { IconButton, Spinner } from '@/components/ui'
import { useChatStore } from '@/stores/chatStore'
import type { FileRecord, TraceData, TraceSpan } from '@/types'



















export const DRAWER_WIDTH = 280








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


function depthOf(span: TraceSpan, byId: Map<string, TraceSpan>): number {
  let depth = 0
  let current = span.parent_id
  
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

      {}
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








export function DetailDrawer({ streaming }: { streaming: boolean }) {
  const trace = useChatStore((state) => state.trace)
  const artifacts = useChatStore((state) => state.artifacts)
  const activeSessionId = useChatStore((state) => state.activeSessionId)
  const setDrawerOpen = useChatStore((state) => state.setDrawerOpen)
  const deleteArtifact = useChatStore((state) => state.deleteArtifact)
  const openTrace = useChatStore((state) => state.drawerTab)

  const [selected, setSelected] = useState<FileRecord | null>(null)

  const artifactCount = artifacts.length
  
  const defaultTab = artifactCount > 0 && !trace ? 'artifacts' : 'trace'
  const tab = openTrace ?? defaultTab

  const previewing = selected ?? null

  return (
    












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
