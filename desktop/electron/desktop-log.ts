/**
 * 主进程的持久日志。
 *
 * ## 为什么必须有这个文件
 *
 * 核心（Python）有 `<userData>/logs/core.log`，而**主进程一行持久日志都没有**。
 * 于是用户报"双击快捷方式没反应、要点第二次才开"时，我们手上没有任何证据 ——
 * 不知道那次启动有没有拿到单实例锁、窗口有没有显示出来、是走 ready-to-show
 * 还是被兜底定时器救的。
 *
 * 这类问题的特点是：**偶发、无法复现、用户也说不清规律**。能不能查清
 * 完全取决于事发当时留下了什么。加日志的成本是几十行，而查不出来的成本
 * 是让用户反复描述一个我们都看不见的现象。
 *
 * ## 为什么不用 electron-log 之类的库
 *
 * 需要的只是"按行追加 + 到量轮转"。为一个日志功能引依赖，换来的是又一处
 * 要跟着 Electron 版本升级的第三方代码，不划算。
 *
 * ## 放在哪
 *
 * 与核心日志**同一个目录**（`<userData>/logs/`）。用户按"打开日志目录"时
 * 两个文件都在，排查时不用记两个位置。
 */
import fs from 'node:fs'
import path from 'node:path'

import { app } from 'electron'

const LOG_DIR = 'logs'
const LOG_NAME = 'desktop.log'
/** 超过这个大小轮转一次。启动日志每行几十字节，1MB 足够存几万次启动 */
const MAX_BYTES = 1024 * 1024

let dirReady = false

function logDir(): string {
  return path.join(app.getPath('userData'), LOG_DIR)
}

function logPath(): string {
  return path.join(logDir(), LOG_NAME)
}

function ensureDir(): boolean {
  if (dirReady) return true
  try {
    fs.mkdirSync(logDir(), { recursive: true })
    dirReady = true
    return true
  } catch {
    return false
  }
}

function rotateIfNeeded(file: string): void {
  let size = 0
  try {
    size = fs.statSync(file).size
  } catch {
    return // 文件还不存在，没什么可轮转的
  }
  if (size < MAX_BYTES) return
  try {
    // 只留一代 `desktop.log.1`。这份日志是用来定位"最近一次"问题的，
    // 留十几代除了占地方没有别的用处。
    fs.renameSync(file, `${file}.1`)
  } catch {
    // 轮转失败不该影响写日志本身（最坏的结果只是文件继续变大，而不是丢日志）
  }
}

/**
 * 追加一行日志。**永远不抛异常**。
 *
 * 日志是诊断手段而不是业务逻辑：磁盘满、目录不可写、文件被杀软锁住……
 * 任何情况下都不该因为它让应用起不来或中断某个操作。这正是这里到处 try 的原因。
 */
export function logDesktop(message: string): void {
  const line = `${new Date().toISOString()} ${message}\n`
  // 开发时同时打到控制台，省得为了看一行字去翻文件
  console.log(`[desktop] ${message}`)

  if (!ensureDir()) return
  const file = logPath()
  rotateIfNeeded(file)
  try {
    fs.appendFileSync(file, line, 'utf-8')
  } catch {
    // 见上：写不进去就算了，绝不让它影响主流程
  }
}
