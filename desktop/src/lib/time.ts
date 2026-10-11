/**
 * 对话里时间戳的显示格式。
 *
 * ## 为什么只做"钟点"和"完整时刻"两种
 *
 * 气泡上的时间**不能**是完整时刻：一条消息一行 `14:32`，几十条下来
 * 满屏都是日期，反而看不清对话。所以：
 *
 * - 常态只显示 `14:32`（今天）或 `09-25 14:32`（不是今天）—— 后者只在**真的跨天**时
 *   才带上日期，否则同一屏里混着两种格式会让人反复确认"这是哪天"；
 * - 鼠标悬停给完整时刻（`title`），想看确切时间的场景不至于没法看。
 *
 * 入参是**毫秒**（前端原生的 `Date.now()` 口径；后端给的 epoch 秒在 `chatStore`
 * 里已经乘过 1000）。传 0 / null / undefined 一律当"不知道"（更早版本落盘的消息
 * 时间戳不可信）—— 返回空串，让调用方什么都不显示，而不是显示 1970 年。
 */

function toDate(ms: number | null | undefined): Date | null {
  if (!ms) return null
  const date = new Date(ms)
  return Number.isNaN(date.getTime()) ? null : date
}

const pad = (value: number): string => String(value).padStart(2, '0')

/** 气泡上的短时间：`14:32`；不是今天则带日期 `09-25 14:32`。不知道就返回空串。 */
export function formatClock(ms: number | null | undefined): string {
  const date = toDate(ms)
  if (!date) return ''
  const clock = `${pad(date.getHours())}:${pad(date.getMinutes())}`
  const today = new Date()
  const sameDay =
    date.getFullYear() === today.getFullYear() &&
    date.getMonth() === today.getMonth() &&
    date.getDate() === today.getDate()
  return sameDay ? clock : `${pad(date.getMonth() + 1)}-${pad(date.getDate())} ${clock}`
}

/** 完整时刻 `14:32`，给 `title` 悬停用。不知道就返回空串。 */
export function formatFull(ms: number | null | undefined): string {
  const date = toDate(ms)
  if (!date) return ''
  return (
    `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())} ` +
    `${pad(date.getHours())}:${pad(date.getMinutes())}`
  )
}
