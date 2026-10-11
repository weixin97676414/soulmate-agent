import { isDarkTheme } from '@shared/bridge'
import { Minus, Moon, RotateCcw, Square, Sun, X } from 'lucide-react'

import { AssistantAvatar } from '@/components/chat/AssistantFormModal'
import { GroupAvatar } from '@/components/chat/GroupAvatar'
import { BrandMark } from '@/components/BrandMark'
import { IconButton } from '@/components/ui'
import { useCurrentGroup } from '@/lib/currentSubject'
import { useAppStore } from '@/stores/appStore'
import { useAssistantStore } from '@/stores/assistantStore'
import { useChatStore } from '@/stores/chatStore'

interface TitleBarProps {
  /**
   * 这一屏**还没进入应用**（启动闪屏 / 首启引导）→ 左上角固定为产品标识与产品名。
   *
   * ⚠️ 为什么需要这个开关：首启时后端会把 `activeId` 自动落到出厂默认搭子，
   * 于是引导页也命中"当前搭子"分支、顶着「搭子总管」的头像和名字 ——
   * 而用户此时连模型都还没配，看到的是一个他从没听说过的东西。
   * 的原话是"这时候我要看到的是我们自己的 logo 和名字"。
   *
   * 由调用方显式声明，而不是让标题栏自己去推导引导态：启动闪屏那一屏拿不到
   * `needsOnboarding` 的结论（模型与本地模型状态都还没加载完），
   * 而且"模型配没配好"和"标题栏显示什么"本来就是两件事。
   */
  brandOnly?: boolean
}

/**
 * 自绘标题栏（含最小化/最大化/关闭按钮）。
 *
 * 不再用系统的 titleBarOverlay 按钮 —— 那一块是纯色，壁纸渲染不过去（反馈 #7）。
 * 整条标题栏现在都是 DOM，背景透出壁纸；右侧三个窗口按钮由我们自绘，
 * 关闭走 ``win.close()`` 以触发既有的 closeAction 流程。
 */
export function TitleBar({ brandOnly = false }: TitleBarProps) {
  const theme = useAppStore((state) => state.theme)
  const toggleTheme = useAppStore((state) => state.toggleTheme)
  const health = useAppStore((state) => state.health)
  // 这里曾有 `skillCount`（用于"工具 + 技能"两个数）。产品要求
  // 合并成一个去重后的数，而那个数就是 `health.skills`（见渲染处说明）。

  /*
    ⚠️ 这里原本取当前会话标题（`sessions` + `activeSessionId` → `activeTitle`）显示在
    标题栏**正中**。产品要求"不再显示当前对话名，暂时留白"，所以整段
    取数逻辑一并删掉了 —— 只留变量不渲染的话，tsc 会报"未使用的变量"，而且下次
    有人看见它还在算，会以为界面上某处仍显示着这个标题。

    ⚠️ 别和**左上角的主体名**搞混：那个（`primaryName` / `nickname`）还在显示。
    用户要留白的是"当前对话名"。
  */
  // 是否有搭子在后台干活（要求 #8）：切到别的页面后，这是用户唯一能
  // "看见它还在跑"的地方 —— 没有它，用户只能靠切回去看内容有没有变。
  const runningAssistantId = useChatStore((state) => state.runningAssistantId)
  /**
   * 有几个会话在跑。
   *
   * ⚠️ 这里**不能**用 `streaming`：它的语义已经收窄成"**当前可见会话**
   * 是否在跑"（输入框该显示「发送」还是「停止」由它决定）。而"后台还有没有
   * 搭子在干活"是另一件事 —— 用户切到设置页时，眼前这条多半是不跑的，
   * 但后台可能正有两条在跑。用 `runs` 的元素个数才不会漏报。
   */
  const runningCount = useChatStore((state) => Object.keys(state.runs).length)

  // 当前搭子（含头像）。左上角标识跟随搭子头像（产品要求）。
  const activeAssistant = useAssistantStore((state) =>
    state.assistants.find((item) => item.id === state.activeId),
  )
  // 用户是否**主动点选过**搭子。没点过就一律显示产品名 —— 首启时 activeId 会被
  // 自动落到后端写死的默认搭子（0.1.36 起是「搭子总管」BuddyManager），
  // 那是"系统选的"不是"用户选的"。
  // ⚠️ 别把这个规则改回"按 default_assistant 判断"：那条规则会让"内置默认搭子被
  // 点中时名字不替换"，用户看到的是"有的 buddy 点了没反应"。
  // ⚠️ 这里曾有 `picked`（"用户主动点选过吗"），用来决定左上角显示产品名还是
  // 搭子名。按产品要求取消了这个区分 —— 进入应用就直接显示当前
  // 搭子的头像与名字（见下面 `shownAssistant` 的说明）。
  // 正在后台干活的那个搭子（可能**不是**当前选中的这个）
  const runningAssistant = useAssistantStore((state) =>
    runningAssistantId
      ? state.assistants.find((item) => item.id === runningAssistantId)
      : undefined,
  )

  // 左上角实际展示的搭子（含头像）。用户没点过时为空 → 回落成产品名 + 品牌标。
  //
  // 「名」与「昵称」是两个不同的东西：`name` 是搭子叫什么（工作助手、生活管家），
  // `nickname` 是它希望你怎么称呼它（小助、阿管）。两者都显示；没设昵称、
  // 或昵称恰好与名字相同（用户没改过默认值）时只显示一个，避免看着像重复。
  /*
    ⚠️ 不再看 `picked`（产品要求）：进入应用后左上角**直接显示
    当前搭子的头像**，之后每次切搭子随时变化。

    原先的规则是"用户主动点选过才换成搭子头像，否则显示产品名 Soulmate Agent"
    —— 那是为了不让用户一进来就顶着一个没听说过的搭子名。但现在的首启流程
    已经把用户送到 BuddyManager 了，再显示产品名反而像"没进应用"：
    用户看到的是一个和左边列表里那个高亮项**对不上**的标识。
    默认落在 BuddyManager 这件事由 `pickInitialAssistant` 保证（后端出厂
    `DEFAULT_ASSISTANT_ID = "BuddyManager"`）。
  */
  const shownAssistant = activeAssistant

  /**
   * 当前正在看的**群**（不在群上下文里就是 `undefined`）。
   *
   * ⚠️ 判定抽在 `lib/currentSubject` —— **语音设置面板要判同一件事**，
   * 而两处判得不一样的表现很微妙：标题栏顶着群名，面板却在配搭子的唤醒词。
   */
  const activeGroup = useCurrentGroup()

  /*
    左上角标识跟的是"当前主体"：群聊页跟群，其余页面跟搭子，都没有时才是产品名。

    群**没有昵称**（那是搭子特有的"它希望你怎么称呼它"），所以群名直接当主标题。

    ⚠️ `brandOnly` 是唯一的前置例外（见类型注释）：启动闪屏与首启引导那两屏
    固定产品名。**标题与昵称必须一起强制** —— 只换图标不换标题会渲染出
    "品牌图标 + 搭子名"这种自相矛盾的一行。
  */
  const primaryName = brandOnly
    ? 'Soulmate Agent'
    : activeGroup?.name || shownAssistant?.name || 'Soulmate Agent'
  const nickname = brandOnly || activeGroup ? '' : (shownAssistant?.nickname?.trim() ?? '')
  const showNickname = Boolean(nickname) && nickname !== primaryName

  /**
   * 品牌标识。品牌态与"没有任何当前主体"时**共用这同一份 JSX** ——
   * 尺寸与圆角必须和另外两种头像严格对齐（见下面"三个分支的尺寸与圆角比例
   * 必须一致"那段说明），拆成两份复制迟早会漂移。
   */
  const brandMark = <BrandMark size={24} radius={6} bordered={false} />

  // ⚠️ `pl-2`（8px）不是随手取的：标题栏高 40px、左上角那个标识 24px，上下各留 8px；
  // 产品要求"logo 左边离左侧的距离，与离上下的距离相同" ——
  // 所以左边距也得是 8px。原来写 `pl-4`（16px），比上下多一倍，看起来是往右缩了一截。
  return (
    <header className="drag-region flex h-10 shrink-0 items-center gap-3 bg-canvas pl-2">
      <div className="flex items-center gap-2">
        {/*
          ⚠️ 尺寸 **24**，与搭子栏列表项的头像**一样大**（
          "该 logo 显示也放大一圈，和搭子表中搭子头像一样大"）。原先是 22。

          ⚠️ 三个分支的 **尺寸与圆角比例必须一致**（`AssistantAvatar` /
          `GroupAvatar` 内部都按 `size * 6/22` 算圆角，`BrandMark` 这里手动对齐）：
          同一位置上三种形态切来切去时，半径差 1px 就会被看成"闪了一下"。

          ⚠️ 不再按 `shownAssistant?.avatar` 判断要不要显示搭子头像 ——
          `AssistantAvatar` **自己就有兜底**（图框占位）。原先那个判断会漏掉
          "有内置包头像但 `avatar` 字段是空串"的出厂搭子，让它们错误地显示成
          产品 logo（用户看到的是"这个搭子没有头像"）。
        */}
        {brandOnly ? (
          brandMark
        ) : activeGroup ? (
          <GroupAvatar group={activeGroup} size={24} />
        ) : shownAssistant ? (
          <AssistantAvatar profile={shownAssistant} size={24} />
        ) : (
          // 完全没有当前主体（搭子列表还没回来）→ 产品标识
          brandMark
        )}
        <span className="text-[13px] font-semibold whitespace-nowrap text-ink">{primaryName}</span>
        {showNickname ? (
          <span
            className="max-w-[140px] truncate text-[11.5px] whitespace-nowrap text-ink-faint"
            title={`昵称：${nickname}`}
          >
            {nickname}
          </span>
        ) : null}
      </div>

      {/*
        标题栏**正中**这一格：暂时留白。

        保留这个空 div 而不是整块删掉 —— 它是三段布局的**中段**（左主体 / 中留白 /
        右状态与窗口按钮），删掉会让右侧那一组整体左移、贴着名字跑。
        将来要恢复显示，把会话标题填回来即可（取数逻辑见文件顶部的说明）。
      */}
      <div className="min-w-0 flex-1" />

      <div className="no-drag flex items-center gap-1">
        {/* 「正在工作」指示（要求 #8）：切到设置/群聊/外观之后，这是唯一能证明
            "搭子还在后台干活"的地方。没有它，用户切走再回来只能靠内容有没有变
            来判断，而"看起来没动静"和"其实已经停了"是一模一样的。

            多个会话同时跑时只报数量（"2 个搭子正在工作"）：
            逐一念名字会把这行撑爆，而用户真正需要知道的只是"还没干完"。 */}
        {runningCount > 0 ? (
          <span
            className="mr-1 hidden items-center gap-1.5 text-[11.5px] text-brand lg:flex"
            title="切到任何页面、切换搭子或对话都不会中断，可以放心去做别的事"
          >
            <span className="h-[6px] w-[6px] animate-pulse rounded-full bg-brand" />
            {runningCount > 1
              ? `${runningCount} 个搭子正在工作`
              : `${runningAssistant?.name ?? '搭子'} 正在工作`}
          </span>
        ) : null}
        {health ? (
          <span
            className="mr-1 hidden items-center gap-1.5 text-[11.5px] text-ink-faint lg:flex"
            title={`数据目录：${health.data_dir}`}
          >
            {/*
              ⚠️ 只显示一个数：**工具 + 技能，已去重**（产品要求
              "改回只显示工具数量，工具数量=工具数量+技能数量，不计算重复的"）。

              这个数就是后端 `health.skills` = `len(runtime.skills)`：
              它统计的是**全部已注册工具**，内置技能与用户上传的自定义技能
              （自定义技能的 `id` 会以同一个 `name` 命名空间注册进去）本来就
              在同一份表里，**天然不重复**。所以"加起来去重"的结果就是它本身，
              不需要在前端做任何合并运算 —— 上一版把它拆成两个数显示，反而
              逼用户自己去心算。
            */}
            <span className="h-[6px] w-[6px] rounded-full bg-success" />
            {health.skills} 个工具
          </span>
        ) : null}
        {/*
          ⚠️ 这里原先是 `theme === 'dark' ?` —— 拿**皮肤 id** 去硬比字面量 `'dark'`。
          而 `ThemeId` 是 15 个值的联合类型：默认日间皮肤是 `deepday`、默认夜间是
          `plum`，两个都不等于 `'dark'` —— 于是**永远走月亮分支**，图标恒为月亮、
          提示恒是"切换到深色主题"实测反馈就是这个）。

          改用 `isDarkTheme(theme)`：它是桥接层给出的唯一判据，`toggleTheme` 自己
          也是用它判断"现在是不是暗色"的。任何地方再写 `=== 'dark'` 都会重蹈覆辙。
        */}
        <IconButton
          label={isDarkTheme(theme) ? '切换到浅色主题' : '切换到深色主题'}
          onClick={toggleTheme}
        >
          {isDarkTheme(theme) ? <Sun size={16} /> : <Moon size={16} />}
        </IconButton>

        {/* 窗口控制按钮（最小化 / 恢复默认大小 / 最大化 / 关闭） */}
        <button
          type="button"
          aria-label="最小化"
          title="最小化"
          onClick={() => window.agentBridge?.minimizeWindow()}
          className="no-drag flex h-8 w-11 items-center justify-center rounded-[6px] text-ink-soft hover:bg-hover hover:text-ink"
        >
          <Minus size={14} />
        </button>
        {/*
          「恢复默认大小」（产品要求加在最小化与最大化之间）。

          ⚠️ 它与右边那个「最大化 / 还原」**不是一回事**，所以不能沿用那个 title：
          那个是 Windows 惯例的**反向操作**（最大化 ↔ 你刚才那档尺寸），
          这个是把窗口**复位**到出厂默认（1366 × 768）—— 用户的原话就是
          "点击后界面长宽恢复默认"。

          ⚠️ 图标用 `RotateCcw`（回转箭头）而不是"两个叠起来的方框"：后者在系统里
          表示"向下还原"（取消最大化），与右边那个按钮**撞语义**，两个图标看着还像。
          用回转箭头一眼能看出是"复位"，且不冒充系统那套。

          ⚠️ 文案里把目标尺寸写出来（1366 × 768），因为"默认"两个字对用户是黑箱 ——
          写出来他才知道点下去会变成多大，不用试。
        */}
        <button
          type="button"
          aria-label="恢复默认大小"
          title="恢复默认大小（1366 × 768）"
          onClick={() => window.agentBridge?.resetWindowSize()}
          className="no-drag flex h-8 w-11 items-center justify-center rounded-[6px] text-ink-soft hover:bg-hover hover:text-ink"
        >
          <RotateCcw size={13} />
        </button>
        <button
          type="button"
          aria-label="最大化 / 还原"
          title="最大化 / 还原"
          onClick={() => window.agentBridge?.toggleMaximizeWindow()}
          className="no-drag flex h-8 w-11 items-center justify-center rounded-[6px] text-ink-soft hover:bg-hover hover:text-ink"
        >
          <Square size={13} />
        </button>
        <button
          type="button"
          aria-label="关闭"
          title="关闭"
          onClick={() => window.agentBridge?.closeWindow()}
          className="no-drag flex h-8 w-11 items-center justify-center rounded-[6px] text-ink-soft hover:bg-danger hover:text-white"
        >
          <X size={15} />
        </button>
      </div>
    </header>
  )
}
