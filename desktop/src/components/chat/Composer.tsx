import { useEffect, useMemo, useState } from 'react'
import clsx from 'clsx'
import { Activity, PictureInPicture2 } from 'lucide-react'

import { ComposerShell } from '@/components/chat/ComposerShell'
import { ConfirmModeButton } from '@/components/chat/ConfirmModeButton'
import { ContextUsagePill } from '@/components/chat/ContextUsagePill'
import { ModelSelector } from '@/components/chat/ModelSelector'
import { ReasoningEffortButton } from '@/components/chat/ReasoningEffortButton'
import {
  SLASH_COMMANDS,
  matchCommands,
  type PaletteItem,
} from '@/components/chat/SlashCommandPanel'
import { useAssistantStore } from '@/stores/assistantStore'
import { useAppStore } from '@/stores/appStore'
import { useChatStore } from '@/stores/chatStore'
import { useNotificationStore } from '@/stores/notificationStore'

/**
 * 单聊输入区。
 *
 * ⚠️ 真正的输入体验在 `ComposerShell` 里（多行、附件、语音、命令面板），
 * 这里只负责把**单聊特有的东西**接上去：
 *
 * - 草稿与附件来自 `chatStore`（发给哪个会话它自己知道）；
 * - 斜杠命令的全套语义：`/new` `/compact` `/clear` `/stop` `/model` `/help`；
 * - 控件行上的思考强度、上下文用量、权限模式。
 *
 * 群聊用同一个壳接它自己的状态 —— 于是"输入栏的操作体验"只有一份实现。
 */
export function Composer() {
  const draft = useChatStore((state) => state.draft)
  const setDraft = useChatStore((state) => state.setDraft)
  const send = useChatStore((state) => state.send)
  const stop = useChatStore((state) => state.stop)
  const streaming = useChatStore((state) => state.streaming)
  const addFiles = useChatStore((state) => state.addFiles)
  const attachments = useChatStore((state) => state.attachments)
  const removeAttachment = useChatStore((state) => state.removeAttachment)
  const startNewSession = useChatStore((state) => state.startNewSession)
  const clearHistory = useChatStore((state) => state.clearHistory)
  const setModelId = useChatStore((state) => state.setModelId)
  const models = useAppStore((state) => state.models)
  const effectiveDefaultModelId = useAppStore((state) => state.modelDefaults.effectiveDefault)
  const sessionModelId = useChatStore((state) => state.modelId)

  // ---- 输入栏下方那一行（产品要求把顶栏那三样搬下来）----
  //
  // 搬过来的理由不只是"挪个位置"：顶栏在**独立窗口**里会空出一整行（那个窗口不
  // 显示"独立窗口对话"按钮），而输入栏下方这一行本来就离手最近。
  const drawerOpen = useChatStore((state) => state.drawerOpen)
  const setDrawerOpen = useChatStore((state) => state.setDrawerOpen)
  // 这里曾有 `trace` / `artifactCount`，用于"没内容就把入口按钮置灰"。
  // 那个置灰规则按产品要求去掉了（见按钮处的说明），变量随之删除。
  const activeSessionId = useChatStore((state) => state.activeSessionId)
  const activeAssistant = useAssistantStore((state) =>
    state.assistants.find((item) => item.id === state.activeId),
  )
  // 独立窗口里这两个入口都没有意义（它自己就是那个窗口），判断与顶栏时代一致
  const isChatWindow = window.agentBridge?.getWindowArgs?.()?.mode === 'chat'
  // 输入框 placeholder 用**当前搭子的称呼**（产品要求：不再是通用的 Soulmate）。
  // 昵称优先、没有昵称就用它的本名。
  const assistantLabel =
    useAssistantStore((state) => {
      const current = state.assistants.find((item) => item.id === state.activeId)
      return current ? current.nickname || current.name : ''
    }) || '助手'

  // ---- 斜杠命令面板 -------------------------------------------------- //
  //
  // 面板有两种"下一步"形态（切模型、确认清空），所以除了开关还需要一个模式，
  // 否则用户选了 /model 之后面板会立刻因为输入框被清空而消失。
  const [paletteOpen, setPaletteOpen] = useState(false)
  const [paletteMode, setPaletteMode] = useState<'command' | 'model' | 'clear'>('command')

  // 命令名后面的那段（到第一个空格为止），用于过滤
  const paletteQuery =
    paletteOpen && paletteMode === 'command' && draft.startsWith('/')
      ? draft.slice(1).split(/\s+/)[0]
      : ''

  const paletteItems = useMemo<PaletteItem[]>(() => {
    if (!paletteOpen) return []
    if (paletteMode === 'model') {
      return models
        .filter((model) => model.enabled)
        .map((model) => ({ key: model.id, title: model.display_name, detail: model.provider }))
    }
    if (paletteMode === 'clear') {
      return [
        {
          key: 'confirm',
          title: '确认清空',
          detail: '删除本对话的全部消息',
          tone: 'danger' as const,
        },
        { key: 'cancel', title: '取消', detail: '什么都不做' },
      ]
    }
    return matchCommands(paletteQuery).map((command) => ({
      key: command.name,
      title: `/${command.name}`,
      detail: command.hint ? `${command.label} · ${command.hint}` : command.label,
    }))
  }, [paletteOpen, paletteMode, paletteQuery, models])

  const closePalette = () => {
    setPaletteOpen(false)
    setPaletteMode('command')
  }

  useEffect(() => {
    // 只在**命令模式**下跟着输入内容开关。切到模型/确认列表之后输入框已经清空，
    // 若还跟着它判断，面板会在用户刚选完 /model 的瞬间自己关掉。
    if (paletteMode !== 'command') return
    const shouldOpen = draft.startsWith('/') && !streaming
    if (shouldOpen && !paletteOpen) {
      setPaletteOpen(true)
    } else if (!shouldOpen && paletteOpen) {
      setPaletteOpen(false)
    }
  }, [draft, streaming, paletteOpen, paletteMode])

  const runPaletteItem = (item: PaletteItem) => {
    if (paletteMode === 'clear') {
      if (item.key === 'confirm') {
        setDraft('')
        void clearHistory()
      }
      closePalette()
      return
    }

    if (paletteMode === 'model') {
      setModelId(item.key)
      setDraft('')
      closePalette()
      return
    }

    const name = item.key
    setDraft('')
    if (name === 'new') {
      closePalette()
      startNewSession()
      return
    }
    if (name === 'stop') {
      closePalette()
      void stop()
      return
    }
    // 清空是不可逆的，所以不直接执行 —— 让面板换成一次确认
    if (name === 'clear') {
      setPaletteMode('clear')
      return
    }
    if (name === 'model') {
      setPaletteMode('model')
      return
    }
    if (name === 'help') {
      closePalette()
      useNotificationStore.getState().push({
        level: 'info',
        title: '可用的快捷命令',
        message: SLASH_COMMANDS.map((command) => `/${command.name} — ${command.label}`).join(
          '\n',
        ),
        autoDismissMs: 0,
      })
      return
    }
    if (name === 'compact') {
      closePalette()
      const sessionId = useChatStore.getState().activeSessionId
      const api = useAppStore.getState().api
      if (!sessionId || !api) {
        useNotificationStore.getState().push({
          level: 'warning',
          title: '无法压缩',
          message: '当前没有进行中的对话，先发一条消息再压缩。',
        })
        return
      }
      void api
        .compressSession(sessionId)
        .then((result) => {
          useNotificationStore.getState().push({
            level: result.compressed ? 'success' : 'info',
            title: result.compressed ? '上下文已压缩' : '无需压缩',
            message: result.message,
          })
          // 压缩会改变会话的摘要状态，刷新上下文用量显示
          useAppStore.getState().reloadHealth?.()
        })
        .catch((error: unknown) => {
          useNotificationStore.getState().push({
            level: 'error',
            title: '压缩失败',
            message: error instanceof Error ? error.message : String(error),
          })
        })
      return
    }
    closePalette()
  }

  // 「附件里有图片、但当前模型不收图」必须当场说清 —— 图片走的是另一条通道，
  // 模型不支持图片输入时它只会作为文件路径发过去，用户却以为"图已经给它看过了"。
  const activeModel = useMemo(() => {
    const id = sessionModelId ?? effectiveDefaultModelId
    if (!id) return null
    return models.find((item) => item.id === id) ?? null
  }, [sessionModelId, effectiveDefaultModelId, models])

  const imageHint =
    activeModel && !activeModel.supports_vision && attachments.some((item) => item.kind === 'image')
      ? `当前模型「${activeModel.display_name}」不接收图片：图片会作为附件（文件路径）发过去，模型看不到画面。要真正把图片发给模型，请到「模型服务商」里选一个支持图片的模型，并勾上「支持图片输入」。`
      : undefined

  return (
    <ComposerShell
      value={draft}
      onChange={setDraft}
      onSubmit={() => void send()}
      busy={streaming}
      onStop={() => void stop()}
      placeholder={`给 ${assistantLabel} 发消息，Enter 发送，Shift + Enter 换行；输入 / 查看快捷命令`}
      attachments={attachments}
      onFiles={(files) => void addFiles(files)}
      onRemoveAttachment={removeAttachment}
      hint={imageHint}
      footerLeft={
        isChatWindow ? null : (
          <button
            type="button"
            onClick={() => {
              if (!activeAssistant?.id) return
              // 带上当前会话 id：独立窗口开的就是**正在看的这一段**，
              // 而不是"这个搭子最近的一条"
              window.agentBridge?.openChatWindow(activeAssistant.id, activeSessionId ?? '')
            }}
            disabled={!activeAssistant}
            className="flex items-center gap-1 rounded-[6px] px-1.5 py-0.5 hover:bg-hover hover:text-ink disabled:opacity-40"
          >
            <PictureInPicture2 size={13} />
            打开独立窗口
          </button>
        )
      }
      footerCenter={<ModelSelector />}
      footerRight={
        <button
          type="button"
          onClick={() => setDrawerOpen(!drawerOpen)}
          /*
            ⚠️ **不再置灰**（报"按钮无法点击"）。

            原先的条件是 `!isChatWindow && !trace && artifactCount === 0`：
            主窗口在当前会话没有 trace、也没有产物时就禁用。问题在于
            **每个窗口各有一份独立的 store**（Electron 的 BrowserWindow 是独立
            渲染进程），所以"在独立窗口里跑出来的链路"主窗口**根本看不到** ——
            用户在主窗口看到的永远是空 trace + 空产物，按钮就一直点不动。

            而且"禁用"本身就是个坏设计：用户想点开看看的**恰恰是没内容那一次**
            （"它到底调了什么？"）。没内容时打开抽屉显示空态，比一个点不动的
            按钮诚实得多。
          */
          /* ⚠️ 展开时高亮（产品要求）：它是个开关，而原样式两种状态
             长得一样 —— 用户看不出抽屉是否开着，也找不到"再点一下就关"的线索。
             用 `brand-soft` 而不是实心主色：它只是状态指示，不是页面上的主动作。 */
          aria-pressed={drawerOpen}
          className={clsx(
            'flex items-center gap-1 rounded-[6px] px-1.5 py-0.5 transition-colors disabled:opacity-40',
            drawerOpen
              ? 'bg-brand-soft font-medium text-brand hover:bg-brand/15'
              : 'hover:bg-hover hover:text-ink',
          )}
        >
          打开链路与产物
          <Activity size={13} />
        </button>
      }
      paletteOpen={paletteOpen}
      paletteItems={paletteItems}
      paletteEmptyText={paletteMode === 'model' ? '没有启用的模型' : '没有匹配的命令'}
      onPaletteSelect={runPaletteItem}
      onNewSession={startNewSession}
      toolbarLeft={
        <>
          <span className="mx-0.5 h-4 w-px shrink-0 bg-line" aria-hidden />
          <ReasoningEffortButton />
          <ContextUsagePill />
          <ConfirmModeButton />
        </>
      }
    />
  )
}
