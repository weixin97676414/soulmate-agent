















from __future__ import annotations

from my_agent.skill import groups


_REGISTRY: dict[str, str] = {
    
    "system_time": "builtin",
    "kb_search": "builtin",
    "self_growth": "builtin",
    
    
    "weather_query": "builtin",
    "excel_read": "builtin",
    "doc_to_pdf": "builtin",
    
    "team_create_group": "builtin",
    "computer_type_text": "builtin",
    "update_assistant_profile": "builtin",
    "pmaster": "builtin",
    
    "my-uploaded": "custom",
    
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





        assert groups.bucket_of("brand_new_skill", "builtin") == groups.BUCKET_BUILTIN

    def test_专属判定认前缀与精确名(self):
        assert groups.is_exclusive("team_whatever") is True
        assert groups.is_exclusive("computer_mouse_move") is True
        assert groups.is_exclusive("custom_skill_install") is True
        assert groups.is_exclusive("weather_query") is False


class TestAssembly:


    def test_内置搭子等于内置加自己的专属加勾选的(self):






        allowed = groups.allowed_skill_names(
            _REGISTRY,
            assistant_id="BuddyManager",
            enabled_skills=["my-uploaded", "weather_query"],
            builtin_assistant=True,
        )
        assert "system_time" in allowed  
        assert "team_create_group" in allowed  
        assert "computer_type_text" in allowed
        
        assert "weather_query" in allowed
        assert "my-uploaded" in allowed

    def test_内置搭子不勾就还是只有内置加专属(self):


        allowed = groups.allowed_skill_names(
            _REGISTRY,
            assistant_id="BuddyManager",
            enabled_skills=[],
            builtin_assistant=True,
        )
        assert "system_time" in allowed
        assert "team_create_group" in allowed
        assert "weather_query" not in allowed
        assert "my-uploaded" not in allowed

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

        allowed = groups.allowed_skill_names(
            _REGISTRY,
            assistant_id="custom-1",
            enabled_skills=["team_create_group", "computer_type_text"],
            builtin_assistant=False,
        )
        assert "team_create_group" not in allowed
        assert "computer_type_text" not in allowed

    def test_指导型技能不在注册表里也要保留(self):




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
        
        assert groups.may_use_exclusive("weather_query", "soulmate") is True

    def test_归属文案(self):
        
        
        
        assert groups.owner_label(("BuddyManager",)) == "Buddy Manager"
        assert groups.owner_label(("soulmate",)) == "Soulmate"

    def test_forbidden_合并了心鉴学与专属(self):
        blocked = groups.forbidden_names(_REGISTRY, "custom-1")
        assert "team_create_group" in blocked  
        assert "xjx_place_lookup" in blocked  
        assert "system_time" not in blocked  

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







        for name in ("browser_read", "browser_snapshot", "calendar_create", "clipboard_write"):
            assert groups.bucket_of(name, "builtin") == groups.BUCKET_BUILTIN, name
            assert groups.is_locked(name, "builtin") is True, name
            assert name not in groups.COMMON_NAMES, name

    def test_mcp与自定义技能不受锁影响(self):
        
        assert groups.is_locked("system_time", "mcp") is False
        assert groups.is_locked("my-uploaded", "custom") is False

    def test_没登记过的技能不算关不掉(self):





        assert groups.is_locked("brand_new_skill", "builtin") is False


class TestRealRegistry:






    @staticmethod
    def _registry() -> dict[str, str]:
        from my_agent.skill.builtin import discover_builtin_skills

        sources = {item.meta.name: item.meta.source for item in discover_builtin_skills()}
        
        sources["custom_skill_install"] = "builtin"
        sources["skill_package_install"] = "builtin"
        return sources

    def test_名单里没有写错的名字(self):



        assert groups.validate_registry(self._registry()) == []

    def test_每个内置技能都真的关不掉(self):




        sources = self._registry()
        unlocked = sorted(
            name
            for name, source in sources.items()
            if groups.bucket_of(name, source) == groups.BUCKET_BUILTIN
            and not groups.is_locked(name, source)
        )
        assert unlocked == []

    def test_每个专属技能都有归属(self):

        sources = self._registry()
        orphan = sorted(
            name
            for name, source in sources.items()
            if groups.is_exclusive(name) and not groups.owners_of(name)
        )
        assert orphan == []

    def test_退役名单里的名字都真的不能再被勾选(self):











        sources = self._registry()
        for name in groups.RETIRED_COMMON_NAMES:
            if name in groups.ALWAYS_ON_INSTRUCTION_NAMES:
                assert groups.bucket_of(name, "custom", "办公") == groups.BUCKET_BUILTIN, name
                continue
            assert groups.is_exclusive(name) is True, name
            assert groups.owners_of(name), name
            if name not in groups.INSTRUCTION_EXCLUSIVE_OWNERS:
                
                assert name in sources, f"{name} 不是真实技能"


class TestSecondRound:






    
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








        assert set(groups.RETIRED_COMMON_NAMES) == (
            set(self.EXCLUSIVATED)
            | set(groups.INSTRUCTION_EXCLUSIVE_OWNERS)
            | set(groups.ALWAYS_ON_INSTRUCTION_NAMES)
        )

    def test_通用技能名单没有被清空(self):



        assert len(groups.COMMON_NAMES) == 20

    def test_mcp工具不受本轮影响(self):





        assert groups.bucket_of("sqlite__query", "mcp") == groups.BUCKET_COMMON
        assert groups.bucket_of("sqlite__list_tables", "mcp") == groups.BUCKET_COMMON
        assert not any("__" in name for name in groups.COMMON_NAMES)


class TestThirdRound:








    
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

    
    PROMOTED: tuple[str, ...] = ("sensitive-data-precheck", "copy-editing")

    def test_名单就是用户点名的那10个(self):


        assert set(groups.INSTRUCTION_EXCLUSIVE_OWNERS) == set(self.EXCLUSIVATED)
        assert set(groups.ALWAYS_ON_INSTRUCTION_NAMES) == set(self.PROMOTED)

    def test_8项已是专属且归搭子总管(self):
        for name in self.EXCLUSIVATED:
            assert groups.is_exclusive(name) is True, name
            assert groups.owners_of(name) == ("BuddyManager",), name
            
            
            
            assert groups.bucket_of(name, "custom", "营销") == groups.BUCKET_EXCLUSIVE, name

    def test_2项已是内置(self):
        for name in self.PROMOTED:
            assert groups.bucket_of(name, "custom", "办公") == groups.BUCKET_BUILTIN, name

    def test_专属的归属隔离(self):

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



        allowed = groups.allowed_skill_names(
            _REGISTRY,
            assistant_id="soulmate",
            enabled_skills=list(self.EXCLUSIVATED),
            builtin_assistant=False,
        )
        assert not (set(self.EXCLUSIVATED) & allowed)

    def test_指导型常驻技能每个搭子自带(self):





        assert set(self.PROMOTED) <= groups.allowed_skill_names(
            _REGISTRY, assistant_id="BuddyManager", enabled_skills=None, builtin_assistant=True
        )
        assert set(self.PROMOTED) <= groups.allowed_skill_names(
            _REGISTRY, assistant_id="soulmate", enabled_skills=None, builtin_assistant=True
        )
        
        assert set(self.PROMOTED) <= groups.allowed_skill_names(
            _REGISTRY, assistant_id="custom-1", enabled_skills=[], builtin_assistant=False
        )

    def test_这10个都关不掉(self):


        for name in self.EXCLUSIVATED + self.PROMOTED:
            assert groups.is_locked_instruction(name) is True, name
        assert groups.is_locked_instruction("weather_query") is False

    def test_新名单没被validate_registry扫到(self):






        missing = groups.validate_registry({"_不存在的占位技能"})
        assert "brand-strategy" not in missing
        assert "copy-editing" not in missing

    def test_不误伤名字相近的技能(self):



        for name in ("ecom-pricing-strategy", "ecom-promotion-enrollment", "activity-campaign-page"):
            assert groups.bucket_of(name, "custom", "电商") == groups.BUCKET_COMMON, name
            assert groups.is_exclusive(name) is False, name
