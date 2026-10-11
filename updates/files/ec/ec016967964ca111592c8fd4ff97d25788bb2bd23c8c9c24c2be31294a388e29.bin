// edit_answer.js — 修改已发布的知乎回答
// 用法（Bash 必须 dangerouslyDisableSandbox:true，且关闭沙箱开关）：
//   先把参数写到 /tmp/zhihu_edit_params.json（见底部 schema），再：
//   ego-browser nodejs < scripts/edit_answer.js
//
// 行为：打开回答页 → 点「编辑回答」→ 清空编辑器 → insertHTML 注入新内容
//       → 校验长度/残留符号 → （dryRun 则停）→ 点「提交修改」→ 轮询编辑态退出
//
// ⚠️ 已知限制（2026-09-01 实测）：
//   内容替换本身已验证可行（fillInput 在清空后的 Draft.js 上失效，len=1；
//   唯一可行方法 = selectAll+delete → execCommand('insertHTML', '<p>…</p>…')）。
//   但 `js click('提交修改')` **无法触发提交**（无弹窗、无报错、编辑态不退出，
//   疑似需 mousedown/mouseup 序列或 React 特殊处理）。
//   因此脚本提交后轮询 5 次，编辑态未退出即输出 SUBMIT_NOT_EFFECTIVE 并停止
//   ——绝不重试点击（防重复提交/风控）。此时请人工在 ego lite 确认。
//
// 🚫 生成源文件禁止 Markdown（`**`、行首 `- ` 会按字面残留）；可用 stripMarkdown:true 自动清洗。

(async () => {
  const fs = require('fs')
  const path = require('path')

  // ---------- 0. 参数加载（env 优先，回退参数文件） ----------
  function loadParams() {
    const p = {}
    if (process.env.AID) p.aid = process.env.AID
    if (process.env.QID) p.qid = process.env.QID
    if (process.env.CONTENT) p.content = process.env.CONTENT
    if (process.env.CONTENT_FILE) p.contentFile = process.env.CONTENT_FILE
    const file = '/tmp/zhihu_edit_params.json'
    try {
      const f = JSON.parse(fs.readFileSync(file, 'utf8'))
      for (const k of ['aid', 'qid', 'answerUrl', 'content', 'contentFile', 'configPath', 'dryRun', 'stripMarkdown']) {
        if (f[k] != null && p[k] == null) p[k] = f[k]
      }
      cliLog('PARAMS_FROM_FILE: ' + file)
    } catch (e) {
      cliLog('PARAMS_FILE_MISSING: ' + file + ' (' + e.message + ')')
    }
    return p
  }
  const P = loadParams()

  // ---------- 1. 正文（可选 Markdown 自动清洗） ----------
  let content = P.content || ''
  if (!content && P.contentFile) {
    try { content = fs.readFileSync(P.contentFile, 'utf8') } catch (e) {
      cliLog('ERROR: cannot read contentFile ' + P.contentFile + ' (' + e.message + ')'); return
    }
    cliLog('CONTENT_FROM_FILE: ' + P.contentFile)
  }
  content = (content || '').trim()
  if (!content) { cliLog('ERROR: no content (set content or contentFile)'); return }
  if (P.stripMarkdown === true) {
    content = content.replace(/\*\*/g, '').replace(/^- /gm, '· ')
    cliLog('STRIP_MARKDOWN: done')
  }
  if (content.indexOf('**') >= 0) cliLog('WARN: content still contains ** — Zhihu editor renders it literally')
  const expectedLen = content.length
  cliLog('CONTENT_LEN: ' + expectedLen)

  // Fail-safe（与 post_moment.js 一致）：未显式 dryRun=false 只改编辑器草稿、不提交
  const dryRun = P.dryRun !== false
  cliLog('DRY_RUN: ' + dryRun + (dryRun ? ' (replace editor content only, will NOT submit)' : ''))

  if (!P.aid) { cliLog('ERROR: set aid (params file or env)'); return }
  const url = P.answerUrl || (P.qid ? ('https://www.zhihu.com/question/' + P.qid + '/answer/' + P.aid) : ('https://www.zhihu.com/answer/' + P.aid))

  // ---------- 2. 打开编辑器 ----------
  const space = 'zhihu-edit-' + P.aid
  const task = await useOrCreateTaskSpace(space)
  await openOrReuseTab(url, { wait: true, timeout: 25 })
  await wait(6)
  const opened = await js('(() => { const btns = Array.from(document.querySelectorAll("button")); const b = btns.find(function (x) { return (x.innerText || "").indexOf("编辑回答") >= 0; }); if (b) { b.click(); return true; } return false; })()')
  cliLog('EDIT_OPENED: ' + opened)
  if (opened !== true) { cliLog('STOP: no 「编辑回答」 button (检查登录态/回答归属)'); await completeTaskSpace(space, { keep: false }); return }
  await wait(8)

  // ---------- 3. 清空 + insertHTML（唯一已验证的内容替换方法） ----------
  await js('(() => { const ed = document.querySelector(".public-DraftEditor-content"); if (!ed) return "no_editor"; ed.focus(); document.execCommand("selectAll"); document.execCommand("delete"); return "cleared"; })()')
  await wait(2)
  const esc = content.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
  const html = esc.split(/\n\n+/).map(function (par) { return '<p>' + par.replace(/\n/g, '<br>') + '</p>'; }).join('')
  const ins = await js('(() => { const ed = document.querySelector(".public-DraftEditor-content"); if (!ed) return "no_editor"; ed.focus(); const ok = document.execCommand("insertHTML", false, ' + JSON.stringify(html) + '); return ok ? "inserted" : "insert_failed"; })()')
  cliLog('INSERT: ' + ins)
  await wait(3)

  // ---------- 4. 护栏校验（不过即停，绝不提交坏内容） ----------
  const chk = await js('(() => { const ed = document.querySelector(".public-DraftEditor-content"); return JSON.stringify({ len: ed ? ed.innerText.length : -1, hasStar: ed ? (ed.innerText.indexOf("**") >= 0) : null }); })()')
  cliLog('CHECK: ' + chk + ' (expected_len≈' + expectedLen + ')')
  const c = JSON.parse(chk)
  const tol = Math.max(80, Math.round(expectedLen * 0.15))
  if (c.len < expectedLen - tol || c.len > expectedLen + tol || c.hasStar) {
    cliLog('STOP: content check failed (len/符号不符)，编辑器草稿保留、未提交。人工检查后重跑。')
    await completeTaskSpace(space, { keep: false })
    return
  }

  if (dryRun) {
    cliLog('DRY_RUN_STOP: 编辑器已替换为新内容（未提交）。浏览器确认无误后，写 "dryRun": false 再跑一次提交。')
    await completeTaskSpace(space, { keep: false })
    return
  }

  // ---------- 5. 提交（按钮真名=「提交修改」） ----------
  await scrollBy(800)
  await wait(3)
  const sub = await js('(() => { const btns = Array.from(document.querySelectorAll("button")); const b = btns.find(function (x) { return (x.innerText || "").trim() === "提交修改"; }); if (b) { b.click(); return "clicked"; } return "not_found"; })()')
  cliLog('SUBMIT: ' + sub)
  if (sub !== 'clicked') { cliLog('STOP: 「提交修改」按钮未找到，未提交'); await completeTaskSpace(space, { keep: false }); return }

  // ---------- 6. 轮询编辑态退出（可能弹确认框，组合词包含匹配） ----------
  let exited = false
  for (let i = 0; i < 5; i++) {
    await wait(4)
    const st = await js('(() => {'
      + ' const btns = Array.from(document.querySelectorAll("button"));'
      + ' const stillEditing = btns.some(function (x) { return (x.innerText || "").trim() === "提交修改"; });'
      + ' const modalBtns = btns.filter(function (b) { const t = (b.innerText || "").trim(); return t && t !== "提交修改" && t !== "发布设置" && /确认|确定|发布|提交/.test(t); }).map(function (b) { return (b.innerText || "").trim(); });'
      + ' return JSON.stringify({ stillEditing: stillEditing, modalBtns: modalBtns.slice(0, 5) });'
      + '})()')
    cliLog('POLL' + (i + 1) + ': ' + st)
    const s = JSON.parse(st)
    if (!s.stillEditing) { exited = true; break }
    if (s.modalBtns.length) {
      const clicked = await js('(() => { const btns = Array.from(document.querySelectorAll("button")).filter(function (b) { const t = (b.innerText || "").trim(); return t && t !== "提交修改" && t !== "发布设置" && /确认|确定|发布|提交/.test(t); }); if (btns.length) { const t = (btns[0].innerText || "").trim(); btns[0].click(); return "clicked:" + t; } return "none"; })()')
      cliLog('CONFIRM_CLICK: ' + clicked)
    }
  }

  // ---------- 7. 结果判定（已知问题：提交点击可能被吞） ----------
  if (exited) {
    cliLog('EDIT_DONE: 提交生效（编辑态已退出）。用 `zhihu-cli me contents --type answer --limit 1` 做权威复核（注意 ~30 分钟内二次修改不更新 updated_time）。')
  } else {
    cliLog('SUBMIT_NOT_EFFECTIVE: 「提交修改」点击未被响应（已知问题，2026-09-01 实测）。已停止，不重试点击。')
    cliLog('ACTION: 请人工在 ego lite 打开该回答确认——编辑器里已是新内容，手动点「提交修改」即可；或先「保存草稿并离开」。')
  }
  const info = await pageInfo()
  cliLog('AFTER_URL: ' + info.url)
  await completeTaskSpace(space, { keep: false })
})()

// 参数文件 schema（/tmp/zhihu_edit_params.json）：
// {
//   "aid": "2078057751377360832",        // 回答 id（必须）
//   "qid": "520978750",                  // 问题 id（可选；用于拼 /question/{qid}/answer/{aid}）
//   "contentFile": "/abs/new-text.txt",  // 新正文（与 content 二选一）
//   "stripMarkdown": true,               // 可选：自动去 ** 与行首 "- "
//   "dryRun": true                       // 默认 true（fail-safe，只替换编辑器草稿不提交）；提交须显式 false
// }
