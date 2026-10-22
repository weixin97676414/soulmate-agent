---
name: wireframe-generation
description: 线框图与用户流程图生成：用脚本快速画 ASCII/SVG 页面线框、单组件线框与含判断点的用户流程图，支持加编号注释、导出独立 HTML、调用内置模板。触发场景：画线框图、低保真页面布局草图、组件草图、用户流程图、给 SVG 加注释、导出线框 HTML。
author: Soulmate Agent团队成员：岸
---

# 线框图与用户流程图生成
## 适用场景

- 用 ASCII/SVG 快速画页面布局草图、单组件草图
- 画页面跳转与判断点的用户流程图
- 给已有 SVG 线框图加编号注释
- 导出为独立 HTML（内联样式）
- 触发词：wireframe、线框图、页面布局草图、低保真、用户流程图、page sketch

## 步骤

1. 确认要画的对象：整页（page）/ 单组件（component）/ 流程（flow）/ 加注释（annotate）/ 导出（export）/ 用内置模板（template）。
2. 调用 `scripts/wireframe/script.sh` 对应子命令，指定 `--format ascii|svg`、`--output`。
3. 需要多人评审时用 `annotate` 加编号图例，或 `export` 出 HTML。
4. 检查输出：区块是否齐全、连线是否成环、标注是否可读。

## 命令与用法

```bash
# 整页线框
bash scripts/wireframe/script.sh page --sections "header,hero,features,cta,footer" --format svg --output wireframe.svg
# 单组件线框
bash scripts/wireframe/script.sh component --type card --fields "image,title,text,button" --output card.svg
# 用户流程（含判断点）
bash scripts/wireframe/script.sh flow --steps "login,dashboard,settings,logout" --decisions "auth:yes/no" --output flow.svg
# 加注释与图例
bash scripts/wireframe/script.sh annotate --input wireframe.svg --notes "1:Logo area,2:Search bar,3:Main content" --output annotated.svg
# 导出独立 HTML
bash scripts/wireframe/script.sh export --input wireframe.svg --format html --output wireframe.html
# 用内置模板（landing / dashboard / blog / ecommerce 等）
bash scripts/wireframe/script.sh template --name landing --format ascii
```

## 输入输出

- **输入**：分区清单 / 组件类型 + 字段 / 流程步骤与判断 / 现有 SVG 与注释 / 模板名。
- **输出**：`page` → stdout ASCII 或 SVG 文件；`component`/`flow`/`annotate` → SVG；`export` → 独立 HTML；`template` → 指定格式线框。

## 注意事项

- 依赖 `bash 4+`。
- 线框是低保真沟通工具，不要在这里做视觉精修。

## 可复用示例

```
bash scripts/wireframe/script.sh page --sections "header,hero,features,cta,footer" --format ascii
bash scripts/wireframe/script.sh template --name dashboard --format svg --output dash.svg
```
