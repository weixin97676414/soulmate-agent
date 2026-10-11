---
name: zhihu-account-nurture
description: 一套依赖 ego-browser 的知乎养号全流程，支持垂直领域收敛 + 用户可配置话题池 + 早/中/晚三班节奏 + 深度版回答 + 想法发布 + 影响力规范 + 点赞/收藏/关注/评论互动，并内置限流禁言期只读降级。触发：知乎养号、养知乎号、发知乎回答、知乎点赞互动、知乎浏览、三班养号、写深度版、发想法、提升创作分、点亮垂直度、按话题养号。可在任意装了 ego-browser 的机器上独立运行。
author: Soulmate Agent团队成员：岸
---

# 知乎养号（zhihu-account-nurture）

一套依赖 ego-browser 的知乎养号全流程，支持 **垂直领域收敛 + 用户可配置话题池 + 早/中/晚三班节奏 + 深度版回答 + 想法发布 + 影响力规范**：

- **垂直收敛**：账号只养 2 个领域，刻意埋关键词帮算法点亮创作垂直度。
- **选题**：全局 `topic_pool`，三班按「日序号 + 班次偏移」自动轮转取关键词（见 `references/topic-strategy.md`）。
- **每日每班 1 回答**：写 / 发布 / 折叠验证。
- **深度版**：每周 1 篇 800–1200 字深度回答，冲内容优质分。
- **想法**：每周若干条短动态，冲关注者亲密度。
- **影响力规范**：每篇回答必须带反直觉 hook + 可操作清单 + 引导互动，并在 24h 内回评论。
- **点赞互动**：前 10 个回答里随机选 3–5 个点赞（自然化），三班各自独立会话。
- **可选互动**：收藏 / 关注问题 / 评论，按 `config.json` 每班 `interactions` 用户自定义。

可在任意装了 ego-browser 的机器上独立运行，不依赖本工作区记忆。

## 何时使用

- 「知乎养号」「养知乎号」「今天养号」「发知乎回答」「知乎点赞 / 互动 / 浏览」「三班养号」「按话题养号」。
- 「写深度版 / 这篇写深一点」「发个想法 / 发动态」「提升创作分 / 创作分复盘」「点亮垂直度」。
- 要在新机器上跑一套**话题可配置、带三班节奏**的知乎增长 routine。

## 前置依赖（必须）

1. 已安装 ego-browser（ego lite 浏览器 + CLI），知乎账号已在 ego-browser 中登录（继承系统登录态，无需单独登录）。
2. ⚠️ **沙箱必须关闭**：ego-browser 的 Mach port IPC 会被沙箱拦截。运行所有 `ego-browser nodejs` 命令时，Bash 工具需加 `dangerouslyDisableSandbox: true`，并临时关闭宿主「沙箱安全」开关（用完开回），否则报 `Failed to connect to ego_cli bootstrap`。
3. **配置话题与班次**：复制 `config.example.json` 为 `config.json`，按你的账号/话题/互动修改（详见 `references/workflow.md` 的「配置 config.json」）。

## ⛔ 跑之前先确认账号状态

若账号处于限流 / 禁言（`config.account_status.silenced=true`），**只做只读浏览**：

- 跑 `scripts/browse_only.js`（零互动浏览）；**不要**跑发布 / 点赞 / 收藏 / 关注 / 评论 / 想法。
- `run_shift.js` 已内置硬护栏（`silenced=true` 时加载配置后立即退出），但不要依赖它兜底。
- 解除后先只开 morning `answer=true`，1 答/天跑两周再评估是否恢复三班。

账号状态只改 `config.json` 的 `account_status`。详见下方「账号受限期模式」。

## 风控红线（最高优先级，必读）

加载并严格遵守 `references/risk-control.md`。以下为硬约束：

- 🚫 1 分钟内连发 > 1 条创作内容（回答）；**单班任务 ≤ 1 回答**（三班 = 3 个独立任务）。
- 🚫 点赞 / 评论间隔 < 30 秒（知乎）；< 8 秒绝对禁止（全局）。
- 🚫 单任务操作密度 > 15 次 / 20 分钟。
- ⚠️ 任务前后各闲逛 3–5 分钟（热榜 / 推荐 / 关注）混入自然流量；发布前模拟阅读 5 分钟 + 发布前等 60 秒。
- ⚠️ 三班跨任务间隔 ≥ 2 小时（早 7:50 / 午 12:30 / 晚 20:00 天然满足）。

## 运行模式（推荐：三班编排）

用 `scripts/run_shift.js` 一把跑完一个班的「选题(可轮转) → 点赞 → 写回答 → 验证 → 可选收藏/关注/评论」，配置全在 `config.json`。

> ⚠️ **环境变量注意**（本机实测关键）：部分 ego-browser 构建的 `nodejs` 子命令**不继承 shell 环境变量**（`CONFIG`/`SHIFT` 会被丢弃，且进程 `cwd` 锁死为 `/`），因此 `CONFIG=... SHIFT=... ego-browser nodejs < script` 跑不起来。可靠写法见下方 heredoc。

```bash
ego-browser nodejs <<'EOF'
const fs = require('fs');
// ⚠️ 驻留进程 env 粘滞：ego-browser nodejs 的 process.env 跨调用残留，
// 上次设过的 SHIFT/QID/CONTENT_FILE 会一直活着，导致 loadParams 判 p.shift 为真、跳过参数文件，
// deep 等仅存在于参数文件的字段永远读不到。启动器必须显式 delete。
delete process.env.SHIFT;
delete process.env.QID;
delete process.env.CONTENT_FILE;
delete process.env.CONTENT;
process.env.CONFIG = '<skill_dir>/config.json';
process.env.SHIFT = 'morning';
const keep = setInterval(function () {}, 1000);
const src = fs.readFileSync('<skill_dir>/scripts/run_shift.js', 'utf8');
Promise.resolve(eval(src)).then(
  function () { clearInterval(keep); cliLog('=== SHIFT_DONE_OK ==='); },
  function (e) { clearInterval(keep); cliLog('=== SHIFT_ERROR: ' + (e && e.message) + ' ==='); }
);
EOF
```

> ⚠️ **上面这个启动器有三条硬约束，改动前先看**：
> ① **heredoc 里不能出现顶层 `await`**——`require` 与顶层 `await` 同时存在会触发 node 模块格式自动探测冲突，直接报 `ReferenceError: Cannot determine intended module format`。**所有机器都一样**。
> ② **`eval(src)` 返回的 Promise 必须有人接管**（上面的 `.then`）。脚本主体是 `(async () => {...})()`，若写成 `(function(){ eval(src); })()`，运行时会认为同步代码已跑完并结束会话，异步流程被丢弃——症状是「跑了三四分钟、零输出、什么都没做」。
> ③ `setInterval` 保活，防止进程在等待浏览器 I/O 时提前退出。
> 备选：确实需要顶层 await 时改用 `import fs from 'node:fs'`（ESM 模式），但 eval 进来的脚本内部若有 `require` 会挂。
> 📌 `cliLog` 输出走 **stderr**，且**延迟到进程结束才 flush**；后台运行时中途看不到日志是正常现象。

三班只需改 `process.env.SHIFT` 为 `noon` / `evening`；指定问题覆盖时额外 `process.env.QID = '...'` + `process.env.CONTENT_FILE = '/tmp/answer.txt'`。

> 📌 **关键选择器/注入修正（已在脚本内固化，勿回退）**：① 点赞选择器用 `button[aria-label*=赞同]`；② 写回答用 `ClipboardEvent` 粘贴注入（Draft.js 不认 `fillInput`）；③ heredoc 注入 env + `.then` 接管 Promise；④ 关注问题按钮按 `FollowButton` class 匹配（页面文案是「关注」/「已关注」，**从不存在**「关注问题」四个字）。

## 创作分提升套件

针对知乎创作分六维体系（创作活跃度 / 创作垂直度 / 内容优质分 / 创作影响力 / 关注者亲密度 / 社区成就分）的定向优化，全部由 `config.json` 驱动：

### 1. 垂直度收敛（`vertical_focus`）

账号只养 **2 个领域**，不再横跨多领域。

- 每篇回答**刻意自然融入 2–3 个本领域关键词**（见 `keyword_hints`），帮算法识别并点亮创作垂直度。
- `topic_pool` 按领域交替排列，保证轮转取到的 3 个关键词横跨两个领域。
- 🚫 不在垂直领域外的话题下写回答，否则垂直度永远点不亮。

### 2. 深度版回答（`deep_answer`，每周 1 篇）

内容优质分是**周更**维度，标准回答（250–800 字）拉不动。每周至少 1 篇深度版：

- **触发方式**（`config.deep_answer.mode`）：`auto`（默认，用户说「深度版/写深一点」即 invite 触发；否则每周随机挑 1 班）／`invite`／`random`。
- **字数**：800–1200 字。
- **硬性三项要求**：① 1 处可核查的史料原文 / 数据 / 案例；② 1 组对比结构（分层或表格化）；③ 1 段可操作的判断框架或结论。
- 深度版同样走 `run_shift.js` 发布流程。

### 3. 想法 / 动态（`moments`）

关注者亲密度是**月更**维度，提升性价比最高。频率 `config.moments.per_week`（默认 4 条/周），长度 50–150 字。内容方向见 `config.moments.topics`。

`scripts/post_moment.js`（已自动化）：

```bash
echo '{"contentFile":"/abs/moment.txt","dryRun":true}' > /tmp/zhihu_moment_params.json
ego-browser nodejs < scripts/post_moment.js
```

建议新机器首次跑先带 `dryRun: true`（只填不发布），确认无异常再写 `"dryRun": false` 实发。⚠️ **默认 fail-safe**：不设置 `dryRun` 时一律只填不发布。

### 4. 创作影响力要求（`influence`）

收藏、评论、分享的权重高于赞同——自动点赞只贡献赞同，必须靠内容质量拉动收藏与评论。每篇回答必须满足：

- **hook**：中段抛 1 个反直觉 / 反常识观点（拉评论）。⚠️ 禁止放开头第一句——「先说个反直觉判断」系开头是折叠高风险特征。
- **actionable**：至少 1 个可操作清单 / 判断框架 / 步骤（拉收藏）。
- **cta**：结尾**禁止机械问号收尾**（如「你觉得…？」）。用观点 / 判断 / 留白自然收束。
- **去 AI 味自检（发布前必做）**：① 结尾无问号互动收尾；② 编号列表尽量融进叙述；③ 破折号「——」≤1 处；④ 至少 1–2 个语气词（吧 / 嘛 / 说白了 / 讲真 / 还挺）；⑤ 节奏参差；⑥ 可留 1 处「的/地/得」类小瑕疵。
- **评论回复**：发布后 24h 内回复全部评论。**由 agent 执行（无脚本）**：下一次养号任务开始时先用 CLI 查上一班回答的评论并回复，或提醒用户手动回复。⚠️ **已知限制**：ego-browser 里评论弹窗点击「N 条评论」后始终卡在 `ModalLoading`，自动化回复不可行；替代：人工回复或真浏览器扩展环境。别在 ego-browser 反复重试评论弹窗。

### 5. 内容去指纹化写作规范

应对知乎「隐藏机制」批量折叠（按时间窗成批折叠历史回答）。写作时执行：

- 🚫 **开头禁用「先说个反直觉判断」系模板**（含「先泼冷水 / 先抛结论 / 说个不太好听的判断 / 反直觉的是」等变体）。反直觉 hook 一律放中段。
- **开头句式池（10 种，轮换）**：场景切入 / 时间锚点 / 材料先行 / 人物视角 / 疑问承接 / 类比引入 / 反面案例 / 朴素直陈 / 引用他人 / 反差细节。同一周内不重复；同一句式连续使用不超过 2 次。每次生成正文前先回顾近 5 篇用过的句式。
- **分层拆解降频**：「第一层 / 第二层 / 三步法 / 一、二、」类显性分层结构每周 ≤1 篇，其余融进叙述。
- **术语词降频**：「心理机制 / 视角拆解 / 从 X 角度看」类分析腔每周 ≤2 篇。
- **真实经验优先（强制）**：每篇至少 1 处第一人称真实经历 / 具体场景细节；禁止「资料整理型通稿」。
- **掉书袋限额**：引用（书名 / 人名 / 原文）每篇 ≤1 处、每周 ≤2 篇。

> **配置分工**：`vertical_focus` / `influence` 是**给 agent 的写作规范**（不被脚本读取）；`deep_answer.min_words/max_words` 在参数文件写 `"deep": true` 时被 `run_shift.js` 用于字数护栏；各班 `shifts.*.interactions` 被 `run_shift.js` 读取执行。
> **字数护栏**：`run_shift.js` 发布前校验 contentFile 字符数——标准区间 `answer_style.min/max_words`（250–800）、深度版（参数 `"deep": true`）区间 `deep_answer.min/max_words`（800–1200）。**超区间输出 `ANSWER_SKIPPED: WORD_COUNT_EXCEEDED` 并跳过发布**（点赞/互动照常收尾）。

## 可用脚本

- `scripts/run_shift.js`：一个班次全流程编排（核心）。
- `scripts/like_top5.js`：指定问题前 10 个回答里随机选 3–5 个点赞（env: `QID`，可选 `POOL`/`LIKE_MIN`/`LIKE_MAX`）。
- `scripts/write_answer.js`：写回答 + 发布（env: `QID` + `CONTENT_FILE`/`CONTENT`）。
- `scripts/verify_via_cli.js`：折叠状态权威验证（参数文件 `/tmp/zhihu_verify_params.json`：`aid`/`type`，或 env `AID`/`TYPE`）。
- `scripts/pick_question.js`：扫热榜按关键词过滤输出候选 qid（env: `KW`、`LIMIT`）。⚠️ 本机 env 不透传时需把 `kwRaw` 写成硬编码。
- `scripts/post_moment.js`：发想法（参数文件 `/tmp/zhihu_moment_params.json`，支持 `dryRun`）。
- `scripts/edit_answer.js`：修改已发布回答（参数文件 `/tmp/zhihu_edit_params.json`）。⚠️ 「提交修改」点击可能不生效，脚本会安全停止并提示人工确认。
- `scripts/fold_audit.js`：折叠巡检。滚动抓取创作者中心全部内容的「被折叠」标签，与基线 `references/fold-baseline.json` 比对输出 `NEW_FOLDED` / `RECOVERED`（参数文件 `/tmp/zhihu_fold_params.json`，`{"update": true}` 写回基线）。**每班开跑先跑一次**。基线文件是**本机状态**，不随包分发；新机器首次跑输出 `NO_BASELINE`，之后带 `{"update": true}` 跑一次即建立基线。
- `scripts/browse_only.js`：禁言期只读浏览（热榜 → 按垂直领域词挑问题 → 逐页滚动停留 → 首页信息流，**零点击互动**，输出 `BROWSE_DONE ... interactions=0` 可验证）。参数文件 `/tmp/zhihu_browse_params.json`（`{"minutes": 6, "pages": 4, "keywords": [...]}`）。

DOM 选择器、按钮点击要点见 `references/selectors.md`。

## 账号受限期模式（`account_status.silenced`）

账号被限流 / 禁言时，养号必须降级为**只读浏览**——禁言期的任何写动作不仅无效，还可能被判定为异常行为而加重处罚。

- **开关**：`config.json` 的 `account_status`（`silenced` / `silenced_from` / `silenced_until` / `reason`）。`silenced: true` 时：
  - `run_shift.js` 在配置加载后**立即退出**（`SILENCED_MODE` / `SHIFT_SKIPPED` 日志），不打开编辑器、不点赞、不互动。
  - 同时把三班 `answer` 置 `false`、`interactions.like.min/max` 置 `0`（双击保险）。
  - 日常动作改用 `scripts/browse_only.js`。
- **受限期该做什么**：① 每天 1–2 次只读浏览；② 复盘存量内容与写作规范；③ **不要**批量删除/修改旧回答；④ **不要**反复申诉。
- **解除后恢复节奏**：先把 `silenced` 改回 `false`，**只开 morning `answer=true`** 跑 1–2 周，观察新篇是否被贴「内容疑似 AI 生成」标签或被折叠，再决定是否恢复三班。
- **写作侧同步收紧**：恢复后每篇至少 1 处第一人称真实经历或具体场景细节。

## 关键陷阱（务必先看）

- 🚨 **折叠 / AI 标签是账号级信号，不是单篇问题**：完整前兆链条＝公开「内容疑似 AI 生成」标签 → 按时间窗批次折叠历史回答 → 账号限流 / 禁言。一旦出现 AI 标签或成批折叠，立刻当全账号事件处理——停写整改、复盘写作规范。
- 🚨 **/tmp 影子配置会绕过禁言护栏**：`run_shift.js` 的 config 搜索顺序里 `/tmp/zhihu_config.json` **优先于正式 config**——遗留的临时副本会把 `account_status` 一起吞掉。防护：脚本在选中 `/tmp/` 路径时输出 `WARN: 正在使用 /tmp 影子配置`；用完临时副本立即删除。
- ⚠️ **发布按钮零宽字符导致静默不发布**：原 `innerText.trim() === "发布回答"` 不去 `\u200b`，按钮带零宽字符时静默 `publish-clicked: false`。已改为 `[\u200b\s]+` 清洗 + 候选 `["发布回答","提交回答"]` + 回退「发布」+ 跳过 disabled，未发布时输出 `SHIFT_PARTIAL_FAIL: publish`。
- ⚠️ **单问题重复操作密度**：同一问题页 15 分钟内连续开编辑器/补发 3 次后，点「写回答」不再挂载编辑器，属密度风控信号。规则：同页发布失败最多重试 1 次；再失败即停，等 1–2 小时或换班次。
- ⚠️ **知乎「隐藏机制」批量折叠**：平台按时间窗分批折叠历史回答。CLI Summary 验证对新机制**失明**（被折回答 Summary 仍非空），折叠的唯一权威信号是创作者中心列表的「被折叠」标签 → **每班开跑先跑 `fold_audit.js` 与基线比对**。新回答未被折 ≠ 安全。
- ⚠️ **ego-browser nodejs 驻留进程 env 粘滞**：`process.env` 跨调用残留，deep 字段会被静默丢弃（症状：深度版正文被按标准区间拦下报 `WORD_COUNT_EXCEEDED (standard)`，且日志缺 `PARAMS_FROM_FILE`）。修复：启动器里 `delete process.env.SHIFT/QID/CONTENT_FILE/CONTENT` 再设新值。
- 🚫 **生成回答禁止输出 Markdown**：编辑器不渲染，`**` / `- ` 按字面残留。纯文本排版用「1.」「· 」、破折号强调。
- 🚫 **永远不要对中文用 `String.raw`**：`fillInput` 直接传 UTF-8 字符串。
- ✅ **点赞按钮**：用 `button[aria-label*="赞同"]`（含尾空格必须 trim），已赞判定用 `classList.contains('is-active')`。
- ⚠️ **点赞按钮 innerText 含前导零宽字符 `\u200b`**：不能用 `===` / `startsWith('赞同')` 精确匹配；一律用 aria-label + trim。
- ✅ 「写回答」按钮文本前有零宽字符，用 `.includes('写回答')`；「发布回答」按钮必须清洗零宽字符后再匹配。
- 🚫 **发布卡「发布中…」disabled 即停**：不要重复点 / 重试。等待账号风控释放或手动在浏览器发布。
- ⚠️ **验证发布/修改成功一律用官方 CLI**：`zhihu-cli me contents --type answer --limit 3`（摘要完整=未折叠；想法用 `--type pin`）。`serverFetch('/api/v4/answers/{aid}')` 自 8/26 起持续 403 已失效；v1.3.3 起已移除 API 验证死路，改用 `scripts/verify_via_cli.js`。

## 验证发布成功

1. 发布后 URL 跳转 `/question/{qid}/answer/{aid}`。
2. **权威校验**：

```bash
echo '{"aid":"<aid>","type":"answer"}' > /tmp/zhihu_verify_params.json && ego-browser nodejs < scripts/verify_via_cli.js
```

输出 `VERIFY_RESULT: OK_NOT_COLLAPSED` 即成功（折叠则 `COLLAPSED`；`NOT_FOUND_YET` 是索引滞后，等 1–2 分钟重跑）。等价手工命令：`zhihu-cli me contents --type answer --limit 3`。

## 部署注意

- ego-browser 可能不在 shell PATH：用绝对路径（如 `~/.local/bin/ego-browser`）。
- zhihu-cli 通常不在 PATH：macOS 常见真实路径 `~/Library/Application Support/zhihu-cli/current/zhihu-cli`（`verify_via_cli.js` 已内置此回退）。

## 文件产出建议

- 日报：`output/zhihu/YYYY-MM-DD-{shift}.md`（shift: morning / noon / evening）。

## 参考资料

- `references/risk-control.md` — 风控红线与全局原则（必读）
- `references/selectors.md` — DOM 选择器 + ego-browser API 速查
- `references/topic-strategy.md` — 全局话题池、心智定位、三班轮转
- `references/workflow.md` — config.json 配置、脚本调用方式、env 变量、示例命令
- `config.example.json` — 配置模板（复制为 `config.json` 后修改；个人 `config.json` 不上传）
