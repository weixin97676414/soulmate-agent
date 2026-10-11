# 跨视频元洞察（cross_video_insight）

本文件供 `video-script-dissect` 技能「步骤 7.5」参考：把已拆的多条视频当作样本库，提炼可反哺新二创的**全局规律**。只看单条容易"见木不见林"；累计 2+ 条后即可发现模式（如"品牌型普遍弱互动"）。

---

## 一、聚合什么

扫描工作区以下文件：
- `视频拆解报告_*.md`（每条的 8 维评分、框架类型、钩子类型、赛道）
- `video-script-dissect_选题库/选题库*.json`（框架类型、钩子、潜力、成本）

提炼维度：
1. **框架类型分布**：干货逻辑型 / 品牌叙事型 / 人物故事型 / 情绪态度型 各占比。
2. **8 维评分均值与短板频率**：哪个维度在样本里最常 < 3（如「互动/转化设计」）。
3. **钩子类型成效**：哪种钩子在已拆样本里出现最多、对应留存/潜力最高。
4. **赛道共性**：哪些赛道被反复拆到、共性短板是什么。

## 二、产出洞察（写入报告「跨视频元洞察」节）

示例洞察句（按真实数据生成，不臆造）：
- "样本 N 条中，品牌型/故事型视频『互动/转化设计』**100% < 3**，二创一律强制补结尾提问钩子。"
- "反常识钩子在干货赛道出现 X 次，平均潜力 4+，二创新选题优先用反常识开场。"
- "人物故事型『可复制性』均值仅 2.8，二创需配套 ★ 轻量版降低拍摄门槛。"

## 三、半自动聚合脚本

把下方脚本存为 `cross_video_insight.py` 放工作区根目录运行（隔离 venv 的 python）。它解析报告里的 8 维评分表与框架类型，输出 Markdown 洞察块。

```python
import re, glob, os, json
from collections import defaultdict, Counter

REPORTS = sorted(glob.glob("视频拆解报告_*.md"))
framework_counter = Counter()
dim_scores = defaultdict(list)   # 维度名 -> [分]
dim_names = ["钩子强度","信息结构清晰度","情绪曲线","节奏与完播设计",
             "信息密度","互动/转化设计","可复制性","适用赛道与边界"]

for rp in REPORTS:
    txt = open(rp, encoding="utf-8").read()
    # 框架类型：从「赛道」或「框架类型」行抓
    m = re.search(r"框架类型[：:]\s*([^\n|]+)", txt)
    if m:
        framework_counter[m.group(1).strip()] += 1
    # 8 维评分表：匹配 | 维度名 | 分数 |
    for line in txt.splitlines():
        if line.count("|") >= 3:
            cells = [c.strip() for c in line.split("|")]
            for name in dim_names:
                if name in cells:
                    # 找分数单元格（数字/半档）
                    for c in cells:
                        if re.fullmatch(r"\d(\.\d)?", c):
                            dim_scores[name].append(float(c)); break

n = len(REPORTS)
lines = [f"# 跨视频元洞察（累计拆解 {n} 条）", ""]
if framework_counter:
    lines.append("**框架类型分布**：" + "、".join(f"{k} ×{v}" for k,v in framework_counter.most_common()) + "\n")
lines.append("**8 维评分均值与短板频率**：")
lines.append("| 维度 | 均值 | <3 出现次数 | 触红线率 |")
lines.append("|------|------|------------|----------|")
for name in dim_names:
    scores = dim_scores.get(name, [])
    if scores:
        avg = sum(scores)/len(scores)
        below = sum(1 for s in scores if s < 3)
        rate = f"{below/len(scores)*100:.0f}%"
        flag = " ⚠️" if avg < 3 else ""
        lines.append(f"| {name} | {avg:.1f} | {below} | {rate}{flag} |")
lines.append("")
# 自动洞察
weak = [name for name in dim_names if dim_scores.get(name) and sum(dim_scores[name])/len(dim_scores[name]) < 3]
if weak:
    lines.append(f"**自动洞察**：样本中最常触红线的维度为 {('、'.join(weak))}，二创时对这些维度一律强制补强。")
out = "\n".join(lines)
open("跨视频洞察.md", "w", encoding="utf-8").write(out)
print(out)
```

> 说明：报告里"框架类型"需以「框架类型：XXX」形式写入（本技能报告模板已含该字段，见附录 A 的 `framework` 与报告头部"框架类型"）。若字段缺失，脚本仅输出 8 维统计。
