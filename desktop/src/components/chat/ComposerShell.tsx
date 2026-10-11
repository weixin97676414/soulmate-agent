import clsx from 'clsx'
import {
  AlertCircle,
  CornerDownLeft,
  FolderPlus,
  Loader2,
  Mic,
  Paperclip,
  Square,
  SquarePen,
  X,
} from 'lucide-react'
import {
  useEffect,
  useMemo,
  useRef,
  useState,
  type KeyboardEvent as ReactKeyboardEvent,
  type ReactNode,
} from 'react'

import { SlashCommandPanel, type PaletteItem } from '@/components/chat/SlashCommandPanel'
import {
  MAX_FILES,
  collectFromDataTransfer,
  collectFromFileList,
  hasDirectory,
  type CollectResult,
} from '@/lib/folderUpload'
import { VoiceGuide, markVoiceGuideSeen, voiceGuideSeen } from '@/components/chat/VoiceGuide'
import { useCurrentGroup } from '@/lib/currentSubject'
import { VOICE_COMMAND_BY_ID, commandWord } from '@/services/voiceCommands'
import { useVoiceCommand } from '@/stores/voiceCommandStore'
import { useVoiceSessionStore, useVoiceSink } from '@/stores/voiceSessionStore'
import { useVoiceStore } from '@/stores/voiceStore'
import { useAppStore } from '@/stores/appStore'
import { useAssistantStore } from '@/stores/assistantStore'
import { useGroupStore } from '@/stores/groupStore'
import { useNotificationStore } from '@/stores/notificationStore'
import type { PendingAttachment } from '@/types'

const MAX_HEIGHT = 200

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`
}

/**
 * 图片附件的缩略图。
 *
 * 图片必须先用带鉴权头的 fetch 取成 Blob 再转 object URL ——
 * `<img src>` 带不上 `X-Local-Token` 头。取不到时显示一个占位方块，
 * 而不是报错：缩略图只是给人看的，失败了不该挡住发送。
 */
function ImageThumb({ id }: { id: string }) {
  const api = useAppStore((state) => state.api)
  const [url, setUrl] = useState<string | null>(null)

  useEffect(() => {
    if (!api) return
    let cancelled = false
    let objectUrl: string | null = null

    void (async () => {
      try {
        const blob = await api.fetchFileBlob(id, 'upload')
        if (cancelled) return
        objectUrl = URL.createObjectURL(blob)
        setUrl(objectUrl)
      } catch {
        /* 缩略图拿不到就用占位块，不影响这一条消息发出去 */
      }
    })()

    return () => {
      cancelled = true
      // **必须撤销**。每张缩略图都是一个独立 blob，不撤销就会一直占着内存
      // 直到窗口关闭 —— 用户连着发十几张图时这个量是看得见的。
      if (objectUrl) URL.revokeObjectURL(objectUrl)
    }
  }, [api, id])

  if (!url) {
    return <div className="h-full w-full animate-pulse bg-hover" />
  }
  return <img src={url} alt="待发送图片" className="h-full w-full object-cover" />
}

/**
 * 图片附件单独一行铺开。
 *
 * 和普通附件分开渲染，是因为它们对用户的意义不同：文件名只要看名字，
 * 而图片**必须看到画面本身**才能确认选对了没有。
 */
function ImageTiles({
  attachments,
  onRemove,
}: {
  attachments: PendingAttachment[]
  onRemove: (id: string) => void
}) {
  const images = attachments.filter((item) => item.kind === 'image')
  if (images.length === 0) return null

  return (
    <div className="mb-2 flex flex-wrap gap-2">
      {images.map((item) => (
        <div key={item.id} className="group relative">
          <div
            title={item.error ?? item.name}
            className={clsx(
              'h-[62px] w-[62px] overflow-hidden rounded-[8px] border',
              item.status === 'error' ? 'border-danger/40' : 'border-line',
            )}
          >
            {item.status === 'uploading' ? (
              <div className="flex h-full w-full items-center justify-center bg-panel">
                <Loader2 size={14} className="animate-spin text-brand" />
              </div>
            ) : item.status === 'error' ? (
              <div className="flex h-full w-full items-center justify-center bg-danger-soft">
                <AlertCircle size={14} className="text-danger" />
              </div>
            ) : (
              <ImageThumb id={item.id} />
            )}
          </div>
          <button
            type="button"
            onClick={() => onRemove(item.id)}
            aria-label={`移除 ${item.name}`}
            className="no-drag absolute -top-1.5 -right-1.5 flex h-4 w-4 items-center justify-center rounded-full border border-line bg-canvas text-ink-soft opacity-0 transition-opacity group-hover:opacity-100 hover:text-ink focus:opacity-100"
          >
            <X size={10} />
          </button>
        </div>
      ))}
    </div>
  )
}

function AttachmentChips({
  attachments,
  onRemove,
}: {
  attachments: PendingAttachment[]
  onRemove: (id: string) => void
}) {
  // 图片走 ImageTiles，这里只剩普通文件
  const files = attachments.filter((item) => item.kind === 'file')
  if (files.length === 0) return null

  return (
    <div className="mb-2 flex flex-wrap gap-1.5">
      {files.map((item) => (
        <div
          key={item.id}
          title={item.error ?? item.name}
          className={clsx(
            'group flex max-w-[240px] items-center gap-1.5 rounded-[8px] border px-2 py-1 text-[12px]',
            item.status === 'error'
              ? 'border-danger/30 bg-danger-soft text-danger'
              : 'border-line bg-panel text-ink-soft',
          )}
        >
          {item.status === 'uploading' ? (
            <Loader2 size={11} className="shrink-0 animate-spin text-brand" />
          ) : item.status === 'error' ? (
            <AlertCircle size={11} className="shrink-0" />
          ) : (
            <Paperclip size={11} className="shrink-0" />
          )}
          <span className="min-w-0 flex-1 truncate text-ink">{item.name}</span>
          <span className="shrink-0 text-[10.5px] text-ink-faint">
            {item.status === 'error' ? '失败' : formatSize(item.size)}
          </span>
          <button
            type="button"
            onClick={() => onRemove(item.id)}
            aria-label={`移除 ${item.name}`}
            className="no-drag flex h-4 w-4 shrink-0 items-center justify-center rounded-[4px] text-ink-faint hover:bg-canvas hover:text-ink"
          >
            <X size={11} />
          </button>
        </div>
      ))}
    </div>
  )
}

export interface ComposerShellProps {
  /** 当前输入内容 */
  value: string
  onChange: (value: string) => void
  /** 发送（点按钮或按 Enter） */
  onSubmit: () => void | Promise<void>
  /** 生成中：发送按钮换成停止，回车不再触发发送 */
  busy: boolean
  onStop?: () => void
  placeholder: string
  /** 附件：列表由调用方持有（单聊在 chatStore，群聊在 groupStore） */
  attachments: PendingAttachment[]
  onFiles: (files: File[]) => void | Promise<void>
  onRemoveAttachment: (id: string) => void
  /**
   * 斜杠命令面板：候选项与开合都由调用方决定。
   *
   * 为什么不让壳自己判断"输入以 / 开头就打开"：命令集合是按场景裁剪的
   * （群里没有"换模型"这类命令），而且面板有"选完命令还要再选一次"的中间态
   * （切模型、确认清空），那种状态下输入框是空的 —— 壳自己判断会立刻把它关掉。
   */
  paletteOpen?: boolean
  paletteItems?: PaletteItem[]
  paletteEmptyText?: string
  onPaletteSelect?: (item: PaletteItem) => void
  /** 是否展示语音输入按钮（默认展示，前提是系统支持） */
  showVoiceInput?: boolean
  /** 控件行左侧的配置类控件（单聊放思考强度 / 上下文用量 / 权限模式） */
  toolbarLeft?: ReactNode
  /** 「开启新对话」按钮；群聊没有这个概念，不传就不渲染 */
  onNewSession?: () => void
  /**
   * 输入框下方的**动态警告**（当前只有一条：附件里有图片、但当前模型不收图）。
   *
   * 单独一个 prop 而不是塞进 `footerNote`：那句免责声明是灰的常驻小字，
   * 而这条说的是"你这张图模型根本看不到"，混在一起会被当装饰忽略掉。
   */
  hint?: ReactNode
  /** 输入框下方的一行说明（单聊是免责声明，群聊是按键提示） */
  footerNote?: ReactNode
  /**
   * 输入框下方那一行的**三个槽位**（产品要求把顶栏那几样挪到这儿）。
   *
   * 做成槽位而不是写死，是因为这个壳是**单聊与群聊共用**的：单聊要放"独立窗口 /
   * 模型下拉 / 链路与产物"，群聊这几样都没有（它有自己的模型选择）。谁要放什么
   * 由调用方决定，壳本身不假设。
   *
   * 布局：左（`footerLeft`）· 中（`footerCenter`，相对输入栏居中）· 右（`footerRight`）。
   */
  footerLeft?: ReactNode
  footerCenter?: ReactNode
  footerRight?: ReactNode
  /** 外层容器附加类名 */
  className?: string
}

/**
 * 通用输入壳：**单聊与群聊共用同一份输入体验**。
 *
 * 为什么要抽出来（用户原话：「群聊输入栏与单聊的操作体验没有区别」）：
 * 群聊原来是个单行 `<input>`，连"换行"这件最普通的事都做不到。
 * 但直接把整个 Composer 复用又不行 —— 它绑死了 chatStore 的草稿、附件、
 * 发送与会话级命令。所以这里只抽**与场景无关**的部分：
 *
 * - 多行输入、Enter 发送 / Shift+Enter 换行、随内容自动增高（200px 封顶）；
 * - 三种加附件的方式（回形针、拖拽、粘贴图片）与附件预览；
 * - 斜杠命令面板的**渲染与键盘导航**（命令集合由调用方给）；
 * - 语音输入；
 * - 发送 / 停止按钮与左侧控件位。
 *
 * 它**不读任何状态 store**（只读文件缩略图需要的 api），因此单聊与群聊各自接
 * 自己的状态，而输入体验只有一份实现 —— 不会出现"单聊能拖文件、群聊拖不进去"
 * 这种两边慢慢长歪的情况。
 */
export function ComposerShell({
  value,
  onChange,
  onSubmit,
  busy,
  onStop,
  placeholder,
  attachments,
  onFiles,
  onRemoveAttachment,
  paletteOpen = false,
  paletteItems = [],
  paletteEmptyText = '没有匹配的命令',
  onPaletteSelect,
  showVoiceInput = true,
  toolbarLeft,
  onNewSession,
  hint,
  footerNote,
  footerLeft,
  footerCenter,
  footerRight,
  className,
}: ComposerShellProps) {
  const textareaRef = useRef<HTMLTextAreaElement>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)
  const folderInputRef = useRef<HTMLInputElement>(null)
  const [dragging, setDragging] = useState(false)
  const [activeIndex, setActiveIndex] = useState(0)

  // ---- 语音（订阅应用级会话，自己不再持有麦克风）---------------------- //
  //
  // ⚠️ 采集与状态机在 `voiceSessionStore`（应用级**唯一**）：常驻监听只允许有一条
  // 麦克风，分散在单聊/群聊两个输入壳里会互相抢设备（Windows 上第二条常静默失败）。
  // 这里只做两件事：把"当前输入框"登记成识别结果的落点、把「发送」接到真正的发送上。
  const availability = useVoiceStore((state) => state.availability)
  /*
    ⚠️ 常驻麦克风只由**主窗口**持有（第 103 批，与 `App.tsx` 里那处判断同一口径）：
    每个窗口都是独立渲染进程、各自一份 store，多个窗口同时开麦会抢设备
    （Windows 上第二条常静默失败，也可能直接报「无法打开麦克风」）。

    所以独立对话窗 / 群聊窗里**不显示**语音入口 —— 一个点了也不会有人听的按钮，
    比不显示更糟（用户会以为"这里也能用语音"，然后怀疑是自己没说清楚）。

    ⚠️ `mode` 取不到（preload 未注入 / 浏览器里跑）时按主窗口处理：宁可多显示一次，
    也不要让正常启动的语音入口整个消失。
  */
  const isMainWindow = (() => {
    const mode = window.agentBridge?.getWindowArgs?.()?.mode
    return mode !== 'chat' && mode !== 'group'
  })()
  // 能力未知时先不显示按钮：宁可晚半秒出现，也别让用户点了才发现不能用
  //
  // ⚠️ `isMainWindow` **刻意不放进这个判据**（第 103 批独立复核后改）：
  // 独立对话窗 / 群聊窗里**保留**「语音设置」入口（它同时是查看语音设置的入口）。
  // "入口无声消失"正是用户这次报障的体验（"语音功能用不了了、状态也没了"），
  // 把按钮拿掉等于换个地方复现同一个困惑。那些窗口不会开麦克风
  // （`bootstrap` 只在主窗口跑，见 App.tsx），所以下面用一行说明讲清楚
  // "语音在主窗口用"，而不是把入口藏掉。
  const canSpeak = showVoiceInput && availability?.asr === true

  /*
    ⚠️ 依赖里必须带"后端就绪"（第 103 批修）。

    原先只依赖 `showVoiceInput`（这个值基本不变）⇒ 能力探测**整个生命周期只跑一次**；
    而 `refresh()` 失败时**不缓存结果**（`availability` 留在 null）⇒ 如果那一次恰好
    落在"核心还没起来 / 正在重启 / token 刚换"的时刻，麦克风按钮与语音状态行就
    **永远不再出现**（实测反馈"语音功能用不了了、输入栏下面的状态显示也没了"正是这一幕）。

    接上后端就绪跳变后：核心一旦 ready 就补探一次。`refresh()` 里"拿到过就不再问"
    的缓存仍然生效，所以正常路径**不会多出任何请求**。
  */
  const backendReady = useAppStore((state) => state.backendStatus.state === 'ready')
  useEffect(() => {
    if (showVoiceInput && isMainWindow && backendReady) {
      void useVoiceStore.getState().refresh()
    }
  }, [showVoiceInput, isMainWindow, backendReady])

  // `submit` 在下面才定义 —— 用 ref 桥一下，免得为了顺序把它整个提上来
  const submitRef = useRef<() => void>(() => {})
  // 标记"这次发送是语音说的"：语音说「发送」**不该**把自己踢出语音模式（用户在
  // 连续对话），只有手动点发送按钮才退出。⚠️ 用户实测报过这个。
  const voiceSendingRef = useRef(false)

  const phase = useVoiceSessionStore((state) => state.phase)
  const scope = useVoiceSessionStore((state) => state.scope)
  const heard = useVoiceSessionStore((state) => state.heard)
  const level = useVoiceSessionStore((state) => state.level)
  // 打不开麦克风的原因 + 自救入口（第 103 批）：`phase` 会因失败回落到 `off`，
  // 那时上面那条状态行整块消失 —— 所以这一条由 `micError` 单独驱动，见下方说明。
  const micError = useVoiceSessionStore((state) => state.micError)
  const retryMic = useVoiceSessionStore((state) => state.retryMic)

  /*
    ⚠️ 语音设置的分层在 重新划过（产品要求）：
      · `globalVoice`：**所有**命令词（发送/取消/确认/拒绝/改一下）+ 开关词 + 命令词；
      · **搭子的那份只剩唤醒词** —— "怎么说话"是用户的习惯，不按对方重复配。

    所以这里不再有 `voiceSettings = 搭子那份 ?? 全局` 那种"就近取"的兜底：
    兜底会让"某个搭子残留了旧字段"时用上它，而那个值用户已经看不到、也改不了了
    （界面上只剩全局那一处），表现为"明明改了全局，跟这个搭子说话还是老词"。
  */
  const globalVoice = useAppStore((state) => state.settings?.voice)
  const activeAssistantProfile = useAssistantStore((state) =>
    state.assistants.find((item) => item.id === state.activeId),
  )
  /**
   * 唤醒词是**唯一**跟着主体走的设置：单聊跟搭子，群聊跟群（
   * 起群也能被唤醒）。
   *
   * ⚠️ 判定与语音设置面板、左上角标题栏**共用 `useCurrentGroup()`** ——
   * 三处必须说的是同一个主体。判得不一样时的表现很微妙：底部状态条提示
   * 「在听（你好小助）」，而实际在听的是这个群的词，用户喊了没反应。
   */
  const activeGroup = useCurrentGroup()
  const wakeWords = activeGroup
    ? activeGroup.wake_words
    : (activeAssistantProfile?.voice?.wake_words ?? globalVoice?.wake_words)

  // 把当前输入框登记为落点。`useMemo` 只是省一次对象分配 —— `useVoiceSink` 内部
  // 按"有没有"判断，不会因为引用变化就反复注销登记。
  useVoiceSink(
    useMemo(
      () => ({
        getDraft: () => value,
        setDraft: onChange,
        send: async () => {
          voiceSendingRef.current = true
          try {
            // ⚠️ 必须等一次渲染再发：`onSubmit` 是父组件给的闭包，捕获的是**它那次
            // 渲染**看到的草稿。同一 tick 里调用它，发出去的是上一版内容 ——
            // 恰好少了用户刚说的最后一句，而且这种错很难在现场复现。
            await new Promise((resolve) => {
              window.setTimeout(resolve, 0)
            })
            submitRef.current()
          } finally {
            voiceSendingRef.current = false
          }
        },
      }),
      [value, onChange],
    ),
  )

  // ---- 语音命令：这个输入壳上的两个高频动作 ----
  //
  // 都只在**真的能点**时才登记：没在生成时说「停下来」不该有反应（传 null 表示
  // "此刻不提供"），群聊那边没有"开启新对话"这个概念，自然也不会登记它。
  useVoiceCommand('chat.stop', busy && onStop ? () => void onStop() : null)
  useVoiceCommand('chat.new', onNewSession ? () => onNewSession() : null)

  // ---- 换主体时清空输入栏 ----
  //
  // 报：在一个搭子这边说完话、转成文字后（还没说取消），
  // 直接喊另一个搭子的唤醒词切过去，输入栏的草稿会**留在原地且清不掉**，
  // 切回原来那个也发不出去。
  //
  // 根因是草稿（`spokenRef` + 父组件的 `value`）不属于任何搭子，而它的"基准点"
  // 只在进入语音模式时取一次；切搭子后两者错位，后续写入与回退都对不上账。
  //
  // 修法：**监听当前主体变化，把草稿与累积量一起归零**。放在这里而不是
  // `switchAssistant` 里，是因为切搭子不止语音一条路（鼠标点、右键菜单、
  // 快捷键都算），而"清空输入栏"是对**所有**切换方式的共同要求。
  //
  // ⚠️ （群聊也能语音）之后，"主体"不再只是搭子，判据扩成
  // **`(搭子 | 群, 对话)`**：
  //   · 单聊切搭子 —— 原来那条；
  //   · 群聊切群、**以及同一个群里切对话** —— 后面这一种最容易漏：同一个群内
  //     换一条对话，屏幕上看不出"换人了"（群名没变），但上一条对话的待令内容
  //     会跟着进到新对话的输入框里，用户说「发送」就把它发到了错误的地方。
  // 所以 key 里必须带上 `activeThreadId`，只带群 id 是不够的。
  const activeAssistantId = useAssistantStore((state) => state.activeId)
  const activeThreadId = useGroupStore((state) => state.activeThreadId)
  const subjectKey = activeGroup
    ? `group:${activeGroup.id}:${activeThreadId ?? ''}`
    : `assistant:${activeAssistantId ?? ''}`
  const firstAssistantRef = useRef(true)
  useEffect(() => {
    // 首次挂载不清：那时 `activeId` 刚从 null 落到默认搭子，不是"用户切了搭子"
    if (firstAssistantRef.current) {
      firstAssistantRef.current = false
      return
    }
    // 先清语音那侧累积的基准（不然下次说话会**追加**到旧内容上），再清输入框
    useVoiceSessionStore.getState().resetDraft()
    onChange('')
    // ⚠️ 依赖里**只放** `subjectKey`：`onChange` 是父组件给的闭包，
    // 每次渲染都可能换引用，放进去会导致"每渲染一次就清空一次输入框"。
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [subjectKey])

  // 「语音在跑」包括全局层（在等「开启语音」）—— 那也算语音功能开着，
  // 界面上要能看出来，否则用户说了「关闭语音」也不知道到底关掉没有。
  //
  // ⚠️ 这里**也要受 `showVoiceInput` 约束**：那条状态条（「在等『开启语音』…
  // 刚听到『X』」）是壳内部渲染的、只看 `phase`，所以"不显示语音"必须同时关掉
  // 按钮与状态条 —— 否则会出现"输入栏上没有麦克风按钮，底部却挂着一行语音状态"。
  //
  // 这条约束现在服务于**只读观察窗**（Q3 拍板：观察窗不给语音，
  // 它没有可落点的输入栏）。可操作的群聊页与单聊一样传 `true`，不再走 `false`。
  const voiceActive = Boolean(showVoiceInput) && isMainWindow && phase !== 'off'
  const recording = phase === 'listening' || phase === 'recognizing' || phase === 'awaiting'
  const [guideOpen, setGuideOpen] = useState(false)
  // 语音设置面板的开关在 store 里 —— 面板要**铺满整个对话框**（产品要求），
  // 所以它渲染在对话框那一层（见 ChatView），输入栏只负责"按一下开/关"。
  const panelOpen = useVoiceSessionStore((state) => state.panelOpen)
  const setPanelOpen = useVoiceSessionStore((state) => state.setPanelOpen)

  const toggleMic = () => {
    // 麦图标**不再开关语音功能**（产品要求）：它现在只是"语音设置"
    // 的入口，点一下开/关面板。语音本身的开关将由**常驻全局监听**那层负责
    // （听到"开启语音"才开始监听搭子）—— 把开关和设置分成两处，是为了不让
    // "我想看看设置"变成"我打开了麦克风"。
    if (!voiceGuideSeen()) setGuideOpen(true)
    setPanelOpen(!panelOpen)
  }

  useEffect(() => {
    const element = textareaRef.current
    if (!element) return
    element.style.height = 'auto'
    element.style.height = `${Math.min(element.scrollHeight, MAX_HEIGHT)}px`
  }, [value])

  const uploading = attachments.some((item) => item.status === 'uploading')
  /**
   * 附件还在传的时候点过「发送」—— 不丢这一次点击，排队等传完自动发。
   *
   * 产品约定：附件常常是整份任务书，传一半时顺手点发送是很自然的动作；
   * 早先那种"按钮直接置灰、点了没反应"会被当成卡死。
   */
  const [queued, setQueued] = useState(false)
  // 用 ref 拿最新的 onSubmit：它通常是父组件里的内联函数，
  // 直接进依赖数组会让下面这个副作用每渲染一次就跑一次。
  const onSubmitRef = useRef(onSubmit)
  onSubmitRef.current = onSubmit

  useEffect(() => {
    if (!queued || uploading) return
    setQueued(false)
    // 有附件传失败就不自动发：否则用户会收到一条"看着正常、其实缺附件"的消息
    if (attachments.some((item) => item.status === 'error')) return
    void onSubmitRef.current()
  }, [queued, uploading, attachments])

  // 键盘接管只在"面板真的开着且有候选"时生效：一条都没有时回车应当照常发送
  const paletteActive = paletteOpen && paletteItems.length > 0

  // 候选项变化时把高亮拉回第一项：否则用户输入过滤后，高亮可能停在一个
  // 已经不存在的下标上，回车会选中一个完全不相干的命令
  useEffect(() => {
    setActiveIndex(0)
  }, [paletteItems.length])

  const submit = () => {
    // 手动点发送时退出语音模式：不然识别还在往里写，发送的瞬间草稿可能又被改回来。
    // 用 toggle 而不是 discard —— 点发送时草稿里正是用户要的内容，不该退回旧版。
    // ⚠️ **语音说的「发送」不在此列**（见 voiceSendingRef）：那条路要留在语音模式里，
    // 否则每发一条都得重新点一次麦克风。
    // ⚠️ 语音模式**不在这里关**：语音的开关现在归全局监听层（说「关闭语音」才关），
    // 点发送按钮只是发消息。这里原先那句 `voice.toggle()` 会让"点一次发送"顺手把
    // 用户的语音会话关掉 —— 而语音是**跨会话**的能力，不该被一次发送打断。
    void voiceSendingRef.current
    if (busy) return
    if (uploading) {
      // 附件还在传：把这次点击记成「排队」，传完自动发出去；再点一下取消排队
      setQueued((prev) => !prev)
      return
    }
    void onSubmit()
  }
  // 语音模式那句「发送」也走这里 —— 用 ref 桥，是为了让 onSend 拿到**当前**的 submit
  submitRef.current = submit

  const pickFiles = (files: FileList | File[] | null) => {
    const list = files ? Array.from(files) : []
    if (list.length) void onFiles(list)
  }

  /**
   * 收下一批"从文件夹里收集来的"文件：先把被跳过的说清楚，再交给上传链路。
   *
   * 为什么必须报出来：用户拖一个 300 个文件的目录进来，界面上只多了 200 个 ——
   * 不说原因的话，他只会以为"这功能坏了"。静默丢东西是本项目零容忍的失败方式。
   */
  const applyCollected = (result: CollectResult) => {
    if (result.skipped.length || result.truncated) {
      const head = result.truncated
        ? `一次最多发送 ${MAX_FILES} 个文件，多出来的没有加入。`
        : '有些文件没有加入。'
      const detail = result.skipped
        .slice(0, 5)
        .map((item) => `${item.name}（${item.reason}）`)
        .join('、')
      const more = result.skipped.length > 5 ? ` 等共 ${result.skipped.length} 个` : ''
      useNotificationStore.getState().push({
        level: 'warning',
        title: '部分文件没有加入',
        message: `${head}${detail ? `\n跳过的：${detail}${more}` : ''}`,
        // 不自动消失：用户可能正要去把那几个文件挑出来单独发
        autoDismissMs: 0,
      })
    }
    if (result.files.length) pickFiles(result.files)
  }

  const selectPalette = (item: PaletteItem | undefined) => {
    if (!item) return
    onPaletteSelect?.(item)
    setActiveIndex(0)
  }

  const onKeyDown = (event: ReactKeyboardEvent<HTMLTextAreaElement>) => {
    // 面板开着时先由面板消费方向键与回车 —— 否则回车会既选中命令又发送消息
    if (paletteActive) {
      if (event.key === 'ArrowDown') {
        event.preventDefault()
        setActiveIndex((index) => (index + 1) % paletteItems.length)
        return
      }
      if (event.key === 'ArrowUp') {
        event.preventDefault()
        setActiveIndex((index) => (index - 1 + paletteItems.length) % paletteItems.length)
        return
      }
      if (event.key === 'Escape') {
        event.preventDefault()
        setActiveIndex(0)
        return
      }
      // 输入法组合中的回车不能当确认：中文输入时选词也会发回车
      if (event.key === 'Enter' && !event.shiftKey && !event.nativeEvent.isComposing) {
        event.preventDefault()
        selectPalette(paletteItems[activeIndex] ?? paletteItems[0])
        return
      }
    }
    if (event.key === 'Enter' && !event.shiftKey && !event.nativeEvent.isComposing) {
      event.preventDefault()
      submit()
    }
  }

  return (
    <div
      className={clsx(
        // 输入栏也是**独立卡片**（产品要求）：圆角 + 描边，与上面的对话框之间留出缝
        'shrink-0 rounded-[12px] border border-line bg-panel px-4 pt-3 pb-3',
        /*
          ⚠️ `@container` = `container-type: inline-size`。**没有它，下面那个
          `25cqw` 的模型下拉会退回成"视口宽度的 1/4"**（`cqw` 找不到容器时的
          回退行为），窗口一拉宽就明显不跟卡片走 —— 用户要的恰恰是"与输入栏的
          宽度比例一直保持一致"。

          ⚠️ 参照的是这张卡片的**内容盒子**（css 的容器查询默认如此），
          也就是已经扣掉左右 `px-4` 的那部分。与"卡片外框的 1/4"差 32px 的 1/4
          = 8px，肉眼不可辨；而换成 `calc` 去凑外框反而会把这条比例绑死在 padding 上
          （以后谁把 `px-4` 改大，比例就悄悄变了）。
        */
        '@container',
        className,
      )}
    >
      {/* 与消息区一样去掉 `max-w-[860px]`：输入栏和上面的对话栏必须同宽，
          否则窗口拉宽后输入框比消息窄一截，看着像没对齐。 */}
      <div className="relative mx-auto w-full">
        {/*
          首次进入语音模式时的引导，放在输入框正上方：用户正要开口，这时候给他一份
          说明，比事后在设置页里放一份文档有用得多。文案与面板里那个可展开的
          「对话语音怎么用」**共用同一份**（`voiceSteps`）。
        */}
        {guideOpen ? (
          <VoiceGuide
            enableWord={(globalVoice?.enable_word ?? '').trim() || '开启语音'}
            disableWord={(globalVoice?.disable_word ?? '').trim() || '关闭语音'}
            // ⚠️ 兜底值与后端 `default_wake_words` 保持一致（「你好」+ 主体名）。
            // 群里兜底的就不再是「你好搭子」——那句话在群聊页看是错的。
            wakeWord={(wakeWords ?? [])[0] ?? (activeGroup ? '你好群聊' : '你好搭子')}
            sendWord={(globalVoice?.send_word ?? '').trim() || '发送'}
            cancelWord={(globalVoice?.cancel_word ?? '').trim() || '取消'}
            // ⚠️ 从**命令表**取词（`confirm_word` / `reject_word` 两个字段
            // 已删，它们从来没有任何代码读过）。拿死字段显示
            // "怎么用"，等于教用户说一句根本没人听的话。
            confirmWord={commandWord(
              VOICE_COMMAND_BY_ID['confirm.allow'],
              globalVoice?.command_words ?? {},
            )}
            rejectWord={commandWord(
              VOICE_COMMAND_BY_ID['confirm.reject'],
              globalVoice?.command_words ?? {},
            )}
            onClose={() => {
              markVoiceGuideSeen()
              setGuideOpen(false)
            }}
          />
        ) : null}

        {paletteOpen ? (
          <SlashCommandPanel
            items={paletteItems}
            activeIndex={activeIndex}
            emptyText={paletteEmptyText}
            onPick={selectPalette}
            onHover={setActiveIndex}
          />
        ) : null}

        <ImageTiles attachments={attachments} onRemove={onRemoveAttachment} />
        <AttachmentChips attachments={attachments} onRemove={onRemoveAttachment} />

        {/* openclaw 式一体化容器：输入区在上、控件行在下，全都在**同一个**圆角框里 */}
        <div
          onDragOver={(event) => {
            // 必须 preventDefault，否则浏览器会直接打开拖进来的那个文件
            event.preventDefault()
            setDragging(true)
          }}
          onDragLeave={() => setDragging(false)}
          onDrop={(event) => {
            event.preventDefault()
            setDragging(false)
            // 拖进来的是**文件夹**时 `dataTransfer.files` 给不了里面的文件
            // （有的平台只给一个空壳、有的干脆为空），必须走递归读取那条路。
            // ⚠️ `webkitGetAsEntry()` 只能在事件同步阶段调用，所以这两步都别 await。
            if (hasDirectory(event.dataTransfer)) {
              void collectFromDataTransfer(event.dataTransfer).then(applyCollected)
              return
            }
            pickFiles(event.dataTransfer.files)
          }}
          className={clsx(
            'rounded-[14px] border bg-canvas px-3 pt-2.5 pb-2 transition-colors',
            dragging ? 'border-brand bg-brand-soft/40' : 'border-line focus-within:border-brand',
          )}
        >
          <input
            ref={fileInputRef}
            type="file"
            multiple
            hidden
            onChange={(event) => {
              pickFiles(event.target.files)
              // 清空 value，否则连续选同一个文件不会触发 change
              event.target.value = ''
            }}
          />
          {/* webkitdirectory 不在 React 的类型里，用展开对象传（Electron 支持它） */}
          <input
            ref={folderInputRef}
            type="file"
            hidden
            {...({ webkitdirectory: 'true', directory: 'true' } as Record<string, string>)}
            onChange={(event) => {
              applyCollected(collectFromFileList(event.target.files))
              event.target.value = ''
            }}
          />

          <textarea
            ref={textareaRef}
            rows={1}
            value={value}
            // ⚠️ 输入框不能只有一个会变的 placeholder（第 90 批，M-34）：
            // 拖动文件时它会变成"松开以添加附件或文件夹"、开始打字后更是整条消失 ——
            // 读屏用户于是永远不知道这个框是什么。`aria-label` 是视觉零改动的修法。
            aria-label="输入消息"
            placeholder={dragging ? '松开以添加附件或文件夹' : placeholder}
            onChange={(event) => onChange(event.target.value)}
            onPaste={(event) => {
              const files = Array.from(event.clipboardData.files)
              if (files.length) {
                event.preventDefault()
                pickFiles(files)
              }
            }}
            onKeyDown={onKeyDown}
            className="max-h-[200px] min-h-[26px] w-full resize-none bg-transparent py-1 text-[13.5px] leading-relaxed text-ink placeholder:text-ink-faint focus:outline-none"
          />

          {/* 控件行：左侧是"配置类"，右侧是"动作类" —— 和大多数聊天应用的方向一致 */}
          <div className="mt-1 flex items-center gap-1">
            <button
              type="button"
              onClick={() => fileInputRef.current?.click()}
              title="添加附件"
              aria-label="添加附件"
              className="no-drag flex h-8 w-8 shrink-0 items-center justify-center rounded-[8px] text-ink-faint hover:bg-hover hover:text-ink"
            >
              <Paperclip size={15} />
            </button>

            {/* 整个文件夹一起传（产品要求）：资料常常一整目录，让他一个个点选不现实 */}
            <button
              type="button"
              onClick={() => folderInputRef.current?.click()}
              title="添加整个文件夹"
              aria-label="添加整个文件夹"
              className="no-drag flex h-8 w-8 shrink-0 items-center justify-center rounded-[8px] text-ink-faint hover:bg-hover hover:text-ink"
            >
              <FolderPlus size={15} />
            </button>

            {onNewSession ? (
              <button
                type="button"
                onClick={onNewSession}
                title="开启新对话 (Ctrl+N)"
                aria-label="开启新对话"
                className="no-drag flex h-8 w-8 shrink-0 items-center justify-center rounded-[8px] text-ink-faint hover:bg-hover hover:text-ink"
              >
                <SquarePen size={15} />
              </button>
            ) : null}

            {toolbarLeft}

            <span className="min-w-2 flex-1" />

            {canSpeak ? (
              <button
                type="button"
                onClick={toggleMic}
                title={panelOpen ? '收起语音设置' : '打开语音设置'}
                aria-label="语音设置"
                aria-pressed={panelOpen}
                className={clsx(
                  'no-drag relative flex h-8 shrink-0 items-center gap-1.5 rounded-[8px] px-2 text-[12px]',
                  /*
                    ⚠️ 三档的配色，以及"已连通"为什么是**绿色**而不是红色
                    （"语音连通时，按钮和状态上的点都显示为绿色
                    而不是红色"）。

                    颜色在这里承担的是**状态**，不是警报：
                    · 品牌色 = 语音功能开着，但还没轮到你说话（在等开关词/唤醒词）；
                    · **绿色 = 已经连通、正在听你**（录音 / 识别 / 待令）；
                    · 灰 = 语音没开。

                    原来"已连通"用的是红色（`danger`）。问题是那个红在界面别处
                    一律表示"危险/出错"（删除、失败、高危操作），于是"它正在好听你
                    说话"看起来像报错 —— 用户每次开口前都要先怀疑一下是不是出事了。
                    绿色与 `TitleBar` 那个"X 个工具"的健康点同色，语义也对得上。
                  */
                  phase === 'global' || phase === 'standby'
                    ? 'bg-brand-soft text-brand'
                    : recording
                      ? 'bg-success-soft text-success'
                      : 'text-ink-faint hover:bg-hover hover:text-ink',
                )}
              >
                {/* 文字在图标**左侧**。整块都是同一个按钮 —— 点「语音设置」这几个字
                    和点图标是一回事，用户不用去瞄准那个小图标。 */}
                <span>语音设置</span>
                {phase === 'recognizing' ? (
                  <Loader2 size={14} className="animate-spin" />
                ) : (
                  <Mic size={14} />
                )}
                {/*
                  「它在听」用**亮度抖动**反馈，不再缩放。

                  ⚠️ 这里换过一次表征方式。原先是一个 `ring` 跟着音量做
                  `scale(1 → 1.35)` —— 看起来像有只框在按钮外围一胀一缩，
                  实测反馈"看着很难受"。原因大概是它**每来一块音频就改元素尺寸**，
                  而这个按钮只有 32px 高，放大 35% 会直接盖到相邻控件上。

                  改成在按钮底上叠一层 `bg-current`（自动跟随按钮当前那一档的颜色），
                  只动 `opacity` —— 同样的"它真的听到你在说话"，
                  但**不改变任何布局尺寸**。
                */}
                {voiceActive ? (
                  <span
                    className="pointer-events-none absolute inset-0 rounded-[8px] bg-current"
                    style={{ opacity: 0.08 + level * 0.5 }}
                  />
                ) : null}
              </button>
            ) : null}

            {busy ? (
              <button
                type="button"
                onClick={() => onStop?.()}
                title="停止生成"
                className="no-drag flex h-8 items-center gap-1.5 rounded-[8px] border border-line px-2.5 text-[12.5px] text-ink-soft hover:bg-hover hover:text-ink"
              >
                <Square size={12} className="fill-current" />
                停止
              </button>
            ) : (
              <button
                type="button"
                onClick={submit}
                // 有附件就能发（产品要求：任务常常整份都在附件里，不该逼他再打一句话）。
                // "既没文字也没附件"仍然禁用，这是唯一真正没有内容可发的情况。
                // ⚠️ 上传中**不置灰**：那时点一下是"排队等传完自动发"，不是"点不动"。
                disabled={!value.trim() && attachments.length === 0}
                title={
                  uploading && queued
                    ? '附件上传中，传完自动发送'
                    : uploading
                      ? '附件上传中，点一下可以排队发送'
                      : value.trim() || attachments.length === 0
                        ? '发送 (Enter)'
                        : '发送附件 (Enter)'}
                className="no-drag flex h-8 w-8 shrink-0 items-center justify-center rounded-[8px] bg-brand text-white transition-opacity disabled:bg-brand/35"
              >
                {uploading && queued ? (
                  <Loader2 size={14} className="animate-spin" />
                ) : (
                  <CornerDownLeft size={14} />
                )}
              </button>
            )}
          </div>
        </div>

        {/*
          语音模式的状态条**必须常驻**：这套交互里用户全程不看键盘，如果界面上
          不写清楚"现在在等什么"，他唯一能做的就是反复说话猜。四种状态各写一句
          人话 —— 尤其"待令"那条，要明确告诉他哪句话才会真正发出去。
        */}
        {voiceActive ? (
          <div
            className={clsx(
              'mt-1.5 flex items-center gap-2 rounded-[8px] px-2.5 py-1.5 text-[11.5px] leading-relaxed',
              phase === 'awaiting' ? 'bg-brand-soft text-brand' : 'bg-canvas text-ink-faint',
            )}
          >
            {/* 与上面那个按钮同一套配色（见那里的说明）：**已连通 = 绿**。
                两处必须同一个色，否则按钮绿、点却红，用户会以为其中一个是报错。 */}
            <span
              className={clsx(
                'h-1.5 w-1.5 shrink-0 rounded-full',
                recording ? 'bg-success' : 'bg-brand',
              )}
              style={phase === 'listening' ? { opacity: 0.4 + level * 0.6 } : undefined}
            />
            <span>
              {phase === 'global'
                ? // 全局层：只等「开启语音」。这一句要写清楚"还没开始听搭子"，
                  // 否则用户喊半天搭子名没反应，会以为是唤醒词配错了。
                  `在等「${(globalVoice?.enable_word ?? '开启语音').trim() || '开启语音'}」…${heard ? ` 刚听到「${heard}」` : ''}`
                : phase === 'standby'
                  ? // ⚠️ 文案从"各搭子自己的词"改成"各搭子与各群自己的词"（用户
                    // 起群也是唤醒目标）：留着旧文案会让用户在群里
                    // 喊群名时以为"这里只认搭子"。
                    `在听唤醒词（${scope === 'standby' ? '各搭子与各群自己的词' : '—'}）…${heard ? ` 刚听到「${heard}」` : ''}`
                  : phase === 'recognizing'
                    ? '正在识别…'
                    : phase === 'awaiting'
                      ? busy
                        ? `等它说完再说「${globalVoice?.send_word ?? '发送'}」发出（内容已留住）· 说「${globalVoice?.cancel_word ?? '取消'}」放弃`
                        : `说「${globalVoice?.send_word ?? '发送'}」发出 · 说「${globalVoice?.cancel_word ?? '取消'}」放弃`
                      : '我在听，说完停顿一下…'}
            </span>
          </div>
        ) : null}

        {/* 独立对话窗 / 群聊窗：语音入口保留（能打开语音设置看配置），但常驻麦克风
            只在主窗口开（`bootstrap` 只在主窗口跑，见 App.tsx 的说明）。这里如实说
            一句 —— 比起"按钮不见了"，一句说明能让用户知道该去哪儿用语音。 */}
        {showVoiceInput && !isMainWindow ? (
          <div className="mt-1.5 px-1 text-[11px] leading-relaxed text-ink-faint">
            语音输入与唤醒只在主窗口使用（同一台麦克风不能同时在两个窗口打开）。
          </div>
        ) : null}

        {/*
          麦克风打不开时的**常驻说明 + 重试**（第 103 批）。

          ⚠️ 为什么单开一段、而不是复用上面那条状态行：状态行的可见性绑在
          `phase !== 'off'` 上 —— 而"打不开"恰恰会把 phase 打回 `off`，
          于是**最需要说明原因、最需要重试的时候，整条状态行正好消失**。
          所以这一段的判据是 `micError`，与 phase 无关。

          ⚠️ 配色用 `warning`（与下面那条 `hint` 同色）：这不是"危险操作"的红，
          而是"你现在做不了这件事，原因是这个"的提醒。

          ⚠️ 只读观察窗（`showVoiceInput === false`）不显示：那个窗口本来就没有
          语音，弹一条麦克风失败只会让人以为出错了。
        */}
        {showVoiceInput && isMainWindow && !voiceActive && micError ? (
          <div
            /*
              `role="status"`（等价 aria-live="polite"）：这条提示是**动态冒出来**的，
              读屏用户否则完全不会知道输入栏下方多了原因与「重试」—— 而那条同名通知
              10 秒后会自动消失，错过就什么都没有了。
            */
            role="status"
            className="mt-1.5 flex items-start gap-2 rounded-[8px] bg-canvas px-2.5 py-1.5 text-[11.5px] leading-relaxed text-warning"
          >
            <span
              aria-hidden="true"
              className="mt-[7px] h-1.5 w-1.5 shrink-0 rounded-full bg-warning"
            />
            {/* `min-w-0`：这句提示可能很长（"麦克风被别的程序占用了，关掉它再试。"之类），
                而 `flex-1` 的默认 `min-width: auto` 会被长内容顶开，把右边的「重试」
                挤出容器 —— 那正是最需要点它的时刻。 */}
            <span className="min-w-0 flex-1">{micError}</span>
            <button
              type="button"
              onClick={retryMic}
              // 只听到"重试"两个字不知道重试什么 —— 补一个可访问名
              aria-label="重试打开麦克风"
              // 键盘可达 + 焦点可见（与壳内其它按钮同一套处理）
              className="no-drag shrink-0 rounded-[6px] px-2 py-0.5 text-[11.5px] font-medium text-brand hover:bg-hover focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand/50"
            >
              重试
            </button>
          </div>
        ) : null}

        {hint ? (
          <div className="mt-1.5 px-1 text-[11px] leading-relaxed text-warning">{hint}</div>
        ) : null}

        {/*
          输入框下方这一行：左（打开独立窗口）· 中（模型下拉，相对输入栏居中）
          · 右（打开链路与产物）。这三样原先在对话框顶栏上，产品要求挪下来 ——
          顶栏因此整条撤掉了（见 ChatView）。

          「AI 生成内容可能有误，请对重要信息自行核实；可拖拽或粘贴文件作为附件。」
          那句按产品要求去掉：这一行现在要放模型选择与两个入口，再塞一句免责声明
          会把要紧的东西挤没。
        */}
        {footerLeft || footerCenter || footerRight ? (
          /*
            ⚠️ 用 `grid-cols-3` 而**不是** `flex` + `flex-1`（
            "清空这条对话的按钮要相对于输入栏的位置居中"）。

            原先中间那格是 `flex-1 justify-center` —— 它居中的是**左右两个按钮
            剩下的那片空间**，而左右两个按钮宽度并不相等（左边"打开独立窗口"、
            右边"打开链路与产物"）。于是"中间"会跟着左右文案的长度漂，
            看起来就是没对着输入栏。

            三列等分之后，中间那格的中心恒等于整行的中心，与左右内容无关。
            `min-w-0` 是给格子里的文字留出缩略余地，否则窄窗口下会把中间挤走。
          */
          <div className="mt-1.5 grid grid-cols-3 items-center gap-3 px-1 text-[11px] text-ink-faint">
            <div className="flex min-w-0 items-center gap-1.5">{footerLeft}</div>
            <div className="flex min-w-0 items-center justify-center">{footerCenter}</div>
            <div className="flex min-w-0 items-center justify-end gap-1.5">{footerRight}</div>
          </div>
        ) : null}

        {footerNote ? (
          <div className="mt-1.5 px-1 text-[11px] text-ink-faint">{footerNote}</div>
        ) : null}
      </div>
    </div>
  )
}
