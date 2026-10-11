import { useEffect, useState } from 'react'

import { Button, Field, Input, Select } from '@/components/ui'
import { useAppStore } from '@/stores/appStore'
import { useNotificationStore } from '@/stores/notificationStore'
import type { CalendarConfig } from '@/types'

/**
 * 「日历」设置区块。
 *
 * 两种用法，默认那种**不用配任何东西**：
 *
 * - **本地日历**（默认）：日程存在本机数据目录下的 `calendar/local.ics`。
 *   这个文件本身就是标准 iCalendar —— 可以导出到手机/系统日历，也能把它们导出的
 *   文件放回来，数据不是锁在应用里的。
 * - **在线日历（CalDAV）**：填地址、账号、密码就能直接读写苹果日历 / Nextcloud 等。
 *   配好之后 `auto` 模式会自动改走在线，用户不必再回来手动切换。
 *
 * 密码的存法与模型 Key 完全一致：**先在主进程用系统加密存起来**（下次启动注入），
 * 再随这次提交把明文交给本地后端放进内存。所以它既不会明文落盘，也不会因为
 * 一次"保存设置"就丢 —— 后端把空值当成"用户没动它"。
 */
export function CalendarSettings() {
  const settings = useAppStore((state) => state.settings)
  const api = useAppStore((state) => state.api)
  const reloadSettings = useAppStore((state) => state.reloadSettings)
  const push = useNotificationStore((state) => state.push)

  const [draft, setDraft] = useState<CalendarConfig | null>(null)
  /** 已保存密码的脱敏预览（形如 `ab****cd`），用来告诉用户"已经配过了" */
  const [maskedPassword, setMaskedPassword] = useState('')
  /** 用户这次输入的密码：留空表示不改（后端同样按空值忽略处理） */
  const [passwordInput, setPasswordInput] = useState('')
  const [busy, setBusy] = useState(false)
  const [testing, setTesting] = useState(false)

  useEffect(() => {
    if (settings?.calendar && !draft) setDraft({ ...settings.calendar })
  }, [settings, draft])

  useEffect(() => {
    void window.agentBridge
      ?.getSecretsMasked()
      .then((payload) => setMaskedPassword(payload.integrations?.calendar?.password ?? ''))
      .catch(() => setMaskedPassword(''))
  }, [])

  if (!settings || !draft) {
    return <p className="text-[12.5px] text-ink-faint">设置加载中…</p>
  }

  const patch = (changes: Partial<CalendarConfig>) => setDraft({ ...draft, ...changes })

  const needsCaldav = draft.mode !== 'local'

  const save = async () => {
    if (!api) return
    setBusy(true)
    try {
      // 顺序有讲究：**先落密码再提交设置**。
      // 反过来的话，提交设置时如果密码还没进加密存储，后端内存里那份会被这次
      // 提交覆盖成空（只有当用户确实输入了新密码时才有区别，但顺序一致更省心）
      if (passwordInput.trim()) {
        await window.agentBridge?.saveSecrets({
          integrations: { calendar: { password: passwordInput.trim() } },
        })
        setMaskedPassword('')
        void window.agentBridge
          ?.getSecretsMasked()
          .then((payload) => setMaskedPassword(payload.integrations?.calendar?.password ?? ''))
      }

      const saved = await api.saveSettings({
        ...settings,
        calendar: { ...draft, caldav_password: passwordInput.trim() },
      })
      useAppStore.setState({ settings: saved })
      setPasswordInput('')
      await reloadSettings()
      push({ level: 'success', title: '日历设置已保存', message: describeMode(saved.calendar) })
    } catch (error) {
      push({
        level: 'error',
        title: '日历设置保存失败',
        message: error instanceof Error ? error.message : String(error),
        autoDismissMs: 0,
      })
    } finally {
      setBusy(false)
    }
  }

  const test = async () => {
    if (!api) return
    setTesting(true)
    try {
      const result = await api.testCalendar({
        caldav_url: draft.caldav_url,
        caldav_username: draft.caldav_username,
        // 留空 = 用已保存的那份密码（后端这么约定，界面不回显密码）
        caldav_password: passwordInput.trim() || undefined,
      })
      push({
        level: 'success',
        title: '连接成功',
        message: `${result.message}${result.sample.length ? `\n例如：${result.sample[0].text}` : ''}`,
        autoDismissMs: 0,
      })
    } catch (error) {
      push({
        level: 'error',
        title: '连不上日历服务',
        message: error instanceof Error ? error.message : String(error),
        autoDismissMs: 0,
      })
    } finally {
      setTesting(false)
    }
  }

  return (
    /*
      ⚠️ `max-w-[880px]`：这一页原先只有内部字段区限了宽（见下面的
      `max-w-[560px]`），整页内容却是铺满的。加个宽度上限，让它和同一排的其它设置页一致。

      ⚠️ **不要再加 `mx-auto`**：居中那一版用户看过之后说"并不好看" ——
      他要的是内容**贴着左边**，不是飘在中间。
    */
    <section className="mb-8 max-w-[880px]">
      <h2 className="text-[15px] font-semibold text-ink">日历</h2>
      <p className="mt-1 text-[12.5px] leading-relaxed text-ink-soft">
        搭子可以查看、新建、修改、删除日程。默认用**本机日历**（数据目录下的
        <code className="mx-1 rounded bg-panel px-1 text-[11.5px]">calendar/local.ics</code>
        ，标准 iCalendar 格式，可导出到手机或系统日历）；填了 CalDAV 就自动改走在线。
      </p>

      <div className="mt-4 max-w-[560px] space-y-3">
        <Field label="用哪个日历" hint={describeMode(draft)}>
          <Select
            value={draft.mode}
            onChange={(event) =>
              patch({ mode: event.target.value as CalendarConfig['mode'] })
            }
          >
            <option value="auto">自动（配了在线就用在线，否则用本机）</option>
            <option value="local">只用本机日历</option>
            <option value="caldav">只用在线日历（CalDAV）</option>
          </Select>
        </Field>

        <Field label="本地日历名称" hint="会写进导出的 .ics 文件，方便在手机日历里区分">
          <Input
            value={draft.calendar_name}
            onChange={(event) => patch({ calendar_name: event.target.value })}
          />
        </Field>

        {needsCaldav ? (
          <>
            <Field
              label="CalDAV 地址"
              hint="填**日历集合**的地址（通常在账号首页下面），例如 https://caldav.example.com/calendars/你的账号/个人日历/"
            >
              <Input
                value={draft.caldav_url}
                placeholder="https://caldav.example.com/"
                onChange={(event) => patch({ caldav_url: event.target.value })}
              />
            </Field>

            <Field label="账号">
              <Input
                value={draft.caldav_username}
                placeholder="通常是邮箱或用户名"
                onChange={(event) => patch({ caldav_username: event.target.value })}
              />
            </Field>

            <Field
              label="密码 / 应用专用密码"
              hint={
                maskedPassword
                  ? `已保存：${maskedPassword}（留空表示不改动）`
                  : '保存后会加密托管在本机，不会明文写进配置文件'
              }
            >
              <Input
                type="password"
                value={passwordInput}
                placeholder={maskedPassword ? '留空表示不改动' : '填入日历密码'}
                onChange={(event) => setPasswordInput(event.target.value)}
              />
            </Field>

            <div className="flex items-center gap-2">
              <Button onClick={() => void test()} disabled={testing || busy}>
                {testing ? '正在测试…' : '测试连接'}
              </Button>
              <span className="text-[11.5px] text-ink-faint">
                测试用的是上面填的值（密码留空则用已保存的那份）
              </span>
            </div>
          </>
        ) : null}

        <Field label="默认日程时长（分钟）" hint="新建日程时没给结束时间，就按这个时长排">
          <Input
            type="number"
            min={5}
            max={1440}
            value={draft.default_duration_minutes}
            onChange={(event) =>
              patch({ default_duration_minutes: Number(event.target.value) || 60 })
            }
          />
        </Field>

        <div className="flex items-center gap-2 pt-1">
          <Button variant="primary" onClick={() => void save()} disabled={busy}>
            {busy ? '保存中…' : '保存日历设置'}
          </Button>
          <span className="text-[11.5px] text-ink-faint">
            改动只影响日历，不会动其它设置
          </span>
        </div>
      </div>
    </section>
  )
}

function describeMode(config: CalendarConfig): string {
  if (config.mode === 'local') return '当前固定使用本机日历'
  const configured = Boolean(config.caldav_url && config.caldav_username)
  if (config.mode === 'caldav') {
    return configured ? '当前固定使用在线日历' : '还没填 CalDAV 地址或账号，暂时用不了在线日历'
  }
  return configured ? '已配置在线日历，读写会走在线' : '还没配在线日历，当前用本机日历'
}
