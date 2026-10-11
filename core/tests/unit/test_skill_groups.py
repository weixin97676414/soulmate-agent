"""技能四分类与"谁能用哪些技能"（对应 `core/src/my_agent/skill/groups.py`）。

## 这一批为什么必须有测试

它反转了一条**全局口径**：`enabled_skills` 从"白名单（空 = 全开）"变成
"增量勾选（空 = 只有内置技能）"，并且给专属技能加了归属限制。

这条链路上任何一处没同步（单聊 / 群聊 / 定时任务 / 提示词注入），
表现都是"某个搭子莫名其妙少了一批能力"，而那种问题没人能从界面上看出来 ——
所以下面这些断言就是它的"体检表"。
"""

from __future__ import annotations

from my_agent.skill import groups

# 一份够用的假注册表：`{技能名: source}`
_REGISTRY: dict[str, str] = {
    # 内置技能（每个搭子默认自带）
    "system_time": "builtin",
    "kb_search": "builtin",
    "self_growth": "builtin",
    # 通用技能（可自选）
    # ⚠️ 别用 browser_read 当这里的例子 —— 它 已转成内置技能
    "weather_query": "builtin",
    "excel_read": "builtin",
    "doc_to_pdf": "builtin",
    # 专属技能（搭子总管那批）
    "team_create_group": "builtin",
    "computer_type_text": "builtin",
    "update_assistant_profile": "builtin",
    "pmaster": "builtin",
    # 我的技能（用户上传 / AI 创建 / AI 下载）
    "my-uploaded": "custom",
    # MCP 外部工具（产品约定：归通用技能）
    "sample__echo": "mcp",
}


class TestBuckets:
    def test_四类判定(self):
        assert groups.bucket_of("system_time", "builtin") == groups.BUCKET_BUILTIN
        assert groups.bucket_of("weather_query", "builtin") == groups.BUCKET_COMMON
        assert groups.bucket_of("team_create_group", "builtin") == groups.BUCKET_EXCLUSIVE
        assert groups.bucket_of("computer_type_text", "builtin") == groups.BUCKET_EXCLUSIVE
        assert groups.bucket_of("my-uploaded", "custom") == groups.BUCKET_MINE
        assert groups.bucket_of("sample__echo", "mcp") == groups.BUCKET_COMMON

    def test_没登记过的内置技能算内置(self):
        """⚠️ 判定方向是"显式列通用、其余都算内置"。

        反过来（未登记算通用）会让新增技能悄悄变成"用户可以随手关掉的" ——
        而"关掉一个本该常开的能力"远比"多一个关不掉的开关"难发现。
        """
        assert groups.bucket_of("brand_new_skill", "builtin") == groups.BUCKET_BUILTIN

    def test_专属判定认前缀与精确名(self):
        assert groups.is_exclusive("team_whatever") is True
        assert groups.is_exclusive("computer_mouse_move") is True
        assert groups.is_exclusive("custom_skill_install") is True
        assert groups.is_exclusive("weather_query") is False


class TestAssembly:
    """搭子实际能用的技能集合。"""

    def test_内置搭子等于内置加自己的专属(self):
        allowed = groups.allowed_skill_names(
            _REGISTRY,
            assistant_id="BuddyManager",
            enabled_skills=["my-uploaded"],
            builtin_assistant=True,
        )
        assert "system_time" in allowed  # 内置
        assert "team_create_group" in allowed  # 自己的专属
        assert "computer_type_text" in allowed
        # ⚠️ 内置搭子**忽略** enabled_skills（那字段同时被 locked_builtins 锁住）
        assert "my-uploaded" not in allowed
        # 通用技能也不给 —— "内置搭子 = 专属技能 + 内置技能，且不能再添加任何技能"
        assert "weather_query" not in allowed

    def test_内置搭子拿不到别人的专属(self):
        allowed = groups.allowed_skill_names(
            _REGISTRY,
            assistant_id="soulmate",
            enabled_skills=None,
            builtin_assistant=True,
        )
        assert "team_create_group" not in allowed
        assert "system_time" in allowed

    def test_自定义搭子没勾就只有内置技能(self):
        allowed = groups.allowed_skill_names(
            _REGISTRY,
            assistant_id="custom-1",
            enabled_skills=None,
            builtin_assistant=False,
        )
        # ⚠️ 起还要并上「指导型常驻技能」那两条，理由见下面
        # `TestThirdRound::test_指导型常驻技能每个搭子自带`：它们与内置技能同级
        # （自带、关不掉），只是来源是数据而不是代码 —— 所以"没勾"的搭子同样有它们。
        assert allowed == {"system_time", "kb_search", "self_growth"} | set(
            groups.ALWAYS_ON_INSTRUCTION_NAMES
        )

    def test_自定义搭子勾了通用与我的就加上去(self):
        allowed = groups.allowed_skill_names(
            _REGISTRY,
            assistant_id="custom-1",
            enabled_skills=["weather_query", "my-uploaded"],
            builtin_assistant=False,
        )
        assert {"weather_query", "my-uploaded"} <= allowed

    def test_自定义搭子勾专属技能也拿不到(self):
        """专属技能**不能**靠勾选获得 —— 这就是"专属"两个字的全部意思。"""
        allowed = groups.allowed_skill_names(
            _REGISTRY,
            assistant_id="custom-1",
            enabled_skills=["team_create_group", "computer_type_text"],
            builtin_assistant=False,
        )
        assert "team_create_group" not in allowed
        assert "computer_type_text" not in allowed

    def test_指导型技能不在注册表里也要保留(self):
        """`kind == "instruction"` 的自定义技能**不注册成工具**（见 skill/custom.py），
        所以"勾了它"在注册表里查不到 —— 必须原样保留，
        否则它的正文永远不会注入（用户会以为"我装的技能没生效"）。
        """
        allowed = groups.allowed_skill_names(
            _REGISTRY,
            assistant_id="custom-1",
            enabled_skills=["some-instruction-skill"],
            builtin_assistant=False,
        )
        assert "some-instruction-skill" in allowed


class TestExclusive:
    def test_归属判定(self):
        assert groups.owners_of("team_create_group") == ("BuddyManager",)
        assert groups.may_use_exclusive("team_create_group", "BuddyManager") is True
        assert groups.may_use_exclusive("team_create_group", "soulmate") is False
        # 非专属技能谁都能用
        assert groups.may_use_exclusive("weather_query", "soulmate") is True

    def test_归属文案(self):
        # ⚠️ ：BuddyManager 的界面叫法从「搭子总管」改成英文「Buddy Manager」
        # （产品要求技能页显示"仅 Buddy Manager 可用"）。它**只影响技能页** ——
        # 操作被拒的提示走 `skill/locked.py::locked_message()`，那个按技能名给理由。
        assert groups.owner_label(("BuddyManager",)) == "Buddy Manager"
        assert groups.owner_label(("soulmate",)) == "Soulmate"

    def test_forbidden_合并了心鉴学与专属(self):
        blocked = groups.forbidden_names(_REGISTRY, "custom-1")
        assert "team_create_group" in blocked  # 搭子总管的专属
        assert "xjx_place_lookup" in blocked  # 心鉴学配套工具（非归属搭子）
        assert "system_time" not in blocked  # 普通技能不受影响

    def test_心鉴学的归属搭子不被挡(self):
        blocked = groups.forbidden_names(_REGISTRY, "RelationBuddy")
        assert "xjx_place_lookup" not in blocked
        assert "team_create_group" in blocked


class TestLocked:
    def test_内置与专属都关不掉(self):
        assert groups.is_locked("system_time", "builtin") is True
        assert groups.is_locked("team_create_group", "builtin") is True
        assert groups.is_locked("computer_type_text", "builtin") is True

    def test_通用技能可关(self):
        assert groups.is_locked("weather_query", "builtin") is False
        assert groups.is_locked("doc_to_pdf", "builtin") is False

    def test_本轮转内置的技能不再可关(self):
        """⚠️ 2026-10-07：用户逐条点名把 27 项从通用技能转成内置技能。

        这 27 项**必须**从 `COMMON_NAMES` 删掉、**同时**进 `LOCKED_BUILTIN_NAMES`。
        只做一半就会出现"bucket 说它是内置、界面却还给它画着开关"的中间态 ——
        用户以为那是可选项，关掉之后搭子的基础能力少一半，还找不到是谁关的。
        这里抽查四个域的边界；全量由 `TestRealRegistry` 兜。
        """
        for name in ("browser_read", "browser_snapshot", "calendar_create", "clipboard_write"):
            assert groups.bucket_of(name, "builtin") == groups.BUCKET_BUILTIN, name
            assert groups.is_locked(name, "builtin") is True, name
            assert name not in groups.COMMON_NAMES, name

    def test_mcp与自定义技能不受锁影响(self):
        # MCP 工具的权限由用户在 MCP 页自己管；自定义技能是用户建的，当然能删能关
        assert groups.is_locked("system_time", "mcp") is False
        assert groups.is_locked("my-uploaded", "custom") is False

    def test_没登记过的技能不算关不掉(self):
        """⚠️ "关不掉"必须**显式声明**（`LOCKED_BUILTIN_NAMES`）。

        否则一个忘了归类的新技能会莫名其妙变成"默认永久开启" ——
        用户既关不掉、也找不到原因，这是最难解释的一类问题。
        """
        assert groups.is_locked("brand_new_skill", "builtin") is False


class TestRealRegistry:
    """对着**真实注册表**再核一遍（上面那些用例用的是简化假表）。

    这三条盯的是"只有在真名单里才会暴露"的错：名字写错、以及漏登记。
    它们比逐条列举的断言可靠 —— 新增技能时不需要记得回来补一条。
    """

    @staticmethod
    def _registry() -> dict[str, str]:
        from my_agent.skill.builtin import discover_builtin_skills

        sources = {item.meta.name: item.meta.source for item in discover_builtin_skills()}
        # 这两个"安装类"技能不在 builtin 包里，由 runtime 单独注册 —— 补进来才是完整注册表
        sources["custom_skill_install"] = "builtin"
        sources["skill_package_install"] = "builtin"
        return sources

    def test_名单里没有写错的名字(self):
        """`COMMON_NAMES` / `EXCLUSIVE_EXACT` 里任何一个错别字，都会让那个**真技能**
        静默掉进「内置技能」（未登记一律算内置），于是它变成关不掉的 ——
        这条断言是那种错误唯一的拦截点。"""
        assert groups.validate_registry(self._registry()) == []

    def test_每个内置技能都真的关不掉(self):
        """反向漏检：某个内置技能若没被列进 `LOCKED_BUILTIN_NAMES`，
        界面就会给它画出关闭开关、而且真能关掉 —— 用户以为那是个可选项，
        结果搭子的基础能力被关掉一半，还找不到是谁关的。
        """
        sources = self._registry()
        unlocked = sorted(
            name
            for name, source in sources.items()
            if groups.bucket_of(name, source) == groups.BUCKET_BUILTIN
            and not groups.is_locked(name, source)
        )
        assert unlocked == []

    def test_每个专属技能都有归属(self):
        """没有归属的专属技能 = 谁都拿不到、也谁都拦不住（形同虚设）。"""
        sources = self._registry()
        orphan = sorted(
            name
            for name, source in sources.items()
            if groups.is_exclusive(name) and not groups.owners_of(name)
        )
        assert orphan == []

    def test_退役名单里的名字都真的不能再被勾选(self):
        """⚠️ `RETIRED_COMMON_NAMES` 写错一个字的后果**极其隐蔽**：
        它被用在"保存搭子时静默剔除"上 —— 若把某个**仍是通用**的技能名写进去，
        用户正常勾选的那个技能会在下次保存时被悄悄删掉，不报错、界面上也看不出，
        他只会发现"我勾的那个怎么没了"。这条断言是它唯一的拦截点。

        ⚠️ 2026-10-07 起名单里有**三种**来源，"不能再被勾选"各自成立但**判据不同**，
        所以分档校验（原来一律断言"是专属"，对新增的常驻那两条不成立）：
        - 代码里注册的自带技能（`pmaster` / `dbskill`）→ 在工具注册表里、是专属、有归属；
        - 指导型专属（8 个）→ **不在**注册表里，但 `is_exclusive` 为真、有归属；
        - 指导型常驻（2 个）→ **不在**注册表里、也不是专属，而是「内置」（`bucket_of`）。
        """
        sources = self._registry()
        for name in groups.RETIRED_COMMON_NAMES:
            if name in groups.ALWAYS_ON_INSTRUCTION_NAMES:
                assert groups.bucket_of(name, "custom", "办公") == groups.BUCKET_BUILTIN, name
                continue
            assert groups.is_exclusive(name) is True, name
            assert groups.owners_of(name), name
            if name not in groups.INSTRUCTION_EXCLUSIVE_OWNERS:
                # 代码注册的那两个：必须在注册表里（"名单里有不存在的技能"是另一种错）
                assert name in sources, f"{name} 不是真实技能"


class TestSecondRound:
    """2026-10-07 用户逐条点名的**第二版**划分（动静比第一版大得多）。

    这一版把 27 项从通用技能转成内置技能、2 项转成 BuddyManager 专属。
    下面钉的是"清单本身"；"每一类都自洽"由 `TestRealRegistry` 兜。
    """

    #: 本轮从「通用技能」→「内置技能」（用户原话里的 27 项）
    PROMOTED: tuple[str, ...] = (
        "calendar_create",
        "calendar_update",
        "calendar_list",
        "calendar_delete",
        "report_generate",
        "svg_create",
        "reminder_create",
        "reminder_list",
        "reminder_cancel",
        "browser_read",
        "browser_act",
        "browser_screenshot",
        "browser_snapshot",
        "browser_tabs",
        "clipboard_read_text",
        "clipboard_read_image",
        "clipboard_write",
        "scheduled_task_create",
        "scheduled_task_delete",
        "scheduled_task_list",
        "scheduled_task_run",
        "scheduled_task_update",
        "system_screenshot",
        "excerpo",
        "grill_me",
        "skill_creator",
        "chart_generate",
    )

    #: 本轮从「通用技能」→「BuddyManager 专属」（用户原话里的 2 项）
    EXCLUSIVATED: tuple[str, ...] = ("pmaster", "dbskill")

    def test_27项都已是内置且关不掉(self):
        assert len(self.PROMOTED) == 27
        for name in self.PROMOTED:
            assert groups.bucket_of(name, "builtin") == groups.BUCKET_BUILTIN, name
            assert groups.is_locked(name, "builtin") is True, name
            assert name not in groups.COMMON_NAMES, name

    def test_2项已转专属且归搭子总管(self):
        for name in self.EXCLUSIVATED:
            assert groups.is_exclusive(name) is True, name
            assert groups.owners_of(name) == ("BuddyManager",), name
            assert groups.bucket_of(name, "builtin") == groups.BUCKET_EXCLUSIVE, name
            assert name not in groups.COMMON_NAMES, name

    def test_退役名单是两轮加起来的那批(self):
        """`RETIRED_COMMON_NAMES` = "曾经通用、现在失效"（**累积**，不是只记最近一轮）。

        它**只**服务于"保存老档案时静默剔除"，所以它的成员必须恰好是"历史上转出去
        的那些名字" —— 多一个会误删用户的正常勾选，少一个会让老档案保存报错。

        ⚠️ 2026-10-07 扩到两轮：第一轮是代码技能那 2 个（`EXCLUSIVATED`），
        第二轮是指导型技能的 8 个专属 + 2 个常驻（下面 `TestThirdRound`）。
        """
        assert set(groups.RETIRED_COMMON_NAMES) == (
            set(self.EXCLUSIVATED)
            | set(groups.INSTRUCTION_EXCLUSIVE_OWNERS)
            | set(groups.ALWAYS_ON_INSTRUCTION_NAMES)
        )

    def test_通用技能名单没有被清空(self):
        """⚠️ 这条防的是"越改越狠"：如果哪天有人图省事把 COMMON_NAMES 清空，
        所有技能都会变成关不掉的内置技能 —— 用户再也挑不了任何能力，
        而界面上只会表现为"通用技能那一栏空了"，看不出是事故。"""
        assert len(groups.COMMON_NAMES) == 20

    def test_mcp工具不受本轮影响(self):
        """明确：MCP 是"用户自己连进来的"，保持通用（可自选）。

        ⚠️ MCP 的归类走 `bucket_of` 里 `source == "mcp"` 那条分支，**不看名单** ——
        所以这条断言同时钉住"没人在名单里偷偷塞 MCP 工具名"。
        """
        assert groups.bucket_of("sqlite__query", "mcp") == groups.BUCKET_COMMON
        assert groups.bucket_of("sqlite__list_tables", "mcp") == groups.BUCKET_COMMON
        assert not any("__" in name for name in groups.COMMON_NAMES)


class TestThirdRound:
    """2026-10-07 用户逐条点名的**第三版**划分：指导型技能的分类。

    这一版最特殊的地方：要动的 10 个是 `skill/custom.py` 管的**指导型技能**
    （`kind == "instruction"`），它们**不注册进 `SkillManager` 工具注册表** ——
    所以"改成专属 / 内置"不能靠调整工具分类，只能新加两份名单 + 在
    `allowed_skill_names` 里显式处理。下面钉的就是这套机制。
    """

    #: 本轮从「通用技能」→「BuddyManager 专属」（用户原话里的 8 项）
    EXCLUSIVATED: tuple[str, ...] = (
        "brand-strategy",
        "event-planning",
        "funnel-analysis",
        "marketing-playbooks",
        "ab-test-setup",
        "marketing-ideas",
        "pricing-strategy",
        "referral-program",
    )

    #: 本轮从「通用技能」→「内置技能」（用户原话里的 2 项）
    PROMOTED: tuple[str, ...] = ("sensitive-data-precheck", "copy-editing")

    def test_名单就是用户点名的那10个(self):
        """名单本身。⚠️ 写错一个字的后果是"那个技能静静地待错分类"，
        界面上只表现为"它怎么还在通用栏"，查起来毫无线索。"""
        assert set(groups.INSTRUCTION_EXCLUSIVE_OWNERS) == set(self.EXCLUSIVATED)
        assert set(groups.ALWAYS_ON_INSTRUCTION_NAMES) == set(self.PROMOTED)

    def test_8项已是专属且归搭子总管(self):
        for name in self.EXCLUSIVATED:
            assert groups.is_exclusive(name) is True, name
            assert groups.owners_of(name) == ("BuddyManager",), name
            # ⚠️ source 故意传 `"custom"`：指导型技能在运行期就是这个 source，
            # 而 `bucket_of` 里 `source == "custom"` 那条分支**本来会把它判成通用** ——
            # 这条断言真正钉住的是"新加的短路排在了那条分支前面"。
            assert groups.bucket_of(name, "custom", "营销") == groups.BUCKET_EXCLUSIVE, name

    def test_2项已是内置(self):
        for name in self.PROMOTED:
            assert groups.bucket_of(name, "custom", "办公") == groups.BUCKET_BUILTIN, name

    def test_专属的归属隔离(self):
        """只有 BuddyManager 拿得到 —— 而且**不是**"能勾但不能用"，是压根不出现在集合里。"""
        for name in self.EXCLUSIVATED:
            assert groups.may_use_exclusive(name, "BuddyManager") is True, name
            assert groups.may_use_exclusive(name, "soulmate") is False, name

        bm = groups.allowed_skill_names(
            _REGISTRY,
            assistant_id="BuddyManager",
            enabled_skills=None,
            builtin_assistant=True,
        )
        assert set(self.EXCLUSIVATED) <= bm

        other = groups.allowed_skill_names(
            _REGISTRY,
            assistant_id="soulmate",
            enabled_skills=None,
            builtin_assistant=True,
        )
        assert not (set(self.EXCLUSIVATED) & other)

    def test_自定义搭子硬塞专属也拿不到(self):
        """⚠️ 这条防的是一个**真实漏洞口**：指导型技能不在工具注册表里，
        于是 `allowed_skill_names` 里那段"注册表查不到 ⇒ 当作我的技能、直接保留"
        的逻辑会**绕过归属判定** —— 一句"我勾了它"就能拿到别人的专属技能。"""
        allowed = groups.allowed_skill_names(
            _REGISTRY,
            assistant_id="soulmate",
            enabled_skills=list(self.EXCLUSIVATED),
            builtin_assistant=False,
        )
        assert not (set(self.EXCLUSIVATED) & allowed)

    def test_指导型常驻技能每个搭子自带(self):
        """用户原话是"改成内置技能"，而内置技能的口径是**每个搭子创建时自带、关不掉**。

        ⚠️ 这里三种搭子都要验：内置搭子、别的内置搭子、用户自建的 ——
        少验一种，"常驻"就可能退化成"只有某类搭子有"（那正是把并集写进某个分支的后果）。
        """
        assert set(self.PROMOTED) <= groups.allowed_skill_names(
            _REGISTRY, assistant_id="BuddyManager", enabled_skills=None, builtin_assistant=True
        )
        assert set(self.PROMOTED) <= groups.allowed_skill_names(
            _REGISTRY, assistant_id="soulmate", enabled_skills=None, builtin_assistant=True
        )
        # 自定义搭子：**一个技能都不勾**也必须有
        assert set(self.PROMOTED) <= groups.allowed_skill_names(
            _REGISTRY, assistant_id="custom-1", enabled_skills=[], builtin_assistant=False
        )

    def test_这10个都关不掉(self):
        """`is_locked`（按 source 判）对指导型技能**永远为假**，所以"关不掉"必须走
        `is_locked_instruction` —— 接口那边拒绝关闭就是用它判的。"""
        for name in self.EXCLUSIVATED + self.PROMOTED:
            assert groups.is_locked_instruction(name) is True, name
        assert groups.is_locked_instruction("weather_query") is False

    def test_新名单没被validate_registry扫到(self):
        """⚠️ 这条是"为什么必须新开两份常量"的原因本身。

        `validate_registry` 只扫 `COMMON_NAMES` 与 `EXCLUSIVE_EXACT`、拿它们跟
        **工具注册表**比对 —— 指导型技能不在注册表里，一旦被塞进那两个集合，
        启动日志会刷满"名单里有不存在的技能"的假告警。
        """
        missing = groups.validate_registry({"_不存在的占位技能"})
        assert "brand-strategy" not in missing
        assert "copy-editing" not in missing

    def test_不误伤名字相近的技能(self):
        """⚠️ 素材库里有几个名字很像的（`ecom-pricing-strategy`「定价策略」、
        `ecom-promotion-enrollment`「平台活动报名助手」、`activity-campaign-page`
        「活动 H5 页面策划」）—— 它们**没有**被点名，必须留在通用技能里。"""
        for name in ("ecom-pricing-strategy", "ecom-promotion-enrollment", "activity-campaign-page"):
            assert groups.bucket_of(name, "custom", "电商") == groups.BUCKET_COMMON, name
            assert groups.is_exclusive(name) is False, name
