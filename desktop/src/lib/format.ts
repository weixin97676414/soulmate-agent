

























const LOCALE = 'zh-CN'







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
    
    
    hour12: false,
  }).format(date)
}








export function formatTokens(value: number): string {
  return new Intl.NumberFormat(LOCALE, {
    notation: 'compact',
    maximumFractionDigits: 1,
  }).format(value)
}











export function formatCost(cost: number | null, currency: string): string {
  if (cost === null) return '未配置价格'
  
  const digits = cost > 0 && cost < 0.01 ? 4 : 2
  return new Intl.NumberFormat(LOCALE, {
    style: 'currency',
    currency: currency === 'USD' ? 'USD' : 'CNY',
    currencyDisplay: 'narrowSymbol',
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  }).format(cost)
}









export function currencySymbol(currency: string): string {
  const parts = new Intl.NumberFormat(LOCALE, {
    style: 'currency',
    currency: currency === 'USD' ? 'USD' : 'CNY',
    currencyDisplay: 'narrowSymbol',
  }).formatToParts(0)
  return parts.find((part) => part.type === 'currency')?.value ?? ''
}


export function formatRate(rate: number | null): string {
  if (rate === null) return '—'
  return new Intl.NumberFormat(LOCALE, {
    style: 'percent',
    maximumFractionDigits: 0,
  }).format(rate)
}
