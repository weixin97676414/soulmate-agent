/**
 * Electron 主进程。
 *
 * 负责：窗口生命周期、Python 后端进程守护、IPC 服务、安全策略。
 * 业务逻辑一律不放这里 —— 它只做「壳」。
 */
import {
  BrowserWindow,
  Menu,
  Tray,
  app,
  dialog,
  ipcMain,
  nativeImage,
  screen,
  session,
  shell,
  type WebContents,
} from 'electron'
import fs from 'node:fs'
import path from 'node:path'

import {
  IPC,
  type AccountSnapshot,
  type AppInfo,
  type BackendStatus,
  type CloseAction,
  type ClosePromptAnswer,
  type DesktopPrefs,
  type RevealTarget,
  type SaveArtifactRequest,
  type SaveArtifactResult,
  type SecretsPatch,
  type SecretsPayload,
  type SkillSecretsPatch,
  type SkillSecretsView,
  type WindowTheme,
} from '../shared/bridge'
import { AccountEngine } from './account/engine'
import { BackendManager, coreFetch } from './backend'
import { logDesktop } from './desktop-log'
import { SecretsStore, emptySecrets } from './secrets'
import { SkillSecretsStore } from './skill-secrets'

// --------------------------------------------------------------------------- //
// openPath 的入参约束
// --------------------------------------------------------------------------- //
// Windows 上 ``shell.openPath`` 走的是 **ShellExecute 语义**：
// 任何文件都会按它的默认关联程序**执行**。也就是说传一个 ``.exe`` / ``.bat`` /
// ``.ps1`` / ``.lnk`` 进去，就等于把它直接跑起来。
//
// 于是这个 handler 是一个完整的「任意程序执行」原语，而它对渲染层只暴露了
// 一个字符串参数 —— 只要渲染层能控制这个字符串（一处 XSS、或被污染的后端响应
// 里夹了一个路径），攻击者就能在本机执行任意程序，且不写入任何自己的文件。
//
// 应用目前**只**用它打开目录（工作区 / 产物 / 数据 / 日志，见
// ``WorkspaceSettings.tsx`` 与 ``SettingsView.tsx``）。但为了不给将来留下坑，
// 这里采取「目录照放、文件挡掉可执行与脚本类型」，而不是一刀切只许目录。
const NON_OPENABLE_EXTENSIONS = new Set([
  // 可执行
  '.exe', '.com', '.bat', '.cmd', '.msi', '.scr', '.pif', '.gadget',
  // 会被默认关联的解释器直接跑起来的脚本
  '.ps1', '.psm1', '.psd1', '.vbs', '.vbe', '.js', '.jse', '.wsf', '.wsh',
  '.hta', '.jar', '.py', '.pyw', '.rb', '.pl', '.sh', '.bash', '.zsh', '.command',
  // 快捷方式 / 链接：自身不含代码，但会指向任意目标并携带目标的参数，
  // 等于把这里的扩展名检查全部绕过去 —— 所以必须一起挡掉
  '.lnk', '.url', '.appref-ms', '.library-ms', '.search-ms', '.website',
  // 写系统配置或挂载为卷
  '.reg', '.inf', '.iso', '.vhd', '.vhdx', '.wim', '.msix', '.appx',
  // 二进制模块：不会被"打开"，放行也没有任何意义
  '.dll', '.sys', '.drv', '.ocx', '.efi',
])

/**
 * 判断一个目标能不能交给 ``shell.openPath``。
 *
 * 判据是「先确认它到底是什么」，而不是「看它长什么样」：
 * ``fs.statSync`` 拿不到就说明路径不存在或不可访问，直接拒绝；
 * 目录没有"按关联程序执行"的语义，天然安全；只有落到**普通文件**上才去看扩展名。
 */
function isOpenableTarget(target: unknown): target is string {
  if (typeof target !== 'string' || target.trim() === '') return false
  // 必须是绝对路径。相对路径会被 ShellExecute 按**当前工作目录**解析，
  // 而 Electron 的 cwd 在不同启动方式下并不一致（包括安装目录），
  // 这让同名的可执行文件有机会被意外选中。
  if (!path.isAbsolute(target)) return false

  let stat: fs.Stats
  try {
    // 不用 lstat：符号链接指向的东西才是真正会被执行的那个，要看它
    stat = fs.statSync(target)
  } catch {
    return false // 不存在或无权访问
  }

  if (stat.isDirectory()) return true
  if (!stat.isFile()) return false // 设备等非常规文件，一律不猜

  const ext = path.extname(target).toLowerCase()
  return !NON_OPENABLE_EXTENSIONS.has(ext)
}

const isDev = !app.isPackaged

let mainWindow: BrowserWindow | null = null
let backend: BackendManager | null = null
let secrets: SecretsStore | null = null
/**
 * 用户给技能的密钥（私钥 / API Secret…）。
 *
 * ⚠️ 与 `secrets` **完全独立**：另一个文件（`skill-secrets.bin`）、另一套键空间
 * （扁平 `名字 -> 值`）、另一个注入变量（`AGENT_SKILL_SECRETS_FILE`）。
 * 产品明确要求不要动现有密钥存储逻辑，所以别想着合并两者。
 */
let skillSecrets: SkillSecretsStore | null = null

/**
 * 把当前的技能密钥推给核心（运行时热更新）。
 *
 * ⚠️ 为什么需要它：核心只在**启动时**读一次那个一次性临时文件
 * （`AGENT_SKILL_SECRETS_FILE`，读完立即删除 —— 见 `config/skill_secrets.py`）。
 * 所以运行期新增的密钥它不知道；不推的话，用户刚粘贴完让 AI 去用，
 * AI 会说"本地没有这个密钥"，而用户看着弹窗里明明已经保存成功了。
 *
 * ⚠️ 这条路是 **main → core** 的直连（HTTP + 本地令牌），
 * **不经过 IPC 到渲染层**，也不落日志内容 —— 与 `pushSession` 同一个模式。
 * 核心端只记条数（见 `runtime.apply_skill_secrets`）。
 *
 * ⚠️ 它是**模块级**而不是写在 `whenReady` 回调里：IPC handler 在另一个函数里注册，
 * 放在回调内会变成"作用域外看不见"（tsc 直接报 TS2552）。这一点踩过一次。
 */
async function pushSkillSecrets(): Promise<void> {
  const info = backend?.current
  // 核心还没起来时静默跳过：等它 `start()` 成功后由 `backend.ts` 在启动参数里
  // 带上 `AGENT_SKILL_SECRETS_FILE`（那份就是最新快照），所以这里漏掉一次
  // 不会造成不一致 —— 反过来"推给一个没起来的核心"只会白抛一条错误日志。
  if (!info) return
  const keys = skillSecrets?.load() ?? {}
  try {
    await coreFetch(info, '/v1/skill-secrets', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ keys }),
    })
  } catch (error: unknown) {
    // ⚠️ 失败**只记一条**、不弹窗、不回滚本地写入：本地那份是真相来源，
    // 核心重启后会从启动参数里拿到同一份内容自愈。
    // 把这里做成"保存失败"会让用户以为他的密钥没保存上。
    logDesktop(
      `[skill-secrets] 推送给核心失败：${error instanceof Error ? error.message : String(error)}`,
    )
  }
}
/** 账号引擎（设备指纹 / 静默首启 / 账号中心数据源）。见 electron/account/ */ 
let accountEngine: AccountEngine | null = null
/** PayPal 结账窗口（首尔线路专有）。同一时刻只允许存在一个。 */
let paypalWindow: BrowserWindow | null = null
/**
 * 是否已经在退出流程里。
 *
 * 声明在**这里**（而不是文件末尾原先的位置）是因为 `second-instance` 处理器也要读它，
 * 而那个处理器在模块加载时就注册了 —— 放在后面会形成"声明之前的引用"，
 * 虽然实际时序上不会触发，但读代码时是个实打实的隐患。
 */
let quitting = false

// --------------------------------------------------------------------------- //
// 改名后的数据目录迁移
// --------------------------------------------------------------------------- //
/**
 * 把改名前的 userData 搬到新名字上。
 *
 * 应用改名后 Electron 的 ``userData`` 会跟着变成 ``%APPDATA%/Soulmate Agent``，
 * 于是用户原来的配置、密钥、会话、向量库会**看起来凭空消失** —— 那等于丢数据。
 * 所以启动早期把它搬过来。
 *
 * 迁移源按**倒序**排列：最近的旧名字排在最前（``Soulmate`` 是 0.1.17 及更早的
 * 名字，``AgentDesktop`` 是它之前那个）。逐个尝试，**搬到第一个存在的就停**。
 *
 * **搬不动就继续用新目录**，只记一笔日志：搬文件失败（文件被占用、权限问题）
 * 不该让应用起不来，那种情况下"空着启动"比"启动失败"好得多。
 */
const LEGACY_DATA_DIR_NAMES = ['Soulmate', 'AgentDesktop']

function migrateLegacyUserData(): void {
  const current = app.getPath('userData')
  for (const name of LEGACY_DATA_DIR_NAMES) {
    const legacy = path.join(app.getPath('appData'), name)
    if (legacy === current) continue
    // 新目录已经存在（应用在新名字下启动过一次）就不再搬：
    // 这时候合并两份目录只会把两边的内容搅在一起
    if (fs.existsSync(current)) return
    if (!fs.existsSync(legacy)) continue
    try {
      fs.renameSync(legacy, current)
      logDesktop(`已把旧数据目录 ${name} 迁移到 ${current}`)
      return
    } catch (error) {
      logDesktop(`旧数据目录 ${name} 迁移失败，继续使用新目录：${String(error)}`)
      return
    }
  }
}

migrateLegacyUserData()

// --------------------------------------------------------------------------- //
// 单实例：多开会导致两个后端进程抢同一份 SQLite 与配置文件
// --------------------------------------------------------------------------- //
const gotLock = app.requestSingleInstanceLock()
if (!gotLock) {
  // 拿不到锁 = **已经有一个实例活着**。这一次双击不会出现任何窗口，
  // 而是由那个实例把窗口拉到前面（见下面的 second-instance）。
  //
  // 这条日志是定位"双击没反应"的关键：它和另一侧的 second-instance 日志
  // 一对，就能还原出用户到底点了几下、每一次分别发生了什么。
  logDesktop('未取得单实例锁：已有实例在运行，本次启动直接退出')
  app.quit()
} else {
  logDesktop(`主进程启动（版本 ${app.getVersion()}，pid ${process.pid}，开发模式=${isDev}）`)

  app.on('second-instance', () => {
    // 用户又双击了一次 —— **这条路径就是"看起来没反应就再点一下"的落点**，
    // 所以它必须和第一次启动一样可靠。原先这里只处理"窗口还在"的情况，
    // 窗口一旦销毁就什么都不做，用户会觉得应用彻底打不开了。
    logDesktop(`收到第二次启动请求（窗口=${describeMainWindow()}，退出中=${quitting}）`)

    if (mainWindow && !mainWindow.isDestroyed()) {
      // 复用托盘那条恢复路径：它在"最小化""被隐藏到托盘""正常可见"三种情况下
      // 都能把窗口正确叫出来。分两处各写一遍，迟早会漏掉其中一种。
      restoreMainWindow()
      return
    }

    // 窗口不存在有两种可能：用户关掉了窗口、但进程还要先把后端收干净
    // （见文件末尾的 before-quit，通常一两秒）；或窗口已销毁而进程仍在。
    // 两种都不该无声无息 —— 直接把窗口再建出来。
    if (quitting) {
      // 正在退出：此刻建出来的窗口马上会被下一次 app.quit() 带走，
      // 反而更让人困惑。如实记一笔，用户再点一次就好。
      logDesktop('正在退出流程中，忽略本次启动请求')
      return
    }
    mainWindow = createWindow()
    logDesktop('窗口不存在，已按启动请求重新创建')
  })

  void bootstrap()
}

// --------------------------------------------------------------------------- //
// 窗口
// --------------------------------------------------------------------------- //
/** 窗口底色必须和该皮肤画布同色，否则首帧会闪一下白。
 *  **加新皮肤时这里和 index.css 要同步。** */
const WINDOW_BACKGROUNDS: Record<string, string> = {
  light: '#ffffff',
  warm: '#fdf8f1',
  sakura: '#fffafc',
  mint: '#f7fdfa',
  sky: '#f7fbff',
  apricot: '#fffdf6',
  // ⚠️ **夜间 7 套一起换了更暗的画布色**（dark/plum/forest/ocean/pine/charcoal/deepnight），
  // 这里必须跟着改（否则启动首帧会闪一下旧底色）。规则见 `src/index.css` 里「夜间」那段注释。
  dark: '#16171a',
  forest: '#0f1512',
  ocean: '#0d131b',
  plum: '#14101b',
  pine: '#0e1311',
  charcoal: '#141414',
  deepday: '#f4f7ff',
  deepnight: '#06080f',
}

/**
 * 窗口底色，取渲染层 ``--app-canvas`` 的同一个值（见 src/index.css）。
 *
 * 它必须和标题栏一起在切主题时更新：窗口底色是**渲染层画出来之前**那一帧的
 * 颜色，不同步的话夜间模式每次启动都会先闪一下白。
 */
function windowBackground(theme: WindowTheme): string {
  return WINDOW_BACKGROUNDS[theme] ?? '#ffffff'
}

/**
 * 主进程侧的桌面偏好：主题 + 点关闭按钮时做什么。
 *
 * ## 为什么这两项必须由主进程自己存
 *
 * 它们都要在**渲染层和后端都不可用**的时候仍然读得到：
 *
 * - **主题**：窗口创建（下面 createWindow）必须在渲染层启动之前就定下首帧配色，
 *   否则夜间模式下每次启动都会白闪一下。而主题真正的家在渲染层的 localStorage，
 *   主进程读不到。所以这里存的是一份**镜像** —— 渲染层每次 bootstrap 都会重发一遍
 *   （见 appStore 的 applyTheme），即使过期也会自愈。
 * - **关闭行为**：用户点 × 的那一刻，后端可能正在退出、甚至已经挂了。
 *   把这个选择放进后端配置，等于让"关窗"依赖一个随时可能不可用的组件。
 *
 * ## 存哪
 *
 * `<userData>/desktop-prefs.json`。上一版只存了 `{theme}`（`window-theme.json`），
 * 所以读取时会**向下兼容**一次，免得用户升级后主题被重置成跟随系统。
 */
const PREFS_FILE = 'desktop-prefs.json'
/** 上一版只存主题的文件名，仅用于向下兼容读取 */
const LEGACY_THEME_FILE = 'window-theme.json'

function prefsPath(): string {
  return path.join(app.getPath('userData'), PREFS_FILE)
}

/**
 * 是否是已知的皮肤 id。
 *
 * 判据只有一个：``WINDOW_BACKGROUNDS`` 里有没有它。这样**新加皮肤时只需改那一处**，
 * 不用记得同步改校验 —— 逐个列举 id 的写法迟早会漏，而漏了的表现是
 * "用户在界面上选了新皮肤，重启后变回默认"，非常难查。
 */
function isKnownTheme(value: unknown): value is WindowTheme {
  return typeof value === 'string' && value in WINDOW_BACKGROUNDS
}

function pickTheme(value: unknown, fallback: WindowTheme): WindowTheme {
  return isKnownTheme(value) ? value : fallback
}

/** 未知取值一律退回 `ask` —— 对关闭行为来说，"不替用户拿主意"是最安全的默认 */
function pickCloseAction(value: unknown): CloseAction {
  return value === 'tray' || value === 'quit' || value === 'ask' ? value : 'ask'
}

/**
 * 录音设备 id：非字符串一律回落到空串（= 系统默认）。
 *
 * ⚠️ 这里**不校验"这个设备现在还在不在"**：设备枚举在渲染层
 * （`navigator.mediaDevices.enumerateDevices`），主进程此刻多半还没有麦克风权限、
 * 也拿不到设备列表。失效的 id 由渲染层负责回落并说明（见 `micPrefs.ts`）。
 */
function pickMicDeviceId(value: unknown): string {
  return typeof value === 'string' ? value : ''
}

function readPrefs(): DesktopPrefs {
  // 出厂主题 = 晨蓝（从暮紫改为晨蓝）。
  // ⚠️ 这一项只决定**渲染层画出来之前那一帧**的窗口底色，所以它必须与渲染层的
  // 出厂主题（`appStore.ts` 的 `readStoredTheme` → `DAY_DEFAULT`）**同值** ——
  // 不一致的话，全新安装启动时会先闪一下另一种颜色。
  // 只影响"从没存过偏好"的全新安装；存过任何一个皮肤的用户都会命中 pickTheme 保留原值。
  const prefs: DesktopPrefs = {
    theme: 'deepday',
    closeAction: 'ask',
    // 空串 = 用系统默认麦克风（从没选过的用户都是这个）
    micDeviceId: '',
  }

  try {
    const raw = JSON.parse(fs.readFileSync(prefsPath(), 'utf-8')) as Partial<DesktopPrefs>
    prefs.theme = pickTheme(raw.theme, prefs.theme)
    prefs.closeAction = pickCloseAction(raw.closeAction)
    prefs.micDeviceId = pickMicDeviceId(raw.micDeviceId)
    return prefs
  } catch {
    // 首次运行还没有这个文件；文件损坏也不该拦住窗口创建 —— 落到下面的兼容分支
  }

  try {
    const legacy = JSON.parse(
      fs.readFileSync(path.join(app.getPath('userData'), LEGACY_THEME_FILE), 'utf-8'),
    ) as { theme?: unknown }
    prefs.theme = pickTheme(legacy.theme, prefs.theme)
  } catch {
    // 没有旧文件才是常态
  }
  return prefs
}

function writePrefs(patch: Partial<DesktopPrefs>): DesktopPrefs {
  // 先读再合并：调用方常常只想改一个字段，直接覆盖会把另一个字段抹回默认值
  const next: DesktopPrefs = { ...readPrefs(), ...patch }
  try {
    fs.writeFileSync(prefsPath(), JSON.stringify(next, null, 2), 'utf-8')
  } catch {
    // 记不住只影响下次启动（配色 / 是否询问），不该影响本次使用，所以不抛出
  }
  return next
}

/**
 * 给日志用的一句话描述：现在有没有窗口、它在不在屏幕上。
 *
 * 抽出来是因为 `second-instance` 那几条日志全靠它 —— 而"窗口存在但不可见"
 * 与"窗口不存在"这两种情况对用户来说都是"点了没反应"，对排查却是完全不同的结论。
 */
function describeMainWindow(): string {
  if (!mainWindow || mainWindow.isDestroyed()) return '不存在'
  return mainWindow.isVisible() ? '可见' : '存在但不可见'
}

/**
 * 首帧显示的兜底时长。
 *
 * 正常首帧在 300~600ms 内完成，所以 300ms 不会在日常启动时抢在
 * `ready-to-show` 前面（那样会先露出一小块空窗口）；而一旦首帧真的卡住，
 * 它就是"窗口至少一定会出现"的保证。详见下面 createWindow 里的说明。
 *
 * 实测反馈"拉起要等约 5 秒、期间像没反应"（#1）：把兜底从 800ms 调短，
 * 让窗口更早带着皮肤底色出现（底色由 backgroundColor 定，不会白闪），
 * 等待期交给 BootScreen 的品牌加载动画。
 */
const WINDOW_REVEAL_FALLBACK_MS = 300

/**
 * 出厂默认窗口大小（定：**1366 × 768**）。
 *
 * ⚠️ 它有两个用途，**必须同源**：① 首启时窗口的初始尺寸；② 标题栏那个「还原」
 * 按钮要恢复到的尺寸（见下面 `IPC.windowResetSize` 的处理）。
 * 写成两个字面量迟早会漂移 —— 表现是"点了还原之后，尺寸跟刚装好时不一样"。
 */
const DEFAULT_WINDOW_SIZE = { width: 1366, height: 768 }

/**
 * 窗口**最小**尺寸（产品定下的 1040×660）。
 *
 * ⚠️ 从 起它与默认值**解耦**：默认值是"我们要的观感"，这个是"用户
 * 还能把窗口拉到多小"。两者不再相等，别看到数字不同就以为写错了。
 */
const MIN_WINDOW_SIZE = { width: 1040, height: 660 }

/**
 * 每个窗口各自的**出厂默认尺寸**（`window:reset-size` 要恢复到的目标）。
 *
 * ⚠️ 为什么必须按窗口分别记，而不是一律用 `DEFAULT_WINDOW_SIZE`：
 * 独立对话窗（900×720）与群窗（780×680）**也渲染同一个 `TitleBar`**
 * （见 `src/App.tsx` 的 `isChatWindow` / `isGroupWindow` 两个分支），
 * 所以它们身上也有那个「恢复默认大小」按钮。一律按主窗口的 1366×768 恢复的话，
 * 用户点一下会把一个"贴在屏幕角落的小观察窗"**撑成大窗**，完全不是他要的。
 *
 * 用 `WeakMap` 而不是普通 `Map`：窗口销毁后条目会被自动回收，不必手动清理
 * （普通 Map 会一直持有已销毁的 BrowserWindow，是那种"看不出问题的泄漏"）。
 */
const windowDefaultSize = new WeakMap<BrowserWindow, { width: number; height: number }>()

/**
 * 把想要的窗口尺寸夹到**当前屏幕装得下**的范围里。
 *
 * ⚠️ 为什么非有不可：默认值 1366×768 **恰好等于**那批常见笔记本的整屏分辨率，
 * 而窗口还要给任务栏（约 40px）让位 —— 不夹的话，1366×768 的屏幕上开出来就是
 * "顶着屏幕下沿、底部被任务栏切掉一截"，用户看到的是**布局被截断**（底部输入框
 * 恰好是最容易被切掉的那一块）。夹完至少保证整窗在工作区内可见。
 *
 * 传 `bounds` 是为了"按窗口当前所在那块屏"算：双屏时主屏装不下、副屏装得下，
 * 一律按主屏夹会把窗口无谓地缩小。
 */
function fitToWorkArea(
  width: number,
  height: number,
  bounds?: { x: number; y: number; width: number; height: number },
): { width: number; height: number } {
  const area = bounds
    ? screen.getDisplayMatching(bounds).workArea
    : screen.getPrimaryDisplay().workArea
  return {
    // 下限守着 minWidth/minHeight：夹到比最小还小的话，Electron 会自己顶回来，
    // 结果"算出来的尺寸"与"实际尺寸"对不上（日志与还原按钮都会因此说谎）。
    width: Math.max(MIN_WINDOW_SIZE.width, Math.min(width, area.width)),
    height: Math.max(MIN_WINDOW_SIZE.height, Math.min(height, area.height)),
  }
}

/**
 * 前端页面文件的位置。
 *
 * ⚠️ 打包后前端**不在 `app.asar` 里**了，而是由 `extraResources` 落到
 * `<安装根>/resources/dist/**`（为"文件级增量更新"做的改动：
 * 单文件的 asar 没法只替换其中几个文件，挪出来才能做到"改哪个文件只下哪个文件"）。
 *
 * 所以不能再拼 `__dirname/../../dist` —— 打包后 `__dirname` 是
 * `<resources>/app.asar/dist-electron/electron`，从 asar 内部跨不到 `resources/dist`。
 * 改走 `process.resourcesPath`（与 `backend.ts` 找 Python 核心用的是同一套办法）。
 *
 * ⚠️ 未打包时（`electron .`，即不带 dev server 的手工调试）`process.resourcesPath`
 * 指向 **Electron 自身**的 resources 目录，那里没有我们的页面 —— 因此按
 * `app.isPackaged` 分叉：未打包就回到源码产物目录。
 *
 * ⚠️ dev 模式（有 `VITE_DEV_SERVER_URL`）根本不走这里，走的是一条 `loadURL` 分支。
 */
function rendererIndexPath(): string {
  return app.isPackaged
    ? path.join(process.resourcesPath, 'dist', 'index.html')
    : path.join(__dirname, '../../dist/index.html')
}

function createWindow(): BrowserWindow {
  // 先读出主题再建窗口：backgroundColor 与 titleBarOverlay 都只在创建那一刻
  // 定得下首帧，窗口显示之后再改就会看到一次跳色。
  const initialTheme = readPrefs().theme
  /*
    ⚠️ 首启尺寸的口径变过三次，当前以第三次为准：

    1. 最初默认 1360×880、最小 1040×660；
    2. 改成"默认 = 最小 = 1040×660"，理由是"不是每个用户都有我这么大的
       显示器"，1360 宽在 1366 屏上几乎顶满；
    3. **现在是默认 1366×768、最小仍 1040×660** —— 产品明确要求"界面默认长宽设置为
       1366×768，用户首启就按这个来"。

    ⚠️ 1366×768 恰好是那批笔记本的整屏分辨率，所以这里**必须**过一遍
    `fitToWorkArea`，否则任务栏会把窗口底部切掉（理由见那个函数的说明）。
  */
  const initialSize = fitToWorkArea(DEFAULT_WINDOW_SIZE.width, DEFAULT_WINDOW_SIZE.height)
  const win = new BrowserWindow({
    width: initialSize.width,
    height: initialSize.height,
    minWidth: MIN_WINDOW_SIZE.width,
    minHeight: MIN_WINDOW_SIZE.height,
    show: false,
    // 窗口与任务栏图标显式指向品牌图。
    //
    // 不设的话打包版会沿用 exe 内嵌图标（没问题），但**开发模式**（`electron .`）
    // 用的是 Electron 自己的图标 —— 开发时看到的不是自家品牌，很容易被误判成
    // "图标没换成功"，从而去排查一个并不存在的问题。
    icon: path.join(__dirname, '../../assets/window.png'),
    backgroundColor: windowBackground(initialTheme),
    // 完全自绘标题栏（含最小化/最大化/关闭按钮）。不再用 titleBarOverlay：
    // 系统的 overlay 按钮区域是**纯色**，用户上传的壁纸渲染不到那一块（反馈 #7）。
    // 去掉 overlay 后整条标题栏都是 DOM，壁纸（body::before）能透出来。
    titleBarStyle: 'hidden',
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
      // 渲染进程开启沙箱。
      //
      // 原先是 false，效果是把渲染进程放进一个**权限更大的**进程里运行 ——
      // 而 preload 只做 ``ipcRenderer.invoke`` 转发（不 require 任何 Node 模块），
      // 完全不需要那份权限。也就是说关掉沙箱没有任何功能收益，只是白白
      // 放大了"渲染层被攻破"时的后果面。
      sandbox: true,
      spellcheck: false,
    },
  })

  // 登记这个窗口的"出厂默认大小"，供标题栏的「恢复默认大小」按钮使用。
  // ⚠️ 记的是**实际开出来的尺寸**（已经过 `fitToWorkArea` 夹取）而不是常量本身：
  // 在小屏上开出来就是被夹过的小尺寸，那时"恢复默认"应当回到**开箱时的样子**，
  // 而不是回到一个当初就放不下的数字（那样点一下反而会顶出屏幕）。
  windowDefaultSize.set(win, initialSize)

  // ---- 保证窗口一定会出现 -------------------------------------------- //
  //
  // 原先只等 `ready-to-show`。那条路本身有道理（首帧带着正确底色出现，不白闪），
  // 但它**没有任何兜底**：只要首帧渲染慢于用户的耐心，用户看到的就是
  // "双击了没反应"，于是再点一次 —— 而第二次会走 second-instance 里的 show()，
  // 看起来就成了"要点两次才打得开"。
  //
  // 实测反馈正是这个现象，而且说不清规律，因为它取决于每次首帧的耗时。
  const createdAt = Date.now()
  let revealed = false
  let revealTimer: ReturnType<typeof setTimeout> | null = null

  const reveal = (reason: string): void => {
    if (revealed || win.isDestroyed()) return
    revealed = true
    if (revealTimer) {
      clearTimeout(revealTimer)
      revealTimer = null
    }
    win.show()
    // show() 之后**显式** focus：Windows 的前台锁会让新窗口开在别的窗口后面，
    // 那种情况下用户同样会以为没打开。
    win.focus()
    logDesktop(`窗口已显示（${reason}，启动后 ${Date.now() - createdAt}ms）`)
  }

  revealTimer = setTimeout(() => reveal('兜底定时器'), WINDOW_REVEAL_FALLBACK_MS)
  win.once('ready-to-show', () => reveal('ready-to-show'))

  // 外链一律交给系统浏览器，应用内不做任意页面跳转
  win.webContents.setWindowOpenHandler(({ url }) => {
    if (/^https?:\/\//i.test(url)) void shell.openExternal(url)
    return { action: 'deny' }
  })
  win.webContents.on('will-navigate', (event, url) => {
    const devServer = process.env.VITE_DEV_SERVER_URL
    if (devServer && url.startsWith(devServer)) return
    if (url.startsWith('file://')) return
    event.preventDefault()
    if (/^https?:\/\//i.test(url)) void shell.openExternal(url)
  })

  const devServer = process.env.VITE_DEV_SERVER_URL
  if (devServer) {
    void win.loadURL(devServer)
    win.webContents.openDevTools({ mode: 'detach' })
  } else {
    void win.loadFile(rendererIndexPath())
  }

  // 渲染层就绪标志：决定关闭询问走应用内弹窗还是原生对话框（见 askCloseAction）
  win.webContents.on('did-finish-load', () => {
    rendererReady.set(win.webContents, true)
  })
  win.webContents.on('render-process-gone', () => {
    rendererReady.set(win.webContents, false)
  })

  win.on('close', (event) => {
    // 真正要退出了（托盘菜单"退出"、系统注销/关机、before-quit 已介入）——放行。
    // 这一句必须排在最前面：没有它，托盘模式下 app.quit() 会被自己的拦截挡住，
    // 应用会变成"退不掉"。
    if (forceQuit) return

    // 每次关窗都重新读偏好：用户在设置里改完要立刻生效，不能等重启
    const { closeAction } = readPrefs()

    if (closeAction === 'tray') {
      event.preventDefault()
      hideToTray(win)
      return
    }

    if (closeAction === 'quit') {
      // 放行，交给正常退出链路（before-quit 会先把 Python 核心收干净）
      return
    }

    // closeAction === 'ask'：拦住这次关闭，问一次
    event.preventDefault()
    void askCloseAction(win)
  })

  win.on('closed', () => {
    // 清掉兜底定时器，免得它对一个已经销毁的窗口再调一次 show()
    if (revealTimer) clearTimeout(revealTimer)
    mainWindow = null
  })
  return win
}

// 独立对话窗口：每个搭子一个，可同时开多个（产品要求）。
//
// 键的选择（产品要求）：给了 sessionId 就**按会话**开窗 —— 同一个搭子的
// 两段对话各自拎出来时互不干扰；没给（例如从搭子栏直接开）才退回按搭子开一个。
const chatWindows = new Map<string, BrowserWindow>()

function createChatWindow(assistantId: string, sessionId = ''): void {
  const key = sessionId || assistantId
  const existing = chatWindows.get(key)
  if (existing && !existing.isDestroyed()) {
    if (existing.isMinimized()) existing.restore()
    existing.focus()
    return
  }

  const initialTheme = readPrefs().theme
  const win = new BrowserWindow({
    width: 900,
    height: 720,
    minWidth: 480,
    minHeight: 400,
    show: false,
    icon: path.join(__dirname, '../../assets/window.png'),
    backgroundColor: windowBackground(initialTheme),
    // 独立窗口同样自绘标题栏（含窗口控制按钮）
    titleBarStyle: 'hidden',
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
      spellcheck: false,
      // 渲染层据此只渲染"这一个搭子的对话区"，不渲染导航/助手栏/会话栏
      additionalArguments: [
        `--window-mode=chat`,
        `--assistant-id=${assistantId}`,
        `--session-id=${sessionId}`,
      ],
    },
  })
  // 独立对话窗的"出厂默认大小"（标题栏那个「恢复默认大小」按钮的目标）。
  // ⚠️ 与主窗口的 1366×768 **不同**：这个按钮在两个窗口里都渲染（都走 `TitleBar`），
  // 所以必须按窗口分别记 —— 否则用户在一个小对话窗里点"恢复默认"，窗口会被撑成大窗。
  windowDefaultSize.set(win, { width: 900, height: 720 })
  chatWindows.set(key, win)

  wireSecondaryWindow(win, {
    onClosed: () => chatWindows.delete(key),
  })
}

/**
 * 接上「次要窗口」（独立对话窗 / 群聊窗）共用的那几件事：外链交给系统浏览器、
 * 开发与生产两种加载方式、就绪后再显示。
 *
 * 抽出来是因为两种窗口需要**一模一样**的这套装配 —— 各写一份的话，迟早出现
 * "群聊窗能点开外链、对话窗点不开"这种只在一边坏掉、还很难注意到的问题。
 */
function wireSecondaryWindow(
  win: BrowserWindow,
  options: { onClosed: () => void; inactive?: boolean },
): void {
  win.webContents.setWindowOpenHandler(({ url }) => {
    if (/^https?:\/\//i.test(url)) void shell.openExternal(url)
    return { action: 'deny' }
  })
  win.webContents.on('will-navigate', (event, url) => {
    const devServer = process.env.VITE_DEV_SERVER_URL
    if (devServer && url.startsWith(devServer)) return
    if (url.startsWith('file://')) return
    event.preventDefault()
    if (/^https?:\/\//i.test(url)) void shell.openExternal(url)
  })

  const devServer = process.env.VITE_DEV_SERVER_URL
  if (devServer) void win.loadURL(devServer)
  // 页面在 asar 之外的 `resources/dist/**`（见 `rendererIndexPath` 的说明）
  else void win.loadFile(rendererIndexPath())

  win.once('ready-to-show', () => {
    // 只读观察窗**不抢焦点**（showInactive）：它是在用户没要求的时候自己弹出来的，
    // 一旦抢走焦点就等于"顶掉了他正在打的字" —— 那是最招骂的一种打扰。
    // 这不能靠 `focusable: false` 实现：那样窗口连点都点不动，用户想细看也看不了。
    if (options.inactive) win.showInactive()
    else {
      win.show()
      win.focus()
    }
  })
  win.on('closed', options.onClosed)
}

// 群聊独立窗口（产品要求：AI 在后台讨论时能看见它在干什么 / 自己也能进去聊）。
//
// **两种形态、同一个窗口**：只读观察窗（observing=true，后台讨论自动弹）与
// 可操作窗口（observing=false，用户从群聊列表手动打开）。
//
// ⚠️ 记录里必须带上形态（observing）：窗口的角色是在创建时写进
// `additionalArguments` 的，创建之后改不了。所以"同一个群已经有一个只读观察窗"时，
// 用户再点「新窗口」**不能只聚焦那个窗**（那就是他报的缺陷：手动打开却是只读的），
// 而要关掉它重开一个可操作的。
/**
 * 已打开的群窗口。
 *
 * ⚠️ key 是 **`groupId:threadId`** 而不是 groupId（一个群可以
 * 有多条对话）。只按群去做 key 的话，对 A 对话点「打开独立窗口」、
 * 再对 B 对话点一次，第二次会聚焦到 A 那个窗口上 —— 用户看到的是"点的明明是
 * B，开出来却是 A"。
 *
 * `threadId` 为空串（观察窗、以及"没指定对话"的调用）时 key 就是 `groupId:`，
 * 与旧行为一致。
 */
const groupWindows = new Map<string, { win: BrowserWindow; observing: boolean }>()

function groupWindowKey(groupId: string, threadId: string): string {
  return `${groupId}:${threadId}`
}

function createGroupWindow(groupId: string, observing: boolean, threadId = ''): void {
  const key = groupWindowKey(groupId, threadId)
  const existing = groupWindows.get(key)
  if (existing && !existing.win.isDestroyed()) {
    if (existing.observing === observing) {
      if (existing.win.isMinimized()) existing.win.restore()
      existing.win.focus()
      return
    }
    // 形态不一致：
    // - 已有只读观察窗、现在要可操作窗（用户点了「新窗口」）→ 关掉重开；
    // - 已有可操作窗、后台事件又来了（要只读窗）→ **不降级**，聚焦现有的那个：
    //   可操作窗能力更全，把它换成只读窗等于把用户手里的窗口收走了。
    if (existing.observing && !observing) {
      existing.win.destroy()
      groupWindows.delete(key)
    } else {
      if (existing.win.isMinimized()) existing.win.restore()
      existing.win.focus()
      return
    }
  }

  const initialTheme = readPrefs().theme
  const win = new BrowserWindow({
    width: 780,
    height: 680,
    minWidth: 420,
    minHeight: 380,
    show: false,
    icon: path.join(__dirname, '../../assets/window.png'),
    backgroundColor: windowBackground(initialTheme),
    titleBarStyle: 'hidden',
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
      spellcheck: false,
      // 渲染层据此只渲染"这一个群的讨论"，不渲染导航 / 助手栏 / 会话栏
      additionalArguments: [
        '--window-mode=group',
        `--group-id=${groupId}`,
        `--group-readonly=${observing ? '1' : '0'}`,
        // 空串 = 没指定，渲染层落到该群"最近有动静"的那条对话
        `--group-thread=${threadId}`,
      ],
    },
  })
  // 群窗的"出厂默认大小"（同上面独立对话窗的理由，别改成主窗口那个 1366×768）
  windowDefaultSize.set(win, { width: 780, height: 680 })
  groupWindows.set(key, { win, observing })

  wireSecondaryWindow(win, {
    onClosed: () => groupWindows.delete(key),
    inactive: observing,
  })
}

// --------------------------------------------------------------------------- //
// 托盘与关闭行为
// --------------------------------------------------------------------------- //

/**
 * 是否**真的要退出**了。
 *
 * 与 `quitting`（后端收尾已经开始）不是一回事：这个标志专门用来放行窗口的
 * close 拦截。托盘菜单里的"退出"、系统注销/关机、以及 before-quit 都会置位。
 */
let forceQuit = false

let tray: Tray | null = null
/** 托盘提示只弹一次，见 notifyFirstHide */
let trayNoticeShown = false
/**
 * 正在等待回应的那个窗口（null = 当前没有询问在进行）。
 *
 * 用窗口引用而不是布尔量：回应必须来自**同一个窗口**，否则一个残留的
 * webContents 就能凭一条消息把主窗口关掉（见 closeAnswer 处理器）。
 */
let closePromptWindow: BrowserWindow | null = null
/**
 * 渲染层是否已就绪（页面加载完成）。决定关闭询问用应用内弹窗还是原生对话框。
 *
 * ⚠️ **按 `WebContents` 记，不能用一个进程内的全局布尔**（第 87 批，M-09）：
 * 多窗口下这个标志会互相顶掉 ——
 * · 主窗口渲染进程崩了（置 false）时，独立对话窗明明活着，点它的 × 也会退回
 *   **系统原生对话框**（与"改用应用内弹窗"的产品口径相悖）；
 * · 反过来，任一窗口 `did-finish-load` 就把标志置真，会让刚创建、其实还没渲染完的
 *   **另一个**窗口被误判为就绪 ⇒ 弹窗发出去没人接，**静默卡住**。
 * 用 `WeakMap` 而不是 Map：窗口关掉之后条目可被回收，不会一直攒着。
 */
const rendererReady = new WeakMap<WebContents, boolean>()

function trayIconPath(): string {
  // __dirname = <resources>/app.asar/dist-electron/electron
  return path.join(__dirname, '../../assets/tray.png')
}

/**
 * 惰性创建托盘。
 *
 * 图标缺失时**返回 null 而不是硬造一个**：Windows 上会出现一个看不见、
 * 点不到、但确实占着位置的图标，用户只会觉得"托盘区多了个莫名其妙的东西"。
 * 没有托盘时调用方会把关闭行为退化成直接退出 —— 宁可少一个功能，
 * 也不要留一个既找不到也点不掉的僵尸图标。
 */
function ensureTray(): Tray | null {
  if (tray && !tray.isDestroyed()) return tray
  try {
    const image = nativeImage.createFromPath(trayIconPath())
    if (image.isEmpty()) {
      logDesktop('托盘图标为空（assets/tray.png 没打进包？），本次不创建托盘')
      return null
    }
    tray = new Tray(image)
    tray.setToolTip('Soulmate Agent')
    tray.setContextMenu(
      Menu.buildFromTemplate([
        { label: '打开主界面', click: () => restoreMainWindow() },
        { type: 'separator' },
        { label: '退出', click: () => quitApp() },
      ]),
    )
    // 单击就恢复：Windows 用户对托盘图标的直觉就是"点一下把它叫出来"
    tray.on('click', () => restoreMainWindow())
    logDesktop('托盘已创建')
    return tray
  } catch (error) {
    logDesktop(`创建托盘失败：${String(error)}`)
    tray = null
    return null
  }
}

/** 把主窗口弄回用户看得见的样子；窗口已经不在了就重建一个 */
function restoreMainWindow(): void {
  if (!mainWindow || mainWindow.isDestroyed()) {
    if (quitting || forceQuit) return
    mainWindow = createWindow()
    return
  }
  if (mainWindow.isMinimized()) mainWindow.restore()
  if (!mainWindow.isVisible()) mainWindow.show()
  mainWindow.focus()
}

/**
 * 第一次缩到托盘时提示一下"它还在后台"。
 *
 * **只提示一次**：每次最小化都弹，用户会把它当成骚扰、进而关掉系统通知，
 * 之后就真的什么都提示不到了。而托盘图标在深色任务栏上并不显眼，
 * 所以这一次提示是必要的。
 */
function notifyFirstHide(): void {
  if (trayNoticeShown) return
  trayNoticeShown = true
  try {
    ensureTray()?.displayBalloon({
      title: 'Soulmate Agent 仍在后台运行',
      content: '双击桌面图标、或点托盘图标即可重新打开；右键托盘图标可以彻底退出。',
    })
  } catch {
    // 系统设置里禁用了气泡提示，忽略即可 —— 提示只是锦上添花
  }
}

function hideToTray(win: BrowserWindow): void {
  if (!ensureTray()) {
    // 托盘没建起来就**不能**隐藏：那样用户既看不到窗口、也没有任何入口找回来。
    // 退化成真正退出，至少行为是可预期的。
    logDesktop('托盘不可用，改为直接退出')
    quitApp()
    return
  }
  win.hide()
  logDesktop('窗口已最小化到托盘')
  notifyFirstHide()
}

// --------------------------------------------------------------------------- //
// PayPal 结账窗口（首尔线路专有）
// --------------------------------------------------------------------------- //

/** paypal.com 及其子域（含 sandbox.paypal.com / www.sandbox.paypal.com）。 */
function isPaypalUrl(target: string): boolean {
  try {
    const host = new URL(target).hostname.toLowerCase()
    return host === 'paypal.com' || host.endsWith('.paypal.com')
  } catch {
    return false
  }
}

/** 关掉结账窗口（幂等）。引擎在到账 / 过期 / 取消时调用。 */
function closePaypalCheckoutWindow(): void {
  const win = paypalWindow
  paypalWindow = null
  if (win && !win.isDestroyed()) win.close()
}

/**
 * 打开 PayPal 结账窗口。
 *
 * ⚠️ **必须放行 paypal.com 的弹窗**（`setWindowOpenHandler` 里 return `allow`）：
 * PayPal 的登录 / 授权流程会把后续页面开在**新窗口**里，一刀切 `deny` 的结果是
 * 授权页根本弹不出来，用户卡在一个空白窗上一动不动 —— 这属于"付不了款"级别的故障，
 * 比任何界面瑕疵都严重。因此只要目标是 paypal.com 域名就一律放行；
 * 其余外链交给系统浏览器，避免这个窗口被当成通用浏览器滥用。
 */
function openPaypalCheckoutWindow(url: string): void {
  closePaypalCheckoutWindow()
  const win = new BrowserWindow({
    width: 460,
    height: 720,
    show: true,
    title: 'PayPal 充值',
    autoHideMenuBar: true,
    webPreferences: {
      // 独立分区：PayPal 的登录 Cookie 与主界面完全隔离，两边都不污染对方的存储
      partition: 'persist:paypal-checkout',
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
    },
  })
  paypalWindow = win

  win.webContents.setWindowOpenHandler(({ url: target }) => {
    if (isPaypalUrl(target)) return { action: 'allow' }
    if (/^https?:\/\//i.test(target)) void shell.openExternal(target)
    return { action: 'deny' }
  })

  win.webContents.on('will-navigate', (event, target) => {
    // paypal.com 内部的跳转留在本窗口；其它地址一律交给系统浏览器，
    // 既避免把结账窗变成"任意网页浏览器"，也不给钓鱼页留可乘之机
    if (isPaypalUrl(target)) return
    event.preventDefault()
    if (/^https?:\/\//i.test(target)) void shell.openExternal(target)
  })

  win.on('closed', () => {
    // 只有"被关掉的那个仍然算当前结账窗"时才通知引擎。
    //
    // 引擎自己关窗（到账 / 过期 / 取消）时 `paypalWindow` 已被置空；重新发起时旧窗
    // 也会被新窗顶替 —— 这两种情况都不代表"用户放弃了结账"。若不判这一下，
    // 旧窗异步发出的 closed 会误清掉刚建好的新订单，把用户正在付的那笔直接取消。
    if (paypalWindow !== win) return
    paypalWindow = null
    // 用户手动关窗 = 放弃这次结账：让引擎停掉轮询，别在后台对着一个没人看的订单空打接口
    accountEngine?.handlePaypalWindowClosed()
  })

  void win.loadURL(url)
}

function quitApp(): void {
  forceQuit = true
  // 窗口**立即消失**：用户点「退出」后不该盯着窗口等 Python 核心收尾（可能数秒，
  // 实测反馈 #2）。先把所有窗口藏起来，后端在后台继续优雅关闭（见 before-quit），
  // 进程随后自行退出。hide() 而不是 destroy()：保留窗口对象，让 app.quit() 走
  // 正常的关闭链路（close 事件里 forceQuit 已放行）。
  for (const win of BrowserWindow.getAllWindows()) {
    if (!win.isDestroyed()) win.hide()
  }
  app.quit()
}

/** 结束一次关闭询问：按用户的选择执行，并（可选）把选择记下来 */
function settleCloseAction(win: BrowserWindow, action: CloseAction, remember: boolean): void {
  closePromptWindow = null

  if (remember) {
    writePrefs({ closeAction: action })
    logDesktop(`已记住关闭行为：${action}`)
  }

  if (action === 'tray') {
    hideToTray(win)
  } else {
    quitApp()
  }
}

/**
 * 问一次：最小化到托盘，还是退出 —— **只用应用内弹窗**。
 *
 * ⚠️ 历史教训（用户实测撞过）：这里曾有"1.5s 超时退回原生对话框"的兜底，
 * 结果**两个弹窗同时出现** —— 应用内的弹窗其实已经弹出，只是首帧渲染慢、
 * 回应超过了 1.5s，原生框又被补了一发。对用户来说就是"关个窗弹两个框"。
 *
 * 现在的规则：
 * - 渲染层**活着** → 只发应用内弹窗，**不设原生回退**（窗口真卡死时用户仍有
 *   托盘右键退出、任务管理器这些出路，不会被困死）；
 * - 渲染层**没起来/已崩** → 才用原生对话框（此时不存在"双弹"问题）。
 */
async function askCloseAction(win: BrowserWindow): Promise<void> {
  // 已经有一个询问在进行（用户狂点 ×）：忽略，别叠出好几个
  if (closePromptWindow === win) return

  const contents = win.webContents
  if (contents.isDestroyed() || contents.isCrashed() || !rendererReady.get(contents)) {
    logDesktop('渲染层不可用或尚未就绪，直接用系统对话框询问关闭行为')
    await askCloseActionNative(win)
    return
  }

  closePromptWindow = win
  contents.send(IPC.closePrompt)
  logDesktop('已向界面弹出关闭询问')
}

/**
 * 系统原生兜底对话框。
 *
 * 只在渲染层不可用、或界面超时没回应时才走到。风格与应用不一致，
 * 但它**完全不依赖渲染层**，所以是"窗口永远关得掉"的最后一道保险。
 */
async function askCloseActionNative(win: BrowserWindow): Promise<void> {
  try {
    const { response, checkboxChecked } = await dialog.showMessageBox(win, {
      type: 'question',
      buttons: ['最小化到托盘', '退出应用'],
      defaultId: 0,
      cancelId: 0,
      noLink: true,
      title: '关闭窗口',
      message: '要最小化到托盘，还是直接退出？',
      detail:
        '最小化到托盘后应用仍在后台运行：双击桌面图标、或点托盘图标就能重新打开，' +
        '从托盘图标右键可以彻底退出。',
      checkboxLabel: '记住我的选择（之后可在左侧「安全与通用」页里修改）',
    })
    // 用按钮**下标**判断而不是文案：以后改文案不会连带改坏逻辑
    settleCloseAction(win, response === 1 ? 'quit' : 'tray', checkboxChecked)
  } catch (error) {
    // 连原生对话框都弹不出来（极小概率）时不能卡住：默认最小化到托盘，
    // 至少窗口不会悬在"关不掉"的状态里
    logDesktop(`原生关闭对话框失败：${String(error)}，默认最小化到托盘`)
    hideToTray(win)
  }
}

// --------------------------------------------------------------------------- //
// 启动流程
// --------------------------------------------------------------------------- //
async function bootstrap(): Promise<void> {
  // 启动分步计时。**这不是调试期的临时日志**：曾经出现过"双击后几分钟才出窗口"
  // 的现象（实测 210 秒），而当时的日志只有"主进程启动 / 窗口已显示"两行，
  // 完全看不出那三分半花在哪一步 —— 只能靠猜。每一步都记一笔之后，
  // 下次一眼就能看出是系统代理、密钥存储还是拉起后端慢。
  const t0 = Date.now()
  const mark = (step: string) =>
    logDesktop(`启动步骤：${step}（累计 ${((Date.now() - t0) / 1000).toFixed(1)}s）`)

  await app.whenReady()
  mark('app.whenReady')

  // 关键：Windows 上 Chromium 会使用「Internet 选项」里的系统代理，
  // 一旦用户配了代理，对 127.0.0.1 的本地请求也会被转发出去而失败。
  // 渲染层只访问本地后端，因此直接关闭代理。
  await session.defaultSession.setProxy({ mode: 'direct' })
  mark('关闭代理')

  // 生产环境去掉默认菜单栏：这是面向普通用户的办公工具，
  // 不需要 Ctrl+P / Ctrl+R 这类会让人困惑的浏览器行为。开发时保留以便调试。
  if (!isDev) Menu.setApplicationMenu(null)

  // 密钥存储必须在 whenReady 之后创建：safeStorage 依赖 app 初始化完成
  secrets = new SecretsStore()
  // 把历史版本明文写在 config/*.json 里的密钥搬进加密存储。
  // 必须排在拉起后端之前——后端一起就会读到那份还没清理的明文。
  const migrated = secrets.migrateFromConfigFiles(path.join(app.getPath('userData'), 'config'))
  const secretsStatus = secrets.status()
  console.log(
    `[secrets] 保护方式=${secretsStatus.protection} 条目=${secretsStatus.count}` +
      (migrated > 0 ? ` 迁移=${migrated}` : ''),
  )
  // 技能密钥：与上面那个 SecretsStore 平行、互不影响（见 skill-secrets.ts 的说明）
  skillSecrets = new SkillSecretsStore()
  mark('技能密钥存储就绪')

  backend = new BackendManager(app.getPath('userData'), secrets, skillSecrets)
  backend.onStatus = (status: BackendStatus) => {
    // 广播给**所有**窗口（含独立对话窗口）：独立窗口也要据此完成握手，
    // 否则它看不到"后端就绪"而一直停在加载态。
    for (const win of BrowserWindow.getAllWindows()) {
      if (!win.isDestroyed()) win.webContents.send(IPC.backendStatusEvent, status)
    }
  }
  backend.onLog = (line, stream) => {
    if (isDev && stream === 'stderr') console.log(`[core] ${line}`)
  }

  // 会话凭证代发通道（见 account/engine.ts 的 SessionSync）：主进程把当前登录的
  // session_token 推给核心，核心在心鉴学报告接口里拿它当 Authorization 头。
  // ⚠️ 凭证只走这条 main→core 通道，**不进 IPC 到渲染层**、不落日志内容。
  const pushSession = (token: string): void => {
    const info = backend?.current
    // 核心还没就绪时先跳过：等 `backend.start()` 成功后会补推一次当前凭证
    if (!info) return
    void coreFetch(info, '/v1/client/session', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ session_token: token }),
    }).catch((error: unknown) => {
      logDesktop(
        `[account] 会话凭证推送给核心失败：${error instanceof Error ? error.message : String(error)}`,
      )
    })
  }

  // 账号引擎要在 registerIpc 之前建好（handler 里会用到它），但**在窗口创建之后**
  // 才 start()：这样第一批快照推出去时已经有窗口在接收。
  //
  // 它跑的是"静默首启"（设备指纹 → 查号 → 没有才注册 → 拉账号信息），
  // 刻意不 await —— 账号是后台准备的东西，不该拖慢第一次看到界面的时间。
  accountEngine = new AccountEngine(
    (snapshot: AccountSnapshot) => {
      for (const win of BrowserWindow.getAllWindows()) {
        if (!win.isDestroyed()) win.webContents.send(IPC.accountChangedEvent, snapshot)
      }
    },
    // 结账窗口是"壳"的一部分，交给 main.ts 开/关；引擎只管什么时候要开要关
    { open: openPaypalCheckoutWindow, close: closePaypalCheckoutWindow },
    // 会话凭证代发（心鉴学报告接口的凭证由核心代发）
    { push: pushSession },
  )

  registerIpc()
  mainWindow = createWindow()
  mark('窗口已创建')

  accountEngine.start()

  // 后端启动与窗口显示并行，窗口先出现再显示加载状态，避免白屏等待
  try {
    await backend.start()
    mark('内置核心已就绪')
    // 核心刚起来，内存里的凭证是空的；把上一次登录留下的凭证补推过去 ——
    // 否则首启后第一次取心鉴学报告会稳定 401（"没登录"其实早就登录了）。
    accountEngine?.syncSession()
  } catch (error) {
    // ⚠️ **生产环境也必须记日志**。原先只有 `if (isDev) console.error(...)`：
    // 打包后核心起不来时，界面上只有一个永远转圈的加载态，日志里什么都没有 ——
    // "双击后打不开"这类问题因此完全无法排查（本机真实踩过）。
    const message = error instanceof Error ? error.message : String(error)
    logDesktop(`内置核心启动失败：${message}`)
    if (isDev) console.error('[desktop] 后端启动失败', error)
  }

  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) mainWindow = createWindow()
  })
}

// --------------------------------------------------------------------------- //
// IPC
// --------------------------------------------------------------------------- //

/**
 * 由建议的文件名推导「另存为」对话框的类型筛选。
 *
 * 只做一件事：把后缀提成一个筛选器，让用户在对话框里能一眼看出这是在存什么类型。
 * 取不到后缀（或后缀很奇怪）就给「所有文件」—— 宁可少一个筛选器，
 * 也不要出现一个空的下拉列表。
 */
function saveFilters(suggestedName: string): Electron.FileFilter[] {
  const extension = path.extname(suggestedName).replace(/^\./, '').toLowerCase()
  const filters: Electron.FileFilter[] = []
  if (/^[a-z0-9]{1,12}$/.test(extension)) {
    filters.push({ name: `${extension.toUpperCase()} 文件`, extensions: [extension] })
  }
  filters.push({ name: '所有文件', extensions: ['*'] })
  return filters
}

function registerIpc(): void {
  ipcMain.handle(IPC.backendInfo, async () => {
    if (!backend) throw new Error('后端管理器未初始化')
    return backend.start()
  })

  ipcMain.handle(IPC.backendStatus, async (): Promise<BackendStatus> => {
    if (!backend) return { state: 'failed', message: '后端管理器未初始化' }
    if (backend.current) return { state: 'ready', message: '智能体核心已就绪' }
    return { state: 'starting', message: '正在启动智能体核心…' }
  })

  ipcMain.handle(IPC.backendRestart, async () => {
    if (!backend) throw new Error('后端管理器未初始化')
    return backend.restart()
  })

  ipcMain.handle(IPC.backendLogs, async () => backend?.logs ?? [])

  ipcMain.handle(IPC.appInfo, async (): Promise<AppInfo> => {
    return {
      version: app.getVersion(),
      electronVersion: process.versions.electron,
      chromeVersion: process.versions.chrome,
      platform: process.platform,
      isDev,
      dataDir: app.getPath('userData'),
    }
  })

  ipcMain.on(IPC.titleBarTheme, (event, theme: WindowTheme) => {
    // 入参来自渲染层，先自查一遍类型再往下用。
    // ⚠️ 这里的校验曾经写成 `theme !== 'light' && theme !== 'dark'` ——
    // 于是**所有成品皮肤**（樱粉/暖阳/森野…）切过来时这段直接早退，
    // 标题栏与窗口底色都不跟随，这正是"切换皮肤后右上角没变"的根因。
    // 校验应该对准"是不是已知皮肤"，而不是"是不是 light/dark"。
    if (!isKnownTheme(theme)) return

    // 记在主进程侧，供下次启动的首帧使用。
    // 这一句刻意排在窗口存活判断**之前** —— 主题是全局偏好，
    // 不该因为某一刻窗口恰好不在（正在关闭、或还没创建）就丢掉。
    writePrefs({ theme })

    const win = BrowserWindow.fromWebContents(event.sender)
    if (!win || win.isDestroyed()) return

    // 底色不套 try：它在所有平台都支持，而且不同步的话，
    // 页面重绘的那一瞬间会从下面露出白底
    win.setBackgroundColor(windowBackground(theme))
  })

  // 自绘标题栏的窗口控制按钮（壁纸铺满标题栏后，系统 overlay 按钮已移除）。
  // 最小化 / 最大化直接操作窗口；关闭走 ``win.close()``，好让既有的
  // closeAction（询问 / 进托盘 / 退出）流程照常触发 —— 不能直接 destroy。
  ipcMain.on(IPC.windowMinimize, (event) => {
    BrowserWindow.fromWebContents(event.sender)?.minimize()
  })
  ipcMain.on(IPC.windowToggleMaximize, (event) => {
    const win = BrowserWindow.fromWebContents(event.sender)
    if (!win) return
    if (win.isMaximized()) win.unmaximize()
    else win.maximize()
  })

  /**
   * 把窗口恢复成**出厂默认大小**（产品要求）。
   *
   * ## 与 `windowToggleMaximize` 的区别（别把两者合并）
   *
   * `windowToggleMaximize` 的"还原"是 Windows 惯例的**反向操作**：最大化 ↔ 上一档
   * 普通尺寸（那个尺寸是用户自己拉的，Electron 自己记着）。
   * 这里则是**复位**：不管现在多大、是不是最大化，一律回到 `DEFAULT_WINDOW_SIZE`。
   * 两条语义不一样，所以是两个按钮、两条通道。
   *
   * ## 三个必须按顺序做的事
   *
   * 1. **先取消最大化 / 退出全屏** —— 最大化状态下调 `setBounds` 是**无效**的
   *    （窗口管理器会忽略尺寸，窗口纹丝不动）。不先做这一步，用户点"还原"会
   *    看起来"什么都没发生"。
   * 2. **按窗口当前所在那块屏夹取** —— 1366×768 在 1366 屏上要减掉任务栏，
   *    不夹就会把底部切掉（见 `fitToWorkArea`）。
   * 3. **位置也要收进工作区** —— 用户可能把窗口拖到屏幕右下角再点还原：尺寸变大后
   *    右/下会伸到屏幕外，用户只看到左上角一块，还得自己拖回来。所以这里算一个
   *    能被工作区完全容纳的左上角（**尽量不动用户的窗口位置**，只在装不下时才挪）。
   */
  ipcMain.on(IPC.windowResetSize, (event) => {
    const win = BrowserWindow.fromWebContents(event.sender)
    if (!win || win.isDestroyed()) return

    if (win.isFullScreen()) win.setFullScreen(false)
    if (win.isMaximized()) win.unmaximize()

    // 目标是**这个窗口自己的**出厂默认大小（主窗口 1366×768 / 独立对话窗 900×720 /
    // 群窗 780×680）—— 三种窗口都渲染同一个 `TitleBar`，所以都可能有这个按钮。
    // 查不到才退回主窗口那套（只有"从没登记过的窗口"会走到这里）。
    const fallback = windowDefaultSize.get(win) ?? DEFAULT_WINDOW_SIZE
    const current = win.getBounds()
    const size = fitToWorkArea(fallback.width, fallback.height, current)
    const area = screen.getDisplayMatching(current).workArea

    win.setBounds({
      // 位置：优先保持原地；右边/下边装不下时才往回收。
      x: Math.max(area.x, Math.min(current.x, area.x + area.width - size.width)),
      y: Math.max(area.y, Math.min(current.y, area.y + area.height - size.height)),
      width: size.width,
      height: size.height,
    })
  })

  ipcMain.on(IPC.windowClose, (event) => {
    BrowserWindow.fromWebContents(event.sender)?.close()
  })

  /**
   * 按增量算并应用新的窗口宽度。返回**是否真的动了窗口**。
   *
   * ## 三个约束（对两个入口都生效）
   *
   * 每个都对应一种"看起来能用、实际很别扭"的失败：
   * · **最大化 / 全屏时直接忽略** —— 那时改宽度没有意义，而且一旦 unmaximize
   *   用户会看到窗口莫名跳成小尺寸（我们没被要求做那件事）。
   * · **变宽不许越过屏幕工作区右边界**：窗口左边缘不动，所以只看 right ——
   *   越过去之后 Windows 不会自动挪回来，用户会看到窗口一半在屏幕外。
   * · **增量夹在 ±600**：渲染层传来的数字不可信（哪怕是我们自己传的），
   *   夹一下，免得一个 bug 把窗口拉成 3 万像素宽。
   *
   * ## 为什么抽成函数：它有两个入口，时序要求不同
   *
   * · `window:resize-by`（异步）—— 侧栏收起/展开（产品要求：
   *   收起侧栏应当**整体收窄窗口**，而不是把腾出的宽度让给对话栏）。
   *   那边没有"必须先变宽再渲染"的顺序要求，走异步、不阻塞界面。
   * · `window:resize-by-sync`（同步）—— 「链路与产物」抽屉。它要求窗口**先**
   *   变宽、抽屉**后**出现；异步版做不到这个顺序，中间那 1~3 帧里抽屉已经渲染、
   *   窗口还没变宽，于是对话栏被硬挤一下再展开，用户看成"整个客户端闪一下"
   *   （反馈）。详见 `AgentBridge.resizeWindowBySync`。
   */
  function applyWindowResizeBy(win: BrowserWindow | null, deltaWidth: unknown): boolean {
    if (!win || win.isDestroyed() || win.isMaximized() || win.isFullScreen()) return false

    const raw = typeof deltaWidth === 'number' && Number.isFinite(deltaWidth) ? deltaWidth : 0
    if (raw === 0) return false
    const delta = Math.max(-600, Math.min(600, Math.round(raw)))

    const bounds = win.getBounds()
    const workArea = screen.getDisplayMatching(bounds).workArea
    const maxWidth = Math.max(640, workArea.x + workArea.width - bounds.x)
    const nextWidth = Math.max(640, Math.min(maxWidth, bounds.width + delta))
    if (nextWidth === bounds.width) return false

    win.setBounds({ ...bounds, width: nextWidth })
    return true
  }

  /** 异步入口：侧栏收起/展开（不关心何时完成） */
  ipcMain.on(IPC.windowResizeBy, (event, deltaWidth: unknown) => {
    applyWindowResizeBy(BrowserWindow.fromWebContents(event.sender), deltaWidth)
  })

  /**
   * 同步入口：「链路与产物」抽屉（渲染层用 `sendSync` 调）。
   *
   * ⚠️ **每个分支都必须落到 `event.returnValue` 上**，否则渲染进程的
   * `sendSync` 会**永久阻塞**、整个界面直接冻死 —— 这是同步 IPC 唯一的、
   * 也是最严重的坑。所以这里不写"提前 return"，只做一次赋值。
   */
  ipcMain.on(IPC.windowResizeBySync, (event, deltaWidth: unknown) => {
    event.returnValue = applyWindowResizeBy(
      BrowserWindow.fromWebContents(event.sender),
      deltaWidth,
    )
  })

  // 打开（或聚焦）某个搭子的独立对话窗口
  ipcMain.handle(IPC.openChatWindow, (_event, assistantId: string, sessionId?: string) => {
    if (typeof assistantId !== 'string' || !assistantId) return false
    // sessionId 来自渲染层，先自查类型：非字符串一律当成"没指定"
    createChatWindow(assistantId, typeof sessionId === 'string' ? sessionId : '')
    return true
  })

  // 打开（或聚焦）某个群的独立窗口；observing=true 是只读观察窗
  ipcMain.handle(
    IPC.openGroupWindow,
    (_event, groupId: string, observing?: boolean, threadId?: string) => {
      if (typeof groupId !== 'string' || !groupId) return false
      // 只认显式 true：渲染层传来别的值（或没传）一律当"可操作窗"，
      // 默认给能力而不是默认剥夺 —— 用户手动打开时就是要能发言
      createGroupWindow(
        groupId,
        observing === true,
        // 非字符串一律当"没指定对话"，与 `sessionId` 那条同一套自查
        typeof threadId === 'string' ? threadId : '',
      )
      return true
    },
  )

  /**
   * 应用内关闭弹窗的回应。
   *
   * 只接受**当前正在等待回应的那个窗口**发来的回应：否则一个残留的 webContents
   * 就能凭一条消息把主窗口关掉。
   */
  ipcMain.on(IPC.closeAnswer, (event, payload: ClosePromptAnswer) => {
    const win = BrowserWindow.fromWebContents(event.sender)
    if (!win || win !== closePromptWindow) return

    if (payload?.action === 'cancel') {
      // 用户按了 Esc 或点了空白处：当作没点过 × —— 只清掉等待状态，
      // **不要**顺手把窗口关掉（那是模态框最容易被误解的行为）
      closePromptWindow = null
      logDesktop('用户取消了关闭')
      return
    }

    // 入参来自渲染层，动作只认 quit，其余一律按"最小化到托盘"处理
    settleCloseAction(win, payload?.action === 'quit' ? 'quit' : 'tray', Boolean(payload?.remember))
  })

  ipcMain.handle(IPC.desktopPrefsGet, async (): Promise<DesktopPrefs> => readPrefs())

  ipcMain.handle(
    IPC.desktopPrefsSet,
    async (_event, patch: Partial<DesktopPrefs>): Promise<DesktopPrefs> => {
      // 入参来自渲染层，逐字段自查后再落盘：不让意外字段混进偏好文件，
      // 否则下次读出来会是个半损坏的结构
      const clean: Partial<DesktopPrefs> = {}
      if (isKnownTheme(patch?.theme)) clean.theme = patch.theme
      if (
        patch?.closeAction === 'ask' ||
        patch?.closeAction === 'tray' ||
        patch?.closeAction === 'quit'
      ) {
        clean.closeAction = patch.closeAction
      }
      // 麦克风设备：只收字符串（空串 = 回到系统默认）。
      // ⚠️ 别放宽成"任何 truthy 都收"：渲染层传个对象进来就会把偏好文件写成半损坏结构。
      if (typeof patch?.micDeviceId === 'string') clean.micDeviceId = patch.micDeviceId
      return writePrefs(clean)
    },
  )

  ipcMain.handle(IPC.pickDirectory, async () => {
    if (!mainWindow) return null
    const result = await dialog.showOpenDialog(mainWindow, {
      properties: ['openDirectory', 'createDirectory'],
      title: '选择目录',
      // 默认定位到用户主目录，而不是"最近使用"：主目录下通常就是各个盘符与
      // 常用文件夹，用户从这里找目标目录最顺。Windows 原生对话框无法程序化
      // "强制展开我的电脑并列出盘符"（那是系统行为），这是能做到的最接近效果。
      defaultPath: app.getPath('home'),
    })
    return result.canceled || result.filePaths.length === 0 ? null : result.filePaths[0]
  })

  /**
   * 「选择文件」：与上面 `pickDirectory` 同一族，只是把 `openDirectory` 换成 `openFile`。
   *
   * 需求来自自动化任务的「文件有更新才执行」：那个输入框要的是**完整路径**，
   * 而普通用户不会自己去复制路径。不设 `filters` —— 要盯的文件可以是任何类型
   * （表格、日志、导出包），替用户先筛一遍只会让他找不到自己的文件。
   */
  ipcMain.handle(IPC.pickFile, async () => {
    if (!mainWindow) return null
    const result = await dialog.showOpenDialog(mainWindow, {
      properties: ['openFile'],
      title: '选择要盯的文件',
      defaultPath: app.getPath('home'),
    })
    return result.canceled || result.filePaths.length === 0 ? null : result.filePaths[0]
  })

  /**
   * 「另存为」：弹系统保存对话框 + 由主进程把产物写到用户选的位置。
   *
   * 这是本次**唯一**新增的 IPC 通道（42 → 43）。
   *
   * 为什么写盘放主进程而不是渲染层：
   * - 系统保存对话框只能在主进程弹（渲染层开着沙箱）；
   * - 渲染层是本项目明确的**不可信边界**（它要渲染模型输出与上传文件），
   *   把"写到任意路径"的能力开在它身上，等于把 `openPath` 那条教训再犯一遍；
   * - 字节由主进程**自己去核心取**（它本来就持有 baseUrl 与本地令牌），
   *   几十 MB 的产物不必走 IPC 传一遍，也不多占一份内存。
   */
  ipcMain.handle(
    IPC.saveFile,
    async (_event, payload: SaveArtifactRequest): Promise<SaveArtifactResult> => {
      if (!mainWindow) return { ok: false, error: '窗口已关闭，无法另存' }

      const fileId = typeof payload?.fileId === 'string' ? payload.fileId : ''
      if (!fileId) return { ok: false, error: '缺少文件标识' }
      const kind = payload?.kind === 'upload' ? 'upload' : 'artifact'
      const suggested =
        typeof payload?.suggestedName === 'string' && payload.suggestedName.trim()
          ? payload.suggestedName.trim()
          : fileId

      const picked = await dialog.showSaveDialog(mainWindow, {
        title: '另存为',
        // 默认落在「下载」目录并预填产物的原始名 —— 少了这个预填，
        // 用户每次都要自己敲一遍中文文件名
        defaultPath: path.join(app.getPath('downloads'), suggested),
        filters: saveFilters(suggested),
      })
      // **取消不是失败**：什么都不做、也不报错。把取消当失败弹一遍是最惹人烦的提示。
      if (picked.canceled || !picked.filePath) return { ok: false, cancelled: true }

      try {
        const info = await backend?.start()
        if (!info) return { ok: false, error: '智能体核心未就绪，请稍后重试' }
        const response = await coreFetch(
          info,
          `/v1/files/${encodeURIComponent(fileId)}?kind=${kind}`,
        )
        if (!response.ok) {
          return { ok: false, error: `读取产物失败（HTTP ${response.status}）` }
        }
        const buffer = Buffer.from(await response.arrayBuffer())
        await fs.promises.writeFile(picked.filePath, buffer)
        logDesktop(`已另存为：${path.basename(picked.filePath)}（${buffer.length} 字节）`)
        return { ok: true, path: picked.filePath }
      } catch (error) {
        const message = error instanceof Error ? error.message : String(error)
        logDesktop(`另存为失败：${message}`)
        return { ok: false, error: message }
      }
    },
  )

  ipcMain.handle(IPC.openPath, async (_event, target: string) => {
    if (!isOpenableTarget(target)) {
      // 渲染层拿到 false 足够让它不做任何事；这里额外记一行便于排查
      // "点了没反应"——否则这个分支是完全静默的。
      console.warn('[main] 已拒绝 openPath 请求:', String(target).slice(0, 200))
      return false
    }
    const error = await shell.openPath(target)
    return error === ''
  })

  ipcMain.handle(IPC.openExternal, async (_event, url: string) => {
    // 只允许 http/https，防止 file:// 或自定义协议被滥用
    if (typeof url !== 'string' || !/^https?:\/\//i.test(url)) return false
    await shell.openExternal(url)
    return true
  })

  // ---- 密钥 ---------------------------------------------------------- //
  // **只下发脱敏预览，不下发明文。**
  // 原先这里的注释写的是"渲染层需要能读到明文才能让用户编辑"，但实际上
  // 设置页从来不需要明文：保存走 saveSecrets 的增量合并，用户没碰过的条目
  // 原样保留。所以那个理由不成立，而下发明文的代价很实在 ——
  // 一次 XSS 或一个依赖漏洞就能把全部 Key 打包外传。
  ipcMain.handle(IPC.secretsMasked, async (): Promise<SecretsPayload> => {
    if (!secrets) return emptySecrets()
    return secrets.masked()
  })

  ipcMain.handle(IPC.secretsSave, async (_event, patch: SecretsPatch) => {
    if (!secrets) throw new Error('密钥存储未初始化')
    // 合并而非全量替换：渲染层只提交改过的条目
    return secrets.merge(patch)
  })

  // ---- 用户给技能的密钥（独立的一份文件，与上面的密钥库无关）---------- //
  //
  // ⚠️ 这一组**没有 reveal**：应用里没有任何界面能显示出它们的明文。
  // 那不是遗漏 —— 能看与能被偷看是同一件事，而这类密钥是用户主动粘贴进来的私钥。
  //
  // ⚠️ 与上面那组的另一个区别：**每次写入后要把新内容推给核心**（见下面
  // `pushSkillSecrets`）。原因见 `skill-secrets.ts` 的 `materialize()`：
  // 核心只在**启动时**读一次那个临时文件，运行期新增的它不知道。
  // 不推的话，用户粘贴完立刻让 AI 用它，AI 会说"本地没有这个密钥"。
  ipcMain.handle(IPC.skillSecretsGet, async (): Promise<SkillSecretsView> => {
    if (!skillSecrets) throw new Error('技能密钥存储未初始化')
    return skillSecrets.view()
  })

  ipcMain.handle(IPC.skillSecretsStatus, async (): Promise<SkillSecretsView> => {
    if (!skillSecrets) throw new Error('技能密钥存储未初始化')
    return skillSecrets.view()
  })

  ipcMain.handle(
    IPC.skillSecretsSave,
    async (_event, patch: SkillSecretsPatch): Promise<SkillSecretsView> => {
      if (!skillSecrets) throw new Error('技能密钥存储未初始化')
      const view = skillSecrets.mergeSave(patch ?? {})
      // ⚠️ 只记**名字**，绝不记值 —— 日志会被用户导出来排查问题
      logDesktop(`[skill-secrets] 已保存：${view.names.join(', ') || '(空)'}`)
      await pushSkillSecrets()
      return view
    },
  )

  ipcMain.handle(
    IPC.skillSecretsRemove,
    async (_event, names: string[]): Promise<SkillSecretsView> => {
      if (!skillSecrets) throw new Error('技能密钥存储未初始化')
      // 传空数组 = 清空全部（管理面板的「全部清空」走这条）
      const list = Array.isArray(names) ? names.map((item) => String(item)) : []
      const view = skillSecrets.remove(list)
      logDesktop(`[skill-secrets] 已删除 ${list.length} 条（传空=清空全部）`)
      await pushSkillSecrets()
      return view
    },
  )

  /**
   * 取单条密钥明文，供设置页的"小眼睛"查看。
   *
   * 这是本项目里**唯一**把明文交给渲染层的入口，所以刻意收窄成"一次只取一条"，
   * 并且每次都记一条日志。全量下发（整份密钥集合）会让一次 XSS 就能把用户
   * 所有 Key 打包外传，而"用户点名要看这一条"没有这个性质。
   */
  ipcMain.handle(IPC.secretsReveal, async (_event, target: RevealTarget): Promise<string> => {
    if (!secrets) return ''
    const value = secrets.reveal(target)
    if (value) {
      const scope = target?.modelId
        ? `model/${target.modelId}`
        : `mcp/${target?.mcpServer ?? '?'}/${target?.mcpVar ?? '?'}`
      logDesktop(`已向界面显示一条密钥明文（${scope}）`)
    }
    return value
  })

  // ---- 账号 / 充值 --------------------------------------------------- //
  // 凭据（device_secret / session_token）只活在引擎里，渲染层拿到的是**没有凭据**的
  // 快照；这里因此没有"取明文"的通道，也不需要给它留。
  const engine = (): AccountEngine => {
    if (!accountEngine) throw new Error('账号引擎未初始化')
    return accountEngine
  }

  ipcMain.handle(IPC.accountSnapshot, async (): Promise<AccountSnapshot> => engine().snapshot())

  ipcMain.handle(IPC.accountRefresh, async (): Promise<AccountSnapshot> => engine().refresh())

  ipcMain.handle(IPC.accountLineSet, async (_event, line: string): Promise<AccountSnapshot> => {
    if (line !== 'cn' && line !== 'seoul') throw new Error('线路取值不合法')
    return engine().setAccountLine(line)
  })

  ipcMain.handle(IPC.accountLineReprobe, async (): Promise<AccountSnapshot> => engine().reprobeLines())

  ipcMain.handle(IPC.accountLogin, async (_event, account: string, password: string) =>
    engine().loginAccount(String(account ?? ''), String(password ?? '')),
  )

  ipcMain.handle(IPC.accountSwitch, async (_event, id: number, password: string) =>
    engine().switchAccount(Number(id), String(password ?? '')),
  )

  ipcMain.handle(IPC.accountRename, async (_event, name: string, password: string) =>
    engine().renameAccount(String(name ?? ''), String(password ?? '')),
  )

  ipcMain.handle(IPC.accountSetPassword, async (_event, next: string, old: string) =>
    engine().setAccountPassword(String(next ?? ''), String(old ?? '')),
  )

  ipcMain.handle(IPC.accountRecover, async (_event, account: string, next: string) =>
    engine().recoverAccount(String(account ?? ''), String(next ?? '')),
  )

  ipcMain.handle(IPC.accountInvite, async (_event, code: string) =>
    engine().submitInviteCode(String(code ?? '')),
  )

  ipcMain.handle(IPC.accountWatch, async () => engine().watchRecharge())

  ipcMain.handle(IPC.accountWatchStop, async (): Promise<AccountSnapshot> =>
    engine().stopRechargeWatch(),
  )

  ipcMain.handle(IPC.accountOfflineAnswer, async (_event, mode: string): Promise<void> => {
    // 只认这两个取值：其它一律当"继续使用（离线）"（更保守的那个）
    await engine().answerOfflinePrompt(mode === 'skip' ? 'skip' : 'continue')
  })

  ipcMain.handle(IPC.accountCommission, async () => engine().getCommission())

  // 兑换码充值 Token：一次性核销，失败原因原样带回渲染层展示（不自动重试）
  ipcMain.handle(IPC.accountRedeem, async (_event, code: string) => engine().redeem(String(code)))

  ipcMain.handle(IPC.accountWxCreate, async (_event, amountYuan: number) =>
    engine().createWxRecharge(Number(amountYuan)),
  )

  ipcMain.handle(IPC.accountWxCancel, async (): Promise<AccountSnapshot> =>
    engine().cancelWxRecharge(),
  )

  // PayPal 充值（首尔专有）。结账窗口在 registerIpc 之外由 openPaypalCheckoutWindow 管理，
  // 这里只做"取配置 / 下单 / 取消"三件事的转发。
  ipcMain.handle(IPC.accountPaypalConfig, async () => engine().loadPaypalConfig())

  ipcMain.handle(IPC.accountPaypalCreate, async (_event, quantity: number) =>
    engine().createPaypalCheckout(Number(quantity)),
  )

  ipcMain.handle(IPC.accountPaypalCancel, async (): Promise<AccountSnapshot> =>
    engine().cancelPaypalCheckout(),
  )

  // 清掉上一次的 PayPal 提示（改数量 / 重新下单前）。写回完整快照，界面照常照单渲染。
  ipcMain.handle(IPC.accountPaypalDismiss, async (): Promise<AccountSnapshot> =>
    engine().dismissPaypalNotice(),
  )

  ipcMain.handle(
    IPC.accountWithdrawRmb,
    async (_event, payload: { amount: number; zhifubao: string; bank: string }) =>
      engine().withdrawRmb({
        amount: Number(payload?.amount),
        zhifubao: String(payload?.zhifubao ?? ''),
        bank: String(payload?.bank ?? ''),
      }),
  )

  ipcMain.handle(
    IPC.accountWithdrawUsdt,
    async (_event, payload: { amount: number; trc20_address: string }) =>
      engine().withdrawUsdt({
        amount: Number(payload?.amount),
        trc20_address: String(payload?.trc20_address ?? ''),
      }),
  )

  ipcMain.handle(IPC.secretsStatus, async () => {
    if (!secrets) {
      return { available: false, protection: 'plaintext' as const, path: '', count: 0 }
    }
    return secrets.status()
  })
}

// --------------------------------------------------------------------------- //
// 退出
// --------------------------------------------------------------------------- //
app.on('before-quit', (event) => {
  // 这一句必须排在早退**之前**：`before-quit` 也可能由系统发起（注销、关机、
  // 任务管理器"结束任务"），那条路不经过托盘菜单 —— 不在这里置位的话，
  // 窗口的 close 拦截会把系统关机一起卡住。
  forceQuit = true

  // 账号引擎有两个定时器（60 秒重试、盯单心跳）。进程退出后它们本来也不会再跑，
  // 但显式停掉能保证"退出途中不会突然又发出去一个网络请求"。
  accountEngine?.stop()

  // 窗口先消失（产品要求）：无论这次退出是用户点的、还是系统发起的，
  // 都不该让用户盯着窗口等 Python 核心收尾。
  for (const win of BrowserWindow.getAllWindows()) {
    if (!win.isDestroyed()) win.hide()
  }

  if (quitting || !backend?.hasProcess) return

  // 先拦一次退出，把 Python 进程收干净再真正退出
  event.preventDefault()
  quitting = true
  void backend.stop().finally(() => app.quit())
})

app.on('window-all-closed', () => {
  // 托盘模式下窗口只是 hide()，**不会**走到这里。能走到这里说明窗口是真的被销毁了
  // （用户在选择里点了退出、或系统强制关闭），此时不退出就会留下一个
  // "既没有窗口、也没有入口"的僵尸进程，所以照旧退出。
  app.quit()
})
