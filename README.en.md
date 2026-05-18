# Deep Research

An end-to-end deep-research Skill. A four-phase pipeline — needs alignment → multi-Agent parallel data collection → evidence cross-validation → report generation — that produces a structured research report with full citations, auto-rendered into the built-in reader page.

Works with [Claude Code](https://docs.anthropic.com/en/docs/claude-code) and any LLM framework that supports custom System Prompts, file I/O, shell execution, and sub-Agent dispatch.

[中文版 README](README.md)

![Report reader](screenshot.png)

---

## Features

- **Four-phase hard-constraint pipeline** — Needs alignment → data collection → evidence analysis → report generation. Phases cannot be skipped or merged
- **Parallel multi-Agent collection** — Sub-Agents are dispatched by domain (academic / engineering / commercial × Chinese / English), each carrying domain-specific search strategies and authority criteria
- **Five-tier source grading** — T1 first-party authoritative / T2 strong secondary / T3 specialist media / T4 general media / T5 user-generated. The same source can sit at different tiers for different questions
- **Evidence cross-validation** — Distinguishes independent sources from restatement chains (10 articles reporting the same study ≠ 10 pieces of evidence). Actively searches for counter-evidence
- **Built-in report reader** — Dark editorial-style web reader with synced table of contents, citation popovers, source-tier color coding, focus mode, and report library management
- **YMYL safety protocol** — Health / finance / legal topics auto-trigger stricter evidence thresholds and phrasing constraints
- **Citation integrity guarantee** — Every citation must come from an actual search result in this session. Fabricating URLs / DOIs / paper titles from memory is forbidden

---

## Report Reader

Generated reports are written to `reports/` and rendered through the built-in web reader.

**Reading experience:**
- Dark editorial-style typography, Newsreader + Noto Serif SC fonts
- Left-side TOC highlights the current section as you scroll
- Hovering a citation footnote pops up the source card: title, excerpt, URL, authority tier (T1–T5 color-coded)
- Focus mode: sidebars hide, current paragraph highlights, others fade
- Light / dark theme toggle, follows system preference

**Report management:**
- Top-left drawer lists all reports, searchable by title
- Shows modified time and word count
- Newly added reports show up on browser refresh; no restart needed

### Launching the Reader

```bash
# Windows
viewer/start.bat

# macOS / Linux
python3 viewer/serve.py
```

Visit `http://127.0.0.1:8765/viewer/`. The Skill auto-launches the service and prints the viewer link after report generation.

---

## Workflow

```
Phase 1  Needs alignment ── Confirm research goal, decompose sub-questions, identify what decision the conclusion serves
│
Phase 2  Data collection ── Dispatch sub-Agents in parallel by domain, each with its own search strategy
│
Phase 3  Evidence analysis ── Cross-validation, confidence estimation, contradiction identification
│
Phase 4  Report generation ── Structured report + sources.json → auto-rendered to the reader
```

### Phase 1: Needs Alignment

Confirm research direction with the user. When someone says "research X for me," there's usually a specific decision behind it — a selection, a risk judgment, an internal pitch. Understanding "X" without understanding the decision leads to off-angle search results. Restate rather than interrogate; use the fewest questions to clarify the most critical things.

### Phase 2: Data Collection

Parallel domain-grouped search. Six specialist sub-Agents:

| Sub-Agent | Coverage |
|-----------|----------|
| English academic | Scientific evidence, clinical research, academic reviews, theoretical analysis |
| Chinese academic | Chinese journals, China clinical trials, Chinese academic ecosystem |
| English engineering | Technical docs, open-source projects, RFC standards, technical communities |
| Chinese engineering | National / industry standards, Chinese tech blogs, Chinese tech communities |
| English commercial | SEC filings, industry reports, financial media, fact-checking |
| Chinese commercial | A-share / HK-share disclosures, official policy media, Chinese financial media |

Each sub-Agent reads its own domain methodology (`references/agents/{domain}.md`) and consults the source-authority guide and search-strategy docs as needed.

### Phase 3: Evidence Analysis

Turn raw evidence into reliable conclusions: identify which sources are truly independent, which contradict each other, and how confident each conclusion is. When evidence is insufficient, "insufficient evidence" is itself the conclusion — don't paper over the gap with fluent language.

### Phase 4: Report Generation

Produce the report and `sources.json` per the format contract, verify that body footnotes match source entries, auto-launch the reader, and deliver the viewer link.

---

## Failure-Mode Defenses

### High risk

- **Giving a definite conclusion when evidence is thin** — On YMYL topics with "low" certainty, no action recommendation is given
- **Treating restatement as an independent source** — Must trace back to the original
- **Missing conflicts of interest** — Pharma-funded studies and vendor whitepapers are not independent evidence
- **Fabricating citations** — Every URL / DOI must come from this session's search results. If not found, mark as "original source not located"

### Medium risk

- **Searching in only one language** — Searching only Chinese for a Chinese question (or vice versa) leaves gaps
- **Conclusion-first, evidence-later** — Actively search for counter-evidence for each conclusion
- **Hand-waving with "further research needed"** — If you don't specify what's missing or what to look up next, you've said nothing

---

## Project Structure

```
deeeeep-research/
├── SKILL.md                           # Core skill definition
├── references/
│   ├── phase1-needs-alignment.md      # Needs alignment methodology
│   ├── phase2-data-collection.md      # Data collection orchestration
│   ├── phase3-evidence-analysis.md    # Evidence analysis methodology
│   ├── phase4-report-generation.md    # Report generation format contract
│   ├── source-authority.md            # Five-tier authority guide
│   ├── search-strategy.md             # Search strategy
│   ├── ymyl-protocol.md               # YMYL safety protocol
│   └── agents/
│       ├── en-academic.md             # English academic sub-Agent
│       ├── zh-academic.md             # Chinese academic sub-Agent
│       ├── en-engineering.md          # English engineering sub-Agent
│       ├── zh-engineering.md          # Chinese engineering sub-Agent
│       ├── en-commercial.md           # English commercial sub-Agent
│       └── zh-commercial.md           # Chinese commercial sub-Agent
├── viewer/                            # Built-in report reader
│   ├── index.html
│   ├── app.js                         # Render engine (Markdown → interactive page)
│   ├── styles.css
│   ├── serve.py                       # Local HTTP server + dynamic manifest
│   ├── start.bat                      # Windows launcher
│   ├── validate_report.py             # Report format validator
│   └── lib/
│       ├── markdown-it.min.js
│       └── markdown-it-anchor.umd.js
└── reports/                           # Report output directory
```

---

## Installation

```bash
git clone https://github.com/koukekoukej-glitch/deeeeep-research.git ~/.claude/skills/deeeeep-research
```

Claude Code auto-detects trigger conditions. You can also load `SKILL.md` as a System Prompt in other frameworks.

### Triggering

Natural-language triggers:

```
> Research X for me
> Compare X vs Y
> Latest progress on X
> Is X safe / effective?
```

---

## Design Principles

1. **Phases are not skippable** — Four phases execute in order, each with explicit completion and gating conditions
2. **Domain specialization** — Sub-Agents split by domain outperform a single general Agent searching everywhere
3. **Evidence before conclusion** — Collect first, judge later. Actively search for counter-evidence. No conclusion-first thinking
4. **Attribute uncertainty to evidence** — Say "the evidence doesn't sufficiently support X," not "I'm not sure"
5. **Traceability** — Every conclusion traces back to specific sources so the reader can judge how much to trust it

---

## License

[MIT](LICENSE)
