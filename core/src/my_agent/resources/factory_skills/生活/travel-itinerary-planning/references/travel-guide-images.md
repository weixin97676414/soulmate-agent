# 攻略图生成（小红书风格图片物料）

> 一次全流程约 8–12 分钟。

## 适用场景

用户要"像小红书那样的攻略图 / 路线图"、要城市景点分布图、要能发朋友圈的精美图片（不是纯文字攻略）时使用。

## 输入

- `plan.json`（行程数据，见 `travel-itinerary-planning.md`）
- 本目录 `scripts/` 下全部脚本

## 产物

| 产物 | 说明 |
|---|---|
| 路线总览卡片 | 3-4 列彩色卡片，每天一列，节点串联含真实照片 |
| 景点分布总地图 | 真实地图底图 + 彩色虚线圈分区 + 图钉标签 |
| Day1-N 每日路线图 | 真实放大底图 + 编号圆圈 + 箭头 + 交通标注 |

## 步骤

### Step 1 · 一键生成几何与样板（planner.py）

```bash
python3 scripts/planner.py plan.json --out guide_out/ --cache tiles/
# 产出：
#   basemap_overview.png + origin.json          总底图（自动 bbox + zoom）
#   daymaps/basemap_dayN.png + origin_dayN.json 每日放大底图
#   map_spec.json  dayN_spec.json               总图/每日图 spec（含标签避让结果）
#   cards_spec.json  photo_queries.json         路线卡片 spec + 照片搜索词
#   docx_content.json                            Word 内容骨架（AI 补文案）
```

planner 自动完成：bbox/zoom 选择、拉底图、经纬度→像素、分区圈、路线链、交通胶囊定位、标签自动避让、图例、照片搜索词、docx 骨架。**全部标签避让成功才继续**；有 unresolved 就回 `plan.json` 合并密集点。

迭代调布局时加 `--reuse-basemaps` 跳过拉底图（bbox/zoom 匹配才复用）。

### Step 2 · 渲染 HTML

模型的唯一工作是**填 plan.json + spec 里的文案**，不手写 spec 坐标/HTML——`planner.py` 自动生成全部 spec，样式已固化在 `scripts/xhs_style.py`：

```bash
python3 scripts/make_overview.py map_spec.json overview_map.html   # 总地图
python3 scripts/make_day_map.py day1_spec.json day1.html           # 每日图
python3 scripts/make_overview.py cards_spec.json cards.html        # 路线卡片（先下照片）
```

`make_day_map.py` 会打印正确的 window-size。

### Step 3 · 截图

```bash
bash scripts/render_html.sh day1.html day1.png 768 1204
# 用法: render_html.sh <html_path> <out_png> <width> <height> [scale=2]
```

必须用本机 Chrome headless，**别用 omp browser/cmux**（视口锁定为 777×1223 竖屏且 fullPage 不可用）。脚本自动把 HTML 路径转绝对路径，`--force-device-scale-factor=2` 输出 2x 高清。

### Step 4 · 下载景点照片（Wikimedia Commons，CC 协议）

```bash
python3 scripts/wiki_photo.py "Hongya Cave night" out.jpg
python3 scripts/wiki_photo.py --batch photo_queries.json --dir photos/
```

### Step 5 · 路线卡片渲染 + 压缩 + 裁底

```bash
cd guide_out/
python3 scripts/make_overview.py cards_spec.json cards.html        # 先下载照片再渲染
bash scripts/render_html.sh cards.html cards.png 1560 1100
python3 scripts/img_tools.py trim-bottom cards.png --bg "#FFF6EE" --margin 60
python3 scripts/img_tools.py to-jpg overview_map.png jpg/overview_map.jpg
# ... 每张图转 jpg 到 jpg/ 目录（docx 用）
```

### Step 6 · 质检 qcheck.py（不可跳过）

```bash
python3 scripts/qcheck.py --out guide_out/
# QC PASS = 无标签重叠 / 无空白截图 / 尺寸正常；FAIL 按 [tag] 定位修复
```

qcheck 用与浏览器一致的包围盒公式自动查标签/交通/Tips 重叠 + 像素采样查空白页 + 尺寸校验，替代人工逐图 read。**标签自动避让后通常直接 PASS**；FAIL 按 `[tag]` 定位回 `plan.json` 修改重跑。

浏览器实测复核可用 qcheck 之外再开 HTML evaluate `getBoundingClientRect`（几何与算法完全一致）。

## 底图：高德瓦片拼接（免 key，planner 自动做）

```bash
# 手动方式（planner.py 内部也是调它）
python3 scripts/fetch_tiles.py --bbox 104.0,30.55,104.20,30.80 --zoom 13 \
    --out basemap.png --meta origin.json
# bbox/zoom 由 planner 按目标宽自动选（总图 ~1536px、每日图 ~1792px）
```

瓦片地址：

```
https://webst0{2,3,4}.is.autonavi.com/appmaptile?style={s}&x={x}&y={y}&z={z}
```

| style | 内容 | 格式 | 用途 |
|---|---|---|---|
| 6 | 暗色夜景底图 | JPEG | **不要用**（看着像底图其实是暗色主题，亮度 ~109） |
| 7 | 浅色标准底图 | JPEG | 底图（亮度 ~224，高德官网默认风格） |
| 8 | 透明地名标注层 | PNG | 叠加在 7 上才有路名/地名 |

- 必须带 `Referer: https://ditu.amap.com/`
- **webst01 经常 SSL 握手超时**，轮询 02/03/04
- 有频控：tile 间隔 ≥0.05s，失败指数退避重试
- 瓦片缓存到本地目录（`--cache`），重复生成不重复下载

**zoom 与范围经验：**

| 场景 | zoom | 典型尺寸 |
|---|---|---|
| 全市总览 | 12-13 | 1536×1280 |
| 城区单日放大 | 14 | 768×1024 |
| 市区→远郊走廊 | 10-11 | 2300×900 裁剪 |

别在 z14+ 拼大范围——瓦片数爆炸（z14 全市 = 几十张 × 2 层）。全市用 z13，每日图从 z13 底图 crop 或单独 fetch 小范围 z14。

## 坐标换算

planner 内部用 `scripts/geo.py` 的 `to_pixels()`；手动可跑：

```bash
python3 scripts/geo.py --meta origin.json --spots spots.json --out pixels.json
# spots.json 输入 {"解放碑": [106.5776, 29.5570]}; 值 = [经度, 纬度]
```

## 景点数据

`scripts/spots_db.py` 内置 10 城（重庆/成都/西安/杭州/北京/上海/广州/深圳/武汉/南京）景点坐标/门票/图标/描述/照片搜索词。`plan.json` 直接写景点名，planner 自动取数。查可用城市：

```bash
python3 scripts/spots_db.py --cities
```

## 小红书风格要点

- 奶油底 `#FFF6EE`，主红 `#C0392B`，Day 配色固定：1红 2紫 3橙 4绿 5蓝
- 标签：米白椭圆 `#FFFBEF` + 橙边 `#E8912D`，黑粗名称 + 棕色小字描述
- 价格标签：黑底白字（免费）/ 红底白字（收费）
- 箭头：Day 色贝塞尔弧线，跨江/长途段用虚线
- 每个景点标"免费"或价格——小红书攻略的信息密度就在这些 chip 上

## 注意事项

- **HTML 渲染四大坑**：
  1. 页面容器必须显式 width/height。子元素全 absolute 时父容器高度坍缩为 0 → 截出全白图。
  2. 底图必须 `no-repeat left top`。用 `cover`/`center` 会缩放底图，所有像素坐标全错位。
  3. window-size 与页面宽高严格一致，否则出现白边或裁剪。
  4. 不要用 omp browser/cmux 截图——视口被锁定；用本机 Chrome headless（`render_html.sh`）。
- **标签避让**：景点密集区（如渝中半岛）标签必然重叠。相邻 <100px 的点合并成一个标签（"解放碑 → 八一路好吃街"）；总图上只标大点，密集小点留给每日放大图。
- 照片必用 CC 协议来源（Wikimedia Commons），页脚标注来源；中文景点用英文名搜命中率更高（重庆搜 "Hongya Cave"，李子坝搜 "Liziba Station"）。
- wiki_photo 有 429 频控，请求限速（脚本约 1.5–4s 间隔），失败指数退避。
- `spots_db.py` 只覆盖 10 城；其他城市需在 `plan.json` 写自定义 `{"name","lon","lat","desc"}`。

## 可复用示例

```bash
# 成都3天：plan.json → 全套图 + Word 骨架
python3 scripts/planner.py plan.json --out guide_out/ --cache tiles/
cd guide_out/
python3 scripts/make_overview.py map_spec.json overview_map.html
python3 scripts/make_day_map.py day1_spec.json day1.html
bash scripts/render_html.sh overview_map.html overview_map.png 1536 1280
bash scripts/render_html.sh day1.html day1.png 768 1024
python3 scripts/wiki_photo.py --batch photo_queries.json --dir photos/
python3 scripts/make_overview.py cards_spec.json cards.html
bash scripts/render_html.sh cards.html cards.png 1560 1100
python3 scripts/img_tools.py trim-bottom cards.png --bg "#FFF6EE" --margin 60
python3 scripts/qcheck.py --out .
```
