---
name: demo-materials
description: 演示材料结构化整理：把零散素材切片建库（S-x）、生成页面骨架（P-x）、填写要点（T-x），经质量校验后渲染 Word 演示脚本。触发场景：演示大纲、PPT 大纲、对外演示/推介/汇报/宣讲材料、素材整理成演示、页面要点、演示脚本。
author: Soulmate Agent团队成员：岸
---

# 演示材料结构化整理
## 适用场景

- 把零散素材整理成结构清晰的对外演示材料大纲与页面要点，导出 Word 演示脚本
- 支持来源：Markdown/文本目录、粘贴长文本、stdin、Word 文档、JSON 清单
- 触发词：演示材料整理、演示大纲、PPT 大纲、对外演示、推介材料、汇报材料、素材整理成演示、页面要点、演示脚本、宣讲材料、售前材料、发布会材料

## 硬性规则

1. **要点必须锚定素材原文**：每条 `points[].quote` 都要在素材库中逐字命中；杜撰、改写（如把"三天内"写成"72 小时"）一律 E3 拦截。
2. **先定主线，再填内容**：禁止"把素材按顺序念一遍"；页面 `role` 必须是十种角色之一，且必须含「封面」与「收尾」（缺一即 E7）。
3. **人工补充必须注明**：`custom=true` 的要点必须填 `note` 说明依据，否则 E13 拦截。
4. **不用绝对化表述**：「行业第一」「绝对」「100%」触发 W10。
5. **只改 outline.json，不在 Word 里改**：Word 是渲染产物；改结构后重跑 `--reindex` 与校验。

## 步骤（五步流程）

```bash
# 1 素材切片建库（S-x）
python3 scripts/demo-materials/parse_materials.py 素材目录 -o materials.json --name "素材库名"
#    其他来源：
#      python3 scripts/demo-materials/parse_materials.py --text "粘贴的一大段内容" --text-name "微信记录" -o materials.json
#      cat 文件 | python3 scripts/demo-materials/parse_materials.py --stdin -o materials.json
#      python3 scripts/demo-materials/parse_materials.py --json-list list.json -o materials.json
#      （目录含 .docx 时自动按标题样式切片；--max-chars 控制单条最大字数）

# 2 生成页面骨架（P-x），按受众与主线预设
python3 scripts/demo-materials/build_outline.py --materials materials.json --name "演示名称" \
    --audience "受众" --goal "演示目标" --duration 20 \
    --preset problem -o outline.json
#    --preset: problem 问题导向（默认）/ solution 方案导向 / internal 内部汇报

# 3 按每页 candidates 推荐素材，填写 points（text / quote / sids）
#    quote 必须逐字复制素材原文；sids 用 find_quote 或人工确认

# 4 校验（有 ERROR 不许交付）
python3 scripts/demo-materials/check_outline.py outline.json -o 校验报告.md

# 5 渲染 Word 演示脚本（--md 可选同步 Markdown 大纲）
python3 scripts/demo-materials/render_docx.py outline.json -o 演示脚本.docx --md 演示大纲.md
```

人工调整结构后：

```bash
python3 scripts/demo-materials/render_docx.py outline.json --reindex --out-json outline.json   # 重排编号
python3 scripts/demo-materials/check_outline.py outline.json -o 校验报告.md                    # 必须复检
python3 scripts/demo-materials/render_docx.py outline.json -o 演示脚本.docx --md 演示大纲.md
```

## 脚本清单

| 脚本 | 作用 |
|------|------|
| `scripts/demo-materials/parse_materials.py` | 素材 → `materials.json`（S-x）。目录/单文件/长文本/stdin/Word/JSON 清单 |
| `scripts/demo-materials/build_outline.py` | 生成页面骨架 `outline.json`（P-x），附每页候选素材线索 |
| `scripts/demo-materials/check_outline.py` | 质量闸门：14 条 ERROR + 10 条 WARN，有 ERROR 则 exit 1 |
| `scripts/demo-materials/render_docx.py` | 渲染 Word 演示脚本；`--md` 出 Markdown 大纲；`--reindex` 重排编号 |
| `scripts/demo-materials/lib_outline.py` | 公共库：切片、归一化逐字比对、相似度、时长配比 |

模板：`assets/demo-materials/outline-template.json`、`assets/demo-materials/materials-list.json`。
细则：`assets/demo-materials/docs/outline-spec.md`、`assets/demo-materials/docs/structuring-guide.md`。

## 校验规则

**ERROR（命中即 exit 1）**：E1 要点文本为空；E2 缺少引文且未标记人工补充；E3 引文找不到逐字匹配；E4 引用不存在的素材编号；E5 非封面页无要点；E6 role 不在十种角色内；E7 缺封面或收尾页；E8 页面标题为空；E9 素材库为空；E10 大纲无页面；E11 页面 id 重复；E12 要点 id 重复；E13 人工补充未写 note；E14 引文与所标素材编号对不上。

**WARN（提示不阻断）**：W1 单页要点 <2 或 >6；W2 素材未被任何页面引用（疑似遗漏）；W3 要点含数字但引文无该数字；W4 缺讲稿备注；W5 时长合计偏差 >20%；W6 缺页面目标；W7 跨页要点高度相似；W8 未填受众或目标；W10 含绝对化/夸大表述。

## 输入输出

- **输入**：素材目录/单文件/长文本/stdin/Word/JSON 清单；演示名称、受众、目标、时长、主线预设。
- **输出**：`materials.json`（素材库）、`outline.json`（大纲）、`校验报告.md`、`演示脚本.docx`（封面信息 + 大纲总览表 + 逐页要点/原文/讲稿备注 + 素材溯源表）；`--md` 输出 Markdown 大纲。

## 注意事项

- 素材原文是锁定区，由脚本带入；**不要手工编辑** `materials[].text`。
- `candidates` 只是字符相似度线索，不是结论；命中套话属正常噪音，人工确认后忽略。
- 语义相关但措辞完全不同的素材脚本推荐不出来，需人工翻 W2 的"未引用素材"。
- 涉及内部成本、竞品负面、未公开数据的内容对外材料不应引用——本技能不替你判断，需人工把关。
- 产出是**演示脚本**（大纲 + 要点 + 讲稿），不是可直接放映的 PPT 文件。
- `render_docx.py` 生成 .docx 依赖 `python-docx`。

## 可复用示例

```bash
python3 scripts/demo-materials/parse_materials.py ./素材 -o materials.json --name "产品推介素材库"
python3 scripts/demo-materials/build_outline.py --materials materials.json --name "智能制造平台对外推介" \
  --audience "制造业客户IT负责人" --goal "促成试用" --duration 20 --preset problem -o outline.json
python3 scripts/demo-materials/check_outline.py outline.json -o 校验报告.md
python3 scripts/demo-materials/render_docx.py outline.json -o 演示脚本.docx --md 演示大纲.md
```
