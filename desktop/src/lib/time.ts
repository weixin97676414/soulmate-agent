
















function toDate(ms: number | null | undefined): Date | null {
  if (!ms) return null
  const date = new Date(ms)
  return Number.isNaN(date.getTime()) ? null : date
}

const pad = (value: number): string => String(value).padStart(2, '0')


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


export function formatFull(ms: number | null | undefined): string {
  const date = toDate(ms)
  if (!date) return ''
  return (
    `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())} ` +
    `${pad(date.getHours())}:${pad(date.getMinutes())}`
  )
}
