---
name: short-drama-writer
description: 竖屏短剧/微短剧剧本创作。按题材生成完整剧集大纲、角色卡、分集剧情、反转设计与钩子/悬念库，覆盖甜宠、逆袭复仇、悬疑、玄幻、家庭等热门赛道，输出可直接开拍的短剧脚本素材。触发场景：短剧剧本、竖屏短剧、微短剧、短剧大纲、短剧分集、短剧角色、短剧反转、短剧钩子、剧本创作、编剧工具、爽文短剧、付费短剧。
author: Soulmate Agent团队成员：岸
---

# 竖屏短剧剧本创作 (short-drama-writer)

按题材批量产出竖屏短剧的剧集大纲、角色卡、分集剧情与反转/钩子。附带的两个脚本可直接在本机跑：

- `scripts/drama.sh` — 短剧创作工具（题材大纲 / 角色 / 分集 / 钩子库）。
- `scripts/drama_gen.py` — 剧情生成器（plot / scene / character / twist）。

## 命令一览

### scripts/drama.sh

```bash
bash scripts/drama.sh help
bash scripts/drama.sh outline <genre> <title> [episodes]   # 全剧大纲
bash scripts/drama.sh character <name> <role>              # 角色卡
bash scripts/drama.sh episode <ep_number> <scene_count>    # 单集分场
bash scripts/drama.sh hooks                                # 钩子/悬念库
```

题材键（`genre`）：`romance`(甜宠)、`revenge`(逆袭)、`suspense`(悬疑)、`fantasy`(玄幻)、`family`(家庭)。

### scripts/drama_gen.py

```bash
python3 scripts/drama_gen.py plot <genre> [--episodes 10]   # 剧情线（可重复运行获得不同反转组合）
python3 scripts/drama_gen.py scene "场景描述"                # 场景生成
python3 scripts/drama_gen.py character "角色类型"            # 角色生成
python3 scripts/drama_gen.py twist                          # 反转设计建议
```

同一题材可重复运行 `plot` / `twist`，获得不同反转组合。

## 使用流程

1. **定题材与调性**：确认题材（甜宠/逆袭/悬疑/玄幻/家庭）、目标平台、集数与单集时长（竖屏短剧常见 80–100 集、每集 1–3 分钟）。
2. **出全剧大纲**：`outline <genre> <title> <eps>`，确认主线与分集节奏。
3. **建角色卡**：`character`，明确男主/女主/配角人设与对比关系（如灰姑娘 vs 恶毒女配）。
4. **铺分集与反转**：`episode` 排分场；`twist` / `plot` 设计反转点。
5. **埋钩子**：`hooks` 取钩子/悬念库，保证每集结尾有 cliffhanger。
6. **自检**：每集是否有推进、反转是否合逻辑、有无烂尾、是否有付费卡点。

## 创作要点

- **钩子**：前 3 秒决定是否继续看。
- **节奏**：每 30 秒一个反转或冲突；一集一个小反转。
- **角色**：人设鲜明、对比强烈。
- **反转原则**：合理但意外（回头逻辑通、第一次想不到）；大反转放第 3/4 集和倒数第 2 集；反转后给观众消化时间。
- **热门题材**：总裁 / 穿越 / 复仇 / 甜宠 / 重生。
- **集数与变现**：竖屏短剧 80–100 集、每集 1–3 分钟；付费解锁常从第 10 集开始收费。

## 输入 / 输出

- **输入**：题材、标题、集数、单集时长、平台、目标受众。
- **输出**：全剧大纲、角色卡、分集剧情/分场、反转设计、钩子与悬念清单。

## 注意事项

- 两个脚本均用本机 Bash / Python3，`scripts/drama.sh` 通过内联 Python 运行；**未在本机实跑验证每个子命令的全部输出**，首次使用建议先 `help` 与 `outline` 各跑一次确认环境。
- 短剧内容需规避平台违规题材与违禁词；涉付费变现时遵守平台规则。


## 参考文件

- `references/short-drama-tips.md` — 短剧编剧实用技巧速查（钩子/节奏/角色/题材/集数/变现）。
- `scripts/drama.sh`、`scripts/drama_gen.py`、`scripts/script.sh` — 剧本创作工具集。
