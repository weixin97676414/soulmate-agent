/**
 * 金额解析（后端下发的是**字符串**，6 位小数，如 `"30.000000"`）。
 *
 * 文档 §2 明确要求客户端不要用浮点直接算，而"到账了没有"这个判断恰恰是
 * 浮点最容易骗人的地方：`0.1 + 0.2 !== 0.3` 那类误差会让"余额变了"时有时无，
 * 表现就是**充值到了、界面却一直不提示**，而用户完全没法自己排查。
 *
 * 所以统一转成"最小单位"的 `BigInt`（1 Token = 10^6）再比大小。
 */
const DECIMALS = 6
const SCALE = 10n ** BigInt(DECIMALS)

/** 把 `"30.000000"` 转成 `30000000n`。解析不了按 0 处理（宁可不提示，也不要报错）。 */
export function parseAmount(value: string | null | undefined): bigint {
  const text = (value ?? '').trim()
  if (!text) return 0n
  const negative = text.startsWith('-')
  const digits = negative ? text.slice(1) : text
  const [whole = '', fraction = ''] = digits.split('.')
  const wholePart = whole.replace(/[^0-9]/g, '') || '0'
  const fractionPart = fraction.replace(/[^0-9]/g, '').slice(0, DECIMALS).padEnd(DECIMALS, '0')
  const units = BigInt(wholePart) * SCALE + BigInt(fractionPart || '0')
  return negative ? -units : units
}
