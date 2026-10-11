/**
 * 金额的**展示**格式化。
 *
 * 后端下发的是 6 位小数字符串（如 `"30.000000"`）。这里只做"去掉尾随的 0"这种
 * 字符串层面的美容，**绝不做浮点运算**：显示要的是好看，而"比较有没有到账"
 * 用的是主进程里的 BigInt（见 electron/account/amount.ts），两边各司其职。
 */
export function formatToken(value: string | undefined | null): string {
  const text = (value ?? '').trim()
  if (!text) return '0'
  if (!text.includes('.')) return text
  const [whole, fraction = ''] = text.split('.')
  const trimmed = fraction.replace(/0+$/, '')
  return trimmed ? `${whole}.${trimmed}` : whole
}

/** 复制到剪贴板（项目里各组件都是内联调用，这里收成一个小工具避免重复）。 */
export async function copyText(text: string): Promise<boolean> {
  try {
    await navigator.clipboard.writeText(text)
    return true
  } catch {
    return false
  }
}
