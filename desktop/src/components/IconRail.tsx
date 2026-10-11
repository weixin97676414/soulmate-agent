import {
  Blocks,
  CalendarDays,
  CircleUser,
  Coins,
  Cpu,
  FolderOpen,
  Mail,
  MessageSquare,
  Palette,
  Plug,
  ScrollText,
  ShieldCheck,
  Sparkles,
  Users,
  Workflow,
} from 'lucide-react'

import { FeedbackDialog, openFeedback } from '@/components/FeedbackDialog'
import { useAppStore, type ViewKey } from '@/stores/appStore'
import { useAccountStore } from '@/stores/accountStore'

interface RailItem {
  /** 「反馈」不是页面（它开弹窗），所以类型比 `ViewKey` 宽一格 */
  key: ViewKey | 'feedback'
  label: string
  icon: typeof MessageSquare
  /**
   * 本轮**隐藏入口**。
   *
   * ⚠️ 只作用于"这个按钮渲染不渲染"—— 页面组件、`ViewKey`、`App.tsx` 的
   * view→组件映射、以及语音的 `nav.*` 命令**全部保留**。用户原话是
   * "隐藏按钮，但不删除页面，用户还可以通过语音打开页面"。
   * 所以用标记而不是删数组项：以后想放出来，去掉 `hidden` 即可，
   * 不必去别处找"它原来排在哪、图标是什么"。
   */
  hidden?: boolean
  /**
   * 固定到底部（版本号那一块）—— 
   * "将关于、反馈、社区这三个按钮，从版本号那块从下往上排"。
   *
   * ⚠️ 它们**不在滚动区里**：左栏在最小窗口（660）下放不下全部按钮，列表要能滚，
   * 而这三项与版本号一起固定，滚列表时不动。
   */
  bottom?: boolean
}

/**
 * 左栏一列，从上到下（给定，**顺序不许改**）：
 *
 * 对话 → 群聊 → 模型 → 任务 → 外观 → 技能 → 消耗
 *
 * ⚠️ 又要求**隐藏 5 个入口**（产物 / 日志 / 日历 / MCP / 安全）——
 * 只从侧栏移除按钮，页面与语音入口都留着（见 `hidden` 说明）。数组项保留不删。
 *
 * ⚠️ 末尾三项（社区 / 反馈 / 关于）本轮**从滚动列表移到底部、与版本号一起固定**
 * （`bottom` 标记），屏幕上从上到下仍是 社区 → 反馈 → 关于。
 *
 * ⚠️「反馈」**必须继续特判**：它不是页面，点它是**开弹窗**，不能走 `setView`
 * （否则会切到一个不存在的 view，整页空白）。
 *
 * ⚠️ 模型 / 技能 / 消耗 这三项原先是**设置页里的二级分栏**。产品要求取消设置页、
 * 把它们提成顶级入口 —— 图标直接复用设置页那套，保证"同一个功能，前后看到的是同一个
 * 图标"。左栏 label 比原名短（模型服务商→模型、用量与费用→消耗）：56px 宽的栏里
 * 放不下长名。
 */
const ITEMS: RailItem[] = [
  { key: 'chat', label: '对话', icon: MessageSquare },
  { key: 'groups', label: '群聊', icon: Users },
  { key: 'models', label: '模型', icon: Cpu },
  // 「任务」是定时任务页（把 label 从「自动」改成「任务」：
  // "自动"两个字看不出这一页是干什么的，而且语音那边一直叫它"打开任务"，
  // 界面与说法对不上）。图标用 Workflow（流程/编排）而不是时钟：
  // 这个页面管的不只是"几点跑"，还有"什么条件下才跑"（网页有变化 / 文件有更新）。
  { key: 'tasks', label: '任务', icon: Workflow },
  { key: 'appearance', label: '外观', icon: Palette },
  { key: 'skills', label: '技能', icon: Blocks },
  { key: 'usage', label: '消耗', icon: Coins },
  // ---- 以下 5 项本轮隐藏入口（页面 / 路由 / 语音命令都保留）----
  { key: 'mcp', label: 'MCP', icon: Plug, hidden: true },
  { key: 'workspace', label: '产物', icon: FolderOpen, hidden: true },
  { key: 'calendar', label: '日历', icon: CalendarDays, hidden: true },
  { key: 'audit', label: '日志', icon: ScrollText, hidden: true },
  { key: 'preference', label: '安全', icon: ShieldCheck, hidden: true },
  // ---- 固定到底部版本号区的三项（社区 → 反馈 → 关于）----
  { key: 'benefits', label: '社区', icon: CircleUser, bottom: true },
  { key: 'feedback', label: '反馈', icon: Mail, bottom: true },
  { key: 'about', label: '关于', icon: Sparkles, bottom: true },
]

export function IconRail() {
  const view = useAppStore((state) => state.view)
  const setView = useAppStore((state) => state.setView)
  const appInfo = useAppStore((state) => state.appInfo)
  const snapshot = useAccountStore((state) => state.snapshot)

  // 「社区」上的状态点：离线或设备不可用时给个提示点，但**不拦截点击** ——
  // 用户点进去正是为了看"为什么不可用"，把入口挡住反而让人看不到原因。
  const dot = (item: { key: string }): string => {
    if (item.key !== 'benefits') return ''
    if (!snapshot) return ''
    if (!snapshot.deviceUsable) return 'bg-danger'
    if (snapshot.offline) return 'bg-warning'
    return ''
  }

  const renderItem = (item: RailItem) => {
    const Icon = item.icon
    // 「反馈」不参与选中判断：它开的是弹窗，不存在"当前正停在这一页"
    const active = item.key !== 'feedback' && view === item.key
    const statusDot = dot(item)
    return (
      <button
        key={item.key}
        type="button"
        title={item.label}
        aria-label={item.label}
        // 「当前停在哪个页面」不要只靠那块淡底高亮传达 —— 屏幕阅读器读不出来。
        // 这是标准属性，不需要额外样式配合。
        aria-current={active ? 'page' : undefined}
        onClick={() => {
          if (item.key === 'feedback') {
            openFeedback()
            return
          }
          setView(item.key)
        }}
        // 项高 44 → 40 → **36**（`h-9`）：栏宽收到 40 之后，40px 的方块会把整栏顶满
        // （圆角块贴到边上），所以再让出 2px 边距。36px 仍是能点准的目标，
        // 而且文字标签保留 —— 用户是靠它认路的。
        className={`no-drag relative flex h-9 w-9 shrink-0 flex-col items-center justify-center gap-0.5 rounded-[10px] transition-colors ${
          active ? 'bg-brand-soft text-brand' : 'text-ink-soft hover:bg-hover hover:text-ink'
        }`}
      >
        {statusDot ? (
          <span
            className={`absolute right-1 top-1 h-1.5 w-1.5 rounded-full ${statusDot}`}
            aria-hidden
          />
        ) : null}
        <Icon size={17} />
        {/*
          ⚠️ 字间距**还原**：加过一版 `tracking-[0.1em]`，
          用户看过后要求还原 —— 两个字的标签在这个宽度里本来就紧，拉开之后
          反而不像一个整体了。

          别再自作主张给这行加字间距：这一栏是"图标墙"，文字是认路的辅助，
          不是用来读的正文。
        */}
        <span className="text-[10px] leading-none">{item.label}</span>
      </button>
    )
  }

  // 栏宽 40px，与标题栏高度（`TitleBar` 的 `h-10`）**相等**：
  // 左上角那一格的横竖两条边一样长，看起来才是一个规整的角。
  // 收窄历程：栏 56 → 44 → **40**、标题栏 48 → 44 → **40**（最后一档是用户说
  // "标题栏还可以再收窄一点"——因为两者必须相等，所以栏也跟着一起收）。
  //
  // 滚动区只放"可滚动项"（去掉 `hidden` 与 `bottom`）；底部三项单独渲染在版本号上方，
  // 与版本号一起固定，滚列表时不动（见 `bottom` 的说明）。
  const visibleItems = ITEMS.filter((item) => !item.hidden && !item.bottom)
  const bottomItems = ITEMS.filter((item) => item.bottom)

  return (
    <nav className="flex w-10 shrink-0 flex-col items-center gap-2 bg-canvas pb-2">
      {/*
        ⚠️ 滚动区现在是 **7 项**（隐藏了 5 个入口、又移走了底部 3 项）。按每项 40px +
        2px 间距算约 294px：常规窗口绰绰有余，但**最小窗口（660）仍要留出底部那三项 +
        版本号的高度** —— 所以列表自己滚（`overflow-y-auto` + `min-h-0`），
        底部三项与版本号始终可见。

        滚动条在 40px 宽的栏里太占地方，直接隐藏（`scrollbar-width` + webkit 伪元素）：
        这一列本来就该是一面"图标墙"，不该被一根滑块从中间切开。
      */}
      <div className="flex min-h-0 w-full flex-1 flex-col items-center gap-2 overflow-y-auto [scrollbar-width:none] [&::-webkit-scrollbar]:hidden">
        {visibleItems.map(renderItem)}
      </div>

      {/*
        底部固定三项（屏幕上从上到下：社区 → 反馈 → 关于，）。
        ⚠️ 这一组在滚动容器**之外** —— 放进滚动区它会跟着上面那列一起滚，
        而用户要的是"从版本号那块"固定住。
      */}
      <div className="flex flex-col items-center gap-2">
        {bottomItems.map(renderItem)}
      </div>

      <div className="pb-1 text-center text-[10px] leading-tight text-ink-faint">
        v{appInfo?.version ?? '0.0.1'}
      </div>

      {/* 反馈是弹窗（见 FeedbackDialog）：挂在这里是因为导航栏在主窗口里始终存在 */}
      <FeedbackDialog />
    </nav>
  )
}
