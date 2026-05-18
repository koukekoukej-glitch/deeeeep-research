# -*- coding: utf-8 -*-
"""报告格式验证器。检查报告 + sources.json 是否符合 viewer 格式契约。

用法：py validate_report.py reports/xxx.md
退出码 0 = 通过（可能含警告），1 = 有错误（错误信息打到 stdout）
"""

import io
import json
import re
import sys
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

REQUIRED_META_FIELDS = {"来源数量", "截至日期"}
OPTIONAL_META_FIELDS = {"grounding 强度"}  # phase 3.5 落地后的报告可带、旧报告省略
REQUIRED_SOURCE_KEYS = {"num", "title", "url", "date", "authority_tier", "evidence_quote"}
VALID_TIERS = {"T1", "T2", "T3"}

# claims.json 10 字段（phase 3.5 grounding 输出）
REQUIRED_CLAIM_KEYS = {
    "claim_id", "claim_text", "claim_type", "source_ids", "grounding_strength",
    "as_of_date", "status", "verification_notes", "degrade_action", "degrade_phrasing",
}
VALID_CLAIM_TYPES = {
    "valuation", "date", "person", "company_relation", "quote", "url", "ymyl_conclusion",
}
VALID_GROUNDING_STRENGTH = {"single-source", "multi-source", "unsupported"}
VALID_DEGRADE_ACTIONS = {"hard_fail", "soft_degrade", "mark_unverified", "drop"}
VALID_CLAIM_STATUS = {"confirmed", "rumored", "estimated", "outdated"}

# user_profile.json 8 字段（phase 1 输出）
REQUIRED_PROFILE_KEYS = {
    "user_role", "user_expertise_level", "decision_context", "key_concerns",
    "known_terms", "unfamiliar_terms", "constraints", "avoid_topics",
}
VALID_EXPERTISE_LEVELS = {"unfamiliar", "basic", "proficient", "expert"}

# report_thesis.json 6 字段（phase 3 末尾 / phase 4 之前输出）
REQUIRED_THESIS_KEYS = {
    "punchline", "key_judgments", "key_assumptions", "thesis_chain",
    "decision_action", "fallback_pivot",
}

# 描述性章节标题黑名单（精确匹配 → 错误）
# 见 phase4 文档「写作纪律」段「章节标题论点化」一节。
DESCRIPTIVE_TITLES = {
    "市场分析", "竞争格局", "用户画像", "行业现状", "未来趋势",
    "发展现状", "总体概述", "主要挑战", "应对策略", "核心要点",
    "关键发现", "研究背景", "问题描述", "解决方案", "建议措施",
    "总结展望", "概览", "现状", "趋势", "展望",
    "总结", "综述", "讨论", "分析", "概述",
}

# AI 文风黑名单（命中 → 警告，不阻断通过）
# 见 phase4 文档「写作纪律」段「AI 文风黑名单」一节。
AI_WORDS_ZH = [
    # 程式化收尾
    "值得注意的是", "综上所述", "由此可见", "总而言之", "显而易见",
    # 浮夸词
    "不容忽视", "举足轻重", "至关重要", "独树一帜", "日新月异",
    "百花齐放", "如火如荼",
    # 商业空话
    "深度赋能", "保驾护航", "全面提升", "显著提升",
    # 含糊归因
    "行业报告显示", "有观察人士认为", "相关人士透露", "业内分析人士",
]
AI_WORDS_EN = [
    "Additionally", "delve", "intricate", "pivotal", "tapestry", "testament",
    "underscore", "vibrant", "fostering", "highlighting", "showcasing",
    "boasts", "nestled", "profound", "groundbreaking", "renowned",
]
AI_PATTERNS = [
    (r"不仅[^，。\n]{1,20}，而且", "否定式平行：'不仅 X，而且 Y'"),
    (r"不只是[^，。\n]{1,20}，更是", "否定式平行：'不只是 X，更是 Y'"),
    (r"Not just .{1,30}, but also", "否定式平行：'Not just X, but also Y'"),
    (r"尽管[^，。\n]{1,30}，但", "'尽管 X 但 Y' 模板收尾"),
]

# 语言纯度模式（命中 → 警告，不阻断通过）
# 见 phase4 文档「写作纪律」段「语言纯度（硬约束）」一节。
# 选取的是高置信、误伤少的中英混搭模式——人工自检仍是主负责。
LANGUAGE_PURITY_PATTERNS = [
    # 固定中英混搭短语（高置信）
    (r"\bsub-?agents?\b", "sub-agent / subagent → 子代理"),
    (r"\bcontext\s+(?:engineering|rot|window|management|anxiety)\b",
     "context [engineering/rot/window/management/anxiety] → 上下文 [工程/腐烂/窗口/管理/焦虑]"),
    (r"\bcache\s+(?:miss(?:es)?|hits?)\b", "cache [miss/hit] → 缓存 [失效/命中]"),
    (r"cache\s+(?:命中|利用率|失效)", "cache + 中文 → 缓存 + 中文"),
    (r"\bsystem\s+prompts?\b", "system prompt → 系统提示词"),
    (r"\bfeedback\s+loops?\b", "feedback loop → 反馈循环"),
    (r"\bouter\s+loops?\b", "outer loop → 外层循环"),
    (r"\breasoning\s+traces?\b", "reasoning trace → 推理轨迹"),
    (r"\bfeature\s+flags?\b", "feature flag → 特性开关"),
    (r"\bcontext-centric\b", "context-centric → 以上下文为中心"),
    (r"\blost-in-the-middle\b", "lost-in-the-middle → 中段遗忘"),
    # 独立英文单词（中置信 - 可能误伤、命中后人工确认）
    (r"(?<![-\w])workflows?(?![\w.])", "workflow → 工作流"),
    (r"(?<![-\w])playbooks?(?![\w])", "playbook → 操作手册"),
    (r"(?<![-\w])compaction(?![\w])", "compaction → 压缩"),
    (r"(?<![-\w])verifications?(?![\w])", "verification → 验证"),
    (r"(?<![-\w])verifiers?(?![\w])", "verifier → 验证器"),
    (r"(?<![-\w])sandbox(?:es|ing)?(?![\w])", "sandbox → 沙箱"),
    (r"(?<![-\w])checkpoints?(?![\w])", "checkpoint → 检查点"),
    (r"(?<![-\w.])benchmarks?(?![-\w])", "benchmark → 基准测试（SWE-bench 等专名豁免）"),
]


def validate(md_path: str) -> tuple[list[str], list[str]]:
    errors = []
    warnings = []
    p = Path(md_path)

    if not p.exists():
        return [f"文件不存在：{p}"], warnings

    text = p.read_text(encoding="utf-8")
    lines = text.splitlines()

    # --- 1. H1 检查 ---
    h1s = [i for i, l in enumerate(lines) if re.match(r"^# ", l)]
    if len(h1s) == 0:
        errors.append("缺少 H1 标题")
    elif len(h1s) > 1:
        errors.append(f"有多个 H1 标题（行 {', '.join(str(i+1) for i in h1s)}）")

    # --- 2. metadata 字段检查（只提取 H1 之后、第一个 H2 之前的 > 行）---
    meta_lines = []
    meta_raw_lines = []
    past_h1 = False
    for l in lines:
        if not past_h1:
            if re.match(r"^# ", l):
                past_h1 = True
            continue
        if re.match(r"^## ", l):
            break
        if l.startswith(">"):
            meta_raw_lines.append(l)
            content = l[1:].strip() if len(l) > 1 else ""
            if content:
                meta_lines.append(content)

    # 检查两个字段之间是否有空 > 行分隔
    if len(meta_lines) >= 2 and ">" not in [l.strip() for l in meta_raw_lines]:
        errors.append("metadata 两个字段之间缺少空 > 行分隔（来源数量和截至日期之间需要一个空的 > 行）")
    found_fields = set()
    for ml in meta_lines:
        m = re.match(r"^(.+?)[:：]", ml)
        if m:
            found_fields.add(m.group(1).strip())
    missing = REQUIRED_META_FIELDS - found_fields
    extra = found_fields - REQUIRED_META_FIELDS - OPTIONAL_META_FIELDS
    if missing:
        errors.append(f"metadata 缺少必需字段：{', '.join(missing)}")
    if extra:
        allowed = REQUIRED_META_FIELDS | OPTIONAL_META_FIELDS
        errors.append(f"metadata 包含非规定字段：{', '.join(extra)}（只允许 {', '.join(sorted(allowed))}）")

    # --- 3. TL;DR 检查 ---
    h2s = [(i, l) for i, l in enumerate(lines) if re.match(r"^## ", l)]
    if h2s:
        first_h2_text = h2s[0][1].strip().replace("## ", "")
        if first_h2_text != "TL;DR":
            errors.append(f"第一个 H2 应为 'TL;DR'，实际是 '{first_h2_text}'（行 {h2s[0][0]+1}）")
    else:
        errors.append("缺少 H2 章节")

    # --- 4. 手工编号检查 ---
    for i, l in enumerate(lines):
        if re.match(r"^#{2,4}\s+[§一二三四五六七八九十\d]+[.、．]", l):
            errors.append(f"H2/H3/H4 包含手工编号（行 {i+1}：{l.strip()[:40]}）")

    # --- 4b. 描述性章节标题检查（BCG Action Title）---
    for i, l in enumerate(lines):
        m = re.match(r"^(#{2,4})\s+(.+?)\s*$", l)
        if m and m.group(2).strip() in DESCRIPTIVE_TITLES:
            errors.append(
                f"描述性章节标题（行 {i+1}）：'{m.group(2).strip()}'"
                f"——章节标题必须论点化（BCG Action Title），不是话题标签。"
                f"详见 phase4 文档「写作纪律」段「章节标题论点化」一节"
            )

    # --- 5. 引用角标格式检查 ---
    bad_cites = []
    for i, l in enumerate(lines):
        if l.startswith("> ") or l.startswith("```"):
            continue
        if re.search(r"\[\d+[,，、]\s*\d+", l):
            bad_cites.append(i + 1)
        if re.search(r"\[\d+-\d+\]", l):
            bad_cites.append(i + 1)
    if bad_cites:
        errors.append(f"角标格式错误（逗号/连字符连写），行：{bad_cites[:5]}")

    # --- 6. 裸 URL 检查 ---
    # `## 引用来源` 段本身就是为了提供裸 URL 让 raw md 用户能跳转，跳过该段。
    url_re = re.compile(r"(?<!\(|`)https?://\S+|(?<!\(|`)\b\w+\.\w+\.\w+/\S*")
    bare_urls = []
    in_code = False
    in_ref_section = False
    for i, l in enumerate(lines):
        if re.match(r"^##\s+引用来源\s*$", l):
            in_ref_section = True
            continue
        if l.strip().startswith("```"):
            in_code = not in_code
            continue
        if in_code or in_ref_section or l.startswith("> "):
            continue
        if url_re.search(l):
            bare_urls.append(i + 1)
    if bare_urls:
        errors.append(f"正文包含裸 URL，行：{bare_urls[:5]}")

    # --- 6b. 末尾自我标识行检查 ---
    tail = [l.strip() for l in lines[-5:] if l.strip()]
    for t in tail:
        if re.match(r"^[（(].{5,}[）)]$", t):
            errors.append(f"文档末尾有自我标识括号行：{t[:50]}")

    # --- 7. 提取正文 [N] 编号集合 ---
    cite_nums = set()
    in_code2 = False
    for l in lines:
        if l.strip().startswith("```"):
            in_code2 = not in_code2
            continue
        if in_code2 or l.startswith("> "):
            continue
        for m in re.finditer(r"\[(\d+)\]", l):
            cite_nums.add(int(m.group(1)))

    # --- 7b. markdown 自带 `## 引用来源` 段检查 ---
    # raw md 脱离 viewer 也要自洽：所有角标必须能在文末段查到。
    ref_section_start = None
    for i, l in enumerate(lines):
        if re.match(r"^##\s+引用来源\s*$", l):
            ref_section_start = i
            break

    ref_section_nums = set()
    if ref_section_start is not None:
        for l in lines[ref_section_start + 1:]:
            if re.match(r"^##\s+", l):
                break
            for m in re.finditer(r"\[(\d+)\]", l):
                ref_section_nums.add(int(m.group(1)))

    body_cite_nums = cite_nums - ref_section_nums
    if body_cite_nums:
        if ref_section_start is None:
            errors.append(
                f"正文有 {len(body_cite_nums)} 个 [N] 角标但 markdown 末尾缺少 `## 引用来源` 段——"
                f"脱离 viewer 看 raw md 时所有角标会悬空。请按 phase4 文档「Viewer 格式契约」第 6 条补上"
            )
        else:
            in_cite_not_ref = body_cite_nums - ref_section_nums
            in_ref_not_cite = ref_section_nums - body_cite_nums
            if in_cite_not_ref:
                errors.append(f"正文有角标但 `## 引用来源` 段没列出：{sorted(in_cite_not_ref)}")
            if in_ref_not_cite:
                errors.append(f"`## 引用来源` 段列了但正文没引用：{sorted(in_ref_not_cite)}")

    # --- 8. sources.json 检查 ---
    src_path = p.with_name(p.stem + ".sources.json")
    if not src_path.exists():
        errors.append(f"缺少 sources.json：{src_path.name}")
    else:
        try:
            raw = json.loads(src_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            errors.append(f"sources.json JSON 解析失败：{e}")
            return errors, warnings

        if isinstance(raw, list):
            errors.append("sources.json 是裸数组，应为 {\"sources\": [...]}")
            sources = raw
        elif isinstance(raw, dict):
            sources = raw.get("sources", [])
            if not isinstance(sources, list):
                errors.append("sources.json 的 sources 字段不是数组")
                return errors, warnings
        else:
            errors.append("sources.json 格式无法识别")
            return errors, warnings

        src_nums = set()
        for idx, s in enumerate(sources):
            num = s.get("num")
            if num is not None:
                src_nums.add(int(num))
            missing_keys = REQUIRED_SOURCE_KEYS - set(s.keys())
            if missing_keys:
                errors.append(f"sources[{idx}]（num={num}）缺少字段：{', '.join(missing_keys)}")
            tier = s.get("authority_tier", "")
            if tier and tier not in VALID_TIERS:
                errors.append(f"sources[{idx}]（num={num}）authority_tier 值无效：{tier}")

        # 一致性比对
        in_report_not_sources = cite_nums - src_nums
        in_sources_not_report = src_nums - cite_nums
        if in_report_not_sources:
            errors.append(f"报告有角标但 sources.json 没有：{sorted(in_report_not_sources)}")
        if in_sources_not_report:
            errors.append(f"sources.json 有条目但报告没引用：{sorted(in_sources_not_report)}")

    # --- 10. AI 文风黑名单检查（软警告，不阻断通过）---
    # 跳过 `## 引用来源` 段（来源标题里出现 AI 词不算 LLM 写作问题，是源数据）。
    ai_hits = {}
    in_code3 = False
    in_ref_section3 = False
    for i, l in enumerate(lines):
        if re.match(r"^##\s+引用来源\s*$", l):
            in_ref_section3 = True
            continue
        if l.strip().startswith("```"):
            in_code3 = not in_code3
            continue
        if in_code3 or in_ref_section3 or l.startswith(">"):
            continue
        for word in AI_WORDS_ZH:
            if word in l:
                ai_hits.setdefault(("中文 AI 词", word), []).append(i + 1)
        for word in AI_WORDS_EN:
            if re.search(r"\b" + re.escape(word) + r"\b", l, re.IGNORECASE):
                ai_hits.setdefault(("英文 AI 词", word), []).append(i + 1)
        for pat, desc in AI_PATTERNS:
            if re.search(pat, l):
                ai_hits.setdefault(("句式", desc), []).append(i + 1)

    for (kind, val), line_nums in sorted(ai_hits.items()):
        if len(line_nums) <= 3:
            warnings.append(f"AI 文风：{kind} '{val}' 出现于行 {line_nums}")
        else:
            warnings.append(
                f"AI 文风：{kind} '{val}' 出现 {len(line_nums)} 次"
                f"（首见行 {line_nums[0]}、之后还有 {len(line_nums)-1} 次）"
            )

    # --- 10b. 语言纯度警告（高频中英混搭模式、命中 → 警告）---
    # 见 phase4 文档「写作纪律」段「语言纯度（硬约束）」一节。
    # 跳过 `## 引用来源` 段（来源标题里的英文词不是 LLM 写作问题）+ 代码块 + 引用块。
    purity_hits = {}
    in_code_p = False
    in_ref_section_p = False
    for i, l in enumerate(lines):
        if re.match(r"^##\s+引用来源\s*$", l):
            in_ref_section_p = True
            continue
        if l.strip().startswith("```"):
            in_code_p = not in_code_p
            continue
        if in_code_p or in_ref_section_p or l.startswith(">"):
            continue
        for pat, desc in LANGUAGE_PURITY_PATTERNS:
            if re.search(pat, l, re.IGNORECASE):
                purity_hits.setdefault(desc, []).append(i + 1)

    for desc, line_nums in sorted(purity_hits.items()):
        if len(line_nums) <= 3:
            warnings.append(f"语言纯度：{desc} 出现于行 {line_nums}")
        else:
            warnings.append(
                f"语言纯度：{desc} 出现 {len(line_nums)} 次"
                f"（首见行 {line_nums[0]}、之后还有 {len(line_nums)-1} 次）"
            )

    # --- 11. claims.json grounding 检查（phase 3.5 落地后的报告必带）---
    # 与报告同名的 .claims.json 文件存在时校验 schema；不存在时只警告（旧报告允许）
    claims_path = p.with_name(p.stem + ".claims.json")
    if claims_path.exists():
        try:
            claims_raw = json.loads(claims_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            errors.append(f"claims.json JSON 解析失败：{e}")
            return errors, warnings

        if isinstance(claims_raw, list):
            errors.append("claims.json 是裸数组，应为 {\"claims\": [...]}")
            claims = claims_raw
        elif isinstance(claims_raw, dict):
            claims = claims_raw.get("claims", [])
            if not isinstance(claims, list):
                errors.append("claims.json 的 claims 字段不是数组")
                return errors, warnings
        else:
            errors.append("claims.json 格式无法识别")
            return errors, warnings

        hard_fail_count = 0
        unverified_count = 0
        soft_degrade_count = 0
        for idx, c in enumerate(claims):
            cid = c.get("claim_id", f"<index {idx}>")
            missing_keys = REQUIRED_CLAIM_KEYS - set(c.keys())
            if missing_keys:
                errors.append(f"claims[{cid}] 缺少字段：{', '.join(sorted(missing_keys))}")
                continue
            ctype = c.get("claim_type")
            if ctype not in VALID_CLAIM_TYPES:
                errors.append(f"claims[{cid}] claim_type 值无效：{ctype}（应为 {sorted(VALID_CLAIM_TYPES)} 之一）")
            gs = c.get("grounding_strength")
            if gs not in VALID_GROUNDING_STRENGTH:
                errors.append(f"claims[{cid}] grounding_strength 值无效：{gs}")
            da = c.get("degrade_action")
            if da not in VALID_DEGRADE_ACTIONS:
                errors.append(f"claims[{cid}] degrade_action 值无效：{da}")
            st = c.get("status")
            if st not in VALID_CLAIM_STATUS:
                errors.append(f"claims[{cid}] status 值无效：{st}")
            sids = c.get("source_ids")
            if not isinstance(sids, list):
                errors.append(f"claims[{cid}] source_ids 不是数组")
            elif gs in {"single-source", "multi-source"} and len(sids) == 0:
                errors.append(f"claims[{cid}] grounding_strength={gs} 但 source_ids 为空")
            # soft_degrade 必须有 degrade_phrasing、其他档必须为 null
            dp = c.get("degrade_phrasing")
            if da == "soft_degrade" and not dp:
                errors.append(f"claims[{cid}] degrade_action=soft_degrade 但 degrade_phrasing 为空")
            if da != "soft_degrade" and dp not in (None, ""):
                errors.append(f"claims[{cid}] degrade_action={da} 时 degrade_phrasing 必须为 null")
            # 统计
            if da == "hard_fail":
                hard_fail_count += 1
            elif da == "mark_unverified":
                unverified_count += 1
            elif da == "soft_degrade":
                soft_degrade_count += 1

        # hard_fail 是错误：phase 3.5 应已处理（升级或移除）、不应进入 phase 4
        if hard_fail_count > 0:
            errors.append(
                f"claims.json 有 {hard_fail_count} 条 hard_fail 状态的 claim 未处理——"
                f"phase 3.5 完成条件要求所有 hard_fail 必须升级或移除、否则不能进入 phase 4"
            )
        # mark_unverified / soft_degrade 是警告：读者应知道 grounding 强度被降级
        if unverified_count > 0:
            warnings.append(
                f"grounding 降级：{unverified_count} 条 claim 标记 mark_unverified——"
                f"应在报告 metadata 的 grounding 强度行显示这个数字"
            )
        if soft_degrade_count > 0:
            warnings.append(
                f"grounding 降级：{soft_degrade_count} 条 claim 走 soft_degrade（改写措辞）"
            )

    # --- 12. user_profile.json 检查（phase 1 输出、phase 4 hard call）---
    profile_path = p.with_name(p.stem + ".user_profile.json")
    if profile_path.exists():
        try:
            profile_raw = json.loads(profile_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            errors.append(f"user_profile.json JSON 解析失败：{e}")
            return errors, warnings

        if not isinstance(profile_raw, dict):
            errors.append("user_profile.json 应为对象、不是数组或其他类型")
        else:
            missing_pk = REQUIRED_PROFILE_KEYS - set(profile_raw.keys())
            if missing_pk:
                errors.append(f"user_profile.json 缺少字段：{', '.join(sorted(missing_pk))}")
            level = profile_raw.get("user_expertise_level")
            if level and level not in VALID_EXPERTISE_LEVELS:
                errors.append(
                    f"user_profile.json user_expertise_level 值无效：{level}（应为 {sorted(VALID_EXPERTISE_LEVELS)} 之一）"
                )
            # 4 个 array 字段必须是 list（哪怕是空数组）
            for arr_key in ("key_concerns", "known_terms", "unfamiliar_terms", "constraints", "avoid_topics"):
                if arr_key in profile_raw and not isinstance(profile_raw[arr_key], list):
                    errors.append(f"user_profile.json {arr_key} 不是数组")
            # decision_context 不能为空（phase 1 完成条件）
            dc = profile_raw.get("decision_context", "")
            if isinstance(dc, str) and not dc.strip():
                errors.append(
                    "user_profile.json decision_context 为空——phase 1 应追问到具体决策动作再完成"
                )
            # avoid_topics 中的话题在报告中不应出现
            avoid = profile_raw.get("avoid_topics", []) or []
            for topic in avoid:
                if isinstance(topic, str) and topic.strip() and topic in text:
                    warnings.append(
                        f"user_profile.json avoid_topics 中 '{topic[:40]}' 在报告正文出现——phase 1 用户明确说不需要研究这个方向"
                    )
            # unfamiliar_terms 中术语在报告首次出现位置应配类比（软警告、判断 "类比" 关键词在术语前后 100 字内出现）
            unfam = profile_raw.get("unfamiliar_terms", []) or []
            for term in unfam:
                if not isinstance(term, str) or not term.strip():
                    continue
                idx = text.find(term)
                if idx == -1:
                    continue  # 报告里没出现这个术语、跳过
                ctx = text[max(0, idx-20):idx+len(term)+100]
                if not re.search(r"约等于|相当于|类似|量级和|大概|差不多|比.{1,10}高|比.{1,10}低", ctx):
                    warnings.append(
                        f"user_profile.json unfamiliar_terms '{term}' 在报告首次出现位置未见类比说明（参见 phase4「类比强制」节）"
                    )

    # --- 13. report_thesis.json 检查（phase 3 末尾输出、phase 4 按它组织报告）---
    thesis_path = p.with_name(p.stem + ".report_thesis.json")
    if thesis_path.exists():
        try:
            thesis_raw = json.loads(thesis_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            errors.append(f"report_thesis.json JSON 解析失败：{e}")
            return errors, warnings

        if not isinstance(thesis_raw, dict):
            errors.append("report_thesis.json 应为对象")
        else:
            missing_tk = REQUIRED_THESIS_KEYS - set(thesis_raw.keys())
            if missing_tk:
                errors.append(f"report_thesis.json 缺少字段：{', '.join(sorted(missing_tk))}")
            # punchline 必须出现在报告核心结论 + 主线复述与回扣两处
            punchline = thesis_raw.get("punchline", "")
            if isinstance(punchline, str) and punchline.strip():
                count = text.count(punchline)
                if count == 0:
                    errors.append(
                        f"report_thesis.json punchline '{punchline[:40]}' 未在报告中出现——"
                        f"phase 4 必须按 thesis 组织报告、punchline 至少出现在核心结论 + 主线复述与回扣两处"
                    )
                elif count == 1:
                    warnings.append(
                        f"report_thesis.json punchline 在报告中只出现 1 次——按 phase 4 契约应在核心结论 + 主线复述与回扣段各出现一次"
                    )
            # key_judgments 必须 3-5 条
            kj = thesis_raw.get("key_judgments", [])
            if isinstance(kj, list) and (len(kj) < 3 or len(kj) > 5):
                warnings.append(
                    f"report_thesis.json key_judgments 数量 {len(kj)} 超出 3-5 范围——少于 3 条说明判断不足、多于 5 条说明没合并"
                )
            # 4 个 array 字段类型检查
            for arr_key in ("key_judgments", "key_assumptions", "thesis_chain"):
                if arr_key in thesis_raw and not isinstance(thesis_raw[arr_key], list):
                    errors.append(f"report_thesis.json {arr_key} 不是数组")

    return errors, warnings


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("用法：py validate_report.py <report.md>")
        sys.exit(1)
    errs, warns = validate(sys.argv[1])
    if warns:
        print(f"⚠ {len(warns)} 个警告（不阻断通过、但应人工复查 AI 文风 / 语言纯度）：")
        for w in warns:
            print(f"  ! {w}")
    if errs:
        print(f"发现 {len(errs)} 个问题：")
        for e in errs:
            print(f"  x {e}")
        sys.exit(1)
    else:
        if warns:
            print("OK 格式验证通过（含警告）")
        else:
            print("OK 格式验证通过")
        sys.exit(0)
