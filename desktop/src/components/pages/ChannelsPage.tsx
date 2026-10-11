import { Info, Radio } from 'lucide-react'

/**
 * 「频道」页 —— 本轮为**规划占位**（用户明确的路线图项）：
 *
 * 目标形态（对齐 openclaw 的 channels）：把助手接入外部 IM/平台 ——
 * 微信、企业微信、Telegram、飞书等。核心模型：
 * - 接入时选择**哪个 Buddy** 接入该频道；
 * - 一个 Buddy 可以同时接入**多个**频道；一个频道也可以配**多个** Buddy
 *   （适配多设备 / 多平台 / 多账号）；
 * - ⚠️ 个别平台**只支持单频道接入**（如微信：同一账号同时只能挂一个会话通道），
 *   接入向导里会显式提示。
 *
 * 真正的接入需要各平台的机器人凭证与回调服务，随「频道接入」版本交付。
 */
export function ChannelsPage() {
  return (
    <div className="flex min-w-0 flex-1 flex-col overflow-y-auto px-8 py-6">
      <div className="max-w-[720px]">
        <div className="flex items-center gap-2">
          <Radio size={18} className="text-brand" />
          <h2 className="text-[15px] font-semibold text-ink">频道</h2>
        </div>
        <p className="mt-2 text-[13px] leading-relaxed text-ink-soft">
          把你的 Buddy 接入微信、Telegram、飞书等外部平台 ——
          在你习惯的聊天软件里直接和它对话。
        </p>

        <div className="mt-6 space-y-3">
          <div className="rounded-[10px] border border-line bg-panel px-4 py-3.5">
            <div className="text-[13px] font-medium text-ink">规划中的能力</div>
            <ul className="mt-2 list-disc space-y-1 pl-5 text-[12.5px] leading-relaxed text-ink-soft">
              <li>接入频道时选择由哪个 Buddy 应答；</li>
              <li>一个 Buddy 可同时接入多个频道，一个频道也可服务多个 Buddy
                  （适配多设备、多平台、多账号）；</li>
              <li>各频道独立开关、独立会话隔离，消息与工具调用照常走本机核心。</li>
            </ul>
          </div>

          <div className="flex items-start gap-2 rounded-[10px] border border-warning/30 bg-warning-soft px-4 py-3">
            <Info size={15} className="mt-0.5 shrink-0 text-warning" />
            <p className="text-[12.5px] leading-relaxed text-ink-soft">
              请注意：部分平台只支持单频道接入（例如微信，同一账号同时只能维持
              一个会话通道）。接入向导会在选择平台时明确提示。
            </p>
          </div>

          <div className="rounded-[10px] border border-dashed border-line px-4 py-6 text-center text-[12.5px] text-ink-faint">
            频道接入即将上线，敬请期待。
          </div>
        </div>
      </div>
    </div>
  )
}

/** 「权益」页 —— 占位（约定的导航顺序里预留的位置）。 */
export function BenefitsPage() {
  return (
    <div className="flex min-w-0 flex-1 flex-col overflow-y-auto px-8 py-6">
      <div className="max-w-[720px]">
        <div className="flex items-center gap-2">
          <h2 className="text-[15px] font-semibold text-ink">权益</h2>
        </div>
        <div className="mt-6 rounded-[10px] border border-dashed border-line px-4 py-10 text-center text-[12.5px] text-ink-faint">
          权益中心即将上线。
        </div>
      </div>
    </div>
  )
}
