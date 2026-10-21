import { AlertTriangle, Loader2 } from 'lucide-react'
import { useEffect, useState } from 'react'

import { useAppStore } from '@/stores/appStore'
























export function isLocalImagePath(src: string): boolean {
  if (!src) return false
  if (/^file:\/\//i.test(src)) return true 
  if (/^[a-zA-Z]:[\\/]/.test(src)) return true 
  if (src.startsWith('\\\\')) return true 
  return src.startsWith('/') 
}


function toPlainPath(src: string): string {
  if (!/^file:\/\//i.test(src)) return src
  let rest = src.replace(/^file:\/\//i, '')
  try {
    rest = decodeURIComponent(rest)
  } catch {
    
  }
  
  
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
