import clsx from 'clsx'
import { FolderPlus, Loader2, Upload } from 'lucide-react'
import { useRef, useState } from 'react'
import { create } from 'zustand'

import { OPTION_BUTTON_CLASS, PACKAGE_ACCEPT, sourceLabel } from '@/components/skillImport'
import { Button, Modal } from '@/components/ui'
import { useAppStore } from '@/stores/appStore'
import { useNotificationStore } from '@/stores/notificationStore'
import { useClosableDialog } from '@/stores/transientDialogs'
import type { SkillImportOutcome } from '@/types'













interface AddSkillState {
  open: boolean
  





  revision: number
  setOpen: (value: boolean) => void
  bump: () => void
}

const useAddSkillStore = create<AddSkillState>((set) => ({
  open: false,
  revision: 0,
  setOpen: (value) => set({ open: value }),
  bump: () => set((state) => ({ revision: state.revision + 1 })),
}))


export function openAddSkill(): void {
  useAddSkillStore.getState().setOpen(true)
}


export function useSkillRevision(): number {
  return useAddSkillStore((state) => state.revision)
}

export function AddSkillDialog() {
  const open = useAddSkillStore((state) => state.open)
  const setOpen = useAddSkillStore((state) => state.setOpen)
  const bump = useAddSkillStore((state) => state.bump)
  const api = useAppStore((state) => state.api)
  const push = useNotificationStore((state) => state.push)

  const [busy, setBusy] = useState(false)
  const [result, setResult] = useState<SkillImportOutcome | null>(null)
  const packageInputRef = useRef<HTMLInputElement>(null)

  
  
  
  useClosableDialog('AddSkillDialog', open, () => setOpen(false))
  useClosableDialog('AddSkillResult', result !== null, () => setResult(null))

  const finish = (outcome: SkillImportOutcome) => {
    setResult(outcome)
    bump()
  }

  
  const fail = (exc: unknown) => {
    push({
      level: 'error',
      title: '导入失败',
      message: exc instanceof Error ? exc.message : String(exc),
    })
  }

  const uploadPackage = async (file: File) => {
    if (!api) return
    setBusy(true)
    try {
      finish(await api.uploadSkillPackage(file))
    } catch (exc) {
      fail(exc)
    } finally {
      setBusy(false)
    }
  }

  





  const importFolder = async () => {
    if (!api) return
    const picked = await window.agentBridge.pickDirectory()
    if (!picked) return
    setBusy(true)
    try {
      finish(await api.importSkillFolder(picked))
    } catch (exc) {
      fail(exc)
    } finally {
      setBusy(false)
    }
  }

  return (
    <>
      {
}
      <input
        ref={packageInputRef}
        type="file"
        accept={PACKAGE_ACCEPT}
        className="hidden"
        onChange={(event) => {
          const file = event.target.files?.[0]
          if (file) void uploadPackage(file)
          event.target.value = ''
        }}
      />

      <Modal
        open={open}
        onClose={() => setOpen(false)}
        width="max-w-sm"
        title="添加技能"
        footer={<Button onClick={() => setOpen(false)}>取消</Button>}
      >
        <div className="space-y-2">
          <button
            type="button"
            disabled={busy}
            className={OPTION_BUTTON_CLASS}
            onClick={() => {
              setOpen(false)
              
              
              window.setTimeout(() => packageInputRef.current?.click(), 0)
            }}
          >
            {busy ? (
              <Loader2 size={15} className="mt-0.5 shrink-0 animate-spin text-brand" />
            ) : (
              <Upload size={15} className="mt-0.5 shrink-0 text-brand" />
            )}
            <span className="min-w-0">
              <span className="block text-[12.5px] font-medium text-ink">
                {busy ? '导入中…' : '上传技能包'}
              </span>
              <span className="mt-0.5 block text-[11px] leading-relaxed text-ink-faint">
                选一个压缩包（.zip / .tar.gz）或单个技能文件
              </span>
            </span>
          </button>
          <button
            type="button"
            disabled={busy}
            className={OPTION_BUTTON_CLASS}
            onClick={() => {
              setOpen(false)
              void importFolder()
            }}
          >
            <FolderPlus size={15} className="mt-0.5 shrink-0 text-brand" />
            <span className="min-w-0">
              <span className="block text-[12.5px] font-medium text-ink">导入文件夹</span>
              <span className="mt-0.5 block text-[11px] leading-relaxed text-ink-faint">
                选一个本机文件夹，多层目录会原样导入
              </span>
            </span>
          </button>
        </div>
      </Modal>

      {}
      <Modal
        open={result !== null}
        onClose={() => setResult(null)}
        width="max-w-md"
        title="技能包导入结果"
        footer={
          <Button variant="primary" onClick={() => setResult(null)}>
            知道了
          </Button>
        }
      >
        {result ? (
          <div className="space-y-2">
            <p className="text-[12.5px] text-ink">{result.message}</p>
            {result.results.map((item, index) => (
              <div
                key={index}
                className={clsx(
                  'rounded-[8px] border px-3 py-2 text-[12px] leading-relaxed',
                  item.ok
                    ? 'border-success/30 bg-success-soft text-success'
                    : 'border-danger/30 bg-danger-soft text-danger',
                )}
              >
                <div className="flex flex-wrap items-center gap-2">
                  <span className="font-medium">{item.name}</span>
                  {sourceLabel(item.source_format) ? (
                    <span className="text-[10.5px] opacity-80">
                      {sourceLabel(item.source_format)}
                    </span>
                  ) : null}
                  {item.skipped ? <span className="text-[10.5px] opacity-80">已跳过</span> : null}
                  {item.updated ? <span className="text-[10.5px] opacity-80">已更新</span> : null}
                </div>
                <div>
                  {item.ok
                    ? (item.message ??
                      (item.kind === 'instruction'
                        ? '导入成功（指导型：内容会进入对话）'
                        : '导入成功'))
                    : (item.message ?? '失败')}
                </div>
                {item.note ? <div className="mt-0.5 opacity-90">{item.note}</div> : null}
              </div>
            ))}
            {result.mcp?.length ? (
              <div className="rounded-[8px] border border-line px-3 py-2 text-[12px]">
                <div className="mb-1 font-medium text-ink">包内的 MCP 服务</div>
                {result.mcp.map((entry, index) => (
                  <div key={index} className={entry.ok ? 'text-success' : 'text-danger'}>
                    {entry.name} —— {entry.message}
                  </div>
                ))}
              </div>
            ) : null}
            {result.skipped.length ? (
              <p className="text-[11.5px] leading-relaxed text-warning">
                有 {result.skipped.length} 个文件看着不对劲，没有往你的电脑里放
                （已经记下来了）。
              </p>
            ) : null}
            {result.unrecognized.length ? (
              <p className="text-[11.5px] leading-relaxed text-ink-faint">
                另外 {result.unrecognized.length} 个文件照原样留着了，没有当成技能用；
                在技能页点「查看详情」能看到它们。
              </p>
            ) : null}
          </div>
        ) : null}
      </Modal>
    </>
  )
}
