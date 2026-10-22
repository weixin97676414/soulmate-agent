import { AVATAR_MAX_SIZE, readImageAsDataUrl } from '@/lib/image'

import { CUSTOM_AVATARS } from '@/services/avatarPack'








const STORAGE_KEY = 'agent-desktop:user-profile'

export interface UserProfile {
  nickname: string
  avatar: string 
}











const DEFAULT_NICKNAME = '宿主'

let cached: UserProfile | null = null


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
        
        
        nickname: saved.nickname ?? DEFAULT_NICKNAME,
        
        
        avatar: saved.avatar || pickDefaultAvatar(),
      }
    } else {
      profile = { nickname: DEFAULT_NICKNAME, avatar: pickDefaultAvatar() }
    }
  } catch {
    profile = { nickname: DEFAULT_NICKNAME, avatar: pickDefaultAvatar() }
  }
  cached = profile
  
  
  if (!localStorage.getItem(STORAGE_KEY)) saveUserProfile(profile)
  return cached
}

export function saveUserProfile(profile: UserProfile): void {
  cached = profile
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(profile))
  } catch {
    
  }
  
  
  window.dispatchEvent(new CustomEvent('user-profile-changed'))
}

export async function pickUserAvatar(file: File): Promise<string> {
  return readImageAsDataUrl(file, AVATAR_MAX_SIZE)
}


export function subscribeUserProfile(onChange: () => void): () => void {
  window.addEventListener('user-profile-changed', onChange)
  return () => window.removeEventListener('user-profile-changed', onChange)
}
