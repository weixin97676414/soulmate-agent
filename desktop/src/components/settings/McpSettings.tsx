import clsx from 'clsx'
import {
  AlertTriangle,
  ChevronDown,
  ChevronRight,
  Loader2,
  Plug,
  Plus,
  RefreshCw,
  RotateCw,
  Square,
  Trash2,
  Wrench,
} from 'lucide-react'
import { useCallback, useEffect, useRef, useState } from 'react'

import { Badge, Button, EmptyState, Field, Input, Modal, Select, Switch } from '@/components/ui'
import { useAppStore } from '@/stores/appStore'
import { subscribeAppEvents } from '@/stores/notificationStore'
import type {
  McpImportResult,
  McpPreset,
  McpServerConfig,
  McpServerState,
  McpServerStatus,
} from '@/types'

const STATE_META: Record<
  McpServerState,
  { label: string; dot: string; tone: 'success' | 'warning' | 'danger' | 'neutral' | 'brand' }
> = {
  ready: { label: '已连接', dot: 'bg-success', tone: 'success' },
  starting: { label: '连接中', dot: 'bg-brand animate-pulse', tone: 'brand' },
  restarting: { label: '重连中', dot: 'bg-warning animate-pulse', tone: 'warning' },
  error: { label: '异常', dot: 'bg-danger', tone: 'danger' },
  stopped: { label: '已停止', dot: 'bg-ink-faint', tone: 'neutral' },
  disabled: { label: '已禁用', dot: 'bg-ink-faint', tone: 'neutral' },
}

const PERMISSION_OPTIONS = [
  { value: '', label: '自动推断' },
  { value: 'safe', label: '只读（直接执行）' },
  { value: 'confirm', label: '需确认' },
  { value: 'admin', label: '高危（需开启）' },
]


const SECRET_KEY_HINT = /key|token|secret|password|passwd|credential|auth/i

function emptyConfig(): McpServerConfig {
  return {
    name: '',
    
    transport: 'stdio',
    url: '',
    headers: {},
    command: '',
    args: [],
    env: {},
    cwd: null,
    enabled: true,
    auto_start: true,
    description: '',
    timeout: 60,
    permission_overrides: {},
  }
}

function linesToArgs(text: string): string[] {
  return text
    .split('\n')
    .map((line) => line.trim())
    .filter(Boolean)
}

function argsToLines(args: string[]): string {
  return args.join('\n')
}


const TRANSPORT_OPTIONS: Array<{ value: McpServerConfig['transport']; label: string }> = [
  { value: 'stdio', label: '本地进程（stdio）' },
  { value: 'streamable_http', label: '远程 · Streamable HTTP' },
  { value: 'sse', label: '远程 · SSE' },
]

function envToText(env: Record<string, string>): string {
  return Object.entries(env)
    .map(([key, value]) => `${key}=${value}`)
    .join('\n')
}

function textToEnv(text: string): Record<string, string> {
  const env: Record<string, string> = {}
  for (const line of text.split('\n')) {
    const trimmed = line.trim()
    if (!trimmed || trimmed.startsWith('#')) continue
    const index = trimmed.indexOf('=')
    if (index <= 0) continue
    env[trimmed.slice(0, index).trim()] = trimmed.slice(index + 1).trim()
  }
  return env
}




function ToolRow({
  server,
  tool,
  onPermissionChange,
  busy,
}: {
  server: McpServerStatus
  tool: McpServerStatus['tools'][number]
  onPermissionChange: (tool: string, level: string) => void
  busy: boolean
}) {
  const override = server.permission_overrides?.[tool.name] ?? ''
  
  
  const hint = tool.destructive
    ? '服务端声明为破坏性操作'
    : tool.read_only
      ? '服务端声明为只读'
      : '未声明，默认按需确认处理'

  return (
    <div className="flex items-start gap-3 px-3.5 py-2.5">
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-[12.5px] font-medium text-ink">{tool.title || tool.name}</span>
          {

}
          <code className="rounded-[4px] bg-panel px-1 py-[1px] text-[11px] break-all text-ink-faint">
            {tool.name}
          </code>
        </div>
        {






}
        <p className="mt-0.5 min-w-0 text-[11.5px] leading-relaxed break-words whitespace-normal text-ink-soft">
          {tool.description || '（服务端未提供描述）'}
        </p>
        <p className="mt-0.5 text-[11px] break-words whitespace-normal text-ink-faint">{hint}</p>
      </div>

      {








}
      <div className="mt-0.5 w-[128px] shrink-0">
        <Select
          value={override}
          disabled={busy}
          onChange={(event) => onPermissionChange(tool.name, event.target.value)}
          className="h-7 text-[11.5px]"
        >
          {PERMISSION_OPTIONS.map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </Select>
      </div>
    </div>
  )
}




function ServerCard({
  server,
  busy,
  onToggle,
  onEdit,
  onRestart,
  onStop,
  onDelete,
  onPermissionChange,
}: {
  server: McpServerStatus
  busy: boolean
  onToggle: (enabled: boolean) => void
  

  onEdit: () => void
  onRestart: () => void
  onStop: () => void
  onDelete: () => void
  onPermissionChange: (tool: string, level: string) => void
}) {
  const [open, setOpen] = useState(false)
  const meta = STATE_META[server.state] ?? STATE_META.stopped
  const commandLine = [server.command, ...server.args].join(' ')

  return (
    <div
      className={clsx(
        'overflow-hidden rounded-[10px] border bg-canvas',
        server.state === 'error' ? 'border-danger/30' : 'border-line',
      )}
    >
      <div className="flex items-start gap-3 px-3.5 py-3">
        <span className={clsx('mt-[6px] h-[8px] w-[8px] shrink-0 rounded-full', meta.dot)} />

        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-[13.5px] font-medium text-ink">{server.name}</span>
            <Badge tone={meta.tone}>{meta.label}</Badge>
            {server.state === 'ready' ? (
              <span className="text-[11.5px] text-ink-faint">{server.tool_count} 个工具</span>
            ) : null}
            {server.restarts > 0 ? (
              <span className="text-[11.5px] text-warning">已重连 {server.restarts} 次</span>
            ) : null}
          </div>

          {server.description ? (
            <p className="mt-0.5 text-[12px] leading-relaxed text-ink-soft">{server.description}</p>
          ) : null}

          <code
            className="mt-1 block truncate text-[11px] text-ink-faint"
            title={commandLine}
          >
            {commandLine}
          </code>

          {server.message && server.state !== 'ready' ? (
            <div
              className={clsx(
                'mt-1.5 flex items-start gap-1.5 rounded-[6px] px-2 py-1.5 text-[11.5px] leading-relaxed',
                server.state === 'error'
                  ? 'bg-danger-soft text-ink-soft'
                  : 'bg-panel text-ink-soft',
              )}
            >
              {server.state === 'error' ? (
                <AlertTriangle size={12} className="mt-[2px] shrink-0 text-danger" />
              ) : (
                <Loader2 size={12} className="mt-[2px] shrink-0 animate-spin" />
              )}
              <span className="selectable break-words">{server.message}</span>
            </div>
          ) : null}
        </div>

        <div className="flex shrink-0 items-center gap-1 pt-0.5">
          <Switch
            checked={server.enabled}
            disabled={busy}
            onChange={onToggle}
            label={`启用 ${server.name}`}
          />
          {}
          <Button size="sm" variant="secondary" onClick={onEdit} disabled={busy}>
            配置
          </Button>
          <button
            type="button"
            onClick={onRestart}
            disabled={busy}
            title="重启"
            aria-label="重启"
            className="no-drag flex h-7 w-7 items-center justify-center rounded-[7px] text-ink-faint hover:bg-hover hover:text-ink disabled:opacity-40"
          >
            {busy ? <Loader2 size={14} className="animate-spin" /> : <RotateCw size={14} />}
          </button>
          <button
            type="button"
            onClick={onStop}
            disabled={busy || server.state === 'stopped' || server.state === 'disabled'}
            title="停止"
            aria-label="停止"
            className="no-drag flex h-7 w-7 items-center justify-center rounded-[7px] text-ink-faint hover:bg-hover hover:text-ink disabled:opacity-40"
          >
            <Square size={13} />
          </button>
          <button
            type="button"
            onClick={onDelete}
            title="删除"
            aria-label="删除"
            className="no-drag flex h-7 w-7 items-center justify-center rounded-[7px] text-ink-faint hover:bg-danger-soft hover:text-danger"
          >
            <Trash2 size={14} />
          </button>
        </div>
      </div>

      <button
        type="button"
        onClick={() => setOpen((value) => !value)}
        className="no-drag flex w-full items-center gap-1.5 border-t border-line-soft px-3.5 py-1.5 text-left text-[12px] text-ink-soft hover:bg-hover"
      >
        {open ? <ChevronDown size={13} /> : <ChevronRight size={13} />}
        <Wrench size={12} />
        {server.tool_count > 0 ? `查看工具（${server.tool_count}）` : '查看工具'}
      </button>

      {open ? (
        <div className="divide-y divide-line-soft border-t border-line-soft">
          {server.tools.length === 0 ? (
            <div className="px-3.5 py-4 text-center text-[12px] text-ink-faint">
              服务未连接，暂无工具。
            </div>
          ) : (
            server.tools.map((tool) => (
              <ToolRow
                key={tool.name}
                server={server}
                tool={tool}
                busy={busy}
                onPermissionChange={onPermissionChange}
              />
            ))
          )}
        </div>
      ) : null}
    </div>
  )
}




export function McpSettings() {
  const api = useAppStore((state) => state.api)
  const reloadSkills = useAppStore((state) => state.reloadSkills)

  const [servers, setServers] = useState<McpServerStatus[]>([])
  const [presets, setPresets] = useState<McpPreset[]>([])
  const [sdkAvailable, setSdkAvailable] = useState(true)
  const [loading, setLoading] = useState(false)
  const [busy, setBusy] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  const [form, setForm] = useState<McpServerConfig | null>(null)
  const [formIsNew, setFormIsNew] = useState(true)
  const [pendingDelete, setPendingDelete] = useState<McpServerStatus | null>(null)
  
  
  const [addChoiceOpen, setAddChoiceOpen] = useState(false)

  
  const [jsonOpen, setJsonOpen] = useState(false)
  const [jsonText, setJsonText] = useState('')
  const [jsonBusy, setJsonBusy] = useState(false)
  const [jsonResult, setJsonResult] = useState<McpImportResult | null>(null)
  const [jsonOverwrite, setJsonOverwrite] = useState(false)

  const submitJson = async () => {
    if (!api) return
    setJsonBusy(true)
    setJsonResult(null)
    try {
      const result = await api.importMcpJson(jsonText, jsonOverwrite)
      setJsonResult(result)
      if (result.added.length) {
        await load()
        await reloadSkills()
      }
    } catch (exc) {
      setJsonResult({
        ok: false,
        added: [],
        errors: [{ name: '整段 JSON', message: exc instanceof Error ? exc.message : String(exc) }],
        total: 0,
      })
    } finally {
      setJsonBusy(false)
    }
  }

  const load = useCallback(async () => {
    if (!api) return
    setLoading(true)
    try {
      const payload = await api.getMcpServers()
      setServers(payload.servers)
      setPresets(payload.presets)
      setSdkAvailable(payload.sdk_available)
      setError(null)
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : String(exc))
    } finally {
      setLoading(false)
    }
  }, [api])

  useEffect(() => {
    void load()
  }, [load])

  
  
  
  
  
  
  const skillsRefreshTimer = useRef<number | null>(null)
  useEffect(() => {
    const refreshSkillsSoon = () => {
      if (skillsRefreshTimer.current !== null) {
        window.clearTimeout(skillsRefreshTimer.current)
      }
      skillsRefreshTimer.current = window.setTimeout(() => {
        skillsRefreshTimer.current = null
        void reloadSkills()
      }, 400)
    }

    return subscribeAppEvents((event, data) => {
      if (event !== 'mcp_status') return
      const incoming = data.server as McpServerStatus
      setServers((prev) => {
        const index = prev.findIndex((item) => item.name === incoming.name)
        if (index < 0) return [...prev, incoming]
        const next = [...prev]
        next[index] = incoming
        return next
      })
      refreshSkillsSoon()
    })
  }, [reloadSkills])

  
  useEffect(
    () => () => {
      if (skillsRefreshTimer.current !== null) {
        window.clearTimeout(skillsRefreshTimer.current)
      }
    },
    [],
  )

  const run = async (key: string, action: () => Promise<unknown>) => {
    setBusy(key)
    setError(null)
    try {
      await action()
      await Promise.all([load(), reloadSkills()])
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : String(exc))
    } finally {
      setBusy(null)
    }
  }

  const submitForm = async () => {
    if (!api || !form) return
    const payload: McpServerConfig = {
      ...form,
      name: form.name.trim(),
      command: form.command.trim(),
      url: form.url.trim(),
    }
    
    
    if (!payload.name) {
      setError('服务名不能为空。')
      return
    }
    if (payload.transport === 'stdio' && !payload.command) {
      setError('本地（stdio）服务必须填写启动命令。')
      return
    }
    if (payload.transport !== 'stdio' && !payload.url) {
      setError('远程服务必须填写地址（URL）。')
      return
    }
    await run(formIsNew ? `create:${payload.name}` : `update:${payload.name}`, () =>
      formIsNew ? api.createMcpServer(payload) : api.updateMcpServer(payload.name, payload),
    )

    
    const secrets = Object.fromEntries(
      Object.entries(payload.env).filter(([key, value]) => SECRET_KEY_HINT.test(key) && value),
    )
    if (Object.keys(secrets).length > 0) {
      try {
        await window.agentBridge?.saveSecrets({ mcp: { [payload.name]: secrets } })
      } catch (error) {
        console.error('[mcp] 环境变量加密保存失败', error)
        setError('服务已保存，但密钥类环境变量写入加密存储失败，重启后可能需要重新填写。')
      }
    }
    setForm(null)
  }

  const openAdd = (preset?: McpPreset) => {
    setError(null)
    setFormIsNew(true)
    setForm(preset ? { ...emptyConfig(), ...preset.server } : emptyConfig())
  }

  







  const openEdit = (server: McpServerStatus) => {
    setError(null)
    setFormIsNew(false)
    setForm({
      name: server.name,
      transport: server.transport,
      url: server.url,
      headers: { ...server.headers },
      command: server.command,
      args: [...server.args],
      env: { ...server.env },
      cwd: server.cwd,
      enabled: server.enabled,
      auto_start: server.auto_start,
      description: server.description,
      timeout: server.timeout,
      permission_overrides: { ...server.permission_overrides },
    })
  }

  return (
    <div className="max-w-[880px]">
      <div className="flex items-start gap-4">
        <div className="flex-1">
          <h2 className="text-[15px] font-semibold text-ink">MCP 服务</h2>
          <p className="mt-1 text-[12.5px] leading-relaxed text-ink-soft">
            连接第三方 MCP Server，它的工具会自动出现在「技能」页签并交给模型使用。
            连接断开时工具会立即从模型的工具列表中移除，恢复后自动重新上线。
          </p>
        </div>
        <div className="flex gap-2">
          <Button
            icon={loading ? <Loader2 size={13} className="animate-spin" /> : <RefreshCw size={13} />}
            onClick={() => void load()}
            disabled={loading}
          >
            刷新服务
          </Button>
          <Button
            variant="primary"
            icon={<Plus size={13} />}
            onClick={() => setAddChoiceOpen(true)}
            disabled={!sdkAvailable}
          >
            添加服务
          </Button>
        </div>
      </div>

      {!sdkAvailable ? (
        <div className="mt-4 rounded-[10px] border border-warning/30 bg-warning-soft px-3.5 py-3">
          <div className="flex items-start gap-2">
            <AlertTriangle size={15} className="mt-0.5 shrink-0 text-warning" />
            <div className="text-[12.5px] leading-relaxed text-ink">
              <div className="font-medium">MCP 功能当前不可用：缺少 mcp 依赖</div>
              <div className="mt-1 text-ink-soft">
                在 core 目录执行：
                <code className="mx-1 rounded bg-canvas px-1 py-0.5">
                  .venv\Scripts\pip install "my-agent-core[mcp]"
                </code>
                后重启客户端即可。
              </div>
            </div>
          </div>
        </div>
      ) : null}

      {error ? (
        <div className="mt-3 rounded-[8px] border border-danger/30 bg-danger-soft px-3 py-2 text-[12.5px] text-danger">
          {error}
        </div>
      ) : null}

      {}
      {sdkAvailable && presets.length > 0 ? (
        <div className="mt-5">
          <div className="mb-2 text-[12.5px] font-medium text-ink-soft">快速添加</div>
          <div className="grid grid-cols-2 gap-2">
            {presets.map((preset) => (
              <button
                key={preset.key}
                type="button"
                onClick={() => openAdd(preset)}
                className="no-drag rounded-[10px] border border-line bg-canvas px-3.5 py-2.5 text-left transition-colors hover:border-brand/40 hover:bg-brand-soft/40"
              >
                <div className="flex items-center gap-2">
                  <Plug size={13} className="shrink-0 text-ink-faint" />
                  <span className="text-[13px] font-medium text-ink">{preset.title}</span>
                </div>
                <p className="mt-1 text-[11.5px] leading-relaxed text-ink-soft">
                  {preset.description}
                </p>
                <p className="mt-1 text-[11px] text-ink-faint">依赖：{preset.requires}</p>
              </button>
            ))}
          </div>
        </div>
      ) : null}

      {}
      <div className="mt-5 flex flex-col gap-3">
        {servers.map((server) => (
          <ServerCard
            key={server.name}
            server={server}
            busy={busy !== null && busy.endsWith(server.name)}
            onToggle={(enabled) =>
              void run(
                `update:${server.name}`,
                () => api?.updateMcpServer(server.name, { ...server, enabled }) ?? Promise.resolve(),
              )
            }
            onEdit={() => openEdit(server)}
            onRestart={() => void run(`restart:${server.name}`, () => api!.restartMcpServer(server.name))}
            onStop={() => void run(`stop:${server.name}`, () => api!.stopMcpServer(server.name))}
            onDelete={() => setPendingDelete(server)}
            onPermissionChange={(tool, level) =>
              void run(`perm:${server.name}`, () =>
                api!.setMcpToolPermission(server.name, tool, level),
              )
            }
          />
        ))}

        {servers.length === 0 && !loading ? (
          <div className="rounded-[10px] border border-dashed border-line px-4 py-10">
            <EmptyState
              title="还没有配置 MCP 服务"
              description="建议先添加「本地示例服务」——它随应用附带，不需要联网也不需要额外安装，可以立刻验证 MCP 链路是否通畅。"
            />
          </div>
        ) : null}
      </div>

      {}
      <Modal
        open={addChoiceOpen}
        onClose={() => setAddChoiceOpen(false)}
        width="max-w-md"
        title="添加 MCP 服务"
        description="手填一个，或把别人发你的 JSON 配置直接粘进来。"
        footer={<Button onClick={() => setAddChoiceOpen(false)}>取消</Button>}
      >
        <div className="grid grid-cols-1 gap-2">
          <button
            type="button"
            className="no-drag rounded-[10px] border border-line bg-canvas px-4 py-3 text-left transition-colors hover:border-brand/40 hover:bg-brand-soft/30"
            onClick={() => {
              setAddChoiceOpen(false)
              openAdd()
            }}
          >
            <div className="flex items-center gap-2 text-[13px] font-medium text-ink">
              <Plus size={14} />
              手动填写
            </div>
            <p className="mt-0.5 text-[11.5px] text-ink-faint">
              一项一项填：服务名、启动命令、参数。适合从零开始配。
            </p>
          </button>
          <button
            type="button"
            className="no-drag rounded-[10px] border border-line bg-canvas px-4 py-3 text-left transition-colors hover:border-brand/40 hover:bg-brand-soft/30"
            onClick={() => {
              setAddChoiceOpen(false)
              setJsonText('')
              setJsonResult(null)
              setJsonOpen(true)
            }}
          >
            <div className="flex items-center gap-2 text-[13px] font-medium text-ink">
              <Plug size={14} />
              粘贴 JSON（可批量）
            </div>
            <p className="mt-0.5 text-[11.5px] text-ink-faint">
              支持标准的 mcpServers 格式，一次粘进来多个服务，逐条校验。
            </p>
          </button>
        </div>
      </Modal>

      {}
      <Modal
        open={form !== null}
        onClose={() => setForm(null)}
        width="max-w-2xl"
        title={formIsNew ? '添加 MCP 服务' : `编辑：${form?.name}`}
        description="本地服务填启动命令；远程服务填地址与请求头。按空格拆分的直觉填写即可，每行一个参数。"
        footer={
          <>
            <Button onClick={() => setForm(null)}>取消</Button>
            <Button variant="primary" onClick={() => void submitForm()}>
              {formIsNew ? '添加并连接' : '保存'}
            </Button>
          </>
        }
      >
        {form ? (
          <div className="grid grid-cols-2 gap-3">
            <Field label="服务名" hint="会作为工具名字前缀，只能包含字母数字与 _ -">
              <Input
                value={form.name}
                disabled={!formIsNew}
                onChange={(event) => setForm({ ...form, name: event.target.value })}
                placeholder="例如 filesystem"
              />
            </Field>

            <Field label="启动命令">
              <Input
                value={form.command}
                onChange={(event) => setForm({ ...form, command: event.target.value })}
                placeholder="npx / uvx / python"
              />
            </Field>

            {
}
            <Field label="连接方式" className="col-span-2">
              <Select
                value={form.transport}
                onChange={(event) =>
                  setForm({ ...form, transport: event.target.value as McpServerConfig['transport'] })
                }
              >
                {TRANSPORT_OPTIONS.map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </Select>
            </Field>

            {form.transport === 'stdio' ? (
              <>
                <Field label="参数（每行一个）" className="col-span-2">
                  <textarea
                    value={argsToLines(form.args)}
                    onChange={(event) => setForm({ ...form, args: linesToArgs(event.target.value) })}
                    rows={3}
                    placeholder={'-y\n@modelcontextprotocol/server-filesystem\nD:\\某个目录'}
                    className="w-full resize-y rounded-[8px] border border-line bg-canvas px-2.5 py-2 font-mono text-[12px] leading-relaxed text-ink placeholder:text-ink-faint focus:border-brand focus:outline-none"
                  />
                </Field>

                <Field label="环境变量（每行 KEY=VALUE）" className="col-span-2">
                  <textarea
                    value={envToText(form.env)}
                    onChange={(event) => setForm({ ...form, env: textToEnv(event.target.value) })}
                    rows={2}
                    placeholder="API_KEY=xxx"
                    className="w-full resize-y rounded-[8px] border border-line bg-canvas px-2.5 py-2 font-mono text-[12px] leading-relaxed text-ink placeholder:text-ink-faint focus:border-brand focus:outline-none"
                  />
                </Field>

                <Field label="工作目录（可选）" className="col-span-2" hint="留空则继承客户端进程目录">
                  <div className="flex gap-2">
                    <Input
                      value={form.cwd ?? ''}
                      onChange={(event) => setForm({ ...form, cwd: event.target.value || null })}
                      placeholder="留空即可"
                    />
                    <Button
                      onClick={async () => {
                        const picked = await window.agentBridge.pickDirectory()
                        if (picked) setForm({ ...form, cwd: picked })
                      }}
                    >
                      选择
                    </Button>
                  </div>
                </Field>
              </>
            ) : (
              <>
                <Field label="地址（URL）" className="col-span-2" hint="服务端文档里给的 MCP 端点地址">
                  <Input
                    value={form.url}
                    onChange={(event) => setForm({ ...form, url: event.target.value })}
                    placeholder="https://example.com/mcp"
                  />
                </Field>

                <Field
                  label="请求头（每行 KEY=VALUE）"
                  className="col-span-2"
                  hint="鉴权头填这里，例如 Authorization=Bearer xxx。内容会被加密保存。"
                >
                  <textarea
                    value={envToText(form.headers)}
                    onChange={(event) => setForm({ ...form, headers: textToEnv(event.target.value) })}
                    rows={2}
                    placeholder="Authorization=Bearer xxx"
                    className="w-full resize-y rounded-[8px] border border-line bg-canvas px-2.5 py-2 font-mono text-[12px] leading-relaxed text-ink placeholder:text-ink-faint focus:border-brand focus:outline-none"
                  />
                </Field>
              </>
            )}

            <Field label="说明（可选）">
              <Input
                value={form.description}
                onChange={(event) => setForm({ ...form, description: event.target.value })}
                placeholder="这个服务用来做什么"
              />
            </Field>

            <Field label="单次调用超时（秒）">
              <Input
                type="number"
                min={5}
                max={600}
                value={form.timeout}
                onChange={(event) =>
                  setForm({ ...form, timeout: Number(event.target.value) || 60 })
                }
              />
            </Field>

            <div className="col-span-2 flex items-center gap-5 border-t border-line-soft pt-3">
              <label className="flex items-center gap-2 text-[12.5px] text-ink-soft">
                <Switch
                  checked={form.enabled}
                  onChange={(enabled) => setForm({ ...form, enabled })}
                  label="启用"
                />
                启用
              </label>
              <label className="flex items-center gap-2 text-[12.5px] text-ink-soft">
                <Switch
                  checked={form.auto_start}
                  onChange={(auto_start) => setForm({ ...form, auto_start })}
                  label="开机自动连接"
                />
                客户端启动时自动连接
              </label>
            </div>

            {form.command && ['npx', 'uvx'].includes(form.command.trim()) && (
              <div className="col-span-2 flex items-start gap-2 rounded-[8px] border border-line bg-panel px-3 py-2 text-[11.5px] leading-relaxed text-ink-soft">
                <AlertTriangle size={12} className="mt-[2px] shrink-0 text-warning" />
                <span>
                  用 {form.command.trim()} 启动时，首次连接需要联网下载对应包，可能要等几十秒。
                  若网络不可用，建议改用「本地示例服务」或自行编写 Python 版 Server。
                </span>
              </div>
            )}
          </div>
        ) : null}
      </Modal>

      {}
      <Modal
        open={pendingDelete !== null}
        onClose={() => setPendingDelete(null)}
        width="max-w-md"
        title="删除 MCP 服务"
        description="会断开连接并从模型中移除该服务的全部工具。"
        footer={
          <>
            <Button onClick={() => setPendingDelete(null)}>取消</Button>
            <Button
              variant="danger"
              onClick={() => {
                const target = pendingDelete
                setPendingDelete(null)
                if (target && api) {
                  void run(`delete:${target.name}`, () => api.deleteMcpServer(target.name))
                }
              }}
            >
              删除
            </Button>
          </>
        }
      >
        <p className="text-[13px] text-ink">
          确定删除「<span className="font-medium">{pendingDelete?.name}</span>」吗？
          它的 {pendingDelete?.tool_count ?? 0} 个工具将立即从模型可用列表中消失。
        </p>
      </Modal>

      {}
      <Modal
        open={jsonOpen}
        onClose={() => setJsonOpen(false)}
        width="max-w-2xl"
        title="粘贴 JSON 批量添加"
        description="MCP 生态里的配置基本都以一段 JSON 流通，直接粘进来比照着手工填表单省事得多。"
        footer={
          <>
            <Button onClick={() => setJsonOpen(false)}>关闭</Button>
            <Button
              variant="primary"
              icon={jsonBusy ? <Loader2 size={13} className="animate-spin" /> : undefined}
              onClick={() => void submitJson()}
              disabled={jsonBusy || !jsonText.trim()}
            >
              {jsonBusy ? '导入中…' : '导入'}
            </Button>
          </>
        }
      >
        <Field
          label="MCP 配置"
          hint={'形如 {"mcpServers": {"名字": {"command": "npx", "args": [...]}}}；也接受直接就是 {名字: 配置}'}
        >
          <textarea
            value={jsonText}
            onChange={(event) => setJsonText(event.target.value)}
            rows={10}
            spellCheck={false}
            placeholder={
              '{\n  "mcpServers": {\n    "filesystem": {\n      "command": "npx",\n      "args": ["-y", "@modelcontextprotocol/server-filesystem", "C:\\\\Users\\\\me"]\n    }\n  }\n}'
            }
            className="w-full resize-y rounded-[8px] border border-line bg-canvas px-2.5 py-2 font-mono text-[12px] leading-relaxed text-ink placeholder:text-ink-faint focus:border-brand focus:outline-none"
          />
        </Field>

        <label className="mt-3 flex items-center gap-2 text-[12.5px] text-ink-soft">
          <Switch checked={jsonOverwrite} onChange={setJsonOverwrite} label="覆盖同名服务" />
          已存在同名服务时覆盖它（不选则跳过并提示）
        </label>

        {jsonResult ? (
          <div className="mt-3">
            {jsonResult.added.length ? (
              <div className="rounded-[8px] border border-success/30 bg-success-soft px-3 py-2 text-[12.5px] text-success">
                已添加 {jsonResult.added.length} 个：{jsonResult.added.join('、')}
              </div>
            ) : null}
            {jsonResult.errors.length ? (
              <div className="mt-2 rounded-[8px] border border-danger/30 bg-danger-soft px-3 py-2">
                <div className="text-[12.5px] text-danger">
                  {jsonResult.errors.length} 个没能导入：
                </div>
                <ul className="mt-1 space-y-1">
                  {jsonResult.errors.map((item: { name: string; message: string }) => (
                    <li key={item.name} className="text-[12px] text-ink-soft">
                      <span className="font-medium text-ink">{item.name}</span>：{item.message}
                    </li>
                  ))}
                </ul>
              </div>
            ) : null}
          </div>
        ) : null}
      </Modal>
    </div>
  )
}
