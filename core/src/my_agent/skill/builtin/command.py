































from __future__ import annotations

import asyncio
import locale
import os
import time
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from ...errors import SkillExecutionError
from ...skill.base import BaseSkill, SkillContext
from ...skill.decorator import skill







MAX_CAPTURE_BYTES = 8 * 1024 * 1024


DEFAULT_TIMEOUT = 60


def _decode(raw: bytes) -> str:






    for encoding in ("utf-8", locale.getpreferredencoding(False), "gbk"):
        if not encoding:
            continue
        try:
            return raw.decode(encoding)
        except (UnicodeDecodeError, LookupError):
            continue
    return raw.decode("utf-8", errors="replace")


def _clip(raw: bytes) -> tuple[bytes, bool]:

    if len(raw) <= MAX_CAPTURE_BYTES:
        return raw, False
    half = MAX_CAPTURE_BYTES // 2
    
    mark = "\n...[中间省略]...\n".encode()
    return raw[:half] + mark + raw[-half:], True


class RunCommandParams(BaseModel):
    command: str = Field(
        ...,
        min_length=1,
        description=(
            "要执行的完整命令行（整条，含参数）。Windows 下走 cmd.exe，"
            "Linux/macOS 下走 sh。多步操作用 `&&` 串起来，不要分多次调用。"
        ),
    )
    cwd: str = Field(
        "",
        description=(
            "工作目录（绝对路径）。留空 = 用户主目录。"
            "必须在文件访问白名单内，否则会被拒绝。"
        ),
    )
    timeout: int = Field(
        DEFAULT_TIMEOUT,
        ge=1,
        le=600,
        description=(
            "超时秒数（默认 60，最长 600）。超时后进程会被杀掉并如实报告 —— "
            "长时间任务（编译整个项目、跑训练）请让用户在自己的终端里跑。"
        ),
    )


@skill(
    name="buddy_run_command",
    display_name="执行命令行",
    description=(
        "在用户电脑上执行**一条**命令行指令，返回退出码、stdout 与 stderr。\n"
        "用途：跑构建 / 测试、看 git 状态、装依赖、批量处理文件、调用外部 CLI。\n"
        "\n"
        "⚠️ 这是**高危操作**：每次都会弹确认框，用户点头才真的执行，"
        "而且**不能被「记住这个技能」放行**（高危操作不该变成橡皮图章）。\n"
        "\n"
        "什么时候用：用户明确说「帮我跑一下 / 执行这条命令 / 装个依赖」；"
        "或者你要核实一件只有命令行才能查清的事（`git status`、`node -v`）。\n"
        "什么时候**不要**用：\n"
        "- 用户只是问「这个怎么弄」—— 给他命令让他自己跑，别替他执行；\n"
        "- 你不确定这条命令会不会删东西 / 改系统 —— 先问清楚再调；\n"
        "- 要跑十几分钟的长任务 —— 告诉他用自己的终端，这里会超时被杀。\n"
        "\n"
        "调用前必须把**完整命令**原样告诉用户（他会看到确认框里的命令），"
        "不要藏着参数。"
    ),
    params_model=RunCommandParams,
    category="system",
    permission_level="confirm",
    tags=["搭子团队", "命令行"],
)
class BuddyRunCommandSkill(BaseSkill):
    async def run(self, ctx: SkillContext, **params: Any) -> dict[str, Any]:
        args = RunCommandParams(**params)
        command = args.command.strip()
        if not command:
            raise SkillExecutionError("命令不能为空。")

        
        if args.cwd.strip():
            try:
                cwd: Path = ctx.resolve_path(args.cwd.strip(), mode="read")
            except Exception as exc:  
                raise SkillExecutionError(f"工作目录不可用：{exc}") from exc
            if not cwd.is_dir():
                raise SkillExecutionError(f"工作目录不是一个目录：{cwd}")
        else:
            cwd = Path.home()

        started = time.monotonic()
        timed_out = False
        try:
            proc = await asyncio.create_subprocess_shell(
                command,
                cwd=str(cwd),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                
                
                **(
                    {"creationflags": 0x00000200}  
                    if os.name == "nt"
                    else {}
                ),
            )
        except (OSError, ValueError) as exc:
            raise SkillExecutionError(f"命令启动失败：{exc}") from exc

        try:
            out_raw, err_raw = await asyncio.wait_for(
                proc.communicate(), timeout=args.timeout
            )
        except TimeoutError:
            timed_out = True
            await self._kill_tree(proc)
            out_raw, err_raw = b"", b""
        duration_ms = round((time.monotonic() - started) * 1000, 2)

        out_raw, out_clipped = _clip(out_raw or b"")
        err_raw, err_clipped = _clip(err_raw or b"")
        exit_code = proc.returncode if proc.returncode is not None else -1

        result: dict[str, Any] = {
            "command": command,
            "cwd": str(cwd),
            "exit_code": exit_code,
            "stdout": _decode(out_raw),
            "stderr": _decode(err_raw),
            "duration_ms": duration_ms,
            "timed_out": timed_out,
        }
        if timed_out:
            result["message"] = (
                f"命令超过 {args.timeout} 秒未结束，已被强制终止。"
                "长时间任务请让用户在自己的终端里跑。"
            )
        elif exit_code != 0:
            result["message"] = f"命令执行完毕但退出码是 {exit_code}，请看 stderr。"
        else:
            result["message"] = "命令执行成功。"
        if out_clipped or err_clipped:
            result["output_clipped"] = True
            result["message"] += (
                f"（输出超过 {MAX_CAPTURE_BYTES // (1024 * 1024)} MB，已只保留头尾）"
            )
        return result

    @staticmethod
    async def _kill_tree(proc: Any) -> None:





        if os.name == "nt":
            try:
                killer = await asyncio.create_subprocess_shell(
                    f"taskkill /F /T /PID {proc.pid}",
                    stdout=asyncio.subprocess.DEVNULL,
                    stderr=asyncio.subprocess.DEVNULL,
                )
                await asyncio.wait_for(killer.wait(), timeout=10)
            except Exception:  
                pass
        try:
            proc.kill()
        except ProcessLookupError:
            pass
        try:
            await asyncio.wait_for(proc.wait(), timeout=10)
        except (TimeoutError, ProcessLookupError):
            pass
