






















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


export async function writeMicDeviceId(deviceId: string): Promise<void> {
  const bridge = window.agentBridge
  if (!bridge?.setDesktopPrefs) return
  try {
    await bridge.setDesktopPrefs({ micDeviceId: deviceId })
  } catch {
    
  }
}
