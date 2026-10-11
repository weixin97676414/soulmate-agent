/**
 * 两个清理脚本（`reset-local-data.mjs` / `clean-test-residue.mjs`）共用的常量与判定。
 *
 * ## 为什么要抽出来（第 86 批 B 组，M-13）
 *
 * 这几份清单以前在两个脚本里**各写一份**，而且**已经漂移**：
 * `clean-test-residue` 的 `DATA_DIR_NAMES` 多一个 `jianyin_agent`（更早期的产品名），
 * `reset-local-data` 没有 —— 于是发版流程那一步的"清零"遇到那套老数据时**只清一半**，
 * 用户看到的下一轮测试仍带着旧配置。进程名清单与 `.lnk` 过滤规则也是逐字复制的两份。
 *
 * ⇒ 名字或判定要改时**只改这里一处**。
 */
import { execFileSync } from 'node:child_process'
import os from 'node:os'
import path from 'node:path'
import process from 'node:process'

export const APPDATA = process.env.APPDATA ?? path.join(os.homedir(), 'AppData', 'Roaming')
export const LOCALAPPDATA = process.env.LOCALAPPDATA ?? path.join(os.homedir(), 'AppData', 'Local')
export const TEMP = process.env.TEMP ?? os.tmpdir()

/**
 * 数据目录名。**改过三次名，旧名字都留着**：
 * 0.1.2 及更早叫 `AgentDesktop`，0.1.3~0.1.17 叫 `Soulmate`，0.1.18 起叫 `Soulmate Agent`；
 * `jianyin_agent` 是更早那套。
 *
 * ⚠️ 不把旧的清掉，"清零"就只清了一半 —— 而用户看到的下一轮测试仍带着旧配置，
 * 排查"改了没生效"时这是最误导人的一种。
 */
export const DATA_DIR_NAMES = ['Soulmate Agent', 'Soulmate', 'AgentDesktop', 'jianyin_agent']

/** 数据目录的绝对路径（两个脚本都按它遍历）。 */
export const dataDirs = DATA_DIR_NAMES.map((name) => path.join(APPDATA, name))

/**
 * 运行中的应用必须挡住：删掉正在写入的 SQLite 会留下**一半状态**的数据库。
 * 新旧进程名都在 —— 旧版本还开着时也不能动它的数据。
 */
export const RUNNING_PROCESSES = [
  'Soulmate Agent.exe',
  'Soulmate.exe',
  'AgentDesktop.exe',
  'agent-core.exe',
]

/**
 * 查一个进程名有没有在跑。
 *
 * ⚠️ `timeout` 是**必须的**：本机出现过"进程枚举不返回导致脚本永久挂死"，
 * 而清零是发版流程的固定一步（卡住等于发版流程永远不动）。
 * 此前 `reset-local-data.mjs` 那份**漏了** timeout，`clean-test-residue` 那份有 ——
 * 这次统一到这里。
 */
export function isRunning(imageName) {
  try {
    // tasklist 在"查无此进程"时也会给出非零退出码，所以只取输出、不看退出码
    const output = execFileSync('tasklist', ['/FI', `IMAGENAME eq ${imageName}`, '/NH'], {
      encoding: 'utf-8',
      windowsHide: true,
      timeout: 20_000,
    })
    return output.toLowerCase().includes(imageName.toLowerCase())
  } catch {
    // 不是 Windows，或 tasklist 不可用：当作没运行（这两个脚本只为本机测试服务）
    return false
  }
}

/**
 * 这个 `.lnk` 是不是**我们自己**创建的快捷方式。
 *
 * ⚠️ 只认这两个名字：桌面/开始菜单里有用户自己的快捷方式，
 * 判定放宽一寸就可能删掉别人的东西，而那是不可逆的。
 */
export function isOurShortcut(name) {
  if (!name.toLowerCase().endsWith('.lnk')) return false
  return name.includes('智能体助手') || name.toLowerCase().includes('soulmate')
}
