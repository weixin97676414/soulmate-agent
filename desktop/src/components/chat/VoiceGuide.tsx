















import { X } from 'lucide-react'








export function voiceSteps(words: {
  enableWord: string
  disableWord: string
  wakeWord: string
  sendWord: string
  cancelWord: string
  confirmWord: string
  rejectWord: string
}): Array<[string, string]> {
  const { enableWord, disableWord, wakeWord, sendWord, cancelWord, confirmWord, rejectWord } = words
  return [
    ['打开语音', `说「${enableWord}」指令后，全部助手进入待命唤醒状态。`],
    [
      '关闭语音',
      `说「${disableWord}」指令后，会关闭整个语音功能，退回到需要说「${enableWord}」指令的状态。`,
    ],
    








    [
      '唤醒助手或群',
      `在语音设置里可以给每个助手、每个群各配一个「唤醒词」${wakeWord ? `（例如「${wakeWord}」）` : ''}。在「${enableWord}」状态下说出它，就会立刻跳到那个助手的对话、或那个群的群聊页。`,
    ],
    ['切换助手与群', '直接说另一个助手、或另一个群的「唤醒词」即可切过去。'],
    [
      '发送消息',
      `唤醒之后，说你要发送的话即可。当你停顿超过 0.8 秒后，会自动将你说的话转成文字填入输入框中，此时你再说「${sendWord}」即可。`,
    ],
    ['清除消息', `当你发现杂音被误识别为一些文字时，你可以说「${cancelWord}」来清空输入框。`],
    [
      '弹窗确认',
      `当助手向你弹窗审批任务时，你可以通过说「${confirmWord}」来同意，也可以通过说「${rejectWord}」来拒绝。`,
    ],
    [
      '实时语音',
      '目前没有支持消费级电脑使用的本地实时语音交互模型，你可以通过二次开发调用相关模型 api 来实现与助手的实时语音交互。',
    ],
  ]
}

export const VOICE_GUIDE_KEY = 'soulmate.voice-guide-seen'











const VOICE_PANEL_SAVED_KEY = 'soulmate.voice-panel-saved'

export function voicePanelSaved(): boolean {
  try {
    return window.localStorage.getItem(VOICE_PANEL_SAVED_KEY) === '1'
  } catch {
    
    return false
  }
}

export function markVoicePanelSaved(): void {
  try {
    window.localStorage.setItem(VOICE_PANEL_SAVED_KEY, '1')
  } catch {
    
  }
}

export function voiceGuideSeen(): boolean {
  try {
    return window.localStorage.getItem(VOICE_GUIDE_KEY) === '1'
  } catch {
    
    
    return false
  }
}

export function markVoiceGuideSeen(): void {
  try {
    window.localStorage.setItem(VOICE_GUIDE_KEY, '1')
  } catch {
    
  }
}

export function VoiceGuide({
  enableWord,
  disableWord,
  wakeWord,
  sendWord,
  cancelWord,
  confirmWord,
  rejectWord,
  onClose,
}: {
  
  enableWord: string
  
  disableWord: string
  
  wakeWord: string
  sendWord: string
  cancelWord: string
  
  confirmWord: string
  rejectWord: string
  onClose: () => void
}) {
  const steps = voiceSteps({
    enableWord,
    disableWord,
    wakeWord,
    sendWord,
    cancelWord,
    confirmWord,
    rejectWord,
  })

  return (
    <div className="relative mb-2 rounded-[10px] border border-brand/30 bg-brand-soft px-3.5 py-3">
      <button
        type="button"
        onClick={onClose}
        aria-label="关闭引导"
        className="absolute top-2 right-2 rounded-[6px] p-1 text-brand/70 hover:bg-brand/10 hover:text-brand"
      >
        <X size={13} />
      </button>

      <h4 className="text-[13px] font-semibold text-brand">语音对话怎么用</h4>
      <ol className="mt-2 flex flex-col gap-1.5">
        {steps.map(([title, detail], index) => (
          <li key={title} className="flex gap-2 text-[12px] leading-relaxed text-ink-soft">
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

      {




}
      <p className="mt-2 text-[11.5px] leading-relaxed text-ink-faint">
        唤醒词与这几个命令词都能改，也可以换成你顺口的说法（有人习惯说 over）——
        点输入栏上的「语音设置」就能改，助手和群各有各的唤醒词。
        识别全部在这台电脑上完成，录音不会上传。
      </p>

      <button
        type="button"
        onClick={onClose}
        className="mt-2.5 h-7 rounded-[8px] bg-brand px-3 text-[12px] text-white hover:opacity-90"
      >
        知道了，开始说
      </button>
    </div>
  )
}
