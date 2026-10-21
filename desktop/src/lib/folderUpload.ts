






















export const MAX_FILES = 200

export const MAX_FILE_BYTES = 50 * 1024 * 1024

export interface SkippedFile {
  name: string
  reason: string
}

export interface CollectResult {
  files: File[]
  
  skipped: SkippedFile[]
  
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





export function filterFolderFiles(input: File[]): CollectResult {
  const files: File[] = []
  const skipped: SkippedFile[] = []
  let truncated = false

  for (const file of input) {
    
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


export function collectFromFileList(list: FileList | File[] | null): CollectResult {
  const input = list ? Array.from(list) : []
  return filterFolderFiles(input)
}







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


export function hasDirectory(dataTransfer: DataTransfer): boolean {
  return Array.from(dataTransfer.items ?? []).some((item) => {
    if (item.kind !== 'file') return false
    return item.webkitGetAsEntry?.()?.isDirectory === true
  })
}

async function walkEntry(entry: FileSystemEntry, out: File[]): Promise<void> {
  if (out.length > MAX_FILES * 4) {
    
    
    return
  }
  if (entry.isFile) {
    const file = await fileFromEntry(entry as FileSystemFileEntry)
    if (file) out.push(file)
    return
  }
  if (!entry.isDirectory) return
  const reader = (entry as FileSystemDirectoryEntry).createReader()
  
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
