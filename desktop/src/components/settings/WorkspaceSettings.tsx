import clsx from 'clsx'
import { FolderOpen, Loader2, RefreshCw, Trash2, Eraser } from 'lucide-react'
import { useCallback, useEffect, useState } from 'react'

import { Badge, Button, EmptyState, Modal } from '@/components/ui'
import { formatDateTime } from '@/lib/format'
import { useAppStore } from '@/stores/appStore'
import type { FileRecord, WorkspaceStats } from '@/types'

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  if (bytes < 1024 * 1024 * 1024) return `${(bytes / 1024 / 1024).toFixed(1)} MB`
  return `${(bytes / 1024 / 1024 / 1024).toFixed(2)} GB`
}

/**
 * 时间列：交给 `lib/format`（第 92 批，M-36 改用 `Intl`）。
 *
 * ⚠️ 保留的**只有那个 `—` 兜底**，而且它是**页面口径**、不是格式问题：
 * 早前的记录可能没有时间戳，那时显示破折号远比显示 1970 年好。
 */
const formatTime = (seconds: number): string => (seconds ? formatDateTime(seconds) : '—')

function StatCard({ label, value, hint }: { label: string; value: string; hint?: string }) {
  return (
    <div className="rounded-[10px] border border-line bg-canvas px-3.5 py-3">
      <div className="text-[11.5px] text-ink-faint">{label}</div>
      <div className="mt-0.5 text-[17px] font-semibold tabular-nums text-ink">{value}</div>
      {hint ? <div className="mt-0.5 text-[11px] text-ink-faint">{hint}</div> : null}
    </div>
  )
}

export function WorkspaceSettings() {
  const api = useAppStore((state) => state.api)
  const paths = useAppStore((state) => state.paths)

  const [files, setFiles] = useState<FileRecord[]>([])
  const [stats, setStats] = useState<WorkspaceStats | null>(null)
  const [tab, setTab] = useState<'upload' | 'artifact'>('upload')
  const [loading, setLoading] = useState(false)
  const [confirmClear, setConfirmClear] = useState(false)

  const load = useCallback(async () => {
    if (!api) return
    setLoading(true)
    try {
      const payload = await api.getFiles()
      setFiles(payload.files)
      setStats(payload.stats)
    } finally {
      setLoading(false)
    }
  }, [api])

  useEffect(() => {
    void load()
  }, [load])

  const visible = files.filter((file) => file.kind === tab)

  return (
    <div className="max-w-[880px]">
      <div className="flex items-start gap-4">
        <div className="flex-1">
          <h2 className="text-[15px] font-semibold text-ink">工作区与产物</h2>
          <p className="mt-1 text-[12.5px] leading-relaxed text-ink-soft">
            上传的附件会保存到工作区目录，技能产生的文件（报告、图表等）会归档到产物目录。
            这两个目录都在文件访问白名单的推荐范围内。
          </p>
        </div>
        <div className="flex gap-2">
          <Button
            icon={loading ? <Loader2 size={13} className="animate-spin" /> : <RefreshCw size={13} />}
            onClick={() => void load()}
            disabled={loading}
          >
            刷新目录
          </Button>
          <Button
            icon={<FolderOpen size={13} />}
            onClick={() =>
              paths &&
              void window.agentBridge.openPath(
                tab === 'upload' ? paths.workspace : paths.artifacts,
              )
            }
          >
            打开目录
          </Button>
        </div>
      </div>

      <div className="mt-4 grid grid-cols-4 gap-2.5">
        <StatCard label="文件总数" value={String(stats?.total ?? 0)} />
        <StatCard label="附件" value={String(stats?.uploads ?? 0)} />
        <StatCard label="产物" value={String(stats?.artifacts ?? 0)} />
        <StatCard label="占用空间" value={formatSize(stats?.total_bytes ?? 0)} />
      </div>

      <div className="mt-5 flex items-center gap-2">
        {(
          [
            ['upload', '附件'],
            ['artifact', '产物'],
          ] as const
        ).map(([key, label]) => (
          <button
            key={key}
            type="button"
            onClick={() => setTab(key)}
            className={clsx(
              'no-drag rounded-[7px] border px-2.5 py-1 text-[12px] transition-colors',
              tab === key
                ? 'border-brand/40 bg-brand-soft text-brand'
                : 'border-line text-ink-soft hover:text-ink',
            )}
          >
            {label}
          </button>
        ))}

        <div className="flex-1" />

        {visible.length > 0 ? (
          <Button
            size="sm"
            variant="ghost"
            icon={<Eraser size={13} />}
            onClick={() => setConfirmClear(true)}
          >
            清空{tab === 'upload' ? '附件' : '产物'}
          </Button>
        ) : null}
      </div>

      <div className="mt-3 divide-y divide-line-soft overflow-hidden rounded-[10px] border border-line">
        {visible.map((file) => (
          <div key={file.id} className="flex items-center gap-3 px-3.5 py-2.5">
            <div className="min-w-0 flex-1">
              <div className="flex items-center gap-2">
                <span className="truncate text-[13px] text-ink" title={file.original_name}>
                  {file.original_name}
                </span>
                {file.mime ? <Badge tone="neutral">{file.mime.split('/').pop()}</Badge> : null}
              </div>
              <div className="mt-0.5 text-[11px] text-ink-faint">
                {formatSize(file.size)} · {formatTime(file.created_at)}
                {file.note ? ` · ${file.note}` : ''}
              </div>
            </div>

            <button
              type="button"
              onClick={async () => {
                if (!api) return
                await api.deleteFile(file.id, file.kind)
                await load()
              }}
              className="no-drag flex h-7 w-7 shrink-0 items-center justify-center rounded-[7px] text-ink-faint hover:bg-danger-soft hover:text-danger"
              aria-label={`删除 ${file.original_name}`}
            >
              <Trash2 size={14} />
            </button>
          </div>
        ))}

        {visible.length === 0 ? (
          <div className="py-10">
            <EmptyState
              title={tab === 'upload' ? '还没有上传任何附件' : '还没有生成任何产物'}
              description={
                tab === 'upload'
                  ? '在对话输入框点回形针，或直接把文件拖进去。'
                  : '技能生成报告、图表等文件后会自动出现在这里。'
              }
            />
          </div>
        ) : null}
      </div>

      <Modal
        open={confirmClear}
        onClose={() => setConfirmClear(false)}
        width="max-w-md"
        title={`清空${tab === 'upload' ? '附件' : '产物'}`}
        description="文件将从磁盘删除，且无法恢复。"
        footer={
          <>
            <Button onClick={() => setConfirmClear(false)}>取消</Button>
            <Button
              variant="danger"
              onClick={async () => {
                setConfirmClear(false)
                if (!api) return
                await api.clearFiles(tab)
                await load()
              }}
            >
              清空
            </Button>
          </>
        }
      >
        <p className="text-[13px] text-ink">
          将删除 {visible.length} 个文件，占用 {formatSize(visible.reduce((sum, f) => sum + f.size, 0))}。
        </p>
      </Modal>
    </div>
  )
}
