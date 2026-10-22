











import { execFileSync } from 'node:child_process'
import os from 'node:os'
import path from 'node:path'
import process from 'node:process'

export const APPDATA = process.env.APPDATA ?? path.join(os.homedir(), 'AppData', 'Roaming')
export const LOCALAPPDATA = process.env.LOCALAPPDATA ?? path.join(os.homedir(), 'AppData', 'Local')
export const TEMP = process.env.TEMP ?? os.tmpdir()









export const DATA_DIR_NAMES = ['Soulmate Agent', 'Soulmate', 'AgentDesktop', 'jianyin_agent']


export const dataDirs = DATA_DIR_NAMES.map((name) => path.join(APPDATA, name))





export const RUNNING_PROCESSES = [
  'Soulmate Agent.exe',
  'Soulmate.exe',
  'AgentDesktop.exe',
  'agent-core.exe',
]









export function isRunning(imageName) {
  try {
    
    const output = execFileSync('tasklist', ['/FI', `IMAGENAME eq ${imageName}`, '/NH'], {
      encoding: 'utf-8',
      windowsHide: true,
      timeout: 20_000,
    })
    return output.toLowerCase().includes(imageName.toLowerCase())
  } catch {
    
    return false
  }
}







export function isOurShortcut(name) {
  if (!name.toLowerCase().endsWith('.lnk')) return false
  return name.includes('智能体助手') || name.toLowerCase().includes('soulmate')
}
