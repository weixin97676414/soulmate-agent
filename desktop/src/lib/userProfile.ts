import { AVATAR_MAX_SIZE, readImageAsDataUrl } from '@/lib/image'
// 出厂头像从搭子头像库里挑（与搭子用同一套图，风格才统一）
import { CUSTOM_AVATARS } from '@/services/avatarPack'

/**
 * 用户自己的资料（头像 + 昵称）。
 *
 * 存 **localStorage** 就够：它只影响**本机界面显示**（对话里的用户气泡、
 * 左上角标识），不参与任何后端逻辑 —— 走后端反而要为一个纯展示字段开接口。
 * 注意与「助手头像」区分：那是助手的（存在 assistants.json），这是用户自己的。
 */
const STORAGE_KEY = 'agent-desktop:user-profile'

export interface UserProfile {
  nickname: string
  avatar: string // data URL；空 = 未设置
}

/**
 * 出厂资料（产品要求）。
 *
 * - **昵称默认「宿主」**：原先默认是空串，于是气泡上那一行直接不显示 ——
 *   用户看到的是"自己的消息没有名字"，而别人的消息都有。给一个中性的默认名
 *   比留白好得多，而且他可以随时改。
 * - **头像默认从自定义搭子头像库里随机选**（见 `pickDefaultAvatar`）：
 *   原先用户那头像是 emoji 🙂 兜底，而搭子全是真实照片 —— 同一个气泡列里
 *   一边照片一边表情，看起来像没配完。
 */
const DEFAULT_NICKNAME = '宿主'

let cached: UserProfile | null = null

/** 出厂头像：从搭子头像库里随机挑一张（产品要求）。 */
function pickDefaultAvatar(): string {
  if (CUSTOM_AVATARS.length === 0) return ''
  return CUSTOM_AVATARS[Math.floor(Math.random() * CUSTOM_AVATARS.length)] ?? ''
}

export function loadUserProfile(): UserProfile {
  if (cached) return cached
  let profile: UserProfile
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (raw) {
      const saved = JSON.parse(raw) as Partial<UserProfile>
      profile = {
        // ⚠️ 昵称**不回落**到默认值：用户主动清空昵称是明确意图（他就是不想显示
        // 名字），每次读都塞回"宿主"会让"删掉名字"变成一个做不到的操作。
        nickname: saved.nickname ?? DEFAULT_NICKNAME,
        // 头像为空则补一张 —— 覆盖两种历史情况：老版本存了空串、或者上次随机
        // 挑的时候头像库还没加载出来。
        avatar: saved.avatar || pickDefaultAvatar(),
      }
    } else {
      profile = { nickname: DEFAULT_NICKNAME, avatar: pickDefaultAvatar() }
    }
  } catch {
    profile = { nickname: DEFAULT_NICKNAME, avatar: pickDefaultAvatar() }
  }
  cached = profile
  // ⚠️ **立刻落盘**：不写的话"随机挑一张"每次启动都会重来一遍，
  // 用户的头像会自己变。写一次它就定下来了，之后只有他自己能改。
  if (!localStorage.getItem(STORAGE_KEY)) saveUserProfile(profile)
  return cached
}

export function saveUserProfile(profile: UserProfile): void {
  cached = profile
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(profile))
  } catch {
    // 存不进去只影响"下次启动还记得吗"，不该中断当前会话
  }
  // 同页的其他组件（标题栏、消息气泡）靠自定义事件感知变化，
  // 而不是各自轮询 localStorage
  window.dispatchEvent(new CustomEvent('user-profile-changed'))
}

export async function pickUserAvatar(file: File): Promise<string> {
  return readImageAsDataUrl(file, AVATAR_MAX_SIZE)
}

/** 订阅资料变化（React 的 useEffect 里调用，返回退订函数） */
export function subscribeUserProfile(onChange: () => void): () => void {
  window.addEventListener('user-profile-changed', onChange)
  return () => window.removeEventListener('user-profile-changed', onChange)
}
