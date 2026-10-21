




















from __future__ import annotations

import errno
import os
import sys
from typing import Iterable


def _classify(e: BaseException) -> tuple[str, str, list[str]]:

    msg = str(e) or type(e).__name__

    
    if isinstance(e, FileNotFoundError):
        return ("找不到文件", f"路径不存在或拼写有误：{msg}", [
            "检查文件路径是否正确（注意中文 / 空格 / 反斜杠）",
            "确认文件是否被移动、删除或改名",
            "若是相对路径，确认是否在正确的工作目录下",
        ])
    if isinstance(e, IsADirectoryError):
        return ("路径指向的是文件夹", f"你可能传了一个目录：{msg}", [
            "确认传入的是具体文件路径，不是目录",
            "如要批量处理目录，请列出文件后逐个传入",
        ])
    if isinstance(e, PermissionError):
        return ("权限不足或文件被占用", f"无法读取/写入：{msg}", [
            "关闭正在打开此文件的软件（Word / PDF 阅读器 / 编辑器等）",
            "确认文件不是「只读」状态（右键 → 属性 → 取消勾选「只读」）",
            "如对系统目录操作，以管理员身份运行",
        ])
    
    if isinstance(e, OSError) and getattr(e, "errno", None) is not None:
        err = e.errno
        if err == errno.ENOSPC:  
            return ("磁盘空间不足", f"无法写入文件：{msg}", [
                "清理磁盘后再试（清理大文件 / 回收站 / 临时文件夹）",
                "更换输出路径到剩余空间更大的盘",
                "如生成 PDF 大，可先用 HTML 版（更轻）",
            ])
        if err == errno.ENAMETOOLONG:  
            return ("文件名或路径太长", f"系统无法处理：{msg}", [
                "把报告文件移近根目录（如 D:\\reports\\），减少路径层级",
                "用英文或拼音重命名文件，避免长中文名",
            ])
        if err == errno.EACCES:
            return ("权限被拒绝", f"操作系统拒绝访问：{msg}", [
                "关闭占用此文件的程序",
                "以管理员身份运行命令",
            ])

    
    if isinstance(e, ModuleNotFoundError) or isinstance(e, ImportError):
        mod = getattr(e, "name", "") or msg
        return ("缺少依赖库", f"本机没装 {mod}：{msg}", [
            "脚本会主动询问是否从官方源安装，确认即可",
            "如拒绝安装，手动执行脚本打印的 pip 命令",
            "非交互环境（CI / 批处理）需预装或加 --yes 显式授权",
        ])

    
    if isinstance(e, UnicodeDecodeError):
        return ("文件编码不是 UTF-8", f"读到第 {e.start} 字节时无法识别：{msg}", [
            "把 .md / .txt 文件另存为 UTF-8 编码（记事本 → 另存为 → 编码选 UTF-8）",
            "如是从 Office 复制来的内容，先粘贴到记事本再去掉格式",
        ])
    if isinstance(e, UnicodeEncodeError):
        return ("输出编码异常", f"无法写出字符：{msg}", [
            "确认终端 / PowerShell 支持 UTF-8（Windows 可执行 chcp 65001）",
            "避免在文件名 / 内容里用生僻 emoji 或特殊字符",
        ])

    
    if isinstance(e, KeyError):
        return ("报告内容缺少必要字段", f"找不到键 {msg!r}", [
            "确认 Markdown 报告按本技能模板的标题层级编写（## 一级节 / ### 二级节）",
            "8 维评分表头需含「维度 / 得分 / 说明」三列",
            "运行 python scripts/verify_report_structure.py <报告.md> 看具体缺什么",
        ])
    if isinstance(e, IndexError):
        return ("报告表格行列对不上", f"读取位置 {msg}", [
            "表格每行单元格数要一致（用 | 分隔），分隔行用 |---|",
            "运行 verify_report_structure.py 定位出错行号",
        ])
    if isinstance(e, AttributeError):
        return ("脚本版本与数据不匹配", f"属性不存在：{msg}", [
            "确认使用的 Python 与本技能要求的 venv 一致",
            "升级脚本（git pull 或重新安装技能）后再试",
        ])
    if isinstance(e, ValueError):
        return ("参数或内容值不合法", f"{msg}", [
            "检查传入的命令行参数是否完整（路径含空格要加引号）",
            "Markdown 表格 / 列表是否闭合完整",
        ])
    if isinstance(e, TypeError):
        return ("类型不匹配", f"{msg}", [
            "多半是脚本 bug，请保存完整报错信息并反馈给作者",
        ])

    
    if isinstance(e, TimeoutError) or "timeout" in msg.lower():
        return ("网络超时", f"等待响应超时：{msg}", [
            "检查网络连接是否正常",
            "稍等几秒后重试",
            "如长时间不稳，把要分析的视频文件直接发给我更稳",
        ])
    if isinstance(e, ConnectionError) or "connection" in msg.lower():
        return ("网络连接失败", f"{msg}", [
            "检查网络 / 防火墙 / 代理设置",
            "稍后重试；如持续失败，发本地文件降级处理",
        ])

    
    if isinstance(e, MemoryError):
        return ("内存不足", f"机器内存不够：{msg}", [
            "关闭其他占内存的程序（浏览器多标签、大表格软件）",
            "把超长报告拆成多份",
            "如频繁出现，考虑升级硬件或换更小的 ASR 模型（tiny / base）",
        ])
    if isinstance(e, RecursionError):
        return ("数据嵌套过深", f"递归深度超限：{msg}", [
            "检查 Markdown 是否含异常嵌套（标题层级跳级等）",
            "如反复出现，简化报告结构后重试",
        ])

    
    if "zip" in type(e).__name__.lower() or "bad zip" in msg.lower():
        return ("ZIP / DOCX 文件损坏", f"{msg}", [
            "重新生成源文件（不要中途打断 / 关闭）",
            "如文件来自网络，重新下载",
        ])

    
    if isinstance(e, AssertionError) and ("font" in msg.lower() or "cjk" in msg.lower()):
        return ("未找到中文字体", f"渲染 PDF 时找不到可用中文字体：{msg}", [
            "Windows 用户确认 C:\\Windows\\Fonts 下有 msyh.ttc / simhei.ttf",
            "如字体被精简过，恢复微软雅黑或安装一个开源中文字体",
            "实在没有，PDF 中文字符会显示为方框（不影响正文，但建议补字体）",
        ])

    
    return ("脚本执行出错", f"{type(e).__name__}: {msg}", [
        "先重试一次（偶发网络 / 文件锁）",
        "把这段报错贴给作者，能直接定位问题",
        "若使用第三方 .md，注意标题层级（## / ###）是否规范",
    ])


def humanize(e: BaseException, context: str, *,
             hints: Iterable[str] | None = None,
             show_tech: bool = True) -> str:











    title, cause, default_hints = _classify(e)
    final_hints = list(hints) if hints else default_hints
    lines = [
        f"❌ {context} · {title}",
        f"   原因：{cause}",
    ]
    if final_hints:
        lines.append("   💡 怎么办：")
        for h in final_hints:
            lines.append(f"     · {h}")
    if show_tech:
        tech = f"{type(e).__name__}: {str(e) or '(无附加信息)'}"
        if len(tech) > 240:
            tech = tech[:237] + "..."
        lines.append(f"   [tech] {tech}")
    return "\n".join(lines)


def print_error(e: BaseException, context: str, *,
                hints: Iterable[str] | None = None,
                show_tech: bool = True) -> None:

    sys.stderr.write(humanize(e, context, hints=hints, show_tech=show_tech) + "\n")
    sys.stderr.flush()



EXIT_OK = 0
EXIT_USER = 2        
EXIT_PERMISSION = 3  
EXIT_DEP = 4         
EXIT_INTERNAL = 1    


def suggest_exit_code(e: BaseException) -> int:

    if isinstance(e, (FileNotFoundError, IsADirectoryError, ValueError, UnicodeDecodeError)):
        return EXIT_USER
    if isinstance(e, (PermissionError, OSError)):
        return EXIT_PERMISSION
    if isinstance(e, (ModuleNotFoundError, ImportError)):
        return EXIT_DEP
    return EXIT_INTERNAL