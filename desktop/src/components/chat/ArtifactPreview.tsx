import { AlertTriangle, Download, Loader2 } from 'lucide-react'
import { useCallback, useEffect, useMemo, useState } from 'react'

import { Markdown } from '@/components/chat/Markdown'
import { Button, Spinner } from '@/components/ui'
import { useAppStore } from '@/stores/appStore'
import { useNotificationStore } from '@/stores/notificationStore'
import type { ArtifactPreview as PreviewData, FileRecord, TableSheet } from '@/types'

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`
}

/**
 * 图片与 SVG 用 blob URL 渲染。
 *
 * 不直接把 SVG 文本塞进 innerHTML：那等于把上传的文件当 HTML 执行，
 * 一个带 <script> 的 SVG 就能拿到 preload 暴露的 IPC 桥。
 * 走 `<img>` 的话浏览器不会执行其中的脚本。
 */
function ImagePreview({ file, kind }: { file: FileRecord; kind: 'upload' | 'artifact' }) {
  const api = useAppStore((state) => state.api)
  const [url, setUrl] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let revoked: string | null = null
    let cancelled = false

    void (async () => {
      if (!api) return
      try {
        const blob = await api.fetchFileBlob(file.id, kind)
        if (cancelled) return
        const objectUrl = URL.createObjectURL(blob)
        revoked = objectUrl
        setUrl(objectUrl)
      } catch (exc) {
        if (!cancelled) {
          setError(exc instanceof Error ? exc.message : String(exc))
        }
      }
    })()

    return () => {
      cancelled = true
      if (revoked) URL.revokeObjectURL(revoked)
    }
  }, [api, file.id, kind])

  if (error) {
    return <div className="px-3 py-8 text-center text-[12px] text-danger">{error}</div>
  }
  if (!url) {
    return (
      <div className="flex items-center justify-center px-3 py-10">
        <Spinner className="h-4 w-4 text-brand" />
      </div>
    )
  }

  return (
    <div className="flex justify-center bg-canvas p-3">
      {/* 图表是 SVG，需要撑满宽度才能看清；照片类则限制高度避免撑爆布局 */}
      <img
        src={url}
        alt={file.original_name}
        className="max-h-[440px] max-w-full rounded-[8px] bg-white object-contain"
      />
    </div>
  )
}

function SheetTable({ sheet }: { sheet: TableSheet }) {
  return (
    <div className="flex min-h-0 flex-col">
      <div className="flex items-center gap-2 border-b border-line-soft px-3 py-1.5">
        <span className="text-[12px] font-medium text-ink">{sheet.name}</span>
        <span className="text-[11px] text-ink-faint">
          {sheet.total_rows} 行
          {sheet.truncated ? `（仅预览前 ${sheet.rows.length} 行）` : ''}
        </span>
      </div>
      <div className="min-h-0 flex-1 overflow-auto">
        <table className="w-full border-collapse text-[11.5px]">
          <thead className="sticky top-0 bg-panel">
            <tr>
              {sheet.columns.map((column, index) => (
                <th
                  key={`${column}-${index}`}
                  className="border-b border-line px-2 py-1.5 text-left font-medium whitespace-nowrap text-ink-soft"
                >
                  {column || `列${index + 1}`}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {sheet.rows.map((row, rowIndex) => (
              <tr key={rowIndex} className="odd:bg-canvas even:bg-panel/40">
                {sheet.columns.map((_, cellIndex) => (
                  <td
                    key={cellIndex}
                    className="max-w-[220px] truncate border-b border-line-soft px-2 py-1 text-ink"
                    title={String(row[cellIndex] ?? '')}
                  >
                    {row[cellIndex] === null || row[cellIndex] === undefined
                      ? ''
                      : String(row[cellIndex])}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

export function ArtifactPreview({
  file,
  kind = 'artifact',
}: {
  file: FileRecord
  kind?: 'upload' | 'artifact'
}) {
  const api = useAppStore((state) => state.api)
  const [data, setData] = useState<PreviewData | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const [sheetIndex, setSheetIndex] = useState(0)
  const [saving, setSaving] = useState(false)

  /**
   * 「另存为」：交给**主进程**弹系统对话框并落盘。
   *
   * 渲染层只说清"要存哪一个"，不给也不拿本地路径（见 shared/bridge.ts 的说明）。
   * 三条分支的处理口径：
   * - 用户取消 → **什么都不做**，不报错（取消不是失败）；
   * - 成功 → 说清保存到了哪里（否则用户不知道去哪儿找那个文件）；
   * - 失败 → 把原因原样说出来，不吞。
   */
  const saveAs = useCallback(async () => {
    const bridge = window.agentBridge
    if (!bridge?.saveArtifactAs) {
      // 桥不可用（极少数环境）时必须明说，否则就是"点了没反应"
      useNotificationStore.getState().push({
        level: 'warning',
        title: '当前窗口不支持另存为',
        message: '请回到主窗口，从产物列表里另存这个文件。',
      })
      return
    }
    setSaving(true)
    try {
      const result = await bridge.saveArtifactAs({
        fileId: file.id,
        kind,
        suggestedName: file.original_name || file.id,
        mime: file.mime ?? undefined,
      })
      if (result.ok) {
        useNotificationStore.getState().push({
          level: 'info',
          title: '已保存',
          message: result.path ? `文件已保存到：${result.path}` : '文件已保存。',
          autoDismissMs: 8000,
        })
      } else if (!result.cancelled) {
        useNotificationStore.getState().push({
          level: 'error',
          title: '另存为失败',
          message: result.error || '未知原因，请重试。',
        })
      }
    } catch (exc) {
      useNotificationStore.getState().push({
        level: 'error',
        title: '另存为失败',
        message: exc instanceof Error ? exc.message : String(exc),
      })
    } finally {
      setSaving(false)
    }
  }, [file.id, file.original_name, file.mime, kind])

  useEffect(() => {
    let cancelled = false
    setData(null)
    setError(null)
    setSheetIndex(0)

    void (async () => {
      if (!api) return
      setLoading(true)
      try {
        const preview = await api.previewFile(file.id, kind)
        if (!cancelled) setData(preview)
      } catch (exc) {
        if (!cancelled) setError(exc instanceof Error ? exc.message : String(exc))
      } finally {
        if (!cancelled) setLoading(false)
      }
    })()

    return () => {
      cancelled = true
    }
  }, [api, file.id, kind])

  const header = useMemo(
    () => (
      <div className="flex shrink-0 items-center gap-2 border-b border-line px-3 py-2">
        <span className="min-w-0 flex-1 truncate text-[12.5px] text-ink" title={file.original_name}>
          {file.original_name}
        </span>
        <span className="shrink-0 text-[11px] text-ink-faint">{formatSize(file.size)}</span>
        <Button
          icon={saving ? <Loader2 size={12} className="animate-spin" /> : <Download size={12} />}
          className="h-6 px-2 text-[11.5px]"
          disabled={saving}
          onClick={() => void saveAs()}
        >
          另存为
        </Button>
      </div>
    ),
    [file, saving, saveAs],
  )

  if (loading) {
    return (
      <div className="flex h-full flex-col">
        {header}
        <div className="flex flex-1 items-center justify-center">
          <Loader2 size={16} className="animate-spin text-ink-faint" />
        </div>
      </div>
    )
  }

  if (error || !data) {
    return (
      <div className="flex h-full flex-col">
        {header}
        <div className="flex flex-1 items-center justify-center px-4 text-center text-[12px] text-danger">
          {error ?? '预览不可用'}
        </div>
      </div>
    )
  }

  return (
    <div className="flex h-full min-h-0 flex-col">
      {header}

      {data.kind === 'unsupported' ? (
        <div className="flex flex-1 flex-col items-center justify-center gap-2 px-6 text-center">
          <AlertTriangle size={16} className="text-warning" />
          <div className="text-[12.5px] leading-relaxed text-ink-soft">{data.reason}</div>
        </div>
      ) : null}

      {data.kind === 'image' || data.kind === 'svg' ? (
        <div className="min-h-0 flex-1 overflow-auto">
          <ImagePreview file={file} kind={kind} />
        </div>
      ) : null}

      {data.kind === 'markdown' ? (
        <div className="min-h-0 flex-1 overflow-auto px-4 py-3">
          <Markdown content={data.content} />
        </div>
      ) : null}

      {data.kind === 'text' ? (
        <pre className="min-h-0 flex-1 overflow-auto px-3 py-2 text-[11.5px] leading-relaxed whitespace-pre-wrap text-ink-soft">
          {data.content}
        </pre>
      ) : null}

      {data.kind === 'json' ? (
        <pre className="min-h-0 flex-1 overflow-auto px-3 py-2 font-mono text-[11.5px] leading-relaxed text-ink-soft">
          {data.content}
        </pre>
      ) : null}

      {data.kind === 'table' ? (
        <div className="flex min-h-0 flex-1 flex-col">
          {data.sheets.length > 1 ? (
            <div className="flex shrink-0 gap-1 border-b border-line px-3 py-1.5">
              {data.sheets.map((sheet, index) => (
                <button
                  key={sheet.name}
                  type="button"
                  onClick={() => setSheetIndex(index)}
                  className={`no-drag rounded-[6px] px-2 py-0.5 text-[11.5px] ${
                    index === sheetIndex
                      ? 'bg-brand-soft text-brand'
                      : 'text-ink-soft hover:bg-hover'
                  }`}
                >
                  {sheet.name}
                </button>
              ))}
            </div>
          ) : null}
          {data.sheets.length === 0 ? (
            <div className="flex flex-1 items-center justify-center text-[12px] text-ink-faint">
              {data.note ?? '没有可预览的数据'}
            </div>
          ) : (
            <SheetTable sheet={data.sheets[Math.min(sheetIndex, data.sheets.length - 1)]} />
          )}
        </div>
      ) : null}
    </div>
  )
}
