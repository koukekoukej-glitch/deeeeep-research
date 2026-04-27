# Phase 2.5：选择性深读

**目标**：从 phase 2 子 agent 返回的所有候选来源中、识别"会决定核心结论怎么写"的少数 URL 进行全文深读、让主 agent 拿到原文细节、避免只看子 agent 的二手摘要。

**核心原则**：子 agent 已经把每条来源的原文片段（key_quotes）切出来了——但 key_quotes 只是 1-3 段、看不到全文上下文。主 agent 要做的是：从所有候选里挑 8-12 个对最终判断最重要的 URL、调 WebFetch 全读、把全文上下文加到 phase 3 / phase 4 的素材库里。

**这一步的关键约束**：不是把所有 URL 都全读——那样主 agent context 会爆。是基于 phase 2 已经做过的初步分级、有选择地深读"会决定核心结论怎么写"的少数 URL。

---

## 第一步：候选汇总

phase 2 各子 agent 返回的所有结构化记录汇总成一个候选池。典型场景：6 子 agent × 8-15 URL = 约 60-90 个候选。

每条候选都已带 11 字段（url / title / tier / key_quotes / summary / relevance_score / as_of_date / status / interest_conflict / fallback_condition + 领域专属字段如 citation / version_scope / content_type / core_index）。这些字段是排序和选择的依据。

---

## 第二步：去重

按 `domain` + `path` 去重——同一 URL 被多个子 agent 同时找到时只保留一条、interest_conflict / fallback_condition 字段做并集。

跨子 agent 共现的 URL（被 2 个以上子 agent 同时返回）单独标记"共现次数"——下一步排序时会用。

---

## 第三步：排序

候选按以下分数降序排列、分数高的优先深读：

```
score = relevance_score × tier_weight × cross_agent_bonus × status_penalty
```

| 因子 | 取值 |
|---|---|
| `relevance_score` | 子 agent 给的 0.0-1.0 相关度 |
| `tier_weight` | 一手权威 = 1.0 / 强二手 = 0.8 / 灰色一手 = 0.6 / 聚合转述 = 0.3 |
| `cross_agent_bonus` | 1 个子 agent 返回 = 1.0 / 2 个 = 1.3 / 3 个及以上 = 1.5（跨子 agent 共现 = 多角度认为重要） |
| `status_penalty` | confirmed = 1.0 / estimated = 0.9 / rumored = 0.6 / outdated = 0.4 |

不需要写程序计算——主 agent 心算或粗排即可、关键是排序方向对。

---

## 第四步：选择 8-12 个深读

按排序选前 8-12 个 URL、调用 WebFetch 全读。

**选择数量的判断**：

| 研究类型 | 推荐深读数 |
|---|---|
| 普通深度研究（5-7 个子问题） | 8-10 个 |
| 大型综述（8+ 子问题、跨多语言/多领域） | 10-12 个 |
| 快速核查 / 仅事实查询 | 4-6 个、或跳过本阶段 |

**强制深读的类别**（不在 8-12 名额限制内、必须额外加）：

- YMYL 话题中、status = `rumored` 或 `estimated` 但被引用作为关键论据的 URL → 必须全读后再决定是否使用
- 任何引用了具体数字（融资额、估值、市占率、临床试验结果、性能 benchmark 等）的 URL → 必须全读核对原文
- 跨子 agent 矛盾的 URL（A 子 agent 标 confirmed、B 子 agent 标 rumored）→ 双方都全读

---

## 第五步：合并素材库

WebFetch 完成后、主 agent 拿到**三层素材**：

1. **全文**（来自 WebFetch、8-12 个深读 URL）
2. **原文片段**（来自 phase 2 的 key_quotes、所有候选）
3. **子 agent 摘要**（来自 phase 2 的 summary、所有候选）

phase 3（证据分析）和 phase 4（报告生成）按以下优先级使用：

- **核心结论** + **关键假设** 必须基于"全文"或"原文片段"、不接受只用"摘要"作为唯一依据
- **背景信息** + **次要数据** 可以用"摘要"
- **需要原话引用**（YMYL 话题的当事人原话、监管文件原文、技术文档代码片段）必须取自 key_quotes 或 WebFetch 全文

---

## token 预算监控

phase 2.5 是主 agent 唯一一处大量 WebFetch 调用集中的地方。预算上限：

- 默认深读 8-12 个 URL、平均每个 5-10K token、合计约 50K
- 主 agent 二次深读后 context 占用应在 12-18%（基于 1M context 估算）

**降级触发**：

- 单个 URL 全文 > 30K token（典型场景：大型 PDF 论文、超长综述）→ 跳过该 URL 的全读、只用 key_quotes、在 phase 3 / phase 4 自检中标"该来源未全读"
- 8-12 个 URL 全读后总 context 占用 > 30% → 立即停止深读、剩余候选改用 key_quotes 模式
- WebFetch 连续 3 次失败（404 / 超时 / 反爬）→ 跳过该 URL、把 fallback_condition 字段补上"URL 不可达、原文未获取"

**降级优先级**：永远先放弃聚合转述（tier = 聚合转述）的全读、保留一手权威和强二手的全读。**强制深读类别**（YMYL 关键论据 / 含具体数字 / 跨子 agent 矛盾）即使触发降级也要全读、必要时跨多次 WebFetch 调用分段读。

---

## 完备性自检

进入 phase 3 之前：

| 检查项 | 标准 |
|---|---|
| 已选定深读 URL 数 | 8-12 个（或按研究类型调整后的数量） |
| 强制深读类别覆盖 | YMYL 关键论据 / 含具体数字 / 跨子 agent 矛盾的 URL 全部已 WebFetch |
| 高 relevance 候选 | 候选池中每个 relevance_score ≥ 0.7 的 URL 都已被深读 或 已显式记录"未深读、原因 X" |
| token 预算 | 未超阈值（主 agent context 占用 ≤ 30%） |

完成 Phase 2.5 后 → 读取 `references/phase3-evidence-analysis.md` 开始证据分析。
