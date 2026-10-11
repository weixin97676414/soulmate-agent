import { useState } from 'react'
import { Check, Radio } from 'lucide-react'

import { Card } from '@/components/account/Card'
import { Badge, Button, Spinner } from '@/components/ui'
import { useAccountStore } from '@/stores/accountStore'
import type { AccountLine } from '@shared/bridge'

const LINE_LABEL: Record<AccountLine, string> = { cn: '大陆', seoul: '首尔' }

function latency(value: number | null): string {
  return value === null ? '不可达' : `${Math.round(value)}ms`
}

/**
 * 线路卡：两侧延迟 + 手动切换 + 重新测速（文档 §6.3）。
 *
 * 手动切换只在"那一侧彻底连不上"时才被自动改走，这里照实渲染：
 * 当前用哪边、另一边延迟多少、哪边不可达，都直接亮出来，不做任何替用户
 * 省略的判断 —— 线路对用户是"玄学"，越透明越好。
 */
export function LineCard() {
  const snapshot = useAccountStore((state) => state.snapshot)
  const setLine = useAccountStore((state) => state.setLine)
  const reprobeLine = useAccountStore((state) => state.reprobeLine)
  const [probing, setProbing] = useState(false)

  if (!snapshot) return null
  const line = snapshot.line
  const disabled = snapshot.offline || !snapshot.deviceUsable

  const switchTo = async (target: AccountLine) => {
    if (target === line?.preferred) return
    await setLine(target)
  }

  const reprobe = async () => {
    setProbing(true)
    await reprobeLine()
    setProbing(false)
  }

  return (
    <Card
      title="线路"
      actions={
        <Button size="sm" variant="ghost" icon={probing ? <Spinner /> : <Radio size={13} />} disabled={disabled || probing} onClick={() => void reprobe()}>
          {probing ? '测速中' : '重新测速'}
        </Button>
      }
    >
      {!line ? (
        <p className="text-[12.5px] text-ink-soft">尚未测得线路，联网后自动完成。</p>
      ) : (
        <div className="space-y-2">
          {(['cn', 'seoul'] as const).map((key) => {
            const active = line.preferred === key
            const unreachable = line.measurements[key] === null
            return (
              <div
                key={key}
                className={
                  'flex items-center justify-between gap-3 rounded-[8px] border px-3 py-2 ' +
                  (active ? 'border-brand/30 bg-brand-soft' : 'border-line-soft bg-canvas')
                }
              >
                <div className="flex items-center gap-2">
                  <span className="text-[13px] font-medium text-ink">{LINE_LABEL[key]}</span>
                  {active ? <Badge tone="brand">当前</Badge> : null}
                </div>
                <div className="flex items-center gap-3">
                  <span
                    className={
                      'text-[12.5px] tabular-nums ' +
                      (unreachable ? 'text-danger' : active ? 'text-brand' : 'text-ink-soft')
                    }
                  >
                    {latency(line.measurements[key])}
                  </span>
                  {!active ? (
                    <Button size="sm" variant="secondary" disabled={disabled || unreachable} onClick={() => void switchTo(key)}>
                      切换到这里
                    </Button>
                  ) : (
                    <Check size={15} className="text-brand" />
                  )}
                </div>
              </div>
            )
          })}
          <p className="pt-1 text-[11.5px] text-ink-faint">
            {line.manual
              ? '当前为你手动选择的线路；只有它彻底连不上时才会自动切走。'
              : '启动时自动按实测延迟选择，切换后所有请求走新线路。'}
          </p>
        </div>
      )}
    </Card>
  )
}
