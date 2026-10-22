





import {
  BrowserWindow,
  Menu,
  Notification,
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
  type UpdateState,
  type WindowTheme,
} from '../shared/bridge'
import { AccountEngine } from './account/engine'
import { BackendManager, coreFetch } from './backend'
import { logDesktop } from './desktop-log'
import { SecretsStore, emptySecrets } from './secrets'
import { SkillSecretsStore } from './skill-secrets'
import { attachTextContextMenu } from './text-context-menu'
import {
  applyPendingAtBoot,
  applyUpdateNow,
  checkForUpdate,
  getUpdateState,
  initUpdater,
  onUpdateState,
  openFullPackage,
  setAutoUpdate,
  setUpdateLine,
} from './updater'















const NON_OPENABLE_EXTENSIONS = new Set([
  
  '.exe', '.com', '.bat', '.cmd', '.msi', '.scr', '.pif', '.gadget',
  
  '.ps1', '.psm1', '.psd1', '.vbs', '.vbe', '.js', '.jse', '.wsf', '.wsh',
  '.hta', '.jar', '.py', '.pyw', '.rb', '.pl', '.sh', '.bash', '.zsh', '.command',
  
  
  '.lnk', '.url', '.appref-ms', '.library-ms', '.search-ms', '.website',
  
  '.reg', '.inf', '.iso', '.vhd', '.vhdx', '.wim', '.msix', '.appx',
  
  '.dll', '.sys', '.drv', '.ocx', '.efi',
  
  '.scpt', '.scptd', '.osax', '.workflow', '.dylib', '.pkg', '.mpkg', '.kext',
  '.webloc', '.inetloc',
])








function isOpenableTarget(target: unknown): target is string {
  if (typeof target !== 'string' || target.trim() === '') return false
  
  
  
  if (!path.isAbsolute(target)) return false

  let stat: fs.Stats
  try {
    
    stat = fs.statSync(target)
  } catch {
    return false 
  }

  if (stat.isDirectory()) return true
  if (!stat.isFile()) return false 

  const ext = path.extname(target).toLowerCase()
  return !NON_OPENABLE_EXTENSIONS.has(ext)
}

const isDev = !app.isPackaged

let mainWindow: BrowserWindow | null = null
let backend: BackendManager | null = null
let secrets: SecretsStore | null = null







let skillSecrets: SkillSecretsStore | null = null
















async function pushSkillSecrets(): Promise<void> {
  const info = backend?.current
  
  
  
  if (!info) return
  const keys = skillSecrets?.load() ?? {}
  try {
    await coreFetch(info, '/v1/skill-secrets', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ keys }),
    })
  } catch (error: unknown) {
    
    
    
    logDesktop(
      `[skill-secrets] 推送给核心失败：${error instanceof Error ? error.message : String(error)}`,
    )
  }
}
 
let accountEngine: AccountEngine | null = null

let paypalWindow: BrowserWindow | null = null







let quitting = false

















const LEGACY_DATA_DIR_NAMES = ['Soulmate', 'AgentDesktop']

function migrateLegacyUserData(): void {
  const current = app.getPath('userData')
  for (const name of LEGACY_DATA_DIR_NAMES) {
    const legacy = path.join(app.getPath('appData'), name)
    if (legacy === current) continue
    
    
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




const gotLock = app.requestSingleInstanceLock()
if (!gotLock) {
  
  
  
  
  
  logDesktop('未取得单实例锁：已有实例在运行，本次启动直接退出')
  app.quit()
} else {
  logDesktop(`主进程启动（版本 ${app.getVersion()}，pid ${process.pid}，开发模式=${isDev}）`)

  app.on('second-instance', () => {
    
    
    
    logDesktop(`收到第二次启动请求（窗口=${describeMainWindow()}，退出中=${quitting}）`)

    if (mainWindow && !mainWindow.isDestroyed()) {
      
      
      restoreMainWindow()
      return
    }

    
    
    
    if (quitting) {
      
      
      logDesktop('正在退出流程中，忽略本次启动请求')
      return
    }
    mainWindow = createWindow()
    logDesktop('窗口不存在，已按启动请求重新创建')
  })

  void bootstrap()
}






const WINDOW_BACKGROUNDS: Record<string, string> = {
  light: '#ffffff',
  warm: '#fdf8f1',
  sakura: '#fffafc',
  mint: '#f7fdfa',
  sky: '#f7fbff',
  apricot: '#fffdf6',
  
  
  dark: '#16171a',
  forest: '#0f1512',
  ocean: '#0d131b',
  plum: '#14101b',
  pine: '#0e1311',
  charcoal: '#141414',
  deepday: '#f4f7ff',
  deepnight: '#06080f',
}







function windowBackground(theme: WindowTheme): string {
  return WINDOW_BACKGROUNDS[theme] ?? '#ffffff'
}




















const PREFS_FILE = 'desktop-prefs.json'

const LEGACY_THEME_FILE = 'window-theme.json'

function prefsPath(): string {
  return path.join(app.getPath('userData'), PREFS_FILE)
}








function isKnownTheme(value: unknown): value is WindowTheme {
  return typeof value === 'string' && value in WINDOW_BACKGROUNDS
}

function pickTheme(value: unknown, fallback: WindowTheme): WindowTheme {
  return isKnownTheme(value) ? value : fallback
}


function pickCloseAction(value: unknown): CloseAction {
  return value === 'tray' || value === 'quit' || value === 'ask' ? value : 'ask'
}








function pickMicDeviceId(value: unknown): string {
  return typeof value === 'string' ? value : ''
}

function readPrefs(): DesktopPrefs {
  
  
  
  
  
  const prefs: DesktopPrefs = {
    theme: 'deepday',
    closeAction: 'ask',
    
    micDeviceId: '',
    
    
    
    autoUpdate: true,
  }

  try {
    const raw = JSON.parse(fs.readFileSync(prefsPath(), 'utf-8')) as Partial<DesktopPrefs>
    prefs.theme = pickTheme(raw.theme, prefs.theme)
    prefs.closeAction = pickCloseAction(raw.closeAction)
    prefs.micDeviceId = pickMicDeviceId(raw.micDeviceId)
    
    prefs.autoUpdate = raw.autoUpdate !== false
    return prefs
  } catch {
    
  }

  try {
    const legacy = JSON.parse(
      fs.readFileSync(path.join(app.getPath('userData'), LEGACY_THEME_FILE), 'utf-8'),
    ) as { theme?: unknown }
    prefs.theme = pickTheme(legacy.theme, prefs.theme)
  } catch {
    
  }
  return prefs
}

function writePrefs(patch: Partial<DesktopPrefs>): DesktopPrefs {
  
  const next: DesktopPrefs = { ...readPrefs(), ...patch }
  try {
    fs.writeFileSync(prefsPath(), JSON.stringify(next, null, 2), 'utf-8')
  } catch {
    
  }
  return next
}







function describeMainWindow(): string {
  if (!mainWindow || mainWindow.isDestroyed()) return '不存在'
  return mainWindow.isVisible() ? '可见' : '存在但不可见'
}












const WINDOW_REVEAL_FALLBACK_MS = 300








const DEFAULT_WINDOW_SIZE = { width: 1366, height: 768 }







const MIN_WINDOW_SIZE = { width: 1040, height: 660 }













const windowDefaultSize = new WeakMap<BrowserWindow, { width: number; height: number }>()












function fitToWorkArea(
  width: number,
  height: number,
  bounds?: { x: number; y: number; width: number; height: number },
): { width: number; height: number } {
  const area = bounds
    ? screen.getDisplayMatching(bounds).workArea
    : screen.getPrimaryDisplay().workArea
  return {
    
    
    width: Math.max(MIN_WINDOW_SIZE.width, Math.min(width, area.width)),
    height: Math.max(MIN_WINDOW_SIZE.height, Math.min(height, area.height)),
  }
}


















function rendererIndexPath(): string {
  return app.isPackaged
    ? path.join(process.resourcesPath, 'dist', 'index.html')
    : path.join(__dirname, '../../dist/index.html')
}

function createWindow(): BrowserWindow {
  
  
  const initialTheme = readPrefs().theme
  











  const initialSize = fitToWorkArea(DEFAULT_WINDOW_SIZE.width, DEFAULT_WINDOW_SIZE.height)
  const win = new BrowserWindow({
    width: initialSize.width,
    height: initialSize.height,
    minWidth: MIN_WINDOW_SIZE.width,
    minHeight: MIN_WINDOW_SIZE.height,
    show: false,
    
    
    
    
    
    icon: path.join(__dirname, '../../assets/window.png'),
    backgroundColor: windowBackground(initialTheme),
    
    
    
    
    titleBarStyle: process.platform === 'darwin' ? 'hiddenInset' : 'hidden',
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
      
      
      
      
      
      
      sandbox: true,
      spellcheck: false,
    },
  })

  
  
  
  
  windowDefaultSize.set(win, initialSize)

  
  
  
  
  
  
  
  
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
    
    
    win.focus()
    logDesktop(`窗口已显示（${reason}，启动后 ${Date.now() - createdAt}ms）`)
  }

  revealTimer = setTimeout(() => reveal('兜底定时器'), WINDOW_REVEAL_FALLBACK_MS)
  win.once('ready-to-show', () => reveal('ready-to-show'))

  
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

  
  
  
  
  
  
  attachTextContextMenu(win)

  const devServer = process.env.VITE_DEV_SERVER_URL
  if (devServer) {
    void win.loadURL(devServer)
    win.webContents.openDevTools({ mode: 'detach' })
  } else {
    void win.loadFile(rendererIndexPath())
  }

  
  win.webContents.on('did-finish-load', () => {
    rendererReady.set(win.webContents, true)
  })
  win.webContents.on('render-process-gone', () => {
    rendererReady.set(win.webContents, false)
  })

  win.on('close', (event) => {
    
    
    
    if (forceQuit) return

    
    const { closeAction } = readPrefs()

    if (closeAction === 'tray') {
      event.preventDefault()
      hideToTray(win)
      return
    }

    if (closeAction === 'quit') {
      
      return
    }

    
    event.preventDefault()
    void askCloseAction(win)
  })

  win.on('closed', () => {
    
    if (revealTimer) clearTimeout(revealTimer)
    mainWindow = null
  })
  return win
}





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
    
    titleBarStyle: 'hidden',
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
      spellcheck: false,
      
      additionalArguments: [
        `--window-mode=chat`,
        `--assistant-id=${assistantId}`,
        `--session-id=${sessionId}`,
      ],
    },
  })
  
  
  
  windowDefaultSize.set(win, { width: 900, height: 720 })
  chatWindows.set(key, win)

  wireSecondaryWindow(win, {
    onClosed: () => chatWindows.delete(key),
  })
}








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

  
  
  
  attachTextContextMenu(win)

  const devServer = process.env.VITE_DEV_SERVER_URL
  if (devServer) void win.loadURL(devServer)
  
  else void win.loadFile(rendererIndexPath())

  win.once('ready-to-show', () => {
    
    
    
    if (options.inactive) win.showInactive()
    else {
      win.show()
      win.focus()
    }
  })
  win.on('closed', options.onClosed)
}





















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
      
      additionalArguments: [
        '--window-mode=group',
        `--group-id=${groupId}`,
        `--group-readonly=${observing ? '1' : '0'}`,
        
        `--group-thread=${threadId}`,
      ],
    },
  })
  
  windowDefaultSize.set(win, { width: 780, height: 680 })
  groupWindows.set(key, { win, observing })

  wireSecondaryWindow(win, {
    onClosed: () => groupWindows.delete(key),
    inactive: observing,
  })
}











let forceQuit = false

let tray: Tray | null = null

let trayNoticeShown = false






let closePromptWindow: BrowserWindow | null = null











const rendererReady = new WeakMap<WebContents, boolean>()

function trayIconPath(): string {
  
  return path.join(__dirname, '../../assets/tray.png')
}









function ensureTray(): Tray | null {
  if (tray && !tray.isDestroyed()) return tray
  try {
    const image = nativeImage.createFromPath(trayIconPath())
    if (image.isEmpty()) {
      logDesktop('托盘图标为空（assets/tray.png 没打进包？），本次不创建托盘')
      return null
    }
    if (process.platform === 'darwin') {
      
      
      image.setTemplateImage(true)
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
    
    tray.on('click', () => restoreMainWindow())
    logDesktop('托盘已创建')
    return tray
  } catch (error) {
    logDesktop(`创建托盘失败：${String(error)}`)
    tray = null
    return null
  }
}


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








function notifyFirstHide(): void {
  if (trayNoticeShown) return
  trayNoticeShown = true
  try {
    if (process.platform === 'darwin') {
      
      new Notification({
        title: 'Soulmate Agent 仍在后台运行',
        body: '点击 Dock 图标即可重新打开；从菜单栏图标右键可以彻底退出。',
      }).show()
      return
    }
    ensureTray()?.displayBalloon({
      title: 'Soulmate Agent 仍在后台运行',
      content: '双击桌面图标、或点托盘图标即可重新打开；右键托盘图标可以彻底退出。',
    })
  } catch {
    
  }
}

function hideToTray(win: BrowserWindow): void {
  if (!ensureTray()) {
    
    
    logDesktop('托盘不可用，改为直接退出')
    quitApp()
    return
  }
  win.hide()
  logDesktop('窗口已最小化到托盘')
  notifyFirstHide()
}






function isPaypalUrl(target: string): boolean {
  try {
    const host = new URL(target).hostname.toLowerCase()
    return host === 'paypal.com' || host.endsWith('.paypal.com')
  } catch {
    return false
  }
}


function closePaypalCheckoutWindow(): void {
  const win = paypalWindow
  paypalWindow = null
  if (win && !win.isDestroyed()) win.close()
}










function openPaypalCheckoutWindow(url: string): void {
  closePaypalCheckoutWindow()
  const win = new BrowserWindow({
    width: 460,
    height: 720,
    show: true,
    title: 'PayPal 充值',
    autoHideMenuBar: true,
    webPreferences: {
      
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
    
    
    if (isPaypalUrl(target)) return
    event.preventDefault()
    if (/^https?:\/\//i.test(target)) void shell.openExternal(target)
  })

  win.on('closed', () => {
    
    
    
    
    
    if (paypalWindow !== win) return
    paypalWindow = null
    
    accountEngine?.handlePaypalWindowClosed()
  })

  void win.loadURL(url)
}

function quitApp(): void {
  forceQuit = true
  
  
  
  
  for (const win of BrowserWindow.getAllWindows()) {
    if (!win.isDestroyed()) win.hide()
  }
  app.quit()
}


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













async function askCloseAction(win: BrowserWindow): Promise<void> {
  
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
    
    settleCloseAction(win, response === 1 ? 'quit' : 'tray', checkboxChecked)
  } catch (error) {
    
    
    logDesktop(`原生关闭对话框失败：${String(error)}，默认最小化到托盘`)
    hideToTray(win)
  }
}




async function bootstrap(): Promise<void> {
  
  
  
  
  const t0 = Date.now()
  const mark = (step: string) =>
    logDesktop(`启动步骤：${step}（累计 ${((Date.now() - t0) / 1000).toFixed(1)}s）`)

  await app.whenReady()
  mark('app.whenReady')

  
  
  
  
  try {
    applyPendingAtBoot()
  } catch (error) {
    logDesktop(`[update] 启动时应用更新失败：${String(error)}`)
  }

  
  
  
  await session.defaultSession.setProxy({ mode: 'direct' })
  mark('关闭代理')

  
  
  if (!isDev) Menu.setApplicationMenu(null)

  
  secrets = new SecretsStore()
  
  
  const migrated = secrets.migrateFromConfigFiles(path.join(app.getPath('userData'), 'config'))
  const secretsStatus = secrets.status()
  console.log(
    `[secrets] 保护方式=${secretsStatus.protection} 条目=${secretsStatus.count}` +
      (migrated > 0 ? ` 迁移=${migrated}` : ''),
  )
  
  skillSecrets = new SkillSecretsStore()
  mark('技能密钥存储就绪')

  backend = new BackendManager(app.getPath('userData'), secrets, skillSecrets)
  backend.onStatus = (status: BackendStatus) => {
    
    
    for (const win of BrowserWindow.getAllWindows()) {
      if (!win.isDestroyed()) win.webContents.send(IPC.backendStatusEvent, status)
    }
  }
  backend.onLog = (line, stream) => {
    if (isDev && stream === 'stderr') console.log(`[core] ${line}`)
  }

  
  
  
  const pushSession = (token: string): void => {
    const info = backend?.current
    
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

  
  
  
  
  
  accountEngine = new AccountEngine(
    (snapshot: AccountSnapshot) => {
      for (const win of BrowserWindow.getAllWindows()) {
        if (!win.isDestroyed()) win.webContents.send(IPC.accountChangedEvent, snapshot)
      }
    },
    
    { open: openPaypalCheckoutWindow, close: closePaypalCheckoutWindow },
    
    { push: pushSession },
  )

  registerIpc()
  mainWindow = createWindow()
  mark('窗口已创建')

  accountEngine.start()

  
  try {
    await backend.start()
    mark('内置核心已就绪')
    
    
    accountEngine?.syncSession()
  } catch (error) {
    
    
    
    const message = error instanceof Error ? error.message : String(error)
    logDesktop(`内置核心启动失败：${message}`)
    if (isDev) console.error('[desktop] 后端启动失败', error)
  }

  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) mainWindow = createWindow()
  })
}












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
    
    
    
    
    
    if (!isKnownTheme(theme)) return

    
    
    
    writePrefs({ theme })

    const win = BrowserWindow.fromWebContents(event.sender)
    if (!win || win.isDestroyed()) return

    
    
    win.setBackgroundColor(windowBackground(theme))
  })

  
  
  
  ipcMain.on(IPC.windowMinimize, (event) => {
    BrowserWindow.fromWebContents(event.sender)?.minimize()
  })
  ipcMain.on(IPC.windowToggleMaximize, (event) => {
    const win = BrowserWindow.fromWebContents(event.sender)
    if (!win) return
    if (win.isMaximized()) win.unmaximize()
    else win.maximize()
  })

  




















  ipcMain.on(IPC.windowResetSize, (event) => {
    const win = BrowserWindow.fromWebContents(event.sender)
    if (!win || win.isDestroyed()) return

    if (win.isFullScreen()) win.setFullScreen(false)
    if (win.isMaximized()) win.unmaximize()

    
    
    
    const fallback = windowDefaultSize.get(win) ?? DEFAULT_WINDOW_SIZE
    const current = win.getBounds()
    const size = fitToWorkArea(fallback.width, fallback.height, current)
    const area = screen.getDisplayMatching(current).workArea

    win.setBounds({
      
      x: Math.max(area.x, Math.min(current.x, area.x + area.width - size.width)),
      y: Math.max(area.y, Math.min(current.y, area.y + area.height - size.height)),
      width: size.width,
      height: size.height,
    })
  })

  ipcMain.on(IPC.windowClose, (event) => {
    BrowserWindow.fromWebContents(event.sender)?.close()
  })

  






















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

  
  ipcMain.on(IPC.windowResizeBy, (event, deltaWidth: unknown) => {
    applyWindowResizeBy(BrowserWindow.fromWebContents(event.sender), deltaWidth)
  })

  






  ipcMain.on(IPC.windowResizeBySync, (event, deltaWidth: unknown) => {
    event.returnValue = applyWindowResizeBy(
      BrowserWindow.fromWebContents(event.sender),
      deltaWidth,
    )
  })

  
  ipcMain.handle(IPC.openChatWindow, (_event, assistantId: string, sessionId?: string) => {
    if (typeof assistantId !== 'string' || !assistantId) return false
    
    createChatWindow(assistantId, typeof sessionId === 'string' ? sessionId : '')
    return true
  })

  
  ipcMain.handle(
    IPC.openGroupWindow,
    (_event, groupId: string, observing?: boolean, threadId?: string) => {
      if (typeof groupId !== 'string' || !groupId) return false
      
      
      createGroupWindow(
        groupId,
        observing === true,
        
        typeof threadId === 'string' ? threadId : '',
      )
      return true
    },
  )

  





  ipcMain.on(IPC.closeAnswer, (event, payload: ClosePromptAnswer) => {
    const win = BrowserWindow.fromWebContents(event.sender)
    if (!win || win !== closePromptWindow) return

    if (payload?.action === 'cancel') {
      
      
      closePromptWindow = null
      logDesktop('用户取消了关闭')
      return
    }

    
    settleCloseAction(win, payload?.action === 'quit' ? 'quit' : 'tray', Boolean(payload?.remember))
  })

  
  
  ipcMain.handle(IPC.updateState, async (): Promise<UpdateState> => getUpdateState())
  ipcMain.handle(IPC.updateCheck, async (): Promise<UpdateState> => checkForUpdate())
  ipcMain.handle(IPC.updateApplyNow, async (): Promise<UpdateState> => applyUpdateNow())
  ipcMain.handle(IPC.updateOpenFull, async (): Promise<void> => openFullPackage())

  
  onUpdateState((next) => {
    for (const win of BrowserWindow.getAllWindows()) {
      if (!win.isDestroyed()) win.webContents.send(IPC.updateStateEvent, next)
    }
  })

  
  
  
  initUpdater({ autoUpdate: readPrefs().autoUpdate })

  ipcMain.handle(IPC.desktopPrefsGet, async (): Promise<DesktopPrefs> => readPrefs())

  ipcMain.handle(
    IPC.desktopPrefsSet,
    async (_event, patch: Partial<DesktopPrefs>): Promise<DesktopPrefs> => {
      
      
      const clean: Partial<DesktopPrefs> = {}
      if (isKnownTheme(patch?.theme)) clean.theme = patch.theme
      if (
        patch?.closeAction === 'ask' ||
        patch?.closeAction === 'tray' ||
        patch?.closeAction === 'quit'
      ) {
        clean.closeAction = patch.closeAction
      }
      
      
      if (typeof patch?.micDeviceId === 'string') clean.micDeviceId = patch.micDeviceId
      
      
      if (typeof patch?.autoUpdate === 'boolean') clean.autoUpdate = patch.autoUpdate
      const saved = writePrefs(clean)
      if (typeof patch?.autoUpdate === 'boolean') setAutoUpdate(patch.autoUpdate)
      return saved
    },
  )

  ipcMain.handle(IPC.pickDirectory, async () => {
    if (!mainWindow) return null
    const result = await dialog.showOpenDialog(mainWindow, {
      properties: ['openDirectory', 'createDirectory'],
      title: '选择目录',
      
      
      
      defaultPath: app.getPath('home'),
    })
    return result.canceled || result.filePaths.length === 0 ? null : result.filePaths[0]
  })

  






  ipcMain.handle(IPC.pickFile, async () => {
    if (!mainWindow) return null
    const result = await dialog.showOpenDialog(mainWindow, {
      properties: ['openFile'],
      title: '选择要盯的文件',
      defaultPath: app.getPath('home'),
    })
    return result.canceled || result.filePaths.length === 0 ? null : result.filePaths[0]
  })

  











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
        
        
        defaultPath: path.join(app.getPath('downloads'), suggested),
        filters: saveFilters(suggested),
      })
      
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
      
      
      console.warn('[main] 已拒绝 openPath 请求:', String(target).slice(0, 200))
      return false
    }
    const error = await shell.openPath(target)
    return error === ''
  })

  ipcMain.handle(IPC.openExternal, async (_event, url: string) => {
    
    if (typeof url !== 'string' || !/^https?:\/\//i.test(url)) return false
    await shell.openExternal(url)
    return true
  })

  
  
  
  
  
  
  ipcMain.handle(IPC.secretsMasked, async (): Promise<SecretsPayload> => {
    if (!secrets) return emptySecrets()
    return secrets.masked()
  })

  ipcMain.handle(IPC.secretsSave, async (_event, patch: SecretsPatch) => {
    if (!secrets) throw new Error('密钥存储未初始化')
    
    return secrets.merge(patch)
  })

  
  
  
  
  
  
  
  
  
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
      
      logDesktop(`[skill-secrets] 已保存：${view.names.join(', ') || '(空)'}`)
      await pushSkillSecrets()
      return view
    },
  )

  ipcMain.handle(
    IPC.skillSecretsRemove,
    async (_event, names: string[]): Promise<SkillSecretsView> => {
      if (!skillSecrets) throw new Error('技能密钥存储未初始化')
      
      const list = Array.isArray(names) ? names.map((item) => String(item)) : []
      const view = skillSecrets.remove(list)
      logDesktop(`[skill-secrets] 已删除 ${list.length} 条（传空=清空全部）`)
      await pushSkillSecrets()
      return view
    },
  )

  






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

  
  
  
  const engine = (): AccountEngine => {
    if (!accountEngine) throw new Error('账号引擎未初始化')
    return accountEngine
  }

  ipcMain.handle(IPC.accountSnapshot, async (): Promise<AccountSnapshot> => engine().snapshot())

  ipcMain.handle(IPC.accountRefresh, async (): Promise<AccountSnapshot> => engine().refresh())

  ipcMain.handle(IPC.accountLineSet, async (_event, line: string): Promise<AccountSnapshot> => {
    if (line !== 'cn' && line !== 'seoul') throw new Error('线路取值不合法')
    const snapshot = await engine().setAccountLine(line)
    
    setUpdateLine(line)
    return snapshot
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
    
    await engine().answerOfflinePrompt(mode === 'skip' ? 'skip' : 'continue')
  })

  ipcMain.handle(IPC.accountCommission, async () => engine().getCommission())

  
  ipcMain.handle(IPC.accountRedeem, async (_event, code: string) => engine().redeem(String(code)))

  ipcMain.handle(IPC.accountWxCreate, async (_event, amountYuan: number) =>
    engine().createWxRecharge(Number(amountYuan)),
  )

  ipcMain.handle(IPC.accountWxCancel, async (): Promise<AccountSnapshot> =>
    engine().cancelWxRecharge(),
  )

  
  
  ipcMain.handle(IPC.accountPaypalConfig, async () => engine().loadPaypalConfig())

  ipcMain.handle(IPC.accountPaypalCreate, async (_event, quantity: number) =>
    engine().createPaypalCheckout(Number(quantity)),
  )

  ipcMain.handle(IPC.accountPaypalCancel, async (): Promise<AccountSnapshot> =>
    engine().cancelPaypalCheckout(),
  )

  
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




app.on('before-quit', (event) => {
  
  
  
  forceQuit = true

  
  
  accountEngine?.stop()

  
  
  for (const win of BrowserWindow.getAllWindows()) {
    if (!win.isDestroyed()) win.hide()
  }

  if (quitting || !backend?.hasProcess) return

  
  event.preventDefault()
  quitting = true
  void backend.stop().finally(() => app.quit())
})

app.on('window-all-closed', () => {
  if (process.platform === 'darwin') {
    
    
    return
  }
  
  
  
  app.quit()
})
