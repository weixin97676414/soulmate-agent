/**
 * 语音设置面板：点输入栏上那个「语音设置」打开。
 *
 * ## 为什么面板里要分两区
 *
 * 语音设置现在是**两层**（产品定下的）：
 *
 * - **全局**：整个语音功能的开关词、启动时的状态、以及所有语音命令的词。
 *   它们不属于任何主体 —— 说「关闭语音」要能一次关掉全部。
 * - **当前主体**：唤醒词。它天然是"这个东西叫什么"（「你好小助」/「你好产品群」），
 *   所以必须跟着主体走。
 *
 * 分两区是为了让"改这一项会影响谁"一眼可见：改全局的会影响所有主体，
 * 改主体的只影响眼前这个。混在一起展示，用户迟早会把两者搞混。
 *
 * ## 当前主体：搭子**或群**
 *
 * 那一区随上下文换主体 —— 群聊页显示当前群、其余页面显示当前搭子。两者在
 * "唤醒词"这件事上完全同构（都是"喊它切过去"），所以没有为群再开一区，
 * 换的只是一个名字和一份数据源。
 *
 * ⚠️ 主体判定与左上角标题栏**共用 `useCurrentGroup()`**：两处判得不一样的表现
 * 很微妙 —— 标题栏顶着群名，面板却在配搭子的唤醒词。
 *
 * ## 保存
 *
 * 全局走 `saveSettings`（后端就是这么设计的：整份提交）；主体那份按类型分流 ——
 * 搭子走 `assistantStore.save`，群走 `groupStore.updateGroup`。都是**失焦即存**：
 * 这个面板是"随手改一下就走"的地方，多一个保存按钮只会让人放弃修改。
 *
 * ⚠️ 群的唤醒词**传空数组是"不要唤醒词"**，不是"清回默认"（后端不会补）。
 * 这与搭子不同（搭子清空会按名字重生成），所以输入框的说明也分两套 ——
 * 用同一句话会让其中一边的用户改不动。
 *
 * ## `globalOnly`：只显示「全局设置」那一区
 *
 * 首启引导页装完语音模型后有一个「开始配置」，点开的就是**这一区**（产品要求
 * "只有全局设置部分，并提示每个搭子的唤醒要在每个搭子的输入栏语音设置那里配置"）。
 * 所以这里加一个开关而不是另写一份：这一区装的是**所有语音命令的词**，
 * 两处各写一遍的话，用户在引导页配好的词会在正式面板里"看不见"。
 *
 * ## 模型不再随包之后，这段文案必须跟着状态走
 *
 * 语音识别模型 起改为**首启按需下载**（见 `model_hub/`）。所以
 * "已加载本地语音识别模型"这句话**不能无条件显示** —— 没下载时说它已加载，
 * 用户会以为"语音坏了"。没装时显示的是如实说明 + 一个下载卡片。
 */

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
  /**
   * 只渲染「全局设置」那一区（首启引导页的「开始配置」用它）。
   *
   * 为真时**不渲染**：头部状态行、启动后的模型说明、「对话语音怎么用」、
   * 当前主体（唤醒词）那一区、底部按钮。只留全局设置卡片 —— 那里的每一项都是
   * **失焦即存**的，没有底部按钮也不影响保存。
   *
   * ⚠️ 之所以"不渲染"而不是"另写一份全局区"：见文件头 `globalOnly` 那段说明。
   */
  globalOnly?: boolean
  phase?: VoicePhase
  /**
   * 当前在等哪一层的东西：全局指令，还是主体层的唤醒词（搭子与群各配各的）。
   *
   * ⚠️ 值从 `'assistant'` 改成 `'standby'`（现在群也能被唤醒）：
   * 那一层听的已经不只有搭子的词了，"assistant"这个名字会让人以为它只管单聊。
   * 改成与 `phase` 同名的 `standby` 之后，两者说的是同一件事。
   */
  scope?: 'global' | 'standby'
  /** 待命期最近听成的话（喊不醒时这是唯一线索） */
  heard?: string
  /** 最近命中的那个**词**（不是目标名）——只用来显示"唤醒了" */
  lastHit?: string
  /** 待令中的内容（不显示的话用户不知道"发送"会发出什么） */
  pending?: string
  /**
   * 关闭整个语音功能（回到只等「开启语音」的全局层）。
   *
   * ⚠️ 这里**故意没有** `onEnable`：产品要求去掉面板上的「开启语音」
   * 按钮 —— 语音的开关完全由「启动后」那个档位 + 开关词负责，界面按钮是重复入口，
   * 还会引出"按钮和档位冲突时听谁的"这种必须解释的问题。
   */
  onDisable?: () => void
  onClose: () => void
}

/** 面板顶部那行状态文案 —— 说清"现在在等哪一句"。 */
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

/**
 * 每一组命令的**适用范围**（显示在组名右边）。
 *
 * ⚠️ 必须写：命令词是全表列出来的，而**运行时只匹配"此刻屏幕上真的注册了那条
 * 命令"**（见 `voiceCommandStore.dispatch` 与 `useVoiceCommand`）。不写清楚的话，
 * 用户会以为"我把『打开群聊』配好了，为什么在主窗口喊没反应" ——
 * 而实际上那条命令得在**导航栏可见**的页面上才成立。
 *
 * 与其把命令藏起来（旧做法，导致"停止"根本配不到），不如列全 + 说清什么时候管用。
 */
const GROUP_NOTES: Record<VoiceCommandGroup, string> = {
  对话: '对话页随时可用',
  导航: '任何页面可用',
  面板: '对应面板可见时可用',
  助手: '助手栏可见时可用',
  确认: '对应弹窗出现时才可用',
}

/**
 * 分区右上角那句说明的样式 —— **高亮**（产品要求）。
 *
 * 只做"整句可辨认"，不靠颜色单独承载信息：文字本身已经把话说完，
 * 颜色只是让它在密集的面板里被一眼看到（色弱势用户读文字照样懂）。
 */
const SCOPE_NOTE_CLASS =
  'rounded-[6px] bg-brand-soft px-1.5 py-0.5 text-[10.5px] font-medium text-brand'

/**
 * 一条命令词：名字 + 可改的词。
 *
 * 本地缓冲 + 失焦提交：受控值直接绑 store 的话，每敲一个字都要写一次配置文件，
 * 而且光标会跳（受控值被回写覆盖）。
 */
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
  // 语音识别模型下没下（起不再随包）。头部那行说明与下载卡片都看它。
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

  /*
    ---- 当前主体：群，还是搭子 ----

    「当前搭子」那一区在**群聊页显示的是当前群**（产品要求）。
    这不是"多做一个页面"：唤醒词天然是"这个主体叫什么"，群和搭子在这一点上
    完全同构（都是"喊它切过去"），所以面板只需要换一个主体，其余（输入框、
    撞词检测、保存时机）一模一样。

    ⚠️ 判定必须与左上角标题栏共用同一个函数（`useCurrentGroup`）：
    两处判得不一样的表现很微妙 —— 标题栏顶着群名，面板却在配搭子的唤醒词，
    而用户改完发现"喊那个词没反应"。
  */
  const activeGroup = useCurrentGroup()
  const groups = useGroupStore((state) => state.groups)
  const updateGroup = useGroupStore((state) => state.updateGroup)

  const globalVoice = settings?.voice
  const assistantVoice = activeAssistant?.voice
  /** 当前主体的唤醒词 —— 群走群的、其余走搭子的，后面所有逻辑只认这一个。 */
  const wakeWords = activeGroup ? (activeGroup.wake_words ?? []) : (assistantVoice?.wake_words ?? [])

  // 唤醒词用本地文本缓冲：直接绑数组的话，用户打「你好，」的逗号会被立刻 split 掉，
  // 光标与输入都会乱跳。失焦时才写回。
  const wakeWordsText = wakeWords.filter(Boolean).join('，')
  const [wakeDraft, setWakeDraft] = useState(wakeWordsText)
  useEffect(() => setWakeDraft(wakeWordsText), [wakeWordsText])

  // ---- 保存 ---------------------------------------------------------- //
  const saveGlobal = async (changes: Partial<AppSettings['voice']>) => {
    const api = useAppStore.getState().api
    const current = useAppStore.getState().settings
    if (!api || !current) return
    setSaving(true)
    try {
      await api.saveSettings({ ...current, voice: { ...current.voice, ...changes } })
      await reloadSettings()

      // ⚠️ **档位必须立刻作用于运行时**，光写配置不够。
      //
      // `bootstrap()` 原先只在 App 启动时跑一次（被 `voiceBooted` 那个 ref 闸死），
      // 而这一次**没有任何地方订阅** `settings.voice.startup_mode` 的变化 ——
      // 于是用户在面板里切成「应用不在后台等待」、点完成后，麦克风还开着在听。
      // 用户实测报的就是这个（"点击完成后并没有生效，应用还在监听"）。
      //
      // `bootstrap()` 是幂等的：`off → shutdown()`、其余 → `openCapture(...)`，
      // 而 `openCapture` 在已经在跑时只切目标、不重开设备。所以这里放心调。
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

  /**
   * 存"当前主体"的唤醒词 —— 群写群设置、其余写搭子档案。
   *
   * ⚠️ 只把**唤醒词**这一类走这个分流：面板上其余主体级设置（发送词、确认词…
   * 其实都在全局区）没有第二份，所以这个函数刻意只处理 `wake_words`
   * （签名的参数类型已经把它钉死了）。
   *
   * ⚠️ 群那边**空数组 = 明确不要唤醒词**（后端不会补默认值）。这与搭子不同
   * （搭子清空会交还给后端按名字重新生成），所以下面输入框的 hint 也分两套说辞 ——
   * 同一句话在两个上下文里说的不是一回事，是最容易让用户改不动设置的一类坑。
   */
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

  // ---- 命令词（全局）-------------------------------------------------- //
  const overrides = globalVoice?.command_words ?? {}
  const disabledCommands = globalVoice?.disabled_commands
  /**
   * 要列出来的命令 = **全表**减去用户停用的。
   *
   * ⚠️ 这里**不再按"当前屏幕上注册了哪些"过滤**（原先是
   * `handlers.has(spec.id)`，即"此刻真有个按钮能用"）。那个判据在设置面板里
   * 是错的，而且错得很隐蔽：
   *
   * · 「停止生成」只在搭子正在说话时才注册 —— 于是用户想改它的词，
   *   得**恰好赶在它生成的时候**打开面板才看得到它；
   * · 于是他在面板上找了一圈没找到"停止"，只能去试「取消词」，
   *   而那个词管的是"放弃刚说的一句"，根本不是停生成实测反馈
   *   "开始之后说停止也没用"就是这么来的）。
   *
   * 设置面板要回答的是"这台机器上有哪些命令、各叫什么词"，与此刻屏幕上有什么
   * 按钮无关。**运行时**才该用 `handlers` 那条判据（见 `voiceCommandStore.dispatch`）
   * —— 那边保持原样，说一个屏幕上不存在的命令依然不该有任何反应。
   */
  const listedSpecs = useMemo(() => {
    const disabled = disabledCommands ?? []
    return VOICE_COMMANDS.filter((spec) => !disabled.includes(spec.id))
  }, [disabledCommands])

  /**
   * 通用命令词（**全局**，见渲染处的说明）。
   *
   * `key` 显式收窄成这五个字符串字段：`keyof AppSettings['voice']` 还包含
   * `wake_words` / `command_words` 这类非字符串字段，拿它索引取值会变成 any。
   */
  /*
    ⚠️ 这里曾有三项 `confirm_word` / `reject_word` / `revise_word`
    （"确认词 / 拒绝词 / 修改计划词"），**删除**。

    它们从来没有任何代码读过 —— 只有这个面板在显示它们。而"批准高危操作 /
    拒绝 / 改计划"三个动作的实现一律走下面的命令表（`VOICE_COMMANDS` +
    `command_words`），词是「允许执行 / 拒绝执行 / 改一下」。

    删掉之前的表现是**配置项骗人**：用户把"确认词"填成「确认」，对着弹窗说
    "确认"毫无反应 —— 而真正要喊的词在下面那个区里、还写着别的字。
    那比没有这个设置项糟得多。

    留下来的这两项是真的有人读的（`voiceSessionStore.handleSegment` 直接匹配
    它们），而且它们**没有对应的按钮**，所以只能单独配。
  */
  const wordRows: Array<{ key: 'send_word' | 'cancel_word'; label: string; hint: string }> = [
    { key: 'send_word', label: '发送词', hint: '说完说它才发出去' },
    { key: 'cancel_word', label: '取消词', hint: '放弃刚说的一句' },
  ]

  const statusWords = {
    enable: (globalVoice?.enable_word ?? '').trim() || '开启语音',
    send: (assistantVoice?.send_word ?? globalVoice?.send_word ?? '发送').trim() || '发送',
    // 当前主体的唤醒词（群或搭子）—— 顶部那行"在听唤醒词（…）"要显示的就是它
    wakes: wakeWords.filter(Boolean),
  }

  /** 「对话语音怎么用」的展开态。默认折叠是刻意的，见下面那段注释。 */
  const [howtoOpen, setHowtoOpen] = useState(false)

  // ---- 麦克风设备（第 103 批）----
  //
  // 为什么需要这一项：Electron 打开麦克风走的是**系统默认录音设备**，而 Windows 上
  // 换设备（蓝牙耳机断连、插拔 USB 麦、切默认设备）经常让"默认"停在一个已经不存在的
  // 设备上 —— 那时 `getUserMedia` 直接失败，用户看到的是「无法打开麦克风」，
  // 完全猜不到跟设备有关。有了这一项就能在应用里直接换，不必去翻系统设置。
  const micDeviceId = useVoiceSessionStore((state) => state.micDeviceId)
  const setMicDevice = useVoiceSessionStore((state) => state.setMicDevice)
  const micDeviceFellBack = useVoiceSessionStore((state) => state.micDeviceFellBack)
  const [micInputs, setMicInputs] = useState<AudioInput[]>([])
  /**
   * 设备枚举读完了没有。
   *
   * ⚠️ 必须区分"还没读完"与"一个都没有"（第 103 批）：两者都是空数组，但用户看到的
   * 应该是两句话 —— 前者"正在读取设备…"，后者"没检测到可用的麦克风"。
   * 不区分的话，枚举（异步）期间下拉里只有「系统默认」，读完后选项突然多出来，
   * 看起来像"我的选择刚才丢了又回来"。
   */
  const [micInputsLoaded, setMicInputsLoaded] = useState(false)
  useEffect(() => {
    // 面板是**条件渲染**（关掉即卸载），所以每次打开都会重新问一次 ——
    // `listAudioInputs` 内部有缓存，而缓存会在 `devicechange`（授权 / 插拔 / 换默认
    // 设备）时失效，所以"刚插上的麦"也能立刻出现在列表里。
    // ⚠️ 组件可能在 promise 回来之前就被关掉（卸载），用 `alive` 挡一下 setState。
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
  /**
   * 「全局设置」的展开态。
   *
   * 的规则分两段：
   * - **出厂默认展开** —— 第一次打开语音设置的人多半就是来调这几项的，
   *   收起来等于让他先点一下才能干活；
   * - **用户点过一次「保存设置」之后就默认收起** —— 那时他已经配好了，
   *   再进来通常是看状态/改一个命令词，全摊开会挤掉真正要看的东西。
   *
   * ⚠️ 面板是条件渲染（关掉即卸载），所以「每次打开回到默认态」是天然满足的，
   * 不需要额外的重置逻辑。别改成常驻挂载。
   */
  /*
    ⚠️ 「全局设置」**永远展开，不再可收起**（产品要求，推翻了
    上一轮的"保存过一次之后默认收起"）。

    理由：这一块现在装着**所有**通用命令词（发送/取消/确认/拒绝/改一下），
    而搭子那一栏只剩唤醒词。也就是说"要改的东西"从两个地方收拢到了一个地方
    —— 把它折叠起来，等于把面板上唯一有用的内容藏起来，只留下一行标题。

    折叠 state 与那个「保存设置」的记账（`voicePanelSaved`）一并删掉，
    免得留下两套互相矛盾的"展开态"规则。
  */

  /** 按分组排好序的命令（渲染处直接遍历）。 */
  const commandGroups = useMemo(
    () =>
      VOICE_COMMAND_GROUPS.map((group) => ({
        group,
        specs: listedSpecs.filter((spec) => spec.group === group),
      })).filter((item) => item.specs.length > 0),
    [listedSpecs],
  )

  /*
    ---- 唤醒词撞车检测实测反馈 bug）----

    现象：给两个搭子配同一个唤醒词，界面**没有任何提示**，"保存设置"也点得动，
    点完之后后台其实没保存上 —— 用户以为改好了。

    根因：后端为保证"喊谁醒谁不靠运气"会拒绝撞车（保存失败），但前端既没有
    预先检测、也没有把失败原因显式呈现（只是静默地把设置回滚了）。

    现在改成**保存前就拦住**：输入框标红 + 「保存设置」禁用 + 一行解释。
    比"存了才发现没存上"好得多 —— 那种情况下用户已经离开这个界面了。
  */
  const wakeCollision = (() => {
    const own = (wakeDraft ?? '')
      .split(/[，,、\s]+/)
      .map((word) => word.trim())
      .filter(Boolean)
    if (own.length === 0) return null

    /*
      ⚠️ **跨类检测**（现在群也是唤醒目标）。

      以前只比"别的搭子"，因为唤醒目标只有搭子。现在把群也拉进来 —— 一个群和
      一个搭子配了同一个词时，后果与两个搭子撞词**完全一样**：说那个词会稳定地
      落到背景排序靠前的那个（见 `voiceSessionStore` 的 `listeningTargets`），
      而用户完全预料不到自己会切到哪儿去。

      ⚠️ 但这里**只是提示，不拦保存**。后端的撞词校验只管搭子之间
      （`assistants.json` 与 `groups.json` 是两份彼此看不见的配置），
      在这里拦死会出现"界面说不能存、后端其实存得下"的怪状态 ——
      用户会以为功能坏了。所以这一条只能靠提示，而提示必须说清"会怎样"。
    */
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

  // 八步文案与首启引导卡**共用同一个来源**（见 VoiceGuide.voiceSteps）：
  // 两处都在讲"说哪句话"，各写一份必然只改一处。
  const steps = voiceSteps({
    enableWord: statusWords.enable,
    disableWord: (globalVoice?.disable_word ?? '').trim() || '关闭语音',
    wakeWord: statusWords.wakes[0] ?? '',
    sendWord: statusWords.send,
    cancelWord: (globalVoice?.cancel_word ?? '取消').trim() || '取消',
    // ⚠️ 确认/拒绝这两个词**必须从命令表取**，不能再用 `confirm_word` /
    // `reject_word` —— 那两个字段没有任何代码读它们（已删）。
    // 拿死字段来显示"怎么用"，会直接教用户说一句**根本没人听**的话。
    confirmWord: commandWord(VOICE_COMMAND_BY_ID['confirm.allow'], overrides),
    rejectWord: commandWord(VOICE_COMMAND_BY_ID['confirm.reject'], overrides),
  })

  return (
    // ⚠️ 覆盖整个对话框（产品要求：长宽位置与它完全一致）。所以用 `inset-0` 铺满
    // 父容器，而不是 `bottom-full` 浮在上方 —— 它是**替换**对话内容来看设置，
    // 不是盖在对话上面的一个小卡片。父容器就是对话框那张卡片（见 ChatView），
    // 圆角与描边因此完全对齐。
    <div
      className={clsx(
        'flex flex-col',
        globalOnly
          ? // 首启引导页里是**内嵌**的（不是盖住整个对话框的浮层）：
            // 不要绝对定位、也不要自己的边框底色 —— 外面那张卡片已经有了。
            'mt-2'
          : 'absolute inset-0 z-20 overflow-hidden rounded-[12px] border border-line bg-elevated',
      )}
    >
      {/* ---- 头部：状态（固定在顶上，不随内容滚动）---- */}
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
          {/* 产品要求在标题下加这一行：把"这是本机能力、不花钱"
              和"想要更实时可以自己接 API"一次说清。不说的话，用户会拿它去和
              "豆包那种秒回"比，然后得出"语音做得很差"的结论 —— 而那根本不是
              同一个东西（这里是识别，不是实时对话）。

              ⚠️ 起这句话**必须跟着模型状态走**：识别模型不再随包分发，
              没下载时却说"已加载"，用户会以为语音坏了（而真正的原因在下面那张卡片上）。
              没装时换成如实说明 + 下载入口。 */}
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

      {/* 中间是可滚动区：面板要盖满整个对话框，内容多时（三个分区 + 命令列表）
          必须能滚，而头部状态与底部按钮固定不动 —— 它们是"随时要看/随时要点"的。 */}
      <div className="min-h-0 flex-1 overflow-y-auto px-4 pt-3 pb-1">
        {pending ? (
          <div className="mb-2 rounded-[8px] border border-brand/30 bg-brand-soft px-2.5 py-1.5 text-[11.5px] text-brand">
            待发出：{pending}
          </div>
        ) : null}

        {/*
          ---- 补装语音模型（产品约定：跳过的用户在这里补装）----

          ⚠️ 只在**没装**时显示：
          · 装好了还挂一张卡片，等于让"设置面板"看起来像还有个任务没做完；
          · 下载中 `installed` 还是假 → 卡片还在，进度条继续显示 —— 正是要的。

          ⚠️ `globalOnly`（首启引导页的「开始配置」）里**不显示**：那里上面就是
          首启自己的语音卡片，同一件事出现两份反而让人以为要下两次。
        */}
        {!globalOnly && !voiceModel?.installed ? (
          <ModelDownloadCard modelKey="voice" className="mb-2.5" />
        ) : null}

        {/*
          「对话语音怎么用」放在**面板最上方**（产品要求），默认折叠。

          ## 为什么默认折叠

          面板是"来改一个词就走"的地方，一进来就顶着四段说明，真正要改的输入框
          会被挤到看不见的位置。折叠起来只留一行标题，想读的人点一下就展开。

          ## 为什么放最上面而不是最下面

          放最下面时它其实等于**不存在** —— 面板本身要滚动，而它正好在滚动区末端，
          用户改完词就直接点「完成」了。放最上面是"进面板先看到一句话"，成本为零。

          ⚠️「每次点开语音设置都重新折叠」是**天然满足**的：面板是条件渲染
          （`{panelOpen ? <VoicePanel/> : null}`），关掉即卸载、再打开是全新挂载，
          `useState(false)` 自然回到折叠态。**不要**把它改成常驻挂载 + 受控显示，
          那样就得再写一遍"打开时重置"的逻辑。
        */}
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

        {/*
          ---- ① 当前主体（只剩唤醒词）----

          ⚠️ 顺序按产品要求调成「对话语音怎么用 → 主体 → 全局设置」。

          为什么这个顺序更顺：用户点开语音设置，第一件事是"我现在在跟谁说话、
          怎么叫它"（这一区的那一个词），第二件事才是"我说什么词它才发出去"
          （全局那一组）。先看到自己刚喊的那个，比先看到五个通用命令词更贴近他
          此刻的意图。

          ⚠️ 这一区**随上下文换主体**（"面板里显示当前群"）：
          群聊页显示当前群、其余页面显示当前搭子。两者在"唤醒词"这件事上完全
          同构（都是"喊它切过去"），所以换的只是一个名字与一份数据源，
          输入框、撞词检测、保存时机全都一样 —— 不为群再写一区。
        */}
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
          {/* 「搭子」→「助手」只在**语音设置**里改：
              左栏、其它设置页、聊天里仍叫搭子，面板里统一叫助手，
              免得用户在同一个界面里看到两种叫法。 */}
          <span className={SCOPE_NOTE_CLASS}>
            {activeGroup ? '只对这个群生效' : '只对这个助手生效'}
          </span>
        </div>

        {activeGroup || activeAssistant ? (
          <div className="mt-2 flex flex-col gap-2.5">
            <Field
              label="唤醒词"
              // ⚠️ 两套说辞，因为它们说的**不是同一件事**：
              // 群清空 = 这个群彻底不参与语音唤醒；搭子清空 = 交还给后端按名字重生成。
              // 用同一句话会让其中一边的用户改不动（或改了没效果）。
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

        {/* ---- ② 全局设置（**永远展开**，不再可收起）---- */}
      <div className="mt-2.5 rounded-[10px] border border-line bg-panel px-3 py-2.5">
        <div className="flex items-baseline justify-between gap-2">
          <h5 className="text-[12.5px] font-semibold text-ink">全局设置</h5>
          {/* 「对所有搭子生效」→「语音执行各种操作」（产品指定）。
              旧说法把这一区说成"作用范围"，但它实际管的是**全局命令词** ——
              导航、开合面板、打开权益这些都在这，与"对谁生效"无关。 */}
          <span className={SCOPE_NOTE_CLASS}>语音执行各种操作</span>
        </div>

        <div className="mt-2 flex flex-col gap-2.5">
          <Field
            label="启动后"
            // 第一项是"完全关闭"。面板上已经没有「开启语音」按钮了（产品要求），
            // 所以这一档下**没有别的办法把语音叫回来** —— 必须说清楚，否则用户
            // 切过去之后会以为"语音怎么坏了"。
            hint="麦克风要不要一直开着等指令 / 等助手（第一项是完全关闭，要回来改档才能用语音）"
          >
            <Select
              // 设置还没加载出来时按出厂默认显示（`global`）——
              // 写 `off` 会让面板在那一瞬间显示成"应用不在后台等待"，
              // 与用户实际所处的状态不符
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

          {/*
            ---- 麦克风设备（第 103 批）----

            为什么放在「全局设置」区而不是主体那一区：麦克风是**这台机器**的属性，
            与"当前在跟谁说话"无关 —— 换搭子不该换麦克风。它和「启动后」那一项同属
            "这台设备上的语音怎么工作"。

            ⚠️ 它同样落在 `globalOnly` 那一区里（首启引导的「开始配置」）：引导流程本来
            就是"把语音配到能用"，那里也应当能选麦克风。
          */}
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
              // 枚举没读完之前先禁用：否则用户能在一个"只有系统默认"的列表上做出选择
              disabled={!micInputsLoaded}
              // 换设备**立刻生效**（`setMicDevice` 会在麦克风正开着时真的用新设备重开
              // 采集），所以不需要额外的"保存"按钮 —— 与这一区其它项的口径一致。
              onChange={(event) => setMicDevice(event.target.value)}
            >
              {!micInputsLoaded ? <option value="">正在读取设备…</option> : null}
              <option value="">系统默认</option>
              {micInputs.map((item) => (
                <option key={item.deviceId} value={item.deviceId}>
                  {item.label}
                </option>
              ))}
              {/* 选定的设备不在枚举结果里：最常见的原因是**还没授权麦克风**时枚举拿不到
                  deviceId（浏览器隐私保护）。把它单独列出来，否则下拉会显示成空白项，
                  看起来像"什么也没选"，用户会以为设置丢了。 */}
              {micDeviceId && !micInputs.some((item) => item.deviceId === micDeviceId) ? (
                <option value={micDeviceId}>上次选择的麦克风（当前枚举不到）</option>
              ) : null}
            </Select>
          </Field>

          <div className="grid grid-cols-2 gap-2.5">
            <Field
              label="开启语音"
              hint="念出开启语音指令后，全部助手进入待命唤醒状态"
            >
              <Input
                defaultValue={globalVoice?.enable_word ?? ''}
                onBlur={(event) =>
                  void saveGlobal({ enable_word: event.target.value.trim() || '开启语音' })
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

          {/*
            ---- 通用命令词（从"当前搭子"移到这里）----

            ⚠️ 它们以前是**每个搭子各配一份**的。用户的口径是"我希望用户通过一个
            语音确认词，就可以管所有的" —— 而按搭子分份的结果恰恰相反：
            他得给四个搭子各配一遍「确认」，少配一个，跟那个搭子说话时
            "说确认没反应"，且完全看不出为什么。

            分层的正确切分是：
            - **全局**：怎么说话（发送 / 取消 / 确认 / 拒绝 / 改一下）；
            - **搭子**：怎么叫它（唤醒词）。
            "怎么说话"本来就该跟着人走，不跟着对方走。
          */}
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

          {/*
            ---- 语音命令词：**全表按分组列出** ----

            ⚠️ 这里曾只留「开启新对话」一条（产品要求），后来又加了
            「改一下」。改成**全列**，因为那种"只留一两条"的做法造成了
            一个很隐蔽的问题：

            用户想把"停生成"换个词（他习惯说"停止"），在面板上找了一圈没有 ——
            于是去改「取消词」，而那个词管的是"放弃刚说的一句"，不是停生成。
            表现出来就是"开始之后说停止也没用"。

            ⚠️ 当初之所以只留一条，理由是"其余命令都是上下文相关的，列出来会让
            用户以为它们在任何页面都管用"。那条担心**已经被运行时兜住了**：
            `voiceCommandStore.dispatch` 只匹配"此刻真的注册在屏幕上"的命令
            （`handlers`），所以列出来最多是"配了一个暂时用不上的词"，
            不会变成误触发。用一句提示就能说清，不该靠藏起来解决。

            所以每一组下面都写了适用范围，把这条规则明说出来。
          */}
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

      {/* ---- 底部（固定，不随内容滚动）---- */}
      {/*
        ⚠️ 这里原本左右各一个按钮：「开启语音」/「关闭语音」+「完成」。
        按产品要求**去掉「开启语音」按钮** —— 语音的开关现在完全由
        「说出指令随时开启」那套（档位 + 开关词）负责，界面上的按钮是重复的入口，
        而且它和档位之间还有"到底听谁的"这种要解释的问题。
        「关闭语音」保留：那是**随时一按就静音**的兜底，和"改档位"不是一回事。
      */}
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
        {/* ⚠️ 文案从「完成」改成「保存设置」（产品要求）：这个面板是**失焦即存**的，
            "完成"会让人以为不点就不生效；而它实际的动作是"我已经改完了"。
            底色用品牌色（产品要求"跟随 UI 主色"）—— 它是这个面板唯一的主动作。 */}
        <button
          type="button"
          onClick={onClose}
          /* ⚠️ 撞车时**禁用**（产品要求"相同时用户无法点击保存设置，
             并给予提示"）。禁用而不是"点了再报错"：报错意味着用户已经以为改好了，
             而这里他连点都点不下去，配合上面那行红字，一眼就知道要改什么。 */
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
