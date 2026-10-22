(async () => {
  const qid = process.env.QID
  let content = process.env.CONTENT || ''
  if (process.env.CONTENT_FILE) {
    const fs = require('fs')
    content = fs.readFileSync(process.env.CONTENT_FILE, 'utf8')
  }
  if (!qid || !content.trim()) { cliLog('ERROR: set QID and CONTENT (or CONTENT_FILE)'); return }

  const space = 'zhihu-answer-' + qid
  const task = await useOrCreateTaskSpace(space)
  const url = 'https://www.zhihu.com/question/' + qid
  await openOrReuseTab(url, { wait: true, timeout: 20 })
  await wait(3)

  const opened = await js('(() => {'
    + ' const btns = Array.from(document.querySelectorAll("button"));'
    + ' const b = btns.find(function(x){ return x.innerText.indexOf("写回答") >= 0; });'
    + ' if (b) { b.click(); return true; }'
    + ' return false;'
    + '})()')
  cliLog('editor-opened: ' + opened)
  await wait(3)

  // 直接 UTF-8 中文，勿用 String.raw；content 内用空行分段（ClipboardEvent 粘贴保留段落）
  await js('((text) => {'
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
  await wait(2)

  cliLog('risk-control wait 60s before publish...')
  await wait(60)

  const pub = await js('(() => {'
    + ' const btns = Array.from(document.querySelectorAll("button"));'
    + ' const b = btns.find(function(x){ return x.innerText.trim() === "发布回答"; });'
    + ' if (b) { b.click(); return true; }'
    + ' return false;'
    + '})()')
  cliLog('publish-clicked: ' + pub)
  await wait(8)

  const info = await pageInfo()
  cliLog('after-publish-url: ' + info.url)
  const m = info.url.match(/answer\/(\d+)/)
  if (m) {
    const aid = m[1]
    cliLog('PUBLISHED aid=' + aid)
    cliLog('verify with: echo ' + JSON.stringify('{"aid":"' + aid + '","type":"answer"}') + ' > /tmp/zhihu_verify_params.json && ego-browser nodejs < scripts/verify_via_cli.js')
  } else {
    cliLog('WARN: url did not jump to /answer/{aid} — possible publish stuck (see risk-control: do NOT retry)')
  }
  await completeTaskSpace(space, { keep: false })
})()
