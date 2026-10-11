import clsx from 'clsx'
import { AlertTriangle, Check, Download, Loader2, RefreshCw, X } from 'lucide-react'
import type { ReactNode } from 'react'
import { useEffect } from 'react'

import { Badge, Button, Spinner } from '@/components/ui'
import { useModelHubStore } from '@/stores/modelHubStore'
import type { ModelHubEntry } from '@/types'

/**
 * 本地模型（语音 / 嵌入）的**下载卡片** —— 四个入口共用同一份渲染。
 *
 * 四个地方要显示同一件事：首启引导页的「语音设置」「长期记忆」两张卡、
 * 语音设置面板里的补装入口、长期记忆设置区的补装入口。各写一遍的话，
 * "跳过后补装"这类规则会在三处慢慢走样（最典型的是某处忘了显示
 * 「已切换到备用线路」，而用户正好在那处看到"下得慢"）。
 *
 * ## 状态从哪来
 *
 * 全部读 `modelHubStore`（SSE 事件 + 轮询两条通道，见那个文件）。卡片本身
 * **不持有进度**：它一卸载再挂载（切页面、关面板）进度就没了。
 *
 * ## 为什么"下载完成"要自动检测
 *
 * 产品要求如此，而且不检测不行：`installed` 只保证"文件在、长度对"，
 * 而模型文件被杀软删掉一块、或者机器缺 `sherpa_onnx` 依赖时，文件看着是齐的
 * —— 那种"装好了却用不了"比"没装"更让人困惑。检测走的是真实的加载路径。
 */

/** 字节 → 人话（下载进度与网速都用它，所以只写一份） */
function formatBytes(bytes: number): string {
  if (!Number.isFinite(bytes) || bytes <= 0) return '0 MB'
  const mb = bytes / 1024 / 1024
  if (mb >= 1024) return `${(mb / 1024).toFixed(2)} GB`
  return `${mb >= 100 ? mb.toFixed(0) : mb.toFixed(1)} MB`
}

function formatSpeed(bytesPerSecond: number): string {
  if (!Number.isFinite(bytesPerSecond) || bytesPerSecond <= 0) return ''
  const kb = bytesPerSecond / 1024
  if (kb < 1024) return `${kb.toFixed(0)} KB/s`
  return `${(kb / 1024).toFixed(1)} MB/s`
}

/** 检测失败时把后端给的机器话翻成人话（`detail` 原样附在后面，不要丢） */
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
  /** 模型 id（'voice' / 'embedding'） */
  modelKey: string
  /** 覆盖核心下发的标题 */
  title?: string
  /**
   * 跳过按钮的文案。**不传 = 不显示跳过按钮**（设置页里没有"跳过"这回事：
   * 用户是主动进来补装的）。
   */
  skipLabel?: string
  /** 用户是否已经在本页跳过过（由调用方持有 —— 跳过一次不该重启就忘了） */
  skipped?: boolean
  onSkip?: () => void
  /** 是否显示「验证一下」（默认显示；引导页的语音卡不需要它） */
  showVerify?: boolean
  /** 动作行末尾的附加内容（例如语音装好后的「开始配置」） */
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

  // 挂载时对一遍状态：卡片可能在"别处下完了"之后才被打开。
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
  // 失败/取消之后要能再点一次下载；已经装好了则不显示下载按钮
  const canDownload = !running && !entry.installed
  const verifyFailed = verifyResult ? !verifyResult.ok : false

  return (
    <div className={clsx('rounded-[10px] border border-line bg-panel px-3 py-2.5', className)}>
      <div className="flex items-baseline justify-between gap-2">
        <h5 className="text-[12.5px] font-semibold text-ink">{title ?? entry.title}</h5>
        {stateBadge(entry, skipped)}
      </div>

      <p className="mt-1 text-[12px] leading-relaxed text-ink-soft">{entry.summary}</p>
      {/* 电脑配置要求必须写在按钮旁边（产品要求）：用户得先判断装不装得下
          —— 600MB 与"四核 CPU"是能劝退一部分老机器的事实，藏起来只会让
          他在下载到一半时才发现 */}
      <p className="mt-0.5 text-[11.5px] leading-relaxed text-ink-faint">{entry.requirement}</p>

      {/* ⚠️ 回退必须说出来：静默换源会让用户以为"我选的国内源其实能用" */}
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
              // `motion-reduce:transition-none`：开了"减少动态效果"的用户不该看到
              // 进度条平滑推进（与 index.css 里对转圈图标的处理同一口径）
              className="h-full rounded-full bg-brand transition-[width] duration-150 ease-out motion-reduce:transition-none"
              style={{ width: `${percent}%` }}
            />
          </div>
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={() => void cancel(modelKey)}
              disabled={busy}
              // ⚠️ 焦点环必须显式写：Tailwind 的 reset 把 outline 清了，
              // 不给 `focus-visible:ring-*` 的话键盘用户看不到焦点在哪
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

      {/* 自检结果：成功与失败都如实显示（失败的 reason 由后端给，别自己编）。
          `role="status"`：这段是**异步冒出来**的（下载完自动检测 / 用户点「验证一下」），
          不播报的话读屏用户只会听到界面莫名其妙多了一段文字。 */}
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
          {/* ⚠️ 顺序是「下载 → 跳过 → 验证」（产品要求把「跳过配置」
              放到「验证一下」前面）。「验证一下」在这两个模型上是**次要动作**，
              而"跳过"是这一步的主要出口之一，放前面更顺。 */}
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
              // ⚠️ **不带图标**（产品要求剔除那个盾牌）：只有"检测中"
              // 才给一个转圈图标 —— 它是状态，不是装饰。
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
