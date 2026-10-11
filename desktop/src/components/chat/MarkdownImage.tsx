import { AlertTriangle, Loader2 } from 'lucide-react'
import { useEffect, useState } from 'react'

import { useAppStore } from '@/stores/appStore'

/**
 * 对话里图片的渲染（Markdown 的 `![说明](地址)`）。
 *
 * ## 为什么要分两类处理
 *
 * 模型给的图片地址有两类，**加载方式完全不同**：
 *
 * 1. **网络图**（`https://...`）：直接交给 `<img>`，CSP 已放行任意 https。
 * 2. **本机路径**（`D:\图片\a.png`、`file:///D:/a.png`）：浏览器根本加载不了 ——
 *    `D:\...` 不是合法 URL（`d:` 会被当成协议名），`file://` 在开发态（页面在
 *    `http://localhost`）拿不到、生产态的 CSP 也不放行 `file:`。
 *    所以由**核心**读文件回字节（`/v1/media/local-image`），前端取成 Blob 再转 object URL。
 *
 * 这个绕法顺带解决了"破图"：核心会把失败原因（不存在 / 不是图片 / 超出访问白名单 /
 * 是网络共享路径）用一句人话回来，这里直接显示。**加载失败时静默一块破图，是用户明确
 * 说过最不能接受的那种失败方式** —— 所以外链图这里也接了失败提示。
 *
 * 注意与产物预览（`ArtifactPreview` 里的 `ImagePreview`）的分工：那个是**工作区里已登记
 * 的文件**（有 file id、有归属），走 `/v1/files/{id}`；这里是**对话内容里随手写的路径**，
 * 走新的代理接口。两者都返回 Blob，但来源与校验规则不同，不适合合并。
 */

/** 看起来像本机绝对路径的几种写法（判断的是"意图"，能不能读到由核心说了算）。 */
export function isLocalImagePath(src: string): boolean {
  if (!src) return false
  if (/^file:\/\//i.test(src)) return true // file:///D:/a.png
  if (/^[a-zA-Z]:[\\/]/.test(src)) return true // D:\a.png 或 D:/a.png
  if (src.startsWith('\\\\')) return true // \\服务器\共享\a.png（核心会拒绝并说明原因）
  return src.startsWith('/') // POSIX 绝对路径（Windows 上核心会拒，理由可见）
}

/** 把 `file:///D:/a.png` 还原成核心要的**路径**（`D:/a.png`）。 */
function toPlainPath(src: string): string {
  if (!/^file:\/\//i.test(src)) return src
  let rest = src.replace(/^file:\/\//i, '')
  try {
    rest = decodeURIComponent(rest)
  } catch {
    // 编码不合法（例如 `%zz`）就按原样送去，让核心回一句可读的原因
  }
  // `file:///D:/a.png` 剥掉协议后是 `/D:/a.png`，多出来的那个斜杠要去掉；
  // `file://host/share` 这种（UNC）保持原样，交给核心拒绝并解释为什么。
  return /^\/[a-zA-Z]:/.test(rest) ? rest.slice(1) : rest
}

function LoadingImage() {
  return (
    <span className="my-1 inline-flex items-center gap-1.5 rounded-[8px] border border-line bg-panel px-2 py-1 text-[11.5px] text-ink-faint">
      <Loader2 size={12} className="animate-spin" />
      图片加载中…
    </span>
  )
}

/** 失败提示。用 `<span>` 而不是 `<div>`：它会被渲染在 Markdown 的 `<p>` 里。 */
function FailedImage({ reason, target }: { reason: string; target: string }) {
  return (
    <span className="my-1 flex items-start gap-2 rounded-[8px] border border-warning/30 bg-warning-soft px-2.5 py-1.5 text-[11.5px] leading-relaxed text-warning">
      <AlertTriangle size={12} className="mt-0.5 shrink-0" />
      <span className="block min-w-0 break-all">
        <span className="block font-medium">图片没能显示</span>
        <span className="mt-0.5 block text-ink-soft">{reason}</span>
        {target ? <span className="mt-0.5 block text-ink-faint">{target}</span> : null}
      </span>
    </span>
  )
}

function LocalImage({ path, alt }: { path: string; alt: string }) {
  const api = useAppStore((state) => state.api)
  const [url, setUrl] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let revoked: string | null = null
    let cancelled = false
    setUrl(null)
    setError(null)

    void (async () => {
      if (!api) return
      try {
        const blob = await api.fetchLocalImage(path)
        if (cancelled) return
        const objectUrl = URL.createObjectURL(blob)
        revoked = objectUrl
        setUrl(objectUrl)
      } catch (exc) {
        if (!cancelled) setError(exc instanceof Error ? exc.message : String(exc))
      }
    })()

    return () => {
      cancelled = true
      // 不撤销就会一直占着内存（一条长对话里可能挂着几十张图）
      if (revoked) URL.revokeObjectURL(revoked)
    }
  }, [api, path])

  if (error) return <FailedImage reason={error} target={path} />
  if (!url) return <LoadingImage />
  return <img src={url} alt={alt} className="max-w-full rounded-[8px]" />
}

function RemoteImage({ src, alt }: { src: string; alt: string }) {
  const [failed, setFailed] = useState(false)

  if (failed) {
    return (
      <FailedImage
        reason="这张外链图没加载成功：可能是地址已失效，或者当前网络访问不到那个站点。"
        target={src}
      />
    )
  }
  return <img src={src} alt={alt} loading="lazy" onError={() => setFailed(true)} />
}

export function MarkdownImage({ src, alt }: { src: string; alt: string }) {
  if (!src) {
    return (
      <FailedImage
        reason="图片地址被安全检查拦下了：只允许 http(s)、data: 与本机图片路径。"
        target=""
      />
    )
  }
  if (isLocalImagePath(src)) return <LocalImage path={toPlainPath(src)} alt={alt} />
  return <RemoteImage src={src} alt={alt} />
}
