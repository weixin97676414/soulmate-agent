import clsx from 'clsx'
import { Check } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'

import { AssistantAvatar } from '@/components/chat/AssistantFormModal'
import { Button, Input } from '@/components/ui'
import {
  loadUserProfile,
  pickUserAvatar,
  saveUserProfile,
  subscribeUserProfile,
} from '@/lib/userProfile'
import { resolveTheme, useAppStore } from '@/stores/appStore'
import type { ThemeId } from '@shared/bridge'




const SKINS: Array<{
  id: ThemeId
  name: string
  canvas: string
  brand: string
  group: 'light' | 'dark'
}> = [
  
  { id: 'light', name: '明亮', canvas: '#ffffff', brand: '#2563eb', group: 'light' },
  { id: 'dark', name: '夜间', canvas: '#16171a', brand: '#4d84f5', group: 'dark' },
  
  { id: 'sakura', name: '樱粉', canvas: '#fffafc', brand: '#db2777', group: 'light' },
  { id: 'plum', name: '暮紫', canvas: '#14101b', brand: '#a78bfa', group: 'dark' },
  
  { id: 'mint', name: '薄荷', canvas: '#f7fdfa', brand: '#059669', group: 'light' },
  { id: 'forest', name: '森野', canvas: '#0f1512', brand: '#34d399', group: 'dark' },
  
  { id: 'sky', name: '天空', canvas: '#f7fbff', brand: '#0284c7', group: 'light' },
  { id: 'ocean', name: '深海', canvas: '#0d131b', brand: '#38bdf8', group: 'dark' },
  
  { id: 'warm', name: '暖阳', canvas: '#fdf8f1', brand: '#c2410c', group: 'light' },
  { id: 'pine', name: '墨绿', canvas: '#0e1311', brand: '#2dd4bf', group: 'dark' },
  
  { id: 'apricot', name: '杏黄', canvas: '#fffdf6', brand: '#d97706', group: 'light' },
  { id: 'charcoal', name: '炭黑', canvas: '#141414', brand: '#94a3b8', group: 'dark' },
  
  { id: 'deepday', name: '晨蓝', canvas: '#f4f7ff', brand: '#4d6bfe', group: 'light' },
  { id: 'deepnight', name: '深空', canvas: '#06080f', brand: '#7b93ff', group: 'dark' },
]

const WALLPAPER_MAX_WIDTH = 1600

function SkinRow({
  title,
  group,
  current,
  onPick,
}: {
  title: string
  group: 'light' | 'dark'
  current: ThemeId
  onPick: (id: ThemeId) => void
}) {
  const list = SKINS.filter((skin) => skin.group === group)
  return (
    <div>
      <div className="mb-1.5 flex items-center gap-2">
        <span className="text-[12.5px] text-ink-soft">{title}</span>
        {current && SKINS.find((skin) => skin.id === current)?.group === group ? (
          <span className="text-[11px] text-brand">当前</span>
        ) : null}
      </div>
      <div className="flex flex-wrap gap-2">
        {list.map((skin) => {
          const active = current === skin.id
          return (
            <button
              key={skin.id}
              type="button"
              onClick={() => onPick(skin.id)}
              className={clsx(
                'no-drag flex items-center gap-2 rounded-[9px] border px-2.5 py-1.5 text-left whitespace-nowrap transition-colors',
                active ? 'border-brand bg-brand-soft' : 'border-line hover:border-brand/40',
              )}
            >
              <span
                className="h-[18px] w-[18px] shrink-0 rounded-full border"
                style={{ background: skin.canvas, borderColor: skin.brand }}
              />
              <span className="text-[12px] text-ink-soft">{skin.name}</span>
              {active ? <Check size={12} className="text-brand" /> : null}
            </button>
          )
        })}
      </div>
    </div>
  )
}








export function AppearanceSettings() {
  const theme = useAppStore((state) => state.theme)
  const setTheme = useAppStore((state) => state.setTheme)
  const wallpaper = useAppStore((state) => state.wallpaper)
  const setWallpaper = useAppStore((state) => state.setWallpaper)
  const wallpaperInputRef = useRef<HTMLInputElement>(null)
  const [wallpaperInfo, setWallpaperInfo] = useState('')

  const [profile, setProfile] = useState(() => loadUserProfile())
  const profileInputRef = useRef<HTMLInputElement>(null)
  useEffect(() => subscribeUserProfile(() => setProfile(loadUserProfile())), [])

  










  const activeSkin = resolveTheme(theme)

  
  
  
  
  
  
  const pick = (id: ThemeId) => {
    setTheme(id)
  }

  
  const pickWallpaper = async (file: File) => {
    const raw = await new Promise<string>((resolve, reject) => {
      const reader = new FileReader()
      reader.onload = () => resolve(String(reader.result))
      reader.onerror = () => reject(new Error('读取图片失败'))
      reader.readAsDataURL(file)
    })

    const scaled = await new Promise<string>((resolve) => {
      const image = new Image()
      image.onload = () => {
        const scale = Math.min(1, WALLPAPER_MAX_WIDTH / image.width)
        const canvas = document.createElement('canvas')
        canvas.width = Math.round(image.width * scale)
        canvas.height = Math.round(image.height * scale)
        const ctx = canvas.getContext('2d')
        if (!ctx) {
          setWallpaperInfo('')
          resolve(raw)
          return
        }
        ctx.drawImage(image, 0, 0, canvas.width, canvas.height)
        setWallpaperInfo(
          `原图 ${image.width}×${image.height}，压缩为 ${canvas.width}×${canvas.height} 保存（不裁剪，自适应窗口缩放）`,
        )
        resolve(canvas.toDataURL('image/jpeg', 0.82))
      }
      image.onerror = () => {
        setWallpaperInfo('')
        resolve(raw)
      }
      image.src = raw
    })

    setWallpaper(scaled)
  }

  return (
    <div className="max-w-[760px]">
      <h2 className="text-[15px] font-semibold text-ink">外观</h2>
      <p className="mt-1 text-[12.5px] leading-relaxed text-ink-soft">
        选一套日间皮肤、一套夜间皮肤 —— 右上角的切换按钮就在这两套之间切换。
        改动立即生效并记住。
      </p>

      <div className="mt-5 flex flex-col gap-5">
        {}
        <SkinRow title="日间皮肤" group="light" current={activeSkin} onPick={pick} />
        <SkinRow title="夜间皮肤" group="dark" current={activeSkin} onPick={pick} />
        <p className="text-[11px] leading-relaxed text-ink-faint">
          提示：点击上面任意一套皮肤即把它设为当前外观，并记住到对应的日/夜槽位。
        </p>

        {}
        <div>
          <div className="text-[12.5px] text-ink-soft">壁纸（可选）</div>
          <div className="mt-2 flex flex-wrap items-center gap-2">
            <Button variant="secondary" onClick={() => wallpaperInputRef.current?.click()}>
              {wallpaper ? '换一张' : '上传图片'}
            </Button>
            {wallpaper ? (
              <Button variant="secondary" onClick={() => setWallpaper(null)}>
                移除壁纸
              </Button>
            ) : null}
            <span className="text-[11px] leading-relaxed text-ink-faint">
              {wallpaper
                ? wallpaperInfo || '已设置。图片只存在本机。'
                : '用自己的图片当背景；不会裁剪，自动按窗口长宽缩放铺满。'}
            </span>
          </div>
          <input
            ref={wallpaperInputRef}
            type="file"
            accept="image/*"
            className="hidden"
            onChange={(event) => {
              const file = event.target.files?.[0]
              if (file) void pickWallpaper(file)
              event.target.value = ''
            }}
          />
        </div>

        {}
        <div>
          <div className="text-[12.5px] text-ink-soft">我的资料</div>
          <div className="mt-2 flex flex-wrap items-center gap-3">
            {profile.avatar ? (
              <AssistantAvatar
                profile={{ avatar: profile.avatar, emoji: '🙂', name: profile.nickname }}
                size={36}
              />
            ) : (
              <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-[8px] border border-line bg-canvas text-[15px]">
                🙂
              </span>
            )}
            <div className="flex flex-wrap items-center gap-2">
              <Input
                value={profile.nickname}
                onChange={(event) => {
                  const next = { ...profile, nickname: event.target.value }
                  setProfile(next)
                  saveUserProfile(next)
                }}
                placeholder="昵称（对话界面里显示的称呼）"
                
                
                aria-label="昵称（对话界面里显示的称呼）"
                className="h-8 w-[200px] text-[12.5px]"
              />
              <Button variant="secondary" onClick={() => profileInputRef.current?.click()}>
                {profile.avatar ? '更换头像' : '上传头像'}
              </Button>
              {profile.avatar ? (
                <Button
                  variant="secondary"
                  onClick={() => {
                    const next = { ...profile, avatar: '' }
                    setProfile(next)
                    saveUserProfile(next)
                  }}
                >
                  移除头像
                </Button>
              ) : null}
            </div>
            <input
              ref={profileInputRef}
              type="file"
              accept="image/*"
              className="hidden"
              onChange={async (event) => {
                const file = event.target.files?.[0]
                if (file) {
                  const avatar = await pickUserAvatar(file)
                  const next = { ...profile, avatar }
                  setProfile(next)
                  saveUserProfile(next)
                }
                event.target.value = ''
              }}
            />
            <span className="w-full text-[11px] leading-relaxed text-ink-faint">
              头像与昵称只存在本机，用于对话界面显示"你是谁"。
            </span>
          </div>
        </div>
      </div>
    </div>
  )
}
