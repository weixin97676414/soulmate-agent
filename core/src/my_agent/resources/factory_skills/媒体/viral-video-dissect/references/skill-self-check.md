# 技能自我评估清单（10 维，映射 browser-automation-toolbox）

> 由 SKILL.md「自我评估触发」加载。每维标记 ✅ / ⚠️ / ❌ + 一行证据。
> 自我评估**不自动改技能**，仅产出差距报告供你决策是否合入改进。

| # | 维度 | 对标 toolbox | 本技能现状（2026-08-03 增强后） | 评分 |
|---|------|-------------|-------------------------------|------|
| 1 | 多路径降级 | 4 引擎 + 优先级 + 重试 | 输入层（链接→文件→逐字稿）+ 执行层降级链（6 类失败） | ✅ |
| 2 | 优先级与回退 | 定义优先级 + per-engine retry | 场景检测阈值回退 + ASR per-attempt retry=1 | ✅ |
| 3 | 延迟依赖 | 选中引擎才装 | venv + imageio-ffmpeg + faster-whisper 隔离安装 | ✅ |
| 4 | 失败分类 | 7 类枚举 | 新增降级原因 6 类（无音频/ASR低置信/视觉缺失/均匀兜底/分段/依赖缺失） | ✅ |
| 5 | 证据收集 | 每步存证据 | 新增「本次运行证据」节（输入/执行/降级/依赖/推测/置信度） | ✅ |
| 6 | 类型感知策略 | --platform 翻转优先级 | 新增类型感知拆解侧重表（5 类视频号类型） | ✅ |
| 7 | 经验累积 | 逐次写回 references | 新增 `dissect-lessons.md` + `record_dissect_lesson.py` | ✅ |
| 8 | 任务契约 | plan JSON 标准化 | 报告模板标准化；plan JSON 为 NICE-TO-HAVE 未做 | ⚠️ |
| 9 | 人工接管 | 暂停-恢复契约 | 步骤 5.5 暂停确认 + 补料暂停规则 | ✅ |
| 10 | 可扩展性 | 引擎注册表 | 模板 A/B/C 可加；无注册式约定 | ⚠️ |

## 总分：9 / 10

## 已知 NICE-TO-HAVE（未做，记录在案）
- **N1 拆解 plan JSON 标准化**：定义 `dissect_plan.json`（input_type / fallback_order / do_visual / target_track / output_format），便于被其他 skill CLI 调用。
- **N2 职责边界声明**：加「当被其他 skill 包装时」的接口说明（本技能拥有领域逻辑，执行交给专门工具）。
- **N3 类型感知失败预案库**：把执行层降级按视频类型细化（如「无字幕外语音频→ASR 语种参数」）。

## 输出示例（Full）
```
Target: video-script-dissect | Status: SELF-EVALUATED
Date: 2026-08-03
Gaps: [NICE-TO-HAVE] n1 plan JSON, n2 边界声明, n3 类型失败预案
Kept (护城河，不动): 抽帧视觉分析 / 8维量化评分+红线 / 人机共创关卡(5.5) / 形态自适应 A/B/C / 选题库+工作台 / 平台规则库(R10) / 二次发布检测(R9)
```
