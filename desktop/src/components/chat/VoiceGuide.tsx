/**
 * 第一次进入语音对话模式时的一次性引导。
 *
 * ## 为什么用卡片而不是全屏弹窗
 *
 * 用户此刻正打算开口说话。全屏弹窗会挡住输入框、还得先关掉它 —— 打断的正是
 * 他刚提起的那股劲。卡片贴在输入框上方，读完直接说就行。
 *
 * ## 为什么必须引导
 *
 * 这套交互有两个**不直觉**的地方：
 *   1. 要先说唤醒词才开始录（不像普通语音输入"点一下就能说"）；
 *   2. 说完了**不会自动发**，要再说一句「发送」。
 * 不先说清，用户会认定"语音坏了"——而实际上两条都是他自己要的设计。
 */

import { X } from 'lucide-react'

/**
 * 「语音对话怎么用」的四步文案。
 *
 * ⚠️ 抽出来是因为它有**两个出口**：首次进语音模式时弹出的引导卡（本文件），
 * 以及语音设置面板里那个可展开的说明。两处各写一份的话，改了命令词默认值
 * 必然只改一处 —— 而这两处恰恰都在讲"说哪句话"，不一致会让用户以为其中一个是错的。
 */
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
    ['开启语音', `说「${enableWord}」指令后，全部助手进入待命唤醒状态。`],
    [
      '关闭语音',
      `说「${disableWord}」指令后，会关闭整个语音功能，退回到需要说「${enableWord}」指令的状态。`,
    ],
    /*
      ⚠️ 这两条从"只讲搭子"扩成"搭子与群"（现在语音也能唤醒群）。
      留着旧文案的后果很具体：用户在群里想用嘴切过去，读到的却全是"唤醒**搭子**"，
      会以为群不支持 —— 而那个功能就在他眼前。

      ⚠️ 但**不能**在这里写成两份（"唤醒搭子"+"唤醒群"两条）：这两句是与
      `VoicePanel` 共用的，而面板会随上下文只显示**当前主体**的词。写成两份的结果
      是单聊里读到一句与群有关的说明、群聊里读到一句与搭子有关的，两边都多一半废话。
    */
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

/**
 * 用户是否**点过语音面板上的「保存设置」**。
 *
 * 用途只有一个：决定「全局设置」这一块下次打开时是展开还是收起
 * （见 `VoicePanel` 的 `globalOpen`）。刚装好时展开（他就是来配这几项的），
 * 配过一次之后收起（他再进来通常是看状态或改一个命令词）。
 *
 * 存 localStorage 而不是后端设置：这是**界面层的一次性偏好**，
 * 不是需要跟着账号走、需要迁移的配置 —— 混进 `settings.json` 只会让它越来越胖。
 */
const VOICE_PANEL_SAVED_KEY = 'soulmate.voice-panel-saved'

export function voicePanelSaved(): boolean {
  try {
    return window.localStorage.getItem(VOICE_PANEL_SAVED_KEY) === '1'
  } catch {
    // 隐私模式下读不到 → 当作没保存过（展开），对第一次用的人是正确的一侧
    return false
  }
}

export function markVoicePanelSaved(): void {
  try {
    window.localStorage.setItem(VOICE_PANEL_SAVED_KEY, '1')
  } catch {
    /* 存不下就存不下 —— 无非是下次仍默认展开，无害 */
  }
}

export function voiceGuideSeen(): boolean {
  try {
    return window.localStorage.getItem(VOICE_GUIDE_KEY) === '1'
  } catch {
    // 隐私模式下 localStorage 会直接抛 —— 那就每次都当没看过，
    // 多看一眼引导，总好过让用户对着麦克风猜
    return false
  }
}

export function markVoiceGuideSeen(): void {
  try {
    window.localStorage.setItem(VOICE_GUIDE_KEY, '1')
  } catch {
    /* 存不下就存不下，不打扰用户 */
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
  /** 全局：开启语音的指令词 */
  enableWord: string
  /** 全局：关闭语音的指令词 */
  disableWord: string
  /** 当前搭子的唤醒词 */
  wakeWord: string
  sendWord: string
  cancelWord: string
  /** 搭子弹窗审批时的同意 / 拒绝词 */
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

      {/*
        ⚠️ 这段文案原先指向「设置 → 偏好设置 → 语音输入」，那**已经不存在了**
        （把语音设置整体搬进输入栏上那个面板）。留着它的后果是
        用户按图索骥走到设置页，只能看到一段"请去输入栏改"的说明 —— 白跑一趟。
        顺带把"每个搭子**和每个群**都有自己的唤醒词"说出来。
      */}
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
