---
name: academic-figures
description: 生成出版级学术配图（24 种图表：柱状/箱线/散点/热力图/森林图/KM/ROC/PRISMA/韦恩等），支持期刊预设、色盲安全配色、600dpi 多格式导出与投稿质量门禁。触发：论文配图、SCI/期刊出图、学术图表、森林图/KM/ROC/PRISMA 出图。
author: Soulmate Agent团队成员：岸
---

# 学术论文配图生成

本技能聚焦出版级统计配图（600dpi、TIFF/PNG/PDF/SVG/EPS 多格式、期刊版式与质量门禁）；面向业务演示的交互式网页图表不由本技能承担。

## 适用场景

- 论文/期刊/SCI 配图：柱状图、分组柱、散点、热力图、森林图、KM 生存曲线、ROC、小提琴、箱线、组合图、流程图、PRISMA 系统综述、Meta 漏斗图、韦恩/欧拉图、PCA、Bland-Altman、斜率图、火山图等 24 种。
- 需要出版级导出：600dpi、TIFF/PNG/PDF/SVG/EPS、色盲安全配色、期刊栏宽与最小字号门禁。
- 把 JSON/CSV/Excel 数据转成学术图表。纯本地渲染，数据不出本机。

## 步骤

1. **首次环境准备**：`python3 assets/academic-figures/scripts/setup_env.py`（安装 matplotlib/numpy/pymupdf/scipy、检测中文字体、自检）。
2. **选图**：不确定图型时跑 `--wizard`（问答生成命令）、`--suggest -d 数据文件`（自动推荐）或 `--quick -d 数据文件`（一键出图）。
3. **出图**：`python3 assets/academic-figures/scripts/gen_figure.py -t <类型> -d <数据> -o <输出> [选项]`。
4. **投稿交付**：加 `--verify`（PDF 像素级重叠检测，exit 2 表示需修复）；必要时用 `--pub-ready` 一键投稿包。
5. **质量门禁**：`python3 assets/academic-figures/scripts/audit_pdf.py <pdf> --min-size <期刊最小字号> --fail-below`；交付每个 PDF 前跑 `verify_overlap_pixel.py`，真实重叠必须为 0。
6. **图例**：禁止图内图例的期刊用 `gen_legend.py` 生成期刊格式图例（与出图同数据源，颜色一致）。

## 输入输出

- 输入：JSON（完整功能）或 CSV（基础）；Excel 用 `--sheet`。全部图型 schema 见 `assets/academic-figures/scripts/` 中的数据格式文档。
- 输出：PNG（默认 600dpi）/ SVG / PDF / TIFF / EPS；`--multi-format tiff,png,pdf` 一次多格式；`--alt` 生成 `<输出>.alt.txt` 无障碍说明。

## 图表类型（`-t`）

| 类别 | 类型与命令 |
|------|-----------|
| 比较 | `bar` 柱状、`hbar` 水平柱、`grouped_bar` 分组柱（`--show-ratio`） |
| 构成 | `stacked_bar` 堆叠柱 |
| 分布 | `box` 箱线、`violin` 小提琴 |
| 配对 | `paired` 前后配对（n≥6 才标注） |
| 趋势 | `scatter` 散点、`line` 折线、`slope` 斜率、`dual_axis` 双轴 |
| 矩阵 | `heatmap` 热力图、`cluster_heatmap` 聚类热图（`--downsample`） |
| 多变量 | `pca` 得分图（≤200 特征列） |
| 统计推断 | `forest` 森林图（`--stats cox` 多因素回归）、`funnel` 漏斗（`--egger`） |
| 生存 | `km` KM 生存曲线（含竞争风险 Aalen-Johansen） |
| 诊断 | `roc` ROC（`--compare` DeLong 对比） |
| 组学 | `volcano` 火山图 |
| 一致性 | `bland_altman` |
| 集合 | `venn` 2~4 集合（`--area` 面积比例） |
| 组合 | `composite` 多面板（面板内不可再嵌套 composite） |
| 流程 | `diagram` 流程图、`prisma` PRISMA 2020（数字自洽校验，不齐拒绝出图） |

## 配色与期刊预设

- 默认 `glm`（莫兰迪，色盲安全）；投稿首选 `okabe-ito`（Nature Methods 金标准）。另有 `cool`、`classic`、`nature`、`lancet`、`nejm`、`science`、`conservative`。
- `--style glm-hatch`（glm+斜纹，黑白友好）、`--style nature-clean`（Okabe-Ito+Nature 版式）、`--alternate`（单系列逐柱交替）。
- 期刊预设：`--journal nature|lancet|nejm|science|cell|jama|ieee|cma|cn-core` + `--column single|double`，自动应用官方栏宽/字号/字体族/600dpi；中文刊自动漫 CJK。预设唯一权威源为 `assets/academic-figures/scripts/journal/*.json`。

## 退出码

| 码 | 含义 |
|----|------|
| 0 | 成功（--verify 时=无真实重叠） |
| 1 | 参数/用法或数据校验致命错（不落盘） |
| 2 | --verify 检出重叠；或流水线有失败项（修复机制，不要交付） |
| 3 | 数据/格式错误 |
| 4 | 环境/依赖错误 |
| 5 | 渲染看门狗超时 |
| 6 | 内存护栏拒绝 |

## 注意事项

- 参数兼容：`--stats` 仅 box/violin（`cox` 仅 forest）；`--compare` 仅 roc；`--egger` 仅 funnel；`--hatch` 仅 bar 系；`--sheet` 仅 xlsx；`--journal` 会锁定图宽（`--width` 被覆盖）；`--area` 仅 venn。
- 数据量：cluster_heatmap >3000 行自动降采样到 2000 行；pca ≤200 特征列；venn 2~4 集合；paired/bland_altman 需等长。
- 中文：`--cjk` 自动检测字体；数据含中文会递归自动检测，无需显式传参。
- 参数含空格或以 `-` 开头时用等号形式：`--xlabel="改善率 (%)"`、`--ylabel="-log10(P)"`。
- 报错前缀 `ERROR:`（中文原因+改法）、`WARNING:`（继续运行）；`AF_DEBUG=1` 取完整细节。
- 脚本位于 `assets/academic-figures/`（scripts/templates/examples），运行时以该目录为准；依赖 4 项 PyPI 开源库。

## 可复用示例

```bash
# 环境
python3 assets/academic-figures/scripts/setup_env.py

# 柱状图 + 中文
python3 assets/academic-figures/scripts/gen_figure.py -t bar -d data.json -o figure.png \
  --title "图2 主标题 / Subtitle" --ylabel "准确率 Accuracy (%)" --cjk

# 投稿包（自动 --verify + 色盲安全 + 多格式）
python3 assets/academic-figures/scripts/gen_figure.py -t bar -d data.json -o fig --pub-ready

# 森林图 / Cox 多因素回归
python3 assets/academic-figures/scripts/gen_figure.py -t forest -d forest.json -o forest.pdf --theme okabe-ito
python3 assets/academic-figures/scripts/gen_figure.py -t forest --data patient.csv --stats cox \
  --cox-time time --cox-event event --cox-cols "age,sex,treat"

# KM 生存曲线
python3 assets/academic-figures/scripts/gen_figure.py -t km -d survival.json -o km.png --theme okabe-ito \
  --xlabel "时间 (月)" --ylabel "生存概率"

# Nature 双栏 + 字号门禁
python3 assets/academic-figures/scripts/gen_figure.py -t bar -d data.json -o nat.pdf --journal nature --column double
python3 assets/academic-figures/scripts/audit_pdf.py nat.pdf --min-size 5 --fail-below

# 组合图
python3 assets/academic-figures/scripts/gen_figure.py -t composite -d composite.json -o figure4.png --theme okabe-ito

# 补充图例
python3 assets/academic-figures/scripts/gen_legend.py -d data.json -t "治疗应答" -f 1 -o legend.txt
```

JSON 柱状图示例：

```json
{
  "labels": ["对照组", "实验组"],
  "series": {"治疗前": [75, 82], "治疗后": [68, 70]},
  "errors": {"治疗前": [3, 2], "治疗后": [2, 1]},
  "significance": {"治疗前:0": "***", "治疗后:1": "NS"}
}
```
