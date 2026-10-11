/**
 * 受限 IPC 桥。
 *
 * 只暴露白名单方法，不把 ipcRenderer / require 直接给渲染层，
 * 这样即使渲染层被注入恶意脚本，也无法调用任意 IPC 通道。
 *
 * ⚠️ 本文件**必须保持自包含**：只能 import `electron` 和 `import type`，
 * 不能从别的文件做**值导入**。
 *
 * 理由是渲染进程开着沙箱（见 main.ts 的 webPreferences.sandbox），而沙箱化
 * preload 的 `require` 是一个**受限 polyfill** —— 它只能解析 `electron` 与少数
 * 内置模块（events / timers / url），**解析不了用户自己的文件**。一旦这里从
 * shared/bridge 做值导入，编译产物里就会留下一条指向同级目录的 require
 * （build:electron 只跑 tsc、不做打包，所以这条 require 会原样留下），
 * preload 会在执行到下面 `contextBridge.exposeInMainWorld` **之前**就抛错退出。
 *
 * 后果属于最难查的那一类：`window.agentBridge` 整个不存在，界面第一个 IPC 调用
 * 就崩在 "Cannot read properties of undefined" 上，而错误信息里完全看不出真正
 * 的原因（实际发生过一次，现场把排查方向误带到了「Python 依赖未安装」）。
 *
 * 所以通道名在下面**内联**了一份。类型用 `import type` 是安全的 ——
 * 它在编译后会被完全擦除，不产生任何 require。
 *
 * 两份通道名的一致性由 scripts/verify-packaged-app.mjs 静态守着：
 * 只改一边会让验收直接失败，不会静默漂移。
 */
import { contextBridge, ipcRenderer } from 'electron'

import type { AccountSnapshot, AgentBridge, BackendStatus, WindowArgs } from '../shared/bridge'

/**
 * 解析主进程通过 ``additionalArguments`` 注入的窗口角色参数。
 * 沙箱化 preload 里 ``process`` 是受限 polyfill，但 ``process.argv`` 可用。
 */
function readWindowArgs(): WindowArgs {
  const pick = (name: string): string => {
    const prefix = `--${name}=`
    const found = process.argv.find((item) => item.startsWith(prefix))
    return found ? found.slice(prefix.length) : ''
  }
  const rawMode = pick('window-mode')
  const mode = rawMode === 'chat' || rawMode === 'group' ? rawMode : 'main'
  return {
    mode,
    assistantId: pick('assistant-id'),
    sessionId: pick('session-id'),
    groupId: pick('group-id'),
    threadId: pick('group-thread'),
    // 只认显式的 '1'：没传 / 传了别的值一律当"可操作"，**默认给能力**而不是默认剥夺
    readonly: pick('group-readonly') === '1',
  }
}
const windowArgs = readWindowArgs()

/** IPC 通道名。**必须与 shared/bridge.ts 的 IPC 逐项一致**（验收脚本会比对）。 */
const IPC = {
  backendInfo: 'backend:info',
  backendStatus: 'backend:status',
  backendStatusEvent: 'backend:status-event',
  backendRestart: 'backend:restart',
  backendLogs: 'backend:logs',
  appInfo: 'app:info',
  titleBarTheme: 'window:titlebar-theme',
  closePrompt: 'window:close-prompt',
  closeAnswer: 'window:close-answer',
  windowMinimize: 'window:minimize',
  windowToggleMaximize: 'window:toggle-maximize',
  /** 恢复出厂默认大小（见 `AgentBridge.resetWindowSize`） */
  windowResetSize: 'window:reset-size',
  windowClose: 'window:close',
  /**
   * 按增量调整窗口宽度（收起/展开侧栏时用）。
   *
   * ⚠️ 为什么需要它：侧栏收起时**不该让对话栏变宽**（产品要求）。
   * 那样等于"收起侧栏 = 换了一屏内容"，用户眼前的排版会整体重排一次。
   * 正确的做法是把窗口本身收窄同样多 —— 视觉上那一块是"被移走了"，而不是
   * "被摊给了别人"。这必须由主进程做：渲染进程改不了窗口尺寸。
   */
  windowResizeBy: 'window:resize-by',
  /**
   * 同步版（见 AgentBridge.resizeWindowBySync）。
   *
   * ⚠️ 本文件**必须**内联一份与 `shared/bridge.ts` 同名的常量：沙箱化 preload
   * 无法 `require` 相对路径，值导入会让它在注入 contextBridge 之前就抛错
   * （后果是 `window.agentBridge` 整个不存在）。两份由
   * `scripts/verify-packaged-app.mjs` 比对，所以改这里**必须同步改那边**。
   */
  windowResizeBySync: 'window:resize-by-sync',
  openChatWindow: 'window:open-chat',
  openGroupWindow: 'window:open-group',
  pickDirectory: 'dialog:pick-directory',
  pickFile: 'dialog:pick-file',
  saveFile: 'dialog:save-file',
  openPath: 'shell:open-path',
  openExternal: 'shell:open-external',
  desktopPrefsGet: 'desktop:prefs-get',
  desktopPrefsSet: 'desktop:prefs-set',
  secretsMasked: 'secrets:masked',
  secretsSave: 'secrets:save',
  secretsStatus: 'secrets:status',
  secretsReveal: 'secrets:reveal',
  /** 用户给技能的密钥（独立文件；必须与 shared/bridge.ts 逐项一致） */
  skillSecretsGet: 'skillsecrets:get',
  skillSecretsSave: 'skillsecrets:save',
  skillSecretsRemove: 'skillsecrets:remove',
  skillSecretsStatus: 'skillsecrets:status',
  accountSnapshot: 'account:snapshot',
  accountRefresh: 'account:refresh',
  accountLineSet: 'account:line-set',
  accountLineReprobe: 'account:line-reprobe',
  accountLogin: 'account:login',
  accountSwitch: 'account:switch',
  accountRename: 'account:rename',
  accountSetPassword: 'account:set-password',
  accountRecover: 'account:recover',
  accountInvite: 'account:invite',
  accountWatch: 'account:watch',
  accountWatchStop: 'account:watch-stop',
  accountOfflineAnswer: 'account:offline-answer',
  accountCommission: 'account:commission',
  accountRedeem: 'account:redeem',
  accountWxCreate: 'account:wx-create',
  accountWxCancel: 'account:wx-cancel',
  accountPaypalConfig: 'account:paypal-config',
  accountPaypalCreate: 'account:paypal-create',
  accountPaypalCancel: 'account:paypal-cancel',
  accountPaypalDismiss: 'account:paypal-dismiss',
  accountWithdrawRmb: 'account:withdraw-rmb',
  accountWithdrawUsdt: 'account:withdraw-usdt',
  accountChangedEvent: 'account:changed',
} as const

const bridge: AgentBridge = {
  getBackendInfo: () => ipcRenderer.invoke(IPC.backendInfo),
  getBackendStatus: () => ipcRenderer.invoke(IPC.backendStatus),
  restartBackend: () => ipcRenderer.invoke(IPC.backendRestart),
  getBackendLogs: () => ipcRenderer.invoke(IPC.backendLogs),
  getAppInfo: () => ipcRenderer.invoke(IPC.appInfo),
  setTitleBarTheme: (theme) => ipcRenderer.send(IPC.titleBarTheme, theme),
  minimizeWindow: () => ipcRenderer.send(IPC.windowMinimize),
  toggleMaximizeWindow: () => ipcRenderer.send(IPC.windowToggleMaximize),
  /** 恢复出厂默认大小（不是"取消最大化"——见 `shared/bridge.ts` 的对比说明） */
  resetWindowSize: () => ipcRenderer.send(IPC.windowResetSize),
  closeWindow: () => ipcRenderer.send(IPC.windowClose),
  /** 按增量改窗口宽度（侧栏收起/展开时用）。正数变宽、负数变窄。 */
  resizeWindowBy: (deltaWidth) => ipcRenderer.send(IPC.windowResizeBy, deltaWidth),
  /**
   * 同步版：等主进程真的改完窗口宽度才返回。
   *
   * 只给「链路与产物」抽屉用 —— 它要求"窗口先变宽、抽屉再出现"，
   * 异步版做不到这个顺序，中间几帧会被用户看成闪屏。理由详见
   * `shared/bridge.ts` 的 `AgentBridge.resizeWindowBySync`。
   */
  resizeWindowBySync: (deltaWidth) => ipcRenderer.sendSync(IPC.windowResizeBySync, deltaWidth),
  getWindowArgs: () => windowArgs,
  openChatWindow: (assistantId, sessionId) =>
    ipcRenderer.invoke(IPC.openChatWindow, assistantId, sessionId ?? ''),
  openGroupWindow: (groupId, observing, threadId) =>
    ipcRenderer.invoke(IPC.openGroupWindow, groupId, observing === true, threadId ?? ''),
  pickDirectory: () => ipcRenderer.invoke(IPC.pickDirectory),
  pickFile: () => ipcRenderer.invoke(IPC.pickFile),
  saveArtifactAs: (payload) => ipcRenderer.invoke(IPC.saveFile, payload),
  openPath: (target) => ipcRenderer.invoke(IPC.openPath, target),
  openExternal: (url) => ipcRenderer.invoke(IPC.openExternal, url),
  onBackendStatus: (callback) => {
    const listener = (_event: unknown, status: BackendStatus) => callback(status)
    ipcRenderer.on(IPC.backendStatusEvent, listener)
    return () => {
      ipcRenderer.removeListener(IPC.backendStatusEvent, listener)
    }
  },
  onClosePrompt: (callback) => {
    const listener = () => callback()
    ipcRenderer.on(IPC.closePrompt, listener)
    return () => {
      ipcRenderer.removeListener(IPC.closePrompt, listener)
    }
  },
  answerClosePrompt: (answer) => ipcRenderer.send(IPC.closeAnswer, answer),
  getDesktopPrefs: () => ipcRenderer.invoke(IPC.desktopPrefsGet),
  setDesktopPrefs: (patch) => ipcRenderer.invoke(IPC.desktopPrefsSet, patch),
  getSecretsMasked: () => ipcRenderer.invoke(IPC.secretsMasked),
  saveSecrets: (payload) => ipcRenderer.invoke(IPC.secretsSave, payload),
  getSecretsStatus: () => ipcRenderer.invoke(IPC.secretsStatus),
  revealSecret: (target) => ipcRenderer.invoke(IPC.secretsReveal, target),
  // 用户给技能的密钥：注意**没有** reveal —— 应用里没有任何界面能显示它们的内容
  getSkillSecrets: () => ipcRenderer.invoke(IPC.skillSecretsGet),
  saveSkillSecrets: (patch) => ipcRenderer.invoke(IPC.skillSecretsSave, patch),
  removeSkillSecrets: (names) => ipcRenderer.invoke(IPC.skillSecretsRemove, names),
  getSkillSecretsStatus: () => ipcRenderer.invoke(IPC.skillSecretsStatus),
  getAccountSnapshot: () => ipcRenderer.invoke(IPC.accountSnapshot),
  refreshAccount: () => ipcRenderer.invoke(IPC.accountRefresh),
  setAccountLine: (line) => ipcRenderer.invoke(IPC.accountLineSet, line),
  reprobeAccountLine: () => ipcRenderer.invoke(IPC.accountLineReprobe),
  loginAccount: (account, password) => ipcRenderer.invoke(IPC.accountLogin, account, password),
  switchAccount: (id, password) => ipcRenderer.invoke(IPC.accountSwitch, id, password),
  renameAccount: (name, password) => ipcRenderer.invoke(IPC.accountRename, name, password),
  setAccountPassword: (next, old) => ipcRenderer.invoke(IPC.accountSetPassword, next, old),
  recoverAccount: (account, next) => ipcRenderer.invoke(IPC.accountRecover, account, next),
  submitInviteCode: (code) => ipcRenderer.invoke(IPC.accountInvite, code),
  watchRecharge: () => ipcRenderer.invoke(IPC.accountWatch),
  stopRechargeWatch: () => ipcRenderer.invoke(IPC.accountWatchStop),
  answerOfflinePrompt: (mode) => ipcRenderer.invoke(IPC.accountOfflineAnswer, mode),
  getAccountCommission: () => ipcRenderer.invoke(IPC.accountCommission),
  redeemCode: (code) => ipcRenderer.invoke(IPC.accountRedeem, code),
  createWxRecharge: (amountYuan) => ipcRenderer.invoke(IPC.accountWxCreate, amountYuan),
  cancelWxRecharge: () => ipcRenderer.invoke(IPC.accountWxCancel),
  getPaypalConfig: () => ipcRenderer.invoke(IPC.accountPaypalConfig),
  createPaypalCheckout: (quantity) => ipcRenderer.invoke(IPC.accountPaypalCreate, quantity),
  cancelPaypalCheckout: () => ipcRenderer.invoke(IPC.accountPaypalCancel),
  dismissPaypalNotice: () => ipcRenderer.invoke(IPC.accountPaypalDismiss),
  withdrawRmb: (payload) => ipcRenderer.invoke(IPC.accountWithdrawRmb, payload),
  withdrawUsdt: (payload) => ipcRenderer.invoke(IPC.accountWithdrawUsdt, payload),
  onAccountChanged: (callback) => {
    const listener = (_event: unknown, snapshot: AccountSnapshot) => callback(snapshot)
    ipcRenderer.on(IPC.accountChangedEvent, listener)
    return () => {
      ipcRenderer.removeListener(IPC.accountChangedEvent, listener)
    }
  },
}

contextBridge.exposeInMainWorld('agentBridge', bridge)
