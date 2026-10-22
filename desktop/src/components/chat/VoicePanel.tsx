















































import { useEffect, useMemo, useState } from 'react'
import clsx from 'clsx'
import { ChevronUp, X } from 'lucide-react'

import { voiceSteps } from '@/components/chat/VoiceGuide'
import { ModelDownloadCard } from '@/components/ModelDownloadCard'
import { Field, Input, Select } from '@/components/ui'
import { useCurrentGroup } from '@/lib/currentSubject'
import {
  VOICE_COMMANDS,
  VOICE_COMMAND_BY_ID,
  VOICE_COMMAND_GROUPS,
  commandWord,
  type VoiceCommandGroup,
  type VoiceCommandSpec,
} from '@/services/voiceCommands'
import { useAppStore } from '@/stores/appStore'
import { listAudioInputs, type AudioInput } from '@/services/voiceCapture'
import { useAssistantStore } from '@/stores/assistantStore'
import { useGroupStore } from '@/stores/groupStore'
import { useModelHubStore } from '@/stores/modelHubStore'
import { useVoiceSessionStore, type VoicePhase } from '@/stores/voiceSessionStore'
import type { AppSettings, AssistantProfile } from '@/types'

export interface VoicePanelProps {
  








  globalOnly?: boolean
  phase?: VoicePhase
  






  scope?: 'global' | 'standby'
  
  heard?: string
  
  lastHit?: string
  
  pending?: string
  






  onDisable?: () => void
  onClose: () => void
}


function phaseText(phase: VoicePhase, scope: 'global' | 'standby', words: {
  enable: string
  send: string
  wakes: string[]
}): string {
  switch (phase) {
    case 'global':
      return `在等「${words.enable}」`
    case 'standby':
      return scope === 'standby'
        ? `在听唤醒词${words.wakes.length ? `（${words.wakes.join(' / ')}）` : ''}`
        : '在听唤醒词…'
    case 'listening':
      return '我在听，说完停顿一下'
    case 'recognizing':
      return '正在识别…'
    case 'awaiting':
      return `待令中 —— 说「${words.send}」才发出去`
    default:
      return '语音功能已关闭'
  }
}











const GROUP_NOTES: Record<VoiceCommandGroup, string> = {
  对话: '对话页随时可用',
  导航: '任何页面可用',
  面板: '对应面板可见时可用',
  助手: '助手栏可见时可用',
  确认: '对应弹窗出现时才可用',
}







const SCOPE_NOTE_CLASS =
  'rounded-[6px] bg-brand-soft px-1.5 py-0.5 text-[10.5px] font-medium text-brand'







function CommandRow({
  spec,
  word,
  onSave,
}: {
  spec: VoiceCommandSpec
  word: string
  onSave: (next: string) => void
}) {
  const [draft, setDraft] = useState(word)
  useEffect(() => setDraft(word), [word])

  return (
    <div className="flex items-center gap-2">
      <span
        title={spec.hint ?? spec.label}
        className="w-[74px] shrink-0 truncate text-[11.5px] text-ink-soft"
      >
        {spec.label}
      </span>
      <Input
        value={draft}
        onChange={(event) => setDraft(event.target.value)}
        onBlur={() => {
          const next = draft.trim()
          if (next && next !== word) onSave(next)
          else setDraft(word)
        }}
      />
      {spec.dangerous ? (
        <span className="shrink-0 text-[10.5px] text-warning" title="会真的执行/放行操作">
          危险
        </span>
      ) : null}
    </div>
  )
}

export function VoicePanel({
  globalOnly = false,
  phase = 'off',
  scope = 'global',
  heard = '',
  lastHit = '',
  pending = '',
  onDisable,
  onClose,
}: VoicePanelProps) {
  const settings = useAppStore((state) => state.settings)
  
  const voiceModel = useModelHubStore((state) => state.models.voice)
  const reloadSettings = useAppStore((state) => state.reloadSettings)
  const activeId = useAssistantStore((state) => state.activeId)
  const assistants = useAssistantStore((state) => state.assistants)
  const saveAssistant = useAssistantStore((state) => state.save)
  const [saving, setSaving] = useState(false)

  const activeAssistant = useMemo<AssistantProfile | undefined>(
    () => assistants.find((item) => item.id === activeId),
    [assistants, activeId],
  )

  











  const activeGroup = useCurrentGroup()
  const groups = useGroupStore((state) => state.groups)
  const updateGroup = useGroupStore((state) => state.updateGroup)

  const globalVoice = settings?.voice
  const assistantVoice = activeAssistant?.voice
  
  const wakeWords = activeGroup ? (activeGroup.wake_words ?? []) : (assistantVoice?.wake_words ?? [])

  
  
  const wakeWordsText = wakeWords.filter(Boolean).join('，')
  const [wakeDraft, setWakeDraft] = useState(wakeWordsText)
  useEffect(() => setWakeDraft(wakeWordsText), [wakeWordsText])

  
  const saveGlobal = async (changes: Partial<AppSettings['voice']>) => {
    const api = useAppStore.getState().api
    const current = useAppStore.getState().settings
    if (!api || !current) return
    setSaving(true)
    try {
      await api.saveSettings({ ...current, voice: { ...current.voice, ...changes } })
      await reloadSettings()

      
      
      
      
      
      
      
      
      
      if ('startup_mode' in changes) useVoiceSessionStore.getState().bootstrap()
      } finally {
      setSaving(false)
      }
      }

  const saveAssistantVoice = async (changes: Partial<AssistantProfile['voice']>) => {
    const target = activeAssistant
    if (!target) return
    setSaving(true)
    try {
      await saveAssistant({ ...target, voice: { ...target.voice, ...changes } })
    } finally {
      setSaving(false)
    }
  }

  










  const saveSubjectWakeWords = async (words: string[]) => {
    if (activeGroup) {
      setSaving(true)
      try {
        await updateGroup(activeGroup.id, { wake_words: words })
      } finally {
        setSaving(false)
      }
      return
    }
    await saveAssistantVoice({ wake_words: words })
  }

  
  const overrides = globalVoice?.command_words ?? {}
  const disabledCommands = globalVoice?.disabled_commands
  
















  const listedSpecs = useMemo(() => {
    const disabled = disabledCommands ?? []
    return VOICE_COMMANDS.filter((spec) => !disabled.includes(spec.id))
  }, [disabledCommands])

  





  














  const wordRows: Array<{ key: 'send_word' | 'cancel_word'; label: string; hint: string }> = [
    { key: 'send_word', label: '发送词', hint: '说完说它才发出去' },
    
    
    
    { key: 'cancel_word', label: '清空输入栏', hint: '清空刚说进输入栏的那一句' },
  ]

  const statusWords = {
    enable: (globalVoice?.enable_word ?? '').trim() || '打开语音',
    send: (assistantVoice?.send_word ?? globalVoice?.send_word ?? '发送').trim() || '发送',
    
    wakes: wakeWords.filter(Boolean),
  }

  
  const [howtoOpen, setHowtoOpen] = useState(false)

  
  
  
  
  
  
  const micDeviceId = useVoiceSessionStore((state) => state.micDeviceId)
  const setMicDevice = useVoiceSessionStore((state) => state.setMicDevice)
  const micDeviceFellBack = useVoiceSessionStore((state) => state.micDeviceFellBack)
  const [micInputs, setMicInputs] = useState<AudioInput[]>([])
  







  const [micInputsLoaded, setMicInputsLoaded] = useState(false)
  useEffect(() => {
    
    
    
    
    let alive = true
    void listAudioInputs().then((items) => {
      if (!alive) return
      setMicInputs(items)
      setMicInputsLoaded(true)
    })
    return () => {
      alive = false
    }
  }, [])
  











  











  
  const commandGroups = useMemo(
    () =>
      VOICE_COMMAND_GROUPS.map((group) => ({
        group,
        specs: listedSpecs.filter((spec) => spec.group === group),
      })).filter((item) => item.specs.length > 0),
    [listedSpecs],
  )

  











  const wakeCollision = (() => {
    const own = (wakeDraft ?? '')
      .split(/[，,、\s]+/)
      .map((word) => word.trim())
      .filter(Boolean)
    if (own.length === 0) return null

    












    const others = [
      ...groups
        .filter((item) => item.id !== activeGroup?.id)
        .map((item) => ({ name: item.name, words: item.wake_words ?? [] })),
      ...assistants
        .filter((item) => item.id !== activeAssistant?.id)
        .map((item) => ({
          name: item.nickname || item.name,
          words: item.voice?.wake_words ?? [],
        })),
    ]
    for (const other of others) {
      const theirs = other.words.filter(Boolean)
      const hit = own.find((word) => theirs.includes(word))
      if (hit) return { word: hit, name: other.name }
    }
    return null
  })()

  
  
  const steps = voiceSteps({
    enableWord: statusWords.enable,
    disableWord: (globalVoice?.disable_word ?? '').trim() || '关闭语音',
    wakeWord: statusWords.wakes[0] ?? '',
    sendWord: statusWords.send,
    cancelWord: (globalVoice?.cancel_word ?? '清空').trim() || '清空',
    
    
    
    confirmWord: commandWord(VOICE_COMMAND_BY_ID['confirm.allow'], overrides),
    rejectWord: commandWord(VOICE_COMMAND_BY_ID['confirm.reject'], overrides),
  })

  return (
    
    
    
    
    <div
      className={clsx(
        'flex flex-col',
        globalOnly
          ? 
            
            'mt-2'
          : 'absolute inset-0 z-20 overflow-hidden rounded-[12px] border border-line bg-elevated',
      )}
    >
      {}
      {globalOnly ? null : (
      <div className="flex shrink-0 items-start justify-between gap-2 border-b border-line px-4 pt-3.5 pb-2.5">
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <h4 className="text-[13px] font-semibold text-ink">语音设置</h4>
            {saving ? <span className="text-[11px] text-ink-faint">保存中…</span> : null}
          </div>
          <p className="mt-0.5 text-[11.5px] leading-relaxed text-ink-soft">
            {phaseText(phase, scope, statusWords)}
            {heard ? <span className="text-ink-faint"> · 刚听到「{heard}」</span> : null}
            {lastHit ? <span className="text-brand"> · 唤醒了</span> : null}
          </p>
          {






}
          {voiceModel?.installed ? (
            <p className="mt-1.5 rounded-[8px] border border-brand/25 bg-brand-soft px-3 py-2 text-[12.5px] leading-relaxed text-ink">
              已加载本地语音识别模型，可
              <b className="font-semibold">免费</b>
              使用。如果觉得体验不理想，可自行二次开发。
            </p>
          ) : (
            <p className="mt-1.5 rounded-[8px] border border-warning/30 bg-warning-soft px-3 py-2 text-[12.5px] leading-relaxed text-warning">
              还没有下载语音识别模型，语音对话与语音命令暂时都用不了。在下面点「开始下载」装好即可
              —— 识别在本机跑，不花钱，也不上传录音。
            </p>
          )}
        </div>
        <button
          type="button"
          onClick={onClose}
          aria-label="收起语音设置"
          className="shrink-0 rounded-[6px] p-1 text-ink-faint hover:bg-hover hover:text-ink"
        >
          <X size={14} />
        </button>
      </div>
      )}

      {
}
      <div className="min-h-0 flex-1 overflow-y-auto px-4 pt-3 pb-1">
        {pending ? (
          <div className="mb-2 rounded-[8px] border border-brand/30 bg-brand-soft px-2.5 py-1.5 text-[11.5px] text-brand">
            待发出：{pending}
          </div>
        ) : null}

        {








}
        {!globalOnly && !voiceModel?.installed ? (
          <ModelDownloadCard modelKey="voice" className="mb-2.5" />
        ) : null}

        {
















}
        {globalOnly ? null : (
        <div className="mb-2.5 rounded-[10px] border border-line bg-panel">
          <button
            type="button"
            onClick={() => setHowtoOpen((prev) => !prev)}
            aria-expanded={howtoOpen}
            className="flex w-full items-center gap-1.5 px-3 py-2"
          >
            <ChevronUp
              size={13}
              className={clsx(
                'shrink-0 text-ink-faint transition-transform',
                howtoOpen ? '' : 'rotate-180',
              )}
            />
            <span className="text-[12px] font-semibold text-ink">对话语音怎么用</span>
            <span className="text-[10.5px] text-ink-faint">{howtoOpen ? '收起' : '展开'}</span>
          </button>
          {howtoOpen ? (
            <div className="border-t border-line-soft px-3 py-2.5">
              <ol className="flex flex-col gap-1.5">
                {steps.map(([title, detail], index) => (
                  <li key={title} className="flex gap-2 text-[11.5px] leading-relaxed text-ink-soft">
                    <span className="mt-[3px] flex h-4 w-4 shrink-0 items-center justify-center rounded-full bg-brand/15 text-[10px] font-semibold text-brand">
                      {index + 1}
                    </span>
                    <span>
                      <b className="text-ink">{title}</b>
                      <span className="text-ink-soft">：{detail}</span>
                    </span>
                  </li>
                ))}
              </ol>
            </div>
          ) : null}
        </div>
        )}

        {













}
      {globalOnly ? null : (
      <div className="mt-2.5 rounded-[10px] border border-line bg-panel px-3 py-2.5">
        <div className="flex items-baseline justify-between gap-2">
          <h5 className="text-[12.5px] font-semibold text-ink">
            {activeGroup
              ? activeGroup.name
              : activeAssistant
                ? activeAssistant.nickname || activeAssistant.name
                : '当前助手'}
          </h5>
          {

}
          <span className={SCOPE_NOTE_CLASS}>
            {activeGroup ? '只对这个群生效' : '只对这个助手生效'}
          </span>
        </div>

        {activeGroup || activeAssistant ? (
          <div className="mt-2 flex flex-col gap-2.5">
            <Field
              label="唤醒词"
              
              
              
              hint={
                activeGroup
                  ? '说了它才切到这个群。多个用逗号隔开；清空 = 不再用语音进这个群'
                  : '说了它才切到这个助手。多个用逗号隔开；清空 = 按名字重新生成'
              }
            >
              <Input
                value={wakeDraft}
                onChange={(event) => setWakeDraft(event.target.value)}
                onBlur={() => {
                  const parsed = wakeDraft
                    .split(/[，,、\s]+/)
                    .map((word) => word.trim())
                    .filter(Boolean)
                  setWakeDraft(parsed.join('，'))
                  void saveSubjectWakeWords(parsed)
                }}
              />
            </Field>

            {wakeCollision ? (
              <p className="rounded-[8px] border border-warning/30 bg-warning-soft px-2.5 py-1.5 text-[11.5px] leading-relaxed text-warning">
                「{wakeCollision.word}」已经被「{wakeCollision.name}」用了。同一个唤醒词会让"喊谁醒谁"变成碰运气 —— 说这个词会固定切到排序靠前的那个，所以两边都改成不同的词才准。
              </p>
            ) : null}
          </div>
        ) : (
          <p className="mt-2 text-[11.5px] text-ink-faint">还没有选中的助手。</p>
        )}
      </div>
      )}

        {}
      <div className="mt-2.5 rounded-[10px] border border-line bg-panel px-3 py-2.5">
        <div className="flex items-baseline justify-between gap-2">
          <h5 className="text-[12.5px] font-semibold text-ink">全局设置</h5>
          {

}
          <span className={SCOPE_NOTE_CLASS}>语音执行各种操作</span>
        </div>

        <div className="mt-2 flex flex-col gap-2.5">
          <Field
            label="启动后"
            
            
            
            hint="麦克风要不要一直开着等指令 / 等助手（第一项是完全关闭，要回来改档才能用语音）"
          >
            <Select
              
              
              
              value={globalVoice?.startup_mode ?? 'global'}
              onChange={(event) =>
                void saveGlobal({
                  startup_mode: event.target.value as AppSettings['voice']['startup_mode'],
                })
              }
            >
              <option value="off">应用不在后台等待</option>
              <option value="global">说出指令随时开启（推荐）</option>
              <option value="all">全体助手直接待命</option>
            </Select>
          </Field>

          {








}
          <Field
            label="麦克风设备"
            hint={
              micDeviceFellBack
                ? '上次选的麦克风不在了（可能已拔掉或换了接口），已改用系统默认。可以在这里重新选一个。'
                : !micInputsLoaded
                  ? '正在读取设备…'
                  : micInputs.length === 0
                    ? '没检测到可用的麦克风（可能还没授权）。授权或插好设备后，重新打开这个面板即可。'
                    : '不选就用系统默认设备；选好立即生效（麦克风开着时会用新设备重开）。换了耳麦后若提示打不开，在这里换一个试试。'
            }
          >
            <Select
              value={micDeviceId}
              
              disabled={!micInputsLoaded}
              
              
              onChange={(event) => setMicDevice(event.target.value)}
            >
              {!micInputsLoaded ? <option value="">正在读取设备…</option> : null}
              <option value="">系统默认</option>
              {micInputs.map((item) => (
                <option key={item.deviceId} value={item.deviceId}>
                  {item.label}
                </option>
              ))}
              {

}
              {micDeviceId && !micInputs.some((item) => item.deviceId === micDeviceId) ? (
                <option value={micDeviceId}>上次选择的麦克风（当前枚举不到）</option>
              ) : null}
            </Select>
          </Field>

          <div className="grid grid-cols-2 gap-2.5">
            {




}
            <Field
              label="打开语音"
              hint="念出打开语音指令后，全部助手进入待命唤醒状态"
            >
              <Input
                defaultValue={globalVoice?.enable_word ?? ''}
                onBlur={(event) =>
                  void saveGlobal({ enable_word: event.target.value.trim() || '打开语音' })
                }
              />
            </Field>
            <Field label="关闭语音" hint="念出关闭语音之后，随时关闭语音功能">
              <Input
                defaultValue={globalVoice?.disable_word ?? ''}
                onBlur={(event) =>
                  void saveGlobal({ disable_word: event.target.value.trim() || '关闭语音' })
                }
              />
            </Field>
          </div>

          {











}
          <div className="grid grid-cols-2 gap-2.5">
            {wordRows.map((row) => (
              <Field key={row.key} label={row.label} hint={row.hint}>
                <Input
                  defaultValue={globalVoice?.[row.key] ?? ''}
                  onBlur={(event) => {
                    const next = event.target.value.trim()
                    if (next) void saveGlobal({ [row.key]: next })
                  }}
                />
              </Field>
            ))}
          </div>

          {


















}
          {commandGroups.map(({ group, specs }) => (
            <div key={group} className="flex flex-col gap-2 border-t border-line-soft pt-2.5">
              <div className="flex items-baseline justify-between gap-2">
                <span className="text-[11px] font-medium text-ink-soft">{group}</span>
                <span className="text-[10.5px] text-ink-faint">{GROUP_NOTES[group]}</span>
              </div>
              <div className="grid grid-cols-2 gap-2.5">
                {specs.map((spec) => (
                  <CommandRow
                    key={spec.id}
                    spec={spec}
                    word={commandWord(spec, overrides)}
                    onSave={(next) =>
                      void saveGlobal({ command_words: { ...overrides, [spec.id]: next } })
                    }
                  />
                ))}
              </div>
            </div>
          ))}
        </div>
      </div>

    </div>

      {}
      {





}
      {globalOnly ? null : (
      <div
        className={clsx(
          'flex shrink-0 items-center gap-2 border-t border-line px-4 py-3',
          phase === 'off' ? 'justify-end' : 'justify-between',
        )}
      >
        {phase === 'off' ? null : (
          <button
            type="button"
            onClick={onDisable}
            className="h-7 rounded-[8px] border border-line px-2.5 text-[12px] text-ink-soft hover:bg-hover hover:text-ink"
          >
            关闭语音
          </button>
        )}
        {

}
        <button
          type="button"
          onClick={onClose}
          


          disabled={Boolean(wakeCollision)}
          className="h-7 rounded-[8px] bg-brand px-3 text-[12px] text-white hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-50"
        >
          保存设置
        </button>
      </div>
      )}
    </div>
  )
}
