import { useEffect, useRef } from 'react'

import { AddSkillDialog, openAddSkill } from '@/components/AddSkillDialog'
import { AuroraBackground } from '@/components/AuroraBackground'
import { ClosePrompt } from '@/components/ClosePrompt'
import { openFeedback } from '@/components/FeedbackDialog'
import { AssistantRail } from '@/components/chat/AssistantRail'
import { AvatarPreview } from '@/components/chat/AvatarPreview'
import { ConfirmDialog } from '@/components/chat/ConfirmDialog'
import { ChatView } from '@/components/chat/ChatView'
import { IconRail } from '@/components/IconRail'
import { SessionList } from '@/components/SessionList'
import { AppearanceSettings } from '@/components/settings/AppearanceSettings'
import { AuditSettings } from '@/components/settings/AuditSettings'
import { CalendarSettings } from '@/components/settings/CalendarSettings'
import { McpSettings } from '@/components/settings/McpSettings'
import { ModelSettings } from '@/components/settings/ModelSettings'
import { PreferenceSettings } from '@/components/settings/PreferenceSettings'
import { SkillSettings } from '@/components/settings/SkillSettings'
import { UsageSettings } from '@/components/settings/UsageSettings'
import { WorkspaceSettings } from '@/components/settings/WorkspaceSettings'
import { AboutPage } from '@/components/pages/AboutPage'
import { BenefitsPage } from '@/components/pages/BenefitsPage'
import { TasksPage } from '@/components/pages/TasksPage'
import { GroupChatPage } from '@/components/pages/GroupChatPage'
import { BootScreen } from '@/components/BootScreen'
import { OfflineDialog } from '@/components/OfflineDialog'
import { Onboarding } from '@/components/Onboarding'
import { InteractionDialog } from '@/components/chat/InteractionDialog'
import { TitleBar } from '@/components/TitleBar'
import { Toaster } from '@/components/Toaster'
import { usePanScroll } from '@/lib/usePanScroll'
import { useAppStore } from '@/stores/appStore'
import { useAssistantStore } from '@/stores/assistantStore'
import { useAccountStore } from '@/stores/accountStore'
import { useChatStore } from '@/stores/chatStore'
import { useNotificationStore } from '@/stores/notificationStore'
import { closeAllTransientDialogs, useTransientDialogsStore } from '@/stores/transientDialogs'
import { useVoiceCommand } from '@/stores/voiceCommandStore'
import { useVoiceSessionStore } from '@/stores/voiceSessionStore'

export default function App() {
  const bootstrap = useAppStore((state) => state.bootstrap)
  const bootstrapping = useAppStore((state) => state.bootstrapping)
  const bootstrapError = useAppStore((state) => state.bootstrapError)
  const view = useAppStore((state) => state.view)
  const onboardingActive = useAppStore((state) => state.onboardingActive)

  // 独立对话窗口（产品要求）：mode='chat' 时只渲染 TitleBar + ChatView，
  // 不渲染导航栏 / 助手栏 / 会话栏，绑定到指定的那个搭子。
  const windowArgs = window.agentBridge?.getWindowArgs?.()
  const isChatWindow = windowArgs?.mode === 'chat'
  // 群聊独立窗口：两种形态共用这一个窗口类型 —— 只读观察窗（AI 后台讨论时自动弹）
  // 与可操作窗口（用户手动打开）。区别只在 readonly 参数上（见 GroupChatPage）。
  const isGroupWindow = windowArgs?.mode === 'group'
  // 引导的唯一判据就是 `onboardingActive`：它在 `appStore.handshake` 里
  // 按**三项实时状态**算出来（语音装了 / 长期记忆装了 / 有可用服务商 ——
  // 见 `needsOnboarding`）。启动时 models 与本地模型状态还没拉回来，
  // 走上面的 BootScreen 早退，所以不会闪引导。
  //
  // ⚠️ **不要在这里另算一套**（把这里收敛成一个开关了）：
  // 曾经这里写的是 `onboardingActive && !onboardingDismissed`、判据在 store 里各算一份，
  // 结果"装了模型还被拦一次""保存服务商后向导自己消失"这类毛病反复出现 ——
  // 判据只能有一处（`needsOnboarding`），要不要显示只有 `onboardingActive` 说了算。
  const onboarding = onboardingActive

  const loadSessions = useChatStore((state) => state.loadSessions)
  const startNewSession = useChatStore((state) => state.startNewSession)
  const loadAssistants = useAssistantStore((state) => state.load)
  const startEventStream = useNotificationStore((state) => state.startEventStream)
  const stopEventStream = useNotificationStore((state) => state.stopEventStream)
  const setView = useAppStore((state) => state.setView)

  // 「按住拖动平移」——原先只有设置页有（长在 SettingsView 自己的容器上）。
  // 它的八个分栏提成顶级页之后，这层外壳跟着提到这里统一包一层，
  // 于是所有"浏览型"页面行为一致（见 lib/usePanScroll）。
  const panRef = usePanScroll()

  /**
   * 语音导航（「很多设置存在，但无法真的通过语音操作应用」）。
   *
   * 命令表里 `nav.*` 原本**只有声明、没有实现** —— 面板里能配词、说出口却
   * 没有任何反应。这里把它们接到 `setView`，与手点左侧导航栏走同一条路。
   *
   * ⚠️ 只在**主界面**提供：独立对话 / 群聊窗口与首启引导页都没有导航栏，
   * 在那里说「打开设置」没有可切的地方。按 `useVoiceCommand` 的约定传 `null`
   * （= "这一刻不提供"，命令表里也不会出现），而不是传一个点了没反应的假处理器。
   */
  const canNavigate =
    !isChatWindow && !isGroupWindow && !onboarding && !bootstrapping && !bootstrapError
  // 当前有几个"可以被语音关掉"的弹窗（见 stores/transientDialogs.ts）。
  // 「关闭弹窗」那条命令靠它决定自己要不要出现在命令表里。
  const transientOpenCount = useTransientDialogsStore((state) => state.openCount)
  useVoiceCommand('nav.chat', canNavigate ? () => setView('chat') : null)
  useVoiceCommand('nav.groups', canNavigate ? () => setView('groups') : null)
  useVoiceCommand('nav.tasks', canNavigate ? () => setView('tasks') : null)
  useVoiceCommand('nav.appearance', canNavigate ? () => setView('appearance') : null)
  useVoiceCommand('nav.benefits', canNavigate ? () => setView('benefits') : null)
  useVoiceCommand('nav.about', canNavigate ? () => setView('about') : null)
  /*
    ⚠️ 「打开设置」这条命令 **删掉了**（连同设置页本身）：`'settings'`
    这个 view 已经不存在。取而代之的是原设置页里那八栏各自的入口 —— 用户现在在左栏
    直接看得到它们，语音也就该能直接说。id 与 `ViewKey` 一一对应。
  */
  useVoiceCommand('nav.models', canNavigate ? () => setView('models') : null)
  useVoiceCommand('nav.skills', canNavigate ? () => setView('skills') : null)
  useVoiceCommand('nav.mcp', canNavigate ? () => setView('mcp') : null)
  useVoiceCommand('nav.workspace', canNavigate ? () => setView('workspace') : null)
  useVoiceCommand('nav.usage', canNavigate ? () => setView('usage') : null)
  useVoiceCommand('nav.calendar', canNavigate ? () => setView('calendar') : null)
  useVoiceCommand('nav.audit', canNavigate ? () => setView('audit') : null)
  useVoiceCommand('nav.preference', canNavigate ? () => setView('preference') : null)
  // ⚠️ 反馈是**弹窗**，不是页面：`ViewKey` 里根本没有 'feedback'，照抄上面几行
  // 把 'feedback' 传给 setView 会切到一片空白（而且还编译得过，所以这里刻意
  // 留一句说明）。它导出的是 openFeedback()，和左侧导航栏底部那个入口同一个函数。
  useVoiceCommand('action.feedback', canNavigate ? () => openFeedback() : null)
  // 「添加技能」：弹层挂在应用顶层，所以在**任何页面**都唤得起。
  // ⚠️ 它同样不走 setView —— 它是弹窗，不是页面（技能页那个页面只是它的一个入口）。
  useVoiceCommand('action.addSkill', canNavigate ? () => openAddSkill() : null)
  /*
    「关闭弹窗」：只关**主动登记过**的浮层（反馈、添加技能这类）。搭子发起的权限
    确认框与任务计划卡片**没有登记**，所以这句命令永远碰不到它们 —— 那是在问
    "允不允许执行"，要驳回请用命令表里那条精确得多的「拒绝执行」
    （见 stores/transientDialogs.ts 顶部）。

    ⚠️ 没有弹窗可关时传 `null`（这条命令干脆不出现）：让它一直挂在那儿、说了却
    毫无反应，用户只会得出"这功能是坏的"。
  */
  useVoiceCommand(
    'action.closeDialog',
    // 包一层：`closeAllTransientDialogs` 返回"关掉了几个"，而命令处理器的签名是
    // void —— 直接传过去会被 tsc 挡下（number 不是 void | Promise<void>）。
    canNavigate && transientOpenCount > 0 ? () => void closeAllTransientDialogs() : null,
  )

  useEffect(() => {
    void bootstrap()
  }, [bootstrap])

  // 账号引擎在主进程里**静默**跑，渲染层只订阅快照。这里不依赖核心是否就绪：
  // 账号流程与智能体核心彼此独立，核心还在启动时账号可能已经注册完了。
  const bootAccount = useAccountStore((state) => state.boot)
  useEffect(() => bootAccount(), [bootAccount])

  // 把**当前线路**同步给智能体核心。
  //
  // 为什么要同步：核心不知道客户端算出来的线路（那是主进程按系统语言 + 探测
  // 定下来的），但"官网搭子库地址"与"兑换码接口域名"**都跟着线路走**
  // （见 core 的 `config/lines.py`）。放这一个 effect 里、而不是散在各处：
  // 启动时账号引擎给出的结论、以及用户在权益页手动切线路，都只会让快照里的
  // `preferred` 变化一次，这里自然就推一次；核心重启后会换成新的 api 实例，
  // 依赖变化同样会重推（新核心的线路状态是默认值，必须重新告诉它）。
  const activeLine = useAccountStore((state) => state.snapshot?.line?.preferred)
  const coreApi = useAppStore((state) => state.api)
  useEffect(() => {
    if (!coreApi || !activeLine) return
    void coreApi.setLine(activeLine).catch(() => {
      // 同步失败不打扰用户：核心会退回默认线路（大陆），功能照常可用，
      // 只是官网搭子库/兑换码可能不是最快的那条线
    })
  }, [coreApi, activeLine])

  useEffect(() => {
    if (bootstrapping || bootstrapError) return
    void loadSessions()
    // 助手必须在会话之前就位：selectSession 会用会话记录的 assistant_id 回填当前助手
    void loadAssistants()
    // 提醒等主动推送依赖这条长连接；断线由 store 内部自动重连
    startEventStream()
    return () => stopEventStream()
  }, [
    bootstrapping,
    bootstrapError,
    loadSessions,
    loadAssistants,
    startEventStream,
    stopEventStream,
  ])

  // 语音：按设置决定启动后要不要开麦克风（产品要求）。
  //
  // ⚠️ 必须等 `settings` 到位再调 —— 启动状态就存在设置里（`voice.startup_mode`）。
  // 只跑**一次**（`voiceBooted` 闸）：这是"启动时"的行为，之后开关由用户说了算；
  // 少了这道闸，设置被重新加载时会顺手又开一次/关一次麦克风。
  //
  // ⚠️ **常驻麦克风只由主窗口开**（第 103 批）。
  // 「应用级唯一」这条约束只在**一个渲染进程内**成立（`voiceSessionStore` 的句柄是
  // 模块级变量），而每个窗口都是独立渲染进程 —— 主窗口 + 每个独立对话窗 + 每个群聊窗
  // 都在这里各自 `bootstrap()`。那恰好是 `voiceSessionStore` 文件头警告过的场景：
  // "同时开两条流会抢设备，Windows 上第二条常拿到静音，而且**不报错**"；
  // 更糟的情况是直接报「无法打开麦克风」（设备被独占）。
  //
  // ⚠️ 独立窗口**不**降级成"开自己的麦"：那就回到互相抢设备了。窗口内的语音设置
  // 入口也不显示（见 `ComposerShell` 里的同名判断）—— 一个点了不会有人听的按钮，
  // 比不显示更糟。这与"语音是跨会话的能力、要一次开关就全关"的既有口径一致。
  const settingsReady = useAppStore((state) => state.settings !== null)
  const voiceBooted = useRef(false)
  // `mode` 取不到（preload 未注入 / 浏览器里跑）时按**主窗口**处理：宁可主窗口多开一次，
  // 也不要让正常启动的语音整个不工作。
  const isMainWindow = windowArgs?.mode !== 'chat' && windowArgs?.mode !== 'group'
  useEffect(() => {
    if (!settingsReady || voiceBooted.current) return
    voiceBooted.current = true
    if (!isMainWindow) return
    useVoiceSessionStore.getState().bootstrap()
  }, [settingsReady, isMainWindow])

  // 全局快捷键
  useEffect(() => {
    const handler = (event: KeyboardEvent) => {
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'n') {
        event.preventDefault()
        startNewSession()
      }
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [startNewSession])

  // 独立窗口：固定到指定搭子；**带 sessionId 时直接打开那条会话**（产品要求）。
  //
  // 之前这里只能"取这个搭子最近一条会话"，于是从某段对话里点「独立窗口对话」
  // 得到的是**另一个新对话**，用户在看的这段并没有被拎过去。没有 sessionId 时
  // 仍保留旧兜底（最近一条 / 空态，发消息时后端才建会话）。
  useEffect(() => {
    if (!isChatWindow || bootstrapping || bootstrapError) return
    const assistantId = windowArgs?.assistantId
    if (!assistantId) return
    useAssistantStore.getState().setActive(assistantId)
    const sessionId = windowArgs?.sessionId
    const active = useChatStore.getState().activeSessionId
    if (sessionId) {
      if (active !== sessionId) void useChatStore.getState().selectSession(sessionId)
      return
    }
    const sessions = useChatStore.getState().sessions
    const recent = sessions.find((item) => item.assistant_id === assistantId)
    if (recent && active !== recent.id) {
      void useChatStore.getState().selectSession(recent.id)
    }
  }, [
    isChatWindow,
    bootstrapping,
    bootstrapError,
    windowArgs?.assistantId,
    windowArgs?.sessionId,
  ])

  // ClosePrompt 在**每个分支**里都要挂上：用户可能在启动中、引导页或主界面
  // 任何一刻点 ×。漏掉任何一个分支，主进程等不到回应就会退回系统原生弹窗 ——
  // 那正是实测反馈"风格不符"的那个东西。
  if (bootstrapping || bootstrapError) {
    return (
      <div className="flex h-full flex-col">
        <AuroraBackground />
        {/* 还没进应用 → 标题栏固定产品标识（产品要求，见 TitleBar 的 brandOnly） */}
        <TitleBar brandOnly />
        <BootScreen />
        <ClosePrompt />
      </div>
    )
  }

  // 独立对话窗口：只放 TitleBar + 对话区（用户确认 #14），不显示引导/导航/助手栏/会话栏
  if (isChatWindow) {
    return (
      <div className="flex h-full flex-col overflow-hidden">
        <AuroraBackground />
        <TitleBar />
        {/*
          ⚠️ `flex` 是必需的，别删。少了它这层就是**块级容器**，`flex-1` 对高度
          完全不起作用 → `ChatView` 根上的 `flex-1` 跟着失效 → 对话卡片塌缩成
          "内容有多高就多高"。

          有消息时内容本身够高，看着正常；而**从"新对话"直接开独立窗口**时里面
          是空态（内容很矮），于是输入栏就浮在窗口中间 —— 实测反馈就是这个。
          群聊那个分支早就写对了（见下面 `flex min-h-0 flex-1 flex-col`）。
        */}
        <div className="flex min-h-0 flex-1 flex-col">
          <ChatView />
        </div>
        <ConfirmDialog />
        {/* 技能要问用户时的弹窗（选择 / 敏感输入）。与 ConfirmDialog 一样
            挂在**每个分支**里 —— 少一处，那个分支下技能就永远问不出来。 */}
        <InteractionDialog />
        <ClosePrompt />
        <AvatarPreview />
        <Toaster />
      </div>
    )
  }

  // 群聊独立窗口：只放 TitleBar + 群聊区（与单聊独立窗口同一个做法，
  // 不带导航栏 / 助手栏 / 会话栏）
  if (isGroupWindow) {
    return (
      <div className="flex h-full flex-col overflow-hidden">
        <AuroraBackground />
        <TitleBar />
        {/* ⚠️ 这一层必须是 flex **列**容器：GroupChatPage 根节点靠 `flex-1` 撑高度，
            而它在普通块级父节点里根本没有高度约束 —— 后果是内部的
            `overflow-y-auto` 拿不到可滚高度，**鼠标滚轮在观察窗里完全推不动**
            （群聊页里它是嵌在有约束的布局里的，所以那边正常）。 */}
        <div className="flex min-h-0 flex-1 flex-col">
          <GroupChatPage
            groupId={windowArgs?.groupId ?? ''}
            readonly={windowArgs?.readonly === true}
            // 空串 = 该窗口没指定对话，进去后落到"最近有动静"的那条
            threadId={windowArgs?.threadId ?? ''}
          />
        </div>
        <ConfirmDialog />
        <InteractionDialog />
        <ClosePrompt />
        <AvatarPreview />
        <Toaster />
      </div>
    )
  }

  // 首启动引导：没有可用模型时挡在前面，避免用户带着"发消息没反应"的困惑去摸索设置
  if (onboarding) {
    return (
      <div className="flex h-full flex-col overflow-hidden">
        <AuroraBackground />
        {/* 引导页还**没进应用** → 标题栏固定产品标识；进了主界面才跟随当前搭子*/}
        <TitleBar brandOnly />
        <div className="min-h-0 flex-1">
          <Onboarding />
        </div>
        <OfflineDialog />
        <ClosePrompt />
        <Toaster />
      </div>
    )
  }

  /**
   * 「浏览型」页面的内容：外观 + 原先设置页里的八栏（把它们提成
   * 左栏的顶级入口，设置页本身取消）。
   *
   * 放成一张表而不是在渲染链里抄九遍：它们**共用同一层外壳**（圆角卡片 + 内边距
   * + 拖动平移），壳在下面统一渲染一次就够。
   */
  const panelContent =
    view === 'appearance' ? (
      <AppearanceSettings />
    ) : view === 'models' ? (
      <ModelSettings />
    ) : view === 'skills' ? (
      <SkillSettings />
    ) : view === 'mcp' ? (
      <McpSettings />
    ) : view === 'workspace' ? (
      <WorkspaceSettings />
    ) : view === 'usage' ? (
      <UsageSettings />
    ) : view === 'calendar' ? (
      <CalendarSettings />
    ) : view === 'audit' ? (
      <AuditSettings />
    ) : view === 'preference' ? (
      <PreferenceSettings />
    ) : null

  return (
    <div className="flex h-full flex-col overflow-hidden">
      {/* 极光在最底层：fixed + z-index:0，画在非定位元素之上、定位卡片之下 */}
      <AuroraBackground />
      <TitleBar />
      <div className="flex min-h-0 flex-1">
        <IconRail />
        {view === 'chat' ? (
          // 每一栏都是**独立的圆角容器**，彼此留出间距（壁纸/极光从缝里透出来）。
          // 单独包一层而不是直接改上面的容器：IconRail 是导航条，它要贴边、
          // 不参与这套卡片布局。
          <div className="flex min-h-0 min-w-0 flex-1 gap-[3px] pb-[3px] pr-[3px]">
            {/* 从左到右：助手栏 → 该助手的对话 → 对话区 */}
            <AssistantRail />
            <SessionList />
            <ChatView />
          </div>
        ) : view === 'groups' ? (
          <div className="flex min-h-0 min-w-0 flex-1 gap-[3px] pb-[3px] pr-[3px]">
            <GroupChatPage />
          </div>
        ) : view === 'tasks' ? (
          <div className="flex min-h-0 min-w-0 flex-1 gap-[3px] pb-[3px] pr-[3px]">
            <TasksPage />
          </div>
        ) : view === 'benefits' ? (
          <div className="flex min-h-0 min-w-0 flex-1 gap-[3px] pb-[3px] pr-[3px]">
            <BenefitsPage />
          </div>
        ) : view === 'about' ? (
          <div className="flex min-h-0 min-w-0 flex-1 gap-[3px] pb-[3px] pr-[3px]">
            <AboutPage />
          </div>
        ) : panelContent ? (
          // 「浏览型」页面**共用一层外壳**：四周留缝（否则里面的侧栏卡片会贴着窗口边）
          // + 圆角卡片 + 可按住的拖动平移（`panRef`）。
          // 原先这层壳长在 `SettingsView` 里；那八个分栏提成顶级页之后搬到这里统一包，
          // 于是九个页面（外观 + 原设置八栏）的外壳**只有一份实现**，不会各写各的。
          <div className="flex min-h-0 min-w-0 flex-1 gap-[3px] pb-[3px] pr-[3px]">
            <div
              ref={panRef}
              className="min-w-0 flex-1 overflow-auto rounded-[12px] border border-line bg-panel px-10 py-5"
            >
              {panelContent}
            </div>
          </div>
        ) : (
          /*
            兜底：`view` 是闭合联合类型，上面已经覆盖了全部取值，正常走不到这里。
            真到了这里说明有人加了新 view 却忘了加分支 —— 那就落回**对话页**
            （用户最熟悉的一屏），而不是渲染一片空白让人以为应用坏了。
            左侧的「设置」按钮已于 连同设置页一起取消，所以这里不再是
            `SettingsView` 兜底。
          */
          <div className="flex min-h-0 min-w-0 flex-1 gap-[3px] pb-[3px] pr-[3px]">
            <AssistantRail />
            <SessionList />
            <ChatView />
          </div>
        )}
      </div>
      <ConfirmDialog />
      <InteractionDialog />
      <OfflineDialog />
      <ClosePrompt />
      {/* 头像大图：挂在最外层一次，所有位置的 `<AssistantAvatar>` 点开都弹它 */}
      <AvatarPreview />
      {/*
        「添加技能」弹窗：挂在最外层一次——
        这样**任何页面**都能用语音或按钮唤起它，不必先切到技能页。
      */}
      <AddSkillDialog />
      <Toaster />
    </div>
  )
}
