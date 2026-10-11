import {
  THEME_IDS,
  isDarkTheme,
  type AppInfo,
  type BackendInfo,
  type BackendStatus,
  type CloseAction,
  type ThemeId,
} from '@shared/bridge'
import { create } from 'zustand'

import { AgentApi } from '@/services/api'
// ⚠️ 与 modelHubStore 是**循环引用**（它要 `useAppStore.getState()` 拿 api）。
// 安全的前提是两边都**只在函数里**取对方的 store，不在模块顶层调用 ——
// 这里与 `notificationStore` 那条循环是同一个形态。
import { useModelHubStore } from '@/stores/modelHubStore'
import { useNotificationStore } from '@/stores/notificationStore'
import type {
  AppSettings,
  BackendHealth,
  ModelInfo,
  PathsInfo,
  ProviderPreset,
  SkillInfo,
} from '@/types'

/**
 * 顶级页面。**顺序与左栏从上到下一致**（给定）：
 * 对话 → 群聊 → 模型 → 自动 → 外观 → 技能 → MCP → 产物 → 消耗 → 日历 → 日志 → 安全
 * → 社区 → 关于（末尾还有「反馈」，它不是页面而是弹窗，所以不在这个枚举里）。
 *
 * ⚠️ ：原先这里只有 `'settings'` 一个值，设置页内部再用一套 tab 做二级导航。
 * 产品要求把设置里的八栏**提到左栏当顶级页**并取消设置页 —— 于是 `'settings'` 删除、
 * 八个分栏各自成为一个 view。
 *
 * 这不只是"少点一层"：左栏是**平铺**的，扫一眼就知道应用有哪几块；
 * 而藏在二级 tab 里的那七块，实际上只有真的进过设置页的人才知道存在。
 */
export type ViewKey =
  | 'chat'
  | 'groups'
  | 'models'
  // 定时任务（左栏叫「自动」）：独立一页（产品要求）——它要管的不只是"什么时候跑"，
  // 还有"该不该跑"，塞进设置的某个折叠区里没人找得到
  | 'tasks'
  | 'appearance'
  | 'skills'
  | 'mcp'
  | 'workspace'
  | 'usage'
  | 'calendar'
  | 'audit'
  | 'preference'
  | 'benefits'
  | 'about'

const THEME_STORAGE_KEY = 'agent-desktop:theme'
const WALLPAPER_STORAGE_KEY = 'agent-desktop:wallpaper'

/**
 * 通信桥不存在时的提示。
 *
 * 抽成常量是因为 `bootstrap` 与 `restartBackend` 两条路径都会遇到它，
 * 而两处文案必须一致 —— 否则用户点「重新启动」后会看到一个措辞不同的错误，
 * 会误以为那是另一个问题。
 */
const BRIDGE_MISSING_MESSAGE =
  '界面与主程序之间的通信桥未建立（预加载脚本未生效）。' +
  '这通常是安装包损坏或版本不匹配导致的，与 Python 环境无关，请重新安装客户端。'

/**
 * system 之外的取值就是成品皮肤；system 要按系统偏好折算成 light/dark。
 *
 * ⚠️ 第 91 批（L-02）起对外导出：设置页也要用它来回答"**当前**是哪一套皮肤"。
 * 不导出的话那边只能自己再判一次 `theme === 'system'`（第二份实现，迟早长歪）。
 */
export function resolveTheme(theme: ThemeId): Exclude<ThemeId, 'system'> {
  if (theme !== 'system') return theme
  const prefersDark = window.matchMedia?.('(prefers-color-scheme: dark)')?.matches
  return prefersDark ? 'dark' : 'light'
}

/** 用户**显式**选过主题的标记。
 *
 * ⚠️ 这个标记是必需的，不能靠"localStorage 里有没有值"来判断 —— 因为
 * **旧版的出厂默认值也是被我们写进 localStorage 的**，它和"用户自己选的"
 * 长得一模一样。没有标记就分不清这两者，于是改了出厂默认之后：
 * 老用户永远看不到新默认（他那里已经写着上一版的默认值了）。
 *
 * 这正是本次踩的坑：出厂默认从 `sakura` 改成 `plum` 之后，界面上还是樱粉 ——
 * 不是代码没生效，而是 `readStoredTheme` 读到了上一版帮用户写下的 `sakura`。
 */
const THEME_CHOSEN_KEY = 'agent-desktop:theme-chosen'

/**
 * 历史出厂默认值。**改出厂默认时把旧的加进来。**
 *
 * 判据是"值和旧默认**完全相同**，且用户没有显式选过的标记" → 视同没选过，
 * 用新默认。只按值判断会误伤"真的就想要樱粉"的人，所以必须配合
 * `THEME_CHOSEN_KEY`：他重选一次就会被打上标记，之后不再被迁移。
 */
const LEGACY_DEFAULT_THEMES: readonly ThemeId[] = ['sakura', 'dark', 'plum']

/** 这个存储值该不该被当成"用户的选择"。 */
function isUserChoice(stored: string | null): stored is string {
  if (!stored) return false
  if (!THEME_IDS.includes(stored as ThemeId)) return false
  // 有显式标记 → 一定是用户选的
  if (localStorage.getItem(THEME_CHOSEN_KEY) === '1') return true
  // 没有标记：只有"不是历史出厂默认值"才算用户选的
  return !LEGACY_DEFAULT_THEMES.includes(stored as ThemeId)
}

function readStoredTheme(): ThemeId {
  const stored = localStorage.getItem(THEME_STORAGE_KEY)
  if (stored === 'system' || isUserChoice(stored)) {
    return stored as ThemeId
  }
  // 出厂主题 = 晨蓝（从暮紫改为晨蓝）。
  // 只对"从没选过主题"的人生效 —— 已经选过的老用户保留自己的选择。
  //
  // ⚠️ 它与下面的 ``DAY_DEFAULT`` 是同一个值，改一个要想着另一个：
  // 出厂状态下右上角那个切换按钮是在"晨蓝 ↔ 暮紫"之间走，而首启看到的是晨蓝。
  //
  // ⚠️ 上一版出厂默认 `plum`（暮紫）已登记进 ``LEGACY_DEFAULT_THEMES`` ——
  // 老用户 localStorage 里那条 `plum` 是上一版**我们替他写下的**、不是他的选择，
  // 所以这次会一起被迁移到晨蓝；真的手选过暮紫的人带着 `THEME_CHOSEN_KEY` 标记，不受影响。
  return DAY_DEFAULT
}

// ---- 日间 / 夜间皮肤槽位（产品要求）-------------------------------- //
// 用户可以分别为日间、夜间选一套皮肤并记住；右上角的切换按钮只在这两个
// 槽位之间切换。没设置过的槽位用出厂默认。
const DAY_THEME_KEY = 'agent-desktop:theme-day'
const NIGHT_THEME_KEY = 'agent-desktop:theme-night'
/**
 * 出厂默认：**日间晨蓝、夜间暮紫**（产品要求）。
 *
 * 挑这两套的理由是它们**同一族**：晨蓝是通透的蓝白、暮紫是低饱和深紫，
 * 品牌色也接近（`#4d6bfe` / `#a78bfa`），所以日夜切换时是"同一套设计换了个
 * 明度"，而不是"换了一个应用"。混搭（比如日间薄荷、夜间炭黑）也能用，
 * 但第一印象会散。
 *
 * ⚠️ 这两个值同时是"从没设置过的用户看到什么"和"出厂主题"（见 ``readStoredTheme``）。
 */
const DAY_DEFAULT: Exclude<ThemeId, 'system'> = 'deepday'
const NIGHT_DEFAULT: Exclude<ThemeId, 'system'> = 'plum'

function readSlot(key: string, fallback: Exclude<ThemeId, 'system'>): Exclude<ThemeId, 'system'> {
  const stored = localStorage.getItem(key)
  // ⚠️ 走和主主题同一套判断（含历史默认值迁移）：槽位里存着上一版出厂默认值
  // 的情况和 `THEME_STORAGE_KEY` 完全一样，用不同判据会让"日/夜切换"与
  // "当前主题"对不上 —— 表现为按一下切换按钮，皮肤跳到一个意想不到的地方。
  if (stored && stored !== 'system' && isUserChoice(stored)) {
    return stored as Exclude<ThemeId, 'system'>
  }
  return fallback
}

export function readDayNightThemes(): {
  day: Exclude<ThemeId, 'system'>
  night: Exclude<ThemeId, 'system'>
} {
  return {
    day: readSlot(DAY_THEME_KEY, DAY_DEFAULT),
    night: readSlot(NIGHT_THEME_KEY, NIGHT_DEFAULT),
  }
}

function writeSlot(key: string, theme: ThemeId): void {
  // system 不能当槽位值（槽位要的是一套具体皮肤）
  if (theme === 'system') return
  localStorage.setItem(key, theme)
}

/**
 * 壁纸（data URL）挂到根元素上，由 CSS 统一消费。
 *
 * 存成 **data URL** 而不是文件路径：打包后页面走 ``file://``，本地路径在
 * CSP 下不一定能当图片加载（``img-src 'self'`` 对 file:// 的行为是实现细节），
 * 而 ``data:`` 是明确允许的。
 */
function applyWallpaper(dataUrl: string | null): void {
  const root = document.documentElement
  if (!dataUrl) {
    root.style.removeProperty('--app-wallpaper')
    delete root.dataset.wallpaper
    return
  }
  // 去掉可能的引号与换行：它们会让 url() 提前闭合，表现为壁纸不显示且无报错
  const safe = dataUrl.replace(/["'\r\n]/g, '')
  root.style.setProperty('--app-wallpaper', `url("${safe}")`)
  root.dataset.wallpaper = 'on'
}

function readStoredWallpaper(): string | null {
  return localStorage.getItem(WALLPAPER_STORAGE_KEY)
}

function applyTheme(theme: ThemeId): void {
  const resolved = resolveTheme(theme)
  // 皮肤靠 data-theme 切换（见 src/index.css）
  document.documentElement.dataset.theme = resolved
  // 同时保留 .dark 这个 class：老的深/浅判断与自定义 variant 还在读它
  document.documentElement.classList.toggle('dark', isDarkTheme(resolved))
  // 窗口按钮是系统原生的，需要单独通知主进程换配色
  window.agentBridge?.setTitleBarTheme(resolved)
  localStorage.setItem(THEME_STORAGE_KEY, theme)
  syncThemeColorMeta()
}

/**
 * 把 `<meta name="theme-color">` 同步成当前皮肤的**画布实底色**（第 90 批，M-37）。
 *
 * ⚠️ 为什么不在这里写死一棵色表：14 套皮肤底色各不相同，写死只对其中一套正确，
 * 而且立刻多出第二处颜色来源（改皮肤要记得同步它 —— 本项目已经在
 * 「画布色要动三处」上栽过一次）。读 CSS 变量拿到的值**永远与皮肤一致**：
 * 色值仍然只有 `index.css` 一份，这条只是把它转发出去。
 *
 * ⚠️ 必须在 `dataset.theme` **之后**调用：`getComputedStyle` 会强制样式重算，
 * 拿到的就是新皮肤的值。读不到（没有 meta / 变量没定义）时安静返回 ——
 * 一个纯装饰性的元信息不值得让主题切换失败。
 */
function syncThemeColorMeta(): void {
  const meta = document.querySelector('meta[name="theme-color"]')
  if (!meta) return
  const canvas = getComputedStyle(document.documentElement)
    .getPropertyValue('--app-canvas-solid')
    .trim()
  if (canvas) meta.setAttribute('content', canvas)
}

interface AppState {
  api: AgentApi | null
  backendInfo: BackendInfo | null
  backendStatus: BackendStatus
  appInfo: AppInfo | null
  health: BackendHealth | null

  models: ModelInfo[]
  modelDefaults: { defaultModel: string; effectiveDefault: string }
  presets: ProviderPreset[]
  skills: SkillInfo[]
  settings: AppSettings | null
  paths: PathsInfo | null

  theme: ThemeId
  /** 壁纸（data URL）。刻意**不**走后端配置：它可能有几百 KB，会撑大 settings.json */
  wallpaper: string | null
  /**
   * 点关闭按钮时的行为。
   *
   * **真相在主进程侧**（`desktop-prefs.json`）：用户点 × 的那一刻，渲染层可能
   * 已经卡住、甚至已经销毁，只有主进程能可靠地读到这个选择。这里存的是给设置页
   * 显示用的副本，改动通过 `setCloseAction` 写回主进程。
   */
  closeAction: CloseAction
  view: ViewKey
  bootstrapping: boolean
  bootstrapError: string | null
  /**
   * 首启向导是否**正在展示** —— 这是"要不要显示向导"的**唯一开关**。
   *
   * ## 判据（产品约定）
   *
   * **三项任一没完成就进**：① 语音模型装了 ② 长期记忆模型装了 ③ 有一个可用服务商。
   * 三项齐了就**直接进主界面**。判据本身写在 `needsOnboarding()` 里（只有一处）。
   *
   * ⚠️ 这里**不再用 localStorage 标记决定**（`agent-desktop:onboarded` 已删除）：
   * 那个标记记的是"上次的判断结果"，而模型可能被删掉、密钥可能被清掉 ——
   * 拿旧标记直接放行的后果是"用户掉进发消息没反应的空界面"，
   * 而那正是首启向导要解决的问题。现在每次握手都按**实时状态**重算。
   *
   * ⚠️ 但**同一会话内只置真、不置假**（见 `handshake(first)`）：
   * 向导里保存完服务商、或者恰好撞上核心重启，都不许让向导自己消失。
   * 退出只有两条路：三项齐了（实时状态说了算）或用户点了底部的「开始」。
   */
  onboardingActive: boolean

  bootstrap: () => Promise<void>
  restartBackend: () => Promise<void>
  reloadHealth: () => Promise<void>
  reloadModels: () => Promise<void>
  reloadSkills: () => Promise<void>
  reloadSettings: () => Promise<void>
  reloadPaths: () => Promise<void>
  setView: (view: ViewKey) => void
  toggleTheme: () => void
  /** 换皮肤（传 null 表示取消壁纸） */
  setTheme: (theme: ThemeId) => void
  setWallpaper: (dataUrl: string | null) => void
  /** 修改「点关闭按钮时」的行为；写入主进程侧偏好 */
  setCloseAction: (action: CloseAction) => void
  dismissOnboarding: () => void
}

/**
 * 有没有一个「真正能用」的服务商。
 *
 * 判据是「有没有一个真正能用的模型」，而不是「有没有模型」——配置里可能留着
 * 本地 Ollama 那条（它不需要 Key，has_api_key 却可能被填成占位串），
 * 光看 has_api_key 会把它当成已配置，于是新用户永远看不到引导、
 * 直接撞上"模型不可用"。所以 ollama 类服务商一律不算。
 */
export function hasUsableProvider(models: ModelInfo[]): boolean {
  return models.some(
    (model) => model.enabled && model.provider !== 'ollama' && model.has_api_key,
  )
}

/**
 * 启动时该不该进首启向导。**判据是三项**（产品约定）：
 * ① 语音模型装了 ② 长期记忆模型装了 ③ 有一个可用服务商 —— **任一没完成就进**。
 * 三项齐了直接进主界面（"只有未安装才需要在再次启动应用时开启导航页"）。
 *
 * 为什么把两个本地模型也算进来：它们在 起改为**按需下载**
 * （不再随安装包分发）。用户装好了模型、也配好了服务商，就不该再被向导拦一次；
 * 反过来，只要还有模型没装，向导就该出现 —— 因为那是唯一的下载入口。
 *
 * ⚠️ **状态拿不到时不算"缺"**：`hub` 里没有这条 = 请求失败或还没取到，
 * 一次网络抖动不该把用户弹回向导页（他会以为自己的模型丢了）。
 */
export function needsOnboarding(
  models: ModelInfo[],
  hub: Record<string, { installed: boolean } | undefined>,
): boolean {
  if (!hasUsableProvider(models)) return true
  const voiceMissing = Boolean(hub.voice && !hub.voice.installed)
  const memoryMissing = Boolean(hub.embedding && !hub.embedding.installed)
  return voiceMissing || memoryMissing
}

let bootstrapStarted = false
// 重新握手的重入保护：后端重启会连发多个状态事件
let rehandshaking = false

/**
 * 完成一次握手：用新的 BackendInfo 重建 api，并刷新依赖它的数据。
 *
 * **为什么必须重建而不是只改状态文字**：后端每次重启都会换端口和令牌
 * （启动参数是 `--port 0`，令牌每次随机生成），而 `AgentApi` 在构造时就把
 * `baseUrl`/`token` 固定下来了。只改状态的话，界面显示「智能体核心已就绪」，
 * 但所有请求仍打向旧端口、带旧令牌，事件长连接也会对着死地址静默重试。
 * 这是最危险的一类缺陷：**用户以为一切正常**。
 */
async function handshake(
  set: (partial: Partial<AppState>) => void,
  get: () => AppState,
  info: BackendInfo,
  first = false,
): Promise<void> {
  set({ api: AgentApi.from(info), backendInfo: info })
  // ⚠️ 模型清单是**判据与界面都要用**的关键数据，所以它拉了才算握手成功：
  // 拉不到时既不能拿空清单去猜"用户是不是还没配服务商"（会把人误弹进首启向导），
  // 也不该假装一切正常 —— 让它照旧走启动失败页（那页有「重新启动」）。
  await get().reloadModels()
  // ⚠️ 下面这几项**不是**一个事务：各自是独立的数据拉取，任何一项失败都不该把整个应用
  // 钉在"启动失败"页（`bootstrapError` 一置上，用户只能手动点「重新启动」，而错误文案
  // 还指向一堆不相干的原因）。以前这里是 `Promise.all`，于是"核心刚起来、某个接口抖
  // 一下"这个窗口必然表现为启动失败 —— 用户的说法会是"双击之后很久进不去，
  // 重启几次又好了"。
  // 失败的那项**补一次重试**；仍然失败就只记日志：这几项在各自页面里都还有入口能
  // 重新拉（技能页的「重新加载」、设置页保存后、MCP 变更事件等）。
  const secondaryReloads: Array<[string, () => Promise<void>]> = [
    ['技能列表', () => get().reloadSkills()],
    ['设置', () => get().reloadSettings()],
    ['路径', () => get().reloadPaths()],
    ['健康检查', () => get().reloadHealth()],
  ]
  const firstPass = await Promise.allSettled(secondaryReloads.map(([, run]) => run()))
  const retried = await Promise.allSettled(
    firstPass.flatMap((outcome, index) =>
      outcome.status === 'rejected' ? [secondaryReloads[index][1]()] : [],
    ),
  )
  for (const outcome of retried) {
    if (outcome.status === 'rejected') {
      console.error(
        '[desktop] 启动时有一项数据没能拉取（已重试过一次），进页面后可手动刷新：',
        outcome.reason,
      )
    }
  }
  // ⚠️ 本地模型的状态也要先取到 —— 向导的判据里含"语音 / 长期记忆装了没"
  // （见 `needsOnboarding`）。原先这一步只在 `ModelDownloadCard` 挂载时做，
  // 于是"启动时该不该进向导"根本没有依据（这正是 那个
  // "明明装好了又被拦一次"的原因之一）。
  // 它拉不到时按"没这两项"处理（`needsOnboarding` 只认显式的 `installed === false`），
  // 也就是**不会**因此把用户拦进向导 —— 这是刻意的：宁可少拦一次，也别误弹。
  try {
    await useModelHubStore.getState().refresh()
  } catch (error) {
    console.error('[desktop] 本地模型状态拉取失败，本次按"未安装"处理：', error)
  }

  if (!needsOnboarding(get().models, useModelHubStore.getState().models)) {
    // 三项齐了 ⇒ 直接进主界面。这里**是允许置假的**：实时状态说了算，
    // 没有东西要装、服务商也能用，再拦着用户没有任何意义。
    set({ onboardingActive: false })
    return
  }
  // 还缺东西：**只在首次握手时赋值，之后只置真不置假**。
  // · 首次（bootstrap）：按实况决定要不要进向导；
  // · 之后（核心重启 / 用户点「重新启动」）：向导已经开着就继续开着 ——
  //   用户在向导里保存完服务商之后，绝不能因为一次重握手就把它关掉，
  //   那样后面的模型下载入口就没了。
  if (first || get().onboardingActive) {
    set({ onboardingActive: true })
  }
}

/** 状态回到 ready 时重新握手（幂等：令牌没变就直接返回）。 */
async function rehandshake(
  set: (partial: Partial<AppState>) => void,
  get: () => AppState,
): Promise<void> {
  if (rehandshaking) return
  rehandshaking = true
  try {
    const info = await window.agentBridge.getBackendInfo()
    const current = get().backendInfo
    // 令牌没变说明已经握手过了。手动「重新启动」按钮也会触发状态事件，
    // 这个判断避免同一轮重启刷两遍数据。
    if (current && current.token === info.token) return
    await handshake(set, get, info)
  } catch {
    // 重新握手失败不打回启动页：保留现有界面，
    // 用户下次操作会自然重试，而不是被弹回一个空白的启动屏。
  } finally {
    rehandshaking = false
  }
}

/** 注册后端状态订阅（含自动重新握手）。 */
function watchBackendStatus(
  set: (partial: Partial<AppState>) => void,
  get: () => AppState,
): void {
  // 用可选链：preload 注入失败时这里会**同步抛错**，把 bootstrap 变成
  // rejected promise，bootstrapping 永远停在 true —— 界面卡在启动页且毫无提示。
  window.agentBridge?.onBackendStatus((status) => {
    const previous = get().backendStatus.state
    set({ backendStatus: status })

    // 只在「非 ready → ready」这一次跳变上重新握手
    if (status.state !== 'ready' || previous === 'ready') return
    // 首次启动由 bootstrap 自己负责，这里避免重复
    if (!get().api) return
    void rehandshake(set, get)
  })
}

export const useAppStore = create<AppState>((set, get) => ({
  api: null,
  backendInfo: null,
  backendStatus: { state: 'starting', message: '正在启动智能体核心…' },
  appInfo: null,
  health: null,

  models: [],
  modelDefaults: { defaultModel: '', effectiveDefault: '' },
  presets: [],
  skills: [],
  settings: null,
  paths: null,
  // 进向导的判定在 `handshake()` 里做（那时模型清单与本地模型状态才拉回来）——
  // 在这里算的话两边都还是空的，会先闪一下向导再消失。
  onboardingActive: false,

  theme: readStoredTheme(),
  wallpaper: readStoredWallpaper(),
  // 默认"每次询问"，启动时会被主进程里记住的值覆盖。
  // 兜底取 ask（而不是 tray/quit）是为了不替用户拿主意。
  closeAction: 'ask',
  view: 'chat',
  bootstrapping: true,
  bootstrapError: null,

  // ------------------------------------------------------------------ //
  // 启动
  // ------------------------------------------------------------------ //
  bootstrap: async () => {
    // React 严格模式下 effect 会执行两次，这里做幂等保护
    if (bootstrapStarted) return
    bootstrapStarted = true

    // 桥不存在时**先**给出准确原因，别让它以 TypeError 的形式冒出来。
    //
    // preload 注入失败会让 window.agentBridge 整个不存在，之后每个 IPC 调用
    // 都变成 "Cannot read properties of undefined (reading 'xxx')"。错误面板
    // 原先据此把原因猜成「Python 依赖未安装」，把排查方向带到了一个与故障
    // 毫无关系的地方（真实原因是打包出来的 preload 没能注入）。
    if (!window.agentBridge) {
      set({
        bootstrapping: false,
        bootstrapError: BRIDGE_MISSING_MESSAGE,
        backendStatus: { state: 'failed', message: BRIDGE_MISSING_MESSAGE },
      })
      return
    }

    applyTheme(get().theme)
    applyWallpaper(get().wallpaper)
    watchBackendStatus(set, get)

    // 读主进程侧记住的关闭行为。
    // **刻意不 await**：它只决定设置页里那个选项的初始选中状态，拿不到就用默认值
    // —— 真正关窗时主进程用的是自己那份，不依赖界面。为它拖慢启动不值得。
    window.agentBridge
      .getDesktopPrefs()
      .then((prefs) => set({ closeAction: prefs.closeAction }))
      .catch(() => undefined)

    try {
      const [info, appInfo] = await Promise.all([
        window.agentBridge.getBackendInfo(),
        window.agentBridge.getAppInfo(),
      ])
      set({ appInfo })
      // `true` = 本次启动的**首次**握手：向导要不要显示由它按下得出（见 `handshake`）
      await handshake(set, get, info, true)

      set({
        bootstrapping: false,
        backendStatus: { state: 'ready', message: '智能体核心已就绪' },
      })
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error)
      set({
        bootstrapping: false,
        bootstrapError: message,
        backendStatus: { state: 'failed', message },
      })
    }
  },

  restartBackend: async () => {
    set({ bootstrapping: true, bootstrapError: null })
    // 同上：桥不存在时重试多少次都不会成功，直接说清楚，
    // 而不是再抛一次看不懂的 TypeError
    if (!window.agentBridge) {
      set({ bootstrapping: false, bootstrapError: BRIDGE_MISSING_MESSAGE })
      return
    }
    try {
      const info = await window.agentBridge.restartBackend()
      await handshake(set, get, info)
      set({
        bootstrapping: false,
        backendStatus: { state: 'ready', message: '智能体核心已就绪' },
      })
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error)
      set({ bootstrapping: false, bootstrapError: message })
    }
  },

  reloadHealth: async () => {
    const api = get().api
    if (!api) return
    try {
      set({ health: await api.health() })
    } catch {
      // 健康检查失败不阻断启动流程
    }
  },

  reloadModels: async () => {
    const api = get().api
    if (!api) return
    const payload = await api.getModels()
    set({
      models: payload.models,
      modelDefaults: {
        defaultModel: payload.default_model,
        effectiveDefault: payload.effective_default,
      },
      presets: payload.presets ?? [],
    })
  },

  reloadSkills: async () => {
    const api = get().api
    if (!api) return
    const payload = await api.getSkills()
    set({ skills: payload.skills })
  },

  reloadSettings: async () => {
    const api = get().api
    if (!api) return
    set({ settings: await api.getSettings() })
  },

  reloadPaths: async () => {
    const api = get().api
    if (!api) return
    set({ paths: await api.getPaths() })
  },

  // ------------------------------------------------------------------ //
  // 界面状态
  // ------------------------------------------------------------------ //
  setView: (view) => set({ view }),

  toggleTheme: () => {
    // **在用户设置的日间/夜间皮肤之间切换**（而不是切回固定的 light/dark ——
    // 那会覆盖用户自己选的皮肤，是用户明确抱怨过的行为）
    const { day, night } = readDayNightThemes()
    const next = isDarkTheme(get().theme) ? day : night
    applyTheme(next)
    set({ theme: next })
    // 点了切换按钮同样是"用户的选择"，要打标记 —— 否则下次启动时它可能被
    // 当成"上一版遗留的出厂默认值"迁移掉（比如切到了 `dark`，而 `dark`
    // 正好在 `LEGACY_DEFAULT_THEMES` 里）。槽位由 `applyTheme` 之外的流程维护，
    // 这里只需要标记。
    localStorage.setItem(THEME_CHOSEN_KEY, '1')
  },

  setTheme: (theme) => {
    applyTheme(theme)
    set({ theme })
    // 用户明确选了一套皮肤 → 记进对应的日/夜槽位，之后右上角切换就在
    // 这两套之间走
    if (theme !== 'system') {
      writeSlot(isDarkTheme(theme) ? NIGHT_THEME_KEY : DAY_THEME_KEY, theme)
      // ⚠️ 同时打上"用户选过"的标记（见 THEME_CHOSEN_KEY）：没有它，
      // 用户重新选回樱粉也会被当成"上一版遗留的出厂默认值"而在下次启动被迁移掉
      // —— 他会遇到"设了没用、重启又变回去"这种最难解释的现象。
      localStorage.setItem(THEME_CHOSEN_KEY, '1')
    }
  },

  setWallpaper: (dataUrl) => {
    applyWallpaper(dataUrl)
    if (dataUrl) {
      localStorage.setItem(WALLPAPER_STORAGE_KEY, dataUrl)
    } else {
      localStorage.removeItem(WALLPAPER_STORAGE_KEY)
    }
    set({ wallpaper: dataUrl })
  },

  setCloseAction: (action) => {
    // 先改界面再落盘：写失败概率极低（主进程只是写个小 JSON），
    // 而且真失败也没什么后果 —— 下次打开看到旧值而已。
    set({ closeAction: action })

    const bridge = window.agentBridge
    if (!bridge) return
    bridge.setDesktopPrefs({ closeAction: action }).catch(() => {
      // 但**必须**告诉用户没记住，否则他会以为"选了却不生效"却不知道为什么
      useNotificationStore.getState().push({
        level: 'warning',
        title: '设置未能保存',
        message: '关闭行为已在本次运行中生效，但可能不会被记住。',
      })
    })
  },

  dismissOnboarding: () => {
    // 用户点了底部那个「开始」（只有三项齐了才可点）⇒ 进主界面。
    // ⚠️ 这里**不写任何持久化标记**（`agent-desktop:onboarded` 已删）：
    // 下次启动该不该进向导，由 `handshake` 按**实时状态**（`needsOnboarding`）重算。
    // 产品明确要求过：跳过 ≠ 配置完成，跳过的下次启动还要再提醒一次；
    // 而真的装好了、配好了，就不该再拦他 —— 两件事都由实时状态自然区分。
    set({ onboardingActive: false })
  },
}))

// 供非组件代码（如 store 内部）调用
export function getApi(): AgentApi {
  const api = useAppStore.getState().api
  if (!api) throw new Error('后端尚未就绪，请稍候重试。')
  return api
}
