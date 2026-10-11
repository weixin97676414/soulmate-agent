"""技能包**落盘**：把成员写到数据目录的 ``skills/<技能 id>/``。

## 为什么要落盘，而不是只把正文读进内存

技能包常常不止一份说明：还有参考文档、模板、示例数据、脚本 —— 说明里会写
"按 <包目录>/templates/report.md 的格式来"。只把正文注入 system，
等于告诉模型"照这个模板做"却把模板扔了，模型只能凭空编 —— 表现成"技能不听话"，
而用户看着界面上明明写着技能已安装。

所以：**整包原样落盘**，再把落盘后的绝对路径与文件清单一起注入，模型才拿得到
那些辅助文件（模型能读文件，但得先知道文件在哪）。

## 一个包出多个技能时，各自只落自己那一份

``SkillRoot`` 记着"这个技能在包里占哪棵子树"（``only_root``）或"只要哪几个文件"
（``only_files``）。老实现是**每条定义都把整包重落一遍** —— 一个包含三个技能的包
会落三份完整副本，而且各技能看到的是同一堆文件，说明里写的相对路径全对不上。
现在按范围落，各技能目录里就是它自己那份。

## 两个必须做的事

1. **剥掉公共根目录**：在 ``archive.py`` 取成员时就做了（那是容器层的事）。
   这里只按 ``only_root`` 再剥一层该技能的子树前缀。
2. **拒绝路径穿越**：成员名在 ``archive.py`` 已过 ``safe_relative``；
   这里在拼接后再校验一次（拼接后必须仍在 ``dest`` 之内），是最后一道闸。

## 文件清单不截断

清单超过 :data:`MAX_LISTING` 时，注入 system 的列表只列前 40 条，但**完整清单**
会写在包目录的 ``_pack_index.md`` 里，注入文本同时给出那个文件的位置。
这样既不把 system 撑成文件清单，也没有任何文件被静默省略。
"""

from __future__ import annotations

import logging
import shutil
from pathlib import Path
from typing import Any

from .archive import Member, iter_members

logger = logging.getLogger(__name__)

# 注入 system 时最多列多少个文件。列全了固然好，但一个几百文件的包会把
# system 撑成文件清单 —— 超出的部分指向 **_pack_index.md**（无损，不丢文件）。
MAX_LISTING = 40

# 落盘时写的"全量文件清单"文件名。以 ``_`` 开头，与用户自己的文件区分开。
INDEX_FILE = "_pack_index.md"


def _human(size: int) -> str:
    if size < 1024:
        return f"{size}B"
    if size < 1024 * 1024:
        return f"{size / 1024:.1f}KB"
    return f"{size / 1024 / 1024:.1f}MB"


def _clear(dest: Path) -> None:
    """清空目标目录，保证"重装 = 干净的一份"。

    不清的话，重装同名技能时会看到上一版独有的残留文件（覆盖只覆盖同名文件），
    说明里提到的文件可能来自上一个版本 —— 最难查的一类问题。
    """
    if not dest.is_dir():
        return
    for item in dest.iterdir():
        if item.is_dir():
            shutil.rmtree(item, ignore_errors=True)
        else:
            try:
                item.unlink()
            except OSError as exc:  # 删不掉就留着，但要说出来
                logger.warning("技能包旧文件删除失败：%s（%s）", item, exc)


def _collapse(name: str, used: set[str]) -> str:
    """把"只要这一个文件"的目标路径摊平到包根（``a/b/rules.mdc`` → ``rules.mdc``）。

    同名的第二个文件才退回完整相对路径 —— 摊平是为了让模型在包目录里一眼看到
    那几个脚本与说明，而不是隔着三层无关目录。
    """
    base = name.rsplit("/", 1)[-1]
    if base and base not in used:
        return base
    return name


def write_index(dest: Path, entries: list[tuple[str, int]], *, source: str = "") -> None:
    """写 ``_pack_index.md``：**全量**文件清单（相对路径 + 大小）。

    这是"不截断"的落地方式：注入 system 的清单有 40 条上限，
    但完整清单永远在包目录里，模型按需读它就能看到全部文件。
    """
    lines = ["# 技能包文件清单", ""]
    if source:
        lines.append(f"来源：{source}")
    lines.append(f"共 {len(entries)} 个文件。")
    lines.append("")
    lines.extend(f"- {name}（{_human(size)}）" for name, size in entries)
    try:
        (dest / INDEX_FILE).write_text("\n".join(lines) + "\n", encoding="utf-8")
    except OSError as exc:
        logger.warning("技能包清单写入失败：%s（%s）", dest, exc)


def extract_members(
    members: list[Member],
    dest: Path,
    *,
    only_root: str = "",
    only_files: tuple[str, ...] | list[str] = (),
    source: str = "",
) -> dict[str, Any]:
    """把 ``members`` 里**属于这个技能的**文件写到 ``dest``（先清空）。

    - ``only_files`` 非空 → 只写这几个文件（规则文件、脚本），摊平到包根；
    - ``only_root`` 非空 → 只写这棵子树，并剥掉该前缀；
    - 两者都空 → 写全部成员（包根就是技能根）。

    返回 ``{"count", "files", "root", "skipped"}``。``count`` **不含** ``_pack_index.md``
    —— 它是我们自己的元文件，不该混进"这个技能有几个文件"的数字里。
    """
    dest.mkdir(parents=True, exist_ok=True)
    _clear(dest)

    wanted: list[tuple[str, bytes]] = []
    wanted_files = set(only_files)
    for name, data in members:
        if wanted_files:
            if name in wanted_files:
                wanted.append((name, data))
            continue
        if only_root:
            if name == only_root:
                continue
            if not name.startswith(f"{only_root}/"):
                continue
            wanted.append((name[len(only_root) + 1 :], data))
            continue
        wanted.append((name, data))

    used: set[str] = set()
    written: list[tuple[str, int]] = []
    skipped: list[str] = []
    root_path = dest.resolve()
    for name, data in wanted:
        relative = _collapse(name, used) if wanted_files else name
        if not relative:
            continue
        target = dest / relative
        # 二次校验：拼接后必须仍在 dest 之内（怪字符、符号链接的最后一道闸）
        try:
            target.resolve().relative_to(root_path)
        except ValueError:
            skipped.append(name)
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        try:
            target.write_bytes(data)
        except OSError as exc:  # 单条写不进去不该毁掉整包
            logger.warning("技能包条目写入失败：%s（%s）", name, exc)
            skipped.append(name)
            continue
        used.add(relative)
        written.append((relative, len(data)))

    write_index(dest, written, source=source)
    if skipped:
        logger.info("技能包解包跳过 %d 个条目（路径不安全或写入失败）", len(skipped))
    return {
        "count": len(written),
        "files": sorted(name for name, _ in written),
        "root": only_root,
        "skipped": skipped,
    }


def extract_package(
    payload: bytes,
    dest: Path,
    *,
    filename: str = "package.zip",
    only_root: str = "",
    only_files: tuple[str, ...] | list[str] = (),
) -> dict[str, Any]:
    """zip / tar.gz / 单文件 → 落盘（``extract_members`` 的便捷包装）。

    保留这个入口是为了老调用点（模型从链接装包、上传路由）不必各自枚举成员 ——
    "取成员"这件事只有 ``archive.py`` 一份实现。
    """
    packed = iter_members(payload, filename)
    return extract_members(
        packed.members, dest, only_root=only_root, only_files=only_files, source=packed.container
    )


def packaged_files(dest: Path) -> list[str]:
    """列出某个已落盘技能包的文件（相对路径，排序，**不含**清单文件本身）。

    注入 system 与自检都用它；目录不存在（这个技能不是包形式装的）返回空列表。
    """
    if not dest.is_dir():
        return []
    return sorted(
        item.relative_to(dest).as_posix()
        for item in dest.rglob("*")
        if item.is_file() and item.name != INDEX_FILE
    )


def listing_hint(dest: Path, *, limit: int = MAX_LISTING) -> str:
    """给模型看的"包里有哪些文件"；没落盘过返回空串。

    超过 ``limit`` 时不截断信息 —— 只少列几行，并**明确指向**
    ``_pack_index.md``（完整清单就在那儿）。

    ``limit`` 由调用方定：正文**整份注入**时值得多列几行（模型手上有全文，
    照着清单找文件即可）；正文走**按需读取**时列少一些 —— 那条路径下模型无论如何
    都要先读 ``SKILL.md``，而说明里会点名它需要哪几个文件，清单列四十条只是白占
    提示词（实测：勾 254 个技能时，仅清单一项就占了 18 万字里的三分之一）。
    """
    files = packaged_files(dest)
    if not files:
        return ""
    shown = files[: max(1, limit)]
    lines = []
    for name in shown:
        try:
            size = (dest / name).stat().st_size
        except OSError:
            size = 0
        lines.append(f"- {name}（{_human(size)}）")
    if len(files) > len(shown):
        lines.append(
            f"- …另有 {len(files) - len(shown)} 个文件，完整清单见 "
            f"{dest / INDEX_FILE}（该文件列出全部 {len(files)} 个文件）"
        )
    return "\n".join(lines)


__all__ = [
    "INDEX_FILE",
    "MAX_LISTING",
    "extract_members",
    "extract_package",
    "listing_hint",
    "packaged_files",
    "write_index",
]
