import clsx from 'clsx'
import {
  MessageSquarePlus,
  MoreHorizontal,
  PanelLeftClose,
  PanelRightClose,
  Pencil,
  PictureInPicture2,
  Search,
  Trash2,
  Eraser,
  AlertTriangle,
} from 'lucide-react'
import { useEffect, useMemo, useRef, useState } from 'react'

import {
  ContextMenu,
  ContextMenuDivider,
  ContextMenuItem,
  ContextMenuLabel,
} from '@/components/ContextMenu'
import { Markdown } from '@/components/chat/Markdown'
import { QuickSetupCard } from '@/components/chat/QuickSetupCard'
import { Button, EmptyState, IconButton, Modal } from '@/components/ui'
import { useCollapsed } from '@/lib/collapse'
import { useAssistantStore } from '@/stores/assistantStore'
import { useChatStore } from '@/stores/chatStore'
import { useVoiceCommand } from '@/stores/voiceCommandStore'
import type { SessionSummary } from '@/types'

type Group = { label: string; items: SessionSummary[] }

const TODAY = '今天'
const YESTERDAY = '昨天'
const THIS_WEEK = '最近 7 天'
const EARLIER = '更早'

function groupSessions(sessions: SessionSummary[]): Group[] {
  const now = new Date()
  const startOfToday = new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime()
  const startOfYesterday = startOfToday - 24 * 60 * 60 * 1000
  const startOfWeek = startOfToday - 6 * 24 * 60 * 60 * 1000

  const buckets: Record<string, SessionSummary[]> = {
    [TODAY]: [],
    [YESTERDAY]: [],
    [THIS_WEEK]: [],
    [EARLIER]: [],
  }
  for (const session of sessions) {
    const stamp = session.updated_at * 1000
    if (stamp >= startOfToday) buckets[TODAY].push(session)
    else if (stamp >= startOfYesterday) buckets[YESTERDAY].push(session)
    else if (stamp >= startOfWeek) buckets[THIS_WEEK].push(session)
    else buckets[EARLIER].push(session)
  }
  return [TODAY, YESTERDAY, THIS_WEEK, EARLIER]
    .map((label) => ({ label, items: buckets[label] }))
    .filter((group) => group.items.length > 0)
}

export function SessionList() {
  const sessions = useChatStore((state) => state.sessions)
  const activeSessionId = useChatStore((state) => state.activeSessionId)
  const persistent = useChatStore((state) => state.persistent)
  const selectSession = useChatStore((state) => state.selectSession)
  const startNewSession = useChatStore((state) => state.startNewSession)
  const deleteSession = useChatStore((state) => state.deleteSession)
  const renameSession = useChatStore((state) => state.renameSession)
  const clearHistory = useChatStore((state) => state.clearHistory)

  // 助手栏选中了哪个助手，这一栏就只显示它的对话
  const activeAssistantId = useAssistantStore((state) => state.activeId)
  const activeAssistant = useAssistantStore(
    (state) => state.assistants.find((item) => item.id === state.activeId) ?? null,
  )
  const assistantName = useAssistantStore(
    (state) => state.assistants.find((item) => item.id === state.activeId)?.name ?? '这个助手',
  )

  const [keyword, setKeyword] = useState('')
  /**
   * 正在打开的菜单：**带鼠标坐标**。
   *
   * 改造前只记 `menuFor: string`，菜单用 `absolute top-7 right-0` 锚在行内的
   * 「⋯」按钮上 —— 那样**右键**就没法复用（右键的位置不是那个按钮）。
   * 现在统一成"在某个坐标弹一张卡片"（见 components/ContextMenu），
   * 右键与「⋯」走的是同一条路。
   */
  const [menu, setMenu] = useState<{ session: SessionSummary; x: number; y: number } | null>(null)
  const [editingId, setEditingId] = useState<string | null>(null)
  const [editingTitle, setEditingTitle] = useState('')
  const [pendingDelete, setPendingDelete] = useState<SessionSummary | null>(null)
  const [pendingClear, setPendingClear] = useState(false)

  const editRef = useRef<HTMLInputElement>(null)
  useEffect(() => {
    if (editingId) editRef.current?.focus()
  }, [editingId])

  const groups = useMemo(() => {
    const lower = keyword.trim().toLowerCase()
    // 助手栏选中哪个助手，这里就只显示哪个助手的对话。
    //
    // activeId 为空（一个助手都没有）时**不过滤**：那样列表会莫名其妙全空，
    // 而用户还没来得及理解"对话是挂在助手下面的"。
    const scoped = activeAssistantId
      ? sessions.filter((session) => session.assistant_id === activeAssistantId)
      : sessions
    const filtered = lower
      ? scoped.filter((session) => session.title.toLowerCase().includes(lower))
      : scoped
    return groupSessions(filtered)
  }, [sessions, keyword, activeAssistantId])

  const beginRename = (session: SessionSummary) => {
    setMenu(null)
    setEditingId(session.id)
    setEditingTitle(session.title)
  }

  const commitRename = async () => {
    const id = editingId
    const title = editingTitle.trim()
    setEditingId(null)
    if (!id || !title) return
    await renameSession(id, title)
  }

  // 折叠后收成一条窄边。会话标题没法缩略显示，所以折叠态只保留"新建"入口，
  // 想翻历史就点开 —— 这比硬塞一列省略号标题更可用。
  const [collapsed, toggleCollapsed, setCollapsed] = useCollapsed('rail:sessions')

  // 语音命令：收起/展开对话列表。注册必须在 early return 之前。
  // 拆成两条定向命令（理由同 AssistantRail）：说「收起」就该收起，不该因为它
  // 本来就是收起的就把列表弹出来。
  useVoiceCommand('panel.sessionRail', () => setCollapsed(true))
  useVoiceCommand('panel.sessionRailExpand', () => setCollapsed(false))

  if (collapsed) {
    return (
      <aside className="flex w-[44px] shrink-0 flex-col items-center overflow-hidden rounded-[12px] border border-line bg-panel py-2.5">
        {/*
          ⚠️ 折叠态必须是**箭头向右**的图标（"收起后该改为展开
          按钮，可现在还是显示的收起按钮"）。

          原先这里用的是 `PanelRightOpen` —— 它和展开态那个 `PanelLeftClose`
          **箭头指向同一个方向（都向左）**，只是竖线的位置不同。15px 下竖线在
          哪根本看不出来，用户看到的就是"两个状态的按钮长得一样"，于是收起之后
          找不到"怎么放出来"。

          现在与展开态构成**镜像**：
          展开态 `PanelLeftClose` = 竖线在左 + 箭头向左（收起来）
          折叠态 `PanelRightClose` = 竖线在右 + 箭头向右（放出来）
        */}
        <IconButton label="展开对话列表" onClick={toggleCollapsed} className="text-ink-faint">
          <PanelRightClose size={15} />
        </IconButton>
        <IconButton
          label="新建对话 (Ctrl+N)"
          onClick={startNewSession}
          className="mt-3 border border-line bg-canvas text-ink-soft"
        >
          <MessageSquarePlus size={16} />
        </IconButton>
      </aside>
    )
  }

  return (
    <aside className="flex w-[240px] shrink-0 flex-col overflow-hidden rounded-[12px] border border-line bg-panel">
      {/*
        这一行与搭子栏的「New Buddy」行**同高对齐**（产品要求两者平行）。
        原先搜索框右边还有个「新建对话」图标按钮，按产品要求**剔除**了 ——
        新建入口留了快捷键 Ctrl+N 与输入栏上那个「开启新对话」，这里再放一个是重复。
        按钮腾出来的宽度给了搜索框。
      */}
      {/*
        ⚠️ 这一行的 `gap-1.5` / `px-2.5` / 右侧 `IconButton` 的 `mt-0.5`
        **必须与搭子列表那一行逐项相同**（"搜索栏宽高要和搭子
        列表的 +New Buddy 按钮相同"）。两栏并排在同一条水平线上，`gap` 差
        0.5（2px）、或者图标没有那 2px 的偏移，两边的"输入框/按钮"就对不齐 ——
        那种不对齐说不清哪里怪，但一眼能看见。
      */}
      <div className="flex h-11 shrink-0 items-center gap-1.5 px-2.5">
        <div className="relative min-w-0 flex-1">
          <Search
            size={14}
            className="pointer-events-none absolute top-1/2 left-2.5 -translate-y-1/2 text-ink-faint"
          />
          <input
            value={keyword}
            onChange={(event) => setKeyword(event.target.value)}
            placeholder="搜索对话"
            // ⚠️ placeholder **不能**当标签用（第 90 批，M-34）：它一输入就消失，
            // 读屏也不会把它当名字念。这里没有可见的 label（设计上就是一行紧凑搜索栏），
            // 所以补 aria-label —— 它对视觉毫无影响，只是让读屏知道这个框是干什么的。
            aria-label="搜索对话"
            /*
              ⚠️ 末尾的 `dark:border-brand/25` 是补上的（"搜索框也
              加上边框，和 +New Buddy 那个按钮相同的边框"）。

              `border-line` 只保证**浅色**下与 secondary 按钮同色；深色下那个按钮走的是
              `dark:border-brand/25`（品牌色 25% 透明），而输入框仍是 `border-line` ——
              出厂皮肤正好是深色系（暮紫），所以默认外观下这两个控件的边框**本来就
              不一样**，并排放在同一条水平线上看得出来。

              ⚠️ 只统一了**边框**：按钮那边还有 `dark:bg-brand-soft dark:text-brand`
              （品牌色的底和字），那是"按钮"该有的强调，输入框不该跟着变 ——
              一个能打字的方块若染上按钮底色，看起来就像个按不了的按钮。
            */
            /*
              ⚠️ `focus-visible:ring-*` 是第 90 批（M-35）加的，**只对键盘生效**：
              原来只有 `focus:border-brand` —— 边框从灰变品牌色，鼠标点进去看着够用，
              但键盘 Tab 过来时"当前焦点在哪"太不明显（同一屏里 h-8 的控件有好几个）。
              刻意保留 `focus:outline-none` + `focus:border-brand`：那是对鼠标用户的既有外观，
              这一批只**增加**键盘线索，不动鼠标下的样子。

              ⚠️ `h-8 w-full rounded-[8px]` 这段字面被打包闸钉着（要和 +New Buddy 按钮同款），
              改类名时别把它拆开。
            */
            className="h-8 w-full rounded-[8px] border border-line bg-canvas pr-2 pl-7 text-[12.5px] text-ink placeholder:text-ink-faint focus:border-brand focus:outline-none focus-visible:ring-2 focus-visible:ring-brand/40 dark:border-brand/25"
          />
        </div>
        {/*
          ⚠️ 展开态这里必须用**向左收**的图标（报"收起后展开
          按钮还是用的收起图标"）。原先两处都是 `PanelRightOpen` —— 展开时按
          它应该是"收起来"，却画着"展开"的箭头，用户点下去之前完全猜不到会发生什么。
        */}
        {/* `mt-0.5` 与搭子列表那个同款：`Button`（h-8）与 `IconButton`（h-8）
            在 44px 的行里各自垂直居中，但图标视觉重心偏上 —— 加这 2px 让两个栏的
            图标落在同一条水平线上 */}
        <IconButton
          label="隐藏对话列表"
          onClick={toggleCollapsed}
          className="mt-0.5 shrink-0 text-ink-faint"
        >
          <PanelLeftClose size={15} />
        </IconButton>
      </div>

      {/* 当前助手简介置顶（产品要求）：不用翻列表就能确认"这些对话属于谁" */}
      {activeAssistant ? (
        <div className="mx-2.5 mb-1 flex items-center gap-2 rounded-[8px] border border-line-soft bg-canvas px-2.5 py-2">
          {/*
            ⚠️ 这里原本有一个 `AssistantAvatar`（产品要求剔除）。
            确实是多余的：这张卡顶在最上面，而正下方就是**同一位搭子**的会话列表，
            左下角搭子栏里还亮着它的头像 —— 同一张脸在一屏里出现三次。而这卡真正
            要回答的是"这些对话属于谁、它是什么脾气"，靠名字 + 简介就够了。
          */}
          <div className="min-w-0 flex-1">
            {/* 显示"对话里的称呼"（nickname 优先，没设才用 name）——与顶部标题栏、
                消息气泡、输入框右下角的称呼保持同一口径。

                ⚠️ 这里**不能**只显示 `name`：AI 改自己名字走的是 nickname
                （内置技能 `update_assistant_profile`），而 name 它改不了。只显示 name
                的话，用户在对话里让 AI 改名、回过头看这张卡还是旧名字，又成了
                "改了没生效"。刷新由 chatStore 在一轮结束时统一做（见其 finally）。 */}
            <div className="truncate text-[12px] font-medium text-ink">
              {activeAssistant.nickname || activeAssistant.name}
            </div>
            {/* 简介**不截断**（产品明确要求：不管多少字都完整展示）并且按
                Markdown 渲染（产品要求：输入能换行、展示也能换行、支持 md）——
                所以走 Markdown 的 compact 变体，而不是一段纯文本。
                `break-words` 留给外层的场景：防长 URL 一类"无空格长串"把侧栏撑宽。 */}
            {activeAssistant.description ? (
              <div className="text-[11px] leading-relaxed break-words text-ink-faint">
                <Markdown content={activeAssistant.description} compact />
              </div>
            ) : (
              <p className="text-[11px] text-ink-faint">这个助手还没有简介</p>
            )}
          </div>
        </div>
      ) : null}

      {/* 内置搭子的快捷设置：只对四个内置搭子出现，保存过一次就换成
          一句固定说明。`key` 必须用搭子 id —— 换搭子时让它**重新挂载**，卡片内部才
          有机会在卸载时把"没保存的预览"撤回原样（见 QuickSetupCard 的卸载清理）。 */}
      {activeAssistant?.locked ? (
        <QuickSetupCard key={activeAssistant.id} assistant={activeAssistant} />
      ) : null}

      <div className="min-h-0 flex-1 overflow-y-auto px-2 pb-3">
        {groups.length === 0 ? (
          <div className="pt-16">
            <EmptyState
              title={
                keyword
                  ? '没有匹配的对话'
                  : activeAssistantId
                    ? '这个助手还没有对话'
                    : '还没有对话'
              }
              // 明确说出"对话是按助手分开的"，否则用户看到空列表会以为历史丢了
              description={
                keyword
                  ? undefined
                  : activeAssistantId
                    ? `发一条消息就会在这里生成「${assistantName}」的对话。`
                    : '点击右上角的加号开始第一次对话。'
              }
            />
          </div>
        ) : (
          groups.map((group) => (
            <section key={group.label} className="mb-3">
              <div className="px-2 py-1.5 text-[11px] font-medium tracking-wide text-ink-faint">
                {group.label}
              </div>
              {group.items.map((session) => {
                const active = session.id === activeSessionId
                const editing = editingId === session.id

                return (
                  <div
                    key={session.id}
                    /*
                      ⚠️ 键盘可达性（第 90 批，M-38）：这一行以前是个**纯 div 带 onClick** ——
                      Tab 跳不进来、回车也没反应，"换个会话"对只用键盘的用户等于不存在。

                      为什么是 `role="button"` 而不是真的写成 `<button>`：行里**嵌着**
                      一个「⋯」菜单按钮和（重命名时的）输入框。`<button>` 里放交互元素
                      是非法结构，浏览器会把点击事件搅在一起。要写成真 button 就得把
                      「⋯」和输入框挪出这一行、再重排内边距 —— 那动的是一处用户反复调过的
                      外观（px-2 py-1.5 / rounded-[8px] / 悬停底色），风险与收益不成比例。
                      `role="button"` + `tabIndex` + 键盘处理给到的是**同一份可达性**。
                    */
                    role="button"
                    tabIndex={editing ? -1 : 0}
                    // 读屏会念出"当前项"（原来只有背景色能看出选中了谁）
                    aria-current={active ? 'true' : undefined}
                    className={clsx(
                      'group relative mb-0.5 flex cursor-pointer items-center rounded-[8px] px-2 py-1.5 transition-colors',
                      // ⚠️ 渲染层虚拟化（第 95 批，L-20）：视口外的行跳过布局与绘制。
                      // 为什么用 CSS 而不是"只渲染可见行"、以及那句 `50px` 是怎么来的、
                      // 改行高时要一起改什么 —— 全在 index.css 的 `.cv-session-row` 注释里。
                      'cv-session-row',
                      // 键盘焦点要看得见（鼠标下不变）：整行加一圈环，别只靠底色
                      'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand/50',
                      active ? 'bg-brand-soft' : 'hover:bg-hover',
                    )}
                    onClick={() => !editing && void selectSession(session.id)}
                    onDoubleClick={() => beginRename(session)}
                    onKeyDown={(event) => {
                      // ⚠️ 只处理**落在行本身**上的按键。行里嵌着「⋯」按钮与重命名输入框，
                      // 它们的键盘事件会冒泡上来 —— 不判 target 的话，用空格点「⋯」
                      // 会顺带把会话也切了（而且空格默认还会滚动列表）。
                      if (event.target !== event.currentTarget) return
                      if (event.key !== 'Enter' && event.key !== ' ') return
                      event.preventDefault()
                      if (!editing) void selectSession(session.id)
                    }}
                    // 右键 = 与行尾「⋯」完全相同的菜单（产品要求）。
                    // 位置用鼠标坐标，所以两者共用一份渲染（见 components/ContextMenu）
                    onContextMenu={(event) => {
                      event.preventDefault()
                      setMenu({ session, x: event.clientX, y: event.clientY })
                    }}
                  >
                    <div className="min-w-0 flex-1">
                      {editing ? (
                        <input
                          ref={editRef}
                          value={editingTitle}
                          onChange={(event) => setEditingTitle(event.target.value)}
                          onClick={(event) => event.stopPropagation()}
                          onBlur={() => void commitRename()}
                          onKeyDown={(event) => {
                            if (event.key === 'Enter') void commitRename()
                            if (event.key === 'Escape') setEditingId(null)
                          }}
                          // ⚠️ `focus-visible:ring-*` 是第 93 批补的（第 90 批的 M-35 漏了这一处，
                          // 文档却把它列进了名单）：它的边框**常驻**是品牌色，
                          // 所以"焦点在哪"从这个框本身完全看不出来，只剩 `focus:outline-none`
                          // 把默认轮廓也压掉了。键盘线索只能靠这圈 ring。
                          className="h-6 w-full rounded-[5px] border border-brand bg-canvas px-1.5 text-[13px] text-ink focus:outline-none focus-visible:ring-2 focus-visible:ring-brand/40"
                        />
                      ) : (
                        <div
                          className={clsx(
                            'truncate text-[13px]',
                            active ? 'font-medium text-brand' : 'text-ink',
                          )}
                        >
                          {session.title}
                        </div>
                      )}
                      <div className="mt-0.5 text-[11px] text-ink-faint">
                        {session.message_count} 条消息
                      </div>
                    </div>

                    {!editing ? (
                      <button
                        type="button"
                        aria-label="更多操作"
                        onClick={(event) => {
                          event.stopPropagation()
                          if (menu?.session.id === session.id) {
                            setMenu(null)
                            return
                          }
                          // 菜单弹在按钮**下方右对齐**的位置（用鼠标坐标那一套，
                          // 所以这里把按钮的右下角当作"鼠标位置"传进去）
                          const rect = event.currentTarget.getBoundingClientRect()
                          setMenu({ session, x: rect.right, y: rect.bottom + 4 })
                        }}
                        className={clsx(
                          'no-drag flex h-6 w-6 shrink-0 items-center justify-center rounded-[6px] text-ink-faint hover:bg-canvas hover:text-ink',
                          // 菜单开着时按钮保持可见，否则鼠标一移开它就"消失"了，
                          // 看起来像菜单失去了归属
                          menu?.session.id === session.id
                            ? 'opacity-100'
                            : // ⚠️ `group-focus-within:opacity-100` 是第 90 批（M-38）加的：
                              // 这个按钮平时是 `opacity-0`，只在鼠标悬停那一行时才浮出来。
                              // 对键盘用户来说它是**可以 Tab 到、但看不见**的 ——
                              // 焦点落在一个完全透明的按钮上，等于没有焦点提示。
                              // 焦点进入这一行（Tab 到行上）时先把它显出来，用户才知道
                              // 下一个 Tab 会落在哪儿。
                              'opacity-0 transition-opacity group-hover:opacity-100 group-focus-within:opacity-100 focus-visible:opacity-100',
                        )}
                      >
                        <MoreHorizontal size={14} />
                      </button>
                    ) : null}
                  </div>
                )
              })}
            </section>
          ))
        )}
      </div>

      {/*
        ⚠️ 这里原本还有一个「新建对话」按钮，按产品要求**剔除**。

        剔除的理由和当初删掉搜索框旁边那个图标按钮是同一条（见上面那一行的注释）：
        新建对话现在有三个入口 —— 快捷键 Ctrl+N、输入栏左下角那个「开启新对话」、
        以及在列表最上面直接开一条。再在底部常驻一个按钮，是**第四处**重复，
        而且它占着列表最后几十像素的高度，把真正要看的历史记录挤掉一行。

        只留"内存模式"这条警告：它不是入口，是**现在的对话会不会丢**的告知，
        少了它用户会以为记录一直在。
      */}
      {!persistent ? (
        <div className="shrink-0 border-t border-line px-3 py-2">
          <div className="flex items-start gap-1.5 px-1 text-[10.5px] leading-relaxed text-warning">
            <AlertTriangle size={11} className="mt-[2px] shrink-0" />
            当前为内存模式，对话不会保留到下次启动
          </div>
        </div>
      ) : null}

      {/* 对话行的菜单：右键与行尾「⋯」共用这一份（见 components/ContextMenu） */}
      {menu ? (
        <ContextMenu
          x={menu.x}
          y={menu.y}
          width={168}
          onClose={() => setMenu(null)}
        >
          <ContextMenuLabel>{menu.session.title}</ContextMenuLabel>

          {menu.session.assistant_id ? (
            <ContextMenuItem
              icon={<PictureInPicture2 size={13} className="text-ink-faint" />}
              onSelect={() => {
                // 传会话 id：独立窗口直接打开**这一条**会话（产品要求）
                const target = menu.session
                setMenu(null)
                window.agentBridge?.openChatWindow(target.assistant_id ?? '', target.id)
              }}
            >
              独立窗口对话
            </ContextMenuItem>
          ) : null}
          <ContextMenuItem
            icon={<Pencil size={13} className="text-ink-faint" />}
            onSelect={() => beginRename(menu.session)}
          >
            重命名
          </ContextMenuItem>

          <ContextMenuDivider />

          <ContextMenuItem
            icon={<Eraser size={13} className="text-ink-faint" />}
            onSelect={() => {
              const target = menu.session
              setMenu(null)
              // 先切过去再确认：清空的是"这条会话"，用户得先看到它
              void selectSession(target.id).then(() => setPendingClear(true))
            }}
          >
            清空对话内容
          </ContextMenuItem>
          <ContextMenuItem
            icon={<Trash2 size={13} />}
            danger
            onSelect={() => {
              const target = menu.session
              setMenu(null)
              setPendingDelete(target)
            }}
          >
            删除对话
          </ContextMenuItem>
        </ContextMenu>
      ) : null}

      {/* 删除确认 */}
      <Modal
        open={pendingDelete !== null}
        onClose={() => setPendingDelete(null)}
        width="max-w-md"
        title="删除对话"
        description="删除后该对话及其全部消息将无法恢复。"
        footer={
          <>
            <Button onClick={() => setPendingDelete(null)}>取消</Button>
            <Button
              variant="danger"
              onClick={() => {
                const target = pendingDelete
                setPendingDelete(null)
                if (target) void deleteSession(target.id)
              }}
            >
              删除
            </Button>
          </>
        }
      >
        <p className="text-[13px] text-ink">
          确定要删除「
          <span className="font-medium">{pendingDelete?.title}</span>
          」吗？该对话共有 {pendingDelete?.message_count ?? 0} 条消息。
        </p>
      </Modal>

      {/* 清空确认 */}
      <Modal
        open={pendingClear}
        onClose={() => setPendingClear(false)}
        width="max-w-md"
        title="清空对话内容"
        description="会删除该对话的全部消息，但保留对话本身。"
        footer={
          <>
            <Button onClick={() => setPendingClear(false)}>取消</Button>
            <Button
              variant="danger"
              onClick={() => {
                setPendingClear(false)
                void clearHistory()
              }}
            >
              清空
            </Button>
          </>
        }
      >
        <p className="text-[13px] text-ink">此操作不可撤销，确定继续吗？</p>
      </Modal>
    </aside>
  )
}
