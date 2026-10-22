














(async () => {
  const fs = require('fs')
  const path = require('path')

  
  function loadParams() {
    const p = {}
    if (process.env.CONTENT) p.content = process.env.CONTENT
    if (process.env.CONTENT_FILE) p.contentFile = process.env.CONTENT_FILE
    if (process.env.DRY_RUN) p.dryRun = (process.env.DRY_RUN === '1' || process.env.DRY_RUN === 'true')
    const file = '/tmp/zhihu_moment_params.json'
    try {
      const f = JSON.parse(fs.readFileSync(file, 'utf8'))
      for (const k of ['content', 'contentFile', 'configPath', 'dryRun']) {
        if (f[k] != null && p[k] == null) p[k] = f[k]
      }
      cliLog('PARAMS_FROM_FILE: ' + file)
    } catch (e) {
      cliLog('PARAMS_FILE_MISSING: ' + file + ' (' + e.message + ')')
    }
    return p
  }
  const P = loadParams()

  
  function loadConfig() {
    const candidates = []
    if (P.configPath) candidates.push(P.configPath)
    candidates.push(path.join(process.cwd(), 'config.json'))
    candidates.push(path.join(__dirname, '..', 'config.json'))
    for (const c of candidates) {
      if (!c) continue
      try { return { path: c, data: JSON.parse(fs.readFileSync(c, 'utf8')) } } catch (e) {}
    }
    return null
  }
  const cfg = loadConfig()
  const mCfg = (cfg && cfg.data && cfg.data.moments) || {}
  const minW = mCfg.min_words || 50
  const maxW = mCfg.max_words || 150
  if (cfg) cliLog('CONFIG_LOADED: ' + cfg.path)

  
  let content = P.content || ''
  if (!content && P.contentFile) {
    try { content = fs.readFileSync(P.contentFile, 'utf8') } catch (e) {
      cliLog('ERROR: cannot read contentFile ' + P.contentFile + ' (' + e.message + ')'); return
    }
    cliLog('CONTENT_FROM_FILE: ' + P.contentFile)
  }
  content = (content || '').trim()
  if (!content) { cliLog('ERROR: no content (set content or contentFile)'); return }
  const w = content.length
  cliLog('CONTENT_LEN: ' + w + ' (config range ' + minW + '-' + maxW + ')')
  if (w < minW || w > maxW) cliLog('WARN: length outside configured moments range — publishing anyway')

  
  const dryRun = P.dryRun !== false
  if (P.dryRun == null) cliLog('DRY_RUN_DEFAULT: 未显式设置 dryRun，默认只填不发布（实发请在参数文件写 "dryRun": false）')
  cliLog('DRY_RUN: ' + dryRun + (dryRun ? ' (fill only, will NOT publish)' : ''))

  
  const space = 'zhihu-moment'
  const task = await useOrCreateTaskSpace(space)
  await openOrReuseTab('https://www.zhihu.com', { wait: true, timeout: 25 })
  await wait(6)

  const opened = await js('(() => {'
    + ' const btns = Array.from(document.querySelectorAll("button, a, div[role=button]"));'
    + ' for (let i = 0; i < btns.length; i++) {'
    + '   const t = (btns[i].innerText || "").trim();'
    + '   if (t.indexOf("发想法") >= 0) { btns[i].click(); return "clicked:" + t; }'
    + ' }'
    + ' return "no_entry";'
    + '})()')
  cliLog('EDITOR_OPEN: ' + opened)
  if (opened === 'no_entry') {
    cliLog('ERROR: 未找到「发想法」入口，可能未登录或页面结构变化')
    await completeTaskSpace(space, { keep: false })
    return
  }
  await wait(6)

  
  try {
    const ok = await js('((text) => {'
      + ' const editor = document.querySelector(".public-DraftEditor-content");'
      + ' if (!editor) return false;'
      + ' editor.focus();'
      + ' const range = document.createRange();'
      + ' range.selectNodeContents(editor);'
      + ' range.collapse(false);'
      + ' const sel = window.getSelection();'
      + ' sel.removeAllRanges();'
      + ' sel.addRange(range);'
      + ' const dt = new DataTransfer();'
      + ' dt.setData("text/plain", text);'
      + ' editor.dispatchEvent(new ClipboardEvent("paste", { clipboardData: dt, bubbles: true, cancelable: true, composed: true }));'
      + ' return true;'
      + '})(' + JSON.stringify(content) + ')')
    if (!ok) throw new Error('DraftEditor not found, 想法内容未注入')
    cliLog('FILLED: ok')
  } catch (e) {
    cliLog('FILL_FAILED: ' + e.message + ' — 若报 Element not found，先查登录态（页面是否「登录/注册」）')
    await completeTaskSpace(space, { keep: false })
    return
  }
  await wait(3)

  if (dryRun) {
    cliLog('DRY_RUN_STOP: 已填内容，按要求不发布。确认无误后去掉 dryRun 再跑一次。')
    await completeTaskSpace(space, { keep: false })
    return
  }

  
  cliLog('risk-control wait 30s before publish...')
  await wait(30)

  const pub = await js('(() => {'
    + ' const ed = document.querySelector(".public-DraftEditor-content");'
    + ' if (!ed) return "no_editor";'
    + ' let root = ed;'
    + ' for (let i = 0; i < 10 && root; i++) {'
    + '   const bs = Array.from(root.querySelectorAll("button"));'
    + '   const b = bs.find(function (x) { return (x.innerText || "").trim() === "发布"; });'
    + '   if (b) { b.click(); return "clicked"; }'
    + '   root = root.parentElement;'
    + ' }'
    + ' return "no_publish_button";'
    + '})()')
  cliLog('PUBLISH_CLICK: ' + pub)
  if (pub !== 'clicked') {
    cliLog('ERROR: 发布失败 — ' + pub + '。不要重试（避免累积卡死草稿），人工检查。')
    await completeTaskSpace(space, { keep: false })
    return
  }
  await wait(12)

  
  
  
  
  
  const verify = await js('(() => {'
    + ' const still = document.querySelectorAll(".public-DraftEditor-content").length;'
    + ' return JSON.stringify({ editorRemaining: still, url: location.href });'
    + '})()')
  cliLog('VERIFY_PAGE_ONLY(unreliable): ' + verify)
  cliLog('VERIFY_HINT: 用 `zhihu-cli me contents --type pin --limit 3` 做权威校验（想法类型=pin）')
  cliLog('MOMENT_DONE' + (dryRun ? ' (dry run)' : ''))

  await completeTaskSpace(space, { keep: false })
})()








