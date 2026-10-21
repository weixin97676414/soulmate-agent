

























import { contextBridge, ipcRenderer } from 'electron'

import type { AccountSnapshot, AgentBridge, BackendStatus, UpdateState, WindowArgs } from '../shared/bridge'





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
    
    readonly: pick('group-readonly') === '1',
  }
}
const windowArgs = readWindowArgs()


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
  
  windowResetSize: 'window:reset-size',
  windowClose: 'window:close',
  







  windowResizeBy: 'window:resize-by',
  







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
  
  updateState: 'update:state',
  updateCheck: 'update:check',
  updateApplyNow: 'update:apply-now',
  updateOpenFull: 'update:open-full',
  updateStateEvent: 'update:state-event',
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
  
  resetWindowSize: () => ipcRenderer.send(IPC.windowResetSize),
  closeWindow: () => ipcRenderer.send(IPC.windowClose),
  
  resizeWindowBy: (deltaWidth) => ipcRenderer.send(IPC.windowResizeBy, deltaWidth),
  






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
  getUpdateState: () => ipcRenderer.invoke(IPC.updateState),
  checkForUpdate: () => ipcRenderer.invoke(IPC.updateCheck),
  applyUpdateNow: () => ipcRenderer.invoke(IPC.updateApplyNow),
  openFullPackage: () => ipcRenderer.invoke(IPC.updateOpenFull),
  
  onUpdateState: (callback) => {
    const listener = (_event: unknown, state: UpdateState) => callback(state)
    ipcRenderer.on(IPC.updateStateEvent, listener)
    return () => {
      ipcRenderer.removeListener(IPC.updateStateEvent, listener)
    }
  },
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
