

















(async () => {
  const fs = require('fs')
  const path = require('path')

  
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

  
  const dryRun = P.dryRun !== false
  cliLog('DRY_RUN: ' + dryRun + (dryRun ? ' (replace editor content only, will NOT submit)' : ''))

  if (!P.aid) { cliLog('ERROR: set aid (params file or env)'); return }
  const url = P.answerUrl || (P.qid ? ('https://www.zhihu.com/question/' + P.qid + '/answer/' + P.aid) : ('https://www.zhihu.com/answer/' + P.aid))

  
  const space = 'zhihu-edit-' + P.aid
  const task = await useOrCreateTaskSpace(space)
  await openOrReuseTab(url, { wait: true, timeout: 25 })
  await wait(6)
  const opened = await js('(() => { const btns = Array.from(document.querySelectorAll("button")); const b = btns.find(function (x) { return (x.innerText || "").indexOf("编辑回答") >= 0; }); if (b) { b.click(); return true; } return false; })()')
  cliLog('EDIT_OPENED: ' + opened)
  if (opened !== true) { cliLog('STOP: no 「编辑回答」 button (检查登录态/回答归属)'); await completeTaskSpace(space, { keep: false }); return }
  await wait(8)

  
  await js('(() => { const ed = document.querySelector(".public-DraftEditor-content"); if (!ed) return "no_editor"; ed.focus(); document.execCommand("selectAll"); document.execCommand("delete"); return "cleared"; })()')
  await wait(2)
  const esc = content.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
  const html = esc.split(/\n\n+/).map(function (par) { return '<p>' + par.replace(/\n/g, '<br>') + '</p>'; }).join('')
  const ins = await js('(() => { const ed = document.querySelector(".public-DraftEditor-content"); if (!ed) return "no_editor"; ed.focus(); const ok = document.execCommand("insertHTML", false, ' + JSON.stringify(html) + '); return ok ? "inserted" : "insert_failed"; })()')
  cliLog('INSERT: ' + ins)
  await wait(3)

  
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

  
  await scrollBy(800)
  await wait(3)
  const sub = await js('(() => { const btns = Array.from(document.querySelectorAll("button")); const b = btns.find(function (x) { return (x.innerText || "").trim() === "提交修改"; }); if (b) { b.click(); return "clicked"; } return "not_found"; })()')
  cliLog('SUBMIT: ' + sub)
  if (sub !== 'clicked') { cliLog('STOP: 「提交修改」按钮未找到，未提交'); await completeTaskSpace(space, { keep: false }); return }

  
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









