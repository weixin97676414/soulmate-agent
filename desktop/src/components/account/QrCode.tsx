import { useEffect, useState } from 'react'
import QRCode from 'qrcode'

/**
 * 本地二维码（微信 `code_url` / USDT `tron:<地址>` 通用）。
 *
 * ## 为什么本地生成而不是后端图片
 *
 * 文档对微信码给的是"本地生成 code_url"或"后端图片"两条路，USDT 码更是**只有**
 * 本地生成（`tron:` 内容）。统一走本地生成：只引一个纯 JS 的 `qrcode`，
 * 不依赖后端图片接口、也不受渲染层 CSP `img-src` 白名单约束。
 *
 * ## 为什么用 SVG 而不是 canvas
 *
 * SVG 无论窗口缩放都保持锐利，且 `qrcode` 的 `toString(type:'svg')` 不需要
 * pngjs 那一路，产物更小。标记是库生成的受控结构、不是用户输入，注入是安全的。
 */
export function QrCode({ value, size = 240 }: { value: string; size?: number }) {
  const [svg, setSvg] = useState('')

  useEffect(() => {
    let cancelled = false
    if (!value) {
      setSvg('')
      return
    }
    QRCode.toString(value, {
      type: 'svg',
      margin: 3, // 3 模块静区：微信/TRC20 扫码器识别所需的留白（含在 SVG 里，不另加 padding）
      width: size,
      color: { dark: '#000000', light: '#ffffff' },
      errorCorrectionLevel: 'M',
    })
      .then((result) => {
        if (!cancelled) setSvg(result)
      })
      .catch(() => {
        if (!cancelled) setSvg('')
      })
    return () => {
      cancelled = true
    }
  }, [value, size])

  if (!svg) {
    // 生成中 / 值无效：占一个同尺寸的空白位，避免布局跳动
    return (
      <div
        className="rounded-[8px] bg-white"
        style={{ width: size, height: size }}
        aria-hidden
      />
    )
  }

  return (
    // 不加 padding：SVG 宽度就是 size，静区已由 margin:3 内置；再加 padding 会让
    // 二维码超出这个白底框而被裁掉
    <div
      className="inline-flex items-center justify-center overflow-hidden rounded-[8px] bg-white"
      style={{ width: size, height: size }}
      dangerouslySetInnerHTML={{ __html: svg }}
    />
  )
}
