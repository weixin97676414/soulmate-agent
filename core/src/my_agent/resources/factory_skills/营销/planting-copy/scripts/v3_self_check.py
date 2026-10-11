#!/usr/bin/env python3
from pathlib import Path
import re, sys

root = Path(__file__).resolve().parents[1]
required = [
    'SKILL.md',
    'references/seeding_conversion_operating_system.md',
    'references/authentic_scene_engine.md',
    'references/platform_and_private_domain_playbook.md',
    'references/comment_dm_conversion_engine.md',
    'references/emotion_audience_trust_engine.md',
    'references/compliance.md',
    'references/quality_gate.md',
    'references/winner-framework-upgrade.md'
]
missing = [p for p in required if not (root / p).exists()]
if missing:
    print('MISSING:', missing)
    sys.exit(1)

skill = (root / 'SKILL.md').read_text(encoding='utf-8')
if not skill.startswith('---'):
    print('SKILL.md missing YAML frontmatter')
    sys.exit(1)
fm = skill.split('---', 2)[1]
if 'name: planting-conversion-copywriter' not in fm:
    print('frontmatter name mismatch')
    sys.exit(1)
forbidden = ['display_name:', 'compatibility:', '升级报告', '对比报告', '归档', '施工痕迹']
bad = [x for x in forbidden if x in skill]
if bad:
    print('FORBIDDEN TERMS:', bad)
    sys.exit(1)
must = ['任务路由', '100分质检', '一票否决', '72小时']
lack = [x for x in must if x not in skill]
if lack:
    print('MISSING CORE TERMS:', lack)
    sys.exit(1)
print('PASS')
