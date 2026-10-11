---
name: ecom-product-data-collection
description: 淘宝商品数据采集：按关键词与价格区间批量采集商品，生成含主图的 Excel 报告。触发：采集淘宝商品数据／电商调研／获取商品信息／价格监控／销量数据统计。
author: Soulmate Agent团队成员：岸
---

# 淘宝商品数据采集（含图片 Excel 报告）

配套脚本：`scripts/`（Node.js + Playwright）。

## 适用场景

- 按关键词/价格区间批量采集淘宝商品信息，做市场调研与竞品分析。
- 生成含主图、标题、价格、销量、评价数、店铺、链接的 Excel 报告。
- 触发词：采集淘宝产品数据、电商调研、获取商品信息、价格监控、销量数据统计。

## 步骤

1. **安装依赖**：
   ```bash
   cd scripts
   npm install
   ```
2. **首次运行登录**：脚本会自动打开浏览器，手动完成淘宝登录后回车继续；登录态保存在 `browser_data/`，之后无需重复登录。
3. **执行采集**：
   ```bash
   node taobao_research.js <关键词> <价格区间> <数量> [输出目录]
   # 例
   node taobao_research.js "AI机器人" "0-169" 15
   node taobao_research.js "智能手表" "100-500" 20 ./output
   node taobao_research.js "无人机" "1000-5000" 10
   ```
4. **程序化调用**：
   ```javascript
   const { TaobaoResearcher } = require('./taobao_research.js');
   new TaobaoResearcher({ keyword:'AI机器人', priceMin:0, priceMax:169, maxItems:15,
     outputDir:'./research_output' }).run().then(r=>console.log('完成:',r));
   ```
5. **取报告**：输出 `taobao_<关键词>_<价格区间>_<时间戳>.xlsx`。

## 输出字段

| 字段 | 说明 |
|-----|------|
| 序号 | 排名 |
| 主图 | 产品图片（嵌入） |
| 标题 | 产品名称 |
| 价格 | 实际售价 |
| 销量 | 付款人数 |
| 评价数 | 评价数量 |
| 店铺 | 店铺名称 |
| 链接 | 可点击的商品链接 |

## 注意事项（反爬）

- 控制采集频率（脚本内置随机延迟）；单次建议 10-20 个；不同价格区间间隔 10 秒以上。
- 保持淘宝登录状态，失效需重新登录。
- 价格筛选双重校验，确保落在区间内。
- 依赖：`playwright`、`xlsx`、`exceljs`。

## 故障排查

- 无法提取数据：检查登录；查看 `debug_*.png` 截图；可能页面结构变化需更新选择器。
- 图片下载失败：检查网络；图片 URL 可能已过期，不影响其它数据。
- 评价数获取失败：部分商品无评价；详情页加载超时（已设 5 秒等待）。

## 可复用示例

> "采集淘宝上'智能手表'100-500 元区间的 20 个商品，生成 Excel 报告。"
