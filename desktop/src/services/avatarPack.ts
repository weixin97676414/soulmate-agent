/**
 * 随包的搭子头像包。
 *
 * ## 为什么头像要随包，而不是让用户去选文件
 *
 * 搭子的头像决定了它在列表、气泡、群聊里长什么样 —— 新用户第一眼看到的界面
 * 全是它。让内置搭子顶着一个 emoji（💫 / 💗）出现在这些位置，看起来像占位符
 * 没做完；而让新用户在第一次创建搭子时先去找一张图，是给"我想试一下"加门槛。
 *
 * ## 内置 / 自定义两套
 *
 * - **内置**：四个出厂搭子各有一张，按**搭子 id** 索引（不看中文名 ——
 *   名字用户能改，id 不会）。
 * - **自定义**：24 张随机池，给"没有头像的搭子"用（AI 创建的新搭子走这里）。
 *
 * ## 为什么用 `import.meta.glob` 而不是 `public/`
 *
 * `public/` 里的文件在打包后是**相对 `index.html` 的路径**，而 Electron 生产
 * 环境走的是 `file://` —— 手写 `/assets/x.png` 会指到磁盘根上去。交给 Vite 的
 * glob，它在构建时就把每张图转成正确（且带 hash 的）URL。
 */

/** 内置搭子的出厂头像：`{ 搭子 id: 图片 URL }` */
const builtinModules = import.meta.glob<string>('../assets/avatar-pack/builtin/*.jpg', {
  eager: true,
  query: '?url',
  import: 'default',
})

export const BUILTIN_AVATARS: Record<string, string> = {}
for (const [path, url] of Object.entries(builtinModules)) {
  // 文件名就是搭子 id（见 `core/build` 旁边的 pack_avatars 脚本）
  const id = path.split('/').pop()?.replace(/\.jpg$/i, '') ?? ''
  if (id) BUILTIN_AVATARS[id] = url
}

const customModules = import.meta.glob<string>('../assets/avatar-pack/custom/*.jpg', {
  eager: true,
  query: '?url',
  import: 'default',
})

/**
 * 自定义头像池。
 *
 * ⚠️ **按文件名里的数字排序**，不按 `Object.entries` 的返回顺序 ——
 * glob 的顺序取决于文件系统的枚举次序，同一台机器上两次构建都可能不同。
 * 顺序不稳定的话，"优先挑没被用过的"会变成每次都换一张，用户会觉得头像
 * 自己在变。
 */
export const CUSTOM_AVATARS: string[] = Object.entries(customModules)
  .sort(([a], [b]) => {
    const num = (p: string) => Number(p.split('/').pop()?.replace(/\.jpg$/i, '')) || 0
    return num(a) - num(b)
  })
  .map(([, url]) => url)

/** 一个搭子该显示哪张图：它自己的头像优先，其次内置包。都没有返回空串。 */
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

/**
 * 群头像池。
 *
 * ⚠️ 与搭子的 `CUSTOM_AVATARS` 是**两个池子**，不要合并：群和搭子出现在同一张
 * 列表里（左边的群列表 / 中间的成员头像），共用一套图会让用户觉得"这个群的头像
 * 好像某个搭子"。
 *
 * 排序理由同 `CUSTOM_AVATARS`（按文件名里的数字，不用 glob 的枚举顺序）。
 */
export const GROUP_AVATARS: string[] = Object.entries(groupModules)
  .sort(([a], [b]) => {
    const num = (p: string) => Number(p.split('/').pop()?.replace(/\.jpg$/i, '')) || 0
    return num(a) - num(b)
  })
  .map(([, url]) => url)

/**
 * 从候选池里挑一张：优先没被占用的，全占满了才允许重复。
 *
 * `seed` 决定池子里的落点（同一个 id 总是得到同一张，不会"每次打开都换一个样"）。
 * 注意这不影响"优先不重复"：`used` 变化时它会重新落在第一个空闲位上 ——
 * 那是**有意的**（新来的应该去填空缺，而不是继续挤在重复的那张上）。
 */
function pickFromPool(pool: readonly string[], used: Iterable<string>, seed: string): string {
  if (pool.length === 0) return ''
  const taken = new Set(used)
  const free = pool.filter((url) => !taken.has(url))
  const candidates = free.length > 0 ? free : pool
  // 稳定散列：让不同的 id 落在池子里不同的位置，而不是全挤在第一个
  let hash = 0
  for (let i = 0; i < seed.length; i += 1) hash = (hash * 31 + seed.charCodeAt(i)) >>> 0
  return candidates[hash % candidates.length] ?? ''
}

/**
 * 给一个**还没有头像**的搭子挑一张。
 *
 * 产品要求：优先挑当前没被别人用过的，全都用过了才允许重复。
 */
export function pickAvatar(used: Iterable<string>, seed: string): string {
  return pickFromPool(CUSTOM_AVATARS, used, seed)
}

/**
 * 给一个**还没有头像**的群挑一张。
 *
 * 规则与搭子那边一致：优先挑现有群都没用过的，全用过了才随机 ——
 * 用户的原话是"优先选择与现有群不重复的，如果现有群用了所有的头像，
 * 则随机选一张即可"。
 */
export function pickGroupAvatar(used: Iterable<string>, seed: string): string {
  return pickFromPool(GROUP_AVATARS, used, seed)
}

/**
 * 一个群该显示哪张图。
 *
 * 与 `resolveAvatar`（搭子）的区别：群**没有"内置包"**这一层 —— 四个出厂搭子
 * 是按 id 硬绑的图，而群没有出厂群，所以只有"自己设过的"和"没设过"（空串，
 * 由 `pickGroupAvatar` 兜底）两种。
 */
export function resolveGroupAvatar(group: { avatar?: string }): string {
  return (group.avatar ?? '').trim()
}
