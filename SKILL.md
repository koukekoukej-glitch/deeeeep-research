---
name: deeeeep-research
description: |
  端到端深度研究——从接收研究需求到交付完整报告。
  收到研究类查询时激活：「深度研究」「帮我调研 X」「比较 X vs Y」「X 的最新进展」
  「X 是否安全/有效」「综述 X 领域」「state of the art」「帮我搞清楚 X」等。
  当用户问的问题需要系统性地从多个来源收集、交叉验证、综合分析才能回答时，用这个 Skill。
  不适用于：简单事实查询、代码调试、一两次搜索能回答的问题。
---

# Deep Research

## 路径约定

本 skill 自包含，所有运行时组件都在 skill 目录内。以下两个路径贯穿整个工作流程：

- **REPORTS_DIR** = 本 skill 目录下的 `reports/` 子目录（即 `~/.claude/skills/deeeeep-research/reports/`）。所有产出文件（`.md` 报告、`.sources.json`、`.user_profile.json`、`.claims.json`、`.report_thesis.json`、`.workflow.log`）都写到这里。如果 `reports/` 不存在，phase 4 写入前自动创建。
- **VIEWER_DIR** = 本 skill 自带的 `viewer/` 目录（即 `~/.claude/skills/deeeeep-research/viewer/`）。包含验证脚本 `validate_report.py`、本地浏览服务 `serve.py`、以及前端资源。

后续文档中所有 `REPORTS_DIR` 和 `VIEWER_DIR` 都指向上述路径。运行验证脚本和启动 viewer 服务时，使用这些路径的完整展开形式。

---

## 成功定义

产出一份让用户觉得有价值、信息可靠的研究报告。三个条件同时满足：

1. **问对了问题**——报告回答的是用户真正关心的问题，覆盖他关心的维度，不遗漏他在意的角度
2. **证据撑得住**——每个结论都有可追溯的来源支撑，用户能判断该信多少
3. **一遍读懂**——用户读一遍就能吸收要点，不用反复查术语或猜你的逻辑

## 核心约束

先确认用户真正想知道什么，然后系统地收集证据，最后用证据说话。不是把搜到的东西原样给用户——要判断找到的东西是否可信、是否相关、是否足够支撑结论。当证据不足时，说清"这个问题目前没有足够证据下结论"，而不是用流畅的语言掩盖空白。

---

## 工作流程（硬约束 · 四阶段顺序执行）

NEVER 跳过任何阶段。NEVER 把多个阶段合并成一步。NEVER 在没有完成当前阶段的情况下进入下一个阶段。每个阶段开始时必须读取对应的参考文档，按文档中的方法论执行。

如果用户明确要求跳过某阶段（如"不用那么复杂，直接写吧"），向用户说明该阶段的作用和跳过的风险，由用户确认后可跳过，但必须在报告 metadata 中标注跳过了哪个阶段。

```
Phase 1   需求对齐 ──→ references/phase1-needs-alignment.md
│                         └─ YMYL 命中时 → references/ymyl-protocol.md
│
Phase 2   数据收集 ──→ references/phase2-data-collection.md（调度器）
│                         ├─ 子 Agent 各读自己的方法论 → references/agents/{domain}.md
│                         └─ 子 Agent 按需参考 → references/source-authority.md · references/search-strategy.md
│
Phase 2.5 选择性深读 ─→ references/phase2.5-selective-deep-read.md
│                         （主 agent 从子 agent 返回的候选里选 8-12 个 URL 调 WebFetch 全读）
│
Phase 3   证据分析 ──→ references/phase3-evidence-analysis.md
│                         └─ YMYL 硬地板 → references/ymyl-protocol.md
│
Phase 3.5 claim 抽取与 grounding ─→ references/phase3.5-claims-grounding.md
│                         （Haiku NLI 判断每条强核查项是否被 source entail、四档降级）
│
Phase 4   报告生成 ──→ references/phase4-report-generation.md（自包含）
```

### Phase 1：需求对齐

**门控**：读取 `references/phase1-needs-alignment.md`，按其方法论与用户对齐研究目标。搞清用户到底要你研究什么、为什么要研究、研究结果要服务什么决策。这一步决定后面所有搜索的方向——搞错了后面全白跑。

**完成条件**：用户确认研究方向，或在用户授权下按合理假设推进。未完成不进入 Phase 2。

### Phase 2：数据收集

**门控**：读取 `references/phase2-data-collection.md`，按其调度逻辑派遣子 Agent。按领域和搜索方向并行搜索——同一领域内有多个独立搜索方向时，为每个方向各派一个子 Agent 并行工作，而不是让一个子 Agent 串行包办。每个子 Agent 带着领域专属的搜索策略和权威判断标准工作。子 Agent 返回结构化字段（含 key_quotes 原文片段）而非自由文本摘要——为 Phase 2.5 选择性深读和 Phase 4 原文引用提供素材。

**完成条件**：所有子 Agent 返回证据，或在超时/无结果时显式记录缺口。未完成不进入 Phase 2.5。

### Phase 2.5：选择性深读

**门控**：读取 `references/phase2.5-selective-deep-read.md`，从所有子 Agent 返回的候选 URL（典型 60-90 个）中按 relevance × tier × 跨子 Agent 共现 × status 排序、选 8-12 个最关键 URL 调用 WebFetch 全读。强制深读类别（YMYL 关键论据 / 含具体数字 / 跨子 Agent 矛盾的 URL）额外加入。

**完成条件**：8-12 个 URL 已 WebFetch、token 预算未超阈值（主 agent context 占用 ≤ 30%）、强制深读类别全部覆盖。未完成不进入 Phase 3。

### Phase 3：证据分析

**门控**：读取 `references/phase3-evidence-analysis.md`，按其方法论交叉验证。把收集到的原始证据整理成可靠的结论——识别哪些信息真正独立、哪些互相矛盾、每个结论的置信度有多高。

**完成条件**：每个子问题都有结论（包括"证据不足"也算结论）。未完成不进入 Phase 3.5。

### Phase 3.5：claim 抽取与 grounding

**门控**：读取 `references/phase3.5-claims-grounding.md`，从 phase 3 结论里抽出所有强核查项（数字 / 时间 / 人名 / 公司关系 / 引文 / URL / YMYL 结论 7 类）、用 Haiku 跑 NLI 判断是否被 source entail、按 4 档降级（hard_fail / soft_degrade / mark_unverified / drop）处理、写入 `claims.json` 供 phase 4 取值使用。范式是 grounding-only 而非 truth-finding——把"事实是否正确"转化为"是否被某个可追溯的 source entail"。

**完成条件**：claims.json 写入完成（10 字段全填）+ 所有 hard_fail claim 已处理（要么二次深读补上、要么从报告移除）+ token 预算不超过 phase 2 的 30%。未完成不进入 Phase 4。

### Phase 4：报告生成

**门控**：读取 `references/phase4-report-generation.md`，严格按其格式契约生成报告。把分析结论转化为用户能一遍读懂、觉得可靠的报告，写入 `REPORTS_DIR` 目录，并向用户交付报告文件链接和在线查看链接。

**完成条件**：报告 + sources.json 写入成功，角标一致性验证通过，两个链接已交付给用户。

---

## 反向回滚机制

不是所有自检失败都该原地修——某些失败的根因在前面的 phase、原地修只是把问题往后藏。下表规定每类失败的回退路径、重试上限、和总预算。**回退不是惩罚、是正确的工作方式**——一个 phase 的产出依赖前面 phase 的对齐质量、对齐质量不够就该回去补、不该硬撑。

### 回退矩阵

| 触发场景 | 当前 phase | 回退到 | 该路径重试上限 | 上限触达后的兜底 |
|---|---|---|---|---|
| phase 1 用户没明确 `decision_context`（user_profile.json 该字段为空） | phase 1 | 不回退、阻塞继续追问 | N/A | 用户明确说"你看着办" → 用工作假设填、metadata 标"phase 1 未完整对齐" |
| phase 2 全部子 agent 没返回任何 ≥ T3 候选 | phase 2 | 不回退、调整 query 重跑子 agent | **1 次** | 仍无候选 → metadata 标"该研究主题缺一手来源、报告退化为负结论说明" |
| phase 2.5 主 agent WebFetch 全部失败 | phase 2.5 | 回退 phase 2 调整子 agent 路由（换领域子 agent / 换语言） | **1 次** | 仍失败 → 用 phase 2 的 key_quotes 模式跑后续 phase、metadata 标"未做主 agent 二次深读" |
| phase 3 完备性自检关键子问题无结论 | phase 3 | 回退 phase 2.5 补深读特定 URL | **1 次** | 仍无结论 → 该子问题改"负结论说明"（搜了 X、Y、Z 未找到） |
| phase 3.5 `hard_fail` claim 二次深读补不上 | phase 3.5 | 不回退、从 claims.json 移除该 claim + 从 phase 4 报告移除依赖该 claim 的段落 | **1 次**（phase 3.5 内 hard_fail 二次深读上限） | 移除后 metadata 标"N 个 YMYL claim 因证据不足从报告移除" |
| phase 3.5 grounding rewrite 超过 2 次仍 unsupported | phase 4 | 回退 phase 3 重做证据分析（说明 phase 3 结论可能有 hallucination） | **1 次** | 仍 unsupported → 该段落保留 `[unverified]`、计入 metadata grounding 强度行的 U 计数 |
| phase 4 `user_profile.json` 字段调用违反硬约束（avoid_topics 出现 / unfamiliar_terms 没配类比 / decision_context 没回扣） | phase 4 | 不回退、当 phase 4 内部 rewrite | **2 次**（每次 rewrite 后 validate 重跑） | 仍违反 → metadata 标"phase 4 与 phase 1 user_profile 部分不对齐" |
| phase 4 `report_thesis.json` punchline 在报告中未出现 / decision_action 未在主线复述与回扣段最后一句 | phase 4 | 回退 phase 3 重新定 thesis（说明 phase 3 thesis 与 phase 4 写作脱节） | **1 次** | 仍不对齐 → metadata 标"phase 4 主线显式化未达成" |

### 总体预算（防无限循环）

**整个研究流程、所有回退动作总和不超过 3 次。** 第 4 次触发回退 → **强制完成**（不再回退、用当前最佳产出收口）+ metadata 必须标注"在 {N} 次回退后强制收口、可能存在以下质量损失：{具体列出}"。

预算管理：

- 每次回退在主 agent 工作日志（保存在 `REPORTS_DIR` 的 `.workflow.log` 文件）记录一行：`{timestamp} | from_phase={X} | to_phase={Y} | reason={...}`
- 进入新 phase 前先扫该 log、统计已用回退次数。已用 ≥ 3 次 → 不再回退、按当前 phase 的"上限触达后兜底"路径处理
- 单条回退路径的"该路径重试上限"和总预算独立——单条用满（如 phase 2 重跑 1 次）也不消耗总预算的额度（这是设计选择、避免在某条路径上卡死把总预算耗完）。但**总和不超过 3** 仍是硬约束

### 为什么必须有上限

LLM 对"回退-修复-验证"循环没有疲劳感、可以无限循环。如果不设上限、某些回退路径（如 grounding rewrite）会形成模型无法跳出的环——每次 rewrite 都觉得"再试一次会更好"、但实际质量不再提升。上限触达 + 强制收口 + metadata 显式标注"未达成项" = 让用户拿到一份**带已知瑕疵但可交付**的报告、好过等不到结果。

诚实告诉用户哪里没做到、比假装一切达标重要。

---

## 失败模式防御

以下错误贯穿所有阶段，始终保持警惕。

### 高危——直接损害用户利益

- **证据不足时给确定结论**：YMYL 话题中，证据确定性为"低"或"极低"时，NEVER 给出行动建议。说"证据不足"。
- **把转述当独立来源**：10 篇报道同一项研究 ≠ 10 重证据。必须追溯原始来源。
- **漏掉利益冲突**：药企资助的研究、厂商白皮书——不是独立证据，标注利益关系。
- **编造引用**：NEVER 根据记忆或推测编造 URL、DOI、论文标题或作者信息。每条引用的 URL 必须来自本次研究中通过搜索工具实际获取到的结果。搜索不到就标注"未能找到原始来源"。

### 中危——降低报告质量

- **只搜一种语言**：中文问题只搜中文或只搜英文，都会错过重要信息。
- **结论先行、证据后补**：先有倾向再找支持证据，忽略反面。每个结论主动搜反面证据。
- **过度引用弱来源**：有高质量来源时不要因为低质量来源更容易找到就大量用。
- **用"进一步研究"敷衍**：不说清缺什么、下一步查什么，"有待进一步研究"等于没说。
- **中英夹杂、可翻译的英文词不翻**：context（上下文）、cache（缓存）、prompt（提示词）、sub-agent（子代理）、verification（验证）、workflow（工作流）、benchmark（基准测试）、playbook（操作手册）、sandbox（沙箱）、compaction（压缩）这类普通词必须翻成中文、不能因为"AI 圈行话"就保留英文。豁免范围（公司名 / 产品名 / 文件名 / 代码标识符 / API SDK MCP 等业界稳定缩写 / 用户 phase 1 已确认的核心术语）按 phase4 写作纪律「语言纯度」节路由表处理。整段英文引用必须配紧邻中文翻译。

### 自检

每次出报告前：

- 是不是因为某个来源很知名就默认它可信了？知名 ≠ 对这个问题权威。
- 是不是忽略了和当前结论矛盾的证据？
- 是不是在用"听起来专业"作为可信度依据？只用可外部验证的信号。
- 正文中每个 [N] 都在 sources.json 中有完整条目吗？不允许占位符、编号跳跃、编号范围。
