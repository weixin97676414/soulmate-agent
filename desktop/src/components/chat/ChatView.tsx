import clsx from 'clsx'
import { AlertTriangle, ChevronDown } from 'lucide-react'
import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react'

import { BrandMark } from '@/components/BrandMark'
import { AssistantAvatar } from '@/components/chat/AssistantFormModal'
import { Composer } from '@/components/chat/Composer'
import { DRAWER_GAP, DRAWER_WIDTH, DetailDrawer } from '@/components/chat/DetailDrawer'
import { ComputerUseBar } from '@/components/chat/ComputerUseBar'
import { Markdown } from '@/components/chat/Markdown'
import { MessageItem } from '@/components/chat/MessageItem'
import { PlanBar } from '@/components/chat/PlanBar'
import { UserProfileDialog } from '@/components/chat/UserProfileDialog'
import { VoicePanel } from '@/components/chat/VoicePanel'
import { Button } from '@/components/ui'
import { useVoiceSessionStore } from '@/stores/voiceSessionStore'
import { useStickToBottom } from '@/lib/useStickToBottom'
import { useAppStore } from '@/stores/appStore'
import { useAssistantStore } from '@/stores/assistantStore'
import { useChatStore } from '@/stores/chatStore'
import { useVoiceCommand } from '@/stores/voiceCommandStore'
import { useUserProfileDialogStore } from '@/stores/userProfileDialogStore'
import { useNotificationStore } from '@/stores/notificationStore'
import type { AssistantProfile, RunRecord } from '@/types'

/**
 * 三个内置搭子的欢迎页说明：**文案直接写在前端**。
 *
 * 早前这里是运行时去读 IDENTITY.md 的「自我介绍」段 —— 好处是用户改了身份介绍，欢迎页
 * 跟着变。代价是那份文件里夹着**写给模型的批注**：名字后面挂着一句"没设昵称就先用出厂名，
 * 设了要改成用户给的称呼"的括号说明 —— 那是规则，不是说明，却被原样摆到了欢迎页上给用户看。
 * 用户的口径：批注留在 md 里不动，欢迎页不许再引用 md，直接写。**最初**下面每段 = IDENTITY.md
 * 「自我介绍」的正文逐字，只去掉那句昵称批注（那句里那串原文在此处一个字都不要复述，
 * 打包验收闸正按"这句话不许出现在欢迎页源文件里"来断言）。
 *
 * ⚠️ ：三段**换成了各搭子简介的内容**（用户："欢迎页说明替换为它的简介"）。
 * 原来那三段与档案里的简介（``persona_pack/<id>/简介.md``）是**两份不一致的文本** ——
 * Soulmate 那段原本有 14 行（含心鉴学说明与四点列举），现在与简介对齐成三句。
 * **仍然写死在前端**（用户明确选了这一支，没有改成运行时去读简介文件）。
 *
 * 行与行之间不留空行（原稿每句之间都有空行，照原样渲染会占一屏）：
 * 剩下的单换行由 remarkLineBreaks 转成段内换行，紧凑但层次还在。
 *
 * ⚠️ 改文案改这里，别再回去读文件；文件里的批注是给模型看的，两边的用途已经分开。
 */
const WELCOME_INTRO: Record<string, string> = {
  soulmate: [
    '我是这个世界上最懂你的人',
    /* ⚠️ 这两句换过（原先说的是"会把自己改造成什么"和"一直在"）。
       简介文件（``persona_pack/soulmate/简介.md``）同步改了：用一句话说自己是干嘛的，
       比说"我会变成什么"更直接 —— **两边必须一致**。
       注：这里刻意用块注释，因为打包验收有一条"旧句子不许回来"的断言，
       而行注释不在它剥除的范围内（`spellOut` 只剥块注释 / 三引号 / `#`）。 */
    '因为我能随时知道你最新的状态',
    '我会陪着你，而且会一直都在',
  ].join('\n'),
  LoveBuddy: [
    '我是你的婚恋情感搭子',
    '帮你运营好你的情感关系',
    '我比你更了解你的另一半哦',
  ].join('\n'),
  RelationBuddy: [
    '我是你的职场人际关系运营助手',
    '日常社交问题同样也能分析与解答',
    '深度剖析一个人的行为和内在的心理运作模式',
  ].join('\n'),
}

/**
 * 首屏渲染多少条消息。取 60 是个折中：绝大多数会话根本用不到"载入更早"，
 * 而 60 条 Markdown 的渲染开销在毫秒级；几百条的时候就明显卡了。
 */
const INITIAL_VISIBLE = 60

/** 每次「载入更早」追加多少条 */
const VISIBLE_STEP = 60

function WelcomePanel({ assistant }: { assistant?: AssistantProfile }) {
  const builtinId = assistant?.builtin ? assistant.id : ''

  // 说明文字的取材：三个内置搭子用上面 WELCOME_INTRO 里写死的文案
  // （不再引用 md，理由见那段注释）；总管用它的简介；用户自建搭子用自己写的简介。
  // 都没有就留空 —— 宁可不显示，也不摆一句产品的功能说明书。
  const description = !assistant
    ? ''
    : !builtinId
      ? (assistant.description ?? '')
      : builtinId === 'BuddyManager'
        ? assistant.description
        : (WELCOME_INTRO[builtinId] ?? assistant.description)

  return (
    // ⚠️ 原先这里有 `max-w-[860px]`：窗口变宽到 860 就封顶居中，再宽也不动。
    // 产品要求"随着窗口变宽而自适应"，所以去掉上限 —— 内容跟着
    // 容器走，多宽都用满。
    <div className="mx-auto flex h-full w-full flex-col items-center px-6 py-10">
      {/*
        上下各占一半（「头像底边要与这个空对话页面的中线重叠，
        中线下面才是名字，名字下面才是简介」）。

        原先整块内容是 `justify-center`（整体垂直居中）—— 头像的位置会随着简介
        长短上下浮动，"底边压中线"这条几何关系根本立不住。改成两个各占 50% 高的
        半区之后：上半区 `justify-end` 把头像**底边**顶到中线上，下半区从线以下开始。
      */}
      <div className="flex min-h-0 w-full flex-1 flex-col items-center justify-end">
      {/* 中央这个图标用**当前搭子的头像**（产品要求）。
          以前这里是应用自己的 ``BrandMark``，于是"给搭子换了头像"在这页
          完全看不出来 —— 而新对话恰恰是用户最常看到的一页。
          走既有的 ``AssistantAvatar``（有图用图、没图用 emoji），
          它的注释里写着"四个地方都要渲染它，各写一遍迟早漏掉规则"，
          这里是第五处，同样不另写一份。 */}
      {assistant ? (
        /*
          ⚠️ 尺寸历程：56 → **88**（"放大欢迎页搭子的头像"）→
          **176**（"再放大一倍"）。

          为什么值得一再放大：这一页除了这个头像和一行简介没有别的内容。
          它是"我现在跟谁说话"唯一的视觉标识，而一屏留白里 88 仍然只是一个
          "角标"大小 —— 用户的视线会先落在留白上，再去找头像。
        */
        <AssistantAvatar profile={assistant} size={176} />
      ) : (
        // 兜底：搭子列表还没加载出来（或全被删了）时仍显示应用标识，
        // 而不是在页面正中留一块空白。**保持与头像同尺寸**，否则这一页会在
        // "有搭子"和"没搭子"两种状态下明显跳一下。
        <BrandMark size={176} radius={44} />
      )}
      </div>

      {/* 下半区：中线以下 —— 名字在上、简介在下（产品指定的次序）。
          名字 `shrink-0` 钉住不动，简介自己滚：长文案（Soulmate 那种十几行）
          不会把名字挤出可视区，也不会把整页撑破。 */}
      <div className="flex min-h-0 w-full flex-1 flex-col items-center pt-3">
        {/* 标题=搭子名：昵称优先，与界面其余地方的称呼一致 */}
        <h1 className="shrink-0 text-[19px] font-semibold text-ink">
          {assistant?.nickname?.trim() || assistant?.name || '有什么可以帮你的？'}
        </h1>
        {/* 说明走 **Markdown 组件**渲染（两点）：① 身份介绍里的
            `**加粗**` 要真的加粗，纯文本 pre-line 会把星号原样摆出来；
            ② 文案**居左**（标题与头像仍居中）。compact 压掉段距，配合上面剔掉
            的空行，整块说明紧凑不占一屏。 */}
        {description ? (
          <div className="mt-1.5 min-h-0 w-full flex-1 overflow-y-auto px-1">
            {/* ⚠️ `text-center`（「四个搭子欢迎页的说明，进行居中处理」）：
                原先这里刻意居左（产品约定），但既然头像与名字都在中轴上，
                说明居左会显得整块往右偏。群聊那一侧本来就是居中的（见 GroupChatPage），
                现在两边终于一致了。 */}
            <div className="mx-auto max-w-[520px] text-center text-[13px] leading-relaxed text-ink-soft">
              <Markdown content={description} compact />
            </div>
          </div>
        ) : null}
      </div>
    </div>
  )
}

/**
 * 打开「链路与产物」时窗口要加宽多少。
 *
 * ⚠️ **必须等于「抽屉宽度 + 列间距」**，不能拍脑袋给个近似值。
 * 这一列是窗口向外长出来的一块：窗口只加宽 480、列实际占 550（旧版是
 * `min(560px,46vw)`），**差的那 70 多像素就必然从对话栏里挤** ——
 * 用户看到的"还是往左压缩了一点"正是它，而且窗口越宽差得越多。
 *
 * 所以这里直接复用 `DetailDrawer` 的常量，让"列多宽"和"窗口加多宽"是**同一个数**。
 * 以后改抽屉宽度只需动那一处。
 */
const DRAWER_WIDTH_DELTA = DRAWER_WIDTH + DRAWER_GAP

export function ChatView() {
  const messages = useChatStore((state) => state.messages)
  const profileDialogOpen = useUserProfileDialogStore((state) => state.open)

  /*
    ---- 抽屉打开时把**窗口整体加宽** ----

    看了截图后点明："就是在客户端向右测长出去一块新的容器，
    整体宽度变宽" —— 也就是说这一列**不该从对话栏身上抠**，而该是窗口长出来的一块。

    我前两版都没理解对：先是把对话栏挤窄（并排），后来又改成浮在消息上（覆盖）。
    两种都是"在固定的窗口宽度里做文章"，而用户要的是**窗口本身变宽**。

    好在主进程早就有这条路：`resizeWindowBy` 是侧栏收起/展开时用的同一套
    （收起侧栏 = 窗口跟着收窄，而不是把宽度让给对话栏，见 `lib/collapse.ts`）。
    这里复用同一条通道，语义完全一致。

    ⚠️ 用 `useEffect` 的 cleanup 处理"关闭时收回去"，而不是在关闭分支里手动调：
    cleanup 天然覆盖"组件卸载"（切到设置页、窗口关闭）这几种情况，
    手动调会漏掉它们，窗口就会永久宽出一块。
  */
  const drawerOpen = useChatStore((state) => state.drawerOpen)
  const loadArtifacts = useChatStore((state) => state.loadArtifacts)
  const streaming = useChatStore((state) => state.streaming)
  // 独立窗口要"带着当前会话"过去，所以这里需要知道在看哪一条（产品要求）。
  // 只读一次快照、不在点击时订阅，避免每轮流式都让它重渲染。
  const activeSessionId = useChatStore((state) => state.activeSessionId)
  // 助手自定义聊天背景
  const activeAssistant = useAssistantStore((state) =>
    state.assistants.find((item) => item.id === state.activeId),
  )
  // 「主对话模型」下拉、「查看执行链路与产物」、以及 `isChatWindow` 那套判断，
  // 已随那几个控件一起搬进 `Composer`（产品要求把它们放到输入栏下方那一行）。
  // 留在这里只会剩下没人读的状态订阅 —— 而 zustand 每次变动照样会触发这里重渲染。

  // 语音设置面板：它要铺满这块对话区，所以状态与渲染都在这一层（见下面卡片里那段）。
  const voicePanelOpen = useVoiceSessionStore((state) => state.panelOpen)
  const setVoicePanelOpen = useVoiceSessionStore((state) => state.setPanelOpen)

  /*
    ---- 抽屉打开时把**窗口整体加宽** ----

    看了截图后点明："就是在客户端向右测长出去一块新的容器，
    整体宽度变宽" —— 这一列**不该从对话栏身上抠**，而该是窗口长出来的一块。

    我前两版都理解错了：先是把对话栏挤窄（并排），后来又改成浮在消息上（覆盖）。
    两种都是"在固定的窗口宽度里做文章"，而用户要的是**窗口本身变宽**。

    好在主进程早就有这条路：`resizeWindowBy` 正是侧栏收起/展开时用的同一套
    （收起侧栏 = 窗口跟着收窄，而不是把宽度让给对话栏，见 `lib/collapse.ts`）。
    这里复用同一条通道，语义完全一致。

    ⚠️ 用 `useEffect` 的 cleanup 处理"关闭时收回去"，而不是在关闭分支里手动调：
    cleanup 天然覆盖"组件卸载"（切到设置页、窗口被关）这几种情况，
    手动调会漏掉它们，窗口就会永久宽出一块。
  */
  const showDrawer = drawerOpen && !voicePanelOpen
  /*
    ⚠️ **必须 `useLayoutEffect` + 同步通道**，这一对是消除"闪屏"的关键
    （反馈：打开/收回时整个客户端闪一下）。

    为什么会闪：这一列是"窗口向外长出来的一块"，所以要求"窗口**先**变宽、
    抽屉**后**出现"。而 `useEffect` 是**绘制之后**才跑的，加上 IPC 往返，
    实际顺序变成了：

      帧 1   抽屉 DOM 出现 → 对话栏被硬挤 288px、消息整体重排
      帧 2~3 窗口终于变宽   → 宽度还回去、消息再重排一次

    那一挤一展就是用户看到的"闪"。收回时方向相反、症状一样。

    改成 `useLayoutEffect`（DOM 变更后、浏览器**绘制前**执行）+ `sendSync`
    （阻塞到主进程真的改完窗口宽度）之后，这两件事落在**同一帧**里，
    中间态根本不会被画出来。

    代价是这一下会阻塞渲染进程 —— 而 `setBounds` 是原生调用、亚毫秒级，
    换来"不再闪"是值得的。**侧栏那边仍走异步版**（见 lib/collapse.ts）：
    它没有这个顺序要求，不该白担同步阻塞的风险。

    ⚠️ cleanup 依然负责"关闭时收回去"，而且时机正好：React 的顺序是
    cleanup → DOM 变更 → layout effect，所以关闭时也是"窗口先收窄、抽屉后消失"，
    同样落在同一帧。它同时天然覆盖"组件卸载"（切到设置页、窗口被关）——
    手动调会漏掉这些，窗口就会永久宽出一块。
  */
  useLayoutEffect(() => {
    if (!showDrawer) return
    window.agentBridge?.resizeWindowBySync?.(DRAWER_WIDTH_DELTA)
    return () => {
      window.agentBridge?.resizeWindowBySync?.(-DRAWER_WIDTH_DELTA)
    }
  }, [showDrawer])
  const voicePhase = useVoiceSessionStore((state) => state.phase)
  const voiceScope = useVoiceSessionStore((state) => state.scope)
  const voiceHeard = useVoiceSessionStore((state) => state.heard)
  const voiceLastHit = useVoiceSessionStore((state) => state.lastHit)
  const voicePending = useVoiceSessionStore((state) => state.pending)
  // 面板上没有「开启语音」按钮了（产品要求），所以这里不再订阅 `enable`
  const disableVoice = useVoiceSessionStore((state) => state.disable)

  /**
   * 这一轮对话**没跑完**时留下的现场（失败 / 被停 / 步数用尽）。
   *
   * 为什么读后端而不是靠界面判断：前端拿不到"被取消 / 失败"的权威状态，只能猜；
   * 而且记录存在库里，刷新、切会话、重启之后按钮状态都自愈。
   *
   * 这也是**面向零基础用户**才必须做的：回答停在半路时，他们的第一反应是
   * "是不是坏了"，而不是"我该补一句『继续』"。
   */
  const [resumable, setResumable] = useState<RunRecord | null>(null)

  const loadResumable = useCallback(async () => {
    const api = useAppStore.getState().api
    if (!api || !activeSessionId) {
      setResumable(null)
      return
    }
    try {
      const payload = await api.getRuns()
      setResumable(
        payload.runs.find(
          (run) => run.kind === 'chat' && run.session_id === activeSessionId,
        ) ?? null,
      )
    } catch {
      // 拿不到续跑信息不该影响对话本身（它只是附加提示）
      setResumable(null)
    }
  }, [activeSessionId])

  // 跟着流式的结束刷新：一轮刚跑完才可能出现（或消失）待续跑记录
  useEffect(() => {
    void loadResumable()
  }, [loadResumable, streaming])

  const resume = async () => {
    const api = useAppStore.getState().api
    if (!api || !resumable) return
    try {
      const payload = await api.resumeRun(resumable.id)
      if (!payload.topic) {
        useNotificationStore.getState().push({
          level: 'warning',
          title: '没法接着做',
          message: payload.message ?? '这条记录已经不能续跑了。',
        })
        return
      }
      // 先把它清掉：接着跑起来的是一轮全新的对话（进度行由后端重建），
      // 留着会让用户以为点了没反应
      setResumable(null)
      // ⚠️ 发出去的是后端给的**协议文本**，气泡里只显示「继续」——
      // 把 `[续跑] 上一轮…` 当成用户说过的话显示出来，用户会以为界面坏了
      await useChatStore.getState().send(payload.topic, '继续')
    } catch (error) {
      useNotificationStore.getState().push({
        level: 'error',
        title: '没能接着做',
        message: error instanceof Error ? error.message : String(error),
        autoDismissMs: 0,
      })
    }
  }

  const dismissResumable = async () => {
    const api = useAppStore.getState().api
    if (!api || !resumable) return
    try {
      await api.dismissRun(resumable.id)
    } catch {
      // 忽略失败没有后果（下次进来还会看到它）
    } finally {
      setResumable(null)
    }
  }

  /*
    语音命令（「很多设置存在，但无法真的通过语音操作应用」）。

    这两条以前只写在命令表里、没有任何实现 —— 面板里配了词，说了却没反应。
    ⚠️ 注册点必须在 early return 之前，否则某些状态下命令会凭空消失。
  */
  // 「看执行链路」：与手点右侧抽屉的入口等价（默认落到「执行链路」那页签）
  useVoiceCommand('panel.drawer', () => {
    const store = useChatStore.getState()
    store.setDrawerOpen(true)
    store.setDrawerTab('trace')
  })
  // 「关闭执行链路」：上面那条**只开不关** —— 说了"关闭执行链路"
  // 没有任何反应。这里补上反向动作。
  // ⚠️ 不能写成 toggle：说"关闭"的时候抽屉本来就是开着的，toggle 会把它**再开一次**，
  // 用户只会认为识别错了（搭子栏那两条踩过同一个坑，见 lib/collapse.ts 的 setCollapsed）。
  useVoiceCommand('panel.drawerClose', () => {
    useChatStore.getState().setDrawerOpen(false)
  })
  // 「接着说」：只在真有没跑完的回答时才提供 —— 没有的时候传 `null`，
  // 命令表里就不会出现它（比"说了没反应"诚实，见 useVoiceCommand 的说明）。
  useVoiceCommand('chat.continue', resumable && !streaming ? () => void resume() : null)

  // 产物可能由上一次会话遗留，进入界面时先同步一次，避免抽屉显示空的
  useEffect(() => {
    void loadArtifacts()
  }, [loadArtifacts])

  // 内容长度变化即触发一次滚动，无需监听每个 token。
  //
  // ⚠️ 必须 memo（第 91 批，L-03）：这段拼接是 **O(全部消息)**，而它在**渲染体内**——
  // 流式输出时每来一个 delta 都会重渲染一次 ChatView，于是一条 500 轮的会话每帧
  // 都要把 500 条消息重新拼一遍字符串（只为回答"有没有变"）。挂上 memo 之后
  // 只在 `messages` 这个数组真的换了引用时才重算。
  //
  // 依赖只能是 `messages` 本身：store 每次更新都会产生**新数组**
  //（`chatStore` 走的是不可变更新），所以流式追加一样会命中重算 —— 贴底跟随不受影响；
  // 反过来说**不能**改成 `[messages.length]`，那样"最后一条还在变长"就检测不到，
  // 流式过程中「回到最新」按钮不会出现、也不会自动贴底。
  const contentSignature = useMemo(
    () =>
      messages
        .map((message) => `${message.content.length}:${message.toolCalls.length}:${message.status}`)
        .join('|'),
    [messages],
  )

  // 贴底跟随 + 「回到最新」按钮。与群聊共用一份实现（见 lib/useStickToBottom.ts）——
  // 群聊原本是"无条件拉到底"，讨论进行中用户翻不上去，正是从这份逻辑里改过来的。
  const { ref: scrollRef, showJump, onScroll, jumpToBottom } = useStickToBottom(
    contentSignature,
    activeSessionId,
  )

  // ---- 消息窗口化 ---------------------------------------------------- //
  //
  // ## 为什么是"窗口化"而不是真正的虚拟化
  //
  // 真虚拟化（只挂载可见区域那几个节点）需要按滚动位置算动态高度，而这里有
  // 两个它很难处理的变量：**流式输出的消息每帧都在变高**，以及"贴底"逻辑
  // 每帧都在改 scrollTop。两者叠加时，虚拟化的测量会不断失准，表现是
  // 滚动条乱跳、内容错位 —— 而这些都只能在交互中才看得出来。
  //
  // 窗口化的收益已经覆盖了真正的问题：**首屏不再渲染全部消息**。
  // 一条 500 轮的会话从"渲染 500 个 Markdown"降到 60 个，
  // 剩下的由用户按需加载（一次 60 条）。
  const [visibleCount, setVisibleCount] = useState(INITIAL_VISIBLE)
  // ⚠️ **切会话必须复位窗口**（第 87 批，M-06）：`visibleCount` 是组件级 state，
  // 而切换会话时 `ChatView` **不会重挂载**（`App.tsx` 没给它 `key`）。
  // 于是在 A 会话里点过几次「载入更早」之后，切到 B 会话仍是放大后的窗口 ——
  // "只渲染 60 条"的省流机制被**静默关掉**（长会话开始卡），
  // 而且因为 `hiddenCount` 变成 0，「载入更早」也不再出现。
  useEffect(() => {
    setVisibleCount(INITIAL_VISIBLE)
  }, [activeSessionId])
  // 载入更早的消息会把内容**插到上方**，若不校正，用户眼前那一条会往下跳。
  // 这里记下加载前的总高度，渲染完把滚动位置补上同样的差值。
  const anchorHeight = useRef<number | null>(null)

  const hiddenCount = Math.max(0, messages.length - visibleCount)
  const visibleMessages = hiddenCount > 0 ? messages.slice(-visibleCount) : messages

  const loadEarlier = () => {
    const element = scrollRef.current
    if (element) anchorHeight.current = element.scrollHeight
    setVisibleCount((count) => count + VISIBLE_STEP)
  }

  useLayoutEffect(() => {
    const before = anchorHeight.current
    if (before === null) return
    anchorHeight.current = null
    const element = scrollRef.current
    if (element) element.scrollTop += element.scrollHeight - before
  }, [visibleCount])

  return (
    /*
      ⚠️ 这里是 `[对话列 flex-1] + [抽屉列 shrink-0]` 的**并排布局**。

      看了截图后明确：抽屉要"以单独容器呈现，和搭子列表等
      那样类似的一个新页面容器"，**在对话区右侧新展开**。

      我上一版把它做成了 `absolute` 浮在消息卡片**之上** —— 那既不是新容器
      （它盖住了右侧消息和"回到最新"按钮），也谈不上"往右展开"，
      只是叠了一层纱。现在改成真正的兄弟列：对话列与抽屉列各自是一张独立卡片，
      和「搭子栏 | 对话列表栏 | 对话栏」是同一种结构。

      ⚠️ 这里的 `gap-[3px]` **必须等于 `DRAWER_GAP`**：打开抽屉时窗口要按
      `DRAWER_WIDTH + DRAWER_GAP` 加宽，漏掉这几像素的话，对话栏每次都会被压
      同样多 —— 单看只是一条细缝，但它是"差一点没对齐"的来源。
    */
    <div className="flex min-h-0 min-w-0 flex-1 gap-[3px]">
      {/* ⚠️ `gap-[3px]`：卡片之间只留 3px（"卡片之间的间隔太宽了，
        保留当前宽度的 1/3 即可"——原先 `gap-2` 是 8px）。这个值要与
        `App.tsx` 那层容器、以及群聊页保持一致，否则两个页面的缝隙不一样宽。 */}
    <div className="flex min-h-0 min-w-0 flex-1 flex-col gap-[3px]">
        {/* `bg-chat-surface` 是**不透明**底色（见 index.css）：
            用户上传壁纸时，壁纸只在标题栏/导航栏/侧栏透出，**对话正文区保持干净**
            （要求 #13）—— 文字压在照片的明暗花纹上，长文读起来非常累。
            这里用底色而不是 `background-image`，所以搭子自己的聊天背景
            （下一层那个 div 的 backgroundImage）依然画在它上面，功能不受影响。 */}
        {/* 对话框是**独立卡片**（产品要求）：圆角 + 描边，与输入栏、左侧列表栏各自独立。
            `overflow-hidden` 是必需的 —— 没有它，里面滚动的内容会从圆角处"溢"出去。 */}
        <div className="relative min-h-0 flex-1 overflow-hidden rounded-[12px] border border-line bg-chat-surface">
          {/*
            语音设置面板**铺满这张卡片**（产品要求：长宽位置与对话框完全一致）。
            渲染在这里而不是输入栏里，是因为它要盖住的是"对话"这一块 ——
            输入栏自己只有一行高，从那儿弹出来的任何东西都不可能对齐整块对话框。
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

          {/*
            助手自定义聊天背景（产品要求）：不裁剪，按窗口长宽缩放；无则跟随全局壁纸。

            ⚠️ **不能用 `backgroundAttachment: 'fixed'`**（报"被对话列表
            遮盖一部分"）：`fixed` 让背景相对**视口**定位，于是这张图是从整个窗口的左上角
            开始铺的 —— 对话栏里能看到的只是它右边那一块，左边半张被助手栏 / 对话列表盖住。
            去掉之后背景相对**这个元素自身**（也就是对话栏）铺满，整张图完整落在这里。
            默认的 `scroll` 对滚动容器正好是"背景钉在元素上、内容在上面滚"，正是想要的。
          */}
          <div
            ref={scrollRef}
            onScroll={onScroll}
            className="h-full overflow-y-auto"
            style={
              activeAssistant?.chat_background
                ? {
                    backgroundImage: `url("${activeAssistant.chat_background}")`,
                    backgroundSize: '100% 100%',
                  }
                : undefined
            }
          >
            {messages.length === 0 ? (
              // 层级与条件都不动：仍然**只在这条对话没有任何消息时**出现，
              // 只是把中央的图标换成这个搭子自己的头像
              <WelcomePanel assistant={activeAssistant} />
            ) : (
              <div className="mx-auto flex w-full flex-col gap-5 px-4 py-5">
                {hiddenCount > 0 ? (
                  <div className="flex justify-center">
                    <button
                      type="button"
                      onClick={loadEarlier}
                      className="rounded-[8px] border border-line bg-canvas px-3 py-1.5 text-[12px] text-ink-soft hover:border-brand/40 hover:text-ink"
                    >
                      载入更早的 {Math.min(VISIBLE_STEP, hiddenCount)} 条
                      <span className="ml-1 text-ink-faint">（还有 {hiddenCount} 条未显示）</span>
                    </button>
                  </div>
                ) : null}

                {visibleMessages.map((message) => (
                  <MessageItem key={message.id} message={message} />
                ))}

                {/* 「继续」：回答没跑完时，用**大白话**说清"它停下来了"，并给一个按钮。
                    "为什么停、最后在做什么"来自后端的 summary —— 界面不自己拼，
                    免得同一件事出现两种说法（见 core 的 routes/runs.py）。
                    只在一个可续跑的现场存在时出现，点一下就把话说出去。 */}
                {resumable && !streaming ? (
                  <div className="rounded-[10px] border border-warning/30 bg-warning-soft px-3.5 py-3">
                    <div className="flex items-start gap-2.5">
                      <AlertTriangle size={15} className="mt-0.5 shrink-0 text-warning" />
                      <div className="min-w-0 flex-1">
                        <div className="text-[13px] font-medium text-ink">
                          要我接着往下做吗？
                        </div>
                        <p className="mt-1 text-[12px] leading-relaxed text-ink-soft">
                          {resumable.summary}
                        </p>
                        <div className="mt-2.5 flex items-center gap-2">
                          <Button size="sm" variant="primary" onClick={() => void resume()}>
                            继续
                          </Button>
                          <Button
                            size="sm"
                            variant="secondary"
                            onClick={() => void dismissResumable()}
                          >
                            不用了
                          </Button>
                        </div>
                      </div>
                    </div>
                  </div>
                ) : null}
              </div>
            )}
          </div>

          {showJump ? (
            <button
              type="button"
              onClick={jumpToBottom}
              className={clsx(
                'no-drag absolute bottom-4 left-1/2 flex -translate-x-1/2 items-center gap-1.5 rounded-full',
                'border border-line bg-canvas px-3 py-1 text-[12px] text-ink-soft shadow-[0_4px_12px_rgba(0,0,0,0.10)] hover:text-ink',
              )}
            >
              <ChevronDown size={13} />
              回到最新
            </button>
          ) : null}
        </div>

        {/*
          任务执行计划条：夹在**对话栏与输入栏之间**（产品要求）。
          传整个 `messages` 而不是 `visibleMessages` —— 计划可能是好几屏之前的
          那条消息带来的（"先看阶段划分，再分头执行"），而被折叠掉的历史里
          正好可能有它；漏掉的话用户会觉得"计划条时有时无"。
        */}
        <PlanBar messages={messages} />

        {/*
          「搭子正在操作你的电脑」提示条 + 急停：与计划条同区域（对话栏与
          输入栏之间）。只有真有 `computer_*` 技能在跑时才渲染 —— 平时不占位。
        */}
        <ComputerUseBar messages={messages} />

        <Composer />

        {/* 「我的资料」弹窗：点消息里自己的头像或昵称打开（见 MessageItem）。
            挂在这里而不是每个气泡里 —— 气泡是列表项，每个都挂一份弹窗既浪费
            又会同时弹出好几个。 */}
        <UserProfileDialog
          open={profileDialogOpen}
          onClose={() => useUserProfileDialogStore.getState().hide()}
        />
      </div>

      {/*
        ---- ③ 链路与产物列 ----

        与左侧的搭子栏 / 对话列表栏**同一种结构**：`flex` 行里的一个独立卡片
        （自己的圆角、描边、`bg-panel`，见 DetailDrawer 的根元素）。

        ⚠️ 与语音设置**互斥**：语音设置是"替换整块对话框"的全屏浮层，而这里是
        新开一列 —— 两个同时开会把界面切成谁也不认识的形状。而且"看任务过程"
        与"改语音配置"本来也不会同时要。
      */}
      {showDrawer ? <DetailDrawer streaming={streaming} /> : null}
    </div>
  )
}
