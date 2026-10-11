---
name: xiaohongshu-account
description: "小红书账号深度拆解：扫码采集近半年全量笔记/评论/素材，六维拆解定位、内容、算法、对标与爆款，输出可溯源 HTML 报告与 SOP。触发场景：拆解某小红书账号、账号为什么能火、竞品对标、爆款分镜。"
author: Soulmate Agent团队成员：岸
---

# 小红书账号深度拆解

## 适用场景

- 给定小红书主页链接、笔记链接、`xhslink` 短链、24 位用户 ID 或昵称，要求分析/拆解/对标。
- 问「这个账号为什么能火」「怎么复制」「值不值得投」「变现模式健康吗」。
- 账号定位诊断、选题库搭建、脚本结构拆解、爆款分镜还原、运营 SOP 输出、竞品横向对比。
- 触发词：拆解/分析某个小红书账号、为什么这个账号能火、怎么复制这个账号、小红书竞品对标、小红书账号定位诊断。

**不使用**：只写文案/起标题（用 `references/xiaohongshu-ops.md` 或文案类功能）；只搜关键词批量拿互动（不做深度拆解）；平台是抖音/B站/视频号（用 `references/tiktok-marketing.md`）；索要创作者后台/私信/粉丝名单等非公开数据（拒绝）。

## 步骤

```
⓪ 扫码登录（每次全新）→ ① 环境自检 → ② 解析目标 → ③ 窗口内全量爬取（反风控）
→ ④ 素材处理 → ⑤ 指标计算（含图文/视频占比）→ ⑥ 深度分析（六维）→ ⑦ 渲染交付
```

**⓪ 登录门禁（每次强制全新登录，无免登录通道）**
```bash
python xhs_login.py                 # 默认 App 扫码（会先清空旧登录态）
python xhs_login.py --mode web      # 手机号 + 短信验证码
python xhs_login.py --reset         # 只清空登录态与缓存
python xhs_login.py --check         # 只检查是否存在登录态文件
```
每次运行先清空 `.runtime/`（`storage_state.json`、`cookies.json`、`cache/`、`browser_profile/`），再弹有头浏览器扫码。扫码等待默认 600 秒。**不要绕过门禁、不要复用上次登录态。**

**②③④ 抓取（默认近半年窗口内全量）**
```bash
python xhs_crawl.py --target "<链接|短链|24位ID|昵称>" --out "output/<账号名>" --media
```
关键参数：`--months 6`（默认只采近 6 个月，`0`=不限）；`--since YYYY-MM-DD`（优先于 `--months`）；`--limit 0`（不限条数）；`--detail-top 0`（全部抓详情+评论，`-1`=跳过）；`--comments 100`；`--media`（下封面+视频+抽帧）；`--media-top 8`；`--pace slow|normal|fast`（默认 normal）；`--challenge-timeout 600`；`--login qr|web`；`--login-timeout 600`；`--resolve-retries 2`；`--tier auto|persistent|cdp|http`。

**⑤ 指标计算**
```bash
python xhs_analyze.py --dataset "<out>/dataset.json"
```
产出 `analysis.json`（全部结论的数据源）+ `notes_metrics.csv`。

**⑥ 深度分析（核心，必须由 Agent 完成，先读素材再下结论）**
1. Read `<out>/analysis.json`；2. 看 `meta.window` / `meta.stopped_reason` 确认窗口与完整性；3. Read `media/media_index.json`；4. 逐张 Read `media/<id>/sheet.jpg` 与 `cover.jpg`（爆款拆解唯一可信依据）；5. Read `raw/notes/<id>.json` 取 TOP 正文；6. 按需读参考。
先复制骨架：`cp assets/narrative_template.md <out>/narrative.md`，按六维填写：
1. 商业定位诊断（变现模式/健康度/天花板）2. 内容结构拆解（选题库/标题公式/正文骨架/视觉模板）3. 算法逻辑推演（流量层级/标签精准度/赛道拥挤度）4. 竞品对标（≥2-3 个同赛道账号）5. 爆款结构拆解（逐镜还原前 3 秒钩子/分镜表/运镜节奏/封面规律）6. SOP 化输出（选题库/生产流程/复盘表/30 天排期，带频次与验收指标）。

**⑦ 渲染交付**
```bash
python xhs_report.py --analysis "<out>/analysis.json" --dataset "<out>/dataset.json" \
    --narrative "<out>/narrative.md" --format both
```
产出 `report.md` + `report.html`（自包含）。PDF：`python xhs_pdf.py --dir <out>`。

## 输入输出

- 输入：账号链接/短链/24 位 ID/昵称；目标重点（商业价值/内容结构/爆款/对标）；交付格式。
- 输出：`report.html`（优先）、`report.md`、`analysis.json`、`notes_metrics.csv`、按需 `report.pdf`/Word/PPT。

## 注意事项

- **图片/视频占比硬性必报**：引用 `analysis.json → formats.mix_label`，注明采集窗口 `meta.window`，样本不完整（`stopped_reason` 非 `window_edge`/`no_more_notes`）必须写"样本 N 条（不完整）"。
- 每条结论可追溯到 `analysis.json` 具体字段，禁止凭印象；至少引用 3 条具体笔记（标题+数据）；禁止"持续优化"这类空话。
- **反风控**：缩短窗口（默认近半年）为第一手段；拟人节奏 HumanPacer；见好就收；遇滑块/短信验证**暂停等人工**，不破解验证码。**绝不许**破解验证码、伪造滑块轨迹、上代理池、多账号轮换。已触发验证下轮建议 `--pace slow --months 3`。
- 数据自检（v1.6.2 起）：抓完看 `dataset.meta.quality`（`详情 N/M · 标签 N/M · 评论 X 条 · 媒体地址 Z 篇`）。
- 通道：`persistent`（主力）→ `cdp`（接管本机 Chrome 调试端口）→ `http`（curl_cffi 兜底）。
- 数据损坏用 `python xhs_rebuild.py --out "<out>"`（离线重建，取 `raw/api` 全部响应并集），不要手搓。
- **合规**：只采公开内容；登录态不长期保存；不采手机号/微信/真实身份；不做任何写操作（点赞/评论/关注/私信/发布）；产出限内部分析。

## 可复用示例

```bash
# 深度拆解一个账号（近半年全量 + 素材）
python xhs_crawl.py --target "https://www.xiaohongshu.com/user/profile/xxx?xsec_token=yyy" \
    --out "output/某某" --media
python xhs_analyze.py --dataset "output/某某/dataset.json"
# 写 narrative.md 后渲染
python xhs_report.py --analysis "output/某某/analysis.json" \
    --dataset "output/某某/dataset.json" \
    --narrative "output/某某/narrative.md" --format both
```

## 配套文件

- `scripts/setup.py`、`scripts/bootstrap.py`、`scripts/xhs_env.py`、`scripts/xhs_common.py`、`scripts/xhs_browser.py`、`scripts/xhs_login.py`、`scripts/xhs_resolve.py`、`scripts/xhs_antibot.py`、`scripts/xhs_crawl.py`、`scripts/xhs_media.py`、`scripts/xhs_analyze.py`、`scripts/xhs_report.py`、`scripts/xhs_pdf.py`、`scripts/xhs_rebuild.py`、`scripts/test_resolve_recovery.py`。
- `assets/analysis-framework.md`（六维分析框架）、`assets/viral-blueprint.md`（爆款拆解）、`assets/sop-templates.md`（SOP 模板）、`assets/crawl-playbook.md`（抓取对抗）、`assets/narrative_template.md`、`assets/report_template.html`。
