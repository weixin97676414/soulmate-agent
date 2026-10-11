/**
 * 设置页里日期 / 数字 / 金额的显示格式。
 *
 * ## 为什么单独一个模块
 *
 * 这些格式原先各自**手写**在工作区、审计、用量三个页面里 —— 其中两处 `formatTime`
 * 是**两份一模一样**的实现（同一天写的）。手写补零、手工拼 `¥` / `$` 的问题不在于难看，
 * 而在于千位分隔、货币符号位置、12/24 小时制这些**约定**都得自己记着，
 * 于是每换一个页面就可能漏一处。
 *
 * ## 为什么区域显式写 `zh-CN`
 *
 * 界面文案全是中文，格式也应当**稳定**：不显式指定的话输出会跟着**系统区域**变 ——
 * 同一份界面在英文 Windows 上会变成 `10/10/2026`、`US$1.00`，与旁边的中文文案对不上。
 * 所以这里把区域钉死，只用 `Intl` 的"正确实现"，不用它的"跟随系统"。
 *
 * ## 金额刻意保住的两件事（换 `Intl` 不必以它们为代价）
 *
 * 1. **不足 1 分钱的金额保留 4 位小数**：默认 2 位会把 `0.0045` 显示成 `¥0.00`，
 *    **看起来像免费** —— 这是"未配置价格"之外最容易误导用户成本决策的一种显示。
 *    （阈值就是"一分钱"，不是"看着小就多给几位"：`0.0123` 仍然两位，与改之前一致。）
 * 2. **用 `narrowSymbol`**：中文区域下 USD 的默认写法是 `US$`，而界面上一直是 `$`；
 *    那是纯粹的外观退化，没必要因为换了实现就一起改掉。
 */

/** 金额/日期的区域。⚠️ 显式钉死，理由见文件头。 */
const LOCALE = 'zh-CN'

/**
 * epoch **秒** → `2026/10/10 15:30`（设置页的完整时刻）。
 *
 * `withSeconds` / `withYear` 是给**审计表**用的：那一列一行一条记录，
 * 带年份会把表格撑得很宽，而它真正要区分的是"哪一天几点几分几秒"。
 */
export function formatDateTime(
  seconds: number,
  options: { withSeconds?: boolean; withYear?: boolean } = {},
): string {
  const date = new Date(seconds * 1000)
  return new Intl.DateTimeFormat(LOCALE, {
    ...(options.withYear === false ? {} : { year: 'numeric' }),
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    ...(options.withSeconds ? { second: '2-digit' } : {}),
    // 24 小时制：`hour12: false` 而不是交给区域决定 —— 表格里"15:30"与"3:30 PM"
    // 混着看很容易读错，而界面上其他地方也都是 24 小时制
    hour12: false,
  }).format(date)
}

/**
 * Token 数 → `100万` / `1.2万` / `1500`。
 *
 * ⚠️ 这里放弃的是 `1.00M` / `10.0K` 那种**英文**紧凑写法，改成中文习惯的万/亿。
 * 依据是界面上其它地方都已经是中文口径（"共 3 条""近 7 天"），
 * 只有 token 数用 K/M 会显得是从另一套界面抄来的。
 */
export function formatTokens(value: number): string {
  return new Intl.NumberFormat(LOCALE, {
    notation: 'compact',
    maximumFractionDigits: 1,
  }).format(value)
}

/**
 * 金额 → `¥12.30` / `¥0.0045`（不足一分钱）/ `$1.00`。
 *
 * `cost === null` 表示**用户没配单价**，不是"花了 0 元"：这两者必须显示成不同的东西，
 * 把"不知道"显示成"免费"会直接误导成本决策，而且是那种用户永远不会发现的误导。
 *
 * ⚠️ 阈值是**一分钱**（见实现），不是"看着小就给 4 位"：`0.0123` 已经超过一分钱，
 * 仍然显示两位（与改 `Intl` 之前**完全一致**）。这里原先举的例子写的是 `$0.0123`，
 * 与实现不符（第 93 批改正）。
 */
export function formatCost(cost: number | null, currency: string): string {
  if (cost === null) return '未配置价格'
  // 小于 1 分钱的非零金额保留 4 位（理由见文件头第 1 条）
  const digits = cost > 0 && cost < 0.01 ? 4 : 2
  return new Intl.NumberFormat(LOCALE, {
    style: 'currency',
    currency: currency === 'USD' ? 'USD' : 'CNY',
    currencyDisplay: 'narrowSymbol',
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  }).format(cost)
}

/**
 * 只要**货币符号**（柱状图标题那种"每日费用（¥）"的位置用）。
 *
 * 从 `Intl` 的 `formatToParts` 里取 `currency` 那一段，而不是自己写
 * `currency === 'USD' ? '$' : '¥'` —— 后者是**第二份货币口径**，
 * 与 `formatCost` 用的那份迟早会不一致（换了实现却漏改一处，就会看到
 * "标题写着 ¥、数字是 $"）。
 */
export function currencySymbol(currency: string): string {
  const parts = new Intl.NumberFormat(LOCALE, {
    style: 'currency',
    currency: currency === 'USD' ? 'USD' : 'CNY',
    currencyDisplay: 'narrowSymbol',
  }).formatToParts(0)
  return parts.find((part) => part.type === 'currency')?.value ?? ''
}

/** 比率（0.5）→ `50%`；`null`（没有数据）→ `—`。 */
export function formatRate(rate: number | null): string {
  if (rate === null) return '—'
  return new Intl.NumberFormat(LOCALE, {
    style: 'percent',
    maximumFractionDigits: 0,
  }).format(rate)
}
