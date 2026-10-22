# 环境安装与排障

## 最小依赖

Python 3.10+（转换器与搜索包装脚本仅使用标准库）；OpenCLI；桌面 Chrome/Chromium；
Browser Bridge 扩展；用户本人在同一个浏览器 profile 中登录小红书。
Agent 必须能运行本机进程，并访问 OpenCLI 的本机桥接服务。

先检查 `python3 --version`（Windows 可用 `py -3 --version`）、`node --version`、
`opencli --version`、`opencli doctor`、`opencli xiaohongshu search --help`。
命令缺失时按用户授权和当前宿主安装规则补齐；不要覆写已有的可用安装。

## 安装 OpenCLI 与扩展

1. 按 [OpenCLI 官方仓库](https://github.com/jackwener/opencli#quick-start) 选择桌面应用或 npm。
   CLI 安装命令是 `npm install -g @jackwener/opencli`。
   npm 方式先用 `npm view @jackwener/opencli engines --json` 核对所选版本的 Node 要求。
   文档与安装包要求不一致时，以所选版本 package.json 的 engines 为准。
2. 从官方 README 链接进入 Chrome 商店安装 Browser Bridge；或从
   [官方 Releases](https://github.com/jackwener/opencli/releases) 下载对应扩展 ZIP。
   手动安装时解压，打开 `chrome://extensions`，启用开发者模式，选择“加载已解压的扩展程序”。
   必须选择含 `manifest.json` 的根目录。文件选择器不显示隐藏目录时，可使用普通可见目录。
3. 保持该浏览器运行，用户本人打开小红书并登录。无需读取、导出、复制 Cookie 或 profile。
4. 再运行 `opencli doctor`。需要进一步诊断且本版本支持时运行 `opencli daemon status`。
   多个 profile 已连接时先看 `opencli profile list`，按用户指定的账号选择；不要猜选另一个账号。
   可给当前进程设置 `OPENCLI_PROFILE`，不必改变全局默认。
5. 用用户实际想查的关键词做一次低频、少量搜索。只有拿到真实站内结果才标记搜索可用。

[Browser Bridge 官方说明](https://opencli.info/docs/guide/browser-bridge.html)描述浏览器与本机 daemon 的连接方式。
无需另装 OpenCLI 的其他 skill；本 skill 已包含此任务所需步骤。

## Windows、WSL 与远程 agent

- Windows：运行 `py -3 scripts/search.py --query '咖啡机 清洁' --limit 5`。
  默认 npm 的 `opencli.cmd` 会由包装脚本解析为相邻安装包的 JS 入口，再用 node 执行；
  不通过 `cmd.exe` / `shell=True` 执行含用户查询的命令。
- 非标准 Windows 安装：通过 `npm root -g` 找到已安装包的目录，核对
  `@jackwener/opencli/package.json` 的 `bin.opencli`，然后指定：

  ```powershell
  py -3 scripts/search.py --opencli-js 'C:\actual\node_modules\@jackwener\opencli\dist\src\main.js' --query '露营 防雨' --limit 5
  ```

  替换为真实路径，不下载陌生 JS 来凑该参数。路径带空格时仍应作为单个参数。
- WSL/容器/远程机器：宿主浏览器和 agent 不一定共享 loopback。
  不将 `localhost` 可达性从一个环境推断到另一个。没有已配置可达桥接时先报告环境缺口；
  不自动开放公网端口、迁移浏览器登录态或安装另一套抓取后端。
- 沙箱：如果宿主 daemon/extension 已连接，但 agent 内报 `Operation not permitted` 或
  `Daemon: not running`，先核对 agent 对本机桥接的访问权限；不同执行环境的可达性可能不同。
  若宿主支持批准该固定搜索命令访问本机桥接，使用其正常机制；不关闭整体沙箱或审批。

## 失败分类

| 现象 | 下一步 |
|---|---|
| `opencli` 不存在 | 检查 agent 进程 PATH 与安装位置；终端可运行不保证桌面 agent 继承同一 PATH |
| extension disconnected / exit 69 | 核对浏览器仍运行、扩展启用、正确 profile、agent 与 daemon 同环境 |
| login required / exit 77 | 让用户在所选浏览器登录，再按需要重试一次 |
| 验证码、请求过频、安全限制 | 停止自动重试，用户处理或稍后再试 |
| timeout / exit 75 | 先检查浏览器与网络；包装脚本默认 120 秒，总上限 300 秒，不自动重试 |
| empty / exit 66 | 该查询无可用结果；若无登录/风控迹象，可换同义词或缩短查询 |
| schema / URL rejected | 对照 links.md 和本机版本输出；不删校验来强行生成链接 |
| 分享链接打不开 | 可能 token 过期、笔记删除或受限；按标题查找，必要时重新搜索取得当次链接 |
| 登录页中文方框 | 字体缺在实际运行浏览器的宿主；不要只在另一个容器装字体 |

退出码按当前 [OpenCLI 源码说明](https://github.com/jackwener/opencli#exit-codes)核对；
旧版本可能只返回通用非零退出。包装脚本对未知非零码报失败，不冒充无结果。
排障时不要把包含原始页面、token、Cookie 的调试日志整份贴入对话或仓库。
