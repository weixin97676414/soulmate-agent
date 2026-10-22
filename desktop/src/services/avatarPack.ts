






















const builtinModules = import.meta.glob<string>('../assets/avatar-pack/builtin/*.jpg', {
  eager: true,
  query: '?url',
  import: 'default',
})

export const BUILTIN_AVATARS: Record<string, string> = {}
for (const [path, url] of Object.entries(builtinModules)) {
  
  const id = path.split('/').pop()?.replace(/\.jpg$/i, '') ?? ''
  if (id) BUILTIN_AVATARS[id] = url
}

const customModules = import.meta.glob<string>('../assets/avatar-pack/custom/*.jpg', {
  eager: true,
  query: '?url',
  import: 'default',
})









export const CUSTOM_AVATARS: string[] = Object.entries(customModules)
  .sort(([a], [b]) => {
    const num = (p: string) => Number(p.split('/').pop()?.replace(/\.jpg$/i, '')) || 0
    return num(a) - num(b)
  })
  .map(([, url]) => url)


export function resolveAvatar(profile: {
  id?: string
  avatar?: string
}): string {
  const own = (profile.avatar ?? '').trim()
  if (own) return own
  return (profile.id && BUILTIN_AVATARS[profile.id]) || ''
}

const groupModules = import.meta.glob<string>('../assets/avatar-pack/groups/*.jpg', {
  eager: true,
  query: '?url',
  import: 'default',
})










export const GROUP_AVATARS: string[] = Object.entries(groupModules)
  .sort(([a], [b]) => {
    const num = (p: string) => Number(p.split('/').pop()?.replace(/\.jpg$/i, '')) || 0
    return num(a) - num(b)
  })
  .map(([, url]) => url)








function pickFromPool(pool: readonly string[], used: Iterable<string>, seed: string): string {
  if (pool.length === 0) return ''
  const taken = new Set(used)
  const free = pool.filter((url) => !taken.has(url))
  const candidates = free.length > 0 ? free : pool
  
  let hash = 0
  for (let i = 0; i < seed.length; i += 1) hash = (hash * 31 + seed.charCodeAt(i)) >>> 0
  return candidates[hash % candidates.length] ?? ''
}






export function pickAvatar(used: Iterable<string>, seed: string): string {
  return pickFromPool(CUSTOM_AVATARS, used, seed)
}








export function pickGroupAvatar(used: Iterable<string>, seed: string): string {
  return pickFromPool(GROUP_AVATARS, used, seed)
}








export function resolveGroupAvatar(group: { avatar?: string }): string {
  return (group.avatar ?? '').trim()
}
