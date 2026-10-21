import type { AgentApi } from '@/services/api'
import type { PendingAttachment } from '@/types'















export function makePlaceholders(files: File[]): PendingAttachment[] {
  return files.map((file) => ({
    
    id: `pending-${crypto.randomUUID()}`,
    name: file.name,
    size: file.size,
    status: 'uploading' as const,
    
    
    kind: file.type.startsWith('image/') ? ('image' as const) : ('file' as const),
  }))
}

export interface AddFilesOptions {
  api: AgentApi
  
  sessionId?: string
  
  onChange: (next: PendingAttachment[]) => void
}


export async function addFilesTo(
  current: PendingAttachment[],
  files: File[],
  { api, sessionId, onChange }: AddFilesOptions,
): Promise<void> {
  if (files.length === 0) return
  const placeholders = makePlaceholders(files)
  let list = [...current, ...placeholders]
  onChange(list)

  const uploadOne = async (file: File, index: number) => {
    const placeholderId = placeholders[index].id
    try {
      const record = await api.uploadFile(file, sessionId)
      list = list.map((item) =>
        item.id === placeholderId
          ? { ...item, id: record.id, size: record.size, status: 'ready' as const }
          : item,
      )
    } catch (error) {
      list = list.map((item) =>
        item.id === placeholderId
          ? {
              ...item,
              status: 'error' as const,
              error: error instanceof Error ? error.message : String(error),
            }
          : item,
      )
    }
    onChange(list)
  }

  
  
  
  const BATCH = 4
  for (let start = 0; start < files.length; start += BATCH) {
    await Promise.all(
      files.slice(start, start + BATCH).map((file, offset) => uploadOne(file, start + offset)),
    )
  }
}


export function readyFileIds(attachments: PendingAttachment[], kind: 'image' | 'file'): string[] {
  return attachments
    .filter((item) => item.kind === kind && item.status === 'ready')
    .map((item) => item.id)
}


export function attachmentNames(
  attachments: PendingAttachment[],
  ids: string[],
): Record<string, string> {
  const map: Record<string, string> = {}
  for (const item of attachments) {
    if (ids.includes(item.id)) map[item.id] = item.name
  }
  return map
}
