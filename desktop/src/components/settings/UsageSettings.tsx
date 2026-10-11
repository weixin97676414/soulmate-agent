import clsx from 'clsx'
import { AlertTriangle, Coins, Info, Loader2, RefreshCw, Trash2, Zap } from 'lucide-react'
import { useCallback, useEffect, useState } from 'react'

import { Badge, Button, EmptyState, Modal } from '@/components/ui'
import { currencySymbol, formatCost, formatRate, formatTokens } from '@/lib/format'
import { budgetStatus, useUsageStore } from '@/stores/usageStore'
import type { UsageSummary, UsageTotals } from '@/types'

const WINDOWS = [7, 30, 90] as const

/**
 * Token 数、金额、比率的显示格式统一在 `lib/format`（第 92 批，M-36 改用 `Intl`）。
 *
 * ⚠️ 它们原来**手写在这里**：`1.00M` / `10.0K` 这种英文紧凑写法、手工拼 `¥` / `$`、
 * 手工 `toFixed`。手写的问题不是难看，而是这些**约定**（千位分隔、货币符号位置、
 * 小数位数）得自己记着 —— 而"小额保留 4 位"那条规则，正是当初为了不让
 * `0.0123` 显示成"看起来免费"才加上的，换个页面就很容易漏掉。
 * 现在金额那两条口径（4 位小数、`$` 而不是 `US$`）连同理由一起写在 `lib/format` 里。
 */

function Metric({
  label,
  value,
  hint,
  tone,
}: {
  label: string
  value: string
  hint?: string
  tone?: 'success' | 'warning' | 'brand'
}) {
  return (
    <div className="rounded-[10px] border border-line bg-canvas px-3 py-2.5">
      <div className="text-[11px] text-ink-faint">{label}</div>
      <div
        className={clsx(
          'mt-1 text-[17px] font-medium tabular-nums',
          tone === 'success' && 'text-success',
          tone === 'warning' && 'text-warning',
          tone === 'brand' && 'text-brand',
          !tone && 'text-ink',
        )}
      >
        {value}
      </div>
      {hint ? <div className="mt-0.5 text-[10.5px] text-ink-faint">{hint}</div> : null}
    </div>
  )
}

/** 纯 CSS 的每日柱状图。数据量小（≤90 条），不值得引入图表库。 */
function DailyBars({ days, currency }: { days: UsageSummary['by_day']; currency: string }) {
  if (days.length === 0) return null
  // 后端按天倒序返回，画图要从左到右是时间正序
  const ordered = [...days].reverse()
  const costs = ordered.map((item) => item.cost ?? 0)
  const max = Math.max(...costs, 1)
  const anyCost = costs.some((value) => value > 0)

  return (
    <div>
      <div className="mb-1.5 flex items-center justify-between text-[11px] text-ink-faint">
        <span>{anyCost ? `每日费用（${currencySymbol(currency)}）` : '每日 Token 用量'}</span>
        <span>{ordered[0]?.day} ~ {ordered[ordered.length - 1]?.day}</span>
      </div>
      <div className="flex h-[72px] items-end gap-[3px]">
        {ordered.map((item) => {
          const value = anyCost ? (item.cost ?? 0) : item.total_tokens
          const limit = anyCost ? max : Math.max(...ordered.map((d) => d.total_tokens), 1)
          const height = limit > 0 ? Math.max((value / limit) * 100, value > 0 ? 4 : 0) : 0
          return (
            <div
              key={item.day}
              className="group relative flex-1"
              title={`${item.day}：${item.calls} 次调用 · ${item.total_tokens} tokens · 缓存命中 ${formatRate(
                item.cache_hit_rate,
              )} · ${formatCost(item.cost, currency)}`}
            >
              <div
                className="w-full rounded-t-[2px] bg-brand/60 transition-colors group-hover:bg-brand"
                style={{ height: `${height}%`, minHeight: value > 0 ? 2 : 0 }}
              />
            </div>
          )
        })}
      </div>
    </div>
  )
}

function TotalsRow({ totals, currency }: { totals: UsageTotals; currency: string }) {
  return (
    <>
      <td className="px-2 py-1.5 text-right tabular-nums text-ink-soft">{totals.calls}</td>
      <td className="px-2 py-1.5 text-right tabular-nums text-ink-soft">
        {formatTokens(totals.prompt_tokens)}
      </td>
      <td className="px-2 py-1.5 text-right tabular-nums text-ink-soft">
        {formatTokens(totals.completion_tokens)}
      </td>
      <td className="px-2 py-1.5 text-right tabular-nums">
        {totals.cache_hit_rate === null ? (
          <span className="text-ink-faint">不支持</span>
        ) : (
          <span
            className={clsx(
              totals.cache_hit_rate >= 0.5
                ? 'text-success'
                : totals.cache_hit_rate > 0
                  ? 'text-warning'
                  : 'text-ink-faint',
            )}
          >
            {formatRate(totals.cache_hit_rate)}
          </span>
        )}
      </td>
      <td className="px-2 py-1.5 text-right tabular-nums text-ink">
        {formatCost(totals.cost, currency)}
      </td>
    </>
  )
}

export function UsageSettings() {
  const summary = useUsageStore((state) => state.summary)
  const loading = useUsageStore((state) => state.loading)
  const error = useUsageStore((state) => state.error)
  const load = useUsageStore((state) => state.load)
  const clear = useUsageStore((state) => state.clear)

  const [days, setDays] = useState<number>(30)
  const [confirming, setConfirming] = useState(false)
  const [clearing, setClearing] = useState(false)

  // 设置页被重新挂载时刷新一次即可；不做轮询——
  // 用量只在对话结束后变化，轮询没有意义还会干扰用户看数字
  useEffect(() => {
    void load(days)
  }, [days, load])

  const refresh = useCallback(() => void load(days), [load, days])

  if (error) {
    return (
      <EmptyState
        icon={<AlertTriangle size={22} />}
        title="读取用量失败"
        description={error}
        action={
          <Button variant="secondary" onClick={refresh}>
            <RefreshCw size={13} />
            重试
          </Button>
        }
      />
    )
  }

  if (!summary && loading) {
    return (
      <div className="flex items-center justify-center py-16 text-ink-faint">
        <Loader2 size={18} className="animate-spin" />
      </div>
    )
  }

  if (summary && !summary.available) {
    return (
      <EmptyState
        icon={<AlertTriangle size={22} />}
        title="用量统计暂不可用"
        description={summary.message ?? '数据库未连接，无法读取用量流水。'}
      />
    )
  }

  const currency = summary?.currency ?? 'CNY'
  const budget = budgetStatus(summary ?? null)
  const hasAnyCall = (summary?.total?.calls ?? 0) > 0

  return (
    /*
      ⚠️ `max-w-[880px]`：这一页原先连宽度上限都没有，内容铺满整宽。
      加它是为了和同一排的其它设置页一样"宽度固定、靠左"。

      ⚠️ **不要再加 `mx-auto`**：做过一版居中的，用户看过之后说"居中并不好看" ——
      他要的是内容**贴着左边**（距侧栏 40px），不是飘在窗口中间。
    */
    <div className="max-w-[880px] space-y-4">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-1 rounded-[8px] border border-line p-0.5">
          {WINDOWS.map((value) => (
            <button
              key={value}
              type="button"
              onClick={() => setDays(value)}
              className={clsx(
                'rounded-[6px] px-2.5 py-1 text-[12px] transition-colors',
                days === value
                  ? 'bg-brand-soft text-brand'
                  : 'text-ink-soft hover:bg-hover hover:text-ink',
              )}
            >
              近 {value} 天
            </button>
          ))}
        </div>
        <div className="flex items-center gap-2">
          <Button variant="secondary" onClick={refresh} disabled={loading}>
            {loading ? <Loader2 size={13} className="animate-spin" /> : <RefreshCw size={13} />}
            刷新
          </Button>
          <Button
            variant="secondary"
            onClick={() => setConfirming(true)}
            disabled={!hasAnyCall}
            title="清空用量流水（不影响会话与消息）"
          >
            <Trash2 size={13} />
            清空
          </Button>
        </div>
      </div>

      {summary && !summary.prices_configured ? (
        <div className="flex items-start gap-2 rounded-[10px] border border-brand/25 bg-brand-soft/40 px-3 py-2.5">
          <Info size={14} className="mt-0.5 shrink-0 text-brand" />
          <div className="text-[12px] leading-relaxed text-ink-soft">
            <span className="font-medium text-ink">还没有配置模型单价，因此无法估算费用。</span>
            <br />
            去「模型服务商」页签编辑模型，填入「输入 / 输出单价（每百万 token）」即可看到金额。
            这里刻意不内置参考价——厂商调价频繁，一个过期的价格比没有价格更容易误导人。
          </div>
        </div>
      ) : null}

      {/* ---- 今日 ---- */}
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <Metric
          label="今日费用"
          value={formatCost(summary?.today?.cost ?? null, currency)}
          hint={
            budget
              ? `预算 ${formatCost(budget.budget, currency)} / 天`
              : '未设置每日预算'
          }
          tone={budget?.exceeded ? 'warning' : 'brand'}
        />
        <Metric
          label="今日 Token"
          value={formatTokens(summary?.today?.total_tokens ?? 0)}
          hint={`${summary?.today?.calls ?? 0} 次模型调用`}
        />
        <Metric
          label="缓存命中率"
          value={formatRate(summary?.today?.cache_hit_rate ?? null)}
          hint="命中部分的输入单价通常低一个数量级"
          tone={
            (summary?.today?.cache_hit_rate ?? 0) >= 0.5
              ? 'success'
              : (summary?.today?.cache_hit_rate ?? 0) > 0
                ? 'warning'
                : undefined
          }
        />
        <Metric
          label="近 7 天费用"
          value={formatCost(
            (summary?.by_day ?? [])
              .slice(0, 7)
              .reduce<number | null>((acc, item) => {
                if (item.cost === null) return acc
                return (acc ?? 0) + item.cost
              }, null),
            currency,
          )}
          hint="按天累计"
        />
      </div>

      {budget?.exceeded ? (
        <div className="flex items-start gap-2 rounded-[10px] border border-warning/30 bg-warning-soft px-3 py-2.5">
          <Coins size={14} className="mt-0.5 shrink-0 text-warning" />
          <div className="text-[12px] leading-relaxed text-warning">
            今日已花费 {formatCost(budget.spent, currency)}，达到设定的每日预算
            {formatCost(budget.budget, currency)}。按你的设置这里只提示、不阻止发送，
            如需限制请在「安全与通用」里调整预算或切换模型。
          </div>
        </div>
      ) : null}

      {/* ---- 窗口汇总 ---- */}
      <div className="rounded-[10px] border border-line">
        <div className="flex items-center gap-2 border-b border-line px-3.5 py-2">
          <Zap size={13} className="text-ink-faint" />
          <span className="text-[12.5px] font-medium text-ink">近 {days} 天</span>
          <Badge tone="neutral">{summary?.window?.calls ?? 0} 次调用</Badge>
        </div>
        <div className="grid grid-cols-2 gap-x-4 gap-y-2 px-3.5 py-3 sm:grid-cols-4">
          {[
            ['总 Token', formatTokens(summary?.window?.total_tokens ?? 0)],
            ['输入', formatTokens(summary?.window?.prompt_tokens ?? 0)],
            ['输出', formatTokens(summary?.window?.completion_tokens ?? 0)],
            ['缓存命中', formatRate(summary?.window?.cache_hit_rate ?? null)],
          ].map(([label, value]) => (
            <div key={label}>
              <div className="text-[11px] text-ink-faint">{label}</div>
              <div className="mt-0.5 text-[13px] tabular-nums text-ink">{value}</div>
            </div>
          ))}
        </div>
        <div className="border-t border-line-soft px-3.5 py-3">
          <DailyBars days={summary?.by_day ?? []} currency={currency} />
        </div>
      </div>

      {/* ---- 按模型 ---- */}
      {(summary?.by_model.length ?? 0) > 0 ? (
        <div className="overflow-hidden rounded-[10px] border border-line">
          <table className="w-full text-[12px]">
            <thead>
              <tr className="border-b border-line bg-panel text-[11px] text-ink-faint">
                <th className="px-2 py-2 text-left font-normal">模型</th>
                <th className="px-2 py-2 text-right font-normal">调用</th>
                <th className="px-2 py-2 text-right font-normal">输入</th>
                <th className="px-2 py-2 text-right font-normal">输出</th>
                <th className="px-2 py-2 text-right font-normal">缓存命中</th>
                <th className="px-2 py-2 text-right font-normal">费用</th>
              </tr>
            </thead>
            <tbody>
              {summary?.by_model.map((item) => (
                <tr key={item.model_id} className="border-b border-line-soft last:border-0">
                  <td className="max-w-[220px] truncate px-2 py-1.5 text-ink" title={item.model_id}>
                    {item.model_id}
                  </td>
                  <TotalsRow totals={item} currency={currency} />
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <EmptyState
          icon={<Coins size={22} />}
          title="还没有用量记录"
          description="发一条消息之后，这里会显示 token 消耗、缓存命中率与费用估算。"
        />
      )}

      <Modal
        open={confirming}
        title="清空用量统计？"
        description="将删除全部 token 用量与费用流水。会话、消息、审计日志都不受影响。"
        onClose={() => setConfirming(false)}
        children={null}
        footer={
          <>
            <Button variant="secondary" onClick={() => setConfirming(false)}>
              取消
            </Button>
            <Button
              variant="danger"
              disabled={clearing}
              onClick={() => {
                setClearing(true)
                void clear().finally(() => {
                  setClearing(false)
                  setConfirming(false)
                })
              }}
            >
              {clearing ? <Loader2 size={13} className="animate-spin" /> : <Trash2 size={13} />}
              确认清空
            </Button>
          </>
        }
      />
    </div>
  )
}
