import { Info } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'

import { AssistantAvatar } from '@/components/chat/AssistantFormModal'
import { Button, Input, Select } from '@/components/ui'
import { AVATAR_MAX_SIZE, readImageAsDataUrl } from '@/lib/image'
import { useAppStore } from '@/stores/appStore'
import { useAssistantStore } from '@/stores/assistantStore'
import type { AssistantProfile } from '@/types'































const DONE_KEY = 'soulmate.quick-setup.done'







const NICKNAME_HINT =
  '（用户未设置昵称前使用，设置昵称后需要你更改为用户设置的昵称或约定称呼）'








const NICKNAME_PREFIX = '用户为你设定的昵称：'


const nicknameLine = (value: string) => `${NICKNAME_PREFIX}${value}`









const GENDER_PREFIX = '性别：'


function normalizeGender(raw: string): string {
  return raw === '男' || raw === '女' ? raw : ''
}


const ADDRESS_PREFIX = '用户称呼：'

function readDone(): string[] {
  try {
    const raw = window.localStorage.getItem(DONE_KEY)
    const parsed: unknown = raw ? JSON.parse(raw) : []
    return Array.isArray(parsed) ? parsed.filter((item): item is string => typeof item === 'string') : []
  } catch {
    
    
    return []
  }
}

function markDone(id: string): void {
  try {
    const done = readDone()
    if (done.includes(id)) return
    window.localStorage.setItem(DONE_KEY, JSON.stringify([...done, id]))
  } catch {
    
  }
}












function applyNickname(identity: string, nickname: string): string {
  if (identity.includes(NICKNAME_HINT)) {
    
    return identity.split(NICKNAME_HINT).join(nicknameLine(nickname))
  }
  
  
  
  const updated = identity.replace(
    new RegExp(`${NICKNAME_PREFIX}[^。\\n]*`, 'g'),
    nicknameLine(nickname),
  )
  if (updated !== identity) return updated
  return `${identity.trimEnd()}\n${nicknameLine(nickname)}\n`
}


function applyGender(identity: string, gender: string): string {
  const line = new RegExp(`^${GENDER_PREFIX}.*$`, 'm')
  if (line.test(identity)) return identity.replace(line, `${GENDER_PREFIX}${gender}`)
  return `${identity.trimEnd()}\n${GENDER_PREFIX}${gender}\n`
}


function applyAddress(user: string, address: string): string {
  const line = new RegExp(`^${ADDRESS_PREFIX}.*$`, 'm')
  if (line.test(user)) return user.replace(line, `${ADDRESS_PREFIX}${address}`)
  return `${user.trimEnd()}\n${ADDRESS_PREFIX}${address}\n`
}







function currentValue(content: string, prefix: string): string {
  const match = new RegExp(`${prefix}([^。\\n]*)`).exec(content)
  return match ? match[1].trim() : ''
}

function fileName(
  files: Array<{ name: string; content: string }>,
  name: string,
): string {
  return files.find((item) => item.name === name)?.content ?? ''
}












function parseWakeWords(text: string): string[] {
  return text
    .split(/[，,、\s]+/)
    .map((word) => word.trim())
    .filter(Boolean)
}

export function QuickSetupCard({ assistant }: { assistant: AssistantProfile }) {
  const api = useAppStore((state) => state.api)
  const save = useAssistantStore((state) => state.save)
  const preview = useAssistantStore((state) => state.preview)
  const reload = useAssistantStore((state) => state.load)

  const [avatar, setAvatar] = useState(assistant.avatar)
  const [nickname, setNickname] = useState(assistant.nickname)
  const [gender, setGender] = useState('')
  const [address, setAddress] = useState('')
  









  const [wakeWords, setWakeWords] = useState((assistant.voice?.wake_words ?? []).join('，'))
  const [saving, setSaving] = useState(false)
  const [leaving, setLeaving] = useState(false)
  const [error, setError] = useState('')
  
  const [done, setDone] = useState(() => readDone().includes(assistant.id))
  const fileRef = useRef<HTMLInputElement>(null)

  
  const baseline = useRef({
    avatar: assistant.avatar,
    nickname: assistant.nickname,
    dirty: false,
    saved: false,
  })

  





  useEffect(() => {
    let cancelled = false
    void (async () => {
      if (!api || done) return
      try {
        const payload = await api.getPersonaFiles(assistant.id)
        if (cancelled) return
        const identity = fileName(payload.files, 'IDENTITY.md')
        const user = fileName(payload.files, 'USER.md')
        
        
        
        setGender(normalizeGender(currentValue(identity, GENDER_PREFIX)))
        setAddress(currentValue(user, ADDRESS_PREFIX))
        setNickname((value) => value || currentValue(identity, '用户为你设定的昵称：'))
      } catch (failure) {
        
        console.error('读取人格文件失败', failure)
      }
    })()
    return () => {
      cancelled = true
    }
  }, [api, assistant.id, done])

  
  useEffect(() => {
    const snapshot = baseline.current
    return () => {
      if (snapshot.dirty && !snapshot.saved) {
        preview(assistant.id, { avatar: snapshot.avatar, nickname: snapshot.nickname })
      }
    }
  }, [assistant.id, preview])

  const pushPreview = (changes: Partial<AssistantProfile>): void => {
    baseline.current.dirty = true
    preview(assistant.id, changes)
  }

  const pickAvatar = async (file: File | undefined): Promise<void> => {
    if (!file) return
    const dataUrl = await readImageAsDataUrl(file, AVATAR_MAX_SIZE)
    setAvatar(dataUrl)
    pushPreview({ avatar: dataUrl }) 
  }

  const submit = async (): Promise<void> => {
    if (!api) return
    setSaving(true)
    setError('')
    try {
      
      
      
      
      
      
      await save({
        ...assistant,
        avatar,
        nickname: nickname.trim(),
        voice: { ...assistant.voice, wake_words: parseWakeWords(wakeWords) },
      })
      
      const payload = await api.getPersonaFiles(assistant.id)
      const identity = fileName(payload.files, 'IDENTITY.md')
      const user = fileName(payload.files, 'USER.md')
      const nicknameValue = nickname.trim()
      if (nicknameValue) {
        await api.writePersonaFile(
          assistant.id,
          'IDENTITY.md',
          applyGender(applyNickname(identity, nicknameValue), gender),
        )
      } else if (gender) {
        await api.writePersonaFile(assistant.id, 'IDENTITY.md', applyGender(identity, gender))
      }
      if (address.trim()) {
        await api.writePersonaFile(assistant.id, 'USER.md', applyAddress(user, address.trim()))
      }
      baseline.current.saved = true
      markDone(assistant.id)
      
      setLeaving(true)
      window.setTimeout(() => {
        setLeaving(false)
        setDone(true)
        
        void reload()
      }, 160)
    } catch (failure) {
      
      
      setError(
        `保存失败，请重试：${failure instanceof Error ? failure.message : String(failure)}`,
      )
    } finally {
      setSaving(false)
    }
  }

  if (done) {
    return (
      <div className="mx-2.5 mb-1 flex items-center gap-1.5 rounded-[8px] border border-line-soft bg-canvas px-2.5 py-1.5 text-[11.5px] text-ink-faint">
        <Info size={12} className="shrink-0" aria-hidden="true" />
        {

}
        <span>点击搭子头像，可修改配置</span>
      </div>
    )
  }

  return (
    <div
      className={
        'mx-2.5 mb-1 rounded-[8px] border border-line-soft bg-canvas px-2.5 py-2 ' +
        'transition-opacity duration-[160ms] motion-reduce:transition-none ' +
        (leaving ? 'opacity-0' : 'opacity-100')
      }
    >
      <div className="mb-1.5 text-[11.5px] font-medium text-ink-soft">快速设置</div>

      <div className="space-y-1.5">
        <div className="flex items-center gap-2">
          <span className="w-[52px] shrink-0 text-[11.5px] text-ink-soft">头像</span>
          {




}
          <AssistantAvatar profile={{ ...assistant, avatar }} size={32} />
          <input
            ref={fileRef}
            type="file"
            accept="image/*"
            className="hidden"
            onChange={(event) => void pickAvatar(event.target.files?.[0])}
          />
          <Button
            size="sm"
            className="ml-auto h-7"
            disabled={saving}
            onClick={() => fileRef.current?.click()}
          >
            选择图片
          </Button>
        </div>

        <div className="flex items-center gap-2">
          <span className="w-[52px] shrink-0 text-[11.5px] text-ink-soft">昵称</span>
          <Input
            value={nickname}
            maxLength={24}
            placeholder="它叫什么"
            
            
            aria-label="昵称"
            className="h-8 min-w-0 flex-1 text-[12.5px]"
            disabled={saving}
            onChange={(event) => {
              setNickname(event.target.value)
              pushPreview({ nickname: event.target.value })
            }}
          />
        </div>

        <div className="flex items-center gap-2">
          <span className="w-[52px] shrink-0 text-[11.5px] text-ink-soft">性别</span>
          <Select
            value={gender}
            aria-label="性别"
            className="h-8 min-w-0 flex-1 text-[12.5px]"
            disabled={saving}
            onChange={(event) => setGender(event.target.value)}
          >
            <option value="">暂不设置</option>
            <option value="男">男</option>
            <option value="女">女</option>
          </Select>
        </div>

        <div className="flex items-center gap-2">
          <span className="w-[52px] shrink-0 text-[11.5px] text-ink-soft">称呼你</span>
          <Input
            value={address}
            maxLength={24}
            placeholder="它该怎么叫你"
            aria-label="怎么称呼你"
            className="h-8 min-w-0 flex-1 text-[12.5px]"
            disabled={saving}
            onChange={(event) => setAddress(event.target.value)}
          />
        </div>

        <div className="flex items-center gap-2">
          {



}
          <span className="w-[52px] shrink-0 text-[11.5px] whitespace-nowrap text-ink-soft">
            语音唤醒
          </span>
          <Input
            value={wakeWords}
            placeholder="喊它说什么，多个用逗号隔开"
            
            aria-label="语音唤醒"
            className="h-8 min-w-0 flex-1 text-[12.5px]"
            disabled={saving}
            onChange={(event) => setWakeWords(event.target.value)}
          />
        </div>
      </div>

      {






}
      <Button
        size="sm"
        variant="primary"
        className="mt-2 w-full"
        disabled={saving}
        onClick={() => void submit()}
      >
        {saving ? '保存中…' : '保存'}
      </Button>

      {error ? (
        
        <p role="status" aria-live="polite" className="mt-1 text-[11.5px] break-words text-danger">
          {error}
        </p>
      ) : null}
    </div>
  )
}
