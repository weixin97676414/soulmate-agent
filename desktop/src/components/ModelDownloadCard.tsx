import clsx from 'clsx'
import { AlertTriangle, Check, Download, Loader2, RefreshCw, X } from 'lucide-react'
import type { ReactNode } from 'react'
import { useEffect } from 'react'

import { Badge, Button, Spinner } from '@/components/ui'
import { useModelHubStore } from '@/stores/modelHubStore'
import type { ModelHubEntry } from '@/types'




























export function formatBytes(bytes: number): string {
  if (!Number.isFinite(bytes) || bytes <= 0) return '0 MB'
  const mb = bytes / 1024 / 1024
  if (mb >= 1024) return `${(mb / 1024).toFixed(2)} GB`
  return `${mb >= 100 ? mb.toFixed(0) : mb.toFixed(1)} MB`
}

export function formatSpeed(bytesPerSecond: number): string {
  if (!Number.isFinite(bytesPerSecond) || bytesPerSecond <= 0) return ''
  const kb = bytesPerSecond / 1024
  if (kb < 1024) return `${kb.toFixed(0)} KB/s`
  return `${(kb / 1024).toFixed(1)} MB/s`
}


function verifyFailureText(result: { reason: string; detail?: string }): string {
  const base =
    result.reason === 'not-installed'
      ? '模型文件还没装好，请重新下载。'
      : result.reason === 'load-failed'
        ? '模型装好了，但加载不起来。'
        : result.reason === 'request-failed'
          ? '无法向本机核心请求检测。'
          : '检测未通过。'
  const detail = (result.detail ?? '').trim()
  return detail ? `${base}${detail}` : base
}

function stateBadge(entry: ModelHubEntry, skipped: boolean) {
  if (entry.state === 'running') return <Badge tone="brand">下载中</Badge>
  if (entry.installed) return <Badge tone="success">已安装</Badge>
  if (entry.state === 'failed') return <Badge tone="danger">下载失败</Badge>
  if (entry.state === 'cancelled') return <Badge tone="warning">已取消</Badge>
  if (skipped) return <Badge tone="neutral">已跳过</Badge>
  return <Badge tone="neutral">未安装</Badge>
}

export interface ModelDownloadCardProps {
  
  modelKey: string
  
  title?: string
  



  skipLabel?: string
  
  skipped?: boolean
  onSkip?: () => void
  
  showVerify?: boolean
  
  extra?: ReactNode
  className?: string
}

export function ModelDownloadCard({
  modelKey,
  title,
  skipLabel,
  skipped = false,
  onSkip,
  showVerify = true,
  extra,
  className,
}: ModelDownloadCardProps) {
  const entry = useModelHubStore((state) => state.models[modelKey])
  const busy = useModelHubStore((state) => Boolean(state.busy[modelKey]))
  const verifying = useModelHubStore((state) => Boolean(state.verifying[modelKey]))
  const verifyResult = useModelHubStore((state) => state.verifyResults[modelKey])
  const refresh = useModelHubStore((state) => state.refresh)
  const start = useModelHubStore((state) => state.start)
  const cancel = useModelHubStore((state) => state.cancel)
  const verify = useModelHubStore((state) => state.verify)

  
  useEffect(() => {
    void refresh()
  }, [refresh])

  if (!entry) {
    return (
      <div className={clsx('rounded-[10px] border border-line bg-panel px-3 py-2.5', className)}>
        <div className="flex items-center gap-2 text-[12.5px] text-ink-soft">
          <Spinner />
          正在读取模型状态…
        </div>
      </div>
    )
  }

  const running = entry.state === 'running'
  const total = entry.total_bytes || 1
  const percent = Math.max(0, Math.min(100, Math.round((entry.done_bytes * 100) / total)))
  const speed = running ? formatSpeed(entry.speed) : ''
  
  const canDownload = !running && !entry.installed
  const verifyFailed = verifyResult ? !verifyResult.ok : false

  return (
    <div className={clsx('rounded-[10px] border border-line bg-panel px-3 py-2.5', className)}>
      <div className="flex items-baseline justify-between gap-2">
        <h5 className="text-[12.5px] font-semibold text-ink">{title ?? entry.title}</h5>
        {stateBadge(entry, skipped)}
      </div>

      <p className="mt-1 text-[12px] leading-relaxed text-ink-soft">{entry.summary}</p>
      {

}
      <p className="mt-0.5 text-[11.5px] leading-relaxed text-ink-faint">{entry.requirement}</p>

      {}
      {entry.fallback_used ? (
        <p className="mt-2 rounded-[8px] border border-warning/30 bg-warning-soft px-2.5 py-1.5 text-[11.5px] leading-relaxed text-warning">
          主源不可用，已切换到备用线路继续下载（模型内容完全一致）。
        </p>
      ) : null}

      {running ? (
        <div className="mt-2.5 flex flex-col gap-1.5">
          <div className="flex items-baseline justify-between gap-2 text-[11.5px] text-ink-soft">
            <span className="min-w-0 truncate">
              {entry.current_file || '准备中…'} · {formatBytes(entry.done_bytes)} /{' '}
              {formatBytes(entry.total_bytes)}
            </span>
            <span className="shrink-0 tabular-nums">
              {speed ? <span className="mr-2 text-ink-faint tabular-nums">{speed}</span> : null}
              {percent}%
            </span>
          </div>
          <div
            role="progressbar"
            aria-valuenow={percent}
            aria-valuemin={0}
            aria-valuemax={100}
            aria-label={`${title ?? entry.title}下载进度`}
            className="h-2 w-full overflow-hidden rounded-full bg-brand-soft"
          >
            <div
              
              
              className="h-full rounded-full bg-brand transition-[width] duration-150 ease-out motion-reduce:transition-none"
              style={{ width: `${percent}%` }}
            />
          </div>
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={() => void cancel(modelKey)}
              disabled={busy}
              
              
              className="inline-flex items-center gap-1 rounded-[6px] text-[11.5px] text-ink-faint hover:text-ink focus-visible:ring-2 focus-visible:ring-brand/60 focus-visible:outline-none disabled:cursor-not-allowed"
            >
              <X size={12} />
              取消下载
            </button>
          </div>
        </div>
      ) : null}

      {!running && entry.state === 'failed' ? (
        <p className="mt-2 rounded-[8px] border border-danger/30 bg-danger-soft px-2.5 py-1.5 text-[11.5px] leading-relaxed text-danger">
          下载失败：{entry.error || '未知原因'}。两条线路都没成功，请检查网络后重试。
        </p>
      ) : null}

      {!running && entry.state === 'cancelled' ? (
        <p className="mt-2 text-[11.5px] text-ink-faint">
          已取消。已经下好的部分会保留，再次下载会接着下。
        </p>
      ) : null}

      {

}
      {verifying ? (
        <p className="mt-2 flex items-center gap-1.5 text-[11.5px] text-ink-soft" role="status">
          <Loader2 size={12} className="animate-spin" />
          正在检测模型能否正常加载…
        </p>
      ) : verifyResult ? (
        verifyResult.ok ? (
          <p
            role="status"
            className="mt-2 flex items-start gap-1.5 rounded-[8px] border border-success/25 bg-success-soft px-2.5 py-1.5 text-[11.5px] leading-relaxed text-ink-soft"
          >
            <Check size={13} className="mt-[2px] shrink-0 text-success" />
            <span>
              下载并安装成功，可以正常使用。
              {verifyResult.detail ? (
                <span className="text-ink-faint">（{verifyResult.detail}）</span>
              ) : null}
            </span>
          </p>
        ) : (
          <p
            role="status"
            className="mt-2 flex items-start gap-1.5 rounded-[8px] border border-danger/30 bg-danger-soft px-2.5 py-1.5 text-[11.5px] leading-relaxed text-danger"
          >
            <AlertTriangle size={13} className="mt-[2px] shrink-0" />
            <span>自动检测没通过：{verifyFailureText(verifyResult)}</span>
          </p>
        )
      ) : null}

      {!running ? (
        <div className="mt-2.5 flex flex-wrap items-center gap-2">
          {canDownload ? (
            <Button
              variant="primary"
              size="sm"
              icon={
                busy ? (
                  <Loader2 size={13} className="animate-spin" />
                ) : entry.state === 'failed' || entry.state === 'cancelled' ? (
                  <RefreshCw size={13} />
                ) : (
                  <Download size={13} />
                )
              }
              disabled={busy}
              onClick={() => void start(modelKey)}
            >
              {entry.state === 'failed' || entry.state === 'cancelled' ? '重新下载' : '开始下载'}
            </Button>
          ) : null}
          {

}
          {skipLabel && onSkip ? (
            <button
              type="button"
              onClick={onSkip}
              disabled={busy || verifying}
              className="h-7 rounded-[8px] border border-line px-2.5 text-[12.5px] text-ink-soft transition-colors hover:bg-hover hover:text-ink focus-visible:ring-2 focus-visible:ring-brand/60 focus-visible:outline-none disabled:cursor-not-allowed disabled:opacity-60"
            >
              {skipLabel}
            </button>
          ) : null}
          {entry.installed && showVerify ? (
            <Button
              size="sm"
              
              
              icon={verifying ? <Loader2 size={13} className="animate-spin" /> : undefined}
              disabled={verifying || busy}
              onClick={() => void verify(modelKey)}
            >
              {verifyFailed ? '再验证一次' : '验证一下'}
            </Button>
          ) : null}
          {extra}
        </div>
      ) : null}
    </div>
  )
}
