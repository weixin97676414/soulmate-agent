# Word 攻略文档组装


## 适用场景

用户要把旅行计划/攻略做成 Word/文档时使用（如"把攻略写成 Word""要一份能打印的攻略文档"）。依赖已完成 `travel-itinerary-planning.md` 的 `plan.json` 与 `travel-guide-images.md` 的图片产物。

## 输入

- `guide_out/docx_content.json`（`planner.py` 生成的骨架，AI 补文案）
- `guide_out/jpg/*.jpg`（转好的图片）
- `scripts/make_docx.js`、`scripts/qcheck.py`

## 步骤

### Step 1 · planner 已生成骨架

`planner.py` 已产出 `docx_content.json` 骨架，**AI 只补文案**：封面速览、住宿/交通表行（若 plan 无 `transport`/`stays`）、预算表、打包清单、文化注意事项、时间线。结构固定 12 节，不可改模板逻辑。

- **目录开箱即有内容**：`make_docx.js` 生成静态目录（10 节标题 + 书签，点击可跳转），不是打开后空白的 TOC 域
- **交通/住宿预填**：`plan.json` 有 `transport`/`stays` 时，骨架的"五、交通明细"和"四、住宿推荐"自动生成具体班次表/酒店表，AI 无需再补这两节

### Step 2 · 生成 Word

```bash
NODE_PATH=$(npm root -g) node scripts/make_docx.js guide_out/docx_content.json
# docx 装在全局，故需 NODE_PATH=$(npm root -g)
```

图片尺寸自动读取缩放，不用手填 w/h。

### Step 3 · 体积质检 + 人工抽查

```bash
python3 scripts/qcheck.py --docx guide_out/成都3天2晚攻略.docx    # 体积 <300KB 视为疑似缺图
```


## 输出

- `guide_out/<城市>N天N晚攻略.docx`
- 文档结构固定 12 节：封面 → 目录 → 路线总览卡片 → 总地图 → Day 图 ×N → 住宿表 → 交通表 → 逐日行程 → 预算表 → 打包清单（checkbox 用 `LevelFormat.BULLET` text `☐`）→ 文化注意 → 行前时间线 → 尾注（时效信息复核提醒）

## 注意事项（docx-js 必踩坑）

环境：`NODE_PATH=$(npm root -g) node script.js`（docx 装在全局）。

1. **表格单元格子元素必须是 Paragraph**。裸 TextRun 数组会产出 `<w:tc>` 下直接挂 `<w:r>` 的非法 XML，打开时报 "Element w:r is not expected"。映射单元格内容时：

```js
children: cells.map(x => {
  if (typeof x === 'string') return new Paragraph({ children: [new TextRun(x)] });
  return x instanceof Paragraph ? x : new Paragraph({ children: [x] });
})
```

2. **表格双宽度**：`columnWidths`（数组，总和 = 表宽）+ 每个 cell 的 `width` 都要设，全部用 `WidthType.DXA`（百分比在 Google Docs 会坏）。
3. **A4 纸**：`size: { width: 11906, height: 16838 }`，1 英寸边距内容宽 9026 DXA。docx-js 默认 A4 但**显式写死**最稳。
4. **中文用微软雅黑**：default run font 设 `Microsoft YaHei`。
5. **图片进文档**：`ImageRun` 必须带 `type: 'jpg'`（或 png）；2x 截图转 JPEG quality=84 再嵌入，否则 docx 20MB+；A4 内容区约 623px 宽 @96dpi，图片按 `maxW/ow` 比例缩放。
6. **交付前核对**：生成后人工打开确认章节文字与嵌入图完整。
7. **目录 TOC**：`features: { updateFields: true }`，提醒用户打开后按提示更新域显示页码。

## 可复用示例

```bash
# plan.json 有 transport/stays 时，交通/住宿两节已预填，只需补预算/清单/文化/时间线文案
NODE_PATH=$(npm root -g) node scripts/make_docx.js guide_out/docx_content.json
python3 scripts/qcheck.py --docx guide_out/成都3天2晚攻略.docx
```
