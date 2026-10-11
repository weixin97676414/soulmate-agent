import type { AgentApi } from '@/services/api'
import type { PendingAttachment } from '@/types'

/**
 * 附件的上传流程（单聊与群聊共用）。
 *
 * ## 为什么抽出来
 *
 * 产品要求"群聊输入栏与单聊完全一致"，而附件是这个体验里最容易两边长歪的部分：
 * 先插占位项、逐个上传、成功回填 id、失败标红并保留原因 —— 少做一步就会变成
 * "单聊上传失败会提示，群聊只会静默消失"。所以这条链路只有一份实现。
 *
 * ## 为什么先插占位项再上传
 *
 * 上传要几百毫秒到几秒。等上传完再显示的话，用户点了选文件之后界面毫无反应，
 * 会以为没选上而再点一次。先显示(带转圈的占位)再回填，是唯一不会让人误解的顺序。
 */
export function makePlaceholders(files: File[]): PendingAttachment[] {
  return files.map((file) => ({
    // 占位 id 用一个明显的临时前缀，上传成功后才换成服务端返回的文件 id
    id: `pending-${crypto.randomUUID()}`,
    name: file.name,
    size: file.size,
    status: 'uploading' as const,
    // 按浏览器给的 MIME 判定，不看扩展名：改过后缀的图片会在这里被正确归到
    // "普通附件"，而后端也会再用真实 mime 校验一次（双保险）
    kind: file.type.startsWith('image/') ? ('image' as const) : ('file' as const),
  }))
}

export interface AddFilesOptions {
  api: AgentApi
  /** 归属会话：单聊传当前会话 id，群聊没有会话就留空 */
  sessionId?: string
  /** 每次列表变化都回调一次，调用方直接写回自己的 store */
  onChange: (next: PendingAttachment[]) => void
}

/** 把文件加进附件列表（含上传与失败标记）。 */
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

  // **分批并发**（每批 4 个）：一次拖进整个目录时可能是几百个文件，
  // 全部同时上传会同时打开几百个请求 —— 后端、磁盘、网络谁都受不了，
  // 而"传到一半失败"是最难定位的一类问题。分批还能让进度一格格往前走。
  const BATCH = 4
  for (let start = 0; start < files.length; start += BATCH) {
    await Promise.all(
      files.slice(start, start + BATCH).map((file, offset) => uploadOne(file, start + offset)),
    )
  }
}

/** 取出可以直接发送的附件 id（上传中/失败的都不发：发给后端只会 404）。 */
export function readyFileIds(attachments: PendingAttachment[], kind: 'image' | 'file'): string[] {
  return attachments
    .filter((item) => item.kind === kind && item.status === 'ready')
    .map((item) => item.id)
}

/** 附件对应的展示名称，按 id 找（发出去之后气泡里要显示文件名）。 */
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
