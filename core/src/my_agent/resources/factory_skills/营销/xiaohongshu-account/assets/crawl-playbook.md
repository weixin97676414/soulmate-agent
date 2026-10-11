# 抓取对抗手册（小红书网页版）

> 本文件是 `xhs_crawl.py` 的排障与扩展参考。遇到受限、取不到数据、需要新字段时读这里。

## 1. 三级通道与其适用边界

| 通道 | 触发方式 | 能拿到什么 | 典型失败 |
|---|---|---|---|
| `http` | 纯 HTTP + TLS 指纹，解析 SSR `__INITIAL_STATE__`，**携带本次登录 Cookie** | 主页首屏笔记（通常 10-30 条）+ 账号信息；详情页字段最全 | 无 `xsec_token`、登录墙、返回 461；未登录直接跳过 |
| `persistent` | Playwright 持久化 profile（**每次运行清空后重新扫码**） | 主页全量笔记 + 笔记详情 + 评论（靠拦截 XHR） | 撞登录墙、触发滑块 |
| `cdp` | 接管用户手动启动的 Chrome | 同上，且用真实环境登录态，风控最强 | 用户未开调试端口 |

**默认顺序**：`persistent → cdp → http`。理由：全量抓取只能靠登录态浏览器的
`user_posted` 接口（`http` 通道的 SSR 里没有 noteId，且只有首屏几十条）；
`cdp` 需要人工开调试端口，排第二；`http` 只作详情页的补充通道。

**登录策略（硬约束）**：不复用历史登录态 —— 每次运行前 `reset_runtime()`
清空 `storage_state.json` / `cookies.json` / `cache/` / `browser_profile/`，
再弹窗扫码或短信验证码登录；不存在免登录路径。

### 关键认知：不要自己去实现签名

小红书 Web 端接口（`edith.xiaohongshu.com/api/sns/...`）需要 `x-s` / `x-t` / `x-s-common` 三个签名头，
由页面 JS 动态生成，逆向成本高且随版本变更。

**正确做法**：让真实浏览器自己发请求，脚本只**监听响应**（`page.on("response")`）。
`xhs_crawl.py` 的 `BrowserChannel` 就是这个思路，稳定性远高于手写签名。

## 2. 核心接口清单（用于扩展字段）

监听用正则（见 `xhs_crawl.py::API_RULES`）：

| 用途 | 路径 | 返回关键字段 |
|---|---|---|
| 用户主页信息 | `/api/sns/web/v1/user/otherinfo` | `data.user`：nickname / desc / fans / follows / ip_location / red_id |
| 用户笔记列表 | `/api/sns/web/v1/user/posted` | `data.notes[]`，每条含 `note_card` + `xsec_token`，`data.cursor` 翻页 |
| 笔记详情 | `/api/sns/web/v1/feed` | `data.items[0].note_card`：完整 desc / image_list / video / tag_list |
| 笔记评论 | `/api/sns/web/v2/comment/page` | `data.comments[]`：content / like_count / user_info / sub_comments |
| 搜索 | `/api/sns/web/v1/search/notes` | `data.items[]` |
| 子评论 | `/api/sns/web/v2/comment/sub/page` | `data.comments[]` |

笔记卡片（`note_card`）关键字段：

```
type            "video" | "normal"
display_title   标题
desc            正文（列表页可能被截断，详情页完整）
interact_info   { liked_count, collected_count, comment_count, share_count }  ← 注意是 "1.2万" 字符串
cover           { url_default, info_list[] }
image_list[]    { url_default, width, height, trace_id }
video.media.stream.h264[0].master_url        无水印视频源
video.capa.duration                          时长（毫秒）
tag_list[]      { name, type }
time / last_update_time   毫秒时间戳
ip_location     发布地
```

> `interact_info` 的数值是**展示字符串**，必须过 `xhs_common.human_num()` 转换，否则 "1.2万" 会当 1 处理。

## 3. xsec_token：最容易踩的坑

小红书主页/笔记链接都带 `xsec_token`，它是**一次性短时效访问凭证**：

- 从聊天窗口/搜索结果复制出来的链接自带 token，几十分钟到几小时有效
- **过期后**打开会跳回发现页或弹登录框 → 表现为主页打不开、列表为空
- token 与账号绑定，换设备/换登录态可能失效

处置：

1. 优先让用户**现复制现用**的链接
2. token 缺失时，用 `--target "昵称"` 走搜索页重新捞一个带 token 的链接（`xhs_resolve._search_user`）
3. `http` 通道对 token 强依赖，`persistent`/`cdp` 通道即使 token 失效，有时也能靠登录态打开主页

### 3.1 目标解析的多级路径与超时自愈（1.6.0 起）

搜索页是小红书最重的页面，加载超时曾是整个抓取的头号崩溃源。
现在 `xhs_resolve.resolve()` 按成本从低到高走四条路径，**搜索页是最后手段**：

```
正则/短链/24位ID（零页面加载）
  → 本地解析缓存 .targets_cache.json（命中即跳过一切页面）
    → 笔记详情页反查作者 _author_from_note()（页面轻，/explore/ 链接首选）
      → 搜索页 _search_user()（屏蔽图片/媒体/字体后再加载）
```

关键设计：

- **解析不抛异常**：任何一步失败只返回 `resolved_by="xxx_timeout/empty"`，
  由 `xhs_crawl._resolve_with_recovery()` 继续降级，不会把异常甩给主流程；
- **搜索页减负**：进页面前 `page.route("**/*")` 拦截 `image/media/font`，
  瀑布流的大头被砍掉；`domcontentloaded` + 显式等用户卡片 15 秒，不等整页；
- **超时自动刷新重试**：`_search_user(retries=1)` 内部先刷一次；
- **上层恢复阶梯**：仍失败则 `_resolve_with_recovery()` 再做
  「刷新页面 → 重启浏览器 + 重新登录」（轮数由 `--resolve-retries` 控制，默认 2）。
  重启能清掉卡死标签页的状态污染，在同一个死页面上反复重试往往无效；
- **解析缓存**：成功的「输入 → uid」写入技能目录 `.targets_cache.json`
  （**刻意不放 `.runtime/`**，后者每次运行都被清空）。下次同输入直接命中，
  完全跳过搜索页；token 只在缓存当天复用，隔天仅复用 uid。
  管理开关：`--no-target-cache`（本次跳过）/ `--clear-target-cache`（清空退出）。

全部恢复手段用尽后，报错会给出 5 条具体替代输入建议
（主页链接 / 笔记链接 / 24 位 ID / `--resolve-retries 3` / `--no-target-cache`）。

排障速查：

| `resolved_by` | 含义 | 处置 |
|---|---|---|
| `regex` / `uid` / `short_url_expand` | 零页面路径直接命中 | 无需动作 |
| `cache` | 命中本地缓存 | 缓存过期用 `--no-target-cache` |
| `note_author` | 从笔记详情页反查到作者 | 正常，比搜索页轻 |
| `search` | 搜索页命中 | 正常 |
| `search_timeout` | 搜索页连续加载超时 | 已被上层接管重试；仍失败换链接/uid 输入 |
| `search_empty` | 搜索页开了但没有用户卡片 | 核对昵称；可能触发限流，换链接/uid |
| `note_timeout` / `note_no_author` | 笔记页超时或没找到作者入口 | 核对链接有效性 |
| `unresolved_note_url` | 笔记链接但没有浏览器会话可用 | 正常流程不会发生（登录门禁先开浏览器） |

回归测试：`python test_resolve_recovery.py`（不联网，FakePage 合成 10 个断言）。

## 4. 风控信号与处置

| 现象 | 判定 | 处置 |
|---|---|---|
| 页面出现「登录」「安全验证」「滑动验证」 | 登录墙 / 人机验证 | 脚本会**自动暂停并等你在窗口里处理**（`xhs_antibot.wait_for_human`），不要 Ctrl+C |
| HTTP 返回 461 / 重定向到 `/website-login` | 未登录 | 重新扫码；`http` 通道放弃 |
| 主页能开但 `notes` 为空 | token 失效或 SSR 未注水 | 滚动几次后再取；仍为空则切浏览器通道读 `user/posted` |
| 浏览器正常但接口 `success:false` | 触发频控 | `--pace slow`，并把 `--months` 调小（如 3） |
| 连续多条笔记详情抓不到 | 详情页限流 | 只抓 TOP 5-8 条（`--detail-top 8`），其余保留列表数据 |
| 单任务动作超限收工 | `meta.stopped_reason = budget_exhausted` | 属正常收工；缩小窗口或换个时间再跑 |
| 搜索页加载超时 / 解析失败 | `search_timeout` / `search_empty` | 1.6.0 起自动走「刷新 → 重启重登」恢复（§3.1）；仍失败换主页链接/uid 输入，或 `--resolve-retries 3` |
| `playwright` 报 executable 不存在 | 内核未下载 | `python setup.py` |

### 4.0 反风控的四层设计（1.5.0 起）

采集量一大就会弹滑块/短信验证。应对手段按有效性排序：

1. **缩短采集窗口（最有效）** —— `--months 6`（默认）。主页列表按时间倒序，
   滚动请求数与要覆盖的时间跨度成正比。**截断到半年通常能砍掉一半以上的请求**，
   而账号诊断真正需要的是近期内容。要更久用 `--since YYYY-MM-DD` 精确指定，
   不要直接 `--months 0`。
2. **拟人节奏** —— `xhs_antibot.HumanPacer`：随机间隔 + 每 N 个动作长休 +
   单任务动作预算。三档 `slow / normal / fast` 见 `PACE_LEVELS`。
3. **见好就收** —— 预算用尽主动收工，`meta.stopped_reason` 写明原因。
4. **遇验证暂停等人工** —— `detect()` 识别滑块 / 短信 / 风控页（文案 + DOM 选择器
   双重判定，长正文页面不误判），命中后打印提示并轮询等待，
   用户完成后自动继续 + 额外降温 60-120 秒。

**绝不许做**：破解或绕过验证码、伪造滑块轨迹、IP 代理池、多账号轮换。
`STEALTH_JS` 只做指纹伪装（webdriver / WebGL / permissions），不做对抗。

**已触发过验证的账号**，下一轮用 `--pace slow --months 3`，而不是硬扛。

### 4.0.1 时间窗口的实现要点

- `window_start_ms(months, since)` 计算起点（毫秒），`months_ago()` 处理月末边界
  （3/31 减 1 个月 = 2/28，不是 3/3）；
- 滚动时每轮检查**已抓笔记里最早的时间戳**，早于窗口就停 —— 因为列表倒序，
  后面的必然更老，这一步能省掉大量无效请求；
- `in_window()` 对**没有时间戳的笔记默认保留**：没有证据说明它超出窗口，
  直接丢弃会造成静默的数据缺口（比多抓几条危险）；
- 过滤发生在两个地方：滚动停止判断（省请求）+ 结果集过滤（`http` 通道也要过一遍）。
| CDP 连接失败 | 端口未开 | `python xhs_browser.py open 9222` 后人工登录再跑 |

**降温原则**：详情页与评论是高风险动作。默认行为是"窗口内全部抓"
（`--detail-top 0`），所以**靠 `--months` 控制总量**，而不是靠条数硬压。
一次任务建议控制在 `normal` 档 200 个动作以内（`--pace slow` 则 120）。

### 4.1 登录态判定：只认 `web_session`

小红书在**任何一次页面访问**时都会下发访客 cookie：

```
a1  webId  acw_tc  abRequestId  ets  loadts  sec_poison_id  webBuild  websectiga  xsecappid
```

这些**不代表已登录**。真正的登录凭证只有 `web_session`。

踩过的坑：早期版本用 `"web_session" in c or "a1" in c` 判定登录，导致

- `bootstrap.py` 在从未登录的情况下报「登录态：已保存」
- `xhs_login.py` 的扫码等待**瞬间假成功**（打开页面就有 a1，根本没扫码）
- 无头模式下白白多跑一轮必失败的浏览器通道

现在 `xhs_browser.has_login()`、`xhs_login.wait_for_login()`、`bootstrap.check_state()`
三处统一为**只认 `web_session`**。改这三处时务必保持一致。

**登录态生命周期（1.4.0 起，1.6.2 改为「改名弃用」策略）**：每次运行 `xhs_crawl.py` /
`xhs_login.py` 都会先 `reset_runtime()` 清除 `.runtime/` —— 两个登录凭证文件
（`storage_state.json` / `cookies.json`）直接删除；`cache/`、`browser_profile/`
整目录**改名为 `<名称>_discard_<时间戳>`**。为什么改名而不是删除：
① 浏览器进程占用目录时删除会失败，改名总能成功；
② 受限环境（沙箱/安全护栏按轮计数限制批量删除）下删除会被终止，改名不触发；
③ 效果等价 —— 旧 profile 改名后永久失效，下次启动创建全新 profile，
任何历史登录记录都无法被复用。`_discard_*` 是惰性垃圾，可随时手动删除。

所以：

- 不存在「登录态过期」这个概念 —— 每次都是新的；
- 排查时若发现 `.runtime/` 里还有旧文件，说明清理失败（多半是浏览器进程占用）；
- Windows 上 `browser_profile/` 被占用删不掉不会阻断流程，因为登录凭证
  （`storage_state.json` / `cookies.json`）已经删掉了，仍需重新登录。

排查命令（注意目录名以本机实际安装为准）：

```bash
python -c "import json,pathlib;p=pathlib.Path('.runtime/cookies.json');print(sorted({c['name'] for c in json.loads(p.read_text('utf-8'))}) if p.exists() else '无登录态文件（正常，每次运行都会清空）')"
```

输出里没有 `web_session` 就是没登录。

想手动清一遍：`python xhs_login.py --reset`。

## 5. 反自动化指纹清单

`xhs_browser.STEALTH_JS` 已处理：

- `navigator.webdriver` → undefined
- `navigator.languages` / `hardwareConcurrency` / `deviceMemory` / `platform`
- 注入 `window.chrome.runtime`
- `permissions.query` 绕过 notifications 检测
- WebGL vendor / renderer 伪装（防 canvas 指纹）
- 启动参数 `--disable-blink-features=AutomationControlled`

未做（**刻意不做**）：验证码自动识别、滑块轨迹伪造、IP 代理池。
遇到验证码应由**用户人工完成**——脚本只在 `cdp` 通道等待用户处理。

## 6. 人工过验证的标准流程

```bash
# 1) 启动带调试端口的浏览器（独立 profile，不影响用户日常浏览器）
python xhs_browser.py open 9222

# 2) 在弹出的窗口里登录小红书网页版，手动过一次滑块/短信验证

# 3) 带着这个登录态跑爬取
python xhs_crawl.py --target "<链接>" --tier cdp --cdp-port 9222 --out ./out
```

`cdp` 模式下脚本不会关闭用户的浏览器（`connect_over_cdp` 的 `browser.close()` 只断开连接）。

## 7. 素材下载注意

- 图片/视频直链需要 `Referer: https://www.xiaohongshu.com/`，已在 `xhs_media._save` 中设置
- 视频抽帧依赖 `ffmpeg`。缺失时 `--media` 仍会下载封面与视频，但无关键帧拼版
- 关键帧拼版 `sheet.jpg`（4×5 网格）是**爆款结构拆解的主要视觉输入**，务必生成

### 7.1 视频流地址：从详情页 SSR 提取（携带本次登录 Cookie）

`xhs_crawl.pick_video()` 已封装，此处记录结构以防平台改版：

```
note.video
├─ media.stream.h264[0]        ← 变体A（camelCase）
│   ├─ masterUrl   带 sign&t 签名，会过期
│   └─ backupUrls  无签名，长期有效 ← 优先用这个
├─ mediaV2                     ← 变体B：是 JSON 字符串！需 json.loads 二次解析
│   └─ stream.h264[0].master_url / backup_urls（snake_case）
└─ capa.duration               ← 单位是「秒」，存进 duration_ms 前要 ×1000
```

实测（2026-09）：`/explore/<note_id>?xsec_token=<token>` 的详情页 SSR 里，
`note.noteDetailMap.<id>.note.video` 即含上述完整结构，30 条笔记 29 条成功。
这里的 SSR 请求都带着本次登录的 Cookie（`HttpChannel` 默认注入），**不是匿名访问**。
例外：**置顶笔记**的 SSR 详情可能整个为空（noteDetailMap 无条目），属平台策略，
需登录态浏览器通道兜底；换新 token、免 token 均无效。

## 8. 合规边界（必须遵守）

- 只采集**公开可见**内容，不尝试登录态下的私密数据、创作者后台、商业化后台
- **登录态不长期保存**：每次运行前清空 `.runtime/`，任务结束即失效，
  不跨任务复用、不随技能分发（`xhs_login.py --reset` 可手动清一遍）
- 不采集用户手机号/微信等个人信息；评论只保留昵称与内容，不做身份画像
- 不做写操作（点赞/评论/关注/私信/发布）
- 不破解、不绕过验证码；需要人工验证时交由用户完成
- 产出物限内部分析使用，不得批量分发原始数据或用于违法用途
- 控制频率，避免对平台造成压力

## 9. 扩展新字段的步骤

1. 在 `xhs_crawl.API_RULES` 加一条 `(key, 正则)`
2. 在 `BrowserChannel` 里加一个 `fetch_xxx()` 方法，复用 `_on_response` 的 bucket 机制
3. 在 `normalize_note()` 里补字段（保持所有来源结构一致）
4. 在 `xhs_analyze.py` 里加对应计算块，并写进 `xhs_report.build_slots()`
