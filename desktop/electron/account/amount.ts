








const DECIMALS = 6
const SCALE = 10n ** BigInt(DECIMALS)


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
