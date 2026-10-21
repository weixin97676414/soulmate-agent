import { useEffect, useState } from 'react'
import QRCode from 'qrcode'















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
      margin: 3, 
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
    
    return (
      <div
        className="rounded-[8px] bg-white"
        style={{ width: size, height: size }}
        aria-hidden
      />
    )
  }

  return (
    
    
    <div
      className="inline-flex items-center justify-center overflow-hidden rounded-[8px] bg-white"
      style={{ width: size, height: size }}
      dangerouslySetInnerHTML={{ __html: svg }}
    />
  )
}
