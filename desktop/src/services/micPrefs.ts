/**
 * "选定的录音设备"的读写（第 103 批）。
 *
 * ## 为什么放主进程偏好（`desktop-prefs.json`）而不是后端设置
 *
 * 两条理由，第二条更硬：
 * - 麦克风是**这台机器**的属性 —— 换台机器、换个后端配置都不该跟着走；
 * - **时序**：这个值必须在**打开麦克风之前**就读到，而那一刻核心可能还没起来
 *   （`voiceSessionStore.bootstrap()` 在 `settings` 就绪后立刻跑）。放后端设置里，
 *   用户重启核心/切换线路之后就有一段时间读不到它，麦克风会"莫名其妙换了设备"。
 *
 * ## 口径
 *
 * - 空串 = **系统默认**（`getUserMedia` 不带 `deviceId` 约束）—— 从没选过的都是这个；
 * - 读写失败一律**静默回落**：记不住只影响"下次启动用哪个麦"，不该影响本次使用
 *   （与 `closeAction` 的既有口径一致：主进程只是写个小 JSON，失败概率极低，
 *   真失败也没什么后果）；
 * - **这里不校验设备还在不在** —— 那需要 `enumerateDevices()`（要麦克风权限），
 *   由调用方拿到列表后自行判断并回落（见 `voiceSessionStore` 的 `openCapture`
 *   与 `VoicePanel` 的「麦克风设备」那一行）。
 */

/** 读"上次选的录音设备 id"；没存过 / 读不到都是空串（= 系统默认）。 */
export async function readMicDeviceId(): Promise<string> {
  const bridge = window.agentBridge
  if (!bridge?.getDesktopPrefs) return ''
  try {
    const prefs = await bridge.getDesktopPrefs()
    return prefs.micDeviceId ?? ''
  } catch {
    return ''
  }
}

/** 记住"用哪个录音设备"（空串 = 回到系统默认）。失败静默。 */
export async function writeMicDeviceId(deviceId: string): Promise<void> {
  const bridge = window.agentBridge
  if (!bridge?.setDesktopPrefs) return
  try {
    await bridge.setDesktopPrefs({ micDeviceId: deviceId })
  } catch {
    // 记不住不影响本次运行（本次已经按新设备重开了采集）
  }
}
