---
name: zhihu-auto-publish
description: 用 Playwright 模拟人工操作，把用户提供的回答或文章保存到知乎草稿箱（只存草稿、绝不发布），并支持点赞/收藏/关注/评论等互动与创作者数据查看。触发：发布知乎回答、发布知乎文章、知乎自动发布、保存知乎草稿、知乎草稿箱、写知乎回答、自动回答知乎、知乎点赞互动、知乎创作者数据、知乎内容管理。
author: Soulmate Agent团队成员：岸
---

# 知乎自动发布（草稿箱）

在知乎上自动完成回答和文章的草稿保存，全程模拟人工键盘鼠标操作。**只保存草稿，不发布。** 用户手动审核后自行决定是否发布。

> ⚠️ **脚本未随包提供**：本技能正文引用的 setup.py、cookie_manager.py、check_login.py、publish_answer.py、publish_article.py、browser_utils.py 均未包含在包内。正文按原文档保留命令接口（照实保留、未验证），若要真正运行需自行实现或另行获取对应脚本。

## 兼容浏览器（Playwright）

| 浏览器 | 类型 | 说明 |
|--------|------|------|
| **Google Chrome** | 系统安装 | 自动检测，优先使用 |
| **Microsoft Edge** | 系统安装 | 自动检测 |
| **Mozilla Firefox** | 系统安装 | 自动检测 |
| **Chromium** | Playwright 内置 | 兜底浏览器（无需系统安装） |

自动选择逻辑：**系统默认浏览器 > Chrome > Edge > Firefox > Chromium**。可通过环境变量指定：`set ZHIHU_BROWSER=firefox`。

## 运行环境

首次使用前需自建环境安装脚本（本包未收录）。安装过程应为：安装 `playwright` Python 包；下载 Chromium + Firefox；检测系统已安装的 Chrome / Edge / Firefox；创建所需目录。推荐使用装好 `playwright` + `chromium` 的 Python 3.10+ 环境。

## 工作原则

- 使用 Playwright 控制浏览器，模拟真实人工操作（随机延迟、逐字输入、鼠标移动）。
- 所有发布操作只到「保存草稿」为止，**绝不点击发布/提交按钮**。
- Cookie 优先从「知乎内容选题助手」共享的 Cookie 配置文件获取；不存在或过期时引导用户重新登录。
- 发布内容由用户提供（文件路径或直接文本），**不自行生成**。
- 操作过程中每一步截图反馈。

## 一、Cookie 管理

### 1.1 Cookie 获取优先级

1. **共享 Cookie**：读取同族「知乎内容选题助手」技能目录下 Cookie 配置文件的 `cookie` 字段
2. **自动提取**：运行 Cookie 管理脚本（`cookie_manager.py extract`，未随包提供）从 Chrome/Edge 浏览器配置文件中自动提取
3. **手动粘贴**：引导用户从浏览器 DevTools 复制 Cookie

### 1.2 检测与引导流程

执行发布操作前，必须检测 Cookie 是否有效（`check_login.py`，未随包提供）。

未登录或 Cookie 过期时：

1. 告诉用户：**「请先在 Chrome 或 Edge 浏览器中打开 https://www.zhihu.com 并扫码登录」**
2. 等待用户确认登录完成
3. 运行 Cookie 管理脚本的 extract 命令自动提取（`cookie_manager.py`，未随包提供）
4. 若自动提取失败，引导用户手动复制：

   > 1. 在知乎页面按 **F12** 打开开发者工具
   > 2. 点击 **Network（网络）** 标签
   > 3. 按 **F5** 刷新页面
   > 4. 点一个 `api.zhihu.com` 开头的请求
   > 5. 右侧 **Request Headers** → 找到 `Cookie:` 行
   > 6. 双击 Cookie 值 → **Ctrl+A** → **Ctrl+C**
   > 7. 把复制的 Cookie 发给我

5. 收到 Cookie 后用 Cookie 管理脚本保存（`cookie_manager.py save`，未随包提供）

### 1.3 Cookie 共享

保存成功后，可将 Cookie 同步到同族「知乎内容选题助手」技能目录下的 Cookie 配置文件（`cookie_manager.py share`，未随包提供）。

## 二、回答发布流程

**触发条件**：用户提供问题链接（如 `https://www.zhihu.com/question/1890153384096555048`）和回答内容。

执行步骤：

```
1. 确认 Cookie 有效（运行 check_login.py）
2. 用 Playwright 打开问题链接
3. 等待页面加载完成
4. ★ 检测是否存在「编辑回答」按钮 → 如果存在，说明该问题已回答过，返回提示并退出
5. 定位并点击「写回答」按钮
6. 等待编辑器加载
7. 将内容逐段粘贴到编辑器中（模拟人工输入节奏）
8. 点击「保存草稿」按钮
9. 确认草稿保存成功
10. 截图反馈给用户
11. 告诉用户："草稿已保存，请在浏览器中查看并决定是否发布"
```

**已回答检测**：发布前自动检测页面上是否存在「编辑回答」或「修改回答」按钮；存在则不再重复发布，返回：

```
[INFO] 该问题之前已写回答，无需重复发布。
  问题链接: https://www.zhihu.com/question/xxx
  请前往链接手动编辑已有回答。
```

**命令接口（照实保留、未验证；对应脚本未随包提供）**：

```bash
# python scripts/publish_answer.py --url "https://www.zhihu.com/question/<qid>" --content "path/to/answer.txt"
# python scripts/publish_answer.py --url "https://www.zhihu.com/question/<qid>" --text "这是回答内容..."
```

**人工模拟细节**：点击前鼠标先移动到按钮位置；输入时逐段粘贴，段落间随机停顿 1-3 秒；不会一次性全选粘贴（避免触发反爬）；遇弹窗/验证码时截图告知用户处理。

## 三、文章发布流程

**触发条件**：用户要求发布知乎文章，需提供标题和正文。

执行步骤：

```
1. 确认 Cookie 有效
2. 用 Playwright 打开 https://www.zhihu.com/
3. 确认页面已登录（检查头像/昵称元素）
4. 定位并点击「写文章」按钮
5. 等待文章编辑器加载
6. 在标题区域输入标题
7. 在正文区域逐段粘贴内容
8. 等待内容渲染完成
9. 点击「保存草稿」
10. 确认保存成功
11. 截图反馈
12. 告诉用户草稿已保存
```

**命令接口（照实保留、未验证；对应脚本未随包提供）**：

```bash
# python scripts/publish_article.py --title "文章标题" --content "path/to/article.txt"
```

## 四、互动与创作者管理

基于持久浏览器会话的语义动作，覆盖搜索、内容发现、互动与创作者数据分析。支持的操作动作：

`goto`、`search`、`find-questions`、`answer-question`、`scroll`、`extract`、`interaction-state`、`upvote`、`downvote`、`favorite`、`unfavorite`、`follow`、`share`、`comment`、`notification`、`wait`、`diagnose`。

### 操作规则

1. 重用同一浏览器会话和账号配置，避免重复登录。
2. 多步操作优先合并为一个执行计划（run-plan），而非逐条单独命令。
3. 使用语义动作（`upvote`/`favorite` 等），避免硬编码 CSS 选择器。
4. 严格区分结果状态：`done`（完成）、`staged`（已暂存）、`unconfirmed`（未确认）、`blocked`（被阻断）、`failed`（失败）。
5. 未确认的修改操作不得重试——先用 `interaction-state` 或全新页面检查确认是否已生效。
6. 已暂存的评论/回答/文章绝不声称「已提交」或「已发布」。
7. 保留生成的任务产物——其中包含用于调试的步骤记录和故障诊断信息。
8. `creator list` 返回的 `type:id` 键用于编辑/数据/删除操作，**禁止仅凭标题选择创作**。

### 创作者管理操作

| 操作 | 说明 |
|------|------|
| `creator list` | 列出所有创作（回答/想法/问题/文章/视频/播客/专栏/草稿），返回 `type:id` 键 |
| `creator stats` | 账号级或单篇创作数据，可选时间范围 |
| `creator edit` | 用修订版 Markdown 更新已有回答或文章；默认 stage，`--direct` 直更 |
| `creator delete` | 解析目标卡片 → 确认对话框 → 删除后验证目标消失；`--direct` 直删 |

### 搜索与 Markdown 出版

- **搜索与发现**：搜索关键词 → 结构化结果（含规范 URL、去重、元数据）；`find-questions` 发现合适回答的问题并做只读可回答性检查。
- **Markdown 回答/文章出版**：默认 `stage`（仅存草稿）；`--direct` 直发。文章支持 Front Matter 元数据：

```markdown
---
title: "文章标题"
topics: [人工智能, 软件工程]
comment_mode: open
---
```

- `--direct` 直发：确认到达规范 `zhuanlan.zhihu.com/p/` URL 且标题匹配才判定成功；`/edit` 结尾的 URL 永远不算已发布。

## 五、错误处理

| 错误 | 处理方式 |
|------|---------|
| Cookie 过期 / 未登录 | 引导用户重新登录，重新提取 Cookie |
| 找不到「写回答」按钮 | 截图发给用户确认页面状态 |
| 编辑器加载超时 | 等待最多 30 秒，超时后截图告知 |
| 保存草稿失败 | 检查是否有「草稿已保存」提示，截图告知 |
| 验证码 / 滑块 | 截图告知用户，等待用户手动处理后继续 |
| 弹窗遮挡 | 尝试关闭弹窗，失败则截图告知 |
| 网络超时 | 重试一次，仍失败则停止 |

## 六、安全原则

1. **只保存草稿，不发布** — 所有操作终点是「保存草稿」按钮。
2. **Cookie 仅本地存储** — 不上传到任何远程服务器。
3. **内容由用户提供** — 不自行生成或修改发布内容。
4. **操作过程全透明** — 每步截图反馈。
5. **合法合规** — 拒绝发布违法违规内容。
6. 不绕过平台登录、权限、风控或内容审核机制；不把本地文档/模板冒充成已执行的平台操作。

## 写与选题/发布联动（可选）

同族「知乎内容选题助手」（zhihu-topic-selection）数据库 `questions` 表的 `url` 字段可直接作为回答发布链接。

工作流：选题 → 本地写好回答 → 本技能自动保存到知乎草稿箱 → 登录知乎查看草稿决定是否发布。本技能自身不依赖该技能，仅作可选联动说明。

## 文件结构（脚本需自建）

```
zhihu-auto-publish/
├── SKILL.md
└── references/            # 预留补充材料目录
```

原实现脚本（`setup.py` / `cookie_manager.py` / `check_login.py` / `publish_answer.py` / `publish_article.py` / `browser_utils.py`）**未随包提供**，需按上文接口自行实现或另行获取；本技能不附带这些脚本。
