# 拆解 Plan JSON 标准契约（v1.3）

本文件定义 `video-script-dissect` 被**其他技能 / 工作流以"接口"方式调用**时的标准输入（plan）与输出（result）结构。

- **对话模式**：用户直接在对话里用本技能，仍按 `SKILL.md` 正常走 9 步流程，无需构造 plan。
- **编排模式**：当本技能作为被其他 skill / 自动化编排的子能力时，调用方构造如下 `plan`，本技能按 plan 执行，并产出机器可读 `result`（与 Markdown 报告同源），方便上层直接解析、串联下一步。

> 设计原则：护城河（抽帧视觉分析 / 8维评分 / 人机共创 / 选题库）一律保留，本契约只新增"可被程序化调用"的标准化参数，不增删分析能力。

---

## 一、Plan（输入契约）

```json
{
  "skill": "video-script-dissect",
  "version": ">=1.3",
  "input": {
    "type": "url | file | transcript",
    "source": "<视频号链接 / 本地视频路径 / 用户粘贴的逐字稿文本>",
    "persona": "<二创人设：默认'模仿原片'；可选'职场IP'等>",
    "duration_est": "<可选，秒，用于预判断形态>"
  },
  "config": {
    "visual_analysis": true,
    "scorecard_dimensions": 8,
    "confirm_gate": true,
    "angle_pool_size": 10,
    "final_angle_count": 5,
    "type_hint": "<可选，视频号类型：见 SKILL.md 类型感知表>",
    "republish_check": false,
    "self_check": false
  },
  "output": {
    "report_path": "<可选，默认 视频拆解报告_<主题>_<YYYY-MM-DD>.md>",
    "save_idea_lib": true,
    "workbench_sync": true,
    "result_json": "<可选，机器可读结果输出路径>"
  }
}
```

| 字段 | 必填 | 说明 / 默认 | 对应 SKILL.md 步骤 |
|------|------|------------|-------------------|
| `input.type` | ✅ | `url` 走降级链取元数据；`file` 抽帧+ASR；`transcript` 直接进 1.5 | 步骤 1 |
| `input.source` | ✅ | 链接/路径/文本 | 步骤 1 |
| `input.persona` | ❌ | 默认"模仿原片" | 步骤 6 |
| `config.visual_analysis` | ❌ | 有文件默认 `true`；无文件强制 `false` | 步骤 1.8 |
| `config.scorecard_dimensions` | ❌ | `8` 或 `9`（加 D9 社交链） | 步骤 5 |
| `config.confirm_gate` | ❌ | `true` 触发步骤 5.5 暂停 | 步骤 5.5 |
| `config.angle_pool_size` | ❌ | 草案候选角度数，默认 `10`（范围 8–12） | 步骤 5.5 |
| `config.final_angle_count` | ❌ | 最终脚本数，默认 `5` | 步骤 6 |
| `config.type_hint` | ❌ | 视频号类型，不明时按"口播观点"处理 | 步骤 5 类型感知 |
| `config.republish_check` | ❌ | `true` 强制步骤 5.6 二次发布检测 | 步骤 5.6 |
| `config.self_check` | ❌ | `true` 调用 `references/skill-self-check.md` 产出差距报告 | 自我评估触发 |
| `output.report_path` | ❌ | 指定报告落盘路径 | 步骤 9 |
| `output.save_idea_lib` | ❌ | 是否沉淀 `video-script-dissect_选题库/` | 步骤 7 |
| `output.workbench_sync` | ❌ | 是否尝试写入工作台 | 步骤 7 |
| `output.result_json` | ❌ | 机器可读结果路径，供上层解析 | 全链路 |

---

## 二、Result（输出契约：`result_json` 内容）

```json
{
  "skill": "video-script-dissect",
  "version": "1.3",
  "status": "ok | partial | failed",
  "evidence": {
    "input_path": "file",
    "exec_path": "asr+visual",
    "degraded": ["uniform_fallback"],
    "deps": {"ffmpeg": true, "faster_whisper": true, "visual_read": true},
    "confidence": "high"
  },
  "transcript": "<校对后逐字稿或 null>",
  "scorecard": {"hook": 5, "structure": 4, "emotion": 5, "pacing": 4, "density": 5, "interaction": 3, "replicability": 2.5, "fit": 5, "social_chain": 4},
  "framework": "<结构框架层级文本>",
  "angles": [
    {"id": 1, "name": "...", "hook_type": "痛点共鸣", "form": "A", "cost": 1, "potential": 5}
  ],
  "scripts": [
    {"angle_id": 1, "title": "...", "shooting_script": "...", "publish_pack": "..."}
  ],
  "idea_lib": {"json": "<路径>", "workbench": "written | not_found"},
  "errors": ["<降级/失败说明>"]
}
```

| 字段 | 说明 |
|------|------|
| `status` | `ok`=全流程完成；`partial`=步骤 5.5 暂停待确认（angles 已给，scripts 待用户确认后二次调用）；`failed`=输入层全部降级失败（无内容可分析） |
| `evidence` | 对齐 C1 证据契约，供上层判断结论可信度 |
| `scorecard` | 8 维（或 9 维含 D9），维度名见 `framework_rubric.md` |
| `angles` / `scripts` | 二创草案 / 最终脚本，结构与报告「七之一 / 七之二」一致 |
| `idea_lib` | 选题库落盘路径 + 工作台写入结果 |

---

## 三、调用方约定（边界）

1. **调用方负责提供 `input.source`**：本技能不主动抓取视频号链接（无态沙箱限制，见降级策略），链接解析请调用方先用元宝 / 腾讯系工具取到逐字稿再传入。
2. **`confirm_gate=true` 时**：本技能在步骤 5.5 暂停，`status=partial`，把 `angles` 草案返回；上层二次调用时把用户确认的角度集合作为 `config.confirmed_angles` 带入，本技能据此生成 `scripts`。
3. **`result_json` 与 Markdown 报告同源**：优先解析 JSON，报告供人读。
4. **失败不吞错**：任何降级都在 `evidence.degraded` + `errors` 暴露，不假装成功。
