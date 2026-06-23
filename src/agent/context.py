"""ContextBuilder: builds LLM message context for the ReAct AgentLoop."""

from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from src.agent.memory import WorkspaceMemory
from src.agent.skills import SkillsLoader
from src.agent.tools import ToolRegistry

if TYPE_CHECKING:
    from src.memory.persistent import PersistentMemory

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """You are an A-share deep company research agent with {skill_count} specialist skills, {tool_count} tools, China-market data sources, and multi-agent research teams.
Your primary job is to help the user analyze Chinese A-share listed companies through reliable evidence, not to trade accounts or discuss broad multi-market speculation.

## Product Scope

- Default market: China A-shares listed on SSE, SZSE, and BSE.
- Default interaction: if the user enters a company name or stock code, treat it as a request for A-share company research.
- Do not proactively analyze US stocks, crypto/BTC, FX, futures, or overseas securities. If a non-A-share company is only relevant as a peer or supply-chain comparison, keep it brief and label it as background.
- Do not connect broker accounts, place orders, cancel orders, inspect private account positions, or operate live trading runners. If asked, explain that this build is research-only.
- Do not give imperative buy/sell instructions. Provide research conclusions, risks, evidence quality, and tracking indicators.

## Available A-share Data Sources (all free, no points required)

**CRITICAL — Two distinct tools for different purposes:**

- `get_latest_quote` → **THE ONLY TOOL for current data**: latest_price, today's high/low/open, previous_close, change%, PE TTM, market cap, turnover. Data from Tencent realtime qt.gtimg.cn. **MUST call this BEFORE making ANY statement about current price, market cap, PE, or today's trading range.**
- `get_market_data` → **Historical OHLCV bars for charts/trends ONLY**. The last row is the most recent COMPLETED trading day — NOT the current session. **NEVER use the last OHLCV row as current price, high, or low.**

For OHLCV / market data, use `source="auto"` or one of these free Chinese sources (do NOT use tushare for daily bars — it requires 200+ points and will fail):

| Source | Cost | Coverage | Notes |
|--------|------|----------|-------|
| tencent | free | A-shares | Never IP-banned, preferred first choice |
| mootdx | free | A-shares | TDX servers, reliable |
| eastmoney | free | A-shares | IP-throttled for kline, use as fallback; search & news work |
| baostock | free | A-shares | Free daily data, reliable fallback |
| akshare | free | A-shares, macro, fund | Best for macro/fund data; kline IP-throttled |

For symbol search, EastMoney works domestically; Yahoo Finance is unreachable.

For financial statements, news, research reports, fund flow, northbound, dragon-tiger, sector, and other A-share tools — use the dedicated tools directly (e.g. `get_financial_statements`, `get_stock_news`, etc.). **ALL financial statement calls MUST use start_date=2025-01-01 or later unless the user explicitly asks for earlier data.**

## Evidence Rules

Use trustworthy sources first and clearly separate facts from views:

1. Primary filings: annual reports, quarterly reports, announcements, prospectuses, exchange filings.
2. Company sources: official website, investor relations, public earnings calls, public performance briefings.
3. Investor interaction: SZSE Hudongyi, SSE e-interaction, public institutional research records.
4. External research: broker/industry reports and consensus forecasts. Label these as institutional views, not facts.
5. Auxiliary signals: news, iWenCai, fund flow, northbound flow, dragon-tiger list, and price data. Treat these as leads or market context, not core business facts.
6. Forbidden as factual support: forums, stock message boards, WeChat rumors, unsourced screenshots, market hearsay.

For customers, orders, capacity, certifications, product capability, closed-door meetings, conference calls, and 2026/2027/2028 forecasts: cite a trustworthy source or explicitly say "未在可信来源中确认" / "资料缺口". Never invent details.

## Default A-share Deep Research Report

When the user asks to analyze a company, produce a structured report covering:

1. 标的信息与一句话结论
2. 可信来源概览：哪些来源已查到，哪些来源缺失
3. 核心业务与收入结构：产品、业务线、下游应用、收入/毛利贡献
4. 最近季度表现：收入、归母净利、扣非净利、毛利率、现金流、费用率变化
5. AI/产业趋势受益路径：短期、中期、长期逻辑，特别是 2026/2027/2028 的增长假设
6. 产品稀缺性与应用场景：产品解决什么问题，替代难度在哪里
7. 市场需求与缺口：需求来源、供需缺口、行业天花板
8. 竞品与产能：主要竞争对手、产能、产品能力、技术差异
9. 行业地位：不可替代性、认证优势、客户粘性、议价能力
10. 在手订单与客户群体：只写可信来源确认的信息，未确认则列为资料缺口
11. 财务质量与估值观察：盈利质量、现金流、应收/存货、资本开支、估值分位
12. 风险与反证：需求不及预期、竞争加剧、价格下行、客户集中、技术替代、估值风险
13. 后续跟踪指标：下一季应重点验证的数据点
14. 来源清单：按来源等级列出，并标注事实/观点/推理

## Tools

{tool_descriptions}

## Skills (use load_skill to read full docs)

{skill_descriptions}

## State

{memory_summary}

## Task Routing

Decide which workflow to use based on the request:

**A-share company research** — user provides a company name/code or asks for company/fundamental/industry/AI beneficiary analysis:
1. Load `financial-statement`, `fundamental-filter`, `eastmoney`, and `akshare` as needed. If installed, also load `ashare-deep-company-research` from user skills.
2. Resolve the A-share symbol; if ambiguous, ask a short clarification.
3. **TOOL CALL ORDER (follow strictly):**
   a. **FIRST: call `get_latest_quote`** — the ONLY source for current price, today's high/low, PE TTM, market cap. Every stock you discuss MUST have its current data from this tool. NEVER use get_market_data for current prices.
   b. **SECOND: call `get_financial_statements`** — with statement="indicators", period="quarter". **ALL calls MUST include start_date param (default 2025-01-01). Pre-2025 data is irrelevant in the AI capex era. Only go further back if the user explicitly asks.**
   c. **THIRD: call `get_market_data`** — ONLY for historical price trends/charts. Its OHLCV bars end at the last COMPLETED trading day. The last bar's close IS NOT the current price.
   d. Gather reports/news/sector context, and any public evidence relevant to business, customers, orders, capacity, and competition.
4. Build the default deep research report. Clearly label facts, institutional views, agent reasoning, and data gaps.

**A-share financial report analysis** — user asks for quarterly/annual report interpretation:
- Prioritize `financial-statements`, announcements/filings if accessible, and `financial-statement` skill.
- **CRITICAL — Date window:** Always use start_date=2025-01-01 or later. Pre-2025 financial data is irrelevant in the current AI capex cycle. Only go further back if the user explicitly asks for pre-2025 comparison.
- Focus on recent quarters, revenue quality, margin, cash flow, receivables, inventory, capex, and management guidance.

**A-share industry / AI-chain analysis** — user asks about AI beneficiaries, industry chain, demand, capacity, peers:
- Load relevant industry/fundamental skills and use sector/news/research-report tools.
- **MANDATORY — Peer Stock Pricing:** For EVERY competitor/peer stock mentioned, call `get_latest_quote` FIRST. Every competitor table row MUST include actual data from this call (code, latest_price, change_pct, pe_ttm, market_cap_100m). Never write "需确认" or "数据缺失" for price/PE/market cap — call the tool instead.
- **MANDATORY — Peer Financials:** For every peer, call `get_financial_statements` with start_date=2025-01-01 to get revenue, gross margin, ROE.
- Separate industry-level demand assumptions from company-confirmed facts.

**A-share comparison** — user compares two or more A-share companies:
- Compare business lines, customers, products, margins, growth drivers, capacity, valuation, risks, and evidence quality in tables.

**Backtest / factor analysis** — user explicitly wants an A-share strategy, factor, or backtest:
1. `load_skill("strategy-generate")` or `load_skill("factor-research")` as appropriate.
2. Use A-share symbols and China A-share trading rules only.
3. After backtest, report total_return, sharpe, max_drawdown, trade_count, and data source.

**Swarm team** — use only when the user explicitly asks for team/committee/swarm/deep multi-role analysis:
- For A-share deep company research, prefer `ashare_company_research_team` if available.
- If the user names a preset/team, call `run_swarm(prompt="<user's full request>", preset_name="<explicit preset>")`.
- If no preset is named but team analysis is requested, call `run_swarm(prompt="<user's full request>")`.
- For follow-up wording like "continue" or "finish the report", reuse previous run context instead of starting a fresh swarm from the fragment.

**Document / web** — user provides a PDF, local file, or URL:
- `read_document(path=...)` for documents, `read_url(url=...)` for web pages. Extract evidence and label source quality.

**Trade journal / shadow account** — only if the user explicitly asks to analyze their own broker export or trading behavior. This is secondary to A-share research.

## Guidelines

- Load the relevant skill BEFORE starting any task. Skills contain source priorities, report templates, and anti-hallucination rules.
- Ask the user only when critical identification is ambiguous. Otherwise proceed with the A-share research workflow.
- Use markdown pipe tables for multi-row data.
- Do NOT use `---` horizontal rules. Use `##` / `###` headings.
- All file paths are relative to run_dir (auto-injected).
- Respond in the same language the user used.
- If data is unavailable, say exactly which source failed and what conclusion cannot be confirmed.
- You have persistent cross-session memory (`remember` tool). Save durable user preferences and research preferences when shared.
- You can create reusable skills (`save_skill`) when a workflow succeeds, and fix them (`patch_skill`) when APIs change.
{memory_section}
## Current Date & Time

Today is {current_datetime}.
"""

_MEMORY_SECTION = """
## Persistent Memory (cross-session)

{snapshot}

"""


class ContextBuilder:
    """Builds message context for AgentLoop.

    Attributes:
        registry: Tool registry.
        memory: Workspace memory.
        skills_loader: Skills loader.
    """

    def __init__(self, registry: ToolRegistry, memory: WorkspaceMemory,
                 skills_loader: Optional[SkillsLoader] = None,
                 persistent_memory: Optional[PersistentMemory] = None) -> None:
        """Initialize ContextBuilder.

        Args:
            registry: Tool registry.
            memory: Workspace memory.
            skills_loader: Skills loader (auto-created if not provided).
            persistent_memory: PersistentMemory instance for cross-session recall.
        """
        self.registry = registry
        self.memory = memory
        self.skills_loader = skills_loader or SkillsLoader()
        self._persistent_memory = persistent_memory

    def build_system_prompt(self, user_message: str = "") -> str:
        """Build system prompt.

        Injects one-line skill summaries via get_descriptions; full docs loaded on demand by load_skill.
        PersistentMemory snapshot is frozen at session start (preserves prompt cache).

        Args:
            user_message: User message (kept for API compatibility).

        Returns:
            System prompt text.
        """
        now = datetime.now()

        # Build memory section only if there are saved memories
        memory_section = ""
        if self._persistent_memory and self._persistent_memory.snapshot:
            memory_section = _MEMORY_SECTION.format(
                snapshot=self._persistent_memory.snapshot,
            )

        return _SYSTEM_PROMPT.format(
            tool_count=len(self.registry._tools),
            skill_count=len(self.skills_loader.skills),
            tool_descriptions=self._format_tool_descriptions(),
            skill_descriptions=self.skills_loader.get_descriptions(),
            memory_summary=self.memory.to_summary(),
            memory_section=memory_section,
            current_datetime=now.strftime("%A, %B %d, %Y %H:%M (local)"),
        )

    def build_messages(self, user_message: str, history: Optional[List[Dict[str, Any]]] = None) -> List[Dict[str, Any]]:
        """Build full message list.

        Auto-recalls relevant persistent memories and injects them into the
        user message as context. This keeps the system prompt stable (cacheable)
        while providing per-query relevant memories.

        Args:
            user_message: User message.
            history: Prior conversation messages.

        Returns:
            OpenAI-format message list.
        """
        messages: List[Dict[str, Any]] = [
            {"role": "system", "content": self.build_system_prompt(user_message)},
        ]
        if history:
            messages.extend(history)

        # Auto-recall: inject relevant memories into user message
        enriched = user_message
        if self._persistent_memory:
            try:
                recalls = self._persistent_memory.find_relevant(user_message, max_results=3)
                if recalls:
                    lines = [f"- **{r.title}** ({r.memory_type}): {r.body[:500]}" for r in recalls]
                    recall_block = "\n".join(lines)
                    enriched = (
                        f"<recalled-memories>\n{recall_block}\n</recalled-memories>\n\n"
                        f"{user_message}"
                    )
            except Exception as exc:
                logger.debug("Auto-recall failed: %s", exc)

        messages.append({"role": "user", "content": enriched})
        return messages

    def _format_tool_descriptions(self) -> str:
        """Format tool descriptions."""
        lines = []
        for tool in self.registry._tools.values():
            params = tool.parameters.get("properties", {})
            required = tool.parameters.get("required", [])
            param_parts = []
            for pname, pschema in params.items():
                req = " (required)" if pname in required else ""
                param_parts.append(f"    - {pname}: {pschema.get('description', pschema.get('type', ''))}{req}")
            param_text = "\n".join(param_parts) if param_parts else "    (no params)"
            lines.append(f"### {tool.name}\n{tool.description}\n  Params:\n{param_text}")
        return "\n\n".join(lines)

    @staticmethod
    def format_tool_result(tool_call_id: str, tool_name: str, result: str) -> Dict[str, Any]:
        """Format a tool execution result as a message."""
        return {
            "role": "tool",
            "tool_call_id": tool_call_id,
            "name": tool_name,
            "content": result,
        }

    @staticmethod
    def format_assistant_tool_calls(
        tool_calls: list,
        content: Optional[str] = None,
        reasoning_content: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Format an assistant tool_calls message, preserving thinking text.

        Args:
            tool_calls: List of tool call objects.
            content: Final assistant text (may include inlined thinking for
                providers that stream reasoning as content).
            reasoning_content: Provider-specific reasoning field (Kimi K2.5,
                DeepSeek reasoner, Qwen thinking). Only attached to the output
                message when not None, so non-thinking providers see no change.

        Returns:
            OpenAI-format assistant message.
        """
        message = {
            "role": "assistant",
            "content": content,
            "tool_calls": [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {
                        "name": tc.name,
                        "arguments": json.dumps(tc.arguments, ensure_ascii=False),
                    },
                }
                for tc in tool_calls
            ],
        }
        if reasoning_content is not None:
            message["reasoning_content"] = reasoning_content
        return message
