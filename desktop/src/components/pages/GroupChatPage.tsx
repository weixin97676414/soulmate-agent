import clsx from 'clsx'
import {
  AlertCircle,
  AlertTriangle,
  ChevronDown,
  ChevronUp,
  Eraser,
  Loader2,
  PanelLeftClose,
  PanelRightClose,
  PictureInPicture2,
  Plus,
  Settings2,
  MessageSquarePlus,
  Trash2,
  Users,
} from 'lucide-react'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'

import { AssistantAvatar } from '@/components/chat/AssistantFormModal'
import { ComposerShell } from '@/components/chat/ComposerShell'
// 思考强度 / 权限两个控件与单聊**共用同一个组件**（值走受控模式）：
// 复制一份样式的话，配色与档位文案改了一处另一处就慢半拍 —— 用户看到的是
// "群里和单聊的按钮不一样"，而那会被直接读成"其中一个坏了"。
import { ConfirmModeButton } from '@/components/chat/ConfirmModeButton'
// 群头像与「左上角标题栏」**共用同一个组件**：圆角比例、点开大图、没头像时的
// 兜底图标都收在它里面，两处不可能长出不一样的样式。
import { GroupAvatar } from '@/components/chat/GroupAvatar'
import { Markdown } from '@/components/chat/Markdown'
// 语音设置面板与单聊**共用同一个组件**（里面只有"当前主体"那一区按上下文换
// 内容：群聊页显示当前群）。见 `VoicePanel` 文件头"当前主体"那一段。
import { VoicePanel } from '@/components/chat/VoicePanel'
import { ReasoningEffortButton } from '@/components/chat/ReasoningEffortButton'
import type { PaletteItem } from '@/components/chat/SlashCommandPanel'
import { UserProfileDialog } from '@/components/chat/UserProfileDialog'
import { GroupContextMenu, GroupThreadContextMenu } from '@/components/pages/GroupContextMenu'
import { Button, IconButton, Modal } from '@/components/ui'
import { useCollapsed } from '@/lib/collapse'
// 切群入口 —— **与语音喊群名同一条路**（见 services/groupSwitch.ts）
import { switchGroup } from '@/services/groupSwitch'
import { readImageAsDataUrl, AVATAR_MAX_SIZE } from '@/lib/image'
import { formatFull } from '@/lib/time'
import { loadUserProfile, subscribeUserProfile } from '@/lib/userProfile'
import { useStickToBottom } from '@/lib/useStickToBottom'
import { useVoiceSessionStore } from '@/stores/voiceSessionStore'
import { useAppStore } from '@/stores/appStore'
import { useAssistantStore } from '@/stores/assistantStore'
import { useGroupStore } from '@/stores/groupStore'
import { useNotificationStore } from '@/stores/notificationStore'
import { useUserProfileDialogStore } from '@/stores/userProfileDialogStore'
import { useVoiceCommand } from '@/stores/voiceCommandStore'
import type { GroupProfile, GroupThread, GroupUpdate, RunRecord } from '@/types'

/**
 * 群聊里可用的斜杠命令。
 *
 * 只有三条 —— 这是**按群聊的真实能力裁剪**的结果，不是偷懒：
 * 群聊没有会话级模型（每个搭子有自己的）、也没有会话级上下文预算
 * （记录是逐条事件流）。
 *
 * ⚠️ 这里原先还写着"群聊没有新会话（话题就是它的边界）"—— 那句话**已经过时**：
 * 产品要求每个群可以有多条对话，所以群聊现在**有**新对话这个概念，
 * 入口在输入栏左下角（与单聊同一个位置）。之所以没顺手加一条 `/new` 命令：
 * 语音/斜杠命令表是用户能改的配置，多一条就要多一处说明，而那个按钮已经
 * 足够显眼了。
 */
const GROUP_COMMANDS: Array<{ name: string; label: string; tone?: 'danger' }> = [
  { name: 'clear', label: '清空本群的讨论记录', tone: 'danger' },
  { name: 'stop', label: '停止正在进行的讨论' },
  { name: 'help', label: '查看群聊里可用的命令' },
]

function matchGroupCommands(query: string): typeof GROUP_COMMANDS {
  const lower = query.trim().toLowerCase()
  if (!lower) return GROUP_COMMANDS
  return GROUP_COMMANDS.filter((command) =>
    `${command.name} ${command.label}`.toLowerCase().includes(lower),
  )
}

/**
 * 群聊（搭子群）：把多个搭子拉进一个群，用户抛出话题后搭子们**自主讨论**
 * —— 按发言顺序逐轮流式发言、可互相 @、可发起结束投票，投票通过后由发起者
 * 做总结（#6 #8）。发言逐条实时出现，可随时叫停。
 *
 * ⚠️ 所有状态都在 `useGroupStore` 里，**不在本组件**：群聊记录会落库，
 * 切页面/重启后仍在；正在进行的讨论也不会因为离开页面而丢（反馈 #6）。
 */
/*
  ⚠️ 这里原本有一个 `GroupPolicyRow`（横贯顶部一行的「思考强度」下拉 +
  「群里一律批准」开关）。按产品要求**删掉**，那两个控件改由
  输入栏左下角的 `toolbarLeft` 承载（与单聊同一行、同一样式）。

  它原先的设计说明仍然成立、只是换了位置：思考强度与权限是**这个群**的属性，
  优先于成员各自的设置（群 > 成员 > 不发送），高危（admin）级操作不受
  「一律批准」影响 —— 那是安全边界，不是体验开关。
*/

/**
 * 群列表项下面那行：把参与的搭子**列出来**（产品要求，
 * 原先只显示"X 位成员"）。
 *
 * 只占**一行**，超出就用一个向下的小箭头展开看全部。
 *
 * ⚠️「是否超出」必须**实测**（`scrollWidth > clientWidth`），不能按名字长度估：
 * 同一个群在不同皮肤的字号下宽度不同，估出来的箭头会时有时无 —— 而"该有的时候
 * 没有"，意味着用户永远看不到完整成员，界面上还没有任何线索提示他被截断了。
 */
function MemberLine({ names }: { names: string[] }) {
  const [expanded, setExpanded] = useState(false)
  const [overflowing, setOverflowing] = useState(false)
  const ref = useRef<HTMLSpanElement>(null)

  useEffect(() => {
    const element = ref.current
    if (!element) return
    // `+1` 是给亚像素舍入留的余量：不加的话，刚好占满一行时会被判成溢出、
    // 冒出一个点了没反应的箭头
    const measure = () => setOverflowing(element.scrollWidth > element.clientWidth + 1)
    measure()
    // 宽度会变（独立窗口拉伸、侧栏折叠），所以跟着 resize 重测，
    // 而不是只在挂载时量一次
    const observer = new ResizeObserver(measure)
    observer.observe(element)
    return () => observer.disconnect()
  }, [names])

  if (names.length === 0) {
    return <div className="mt-0.5 text-[11px] text-ink-faint">还没有成员</div>
  }

  return (
    <div className="mt-0.5 flex items-start gap-1">
      <span
        ref={ref}
        title={names.join('、')}
        className={clsx(
          'min-w-0 flex-1 text-[11px] text-ink-faint',
          expanded ? 'break-all' : 'truncate',
        )}
      >
        {names.join('、')}
      </span>
      {/* 展开之后 `overflowing` 会因为换行而变回 false，所以判据要并上 `expanded`
          —— 否则一点开箭头就消失，用户再也收不回去 */}
      {overflowing || expanded ? (
        <button
          type="button"
          aria-expanded={expanded}
          aria-label={expanded ? '收起群成员' : '展开全部群成员'}
          onClick={(event) => {
            // 别把点击冒泡到行上 —— 那会顺手把群切走
            event.stopPropagation()
            setExpanded((prev) => !prev)
          }}
          className="mt-[1px] shrink-0 rounded-[4px] text-ink-faint transition-colors hover:text-ink"
        >
          <ChevronDown
            size={11}
            className={clsx('transition-transform', expanded && 'rotate-180')}
          />
        </button>
      ) : null}
    </div>
  )
}

/**
 * 群头像选择器（建群弹窗与「群设置」弹窗共用）。
 *
 * ⚠️ 只给"上传一张"这一个入口，**不做图库挑选墙**：默认那条"不上传"的路已经
 * 覆盖了（自动配一张，与 AI 建群同一条规则），再摆 24 张图让用户挑，会把这个
 * 弹窗从"填个名字就能建"变成一次选择负担 —— 而群头像之后随时能改。
 */
function GroupAvatarPicker({
  value,
  onChange,
  hint,
}: {
  value: string
  hint: string
  onChange: (next: string) => void
}) {
  const inputRef = useRef<HTMLInputElement>(null)

  const pick = async (file: File | undefined) => {
    if (!file) return
    try {
      // `AVATAR_MAX_SIZE`（800）与搭子头像同一个上限：群头像也要写进
      // `groups.json`、每次启动都被读，压到 800 是拿"够清晰"换"配置不膨胀"
      onChange(await readImageAsDataUrl(file, AVATAR_MAX_SIZE))
    } catch (error) {
      useNotificationStore.getState().push({
        level: 'error',
        title: '这张图用不了',
        message: error instanceof Error ? error.message : String(error),
      })
    }
  }

  return (
    <div className="flex items-center gap-3">
      <button
        type="button"
        onClick={() => inputRef.current?.click()}
        title="选择群头像（不选的话会自动配一张）"
        className="group relative h-11 w-11 shrink-0 cursor-pointer overflow-hidden rounded-[10px] border border-line bg-canvas"
      >
        {value ? (
          <img
            src={value}
            alt=""
            draggable={false}
            className="h-full w-full object-cover select-none"
          />
        ) : (
          <span className="flex h-full w-full items-center justify-center text-ink-faint group-hover:text-ink-soft">
            <Plus size={14} />
          </span>
        )}
      </button>
      <div className="min-w-0 flex-1 text-[11.5px] leading-relaxed text-ink-faint">
        <div className="text-ink-soft">群头像</div>
        <div>{value ? "已选好这张；点它可换。" : hint}</div>
      </div>
      {value ? (
        <button
          type="button"
          onClick={() => onChange('')}
          className="shrink-0 rounded-[6px] px-1.5 py-0.5 text-[11.5px] text-ink-faint hover:bg-hover hover:text-ink"
        >
          取消
        </button>
      ) : null}
      <input
        ref={inputRef}
        type="file"
        accept="image/*"
        className="hidden"
        onChange={(event) => void pick(event.target.files?.[0])}
      />
    </div>
  )
}

export function GroupChatPage({
  groupId = '',
  readonly = false,
  threadId = '',
}: {
  /** 独立窗口用：固定打开这个群，并隐掉左侧群列表（与单聊独立窗口同一个做法） */
  groupId?: string
  /**
   * 独立窗口用：固定打开这个群的**哪条对话**。
   *
   * 空串 = 没指定（观察窗、或从群的右键菜单开出来的窗口），进去后落到该群
   * "最近有动静"的那条 —— 与不带参数直接开一个群窗口的行为一致。
   */
  threadId?: string
  /**
   * 只读观察窗：AI 在后台跑讨论时自动弹出的那个。
   *
   * 它**只能看**：不渲染输入栏、不提供清空/删除/改群设置 —— 那场讨论由后端的
   * 后台运行器在跑，这里能发言的话会变成"两场讨论同时往一个群里写"。
   */
  readonly?: boolean
} = {}) {
  const assistants = useAssistantStore((state) => state.assistants)
  /** 独立窗口：没有左侧列表，固定看一个群 */
  const standalone = Boolean(groupId)
  /**
   * 观察窗「就地转可操作」的关键：readonly 是窗口创建时写进启动参数的，创建后
   * 主进程改不了。这里用本地 state 接住它，点「暂停任务」停掉讨论后
   * `setIsReadonly(false)`，当前窗口**不重开**就变成可操作群聊。
   */
  const [isReadonly, setIsReadonly] = useState(readonly)
  /** 暂停任务进行中：期间禁掉按钮，避免连点发出两次停止请求 */
  const [stopping, setStopping] = useState(false)

  const groups = useGroupStore((state) => state.groups)
  const selectedId = useGroupStore((state) => state.selectedId)
  const bubbles = useGroupStore((state) => state.bubbles)
  const busy = useGroupStore((state) => state.busy)
  const loadGroups = useGroupStore((state) => state.loadGroups)
  const selectGroup = useGroupStore((state) => state.selectGroup)
  const createGroup = useGroupStore((state) => state.createGroup)
  const deleteGroup = useGroupStore((state) => state.deleteGroup)
  const clearMessages = useGroupStore((state) => state.clearMessages)
  // ---- 群「对话」（一个群可以有多条，）-------------------- //
  const profileDialogOpen = useUserProfileDialogStore((state) => state.open)

  /**
   * 三栏的折叠状态（与搭子栏 / 对话列表共用 `useCollapsed`，收成 44px 窄条）。
   *
   * ⚠️ key 必须各不相同（`rail:groups` / `rail:group-threads`）：用同一个 key
   * 的话，收起群列表会顺带把对话列表也收起来，而用户只点了一个按钮。
   */
  const [groupsCollapsed, toggleGroupsCollapsed, setGroupsCollapsed] =
    useCollapsed('rail:groups')
  const [threadsCollapsed, toggleThreadsCollapsed, setThreadsCollapsed] =
    useCollapsed('rail:group-threads')

  const threads = useGroupStore((state) => state.threads)
  const activeThreadId = useGroupStore((state) => state.activeThreadId)
  const selectThread = useGroupStore((state) => state.selectThread)
  const startNewThread = useGroupStore((state) => state.startNewThread)
  const deleteThread = useGroupStore((state) => state.deleteThread)
  const renameThread = useGroupStore((state) => state.renameThread)
  const discuss = useGroupStore((state) => state.discuss)

  /*
    ---- 语音（群聊也要能语音唤醒、也要有语音状态）--------

    与单聊**逐项相同**：采集与状态机全在应用级的 `voiceSessionStore`（常驻监听
    只允许有一条麦克风，单聊/群聊两个输入壳各开一条会互相抢设备），这里只是
    把状态订阅出来交给面板与输入栏。

    ⚠️ 面板本体渲染在**对话卡片**那一层（见下面），不是这里 —— 它要铺满整张卡片，
    而输入栏只有一行高，从那儿弹出来的东西不可能与卡片对齐（单聊同理）。
  */
  const voicePanelOpen = useVoiceSessionStore((state) => state.panelOpen)
  const setVoicePanelOpen = useVoiceSessionStore((state) => state.setPanelOpen)
  const voicePhase = useVoiceSessionStore((state) => state.phase)
  const voiceScope = useVoiceSessionStore((state) => state.scope)
  const voiceHeard = useVoiceSessionStore((state) => state.heard)
  const voiceLastHit = useVoiceSessionStore((state) => state.lastHit)
  const voicePending = useVoiceSessionStore((state) => state.pending)
  const disableVoice = useVoiceSessionStore((state) => state.disable)
  const stop = useGroupStore((state) => state.stop)
  const updateGroup = useGroupStore((state) => state.updateGroup)
  const draft = useGroupStore((state) => state.draft)
  const attachments = useGroupStore((state) => state.attachments)
  const setDraft = useGroupStore((state) => state.setDraft)
  // 断点续跑要直接调接口：群 store 不管这件事（它只管"一场讨论怎么跑"）
  const api = useAppStore((state) => state.api)
  const addFiles = useGroupStore((state) => state.addFiles)
  const removeAttachment = useGroupStore((state) => state.removeAttachment)

  const [paletteOpen, setPaletteOpen] = useState(false)
  const [showCreate, setShowCreate] = useState(false)
  const [newName, setNewName] = useState('')
  /**
   * 建群时用户自己选的群头像（data URL）。
   *
   * 空串 = 用户没上传 —— 那是最常见的情况，后端会存空串，前端在拉到清单后
   * 按"优先不与现有群重复"的规则自动配一张（与 AI 建群同一条规则）。
   */
  const [newAvatar, setNewAvatar] = useState('')
  const [picked, setPicked] = useState<string[]>([])
  const [pendingDelete, setPendingDelete] = useState(false)
  const [pendingClear, setPendingClear] = useState(false)
  /** 正在就地改名的那条对话（双击标题进入） */
  const [renamingId, setRenamingId] = useState<string | null>(null)
  /** 待确认删除的对话 —— 删除是不可逆的（连带事件），必须问一次 */
  const [pendingDeleteThread, setPendingDeleteThread] = useState<GroupThread | null>(null)
  /**
   * 对话列表项的右键菜单。
   *
   * 记下 `groupId` 而不只记 thread：菜单可能开着的时候用户切到了别的群
   * （右键之后滚轮/快捷键切群），那时「打开独立窗口」要开的是**原来那个群**
   * 的这条对话，不能跟着当前群跑。
   */
  const [threadMenu, setThreadMenu] = useState<{
    groupId: string
    thread: GroupThread
    x: number
    y: number
  } | null>(null)
  /** 群设置正在保存：期间禁掉控件，避免连点产生两次提交 */
  const [savingSettings, setSavingSettings] = useState(false)
  // ---- 群设置弹窗（改名 / 增删成员 / 发言顺序，建好之后也要能改）---- //
  const [showSettings, setShowSettings] = useState(false)
  const [editName, setEditName] = useState('')
  /** 群设置弹窗里正在编辑的群头像（空串 = 清掉，由前端重新配一张） */
  const [editAvatar, setEditAvatar] = useState('')
  const [editPicked, setEditPicked] = useState<string[]>([])
  /** 右键群列表项弹出的菜单（打开时记录是哪个群、在哪个坐标） */
  const [menu, setMenu] = useState<{ group: GroupProfile; x: number; y: number } | null>(null)

  // 内容变化用一段"签名"表达（与单聊同一做法）：它变了就说明有新内容。
  const bubbleSignature = `${busy ? 'busy' : ''}|${bubbles
    .map((item) => `${item.id}:${item.content.length}`)
    .join('|')}`

  /**
   * 滚动：**贴底才跟随**，用户翻上去就停在那儿，并露出「回到最新」按钮。
   *
   * 这里以前是"每次内容变化都无条件 `scrollTo(底部)`" —— buddy 们讨论时每个字都在触发，
   * 用户手一滑就被拽回底部，**根本翻不上去**（实测反馈："无法通过操作翻看上面的其他
   * buddy 发言"）。什么时候该跟着新内容走，只有用户自己的滚动位置说了算。
   */
  const { ref: scrollRef, showJump, onScroll, jumpToBottom } = useStickToBottom(
    bubbleSignature,
    selectedId,
  )

  /**
   * 上次这场讨论**没跑完**（有搭子挂了，或用户点了停止）。
   *
   * 进度已经落盘（轮次、最后是谁在说），所以这里能明确告诉用户"停在哪儿"。
   * 点「继续讨论」时后端把"接着说什么"给回来，再用**既有的讨论流**继续 ——
   * 复用同一条渲染路径，不另造一套"从断点恢复"的流。
   */
  const [resumable, setResumable] = useState<RunRecord | null>(null)
  const loadResumable = useCallback(async () => {
    if (!api || !selectedId) {
      setResumable(null)
      return
    }
    try {
      const payload = await api.getRuns()
      setResumable(
        payload.runs.find((run) => run.kind === 'group' && run.ref_id === selectedId) ?? null,
      )
    } catch {
      // 拿不到续跑信息不该影响群聊本身（它只是附加提示）
      setResumable(null)
    }
  }, [api, selectedId])

  // 讨论结束时（busy 由 true 变 false）刷新一次：那正是可能产生"没跑完"的时刻
  useEffect(() => {
    void loadResumable()
  }, [loadResumable, busy])

  const resumeDiscussion = async () => {
    if (!api || !resumable) return
    try {
      const payload = await api.resumeRun(resumable.id)
      if (!payload.topic) {
        useNotificationStore.getState().push({
          level: 'warning',
          title: '没法继续这场讨论',
          message: payload.message ?? '这条记录已经不能续跑了。',
        })
        setResumable(null)
        return
      }
      setResumable(null)
      // 先写进输入框再发起：讨论接口读的就是 draft，而这句话必须原样送出去
      setDraft(payload.topic)
      await discuss()
    } catch (error) {
      useNotificationStore.getState().push({
        level: 'error',
        title: '续跑失败',
        message: error instanceof Error ? error.message : String(error),
        autoDismissMs: 0,
      })
    }
  }

  const dropResumable = async () => {
    if (!api || !resumable) return
    try {
      await api.dismissRun(resumable.id)
    } catch {
      // 忽略失败没有后果（下次进来还会看到它）
    } finally {
      setResumable(null)
    }
  }

  // 语音「接着说」：群聊页对应的是「继续讨论」。
  // 只在真有没跑完的讨论时才提供 —— 没有就传 `null`，命令表里也不会出现它。
  useVoiceCommand('chat.continue', resumable && !busy ? () => void resumeDiscussion() : null)

  // 群聊页两栏的折叠 / 展开。
  // ⚠️ 用**定向** `setCollapsed(true/false)` 而不是 `toggle`：说「折叠」时若它本来就
  // 收着，toggle 会把它弹出来，用户只会以为识别错了（同单聊的对话表 / 助手栏那两条）。
  useVoiceCommand('panel.groupThreads', () => setThreadsCollapsed(true))
  useVoiceCommand('panel.groupThreadsExpand', () => setThreadsCollapsed(false))
  useVoiceCommand('panel.groupList', () => setGroupsCollapsed(true))
  useVoiceCommand('panel.groupListExpand', () => setGroupsCollapsed(false))

  const byId = useMemo(() => new Map(assistants.map((item) => [item.id, item])), [assistants])
  const selected = groups.find((item) => item.id === selectedId) ?? null
  /** 当前群的成员名（空态与群列表项都要用，抽出来免得两处各拼一遍） */
  const memberNames = useMemo(
    () => (selected?.member_assistant_ids ?? []).map((id) => byId.get(id)?.name ?? id),
    [selected, byId],
  )

  /**
   * 独立窗口指定的那条对话：等对话列表拉回来之后切过去。
   *
   * ⚠️ 只做**一次**（`appliedInitialThread`）。不加这个标记的话，用户在这个
   * 窗口里手动切到别的对话后，这个 effect 会因为 `activeThreadId !== threadId`
   * 再次成立，把他**拽回**原来那条 —— 表现为"切了没用，过一下又跳回去"。
   *
   * 等待"列表里有它"再切，是因为 `selectGroup` 会先把列表拉回来并落到第一条
   * （那是"没指定对话"时的正确行为）；指定的对话在列表里出现过之后才谈得上切。
   * 指定了一个**不存在**的 id（对话被删了）就什么都不做，留在第一条上。
   */
  const appliedInitialThread = useRef(false)
  useEffect(() => {
    if (!standalone || !threadId || appliedInitialThread.current) return
    if (!threads.some((item) => item.id === threadId)) return
    appliedInitialThread.current = true
    if (activeThreadId !== threadId) void selectThread(threadId)
  }, [standalone, threadId, threads, activeThreadId, selectThread])

  const settingsRequestId = useGroupStore((state) => state.settingsRequestId)
  const clearGroupSettingsRequest = useGroupStore((state) => state.clearGroupSettingsRequest)

  /**
   * 「群设置」请求 —— 来自 App 顶层的**头像大图弹窗**（点群头像 → 顶部那个按钮）。
   *
   * 那个弹窗与这个页面的「群设置」Modal 之间没有可用的调用路径（一个在 App 顶层、
   * 一个在页面局部），所以走 store 传一个"请求"，这里看到就打开。
   *
   * ⚠️ 处理完**必须清掉**（`clearGroupSettingsRequest`）：不清的话，用户关掉弹窗
   * 之后再切回群聊页，这个 effect 会因为他重新挂载而再打开一次 —— 他会觉得
   * "这个弹窗关不掉"。
   */
  useEffect(() => {
    if (!settingsRequestId) return
    const group = useGroupStore.getState().groups.find((item) => item.id === settingsRequestId)
    if (group) {
      void selectGroup(group.id)
      setEditName(group.name)
      setEditAvatar(group.avatar)
      setEditPicked([...group.member_assistant_ids])
      setShowSettings(true)
    }
    clearGroupSettingsRequest()
  }, [settingsRequestId, clearGroupSettingsRequest, selectGroup])

  /**
   * 用户自己的头像与昵称（纯本机数据，存在 localStorage 里）。
   *
   * ⚠️ 订阅 `user-profile-changed` 而不是"挂载时读一次"：用户在外观设置里换了
   * 头像之后，消息列表里那些旧头像要**立刻**跟着换 —— 否则他会以为没生效，
   * 然后再改一次。
   */
  const [userAvatar, setUserAvatar] = useState(() => loadUserProfile().avatar)
  useEffect(
    () => subscribeUserProfile(() => setUserAvatar(loadUserProfile().avatar)),
    [],
  )

  /**
   * 观察窗「暂停任务」：停掉正在跑的后台讨论，然后把窗口就地变成可操作群聊。
   *
   * 停止走后端 `/groups/{id}/stop`（取消后台那个协程），它会自动写「讨论被中断」
   * 并推 group_task_done；这里只负责把只读形态收起来。
   */
  const pauseTask = async () => {
    if (!api || !selected || stopping) return
    setStopping(true)
    try {
      await api.stopGroupDiscussion(selected.id)
      setIsReadonly(false)
    } catch (error) {
      useNotificationStore.getState().push({
        level: 'error',
        title: '暂停失败',
        message: error instanceof Error ? error.message : String(error),
      })
    } finally {
      setStopping(false)
    }
  }

  useEffect(() => {
    if (!standalone) {
      void loadGroups()
      return
    }
    // 独立窗口：先把群清单拉回来（成员名靠它解析），再**固定切到目标群**。
    // 顺序不能反 —— `loadGroups` 在没有选中项时会自动选中第一个群，
    // 反过来写会让窗口先闪一下别的群再跳过去。
    void (async () => {
      await loadGroups()
      await selectGroup(groupId)
    })()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [standalone, groupId])

  const submitCreate = async () => {
    if (!newName.trim() || picked.length === 0) return
    try {
      await createGroup({
        name: newName.trim(),
        member_assistant_ids: picked,
        // 勾选并调整后的顺序就是发言顺序
        speaking_order: picked,
        // 空串 = 没上传 → 后端存空串 → 前端拉到清单后自动配一张
        avatar: newAvatar,
      })
    } catch (error) {
      // ⚠️ 不能静默：建群失败时用户点了「创建」却什么都没发生，
      // 而弹窗还开着 —— 他只会再点一次（然后失败第二次）
      useNotificationStore.getState().push({
        level: 'error',
        title: '建群失败',
        message: error instanceof Error ? error.message : String(error),
        autoDismissMs: 0,
      })
      return
    }
    setShowCreate(false)
    setNewName('')
    setPicked([])
    setNewAvatar('')
  }

  const togglePick = (id: string) =>
    setPicked((prev) => (prev.includes(id) ? prev.filter((item) => item !== id) : [...prev, id]))

  /**
   * 保存群级策略（思考强度 / 权限模式）。
   *
   * 与「群设置」弹窗共用同一个 `savingSettings` 闸门：两者写的是同一份配置，
   * 各自维护一个"保存中"标志的话，用户在弹窗里点保存、同时又在输入栏上点
   * 切换档位，两次提交会互相覆盖（后到的把先到的结果盖掉）。
   */
  const saveGroupPolicy = async (patch: GroupUpdate) => {
    if (!selected) return
    setSavingSettings(true)
    try {
      await updateGroup(selected.id, patch)
    } finally {
      setSavingSettings(false)
    }
  }

  /** 群设置保存：改名 + 增删成员 + 发言顺序一次提交（局部更新，只动这些字段） */
  const submitSettings = async () => {
    // ⚠️ 不再要求 `editPicked.length >= 2`（与后端一并放开）：手动建的群
    // 可以只有 0/1 个搭子，用户想怎么安排就怎么安排。
    if (!selected || !editName.trim()) return
    setSavingSettings(true)
    try {
      const patch: {
        name?: string
        member_assistant_ids: string[]
        speaking_order: string[]
        avatar?: string
      } = {
        member_assistant_ids: editPicked,
        speaking_order: editPicked,
      }
      if (editName.trim() !== selected.name) patch.name = editName.trim()
      // 头像只在**真的变了**的时候传：每次都传会让后端重走一遍图片校验与落盘，
      // 而用户多半只是来改个名字的
      if (editAvatar !== selected.avatar) patch.avatar = editAvatar
      await updateGroup(selected.id, patch)
      setShowSettings(false)
    } finally {
      setSavingSettings(false)
    }
  }

  /** 调整发言顺序：把第 index 个成员上移或下移一位 */
  const movePick = (index: number, delta: number) =>
    setPicked((prev) => {
      const target = index + delta
      if (target < 0 || target >= prev.length) return prev
      const next = [...prev]
      ;[next[index], next[target]] = [next[target], next[index]]
      return next
    })

  // ---- 群里的斜杠命令 ------------------------------------------------- //
  //
  // **按群聊的真实能力裁剪过**（产品要求"与单聊没有区别"，但这里必须少几条）：
  // `/model` 改的是单个会话的模型，而群里每个搭子有自己的模型；
  // `/compact` 压的是会话上下文，而群聊上下文是逐条落库的事件流，
  // 没有会话级预算可言。摆一个点了没反应的命令，比不放更糟 ——
  // 用户会以为功能坏了，footerNote 里也写明了这一点。
  const paletteItems = useMemo<PaletteItem[]>(() => {
    if (!paletteOpen) return []
    const query = (draft.startsWith('/') ? draft.slice(1).split(/\s+/)[0] : '').toLowerCase()
    const matched = matchGroupCommands(query)
    return matched.map((command) => ({
      key: command.name,
      title: `/${command.name}`,
      detail: command.label,
      tone: command.tone,
    }))
  }, [paletteOpen, draft])

  useEffect(() => {
    const shouldOpen = draft.startsWith('/') && !busy
    setPaletteOpen(shouldOpen)
  }, [draft, busy])

  const runGroupCommand = (item: PaletteItem) => {
    setDraft('')
    setPaletteOpen(false)
    if (item.key === 'clear') {
      // 复用已有的确认弹窗：清空是不可逆的，不该一下点掉
      setPendingClear(true)
      return
    }
    if (item.key === 'stop') {
      stop()
      return
    }
    if (item.key === 'help') {
      useNotificationStore.getState().push({
        level: 'info',
        title: '群聊里可用的命令',
        message:
          GROUP_COMMANDS.map((command) => `/${command.name} — ${command.label}`).join('\n') +
          '\n\n换模型与压缩上下文是"单个对话"的概念：群里每个搭子有自己的模型，' +
          '上下文也是逐条记录，所以这两个命令在群里不适用。',
        autoDismissMs: 0,
      })
    }
  }

  return (
    // `min-h-0` + `h-full` 是给**独立窗口**用的：那里这层是窗口内容区唯一的子节点，
    // 少了高度约束，里面的滚动容器就撑不出可滚高度（表现为滚轮推不动）
    // `gap-2`：三栏各自是独立卡片，留缝才能让圆角成立（与单聊那个容器一致）
    <div className="flex h-full min-h-0 min-w-0 flex-1 gap-[3px]">
      {/*
        左侧：群列表（独立窗口里隐掉：那种窗口只看一个群）。

        ## 折叠态

        与搭子栏 / 对话列表同一套（`useCollapsed`，收成 44px 窄条）——
        产品要求"在它原来的位置增加收起展开按钮"，而那个位置
        原本放的是「建群」按钮（已挪到下面一行）。

        ⚠️ 折叠态和展开态**都**要带 `standalone && 'hidden'`：独立窗口里
        这一栏整个不该出现，漏掉折叠态那个分支的话，一个在普通窗口里收起来的
        群列表会在独立窗口里冒出来。
      */}
      {groupsCollapsed ? (
        <aside
          className={clsx(
            'flex w-[44px] shrink-0 flex-col items-center overflow-hidden rounded-[12px] border border-line bg-panel py-2.5',
            standalone && 'hidden',
          )}
        >
          {/* 「展开」用箭头**向右**的图标，与展开态那个（箭头向左）构成镜像 ——
              理由见 SessionList 里那段说明 */}
          <IconButton
            label="展开群聊列表"
            onClick={toggleGroupsCollapsed}
            className="text-ink-faint"
          >
            <PanelRightClose size={15} />
          </IconButton>
          <IconButton
            label="新建群"
            onClick={() => setShowCreate(true)}
            className="mt-3 border border-line bg-canvas text-ink-soft"
          >
            <Plus size={16} />
          </IconButton>
        </aside>
      ) : (
      <aside
        className={clsx(
          // 与搭子栏 / 对话列表同宽同款（产品要求三处列表样式一致）
          'flex w-[240px] shrink-0 flex-col overflow-hidden rounded-[12px] border border-line bg-panel',
          standalone && 'hidden',
        )}
      >
        {/* 标题行：左边是栏名，右边是**收起**按钮（产品要求把
            「建群」从这里挪到下面一行、腾出的位置给收起/展开） */}
        <div className="flex h-11 shrink-0 items-center justify-between px-2.5">
          <div className="flex items-center gap-1.5 pl-0.5 text-[13px] font-medium text-ink">
            <Users size={14} className="text-brand" />
            群聊
          </div>
          <IconButton
            label="隐藏群聊列表"
            onClick={toggleGroupsCollapsed}
            className="mt-0.5 shrink-0 text-ink-faint"
          >
            <PanelLeftClose size={15} />
          </IconButton>
        </div>
        {/*
          「新建群」单独一行，与下面的群名卡片**同宽**
          （"建群→新建群，并将此按钮放到「群聊」的下面一行，
          与群名卡片同宽"）。

          `mx-2` 与列表容器（`px-2`）对齐 —— 卡片就在 `px-2` 里，所以它们
          左右边缘落在同一条线上。原先它在标题行右侧，是个贴右的小按钮，
          与下面的卡片完全对不齐。
        */}
        <div className="shrink-0 px-2 pb-1.5">
          <Button
            variant="secondary"
            size="sm"
            icon={<Plus size={13} />}
            className="h-8 w-full justify-center"
            onClick={() => setShowCreate(true)}
          >
            新建群
          </Button>
        </div>
        <div className="min-h-0 flex-1 overflow-y-auto px-2 pb-3">
          {groups.length === 0 ? (
            <p className="px-2 py-8 text-center text-[12px] text-ink-faint">
              还没有搭子群。点上面的「新建群」把几个搭子拉进来，抛个话题让它们自己聊。
            </p>
          ) : (
            groups.map((group) => (
              // ⚠️ 行本身是 `div` 而不是 `button`：里面还要放一个「⋯」按钮，
              // 而 HTML **不允许**交互元素互相嵌套（button 里套 button 会让
              // 内层那个在某些浏览器里点不动）。所以外层改用 div + role/tabIndex，
              // 键盘可达性（Tab 聚焦 + Enter 选中）自己补上。
              <div
                key={group.id}
                role="button"
                tabIndex={0}
                // ⚠️ 走 `switchGroup`（而不是就地 `selectGroup`）——**与语音喊群名
                // 完全同一条路**（"切换规则和切换搭子时是相同的"）。
                // 那边也调它，所以"用嘴切"和"用鼠标切"不可能分叉。
                onClick={() => switchGroup(group.id)}
                onKeyDown={(event) => {
                  if (event.key === 'Enter' || event.key === ' ') {
                    event.preventDefault()
                    switchGroup(group.id)
                  }
                }}
                onContextMenu={(event) => {
                  event.preventDefault()
                  // 与对话菜单互斥（理由见对话项那处）
                  setThreadMenu(null)
                  setMenu({ group, x: event.clientX, y: event.clientY })
                }}
                className={clsx(
                  'no-drag group mb-0.5 flex w-full cursor-pointer items-center gap-1 rounded-[8px] px-2.5 py-2 text-left transition-colors focus:outline-none focus-visible:ring-1 focus-visible:ring-brand',
                  selected?.id === group.id ? 'bg-brand-soft' : 'hover:bg-hover',
                )}
              >
                {/*
                  群头像 —— 渲染规则全部收在 `GroupAvatar` 里（圆角比例、点开大图、
                  没头像时的兜底图标）。

                  ⚠️ 尺寸 **32**（"群名卡片上的头像放大一圈"）——
                  原先是 26，与搭子栏那个摆在一起时显得偏小。32 正好等于这一行
                  两行正文（13 + 11 + 行距）的高度，头像与文字块齐平。

                  ⚠️ 之所以不再就地写 `<button><img>`：**左上角标题栏现在也要显示
                  同一个群头像**。两处各写一份的话，圆角差 1px、兜底图标差一号，
                  看起来就像"其中一个没对齐"。
                */}
                <GroupAvatar group={group} size={32} />
                <div className="min-w-0 flex-1">
                  <div className="truncate text-[13px] text-ink">{group.name}</div>
                  {/* 列出成员而不是"X 位成员"：一个群叫什么
                      是我起的，里面有谁才是我真正关心的 */}
                  <MemberLine
                    names={group.member_assistant_ids.map((id) => byId.get(id)?.name ?? id)}
                  />

                </div>
                {/*
                  ⚠️ 这里原本有个「⋯」按钮（右键菜单的可见入口），按
                  要求**剔除**。

                  右键菜单本身保留（行上仍有 `onContextMenu`）—— 去掉的只是这个
                  常驻图标。为什么值得去掉：它占着卡片右侧一格，而行里的"群名 +
                  成员名单"本来就挤（名单经常要截断）；而右键菜单**另外还有入口**
                  （「群设置」弹窗、以及对话列表那套），不缺这一个。
                */}
              </div>
            ))
          )}
        </div>
      </aside>
      )}

      {/*
        中间：该群的**对话列表**（"每个群可能产生多个对话"）。

        与单聊的结构对齐 —— 单聊是「搭子列表 | 会话列表 | 对话区」，
        群聊现在是「群列表 | 对话列表 | 讨论区」。同一件事在两个页面长成同一个
        形状，用户不用重新学一遍。

        ⚠️ 独立窗口（`standalone`）里隐藏：那种窗口只看一个群，而它连群列表都
        隐掉了 —— 再塞一栏对话列表会把对话框挤到很窄。观察窗/独立窗口要换对话的
        场景很少（AI 后台讨论固定落在最近一条上）。
      */}
      {threadsCollapsed ? (
        <aside
          className={clsx(
            'flex w-[44px] shrink-0 flex-col items-center overflow-hidden rounded-[12px] border border-line bg-panel py-2.5',
            standalone && 'hidden',
          )}
        >
          <IconButton
            label="展开对话列表"
            onClick={toggleThreadsCollapsed}
            className="text-ink-faint"
          >
            <PanelRightClose size={15} />
          </IconButton>
          {isReadonly ? null : (
            <IconButton
              label="开启新对话"
              onClick={() => void startNewThread()}
              className="mt-3 border border-line bg-canvas text-ink-soft"
            >
              <MessageSquarePlus size={16} />
            </IconButton>
          )}
        </aside>
      ) : (
      <aside
        className={clsx(
          // ⚠️ 宽度必须与单聊的会话列表**逐像素相同**（`SessionList` 是 `w-[240px]`）：
          // 这两个列表在同一个位置、同一个角色，宽度差一点就会被看成"没对齐"。
          'flex w-[240px] shrink-0 flex-col overflow-hidden rounded-[12px] border border-line bg-panel',
          standalone && 'hidden',
        )}
      >
        {/* 标题行：左边栏名、右边**收起**按钮（产品要求把
            「群设置」「新对话」从这里挪走，腾出的位置给收起/展开） */}
        <div className="flex h-11 shrink-0 items-center justify-between px-2.5">
          <div className="flex items-center gap-1.5 pl-0.5 text-[13px] font-medium text-ink">
            <MessageSquarePlus size={14} className="text-brand" />
            对话
          </div>
          <IconButton
            label="隐藏对话列表"
            onClick={toggleThreadsCollapsed}
            className="mt-0.5 shrink-0 text-ink-faint"
          >
            <PanelLeftClose size={15} />
          </IconButton>
        </div>
        {/*
          「群设置」单独一行、与下面的对话卡片**同宽**。

          ⚠️ 「新对话」**已剔除**—— 它与输入栏左下角那个
          「开启新对话」是同一个动作（`startNewThread`），两处常驻入口是重复。
          输入栏那个更靠近"你要开始说话"的位置，留它。
        */}
        {isReadonly || !selected ? null : (
          <div className="shrink-0 px-2 pb-1.5">
            <Button
              variant="secondary"
              size="sm"
              icon={<Settings2 size={13} />}
              className="h-8 w-full justify-center"
              onClick={() => {
                // 打开前把当前群的状态灌进去：改的是它、不是新建
                setEditName(selected.name)
                setEditAvatar(selected.avatar)
                setEditPicked([...selected.member_assistant_ids])
                setShowSettings(true)
              }}
            >
              群设置
            </Button>
          </div>
        )}
        <div className="min-h-0 flex-1 overflow-y-auto px-2 pb-3">
          {threads.length === 0 ? (
            <p className="px-2 py-8 text-center text-[12px] text-ink-faint">正在载入对话…</p>
          ) : (
            threads.map((thread) => {
              const activeItem = thread.id === activeThreadId
              const editingThis = renamingId === thread.id
              return (
                <div
                  key={thread.id}
                  // ⚠️ `div` + role 而不是 `button`：行内还要放「⋯」按钮，
                  // HTML 不允许交互元素互相嵌套（与群列表同一处理）
                  role="button"
                  tabIndex={0}
                  onClick={() => void selectThread(thread.id)}
                  // 双击改名（与单聊的会话列表一致），右键出一份完整菜单
                  onDoubleClick={() => setRenamingId(thread.id)}
                  onContextMenu={(event) => {
                    event.preventDefault()
                    // 两份菜单互斥：用户先右键群、再右键对话时，若都留着，
                    // 屏幕上会同时压着两个上下文菜单（后开的盖在前的上面），
                    // 点一下关掉的是上层那个，下层那个还在 —— 看起来像"关不掉"。
                    setMenu(null)
                    setThreadMenu({
                      groupId: selectedId ?? '',
                      thread,
                      x: event.clientX,
                      y: event.clientY,
                    })
                  }}
                  onKeyDown={(event) => {
                    if (event.key === 'Enter' || event.key === ' ') {
                      event.preventDefault()
                      void selectThread(thread.id)
                    }
                  }}
                  className={clsx(
                    'group mb-0.5 flex w-full cursor-pointer items-center gap-1 rounded-[8px] px-2.5 py-2 text-left transition-colors focus:outline-none focus-visible:ring-1 focus-visible:ring-brand',
                    activeItem ? 'bg-brand-soft' : 'hover:bg-hover',
                  )}
                >
                  {editingThis ? (
                    <input
                      autoFocus
                      defaultValue={thread.title}
                      onClick={(event) => event.stopPropagation()}
                      onBlur={(event) => {
                        setRenamingId(null)
                        const next = event.target.value.trim()
                        if (next && next !== thread.title) void renameThread(thread.id, next)
                      }}
                      onKeyDown={(event) => {
                        if (event.key === 'Enter') event.currentTarget.blur()
                        if (event.key === 'Escape') setRenamingId(null)
                      }}
                      className="h-6 min-w-0 flex-1 rounded-[6px] border border-line bg-canvas px-1.5 text-[12.5px] text-ink focus:border-brand focus:outline-none"
                    />
                  ) : (
                    /*
                      ⚠️ 字号必须与**群名卡片**逐项相同（"群名卡片
                      与群对话名的卡片高度宽度都相同"）：13px 主标题 + 11px 次行。

                      原先这里是 12.5 / 10.5 —— 与群名卡片差 0.5px。卡片宽度都是
                      `w-full` 所以并排看不出宽差，但**高度**会差 1px，两栏的行
                      就错开了；滚动起来尤其明显（左边第 3 行对不上右边第 3 行）。
                    */
                    <div className="min-w-0 flex-1">
                      <div
                        className={clsx(
                          'truncate text-[13px]',
                          activeItem ? 'text-brand' : 'text-ink',
                        )}
                        title={thread.title}
                      >
                        {thread.title}
                      </div>
                      <div className="mt-0.5 text-[11px] text-ink-faint">
                        {formatFull(new Date(thread.updated_at).getTime())}
                      </div>
                    </div>
                  )}
                  {isReadonly || editingThis ? null : (
                    <button
                      type="button"
                      aria-label="删除这条对话"
                      title="删除这条对话"
                      onClick={(event) => {
                        event.stopPropagation()
                        setPendingDeleteThread(thread)
                      }}
                      className="hidden shrink-0 rounded-[6px] p-1 text-ink-faint hover:bg-hover hover:text-danger group-hover:block"
                    >
                      <Trash2 size={12} />
                    </button>
                  )}
                </div>
              )
            })
          )}
        </div>
      </aside>
      )}

      {/*
        右侧：群聊区。这一层是**列容器**，与单聊 `ChatView` 里那层
        `flex ... flex-col gap-2` 完全对应。

        ⚠️ `gap-2` 是必需的（"对话卡片和输入卡片连接在一起了，
        它俩之间要有间隔"）：这一栏里有**两张独立的卡片** —— 上面的对话卡片、
        下面的输入卡片。少了间距它们会贴成一张，看起来像"输入框长在对话里"。

        ⚠️ 卡片规格（`rounded-[12px]` + `border-line` + `bg-chat-surface`）在
        **消息区那一层**上，不在这一层 —— 这一层只是把两张卡片摞起来。
        把规格加在这里（我上一版的错）会把输入卡片也吞进同一张卡片里，
        圆角与间距全没了。
      */}
      <div className="flex min-w-0 flex-1 flex-col gap-[3px]">
        {selected ? (
          <>
            {/*
              ⚠️ 这里原本是**常驻的一整行**：群名 + 成员名单 + 新窗口/群设置/
              清空对话/删除群四个按钮。按产品要求拆掉：

              · 群名与成员名单**不再显示** —— 左边群列表里那条已经写着它们了，
                而且成员名单现在就在它下面（可展开），顶上再来一遍是重复；
              · 四个按钮全部**按单聊的位置**重新落位（见下面 ComposerShell：
                新窗口→左、清空对话→中、删除群→右；群设置→对话列表顶部）。

              为什么值得拆：单聊的对话栏顶部是**空的**（那块地方早就让给了
              输入栏底栏），群聊却顶着一条横贯整宽的信息栏 —— 两个页面的对话栏
              因此长得完全不一样，用户每次切过去都要重新找按钮在哪。
            */}
            {isReadonly ? (
              // 只读观察窗是**唯一**还留着这一行的情况：它不是单聊的对应物
              // （没有输入栏，所以也没有底栏可放），而「暂停任务」是它唯一的主动作 ——
              // 没有它，用户只能去主窗口把整场讨论停掉。
              <div className="flex h-11 shrink-0 items-center gap-2 border-b border-line bg-canvas px-4">
                <span className="rounded-full bg-brand-soft px-2 py-0.5 text-[11px] text-brand">
                  观察窗（只读）
                </span>
                <span className="min-w-0 flex-1 truncate text-[11px] text-ink-faint">
                  AI 正在后台讨论这一场，这里只能看
                </span>
                <Button
                  size="sm"
                  variant="secondary"
                  disabled={stopping}
                  onClick={() => void pauseTask()}
                >
                  {stopping ? '暂停中…' : '暂停任务'}
                </Button>
              </div>
            ) : null}

            {/*
              ⚠️ 这里原本有一行 `GroupPolicyRow`（思考强度 + 「群里一律批准」开关）。
              按产品要求**撤掉**：这两个控件挪进输入栏左下角、和单聊
              同一行同一样式（见下面 ComposerShell 的 `toolbarLeft`）。

              为什么值得撤：那一行横贯整个聊天区顶部，占着一整条高度，而它装的东西
              只有两个小设置 —— 用户每次进群都要先扫过它。单聊早就把这些收进输入栏了，
              群聊留着那一行只会显得"这两个页面不是一个应用"。
            */}

            {/*
              ⚠️ 这一层**同时就是「对话卡片」**（"群聊的对话部分
              和单聊对比，差了一个深色容器"）。规格与单聊那张逐项相同：
              `rounded-[12px]` + `border-line` + `bg-chat-surface` + `overflow-hidden`。

              原先这里是"三栏排开、消息直接铺在窗口背景上，而输入栏自己是一张
              卡片"—— 同一个页面里文字浮在底色上、输入框却镶着边，像两套东西拼的。

              `overflow-hidden` 是必需的：没有它，滚动的内容会从圆角处溢出去。
            */}
            <div className="relative min-h-0 flex-1 overflow-hidden rounded-[12px] border border-line bg-chat-surface">
              {/*
                语音设置面板**铺满这张卡片**（产品要求：长宽位置与对话框完全一致），
                与单聊那一处逐项对应。

                ⚠️ 为了放它，这一层被拆成了**两层**（原先滚动就长在卡片上）：
                卡片负责圆角/描边/裁剪，内层负责滚动。不拆的话 `absolute inset-0`
                会跟着内容一起滚走 —— 用户滚到一半打开语音设置，面板会跑到屏幕外。
                单聊从一开始就是这个结构（见 `ChatView`），这里只是补齐。
              */}
              {voicePanelOpen ? (
                <VoicePanel
                  phase={voicePhase}
                  scope={voiceScope}
                  heard={voiceHeard}
                  lastHit={voiceLastHit}
                  pending={voicePending}
                  onDisable={disableVoice}
                  onClose={() => setVoicePanelOpen(false)}
                />
              ) : null}

              <div
                ref={scrollRef}
                onScroll={onScroll}
                className="h-full overflow-y-auto px-4 py-4"
              >
              {bubbles.length === 0 ? (
                /*
                  空态与单聊的 `WelcomePanel` **同一套规格**（产品要求
                  "群对话栏也需要一个这样的容器"）：居中大图标 + 标题 + 说明。

                  原先只有一行居中的灰字 —— 同一件事（"这里还没有内容"），
                  单聊给了一整块有主次的欢迎区，群聊只给一句小字，用户会觉得
                  自己进错了页面。规格（88px 圆角方块 / 19px 标题 / 520px 说明）
                  直接从 WelcomePanel 抄过来，两边才会看起来是同一个应用。
                */
                <div className="mx-auto flex h-full w-full flex-col items-center px-6 py-10">
                  {/*
                    构图与单聊的 `WelcomePanel` **逐项相同**（产品要求两处
                    统一）：上下各占一半，头像底边压在中线上，中线以下是名字、再下面是说明。
                    原先两处都是 `justify-center`（整体居中），头像位置随说明长短浮动，
                    "底边压中线"立不住。
                  */}
                  <div className="flex min-h-0 w-full flex-1 flex-col items-center justify-end">
                    {/*
                      ⚠️ 用**这个群的头像**而不是一个通用图标（"群新对话
                      的欢迎页把 logo 替换为该群头像"）。与单聊欢迎页用搭子头像是同一个
                      道理：这一页除了头像和一行说明没有别的内容，而头像是"我现在在看哪个
                      群"唯一的视觉标识。

                      尺寸与单聊欢迎页**逐项相同**（176 + 同样的圆角比例），两边才会看起来
                      是同一个应用。这里也能点开大图 —— 与群名卡片、标题栏同一份实现。
                    */}
                    <GroupAvatar group={selected} size={176} />
                  </div>
                  <div className="flex min-h-0 w-full flex-1 flex-col items-center pt-3">
                    <h1 className="shrink-0 text-[19px] font-semibold text-ink">
                      {selected.name}
                    </h1>
                    <div className="mt-1.5 min-h-0 w-full flex-1 overflow-y-auto px-1">
                      <div className="mx-auto max-w-[520px] text-center text-[13px] leading-relaxed text-ink-soft">
                        {memberNames.length > 0 ? (
                          <p>{memberNames.join('、')}</p>
                        ) : (
                          <p>这个群还没有搭子，去「群设置」拉几个进来。</p>
                        )}
                        <p className="mt-1">
                          抛出一个话题（例如「帮我定一下这周的学习计划」），它们会自己讨论到达成结论。
                        </p>
                      </div>
                    </div>
                  </div>
                </div>
              ) : (
                // ⚠️ 去掉 `max-w-[720px] mx-auto`（群聊内容
                // 不随窗口变宽自适应）。窗口变宽时消息区固定在 720px 居中，
                // 两侧留一大片空白 —— 而群聊恰恰是"内容多、想多看几行"的场景。
                <div className="flex w-full flex-col gap-3">
                  {bubbles.map((item) =>
                    item.kind === 'system' ? (
                      <div key={item.id} className="flex items-center justify-center">
                        <span className="rounded-full bg-panel px-2.5 py-0.5 text-[11px] text-ink-faint">
                          {item.content}
                        </span>
                      </div>
                    ) : (
                      <div
                        key={item.id}
                        className={clsx('flex gap-2.5', item.kind === 'user' ? 'flex-row-reverse' : '')}
                      >
                        {/*
                          ⚠️ 用户自己也要有头像（"群聊当中也要能
                          展示用户的头像，并且点击头像也能和单聊当中一样进行配置"）。

                          原先这里对 `kind === 'user'` 直接不渲染头像 —— 于是同一列
                          里搭子都有脸、只有"我"是个光秃秃的气泡，看不出说的话是谁的。

                          规格与 `MessageItem` 逐项对齐（26px、圆角按 26*(6/22) 取整、
                          无头像时显示品牌色的「我」），点开的是**同一个**「我的资料」
                          弹窗 —— 那是两条路径，不是两份资料。
                        */}
                        {item.kind === 'user' ? (
                          <button
                            type="button"
                            onClick={() => useUserProfileDialogStore.getState().show()}
                            title="修改我的资料"
                            aria-label="修改我的资料"
                            className="mt-0.5 shrink-0 cursor-pointer overflow-hidden"
                            style={{ width: 26, height: 26, borderRadius: Math.round(26 * (6 / 22)) }}
                          >
                            {userAvatar ? (
                              <img
                                src={userAvatar}
                                alt="我"
                                width={26}
                                height={26}
                                draggable={false}
                                className="h-full w-full object-cover select-none"
                              />
                            ) : (
                              <span className="flex h-full w-full items-center justify-center bg-brand-soft text-[11px] text-brand">
                                我
                              </span>
                            )}
                          </button>
                        ) : (
                          <AssistantAvatar
                            profile={byId.get(item.assistantId ?? '') ?? { name: item.name, emoji: '🤖', avatar: '' }}
                            size={26}
                          />
                        )}
                        {/* ⚠️ 这一层**不能**整块加 `text-right`：气泡本体是
                            `inline-block`，文字对齐会**继承**进去 —— 用户写多行时
                            每一行就都贴着右边、左边参差不齐（实测反馈的正是这个）。
                            气泡整体靠右由外层 `flex-row-reverse` 负责；这里只让
                            昵称/时间那一行单独贴右。 */}
                        <div className="max-w-[78%]">
                          <div
                            className={clsx(
                              'mb-0.5 flex items-center gap-1.5 text-[11px] text-ink-faint',
                              item.kind === 'user' && 'justify-end',
                            )}
                          >
                            {item.kind === 'user' ? '我' : item.name}
                            {item.badge ? (
                              <span className="rounded bg-brand-soft px-1 py-px text-[10px] text-brand">
                                {item.badge}
                              </span>
                            ) : null}
                          </div>
                          <div
                            className={clsx(
                              'inline-block rounded-[10px] px-3 py-2 text-left text-[13px] leading-relaxed',
                              item.kind === 'user'
                                ? 'bg-brand whitespace-pre-wrap text-white'
                                : item.kind === 'summary'
                                  ? 'border border-brand/40 bg-brand-soft/40 text-ink'
                                  : 'border border-line bg-canvas text-ink',
                            )}
                          >
                            {/* 搭子的发言按 Markdown 渲染（实测反馈 #5：这里原来是
                                纯文本，于是 `**加粗**`、列表、代码块全都原样显示成符号）。
                                用户自己说的话保持纯文本 —— 与单聊气泡一致。 */}
                            {item.kind === 'user' ? item.content : <Markdown content={item.content} />}
                            {item.streaming ? (
                              <span className="ml-0.5 inline-block animate-pulse">▍</span>
                            ) : null}
                          </div>
                        </div>
                      </div>
                    ),
                  )}
                  {busy ? (
                    <div className="flex items-center gap-2 text-[12px] text-ink-faint">
                      <Loader2 size={13} className="animate-spin" />
                      搭子们正在讨论…
                    </div>
                  ) : null}
                </div>
              )}

              {/* 「回到最新」：与单聊同一个样式与行为（产品要求"保留和单聊一样的回到最新按钮"）。
                  这里用 sticky 而不是 absolute —— 本组件里**滚动容器就是这一层**，
                  absolute 会跟着内容一起滚走；单聊那边多包了一层定位父级，所以能用 absolute。
                  只在用户翻上去时渲染，贴底时它不存在，不占位。 */}
              {showJump ? (
                <button
                  type="button"
                  onClick={jumpToBottom}
                  className={clsx(
                    'no-drag sticky bottom-2 mx-auto flex w-fit items-center gap-1.5 rounded-full',
                    'border border-line bg-canvas px-3 py-1 text-[12px] text-ink-soft shadow-[0_4px_12px_rgba(0,0,0,0.10)] hover:text-ink',
                  )}
                >
                  <ChevronDown size={13} />
                  回到最新
                </button>
              ) : null}
              </div>
            </div>

            {/* 上次这场讨论没跑完：进度已落盘，点「继续讨论」接着它的记录往下说
                （不用重新解释一遍背景 —— 那正是用户说的"别一次失败全白干"）。
                只读观察窗里不给这个按钮：那会在两个窗口里各起一场讨论。 */}
            {resumable && !isReadonly ? (
              <div className="mx-4 mb-1.5 flex items-start gap-2 rounded-[10px] border border-warning/30 bg-warning-soft px-3 py-2">
                <AlertTriangle size={13} className="mt-0.5 shrink-0 text-warning" />
                <div className="min-w-0 flex-1">
                  <div className="text-[12px] text-ink">{resumable.summary}</div>
                  <div className="mt-0.5 text-[11px] text-ink-faint">
                    共 {resumable.step} 条发言 · {formatFull(resumable.updated_at * 1000)}
                  </div>
                </div>
                <Button size="sm" variant="primary" onClick={() => void resumeDiscussion()}>
                  继续讨论
                </Button>
                <Button size="sm" variant="secondary" onClick={() => void dropResumable()}>
                  忽略
                </Button>
              </div>
            ) : null}

            {isReadonly ? (
              // 只读窗**没有输入栏**：能发言的话就成了"两场讨论同时往一个群里写"。
              // 这里要明确说清它是干什么的、以及想去参与该去哪儿 ——
              // 光是不渲染输入框，用户只会以为"输入栏坏了"。
              <div className="border-t border-line bg-canvas px-4 py-3 text-[12px] leading-relaxed text-ink-faint">
                这是 AI 在后台讨论的**观察窗**：只能看，不能在这里发言。
                想参与讨论，请到主窗口的「群聊」页，或在大厅里用「新窗口打开」开一个可操作的群窗口。
              </div>
            ) : (
              <ComposerShell
                /*
                  ⚠️ **不传 `showVoiceInput`**（= 用默认的 true）。

                  这里原先写的是 `showVoiceInput={false}`，理由是"群里语音是错的
                  上下文"。那条理由在**群聊也能被语音唤醒之后已经不成立**了
                  ：群有自己的唤醒词、语音面板里的主体那一区
                  会显示当前群，和单聊完全对应。

                  唯一的例外是**只读观察窗** —— 它连输入框都不渲染（见上面的分支），
                  所以根本不走到这里，也就不需要再传 `false`。
                */
                /*
                  「开启新对话」按钮（产品要求，与单聊同一个位置同一个样式）。
                  单聊那边它会立刻进入一条空白会话；群里同理 —— 新建一条对话并切过去。

                  ⚠️ 只在**可操作**的群聊里给：只读观察窗（AI 后台讨论时弹出的那个）
                  里新建对话没有意义 —— 那场讨论正跑在别的对话上，用户在这个窗口里
                  开一条新的只会让他以为"讨论跑到别处去了"。
                */
                onNewSession={isReadonly ? undefined : () => void startNewThread()}
                /*
                  思考强度 + 权限合并到输入栏左下角（产品要求：位置和样式
                  与单聊一致）。两者都走组件的**受控模式** —— 值来自群设置，改了就写回
                  群设置，与单聊那套（会话 / 全局）互不干扰。

                  ⚠️ 权限那档的 `?? 'interactive'`：群的 `confirm_mode` 为 `null` 时
                  表示"跟随每个成员自己的设置"。三档按钮表达不了"跟随"，所以这里
                  显示成出厂档（每次确认），并在说明里点明当前是跟随状态 ——
                  比给这个组件硬塞一个单聊没有的档位要好，那会破坏"样式一样"。
                */
                toolbarLeft={
                  isReadonly || !selected ? undefined : (
                    <>
                      <ReasoningEffortButton
                        value={selected.reasoning_effort}
                        visible
                        disabled={savingSettings}
                        // ⚠️ 群里的 `null` 不是"关闭"，是"这个群不管，用各成员自己的"
                        // —— 两边的 `null` 语义不同（见组件里 nullLabel 的说明）
                        nullLabel="跟随每个搭子"
                        nullDetail="这个群不统一指定，各自按搭子档案里的档位"
                        note="只对这个群生效，会覆盖每个搭子自己的思考强度设置。"
                        onChange={(next) =>
                          // 组件的档位是 `string | null`（`null` = 跟随每个搭子），
                          // 而群设置那边用空串表示"跟随" —— 这里显式转换，
                          // 不让 `null` 直接漏成后端的 `undefined`
                          void saveGroupPolicy({
                            reasoning_effort: (next ?? '') as GroupUpdate['reasoning_effort'],
                          })
                        }
                      />
                      <ConfirmModeButton
                        value={selected.confirm_mode ?? 'interactive'}
                        disabled={savingSettings}
                        note={
                          selected.confirm_mode === null
                            ? '当前跟随每个搭子自己的设置；在这里选一档就固定为群级设置。高危操作始终会弹窗询问。'
                            : '群设置优先于搭子档案；高危操作始终会弹窗询问。'
                        }
                        onChange={(next) => void saveGroupPolicy({ confirm_mode: next })}
                      />
                    </>
                  )
                }
                /*
                  底栏三槽位与单聊**逐一对应**（产品要求）：
                  左 = 新窗口（单聊是"打开独立窗口"）
                  中 = 清空对话（单聊是模型下拉选单）
                  右 = 删除群（单聊是"打开链路与产物"）

                  ⚠️ 刻意**做成与单聊同款的小按钮**（不是 `Button` 组件）：那里就是
                  三个 `text-[11px]` 的文字按钮，中间那个还是相对输入框居中的。
                  用大一号的 `Button` 会立刻看出"这不是同一套底栏"。
                */
                footerLeft={
                  isReadonly ? null : (
                    <button
                      type="button"
                      // 手动开的群窗口是**可操作**的（false）：与这一页能力一致，
                      // 用户想要的是"把群聊单独拎出来一边看一边干别的"
                      onClick={() => window.agentBridge?.openGroupWindow?.(selected.id, false)}
                      className="flex items-center gap-1 rounded-[6px] px-1.5 py-0.5 hover:bg-hover hover:text-ink"
                    >
                      <PictureInPicture2 size={13} />
                      打开独立窗口
                    </button>
                  )
                }
                footerCenter={
                  isReadonly ? null : (
                    <button
                      type="button"
                      disabled={busy || bubbles.length === 0}
                      onClick={() => setPendingClear(true)}
                      className="flex items-center gap-1 rounded-[6px] px-1.5 py-0.5 hover:bg-hover hover:text-ink disabled:opacity-40 disabled:hover:bg-transparent"
                    >
                      <Eraser size={13} />
                      {/* 说"这条"而不是"对话"：一个群可以有多条对话，
                          按钮上不写清楚会让人以为要把整个群清空 */}
                      清空这条对话
                    </button>
                  )
                }
                footerRight={
                  isReadonly ? null : (
                    <button
                      type="button"
                      disabled={busy}
                      onClick={() => setPendingDelete(true)}
                      className="flex items-center gap-1 rounded-[6px] px-1.5 py-0.5 hover:bg-hover hover:text-danger disabled:opacity-40 disabled:hover:bg-transparent"
                    >
                      删除群
                      <Trash2 size={13} />
                    </button>
                  )
                }
                value={draft}
                onChange={setDraft}
                onSubmit={() => void discuss()}
                busy={busy}
                onStop={stop}
                placeholder="抛出一个话题，搭子们会自己讨论到收敛；可以拖入文件或粘贴图片"
                attachments={attachments}
                onFiles={(files) => void addFiles(files)}
                onRemoveAttachment={removeAttachment}
                paletteOpen={paletteOpen}
                paletteItems={paletteItems}
                paletteEmptyText="群里没有这个命令"
                onPaletteSelect={runGroupCommand}
                /*
                  ⚠️ 这里原先还有一段 `footerNote`（「群里每个搭子都有自己的模型与
                  能力；附件会随话题一起交给他们。Enter 发送，Shift + Enter 换行。」），
                  按产品要求**剔除**。它和单聊把说明塞进 placeholder 是
                  同一个取舍：输入栏下方那点高度应该留给**能点的东西**，而不是
                  需要读一遍才知道用不上的一句话。
                */
              />
            )}
          </>
        ) : (
          <div className="flex flex-1 items-center justify-center text-[12.5px] text-ink-faint">
            选择左侧的搭子群开始。
          </div>
        )}
      </div>

      {/*
        「我的资料」弹窗。挂在页面根上**一次**（与单聊 `ChatView` 同一个做法）：
        气泡是列表项，每个都挂一份弹窗既浪费又会同时弹出好几个。
        群聊里用户头像与单聊点开的是同一个弹窗、同一份数据。
      */}
      <UserProfileDialog
        open={profileDialogOpen}
        onClose={() => useUserProfileDialogStore.getState().hide()}
      />

      {/*
        删对话的确认。**必须问一次**：删除会连带它的事件（后端 `GroupThreadRepository.
        delete`），是不可逆的 —— 一次误点就丢掉一整场讨论，而且没有任何地方能找回来。
      */}
      <Modal
        open={pendingDeleteThread !== null}
        onClose={() => setPendingDeleteThread(null)}
        width="max-w-sm"
        title="删除这条对话？"
        description={
          pendingDeleteThread
            ? `「${pendingDeleteThread.title}」里的全部记录会被一起删掉，无法恢复。群本身和其它对话不受影响。`
            : ''
        }
        footer={
          <>
            <Button onClick={() => setPendingDeleteThread(null)}>取消</Button>
            <Button
              variant="primary"
              onClick={() => {
                const target = pendingDeleteThread
                setPendingDeleteThread(null)
                if (target) void deleteThread(target.id)
              }}
            >
              删除
            </Button>
          </>
        }
      >
        {/* 没有额外内容：它要问的就只有"删还是别删"，`description` 已经说全了 */}
        {null}
      </Modal>

      {/* 建群弹窗 */}
      <Modal
        open={showCreate}
        onClose={() => setShowCreate(false)}
        width="max-w-md"
        title="新建搭子群"
        description="勾选要拉进群的搭子；抛出一个话题后，它们会自己讨论、互相接话。"
        footer={
          <>
            <Button onClick={() => setShowCreate(false)}>取消</Button>
            {/*
              ⚠️ 去掉 `picked.length === 0`（"现在用户无法手动
              自定义创建群了，创建按钮灰色。用户手动创建的群，不需要有必须指定的
              搭子 —— 只有 AI 创建的群才保持现状"）。

              为什么这个限制本来就不该有：用户建群之后完全可以**先"群设置"里
              再加人**，而"必须先想好拉谁"会让"我想先建个群"这件事做不成 ——
              按钮从进这个弹窗起就是灰的，他会以为功能坏了。
            */}
            <Button
              variant="primary"
              disabled={!newName.trim()}
              onClick={() => void submitCreate()}
            >
              创建
            </Button>
          </>
        }
      >
        <div className="space-y-3">
          {/*
            ⚠️ 群名称这一栏的边框**加粗并高亮**（"同页面内，群名称
            设置栏的边框要加粗且高亮，包括其中的占位文字也是一样"）。

            `border-2 border-brand/40` + 品牌色的 placeholder：这一栏和下面的勾选列表
            分量完全不同 —— 名字是**必填**的、也是这个弹窗里唯一"必须想一下"的东西；
            其余都能之后再改。原先是和其他输入框一模一样的灰细边，用户会以为
            "填不填都行"，然后在按钮灰着的时候困惑。
          */}
          <input
            value={newName}
            onChange={(event) => setNewName(event.target.value)}
            placeholder="群名称（必填），例如 我的智囊团"
            className="h-9 w-full rounded-[8px] border-2 border-brand/40 bg-canvas px-3 text-[13px] text-ink transition-colors placeholder:font-medium placeholder:text-brand/60 focus:border-brand focus:outline-none"
          />

          {/*
            群头像（"用户可以自己上传，也可以不上传；没上传就按 AI
            创建群的规则随机匹配一张"）。
          */}
          <GroupAvatarPicker
            value={newAvatar}
            onChange={setNewAvatar}
            hint="不上传也行，会自动配一张。"
          />
          <div className="max-h-[240px] overflow-y-auto rounded-[8px] border border-line">
            {assistants.map((assistant) => (
              <label
                key={assistant.id}
                className="flex cursor-pointer items-center gap-2.5 border-b border-line-soft px-3 py-2 last:border-b-0 hover:bg-hover"
              >
                <input
                  type="checkbox"
                  checked={picked.includes(assistant.id)}
                  onChange={() => togglePick(assistant.id)}
                  className="h-3.5 w-3.5 accent-[var(--app-brand)]"
                />
                <AssistantAvatar profile={assistant} size={22} />
                <span className="text-[13px] text-ink">{assistant.name}</span>
              </label>
            ))}
          </div>
          {/* 发言顺序：勾选顺序即默认发言顺序，这里可上下调整 */}
          {picked.length > 0 ? (
            <div className="rounded-[8px] border border-line px-3 py-2">
              <div className="mb-1.5 text-[11.5px] text-ink-soft">
                发言顺序（从上到下依次发言，可调整）
              </div>
              <div className="space-y-1">
                {picked.map((id, index) => (
                  <div key={id} className="flex items-center gap-2">
                    <span className="w-4 shrink-0 text-[11px] text-ink-faint">{index + 1}.</span>
                    <AssistantAvatar profile={byId.get(id) ?? { name: id, emoji: '🤖', avatar: '' }} size={18} />
                    <span className="min-w-0 flex-1 truncate text-[12.5px] text-ink">
                      {byId.get(id)?.name ?? id}
                    </span>
                    <button
                      type="button"
                      disabled={index === 0}
                      onClick={() => movePick(index, -1)}
                      title="上移"
                      aria-label="上移"
                      className="no-drag flex h-6 w-6 items-center justify-center rounded-[5px] text-ink-faint hover:bg-hover hover:text-ink disabled:opacity-30 disabled:hover:bg-transparent"
                    >
                      <ChevronUp size={13} />
                    </button>
                    <button
                      type="button"
                      disabled={index === picked.length - 1}
                      onClick={() => movePick(index, 1)}
                      title="下移"
                      aria-label="下移"
                      className="no-drag flex h-6 w-6 items-center justify-center rounded-[5px] text-ink-faint hover:bg-hover hover:text-ink disabled:opacity-30 disabled:hover:bg-transparent"
                    >
                      <ChevronDown size={13} />
                    </button>
                  </div>
                ))}
              </div>
            </div>
          ) : null}
          <div className="flex items-start gap-2 rounded-[8px] border border-line-soft bg-panel px-3 py-2 text-[11.5px] leading-relaxed text-ink-faint">
            <AlertCircle size={13} className="mt-0.5 shrink-0" />
            <span>
              填好群名称、并至少勾选一个搭子，「创建」按钮才会变为可用。
              <br />
              注意：群聊中搭子们会相互讨论、多轮发言，可能消耗较多 token。
            </span>
          </div>
        </div>
      </Modal>

      {/* 群设置（改名 / 增删成员 / 发言顺序）：复用建群弹窗那套勾选 + 上下移 */}
      <Modal
        open={showSettings}
        onClose={() => setShowSettings(false)}
        width="max-w-md"
        title="群设置"
        description="改群名、增减搭子、调整发言顺序；保存后立刻生效。"
        footer={
          <>
            <Button onClick={() => setShowSettings(false)}>取消</Button>
            <Button
              variant="primary"
              disabled={!editName.trim() || savingSettings}
              onClick={() => void submitSettings()}
            >
              {savingSettings ? '保存中…' : '保存'}
            </Button>
          </>
        }
      >
        <div className="space-y-3">
          {/* 群头像可在这里改（用户从大图弹窗点「群设置」进来，正是为了改它） */}
          <GroupAvatarPicker
            value={editAvatar}
            onChange={setEditAvatar}
            hint="不上传也行，会自动配一张。"
          />
          <input
            value={editName}
            onChange={(event) => setEditName(event.target.value)}
            placeholder="群名称"
            className="h-9 w-full rounded-[8px] border border-line bg-canvas px-3 text-[13px] text-ink placeholder:text-ink-faint focus:border-brand focus:outline-none"
          />
          <div className="max-h-[220px] overflow-y-auto rounded-[8px] border border-line">
            {assistants.map((assistant) => (
              <label
                key={assistant.id}
                className="flex cursor-pointer items-center gap-2.5 border-b border-line-soft px-3 py-2 last:border-b-0 hover:bg-hover"
              >
                <input
                  type="checkbox"
                  checked={editPicked.includes(assistant.id)}
                  onChange={() =>
                    setEditPicked((prev) =>
                      prev.includes(assistant.id)
                        ? prev.filter((item) => item !== assistant.id)
                        : [...prev, assistant.id],
                    )
                  }
                  className="h-3.5 w-3.5 accent-[var(--app-brand)]"
                />
                <AssistantAvatar profile={assistant} size={22} />
                <span className="text-[13px] text-ink">{assistant.name}</span>
              </label>
            ))}
          </div>
          {editPicked.length > 0 ? (
            <div className="rounded-[8px] border border-line px-3 py-2">
              <div className="mb-1.5 text-[11.5px] text-ink-soft">
                发言顺序（从上到下依次发言，可调整）
              </div>
              <div className="space-y-1">
                {editPicked.map((id, index) => (
                  <div key={id} className="flex items-center gap-2">
                    <span className="w-4 shrink-0 text-[11px] text-ink-faint">{index + 1}.</span>
                    <AssistantAvatar profile={byId.get(id) ?? { name: id, emoji: '🤖', avatar: '' }} size={18} />
                    <span className="min-w-0 flex-1 truncate text-[12.5px] text-ink">
                      {byId.get(id)?.name ?? id}
                    </span>
                    <button
                      type="button"
                      disabled={index === 0}
                      onClick={() =>
                        setEditPicked((prev) => {
                          const next = [...prev]
                          ;[next[index], next[index - 1]] = [next[index - 1], next[index]]
                          return next
                        })
                      }
                      title="上移"
                      aria-label="上移"
                      className="no-drag flex h-6 w-6 items-center justify-center rounded-[5px] text-ink-faint hover:bg-hover hover:text-ink disabled:opacity-30 disabled:hover:bg-transparent"
                    >
                      <ChevronUp size={13} />
                    </button>
                    <button
                      type="button"
                      disabled={index === editPicked.length - 1}
                      onClick={() =>
                        setEditPicked((prev) => {
                          const next = [...prev]
                          ;[next[index], next[index + 1]] = [next[index + 1], next[index]]
                          return next
                        })
                      }
                      title="下移"
                      aria-label="下移"
                      className="no-drag flex h-6 w-6 items-center justify-center rounded-[5px] text-ink-faint hover:bg-hover hover:text-ink disabled:opacity-30 disabled:hover:bg-transparent"
                    >
                      <ChevronDown size={13} />
                    </button>
                  </div>
                ))}
              </div>
            </div>
          ) : null}
          <div className="flex items-start gap-2 rounded-[8px] border border-line-soft bg-panel px-3 py-2 text-[11.5px] leading-relaxed text-ink-faint">
            <AlertCircle size={13} className="mt-0.5 shrink-0" />
            <span>至少要留两个搭子，否则讨论不起来。</span>
          </div>
        </div>
      </Modal>

      {/* 清空对话确认 */}
      <Modal
        open={pendingClear}
        onClose={() => setPendingClear(false)}
        width="max-w-md"
        title="清空群聊记录"
        description="只清掉这个群的讨论记录，群本身和成员都保留。"
        footer={
          <>
            <Button onClick={() => setPendingClear(false)}>取消</Button>
            <Button
              variant="danger"
              onClick={() => {
                setPendingClear(false)
                void clearMessages()
              }}
            >
              清空
            </Button>
          </>
        }
      >
        <p className="text-[13px] text-ink">
          确定清空「{selected?.name}」的 {bubbles.length} 条记录吗？清空后无法恢复。
        </p>
      </Modal>

      {/* 删除群确认 */}
      <Modal
        open={pendingDelete}
        onClose={() => setPendingDelete(false)}
        width="max-w-md"
        title="删除搭子群"
        description="群和它的讨论记录都会被删除。"
        footer={
          <>
            <Button onClick={() => setPendingDelete(false)}>取消</Button>
            <Button
              variant="danger"
              onClick={() => {
                setPendingDelete(false)
                if (selected) void deleteGroup(selected.id)
              }}
            >
              删除
            </Button>
          </>
        }
      >
        <p className="text-[13px] text-ink">
          确定删除「{selected?.name}」吗？成员搭子本身不会被删除。
        </p>
      </Modal>

      {/*
        群列表项的右键菜单 —— **只作用于这个群**（
        "群右键的功能是管整个群"）。所以先 `selectGroup`：「删除群」「群设置」
        都得先让右侧切到它，否则用户点了之后不知道改的是哪个群。

        「打开独立窗口」「清空对话」已经从这份菜单里**剔除** —— 它们说的是
        "某一条对话"，放在群上会被读成"清掉整个群的记录"。见下面的对话菜单。
      */}
      {menu ? (
        <GroupContextMenu
          name={menu.group.name}
          x={menu.x}
          y={menu.y}
          onSettings={() => {
            void selectGroup(menu.group.id)
            // 右键菜单只知道 `menu.group`（可能是稍早的一份快照），
            // 所以这里从 store 现取一次，免得头像用的是过期的那个值
            const fresh =
              useGroupStore.getState().groups.find((item) => item.id === menu.group.id) ??
              menu.group
            setEditName(fresh.name)
            setEditAvatar(fresh.avatar)
            setEditPicked([...fresh.member_assistant_ids])
            setShowSettings(true)
            setMenu(null)
          }}
          onDelete={() => {
            void selectGroup(menu.group.id)
            setPendingDelete(true)
            setMenu(null)
          }}
          onClose={() => setMenu(null)}
        />
      ) : null}

      {/*
        对话列表项的右键菜单 —— **只作用于这一条对话**（
        "对话名右键的功能是管这一个对话"）。

        ⚠️ 这里的「删除」和「清空」都作用于 `threadMenu.thread.id`，**不是**
        `activeThreadId`：用户对着 B 对话点了右键，而当前正看着 A —— 那也必须删 B。
        所以清空/删除前先 `selectThread` 切过去：一来用户能看见自己要动的是哪条，
        二来 `clearMessages` 走的就是"当前对话"这条路径。
      */}
      {threadMenu ? (
        <GroupThreadContextMenu
          title={threadMenu.thread.title}
          x={threadMenu.x}
          y={threadMenu.y}
          onRename={() => {
            setRenamingId(threadMenu.thread.id)
            setThreadMenu(null)
          }}
          onOpenWindow={() => {
            // 带上对话 id：开出来的窗口就落在这条上（见 main.ts 的 groupWindows key）
            window.agentBridge?.openGroupWindow?.(
              threadMenu.groupId,
              false,
              threadMenu.thread.id,
            )
            setThreadMenu(null)
          }}
          onClear={() => {
            const target = threadMenu.thread
            void selectThread(target.id).then(() => setPendingClear(true))
            setThreadMenu(null)
          }}
          onDelete={() => {
            setPendingDeleteThread(threadMenu.thread)
            setThreadMenu(null)
          }}
          onClose={() => setThreadMenu(null)}
        />
      ) : null}
    </div>
  )
}
