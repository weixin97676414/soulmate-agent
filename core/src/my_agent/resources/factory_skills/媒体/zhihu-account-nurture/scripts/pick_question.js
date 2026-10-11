(async () => {
  const kwRaw = process.env.KW || '历史,古代,朝代,皇帝,考古,文物,神话,孔子,老子,诗词,传统,三国,唐,宋,明,清,曾国藩,王阳明,周易,兵法,职场,中年,人际,心理,代际,社交,断舍离'
  const kw = kwRaw.split(',').map(function(s){ return s.trim(); }).filter(Boolean)
  const limit = parseInt(process.env.LIMIT || '25', 10)
  const space = 'zhihu-pick'
  const task = await useOrCreateTaskSpace(space)
  await openOrReuseTab('https://www.zhihu.com/hot', { wait: true, timeout: 20 })
  await wait(5)
  const hot = await js('(() => {'
    + ' const items = Array.from(document.querySelectorAll(".HotItem"));'
    + ' const out = [];'
    + ' for (let i=0;i<items.length && i<' + limit + ';i++){'
    + '   const el = items[i];'
    + '   const a = el.querySelector("a");'
    + '   const titleEl = el.querySelector(".HotItem-title") || a;'
    + '   const metrics = el.querySelector(".HotItem-metrics");'
    + '   out.push({ i: i, title: titleEl ? titleEl.innerText.trim() : "", href: a ? a.getAttribute("href") : "", metrics: metrics ? metrics.innerText.trim() : "" });'
    + ' }'
    + ' return out.filter(function(x){ return x.title; });'
    + '})()')
  const hit = hot.filter(function(x){ return kw.some(function(k){ return x.title.indexOf(k) >= 0; }); })
  cliLog('HOT_TOTAL: ' + hot.length)
  cliLog('KEYWORD_HITS: ' + JSON.stringify(hit, null, 2))
  cliLog('ALL_TITLES:\n' + hot.map(function(x){ return x.i + '. ' + x.title + ' [' + x.metrics + ']'; }).join('\n'))
  await completeTaskSpace(space, { keep: false })
})()
