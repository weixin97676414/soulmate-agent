---
name: douyin-scraper
description: 用 Selenium 抓取抖音热门视频 TOP10、电商带货榜 TOP10、百度热搜 TOP10，输出四段式文本报告与 CSV。触发场景：抖音爬虫、Selenium 抓取、蝉妈妈数据、热门视频榜、电商带货榜、动态页面/JS 渲染爬虫。
author: Soulmate Agent团队成员：岸
---

# 功能：抖音数据爬虫（Selenium）

主脚本位于 `scripts/douyin-scraper/douyin_scraper.py`（约 1100 行，Windows 环境）。

## 适用场景
抓取抖音热门视频 TOP10、电商带货榜 TOP10、热搜榜 TOP10，输出四段式文本报告 + CSV。触发词：抖音爬虫、Selenium 抓取、蝉妈妈数据、热门视频榜、电商带货榜、douyin scraper、动态页面抓取、JS 渲染爬虫。

## 前置条件
- Python 3.10+（推荐 3.13）；
- Chrome 浏览器已安装（`webdriver-manager` 自动匹配驱动）；
- 项目目录下 `.venv/`。

## 步骤
1. **安装依赖**：
   ```bash
   python -m venv .venv
   .venv/Scripts/pip install selenium requests beautifulsoup4 pandas lxml webdriver-manager
   ```
2. **运行**（脚本内配置了输出目录与 URL）：
   ```bash
   .venv/Scripts/python.exe scripts/douyin-scraper/douyin_scraper.py
   ```
3. **查看产出**（`reports/` 下带时间戳）：
   - `douyin_report_YYYYMMDD_HHMMSS.txt`（四段式报告，>2000 bytes）；
   - `douyin_hot_videos_*.csv`（热门视频，UTF-8-BOM）；
   - `douyin_ecommerce_*.csv`（电商带货）。
4. **主流程**：初始化 headless Chrome（含 stealth JS）→ 抓热门视频（蝉妈妈 `hotAweme`）→ 抓电商带货（蝉妈妈 `promotionAweme/`）→ 抓热搜（百度实时热搜）→ 写两个 CSV → 生成四段式报告 → 预览并关闭。
5. **报告结构**：热门视频 TOP10 → 热搜 TOP10 → 电商带货 TOP10 → 趋势洞察（赛道分布/热搜特征/超级爆款>30万赞/电商热品/带货王/今日节点/黑马观察）。

## 数据源与解析
| 数据源 | URL | 解析 | 量 |
|---|---|---|---|
| 蝉妈妈·热门视频 | `https://chanmama.com/awemeRank/hotAweme` | 表格 `<table>`（三策略降级：表格→CSS 卡片→正则） | TOP10 |
| 蝉妈妈·电商带货 | `https://www.chanmama.com/awemeRank/promotionAweme/` | 复用表格逻辑 | TOP10 |
| 百度实时热搜 | `https://top.baidu.com/board?tab=realtime` | JSON 正则提取 word+hotScore | TOP10 |

- 蝉妈妈榜单页是 SPA，必须 Selenium 渲染（requests 只拿到约 3.8KB 空壳）；百度热搜是服务端渲染，可直接 requests。
- 链接转换：从隐藏 `<a>` 提取 `iesdouyin.com/share/video/{ID}` → 转为 `douyin.com/video/{ID}`（实测 10/10 成功）。
- 达人名清理：去除「粉丝数、时间戳」污染，两轮正则 + 长度保底校验。
- 分类：视频 18 赛道（剧情/搞笑/体育/音乐/游戏/美食/情感/社会热点/二次元/创意/美妆时尚/汽车/萌宠/教育科普/舞蹈/旅行/其他）；商品 7 品类（美妆护肤/服装鞋包/食品饮料/家居日用/数码家电/母婴亲子/运动户外）。

## 输入输出
- 输入：无（脚本内置 URL 与配置）；可选修改 `main()` 只跑单榜单。
- 输出：`reports/` 下四段式报告 + 两个 CSV。

## 注意事项 / 排障
| 症状 | 原因 | 解决 |
|---|---|---|
| 三策略均未提取到数据 | 蝉妈妈改版 DOM | 打印关键 class 更新 CSS 选择器 |
| 电商带货「未获取到」 | URL 错（404） | 用 `promotionAweme/`（含尾斜杠） |
| 写 CSV Permission denied | 文件被占用 | 文件名已加时间戳防冲突；检查占用进程 |
| ChromeDriver 版本不匹配 | Chrome 自动更新 | 删缓存 `~/.wdm/drivers/` 重启重下 |
| 百度热搜空列表 | 百度改版 JSON | 检查 `"word"`/`"hotScore"` 正则 |
| 超时崩溃 | 网络/响应慢 | 调大 `PAGE_LOAD_TIMEOUT`（45s）/`ELEMENT_WAIT_TIMEOUT`（30s） |
| 触发验证码 | 访问过频 | 每天 ≤3 次 |
| headless 白屏 | Windows 沙箱 | 去 `--headless=new` 有头模式调试一次 |

## 验证清单（全部满足才算成功）
- [ ] 日志 `✅ chanmama: 成功提取 10 条记录`
- [ ] 日志 `✅ chanmama_ecommerce: 成功提取 10 条电商带货视频`
- [ ] 日志 `✅ 热搜榜: 获取到 10 条`
- [ ] `reports/douyin_report_*` 存在且 >2000 bytes
- [ ] 两个 CSV 存在（UTF-8-BOM）
- [ ] 报告含完整四段；总耗时 <60s（正常 20–35s）

## 可复用示例
```bash
.venv/Scripts/python.exe scripts/douyin-scraper/douyin_scraper.py
# 增强模式（由 Agent 执行）：读最新报告 → 为每条视频补一句话点评 → 对比昨日标注升降榜 → 转 Markdown 推送
```
