






export function formatToken(value: string | undefined | null): string {
  const text = (value ?? '').trim()
  if (!text) return '0'
  if (!text.includes('.')) return text
  const [whole, fraction = ''] = text.split('.')
  const trimmed = fraction.replace(/0+$/, '')
  return trimmed ? `${whole}.${trimmed}` : whole
}


export async function copyText(text: string): Promise<boolean> {
  try {
    await navigator.clipboard.writeText(text)
    return true
  } catch {
    return false
  }
}
