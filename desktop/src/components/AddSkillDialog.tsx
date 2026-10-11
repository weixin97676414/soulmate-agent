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

/*
  「添加技能」弹窗 —— 挂在应用顶层，**任何页面**都能唤起。

  ⚠️ 它原先只是技能页里某个组件内部的 state（`CustomSkillsSection` 的 `adding`）。
  那样的问题是：语音里"添加技能"这条命令只有**停在技能页时**才有效 ——
  `useVoiceCommand` 的实现由渲染它的组件提供，组件没挂载，说了就没反应。
  产品要求"在任何页面都可以有效打开"，所以整块提到了顶层。

  这里顺带带上"导入结果"那个弹窗：导入是异步的、可能跑好几秒，用户往往会先
  把选项弹层关掉；结果必须**自己冒出来**，而不是塞进一个已经关掉的窗里。
*/

interface AddSkillState {
  open: boolean
  /**
   * 技能列表的"版本号"：每次导入成功就 +1。
   *
   * 技能页订阅它来重新拉列表 —— 否则从别的页面用语音导入完，切回技能页看到的
   * 还是那份旧列表（"我明明添加了，怎么没有"）。
   */
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

/** 打开「添加技能」弹窗（任何地方都能调，含语音） */
export function openAddSkill(): void {
  useAddSkillStore.getState().setOpen(true)
}

/** 技能列表的版本号，技能页用它触发刷新 */
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

  // 登记给「关闭弹窗」那条语音命令（见 stores/transientDialogs.ts）。
  // ⚠️ 两个弹层都要登记：结果弹层也是"因按钮或语音跳出来的浮层"，
  // 只登记选项层的话，用户说完"关闭弹窗"结果它还杵在那儿。
  useClosableDialog('AddSkillDialog', open, () => setOpen(false))
  useClosableDialog('AddSkillResult', result !== null, () => setResult(null))

  const finish = (outcome: SkillImportOutcome) => {
    setResult(outcome)
    bump()
  }

  /** 失败要看得见：走 toast 而不是弹层里的红条 —— 这时候选项弹层多半已经关了 */
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

  /**
   * 导入本机文件夹：多层目录原样导入，不用先压缩。
   *
   * 遍历在**核心侧**做（路径直接交给它），所以没有浏览器文件数限制，
   * 也不会把几万个小文件塞进一个 multipart 请求里。
   */
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
      {/* 容器类型由**后端按内容**识别（用户常把包改名、或拖来没有后缀的文件），
          所以这里只给一个合理的后缀过滤，不做拦截 */}
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
              // 等弹层关掉再唤起文件选择框：同一帧里 click 会被弹层的焦点回收吃掉，
              // 表现为"点了没反应"（用户看到的最恼人的失败方式）
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

      {/* 导入结果：逐条列出成功/失败，坏在哪一条一目了然 */}
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
