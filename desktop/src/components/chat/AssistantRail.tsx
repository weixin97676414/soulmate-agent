import clsx from 'clsx'
import { PanelLeftClose, PanelRightClose, Plus } from 'lucide-react'
import { Fragment, useEffect, useState } from 'react'

import {
  AssistantAvatar,
  AssistantFormModal,
  blankProfile,
} from '@/components/chat/AssistantFormModal'
import { AssistantContextMenu } from '@/components/chat/AssistantContextMenu'
import { NewBuddyFlow } from '@/components/chat/NewBuddyDialog'
import { Button, IconButton, Modal } from '@/components/ui'
import { useCollapsed } from '@/lib/collapse'
import { switchAssistant } from '@/services/assistantSwitch'
import { useAssistantStore } from '@/stores/assistantStore'
import { useVoiceCommand } from '@/stores/voiceCommandStore'
import type { AssistantProfile } from '@/types'

/**
 * 左侧助手栏。
 *
 * 把"选哪个助手"从对话区顶栏挪到独立一栏，理由有两个：
 * - 零基础用户很难理解"顶栏那个下拉框决定的是人设"——它和右边的模型下拉长得太像了；
 * - 助手是**一整套设定**（人设 + 模型 + 工具白名单 + 权限策略），值得有自己的一栏，
 *   而且它的对话就挂在它下面，层级关系一眼可见。
 *
 * 注意助手项显示的是**各自的 emoji**而不是应用品牌图：emoji 是这个助手自己的
 * 标识（表单里可以选），全换成品牌图反而让列表失去区分度。
 */
export function AssistantRail() {
  const assistants = useAssistantStore((state) => state.assistants)
  const activeId = useAssistantStore((state) => state.activeId)
  const remove = useAssistantStore((state) => state.remove)

  // ⚠️ 这里以前还订阅了 `sessions` / `selectSession` / `startNewSession`，
  // 因为切换搭子的落点逻辑写在本组件里。它现在搬去了 `services/assistantSwitch`
  // （语音喊名字那条路也要有完全一样的落点），所以这几个订阅不再需要 ——
  // 顺带的好处是**这个组件的重渲染不再跟着会话列表跑**。

  const [menu, setMenu] = useState<{ profile: AssistantProfile; x: number; y: number } | null>(null)
  /** 「New Buddy」打开的是**新建方式选择**（手动 / 导入搭子 / 导入搭子群） */
  const [newOpen, setNewOpen] = useState(false)
  const [editing, setEditing] = useState<{ profile: AssistantProfile; isNew: boolean } | null>(
    null,
  )
  const [pendingDelete, setPendingDelete] = useState<AssistantProfile | null>(null)

  /**
   * 响应"请打开某个搭子的编辑弹窗"（来自头像大图里的「配置搭子」等外部入口）。
   *
   * ⚠️ 读到之后**立刻清掉**：它是一次性信号，不清的话这个组件下次重渲染
   * （切搭子、加载出新数据都会）会莫名其妙又弹一次。
   */
  const editRequestId = useAssistantStore((state) => state.editRequestId)
  const clearEditRequest = useAssistantStore((state) => state.clearEditRequest)
  useEffect(() => {
    if (!editRequestId) return
    const target = assistants.find((item) => item.id === editRequestId)
    clearEditRequest()
    if (target) setEditing({ profile: target, isNew: false })
  }, [editRequestId, assistants, clearEditRequest])

  /**
   * 「请打开**新建**流程」的一次性信号（与上面那条编辑信号同一套机制）。
   *
   * 设置页取消之后，输入栏那个「新建助手」按钮改成了发这个信号 —— 它够不着
   * 本组件里那个 `newOpen` 本地状态，而新建流程的落点（先问"手动 / 导入搭子包 /
   * 导入搭子群"）在这里。信号必须**读到就清掉**，否则下次重渲染又会弹一次。
   */
  const newRequest = useAssistantStore((state) => state.newRequest)
  const clearNewRequest = useAssistantStore((state) => state.clearNewRequest)
  useEffect(() => {
    if (!newRequest) return
    clearNewRequest()
    setNewOpen(true)
  }, [newRequest, clearNewRequest])

  /**
   * 切换搭子的落点：优先取**这个搭子最近一次会话**。
   *
   * 直接切过去停在一个空白页会让人以为"之前的对话丢了"；而没有会话时进入空白态
   * 是对的 —— 这里刻意**不**提前创建会话，因为真正的会话是后端在首次发送时才建的
   * （见 chatStore 的说明），提前建会在数据库里留下一堆空会话。
   *
   * ⚠️ **正在回答时也能切**（产品要求「切换对话，切换搭子，
   * 切换到任何页面都不打断」）。
   *
   * 这里原先有一段拦截：正在流式时弹一条「切换搭子会打断这一轮回答」然后 return。
   * 拦的原因其实不是"会打断"，而是**老架构切不了** —— 全局只有一个消息列表，
   * 切走之后流式分片会补到另一个搭子的对话上。
   *
   * 现在消息与运行态都按会话分桶（见 chatStore 的 `messagesBySession` / `runs`），
   * 每一轮写的是**它自己那条会话**，切走只是"看不见"，任务照跑。所以拦截与提示
   * 一起删掉：没有任何东西会被打断，再说"会打断"就成了假话。
   */
  const switchTo = (id: string) => {
    // 点已经选中的那个搭子不做事：连"重新加载最近会话"都省掉，
    // 否则用户在当前对话里翻找时手滑点一下自己，视图会被拽回列表顶部那条。
    if (id === activeId) return
    // ⚠️ 逻辑搬去了 `services/assistantSwitch`：语音喊名字那条路也要有**完全一样**的
    // 落点（切过去打开该搭子最近一次对话）。两处各写一份的结果就是它们悄悄走歪
    // —— 实测反馈"用嘴切搭子跟用鼠标切不是一个效果"正是这么来的。
    switchAssistant(id)
  }

  const confirmDelete = async () => {
    const target = pendingDelete
    setPendingDelete(null)
    if (!target) return

    const wasActive = target.id === useAssistantStore.getState().activeId
    await remove(target.id)

    // 删掉"当前助手"后不能停在 null：那样对话列表会因为"没有助手"而不过滤，
    // 突然显示出全部对话，看起来像"别的助手的对话跑过来了"。
    if (!wasActive) return
    const rest = useAssistantStore.getState().assistants
    if (rest.length > 0) switchTo(rest[0].id)
  }

  // 折叠后收成一条窄边，只留头像 —— 想看全名再点开。
  // 状态记在本机（见 useCollapsed），下次启动沿用。
  const [collapsed, toggleCollapsed, setCollapsed] = useCollapsed('rail:assistants')

  // 语音命令：收起/展开搭子栏、新建搭子 —— 以前只在命令表里有声明。
  // ⚠️ 必须在下面的 `if (collapsed) return` **之前**注册：折叠态恰恰是最想说这句话的时候。
  //
  // 收起与展开拆成**两条**命令（实测反馈"只有收起没有展开"）：都用 toggle 的话，
  // 已经收起时说「收起搭子栏」反而会把它弹出来，用户只会认为识别错了。
  // 按钮上那个 toggle 保持不变 —— 点它的人眼前看得见当前是开是合，没有这个歧义。
  useVoiceCommand('panel.assistantRail', () => setCollapsed(true))
  useVoiceCommand('panel.assistantRailExpand', () => setCollapsed(false))
  useVoiceCommand('buddy.new', () => setNewOpen(true))

  if (collapsed) {
    return (
      <aside className="flex w-[44px] shrink-0 flex-col items-center overflow-hidden rounded-[12px] border border-line bg-panel py-2.5">
        {/* 折叠控件用「面板」样式（产品要求）：点它的意思就是"把这一栏收起来/放出来"，
            比书页更直接地表达"面板开合" */}
        {/* ⚠️ 折叠态必须用**箭头向右**的图标（报"收起后还是显示
            的收起按钮"）：原先的 `PanelRightOpen` 与展开态的 `PanelLeftClose`
            箭头**同向（都向左）**，竖线位置的不同在 15px 下看不出来 —— 用户看到
            的就是"收起来之后按钮没变，找不到怎么放出来"。
            现在与展开态构成镜像：展开态竖线左+箭头左，折叠态竖线右+箭头右。 */}
        <IconButton label="展开助手栏" onClick={toggleCollapsed} className="text-ink-faint">
          <PanelRightClose size={15} />
        </IconButton>
        <div className="mt-3 flex min-h-0 flex-1 flex-col items-center gap-1.5 overflow-y-auto">
          {assistants.map((profile) => (
            <button
              key={profile.id}
              type="button"
              title={profile.name}
              onClick={() => switchTo(profile.id)}
              className={clsx(
                'rounded-[7px] p-0.5 transition-opacity',
                profile.id === activeId ? 'ring-1 ring-brand/50' : 'opacity-70 hover:opacity-100',
              )}
            >
              <AssistantAvatar profile={profile} size={22} />
            </button>
          ))}
        </div>
      </aside>
    )
  }

  return (
    <aside className="flex w-[240px] shrink-0 flex-col overflow-hidden rounded-[12px] border border-line bg-panel">
      {/* 这一行的高度与下面「对话列表」的搜索框对齐（产品要求两者平行同高） */}
      <div className="flex h-11 shrink-0 items-center gap-1.5 px-2.5">
        <Button
          variant="secondary"
          size="sm"
          icon={<Plus size={13} />}
          /*
            ⚠️ `!h-8` 里的 `!` 不能去掉（报"搜索栏和这个按钮一大一小"）。

            根因：`size="sm"` 的基础类里写着 `h-7`（28px，见 components/ui.tsx），
            而这里又追加 `h-8`（32px）—— **同一个属性两个类**，谁赢只取决于 Tailwind
            生成 CSS 的顺序，不取决于写在谁后面。实际渲染成了 28px，于是它比旁边
            「对话列表」那个 h-8（32px）的搜索框矮 4px。
            加 `!`（Tailwind 的 important）之后高度是确定的，两栏那一排才真正齐。
          */
          className="!h-8 flex-1"
          // 先选"怎么建"（手动 / 导入搭子包 / 导入搭子群），不再直接开表单
          onClick={() => setNewOpen(true)}
        >
          New Buddy
        </Button>
        {/* 折叠 = 面板图标（产品要求，原来是书页）；只留图标的话没人知道点了会怎样 */}
        {/* ⚠️ 展开态用「向左收」的图标（报"收起后展开按钮还是
            用的收起图标"）。原先这里和折叠态那个都是 `PanelRightOpen` ——
            展开时按它本该是"收起来"，却画着"展开"的箭头。 */}
        <IconButton
          label="隐藏助手栏"
          onClick={toggleCollapsed}
          className="mt-0.5 shrink-0 text-ink-faint"
        >
          <PanelLeftClose size={15} />
        </IconButton>
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto px-1.5 pb-2">
        {assistants.length === 0 ? (
          <p className="px-2 py-3 text-[11.5px] leading-relaxed text-ink-faint">
            还没有搭子。点上面的「New Buddy」创建一个。
          </p>
        ) : null}

        {assistants.map((profile, index) => {
          const selected = profile.id === activeId
          /*
            内置搭子（四个）与用户自建之间画一条分隔线（产品要求）。
            这两组性质不同：上面是不可删除的出厂搭子，下面是用户自己的 ——
            原先它们只是首尾相接的一串，用户看不出边界在哪，也会误以为内置的
            那几个删得掉。
          */
          const divider = Boolean(assistants[index - 1]?.builtin) && !profile.builtin
          return (
            <Fragment key={profile.id}>
            {divider ? <div className="my-1.5 border-t border-line-soft" /> : null}
            <button
              type="button"
              onClick={() => switchTo(profile.id)}
              // 右键直接配置这个助手 —— 这是用户明确要的交互
              onContextMenu={(event) => {
                event.preventDefault()
                setMenu({ profile, x: event.clientX, y: event.clientY })
              }}
              className={clsx(
                'mb-0.5 flex w-full items-center gap-2 rounded-[8px] px-2 py-1.5 text-left transition-colors',
                selected
                  ? 'bg-brand-soft font-medium text-brand'
                  : 'text-ink-soft hover:bg-hover hover:text-ink',
              )}
            >
              {/* ⚠️ 尺寸 **24**（"搭子栏搭子卡片上的头像放大一圈"）——
                  原先是 18，与右边的名字（12.5px）差不多高，头像几乎看不出是谁。
                  24 之后行高会从 30 涨到 36，这是**有意的**：那一圈正是要的效果。 */}
              <AssistantAvatar profile={profile} size={24} />
              <span className="min-w-0 flex-1 truncate text-[12.5px]">{profile.name}</span>
              {/*
                ⚠️ 这里原有一个「内置」小标签（`profile.builtin`），产品要求剔除：
                列表里四个内置搭子右边都挂着这两个字，而它们**本来就是出厂就有的**，
                天天摆在那里既挤占名字的宽度，也不提供任何可操作的信息 ——
                真正需要知道"哪些改不了"的时候，进配置页会有明确的「固定」标记。
                分组分隔线（下面那个用 `builtin` 判定的）**保留**：它区分"内置"与
                "我自己的"，是有用的结构信息，不是标签。
              */}
            </button>
            </Fragment>
          )
        })}
      </div>

      {menu ? (
        <AssistantContextMenu
          profile={menu.profile}
          x={menu.x}
          y={menu.y}
          isActive={menu.profile.id === activeId}
          onClose={() => setMenu(null)}
          onEdit={() => {
            setEditing({ profile: menu.profile, isNew: false })
            setMenu(null)
          }}
          onSetActive={() => {
            switchTo(menu.profile.id)
            setMenu(null)
          }}
          onDelete={() => {
            setPendingDelete(menu.profile)
            setMenu(null)
          }}
        />
      ) : null}

      <AssistantFormModal
        open={editing !== null}
        initial={editing?.profile ?? null}
        isNew={editing?.isNew ?? true}
        onClose={() => setEditing(null)}
      />

      {/* 新建方式：手动配置走上面的表单，导入则切到导入面板（搭子栏与设置页共用同一份） */}
      <NewBuddyFlow
        open={newOpen}
        onClose={() => setNewOpen(false)}
        onManual={() => {
          setNewOpen(false)
          setEditing({ profile: blankProfile(), isNew: true })
        }}
      />

      <Modal
        open={pendingDelete !== null}
        onClose={() => setPendingDelete(null)}
        title="删除搭子"
        width="max-w-md"
        description="这个搭子会被删除，但它名下的对话不会丢，之后仍能在其他搭子下打开。"
        footer={
          <>
            <Button onClick={() => setPendingDelete(null)}>取消</Button>
            <Button variant="danger" onClick={() => void confirmDelete()}>
              删除
            </Button>
          </>
        }
      >
        <p className="text-[12.5px] leading-relaxed text-ink-soft">
          确定要删除「{pendingDelete?.name}」吗？
          {pendingDelete?.builtin
            ? /* ⚠️ 这个分支只对**存量**的内置搭子有效（例如老版本留下的 office）：
                四个在册内置搭子的右键菜单里根本不画删除项（`profile.locked`），
                但「builtin 且不 locked」的旧记录**删得掉**，那时必须把后果说清楚。

                ⚠️ 措辞在 改过：恢复入口（`POST /v1/assistants/reset`）
                随设置页一起删除了，产品约定是「正常用户没有删除它的途径，
                所以不支持找回」—— 所以这里不能再写"之后可以找回"，
                也不能再指着那个已经不在的界面说事。 */
              ' 它是内置搭子（出厂自带、名称与简介由产品固定），删掉之后无法找回。'
            : ''}
        </p>
      </Modal>
    </aside>
  )
}
