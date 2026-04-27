# Phase 3.5：claim 抽取与 grounding

**目标**：从 phase 3 结论里抽出所有强核查项（数字 / 时间 / 人名 / 公司关系 / 引文 / URL / YMYL 结论 7 类）、对每条做 NLI grounding 判断、按"有据可查"的强弱分档处理（hard fail / soft degrade / mark unverified / drop）、把可核查的 claim 集合写入 `claims.json` 供 phase 4 取值使用。

**核心原则**：grounding-only 而非 truth-finding——把"事实是否正确"转化为"是否被某个可追溯的 source entail"。这是业界 FACTS Grounding / SAFE 的核心范式、可执行性比 truth-finding 高一个量级。LLM 没法判断"Harvey 估值 110 亿是否真的"、但能判断"这条数字是否被 source S012 entail"。

**关键约束**：phase 3.5 只对**强核查项**强约束、不对叙述性判断强约束——给 LLM 留判断空间。phase 4 写作时所有数字/日期/人名/引文必须按 `claim_id` 从 `claims.json` 取值、不允许 LLM 自己生成；但论证链、洞察、对比这些叙述性内容仍由 LLM 自由组织。

---

## claims.json schema（10 字段）

每条 claim 是 `claims.json` 数组里的一个对象。10 字段全部必填、缺字段或格式错误立刻报错并要求重填。

| 字段 | 类型 | 说明 |
|---|---|---|
| `claim_id` | string | 顺序编号 `C001` `C002`...、phase 4 引用此 ID 取值 |
| `claim_text` | string | claim 原文、**必须从 phase 3 结论逐字摘出、不重写不缩写** |
| `claim_type` | enum | 7 类之一：`valuation` / `date` / `person` / `company_relation` / `quote` / `url` / `ymyl_conclusion` |
| `source_ids` | array of string | 指向 `sources.json` 的 [n] 编号数组、**至少 1 个**；为空触发 unsupported |
| `grounding_strength` | enum | NLI 判断结果：`single-source`（只有 1 个 source entail）/ `multi-source`（≥ 2 个独立 source entail）/ `unsupported`（没有 source entail） |
| `as_of_date` | string | YYYY-MM-DD 格式、**复用**子 agent 11 字段同名字段、不重新发明。指数据/事件的实际时点、不是发布日期 |
| `status` | enum | `confirmed` / `rumored` / `estimated` / `outdated`、**复用**子 agent 11 字段同名字段 |
| `verification_notes` | string | NLI 判断依据备注（哪个 source 的哪段 entail 了这条 claim）。例："S012 第 3 段 'GIC + Sequoia 共同领投 2 亿美元' entail 估值 110 亿" |
| `degrade_action` | enum | 4 档之一：`hard_fail` / `soft_degrade` / `mark_unverified` / `drop`、由「降级策略」段决定 |
| `degrade_phrasing` | string \| null | `soft_degrade` 时改写后的措辞模板填这个字段；其他 3 档填 `null` |

**字段填写纪律**：

- `claim_text` 必须逐字从 phase 3 结论摘出——重写或缩写会让 NLI 判断对不上原文细节、grounding 结果不可信
- `as_of_date` 和 `status` 必须从子 agent 11 字段同名字段直接取值——不要让 LLM 重新推理一次
- `source_ids` 只能引用已经在 `sources.json` 出现的 [n] 编号——不允许凭空生成新 source
- `verification_notes` 不能空泛写"已核查"、必须具体到"S0XX 第 N 段 / 第 N 句 entail 了这条 claim"

---

## 第一步：claim 抽取

phase 3 结论里逐条扫强核查项、每条分配一个 `claim_id`、记录 `claim_text` 和 `claim_type`。

**7 类强核查项的判断依据**：

| claim_type | 触发条件 | 例 |
|---|---|---|
| `valuation` | 出现金额、估值、融资额、市占率、营收、利润等具体数字 | "Harvey AI 估值 110 亿美元" |
| `date` | 出现具体日期、年份、时间点（不含相对时间如"近期"） | "Harvey C 轮融资完成于 2026-03-25" |
| `person` | 出现具体人名 + 该人的具体身份/动作（不含泛指如"业内人士"） | "OpenAI CEO Sam Altman 在 X 帖中表示..." |
| `company_relation` | 出现两家公司之间的具体关系（投资 / 收购 / 合作 / 诉讼等） | "Sequoia 是 Harvey 本轮领投方" |
| `quote` | 出现引号内的原话引用 | "Lambert：'对 LLM 来说新发现和错误无法区分'" |
| `url` | 出现具体 URL 引用（不含一般化的 "见官方文档"） | 引用 https://harvey.ai/about 的"成立于 2022"主张 |
| `ymyl_conclusion` | 出现健康 / 财务 / 法律 / 安全等 YMYL 领域的具体建议结论 | "X 药对 Y 疾病有效"、"Z 投资策略风险等级低" |

**叙述性判断不抽**：

- "Harvey 是当前估值最高的 legal AI"（对比性判断、不是单点强核查项）
- "AI Agent 赛道正处于早期"（趋势性判断）
- "用户应该优先选 A 而非 B"（推荐性判断）

这些由 phase 4 写作纪律段管控、不进入 claims.json。

**抽取数量参考**：典型一份完整深度研究 30-80 条 claim。少于 20 条说明可能漏抽（去检查 phase 3 结论是不是只有定性判断、缺乏数字/事实支撑）；超过 100 条说明可能把叙述性判断当成强核查项了（重新过 7 类判断依据）。

---

## 第二步：NLI grounding（用 Haiku）

每条 claim 对所有候选 source 跑 NLI（自然语言推理）判断、确定哪些 source entail 这条 claim。

**模型选择**：用 `claude-haiku-4-5-20251001`、不要用 Sonnet。SAFE / MiniCheck 等业界研究显示小模型在 NLI 任务上和 GPT-4 一致率约 72%、成本 1/400。phase 3.5 总开销上限 36K token、Haiku 才能控住。

**NLI 输入格式**：

```
Premise（候选 source 的相关段落、来自 sources.json + key_quotes / phase 2.5 全文）
Hypothesis（claim_text）
```

**NLI 输出三档**：

- `entailment`：source 明确支持 claim → 计入 source_ids
- `neutral`：source 没说反、也没说支持 → 不计入 source_ids
- `contradiction`：source 直接反驳 claim → 不计入 source_ids、且在 verification_notes 标注"S0XX 与 claim 矛盾"

**grounding_strength 判定**：

| source_ids 数量 + 独立性 | grounding_strength |
|---|---|
| ≥ 2 个独立 source（按 `source-authority.md` 的"伪独立六脸"判断真独立）entail | `multi-source` |
| 1 个 source entail | `single-source` |
| 0 个 source entail（全部 neutral 或 contradiction） | `unsupported` |

**中文 NLI 准确度的兜底**：业界 SAFE 数据是英文场景、中文场景一致率可能显著低于 72%。Haiku 误判时走「降级策略」的 `mark_unverified`——读者仍能看到信息但带 [unverified] 标记、不删除。最终的兜底是 ymyl-protocol 的不可降级原则 + 用户拿到报告后的人工核查。

---

## 第三步：URL 类可达性检查

`claim_type = url` 的 claim 额外跑可达性检查（不只 NLI）。

- HTTP HEAD 请求该 URL、看返回状态码
- 200 → 通过
- 4xx / 5xx / 超时 → 跑 Wayback Machine fallback（查 https://web.archive.org/web/*/{url}、取最近一次快照）
- Wayback 也没快照 → grounding_strength 标 `unsupported`、`source_ids` 清空、走 `mark_unverified` 降级

URL 可达性检查不消耗 LLM token、是 HTTP 调用。

---

## 降级策略（4 档）

每条 claim 在 NLI grounding 完成后、按下表决定 `degrade_action`：

| 触发条件 | degrade_action | phase 4 行为 |
|---|---|---|
| `claim_type = ymyl_conclusion` + `grounding_strength = unsupported` | `hard_fail` | **触发 phase 2.5 二次深读**：主 agent 用更精准的 query 调 WebFetch 补找一手 source；补到 → 重跑 NLI、状态升级；补不到 → 从 phase 4 报告中**移除**这条 claim 及依赖它的段落 |
| `claim_type ∈ {valuation, company_relation}` + `grounding_strength = single-source` | `soft_degrade` | 改写为带"据 X 报道、截至 Y 日尚未由官方确认"的措辞、`degrade_phrasing` 字段填具体改写文本 |
| 其他 `claim_type` + `grounding_strength = unsupported`（且非 YMYL） | `mark_unverified` | phase 4 该 claim 角标旁加 `[unverified]`、报告 metadata 段列出所有 unverified claim 数量 |
| 弱核查项（如非 YMYL 的 person 引用、非关键的 date）+ `grounding_strength = unsupported` + 该 claim 不出现在核心结论或关键假设段 | `drop` | 静默从 phase 4 报告移除、不在最终报告出现 |

**hard_fail 触发的二次深读流程**（复用 phase 2.5 的 WebFetch 机制、不新建检索阶段）：

1. 主 agent 基于 claim_text 构造更精准的 query（例："Harvey AI 110 billion valuation Sequoia GIC official announcement 2026"）
2. 调 WebFetch 全读 1-3 个一手权威候选（按 `source-authority.md` 的 T1 级判断）
3. 把新拿到的 source 加入 `sources.json` + 重跑该 claim 的 NLI
4. 二次深读最多触发 1 次——仍不通过则该 claim 移除（避免无限循环）

**soft_degrade 措辞模板示例**：

| 原 claim_text | degrade_phrasing |
|---|---|
| "Harvey AI 估值 110 亿美元" | "据 [TheInformation] 报道、Harvey AI 估值约 110 亿、截至本报告日（2026-04-26）尚未由 Harvey 官方确认" |
| "Sequoia 是 Harvey 本轮领投方" | "据 [TheInformation] 报道、Sequoia 为本轮领投、单一来源、本报告日尚未独立交叉确认" |

**mark_unverified 角标格式**：

phase 4 报告中、unverified claim 的角标在原 [n] 之后追加 `[unverified]` 标记。例："Lambert 指出 LLM 无法区分新发现和错误[12][unverified]"。

报告末尾的 metadata 段列出本报告 unverified claim 总数 + 占比，例："本报告共 47 条强核查项、其中 3 条 [unverified]、占比 6.4%"。

---

## 成本控制与降级触发

**总开销上限**：phase 3.5 不超过 phase 2 的 30%（phase 2 子 agent 总开销约 120K token、phase 3.5 上限约 36K token）。

**单项开销估算**：

| 操作 | 单次 token | 典型场景总量 |
|---|---|---|
| claim 抽取（一次性扫 phase 3 结论） | ~3K | 1 次 = 3K |
| NLI 判断（每条 claim × 候选 source 数） | ~500 token/次（Haiku） | 50 claim × 5 候选 = 250 次 = ~125K Haiku token、折合 Sonnet 约 0.3K |
| URL 可达性检查 | 0（HTTP 调用） | 不计入 token |
| hard_fail 触发的二次深读 | phase 2.5 WebFetch 开销 | 最多 3 个 URL × 8K = 24K |

**超阈值降级**（复用 phase 2.5 已建立的 token 预算监控框架）：

- phase 3.5 总开销超 36K → 立即停止深度 NLI、剩余 claim 改用**轻量模式**：只检查 `source_ids` 字段是否非空（非空 → grounding_strength 默认 `single-source`、空 → `unsupported`）、不再跑 NLI 判断 entail 关系
- 轻量模式触发后、phase 4 报告 metadata 段必须显式标注"本报告 N 条 claim 在轻量模式下 grounded、未做完整 NLI 判断"

**降级优先级**：永远先放弃 `claim_type ∈ {date, person, quote}` 的深度 NLI（这三类相对低风险）、保留 `valuation` / `company_relation` / `ymyl_conclusion` 的完整 NLI 判断。

---

## 完备性自检

进入 phase 4 之前：

| 检查项 | 标准 |
|---|---|
| `claims.json` 文件存在且 schema 完整 | 10 字段全部填、无缺字段、无格式错误 |
| 所有 `hard_fail` claim 已处理 | 要么二次深读后升级、要么从报告移除——不允许 `hard_fail` 状态进入 phase 4 |
| `unsupported` claim 已分档 | 全部 `unsupported` claim 都有明确的 `degrade_action`（不允许 unsupported 但 degrade_action 为空） |
| `verification_notes` 非空泛 | 抽样检查 5-10 条 `multi-source` 或 `single-source` claim 的 notes、确认具体到 "S0XX 第 N 段 entail" 而非 "已核查" |
| 总开销在预算内 | phase 3.5 总 token ≤ 36K（或已显式触发轻量模式且 metadata 标注） |

完成 phase 3.5 后 → 读取 `references/phase4-report-generation.md` 开始报告生成。
