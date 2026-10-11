---
name: skill-authoring
description: 创建与打包 Skill：Skill 结构、三层渐进披露、init_skill.py 初始化、package_skill.py 打包与校验、scripts/references/assets 规划。触发场景：新建或更新 Skill、打包 .skill 文件、设计技能目录结构。
author: Soulmate Agent团队成员：岸
---

# 功能：Skill 创建

脚本位于 `scripts/skill-creator/`（`init_skill.py`、`package_skill.py`、`quick_validate.py`）；设计模式参考见 `assets/skill-creator-references/workflows.md`、`assets/skill-creator-references/output-patterns.md`。

## 适用场景
用户想新建或更新一个扩展能力的 Skill（专门知识、工作流、工具集成）时使用。

## 核心原则
- **简洁是关键**：上下文窗口是公共资源，默认「AI 已经很聪明」，只加入它没有的信息；用简洁示例代替冗长解释。
- **合适的自由度**：多路径/依赖上下文 → 文本指令（高自由度）；有偏好模式/可有变化 → 伪代码或带参脚本（中）；易错、需一致、固定顺序 → 具体脚本少参数（低）。

## Skill 结构
```
skill-name/
├── SKILL.md（必需）
│   ├── YAML frontmatter（仅 name + description）
│   └── Markdown 指令
└── 捆绑资源（可选）
    ├── scripts/     可执行代码（Python/Bash）
    ├── references/  按需加载的文档
    └── assets/      产出用的文件（模板/图标/字体）
```
- SKILL.md 正文保持 <500 行；接近上限就拆分并在 SKILL.md 中引用、说明何时读。
- references 保持一层深（全部直接由 SKILL.md 链接）；超过 100 行的参考文件顶部加目录。
- **不要**放 README.md、INSTALLATION_GUIDE.md、CHANGELOG.md 等杂项文档。

## 渐进披露三层
1. Metadata（name + description）——始终在上下文（~100 词）；
2. SKILL.md 正文——触发时加载（<5k 词）；
3. 捆绑资源——按需加载（脚本可不读入上下文直接执行）。

模式：高层指南 + 引用；按领域组织 reference 目录；条件细节（基础写在正文，进阶链接出去）。

## 创建流程

1. **用具体示例理解 Skill**：问功能范围、使用示例、触发说法。避免一次问太多问题。
2. **规划可复用内容**：对每个示例，从零执行需要什么 → 列出 scripts/references/assets。例：要反复写同样代码 → `scripts/<脚本>.py`；要同样样板 → `assets/` 模板；要反复发现 schema → `references/<schema>.md`。
3. **初始化**：
   ```bash
   python scripts/skill-creator/init_skill.py <skill-name> --path <output-directory>
   ```
   生成目录、SKILL.md 模板（含 TODO）、示例 `scripts/`/`references/`/`assets/`。
4. **编辑 Skill**：先实现可复用资源（脚本**必须真实运行测试**）；删除不需要的示例；更新 SKILL.md——正文用祈使句，**frontmatter 只写 name 和 description**，description 包含「做什么 + 何时用（所有触发场景）」。
5. **打包**：
   ```bash
   python scripts/skill-creator/package_skill.py <path/to/skill-folder> [./dist]
   ```
   先自动校验（frontmatter 格式与必填、命名与目录、description 完整度、文件组织与引用），通过后生成 `<skill>.skill`（含 .skill 扩展名的 zip）。
6. **迭代**：真实使用 → 发现低效 → 更新 SKILL.md/资源 → 再测。

## 输入输出
- 输入：要创建/更新的 Skill 名称与用途示例。
- 输出：符合结构的 Skill 目录 + 打包的 `.skill` 文件 + 校验结果。

## 注意事项
- frontmatter 只保留 `name`/`description`。
- description 决定触发，务必涵盖所有「何时用」；不要把「使用时」信息放进正文。
- 参考文件与正文避免重复：核心程序指令留正文，详细参考/示例移入 references。

## 可复用示例
> 新建 `pdf-editor`：示例「帮我旋转这个 PDF」→ 规划 `scripts/<rotate_pdf>.py` → `init_skill.py pdf-editor --path .` → 写脚本并实跑验证 → 完善 SKILL.md（description 含旋转/合并/拆分等触发）→ `package_skill.py pdf-editor` → 产出 `pdf-editor.skill`。
