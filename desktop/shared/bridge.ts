






export interface BackendInfo {
  port: number
  token: string
  baseUrl: string
  pid: number
  mode: 'development' | 'packaged'
}

export type BackendState = 'starting' | 'ready' | 'restarting' | 'stopped' | 'failed'

export interface BackendStatus {
  state: BackendState
  message: string
  restarts?: number
}

export interface AppInfo {
  version: string
  electronVersion: string
  chromeVersion: string
  

  platform: string
  isDev: boolean
  dataDir: string
}










export interface SecretsPayload {
  
  models: Record<string, string>
  
  mcp: Record<string, Record<string, string>>
  





  integrations: Record<string, Record<string, string>>
}
















export interface SecretsPatch {
  
  models?: Record<string, string>
  
  removeModelIds?: string[]
  
  mcp?: Record<string, Record<string, string>>
  
  removeMcpVars?: Record<string, string[]>
  
  integrations?: Record<string, Record<string, string>>
}

export interface SecretsStatus {
  
  available: boolean
  
  protection: 'encrypted' | 'plaintext'
  
  path: string
  
  count: number
}












export interface SkillSecretsPatch {
  
  keys?: Record<string, string>
  
  remove?: string[]
}







export interface SkillSecretsView {
  
  names: string[]
  
  masked: Record<string, string>
  
  available: boolean
  
  protection: 'encrypted' | 'plaintext'
  
  path: string
}











export type ThemeId =
  | 'light'
  | 'dark'
  | 'system'
  | 'warm'
  | 'forest'
  | 'ocean'
  | 'sakura'
  | 'mint'
  | 'sky'
  | 'apricot'
  | 'plum'
  | 'pine'
  | 'charcoal'
  | 'deepday'
  | 'deepnight'


export type WindowTheme = ThemeId


export function isDarkTheme(theme: ThemeId): boolean {
  return (
    theme === 'dark' ||
    theme === 'forest' ||
    theme === 'ocean' ||
    theme === 'plum' ||
    theme === 'pine' ||
    theme === 'charcoal' ||
    theme === 'deepnight'
  )
}


export const THEME_IDS: readonly ThemeId[] = [
  'light',
  'warm',
  'sakura',
  'mint',
  'sky',
  'apricot',
  'deepday',
  'dark',
  'forest',
  'ocean',
  'plum',
  'pine',
  'charcoal',
  'deepnight',
]


export type CloseAction = 'ask' | 'tray' | 'quit'











export interface DesktopPrefs {
  theme: WindowTheme
  





  autoUpdate: boolean
  




  closeAction: CloseAction
  










  micDeviceId?: string
}







export type ClosePromptResult = 'cancel' | 'tray' | 'quit'


export interface ClosePromptAnswer {
  action: ClosePromptResult
  
  remember: boolean
}








export interface WindowArgs {
  



  mode: 'main' | 'chat' | 'group'
  
  assistantId: string
  






  threadId: string
  






  sessionId: string
  
  groupId: string
  






  readonly: boolean
}













export interface SaveArtifactRequest {
  
  fileId: string
  kind: 'upload' | 'artifact'
  
  suggestedName: string
  
  mime?: string
}







export interface SaveArtifactResult {
  ok: boolean
  cancelled?: boolean
  
  path?: string
  
  error?: string
}

export interface RevealTarget {
  
  modelId?: string
  
  mcpServer?: string
  mcpVar?: string
  
  integration?: string
  integrationField?: string
}










export type AccountLine = 'cn' | 'seoul'









export interface AccountUser {
  id: number
  account: string
  
  has_password: boolean
  
  my_invite_code: string
  
  invite_bound: boolean
  
  token_balance: string
  
  tron_address: string
  created_at: string
  
  is_primary?: boolean
  last_used_at?: string
  
  inviter_masked?: string | null
}


export interface AccountLineState {
  preferred: AccountLine
  
  measurements: Record<string, number | null>
  
  updatedAt: number
  





  manual: boolean
}







export type AccountPhase =
  | 'idle'
  | 'checking-network'
  | 'probing-line'
  | 'lookup'
  | 'register'
  | 'ready'
  | 'offline'
  | 'device-unusable'
  | 'error'


export interface AccountSnapshot {
  phase: AccountPhase
  
  message: string
  
  deviceUsable: boolean
  
  offline: boolean
  
  offlinePrompt: boolean
  
  accounts: AccountUser[]
  
  currentId: number | null
  
  hasDeviceSecret: boolean
  
  loggedIn: boolean
  
  rate: number | null
  line: AccountLineState | null
  
  watching: boolean
  
  watchSecondsLeft: number
  





  balanceIncreasedAt: number | null
  
  commission: AccountCommission | null
  





  commissionError: string
  
  wxOrder: WxOrderState | null
  



  paypalConfig: PayPalConfig | null
  
  paypalOrder: PayPalOrderState | null
  





  paypalNotice: PayPalNotice | null
}






export type WxOrderStatus = 'CREATING' | 'NOTPAY' | 'SUCCESS' | 'CLOSED' | 'FAIL'


export interface WithdrawalRecord {
  id: number
  amount: string
  gross_amount?: string
  fee?: string
  method?: string
  status: 'pending' | 'done' | 'rejected'
  admin_note: string | null
  created_at: string
  reviewed_at?: string | null
}


export interface RmbCommission {
  withdrawable: string
  total: string
  withdrawn: string
  
  fee_rate: number
  
  commission_rate: number
  
  payee_ready: Record<string, boolean>
  withdrawals: WithdrawalRecord[]
}


export interface UsdtCommission {
  withdrawable: string
  total: string
  withdrawn: string
  
  fee_fixed: number
  commission_rate: number
  withdrawals: WithdrawalRecord[]
}


export interface AccountCommission {
  region: AccountLine
  rmb: RmbCommission
  usdt: UsdtCommission
}







export interface WxOrderState {
  order_no: string
  amount_yuan: number
  token_amount: string
  status: WxOrderStatus
  
  code_url: string
  
  countdown_seconds: number
}








export interface AccountActionResult {
  ok: boolean
  
  error?: string
  
  manualReset?: { email: string; require: string }
  snapshot: AccountSnapshot
}








export interface RedeemOutcome {
  ok: boolean
  
  message: string
  
  error: string
  snapshot: AccountSnapshot
}






export interface PayPalConfig {
  
  unit_price: number
  







  unit_usd: number
  
  min: number
  
  max: number
  
  client_id: string
  
  mode: string
  currency: string
}


export type PayPalOrderStatus = 'PENDING' | 'PAID' | 'EXPIRED' | 'CANCELLED' | 'FAILED'








export interface PayPalOrderState {
  ct: string
  
  quantity: number
  status: PayPalOrderStatus
  
  countdown_seconds: number
  
  expires_seconds: number
}


export type PayPalNoticeTone = 'warning' | 'danger' | 'success'

export interface PayPalNotice {
  tone: PayPalNoticeTone
  
  message: string
}

export interface PayPalResult {
  ok: boolean
  
  error?: string
  
  notice?: PayPalNotice
  snapshot: AccountSnapshot
}








export interface UpdateState {
  
  supported: boolean
  
  phase: 'idle' | 'checking' | 'downloading' | 'ready' | 'need-full' | 'error'
  
  version: string
  
  availableVersion: string | null
  
  total: number
  
  downloaded: number
  
  bytesDone: number
  bytesTotal: number
  
  pendingApply: boolean
  
  fullPackageUrl: string
  
  lastCheckedAt: string
  
  message: string
}

export interface AgentBridge {
  getBackendInfo: () => Promise<BackendInfo>
  getBackendStatus: () => Promise<BackendStatus>
  restartBackend: () => Promise<BackendInfo>
  getBackendLogs: () => Promise<string[]>
  getAppInfo: () => Promise<AppInfo>
  setTitleBarTheme: (theme: WindowTheme) => void
  
  minimizeWindow: () => void
  toggleMaximizeWindow: () => void
  










  resetWindowSize: () => void
  closeWindow: () => void
  





  resizeWindowBy: (deltaWidth: number) => void
  




















  resizeWindowBySync: (deltaWidth: number) => boolean
  
  getWindowArgs: () => WindowArgs
  
  openChatWindow: (assistantId: string, sessionId?: string) => void
  





  openGroupWindow: (groupId: string, observing?: boolean, threadId?: string) => void
  pickDirectory: () => Promise<string | null>
  







  pickFile: () => Promise<string | null>
  






  saveArtifactAs: (payload: SaveArtifactRequest) => Promise<SaveArtifactResult>
  openPath: (target: string) => Promise<boolean>
  openExternal: (url: string) => Promise<boolean>
  onBackendStatus: (callback: (status: BackendStatus) => void) => () => void
  




  getUpdateState: () => Promise<UpdateState>
  





  checkForUpdate: () => Promise<UpdateState>
  





  applyUpdateNow: () => Promise<UpdateState>
  





  openFullPackage: () => Promise<void>
  
  onUpdateState: (callback: (state: UpdateState) => void) => () => void

  
  





  onClosePrompt: (callback: () => void) => () => void
  
  answerClosePrompt: (answer: ClosePromptAnswer) => void

  
  getDesktopPrefs: () => Promise<DesktopPrefs>
  setDesktopPrefs: (patch: Partial<DesktopPrefs>) => Promise<DesktopPrefs>

  
  






  getSecretsMasked: () => Promise<SecretsPayload>
  saveSecrets: (patch: SecretsPatch) => Promise<SecretsStatus>
  getSecretsStatus: () => Promise<SecretsStatus>
  








  revealSecret: (target: RevealTarget) => Promise<string>

  
  




  getSkillSecrets: () => Promise<SkillSecretsView>
  







  saveSkillSecrets: (patch: SkillSecretsPatch) => Promise<SkillSecretsView>
  
  removeSkillSecrets: (names: string[]) => Promise<SkillSecretsView>
  
  getSkillSecretsStatus: () => Promise<SkillSecretsView>

  
  
  getAccountSnapshot: () => Promise<AccountSnapshot>
  
  refreshAccount: () => Promise<AccountSnapshot>
  
  setAccountLine: (line: AccountLine) => Promise<AccountSnapshot>
  
  reprobeAccountLine: () => Promise<AccountSnapshot>
  
  loginAccount: (account: string, password: string) => Promise<AccountActionResult>
  





  switchAccount: (id: number, password: string) => Promise<AccountActionResult>
  
  renameAccount: (name: string, password: string) => Promise<AccountActionResult>
  
  setAccountPassword: (next: string, old: string) => Promise<AccountActionResult>
  
  recoverAccount: (account: string, next: string) => Promise<AccountActionResult>
  
  submitInviteCode: (code: string) => Promise<AccountActionResult>
  
  watchRecharge: () => Promise<AccountActionResult>
  
  stopRechargeWatch: () => Promise<AccountSnapshot>

  
  
  getAccountCommission: () => Promise<AccountActionResult>
  




  redeemCode: (code: string) => Promise<RedeemOutcome>
  
  createWxRecharge: (amountYuan: number) => Promise<AccountActionResult>
  
  cancelWxRecharge: () => Promise<AccountSnapshot>
  




  getPaypalConfig: () => Promise<PayPalResult>
  




  createPaypalCheckout: (quantity: number) => Promise<PayPalResult>
  
  cancelPaypalCheckout: () => Promise<AccountSnapshot>
  





  dismissPaypalNotice: () => Promise<AccountSnapshot>
  






  withdrawRmb: (payload: {
    amount: number
    zhifubao: string
    bank: string
  }) => Promise<AccountActionResult>
  
  withdrawUsdt: (payload: { amount: number; trc20_address: string }) => Promise<AccountActionResult>
  





  answerOfflinePrompt: (mode: 'continue' | 'skip') => Promise<void>
  





  onAccountChanged: (callback: (snapshot: AccountSnapshot) => void) => () => void
}











export const IPC = {
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
