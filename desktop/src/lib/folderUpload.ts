/**
 * 把**整个文件夹**批量变成待发送的附件（产品要求）。
 *
 * ## 为什么放在渲染层、而不是让主进程去扫目录
 *
 * 主进程已有的「选目录」对话框（`dialog:pick-directory`）只回一个**路径字符串**，
 * 渲染层拿不到文件列表，而沙箱化的渲染层也读不了目录 —— 那就要新增一个
 * "递归列目录"的 IPC 通道。而浏览器本来就有两条现成的路：
 *
 * - `<input type="file" webkitdirectory>` 直接给出 `File[]`（含 `webkitRelativePath`）；
 * - 拖拽时 `DataTransferItem.webkitGetAsEntry()` 能递归读目录。
 *
 * 两条都拿到真正的 `File` 对象，于是可以直接走**现有的**上传链路
 * （`services/attachments.ts` 的 `addFilesTo`），一行 IPC 都不用加。
 *
 * ## 为什么要有上限
 *
 * 用户可能把几万个文件的目录拖进来：几百个并发上传会打爆后端与磁盘，
 * 而"传到一半失败"最难定位。所以设两个闸（数量、单文件大小），
 * 超了**停下来并说明原因** —— 绝不静默截断（本项目对"静默"是零容忍的）。
 */

/** 一次最多收多少文件。够覆盖"一个项目的资料文件夹"，又不会把应用拖死 */
export const MAX_FILES = 200
/** 单个文件上限（与后端上传限制保持同一量级） */
export const MAX_FILE_BYTES = 50 * 1024 * 1024

export interface SkippedFile {
  name: string
  reason: string
}

export interface CollectResult {
  files: File[]
  /** 被跳过的文件与原因（展示给用户，不静默丢） */
  skipped: SkippedFile[]
  /** 因为数量上限而中止（剩下的没收集） */
  truncated: boolean
}

const SKIP_NAMES = new Set(['thumbs.db', 'desktop.ini', '.ds_store'])

function skipReason(file: File): string {
  const name = file.name
  if (SKIP_NAMES.has(name.toLowerCase())) return '系统文件'
  if (name.startsWith('.')) return '隐藏文件'
  if (file.size > MAX_FILE_BYTES) return `超过 ${Math.round(MAX_FILE_BYTES / 1024 / 1024)} MB`
  return ''
}

/**
 * 过滤 + 限量。目录里通常混着一堆不需要的东西（缩略图缓存、macOS 的 `._` 旁支文件、
 * Office 的临时文件），全传过去只会让模型把注意力花在垃圾上。
 */
export function filterFolderFiles(input: File[]): CollectResult {
  const files: File[] = []
  const skipped: SkippedFile[] = []
  let truncated = false

  for (const file of input) {
    // 相对路径里带 __MACOSX 的是 macOS 打包压缩时留下的旁支，对任务没有任何价值
    const relative = (file as File & { webkitRelativePath?: string }).webkitRelativePath ?? ''
    if (relative.includes('__MACOSX') || /(^|\/)~\$/.test(relative)) {
      skipped.push({ name: relative || file.name, reason: '临时/旁支文件' })
      continue
    }
    const reason = skipReason(file)
    if (reason) {
      skipped.push({ name: file.name, reason })
      continue
    }
    if (files.length >= MAX_FILES) {
      truncated = true
      break
    }
    files.push(file)
  }
  return { files, skipped, truncated }
}

/** 从 `<input webkitdirectory>` 的 FileList 收集 */
export function collectFromFileList(list: FileList | File[] | null): CollectResult {
  const input = list ? Array.from(list) : []
  return filterFolderFiles(input)
}

/**
 * 递归读拖进来的文件夹。
 *
 * `webkitGetAsEntry()` 必须在 `drop` 事件**同步**调用（事件结束后 DataTransfer
 * 就失效了），所以这里先把 entry 全部取出来，再慢慢递归读。
 */
export async function collectFromDataTransfer(dataTransfer: DataTransfer): Promise<CollectResult> {
  const items = Array.from(dataTransfer.items ?? [])
  const entries = items
    .filter((item) => item.kind === 'file')
    .map((item) => {
      const entry = item.webkitGetAsEntry?.() as FileSystemEntry | null | undefined
      return entry ?? null
    })
    .filter((entry): entry is FileSystemEntry => Boolean(entry))

  const collected: File[] = []
  for (const entry of entries) {
    await walkEntry(entry, collected)
  }
  return filterFolderFiles(collected)
}

/** 拖进来的东西里有没有文件夹（决定走"文件夹批量"还是"几个文件"这条路） */
export function hasDirectory(dataTransfer: DataTransfer): boolean {
  return Array.from(dataTransfer.items ?? []).some((item) => {
    if (item.kind !== 'file') return false
    return item.webkitGetAsEntry?.()?.isDirectory === true
  })
}

async function walkEntry(entry: FileSystemEntry, out: File[]): Promise<void> {
  if (out.length > MAX_FILES * 4) {
    // 目录太大时**先停下**：再往下读只是浪费时间，而收集完也会被 filter 截断。
    // 多留一点余量（4 倍）是为了让"被截断"这件事由 filterFolderFiles 统一报告。
    return
  }
  if (entry.isFile) {
    const file = await fileFromEntry(entry as FileSystemFileEntry)
    if (file) out.push(file)
    return
  }
  if (!entry.isDirectory) return
  const reader = (entry as FileSystemDirectoryEntry).createReader()
  // readEntries 每次最多回 100 条，要反复读到空为止 —— 只调一次是常见的坑
  for (;;) {
    const batch = await readEntries(reader)
    if (batch.length === 0) break
    for (const child of batch) {
      await walkEntry(child, out)
    }
  }
}

function readEntries(reader: FileSystemDirectoryReader): Promise<FileSystemEntry[]> {
  return new Promise((resolve) => {
    reader.readEntries(
      (entries) => resolve(Array.from(entries)),
      () => resolve([]),
    )
  })
}

function fileFromEntry(entry: FileSystemFileEntry): Promise<File | null> {
  return new Promise((resolve) => {
    entry.file(
      (file) => resolve(file),
      () => resolve(null),
    )
  })
}
