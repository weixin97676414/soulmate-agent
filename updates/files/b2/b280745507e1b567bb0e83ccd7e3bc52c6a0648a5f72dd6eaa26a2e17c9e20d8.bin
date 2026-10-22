---
name: law-retrieval
description: 法条与案例检索：官方 API 优先、本地库兜底的法规与案例查询，附检索结果与风险提示。触发场景：要「查法条/搜法律/法律咨询」，或描述纠纷需要相关法条与参考案例。
author: Soulmate Agent团队成员：岸
---

# 法条与案例检索

## 适用场景

- 用户要「查一下法条」「这个条款出自哪部法律」「搜一下法律」「法律咨询」。
- 用户描述民事纠纷、劳动争议、合同问题、借贷、侵权，需要相关法条与参考案例。
- 用户问「这种行为是否合法 / 一般怎么判」。

## 步骤

1. **确定检索目标**：区分「查法条」还是「查案例」，提炼关键词（可组合，如「违约金 合同解除」「未签劳动合同」）。
2. **在线优先检索（官方 API）**：调用国家法律法规数据库官方接口（无密钥）：
   - 地址：`https://flk.npc.gov.cn/api/`
   - 方式：GET；核心参数 `type=flfg`、`searchType=title;vague`、`keyword=<关键词>`、`page=1`、`size=5`
   - 返回 200 且含有效数据 → 解析并展示法条；否则进入本地兜底。
3. **本地兜底检索**：
   - 法条库 `scripts/legal_hybrid/law_db.json`（键值对：法条名 → 全文，如「民法典183」）；
   - 案例库 `scripts/legal_hybrid/case_db.json`（数组，含 title / keywords / fact / judgement / laws），按标题、关键词、案情、判决多维度匹配。
4. **离线全文检索（可选，覆盖面更广）**：用 `search_law.py` 在已收录法律中全文搜索：

```bash
python3 scripts/legalkb/search_law.py "违约金 合同解除" --max 5
python3 scripts/legalkb/search_law.py --list
```

   首次使用需先把法律仓库 clone 到本地（脚本支持 `--repo <路径>` / `--local <目录>`），默认数据源为 GitHub 上的法律文本仓库；无网络/无仓库时该脚本不可用。
5. **检索本地文档兜底**（合同 PDF/DOCX 等）：

```bash
python3 scripts/legalkb/list_files.py <目录>
python3 scripts/legalkb/search_kb.py <目录> <关键词>
python3 scripts/legalkb/read_pdf.py <文件> [页码]
python3 scripts/legalkb/read_docx.py <文件>
```

6. **格式化输出**：按「法条 + 参考案例」分类展示；条款标注具体编号（第 XXX 条），注明来源；结果按法律分类分组。无结果时明确告知覆盖范围，并建议用 `web_search` 补充。

调用本功能的程序化入口（`Skill.run(query)`）：

```python
# scripts/legal_hybrid/main.py 提供 Skill 类
from scripts.legal_hybrid.main import Skill
print(Skill().run("未签劳动合同"))
```

（需 `pip install requests`；`scripts/legal_hybrid/requirements.txt` 已随附。**未实测运行**，以实际输出为准。）

## 输入输出

- 输入：关键词或自然语言法律问题（事件起因、经过、诉求）。
- 输出：相似案件（优先在线）+ 相关法条 + 风险提示与免责声明。

## 注意事项

- API 超时默认 8 秒（`main.py` 中 `self.timeout`），网络较差时可调整；关键词过泛（如只填「劳动合同」）易无结果，建议更具体。
- 本地库是可维护的：法条库为 JSON 键值对，案例库为 JSON 数组，可按格式增删条目以提升匹配度（案例需字段完整、关键词准确）。
- legalkb 的脚本依赖外部法律仓库/本地文件，**并非开箱即用**；无仓库时以在线 API 与本地 JSON 兜底为准。
- 检索结果须核对时效（是否修订/废止），优先适用最新版本，注意过渡期规定；引用时注明版本与施行日期。
- 输出仅供初步参考，不构成正式法律意见。

## 可复用示例

用户：「试用期无故被辞退，赔偿怎么算？相关法条有哪些？」
处理：提炼关键词「试用期 辞退 补偿」→ 在线 API 查法条 → 本地 case_db 匹配「试用期无故辞退」案例 → 输出《劳动合同法》相关条文 + 参考案例（公司违法解除应支付赔偿金）+ 风险提示。

用户：「查一下民法典关于高空抛物的条文。」
处理：关键词「高空抛物」→ API 检索 → 命中则展示条文；否则本地 `law_db.json` 兜底 → 标注来源。

## 关联资产

- `scripts/legal_hybrid/main.py`、`law_db.json`、`case_db.json`、`requirements.txt`
- `scripts/legalkb/search_law.py`、`search_kb.py`、`list_files.py`、`read_pdf.py`、`read_docx.py`
