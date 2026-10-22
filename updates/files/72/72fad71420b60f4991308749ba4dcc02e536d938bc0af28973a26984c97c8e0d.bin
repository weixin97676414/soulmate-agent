# 中间层规范：materials.json / outline.json

两个 JSON 是整条链路的唯一真相源。代码、Word、Markdown 全部由它渲染，**不要在 Word 里直接改内容**——改结构改 outline.json，再重新渲染，避免三处产物对不上。

---

## 一、materials.json（素材库）

由 `parse_materials.py` 生成，**一般不需要手工编辑**。

```json
{
  "schema": "demo-materials/v1",
  "name": "素材库名称",
  "generated_at": "2026-09-10 10:00:00",
  "total": 37,
  "materials": [
    {
      "id": "S-1",
      "source": "产品与方案介绍.md",
      "section": "产品定位",
      "text": "智质云是一套面向离散制造企业的全流程质量管控平台……",
      "tags": []
    }
  ]
}
```

| 字段 | 说明 |
|---|---|
| `id` | 素材编号 S-1…Sn，按解析顺序生成，是溯源锚点 |
| `source` | 来源文件名（粘贴内容时为自定义来源名） |
| `section` | 所属章节/切片名，便于人工定位 |
| `text` | 原文全文。**引文必须是它的连续子串**（归一化后逐字比对） |

### 切片规则

- Markdown/文本：按 `#` 标题、中文编号、数字编号分层；空行分段
- 以句读结尾或超过 30 字的行**不判为标题**（否则「第一条，检验记录仍以纸质表单为主……」会被整行吞成标题，正文丢失）
- Word：按 `Heading`/`Title` 样式切片，无样式时回退到标题正则
- 单条超过 `--max-chars`（默认 300 字）按句二次切分，避免引用粒度太粗

---

## 二、outline.json（演示大纲）

```json
{
  "schema": "demo-outline/v1",
  "meta": {
    "name": "演示名称",
    "audience": "受众",
    "goal": "本次演示要达成的目标",
    "duration_min": 20,
    "created_at": "",
    "edited_by": "人工调整者",
    "edit_note": "调整说明",
    "materials": "materials.json 的绝对路径"
  },
  "pages": [
    {
      "id": "P-1",
      "role": "封面",
      "title": "开场：一句话价值主张",
      "goal": "本页要达成的目的",
      "minutes": 0.5,
      "speaker_note": "讲稿提示",
      "candidates": [{"sid": "S-2", "score": 0.31, "section": "核心能力", "excerpt": "……"}],
      "points": [
        {
          "id": "T-1-1",
          "text": "页面要点（给听众看的一句话）",
          "quote": "素材中的原文片段（逐字）",
          "sids": ["S-2"],
          "custom": false,
          "note": "人工补充时的依据说明"
        }
      ]
    }
  ]
}
```

### 字段约束

| 字段 | 必填 | 说明 |
|---|---|---|
| 页面 `id` | 是 | P-1…P-n，**不可重复** |
| 页面 `role` | 是 | 只能是：封面、背景、痛点、方案、能力、价值、案例、路线、保障、收尾 |
| 页面 `title` | 是 | 对外页面标题 |
| 页面 `goal` | 否 | 建议填写，缺了会 WARN |
| 页面 `minutes` | 否 | 用于时长配比校验 |
| 页面 `speaker_note` | 否 | 讲稿备注 |
| 要点 `text` | 是 | 页面要点 |
| 要点 `quote` | 是（除非 custom） | 素材原文片段，逐字 |
| 要点 `sids` | 是（除非 custom） | 素材编号数组 |
| 要点 `custom` | 否 | 标记该条为人工补充（原素材没有的内容） |

### 人工补充内容的正确姿势

原素材里确实没有、但材料必须有的内容（如会后承诺、时间约定）：

```json
{"id": "T-10-2", "text": "会后三天内提供同行业脱敏案例与试点方案初稿",
 "quote": "", "sids": [], "custom": true,
 "note": "人工补充：本次演示承诺的会后交付物，原素材中无对应表述"}
```

`custom=true` 但 `note` 为空 → **E13 拦截**。这样"哪些来自素材、哪些是人工加的"始终可追溯。

---

## 三、人工调整结构

支持三种调整，改完重跑校验即可：

1. **改顺序**：直接调整 `pages` 数组顺序，然后 `render_docx.py outline.json --reindex` 重排编号
2. **增/删页面**：增删 `pages` 元素；新增页记得带 `role` 与 `title`
3. **要点搬家**：把 `points` 元素从一个页面移到另一个页面，`quote`/`sids` 跟着走，溯源不会断

调整后建议填 `meta.edited_by` 与 `meta.edit_note` 留痕。

调整完**必须**重跑：

```bash
python check_outline.py outline.json -o 校验报告.md   # 有 ERROR 则不许交付
python render_docx.py outline.json -o 演示脚本.docx --md 演示大纲.md
```
